import os

from blender_agent.config import AgentConfig, load_config
from blender_agent.core.llm import LLMClient
from blender_agent.core.tool_provider import ToolProvider
from blender_agent.core.planner import Planner
from blender_agent.core.executor import Executor
from blender_agent.core.observer import Observer
from blender_agent.core.memory import Memory
from blender_agent.core.types import ChatMessage, Step
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

    def _pick_skill_steps(self, goal: str) -> list[Step]:
        for s in self.skills:
            if s.accept(goal):
                return s.build_steps(goal)
        return self.planner.plan(goal, scene=self._scene()).steps

    def run(self, goal: str, image: bytes | None = None) -> dict:
        os.makedirs(self.cfg.workspace, exist_ok=True)
        steps = self._pick_skill_steps(goal)
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
        for step in steps:
            res = self.executor.run_step(step, tools, history)
            history.append(ChatMessage(role="user", content=f"步骤结果：{res.content}"))
            self.memory.record(step, res)
            self.memory.maybe_checkpoint(self.provider,
                                        f"{self.cfg.workspace}/auto_checkpoint.blend")
            report = self.autocheck.run(step.goal, res)
            if not report["passed"]:  # reflect：把问题回灌，再跑一轮修复
                any_failed = True
                fix_step = Step(index=step.index, goal=f"修复：{'；'.join(report['issues'])}")
                self.executor.run_step(fix_step, tools, history)
        # 交付：把“保存工程 + 导出 fbx/glb”作为最后步骤，交给 LLM 用
        # execute_blender_code 完成（真实 mcp-for-blender 没有独立的 save/export 工具）
        steps += self.files.build_steps("导出 fbx glb",
                                        {"workspace": self.cfg.workspace, "base_name": "result"})
        deliverables = FileManagement.expected_paths("导出 fbx glb", self.cfg.workspace, "result")
        return {"goal": goal, "steps_log": self.memory.log,
                "deliverables": deliverables, "passed": not any_failed}

    def _scene(self) -> str:
        try:
            return SceneUnderstanding(self.provider).report()
        except Exception:  # noqa
            return ""
