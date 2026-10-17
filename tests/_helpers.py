"""Pytest-style helper for making small in-memory skin-like images."""
import io
import numpy as np
from PIL import Image


def make_skin_image(seed: int = 42, size: tuple = (300, 300)) -> Image.Image:
    """Generate a deterministic skin-like test image."""
    rng = np.random.default_rng(seed)
    w, h = size
    base = np.array([220, 170, 130], dtype=np.uint8)
    arr = np.tile(base, (h, w, 1)).astype(np.uint8)
    noise = rng.integers(-20, 20, size=(h, w, 3), dtype=np.int16)
    arr = np.clip(arr.astype(np.int16) + noise, 0, 255).astype(np.uint8)
    yy, xx = np.mgrid[0:h, 0:w]
    cy, cx = h // 2, w // 2
    dist = np.sqrt((yy - cy) ** 2 + (xx - cx) ** 2)
    mask = dist < min(w, h) * 0.2
    arr[mask] = [120, 70, 50]
    edge = (dist > min(w, h) * 0.18) & (dist < min(w, h) * 0.22)
    arr[edge] = [180, 120, 90]
    return Image.fromarray(arr).convert("RGB")


def image_to_jpeg_bytes(img: Image.Image, quality: int = 90) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()
