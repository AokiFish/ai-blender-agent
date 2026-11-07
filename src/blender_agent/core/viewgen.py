"""视图生成层：用图片模型（默认 agnes-image）从参考图生成多视角定妆图。

用途：
1) 给 Verifier 提供与参考图一致、背景干净的对照视图（比原始视频截图更适合比对）；
2) 给支持多图的 3D 后端（hyper3d/scenario）做重建输入；
3) 作为贴图投射的素材。

设计成最小依赖：只用 OpenAI 兼容的 POST {base}/images/generations（image 字段做 i2i），
失败逐视图降级，绝不阻断主流程。
"""
from __future__ import annotations

import base64
import os
from dataclasses import dataclass

VIEW_PROMPTS: dict[str, str] = {
    "front": "same character, front view, full body, standing symmetrically facing the camera, "
             "plain white background, soft even lighting, product turnaround sheet, no text",
    "side": "same character, side view, full body, plain white background, "
            "soft even lighting, product turnaround sheet, no text",
    "three_quarter": "same character, three-quarter view, full body, plain white background, "
                     "soft even lighting, product turnaround sheet, no text",
}
DEFAULT_VIEWS = ("front", "side", "three_quarter")


@dataclass
class ImageGenConfig:
    base_url: str = ""
    api_key: str = ""
    model: str = "agnes-image-2.5-flash"
    size: str = "1024x1024"
    timeout: float = 180.0

    def ready(self) -> bool:
        return bool(self.base_url and self.api_key and self.model)


class HttpImageAPI:
    """真实实现：OpenAI 兼容 /images/generations + 下载。"""

    def __init__(self, cfg: ImageGenConfig):
        self.cfg = cfg
        self._session = None

    @property
    def session(self):
        if self._session is None:
            import requests
            self._session = requests.Session()
        return self._session

    def post_image(self, payload: dict) -> str:
        url = self.cfg.base_url.rstrip("/") + "/images/generations"
        r = self.session.post(
            url,
            headers={"Authorization": f"Bearer {self.cfg.api_key}",
                     "Content-Type": "application/json"},
            json=payload,
            timeout=self.cfg.timeout,
        )
        r.raise_for_status()
        data = r.json()
        item = (data.get("data") or [{}])[0]
        if item.get("url"):
            return item["url"]
        if item.get("b64_json"):
            return "data:image/png;base64," + item["b64_json"]
        raise RuntimeError(f"image api returned no url: {str(data)[:200]}")

    def download(self, url: str) -> bytes:
        if url.startswith("data:"):
            return base64.b64decode(url.split(",", 1)[1])
        r = self.session.get(url, timeout=self.cfg.timeout)
        r.raise_for_status()
        return r.content


def default_api() -> HttpImageAPI | None:
    """从当前 LLM 配置派生图片模型配置（同 base_url/api_key，模型名可单独指定）。"""
    from blender_agent.config import load_config
    cfg = load_config()
    model = os.getenv("BLENDER_AGENT_IMAGE_MODEL", "agnes-image-2.5-flash")
    ig = ImageGenConfig(base_url=cfg.provider.base_url, api_key=cfg.provider.api_key, model=model)
    return HttpImageAPI(ig) if ig.ready() else None


def generate_views(ref_image: bytes, out_dir: str, views=DEFAULT_VIEWS,
                   api=None) -> list[str]:
    """参考图 → 多视角定妆图；单视图失败跳过，全失败返回 []。"""
    api = api or default_api()
    if api is None or not ref_image:
        return []
    os.makedirs(out_dir, exist_ok=True)
    b64 = base64.b64encode(ref_image).decode()
    paths: list[str] = []
    for view in views:
        prompt = VIEW_PROMPTS[view]
        try:
            url = api.post_image({
                "model": getattr(getattr(api, "cfg", None), "model", "agnes-image-2.5-flash"),
                "prompt": prompt,
                "image": "data:image/jpeg;base64," + b64,
                "n": 1,
                "size": getattr(getattr(api, "cfg", None), "size", "1024x1024"),
            })
            data = api.download(url)
            path = os.path.join(out_dir, f"{view}.png")
            with open(path, "wb") as f:
                f.write(data)
            paths.append(path)
        except Exception:  # noqa: 单视图失败不影响其他视图
            continue
    return paths
