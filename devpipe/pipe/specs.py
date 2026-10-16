"""パイプの段の設定：権限の型（read / docs / tests / code）から書き込める範囲を作り、段への指示文を組み立てる。"""

from __future__ import annotations

from collections.abc import Callable
from importlib import resources

from ..engine.config import Config
from ..engine.guard import is_test_path
from ..engine.pipeline import INPUT
from ..engine.spec import EDIT_TOOLS, NO_SHELL_BYPASS, NO_WEB, READ_TOOLS, StageSpec, protect
from .definition import PipeDef, PipeStage

DEFAULT_MAX_TURNS = 100


def _stage_rules() -> str:
    return resources.files("devpipe.pipe").joinpath("stage_rules.md").read_text(encoding="utf-8")


def _can_write(cfg: Config, stage: PipeStage) -> tuple[Callable[[str], bool], str]:
    work = cfg.rel(cfg.work_dir)
    own = f"{work}/{stage.output}"

    def under_work(rel: str) -> bool:
        return rel == work or rel.startswith(work + "/")

    if stage.access == "docs":
        docs = cfg.rel((cfg.project_dir / (stage.docs_dir or "")).resolve())
        return (lambda rel: rel == own or rel == docs or rel.startswith(docs + "/")), f"{own} と {docs}/ の下"
    if stage.access == "tests":
        return (
            lambda rel: rel == own or (not under_work(rel) and is_test_path(rel, cfg.extra_test_globs))
        ), f"テストファイルと {own}"
    if stage.access == "code":
        return (
            lambda rel: rel == own or (not under_work(rel) and not is_test_path(rel, cfg.extra_test_globs))
        ), f"製品コードと {own}（テストファイルは除く）"
    return (lambda rel: rel == own), own


def _outside_pipe(can_write: Callable[[str], bool], cfg: Config, pipe: PipeDef) -> Callable[[str], bool]:
    """パイプのフォルダ（定義・指示文）は、どの段からも書き換えさせない（devpipe 自身を対象にしたときのため）。"""
    pipe_rel = cfg.rel(pipe.dir.resolve())

    def wrapped(rel: str) -> bool:
        return not (rel == pipe_rel or rel.startswith(pipe_rel + "/")) and can_write(rel)

    return wrapped


def build_pipe_specs(cfg: Config, pipe: PipeDef) -> dict[str, StageSpec]:
    rules = _stage_rules()
    specs: dict[str, StageSpec] = {}
    for s in pipe.stages:
        can_write, hint = _can_write(cfg, s)
        specs[s.name] = StageSpec(
            name=s.name,
            label=s.label,
            output=s.output,
            review=s.review,
            allowed_tools=READ_TOOLS + EDIT_TOOLS + (["Bash"] if s.bash else []),
            disallowed_tools=([] if s.bash else ["Bash"]) + NO_WEB + NO_SHELL_BYPASS,
            allow_bash=s.bash,
            can_write=_outside_pipe(can_write, cfg, pipe),
            write_scope_hint=hint,
            system_append=rules,
            model=s.model,
            max_turns=s.max_turns or DEFAULT_MAX_TURNS,
            max_budget_usd=s.max_budget_usd,
        )
    return protect(specs, cfg)


def stage_prompt(cfg: Config, pipe: PipeDef, index: int) -> str:
    w = cfg.rel(cfg.work_dir)
    stage = pipe.stages[index]
    given: list[str] = []
    if (cfg.work_dir / INPUT).is_file():
        given.append(f"- 依頼メモ: `{w}/{INPUT}`")
    given += [f"- {prev.label}の成果物: `{w}/{prev.output}`" for prev in pipe.stages[:index]]
    lines = [stage.prompt_text(), ""]
    if given:
        lines += ["## 渡すもの", "", "先に読んでください。", "", *given, ""]
    lines += ["## 書くもの", "", f"成果物を `{w}/{stage.output}` に書いてください。"]
    if stage.access == "docs" and stage.docs_dir:
        docs = cfg.rel((cfg.project_dir / stage.docs_dir).resolve())
        lines.append(f"図や文書のファイルは `{docs}/` の下に置き、成果物からリンクしてください。")
    return "\n".join(lines)


def revise_prompt(cfg: Config, pipe: PipeDef, stage: str, feedback: str) -> str:
    s = next(x for x in pipe.stages if x.name == stage)
    target = f"{cfg.rel(cfg.work_dir)}/{s.output}"
    return (
        f"確認で次の指摘がありました。指摘を反映して `{target}` を更新してください"
        "（この段で作ったほかのファイルも、必要なら直してください）。\n"
        "反映しなかった指摘があれば、その理由を成果物の末尾「レビュー対応」に書いてください。\n\n"
        f"## 指摘\n{feedback}"
    )
