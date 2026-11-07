"""3D 生成后端层：可插拔的 image-to-3D 通道。

本层只做「编排」，真正的生成调用统一走 mcp-for-blender 的 generate_3d
（该工具内部已实现 tripo / hyper3d / meshy / hunyuan3d 的提交、轮询、导入）。
好处：换后端只改一个 provider 字符串；没有额度时整层优雅跳过，退回参数化构建器。

密钥不写进代码、不打印：configure_provider() 生成一段 bpy 代码，把 key 直接写进
Blender 场景属性（插件从那里读），调用方只在内存里传递。
"""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field

# provider -> 插件里对应的场景开关与密钥属性
_PROVIDER_PROPS = {
    "tripo": ("blendermcp_use_tripo", "blendermcp_tripo_api_key"),
    "hyper3d": ("blendermcp_use_hyper3d", "blendermcp_hyper3d_api_key"),
    "meshy": ("blendermcp_use_meshy", "blendermcp_meshy_api_key"),
    "hunyuan3d": ("blendermcp_use_hunyuan3d", "blendermcp_hunyuan3d_secret_id"),
}

SUPPORTED_PROVIDERS = tuple(_PROVIDER_PROPS)


def available_providers() -> tuple[str, ...]:
    return SUPPORTED_PROVIDERS


@dataclass
class Model3DRequest:
    provider: str = "auto"
    images: list[str] = field(default_factory=list)   # 本地绝对路径或 URL
    name: str = "Generated"
    prompt: str = ""                                  # 多图时可为空
    wait_seconds: int = 45
    max_polls: int = 40
    quality: str | None = None


def parse_job_handle(text: str) -> str | None:
    """从 generate_3d 的等待提示里取出 job handle。"""
    if not text:
        return None
    m = re.search(r"job\s*[=:]\s*['\"]?([A-Za-z0-9_\-]{2,})", text)
    return m.group(1) if m else None


def configure_provider(provider: str, api_key: str) -> str:
    """生成 bpy 代码：开启插件里的 provider 并写入密钥（返回代码，勿打印）。"""
    if provider not in _PROVIDER_PROPS:
        raise ValueError(f"unknown provider: {provider}")
    use_prop, key_prop = _PROVIDER_PROPS[provider]
    return (
        "import bpy\n"
        f"s = bpy.context.scene\n"
        f"s.{use_prop} = True\n"
        f"s.{key_prop} = {api_key!r}\n"
        f"print('PROVIDER_READY {provider}')\n"
    )


def generate_mesh(provider_mcp, req: Model3DRequest) -> str:
    """提交生成任务并轮询到完成；返回最终文本（成功含导入信息，失败以 ERROR 开头）。"""
    if not req.images:
        raise ValueError("generate_mesh needs at least one image")
    normalized = [p.replace("\\", "/") if not p.startswith("http") else p for p in req.images]
    args: dict = {
        "provider": req.provider,
        "name": req.name,
        "wait_seconds": min(int(req.wait_seconds), 45),
    }
    # generate_3d 只接受 prompt 或 image 二选一：多图时用第一张 + prompt 补充
    args["image"] = normalized[0]
    if len(normalized) > 1 and req.prompt:
        args["prompt"] = req.prompt
    if req.quality:
        args["quality"] = req.quality

    last = ""
    for _ in range(max(1, req.max_polls)):
        res = provider_mcp.sync_call_tool("generate_3d", args)
        text = (getattr(res, "content", "") or getattr(res, "error", "") or "").strip()
        if not getattr(res, "ok", True):
            return f"ERROR: {text}"
        if text.startswith("Error") or "API_" in text:
            return f"ERROR: {text}"
        if "SUCCEEDED" in text or "imported" in text.lower():
            return text
        job = parse_job_handle(text)
        if not job:
            return text or "ERROR: unknown generate_3d result"
        args = {"provider": req.provider, "name": req.name, "job": job, "wait_seconds": 45}
        last = text
        time.sleep(1.0)
    return f"ERROR: timeout, last={last[:200]}"


# ---------- local 后端：Hunyuan3D-2mini（自托管，无额度限制） ----------

HUNYUAN3D_HOME = os.environ.get(
    "HUNYUAN3D_HOME", r"D:/Mytools/design/Blender2023/hunyuan3d"
)
LOCAL_TIMEOUT_SECONDS = 900


def local_backend_available() -> bool:
    """本地 Hunyuan3D venv + runner 是否就绪。"""
    py = os.path.join(HUNYUAN3D_HOME, "venv", "Scripts", "python.exe")
    runner = os.path.join(HUNYUAN3D_HOME, "local_gen.py")
    return os.path.isfile(py) and os.path.isfile(runner)


@dataclass
class LocalMeshResult:
    output_path: str
    faces: int = 0
    verts: int = 0
    seconds: float = 0.0


def generate_mesh_local(
    image_path: str,
    output_path: str,
    steps: int = 30,
    octree_resolution: int = 256,
) -> LocalMeshResult:
    """本地 Hunyuan3D 推理：单图 -> glb。失败抛 RuntimeError（调用方决定回落）。"""
    import subprocess

    if not local_backend_available():
        raise RuntimeError("local hunyuan3d backend not installed")
    py = os.path.join(HUNYUAN3D_HOME, "venv", "Scripts", "python.exe")
    runner = os.path.join(HUNYUAN3D_HOME, "local_gen.py")
    proc = subprocess.run(
        [py, runner, os.path.abspath(image_path), os.path.abspath(output_path),
         str(steps), str(octree_resolution)],
        capture_output=True, text=True, timeout=LOCAL_TIMEOUT_SECONDS,
        encoding="utf-8", errors="replace",
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    for line in reversed(out.splitlines()):
        if line.startswith("SHAPE_DONE"):
            # SHAPE_DONE 170.4 s | faces: 332040 | verts: 166019
            try:
                secs = float(line.split()[1])
                faces = int(re.search(r"faces:\s*(\d+)", line).group(1))
                verts = int(re.search(r"verts:\s*(\d+)", line).group(1))
                return LocalMeshResult(os.path.abspath(output_path), faces, verts, secs)
            except (ValueError, AttributeError):
                break
    if proc.returncode != 0 or not os.path.isfile(output_path):
        tail = out.strip().splitlines()[-1][:200] if out.strip() else "no output"
        raise RuntimeError(f"local generation failed: {tail}")
    return LocalMeshResult(os.path.abspath(output_path))


def provider_from_env() -> tuple[str, str] | None:
    """读 .env 里的通用配置：BLENDER_AGENT_3D_PROVIDER / BLENDER_AGENT_3D_API_KEY。

    也兼容按厂商命名的变量（BLENDER_TRIPO3D_API_KEY 等），便于直接复用已有 key。
    """
    from blender_agent.config import load_config  # 触发 .env 加载

    load_config()
    provider = (os.getenv("BLENDER_AGENT_3D_PROVIDER") or "").strip().lower()
    key = os.getenv("BLENDER_AGENT_3D_API_KEY", "").strip()
    alias = {
        "tripo": ("BLENDER_TRIPO3D_API_KEY", "TRIPO_API_KEY"),
        "hyper3d": ("BLENDERMCP_HYPER3D_API_KEY", "HYPER3D_API_KEY"),
        "meshy": ("BLENDERMCP_MESHY_API_KEY", "MESHY_API_KEY"),
    }
    if not key and provider in alias:
        for name in alias[provider]:
            key = (os.getenv(name) or "").strip()
            if key:
                break
    if not provider or not key:
        return None
    return provider, key
