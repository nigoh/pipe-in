"""パイプの定義（<対象>/.pipe-in/pipes/pipe-in-<名前>/pipe.toml など）を読み、検査し、探す。

パイプは1つのフォルダで、pipe.toml（段の並び・権限・確認の有無）と prompts/（段ごとの指示文）と README.md を持つ。
作るのはジェネレーター（generator/）。ここは読むだけで、書かない。
前の版（devpipe）の置き場所 .devpipe/pipes/・フォルダ名 devpipe-<名前>/・環境変数 DEVPIPE_PIPES_DIR も読み続ける。
"""

from __future__ import annotations

import os
import re
import tomllib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

from ..engine.guard import DANGEROUS_BASH

PIPE_FILE = "pipe.toml"
# パイプのフォルダ名の頭。前の版（devpipe）の頭も読み続ける。同じ置き場所の中ではこの順に探す
PREFIX = "pipe-in-"
LEGACY_PREFIX = "devpipe-"
PREFIXES = (PREFIX, LEGACY_PREFIX)
# 今までの置き場所を変える環境変数。前の版の名前も読む（両方あれば新しいほう）
PIPES_DIR_ENV = "PIPE_IN_PIPES_DIR"
LEGACY_PIPES_DIR_ENV = "DEVPIPE_PIPES_DIR"
# 対象プロジェクトの中のパイプの置き場所（先に探す）。前の版の置き場所はその次に探す
PROJECT_PIPES_DIR = Path(".pipe-in") / "pipes"
LEGACY_PROJECT_PIPES_DIR = Path(".devpipe") / "pipes"
KINDS = ("dev", "linear")
ACCESS = ("read", "docs", "tests", "code")
INPUT_MODES = ("required", "optional", "none")
NAME_RE = re.compile(r"[a-z0-9][a-z0-9-]*")
# 記録の置き場所の中で、パイプや成果物の名前に使えないもの
RESERVED_NAMES = {"logs", "end"}
RESERVED_OUTPUTS = {"00_input.md", "99_summary.md", "state.json"}
# 分岐・飛び先で「ここで終わる」を表す名前
END = "end"
DEFAULT_MAX_STEPS = 50
# mcp__<サーバー>__<ツール> か mcp__<サーバー>__*（サーバーの名前は必ず書く）
MCP_RE = re.compile(r"mcp__[A-Za-z0-9][A-Za-z0-9_.-]*?__(\*|[A-Za-z0-9][A-Za-z0-9_.-]*)")
DOMAIN_RE = re.compile(r"[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+")
# 許可のモードは、確認を省く・何でも許すものを除く（本体の guard と人の確認で守るため）
PERMISSION_MODES = ("default", "acceptEdits", "plan")
MCP_TYPES = ("stdio", "http", "sse")
# サブエージェントに持たせられない道具（入れ子・すり抜けの道）
AGENT_FORBIDDEN_TOOLS = ("Task", "Agent", "PowerShell")
READ_ONLY_TOOLS = ("Read", "Glob", "Grep", "Skill", "ToolSearch", "TodoWrite", "StructuredOutput")
EDIT_TOOLS = ("Write", "Edit", "MultiEdit", "NotebookEdit")


class PipeError(Exception):
    """定義のファイルを読めない。"""


@dataclass
class JudgeItem:
    """審査の項目か must の1つ。"""

    name: str
    description: str = ""


@dataclass
class StageJudge:
    """段の検証の審査（[stages.check.judge]）。"""

    threshold: float = 0.7
    criteria: list[JudgeItem] = field(default_factory=list)
    must: list[JudgeItem] = field(default_factory=list)


@dataclass
class StageCheck:
    """段の検証。どちらかが不合格なら on_fail の段へ戻す。"""

    verdict: bool = False  # 段に判定（pass / fail と直す点）を構造化出力で返させる
    command: str | None = None  # 本体が流す確認用のコマンド。終了コード 0 で合格
    timeout_sec: int = 600
    on_fail: str | None = None  # 不合格のときに戻す段（自分か前の段）。省くと自分
    max_retries: int = 2
    judge: StageJudge | None = None


@dataclass
class AgentDef:
    """段の中で使うサブエージェント（Agent SDK の AgentDefinition）。"""

    description: str = ""
    prompt: str = ""
    tools: list[str] = field(default_factory=list)
    model: str | None = None


@dataclass
class McpServerDef:
    """段で使う MCP サーバー。stdio は command・args、http・sse は url。"""

    type: str = "stdio"
    command: str | None = None
    args: list[str] = field(default_factory=list)
    url: str | None = None


@dataclass
class PipeStage:
    name: str
    label: str
    output: str
    access: str
    prompt: str | None = None
    prompt_file: Path | None = None
    docs_dir: str | None = None
    bash: bool = False
    review: bool = False
    model: str | None = None
    max_turns: int | None = None
    max_budget_usd: float | None = None
    check: StageCheck | None = None
    # 分岐：段が choice で返した値 → 次の段（"end" で終わり）
    routes: dict[str, str] = field(default_factory=dict)
    # 次の段（"end" で終わり）。省くと定義の次の段
    next: str | None = None
    # 同じ group の続いた段は同時に流す
    group: str | None = None
    # web = true なら WebFetch と WebSearch。web = ["ドメイン"] なら、そのドメインへの WebFetch だけ
    web: bool = False
    fetch_domains: list[str] | None = None
    mcp: list[str] = field(default_factory=list)
    # 書き込み範囲を、さらにこの glob に絞る
    writes: list[str] = field(default_factory=list)
    # Agent SDK の設定
    permission_mode: str | None = None
    max_thinking_tokens: int | None = None
    fallback_model: str | None = None
    system_append: str | None = None
    add_dirs: list[str] = field(default_factory=list)
    agents: dict[str, AgentDef] = field(default_factory=dict)
    mcp_servers: dict[str, McpServerDef] = field(default_factory=dict)
    # 段の1回の実行で呼べるサブエージェントの数（D0034）。省くと既定（20）。agents のある段だけに書ける
    max_agent_calls: int | None = None
    # 読み込みのときに見つけた、型の誤り（check_pipe が報告する）
    problems: list[str] = field(default_factory=list)

    def prompt_text(self) -> str:
        if self.prompt_file is not None:
            return self.prompt_file.read_text(encoding="utf-8").strip()
        return (self.prompt or "").strip()


@dataclass
class PipeDef:
    name: str
    dir: Path
    kind: str = "linear"
    label: str = ""
    description: str = ""
    input: str = "optional"
    test_command: str | None = None
    stages: list[PipeStage] = field(default_factory=list)
    # 段を流す回数の上限（差し戻しや飛び先の無限ループを止める）
    max_steps: int = DEFAULT_MAX_STEPS


def pipe_folders(name: str) -> list[str]:
    """名前のパイプのフォルダ名の候補を、探す順に返す（新しい頭 → 前の版の頭）。"""
    return [p + name for p in PREFIXES]


def name_of(folder: str) -> str | None:
    """フォルダ名からパイプの名前を返す。どちらかの頭で始まり、残りが正しい名前のときだけ。ほかは None。"""
    for p in PREFIXES:
        if folder.startswith(p):
            rest = folder[len(p):]
            return rest if is_valid_name(rest) else None
    return None


def is_legacy(pipe_dir: Path) -> bool:
    """前の版の名前のパイプか（フォルダ名が前の版の頭で始まるか、前の版の置き場所の中にあるか）。"""
    if pipe_dir.name.startswith(LEGACY_PREFIX):
        return True
    parent = pipe_dir.parent
    return (parent.parent.name, parent.name) == LEGACY_PROJECT_PIPES_DIR.parts


def env_pipes_dir(environ: Mapping[str, str]) -> Path | None:
    """環境変数で指定した置き場所。PIPE_IN_PIPES_DIR → DEVPIPE_PIPES_DIR の順。空の値は無いものとする。"""
    for key in (PIPES_DIR_ENV, LEGACY_PIPES_DIR_ENV):
        value = environ.get(key)
        if value:
            return Path(value).expanduser()
    return None


def is_valid_name(name: str) -> bool:
    return bool(NAME_RE.fullmatch(name)) and name not in RESERVED_NAMES


def default_pipes_dir() -> Path:
    """今までのパイプの置き場所。環境変数（env_pipes_dir）があればそこ、なければこのリポジトリの pipes/。

    リポジトリを clone して pip install -e . で使う前提（リポジトリの中のフォルダを指す）。
    """
    env = env_pipes_dir(os.environ)
    if env is not None:
        return env
    return Path(__file__).resolve().parents[2] / "pipes"


def pipes_dirs(project: Path | None = None, pipes_dir: Path | None = None) -> list[Path]:
    """パイプを探す場所を、探す順に返す。

    pipes_dir（--pipes-dir）を指定したときはそこだけ。なければ、対象の .pipe-in/pipes/ → 前の版の置き場所 → 今までの場所。
    """
    if pipes_dir is not None:
        return [pipes_dir]
    dirs = [project / PROJECT_PIPES_DIR, project / LEGACY_PROJECT_PIPES_DIR] if project is not None else []
    return [*dirs, default_pipes_dir()]


def new_pipes_dir(project: Path, pipes_dir: Path | None = None) -> Path:
    """新しいパイプを作る場所：--pipes-dir → 環境変数（新 → 前の版）→ 対象の .pipe-in/pipes/。"""
    if pipes_dir is not None:
        return pipes_dir
    env = env_pipes_dir(os.environ)
    return env if env is not None else project / PROJECT_PIPES_DIR


def existing_pipes(name: str, dirs: Iterable[Path]) -> list[Path]:
    """dirs の中にある、その名前のパイプのフォルダ（新旧どちらの頭も）。同じものは1度だけ並べる。"""
    found: list[Path] = []
    seen: set[Path] = set()
    for base in dirs:
        for folder in pipe_folders(name):
            d = base / folder
            key = d.resolve()
            if d.exists() and key not in seen:
                seen.add(key)
                found.append(d)
    return found


def find_pipe(name_or_path: str, pipes_dir: Path | None = None, *, project: Path | None = None) -> Path | None:
    """名前なら pipes_dirs() の順に、その中で pipe-in-<名前>/ → devpipe-<名前>/ の順に探す。パスならそのフォルダ。

    pipe.toml がなければ None。
    """
    if is_valid_name(name_or_path):
        for base in pipes_dirs(project, pipes_dir):
            for folder in pipe_folders(name_or_path):
                d = base / folder
                if (d / PIPE_FILE).is_file():
                    return d
    p = Path(name_or_path).expanduser()
    if name_or_path and p.is_dir() and (p / PIPE_FILE).is_file():
        return p
    return None


# ---- 読み込み -------------------------------------------------------------


MAX_AGENT_CALLS_ERROR = "max_agent_calls は 1 以上の整数で書いてください"


def _opt_int(value: Any) -> int | None:
    return int(value) if isinstance(value, int) and not isinstance(value, bool) else None


def _opt_float(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _opt_str(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _str_list(value: Any, key: str, problems: list[str]) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list) and all(isinstance(v, str) for v in value):
        return list(value)
    problems.append(f"{key} は文字列の一覧で書いてください")
    return []


JUDGE_KEYS = ("threshold", "criteria", "must")
JUDGE_ITEM_KEYS = ("name", "description")


def _load_judge_items(raw: Any, key: str, problems: list[str]) -> list[JudgeItem]:
    if raw is None:
        return []
    if not isinstance(raw, list) or not all(isinstance(x, dict) for x in raw):
        problems.append(f"check.judge の {key} は [[stages.check.judge.{key}]] の表の並びで書いてください")
        return []
    items: list[JudgeItem] = []
    for n, x in enumerate(raw, start=1):
        at = f"check.judge の {key} の {n} つ目"
        for k in x:
            if k not in JUDGE_ITEM_KEYS:
                problems.append(f"{at}に知らないキー「{k}」があります（{' / '.join(JUDGE_ITEM_KEYS)} だけ）")
        name, desc = x.get("name"), x.get("description")
        if not isinstance(name, str):
            problems.append(f"{at}には name（文字列）が要ります")
        if not isinstance(desc, str):
            problems.append(f"{at}には description（文字列）が要ります")
        items.append(JudgeItem(name=name if isinstance(name, str) else "", description=desc if isinstance(desc, str) else ""))
    return items


def _load_judge(raw: Any, problems: list[str]) -> StageJudge | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        problems.append("check.judge は表（[stages.check.judge]）で書いてください")
        return None
    for k in raw:
        if k not in JUDGE_KEYS:
            problems.append(f"check.judge に知らないキー「{k}」があります（{' / '.join(JUDGE_KEYS)} だけ）")
    threshold = raw.get("threshold", 0.7)
    if isinstance(threshold, bool) or not isinstance(threshold, (int, float)):
        problems.append("check.judge の threshold は数（0 以上 1 以下）で書いてください")
        threshold = 0.7
    return StageJudge(
        threshold=float(threshold),
        criteria=_load_judge_items(raw.get("criteria"), "criteria", problems),
        must=_load_judge_items(raw.get("must"), "must", problems),
    )


def _load_check(raw: Any, problems: list[str]) -> StageCheck | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        problems.append("check は表（[stages.check]）で書いてください")
        return None
    max_retries = raw.get("max_retries", 2)
    timeout = raw.get("timeout_sec", 600)
    return StageCheck(
        verdict=raw.get("verdict") is True,
        command=_opt_str(raw.get("command")),
        timeout_sec=timeout if isinstance(timeout, int) and not isinstance(timeout, bool) else 0,
        on_fail=_opt_str(raw.get("on_fail")),
        max_retries=max_retries if isinstance(max_retries, int) and not isinstance(max_retries, bool) else -1,
        judge=_load_judge(raw.get("judge"), problems),
    )


def _load_agents(raw: Any, problems: list[str]) -> dict[str, AgentDef]:
    if raw is None:
        return {}
    if not isinstance(raw, dict) or not all(isinstance(v, dict) for v in raw.values()):
        problems.append("agents は [stages.agents.<名前>] の表で書いてください")
        return {}
    return {
        str(name): AgentDef(
            description=_opt_str(a.get("description")) or "",
            prompt=_opt_str(a.get("prompt")) or "",
            tools=_str_list(a.get("tools"), f"サブエージェント「{name}」の tools", problems),
            model=_opt_str(a.get("model")),
        )
        for name, a in raw.items()
    }


def _load_mcp_servers(raw: Any, problems: list[str]) -> dict[str, McpServerDef]:
    if raw is None:
        return {}
    if not isinstance(raw, dict) or not all(isinstance(v, dict) for v in raw.values()):
        problems.append("mcp_servers は [stages.mcp_servers.<名前>] の表で書いてください")
        return {}
    return {
        str(name): McpServerDef(
            type=str(m.get("type", "stdio")),
            command=_opt_str(m.get("command")),
            args=_str_list(m.get("args"), f"MCP サーバー「{name}」の args", problems),
            url=_opt_str(m.get("url")),
        )
        for name, m in raw.items()
    }


def _load_stage(s: dict[str, Any], pipe_dir: Path) -> PipeStage:
    problems: list[str] = []
    prompt_file = _opt_str(s.get("prompt_file"))
    web_raw = s.get("web", False)
    web, fetch_domains = False, None
    if web_raw is True or web_raw is False:
        web = web_raw
    elif isinstance(web_raw, list) and all(isinstance(d, str) for d in web_raw):
        fetch_domains = list(web_raw)
    else:
        problems.append("web は true / false か、ドメインの一覧（例: [\"docs.python.org\"]）で書いてください")
    routes_raw = s.get("routes", {})
    routes: dict[str, str] = {}
    if isinstance(routes_raw, dict) and all(isinstance(v, str) for v in routes_raw.values()):
        routes = dict(routes_raw)
    else:
        problems.append("routes は「選んだ値 = 次の段」の表（[stages.routes]）で書いてください")
    max_agent_calls = _opt_int(s.get("max_agent_calls"))
    if "max_agent_calls" in s and max_agent_calls is None:
        problems.append(MAX_AGENT_CALLS_ERROR)
    return PipeStage(
        name=str(s.get("name", "")),
        label=str(s.get("label") or s.get("name", "")),
        output=str(s.get("output", "")),
        access=str(s.get("access", "read")),
        prompt=_opt_str(s.get("prompt")),
        prompt_file=pipe_dir / prompt_file if prompt_file else None,
        docs_dir=_opt_str(s.get("docs_dir")),
        bash=s.get("bash") is True,
        review=s.get("review") is True,
        model=_opt_str(s.get("model")),
        max_turns=_opt_int(s.get("max_turns")),
        max_budget_usd=_opt_float(s.get("max_budget_usd")),
        check=_load_check(s.get("check"), problems),
        routes=routes,
        next=_opt_str(s.get("next")),
        group=_opt_str(s.get("group")),
        web=web,
        fetch_domains=fetch_domains,
        mcp=_str_list(s.get("mcp"), "mcp", problems),
        writes=_str_list(s.get("writes"), "writes", problems),
        permission_mode=_opt_str(s.get("permission_mode")),
        max_thinking_tokens=_opt_int(s.get("max_thinking_tokens")) if "max_thinking_tokens" in s else None,
        fallback_model=_opt_str(s.get("fallback_model")),
        system_append=_opt_str(s.get("system_append")),
        add_dirs=_str_list(s.get("add_dirs"), "add_dirs", problems),
        agents=_load_agents(s.get("agents"), problems),
        mcp_servers=_load_mcp_servers(s.get("mcp_servers"), problems),
        max_agent_calls=max_agent_calls,
        problems=problems,
    )


def load_pipe(pipe_dir: Path) -> PipeDef:
    path = pipe_dir / PIPE_FILE
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as e:
        raise PipeError(f"{path} を TOML として読めません: {e}") from e
    except OSError as e:
        raise PipeError(f"{path} を読めません: {e}") from e

    p = raw.get("pipe") if isinstance(raw.get("pipe"), dict) else {}
    raw_stages = raw.get("stages", [])
    stages = [_load_stage(s, pipe_dir) for s in (raw_stages if isinstance(raw_stages, list) else []) if isinstance(s, dict)]
    test_command = _opt_str(p.get("test_command"))
    max_steps = p.get("max_steps", DEFAULT_MAX_STEPS)
    return PipeDef(
        # 頭（pipe-in- か devpipe-）を除いた名前。どちらの頭でもないフォルダは、そのフォルダ名のまま
        name=name_of(pipe_dir.name) or pipe_dir.name,
        dir=pipe_dir,
        kind=str(p.get("kind", "linear")),
        label=str(p.get("label", "")),
        description=str(p.get("description", "")),
        input=str(p.get("input", "optional")),
        test_command=test_command if test_command and test_command.strip() else None,
        stages=stages,
        max_steps=max_steps if isinstance(max_steps, int) and not isinstance(max_steps, bool) else 0,
    )


# ---- 検査 ---------------------------------------------------------------


def _inside(root: Path, rel: str) -> bool:
    if Path(rel).is_absolute():
        return False
    target = (root / rel).resolve()
    root = root.resolve()
    return target != root and root in target.parents


def _dangerous(command: str) -> str | None:
    for pattern, reason in DANGEROUS_BASH:
        if re.search(pattern, command):
            return reason
    return None


def _check_stage_basics(s: PipeStage, project_dir: Path, pipe: PipeDef, at: str) -> list[str]:
    errors: list[str] = []
    if s.access not in ACCESS:
        errors.append(at + f"権限の型「{s.access}」は使えません（{' / '.join(ACCESS)} のどれか）")
    if s.access == "docs":
        if not s.docs_dir:
            errors.append(at + 'access = "docs" には docs_dir（書き込める文書のフォルダ）が必要です')
        elif not _inside(project_dir, s.docs_dir):
            errors.append(at + f"docs_dir「{s.docs_dir}」はプロジェクトの外を指しています")
    elif s.docs_dir:
        errors.append(at + 'docs_dir は access = "docs" のときだけ書けます')

    if s.writes:
        if s.access == "read":
            errors.append(at + 'access = "read" の段には writes を書けません（成果物のほかは書けない型です）')
        for g in s.writes:
            parts = PurePosixPath(g).parts
            if not g or g.startswith(("/", "\\")) or re.match(r"[A-Za-z]:", g) or ".." in parts:
                errors.append(at + f"writes の「{g}」は、プロジェクトの中の相対パスの glob で書いてください")

    if s.prompt is not None and s.prompt_file is not None:
        errors.append(at + "prompt と prompt_file はどちらか一方だけ書いてください")
    elif s.prompt_file is not None:
        rel = os.path.relpath(s.prompt_file, pipe.dir)
        if not _inside(pipe.dir, rel):
            errors.append(at + f"指示ファイル {rel} はパイプのフォルダの外にあります（prompts/ の下に置いてください）")
        elif not s.prompt_file.is_file():
            errors.append(at + f"指示ファイル {rel} が見つかりません")
    elif not (s.prompt or "").strip():
        errors.append(at + "指示（prompt か prompt_file）がありません")

    for m in s.mcp:
        if not MCP_RE.fullmatch(m):
            errors.append(at + f"mcp の「{m}」は使えません（mcp__<サーバー>__<ツール> か mcp__<サーバー>__* で書いてください）")
    for d in s.fetch_domains or []:
        if not DOMAIN_RE.fullmatch(d):
            errors.append(at + f"web のドメイン「{d}」は、ドメインの名前だけで書いてください（例: docs.python.org）")
    return errors


def stage_tools(s: PipeStage) -> list[str]:
    """段で使える道具（サブエージェントに持たせてよい範囲）。MCP は段の mcp に書いたもの。"""
    tools = [*READ_ONLY_TOOLS, *EDIT_TOOLS]
    if s.bash:
        tools.append("Bash")
    if s.web:
        tools += ["WebFetch", "WebSearch"]
    elif s.fetch_domains:
        tools.append("WebFetch")
    return tools


def _mcp_allowed(tool: str, mcp: list[str]) -> bool:
    return any(tool == m or (m.endswith("__*") and tool.startswith(m[:-1])) for m in mcp)


def _check_sdk(s: PipeStage, at: str) -> list[str]:
    """Agent SDK の設定の検査。"""
    errors: list[str] = []
    if s.permission_mode is not None and s.permission_mode not in PERMISSION_MODES:
        errors.append(
            at + f"permission_mode「{s.permission_mode}」は使えません（{' / '.join(PERMISSION_MODES)} のどれか。"
            "確認を省くモードは、安全のため使えません）"
        )
    if s.max_thinking_tokens is not None and s.max_thinking_tokens < 1:
        errors.append(at + "max_thinking_tokens は 1 以上の整数で書いてください")
    if s.max_agent_calls is not None and s.max_agent_calls < 1:
        errors.append(at + MAX_AGENT_CALLS_ERROR)
    if s.max_agent_calls is not None and not s.agents:
        errors.append(at + "max_agent_calls は agents を書いた段だけに書けます（サブエージェントを呼ばない段には要りません）")
    for d in s.add_dirs:
        if not d or d.startswith(("/", "\\")) or re.match(r"[A-Za-z]:", d):
            errors.append(at + f"add_dirs の「{d}」は、プロジェクトからの相対パスで書いてください（手元の絶対パスを書かないため）")
    allowed = set(stage_tools(s))
    for name, a in s.agents.items():
        if not NAME_RE.fullmatch(name):
            errors.append(at + f"サブエージェントの名前「{name}」は、英小文字・数字・- で書いてください")
        if not a.description.strip():
            errors.append(at + f"サブエージェント「{name}」の description（いつ任せるか）がありません")
        if not a.prompt.strip():
            errors.append(at + f"サブエージェント「{name}」の prompt（指示）がありません")
        for t in a.tools:
            if t in AGENT_FORBIDDEN_TOOLS:
                errors.append(at + f"サブエージェント「{name}」に {t} は持たせられません（入れ子や、決まりのすり抜けになるため）")
            elif t not in allowed and not (t.startswith("mcp__") and _mcp_allowed(t, s.mcp)):
                errors.append(at + f"サブエージェント「{name}」の道具 {t} は、この段で使えない道具です")
    for name, m in s.mcp_servers.items():
        if not NAME_RE.fullmatch(name.replace("_", "-")):
            errors.append(at + f"MCP サーバーの名前「{name}」は、英小文字・数字・- で書いてください")
        if m.type not in MCP_TYPES:
            errors.append(at + f"MCP サーバー「{name}」の type「{m.type}」は使えません（{' / '.join(MCP_TYPES)} のどれか）")
        elif m.type == "stdio" and not m.command:
            errors.append(at + f"MCP サーバー「{name}」（stdio）には command が要ります")
        elif m.type != "stdio" and not m.url:
            errors.append(at + f"MCP サーバー「{name}」（{m.type}）には url が要ります")
        # MCP サーバーを足しても、使う道具を mcp に1つも書かなければ何も使えない（guard が止める）
        if not s.mcp:
            errors.append(at + f"MCP サーバー「{name}」の道具が mcp にありません（mcp__{name}__<道具> を書いてください）")
    return errors


def _check_judge(j: StageJudge) -> list[str]:
    """審査（check.judge）の検査。criteria 同士・must 同士の同名は誤り（別々の入れ物の間は許す）。"""
    errors: list[str] = []
    if not 0 <= j.threshold <= 1:
        errors.append("check.judge の threshold は 0 以上 1 以下で書いてください")
    if not j.criteria:
        errors.append("check.judge の criteria（採点の項目）が1つも書かれていません")
    for key, items in (("criteria", j.criteria), ("must", j.must)):
        seen: set[str] = set()
        for it in items:
            if not it.name.strip():
                errors.append(f"check.judge の {key} に、name が空の項目があります")
            elif it.name in seen:
                errors.append(f"check.judge の {key} の名前「{it.name}」が重複しています")
            seen.add(it.name)
    return errors


def _check_flow(s: PipeStage, i: int, pipe: PipeDef, at: str) -> list[str]:
    """検証・分岐・飛び先の検査。"""
    errors: list[str] = []
    index = {x.name: j for j, x in enumerate(pipe.stages)}

    def target_ok(name: str, what: str) -> None:
        if name != END and name not in index:
            errors.append(at + f"{what}の「{name}」という段はありません（段の名前か end）")

    if s.next is not None and s.routes:
        errors.append(at + "next と routes はどちらか一方だけ書いてください")
    if s.next is not None:
        target_ok(s.next, "next ")
    for choice, target in s.routes.items():
        target_ok(target, f"routes の {choice} の行き先")

    c = s.check
    if c is not None:
        if not c.verdict and not c.command and c.judge is None:
            errors.append(at + "check には verdict か command か judge のどれかを書いてください")
        if c.judge is not None:
            errors += [at + e for e in _check_judge(c.judge)]
        if c.command:
            reason = _dangerous(c.command)
            if reason:
                errors.append(at + f"check の command は使えません：{reason}")
        if c.max_retries < 0:
            errors.append(at + "check の max_retries は 0 以上の整数で書いてください")
        if c.timeout_sec <= 0:
            errors.append(at + "check の timeout_sec は 1 以上の整数で書いてください")
        if c.on_fail is not None:
            if c.on_fail not in index:
                errors.append(at + f"on_fail の「{c.on_fail}」という段はありません")
            elif index[c.on_fail] > i:
                errors.append(at + "on_fail は自分か前の段を指してください")
    return errors


def _check_groups(pipe: PipeDef) -> list[str]:
    errors: list[str] = []
    seen_closed: set[str] = set()
    prev: str | None = None
    for i, s in enumerate(pipe.stages, start=1):
        at = f"段 {i}（{s.name or '名前なし'}）: "
        g = s.group
        if g is not None:
            if g in seen_closed:
                errors.append(at + f"group「{g}」の段は続けて並べてください")
            if s.review or s.routes or s.next is not None:
                errors.append(at + "group の段には review・routes・next を書けません（同時に流すため）")
            if s.check and s.check.on_fail not in (None, s.name):
                errors.append(at + "group の段の on_fail は自分だけを指せます")
        if prev is not None and g != prev:
            seen_closed.add(prev)
        prev = g
    return errors


def check_pipe(pipe: PipeDef, project_dir: Path) -> list[str]:
    """定義の誤りを、日本語の文の一覧で返す。空なら問題なし。"""
    errors: list[str] = []
    if not is_valid_name(pipe.name):
        errors.append(f"パイプの名前「{pipe.name}」は使えません（英小文字・数字・- だけ。logs・end は不可）")
    if pipe.kind not in KINDS:
        errors.append(f"kind「{pipe.kind}」は使えません（{' / '.join(KINDS)} のどれか）")
    if pipe.input not in INPUT_MODES:
        errors.append(f"input「{pipe.input}」は使えません（{' / '.join(INPUT_MODES)} のどれか）")
    if pipe.kind == "dev":
        if pipe.stages:
            errors.append('kind = "dev" のパイプには [[stages]] を書けません（段は本体に組み込みの5段です）')
        return errors
    if pipe.max_steps < 1:
        errors.append("max_steps は 1 以上の整数で書いてください")
    if not pipe.stages:
        errors.append("段がありません（[[stages]] を1つ以上書いてください）")

    seen_names: set[str] = set()
    seen_outputs: set[str] = set()
    for i, s in enumerate(pipe.stages, start=1):
        at = f"段 {i}（{s.name or '名前なし'}）: "
        errors += [at + p for p in s.problems]
        if not is_valid_name(s.name):
            errors.append(at + "name は英小文字・数字・- で書いてください（logs・end は不可）")
        elif s.name in seen_names:
            errors.append(at + f"段の名前「{s.name}」が重複しています")
        seen_names.add(s.name)

        if not s.output or "/" in s.output or "\\" in s.output or s.output.startswith("."):
            errors.append(at + "output は記録の置き場所の中のファイル名だけを書いてください（例: 01_survey.md）")
        elif s.output in RESERVED_OUTPUTS:
            errors.append(at + f"output に「{s.output}」は使えません（本体が書くファイルです）")
        elif s.output in seen_outputs:
            errors.append(at + f"成果物「{s.output}」が重複しています")
        seen_outputs.add(s.output)

        errors += _check_stage_basics(s, project_dir, pipe, at)
        errors += _check_flow(s, i - 1, pipe, at)
        errors += _check_sdk(s, at)
    errors += _check_groups(pipe)
    return errors


def list_pipes(pipes_dir: Path | None = None) -> list[Path]:
    """置き場所の中の、pipe.toml を持つパイプのフォルダ（新旧どちらの頭も）。"""
    d = pipes_dir or default_pipes_dir()
    if not d.is_dir():
        return []
    return sorted(p for p in d.iterdir() if name_of(p.name) is not None and (p / PIPE_FILE).is_file())
