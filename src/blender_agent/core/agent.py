import json
import os

from blender_agent.config import AgentConfig, load_config
from blender_agent.core.llm import LLMClient
from blender_agent.core.tool_provider import ToolProvider
from blender_agent.core.planner import Planner
from blender_agent.core.executor import Executor
from blender_agent.core.observer import Observer
from blender_agent.core.memory import Memory
from blender_agent.core.types import ChatMessage, Step, ToolResult
from blender_agent.skills.scene_understanding import SceneUnderstanding
from blender_agent.skills.character import Character
from blender_agent.skills.talking_head import TalkingHead
from blender_agent.skills.nl_modeling import NLModeling
from blender_agent.skills.animation import Animation
from blender_agent.skills.autocheck import AutoCheck
from blender_agent.skills.file_management import FileManagement


class Agent:
    def __init__(self, llm, provider, cfg: AgentConfig):
        self.llm, self.provider, self.cfg = llm, provider, cfg
        self.planner = Planner(llm)
        self.executor = Executor(llm, provider)
        self.observer = Observer(provider, llm if cfg.provider.vision else None)
        self.memory = Memory(checkpoint_every=3)
        # 越具体的 skill 越靠前，保证图片/口播/角色目标优先命中
        self.skills = [SceneUnderstanding(provider), TalkingHead(provider),
                       Character(provider), NLModeling(provider), Animation(provider)]
        self.autocheck = AutoCheck(self.observer)
        self.files = FileManagement(provider)

    @classmethod
    def from_parts(cls, llm, provider, workspace="/tmp/w"):
        cfg = load_config(); cfg.workspace = workspace
        return cls(llm, provider, cfg)

    @classmethod
    def from_config(cls, cfg: AgentConfig | None = None):
        cfg = cfg or load_config()
        llm = LLMClient(cfg.provider)
        from blender_agent.core.mcp_adapter import McpToolProvider
        provider = McpToolProvider(cfg.blender)
        return cls(llm, provider, cfg)

    def _pick_skill_steps(self, goal: str, has_image: bool = False) -> list[Step]:
        for s in self.skills:
            if s.accept(goal):
                return s.build_steps(goal, {"has_image": has_image})
        return self.planner.plan(goal, scene=self._scene()).steps

    def _look_screenshot(self):
        try:
            return self.provider.sync_call_tool("look", {})
        except Exception:  # noqa: stub / 工具缺失
            return None

    def _visual_qc(self, ref_image: bytes | None) -> bool:
        """把当前渲染与参考图喂给模型比对；不达标返回 False 触发修复轮。"""
        look = self._look_screenshot()
        if look is None or not look.images:
            return True  # 无截图能力时跳过视觉质检
        ask = ("第一张是参考图，第二张是当前 Blender 场景的渲染。"
               "判断角色是否达到可交付水平，硬性标准："
               "①能一眼认出是参考图中的角色；②有清晰可见的眼睛/鼻子/嘴几何；"
               "③颜色按部位正确分区（不是通体一色）。"
               "全部满足回复 PASS；否则列出缺失项（简短）。")
        imgs = [ref_image] + look.images if ref_image else list(look.images)
        reply = self.llm.chat([ChatMessage(role="user", content=ask, images=imgs)])
        return "PASS" in (reply.content or "").upper()

    def run(self, goal: str, image: bytes | None = None) -> dict:
        os.makedirs(self.cfg.workspace, exist_ok=True)
        steps = self._pick_skill_steps(goal, has_image=image is not None)
        history: list[ChatMessage] = []
        if image:  # 参考图存成文件，既能给 LLM 看，也能传给 generate_3d 的 image 参数
            ref_path = os.path.join(self.cfg.workspace, "reference.png")
            with open(ref_path, "wb") as f:
                f.write(image)
            history.append(ChatMessage(
                role="user",
                content=f"参考图已保存到 {ref_path}，可用 generate_3d 的 image 参数传入"
                        f"该路径进行图生3D建模；也可直接作为多模态参考。",
                images=[image]))
        tools = (self.provider.sync_list_tools()
                 if hasattr(self.provider, "sync_list_tools") else [])
        any_failed = False
        builder_ok = False

        # 确定性构建器优先：命中模板时先跑参数化建模脚本（几何/材质/控制器可复现），
        # 再由 LLM 只做检查与微调，避免小模型即兴写建模代码导致几何错乱。
        # 有参考图且模型支持视觉时：先 VLM 提取特征（颜色/斑纹/配饰）注入构建参数。
        from blender_agent.builders import match_builder
        builder = match_builder(goal)
        if builder and hasattr(self.provider, "sync_call_tool"):
            name, make = builder
            feats = None
            if image and self.cfg.provider.vision:
                from blender_agent.core.features import extract_features, CatFeatures
                cache = os.path.join(self.cfg.workspace, "features.json")
                if os.path.exists(cache):
                    # 缓存命中：同一参考图不重复做 VLM 特征提取（一次 ~50s）
                    with open(cache, encoding="utf-8") as f:
                        feats = CatFeatures.from_json(f.read())
                else:
                    feats = extract_features(self.llm, image)
                    with open(cache, "w", encoding="utf-8") as f:
                        json.dump(feats.to_params(), f, ensure_ascii=False, indent=2)
            script = make(feats.to_params() if feats else None)
            bres = self.provider.sync_call_tool("execute_blender_code", {"code": script})
            self.memory.record(Step(index=-1, goal=f"确定性构建器：{name}"), bres)
            builder_ok = bres.ok
            if bres.ok:
                feat_desc = (f"特征已按参考图提取并注入：{json.dumps(feats.to_params(), ensure_ascii=False)}"
                             if feats else "未提供参考图，使用默认特征")
                # 构建器已产出完整资产（几何/材质/骨架/控制器/相机全部由代码确定）。
                # 不再让 LLM 自由改写计划步骤；质量提升交给下方 verifier 驱动的修订循环。
                steps = []
                history.append(ChatMessage(role="user", content=(
                    f"已用确定性构建器 {name} 生成角色，包含头部/吻部/眼睛(巩膜+虹膜+瞳孔+高光)/"
                    "鼻/嘴(含舌头)/耳/胡须/身体/前爪/尾/项圈+铃铛+蝴蝶结，"
                    "以及 Cat_Armature(11 骨)、MouthOpen/MouthCorner 口型键、Blink 眨眼键、"
                    f"Eye_L/Eye_R 眼球骨骼。{feat_desc}。")))
                # VIGA 式 write-run-compare-revise 循环：多视角渲染 → 结构化对比 → 定向修补
                if self.cfg.provider.vision and self.llm is not None:
                    from blender_agent.core.loop import ReviseLoop
                    from blender_agent.core.lessons import Lessons
                    lessons = Lessons(path=os.path.join(
                        self.cfg.workspace, "lessons.json")).load()
                    loop = ReviseLoop(self.provider, self.cfg.workspace,
                                      lessons=lessons, llm=self.llm)
                    loop.plan_summary = (
                        f"确定性构建器 {name} 已产出完整角色资产；"
                        f"特征参数：{json.dumps(feats.to_params(), ensure_ascii=False)}"
                        if feats else f"确定性构建器 {name} 已产出完整角色资产")
                    try:
                        loop_out = loop.run(ref_image=image)
                    except Exception as e:  # noqa: 循环内任何异常都不该阻断交付
                        loop_out = {"scores": [], "final_score": 0.0,
                                    "verified": False, "trajectory": ""}
                        self.memory.record(Step(index=-2, goal="修订循环异常"),
                                           ToolResult(ok=False, content=repr(e)))
                    else:
                        self.memory.record(Step(index=-2, goal="write-run-compare-revise 修订循环"),
                                           ToolResult(ok=True, content=(
                                               f"评分序列 {loop_out['scores']}，"
                                               f"最终 {loop_out['final_score']}，"
                                               f"轨迹 {loop_out['trajectory']}")))
                    if loop_out["verified"] and loop_out["final_score"] < 5:
                        any_failed = True

        for step in steps:
            try:
                res = self.executor.run_step(step, tools, history)
            except Exception as e:  # noqa: 单步 LLM 超时不毁任务
                any_failed = True
                self.memory.record(step, ToolResult(ok=False, content=repr(e)))
                continue
            history.append(ChatMessage(role="user", content=f"步骤结果：{res.content}"))
            self.memory.record(step, res)
            self.memory.maybe_checkpoint(self.provider,
                                        f"{self.cfg.workspace}/auto_checkpoint.blend")
            report = self.autocheck.run(step.goal, res)
            if not report["passed"]:  # reflect：把问题回灌，再跑一轮修复
                any_failed = True
                fix_step = Step(index=step.index, goal=f"修复：{'；'.join(report['issues'])}")
                self.executor.run_step(fix_step, tools, history)
        # 视觉质检闭环：渲染 vs 参考图，不达标回炉修复（最多 2 轮）
        for round_no in range(2):
            if self._visual_qc(image):
                break
            any_failed = True
            if builder_ok:  # 构建器产物不做 LLM 自由改写（会破坏比例/构图），只标记不合格
                break
            fix = Step(index=90 + round_no, goal=(
                "视觉质检不达标，根据参考图与当前渲染的差距修复角色外观："
                "缺五官几何就补几何，颜色未分区就按面重新分配材质，"
                "修完必须用 look 重新确认"))
            res = self.executor.run_step(fix, tools, history)
            history.append(ChatMessage(role="user", content=f"修复轮结果：{res.content}"))
            self.memory.record(fix, res)
        # 交付：保存工程 + 导出 fbx/glb 是确定性操作，直接用固定脚本一次执行，
        # 不再让 LLM 生成代码（实测 5 个 LLM 步骤要 10 分钟）。失败才回退到 LLM。
        abs_ws = os.path.abspath(self.cfg.workspace)
        code = FileManagement.deliver_script(abs_ws, "result")
        dres = self.provider.sync_call_tool("execute_blender_code", {"code": code})
        self.memory.record(Step(index=95, goal="确定性交付：保存/导出"), dres)
        if not dres.ok:
            any_failed = True
            deliver_steps = self.files.build_steps(
                "导出 fbx glb", {"workspace": abs_ws, "base_name": "result"})
            for step in deliver_steps:
                res = self.executor.run_step(step, tools, history)
                history.append(ChatMessage(role="user", content=f"步骤结果：{res.content}"))
                self.memory.record(step, res)
                if not res.ok:
                    any_failed = True
        deliverables = FileManagement.expected_paths("导出 fbx glb", abs_ws, "result")
        return {"goal": goal, "steps_log": self.memory.log,
                "deliverables": deliverables, "passed": not any_failed}

    def _scene(self) -> str:
        try:
            return SceneUnderstanding(self.provider).report()
        except Exception:  # noqa
            return ""
