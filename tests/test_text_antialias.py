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

from typing import Any

import pytest

from custom_components.eink_dashboard.const import COLOR_GRAY
from custom_components.eink_dashboard.svg_render import (
    _text_antialias,
    render_widget_svg,
)
from tests.helpers import make_config, render_to_image

_ATTR = 'text-rendering="optimizeSpeed"'

_WIDGET: dict[str, Any] = {
    "type": "heading",
    "x": 0,
    "y": 0,
    "w": 300,
    "h": 40,
    "heading": "Heute: Tag der Deutschen Einheit",
    "heading_style": "subtitle",
    "card_style": "none",
}

_TITLE: dict[str, Any] = {
    "type": "heading",
    "x": 0,
    "y": 0,
    "w": 300,
    "h": 40,
    "heading": "Samstag",
    "card_style": "none",
}

_DEFAULTS: dict[str, Any] = {"width": 300, "height": 40, "states": {}}


class TestTextAntialias:
    """Verify the anti-aliasing switch for low-level displays."""

    @pytest.mark.parametrize(
        ("levels", "expected"),
        [(2, False), (4, False), (8, True), (16, True), (256, True)],
    )
    def test_default_depends_on_display_levels(
        self, levels: int, expected: bool
    ) -> None:
        assert _text_antialias({"display_levels": levels}) is expected

    def test_default_without_display_levels_is_antialiased(self) -> None:
        assert _text_antialias({}) is True

    @pytest.mark.parametrize("levels", [2, 4])
    def test_explicit_true_wins_on_low_levels(self, levels: int) -> None:
        cfg = {"display_levels": levels, "text_antialias": True}
        assert _text_antialias(cfg) is True

    def test_explicit_false_wins_on_high_levels(self) -> None:
        cfg = {"display_levels": 16, "text_antialias": False}
        assert _text_antialias(cfg) is False

    def test_svg_root_carries_attribute_on_four_levels(self) -> None:
        cfg = make_config(_DEFAULTS, display_levels=4)
        svg = render_widget_svg(_WIDGET, cfg)
        assert svg.count(_ATTR) == 1
        assert _ATTR in svg.split(">", 1)[0]

    def test_svg_root_has_no_attribute_on_sixteen_levels(self) -> None:
        cfg = make_config(_DEFAULTS, display_levels=16)
        assert _ATTR not in render_widget_svg(_WIDGET, cfg)

    def test_gray_text_has_only_display_levels_when_dithered(self) -> None:
        # Without anti-aliasing the gray text is made of the gray level
        # itself and the background, nothing in between.  The black
        # title keeps the optimiser's autocontrast from stretching the
        # gray to black.
        cfg = make_config(
            _DEFAULTS,
            height=80,
            display_levels=4,
            optimize=True,
            language="de",
        )
        widgets = [_TITLE, {**_WIDGET, "y": 40}]
        img = render_to_image(widgets, cfg)
        tones = {v for _, v in img.crop((0, 40, 300, 80)).getcolors(256)}
        assert tones == {COLOR_GRAY, 255}

    def test_antialiased_text_has_edge_tones(self) -> None:
        cfg = make_config(
            _DEFAULTS,
            height=80,
            display_levels=4,
            optimize=True,
            language="de",
            text_antialias=True,
        )
        widgets = [_TITLE, {**_WIDGET, "y": 40}]
        img = render_to_image(widgets, cfg)
        tones = {v for _, v in img.crop((0, 40, 300, 80)).getcolors(256)}
        assert len(tones) > 2
