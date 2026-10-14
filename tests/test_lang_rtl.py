"""Tests for RTL language support (Urdu, Arabic) and reading order."""

from __future__ import annotations

import pytest

from examforge.ir.schema import BBox, Block, BlockStatus, BlockType
from examforge.lang.rtl import (
    format_dir_attribute,
    is_rtl_language,
    reorder_rtl_blocks,
)


def test_is_rtl_language():
    assert is_rtl_language("ur") is True
    assert is_rtl_language("ar") is True
    assert is_rtl_language("fa") is True
    assert is_rtl_language("en") is False
    assert is_rtl_language("hi") is False
    assert is_rtl_language("bn") is False


def test_format_dir_attribute():
    assert format_dir_attribute("ur") == 'dir="rtl"'
    assert format_dir_attribute("ar") == 'dir="rtl"'
    assert format_dir_attribute("en") == 'dir="ltr"'
    assert format_dir_attribute("hi") == 'dir="ltr"'


def test_reorder_rtl_blocks():
    # In an RTL layout, block on the right should be read before block on the left on the same line
    b_left = Block(
        id="b_left",
        page=1,
        type=BlockType.TEXT,
        bbox=BBox(x1=50, y1=100, x2=200, y2=130),
        text="حصہ اول",
        confidence=1.0,
        status=BlockStatus.TRUSTED,
    )
    b_right = Block(
        id="b_right",
        page=1,
        type=BlockType.TEXT,
        bbox=BBox(x1=250, y1=100, x2=400, y2=130),
        text="سوال نمبر 1",
        confidence=1.0,
        status=BlockStatus.TRUSTED,
    )

    ordered = reorder_rtl_blocks([b_left, b_right])
    assert ordered[0].id == "b_right"
    assert ordered[1].id == "b_left"
