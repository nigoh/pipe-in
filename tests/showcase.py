"""画面用の見本の記録（tests/fixtures/showcase/）を作る部品と台本。

README の画像と、拡張の確認用のページ（vscode/scripts/previewPages.ts）がこの見本を読む。
本物の開発フロー（DevPipeline）を、段の代わりに成果物とログを書く runner で流して作る。SDK は呼ばない。

- 台本：要件定義で修正の依頼が1回 → 承認、設計 → 承認、テスト先行（赤）→ 承認、
  実装（1 回目）→ 検証（1 回目）不合格 → 実装（2 回目）→ 検証（2 回目）合格。
- 使用量の数字は見本（段ごとに決めた表から入れる）。session_id はどこも null。
- 時計は決まった時刻から少しずつ進むものに差し替え、終わったら戻す（開始の時刻が毎回同じになる）。

作り直す：python tests/showcase.py（本体の記録の形が変わったときだけ。tests/test_showcase.py が形のずれを知らせる）。
テストからは build_showcase(tmp_path) だけを使う（main() は呼ばない）。
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import json
import shutil
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipe_in.dev import specs as st  # noqa: E402
from pipe_in.dev.pipeline import DevPipeline  # noqa: E402
from pipe_in.engine import pipeline as engine_pipeline  # noqa: E402
from pipe_in.engine.checkpoint import Decision  # noqa: E402
from pipe_in.engine.config import load_config  # noqa: E402
from pipe_in.engine.pipeline import Exit  # noqa: E402
from pipe_in.engine.runner import StageRun  # noqa: E402
from pipe_in.usage.metrics import StageMetrics  # noqa: E402

MEMO = "ユーザー一覧に CSV 出力ボタンを追加したい"
FIXTURE = Path(__file__).parent / "fixtures" / "showcase"

MODEL = "claude-opus-5-5"
CLAUDE_CODE_VERSION = "2.1.301"
START = datetime(2026, 10, 17, 10, 0, 0)
TICK = timedelta(seconds=45)
RESETS_AT = {"five_hour": 1792213200, "seven_day": 1792713600}  # 2026-10-17 05:00・2026-10-23 00:00（UTC）

# 確認での答え（要件定義で修正を1回依頼し、あとはすべて承認）
ANSWERS = [
    Decision("revise", "AC-02 を『文字コード』と『列の順』に分けて"),
    Decision("approve"),
    Decision("approve"),
    Decision("approve"),
]

# 段の呼び出し（ログの名前）ごとの数字：費用・ターン・秒・API 待ちのミリ秒・入力・キャッシュ書き込み・キャッシュ読み込み・出力・うち thinking・5時間枠・7日枠
USAGE: dict[str, dict[str, Any]] = {
    "01_requirements": dict(cost=0.21, turns=9, sec=48.0, api_ms=40100, input=24, cw=21800, cr=88400, out=3900, think=1100, five=0.04, seven=0.21),
    "02_requirements": dict(cost=0.09, turns=4, sec=21.0, api_ms=17300, input=8, cw=4100, cr=102600, out=1500, think=400, five=0.05, seven=0.21),
    "03_design": dict(cost=0.27, turns=12, sec=66.0, api_ms=55800, input=31, cw=26300, cr=141900, out=5200, think=1600, five=0.07, seven=0.22),
    "04_red": dict(cost=0.34, turns=18, sec=94.0, api_ms=71200, input=46, cw=29700, cr=233500, out=6100, think=1800, five=0.10, seven=0.22),
    "05_implement_1": dict(cost=0.41, turns=23, sec=121.0, api_ms=96400, input=58, cw=33200, cr=312800, out=7400, think=2100, five=0.13, seven=0.23),
    "06_test_1": dict(cost=0.18, turns=10, sec=57.0, api_ms=38900, input=27, cw=12600, cr=128300, out=2600, think=700, five=0.15, seven=0.23),
    "07_implement_2": dict(cost=0.29, turns=14, sec=78.0, api_ms=61700, input=39, cw=18400, cr=226100, out=4300, think=1300, five=0.17, seven=0.24),
    "08_test_2": dict(cost=0.16, turns=9, sec=52.0, api_ms=35200, input=22, cw=10900, cr=119700, out=2300, think=600, five=0.19, seven=0.24),
}


def _text(text: str) -> dict[str, Any]:
    return {"text": text}


def _tool(log_name: str, n: int, name: str, **tool_input: Any) -> dict[str, Any]:
    return {"id": f"toolu_showcase_{log_name}_{n}", "name": name, "input": tool_input}


# 段の呼び出しごとの、発言の部品（文と道具の呼び出し）。道具の入力のパスはプロジェクトからの相対パス
def _parts(log_name: str) -> list[dict[str, Any]]:
    t = lambda n, name, **kw: _tool(log_name, n, name, **kw)  # noqa: E731
    return {
        "01_requirements": [
            _text("要件メモと、ユーザー一覧の画面のコードを読みます。"),
            t(1, "Read", file_path="src/users/views.py"),
            t(2, "Grep", pattern="def user_list", path="src/users"),
            t(3, "Write", file_path="docs/pipeline/01_requirements.md"),
        ],
        "02_requirements": [
            _text("AC-02 を文字コードと列の順の2つに分けます。"),
            t(1, "Edit", file_path="docs/pipeline/01_requirements.md"),
        ],
        "03_design": [
            _text("一覧の画面と、表の列の定義を読みます。"),
            t(1, "Read", file_path="src/users/views.py"),
            t(2, "Read", file_path="templates/users/list.html"),
            t(3, "Write", file_path="docs/pipeline/02_design.md"),
        ],
        "04_red": [
            t(1, "Write", file_path="tests/test_users_export.py"),
            t(2, "Bash", command="pytest -q tests/test_users_export.py"),
            _text("3 件とも、出力の関数がまだ無いため落ちることを確かめました。"),
            t(3, "Write", file_path="docs/pipeline/03_red_tests.md"),
        ],
        "05_implement_1": [
            t(1, "Write", file_path="src/users/export.py"),
            t(2, "Edit", file_path="src/users/views.py"),
            t(3, "Edit", file_path="templates/users/list.html"),
            t(4, "Bash", command="pytest -q"),
        ],
        "06_test_1": [
            t(1, "Bash", command="pytest -q"),
            t(2, "Read", file_path="src/users/export.py"),
            _text("AC-02 が不合格です。出力の先頭に BOM が無く、Excel で開くと文字化けします。"),
            t(3, "Write", file_path="docs/pipeline/05_test_report.md"),
        ],
        "07_implement_2": [
            _text("検証の指摘（AC-02）を直します。出力の先頭に BOM を付けます。"),
            t(1, "Edit", file_path="src/users/export.py"),
            t(2, "Bash", command="pytest -q"),
        ],
        "08_test_2": [
            t(1, "Bash", command="pytest -q"),
            t(2, "Write", file_path="docs/pipeline/05_test_report.md"),
            _text("AC-01〜AC-03 はすべて合格です。"),
        ],
    }[log_name]


RESULTS = {
    "01_requirements": "要件定義書を書きました（AC-01〜AC-02）",
    "02_requirements": "AC-02 を分けて、AC-01〜AC-03 にしました",
    "03_design": "設計書を書きました（出力の関数・ボタン・テストの置き場所）",
    "04_red": "AC-01〜AC-03 のテストを書き、落ちることを確かめました",
    "05_implement_1": "CSV の出力とボタンを作りました",
    "06_test_1": "AC-02 が不合格（BOM が無い）",
    "07_implement_2": "出力の先頭に BOM を付けました",
    "08_test_2": "AC-01〜AC-03 すべて合格",
}

REQUIREMENTS_V1 = """# 要件定義：ユーザー一覧の CSV 出力

## 目的

ユーザー一覧に表示している内容を、表計算ソフトで開ける CSV で取り出せるようにする。

## 受け入れ基準

- **AC-01**：ユーザー一覧に「CSV 出力」ボタンがあり、押すと表示中の一覧（絞り込みを含む）が CSV で落ちてくる。
- **AC-02**：CSV は Excel でそのまま開けて、列は画面の表と同じ順に並ぶ。
"""

REQUIREMENTS_V2 = """# 要件定義：ユーザー一覧の CSV 出力

## 目的

ユーザー一覧に表示している内容を、表計算ソフトで開ける CSV で取り出せるようにする。

## 受け入れ基準

- **AC-01**：ユーザー一覧に「CSV 出力」ボタンがあり、押すと表示中の一覧（絞り込みを含む）が CSV で落ちてくる。
- **AC-02**：文字コードは UTF-8（BOM 付き）で、Excel でそのまま開いても文字化けしない。
- **AC-03**：列の順は画面の表と同じ（名前・メール・部署・登録日）。
"""

DESIGN = """# 設計：ユーザー一覧の CSV 出力

## 置き場所

| 置くもの | 場所 |
| --- | --- |
| CSV を組み立てる関数 `export_users_csv(users)` | `src/users/export.py` |
| 出力の入口（一覧と同じ絞り込みを使う） | `src/users/views.py` |
| ボタン | `templates/users/list.html` |

## AC とテストの対応

| AC | テスト |
| --- | --- |
| AC-01 | `tests/test_users_export.py::test_ac01_button_downloads_csv` |
| AC-02 | `tests/test_users_export.py::test_ac02_utf8_with_bom` |
| AC-03 | `tests/test_users_export.py::test_ac03_column_order` |
"""

RED = """# テスト先行の記録

| AC | テスト | 落ちた理由 |
| --- | --- | --- |
| AC-01 | `test_ac01_button_downloads_csv` | 出力の入口がまだ無い（404） |
| AC-02 | `test_ac02_utf8_with_bom` | `export_users_csv` がまだ無い |
| AC-03 | `test_ac03_column_order` | `export_users_csv` がまだ無い |

流したコマンド：`pytest -q tests/test_users_export.py`（3 failed）
"""

IMPLEMENTATION_1 = """# 実装の記録

## 1 回目

- `src/users/export.py` に `export_users_csv` を足した。
- 一覧と同じ絞り込みで出力する入口と、「CSV 出力」ボタンを足した。
"""

IMPLEMENTATION_2 = """
## 2 回目

- 検証の指摘（AC-02）を受けて、出力の先頭に BOM を付けた。
"""

TEST_REPORT_1 = """# 検証報告（1 回目）

| AC | 結果 | 内容 |
| --- | --- | --- |
| AC-01 | 合格 | ボタンから CSV が落ちてくる |
| AC-02 | 不合格 | 出力の先頭に BOM が無く、Excel で開くと文字化けする |
| AC-03 | 合格 | 列の順が画面の表と同じ |
"""

TEST_REPORT_2 = """# 検証報告（2 回目）

| AC | 結果 | 内容 |
| --- | --- | --- |
| AC-01 | 合格 | ボタンから CSV が落ちてくる |
| AC-02 | 合格 | BOM 付きの UTF-8 で、Excel で開いても文字化けしない |
| AC-03 | 合格 | 列の順が画面の表と同じ |

流したコマンド：`pytest -q`（12 passed）
"""

RED_RESULT = {
    "status": "red",
    "summary": "AC-01〜AC-03 の 3 件とも、出力の関数がまだ無いため落ちる",
    "tests": [
        {"criterion": "AC-01", "test": "tests/test_users_export.py::test_ac01_button_downloads_csv"},
        {"criterion": "AC-02", "test": "tests/test_users_export.py::test_ac02_utf8_with_bom"},
        {"criterion": "AC-03", "test": "tests/test_users_export.py::test_ac03_column_order"},
    ],
    "commands": ["pytest -q tests/test_users_export.py"],
}

VERDICTS = {
    "06_test_1": {
        "status": "fail",
        "summary": "AC-02 が不合格（BOM が無い）",
        "failures": [{"criterion": "AC-02", "detail": "出力の先頭に BOM が無く、Excel で開くと文字化けする"}],
        "commands": ["pytest -q"],
    },
    "08_test_2": {
        "status": "pass",
        "summary": "AC-01〜AC-03 すべて合格",
        "failures": [],
        "commands": ["pytest -q"],
    },
}


def _write_artifact(work: Path, log_name: str) -> None:
    if log_name == "01_requirements":
        (work / st.REQUIREMENTS).write_text(REQUIREMENTS_V1, encoding="utf-8")
    elif log_name == "02_requirements":
        (work / st.REQUIREMENTS).write_text(REQUIREMENTS_V2, encoding="utf-8")
    elif log_name == "03_design":
        (work / st.DESIGN).write_text(DESIGN, encoding="utf-8")
    elif log_name == "04_red":
        (work / st.RED).write_text(RED, encoding="utf-8")
    elif log_name == "05_implement_1":
        (work / st.IMPLEMENTATION).write_text(IMPLEMENTATION_1, encoding="utf-8")
    elif log_name == "07_implement_2":
        with (work / st.IMPLEMENTATION).open("a", encoding="utf-8") as f:
            f.write(IMPLEMENTATION_2)
    elif log_name == "06_test_1":
        (work / st.TEST_REPORT).write_text(TEST_REPORT_1, encoding="utf-8")
    elif log_name == "08_test_2":
        (work / st.TEST_REPORT).write_text(TEST_REPORT_2, encoding="utf-8")


def _messages(log_name: str, structured: Any) -> list[dict[str, Any]]:
    """SDK のメッセージを dict にしたもの（run_stage_sdk がログに書く形）。_type は最後に付く。"""
    u = USAGE[log_name]
    return [
        {
            "subtype": "init",
            "data": {
                "type": "system",
                "subtype": "init",
                "model": MODEL,
                "claude_code_version": CLAUDE_CODE_VERSION,
                "apiKeySource": "none",
                "permissionMode": "default",
            },
            "_type": "SystemMessage",
        },
        *(
            {"content": [part], "model": MODEL, "parent_tool_use_id": None, "_type": "AssistantMessage"}
            for part in _parts(log_name)
        ),
        {
            "rate_limit_info": {
                "raw": {
                    "unifiedWindows": {
                        "five_hour": {"utilization": u["five"], "resetsAt": RESETS_AT["five_hour"]},
                        "seven_day": {"utilization": u["seven"], "resetsAt": RESETS_AT["seven_day"]},
                    }
                },
            },
            "_type": "RateLimitEvent",
        },
        {
            "subtype": "success",
            "duration_ms": int(u["sec"] * 1000),
            "duration_api_ms": u["api_ms"],
            "is_error": False,
            "num_turns": u["turns"],
            "session_id": None,
            "total_cost_usd": u["cost"],
            "usage": {
                "input_tokens": u["input"],
                "cache_creation_input_tokens": u["cw"],
                "cache_read_input_tokens": u["cr"],
                "output_tokens": u["out"],
                "output_tokens_details": {"thinking_tokens": u["think"]},
            },
            "model_usage": {
                MODEL: {
                    "inputTokens": u["input"],
                    "cacheCreationInputTokens": u["cw"],
                    "cacheReadInputTokens": u["cr"],
                    "outputTokens": u["out"],
                    "thinkingTokens": u["think"],
                    "costUSD": u["cost"],
                    "costBasis": "list",
                }
            },
            "result": RESULTS[log_name],
            "structured_output": structured,
            "_type": "ResultMessage",
        },
    ]


class ShowcaseRunner:
    """段の代わりに成果物とログを書き、決めた数字の使用量を返す（runner の口：tests/test_pipeline.py の FakeRunner と同じ）。"""

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def __call__(self, spec, prompt, cfg, *, resume, log_name) -> StageRun:
        if log_name not in USAGE:
            raise RuntimeError(f"台本に無い段の呼び出しです: {log_name}（台本か本体の流れが変わった）")
        self.calls.append(log_name)
        work = cfg.work_dir
        _write_artifact(work, log_name)
        structured: Any = None
        if spec.name == "red":
            structured = RED_RESULT
        elif spec.name == "test":
            structured = VERDICTS[log_name]
        messages = _messages(log_name, structured)

        log_dir = work / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        metrics = StageMetrics()
        with (log_dir / f"{log_name}.jsonl").open("a", encoding="utf-8") as log:
            log.write(json.dumps({"_type": "Prompt", "stage": spec.name, "resume": resume, "prompt": prompt}, ensure_ascii=False) + "\n")
            for msg in messages:
                line = json.dumps(msg, ensure_ascii=False)
                log.write(line + "\n")
                metrics.feed(json.loads(line))  # run_stage_sdk と同じく、ログと同じ形から集める

        u = USAGE[log_name]
        return StageRun(
            stage=spec.name,
            session_id=None,
            subtype="success",
            result=RESULTS[log_name],
            structured=structured,
            cost_usd=u["cost"],
            num_turns=u["turns"],
            duration_sec=u["sec"],
            metrics=metrics,
        )


def _ticking_clock() -> type[datetime]:
    """呼ぶたびに START から TICK ずつ進む now() を持つ datetime（本体の pipeline の datetime と差し替える）。"""
    state = {"t": START}

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):  # noqa: ANN001
            current = state["t"]
            state["t"] = current + TICK
            return current

    return Clock


def build_showcase(project: Path) -> Path:
    """project の中で台本どおりに開発フローを流し、work_dir（project/docs/pipeline）を返す。"""
    project.mkdir(parents=True, exist_ok=True)
    cfg = load_config(project, None, auto_approve=False)
    answers = iter(ANSWERS)
    original = engine_pipeline.datetime
    engine_pipeline.datetime = _ticking_clock()
    try:
        pipeline = DevPipeline(cfg, runner=ShowcaseRunner(), ask=lambda stage, doc: next(answers))
        result = asyncio.run(pipeline.run(MEMO))
    finally:
        engine_pipeline.datetime = original
    if result != Exit.PASSED:
        raise RuntimeError(f"見本の台本が最後まで流れませんでした（{result.name}）")
    return cfg.work_dir


def shape(value: Any) -> Any:
    """形：dict はキーごとの形、list は要素ごとの形（長さも含む）、ほかは型の名前。値そのものは見ない。"""
    if isinstance(value, dict):
        return {k: shape(v) for k, v in value.items()}
    if isinstance(value, list):
        return [shape(v) for v in value]
    return type(value).__name__


def main() -> None:
    """tests/fixtures/showcase/ を作り直す（一時フォルダで流して写す。前の中身は消す）。"""
    with tempfile.TemporaryDirectory() as tmp:
        with contextlib.redirect_stdout(io.StringIO()):
            work = build_showcase(Path(tmp) / "myapp")
        if FIXTURE.exists():
            shutil.rmtree(FIXTURE)
        shutil.copytree(work, FIXTURE)
    print(f"{FIXTURE.relative_to(ROOT).as_posix()}/ を作り直しました")


if __name__ == "__main__":
    main()
