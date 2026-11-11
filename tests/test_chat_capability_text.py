"""D0082-AC-04〜06：会話の道の「断る文」と「効かない設定の一覧」を、今の実装が出す文のまま固定する。

これは「赤を見る」テストではなく固定のテスト：置き換え前の chat.unsupported() / chat.ineffective() を流して
確かめた文を、文字どおり書き写してある（chat.py や capability.py から文を import しない）。
能力表への置き換えのあとも、1文字も変わらずに緑のままであることが合格の条件。
SDK は呼ばない。パイプも pipeline.toml も tmp_path の中に作る。
"""

from __future__ import annotations

import pytest
from chat_support import OK_CMD, Run, make_pipe, no_sdk, pipe_toml, stage_toml  # noqa: F401

from pipe_in.engine.config import load_config
from pipe_in.pipe import chat
from pipe_in.pipe import definition as pd

pytestmark = pytest.mark.usefixtures("no_sdk")


def build(tmp_path, toml, pipeline_toml=None):
    """tmp_path にパイプ（と pipeline.toml）を作り、読み込んだ (pipe, cfg) を返す。check_pipe は通さない（断る形を作るため）。"""
    d = make_pipe(tmp_path, toml, "hp", valid=False)
    if pipeline_toml is not None:
        (tmp_path / "pipeline.toml").write_text(pipeline_toml, encoding="utf-8")
    return pd.load_pipe(d), load_config(tmp_path)


JUDGE = f"[stages.check]\ncommand = '{OK_CMD}'\n[stages.check.judge]\nthreshold = 0.7\n[[stages.check.judge.criteria]]\nname = \"a\"\ndescription = \"b\"\n"

# (id, 段の extra, 追加の段, [pipe] に足す行, pipeline.toml の中身, after, 今の戻り)
SHAPES = [
    (
        "group",
        'group = "g"\n',
        stage_toml("other", extra='group = "g"\n'),
        "",
        None,
        None,
        ["段「s」のgroup（並列の段）は、会話の中では流せません", "段「other」のgroup（並列の段）は、会話の中では流せません"],
    ),
    ("routes", '[stages.routes]\nok = "end"\n', "", "", None, None, ["段「s」のroutes（分岐）は、会話の中では流せません（構造化出力が無いため）"]),
    ("check-judge", JUDGE, "", "", None, None, ["段「s」のcheck.judge（審査）は、会話の中では流せません（構造化出力が無いため）"]),
    (
        "agents",
        '[stages.agents.helper]\ndescription = "d"\nprompt = "p"\ntools = ["Read"]\n',
        "",
        "",
        None,
        None,
        ["段「s」のagents（段の中のサブエージェント）は、会話の中では流せません"],
    ),
    ("mcp", 'mcp = ["mcp__srv__tool"]\n', "", "", None, None, ["段「s」のmcp（MCP の道具）は、会話の中では流せません"]),
    (
        "mcp_servers",
        'mcp = ["mcp__srv__*"]\n[stages.mcp_servers.srv]\ntype = "stdio"\ncommand = "srv"\n',
        "",
        "",
        None,
        None,
        ["段「s」のmcp（MCP の道具）は、会話の中では流せません", "段「s」のmcp_servers（MCP サーバー）は、会話の中では流せません"],
    ),
    ("web-true", "web = true\n", "", "", None, None, ["段「s」のweb（Web の道具）は、会話の中では流せません"]),
    ("web-domains", 'web = ["docs.python.org"]\n', "", "", None, None, ["段「s」のweb（Web の道具）は、会話の中では流せません"]),
    ("max_budget_usd-pipe", "max_budget_usd = 1.0\n", "", "", None, None, ["段「s」のmax_budget_usd（費用の上限）は、会話の中では守れないので流せません"]),
    (
        "max_budget_usd-pipeline",
        "",
        "",
        "",
        "[stages.s]\nmax_budget_usd = 1.0\n",
        None,
        ["pipeline.toml の [stages.s] の max_budget_usd（費用の上限）は、会話の中では守れないので流せません"],
    ),
    ("after", "", "", "", None, "prev", ["--after（前の実行の受け取り）は、会話の中では使えません"]),
    ("dev", "", "", 'kind = "dev"\n', None, None, ['kind = "dev" のパイプ（組み込みの開発フロー dev）は、会話の中では流せません']),
]


@pytest.mark.parametrize("shape", SHAPES, ids=[s[0] for s in SHAPES])
def test_d0082_ac04_断る形ごとの文が今と同じ(tmp_path, shape):
    """D0082-AC-04: tests/test_chat_start.py の BAD_SHAPES の12通りの形で、unsupported() の戻りが、置き換え前の文と1文字も変わらない。"""
    _, extra, more, head, pipeline_toml, after, expected = shape
    pipe, cfg = build(tmp_path, pipe_toml(stage_toml("s", extra=extra), more), pipeline_toml)
    if head:  # kind = "dev"（pipe.toml の kind は linear 以外の値を load_pipe がそのまま入れるので、読み込んだあとに変えて同じ形にする）
        pipe.kind = "dev"
    assert chat.unsupported(pipe, cfg, after) == expected


def test_d0082_ac04_kindの文は値が変わっても同じ言い回し(tmp_path):
    """D0082-AC-04: kind の文は「dev」と言い切る固定の言い回しで、値だけが入る（kind = "foo" でも「組み込みの開発フロー dev」のまま）。"""
    pipe, cfg = build(tmp_path, pipe_toml(stage_toml("s")))
    pipe.kind = "foo"
    assert chat.unsupported(pipe, cfg) == ['kind = "foo" のパイプ（組み込みの開発フロー dev）は、会話の中では流せません']


def test_d0082_ac04_扱える形のパイプは断らない(tmp_path):
    """D0082-AC-04: 扱える形（断る項目が1つも無い）では、戻りが空。"""
    pipe, cfg = build(tmp_path, pipe_toml(stage_toml("s"), stage_toml("t", access="docs", docs_dir="docs/out")))
    assert chat.unsupported(pipe, cfg) == []


def test_d0082_ac04_空のwebと0の費用上限は断らない(tmp_path):
    """D0082-AC-04: web = [] と、pipeline.toml の max_budget_usd = 0（未設定になる）は、断らない（今の動きを固定する）。"""
    pipe, cfg = build(tmp_path, pipe_toml(stage_toml("s", extra="web = []\n")), "[stages.s]\nmax_budget_usd = 0\n")
    assert pipe.stages[0].fetch_domains == [] and cfg.stages["s"].max_budget_usd is None
    assert chat.unsupported(pipe, cfg) == []


def test_d0082_ac04_子の項目だけでは断らない(tmp_path):
    """D0082-AC-04: max_agent_calls は agents を断る文の一部で、単独の項目としては文を出さない（agents が無ければ戻りは空）。"""
    pipe, cfg = build(tmp_path, pipe_toml(stage_toml("s", extra="max_agent_calls = 5\n")))
    assert pipe.stages[0].max_agent_calls == 5
    assert chat.unsupported(pipe, cfg) == []


# ---- AC-05：順番 ----------------------------------------------------------------------------------


def test_d0082_ac05_断る形が複数のとき文の順番が今と同じ(tmp_path):
    """D0082-AC-05: kind → --after → 段ごと（パイプの段の順に、group・routes・check.judge・agents・mcp・mcp_servers・web・max_budget_usd）
    → pipeline.toml の [stages.<段>]（書いた順）。段ごとの外側のループが段、内側が項目の並び。"""
    everything = (
        'group = "g"\n'
        'mcp = ["mcp__srv__*"]\n'
        "web = true\n"
        "max_budget_usd = 2.0\n"
        '[stages.routes]\nok = "end"\n'
        '[stages.agents.helper]\ndescription = "d"\nprompt = "p"\ntools = ["Read"]\n'
        '[stages.mcp_servers.srv]\ntype = "stdio"\ncommand = "srv"\n'
        f"[stages.check]\ncommand = '{OK_CMD}'\n[stages.check.judge]\nthreshold = 0.7\n"
        '[[stages.check.judge.criteria]]\nname = "a"\ndescription = "b"\n'
    )
    toml = pipe_toml(
        stage_toml("first", extra=everything),
        stage_toml("second", extra="max_budget_usd = 3.0\nweb = true\n"),
    )
    pipeline = "[stages.second]\nmax_budget_usd = 1.0\n[stages.first]\nmax_budget_usd = 4.0\n"
    pipe, cfg = build(tmp_path, toml, pipeline)
    pipe.kind = "dev"
    assert chat.unsupported(pipe, cfg, "prev") == [
        'kind = "dev" のパイプ（組み込みの開発フロー dev）は、会話の中では流せません',
        "--after（前の実行の受け取り）は、会話の中では使えません",
        "段「first」のgroup（並列の段）は、会話の中では流せません",
        "段「first」のroutes（分岐）は、会話の中では流せません（構造化出力が無いため）",
        "段「first」のcheck.judge（審査）は、会話の中では流せません（構造化出力が無いため）",
        "段「first」のagents（段の中のサブエージェント）は、会話の中では流せません",
        "段「first」のmcp（MCP の道具）は、会話の中では流せません",
        "段「first」のmcp_servers（MCP サーバー）は、会話の中では流せません",
        "段「first」のweb（Web の道具）は、会話の中では流せません",
        "段「first」のmax_budget_usd（費用の上限）は、会話の中では守れないので流せません",
        "段「second」のweb（Web の道具）は、会話の中では流せません",
        "段「second」のmax_budget_usd（費用の上限）は、会話の中では守れないので流せません",
        "pipeline.toml の [stages.second] の max_budget_usd（費用の上限）は、会話の中では守れないので流せません",
        "pipeline.toml の [stages.first] の max_budget_usd（費用の上限）は、会話の中では守れないので流せません",
    ]


def test_d0082_ac05_パイプに無い段名のpipeline_tomlでも断る(tmp_path):
    """D0082-AC-05: pipeline.toml の [stages.<段>] の max_budget_usd は、パイプに無い段の名前でも断る（FR-07 の食い違いを今のまま固定する）。"""
    pipe, cfg = build(tmp_path, pipe_toml(stage_toml("s")), "[stages.ghost]\nmax_budget_usd = 1.0\n")
    assert [s.name for s in pipe.stages] == ["s"]
    assert chat.unsupported(pipe, cfg) == ["pipeline.toml の [stages.ghost] の max_budget_usd（費用の上限）は、会話の中では守れないので流せません"]


# ---- AC-06：効かない設定 ---------------------------------------------------------------------------

ALL_KEYS = (
    'model = "sonnet"\nmax_turns = 5\nmax_thinking_tokens = 2000\nfallback_model = "haiku"\npermission_mode = "acceptEdits"\nadd_dirs = ["docs"]\n'
)


def _items(stage, *keys, where="pipe.toml"):
    return [{"stage": stage, "key": k, "where": where} for k in keys]


def test_d0082_ac06_ineffectiveの内容と順番が今と同じ(tmp_path):
    """D0082-AC-06: 段ごとに、pipe.toml の model・max_turns・max_thinking_tokens・fallback_model・permission_mode、続けて add_dirs、
    続けて pipeline.toml の model・max_turns。パイプに無い段名の [stages.<段>] は出さない。"""
    toml = pipe_toml(stage_toml("a", extra=ALL_KEYS), stage_toml("b", extra='model = "opus"\n'), stage_toml("c"))
    pipeline = '[stages.ghost]\nmodel = "sonnet"\nmax_turns = 1\n[stages.b]\nmax_turns = 9\nmodel = "haiku"\n[stages.a]\nmodel = "x"\nmax_turns = 2\n'
    pipe, cfg = build(tmp_path, toml, pipeline)
    assert chat.ineffective(pipe, cfg) == (
        _items("a", "model", "max_turns", "max_thinking_tokens", "fallback_model", "permission_mode", "add_dirs")
        + _items("a", "model", "max_turns", where="pipeline.toml")
        + _items("b", "model")
        + _items("b", "model", "max_turns", where="pipeline.toml")
    )


def test_d0082_ac06_add_dirsが空なら出さない(tmp_path):
    """D0082-AC-06: add_dirs = [] は出さない（is not None でなく、空かどうかで見る）。"""
    pipe, cfg = build(tmp_path, pipe_toml(stage_toml("s", extra="add_dirs = []\n")))
    assert chat.ineffective(pipe, cfg) == []


def test_d0082_ac06_パイプに無い段名は出ない(tmp_path):
    """D0082-AC-06: pipeline.toml の [stages.<段>] の model・max_turns は、パイプにある段だけが出る（断る側と違い、ghost は出ない）。"""
    pipe, cfg = build(tmp_path, pipe_toml(stage_toml("s")), '[stages.ghost]\nmodel = "sonnet"\nmax_turns = 3\n')
    assert chat.ineffective(pipe, cfg) == []


def test_d0082_ac06_pipeline_tomlのmax_turnsだけでも出る(tmp_path):
    """D0082-AC-06: pipeline.toml の model が無く max_turns だけでも、その1つだけが出る。"""
    pipe, cfg = build(tmp_path, pipe_toml(stage_toml("s")), "[stages.s]\nmax_turns = 3\n")
    assert chat.ineffective(pipe, cfg) == _items("s", "max_turns", where="pipeline.toml")


def test_d0082_ac06_startの効かない設定の文が同じ(tmp_path):
    """D0082-AC-06: start の「効かない設定」の文（dry-run の message と、記録の warnings）が、今と1文字も変わらない。"""
    r = Run(tmp_path)
    r.make(pipe_toml(stage_toml("s", extra='model = "sonnet"\nadd_dirs = ["docs"]\n'), stage_toml("t")))
    (tmp_path / "pipeline.toml").write_text("[stages.t]\nmax_turns = 3\n", encoding="utf-8")
    listing = "効かない設定（会話の中では効きません）: s の model（pipe.toml）、s の add_dirs（pipe.toml）、t の max_turns（pipeline.toml）"
    out = r.start("--dry-run")
    assert r.code == 0 and out["ok"] is True, out
    assert out["message"] == f"パイプ「hp」（2 段）を会話の中で流せます。{listing}。何も書いていません。続けるなら chat start（--dry-run なし）で始めてください"
    assert out["ineffective"] == _items("s", "model", "add_dirs") + _items("t", "max_turns", where="pipeline.toml")
    out = r.start()
    assert r.code == 0 and out["ok"] is True, out
    assert out["message"] == f"パイプ「hp」（2 段）の記録を作りました。{listing}。次は chat probe で、守りが効いているかを確かめてください"
    assert r.state()["warnings"] == [
        "効かない設定: s の model（pipe.toml）",
        "効かない設定: s の add_dirs（pipe.toml）",
        "効かない設定: t の max_turns（pipeline.toml）",
    ]


def test_d0082_ac06_効かない設定が無いときはなしと出る(tmp_path):
    """D0082-AC-06: 効かない設定が1つも無いときは「なし」。"""
    r = Run(tmp_path)
    r.make(pipe_toml(stage_toml("s")))
    out = r.start("--dry-run")
    assert out["message"].endswith("効かない設定（会話の中では効きません）: なし。何も書いていません。続けるなら chat start（--dry-run なし）で始めてください")
    assert out["ineffective"] == []
