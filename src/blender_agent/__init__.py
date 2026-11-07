"""AI Blender Agent —— 能自主完成 3D 制作任务的 Agent 编排层。

不重写 Blender 控制协议，只通过 MCP 客户端接入现成 Blender MCP Server，
用任意 OpenAI 兼容模型做推理与工具选择，跑 plan→act→observe→reflect 自驱循环。
"""

__version__ = "0.1.0"
