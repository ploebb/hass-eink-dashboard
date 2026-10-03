"""Tests for hinted text rendering."""

from __future__ import annotations

import io

from PIL import Image

from custom_components.eink_dashboard.render import render_dashboard
from custom_components.eink_dashboard.text_render import (
    TextStyle,
    split_text,
    style_from_config,
)

_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="40">'
    '<text x="5" y="20" font-family="Roboto" font-size="16"'
    ' font-weight="bold" fill="#000000">Hi &amp; Bye</text>'
    "</svg>"
)


def test_style_defaults_to_unhinted() -> None:
    """Hinted text is opt-in and falls back to Roboto for bad families."""
    assert style_from_config({}) == TextStyle()
    assert style_from_config({"font_family": "nope"}).family == "roboto"


def test_split_text_lifts_element() -> None:
    """Text is removed from the SVG and returned as an item."""
    svg, items = split_text(_SVG, TextStyle(family="dejavu", hinted=True))
    assert "<text" not in svg
    assert len(items) == 1
    assert items[0].text == "Hi & Bye"
    assert items[0].bold


def test_split_text_keeps_unsupported_glyphs_in_svg() -> None:
    """Text with glyphs missing from the font stays with resvg."""
    svg = _SVG.replace("Hi &amp; Bye", "\u6f22\u5b57")
    out, items = split_text(svg, TextStyle(family="dejavu", hinted=True))
    assert items == []
    assert "<text" in out


def test_hinted_render_has_only_solid_text_pixels() -> None:
    """With hinting, text pixels are pure black or white (no AA grays)."""
    widgets = [
        {
            "type": "heading",
            "heading": "Hello",
            "x": 0,
            "y": 0,
            "w": 200,
            "h": 60,
            "card_style": "none",
            "heading_style": "title",
        }
    ]
    cfg = {
        "width": 200,
        "height": 60,
        "hinted_text": True,
        "font_family": "dejavu",
        "text_size_delta": 2,
    }
    img = Image.open(io.BytesIO(render_dashboard(widgets, cfg))).convert("L")
    assert set(img.getdata()) <= {0, 255}
    assert 0 in set(img.getdata())
