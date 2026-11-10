"""D0078-AC-34〜38：作業台の「流す」が pipe-in に渡す引数の形を、本体（pipe_in.cli）の側から確かめる。

拡張の vscode/src/domain/runCommand.test.ts と同じ表（tests/fixtures/run_command.json の rows）を読む。
表の args は拡張（buildRunCommand）が作る配列。ここでは、その配列を本体の _parse_args と main に渡して、
依頼メモが旗やシェルの文字として読まれず、1つの値として届くことを確かめる。本体は変えないので、これらは今のまま通る（守る検査）。
SDK は呼ばない（runner を差し替える）。ファイルは tmp_path の中だけに作る。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipe_in import cli
from pipe_in.pipe import definition as pd
from test_pipe_flow import ScriptedRunner, pipe_toml, stage_toml

TABLE = json.loads((Path(__file__).parent / "fixtures" / "run_command.json").read_text(encoding="utf-8"))
ROWS = TABLE["rows"]
ROW_IDS = [r["id"] for r in ROWS]

# 既定の値（--pipe だけを渡したときの _parse_args の結果）。表の行で pipe・project・text 以外が動いていないかを比べる
DEFAULTS = vars(cli._parse_args(["--pipe=/x"]))
EXPECTED_KEYS = {"pipe", "project", "text"}


def parse(row: dict):
    return cli._parse_args(row["args"])


def has_text(row: dict) -> bool:
    return len(row["args"]) == 3


def test_ac34_table_has_the_rows_the_design_names():
    """D0078-AC-34: 表に optional の空・空白だけ・none の行と、旗・シェルの文字・省略形・パスの行がある（表が痩せていない）。"""
    for needed in (
        "optional-empty", "optional-spaces-only", "none-with-text", "none-empty",
        "text-yes", "text-help", "text-after", "text-text-flag", "text-pipe-evil", "text-review-approve",
        "text-dashdash", "text-leading-dash", "text-equals", "text-semicolon", "text-subst", "text-backtick",
        "text-quotes", "text-newline", "text-japanese", "text-long",
        "text-abbrev-pipe", "text-abbrev-project", "text-abbrev-text",
        "path-space", "path-equals", "path-japanese", "path-windows",
    ):
        assert needed in ROW_IDS, needed
    assert len(set(ROW_IDS)) == len(ROW_IDS), "id が重なっている"
    assert any(r["input"] == "optional" and not has_text(r) for r in ROWS)
    assert any(r["input"] == "none" for r in ROWS)
    assert next(r for r in ROWS if r["id"] == "text-long")["text"].__len__() > 250


@pytest.mark.parametrize("row", ROWS, ids=ROW_IDS)
def test_ac34_every_row_args_are_accepted_by_parse_args(row):
    """D0078-AC-34: 表のどの行の args も、本体の _parse_args がそのまま受け取れる（SystemExit にならない）。"""
    ns = parse(row)
    assert ns.pipe == row["args"][0].removeprefix("--pipe=")


@pytest.mark.parametrize("row", ROWS, ids=ROW_IDS)
def test_ac35_pipe_project_text_arrive_as_expected_and_nothing_else_moves(row):
    """D0078-AC-35: どの行でも pipe・project・text が期待どおりで、ほかの旗（--yes・--review・--after・-h など）は既定のまま。"""
    ns = parse(row)
    assert ns.pipe == row["pipe_dir"]
    assert ns.project == Path(row["project"])
    if has_text(row):
        assert ns.text == row["text"]
    else:
        assert ns.text is None
    others = {k: v for k, v in vars(ns).items() if k not in EXPECTED_KEYS}
    expected = {k: v for k, v in DEFAULTS.items() if k not in EXPECTED_KEYS}
    assert others == expected


@pytest.mark.parametrize("row", ROWS, ids=ROW_IDS)
def test_ac36_flags_are_full_names_so_abbreviations_in_the_text_stay_text(row):
    """D0078-AC-36: args の旗は完全な名前（--pipe=・--project=・--text=）。依頼メモが --pi・--proj・--te の省略形に見える行でも、pipe・project・text は変わらない。"""
    args = row["args"]
    assert args[0].startswith("--pipe=")
    assert args[1].startswith("--project=")
    assert len(args) in (2, 3)
    if len(args) == 3:
        assert args[2].startswith("--text=")
    ns = parse(row)
    assert ns.pipe == row["pipe_dir"]
    assert ns.project == Path(row["project"])


def test_ac36_the_abbreviation_rows_really_look_like_abbreviations():
    """D0078-AC-36: 省略形の行の依頼メモは、本当に --pi・--proj・--te で始まる（argparse の省略形の受け入れに対する確かめになっている）。"""
    by_id = {r["id"]: r for r in ROWS}
    assert by_id["text-abbrev-pipe"]["text"].startswith("--pi=")
    assert by_id["text-abbrev-project"]["text"].startswith("--proj")
    assert by_id["text-abbrev-text"]["text"].startswith("--te=")


def test_ac36_a_bare_abbreviation_would_have_been_read_as_a_flag():
    """D0078-AC-36: 対の確かめ：依頼メモを --text= に包まず、別の要素として渡すと、本体は省略形を旗として読んでしまう。だから包んで 1 つの要素にする。"""
    ns = cli._parse_args(["--pipe=/work/app/.pipe-in/pipes/pipe-in-p", "--project=/work/app", "--pi=evil"])
    assert ns.pipe == "evil"


# ---- AC-37：main に渡して、依頼メモがそのままパイプラインに届く ------------------------------


def make_real_pipe(tmp_path: Path, input_mode: str) -> Path:
    d = tmp_path / ".pipe-in" / "pipes" / "pipe-in-p"
    d.mkdir(parents=True)
    (d / "pipe.toml").write_text(pipe_toml(stage_toml("a"), head=f'input = "{input_mode}"\n'), encoding="utf-8")
    return d


def run_main(tmp_path: Path, monkeypatch, input_mode: str, args: list[str]):
    """表の args の 0・1 番目だけを実在のパスに差し替えて cli.main を呼ぶ。run に渡った依頼メモを集めて返す。"""
    d = make_real_pipe(tmp_path, input_mode)
    pipe = pd.load_pipe(d)
    seen: list[str | None] = []
    real = cli.pipeline_for

    def fake(cfg, pipe_def, *, test_cmd_given=False):
        p = real(cfg, pipe_def, test_cmd_given=test_cmd_given)
        p.runner = ScriptedRunner(pipe)
        original = p.run

        async def recording(input_text, from_stage=None):
            seen.append(input_text)
            return await original(input_text, from_stage)

        p.run = recording
        return p

    monkeypatch.setattr(cli, "pipeline_for", fake)
    argv = [f"--pipe={d}", f"--project={tmp_path}", *args[2:]]
    return argv, seen


TEXT_ROWS = [r for r in ROWS if has_text(r) and r["input"] in ("required", "optional")]


@pytest.mark.parametrize("row", TEXT_ROWS, ids=[r["id"] for r in TEXT_ROWS])
def test_ac37_text_rows_reach_the_pipeline_unchanged(tmp_path, monkeypatch, row):
    """D0078-AC-37: --text= の行は、cli.main に渡すと、パイプラインに依頼メモがそのまま（strip される前の文字で）渡り、終了コード 0 で終わる。"""
    argv, seen = run_main(tmp_path, monkeypatch, row["input"], row["args"])
    assert cli.main(argv) == 0
    assert seen == [row["text"]]


NO_TEXT_ROWS = [r for r in ROWS if not has_text(r)]


@pytest.mark.parametrize("row", NO_TEXT_ROWS, ids=[r["id"] for r in NO_TEXT_ROWS])
def test_ac37_rows_without_text_run_with_none(tmp_path, monkeypatch, row):
    """D0078-AC-37: --text の無い行（optional の空・空白だけ、none）は、依頼メモ None で流れて終了コード 0 で終わる。"""
    argv, seen = run_main(tmp_path, monkeypatch, row["input"], row["args"])
    assert cli.main(argv) == 0
    assert seen == [None]


def test_ac37_required_without_text_is_refused_by_the_core(tmp_path, monkeypatch):
    """D0078-AC-37: required のパイプに --text を渡さないと、本体が断る（SystemExit。依頼メモが要る旨）。拡張が空を止めるのは二重の守り。"""
    row = next(r for r in ROWS if r["id"] == "optional-empty")
    argv, _ = run_main(tmp_path, monkeypatch, "required", row["args"])
    with pytest.raises(SystemExit) as e:
        cli.main(argv)
    assert "依頼メモ" in str(e.value)


# ---- AC-38：前の版の置き場所のパイプ -----------------------------------------------------------


def test_ac38_legacy_folder_absolute_path_is_found_and_loaded(tmp_path):
    """D0078-AC-38: devpipe-<名前> のフォルダの絶対パスを --pipe= に渡すと、find_pipe が見つけて、load_pipe が読める。"""
    d = tmp_path / ".devpipe" / "pipes" / "devpipe-x"
    d.mkdir(parents=True)
    (d / "pipe.toml").write_text(pipe_toml(stage_toml("a")), encoding="utf-8")
    ns = cli._parse_args([f"--pipe={d}", f"--project={tmp_path}", "--text=メモ"])
    found = pd.find_pipe(ns.pipe, project=ns.project)
    assert found == d
    pipe = pd.load_pipe(found)
    assert [s.name for s in pipe.stages] == ["a"]
