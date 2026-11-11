"""D0089: プラグインのフックが動かないときの扱い（onFailure を付けない）の固定。

リポジトリの実物を読むだけで、書かない。ほかのテストファイルから import しない。
"""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HOOKS_JSON = ROOT / "plugin" / "hooks" / "hooks.json"
PLUGIN_MD = ROOT / "docs" / "guide" / "plugin.md"
SAFETY_MD = ROOT / "docs" / "guide" / "safety.md"
DECISION = ROOT / "docs" / "decisions" / "D0089-hook-failure.md"
DECISIONS_README = ROOT / "docs" / "decisions" / "README.md"


def on_failure_places(config: object, path: str = "") -> list[str]:
    """設定を深さに関わらずたどり、onFailure の鍵がある場所を道の文字で返す。"""
    found: list[str] = []
    if isinstance(config, dict):
        for key, value in config.items():
            here = f"{path}.{key}" if path else str(key)
            if key == "onFailure":
                found.append(here)
            found.extend(on_failure_places(value, here))
    elif isinstance(config, list):
        for i, value in enumerate(config):
            found.extend(on_failure_places(value, f"{path}[{i}]"))
    return found


def load_hooks() -> dict:
    return json.loads(HOOKS_JSON.read_text(encoding="utf-8"))


def section(text: str, heading: str) -> str:
    """見出し（`## ` 行）から、次の `## ` の前までの本文。無ければ空。"""
    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if line.strip() == heading:
            start = i + 1
            break
    if start is None:
        return ""
    body: list[str] = []
    for line in lines[start:]:
        if line.startswith("## "):
            break
        body.append(line)
    return "\n".join(body)


def test_d0089_ac05_hooks_jsonの形は固定_onFailureは無い() -> None:
    """D0089-AC-05: hooks.json の形を固定し、onFailure がどこにも無い。

    付けるように変えるときは、このテストと決定の記録 D0089 を一緒に直すこと。
    """
    config = load_hooks()
    hint = "（onFailure を付けるなら、このテストと docs/decisions/D0089-hook-failure.md を一緒に直す）"
    assert list(config["hooks"].keys()) == ["PreToolUse"], hint
    groups = config["hooks"]["PreToolUse"]
    assert len(groups) == 1, hint
    assert groups[0]["matcher"] == "*", hint
    inner = groups[0]["hooks"]
    assert len(inner) == 1, hint
    hook = inner[0]
    assert hook["type"] == "command", hint
    assert hook["command"] == "pipe-in-gen", hint
    assert hook["args"] == ["guard-hook"], hint
    assert hook["timeout"] == 30, hint
    assert on_failure_places(config) == [], hint


@pytest.mark.parametrize(
    ("where", "expected"),
    [
        ("none", []),
        ("group", ["hooks.PreToolUse[0].onFailure"]),
        ("hook", ["hooks.PreToolUse[0].hooks[0].onFailure"]),
        ("deep", ["hooks.PreToolUse[0].hooks[0].extra.onFailure"]),
        ("top", ["onFailure"]),
    ],
)
def test_d0089_ac06_onFailureの見つけ方_偽の設定(where: str, expected: list[str]) -> None:
    """D0089-AC-06: 偽の設定に onFailure を足すと、見つけ方が道の文字で1件見つける。"""
    config = copy.deepcopy(load_hooks())
    group = config["hooks"]["PreToolUse"][0]
    if where == "group":
        group["onFailure"] = "block"
    elif where == "hook":
        group["hooks"][0]["onFailure"] = "block"
    elif where == "deep":
        group["hooks"][0]["extra"] = {"onFailure": "block"}
    elif where == "top":
        config["onFailure"] = "block"
    assert on_failure_places(config) == expected


def test_d0089_ac07_plugin_mdに付けない理由と確かめの無いことが書いてある() -> None:
    """D0089-AC-07: plugin.md に onFailure を付けない理由と、流す前の確かめが無いことがある。"""
    text = PLUGIN_MD.read_text(encoding="utf-8")
    missing = [
        w
        for w in (
            "onFailure",
            "pipe-builder",
            "pipe-judge",
            "hook error",
            "流す前の確かめ",
            "エージェントの種類",
        )
        if w not in text
    ]
    assert not missing, f"docs/guide/plugin.md に無い言葉：{missing}"


def test_d0089_ac08_safety_mdにフックが動かないときの節がある() -> None:
    """D0089-AC-08: safety.md の「プラグインのフックが動かないとき」の節に、必要な言葉がある。"""
    text = SAFETY_MD.read_text(encoding="utf-8")
    body = section(text, "## プラグインのフックが動かないとき")
    assert body, "safety.md に見出し `## プラグインのフックが動かないとき` が無い"
    missing = [
        w
        for w in (
            "pipe-in-gen guard-hook",
            "止める側に倒れ",
            "通ります",
            "pipe-builder",
            "pipe-run",
            "chat probe",
            "onFailure",
        )
        if w not in body
    ]
    assert not missing, f"その節に無い言葉：{missing}"


def _decision_text() -> str:
    assert DECISION.exists(), "docs/decisions/D0089-hook-failure.md がまだ無い"
    return DECISION.read_text(encoding="utf-8")


def _heading_section(text: str, word: str) -> str:
    """word を含む見出し（# 始まりの行）の本文（同じか上の階層の見出しまで）。見出しが無ければ全文。"""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        m = re.match(r"^(#+)\s", line)
        if m and word in line:
            level = len(m.group(1))
            body: list[str] = []
            for nxt in lines[i + 1 :]:
                m2 = re.match(r"^(#+)\s", nxt)
                if m2 and len(m2.group(1)) <= level:
                    break
                body.append(nxt)
            return "\n".join(body)
    return text


def test_d0089_ac01_03_決定の記録に必要な言葉がある() -> None:
    """D0089-AC-01〜03: 決定の記録に URL・形・条件・確かめていないこと・残った課題の言葉がある。"""
    text = _decision_text()
    assert "https://code.claude.com/docs/en/hooks" in text
    for word in (
        "選んだ形",
        "選ばなかった形",
        "付けられる条件",
        "確かめていないこと",
        "残った課題",
        "onFailure",
        "v2.1.295",
        "matcher",
        "起動用のスクリプト",
    ):
        assert word in text, f"決定の記録に無い言葉：{word}"
    unverified = _heading_section(text, "確かめていないこと")
    for word in ("実機", "まだ"):
        assert word in unverified, f"「確かめていないこと」に無い言葉：{word}"


def test_d0089_ac10_決定の記録の一覧に載っている() -> None:
    """D0089-AC-10: docs/decisions/README.md に D0089 の行（リンク）がある。"""
    text = DECISIONS_README.read_text(encoding="utf-8")
    assert "(D0089-hook-failure.md)" in text
