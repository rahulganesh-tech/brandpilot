"""Builds test images in memory."""
from __future__ import annotations

import io

from PIL import Image, ImageDraw, ImageFont


def poster(lines: list[tuple[str, str]], bg: str = "#FFFFFF", block: str | None = None, size=(1200, 700)) -> bytes:
    img = Image.new("RGB", size, bg)
    d = ImageDraw.Draw(img)
    if block:
        d.rectangle((0, size[1] - 260, size[0], size[1]), fill=block)
    font = ImageFont.load_default(size=56)
    y = 60
    for text, colour in lines:
        d.text((60, y), text, fill=colour, font=font)
        y += 100
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()
