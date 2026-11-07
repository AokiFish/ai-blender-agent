"""抠背景：调用本地 Hunyuan3D venv（bria-rmbg）产出 RGBA npy，供 Blender 顶点色投影。

Blender 自带 Python 没有 PIL，所以图像解码放在这边完成，只把数组交给 Blender。
"""
from __future__ import annotations

import os
import subprocess

HUNYUAN3D_HOME = os.environ.get(
    "HUNYUAN3D_HOME", r"D:/Mytools/design/Blender2023/hunyuan3d"
)

_CUTOUT_PY = '''
import os, sys
ROOT = {root!r}
os.environ["REMBG_HOME"] = os.path.join(ROOT, "rembg")
sys.path.insert(0, os.path.join(ROOT, "Hunyuan3D-2"))
import numpy as np
from PIL import Image
from hy3dgen.rembg import BackgroundRemover
src, npy_out = sys.argv[1], sys.argv[2]
out = BackgroundRemover()(Image.open(src))
np.save(npy_out, np.array(out.convert("RGBA")))
print("CUTOUT_NPY_OK", npy_out)
'''


def make_cutout_npy(image_path: str, npy_path: str) -> str | None:
    """去掉背景并存成 RGBA npy；失败返回 None（调用方可以不带色）。"""
    py = os.path.join(HUNYUAN3D_HOME, "venv", "Scripts", "python.exe")
    if not os.path.isfile(py):
        return None
    script_path = os.path.join(HUNYUAN3D_HOME, "cutout_npy.py")
    with open(script_path, "w", encoding="utf-8") as f:
        f.write(_CUTOUT_PY.format(root=HUNYUAN3D_HOME))
    try:
        proc = subprocess.run(
            [py, script_path, os.path.abspath(image_path), os.path.abspath(npy_path)],
            capture_output=True, text=True, timeout=300, encoding="utf-8", errors="replace",
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if os.path.isfile(npy_path) and "CUTOUT_NPY_OK" in (proc.stdout or ""):
        return os.path.abspath(npy_path)
    return None
