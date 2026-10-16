"""パイプ（kind = "linear"）の流れ：段を定義の順に流し、review = true の段のあとで人の確認を取る。差し戻しはしない。"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from ..engine.checkpoint import Decision
from ..engine.config import Config
from ..engine.pipeline import INPUT, BasePipeline, Exit, ShellResult, run_shell
from ..engine.runner import StageRunner, run_stage_sdk
from . import specs as ps
from .definition import PipeDef


class LinearPipeline(BasePipeline):
    def __init__(
        self,
        cfg: Config,
        pipe: PipeDef,
        *,
        runner: StageRunner = run_stage_sdk,
        ask: Callable[[str, Path], Decision] | None = None,
        shell: Callable[[str, Path, int], ShellResult] = run_shell,
    ) -> None:
        super().__init__(cfg, ps.build_pipe_specs(cfg, pipe), runner=runner, ask=ask, shell=shell)
        self.pipe = pipe

    def _revise_prompt(self, stage: str, feedback: str) -> str:
        return ps.revise_prompt(self.cfg, self.pipe, stage, feedback)

    def _artifacts(self) -> list[tuple[str, str]]:
        return [(INPUT, "依頼メモ")] + [(s.output, s.label) for s in self.pipe.stages]

    async def run(self, input_text: str | None, from_stage: str | None = None) -> Exit:
        names = self.stage_order
        start_name = from_stage or names[0]
        if start_name not in names:
            raise SystemExit(f"--from には {', '.join(names)} のどれかを指定してください")
        start = names.index(start_name)
        if input_text is None and self.pipe.input == "required" and not self._doc_ready(INPUT):
            raise SystemExit(f"パイプ「{self.pipe.name}」には依頼メモが要ります。--input か --text で渡してください")
        missing = [self.cfg.rel(self.doc(s.output)) for s in self.pipe.stages[:start] if not self._doc_ready(s.output)]
        if missing:
            raise SystemExit(f"{self.labels[start_name]}から始めるには次のファイルが必要です: {', '.join(missing)}")
        self.cfg.work_dir.mkdir(parents=True, exist_ok=True)
        if input_text is not None:
            self.doc(INPUT).write_text(input_text.strip() + "\n", encoding="utf-8")
        return self._finish(await self._stages_from(start))

    async def _stages_from(self, start: int, *, first: tuple[str, str] | None = None) -> Exit:
        for i in range(start, len(self.pipe.stages)):
            s = self.pipe.stages[i]
            if first is not None and i == start:
                prompt, opts = first[0], {"resume": first[1], "note": "指摘を反映"}
            else:
                prompt, opts = ps.stage_prompt(self.cfg, self.pipe, i), {}
            result = await self._doc_stage(s.name, prompt, s.output, review=s.review, **opts)
            if result is not None:
                return result
        return Exit.PASSED
