"""视觉输入压缩：大 PNG 直接喂 VLM 是延迟与限速的大头。"""
import io


def shrink_image(data: bytes, max_px: int = 640, quality: int = 80) -> bytes:
    """超过 max_px 的图等比缩到 max_px 并转 JPEG；失败原样返回。"""
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(data))
        w, h = img.size
        if max(w, h) <= max_px and len(data) < 150_000:
            return data
        img = img.convert("RGB")
        scale = max_px / max(w, h)
        img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))),
                         Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality)
        return buf.getvalue()
    except Exception:  # noqa: 非图片/无 PIL 都不阻断
        return data
