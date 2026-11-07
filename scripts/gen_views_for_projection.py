"""为贴图投影生成同姿态多视图（agnes i2i）。

与 viewgen.VIEW_PROMPTS 的差别：这里强制锁定原始姿态（趴卧、前爪并拢），
只允许相机绕轴旋转，否则侧视图会变成站姿，投影会严重错位。
"""
from __future__ import annotations

import base64
import os
import sys

sys.path.insert(0, r"D:/Mydata/WorkBuddy/AI-blender-agent/src")

from blender_agent.core import viewgen  # noqa: E402

POSE = ("the same animal, identical body pose (lying down with front paws stretched forward "
        "and tail curled to the side), identical accessories, identical colors and markings")

PROMPTS = {
    "side_right": POSE + ", photographed from the right side, 90 degree camera rotation, "
                  "orthographic side profile, plain light gray background (#b8b8b8), "
                  "soft even studio lighting, full body visible, no text",
    "side_left": POSE + ", photographed from the left side, 90 degree camera rotation, "
                 "orthographic side profile, plain light gray background (#b8b8b8), "
                 "soft even studio lighting, full body visible, no text",
    "back": POSE + ", photographed directly from behind, 180 degree camera rotation, "
            "tail and back of head visible, plain light gray background (#b8b8b8), "
            "soft even studio lighting, full body visible, no text",
}


def main() -> None:
    ref_path, out_dir = sys.argv[1], sys.argv[2]
    views = tuple(sys.argv[3].split(",")) if len(sys.argv) > 3 else ("side_right",)
    api = viewgen.default_api()
    if api is None:
        print("NO_API")
        return
    with open(ref_path, "rb") as f:
        ref = f.read()
    os.makedirs(out_dir, exist_ok=True)
    b64 = base64.b64encode(ref).decode()
    for view in views:
        try:
            url = api.post_image({
                "model": api.cfg.model,
                "prompt": PROMPTS[view],
                "image": "data:image/jpeg;base64," + b64,
                "n": 1,
                "size": api.cfg.size,
            })
            data = api.download(url)
            path = os.path.join(out_dir, f"{view}.png")
            with open(path, "wb") as f:
                f.write(data)
            print("VIEW_OK", view, path, len(data))
        except Exception as exc:  # noqa: BLE001
            print("VIEW_FAIL", view, type(exc).__name__, str(exc)[:160])


if __name__ == "__main__":
    main()
