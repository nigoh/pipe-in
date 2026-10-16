"""ひな形の {{名前}} を、対象の環境から決めた値で埋める。"""

from __future__ import annotations

import re

from .detect import Env

PLACEHOLDER = re.compile(r"\{\{(\w+)\}\}")


def template_values(env: Env, name: str = "") -> dict[str, str | None]:
    """ひな形で使える値。対象の絶対パスは入れない（作ったパイプを人に渡しても、手元の事情が漏れないように）。"""
    docs = env.docs_dirs[0] if env.docs_dirs else "docs"
    sources = "プロジェクト全体" if env.source_dirs == ["."] else "、".join(f"`{d}/`" for d in env.source_dirs)
    return {
        "name": name,
        "test_command": env.test_command,
        "source_dirs": sources,
        "diagrams_dir": f"{docs}/diagrams",
        "docs_hint": "、".join(f"`{d}/`" for d in env.docs_dirs) or "プロジェクトの中",
    }


def _toml_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def render_template(text: str, values: dict[str, str | None], *, toml: bool = True) -> str:
    """{{名前}} を値で埋める。

    toml なら、値を TOML の文字列として壊れない形にし、値が None の行はコメントにする（例：テストのコマンドが見つからない）。
    Markdown なら値はそのまま入れ、値が None の行は消す。
    """
    out: list[str] = []
    for line in text.splitlines(keepends=True):
        keys = [k for k in PLACEHOLDER.findall(line) if k in values]
        if any(values[k] is None for k in keys):
            if toml:
                out.append("# " + PLACEHOLDER.sub("", line))
            continue

        def fill(m: re.Match[str]) -> str:
            if m.group(1) not in values:
                return m.group(0)
            value = values[m.group(1)] or ""
            return _toml_escape(value) if toml else value

        out.append(PLACEHOLDER.sub(fill, line))
    return "".join(out)
