# 示例运行说明（EXAMPLE_RUN）

记录一条真实跑通示例的预期终端输出、产物路径，以及免费模型限速下的行为。

## 1. 文本目标：做完整 3D 角色

```bash
python -m blender_agent.cli run "给 Mimi 制作一个完整的 3D 角色，包含模型、材质、骨骼、面部表情控制器，以及基础走路动画"
```

### 期望行为
- Agent 调 `Planner` 拆解目标 → 命中 `Character` Skill → 生成 6 步管线：
  1. 建模角色身体与头部基础网格
  2. 分配皮肤/衣服/眼睛 PBR 材质
  3. 创建骨架（armature）
  4. 网格与骨架绑定（权重）
  5. 添加面部骨骼与表情控制器（shape keys / bone constraints）
  6. 渲染正面/侧面自检并修复
- 每步由 `Executor` 调 Blender MCP 工具执行，`Observer` 跑确定性几何检查（非流形边 / 零面积面 / 缺材质），发现问题回灌修复。
- 最后 `FileManagement` 保存 `result.blend` 并导出 `result.fbx` / `result.glb`。

### 期望产物（`BLENDER_AGENT_WORKSPACE`，默认 `./workspace`）
- `result.blend` —— 可继续编辑的工程
- `result.fbx` / `result.glb` —— 导出文件
- `auto_checkpoint.blend` —— 每 3 步一次的检查点（防中断丢失）

### 期望终端输出
```
完成 步骤 6 个，交付：['./workspace/result.blend', './workspace/result.fbx', './workspace/result.glb']
```

## 2. 图片目标：按猫咪照片做口播角色

```bash
python -m blender_agent.cli run "参考猫咪图片做口播角色，含独立嘴/眼控制器和可换贴图" --image cat.png
```

### 期望行为
- 参考图 `cat.png` 以多模态上下文（OpenAI `image_url`）注入，后续每步 LLM 都能看到。
- 命中 `TalkingHead` Skill（图片/口播/猫 + 角色语义双重匹配，排在 `Character` 之前优先命中）→ 7 步管线：
  1. 参考图片建模头部与身体基础网格
  2. 模块化材质槽（皮肤/毛发/眼睛 PBR），便于后期换贴图
  3. 创建骨架并绑定（含头部骨骼）
  4. **独立嘴部控制器**：口型 shape key（张嘴/嘴角）+ 骨骼，导出后仍可控
  5. **独立眼部控制器**：眼球看向骨骼 + 眨眼 shape key
  6. 独立 UV 展开 + 可替换贴图材质槽（模块化）
  7. 渲染正面/口型/眼神视图自检并修复

### 为何适合口播视频
- 独立嘴/眼控制器 → 后期在 AE / Blender 里做口型同步、眨眼、视线跟随，不耦合身体动画。
- 模块化贴图 → 可单独替换贴图换装/换脸，不动几何。

## 3. 免费模型限速预期

默认 `google/gemma-4-26b-it:free` 的 `:free` 变体限制约 **20 次/分、50 次/天**。
- 多轮 agent 循环（规划 + 每步若干工具轮次 + 自检）会快速消耗额度，预计单次复杂任务耗时数分钟到更久，并触发 `LLMClient` 内置退避重试。
- **开发/调试建议**：用付费低价或本地模型；免费模型仅做演示。换端点只需改 `.env` 三项，无代码改动。
