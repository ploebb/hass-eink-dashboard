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

from ..const import PADDING, DisplayConfig, Widget, color_to_hex
from ._helpers import _color_context, _fmt, _widget_dim

# Gap between the end of the track and the value text, as a
# fraction of the track height.
_GAP_RATIO = 0.75
# Width reserved for the value text, in multiples of its font size.
_VALUE_W_RATIO = 3.6
# Value font size as a fraction of the track height.
_FONT_RATIO = 0.95
# Value font size as a fraction of the track height when the text sits
# inside the track.
_INSIDE_FONT_RATIO = 0.6
# Clearance between inside text and the zero tick, as a fraction of
# the track height.
_INSIDE_PAD_RATIO = 0.3
# Outline stroke width as a fraction of the track height (min 2 px).
_OUTLINE_RATIO = 0.09
# A non-zero value never fills less than this many track heights,
# so tiny readings stay visible.
_MIN_FILL_RATIO = 0.75


def _fill_path(
    zero_x: float,
    top: float,
    track_h: float,
    length: float,
    *,
    positive: bool,
) -> str:
    """Return an SVG path for a fill that is flat at zero.

    The fill starts square at the zero line and is rounded at the
    outer end with the same radius as the track.

    Args:
        zero_x: X coordinate of the zero line.
        top: Y coordinate of the track's top edge.
        track_h: Track height in pixels.
        length: Fill length in pixels, at least ``track_h / 2``.
        positive: Grow to the right when ``True``, else to the left.

    Returns:
        SVG path data string.
    """
    r = track_h / 2
    bottom = top + track_h
    end = zero_x + length if positive else zero_x - length
    inner = end - r if positive else end + r
    sweep_top, sweep_bottom = (1, 1) if positive else (0, 0)
    return (
        f"M {zero_x:g} {top:g} H {inner:g} "
        f"A {r:g} {r:g} 0 0 {sweep_top} {end:g} {top + r:g} "
        f"A {r:g} {r:g} 0 0 {sweep_bottom} {inner:g} {bottom:g} "
        f"H {zero_x:g} Z"
    )


def _build_bar_context(
    widget: Widget,
    config: DisplayConfig,
) -> dict[str, object]:
    """Build Jinja2 template context for the bar widget.

    Renders a horizontal bar with zero at the centre of the track:
    the fill grows to the left for negative values and to the right
    for positive ones, with the value as text to the right of the
    track.  Intended for signed readings such as grid power
    (import/feed-in).  The track height follows from the widget
    height, leaving room above and below for the zero tick.

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
            track, left of the zero tick for positive values and
            right of it for negative ones, so it never overlaps the
            fill; default ``"outside"``),
            ``track_style`` (``"filled"`` draws the track as a solid
            light-gray bar; ``"outline"`` draws only a thin light-gray
            outline, which stays solid on few-level panels where a
            lighter fill is dithered into a pattern; default
            ``"filled"``),
            ``bold_value`` (bold value text; default ``True`` outside
            the track and ``False`` inside),
            ``track_gray`` (track gray, 0-255; default the standard
            light gray, which is a display level).  A gray that is
            not a display level is dithered by the e-ink optimiser,
            so a lighter track shows as a fine pattern on 4-level
            panels,
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
    outline: bool = widget.get("track_style", "filled") == "outline"
    inside: bool = widget.get("value_position", "outside") == "inside"
    value_bold: bool = bool(widget.get("bold_value", not inside))
    track_gray = widget.get("track_gray")

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
    # The zero tick overshoots the track by ~13% of the widget
    # height at both ends; the track takes what is left.
    overshoot = max(2, round(h * 0.13))
    track_h = max(2, h - 2 * overshoot)
    track_top = overshoot
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
        length = max(frac * half_w, track_h * _MIN_FILL_RATIO)
        fill_path = _fill_path(
            zero_x, track_top, track_h, length, positive=value > 0
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

    # Inside the track the text sits in the half without fill, hugging
    # the zero tick; zero and unknown values use the left half.
    tick_w = max(2, round(track_h * 0.18))
    value_x = track_w + gap
    value_anchor = "start"
    if inside:
        pad = round(track_h * _INSIDE_PAD_RATIO)
        if value is not None and value < 0:
            value_x = zero_x + tick_w / 2 + pad
        else:
            value_x = zero_x - tick_w / 2 - pad
            value_anchor = "end"

    return {
        "w": w,
        "h": h,
        "has_entity": True,
        "track_x": 0,
        "track_top": track_top,
        "track_w": track_w,
        "track_h": track_h,
        "track_r": track_h / 2,
        "outline": outline,
        "outline_w": max(2, round(track_h * _OUTLINE_RATIO)),
        "zero_x": zero_x,
        "tick_w": tick_w,
        "tick_top": 0,
        "tick_h": h,
        "track_color": (
            color_to_hex(int(track_gray))
            if track_gray is not None
            else colors["hex_light_gray"]
        ),
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
