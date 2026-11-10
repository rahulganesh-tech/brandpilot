"""Image checks: read the text, check text contrast, and check brand colours.

- Text is read with Tesseract OCR and then goes through the same rule and AI checks as typed content.
- Contrast: every line of text is measured against WCAG 1.4.3 (4.5:1, or 3:1 for large text).
- Colours: strong colours that cover a real share of the image must be close to a brand colour.
"""
from __future__ import annotations

import io
from dataclasses import dataclass

from PIL import Image, ImageOps, UnidentifiedImageError

from .rules_engine import Finding

Image.MAX_IMAGE_PIXELS = 40_000_000  # refuse decompression bombs

MAX_SIDE = 1600
MIN_WORD_CONFIDENCE = 55
CONTRAST_NORMAL = 4.5
CONTRAST_LARGE = 3.0
LARGE_TEXT_SHARE = 0.06  # line taller than 6% of the image counts as large text
COLOUR_MIN_SHARE = 0.08
COLOUR_MAX_DISTANCE = 80
NEUTRAL_SPREAD = 30  # max(r,g,b) - min(r,g,b) below this = white, grey or black


class ImageError(ValueError):
    pass


@dataclass
class ImageReport:
    text: str
    findings: list[Finding]


def load_image(data: bytes) -> Image.Image:
    try:
        with Image.open(io.BytesIO(data)) as probe:
            probe.verify()
        img = Image.open(io.BytesIO(data))
        img = ImageOps.exif_transpose(img).convert("RGB")
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ImageError("That file isn't a readable PNG, JPEG or WebP image") from exc
    img.thumbnail((MAX_SIDE, MAX_SIDE))
    return img


def hex_to_rgb(value: str) -> tuple[int, int, int] | None:
    v = value.strip().lstrip("#")
    if len(v) == 3:
        v = "".join(c * 2 for c in v)
    if len(v) != 6:
        return None
    try:
        return int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16)
    except ValueError:
        return None


def rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    return "#{:02X}{:02X}{:02X}".format(*rgb)


def _channel(c: float) -> float:
    c = c / 255
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def luminance(rgb: tuple[int, int, int]) -> float:
    r, g, b = rgb
    return 0.2126 * _channel(r) + 0.7152 * _channel(g) + 0.0722 * _channel(b)


def contrast_ratio(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


# ---------- OCR ----------


@dataclass
class Line:
    text: str
    box: tuple[int, int, int, int]  # left, top, right, bottom


def _ocr_lines(prepared: Image.Image) -> list[Line]:
    import pytesseract

    try:
        data = pytesseract.image_to_data(prepared, output_type=pytesseract.Output.DICT, config="--psm 3")
    except pytesseract.TesseractNotFoundError as exc:
        raise ImageError("Text reading (OCR) isn't installed on this server") from exc

    lines: dict[tuple[int, int, int], list[int]] = {}
    for i, word in enumerate(data["text"]):
        if not word.strip():
            continue
        try:
            conf = float(data["conf"][i])
        except (TypeError, ValueError):
            conf = -1
        if conf < MIN_WORD_CONFIDENCE:
            continue
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        lines.setdefault(key, []).append(i)

    out = []
    for key in sorted(lines):
        idx = lines[key]
        words = " ".join(data["text"][i].strip() for i in idx)
        left = min(data["left"][i] for i in idx)
        top = min(data["top"][i] for i in idx)
        right = max(data["left"][i] + data["width"][i] for i in idx)
        bottom = max(data["top"][i] + data["height"][i] for i in idx)
        out.append(Line(words, (left, top, right, bottom)))
    return out


def _faint_text_mask(img: Image.Image) -> Image.Image:
    """Black wherever a pixel differs from the main background colour, so faint text becomes readable."""
    grey = img.convert("L")
    background = max(grey.getcolors(256 * 256) or [(0, 255)])[1]
    return grey.point(lambda v: 0 if abs(v - background) > 12 else 255)


def _overlap(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    if w <= 0 or h <= 0:
        return 0.0
    smaller = min((a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1])) or 1
    return w * h / smaller


def read_lines(img: Image.Image) -> list[Line]:
    """OCR twice: on the normal image, and on a mask that makes faint text dark. Merge the lines."""
    lines = _ocr_lines(ImageOps.autocontrast(img.convert("L"), cutoff=1))
    for extra in _ocr_lines(_faint_text_mask(img)):
        if not any(_overlap(extra.box, l.box) > 0.5 for l in lines):
            lines.append(extra)
    lines.sort(key=lambda l: (l.box[1], l.box[0]))
    return lines


def text_colours(img: Image.Image, box: tuple[int, int, int, int]) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    """Estimate (text colour, background colour) inside a line's box."""
    left, top, right, bottom = box
    pad = max(2, (bottom - top) // 4)
    crop = img.crop((max(0, left - pad), max(0, top - pad), min(img.width, right + pad), min(img.height, bottom + pad)))
    crop.thumbnail((300, 300))
    pixels = list(crop.getdata())
    pixels.sort(key=luminance)
    n = len(pixels)
    dark = pixels[: max(1, n // 10)]
    light = pixels[-max(1, n // 10) :]
    dark_c = tuple(sum(p[k] for p in dark) // len(dark) for k in range(3))
    light_c = tuple(sum(p[k] for p in light) // len(light) for k in range(3))
    # The background is the colour that covers more of the box.
    mid = luminance(pixels[n // 2])
    if abs(mid - luminance(light_c)) <= abs(mid - luminance(dark_c)):
        return dark_c, light_c
    return light_c, dark_c


def contrast_findings(img: Image.Image, lines: list[Line]) -> list[Finding]:
    findings = []
    for line in lines:
        if len(line.text) < 3:
            continue
        fg, bg = text_colours(img, line.box)
        ratio = contrast_ratio(fg, bg)
        large = (line.box[3] - line.box[1]) >= LARGE_TEXT_SHARE * img.height
        need = CONTRAST_LARGE if large else CONTRAST_NORMAL
        if ratio < need:
            findings.append(
                Finding(
                    type="Low contrast text",
                    severity="medium",
                    span_start=-1,
                    span_end=-1,
                    excerpt=line.text[:120],
                    why=(
                        f"Text colour {rgb_to_hex(fg)} on {rgb_to_hex(bg)} has a contrast of about {ratio:.1f}:1. "
                        f"{'Large' if large else 'Normal'} text needs at least {need:g}:1 so everyone can read it."
                    ),
                    source_code="WCAG 1.4.3",
                    fix=None,
                    engine="vision",
                )
            )
    return findings


# ---------- colours ----------


def dominant_colours(img: Image.Image, count: int = 8) -> list[tuple[tuple[int, int, int], float]]:
    small = img.copy()
    small.thumbnail((200, 200))
    q = small.quantize(colors=count, method=Image.Quantize.MEDIANCUT)
    palette = q.getpalette() or []
    total = small.width * small.height
    out = []
    for n, index in sorted(q.getcolors() or [], reverse=True):
        rgb = tuple(palette[index * 3 : index * 3 + 3])
        out.append((rgb, n / total))
    return out


def _distance(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    return sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5


def colour_findings(img: Image.Image, brand_colours: list[str]) -> list[Finding]:
    brand = [c for c in (hex_to_rgb(h) for h in brand_colours) if c]
    if not brand:
        return []
    off = []
    for rgb, share in dominant_colours(img):
        if share < COLOUR_MIN_SHARE or max(rgb) - min(rgb) < NEUTRAL_SPREAD:
            continue
        nearest = min(brand, key=lambda b: _distance(rgb, b))
        if _distance(rgb, nearest) > COLOUR_MAX_DISTANCE:
            off.append((rgb, share, nearest))
    if not off:
        return []
    listed = ", ".join(f"{rgb_to_hex(rgb)} ({share:.0%} of the image)" for rgb, share, _ in off[:3])
    palette = ", ".join(rgb_to_hex(b) for b in brand)
    return [
        Finding(
            type="Off-brand colour",
            severity="low",
            span_start=-1,
            span_end=-1,
            excerpt=listed,
            why=f"These colours aren't in the brand palette ({palette}). Closest brand colour: {rgb_to_hex(off[0][2])}.",
            source_code="Brand colours",
            fix=None,
            engine="vision",
        )
    ]


def analyze_image(data: bytes, brand_colours: list[str]) -> ImageReport:
    img = load_image(data)
    lines = read_lines(img)
    text = "\n".join(line.text for line in lines)
    findings = contrast_findings(img, lines) + colour_findings(img, brand_colours)
    return ImageReport(text=text, findings=findings)
