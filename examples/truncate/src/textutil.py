"""文字列ユーティリティ。"""


def normalize_spaces(text: str) -> str:
    """連続する空白を1つにまとめる。"""
    return " ".join(text.split())


def truncate(text: str, width: int) -> str:
    """文字列を width 文字以内に切り詰める。超える場合は末尾を「…」にする。"""
    if width < 1:
        raise ValueError("width must be 1 or more")
    if len(text) <= width:
        return text
    return text[: width - 1] + "…"
