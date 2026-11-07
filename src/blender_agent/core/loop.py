"""write-run-compare-revise 修订循环（借鉴 VIGA）+ 演进上下文记忆。

与 VIGA 的差异：
- 几何由确定性 builder 产出，循环只做"验证→定向修补"，不重做；
- 上下文记忆 = 计划摘要 + 每轮一行修订记录（滑窗注入）；
- 额外的跨运行进化层在 core/lessons.py（VIGA 没有）。
"""
import json
import os
import re
import shutil
import time

from blender_agent.core.types import ChatMessage
from blender_agent.core.verifier import verify, is_parse_error
from blender_agent.core.lessons import Lessons, format_lessons

MAX_ROUNDS = 3
SCORE_THRESHOLD = 8.0

# 多视角诊断渲染：3 个机位各渲一张，正面/45°/侧面
RENDER_VIEWS_SCRIPT = r'''
import bpy, math, os
from mathutils import Vector

WS = r"__WS__"
os.makedirs(os.path.join(WS, "diag"), exist_ok=True)

meshes = [o for o in bpy.data.objects if o.type == 'MESH' and o.name != "DiagCam"]
assert meshes, "场景没有网格"
mn = Vector((1e9, 1e9, 1e9)); mx = Vector((-1e9, -1e9, -1e9))
for o in meshes:
    for c in o.bound_box:
        w = o.matrix_world @ Vector(c)
        mn = Vector((min(mn.x, w.x), min(mn.y, w.y), min(mn.z, w.z)))
        mx = Vector((max(mx.x, w.x), max(mx.y, w.y), max(mx.z, w.z)))
center = (mn + mx) / 2
radius = max((mx - mn).length / 2, 1.0)

old_cam = bpy.context.scene.camera
cam_data = bpy.data.cameras.new("DiagCam"); cam_data.lens = 60
cam = bpy.data.objects.new("DiagCam", cam_data)
bpy.context.scene.collection.objects.link(cam)
old_render = bpy.context.scene.render.filepath
old_fmt = bpy.context.scene.render.image_settings.file_format
old_res = (bpy.context.scene.render.resolution_x, bpy.context.scene.render.resolution_y)
old_samples = getattr(getattr(bpy.context.scene, "eevee", None), "taa_render_samples", None)
bpy.context.scene.render.image_settings.file_format = 'PNG'
# 诊断图只给 VLM 看：640px + 16 采样，渲染耗时从 ~20s/张 压到 ~2s/张
bpy.context.scene.render.resolution_x = 640
bpy.context.scene.render.resolution_y = 640
if hasattr(bpy.context.scene, "eevee"):
    bpy.context.scene.eevee.taa_render_samples = 16

for name, az in (("front", 0), ("side45", -45), ("side90", -90)):
    a = math.radians(az)
    d = radius * 2.4
    cam.location = center + Vector((d * math.sin(a), -d * math.cos(a), radius * 0.35))
    direction = center - cam.location
    cam.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
    bpy.context.scene.camera = cam
    out = os.path.join(WS, "diag", f"{name}.png")
    bpy.context.scene.render.filepath = out
    bpy.ops.render.render(write_still=True)
    print(f"DIAG_VIEW {out}")

bpy.context.scene.camera = old_cam
bpy.context.scene.render.filepath = old_render
bpy.context.scene.render.image_settings.file_format = old_fmt
bpy.context.scene.render.resolution_x, bpy.context.scene.render.resolution_y = old_res
if old_samples is not None and hasattr(bpy.context.scene, "eevee"):
    bpy.context.scene.eevee.taa_render_samples = old_samples
bpy.data.objects.remove(cam, do_unlink=True)
print("RENDER_VIEWS_OK")
'''

PATCH_CONSTRAINTS = """允许修改：材质颜色/金属度/粗糙度/自发光、物体的位置/旋转/缩放（整体微调，不得删除部件）、
灯光强度与位置、相机构图、物体显隐。
绝对禁止：删除或重命名既有部件（Cat_ 前缀对象）、修改骨骼/骨架/MouthOpen/Blink 等 shape key、
修改网格拓扑（不得新建/删除顶点面）、整体重建。"""

PATCH_PROMPT = """你是 Blender 修订工程师（Generator）。质检员对当前渲染提出以下问题：

{issues_json}

【计划背景】{plan_summary}
【历史修订记录】
{memory}
【往期教训】
{lessons}

写一段能在 Blender 内用 bpy 直接执行的 Python 代码修复上述问题。约束：
{constraints}

只输出代码，不要解释。"""


def build_patch_prompt(issues: list[dict], memory: str, lessons: str,
                       plan_summary: str) -> str:
    return PATCH_PROMPT.format(
        issues_json=json.dumps(issues, ensure_ascii=False, indent=1),
        plan_summary=plan_summary, memory=memory or "（无）",
        lessons=lessons or "（无）", constraints=PATCH_CONSTRAINTS)


def extract_code(text: str) -> str:
    """模型常把代码包在 ```python 围栏里；剥出来再执行。"""
    m = re.search(r"```(?:python)?\s*(.*?)```", text, re.DOTALL)
    return (m.group(1) if m else text).strip()


def render_views(provider, workspace: str, ref_bytes: bytes | None = None) -> list[str]:
    """执行诊断渲染脚本，返回三张视角图的路径（可能不存在=渲染失败）。"""
    script = RENDER_VIEWS_SCRIPT.replace("__WS__", os.path.abspath(workspace))
    provider.sync_call_tool("execute_blender_code", {"code": script})
    d = os.path.join(workspace, "diag")
    return [os.path.join(d, f"{n}.png") for n in ("front", "side45", "side90")]


class ReviseLoop:
    def __init__(self, provider, workspace: str, lessons: Lessons | None = None,
                 llm=None, max_rounds: int = MAX_ROUNDS,
                 score_threshold: float = SCORE_THRESHOLD, views_fn=None):
        self.provider = provider
        self.workspace = workspace
        self.lessons = lessons or Lessons()
        self.llm = llm
        self.max_rounds = max_rounds
        self.threshold = score_threshold
        self.views_fn = views_fn
        self.plan_summary = "确定性构建器已产出完整角色资产"

    # -- helpers ---------------------------------------------------------
    def _traj_dir(self) -> str:
        d = os.path.join(self.workspace, "trajectory",
                         f"run_{time.strftime('%H%M%S')}")
        for sub in ("renders", "verifier", "codes"):
            os.makedirs(os.path.join(d, sub), exist_ok=True)
        return d

    @staticmethod
    def _read_png(path: str) -> bytes | None:
        try:
            if os.path.exists(path) and os.path.getsize(path) > 0:
                with open(path, "rb") as f:
                    return f.read()
        except OSError:
            pass
        return None

    # -- main loop -------------------------------------------------------
    def run(self, ref_image: bytes | None = None) -> dict:
        assert self.llm is not None, "ReviseLoop 需要 llm"
        tj = self._traj_dir()
        memory_lines: list[str] = []   # 演进上下文：每轮一行
        scores: list[float] = []
        final_score = 0.0
        verified = False               # 至少一轮拿到了可信的 verifier 结论

        for rnd in range(1, self.max_rounds + 1):
            fn = self.views_fn or render_views
            paths = fn(self.provider, self.workspace, ref_bytes=ref_image)
            main = next((b for b in map(self._read_png, paths) if b), None)
            if main is None:
                memory_lines.append(f"第{rnd}轮：诊断渲染失败，终止循环")
                break

            try:
                report = verify(self.llm, ref_image, main,
                                memory="\n".join(memory_lines[-3:]),
                                lessons=format_lessons(self.lessons))
            except Exception as e:  # noqa: 网络/限速失败不该毁掉整个任务
                memory_lines.append(f"第{rnd}轮：verifier 调用失败（{e!r}），终止循环")
                break
            if is_parse_error(report):
                # 拿不到可信评分就不要瞎改：止损比乱打补丁便宜
                memory_lines.append(f"第{rnd}轮：verifier 输出不可解析，终止循环")
                break
            verified = True
            scores.append(report.score)
            final_score = report.score
            with open(os.path.join(tj, "verifier", f"round{rnd}.json"),
                      "w", encoding="utf-8") as f:
                json.dump({"score": report.score, "summary": report.summary,
                           "issues": report.issues}, f, ensure_ascii=False, indent=2)
            shutil.copyfile(paths[0], os.path.join(tj, "renders", f"round{rnd}.png"))

            if report.score >= self.threshold or not report.should_continue:
                # 即使止损，也把"缺什么"沉淀成跨运行教训
                for issue in report.issues:
                    self.lessons.add(issue.get("feature", ""), issue.get("fix_hint", ""))
                break

            prompt = build_patch_prompt(report.issues,
                                        memory="\n".join(memory_lines),
                                        lessons=format_lessons(self.lessons),
                                        plan_summary=self.plan_summary)
            try:
                reply = self.llm.chat([ChatMessage(role="user", content=prompt,
                                                   images=([ref_image] if ref_image else []) + [main])])
            except Exception as e:  # noqa: 补丁生成失败 → 保留当前成果，不再重试
                memory_lines.append(f"第{rnd}轮：补丁生成失败（{e!r}），终止循环")
                break
            code = extract_code(getattr(reply, "content", "") or "")
            with open(os.path.join(tj, "codes", f"round{rnd}.py"),
                      "w", encoding="utf-8") as f:
                f.write(code)
            if not code.strip():
                memory_lines.append(f"第{rnd}轮：模型未产出代码，终止循环")
                break
            res = self.provider.sync_call_tool("execute_blender_code", {"code": code})
            memory_lines.append(
                f"第{rnd}轮：{report.to_memory(rnd)}；补丁{'已执行' if res.ok else '执行失败'}")
            for issue in report.issues:
                self.lessons.add(issue.get("feature", ""), issue.get("fix_hint", ""))

        with open(os.path.join(tj, "scores.json"), "w", encoding="utf-8") as f:
            json.dump({"scores": scores, "final_score": final_score,
                       "verified": verified}, f)
        return {"trajectory": tj, "scores": scores, "final_score": final_score,
                "verified": verified}
