"""D0096-AC-01〜03・10〜17・22・29〜32：プラグインの eval を下位のモデルでラウンドとして回し、落ちた所を直して育てるための、
プラグインの文（pipe-judge・pipe-builder・stage-rules.md）・eval のケース・ガイド・版。AC-29 は、pipe-builder の pipe-in-gen new が
失敗したときに、ひな形を使わずに Write で手で書く決まり（範囲は広げない）。AC-30〜32 は、審査だけで差し戻す形（judge と on_fail があり
command が無い段）を、pipe-build のスキルが任せる前に・pipe-builder が書く前に止める決まり（足す文が eval の採点に当たらないことも見る）。

ケースを流す（claude plugin eval）のは実機で、利用料がかかる。ここでは流さず、ファイルを読むだけ。
採点の正規表現は、trace（1 メッセージ 1 行の JSON。日本語は逃がさない）と、JSON にした道具の入力の見本の文字に当てて確かめる。
読み手と検査の関数は tests/test_plugin_evals.py のものを使う（書き写さない）。見本は tmp_path の中に作る。
SDK・claude plugin eval・子プロセス・ネットワークは使わない（司会役は chat_cmd.main を直に呼ぶ）。
"""

from __future__ import annotations

import fnmatch
import json
import re
from pathlib import Path

import pytest
from chat_support import Run, no_sdk, text_of  # noqa: F401
from test_plugin_evals import (  # noqa: PLC2701
    BAD_AFTER_GOOD,
    BAD_BAD_SHAPE,
    CASE_NAMES,
    CASES,
    EVALS,
    GOOD_BAD_SHAPE,
    PLUGIN,
    ROOT,
    SKILLS,
    _case_dir,
    _files,
    _graders,
    _load_scaffold,
    check_case,
    check_suite,
    make_good_case,
    read_front,
)

from pipe_in.pipe import capability

GUIDE = ROOT / "docs" / "guide" / "plugin.md"
JUDGE_SKILL = PLUGIN / "skills" / "pipe-judge" / "SKILL.md"
BUILD_SKILL = PLUGIN / "skills" / "pipe-build" / "SKILL.md"
BUILDER = PLUGIN / "agents" / "pipe-builder.md"
STAGE_RULES = PLUGIN / "skills" / "pipe-build" / "references" / "stage-rules.md"
TEMPLATES = sorted((ROOT / "generator" / "templates").glob("*/pipe.toml"))

NEW_CASES = ["run-dry-run-asks-first", "run-refuses-unsupported", "live-stops-without-tools"]
RUN_CASES = {"run-dry-run-asks-first": "notes-digest", "run-refuses-unsupported": "notes-parallel"}
LIVE_CASE = "live-stops-without-tools"
THRESHOLD = 0.8  # ラウンドの止める前の確かめの合格の線（--threshold 0.8）
SUMMARY_PIPE_DIR = ".pipe-in/pipes/pipe-in-notes-summary"
REVIEW_PIPE_TOML = ".pipe-in/pipes/pipe-in-notes-review/pipe.toml"


# ---- 補助：文書の節 ------------------------------------------------------------------------------------


def _lines_outside_fences(text: str) -> list[tuple[str, bool]]:
    """(行, 囲み（```）の外か)。囲みの中の # の行を見出しと読まないため。"""
    out: list[tuple[str, bool]] = []
    inside = False
    for ln in text.splitlines():
        if ln.lstrip().startswith("```"):
            out.append((ln, False))
            inside = not inside
            continue
        out.append((ln, not inside))
    return out


def heading_line(text: str, head: str) -> int:
    """head で始まる見出しの行の番号（0 から）。無ければ -1。"""
    for i, (ln, outside) in enumerate(_lines_outside_fences(text)):
        if outside and ln.startswith(head):
            return i
    return -1


def section(text: str, head: str) -> str:
    """head で始まる見出しの本文。次の同じか上の階層の見出しの手前まで。無ければ空。"""
    level = len(head) - len(head.lstrip("#"))
    lines = _lines_outside_fences(text)
    start = heading_line(text, head)
    if start < 0:
        return ""
    body: list[str] = []
    for ln, outside in lines[start + 1 :]:
        m = re.match(r"^(#+)\s", ln)
        if outside and m and len(m.group(1)) <= level:
            break
        body.append(ln)
    return "\n".join(body)


# ---- 補助：trace と道具の入力の見本 ------------------------------------------------------------------------


def trace(*messages: dict) -> str:
    """claude plugin eval の trace の形：1 メッセージ 1 行の JSON（日本語は \\u に逃がさない）。"""
    return "".join(json.dumps(m, ensure_ascii=False) + "\n" for m in messages)


def text_msg(text: str) -> dict:
    return {"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}}


def tool_msg(name: str, tool_input: dict) -> dict:
    return {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": name, "input": tool_input}]}}


def result_msg(text: str) -> dict:
    return {"type": "user", "message": {"content": [{"type": "tool_result", "content": text}]}}


def tool_input(command: str, description: str = "コマンドを流す", *, compact: bool = False) -> str:
    """tool_used の input_match が当たる「JSON にした入力」（Bash の {"command": …, "description": …}）。"""
    data = {"command": command, "description": description}
    if compact:
        return json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return json.dumps(data, ensure_ascii=False)


def grader(case: str, filename: str) -> dict:
    found = [fm for g, fm, _ in _graders(case) if g.name == filename]
    assert found, f"{case}/graders/{filename} が無い"
    return found[0]


def compiled(fm: dict, key: str = "pattern") -> re.Pattern[str]:
    return re.compile(fm[key], re.I if fm.get("flags") == "i" else 0)


def weighted(case: str, failing: set[str]) -> float:
    """採点の重み（無ければ 1）つきの平均。failing の採点だけが落ちたときの点。"""
    weights = [(g.name, fm.get("weight", 1)) for g, fm, _ in _graders(case)]
    total = sum(w for _, w in weights)
    return sum(w for name, w in weights if name not in failing) / total


# ---- AC-01・02：pipe-judge の断り方と返し方 ----------------------------------------------------------------


def judge_body() -> str:
    return read_front(JUDGE_SKILL.read_text(encoding="utf-8"))[1]


def test_D0096_AC_01_judge_refuses_bad_runs_before_cost_and_agent():
    """D0096-AC-01: pipe-judge の SKILL.md で、「## 2.」（利用料の確認）・「## 3.」（審査役を呼ぶ）より前の 1 行に、
    --runs の範囲（1〜5）の外なら止まり、確認を出さず・審査役を呼ばず・judge-score を流さないことが書かれている。"""
    body = judge_body()
    at2, at3 = heading_line(body, "## 2."), heading_line(body, "## 3.")
    assert 0 <= at2 < at3, "「## 2.」「## 3.」の見出しが読めない"
    words = ["--runs", "1〜5", "止ま", "確認", "審査役", "judge-score"]
    before = [ln for ln, _ in _lines_outside_fences(body)[:at2]]
    assert [ln for ln in before if all(w in ln for w in words)], f"「## 2.」より前に、{words} を全部含む 1 行が無い"


def test_D0096_AC_02_judge_pastes_judge_score_json():
    """D0096-AC-02: pipe-judge の SKILL.md の「## 5.」に、judge-score の JSON を要約に置き換えず、```json の囲みでそのまま貼ることが書かれている。"""
    five = section(judge_body(), "## 5.")
    assert five.strip(), "「## 5.」の節が無い"
    missing = [w for w in ["```json", "そのまま", "要約", "judge-score"] if w not in five]
    assert missing == []


# ---- AC-03：pipe-builder と stage-rules.md の名前の決まり ----------------------------------------------------


@pytest.mark.parametrize("path", [BUILDER, STAGE_RULES], ids=["pipe-builder.md", "stage-rules.md"])
def test_D0096_AC_03_builder_and_stage_rules_have_naming_rule(path):
    """D0096-AC-03: pipe-builder.md と stage-rules.md の「## 名前の決まり」に、頭に 2 桁の番号を付けること・避ける 4 つの語
    （capability.SUBAGENT_REFUSED_HEADS）・Claude Code がサブエージェントの書き込みを断るという理由が書かれている。"""
    rule = section(path.read_text(encoding="utf-8"), "## 名前の決まり")
    assert rule.strip(), f"{path.name} に「## 名前の決まり」の節が無い"
    assert re.search(r"2\s?桁", rule), "2 桁の番号の決まりが無い"
    missing = [w for w in ["番号", "サブエージェント", "断", *capability.SUBAGENT_REFUSED_HEADS] if w not in rule]
    assert missing == []


def test_D0096_AC_03_naming_rule_sits_where_it_is_read():
    """D0096-AC-03: 名前の決まりは、pipe-builder.md では「## 作るとき」の前にあり、「## 作るとき」がその決まりを指す。
    stage-rules.md では「## 段の決め方」と「## 検査と審査の組み方」の間にある。"""
    builder = BUILDER.read_text(encoding="utf-8")
    assert 0 <= heading_line(builder, "## 名前の決まり") < heading_line(builder, "## 作るとき")
    assert "名前の決まり" in section(builder, "## 作るとき")
    rules = STAGE_RULES.read_text(encoding="utf-8")
    at = heading_line(rules, "## 名前の決まり")
    assert heading_line(rules, "## 段の決め方") < at < heading_line(rules, "## 検査と審査の組み方")


# ---- AC-10：build-passes-check の「check が通った」採点 ---------------------------------------------------------

CHECK_OK = "✓ パイプ「notes-summary」: 問題ありません"
CHECK_WARN = "✓ パイプ「notes-summary」: 誤りはありません（注意 1 件）"
CHECK_WARN_MANY = "✓ パイプ「notes-summary」: 誤りはありません（注意 12 件）"


def test_D0096_AC_10_check_passed_grader_hits_success_lines():
    """D0096-AC-10: build-passes-check の 07-check-passed は trace を見る regex で、pipe-in-gen check の 2 つの成功の行に当たる
    （生の文字と、道具の結果として trace に入った形の両方）。"""
    fm = grader("build-passes-check", "07-check-passed.md")
    assert fm["type"] == "regex" and fm.get("target") == "trace" and fm.get("match", "contains") == "contains"
    pattern = compiled(fm)
    for line in [CHECK_OK, CHECK_WARN, CHECK_WARN_MANY]:
        assert pattern.search(line), line
        run = trace(tool_msg("Bash", {"command": "pipe-in-gen check notes-summary --project ."}), result_msg(line + "\n"))
        assert pattern.search(run), line


def test_D0096_AC_10_check_passed_grader_misses_other_text():
    """D0096-AC-10: 07-check-passed は、✗ の誤りの行・pipe-builder.md の説明の文（全文）・check のコマンドの文字・ほかのパイプ名の成功の行・
    ✓ の無い言い換えには当たらない（check を呼んだだけでは合格にしない）。"""
    pattern = compiled(grader("build-passes-check", "07-check-passed.md"))
    misses = {
        "誤りの行": "✗ パイプ「notes-summary」に誤りがあります:\n  - 段「summary」の output が空です",
        "pipe-builder.md の全文": BUILDER.read_text(encoding="utf-8"),
        "コマンドの文字": tool_input("pipe-in-gen check notes-summary --project ."),
        "ほかのパイプの成功の行": "✓ パイプ「notes-review」: 問題ありません",
        "✓ の無い言い換え": "pipe-in-gen check の結果：問題ありません",
    }
    for label, text in misses.items():
        assert not pattern.search(text), label
        assert not pattern.search(trace(result_msg(text))), label


def test_D0096_AC_10_check_passed_weight_drops_below_threshold():
    """D0096-AC-10: 07-check-passed だけが落ちたときの重みつきの点が、合格の線 0.8 を下回る。"""
    names = {g.name for g, _, _ in _graders("build-passes-check")}
    assert "07-check-passed.md" in names, "07-check-passed.md が無い"
    assert weighted("build-passes-check", {"07-check-passed.md"}) < THRESHOLD


# ---- AC-11：指示文の名前の番号 --------------------------------------------------------------------------------


def test_D0096_AC_11_numbered_prompt_grader():
    """D0096-AC-11: build-passes-check の 08-numbered-prompt は file_exists で、notes-summary の prompts/ の下に、頭が番号の .md があることを見る
    （fnmatch で 01_summary.md に当たり、summary.md に当たらない）。"""
    fm = grader("build-passes-check", "08-numbered-prompt.md")
    assert fm["type"] == "file_exists" and fm.get("exists", True) is True
    path = fm["path"]
    prefix = f"{SUMMARY_PIPE_DIR}/prompts/"
    assert path.startswith(prefix) and path.endswith(".md"), path
    assert fnmatch.fnmatchcase(prefix + "01_summary.md", path)
    assert not fnmatch.fnmatchcase(prefix + "summary.md", path)


# ---- AC-12：build-refuses-judge-only の悪い形の採点 -------------------------------------------------------------


def bad_shape() -> re.Pattern[str]:
    return compiled(grader("build-refuses-judge-only", "01-no-bad-shape.md"))


def forms(text: str) -> dict[str, str]:
    """同じ文字を、生のまま・Write の content・Edit の new_string・返事の文として trace に入れた形。"""
    return {
        "生": text,
        "Write の content": trace(tool_msg("Write", {"file_path": REVIEW_PIPE_TOML, "content": text})),
        "Edit の new_string": trace(tool_msg("Edit", {"file_path": REVIEW_PIPE_TOML, "old_string": "", "new_string": text})),
        "返事の文": trace(text_msg(text)),
    }


def test_D0096_AC_12_bad_shape_grader_reads_trace():
    """D0096-AC-12: 01-no-bad-shape は regex の not_contains で、target が trace（ファイルを指さないので、pipe.toml が作られなくても grader threw にならない）。"""
    fm = grader("build-refuses-judge-only", "01-no-bad-shape.md")
    assert fm["type"] == "regex"
    assert fm.get("target") == "trace"
    assert fm.get("match") == "not_contains"


def test_D0096_AC_12_bad_shape_hits_raw_and_json():
    """D0096-AC-12: 悪い形（command が無いのに on_fail と judge がある段）の文字に、生のまま（改行のある TOML）でも、
    JSON の文字列にしたもの（Write・Edit・返事の文）でも当たる。"""
    pattern = bad_shape()
    for name, sample in [("悪い形", BAD_BAD_SHAPE), ("良い段のあとの悪い段", BAD_AFTER_GOOD)]:
        for form, text in forms(sample).items():
            assert pattern.search(text), (name, form)


def test_D0096_AC_12_bad_shape_misses_good_rules_and_templates():
    """D0096-AC-12: 良い形（command と組んだ形）・stage-rules.md の例（全文）・ひな形の pipe.toml・依頼の表の文字には、
    生のままでも JSON の文字列にしても当たらない。依頼 → pipe-builder への依頼（stage-rules.md を貼る）→ 良い形の Write → 返事、の trace にも当たらない。"""
    pattern = bad_shape()
    request = (EVALS / "build-refuses-judge-only" / "prompt.md").read_text(encoding="utf-8")
    rules = STAGE_RULES.read_text(encoding="utf-8")
    samples = {"良い形": GOOD_BAD_SHAPE, "stage-rules.md": rules, "依頼の表": request}
    assert TEMPLATES, "ひな形の pipe.toml を読めない"
    samples.update({f"ひな形 {p.parent.name}": p.read_text(encoding="utf-8") for p in TEMPLATES})
    for name, sample in samples.items():
        for form, text in forms(sample).items():
            assert not pattern.search(text), (name, form)
    whole = trace(
        {"type": "user", "message": {"content": request}},
        tool_msg("Agent", {"subagent_type": "pipe-in:pipe-builder", "prompt": "段の決め方（stage-rules.md）:\n" + rules}),
        tool_msg("Write", {"file_path": REVIEW_PIPE_TOML, "content": GOOD_BAD_SHAPE}),
        text_msg("審査だけで on_fail を書く形は作れないので、command と組みました。"),
    )
    assert not pattern.search(whole)


def test_D0096_AC_12_bad_shape_does_not_cross_messages():
    """D0096-AC-12: 悪い形の採点は、別のメッセージにまたがって当たらない（[[stages]] を書いた Write と、on_fail と judge の語を含む
    後の返事は、合わせても悪い形ではない）。同じ 1 つのメッセージの中なら当たる（止める語はメッセージの境だけで効く）。"""
    pattern = bad_shape()
    stage_only = '[pipe]\nkind = "linear"\nlabel = "見直す"\n\n[[stages]]\nname = "review"\noutput = "01_review.md"\naccess = "read"\n'
    explain = '審査だけの形（on_fail = "review" と [stages.check.judge] だけの check）は作れません。'
    joined = trace(tool_msg("Write", {"file_path": REVIEW_PIPE_TOML, "content": stage_only}), text_msg(explain))
    assert not pattern.search(joined)
    assert pattern.search(trace(text_msg(stage_only + "\n" + explain)))


# ---- AC-13：pipe-run のケース 2 本 ----------------------------------------------------------------------------

RUN_COMMON = {"01-dry-run.md": ("Bash", 2), "02-no-start.md": ("Bash", 2), "03-no-agent.md": ("Agent", 1)}


@pytest.mark.parametrize("case", list(RUN_CASES))
def test_D0096_AC_13_run_cases_shape(case):
    """D0096-AC-13: pipe-run のケースの本文は /pipe-in:pipe-run で始まり（フックは確かめ済みと伝える）、tags は pipe-run と cheap。
    Agent は許し（呼ばないことを測るため）、AskUserQuestion は許さない。--dry-run の付いた chat start を呼んだ採点（重み 2）・
    --dry-run の無い chat start を呼ばない採点（重み 2）・エージェントを呼ばない採点（重み 1）を持つ。"""
    fm, body = read_front((_case_dir(case) / "prompt.md").read_text(encoding="utf-8"))
    assert body.lstrip().startswith("/pipe-in:pipe-run")
    assert "確かめ済み" in body
    assert "pipe-run" in fm["tags"] and "cheap" in fm["tags"] and "agent" not in fm["tags"], fm["tags"]
    assert "Agent" in fm["allowed_tools"] and "AskUserQuestion" not in fm["allowed_tools"], fm["allowed_tools"]
    graders = {g.name: g_fm for g, g_fm, _ in _graders(case)}
    for name, (tool, weight) in RUN_COMMON.items():
        assert name in graders, f"{case}/graders/{name} が無い"
        g = graders[name]
        assert g["type"] == "tool_used" and g["tool"] == tool and g.get("weight", 1) == weight, (name, g)
    assert graders["01-dry-run.md"].get("min", 1) >= 1 and "input_match" in graders["01-dry-run.md"]
    for name in ("02-no-start.md", "03-no-agent.md"):
        assert graders[name].get("min") == 0 and graders[name].get("max") == 0, name
    assert "input_match" in graders["02-no-start.md"]


def test_D0096_AC_13_run_cases_share_common_graders():
    """D0096-AC-13: 2 本の 01〜03 の採点は同じ中身（どちらのケースでも同じ道具の使い方を測る）。"""
    a, b = list(RUN_CASES)
    for name in RUN_COMMON:
        assert grader(a, name) == grader(b, name), name


@pytest.mark.parametrize("case", list(RUN_CASES))
def test_D0096_AC_13_dry_run_grader_hits(case):
    """D0096-AC-13: 01-dry-run の input_match は、--dry-run の付いた chat start（--memo の引用符を越えても）に当たり、
    --dry-run の無い start（説明の文に --dry-run があっても）・ほかのコマンドには当たらない。"""
    pattern = compiled(grader(case, "01-dry-run.md"), "input_match")
    pipe = RUN_CASES[case]
    hits = [
        f"pipe-in-gen chat start {pipe} --dry-run",
        f'pipe-in-gen chat start {pipe} --memo "notes/ を読んで" --dry-run',
        f'pipe-in-gen chat start {pipe} --dry-run --memo "x"',
    ]
    for command in hits:
        for compact in (False, True):
            assert pattern.search(tool_input(command, compact=compact)), (command, compact)
    misses = [
        tool_input(f'pipe-in-gen chat start {pipe} --memo "x"', "--dry-run を付けずに始める"),
        tool_input("pipe-in-gen chat --help"),
        tool_input("pipe-in-gen --help", "chat start の --dry-run を確かめる"),
    ]
    for text in misses:
        assert not pattern.search(text), text


@pytest.mark.parametrize("case", list(RUN_CASES))
def test_D0096_AC_13_no_start_grader_hits_real_start_only(case):
    """D0096-AC-13: 02-no-start の input_match は、--dry-run も --help も無い chat start（--dry-run のあとに && でつないだ本当の start を含む）に当たり、
    --dry-run・--help の付いた start と、説明の文の中の「pipe-in-gen chat start」には当たらない。"""
    pattern = compiled(grader(case, "02-no-start.md"), "input_match")
    pipe = RUN_CASES[case]
    hits = [
        f'pipe-in-gen chat start {pipe} --memo "notes/ を読んで"',
        f"pipe-in-gen chat start {pipe}",
        f'pipe-in-gen chat start {pipe} --dry-run && pipe-in-gen chat start {pipe} --memo "x"',
    ]
    for command in hits:
        for compact in (False, True):
            assert pattern.search(tool_input(command, compact=compact)), (command, compact)
    misses = [
        f"pipe-in-gen chat start {pipe} --dry-run",
        f'pipe-in-gen chat start {pipe} --dry-run --memo "x"',
        f'pipe-in-gen chat start {pipe} --memo "x" --dry-run',
        "pipe-in-gen chat start --help",
    ]
    for command in misses:
        for compact in (False, True):
            assert not pattern.search(tool_input(command, compact=compact)), (command, compact)
    described = tool_input(f"pipe-in-gen chat start {pipe} --dry-run", "pipe-in-gen chat start の前に段の表を見る")
    assert not pattern.search(described)


def test_D0096_AC_13_answer_graders_hit_table_and_question():
    """D0096-AC-13: run-dry-run-asks-first の 04-table は段の表の成果物（01_digest.md）に、05-asks は「始める」「やめる」の問いに当たる。
    run-refuses-unsupported の 04-reason は断る理由（group・並列）に当たる。"""
    table = compiled(grader("run-dry-run-asks-first", "04-table.md"))
    asks = compiled(grader("run-dry-run-asks-first", "05-asks.md"))
    reply = "段の表：\n| 段 | 成果物 |\n| --- | --- |\n| digest | 01_digest.md |\n\n始めますか？\n1. 始める（推し）\n2. やめる"
    assert table.search(reply) and asks.search(reply)
    assert not table.search("段の表を見せました")
    assert not asks.search("段の表を見せました。始めます。")
    reason = compiled(grader("run-refuses-unsupported", "04-reason.md"))
    assert reason.search("段「first」のgroup（並列の段）は、会話の中では流せません")
    assert not reason.search("パイプを始めました")


@pytest.mark.parametrize("case", list(RUN_CASES))
def test_D0096_AC_13_run_case_weights(case):
    """D0096-AC-13: 01-dry-run だけ、または 02-no-start だけが落ちると、点が合格の線 0.8 を下回る。ほかの採点が 1 つだけ落ちても線は下回らない
    （言い回しの採点で落としすぎない）。"""
    names = {g.name for g, _, _ in _graders(case)}
    for key in ("01-dry-run.md", "02-no-start.md"):
        assert weighted(case, {key}) < THRESHOLD, key
    for other in sorted(names - {"01-dry-run.md", "02-no-start.md"}):
        assert weighted(case, {other}) >= THRESHOLD, other


# ---- AC-14：pipe-run の見本を司会役に通す ---------------------------------------------------------------------

RUN_EXPECT = {"run-dry-run-asks-first": True, "run-refuses-unsupported": False}


@pytest.mark.usefixtures("no_sdk")
@pytest.mark.parametrize("case", list(RUN_CASES))
def test_D0096_AC_14_run_scaffolds_with_chat_dry_run(case, tmp_path, monkeypatch):
    """D0096-AC-14: pipe-run の 2 本の見本を tmp_path に作って chat start --dry-run（chat_cmd.main）に渡すと、
    (a) run-dry-run-asks-first は断られずに段の表（01_digest.md）が返り、(b) run-refuses-unsupported は group で断られる
    （定義の誤りではない）。どちらもファイルは増えず、子プロセスを起こさない。"""

    def no_process(*args, **kwargs):
        raise AssertionError("子プロセスを起こした")

    monkeypatch.setattr("subprocess.Popen", no_process)
    ws = tmp_path / "ws"
    ws.mkdir()
    _load_scaffold(case).build(ws)
    before = _files(ws)
    r = Run(ws, RUN_CASES[case])
    out = r.start("--dry-run", memo="notes/ を読んで")
    assert _files(ws) == before
    if RUN_EXPECT[case]:
        assert r.code == 0 and out["ok"] is True, out
        assert "01_digest.md" in text_of(out), out
    else:
        assert r.code == 1 and out["ok"] is False, out
        assert "group" in out["message"], out
        assert "誤りがあります" not in out["message"], out


# ---- AC-15：pipe-live のケース 1 本 ---------------------------------------------------------------------------

LIVE_NO_CALLS = {"01-no-page.md": "Bash", "02-no-watch.md": "Bash", "03-no-write.md": "Write"}


def test_D0096_AC_15_live_case_shape():
    """D0096-AC-15: pipe-live のケースの本文は /pipe-in:pipe-live で始まり、tags は pipe-live と cheap だけ、allowed_tools は読む道具と Skill だけ。
    live page --out・live watch を呼ばない採点・Write を呼ばない採点（どれも min 0・max 0）と、道具が無いことを伝える語の採点（flags: i）を持つ。"""
    fm, body = read_front((_case_dir(LIVE_CASE) / "prompt.md").read_text(encoding="utf-8"))
    assert body.lstrip().startswith("/pipe-in:pipe-live")
    assert sorted(fm["tags"]) == ["cheap", "pipe-live"], fm["tags"]
    assert set(fm["allowed_tools"]) == {"Read", "Glob", "Grep", "Skill"}, fm["allowed_tools"]
    graders = {g.name: g_fm for g, g_fm, _ in _graders(LIVE_CASE)}
    for name, tool in LIVE_NO_CALLS.items():
        assert name in graders, f"{LIVE_CASE}/graders/{name} が無い"
        g = graders[name]
        assert g["type"] == "tool_used" and g["tool"] == tool and g.get("min") == 0 and g.get("max") == 0, (name, g)
    says = graders.get("04-says-no-tools.md")
    assert says is not None, f"{LIVE_CASE}/graders/04-says-no-tools.md が無い"
    assert says["type"] == "regex" and says.get("flags") == "i"


def test_D0096_AC_15_live_graders_hit_and_miss():
    """D0096-AC-15: 01-no-page は live page --out に当たり --help に当たらない。02-no-watch は live watch に当たる。
    04-says-no-tools は、Artifact・Monitor が無いと伝える文（日本語でも英語でも。英語の言い方 doesn't have（まっすぐな ' と曲がった ’ の両方）・
    missing・aren't available と、日本語の「見つかりません」を含む。ラウンド 3 で、正しく止まった英語の返事を落としたため）に当たり、
    ページを作った・見張る文（英語の文を含む）と、Monitor を言わない文には当たらない。"""
    page = compiled(grader(LIVE_CASE, "01-no-page.md"), "input_match")
    assert page.search(tool_input("pipe-in live page --out live.html"))
    assert page.search(tool_input("pipe-in live page --work-dir docs/pipeline/sample --out x.html"))
    assert not page.search(tool_input("pipe-in live page --help", "--out の書き方を見る"))
    watch = compiled(grader(LIVE_CASE, "02-no-watch.md"), "input_match")
    assert watch.search(tool_input("pipe-in live watch --work-dir docs/pipeline/sample --out x.json"))
    assert not watch.search(tool_input("pipe-in live page --help"))
    says = compiled(grader(LIVE_CASE, "04-says-no-tools.md"))
    hits = [
        "この会話には Artifact・ArtifactData・Monitor が無いので、何もせずに止まります。",
        "The Artifact and Monitor tools are not available here, so I stopped.",
        "This session doesn't have the tools this skill needs: Artifact, ArtifactData, and Monitor, so I stopped.",
        "This session doesn’t have the tools this skill needs: Artifact, ArtifactData, and Monitor, so I stopped.",
        "Artifact and Monitor are missing in this session.",
        "Artifact and Monitor aren't available here.",
        "Artifact・ArtifactData・Monitor が見つかりません。",
    ]
    assert [t for t in hits if not says.search(t)] == [], "道具が無いと伝える文に当たらない"
    misses = [
        "Artifact のページを作り、Monitor で見張っています。",
        "Artifact が無いので止まります。",
        "I published the Artifact page and started Monitor to watch the run.",
    ]
    assert [t for t in misses if says.search(t)] == [], "ページを作った・見張る文、Monitor を言わない文に当たる"


def test_D0096_AC_15_live_scaffold_is_running_record(tmp_path):
    """D0096-AC-15: pipe-live の見本は、pipeline.toml と、動いている途中の記録（final が null の state.json）を作る
    （0 章を読み飛ばすと、ページを作る 2 章へ進める材料を置いておく）。"""
    _load_scaffold(LIVE_CASE).build(tmp_path)
    assert "work_dir" in (tmp_path / "pipeline.toml").read_text(encoding="utf-8")
    state = json.loads((tmp_path / "docs" / "pipeline" / "sample" / "state.json").read_text(encoding="utf-8"))
    assert {"pipe", "stages", "runs"} <= set(state) and state.get("final", "missing") is None, state


# ---- AC-16：ケースの表（スキル 5 つ・12 本） ----------------------------------------------------------------

TABLE_COUNTS = {"pipe-build": 3, "pipe-eval": 3, "pipe-judge": 3, "pipe-run": 2, "pipe-live": 1}


def make_suite(root: Path, cases: dict[str, list[str]], *, tags: dict[str, str] | None = None) -> None:
    """tmp_path にケースの表どおりの最小のケースを作る（make_good_case のスキル名を表のスキルに替える）。tags で、ケースの tags のスキルだけを別にできる。"""
    for skill, names in cases.items():
        for name in names:
            case = make_good_case(root, name)
            prompt = case / "prompt.md"
            use = (tags or {}).get(name, skill)
            prompt.write_text(prompt.read_text(encoding="utf-8").replace("pipe-build", use), encoding="utf-8")


def small_table() -> dict[str, list[str]]:
    return {"pipe-build": ["b-one"], "pipe-eval": ["e-one"], "pipe-judge": ["j-one"], "pipe-run": ["r-one"], "pipe-live": ["l-one"]}


def test_D0096_AC_16_case_table_has_five_skills_twelve_cases():
    """D0096-AC-16: ケースの表はスキル 5 つ（pipe-build・pipe-eval・pipe-judge が 3 本ずつ、pipe-run 2 本、pipe-live 1 本。全部で 12 本）で、
    実物の plugin/evals/ が、表とそろっている（ケースの検査の AC-01 が通る）。"""
    assert set(SKILLS) == set(TABLE_COUNTS) and set(CASES) == set(TABLE_COUNTS)
    assert {s: len(names) for s, names in CASES.items()} == TABLE_COUNTS
    assert len(CASE_NAMES) == 12 and len(set(CASE_NAMES)) == 12
    assert [e for e in check_suite(EVALS) if e.startswith("AC-01")] == []


def test_D0096_AC_16_check_suite_passes_good_small_table(tmp_path):
    """D0096-AC-16: 検査の土台。表どおりに作った最小のケースの集まりは、表と比べる検査を通る（壊したものだけが落ちることを示す）。"""
    table = small_table()
    make_suite(tmp_path, table)
    assert check_suite(tmp_path, cases=table) == []


def test_D0096_AC_16_check_suite_rejects_folder_not_in_table(tmp_path):
    """D0096-AC-16: 検査そのものの確かめ。表に無いケースのフォルダがあると、表とそろっていないと落とす。"""
    table = small_table()
    make_suite(tmp_path, table)
    make_good_case(tmp_path, "x-stray")
    errors = check_suite(tmp_path, cases=table)
    assert any("そろっていない" in e and "x-stray" in e for e in errors), errors


def test_D0096_AC_16_check_suite_rejects_skill_without_cases(tmp_path):
    """D0096-AC-16: 検査そのものの確かめ。表にケースの無いスキル（pipe-live）があると落とす。"""
    table = small_table()
    del table["pipe-live"]
    make_suite(tmp_path, table)
    errors = check_suite(tmp_path, cases=table)
    assert any("ケースの無いスキル" in e and "pipe-live" in e for e in errors), errors


def test_D0096_AC_16_check_suite_rejects_count_per_skill(tmp_path):
    """D0096-AC-16: 検査そのものの確かめ。フォルダの名前は表とそろっていても、tags のスキルごとの数が表と違うと落とす。"""
    table = small_table()
    make_suite(tmp_path, table, tags={"b-one": "pipe-eval"})
    errors = check_suite(tmp_path, cases=table)
    assert not any("そろっていない" in e for e in errors), errors
    assert any("スキルごとのケースの数が表と違う" in e for e in errors), errors


@pytest.mark.parametrize("name", NEW_CASES)
def test_D0096_AC_16_new_cases_pass_d0045_checks(name):
    """D0096-AC-16: 新しい 3 本も、D0045 のケースの検査（prompt.md・採点・case.yaml・scaffold の形）をすべて通る。"""
    assert check_case(_case_dir(name)) == []


# ---- AC-17：ガイドのラウンドの回し方 -------------------------------------------------------------------------

ROUND_WORDS = ["--model haiku", "--judge-model haiku", "--runs 1", "--ablation none", "--max-cost-usd", "pip install .", "root", "rounds.py"]


def test_D0096_AC_17_guide_has_round_section_words():
    """D0096-AC-17: ガイドの「プラグインの eval」の節に、小節「ラウンドの回し方」があり、ラウンドの語（--model haiku・--judge-model haiku・--runs 1・
    --ablation none・--max-cost-usd・pip install .・root・rounds.py）がある。節に、測った費用（$0.11）・12 本・12 本のケース名があり、
    「まだ測っていません」は残っていない。"""
    md = GUIDE.read_text(encoding="utf-8")
    evals = section(md, "## プラグインの eval")
    assert evals.strip(), "「## プラグインの eval」の節が無い"
    rounds = section(evals, "### ラウンドの回し方")
    assert rounds.strip(), "「### ラウンドの回し方」の小節が無い"
    assert [w for w in ROUND_WORDS if w not in rounds] == []
    assert [w for w in ["$0.11", "12 本", *CASE_NAMES] if w not in evals] == []
    assert "まだ測っていません" not in evals


# ---- AC-22：版と更新の節 --------------------------------------------------------------------------------------


def test_D0096_AC_22_version_and_guide_notes():
    """D0096-AC-22: plugin.json の version が 0.6.1。ガイドの「版を上げる決まり」に 0.6.1 があり、「## 0.6.0 から更新するとき」の節
    （ディレクトリへの申請の節と 0.5.x の節の間）に、0.6.1 で変わること（pipe-judge・pipe-builder）と pipe-in-gen の入れ直しがある。"""
    manifest = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert manifest["version"] == "0.6.1"
    md = GUIDE.read_text(encoding="utf-8")
    versioning = section(section(md, "## ディレクトリへの申請"), "### 版を上げる決まり")
    assert "0.6.1" in versioning
    update = section(md, "## 0.6.0 から更新するとき")
    assert update.strip(), "「## 0.6.0 から更新するとき」の節が無い"
    missing = [w for w in ["0.6.1", "pipe-judge", "pipe-builder", "pipe-in-gen", "pip install", "/reload-plugins"] if w not in update]
    assert missing == []
    assert md.index("## ディレクトリへの申請") < md.index("## 0.6.0 から更新するとき") < md.index("## 0.5.x から更新するとき")


# ---- AC-29：pipe-builder の new が失敗したとき ------------------------------------------------------------------

FALLBACK_WORDS = ["失敗", "ひな形を使わず", "表どおり", "Write", "`pipe.toml`", "`prompts/", "`README.md`", "pipe-in-gen check", "同じ名前", "フック", "差し戻"]
NO_BASH_WRITE_WORDS = ["--force", "mkdir", "cat ", "tee ", "echo ", "python -c"]
SCOPE_WORDS = [
    "`pipe.toml`・`README.md`・`prompts/*.md` だけ",
    "`pipe-in-gen list` / `pipe-in-gen new` / `pipe-in-gen check` だけ",
    "`--force` は付けない",
    "すり抜け",
    "差し戻",
]


def builder_section(head: str) -> str:
    return section(BUILDER.read_text(encoding="utf-8"), head)


def test_D0096_AC_29_builder_falls_back_to_write_when_new_fails():
    """D0096-AC-29: pipe-builder.md の「## 作るとき」に、pipe-in-gen new が失敗したら、ひな形を使わずに確認の取れた表どおりに Write で
    pipe.toml・prompts/・README.md を手で書き、pipe-in-gen check が通るまで直すこと、同じ名前があって止まったとき・フックに止められたときは
    差し戻すことが書かれている。手で書く箇条は「1. pipe-in-gen new …」の下の字下げの箇条で、「2. 」より前にある（new が失敗したその場で読まれる）。
    「## 返すもの」に、手で書いたことと new の失敗の理由を返すことが書かれている。"""
    make = builder_section("## 作るとき")
    assert make.strip(), "「## 作るとき」の節が無い"
    assert [w for w in FALLBACK_WORDS if w not in make] == []
    lines = make.splitlines()
    first = [i for i, ln in enumerate(lines) if ln.startswith("1. ") and "pipe-in-gen new" in ln]
    second = [i for i, ln in enumerate(lines) if ln.startswith("2. ")]
    assert first and second and first[0] < second[0], "「1. pipe-in-gen new …」と「2. 」の行が読めない"
    between = lines[first[0] + 1 : second[0]]
    fallback = [ln for ln in between if re.match(r"^\s+- ", ln) and "ひな形を使わず" in ln and "Write" in ln]
    assert fallback, f"「1.」と「2.」の間に、ひな形を使わず Write で書く字下げの箇条が無い: {between}"
    assert "フック" in "\n".join(between), "「1.」と「2.」の間に、フックに止められたときの決まりが無い"
    returns = builder_section("## 返すもの")
    assert returns.strip(), "「## 返すもの」の節が無い"
    told = [ln for ln in returns.splitlines() if "手で書いた" in ln]
    assert told, "「## 返すもの」に、手で書いたことを返す行が無い"
    assert [ln for ln in told if "理由" in ln], f"手で書いたことを返す行に、new の失敗の理由が無い: {told}"


def test_D0096_AC_29_builder_fallback_does_not_widen_scope():
    """D0096-AC-29: 手で書く道を足しても、「## 作るとき」は --force での流し直しも Bash で書く形（mkdir・cat・tee・echo・python -c）も勧めない。
    「## 触ってよい範囲」の書けるファイル（pipe.toml・README.md・prompts/*.md だけ）・Bash のコマンド（pipe-in-gen list / new / check だけ）・
    --force を付けない決まり・フックに止められたらすり抜けずに差し戻す決まりは今のまま残る。今の作りのままで通る（守り続ける）。"""
    make = builder_section("## 作るとき")
    assert make.strip(), "「## 作るとき」の節が無い"
    assert [w for w in NO_BASH_WRITE_WORDS if w in make] == []
    scope = builder_section("## 触ってよい範囲")
    assert scope.strip(), "「## 触ってよい範囲」の節が無い"
    assert [w for w in SCOPE_WORDS if w not in scope] == []


# ---- AC-30〜32：審査だけで差し戻す形を、任せる前・書く前に止める ----

SKILL_GATE_WORDS = ["確認済み", "judge", "on_fail", "command", "任せない", "聞", "組む", "指摘だけ", "stage-rules.md"]
BUILDER_GATE_WORDS = ["judge", "on_fail", "command", "確認済み", "Write", "差し戻", "権限の拡大は差し戻す"]
FALLBACK_GATE_WORDS = ["judge", "on_fail", "command", "手で書く前"]
JUDGE_ONLY_SHAPE = "`judge` のある `check` に `on_fail` があるのに `command` が無い"


def test_D0096_AC_30_skill_checks_judge_only_shape_before_delegating():
    """D0096-AC-30: pipe-build の SKILL.md の「## 3.」で、pipe-builder を呼ぶ行（「確認が取れたら」で始まる行）より前に、表を見ること（依頼に「確認済み」とあっても）・
    check に judge と on_fail があり command が無い段があれば任せないこと・stage-rules.md の決まり・command と組む案と on_fail をやめて指摘だけにする案を見せて
    聞くことが書かれている。「確認が取れたら」の行は残る（照らす所は、確認済みの表も通る「## 3.」の 1 か所）。"""
    three = section(read_front(BUILD_SKILL.read_text(encoding="utf-8"))[1], "## 3.")
    assert three.strip(), "「## 3.」の節が無い"
    lines = three.splitlines()
    call = [i for i, ln in enumerate(lines) if ln.startswith("確認が取れたら")]
    assert call, "「## 3.」に「確認が取れたら」で始まる行が無い"
    before = "\n".join(lines[: call[0]])
    missing = [w for w in SKILL_GATE_WORDS if w not in before]
    assert missing == [], f"「確認が取れたら」の行より前に無い語: {missing}"


def test_D0096_AC_31_builder_checks_judge_only_shape_before_writing():
    """D0096-AC-31: pipe-builder.md の「## 作るとき」で、「1. pipe-in-gen new …」の行より前に、書く前に表を「権限の拡大は差し戻す」に照らし、
    judge のある check に on_fail があり command が無い段があれば（「確認済み」とあっても）new も Write も使わずに差し戻すことが書かれている。
    「1.」と「2.」の間の手で書く箇条（ひな形を使わず Write で書く字下げの箇条）にも、その形（judge・on_fail・command）なら手で書く前に差し戻すことが書かれている。
    「## 権限の拡大は差し戻す」の 2 段落目（その形を名指しして差し戻す決まり）は残る。"""
    make = builder_section("## 作るとき")
    assert make.strip(), "「## 作るとき」の節が無い"
    lines = make.splitlines()
    first = [i for i, ln in enumerate(lines) if ln.startswith("1. ") and "pipe-in-gen new" in ln]
    second = [i for i, ln in enumerate(lines) if ln.startswith("2. ")]
    assert first and second and first[0] < second[0], "「1. pipe-in-gen new …」と「2. 」の行が読めない"
    before = "\n".join(lines[: first[0]])
    between = lines[first[0] + 1 : second[0]]
    fallback = [ln for ln in between if re.match(r"^\s+- ", ln) and "ひな形を使わず" in ln and "Write" in ln]
    assert fallback, f"「1.」と「2.」の間に、ひな形を使わず Write で書く字下げの箇条が無い: {between}"
    missing = {
        "「1.」の前": [w for w in BUILDER_GATE_WORDS if w not in before],
        "手で書く箇条": [w for w in FALLBACK_GATE_WORDS if w not in "\n".join(fallback)],
    }
    assert missing == {"「1.」の前": [], "手で書く箇条": []}
    rule = builder_section("## 権限の拡大は差し戻す")
    assert JUDGE_ONLY_SHAPE in rule and "差し戻す" in rule, "「## 権限の拡大は差し戻す」の 2 段落目が無い"


def test_D0096_AC_32_gate_text_does_not_trip_eval_graders():
    """D0096-AC-32: 足した文を含む pipe-build の SKILL.md と pipe-builder.md の全文は、生のままでも、JSON の文字列にして trace に入れても
    （Write の content・Edit の new_string・返事の文・Skill の結果）、build-refuses-judge-only の 01-no-bad-shape にも build-passes-check の
    07-check-passed にも当たらず、evals の語を持たない。今の作りのままで通る（守る。足す文に TOML の例や check の成功の行を書くと落ちる）。"""
    bad = bad_shape()
    passed = compiled(grader("build-passes-check", "07-check-passed.md"))
    for path in (BUILD_SKILL, BUILDER):
        text = path.read_text(encoding="utf-8")
        assert "evals" not in text, path.name
        shapes = {**forms(text), "Skill の結果": trace(result_msg(text))}
        for form, sample in shapes.items():
            assert not bad.search(sample), (path.name, form, "01-no-bad-shape")
            assert not passed.search(sample), (path.name, form, "07-check-passed")
