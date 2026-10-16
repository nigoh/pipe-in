"""truncate 関数の受け入れ基準テスト。"""
import pytest

from src.textutil import truncate


def test_ac01_no_truncation_when_shorter_than_width():
    """AC-01: text="hello", width=10 -> "hello"（切り詰めなし）"""
    assert truncate("hello", 10) == "hello"


def test_ac02_no_truncation_when_equal_to_width():
    """AC-02: text="hello", width=5 -> "hello"（ちょうど width と同じ長さは切り詰めなし）"""
    assert truncate("hello", 5) == "hello"


def test_ac03_truncated_with_ellipsis():
    """AC-03: text="hello world", width=5 -> "hell…"（長さ5、末尾が「…」）"""
    result = truncate("hello world", 5)
    assert result == "hell…"
    assert len(result) == 5


def test_ac04_width_one_returns_ellipsis_only():
    """AC-04: text="hello", width=1 -> "…"（長さ1）"""
    result = truncate("hello", 1)
    assert result == "…"
    assert len(result) == 1


def test_ac05_width_zero_raises_value_error():
    """AC-05: text="hello", width=0 -> ValueError"""
    with pytest.raises(ValueError):
        truncate("hello", 0)


def test_ac06_negative_width_raises_value_error():
    """AC-06: text="hello", width=-1 -> ValueError"""
    with pytest.raises(ValueError):
        truncate("hello", -1)


def test_empty_string_returns_empty_string():
    """前提: text が空文字列の場合は FR-01 により空文字列がそのまま返る。"""
    assert truncate("", 5) == ""
