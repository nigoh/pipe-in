"""D0046：確認待ちになったら通知する。スキル（b）・案内の文書（c）・文書・本体を変えないこと（AC-20〜23・AC-25〜29。AC-24 は手で）の検査。

拡張（a）のテストは vscode/src/**/*.test.ts にある。ここは SDK を呼ばず、文書とファイルを文字で読むだけ。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / ".claude" / "skills" / "pipe-in"
SKILL = SKILL_DIR / "SKILL.md"
RECORD = SKILL_DIR / "record.md"
DEVELOP = ROOT / "docs" / "guide" / "develop.md"
VSCODE_GUIDE = ROOT / "docs" / "guide" / "vscode.md"
VSCODE_README = ROOT / "vscode" / "README.md"
SETTINGS = ROOT / ".claude" / "settings.json"


def read(path: Path) -> str:
    if not path.is_file():
        pytest.fail(f"{path.relative_to(ROOT)} が無い", pytrace=False)
    return path.read_text(encoding="utf-8")


def section(md: str, title: str) -> str | None:
    """見出しに title を含む節の中身（次の同じか上の階層の見出しの前まで）。無ければ None。コードの囲みの中の # は見出しにしない。"""
    lines = md.splitlines(keepends=True)
    fenced = False
    heads: list[tuple[int, int, str]] = []  # (行番号, 階層, 見出しの文字)
    for i, line in enumerate(lines):
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        m = None if fenced else re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            heads.append((i, len(m.group(1)), m.group(2)))
    for n, (i, depth, text) in enumerate(heads):
        if title in text:
            end = len(lines)
            for j, d, _ in heads[n + 1 :]:
                if d <= depth:
                    end = j
                    break
            return "".join(lines[i + 1 : end])
    return None


def must_section(path: Path, title: str) -> str:
    body = section(read(path), title)
    if body is None:
        pytest.fail(f"{path.relative_to(ROOT)} に「{title}」の節が無い", pytrace=False)
    return body


def missing(text: str, words: list[str]) -> list[str]:
    return [w for w in words if w not in text]


# ---- 検査そのものが働くこと ----


def test_section_helper_finds_body_and_ignores_fenced_hash():
    md = "# a\n## 必ず守ること\n- x\n```\n# not head\n```\n## 次\n- y\n"
    body = section(md, "必ず守ること")
    assert body is not None and "- x" in body and "not head" in body and "- y" not in body
    assert section(md, "無い節") is None


# ---- (b) スキル ----


def test_D0046_AC_21_必ず守ることに_PushNotification_で知らせる決まりがある():
    """D0046-AC-21: SKILL.md の「必ず守ること」に、record wait のあと人に聞く前に PushNotification で知らせること、ツールが無い会話では何もしないことがある。"""
    body = must_section(SKILL, "必ず守ること")
    assert missing(body, ["record wait", "PushNotification", "ツールが無い", "何もしない"]) == []


def test_D0046_AC_22_auto_で止まって聞く4つの場面でも知らせ_止まらずに進むところでは知らせないと書いてある():
    """D0046-AC-22: SKILL.md と record.md に、--auto で止まって聞く4つの場面でも知らせることと、止まらずに進むところでは知らせないことがある。"""
    text = read(SKILL) + read(RECORD)
    # 知らせる決まりそのものがまだ無いのに、既存の「決めきれない点」などの語だけで通らないよう、PushNotification を条件にする
    assert "PushNotification" in text
    assert missing(text, ["決めきれない点", "文書係の案", "監査と助言", "不合格", "止まらずに進", "知らせない"]) == []
    notify_part = "\n".join(l for l in text.splitlines() if "PushNotification" in l or "知らせ" in l)
    assert "--auto" in notify_part, "知らせの決まりの行に --auto の扱いが書いてある"


def test_D0046_AC_23_知らせの文に要件メモ_パス_秘密を入れないと書いてある():
    """D0046-AC-23: record.md に、知らせの文へ要件メモ・パス・秘密を入れない（段の名前と固定の言葉だけ）と書いてある。"""
    text = read(RECORD)
    assert "PushNotification" in text
    notify_part = "\n".join(l for l in text.splitlines() if "PushNotification" in l or "知らせ" in l)
    assert missing(notify_part, ["要件メモ", "パス", "秘密", "入れない"]) == []


def test_D0046_AC_23_PushNotification_の引数は確かめていないか確かめた旨が書いてある():
    """D0046-AC-23: PushNotification の引数は公式の文書で確かめていない（読めなければそう書く）。record.md に確かめたかどうかの文がある。"""
    text = read(RECORD)
    lines = [l for l in text.splitlines() if "PushNotification" in l]
    assert lines, "record.md に PushNotification の説明が無い"
    assert re.search(r"確かめて(いない|ある)|公式の文書", text), "引数を確かめたか、確かめていないかを書く"


# ---- (c) 案内の文書 ----

NOTICE_TITLE = "確認待ちの知らせ"


def test_D0046_AC_25_ガイドに_Claude_Code_自身の通知の設定の案内がある():
    """D0046-AC-25: develop.md の「確認待ちの知らせ」の節に、/config・端末のベル・許可待ち・入力待ちと、確かめていないこと（か確かめた旨）がある。"""
    body = must_section(DEVELOP, NOTICE_TITLE)
    assert missing(body, ["/config", "端末のベル", "許可待ち", "入力待ち"]) == []
    assert re.search(r"確かめていない|公式の文書で確かめた", body), "設定の名前・項目を確かめたかどうかを書く"


def test_D0046_AC_26_フックを足さない理由が書いてある():
    """D0046-AC-26: 同じ節に、Notification フックを足さない理由（標準出力・ベル・組み込みの通知）がある。"""
    body = must_section(DEVELOP, NOTICE_TITLE)
    assert missing(body, ["Notification", "標準出力", "ベル", "組み込みの通知"]) == []


def test_D0046_AC_29_ガイドに_PushNotification_の短い説明がある():
    """D0046-AC-29: develop.md の節に、PushNotification・ツールが無いと何もしない・拡張の設定では切れないがある。"""
    body = must_section(DEVELOP, NOTICE_TITLE)
    assert missing(body, ["PushNotification", "ツールが無い", "何もしない", "拡張の設定", "切れない"]) == []


# ---- 文書（a） ----


def test_D0046_AC_28_ガイドと拡張_README_に知らせの条件と設定が書いてある():
    """D0046-AC-28: vscode.md の「確認待ちの知らせ」の節と vscode/README.md に、設定名・開いた直後・見ている実行・音と色を出さないことがある。"""
    guide = must_section(VSCODE_GUIDE, NOTICE_TITLE)
    readme = read(VSCODE_README)
    for name, text in (("docs/guide/vscode.md の節", guide), ("vscode/README.md", readme)):
        gone = missing(text, ["pipe-in.notifyWhenWaiting", "開いた直後", "見ている実行", "音", "色"])
        assert gone == [], f"{name} に足りない言葉：{gone}"


def test_D0046_AC_28_通知ではありませんの古い文が残っていない_吹き出しの語は残る():
    """D0046-AC-28: vscode.md から「通知ではありません」が消え、ステータスバーの節には「吹き出し」の語が残る（D0024-AC-46 の検査のため）。"""
    md = read(VSCODE_GUIDE)
    assert "通知ではありません" not in md
    bar = section(md, "ステータスバー")
    assert bar is not None and "吹き出し" in bar


# ---- 変えないもの ----


def test_D0046_AC_27_settings_json_の_hooks_は_PreToolUse_と_Stop_だけで_notify_py_が無い():
    """D0046-AC-27: .claude/settings.json の hooks は PreToolUse と Stop だけ（Notification なし）、permissions は今のまま、.claude/hooks/notify.py が無い。今のまま通る。守る。"""
    data = json.loads(read(SETTINGS))
    assert set(data["hooks"]) == {"PreToolUse", "Stop"}
    assert not (ROOT / ".claude" / "hooks" / "notify.py").exists()
    perms = data["permissions"]
    assert set(perms) == {"allow", "ask", "deny"}
    assert perms["ask"] == [
        "Bash(git push:*)",
        "Bash(git commit:*)",
        "Bash(git merge:*)",
        "Bash(npm publish:*)",
        "Bash(npx vsce publish:*)",
        "Bash(twine upload:*)",
    ]
    assert perms["deny"] == [
        "Read(./.env)",
        "Read(./.env.*)",
        "Read(**/.env)",
        "Read(**/.env.*)",
        "Read(**/*.pem)",
        "Read(**/*.key)",
        "Read(**/id_rsa*)",
        "Read(**/id_ed25519*)",
        "Read(~/.ssh/**)",
        "Read(~/.aws/**)",
        "Read(~/.npmrc)",
        "Read(~/.pypirc)",
    ]
    assert perms["allow"] == [
        "Bash(pytest:*)",
        "Bash(python -m pytest:*)",
        "Bash(npm test:*)",
        "Bash(npm run typecheck:*)",
        "Bash(npm run build:*)",
        "Bash(git status:*)",
        "Bash(git diff:*)",
        "Bash(git log:*)",
        "Bash(git show:*)",
        "Bash(npm --prefix vscode test)",
        "Bash(npm --prefix vscode run typecheck)",
        "Bash(npm --prefix vscode run build)",
        "Bash(npm --prefix vscode run preview)",
        "Bash(python -m http.server 8765 --bind 127.0.0.1 --directory vscode/out/preview)",
        "Agent(pipe-in-analyst)",
        "Agent(pipe-in-tester)",
        "Agent(pipe-in-coder)",
        "Agent(pipe-in-verifier)",
        "Agent(pipe-in-auditor)",
        "Agent(pipe-in-advisor)",
        "Agent(pipe-in-judge)",
        "Agent(pipe-in-documenter)",
    ]


GUARDED = [
    *sorted((ROOT / "pipe_in").rglob("*.py")),
    *sorted((ROOT / "generator").rglob("*.py")),
    ROOT / ".claude" / "hooks" / "pipe_in_guard.py",
]


def test_D0046_AC_20_守る対象のファイルが見つかる():
    """D0046-AC-20: 下の検査が空の一覧で通ってしまわないよう、対象のファイルがあることを確かめる。"""
    names = {p.name for p in GUARDED}
    assert {"guard.py", "guard_hook.py", "pipe_in_guard.py"} <= names


@pytest.mark.parametrize("path", GUARDED, ids=lambda p: str(p.relative_to(ROOT)))
def test_D0046_AC_20_本体と守りの仕組みに_notify_も_PushNotification_も入っていない(path: Path):
    """D0046-AC-20: pipe_in/・generator/・pipe_in_guard.py は通知のために変えない（今のまま通る。守る）。"""
    text = path.read_text(encoding="utf-8").lower()
    assert "notif" not in text and "pushnotification" not in text


def test_D0046_AC_20_検査が通知の語を見つけられる():
    """D0046-AC-20: 上の検査の探し方（小文字にして notif）は、PushNotification・notify を見つける。"""
    for sample in ("PushNotification", "def notify():", "Notification"):
        assert "notif" in sample.lower()
