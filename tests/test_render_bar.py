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

from __future__ import annotations

from typing import Any, ClassVar

from custom_components.eink_dashboard.svg_render import render_widget_svg
from custom_components.eink_dashboard.widgets import _build_bar_context
from tests.helpers import (
    assert_all_white,
    assert_has_dark_pixels,
    make_config,
    render_to_image,
)


def _states(value: str, unit: str = "W") -> dict[str, Any]:
    """Return a one-entity state dict for ``sensor.power``."""
    return {
        "sensor.power": {
            "state": value,
            "attributes": {
                "unit_of_measurement": unit,
                "friendly_name": "Power",
            },
        }
    }


class TestRenderBar:
    """Verify rendering of the zero-centred bar widget."""

    _DEFAULTS: ClassVar[dict[str, object]] = {
        "width": 400,
        "height": 100,
        "states": _states("0"),
    }

    def _config(self, value: str = "0", **overrides: object) -> dict:
        """Return display config with the power sensor at ``value``."""
        return make_config(self._DEFAULTS, states=_states(value), **overrides)

    def _base_widget(self, **overrides: object) -> dict[str, object]:
        """Return a 380x30 bar widget dict merged with overrides."""
        w: dict[str, object] = {
            "type": "bar",
            "x": 0,
            "y": 20,
            "w": 380,
            "h": 30,
            "entity": "sensor.power",
            "min": -400,
            "max": 400,
        }
        w.update(overrides)
        return w

    # ── Context ────────────────────────────────────────────────────────

    def test_missing_entity_is_blank(self) -> None:
        ctx = _build_bar_context(
            self._base_widget(entity="sensor.nope"), self._config()
        )
        assert ctx["has_entity"] is False

    def test_missing_entity_renders_white(self) -> None:
        img = render_to_image(
            [self._base_widget(entity="sensor.nope")], self._config()
        )
        assert_all_white(img, 0, 20, 380, 50)

    def test_geometry_matches_design(self) -> None:
        # 380x30 -> 288 px track, 22 px tall, tick at the centre.
        ctx = _build_bar_context(self._base_widget(), self._config("0"))
        assert ctx["track_w"] == 288
        assert ctx["track_h"] == 22
        assert ctx["zero_x"] == 144
        assert ctx["track_top"] == 4

    def test_zero_has_no_fill_and_gray_text(self) -> None:
        ctx = _build_bar_context(self._base_widget(), self._config("0"))
        assert ctx["fill_path"] == ""
        assert ctx["value_is_zero"] is True
        assert ctx["value_text"] == "0 W"

    def test_positive_text_has_plus_sign(self) -> None:
        ctx = _build_bar_context(self._base_widget(), self._config("250"))
        assert ctx["value_text"] == "+250 W"
        assert ctx["value_is_zero"] is False

    def test_negative_text_keeps_minus(self) -> None:
        ctx = _build_bar_context(self._base_widget(), self._config("-180"))
        assert ctx["value_text"] == "-180 W"

    def test_show_sign_off(self) -> None:
        ctx = _build_bar_context(
            self._base_widget(show_sign=False), self._config("250")
        )
        assert ctx["value_text"] == "250 W"

    def test_unit_override_and_hidden(self) -> None:
        ctx = _build_bar_context(
            self._base_widget(unit="kW"), self._config("250")
        )
        assert ctx["value_text"] == "+250 kW"
        ctx = _build_bar_context(
            self._base_widget(show_unit=False), self._config("250")
        )
        assert ctx["value_text"] == "+250"

    def test_unavailable_state_shows_dash_and_no_fill(self) -> None:
        ctx = _build_bar_context(
            self._base_widget(), self._config("unavailable")
        )
        assert ctx["fill_path"] == ""
        assert ctx["value_text"] == "–"

    def test_values_clip_at_range(self) -> None:
        full = _build_bar_context(self._base_widget(), self._config("400"))
        over = _build_bar_context(self._base_widget(), self._config("900"))
        assert full["fill_path"] == over["fill_path"]

    def test_tiny_value_has_minimum_fill(self) -> None:
        svg = render_widget_svg(self._base_widget(), self._config("1"))
        # 0.75 * 22 px = 16.5 px, so the fill ends at 144 + 16.5.
        assert "160.5" in svg

    def test_negative_fill_grows_left(self) -> None:
        ctx = _build_bar_context(self._base_widget(), self._config("-400"))
        # Rounded end sits at the left edge of the track (x = 0).
        assert " 0 15 " in str(ctx["fill_path"])

    def test_show_value_off_uses_full_width(self) -> None:
        ctx = _build_bar_context(
            self._base_widget(show_value=False), self._config("250")
        )
        assert ctx["track_w"] == 380

    # ── Pixels ─────────────────────────────────────────────────────────

    # Widget sits at y=20, h=30: track spans y 24..46 (centre 35),
    # the zero tick is x 142..146 and spans the full widget height.

    def test_zero_draws_light_track_and_black_tick(self) -> None:
        img = render_to_image([self._base_widget()], self._config("0"))
        assert 150 < img.getpixel((60, 35)) < 230
        assert img.getpixel((144, 35)) < 60
        # Tick overshoots the track, track itself does not reach it.
        assert img.getpixel((144, 21)) < 60
        assert img.getpixel((60, 21)) == 255

    def test_positive_fill_is_right_of_centre_only(self) -> None:
        img = render_to_image([self._base_widget()], self._config("400"))
        assert img.getpixel((230, 35)) < 60
        assert 150 < img.getpixel((60, 35)) < 230

    def test_negative_fill_is_left_of_centre_only(self) -> None:
        img = render_to_image([self._base_widget()], self._config("-400"))
        assert img.getpixel((60, 35)) < 60
        assert 150 < img.getpixel((230, 35)) < 230

    def test_value_text_stays_inside_widget(self) -> None:
        img = render_to_image(
            [self._base_widget()], self._config("-400", width=800)
        )
        assert_has_dark_pixels(img, 304, 25, 380, 46, threshold=100)
        assert_all_white(img, 381, 0, 800, 100)
