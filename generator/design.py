"""目的から段を組む（pipe-in-gen design）。

Claude に対象を読むだけで調べさせ、パイプの設計を構造化出力で返させる。ジェネレーターがそれを
pipe.toml・prompts/・README.md に書き、pipe_in.pipe の検査に通るまで（max_rounds 回まで）直させる。
検査に通らなければ、何も書かない。SDK の受信バッファの上限を超えたときは、やり直さずに止める。
"""

from __future__ import annotations

import asyncio
import json
import shutil
from importlib import resources
from pathlib import Path
from typing import Any

from pipe_in.engine.config import load_config
from pipe_in.engine.runner import BUFFER_OVERFLOW_SUBTYPE, StageRunner, run_stage_sdk
from pipe_in.engine.spec import EDIT_TOOLS, NO_SHELL_BYPASS, NO_WEB, READ_TOOLS, StageSpec
from pipe_in.pipe import definition as pd

from .cli import refuse_clash
from .detect import Env, detect

STAGE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "label": {"type": "string"},
        "output": {"type": "string"},
        "access": {"type": "string", "enum": list(pd.ACCESS)},
        "docs_dir": {"type": "string"},
        "writes": {"type": "array", "items": {"type": "string"}},
        "bash": {"type": "boolean"},
        "review": {"type": "boolean"},
        "prompt": {"type": "string"},
        "check": {
            "type": "object",
            "properties": {
                "verdict": {"type": "boolean"},
                "command": {"type": "string"},
                "on_fail": {"type": "string"},
                "max_retries": {"type": "integer"},
            },
        },
    },
    "required": ["name", "label", "output", "access", "prompt"],
}

DESIGN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "label": {"type": "string", "description": "パイプの短い名前（日本語）"},
        "description": {"type": "string", "description": "何をするパイプか（1文）"},
        "input": {"type": "string", "enum": list(pd.INPUT_MODES), "description": "依頼メモが要るか"},
        "stages": {"type": "array", "items": STAGE_SCHEMA},
    },
    "required": ["label", "input", "stages"],
}


def _rules() -> str:
    return resources.files("pipe_in_generator").joinpath("design_rules.md").read_text(encoding="utf-8")


def designer_spec(model: str | None = None) -> StageSpec:
    """設計の段：対象を読むだけで、何も書かない。"""
    return StageSpec(
        name="design",
        label="パイプの設計",
        allowed_tools=list(READ_TOOLS),
        disallowed_tools=["Bash", *EDIT_TOOLS, *NO_WEB, *NO_SHELL_BYPASS],
        allow_bash=False,
        can_write=lambda rel: False,
        write_scope_hint="（この段は何も書きません）",
        system_append=_rules(),
        output_format={"type": "json_schema", "schema": DESIGN_SCHEMA},
        model=model,
        max_turns=40,
    )


def _env_note(env: Env) -> str:
    return (
        f"- 言語: {', '.join(env.languages) or '不明'}\n"
        f"- テストのコマンド: {env.test_command or 'なし'}\n"
        f"- ソースの場所: {', '.join(env.source_dirs)}\n"
        f"- 文書の場所: {', '.join(env.docs_dirs) or 'なし'}"
    )


def _q(value: str) -> str:
    """TOML の文字列（JSON の文字列は TOML の基本文字列としても読める）。"""
    return json.dumps(value, ensure_ascii=False)


def render_pipe(name: str, purpose: str, design: dict[str, Any]) -> dict[str, str]:
    """設計から、パイプのフォルダのファイル（相対パス → 中身）を作る。"""
    files: dict[str, str] = {}
    lines = [
        "# pipe-in-gen design で作ったパイプ。段の並び・書き込める範囲・確認の有無はここで、各段への指示は prompts/ で決めます。",
        "",
        "[pipe]",
        'kind = "linear"',
        f"label = {_q(str(design.get('label', name)))}",
        f"description = {_q(str(design.get('description', '')))}",
        f"input = {_q(str(design.get('input', 'optional')))}",
    ]
    stages = design.get("stages") if isinstance(design.get("stages"), list) else []
    table_rows: list[str] = []
    for n, s in enumerate(s for s in stages if isinstance(s, dict)):
        sname = str(s.get("name", ""))
        prompt_rel = f"prompts/{n + 1:02d}_{sname or 'stage'}.md"
        files[prompt_rel] = str(s.get("prompt", "")).strip() + "\n"
        lines += [
            "",
            "[[stages]]",
            f"name = {_q(sname)}",
            f"label = {_q(str(s.get('label', sname)))}",
            f"output = {_q(str(s.get('output', '')))}",
            f"access = {_q(str(s.get('access', 'read')))}",
        ]
        if s.get("docs_dir"):
            lines.append(f"docs_dir = {_q(str(s['docs_dir']))}")
        if isinstance(s.get("writes"), list) and s["writes"]:
            lines.append("writes = [" + ", ".join(_q(str(g)) for g in s["writes"]) + "]")
        if s.get("bash") is True:
            lines.append("bash = true")
        if s.get("review") is True:
            lines.append("review = true")
        lines.append(f"prompt_file = {_q(prompt_rel)}")
        check = s.get("check")
        if isinstance(check, dict) and (check.get("verdict") or check.get("command")):
            lines.append("[stages.check]")
            if check.get("verdict") is True:
                lines.append("verdict = true")
            if check.get("command"):
                lines.append(f"command = {_q(str(check['command']))}")
            if check.get("on_fail"):
                lines.append(f"on_fail = {_q(str(check['on_fail']))}")
            if isinstance(check.get("max_retries"), int):
                lines.append(f"max_retries = {check['max_retries']}")
        scope = s.get("access", "read") + (f"（{s['docs_dir']}/）" if s.get("docs_dir") else "")
        table_rows.append(
            f"| {s.get('label', sname)} | `{s.get('output', '')}` | {scope} | {'あり' if s.get('review') else 'なし'} | "
            f"{'あり' if isinstance(check, dict) and (check.get('verdict') or check.get('command')) else 'なし'} |"
        )
    files[pd.PIPE_FILE] = "\n".join(lines) + "\n"
    need = ' --text "依頼メモ"' if design.get("input") == "required" else ""
    files["README.md"] = "\n".join(
        [
            f"# {pd.PREFIX}{name}：{design.get('label', name)}",
            "",
            str(design.get("description", "")),
            "",
            f"`pipe-in-gen design` で、次の目的から作ったパイプです：{purpose}",
            "",
            "## 段",
            "",
            "| 段 | 成果物 | 書き込める範囲 | 人の確認 | 検証 |",
            "|---|---|---|---|---|",
            *table_rows,
            "",
            "## 流し方",
            "",
            "```bash",
            f"pipe-in --pipe {name} --project <対象のフォルダ>{need}",
            "```",
            "",
            "## 直し方",
            "",
            "- 段の並び・書き込める範囲・確認と検証は `pipe.toml`、各段への指示は `prompts/` のファイルです。",
            f"- 直したら `pipe-in-gen check {name} --project <対象のフォルダ>` で確かめてください。",
            "",
        ]
    )
    return files


def _write(dest: Path, files: dict[str, str]) -> None:
    for rel, text in files.items():
        out = dest / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")


def _validate(name: str, purpose: str, data: Any, staging: Path, project: Path) -> list[str]:
    if not isinstance(data, dict):
        return ["設計が構造化出力で返りませんでした（label・input・stages を持つ形で返してください）"]
    if staging.exists():
        shutil.rmtree(staging)
    _write(staging, render_pipe(name, purpose, data))
    try:
        return pd.check_pipe(pd.load_pipe(staging), project)
    except pd.PipeError as e:
        return [str(e)]


async def _design(
    project: Path, name: str, purpose: str, dest: Path, runner: StageRunner, max_rounds: int, model: str | None
) -> int:
    cfg = load_config(project).for_pipe(f"design-{name}", own_work_dir=True)
    cfg.work_dir.mkdir(parents=True, exist_ok=True)
    spec = designer_spec(model)
    staging = dest.parent / ".design-staging" / dest.name
    prompt = (
        f"次の目的のための pipe-in のパイプを設計してください。\n\n## 目的\n{purpose}\n\n"
        f"## 対象プロジェクトの形（ファイルから推し量ったもの）\n{_env_note(detect(project))}\n"
    )
    resume: str | None = None
    try:
        for round_ in range(1, max_rounds + 1):
            print(f"\n▶ パイプの設計（{round_} 回目）", flush=True)
            run = await runner(spec, prompt, cfg, resume=resume, log_name=f"{round_:02d}_design")
            if run.is_error and run.subtype == BUFFER_OVERFLOW_SUBTYPE:
                # やり直しても同じものを読んで同じように超えるので、すぐに止める。作業用フォルダは finally で消える
                print("✗ 設計の段が SDK の受信バッファの上限を超えたため、やり直さずに止めます")
                for e in run.errors:
                    print(e)
                print("パイプは作りませんでした")
                return 1
            errors = ["設計の段が失敗しました"] if run.is_error else _validate(name, purpose, run.structured, staging, project)
            if not errors:
                if dest.exists():
                    shutil.rmtree(dest)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(staging), str(dest))
                print(f"✓ {dest} を作りました（設計 {round_} 回・${run.cost_usd:.3f}）")
                print(f"流す: pipe-in --pipe {name} --project <対象のフォルダ>")
                return 0
            print("  ✗ 設計に誤りがありました:")
            for e in errors:
                print(f"    - {e}")
            prompt = "設計に次の誤りがありました。直した設計を、全体をもう一度返してください。\n\n" + "\n".join(f"- {e}" for e in errors)
            resume = run.session_id or resume
        print(f"✗ {max_rounds} 回直しても検査に通らなかったため、パイプは作りませんでした")
        return 1
    finally:
        if staging.parent.exists():
            shutil.rmtree(staging.parent)


def design_pipe(
    project: Path,
    name: str,
    purpose: str,
    *,
    pipes_dir: Path | None = None,
    runner: StageRunner | None = None,
    force: bool = False,
    max_rounds: int = 3,
    model: str | None = None,
) -> int:
    if not pd.is_valid_name(name):
        print(f"✗ パイプの名前「{name}」は使えません（英小文字・数字・- だけ。logs・end は不可）")
        return 1
    if not purpose.strip():
        print("✗ 目的（--purpose）を書いてください")
        return 1
    # 置き場所は cli.main が決めて渡す。渡されなければ new と同じ決まり（new_pipes_dir）で決める
    dest = (pipes_dir or pd.new_pipes_dir(project)) / f"{pd.PREFIX}{name}"
    if refuse_clash(name, dest, project):
        return 1
    if dest.exists():
        if not force:
            print(f"✗ {dest} はもうあります。作り直すなら --force を付けてください")
            return 1
        if not (dest / pd.PIPE_FILE).is_file():
            print(f"✗ {dest} はパイプのフォルダではないため、作り直しません")
            return 1
    project = project.expanduser().resolve()
    return asyncio.run(_design(project, name, purpose, dest, runner or run_stage_sdk, max_rounds, model))
