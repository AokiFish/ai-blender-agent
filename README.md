# AI Blender Agent

一个**能自主完成 3D 制作任务的 Agent**（不是只会执行 Python 的聊天机器人）。

## 设计方向

- **真 Agent，不是聊天机器人**：接收高层目标（文本或上传参考图），自主拆解 → 调用 Blender 工具执行 → 渲染截图自检 → 发现问题修复 → 交付可继续编辑的 `.blend` 与导出文件（FBX/GLB）。
- **不自研 Blender 控制协议**：只通过标准 MCP 客户端接入现成 Blender MCP Server（默认 `ahujasid/mcp-for-blender`，可选 `dcc-mcp-blender` / `bpy.dev` headless）。
- **模型层对 OpenAI 兼容免费模型开放**：OpenRouter / Agnes 等，只需切换 `base_url` + `api_key` + `model`。
- **多模态输入**：支持上传参考图（如猫咪照片）按图建模，图片作为多模态上下文传给 LLM。
- **口播角色专用**：图像驱动角色含**独立嘴部控制器**与**独立眼部控制器**，并支持**模块化贴图**（可单独替换贴图，为后期口播/口型同步视频准备）。
- **能力模块化**：每个能力是独立可注册 Skill，新增能力不改动核心循环。

## 能力清单

场景理解 · 自然语言建模 · 角色制作 · 图像驱动口播角色（嘴/眼控制器 + 模块化贴图）· 动画制作 · 自动检查 · 文件管理（保存/导出）。

## 调研结论（关键决策依据）

1. **不存在"官方 Blender MCP"**。社区事实标准是 `ahujasid/mcp-for-blender`（原 blender-mcp，33k★），自带视觉校验与资产/AI-3D 生成。
2. 其它可选：`dcc-mcp-blender`（200+ 类型化工具、内嵌 HTTP）、`BrightX/blender-mcp`（359 工具 + skill 系统）。
3. `bpy.dev` = 无界面 Blender 后端，走 reference→build→inspect 循环，适合批量/CI。

## 快速开始

详见实现计划 `docs/superpowers/plans/2026-11-07-ai-blender-agent.md`（含 18 个任务化步骤与测试）。

```bash
# 1. 安装依赖（隔离环境）
python -m venv .venv && .venv\Scripts\activate && pip install -e .[test]

# 2. 安装 Blender 插件（已在本地执行过，文件已就位）
#    uvx mcp-for-blender install-addon
#    → 已写入 C:\Users\Administrator\AppData\Roaming\Blender Foundation\Blender\3.6\scripts\addons\blender_mcp.py
#    你只需在 Blender 里【启用 + 启动 Server】（GUI 步骤，必须做）：
#      a. 打开 Blender → Edit → Preferences → Add-ons → 搜 “MCP for Blender” → 勾选启用
#      b. 3D 视图按 N → 侧栏 “MCP for Blender” → 点【Start MCP Server】（开 6688 端口）
#    ※ Agent 会用 uvx mcp-for-blender 自动拉起 MCP 服务端并连上这个端口，前提是上面的 Server 已启动。

# 3. 填入模型密钥（你已填 OpenRouter）
cp .env.example .env        # 编辑 .env：BLENDER_AGENT_API_KEY 与 BLENDER_AGENT_MODEL
                          # 默认 google/gemma-4-26b-it:free（OpenRouter 免费、多模态）

# 4. 运行
python -m blender_agent.cli run "给 Mimi 制作一个完整的 3D 角色，包含模型、材质、骨骼、面部表情控制器，以及基础走路动画"
python -m blender_agent.cli run "参考猫咪图片做口播角色，含独立嘴/眼控制器和可换贴图" --image cat.png

# 仅做场景自检
python -m blender_agent.cli check
```

> 也可换 Agnes 等任何 OpenAI 兼容端点：把 `.env` 里的 `BLENDER_AGENT_BASE_URL`、`BLENDER_AGENT_API_KEY`、`BLENDER_AGENT_MODEL` 改掉即可，无需改代码。

## 测试

```bash
pytest tests/ -q        # 22 passed, 1 skipped（skip 为需真实 Blender 的 live 用例）
```

无 Blender 也能跑完全部核心逻辑（Stub + FakeLLM）。

## 真实工具名（mcp-for-blender 实际暴露，代码只用这些）

`execute_blender_code`（跑 bpy 代码，保存/导出全靠它）、`look`（视口/相机看结果，返回图）、`get_scene_info`（场景摘要）、`generate_3d`（支持 `image` 参数，图生3D）、`search_assets` / `import_asset`、`get_addon_status` / `disable_telemetry` / `record_trajectory_feedback`。**注意：没有独立的 save/export/fbx/glb 工具**，保存 `.blend` 和导出 FBX/GLB 都由 LLM 通过 `execute_blender_code` 写 bpy 代码完成。

## 许可

MIT（与所采用的 Blender MCP 后端一致）。
