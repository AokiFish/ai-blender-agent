"""图片压缩 + 特征缓存 的测试。"""
from blender_agent.core.images import shrink_image


def _png_bytes(w, h, color=(200, 120, 60)):
    import io
    from PIL import Image
    img = Image.new("RGB", (w, h), color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_shrink_downscales_large_png():
    big = _png_bytes(1600, 1200)
    small = shrink_image(big)
    assert len(small) < len(big)
    from PIL import Image
    import io
    out = Image.open(io.BytesIO(small))
    assert max(out.size) <= 640


def test_shrink_keeps_small_image_untouched():
    tiny = _png_bytes(200, 200)
    assert shrink_image(tiny) == tiny


def test_shrink_garbage_passthrough():
    assert shrink_image(b"not an image") == b"not an image"


def test_shrunk_image_is_valid_jpeg():
    big = _png_bytes(1024, 768)
    small = shrink_image(big)
    from PIL import Image
    import io
    img = Image.open(io.BytesIO(small))
    assert img.format == "JPEG"
