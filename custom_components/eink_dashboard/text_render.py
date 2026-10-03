# Copyright 2026 Andreas Schneider
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Hinted, non-anti-aliased text rendering via FreeType (Pillow).

resvg draws unhinted outlines, so on a low-ppi panel with few gray
levels thin strokes drop out (no anti-aliasing) or get dithered into
patches (anti-aliasing).  Pillow's ``fontmode = "1"`` with the BASIC
layout engine runs FreeType's hinter and writes solid pixels only,
which is much crisper.

The widget SVG is split in two: every ``<text>`` element is lifted out
of the SVG (shapes still go through resvg) and drawn afterwards with
Pillow from its attributes.  Text that Pillow cannot reproduce (glyphs
missing from the chosen font, fill opacity) stays in the SVG and is
drawn by resvg as before.
"""

from __future__ import annotations

import contextvars
import functools
import html
import re
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

_FONTS_ROOT = Path(__file__).parent / "fonts"

# family -> (regular, medium, bold) file names below ``fonts/<dir>``.
# DejaVu has no medium cut, so medium maps to regular.
_FAMILIES: dict[str, tuple[str, tuple[str, str, str]]] = {
    "roboto": (
        "Roboto",
        ("Roboto-Regular.ttf", "Roboto-Medium.ttf", "Roboto-Bold.ttf"),
    ),
    "dejavu": (
        "DejaVu",
        ("DejaVuSans.ttf", "DejaVuSans.ttf", "DejaVuSans-Bold.ttf"),
    ),
    "ubuntu": (
        "Ubuntu",
        ("Ubuntu-Regular.ttf", "Ubuntu-Medium.ttf", "Ubuntu-Bold.ttf"),
    ),
}
DEFAULT_FONT_FAMILY = "roboto"
FONT_FAMILIES = tuple(_FAMILIES)


@dataclass(frozen=True)
class TextStyle:
    """Active text style for one dashboard render.

    Attributes:
        family: Key of ``_FAMILIES``.
        size_delta: Pixels added to every font size.
        hinted: Draw text with Pillow instead of resvg.
    """

    family: str = DEFAULT_FONT_FAMILY
    size_delta: int = 0
    hinted: bool = False


_style: contextvars.ContextVar[TextStyle | None] = contextvars.ContextVar(
    "eink_text_style", default=None
)


def style_from_config(config: dict) -> TextStyle:
    """Build the text style from display config options."""
    family = config.get("font_family", DEFAULT_FONT_FAMILY)
    if family not in _FAMILIES:
        family = DEFAULT_FONT_FAMILY
    return TextStyle(
        family=family,
        size_delta=int(config.get("text_size_delta", 0) or 0),
        hinted=bool(config.get("hinted_text", False)),
    )


def set_style(style: TextStyle) -> contextvars.Token[TextStyle | None]:
    """Activate ``style`` for the current context; returns a reset token."""
    return _style.set(style)


def reset_style(token: contextvars.Token[TextStyle | None]) -> None:
    """Restore the style that was active before ``set_style``."""
    _style.reset(token)


def get_style() -> TextStyle:
    """Return the text style active for the current render."""
    return _style.get() or TextStyle()


def font_path(family: str, medium: bool, bold: bool) -> Path:
    """Return the TTF path for a family and weight."""
    directory, files = _FAMILIES[family]
    idx = 2 if bold else 1 if medium else 0
    return _FONTS_ROOT / directory / files[idx]


@functools.cache
def hinted_font(
    family: str, size: int, medium: bool, bold: bool
) -> ImageFont.FreeTypeFont:
    """Load a font with the BASIC layout engine (FreeType hinting)."""
    return ImageFont.truetype(
        str(font_path(family, medium, bold)),
        max(1, size),
        layout_engine=ImageFont.Layout.BASIC,
    )


_TEXT_RE = re.compile(r"<text\b([^>]*)>(.*?)</text>", re.DOTALL)
_ATTR_RE = re.compile(r'([\w:-]+)\s*=\s*"([^"]*)"')
_HEX_RE = re.compile(r"^#([0-9a-fA-F]{6})$")


@dataclass(frozen=True)
class TextItem:
    """One ``<text>`` element reduced to what Pillow needs."""

    x: float
    y: float
    size: float
    medium: bool
    bold: bool
    anchor: str  # start / middle / end
    baseline: str  # alphabetic / central / hanging
    fill: tuple[int, int, int]
    text: str


def _weight(value: str | None) -> tuple[bool, bool]:
    """Map a font-weight attribute to ``(medium, bold)``."""
    if value in (None, "", "normal", "400"):
        return False, False
    if value in ("bold", "700", "800", "900"):
        return False, True
    if value in ("500", "600"):
        return True, False
    return False, False


def _glyph_bitmap(font: ImageFont.FreeTypeFont, ch: str) -> tuple:
    """Return a comparable (size, pixels) form of one rendered glyph."""
    _, _, right, bottom = font.getbbox(ch)
    canvas = Image.new("1", (max(1, int(right)), max(1, int(bottom))))
    ImageDraw.Draw(canvas).text((0, 0), ch, font=font, fill=1)
    return canvas.size, canvas.tobytes()


def _supported(font: ImageFont.FreeTypeFont, text: str) -> bool:
    """Return whether every non-space character has a real glyph."""
    probe = _glyph_bitmap(font, "\uffff")
    for ch in set(text):
        if ch.isspace():
            continue
        if _glyph_bitmap(font, ch) == probe:
            return False
    return True


def split_text(svg: str, style: TextStyle) -> tuple[str, list[TextItem]]:
    """Lift drawable ``<text>`` elements out of ``svg``.

    Args:
        svg: Widget SVG string.
        style: Active text style (used for glyph coverage checks).

    Returns:
        The SVG without the lifted elements, and the lifted items in
        document order.  Elements that cannot be reproduced are left in
        the SVG.
    """
    items: list[TextItem] = []

    def _lift(match: re.Match[str]) -> str:
        attrs = dict(_ATTR_RE.findall(match.group(1)))
        content = match.group(2)
        fill = _HEX_RE.match(attrs.get("fill", "#000000"))
        if "<" in content or fill is None or "fill-opacity" in attrs:
            return match.group(0)
        text = html.unescape(content).strip()
        medium, bold = _weight(attrs.get("font-weight"))
        size = float(attrs.get("font-size", "16"))
        font = hinted_font(
            style.family, round(size) + style.size_delta, medium, bold
        )
        if not _supported(font, text):
            return match.group(0)
        rgb = fill.group(1)
        items.append(
            TextItem(
                x=float(attrs.get("x", "0")),
                y=float(attrs.get("y", "0")),
                size=size,
                medium=medium,
                bold=bold,
                anchor=attrs.get("text-anchor", "start"),
                baseline=attrs.get("dominant-baseline", "alphabetic"),
                fill=(int(rgb[0:2], 16), int(rgb[2:4], 16), int(rgb[4:6], 16)),
                text=text,
            )
        )
        return ""

    return _TEXT_RE.sub(_lift, svg), items


_ANCHORS = {"start": "l", "middle": "m", "end": "r"}


def _fill_for(img: Image.Image, rgb: tuple[int, int, int]) -> int | tuple:
    """Convert an RGB fill to the pixel format of ``img``."""
    if img.mode == "RGB":
        return rgb
    r, g, b = rgb
    return round(0.299 * r + 0.587 * g + 0.114 * b)


def draw_text(
    img: Image.Image,
    items: list[TextItem],
    style: TextStyle,
    origin: tuple[int, int] = (0, 0),
) -> None:
    """Draw ``items`` onto the dashboard canvas in place.

    Drawing on the canvas instead of the widget image means text wider
    than its widget (larger or wider fonts) is not clipped at the
    widget edge.  Pixels are written with no blending, so glyph edges
    stay solid.

    Args:
        img: Canvas in mode ``L`` or ``RGB``.
        items: Items from ``split_text``, in widget coordinates.
        style: Active text style.
        origin: Widget position on the canvas.
    """
    draw = ImageDraw.Draw(img)
    draw.fontmode = "1"
    for item in items:
        font = hinted_font(
            style.family,
            round(item.size) + style.size_delta,
            item.medium,
            item.bold,
        )
        ascent, descent = font.getmetrics()
        h = _ANCHORS.get(item.anchor, "l")
        if item.baseline == "central":
            # resvg centres the em box; approximate with the line box.
            y = item.y + (ascent - descent) / 2
            v = "s"
        elif item.baseline == "hanging":
            y = item.y
            v = "a"
        else:
            y = item.y
            v = "s"
        draw.text(
            (origin[0] + round(item.x), origin[1] + round(y)),
            item.text,
            font=font,
            fill=_fill_for(img, item.fill),
            anchor=h + v,
        )
