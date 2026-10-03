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

"""Bar widget context builder."""

from __future__ import annotations

import contextlib

from ..const import PADDING, DisplayConfig, Widget
from ..svg_render import _mdi_svg_filter
from ._helpers import _color_context, _fmt, _widget_dim

# Gap between the end of the track and the value text, as a
# fraction of the track height.
_GAP_RATIO = 0.55
# Width reserved for the value text, in multiples of its font size.
_VALUE_W_RATIO = 3.6
# Value font size as a fraction of the track height when the text sits
# beside the track.
_FONT_RATIO = 0.7
# Value font size as a fraction of the track height when the text sits
# inside the track.
_INSIDE_FONT_RATIO = 0.5
# Clearance between inside text and the zero line, as a fraction of
# the track height.
_INSIDE_PAD_RATIO = 0.3
# Outline stroke width as a fraction of the track height (min 2 px).
_OUTLINE_RATIO = 0.09
# Clearance between an icon and the rounded track end, as a fraction
# of the track height.
_EDGE_RATIO = 0.6
# Minimum clearance between an icon and the value text, as a fraction
# of the track height.
_ICON_VALUE_GAP_RATIO = 0.5
# Icon size as a multiple of the value font size.
_ICON_RATIO = 1.2
# A non-zero value never fills less than this many track heights,
# so tiny readings stay visible.
_MIN_FILL_RATIO = 0.55


def _fill_path(
    zero_x: float,
    top: float,
    track_h: float,
    length: float,
    radius: float,
    *,
    positive: bool,
) -> str:
    """Return an SVG path for a fill that is flat at zero.

    The fill starts square at the zero line and has rounded corners
    at the outer end with the same radius as the track.

    Args:
        zero_x: X coordinate of the zero line.
        top: Y coordinate of the track's top edge.
        track_h: Track height in pixels.
        length: Fill length in pixels, at least ``radius``.
        radius: Corner radius of the outer end.
        positive: Grow to the right when ``True``, else to the left.

    Returns:
        SVG path data string.
    """
    r = radius
    bottom = top + track_h
    end = zero_x + length if positive else zero_x - length
    inner = end - r if positive else end + r
    sweep = 1 if positive else 0
    # A straight side only exists when the radius is below half the
    # track height.
    side = f"V {bottom - r:g} " if bottom - r > top + r else ""
    return (
        f"M {zero_x:g} {top:g} H {inner:g} "
        f"A {r:g} {r:g} 0 0 {sweep} {end:g} {top + r:g} "
        f"{side}"
        f"A {r:g} {r:g} 0 0 {sweep} {inner:g} {bottom:g} "
        f"H {zero_x:g} Z"
    )


def _build_bar_context(
    widget: Widget,
    config: DisplayConfig,
) -> dict[str, object]:
    """Build Jinja2 template context for the bar widget.

    Renders a horizontal bar with zero at the centre of a light-gray
    outlined track: the black fill grows to the left for negative
    values and to the right for positive ones.  Intended for signed
    readings such as grid power (import/feed-in).  The track takes
    the full widget height.

    Args:
        widget: Widget config dict.  Recognised keys:
            ``entity`` (HA entity ID, required),
            ``attribute`` (HA attribute key to use instead of the
            state),
            ``min`` (value at the left end; default -100),
            ``max`` (value at the right end; default 100),
            ``unit`` (unit string override),
            ``show_unit`` (display unit; default ``True``),
            ``show_value`` (display the value text; default
            ``True``),
            ``show_sign`` (prefix positive values with ``+``;
            default ``True``),
            ``decimals`` (decimal places; default 0),
            ``value_position`` (``"outside"`` puts the value right of
            the track; ``"inside"`` puts it in the empty half of the
            track next to the zero position, left of it for positive
            values and right of it for negative ones, so it never
            overlaps the fill; default ``"outside"``),
            ``icon_positive`` / ``icon_negative`` (MDI icon, with or
            without the ``mdi:`` prefix, drawn at the outer end of
            the empty half for positive or negative values, e.g. a
            grid icon for import and a solar icon for feed-in;
            nothing is drawn at zero; default none),
            ``bold_value`` (bold value text; default ``True`` outside
            the track and ``False`` inside),
            ``corner_radius`` (corner radius of track and fill in
            pixels, limited to half the track height; default fully
            rounded ends.  The tiles use 11 px at their standard
            height),
            ``x``, ``w``, ``h``.
        config: Display config with ``width`` and ``states``.

    Returns:
        Template context dict consumed by ``bar.svg.j2``.  Returns
        ``{"w": …, "h": …, "has_entity": False, **_color_context()}``
        when the entity is missing from the state dict.
    """
    x = widget.get("x", PADDING)
    w = _widget_dim(widget, "w", config["width"] - x)
    h = _widget_dim(widget, "h", 30)

    entity_id: str = widget.get("entity", "")
    states = config.get("states", {})
    attribute: str | None = widget.get("attribute")
    min_val = float(widget.get("min", -100))
    max_val = float(widget.get("max", 100))
    show_unit: bool = bool(widget.get("show_unit", True))
    show_value: bool = bool(widget.get("show_value", True))
    show_sign: bool = bool(widget.get("show_sign", True))
    decimals = int(widget.get("decimals", 0))
    inside: bool = widget.get("value_position", "outside") == "inside"
    value_bold: bool = bool(widget.get("bold_value", not inside))

    state = states.get(entity_id) if entity_id else None
    if state is None:
        return {
            "w": w,
            "h": h,
            "has_entity": False,
            **_color_context(),
        }

    attrs: dict[str, object] = state.get("attributes", {})
    colors = _color_context()

    # --- Value ---
    raw = attrs.get(attribute) if attribute is not None else state.get("state")
    try:
        value: float | None = float(str(raw))
    except (TypeError, ValueError):
        value = None  # unavailable / unknown / non-numeric

    # --- Geometry ---
    track_h = max(2, h)
    track_top = 0
    radius = track_h / 2
    if widget.get("corner_radius") is not None:
        radius = min(radius, max(0.0, float(widget["corner_radius"])))
    font_sz = max(
        8, round(track_h * (_INSIDE_FONT_RATIO if inside else _FONT_RATIO))
    )
    gap = round(track_h * _GAP_RATIO)
    value_w = round(font_sz * _VALUE_W_RATIO) if show_value else 0
    reserved = value_w + gap if show_value and not inside else 0
    track_w = max(track_h * 2, w - reserved)
    zero_x = track_w / 2
    half_w = track_w / 2

    # Lower bound clamps to <= 0 and upper to >= 0 so zero always
    # exists on the track; each side scales on its own limit.
    neg_limit = abs(min(min_val, 0.0))
    pos_limit = max(max_val, 0.0)

    fill_path = ""
    if value is not None and value != 0:
        limit = pos_limit if value > 0 else neg_limit
        frac = min(abs(value) / limit, 1.0) if limit > 0 else 1.0
        length = max(frac * half_w, track_h * _MIN_FILL_RATIO, radius)
        fill_path = _fill_path(
            zero_x,
            track_top,
            track_h,
            length,
            radius,
            positive=value > 0,
        )

    # --- Text ---
    if value is None:
        value_text = "–"
    else:
        rounded = f"{value:.{decimals}f}"
        value_text = _fmt(rounded, config)
        if show_sign and value > 0:
            value_text = f"+{value_text}"
    if show_unit and value is not None:
        unit = widget.get("unit")
        if unit is None:
            unit = attrs.get("unit_of_measurement", "")
        if unit:
            value_text = f"{value_text} {unit}"

    # Inside the track the text sits in the half without fill, next to
    # the zero position; zero and unknown values use the left half.
    value_x = track_w + gap
    value_anchor = "start"
    pad_inside = round(track_h * _INSIDE_PAD_RATIO)
    if inside:
        if value is not None and value < 0:
            value_x = zero_x + pad_inside
        else:
            value_x = zero_x - pad_inside
            value_anchor = "end"

    # --- Icon ---
    # Outer end of the empty half.  The empty half is the right one
    # only for negative values.
    icon_svg: object = ""
    icon_size = round(font_sz * _ICON_RATIO)
    edge = round(track_h * _EDGE_RATIO)
    if value is not None and value != 0:
        icon_name = widget.get(
            "icon_negative" if value < 0 else "icon_positive"
        )
        if icon_name:
            icon_name = str(icon_name).removeprefix("mdi:")
            with contextlib.suppress(FileNotFoundError, ValueError):
                icon_svg = _mdi_svg_filter(icon_name, icon_size)
    if icon_svg:
        from ..render import _load_font

        value_w_px = (
            _load_font(
                font_sz, medium=not value_bold, bold=value_bold
            ).getlength(value_text)
            if show_value and inside
            else 0
        )
        room = half_w - edge - (pad_inside if inside else 0)
        if icon_size + value_w_px + track_h * _ICON_VALUE_GAP_RATIO > room:
            icon_svg = ""
    icon_right = value is not None and value < 0
    icon_x = track_w - edge - icon_size if icon_right else edge
    icon_y = track_top + (track_h - icon_size) / 2

    outline_w = max(2, round(track_h * _OUTLINE_RATIO))
    return {
        "w": w,
        "h": h,
        "has_entity": True,
        "icon_svg": icon_svg,
        "icon_x": icon_x,
        "icon_y": icon_y,
        "track_x": 0,
        "track_top": track_top,
        "track_w": track_w,
        "track_h": track_h,
        "track_r": radius,
        "zero_x": zero_x,
        "outline_w": outline_w,
        "fill_path": fill_path,
        "show_value": show_value,
        "value_text": value_text,
        "value_x": value_x,
        "value_anchor": value_anchor,
        "value_y": track_top + track_h / 2,
        "value_font_sz": font_sz,
        "value_bold": value_bold,
        "value_is_zero": value is None or value == 0,
        **colors,
    }
