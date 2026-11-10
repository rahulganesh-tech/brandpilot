import shutil

import pytest

from app.vision import ImageError, analyze_image, contrast_ratio, hex_to_rgb, load_image

from .images import poster

BRAND = ["#E8572A", "#121933", "#F6F4EE"]
needs_ocr = pytest.mark.skipif(shutil.which("tesseract") is None, reason="tesseract not installed")


def test_contrast_ratio_matches_wcag_examples():
    assert round(contrast_ratio((0, 0, 0), (255, 255, 255)), 1) == 21.0
    assert round(contrast_ratio((118, 118, 118), (255, 255, 255)), 1) == 4.5


def test_hex_parsing():
    assert hex_to_rgb("#E8572A") == (232, 87, 42)
    assert hex_to_rgb("fff") == (255, 255, 255)
    assert hex_to_rgb("nope") is None


def test_rejects_non_images():
    with pytest.raises(ImageError):
        load_image(b"definitely not an image")


@needs_ocr
def test_reads_text_and_flags_faint_text_and_off_brand_colour():
    r = analyze_image(poster([("Guaranteed results, guys!!", "#121933"), ("Only Rs 99 per bar", "#C8C8C8")], block="#1E90FF"), BRAND)
    assert "Guaranteed results" in r.text and "Only Rs 99 per bar" in r.text
    kinds = {f.type: f for f in r.findings}
    assert kinds["Low contrast text"].excerpt == "Only Rs 99 per bar"
    assert kinds["Low contrast text"].source_code == "WCAG 1.4.3"
    assert "#1E90FF" in kinds["Off-brand colour"].excerpt
    assert all(f.span_start == -1 and f.engine == "vision" for f in r.findings)


@needs_ocr
def test_on_brand_readable_image_is_clean():
    r = analyze_image(poster([("NutriCrunch has 20 g protein", "#121933")], block="#E8572A"), BRAND)
    assert r.findings == []
    # White on the brand orange is about 3.6:1, which passes for large text.
    assert analyze_image(poster([("White text on orange", "#FFFFFF")], bg="#E8572A"), BRAND).findings == []
