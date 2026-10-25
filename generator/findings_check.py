"""仕様書レビューの指摘（指摘の形 v1）と出典の台帳を、LLM を呼ばずに検査する（D0043）。

findings-check は、指摘のファイル・台帳・仕様書の本文を読み、形・出典・引用の一致・役割ごとの決まりを確かめる。
（テスト先行のための空の形。中身は実装の段で書く。）
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1


@dataclass(frozen=True)
class Problem:
    owner: str
    field: str
    reason: str

    def line(self) -> str:
        return f"{self.owner}: {self.field}: {self.reason}"


class InputError(Exception):
    """入力を受け取れない（終了コード 2）。"""


def normalize(text: str) -> str:
    raise NotImplementedError


def load_json(path: Path) -> Any:
    raise NotImplementedError


def load_versioned(doc: Any, key: str, label: str) -> list:
    raise NotImplementedError


def resolve_specs(sources: list, spec_files: list[tuple[str, str]]) -> dict[str, str]:
    raise NotImplementedError


def check_sources(sources: list) -> list[Problem]:
    raise NotImplementedError


def check_findings(findings: list, sources: list, specs: dict[str, str]) -> list[Problem]:
    raise NotImplementedError


def check_documents(findings_doc: Any, sources_doc: Any, specs: dict[str, str]) -> list[Problem]:
    raise NotImplementedError


def run(findings_path: Path, sources_path: Path, spec_paths: list[Path]) -> tuple[int, list[str]]:
    raise NotImplementedError


def main(argv: list[str]) -> int:
    raise NotImplementedError
