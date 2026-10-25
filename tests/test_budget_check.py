"""D0051：段の費用の上限（max_budget_usd）の値の検査。FR-21・FR-22・FR-24。

0 より大きい有限な数でない上限は、SDK を呼ぶ前に止める。
- pipeline.toml 側（[stages.<段>] max_budget_usd）：load_config が SystemExit で止まる。load_config を呼ぶ入口（cli.main・pipe-in record・
  pipe-in skill record・pipe-in live の snapshot/watch/answer・pipe-in-gen design）は、コードを触らずに同じ文で止まる。
- pipe.toml 側（[[stages]] max_budget_usd）：check_pipe が段の誤りとして返す（load_pipe は止めない）。

合否の基準（要件定義の「上限の値の検査」）：
- 基準 A：文に pipeline.toml・[stages.<書いてあった段の名前>]・max_budget_usd・「0 より大きい数」・max_budget_usd = 1.0・「今の値: 」と repr の値が入る。
- 基準 B：check_pipe の一覧に、頭「段 <番号>（<段の名前>）: 」・pipe.toml・max_budget_usd・「0 より大きい数」・max_budget_usd = 1.0・「今の値: 」と repr の値が入った文が 1 つ入る。

SDK は呼ばない（runner は偽物）。ファイルは tmp_path の中にだけ作る。pipe-in のコマンドは、いつも --project（か cwd）を tmp_path に向ける
（リポジトリの pipeline.toml と docs/pipeline/ には触れない）。今の作りのままで通るテストは、名前の末尾を _守る にし、説明の末尾に「（今のまま通る。守る）」と書く。
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from pipe_in import cli
from pipe_in.dev import record
from pipe_in.dev import specs as st
from pipe_in.dev.pipeline import DevPipeline
from pipe_in.engine import live_cmd
from pipe_in.engine.config import load_config
from pipe_in.engine.runner import StageRun, sdk_options
from pipe_in.pipe import definition as pd

ROOT = Path(__file__).resolve().parents[1]
STATE_REL = Path("docs") / "pipeline" / "state.json"
# 前の版のパイプのフォルダ名の頭。前の名前は、この文書に直接書かない（tests/test_rename.py の一覧に無いファイルなので）。文字をつないで作る
OLD_PREFIX = "dev" + "pipe-"


# ---- 補助：値の書き方 ----------------------------------------------------------------------------


def toml_literal(value) -> str:
    """Python の値を TOML の値の書き方にする（真偽・文字・nan・inf・巨大な整数も）。"""
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, float) and value != value:
        return "nan"
    if isinstance(value, float) and value in (float("inf"), float("-inf")):
        return "inf" if value > 0 else "-inf"
    return repr(value)


def write_budget(project: Path, value, stage: str = "requirements") -> None:
    (project / "pipeline.toml").write_text(f"[stages.{stage}]\nmax_budget_usd = {toml_literal(value)}\n", encoding="utf-8")


def make_project(tmp_path: Path, name: str) -> Path:
    project = tmp_path / name
    project.mkdir()
    return project


NEGATIVE = [pytest.param(-1, id="minus1"), pytest.param(-0.5, id="minus0.5")]
STRINGS = [pytest.param("1.0", id="str-1.0"), pytest.param("", id="str-empty")]
BOOLS = [pytest.param(True, id="true"), pytest.param(False, id="false")]
NON_FINITE = [pytest.param(float("inf"), id="inf"), pytest.param(float("-inf"), id="neginf"), pytest.param(10**400, id="huge-int")]
ZEROS = [pytest.param(0, id="int0"), pytest.param(0.0, id="float0")]


# ---- 補助：基準 A（pipeline.toml 側） ----------------------------------------------------------------


def assert_basis_a(message: str, stage: str, value) -> None:
    words = [
        "pipeline.toml",
        f"[stages.{stage}]",
        "max_budget_usd",
        "0 より大きい数",
        "max_budget_usd = 1.0",
        f"今の値: {value!r}",
    ]
    missing = [w for w in words if w not in message]
    assert missing == [], f"基準 A に無い語 {missing}。実際の文: {message!r}"


def stop_message(project: Path) -> str:
    """load_config が SystemExit で止まるときの文。止まらなければ、その理由で落ちる。"""
    with pytest.raises(SystemExit) as e:
        load_config(project, None, auto_approve=True)
    assert isinstance(e.value.code, str) and e.value.code, f"終了コードが文でない: {e.value.code!r}"
    return str(e.value)


class StubRunner:
    """要件定義の文書だけを書いて終わる偽の runner（SDK は呼ばない）。呼ばれた段を calls に残す。"""

    def __init__(self):
        self.calls: list[str] = []

    async def __call__(self, spec, prompt, cfg, *, resume, log_name):
        self.calls.append(spec.name)
        if spec.name == "requirements":
            (cfg.work_dir / st.REQUIREMENTS).write_text("# 要件定義書\nAC-01\n", encoding="utf-8")
        return StageRun(stage=spec.name, session_id="s-1")


# ---- 補助：pipe.toml 側・基準 B ------------------------------------------------------------------------


def stage_block(name: str, extra: str = "", output: str | None = None) -> str:
    out = f"{name}.md" if output is None else output
    return f'\n[[stages]]\nname = "{name}"\nlabel = "{name}の段"\noutput = "{out}"\naccess = "read"\nprompt = "{name}をする"\n{extra}'


def budget_line(value) -> str:
    return f"max_budget_usd = {toml_literal(value)}\n"


def write_pipe(project: Path, *blocks: str, prefix: str = "pipe-in-") -> Path:
    d = project / "pipes" / f"{prefix}p"
    d.mkdir(parents=True)
    (d / "pipe.toml").write_text('[pipe]\nkind = "linear"\nlabel = "試し"\n' + "".join(blocks), encoding="utf-8")
    return d


def pipe_errors(project: Path, value, *, output: str | None = None) -> list[str]:
    """段 2（draw）に value を書いたパイプを読み（load_pipe は止まらない）、check_pipe の一覧を返す。"""
    d = write_pipe(project, stage_block("survey"), stage_block("draw", budget_line(value), output=output))
    return pd.check_pipe(pd.load_pipe(d), project)


def assert_basis_b(errors: list[str], value, *, index: int = 2, exact_head: bool = True) -> None:
    found = [e for e in errors if "max_budget_usd" in e]
    assert len(found) == 1, f"max_budget_usd の誤りが {len(found)} 件（1 件のはず）。一覧: {errors}"
    sentence = found[0]
    head = f"段 {index}（draw）: "
    assert (sentence.startswith(head) if exact_head else head in sentence), f"頭が「{head}」でない: {sentence!r}"
    words = ["pipe.toml", "max_budget_usd", "0 より大きい数", "max_budget_usd = 1.0", f"今の値: {value!r}"]
    missing = [w for w in words if w not in sentence]
    assert missing == [], f"基準 B に無い語 {missing}。実際の文: {sentence!r}"


# ---- 補助：cli.main を、runner を差し替えて流す ---------------------------------------------------------


@pytest.fixture
def counting(monkeypatch):
    """pipe-in のコマンドが作る流れの runner を、呼ばれた段を数える偽物に差し替える（SDK を呼ばない）。"""
    runner = StubRunner()
    real = cli.pipeline_for

    def fake(cfg, pipe, *, test_cmd_given=False):
        p = real(cfg, pipe, test_cmd_given=test_cmd_given)
        p.runner = runner
        return p

    monkeypatch.setattr(cli, "pipeline_for", fake)
    return runner


# ==== pipeline.toml 側（FR-21）：load_config =====================================================================


@pytest.mark.parametrize("value", NEGATIVE)
def test_d0051_ac20_負の数の上限でload_configは基準Aのとおり止まる(tmp_path, value):
    """D0051-AC-20: [stages.requirements] の max_budget_usd が負の数（-1・-0.5）のとき、load_config は SystemExit で止まり、文に基準 A の語
    （pipeline.toml・[stages.requirements]・max_budget_usd・「0 より大きい数」・max_budget_usd = 1.0・「今の値: -1」など）が入る。"""
    write_budget(tmp_path, value)
    assert_basis_a(stop_message(tmp_path), "requirements", value)


def test_d0051_ac20_max_buffer_mbと上限が両方不正ならmax_buffer_mbの文が先_守る(tmp_path):
    """D0051-AC-20: [pipeline] max_buffer_mb = 0 と [stages.requirements] max_budget_usd = -1 を両方書くと、止まる文は max_buffer_mb のもの
    （今の検査の順 max_buffer_mb → [stages.*] を変えない）。（今のまま通る。守る）"""
    (tmp_path / "pipeline.toml").write_text("[pipeline]\nmax_buffer_mb = 0\n[stages.requirements]\nmax_budget_usd = -1\n", encoding="utf-8")
    message = stop_message(tmp_path)
    assert "max_buffer_mb" in message and "max_budget_usd" not in message, message


@pytest.mark.parametrize("value", STRINGS)
def test_d0051_ac89_文字の上限は止まる(tmp_path, value):
    """D0051-AC-89: max_budget_usd が文字（"1.0"・""）のとき、load_config は基準 A のとおり止まる。空の文字は偽だが、数ではないので、未設定にしない。"""
    write_budget(tmp_path, value)
    assert_basis_a(stop_message(tmp_path), "requirements", value)


@pytest.mark.parametrize("value", BOOLS)
def test_d0051_ac90_真偽の上限は止まる(tmp_path, value):
    """D0051-AC-90: max_budget_usd が真偽（true・false）のとき、load_config は基準 A のとおり止まる。false は偽だが 0 ではなく数でもないので、未設定にしない。"""
    write_budget(tmp_path, value)
    assert_basis_a(stop_message(tmp_path), "requirements", value)


def test_d0051_ac91_nanは止まる(tmp_path):
    """D0051-AC-91: max_budget_usd が nan のとき、load_config は基準 A のとおり止まる（文は「今の値: nan」）。"""
    write_budget(tmp_path, float("nan"))
    message = stop_message(tmp_path)
    assert_basis_a(message, "requirements", float("nan"))
    assert "今の値: nan" in message


@pytest.mark.parametrize("value", NON_FINITE)
def test_d0051_ac92_infと巨大な整数は止まる(tmp_path, value):
    """D0051-AC-92: max_budget_usd が inf・-inf、または float にできないほど大きい整数（10 の 400 乗）のとき、load_config は基準 A のとおり止まる。
    OverflowError などの例外で落ちない。"""
    write_budget(tmp_path, value)
    assert_basis_a(stop_message(tmp_path), "requirements", value)


@pytest.mark.parametrize("value", [1, 0.6, 0.001], ids=["int1", "0.6", "0.001"])
def test_d0051_ac93_正の有限な数は止まらず値が等しい(tmp_path, value):
    """D0051-AC-93: max_budget_usd が 0 より大きい有限な数（整数の 1・小数の 0.6・0.001）のときは止まらない。sdk_options が SDK に渡す値と
    記録される値は、その数に等しい。"""
    write_budget(tmp_path, value)
    cfg = load_config(tmp_path, None, auto_approve=True)
    spec = st.build_specs(cfg)["requirements"]
    assert sdk_options(spec, cfg, resume=None)["max_budget_usd"] == value
    cfg.work_dir.mkdir(parents=True)
    p = DevPipeline(cfg, runner=StubRunner())
    asyncio.run(p._run("requirements", "指示"))
    assert p.history[-1].get("max_budget_usd") == value, f"記録の上限が {p.history[-1].get('max_budget_usd')!r}"


OLD_TOML = """[pipeline]
work_dir = "docs/pipeline"
max_retries = 2

[stages.requirements]
model = "sonnet"
max_turns = 20

[stages.design]
max_turns = 25
"""


def test_d0051_ac93_max_budget_usdの無い前の版のpipeline_tomlも今までどおり読める_守る(tmp_path):
    """D0051-AC-93: max_budget_usd を持たない前の版の pipeline.toml（[stages.*] に model・max_turns だけ）を読むと、止まらず、段の設定は書いたとおりに効き、
    上限は無い（sdk_options の値は None）。（今のまま通る。守る）"""
    (tmp_path / "pipeline.toml").write_text(OLD_TOML, encoding="utf-8")
    cfg = load_config(tmp_path, None, auto_approve=True)
    sc = cfg.stage("requirements")
    assert (sc.model, sc.max_turns, sc.max_budget_usd) == ("sonnet", 20, None)
    assert cfg.stage("design").max_turns == 25
    assert sdk_options(st.build_specs(cfg)["requirements"], cfg, resume=None)["max_budget_usd"] is None


def test_d0051_ac93_examplesのpipeline_tomlも今までどおり読める_守る():
    """D0051-AC-93: examples/truncate/pipeline.toml（正の上限 0.6・1.0 を持つ前からの見本）が、止まらずに読め、値がそのまま効く。
    リポジトリのファイルを読むだけで、何も書かない。（今のまま通る。守る）"""
    cfg = load_config(ROOT / "examples" / "truncate", None, auto_approve=True)
    assert (cfg.stage("requirements").max_budget_usd, cfg.stage("implement").max_budget_usd) == (0.6, 1.0)


@pytest.mark.parametrize("kind", ["dev", "pipe"])
def test_d0051_ac94_cli_mainは負の数で止まりrunnerは呼ばれずstate_jsonも作らない(tmp_path, counting, kind):
    """D0051-AC-94: 負の数の pipeline.toml で、runner を差し替えて cli.main から流す（開発フロー、と、pipe.toml の上限が正しいパイプを --pipe で）と、
    SystemExit で基準 A のとおり止まり、runner は 1 回も呼ばれず、state.json は作られない。"""
    write_budget(tmp_path, -1)
    argv = ["--project", str(tmp_path), "--yes", "--text", "x"]
    if kind == "pipe":
        argv += ["--pipe", str(write_pipe(tmp_path, stage_block("requirements", budget_line(1.5)), stage_block("b")))]
    with pytest.raises(SystemExit) as e:
        cli.main(argv)
    assert_basis_a(str(e.value), "requirements", -1)
    assert counting.calls == []
    assert not (tmp_path / "docs").exists(), "記録のフォルダができている"


@pytest.mark.parametrize(
    ("stage", "extra"),
    [("requirements", ["--from", "design"]), ("nothing", ["--text", "x"])],
    ids=["requirements-from-design", "nothing"],
)
def test_d0051_ac95_流さない段と存在しない段名の不正も止まる(tmp_path, counting, stage, extra):
    """D0051-AC-95: 不正な値のある [stages.<名前>] は、流さない段でも止まる。開発フローを --from design で流すときの [stages.requirements] と、
    どの段にも無い名前の [stages.nothing] のどちらも、基準 A のとおり止まり、runner は呼ばれない。"""
    write_budget(tmp_path, -1, stage=stage)
    work = tmp_path / "docs" / "pipeline"
    work.mkdir(parents=True)
    (work / st.REQUIREMENTS).write_text("# 要件定義書\nAC-01\n", encoding="utf-8")  # --from design の前提の文書
    with pytest.raises(SystemExit) as e:
        cli.main(["--project", str(tmp_path), "--yes", *extra])
    assert_basis_a(str(e.value), stage, -1)
    assert counting.calls == []


# ==== pipe.toml 側（FR-22）：check_pipe ==========================================================================


@pytest.mark.parametrize("value", ZEROS)
def test_d0051_ac96_pipe_tomlの0はcheck_pipeが基準Bの文を返す(tmp_path, value):
    """D0051-AC-96: pipe.toml の段 2（draw）の max_budget_usd が 0・0.0 のとき、load_pipe は止まらず、check_pipe の一覧に基準 B の文が 1 つ入る
    （本物の CLI は 0 を断る。pipeline.toml の 0 は未設定で、これとは別）。"""
    assert_basis_b(pipe_errors(tmp_path, value), value)


def test_d0051_ac96_pipe_tomlの上限の誤りは同じ段のほかの誤りと一緒に一覧に出る(tmp_path):
    """D0051-AC-96: 上限が 0 の段に、ほかの誤り（output が空）もあるとき、check_pipe の一覧に両方が出る（上限の誤りが、ほかの誤りで隠れない）。"""
    errors = pipe_errors(tmp_path, 0, output="")
    assert_basis_b(errors, 0)
    assert any(e.startswith("段 2（draw）: ") and "output" in e for e in errors), errors


@pytest.mark.parametrize("value", NEGATIVE)
def test_d0051_ac97_pipe_tomlの負の数はcheck_pipeが基準Bの文を返す(tmp_path, value):
    """D0051-AC-97: pipe.toml の段の max_budget_usd が負の数（-1・-0.5）のとき、check_pipe は基準 B の文を返す。"""
    assert_basis_b(pipe_errors(tmp_path, value), value)


@pytest.mark.parametrize("value", STRINGS)
def test_d0051_ac98_pipe_tomlの文字はcheck_pipeが基準Bの文を返す(tmp_path, value):
    """D0051-AC-98: pipe.toml の段の max_budget_usd が文字（"1.0"・""）のとき、check_pipe は基準 B の文を返す（今までは黙って「上限なし」に読んでいた）。"""
    assert_basis_b(pipe_errors(tmp_path, value), value)


@pytest.mark.parametrize("value", BOOLS)
def test_d0051_ac99_pipe_tomlの真偽はcheck_pipeが基準Bの文を返す(tmp_path, value):
    """D0051-AC-99: pipe.toml の段の max_budget_usd が真偽（true・false）のとき、check_pipe は基準 B の文を返す（今までは黙って「上限なし」に読んでいた）。"""
    assert_basis_b(pipe_errors(tmp_path, value), value)


def test_d0051_ac100_pipe_tomlのnanはcheck_pipeが基準Bの文を返す(tmp_path):
    """D0051-AC-100: pipe.toml の段の max_budget_usd が nan のとき、check_pipe は基準 B の文を返す（文は「今の値: nan」）。"""
    errors = pipe_errors(tmp_path, float("nan"))
    assert_basis_b(errors, float("nan"))
    assert any("今の値: nan" in e for e in errors)


@pytest.mark.parametrize("value", NON_FINITE)
def test_d0051_ac101_pipe_tomlのinfと巨大な整数はcheck_pipeが基準Bの文を返す(tmp_path, value):
    """D0051-AC-101: pipe.toml の段の max_budget_usd が inf・-inf、または float にできないほど大きい整数（10 の 400 乗）のとき、
    load_pipe・check_pipe は OverflowError などの例外で落ちず、check_pipe は基準 B の文を返す。"""
    assert_basis_b(pipe_errors(tmp_path, value), value)


@pytest.mark.parametrize("value", [1.5, 2, 0.001, None, "legacy"], ids=["1.5", "int2", "0.001", "unset", "legacy-prefix"])
def test_d0051_ac102_正の数と書かない段は誤りを返さない_守る(tmp_path, value):
    """D0051-AC-102: 0 より大きい有限な数（1.5・整数の 2・0.001）の段と、max_budget_usd を書かない段は、check_pipe が誤りを返さない。
    前の版の頭のフォルダ（上限 1.5）も同じ。（今のまま通る。守る）"""
    legacy = value == "legacy"
    line = budget_line(1.5 if legacy else value) if value is not None else ""
    d = write_pipe(tmp_path, stage_block("survey"), stage_block("draw", line), prefix=OLD_PREFIX if legacy else "pipe-in-")
    assert pd.check_pipe(pd.load_pipe(d), tmp_path) == []


def test_d0051_ac102_examplesの動画のパイプは誤りを返さない_守る(tmp_path):
    """D0051-AC-102: examples/video/pipes/pipe-in-video（tests/test_video_example.py が使うパイプ。段ごとに 0.5〜3.0 の上限を持つ）は、変更なしで
    check_pipe が空のまま。リポジトリのファイルを読むだけ。（今のまま通る。守る）"""
    pipe = pd.load_pipe(ROOT / "examples" / "video" / "pipes" / "pipe-in-video")
    assert any(s.max_budget_usd is not None for s in pipe.stages)
    assert pd.check_pipe(pipe, tmp_path) == []


@pytest.mark.parametrize("layout", ["simple", "from_skip", "routes_skip"])
def test_d0051_ac103_pipe_tomlの不正でcli_mainはパイプに誤りがありますで止まる(tmp_path, counting, layout):
    """D0051-AC-103: 不正な値（0）のある pipe.toml のパイプを、runner を差し替えて cli.main から --pipe で流すと、SystemExit で止まり、文は
    「パイプ「p」に誤りがあります:」で始まって基準 B の文を含み、runner は 1 回も呼ばれず、state.json は作られない。不正な段が、--from で飛ばす段でも、
    分岐（routes）で通らない段でも、同じように止まる。"""
    bad = stage_block("draw", budget_line(0))
    extra: list[str] = []
    index = 2
    if layout == "simple":
        blocks = [stage_block("survey"), bad]
    elif layout == "from_skip":
        blocks, extra, index = [bad, stage_block("report")], ["--from", "report"], 1
    else:
        blocks = [stage_block("classify", '[stages.routes]\ngo = "last"\n'), bad, stage_block("last")]
    d = write_pipe(tmp_path, *blocks)
    if layout == "from_skip":  # --from report の前提の文書（draw の成果物）を置く。前提を満たしたうえで、不正な値で止まることを見る（AC-95 と同じ）
        (tmp_path / "docs" / "pipeline" / "p").mkdir(parents=True)
        (tmp_path / "docs" / "pipeline" / "p" / "draw.md").write_text("# draw\n", encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        cli.main(["--project", str(tmp_path), "--pipe", str(d), "--yes", "--text", "x", *extra])
    message = str(e.value)
    assert message.startswith("パイプ「p」に誤りがあります:"), message
    assert_basis_b(message.splitlines(), 0, index=index, exact_head=False)
    assert counting.calls == []
    assert list(tmp_path.rglob("state.json")) == [], "state.json ができている"
    if layout != "from_skip":
        assert not (tmp_path / "docs").exists(), "記録のフォルダができている"


@pytest.mark.parametrize("pipeline_value", [None, 0, 0.6], ids=["no-pipeline-toml", "pipeline-0", "pipeline-0.6"])
def test_d0051_ac104_pipe_tomlが不正ならpipeline_tomlが無い_0_0_6のどれでも止まる(tmp_path, counting, pipeline_value):
    """D0051-AC-104: pipe.toml の段 draw に不正な値（0）があるとき、pipeline.toml の [stages.draw] が無い・0・0.6 のどれでも、AC-103 のとおり止まる
    （pipeline.toml の 0.6 が実行時には勝つ場合でも、定義の誤りは直させる）。"""
    if pipeline_value is not None:
        write_budget(tmp_path, pipeline_value, stage="draw")
    d = write_pipe(tmp_path, stage_block("survey"), stage_block("draw", budget_line(0)))
    with pytest.raises(SystemExit) as e:
        cli.main(["--project", str(tmp_path), "--pipe", str(d), "--yes", "--text", "x"])
    message = str(e.value)
    assert message.startswith("パイプ「p」に誤りがあります:"), message
    assert_basis_b(message.splitlines(), 0, exact_head=False)
    assert counting.calls == []


def run_gen_check(capsys, project: Path) -> tuple[int, str]:
    from pipe_in_generator import cli as gen_cli

    capsys.readouterr()
    code = gen_cli.main(["check", "p", "--pipes-dir", str(project / "pipes"), "--project", str(project)])
    return code, capsys.readouterr().out


@pytest.mark.parametrize("value", [0, -1, "1.0", True], ids=["zero", "minus1", "str", "true"])
def test_d0051_ac105_pipe_in_gen_checkは不正で基準Bの文を出して終了コード1(tmp_path, capsys, value):
    """D0051-AC-105: pipe-in-gen check <パイプ> は、不正な値の pipe.toml で基準 B の文を出して終了コード 1（check_pipe を共有するので、generator/ のコードは変えない）。"""
    write_pipe(tmp_path, stage_block("survey"), stage_block("draw", budget_line(value)))
    code, out = run_gen_check(capsys, tmp_path)
    assert code == 1, out
    assert_basis_b([line.strip().removeprefix("- ") for line in out.splitlines()], value)


@pytest.mark.parametrize("value", [1.5, None], ids=["1.5", "unset"])
def test_d0051_ac105_pipe_in_gen_checkは正しい値と書かない場合は誤りを出さず終了コード0_守る(tmp_path, capsys, value):
    """D0051-AC-105: 正しい値（1.5）と、max_budget_usd を書かない場合は、max_budget_usd の誤りを出さず、ほかに誤りが無ければ終了コード 0。
    （今のまま通る。守る）"""
    write_pipe(tmp_path, stage_block("survey"), stage_block("draw", "" if value is None else budget_line(value)))
    code, out = run_gen_check(capsys, tmp_path)
    assert code == 0, out
    assert "max_budget_usd" not in out, out


# ==== load_config を呼ぶ、流す入口以外のコマンド（FR-24） ==========================================================


def test_d0051_ac109_record_startは不正で止まりstate_jsonを作らない(tmp_path):
    """D0051-AC-109: [stages.requirements] の max_budget_usd = -1 があるフォルダで pipe-in record start（pipe_in.dev.record.main）を流すと、
    基準 A のとおり SystemExit で止まり、state.json は作られない。"""
    write_budget(tmp_path, -1)
    with pytest.raises(SystemExit) as e:
        record.main(["start", "--project", str(tmp_path), "--text", "足したい機能"])
    assert_basis_a(str(e.value), "requirements", -1)
    assert not (tmp_path / STATE_REL).exists()


def test_d0051_ac109_configで渡した別のpipeline_tomlの値で止まる(tmp_path):
    """D0051-AC-109: --config で別の pipeline.toml（[stages.design] max_budget_usd = -0.5）を渡したときは、プロジェクトの pipeline.toml（正しい 1.0）ではなく、
    渡したほうの値で、基準 A のとおり止まり、state.json は作られない。"""
    project = make_project(tmp_path, "proj")
    write_budget(project, 1.0)
    other = tmp_path / "other.toml"
    other.write_text("[stages.design]\nmax_budget_usd = -0.5\n", encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        record.main(["start", "--project", str(project), "--config", str(other), "--text", "足したい機能"])
    assert_basis_a(str(e.value), "design", -0.5)
    assert not (project / STATE_REL).exists()


def test_d0051_ac109_skill_record_startも不正で止まりstate_jsonを作らない(tmp_path, monkeypatch):
    """D0051-AC-109: /pipe-in のスキルが打つ入口 pipe-in skill record start（cli.main(["skill", "record", "start", …])。cwd のフォルダだけを読む）も、
    負の数の pipeline.toml で基準 A のとおり SystemExit で止まり、state.json は作られない。"""
    write_budget(tmp_path, -1)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit) as e:
        cli.main(["skill", "record", "start", "--text", "足したい機能"])
    assert_basis_a(str(e.value), "requirements", -1)
    assert not (tmp_path / STATE_REL).exists()


@pytest.mark.parametrize("via", ["record", "skill"])
@pytest.mark.parametrize("value", [None, 1.0, 0], ids=["unset", "1.0", "0"])
def test_d0051_ac109_上限が無い_1_0_0では動く_守る(tmp_path, monkeypatch, via, value):
    """D0051-AC-109: max_budget_usd が無い・1.0・0 の pipeline.toml では、pipe-in record start も pipe-in skill record start も今までどおり動き（戻り値 0）、
    state.json が作られる。（今のまま通る。守る）"""
    if value is not None:
        write_budget(tmp_path, value)
    monkeypatch.chdir(tmp_path)
    if via == "record":
        code = record.main(["start", "--project", str(tmp_path), "--text", "足したい機能"])
    else:
        code = cli.main(["skill", "record", "start", "--text", "足したい機能"])
    assert code == 0
    assert (tmp_path / STATE_REL).is_file()


class Ticker:
    """watch の時計の偽物。呼ぶたびに 100 秒進むので、上限（--timeout 1）にすぐ届き、本物の時間を待たない。"""

    def __init__(self):
        self.now = 0.0

    def __call__(self) -> float:
        self.now += 100.0
        return self.now


def watch_deps() -> dict:
    return {"clock": Ticker(), "sleep": lambda seconds: None}


@pytest.mark.parametrize("command", ["snapshot", "watch", "answer"])
def test_d0051_ac110_live_snapshot_watch_answerは_work_dirなしで止まる(tmp_path, capsys, command):
    """D0051-AC-110: 負の数の pipeline.toml で、pipe-in live の snapshot・watch・answer（どれも --work-dir を渡さない）を流すと、どれも基準 A のとおり
    SystemExit で止まる。snapshot は写しを出さず、watch は見張りを始めず、answer は答えを読まない（--out・--feedback-out のファイルを作らず、何も出力しない）。"""
    write_budget(tmp_path, -1)
    out = tmp_path / "out.json"
    feedback = tmp_path / "feedback.txt"
    if command == "snapshot":
        argv, made = ["snapshot", "--project", str(tmp_path), "--out", str(out)], out
    elif command == "watch":
        argv, made = ["watch", "--project", str(tmp_path), "--out", str(out), "--timeout", "1"], out
    else:
        text = tmp_path / "answer.txt"
        text.write_text("x", encoding="utf-8")
        argv, made = ["answer", "--text-file", str(text), "--feedback-out", str(feedback), "--project", str(tmp_path)], feedback
    capsys.readouterr()
    with pytest.raises(SystemExit) as e:
        live_cmd.main(argv, watch_deps=watch_deps())
    assert_basis_a(str(e.value), "requirements", -1)
    assert not made.exists(), f"{made.name} が作られている"
    assert capsys.readouterr().out == ""


def test_d0051_ac110_work_dirを渡す形とpageは止まらない_守る(tmp_path, capsys, monkeypatch):
    """D0051-AC-110: 同じ負の数の pipeline.toml があっても、--work-dir を渡す pipe-in live（snapshot・watch・answer）と pipe-in live page は、load_config を呼ばないので、
    今までどおり止まらずに動く。（今のまま通る。守る）"""
    project = make_project(tmp_path, "proj")
    write_budget(project, -1)
    monkeypatch.chdir(project)  # page は --project を持たない。cwd に不正な pipeline.toml があっても影響しない
    work = tmp_path / "work"
    work.mkdir()
    (work / "state.json").write_text(json.dumps({"final": "PASSED", "stages": [], "runs": []}), encoding="utf-8")
    snap, watched, page = tmp_path / "snap.json", tmp_path / "watched.json", tmp_path / "page.html"
    assert live_cmd.main(["snapshot", "--project", str(project), "--work-dir", str(work), "--out", str(snap)]) == 0
    assert snap.is_file()
    code = live_cmd.main(
        ["watch", "--project", str(project), "--work-dir", str(work), "--out", str(watched), "--timeout", "1"], watch_deps=watch_deps()
    )
    assert code == 0 and watched.is_file()
    text = tmp_path / "answer.txt"
    text.write_text("x", encoding="utf-8")
    capsys.readouterr()
    assert live_cmd.main(["answer", "--text-file", str(text), "--project", str(project), "--work-dir", str(work)]) == 1  # 答えとして読めない文
    assert '"ok":false' in capsys.readouterr().out
    assert live_cmd.main(["page", "--out", str(page)]) == 0
    assert page.is_file()


def test_d0051_ac111_gen_designの_designはSDKを呼ぶ前に止まる(tmp_path):
    """D0051-AC-111: 負の数の pipeline.toml があるプロジェクトで、pipe-in-gen design の設計の流れ（generator/design.py の _design）を、runner を差し替えて呼ぶと、
    基準 A のとおり SystemExit で止まり、runner は 1 回も呼ばれない。"""
    from pipe_in_generator import design

    project = make_project(tmp_path, "shop")
    (project / "pyproject.toml").write_text('[project]\nname = "shop"\n', encoding="utf-8")
    write_budget(project, -1)
    runner = StubRunner()
    dest = tmp_path / "pipes" / "pipe-in-apidoc"
    with pytest.raises(SystemExit) as e:
        asyncio.run(design._design(project.resolve(), "apidoc", "API の文書を作りたい", dest, runner, 1, None))
    assert_basis_a(str(e.value), "requirements", -1)
    assert runner.calls == []
