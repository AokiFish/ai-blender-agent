"""确定性构建器注册表：按目标关键词匹配参数化建模脚本。

这些脚本是纯 bpy 代码，由 Agent 通过 execute_blender_code 执行，
结果可复现，避免小模型即兴写建模代码导致几何错乱。
"""

from blender_agent.builders.cat import SCRIPT as CAT_SCRIPT

BUILDERS: dict[tuple[str, ...], tuple[str, str]] = {
    ("猫", "cat", "猫咪"): ("cat", CAT_SCRIPT),
}


def match_builder(goal: str) -> tuple[str, str] | None:
    g = goal.lower()
    for keywords, builder in BUILDERS.items():
        if any(k.lower() in g for k in keywords):
            return builder
    return None
