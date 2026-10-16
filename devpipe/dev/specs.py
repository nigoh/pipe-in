"""開発フローの5段の定義（使えるツール、書き込める範囲、指示文）とプロンプトの組み立て。"""

from __future__ import annotations

from collections.abc import Callable
from importlib import resources
from typing import Any

from ..engine.config import Config
from ..engine.guard import is_test_path
from ..engine.pipeline import INPUT, STATE, SUMMARY
from ..engine.spec import EDIT_TOOLS, NO_SHELL_BYPASS, NO_WEB, READ_TOOLS, StageSpec, protect

__all__ = ["INPUT", "STATE", "SUMMARY"]  # 開発フローの記録のファイル名として、ここからも引けるようにする

STAGES: tuple[str, ...] = ("requirements", "design", "red", "implement", "test")

STAGE_LABELS: dict[str, str] = {
    "requirements": "要件定義",
    "design": "設計",
    "red": "テスト先行",
    "implement": "実装",
    "test": "検証",
}

# 段ごとの既定のターン数（pipeline.toml の [stages.<段>] max_turns が優先）
DEFAULT_MAX_TURNS = {"requirements": 40, "design": 60, "red": 100, "implement": 150, "test": 100}

REQUIREMENTS = "01_requirements.md"
DESIGN = "02_design.md"
RED = "03_red_tests.md"
IMPLEMENTATION = "04_implementation.md"
TEST_REPORT = "05_test_report.md"

TEST_VERDICT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "status": {
            "type": "string",
            "enum": ["pass", "fail", "blocked"],
            "description": "pass=全受け入れ基準を確認して合格 / fail=不合格あり / blocked=環境などの理由で確認できない",
        },
        "summary": {"type": "string", "description": "結果の要約（日本語・3行以内）"},
        "failures": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "criterion": {"type": "string", "description": "受け入れ基準のID（例: AC-03）"},
                    "detail": {"type": "string", "description": "期待した結果と実際の結果"},
                },
                "required": ["criterion", "detail"],
            },
        },
        "commands": {"type": "array", "items": {"type": "string"}, "description": "実行したテストコマンド"},
    },
    "required": ["status", "summary", "failures", "commands"],
}

RED_RESULT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "status": {
            "type": "string",
            "enum": ["red", "blocked"],
            "description": "red=受け入れ基準のテストを書き、実行して落ちることを確かめた / blocked=環境などの理由で実行できない",
        },
        "summary": {"type": "string", "description": "結果の要約（日本語・3行以内）"},
        "tests": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "criterion": {"type": "string", "description": "受け入れ基準のID（例: AC-03）"},
                    "test": {"type": "string", "description": "テストファイルとテスト名"},
                },
                "required": ["criterion", "test"],
            },
        },
        "commands": {"type": "array", "items": {"type": "string"}, "description": "実行したテストコマンド"},
    },
    "required": ["status", "summary", "tests", "commands"],
}


def _prompt_text(name: str) -> str:
    return resources.files("devpipe.dev").joinpath(f"prompts/{name}.md").read_text(encoding="utf-8")


def build_specs(cfg: Config) -> dict[str, StageSpec]:
    work = cfg.rel(cfg.work_dir)

    def in_work(rel: str, *names: str) -> bool:
        return rel in {f"{work}/{n}" for n in names}

    def under_work(rel: str) -> bool:
        return rel == work or rel.startswith(work + "/")

    def test_writer(doc: str) -> Callable[[str], bool]:
        def can_write(rel: str) -> bool:
            if under_work(rel):
                return in_work(rel, doc)
            return is_test_path(rel, cfg.extra_test_globs)

        return can_write

    domain = cfg.rel(cfg.domain_dir) if cfg.domain_dir else None

    def design_can_write(rel: str) -> bool:
        if domain and (rel == domain or rel.startswith(domain + "/")):
            return True
        return in_work(rel, DESIGN)

    def impl_can_write(rel: str) -> bool:
        if under_work(rel):
            return in_work(rel, IMPLEMENTATION)
        if domain and (rel == domain or rel.startswith(domain + "/")):
            return False
        return not is_test_path(rel, cfg.extra_test_globs)

    design_hint = f"{work}/{DESIGN}" + (f" と {domain}/ のドメイン文書" if domain else "")

    specs = {
        "requirements": StageSpec(
            name="requirements",
            label=STAGE_LABELS["requirements"],
            output=REQUIREMENTS,
            review=True,
            max_turns=DEFAULT_MAX_TURNS["requirements"],
            allowed_tools=READ_TOOLS + EDIT_TOOLS,
            disallowed_tools=["Bash"] + NO_WEB + NO_SHELL_BYPASS,
            allow_bash=False,
            can_write=lambda rel: in_work(rel, REQUIREMENTS),
            write_scope_hint=f"{work}/{REQUIREMENTS}",
            system_append=_prompt_text("requirements"),
        ),
        "design": StageSpec(
            name="design",
            label=STAGE_LABELS["design"],
            output=DESIGN,
            review=True,
            max_turns=DEFAULT_MAX_TURNS["design"],
            allowed_tools=READ_TOOLS + EDIT_TOOLS,
            disallowed_tools=["Bash"] + NO_WEB + NO_SHELL_BYPASS,
            allow_bash=False,
            can_write=design_can_write,
            write_scope_hint=design_hint,
            system_append=_prompt_text("design"),
        ),
        "red": StageSpec(
            name="red",
            label=STAGE_LABELS["red"],
            output=RED,
            review=True,
            max_turns=DEFAULT_MAX_TURNS["red"],
            allowed_tools=READ_TOOLS + EDIT_TOOLS + ["Bash"],
            disallowed_tools=NO_WEB + NO_SHELL_BYPASS,
            allow_bash=True,
            can_write=test_writer(RED),
            write_scope_hint=f"テストファイルと {work}/{RED}",
            system_append=_prompt_text("red"),
            output_format={"type": "json_schema", "schema": RED_RESULT_SCHEMA},
        ),
        "implement": StageSpec(
            name="implement",
            label=STAGE_LABELS["implement"],
            output=IMPLEMENTATION,
            max_turns=DEFAULT_MAX_TURNS["implement"],
            allowed_tools=READ_TOOLS + EDIT_TOOLS + ["Bash"],
            disallowed_tools=NO_WEB + NO_SHELL_BYPASS,
            allow_bash=True,
            can_write=impl_can_write,
            write_scope_hint=f"製品コードと {work}/{IMPLEMENTATION}（テストファイルは除く）",
            system_append=_prompt_text("implement"),
        ),
        "test": StageSpec(
            name="test",
            label=STAGE_LABELS["test"],
            output=TEST_REPORT,
            max_turns=DEFAULT_MAX_TURNS["test"],
            allowed_tools=READ_TOOLS + EDIT_TOOLS + ["Bash"],
            disallowed_tools=NO_WEB + NO_SHELL_BYPASS,
            allow_bash=True,
            can_write=test_writer(TEST_REPORT),
            write_scope_hint=f"テストファイルと {work}/{TEST_REPORT}",
            system_append=_prompt_text("test"),
            output_format={"type": "json_schema", "schema": TEST_VERDICT_SCHEMA},
        ),
    }
    return protect(specs, cfg)


# ---- 各段への依頼文 -------------------------------------------------------


def _files(cfg: Config) -> dict[str, str]:
    w = cfg.rel(cfg.work_dir)
    return {
        "input": f"{w}/{INPUT}",
        "req": f"{w}/{REQUIREMENTS}",
        "design": f"{w}/{DESIGN}",
        "red": f"{w}/{RED}",
        "impl": f"{w}/{IMPLEMENTATION}",
        "test": f"{w}/{TEST_REPORT}",
    }


def _domain_note(cfg: Config, *, writable: bool) -> str:
    if not cfg.domain_dir:
        return ""
    d = cfg.rel(cfg.domain_dir)
    if writable:
        return (
            f"\nドメインの文書（用語集・コンテキストの地図）は `{d}/` にあります。先に読み、設計で使う言葉をそろえてください。"
            f"\n新しい用語や、コンテキストの境界の変更があれば、`{d}/` の文書も更新してください。"
        )
    return f"\nドメインの文書（用語集・コンテキストの地図）は `{d}/` にあります。先に読み、そこにある言葉で書いてください。"


def requirements_prompt(cfg: Config) -> str:
    f = _files(cfg)
    return (
        f"要件メモ `{f['input']}` を読み、要件定義書を `{f['req']}` に書いてください。\n"
        "必要なら既存のコードやドキュメントを読んで、現状との食い違いがないか確かめてください。"
        + _domain_note(cfg, writable=False)
    )


def design_prompt(cfg: Config) -> str:
    f = _files(cfg)
    return (
        f"要件定義書 `{f['req']}` を読み、既存のコードを調べたうえで、設計書を `{f['design']}` に書いてください。"
        + _domain_note(cfg, writable=True)
    )


def red_prompt(cfg: Config) -> str:
    f = _files(cfg)
    return (
        f"要件定義書 `{f['req']}` の受け入れ基準ごとに、設計書 `{f['design']}` のテスト方針に沿って、"
        "製品コードより先にテストを書いてください。\n"
        f"テストを実行して、まだ実装がないために落ちる（赤になる）ことを確かめ、記録を `{f['red']}` に書き、"
        "最後に結果を構造化出力で返してください。"
    )


def red_missing_prompt(cfg: Config, missing: list[str]) -> str:
    f = _files(cfg)
    return (
        f"次の受け入れ基準に対応するテストがありません: {', '.join(missing)}\n"
        f"これらのテストを書き足して実行し、`{f['red']}` を更新してから、結果をもう一度構造化出力で返してください。"
    )


def implement_prompt(cfg: Config, attempt: int, failure_note: str | None) -> str:
    f = _files(cfg)
    if attempt == 1 or not failure_note:
        return (
            f"テスト先行の段で書かれたテスト（記録は `{f['red']}`）が通るように、"
            f"設計書 `{f['design']}` に沿って実装してください（要件は `{f['req']}`）。\n"
            "まず通る最小の実装を書き、テストが通ったまま設計に沿って整理（リファクタリング）してください。\n"
            f"終わったら `{f['impl']}` に「実装 {attempt} 回目」の節を追記してください。"
        )
    return (
        f"テストで不合格が出たため、実装の {attempt} 回目です。\n"
        f"テスト報告 `{f['test']}` と下の要約を読み、製品コード側の原因を直してください。\n"
        f"終わったら `{f['impl']}` に「実装 {attempt} 回目」の節を追記してください。\n\n"
        f"## テスト結果の要約\n{failure_note}"
    )


def test_prompt(cfg: Config, attempt: int) -> str:
    f = _files(cfg)
    lines = [
        f"要件定義書 `{f['req']}` の受け入れ基準を、設計書 `{f['design']}` のテスト方針に沿って確かめてください。",
        f"先に書かれたテストの記録は `{f['red']}`、実装の記録は `{f['impl']}` です。",
        f"結果は `{f['test']}` に書き、最後に判定を構造化出力で返してください。",
    ]
    if attempt > 1:
        lines.append(
            f"これは {attempt} 回目のテストです。前回の報告を上書きし、"
            "実装の記録に「テストへの異議」があれば、その妥当性を判断してからテストを直すか判断してください。"
        )
    return "\n".join(lines)


def revise_prompt(cfg: Config, stage: str, feedback: str) -> str:
    f = _files(cfg)
    target = {"requirements": f["req"], "design": f["design"], "red": f["red"]}[stage]
    return (
        f"レビューで次の指摘がありました。指摘を反映して `{target}` を更新してください。\n"
        f"反映しなかった指摘があれば、その理由を文書の末尾「レビュー対応」に書いてください。\n\n"
        f"## 指摘\n{feedback}"
    )
