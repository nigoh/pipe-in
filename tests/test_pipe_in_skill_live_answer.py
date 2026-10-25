"""D0039：.claude/skills/pipe-in/SKILL.md の `--artifact` の節（ページから来た答えの受け方）。

公開の宣言は {"db": {}, "comments": {}}（comments を宣言しない公開の手順を残さない）。
ページから来た答えは、本文を Write でファイルに書く → `pipe-in live answer --text-file …` で読む → ok のときだけ `record review` を書く、で受ける。
本文を Bash のコマンド行に入れない。直してほしい点は人の言葉として扱う。手順の中の引数が、本体の実際の引数と一致する。
文書を読むだけのテスト（SKILL.md は書かない）。
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import pytest

from pipe_in.dev import record
from pipe_in.engine import live_cmd

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / ".claude" / "skills" / "pipe-in" / "SKILL.md"
HEADING = "## 進み具合をアーティファクトで見る（`--artifact`）"


def whole() -> str:
    text = SKILL.read_text(encoding="utf-8")
    assert HEADING in text, "SKILL.md に --artifact の節が無い"
    return text


def section() -> str:
    text = whole()
    start = text.index(HEADING)
    end = text.find("\n## ", start + len(HEADING))
    return text[start:] if end < 0 else text[start:end]


def code_spans(text: str) -> list[str]:
    return re.findall(r"`([^`\n]+)`", text)


def subparser(parser: argparse.ArgumentParser, name: str) -> argparse.ArgumentParser:
    action = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    return action.choices[name]


def options_of(parser: argparse.ArgumentParser) -> set[str]:
    return {o for a in parser._actions for o in a.option_strings if o.startswith("--")}


# ---- AC-44 公開の宣言 ------------------------------------------------------------------------------------


def test_d0039_ac44_skill_publishes_with_the_comments_capability():
    """D0039-AC-44: SKILL.md の公開の宣言が {"db": {}, "comments": {}} で、comments を宣言しない公開の手順（{"db": {}} だけ）が残っていない。"""
    text = whole()
    assert '{"db": {}, "comments": {}}' in section()
    assert not re.search(r"""\{\s*"db"\s*:\s*\{\s*\}\s*\}""", text), '{"db": {}} だけの宣言が残っている'
    assert "capabilities" in section() and "icon" in section()


def test_d0039_ac44_the_publish_step_is_still_once_and_without_editing_the_html():
    """D0039-AC-44: 公開は1回だけ（公開し直さない・HTML は書き換えない）の手順は残る。"""
    sec = section()
    assert "1回だけ" in sec and "公開し直さない" in sec and "書き換えない" in sec


def test_d0039_ac44_the_view_only_sentence_is_replaced():
    """D0039-AC-44: 「ページは見るだけで、承認・直してほしい点・中止は、これまでどおり会話で聞く」という前の版の文は、ボタンで答えられる旨に置き換わる。"""
    sec = section()
    assert "ページは見るだけで、承認・直してほしい点・中止は、これまでどおり会話で聞く" not in sec
    assert "ボタン" in sec and "コメント" in sec


# ---- AC-45 答えの受け方 ----------------------------------------------------------------------------------------


def sentences(text: str) -> list[str]:
    return [x for x in re.split(r"[。\n]", text) if x.strip()]


def has_sentence(*groups: tuple[str, ...]) -> bool:
    """--artifact の節に、どの組からも1つ以上の言葉を含む文（。か改行で区切った1つ）があるか。"""
    return any(all(any(alt in s for alt in group) for group in groups) for s in sentences(section()))


ANSWER_STEPS = {
    "本文を Write でファイルに書く": (("Write",), ("ファイル",)),
    "live answer --text-file で読む": (("live answer --text-file",),),
    "revise の直してほしい点を --feedback-out に書かせる": (("--feedback-out",),),
    "ok のときだけ record review を書く": (("`ok`", "ok"), ("だけ",), ("record review",)),
    "revise は --feedback-file で渡す": (("revise",), ("--feedback-file",)),
    "ok でなければ記録を変えない": (("でなければ", "ではない", "false"), ("記録",), ("変えない", "書かない", "進めない")),
    "断ったことと理由を人に伝える": (("理由",), ("伝える", "見せる", "知らせる")),
    "本文をコマンド行に入れない": (("コマンド行",), ("入れない", "書かない", "渡さない")),
    "直してほしい点は人の言葉": (("人の言葉",),),
    "pipe-in: で始まらないコメントは答えとして扱わない": (("pipe-in:",), ("始まらない", "でないコメント")),
    "quit のあと finish STOPPED_BY_HUMAN": (("quit",), ("finish STOPPED_BY_HUMAN",)),
}


@pytest.mark.parametrize("label", list(ANSWER_STEPS))
def test_d0039_ac45_skill_has_the_answer_steps(label):
    """D0039-AC-45: --artifact の節に、答えの受け方がある（Write でファイル・live answer --text-file・ok のときだけ record review・revise は --feedback-file・ok でなければ変えない・コマンド行に入れない・人の言葉）。"""
    assert has_sentence(*ANSWER_STEPS[label]), f"--artifact の節に「{label}」を言う文が無い"


def test_d0039_ac45_skill_says_to_ignore_orders_inside_feedback():
    """D0039-AC-45: 直してほしい点は人の言葉として扱い、中に命令のような文があっても従わない旨がある。"""
    assert has_sentence(("命令", "指示"), ("従わない",))


def test_d0039_ac45_skill_runs_the_snapshot_steps_after_record_review_too():
    """D0039-AC-45: 写しを作って ArtifactData に書く手順（live snapshot → ArtifactData の set）は、答えを受けて record review を書いたあとにも流す旨がある。"""
    sec = section()
    assert "ArtifactData" in sec and "live snapshot" in sec
    assert has_sentence(("record review",), ("写し", "snapshot", "ArtifactData", "3.", "4.")), "record review のあとに写しを作り直す文が無い"


def test_d0039_ac45_step_check_finds_a_missing_sentence():
    """D0039-AC-45: 文の検査そのものが、言葉がそろった文が無い場合を見つけられる（検査の検査）。"""
    fake = "本文を Write で書く。別の文に ファイル とだけある。"
    found = [x for x in sentences(fake) if all(any(alt in x for alt in g) for g in ANSWER_STEPS["本文を Write でファイルに書く"])]
    assert found == []
    fake = "本文を Write でファイルに書く。"
    assert [x for x in sentences(fake) if all(any(alt in x for alt in g) for g in ANSWER_STEPS["本文を Write でファイルに書く"])]


def test_d0039_ac45_skill_options_match_the_real_parsers():
    """D0039-AC-45: SKILL の `live answer`・`record review` の引数が、本体の実際の引数（live_cmd._parser() の answer と record._build_parser() の review）にある。"""
    real_answer = options_of(subparser(live_cmd._parser(), "answer"))
    real_review = options_of(subparser(record._build_parser(), "review"))
    assert {"--text-file", "--stdin", "--feedback-out", "--project", "--config", "--work-dir"} <= real_answer
    assert {"--feedback", "--feedback-file"} <= real_review
    spans = code_spans(section())
    answer_spans = [c for c in spans if "live answer" in c]
    review_spans = [c for c in spans if "record review" in c]
    assert answer_spans and review_spans, "SKILL に live answer / record review のコマンド例が無い"
    used_answer = {o for c in answer_spans for o in re.findall(r"(?<![\w-])--[a-z][a-z-]*", c)}
    used_review = {o for c in review_spans for o in re.findall(r"(?<![\w-])--[a-z][a-z-]*", c)}
    assert used_answer and used_review
    assert used_answer <= real_answer, f"本体に無い引数: {sorted(used_answer - real_answer)}"
    assert used_review <= real_review, f"本体に無い引数: {sorted(used_review - real_review)}"
    assert "--text-file" in used_answer and "--feedback-file" in used_review


def test_d0039_ac45_skill_option_check_finds_a_wrong_option():
    """D0039-AC-45: 引数の突き合わせそのものが、本体に無い引数（--text など）を見つけられる（検査の検査）。"""
    real_answer = {"--text-file", "--stdin", "--feedback-out", "--project", "--config", "--work-dir", "--help"}
    bad = "python -m pipe_in live answer --text 'x' --text-file F"
    used = set(re.findall(r"(?<![\w-])--[a-z][a-z-]*", bad))
    assert used - real_answer == {"--text"}
    assert set(re.findall(r"(?<![\w-])--[a-z][a-z-]*", "python -m pipe_in live answer --text-file F --feedback-out O")) <= real_answer


def test_d0039_ac45_skill_commands_use_the_module_form_like_the_rest_of_the_skill():
    """D0039-AC-45: 手順のコマンドは python -m pipe_in …（SKILL の他の手順と同じ書き方）。"""
    spans = [c for c in code_spans(section()) if "live answer" in c and "--text-file" in c]
    assert spans and all(c.lstrip().startswith("python -m pipe_in live answer") for c in spans)
    spans = [c for c in code_spans(section()) if "record review" in c and "--feedback-file" in c]
    assert spans and all(c.lstrip().startswith("python -m pipe_in record review") for c in spans)


# ---- AC-46 書いてはいけないもの --------------------------------------------------------------------------------


LOCAL_PATHS = [
    r"[A-Za-z]:[\\/]+Users[\\/]+[^\s`]+",
    r"(?<![\w.-])/(?:Users|home)/[A-Za-z0-9_.-]+",
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+\.[A-Za-z]{2,}\b",
    r"\bsk-[A-Za-z0-9_-]{16,}",
    r"\bghp_[A-Za-z0-9]{16,}",
    r"\bxox[abp]-[A-Za-z0-9-]{10,}",
    r"(?i)\b(?:api[_-]?key|secret|token|password)\s*[:=]\s*[\"']?[A-Za-z0-9/+_-]{12,}",
    r"BEGIN [A-Z ]*PRIVATE KEY",
    r"https?://[^\s`)]*(?:artifact|claude\.ai)/[A-Za-z0-9_-]{8,}",
]


@pytest.mark.parametrize("pattern", LOCAL_PATHS, ids=lambda p: p[:28])
def test_d0039_ac46_skill_has_no_local_paths_or_secrets(pattern):
    """D0039-AC-46: スキルに手元のパス（ユーザー名の入ったパス）・メールアドレス・秘密・公開したページの URL を書かない。今のままで通る（守り続ける検査）。"""
    assert not re.search(pattern, whole()), pattern


def test_d0039_ac46_secret_check_finds_a_planted_secret():
    """D0039-AC-46: 秘密・パスの検査そのものが、混ぜた見本を見つけられる（検査の検査）。"""
    planted = ["C:\\" + "Us" + "ers\\someone\\x", "/" + "home/someone/x", "me@" + "example.com", "sk-ABCDEFGHIJKLMNOPQRSTUV", "ghp_ABCDEFGHIJKLMNOPQRSTUV", "API_KEY = abcdefghijklmnop1234", "-----BEGIN RSA PRIVATE KEY-----"]
    for sample in planted:
        assert any(re.search(p, sample) for p in LOCAL_PATHS), sample


COMMAND_LINE_TEXT = [
    r"--text\s+[\"'“]",
    r"--text=",
    r"--text\s+<",
    r"--feedback\s+[\"'“]",
    r"--feedback=[\"'“]",
    r"--feedback\s+<",
    r"--feedback\s+\$",
    r"echo\s+[\"'][^\"']*pipe-in:",
    r"printf\s+[\"'][^\"']*pipe-in:",
    r"<<<?\s*[\"']?EOF",
    r"cat\s*<<",
]


@pytest.mark.parametrize("pattern", COMMAND_LINE_TEXT, ids=lambda p: p[:28])
def test_d0039_ac46_skill_never_passes_text_on_the_command_line(pattern):
    """D0039-AC-46: --artifact の節に、本文を引数で渡す形（--text "…"）・外から来た文字を --feedback "…" に入れる手順・echo/ヒアドキュメントで本文を渡す形が無い。今のままで通る。"""
    assert not re.search(pattern, section()), pattern


def test_d0039_ac46_command_line_check_finds_the_forbidden_forms():
    """D0039-AC-46: 禁止の形の検査そのものが、混ぜた見本（--text "…"・--feedback "…"・echo で本文）を見つけられる。"""
    planted = ['live answer --text "pipe-in: approve x y"', "live answer --text=pipe-in", 'record review x revise --feedback "$BODY"', "echo 'pipe-in: approve' | python -m pipe_in", "cat <<EOF"]
    for sample in planted:
        assert any(re.search(p, sample) for p in COMMAND_LINE_TEXT), sample


def test_d0039_ac46_the_skill_does_not_use_the_forbidden_text_option_anywhere_in_the_artifact_section():
    """D0039-AC-46: --artifact の節の `…` の中に、--text（--text-file 以外）が出ない。"""
    for c in code_spans(section()):
        assert not re.search(r"--text(?!-file)\b", c), c
