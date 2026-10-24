"""パイプの定義の警告（D0037）。誤りではないが、流すと思いどおりに動かない形を知らせる。

check_pipe（誤りだけを返す）とは別にして、返り値は変えない。ファイルには書かず、
読むのは定義と段の指示文だけ。標準ライブラリと .definition のほかは import しない。
"""

from __future__ import annotations

from .definition import PipeDef

# W1 で「成果物のほかを書きたい」と見なす指示文の言葉。直すのはここ1か所
# （「描」は「描く」「描画」を拾うため広め。警告なので受け入れる。英語の指示文は拾えないものがある）
WRITE_WORDS = ("書き出", "書き込", "保存", "取り出", "置き場所", "下書き", "試作", "出力先", "mkdir", "ファイルを作", "描")


def _prompt(stage) -> str:
    try:
        return stage.prompt_text()
    except (OSError, UnicodeDecodeError):
        return ""


def lint_pipe(pipe: PipeDef) -> list[str]:
    """警告の文を返す（空なら注意なし）。"""
    warnings: list[str] = []
    by_name = {s.name: s for s in pipe.stages}
    for i, s in enumerate(pipe.stages, start=1):
        at = f"段 {i}（{s.name or '名前なし'}）: "

        # W1: read + bash の段は、Bash でも成果物のほかは書けない
        if s.access == "read" and s.bash:
            text = _prompt(s)
            if any(w in text for w in WRITE_WORDS):
                warnings.append(
                    at + 'access = "read" で bash = true の段は、Bash でも成果物のほかは書けません（D0036）。'
                    '試作・図・下書きなどを置くなら、access = "docs" と docs_dir にしてください'
                )

        # W3: テストを書く段に bash が無く、後ろの段の check.command と同じ検査を流せない
        if s.access == "tests" and not s.bash:
            later = next((t for t in pipe.stages[i:] if t.check is not None and t.check.command), None)
            if later is not None:
                warnings.append(
                    at + f"テストを書く段で bash が使えず、後ろの段「{later.name}」の check.command と同じ検査を、この段で流せません。"
                    "bash = true にして、書いたテストを同じ検査で流させてください"
                )

        # W5: 不合格の戻り先が read の段だと、指摘を直せない
        if s.check is not None and s.check.on_fail and s.check.on_fail != s.name:
            target = by_name.get(s.check.on_fail)
            if target is not None and target.access == "read":
                warnings.append(
                    at + f"不合格の戻り先「{target.name}」は access = \"read\" で、成果物のほかは書けず、指摘を直せません。"
                    "直せる段（docs・tests・code）に戻してください"
                )
    return warnings
