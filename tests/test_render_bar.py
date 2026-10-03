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

from typing import TYPE_CHECKING, Any, ClassVar

from custom_components.eink_dashboard.svg_render import render_widget_svg
from custom_components.eink_dashboard.widgets import _build_bar_context, bar
from custom_components.eink_dashboard.widgets.bar import _fill_path
from tests.helpers import (
    assert_all_white,
    assert_has_dark_pixels,
    make_config,
    render_to_image,
)

if TYPE_CHECKING:
    import pytest


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

    def _inside_ctx(self, value: str, **overrides: object) -> dict:
        """Return the bar context with ``value_position="inside"``."""
        widget = self._base_widget(value_position="inside", **overrides)
        return _build_bar_context(widget, self._config(value))

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
        # 380x30 -> 288 px track taking the full widget height.
        ctx = _build_bar_context(self._base_widget(), self._config("0"))
        assert ctx["track_w"] == 288
        assert ctx["track_h"] == 30
        assert ctx["zero_x"] == 144
        assert ctx["track_top"] == 0

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
        # 0.55 * 30 px = 16.5 px, so the fill ends at 144 + 16.5.
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

    def test_no_zero_tick_in_svg(self) -> None:
        svg = render_widget_svg(self._base_widget(), self._config("250"))
        assert "<rect" in svg
        assert svg.count("<rect") == 1  # the track outline only

    # ── Corner radius ──────────────────────────────────────────────────

    def test_default_ends_are_fully_rounded(self) -> None:
        ctx = _build_bar_context(self._base_widget(), self._config("400"))
        assert ctx["track_r"] == 15
        assert "V" not in str(ctx["fill_path"])

    def test_smaller_radius_gives_straight_fill_sides(self) -> None:
        path = _fill_path(144, 0, 30, 100, 11, positive=True)
        assert "A 11 11" in path
        assert "V 19" in path

    def test_radius_hook_changes_track_and_fill(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(bar, "_track_radius", lambda track_h: 11)
        ctx = _build_bar_context(self._base_widget(), self._config("400"))
        assert ctx["track_r"] == 11
        assert "A 11 11" in str(ctx["fill_path"])

    # ── Inside value ───────────────────────────────────────────────────

    def test_inside_uses_full_width_track(self) -> None:
        ctx = self._inside_ctx("0")
        assert ctx["track_w"] == 380

    def test_inside_positive_text_left_of_zero(self) -> None:
        ctx = self._inside_ctx("200")
        assert ctx["value_anchor"] == "end"
        assert ctx["value_x"] < ctx["zero_x"]

    def test_inside_negative_text_right_of_zero(self) -> None:
        ctx = self._inside_ctx("-200")
        assert ctx["value_anchor"] == "start"
        assert ctx["value_x"] > ctx["zero_x"]

    def test_inside_text_is_smaller_and_not_bold_by_default(self) -> None:
        outside = _build_bar_context(self._base_widget(), self._config("0"))
        ctx = self._inside_ctx("0")
        assert ctx["value_font_sz"] < outside["value_font_sz"]
        assert not ctx["value_bold"]
        assert outside["value_bold"]

    def test_inside_bold_can_be_forced(self) -> None:
        assert self._inside_ctx("0", bold_value=True)["value_bold"]

    def test_inside_text_stays_clear_of_fill(self) -> None:
        for value in ("400", "-400"):
            ctx = self._inside_ctx(value)
            assert abs(ctx["value_x"] - ctx["zero_x"]) > 0

    # ── Icons ──────────────────────────────────────────────────────────

    def test_icon_follows_sign_of_value(self) -> None:
        kw = {
            "icon_positive": "mdi:transmission-tower",
            "icon_negative": "mdi:white-balance-sunny",
        }
        pos = self._inside_ctx("200", **kw)
        neg = self._inside_ctx("-200", **kw)
        assert pos["icon_svg"]
        assert neg["icon_svg"]
        assert pos["icon_svg"] != neg["icon_svg"]
        assert pos["icon_x"] < pos["zero_x"] < neg["icon_x"]

    def test_icon_absent_at_zero_and_when_unset(self) -> None:
        kw = {"icon_positive": "mdi:transmission-tower"}
        assert not self._inside_ctx("0", **kw)["icon_svg"]
        assert not self._inside_ctx("200")["icon_svg"]
        assert not self._inside_ctx("-200", **kw)["icon_svg"]

    def test_unknown_icon_is_ignored(self) -> None:
        ctx = self._inside_ctx("200", icon_positive="mdi:no-such-icon-xyz")
        assert not ctx["icon_svg"]

    def test_icon_size_follows_font_size(self) -> None:
        def icon_and_font(h: int) -> tuple[int, int]:
            ctx = self._inside_ctx(
                "200", icon_positive="mdi:transmission-tower", h=h
            )
            svg = str(ctx["icon_svg"])
            px = int(svg.split('width="')[1].split('"')[0])
            return px, int(ctx["value_font_sz"])

        small, big = icon_and_font(24), icon_and_font(48)
        assert small[0] < big[0]
        for icon_px, font in (small, big):
            assert icon_px == round(font * 1.2)

    # ── Pixels ─────────────────────────────────────────────────────────

    # Widget sits at y=20, h=30: track spans y 20..50 (centre 35).

    def test_zero_draws_hollow_outline_without_tick(self) -> None:
        img = render_to_image([self._base_widget()], self._config("0"))
        # Inside the outline stays white, including where zero is.
        assert img.getpixel((60, 35)) == 255
        assert img.getpixel((144, 35)) == 255
        # The outline itself is light gray.
        assert 120 < img.getpixel((60, 21)) < 230

    def test_positive_fill_is_right_of_centre_only(self) -> None:
        img = render_to_image([self._base_widget()], self._config("400"))
        assert img.getpixel((230, 35)) < 60
        assert img.getpixel((60, 35)) == 255

    def test_negative_fill_is_left_of_centre_only(self) -> None:
        img = render_to_image([self._base_widget()], self._config("-400"))
        assert img.getpixel((60, 35)) < 60
        assert img.getpixel((230, 35)) == 255

    def test_value_text_stays_inside_widget(self) -> None:
        img = render_to_image(
            [self._base_widget()], self._config("-400", width=800)
        )
        assert_has_dark_pixels(img, 304, 22, 380, 48, threshold=100)
        assert_all_white(img, 381, 0, 800, 100)

    # ── Display levels ─────────────────────────────────────────────────

    def test_outline_is_flat_after_dithering(self) -> None:
        # The outline gray is a display level, so even with the
        # optimiser on it must stay one solid tone, not a stipple.
        cfg = self._config("289", width=800, display_levels=4, optimize=True)
        img = render_to_image([self._base_widget(x=360)], cfg)
        # Row through the top stroke of the left half (y 21).
        row = {img.getpixel((x, 21)) for x in range(400, 490)}
        assert row == {170}

    def test_zero_text_is_not_stippled_after_dithering(self) -> None:
        # The zero-state text gray is a display level, so that level
        # dominates; the rest is antialiasing at the glyph edges.
        cfg = self._config("0", width=800, display_levels=4, optimize=True)
        # Autocontrast stretches the darkest tone to black, so the image
        # needs a black element besides the gray zero text.
        black = {
            "type": "heading",
            "heading": "Black",
            "x": 0,
            "y": 60,
            "w": 200,
            "h": 30,
            "card_style": "none",
        }
        img = render_to_image([self._base_widget(x=360), black], cfg)
        pixels = [
            img.getpixel((x, y))
            for x in range(660, 740)
            for y in range(25, 46)
        ]
        assert pixels.count(85) > 2 * pixels.count(170)
