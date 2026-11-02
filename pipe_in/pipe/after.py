"""前のパイプの記録を受けて、後ろのパイプへ渡す（--after。D0069）。

前のパイプが PASSED で終わった記録だけを受け、渡すのは成果物の場所だけにする。
依頼メモは渡さない。受けた元は後ろの state.json（received_from）に書き、続きはそれを使う。
"""

from __future__ import annotations

import json
import posixpath
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from ..engine.config import Config
from ..engine.pipeline import STATE
from . import definition as pd

# 組み込みの開発フローの名前。記録の形が同じで区別できないため、前のパイプにはできない（D0069 の決めきれない点 1）
BUILTIN_DEV_NAME = "dev"


class AfterError(Exception):
    """--after を断るときの文（理由と直し方）。cli が SystemExit に直す。"""


@dataclass(frozen=True)
class Previous:
    name: str
    kind: str
    updated_at: str | None
    artifacts: tuple[tuple[str, str], ...]  # （段の表示名, 作業フォルダからの相対パス）。段の順

    def record(self) -> dict[str, Any]:
        """後ろの state.json の received_from の形。dir は作業フォルダからの相対（dev は "."）。"""
        return {
            "pipe": self.name,
            "kind": self.kind,
            "updated_at": self.updated_at,
            "dir": self.name if self.kind == "linear" else ".",
            "artifacts": [{"stage": label, "path": path} for label, path in self.artifacts],
        }


def check_after(values: list[str] | None, later: pd.PipeDef) -> str | None:
    """--after の形と組み合わせを検める。書かなければ None、名前なら名前を返す。断るなら AfterError。"""
    if not values:
        return None
    if len(values) > 1:
        raise AfterError("--after は1つだけ指定できます（前のパイプは1つだけ受けられます）")
    name = values[0]
    if "/" in name or "\\" in name:
        raise AfterError(f"--after にはパスではなく前のパイプの名前を書いてください（今の値: {name}。例: --after diagrams）")
    if not pd.is_valid_name(name):
        raise AfterError(f"--after「{name}」は名前ではありません（英小文字・数字・- だけ。例: --after diagrams）")
    if name == BUILTIN_DEV_NAME:
        raise AfterError("--after dev は使えません（組み込みの開発フローは前のパイプにできません。名前のあるパイプを指してください）")
    if name == later.name:
        raise AfterError(f"--after に後ろのパイプと同じ名前「{name}」は指せません（自分自身は前にできません）")
    if later.kind == "dev":
        raise AfterError(
            f"後ろのパイプ「{later.name}」は kind = \"dev\" なので --after は使えません"
            "（記録の場所が前のパイプと同じになるため。kind = \"linear\" のパイプで使ってください）"
        )
    return name


def _plain_name(value: str) -> bool:
    """記録の中のファイル名として読めるか（フォルダをまたがない・空でない）。"""
    return bool(value) and "/" not in value and "\\" not in value and value not in (".", "..")


def read_previous(name: str, cfg: Config, base: Path) -> Previous:
    """前のパイプの記録を読んで、受けてよいか決める。base は呼ぶ前の作業フォルダ（後ろの cfg.work_dir ではない）。

    読みの順番：定義（--pipe と同じ探し方）→ 種類 → 記録の場所 → JSON → 名前 → 開発用スキルの記録でないか
    → 確認待ち → 途中 → 失敗 → 成果物があるか。どこかで断るなら AfterError。
    """
    if not pd.is_valid_name(name):
        raise AfterError(f"--after「{name}」は名前ではありません（英小文字・数字・- だけ）")
    path = pd.find_pipe(name, project=cfg.project_dir)
    if path is None:
        raise AfterError(f"前のパイプ「{name}」が見つかりません（pipe-in-gen list で一覧を出せます）")
    try:
        pipe = pd.load_pipe(path)
    except pd.PipeError as e:
        raise AfterError(
            f"前のパイプ「{name}」の定義が読めません（{e}）。直し方：pipe.toml を直してから、前のパイプを流し直してください"
        ) from e
    if pipe.kind not in pd.KINDS:
        raise AfterError(f"前のパイプ「{name}」の kind「{pipe.kind}」は使えません。直し方：pipe.toml の kind を直してください")

    if pipe.kind == "linear":
        rec, shown = base / name, f"{name}/{STATE}"
    else:
        rec, shown = base, STATE
    state_path = rec / STATE
    if not state_path.is_file():
        raise AfterError(
            f"前のパイプ「{name}」の記録が、この実行の作業フォルダ（{cfg.rel(base)}）の中に見つかりません"
            f"（見た場所: {shown}）。直し方：--project・--config を前の実行と同じにする、または前のパイプを先に流してから --after を付けてください"
        )
    where = cfg.rel(state_path)
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise AfterError(
            f"前の記録 {where} が JSON として読めません（{e}）。直し方：前のパイプを流し直して、記録を作り直してください"
        ) from e
    if not isinstance(data, dict):
        raise AfterError(f"前の記録 {where} の形が読めません。直し方：前のパイプを流し直して、記録を作り直してください")
    if data.get("pipe") != name:
        raise AfterError(
            f"前の記録 {where} は「{data.get('pipe')}」の記録で、「{name}」ではありません"
            "（組み込みの開発フローの記録に上書きされた、などの場合があります）。"
            f"直し方：前のパイプ「{name}」を流し直してから、--after を付けてください"
        )
    if data.get("driver") is not None:
        raise AfterError(
            f"前の記録 {where} は Claude Code の開発用スキルの記録なので、受けられません。"
            "直し方：pipe-in のパイプを前のパイプにしてください"
        )
    if data.get("pending_review"):
        raise AfterError(
            f"前のパイプ「{name}」は確認待ちで止まっています（{where}）。"
            "直し方：前のパイプを --review（approve・revise・quit）で続けて終わらせてから、--after を付けてください"
        )
    final = data.get("final")
    if final is None:
        raise AfterError(
            f"前のパイプ「{name}」は途中で止まっています（{where} に結果が無い）。"
            "直し方：前のパイプを流し直して最後まで終わらせてから、--after を付けてください"
        )
    if final != "PASSED":
        raise AfterError(
            f"前のパイプ「{name}」は失敗で終わっています（結果: {final}）。"
            "直し方：失敗の原因を直して前のパイプを流し直してから、--after を付けてください"
        )

    artifacts: list[tuple[str, str]] = []
    stages = data.get("stages") if isinstance(data.get("stages"), list) else []
    for s in stages:
        if not isinstance(s, dict):
            continue
        out = s.get("output")
        if not isinstance(out, str) or not _plain_name(out):
            continue
        if (rec / out).is_file():
            label = s.get("label") if isinstance(s.get("label"), str) and s.get("label") else out
            artifacts.append((label, f"{name}/{out}" if pipe.kind == "linear" else out))
    if not artifacts:
        raise AfterError(
            f"前のパイプ「{name}」の成果物が1つもありません（{where} の段の成果物が見つかりません）。"
            "直し方：前のパイプを流し直して成果物を作ってから、--after を付けてください"
        )

    updated = data.get("updated_at")
    return Previous(
        name=name,
        kind=pipe.kind,
        updated_at=updated if isinstance(updated, str) else None,
        artifacts=tuple(artifacts),
    )


def guard_for(record: dict[str, Any], base_rel: str) -> tuple[Callable[[str], bool], str]:
    """受けた元の記録（received_from）から、前の記録を後ろの段が書けないかの判定と、hint に足す文を作る。

    base_rel は作業フォルダのプロジェクトからの相対（例: docs/pipeline）。判定の関数は、
    プロジェクトからの相対パスを受けて、書けないなら True を返す（書き込みを止める方向にしか働かない）。
    """
    d = posixpath.normpath(posixpath.join(base_rel, record["dir"]))
    linear = record["kind"] == "linear"
    name = record["pipe"]

    def blocked(rel: str) -> bool:
        p = posixpath.normpath(rel)
        # 記録のフォルダそのもの、またはそれを含むフォルダ（消す・動かす操作を止める）
        if p == d or p == "." or d.startswith(p + "/"):
            return True
        if linear:
            return p.startswith(d + "/")
        # dev の記録は作業フォルダ直下にある（state.json・00_input.md・成果物など）。後ろ自身の記録は含まない
        return posixpath.dirname(p) == d or p.startswith(d + "/logs/")

    return blocked, f"前のパイプ「{name}」の記録（{d}）は書けません"


def intro_line(prev: Previous) -> str:
    """流す前の画面の1行（前の名前・結果・終わった日時）。古さは判定しない。"""
    when = prev.updated_at or "不明"
    return f"前のパイプ「{prev.name}」：結果 PASSED・終わった日時 {when}"


def check_received(record: Any) -> str | None:
    """受けた元の記録の形を検める。読めない形なら、問題の文を返す（None なら読める）。"""
    if not isinstance(record, dict):
        return "形が違います（記録の項目は辞書で書かれているはずです）"
    if not isinstance(record.get("pipe"), str) or not record["pipe"]:
        return "pipe が読めません"
    if record.get("kind") not in pd.KINDS:
        return "kind が読めません"
    d = record.get("dir")
    if not isinstance(d, str) or not d or PurePosixPath(d).is_absolute() or ".." in PurePosixPath(d).parts:
        return "dir が読めません"
    arts = record.get("artifacts")
    if not isinstance(arts, list):
        return "artifacts が読めません"
    for a in arts:
        if not isinstance(a, dict) or not isinstance(a.get("stage"), str) or not isinstance(a.get("path"), str):
            return "artifacts の項目が読めません"
    return None
