"""パイプの定義（pipes/devpipe-<名前>/pipe.toml）を読み、検査し、探す。

パイプは1つのフォルダで、pipe.toml（段の並び・権限・確認の有無）と prompts/（段ごとの指示文）と README.md を持つ。
作るのはジェネレーター（generator/）。ここは読むだけで、書かない。
"""

from __future__ import annotations

import os
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PIPE_FILE = "pipe.toml"
PREFIX = "devpipe-"
PIPES_DIR_ENV = "DEVPIPE_PIPES_DIR"
KINDS = ("dev", "linear")
ACCESS = ("read", "docs", "tests", "code")
INPUT_MODES = ("required", "optional", "none")
NAME_RE = re.compile(r"[a-z0-9][a-z0-9-]*")
# 記録の置き場所の中で、パイプや成果物の名前に使えないもの
RESERVED_NAMES = {"logs"}
RESERVED_OUTPUTS = {"00_input.md", "99_summary.md", "state.json"}


class PipeError(Exception):
    """定義のファイルを読めない。"""


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


def is_valid_name(name: str) -> bool:
    return bool(NAME_RE.fullmatch(name)) and name not in RESERVED_NAMES


def default_pipes_dir() -> Path:
    """パイプを置くフォルダ。DEVPIPE_PIPES_DIR があればそこ、なければ devpipe のリポジトリの pipes/。

    devpipe を clone して pip install -e . で使う前提（リポジトリの中のフォルダを指す）。
    """
    env = os.environ.get(PIPES_DIR_ENV)
    if env:
        return Path(env).expanduser()
    return Path(__file__).resolve().parents[2] / "pipes"


def find_pipe(name_or_path: str, pipes_dir: Path | None = None) -> Path | None:
    """名前なら pipes_dir/devpipe-<名前>/ を、パスならそのフォルダを返す。pipe.toml がなければ None。"""
    if is_valid_name(name_or_path):
        d = (pipes_dir or default_pipes_dir()) / f"{PREFIX}{name_or_path}"
        if (d / PIPE_FILE).is_file():
            return d
    p = Path(name_or_path).expanduser()
    if name_or_path and p.is_dir() and (p / PIPE_FILE).is_file():
        return p
    return None


def _opt_int(value: Any) -> int | None:
    return int(value) if isinstance(value, int) and not isinstance(value, bool) else None


def _opt_float(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _opt_str(value: Any) -> str | None:
    return value if isinstance(value, str) else None


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
    stages: list[PipeStage] = []
    for s in raw_stages if isinstance(raw_stages, list) else []:
        if not isinstance(s, dict):
            continue
        prompt_file = _opt_str(s.get("prompt_file"))
        stages.append(
            PipeStage(
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
            )
        )
    test_command = _opt_str(p.get("test_command"))
    name = pipe_dir.name.removeprefix(PREFIX)
    return PipeDef(
        name=name,
        dir=pipe_dir,
        kind=str(p.get("kind", "linear")),
        label=str(p.get("label", "")),
        description=str(p.get("description", "")),
        input=str(p.get("input", "optional")),
        test_command=test_command if test_command and test_command.strip() else None,
        stages=stages,
    )


def _inside(root: Path, rel: str) -> bool:
    if Path(rel).is_absolute():
        return False
    target = (root / rel).resolve()
    root = root.resolve()
    return target != root and root in target.parents


def check_pipe(pipe: PipeDef, project_dir: Path) -> list[str]:
    """定義の誤りを、日本語の文の一覧で返す。空なら問題なし。"""
    errors: list[str] = []
    if not is_valid_name(pipe.name):
        errors.append(f"パイプの名前「{pipe.name}」は使えません（英小文字・数字・- だけ。logs は不可）")
    if pipe.kind not in KINDS:
        errors.append(f"kind「{pipe.kind}」は使えません（{' / '.join(KINDS)} のどれか）")
    if pipe.input not in INPUT_MODES:
        errors.append(f"input「{pipe.input}」は使えません（{' / '.join(INPUT_MODES)} のどれか）")
    if pipe.kind == "dev":
        if pipe.stages:
            errors.append('kind = "dev" のパイプには [[stages]] を書けません（段は devpipe に組み込みの5段です）')
        return errors
    if not pipe.stages:
        errors.append("段がありません（[[stages]] を1つ以上書いてください）")

    seen_names: set[str] = set()
    seen_outputs: set[str] = set()
    for i, s in enumerate(pipe.stages, start=1):
        at = f"段 {i}（{s.name or '名前なし'}）: "
        if not is_valid_name(s.name):
            errors.append(at + "name は英小文字・数字・- で書いてください（logs は不可）")
        elif s.name in seen_names:
            errors.append(at + f"段の名前「{s.name}」が重複しています")
        seen_names.add(s.name)

        if not s.output or "/" in s.output or "\\" in s.output or s.output.startswith("."):
            errors.append(at + "output は記録の置き場所の中のファイル名だけを書いてください（例: 01_survey.md）")
        elif s.output in RESERVED_OUTPUTS:
            errors.append(at + f"output に「{s.output}」は使えません（devpipe が書くファイルです）")
        elif s.output in seen_outputs:
            errors.append(at + f"成果物「{s.output}」が重複しています")
        seen_outputs.add(s.output)

        if s.access not in ACCESS:
            errors.append(at + f"権限の型「{s.access}」は使えません（{' / '.join(ACCESS)} のどれか）")
        if s.access == "docs":
            if not s.docs_dir:
                errors.append(at + 'access = "docs" には docs_dir（書き込める文書のフォルダ）が必要です')
            elif not _inside(project_dir, s.docs_dir):
                errors.append(at + f"docs_dir「{s.docs_dir}」はプロジェクトの外を指しています")
        elif s.docs_dir:
            errors.append(at + 'docs_dir は access = "docs" のときだけ書けます')

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
    return errors


def list_pipes(pipes_dir: Path | None = None) -> list[Path]:
    d = pipes_dir or default_pipes_dir()
    if not d.is_dir():
        return []
    return sorted(p for p in d.glob(f"{PREFIX}*") if (p / PIPE_FILE).is_file())
