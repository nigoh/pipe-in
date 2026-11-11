"""会話の道の能力表（D0082）。項目 × 実行役（sdk・chat）の動きを、データで持つ。

動きの種類：効く（works）・断る（refuse）・一覧に出す（list。効かないが断らず、見せる）・黙る（silent。
効かないが何も言わない）・関係しない（na）。「断る文」と「効かない設定の一覧」は、この表から作る。
項目を足したのに表へ足し忘れると、tests/test_capability.py が落ちる（check_table で全項目を突き合わせる）。

標準ライブラリだけ。pipe_in.pipe.definition・pipe_in.engine.config は import しない（項目は名前の文字列で読む）。
表の中の行の並びが、同じ scope の中の出力の順（今の chat.py の文と順番を変えない）。
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Any

WORKS, REFUSE, LIST, SILENT, NA = "works", "refuse", "list", "silent", "na"
ACTIONS = (WORKS, REFUSE, LIST, SILENT, NA)
ACTORS = ("sdk", "chat")  # 足すときは Row に同名の欄を足す

REFUSE_SCOPES = ("pipe", "after", "stage", "config_stage")
LIST_SCOPES = ("stage_list", "config_list")


@dataclass(frozen=True)
class Row:
    key: str  # "PipeStage.group"・"Config.model" の形。--after だけ "--after"
    sdk: str
    chat: str
    reason: str = ""  # 理由の文。断る・黙るときは必須
    caveat: str = ""  # 注記（既知の食い違い・書き方の癖）。動きは変えない
    # ---- 判断のしかた（断る・一覧に出す行だけ。子の項目は書かない）----
    scope: str = ""  # 断る: pipe | after | stage | config_stage、一覧: stage_list | config_list
    path: tuple[str, ...] = ()  # 値の読み方。複数は「どれか」。nested=True なら入れ子をたどる
    test: str = "truthy"  # truthy | not_none | ne:<値>
    sentence: str = ""  # 断る文のひな形。{stage}・{value} を format で埋める
    where: str = ""  # 一覧の where（pipe.toml | pipeline.toml）
    via: str = ""  # 子の項目の親の鍵。動きは親と同じで、文は親の行が出す
    nested: bool = False  # path を a.b.c のように入れ子でたどる（途中が None なら「無い」）


def _w(key: str, reason: str = "そのまま使う") -> Row:
    return Row(key, WORKS, WORKS, reason=reason)


def _child(key: str, parent: str) -> Row:
    return Row(key, WORKS, REFUSE, reason=f"親の {parent} を断るので、この項目も使えない", via=parent)


def _na(key: str, reason: str) -> Row:
    return Row(key, WORKS, NA, reason=reason)


TABLE: tuple[Row, ...] = (
    # ---- PipeDef ----
    _w("PipeDef.name"),
    _w("PipeDef.dir"),
    Row(
        "PipeDef.kind",
        WORKS,
        REFUSE,
        reason="linear 以外（組み込みの開発フロー dev）は本体の専用の流れで、会話の道では流せない",
        caveat='文は dev と言い切るが、値は変数で入る（kind = "foo" も同じ言い回し）',
        scope="pipe",
        path=("kind",),
        test="ne:linear",
        sentence='kind = "{value}" のパイプ（組み込みの開発フロー dev）は、会話の中では流せません',
    ),
    _w("PipeDef.label"),
    _w("PipeDef.description"),
    _w("PipeDef.input"),
    _na("PipeDef.test_command", "会話の道は検査の確認用コマンドを段の check.command で流し、パイプ全体の既定は使わない"),
    _w("PipeDef.stages"),
    _w("PipeDef.max_steps"),
    # ---- --after ----
    Row(
        "--after",
        WORKS,
        REFUSE,
        reason="前の実行の受け取りは本体の機能で、会話の道には無い",
        scope="after",
        sentence="--after（前の実行の受け取り）は、会話の中では使えません",
    ),
    # ---- PipeStage（断る行は、この並びが段ごとの文の順）----
    _w("PipeStage.name"),
    _w("PipeStage.label"),
    _w("PipeStage.output"),
    _w("PipeStage.access"),
    _w("PipeStage.prompt"),
    _w("PipeStage.prompt_file"),
    _w("PipeStage.docs_dir"),
    _w("PipeStage.bash"),
    _w("PipeStage.review"),
    Row(
        "PipeStage.model",
        WORKS,
        LIST,
        reason="会話の道の段は pipe-stage エージェントが流し、モデルは会話側で決まる",
        scope="stage_list",
        path=("model",),
        test="not_none",
        where="pipe.toml",
    ),
    Row(
        "PipeStage.max_turns",
        WORKS,
        LIST,
        reason="ターン数の上限は会話側で決まる",
        scope="stage_list",
        path=("max_turns",),
        test="not_none",
        where="pipe.toml",
    ),
    Row(
        "PipeStage.max_thinking_tokens",
        WORKS,
        LIST,
        reason="考える量の上限は会話側で決まる",
        scope="stage_list",
        path=("max_thinking_tokens",),
        test="not_none",
        where="pipe.toml",
    ),
    Row(
        "PipeStage.fallback_model",
        WORKS,
        LIST,
        reason="予備のモデルは会話側で決まる",
        scope="stage_list",
        path=("fallback_model",),
        test="not_none",
        where="pipe.toml",
    ),
    Row(
        "PipeStage.permission_mode",
        WORKS,
        LIST,
        reason="許可の方式は会話側で決まる",
        scope="stage_list",
        path=("permission_mode",),
        test="not_none",
        where="pipe.toml",
    ),
    _w("PipeStage.check"),
    _w("PipeStage.next"),
    _w("PipeStage.writes"),
    _w("PipeStage.system_append"),
    # 断る行（段ごとの文の順：group → routes → check.judge → agents → mcp → mcp_servers → web → max_budget_usd）
    Row(
        "PipeStage.group",
        WORKS,
        REFUSE,
        reason="並列の段は本体が同時に流す仕組みで、会話の道は段を1つずつ流す",
        scope="stage",
        path=("group",),
        sentence="段「{stage}」のgroup（並列の段）は、会話の中では流せません",
    ),
    Row(
        "PipeStage.routes",
        WORKS,
        REFUSE,
        reason="分岐は構造化出力で次の段を決めるが、会話の道には構造化出力が無い",
        scope="stage",
        path=("routes",),
        sentence="段「{stage}」のroutes（分岐）は、会話の中では流せません（構造化出力が無いため）",
    ),
    Row(
        "StageCheck.judge",
        WORKS,
        REFUSE,
        reason="審査は構造化出力で点を受け取るが、会話の道には構造化出力が無い",
        scope="stage",
        path=("check", "judge"),
        test="not_none",
        nested=True,
        sentence="段「{stage}」のcheck.judge（審査）は、会話の中では流せません（構造化出力が無いため）",
    ),
    Row(
        "PipeStage.agents",
        WORKS,
        REFUSE,
        reason="段の中のサブエージェントの定義を会話の道では渡せない",
        scope="stage",
        path=("agents",),
        sentence="段「{stage}」のagents（段の中のサブエージェント）は、会話の中では流せません",
    ),
    Row(
        "PipeStage.mcp",
        WORKS,
        REFUSE,
        reason="MCP の道具の許可を会話の道では絞れない",
        scope="stage",
        path=("mcp",),
        sentence="段「{stage}」のmcp（MCP の道具）は、会話の中では流せません",
    ),
    Row(
        "PipeStage.mcp_servers",
        WORKS,
        REFUSE,
        reason="MCP サーバーの定義を会話の道では渡せない",
        scope="stage",
        path=("mcp_servers",),
        sentence="段「{stage}」のmcp_servers（MCP サーバー）は、会話の中では流せません",
    ),
    Row(
        "PipeStage.web",
        WORKS,
        REFUSE,
        reason="Web の道具の許可を会話の道では絞れない",
        caveat="web = [] や fetch_domains = [] は偽なので断らない（web か fetch_domains のどちらかが真のとき断る）",
        scope="stage",
        path=("web", "fetch_domains"),
        sentence="段「{stage}」のweb（Web の道具）は、会話の中では流せません",
    ),
    Row(
        "PipeStage.max_budget_usd",
        WORKS,
        REFUSE,
        reason="会話の道では使用量を取れず、費用の上限を守れない",
        scope="stage",
        path=("max_budget_usd",),
        test="not_none",
        sentence="段「{stage}」のmax_budget_usd（費用の上限）は、会話の中では守れないので流せません",
    ),
    _child("PipeStage.fetch_domains", "PipeStage.web"),
    Row(
        "PipeStage.add_dirs",
        WORKS,
        LIST,
        reason="追加で読めるフォルダは会話側の許可で決まる",
        caveat="add_dirs = [] は偽なので一覧に出さない",
        scope="stage_list",
        path=("add_dirs",),
        where="pipe.toml",
    ),
    _child("PipeStage.max_agent_calls", "PipeStage.agents"),
    Row("PipeStage.problems", WORKS, NA, reason="定義を読んだときの問題の控え（検査用の内部欄）で、流すときの設定ではない"),
    # ---- StageCheck / StageJudge / JudgeItem ----
    _w("StageCheck.verdict"),
    _w("StageCheck.command"),
    _w("StageCheck.timeout_sec"),
    _w("StageCheck.on_fail"),
    _w("StageCheck.max_retries"),
    _child("StageJudge.threshold", "StageCheck.judge"),
    _child("StageJudge.criteria", "StageCheck.judge"),
    _child("StageJudge.must", "StageCheck.judge"),
    _child("JudgeItem.name", "StageCheck.judge"),
    _child("JudgeItem.description", "StageCheck.judge"),
    # ---- AgentDef / McpServerDef ----
    _child("AgentDef.description", "PipeStage.agents"),
    _child("AgentDef.prompt", "PipeStage.agents"),
    _child("AgentDef.tools", "PipeStage.agents"),
    _child("AgentDef.model", "PipeStage.agents"),
    _child("McpServerDef.type", "PipeStage.mcp_servers"),
    _child("McpServerDef.command", "PipeStage.mcp_servers"),
    _child("McpServerDef.args", "PipeStage.mcp_servers"),
    _child("McpServerDef.url", "PipeStage.mcp_servers"),
    # ---- StageConfig（pipeline.toml の [stages.<段>]）----
    Row(
        "StageConfig.model",
        WORKS,
        LIST,
        reason="モデルは会話側で決まる",
        caveat="一覧に出すのはパイプにある段だけ（パイプに無い段名は出ない）",
        scope="config_list",
        path=("model",),
        test="not_none",
        where="pipeline.toml",
    ),
    Row(
        "StageConfig.max_turns",
        WORKS,
        LIST,
        reason="ターン数の上限は会話側で決まる",
        caveat="一覧に出すのはパイプにある段だけ（パイプに無い段名は出ない）",
        scope="config_list",
        path=("max_turns",),
        test="not_none",
        where="pipeline.toml",
    ),
    Row(
        "StageConfig.max_budget_usd",
        WORKS,
        REFUSE,
        reason="会話の道では使用量を取れず、費用の上限を守れない",
        caveat=(
            "断る判断は cfg.stages を全部見るので、パイプに無い段名の [stages.<段>] でも断る。"
            "pipeline.toml の max_budget_usd = 0 は未設定（None）になるので断らない"
        ),
        scope="config_stage",
        path=("max_budget_usd",),
        test="not_none",
        sentence="pipeline.toml の [stages.{stage}] の max_budget_usd（費用の上限）は、会話の中では守れないので流せません",
    ),
    # ---- Config ----
    _w("Config.project_dir"),
    _w("Config.work_dir"),
    _na("Config.max_retries", "会話の道は段の check.max_retries を使い、パイプ全体の既定の回数は使わない"),
    _na("Config.test_command", "会話の道は検査の確認用コマンドを段の check.command で流す"),
    _na("Config.test_timeout_sec", "会話の道は検査のタイムアウトを段の check.timeout_sec で決める"),
    Row(
        "Config.auto_approve",
        WORKS,
        SILENT,
        reason="確認は会話の中で人に聞くので、自動承認は効かない（断らず黙る）",
    ),
    _na("Config.pause_for_review", "会話の道は確認待ちで止まるのが常で、設定で切り替えない"),
    _w("Config.extra_test_globs"),
    _w("Config.stages"),
    _na("Config.domain_dir", "ドメインの文書を積む設計の段は本体の専用の流れで、会話の道では使わない"),
    Row(
        "Config.setting_sources",
        WORKS,
        SILENT,
        reason="SDK に渡す設定の出どころ。会話の道は会話側の設定が効くので、この設定は効かない（断らず黙る）",
    ),
    _w("Config.protected_paths"),
    _w("Config.pipe"),
    _na("Config.max_buffer_mb", "SDK の受信バッファの大きさで、SDK を呼ばない会話の道には関係しない"),
)


# ---- 判断 -------------------------------------------------------------------------------------------


def _read(obj: Any, row: Row) -> list[Any]:
    """行の path で値を読む。nested なら入れ子をたどる（途中が None なら空）。そうでなければ名前ごとの値。"""
    if row.nested:
        cur = obj
        for name in row.path:
            if cur is None:
                return [None]
            cur = getattr(cur, name)
        return [cur]
    return [getattr(obj, name) for name in row.path]


def _hit(obj: Any, row: Row) -> bool:
    """行の test を満たすか（path が複数なら、どれか）。"""
    for v in _read(obj, row):
        if row.test == "truthy":
            ok = bool(v)
        elif row.test == "not_none":
            ok = v is not None
        elif row.test.startswith("ne:"):
            ok = v != row.test[3:]
        else:
            raise ValueError(f"知らない test: {row.test}（{row.key}）")
        if ok:
            return True
    return False


def _rows(table: tuple[Row, ...], actor: str, action: str, scope: str) -> list[Row]:
    return [r for r in table if r.scope == scope and getattr(r, actor) == action]


def refusals(pipe: Any, cfg: Any, after: Any, table: tuple[Row, ...] = TABLE, actor: str = "chat") -> list[str]:
    """actor では流せない形を、全部集めて返す（空なら流せる）。順番は pipe → after → 段ごと → pipeline.toml。"""
    out: list[str] = []
    for r in _rows(table, actor, REFUSE, "pipe"):
        if _hit(pipe, r):
            out.append(r.sentence.format(value=_read(pipe, r)[0]))
    for r in _rows(table, actor, REFUSE, "after"):
        if after:
            out.append(r.sentence)
    stage_rows = _rows(table, actor, REFUSE, "stage")
    for s in pipe.stages:
        for r in stage_rows:
            if _hit(s, r):
                out.append(r.sentence.format(stage=s.name))
    config_rows = _rows(table, actor, REFUSE, "config_stage")
    for name, sc in cfg.stages.items():
        for r in config_rows:
            if _hit(sc, r):
                out.append(r.sentence.format(stage=name))
    return out


def list_items(pipe: Any, cfg: Any, table: tuple[Row, ...] = TABLE, actor: str = "chat") -> list[dict[str, str]]:
    """actor では効かない設定（断らず、見せる）。段ごとに pipe.toml の分、そのあと pipeline.toml の分。"""
    out: list[dict[str, str]] = []
    stage_rows = _rows(table, actor, LIST, "stage_list")
    config_rows = _rows(table, actor, LIST, "config_list")
    for s in pipe.stages:
        for r in stage_rows:
            if _hit(s, r):
                out.append({"stage": s.name, "key": r.path[0], "where": r.where})
        sc = cfg.stages.get(s.name)
        if sc is not None:
            for r in config_rows:
                if _hit(sc, r):
                    out.append({"stage": s.name, "key": r.path[0], "where": r.where})
    return out


def keys_with(action: str, actor: str = "chat", table: tuple[Row, ...] = TABLE) -> list[str]:
    """actor の動きが action の行の鍵（表の並び）。"""
    return [r.key for r in table if getattr(r, actor) == action]


# ---- 表の検査 ---------------------------------------------------------------------------------------


def check_table(table: tuple[Row, ...], classes: Any, extra_keys: tuple[str, ...] = ("--after",)) -> list[str]:
    """表の問題の文を返す（空なら問題なし）。classes は dataclass の型の並び。"""
    problems: list[str] = []
    real: list[str] = []
    for cls in classes:
        real += [f"{cls.__name__}.{f.name}" for f in dataclasses.fields(cls)]
    real += list(extra_keys)
    keys = [r.key for r in table]
    for k in real:
        if k not in keys:
            problems.append(f"表に無い: {k}")
    for k in keys:
        if k not in real:
            problems.append(f"実在しない: {k}")
    seen: set[str] = set()
    for k in keys:
        if k in seen:
            problems.append(f"鍵が重複: {k}")
        seen.add(k)
    by_key = {r.key: r for r in table}
    for r in table:
        for actor in ACTORS:
            act = getattr(r, actor)
            if act not in ACTIONS:
                problems.append(f"知らない動き: {r.key} の {actor} = {act}")
            if act in (REFUSE, SILENT) and not r.reason.strip():
                problems.append(f"理由が無い: {r.key}（{actor} が {act}）")
        if r.scope:
            if r.scope in REFUSE_SCOPES:
                if r.chat != REFUSE:
                    problems.append(f"scope と動きが合わない: {r.key}（{r.scope} は断る行）")
                if not r.sentence:
                    problems.append(f"断る文が無い: {r.key}")
            elif r.scope in LIST_SCOPES:
                if r.chat != LIST:
                    problems.append(f"scope と動きが合わない: {r.key}（{r.scope} は一覧に出す行）")
                if not r.where:
                    problems.append(f"where が無い: {r.key}")
            else:
                problems.append(f"知らない scope: {r.key}（{r.scope}）")
            if not r.path and r.scope != "after":  # --after は引数の真だけを見る
                problems.append(f"path が無い: {r.key}")
        if r.via:
            parent = by_key.get(r.via)
            if parent is None:
                problems.append(f"親が表に無い: {r.key} の via {r.via}")
            else:
                if parent.chat != r.chat:
                    problems.append(f"親と動きが違う: {r.key} と {r.via}")
                if not parent.scope:
                    problems.append(f"親に scope が無い: {r.via}")
        if r.chat in (REFUSE, LIST) and not r.scope and not r.via:
            problems.append(f"判断が書かれていない: {r.key}")
    return problems
