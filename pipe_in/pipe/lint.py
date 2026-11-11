"""パイプの定義の警告（D0038）。誤りではないが、流すと思いどおりに動かない形を知らせる。

check_pipe（誤りだけを返す）とは別にして、返り値は変えない。ファイルには書かず、
読むのは定義と段の指示文だけ。標準ライブラリと .definition と pipe_in.engine.spec の定数のほかは import しない。
D0084 で W7（docs_dir・writes が既定で守る場所と重なる）を足した。
D0053 で W6（指摘を出す段に、引用の指示も findings-check も無い）を足した。
D0076 で W5 に例外を足した（検査の command が戻り先の段の成果物を名指しするときは出さない）。
"""

from __future__ import annotations

import fnmatch

from ..engine.spec import DEFAULT_PROTECTED_PATHS
from .definition import PipeDef

# W1 で「成果物のほかを書きたい」と見なす指示文の言葉。直すのはここ1か所
# （「描」は「描く」「描画」を拾うため広め。警告なので受け入れる。英語の指示文は拾えないものがある）
WRITE_WORDS = ("書き出", "書き込", "保存", "取り出", "置き場所", "下書き", "試作", "出力先", "mkdir", "ファイルを作", "描")

# W6 で「指摘を出す段」と見なす指示文の言葉（D0053）。指摘を直す・まとめる・読む側の言葉（「指摘を直」「指摘をまとめ」
# 「指摘を読」）と、判定の段が返す「problems」は入れない。「洗い出」は調べる段にも当たるので入れない（見逃しは受け入れる）
FINDING_WORDS = ("指摘にし", "指摘を出", "指摘を挙げ", "指摘を探", "findings")
# W6 で「引用を出させる指示」と見なす言葉
QUOTE_WORDS = ("引用", "逐語", "そのまま写", "quote")
# W6 で「機械の照合がある」と見なす check.command の文字
FINDINGS_CHECK = "findings-check"


def _prompt(stage) -> str:
    try:
        return stage.prompt_text()
    except (OSError, UnicodeDecodeError):
        return ""


def lint_pipe(pipe: PipeDef) -> list[str]:
    """警告の文を返す（空なら注意なし）。"""
    warnings: list[str] = []
    by_name = {s.name: s for s in pipe.stages}
    # W6 用：パイプのどれかの段（前・あと・同じ段のどれでもよい）が findings-check で照合しているか
    has_findings_check = any(
        s.check is not None and s.check.command and FINDINGS_CHECK in s.check.command for s in pipe.stages
    )
    for i, s in enumerate(pipe.stages, start=1):
        at = f"段 {i}（{s.name or '名前なし'}）: "
        # 指示文は W1 と W6 で使うので、要る段だけ1回読む（読めなければ空）
        text = _prompt(s) if s.access in ("read", "docs") else ""

        # W1: read + bash の段は、Bash でも成果物のほかは書けない
        if s.access == "read" and s.bash:
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
        # 例外（D0076-AC-23）: 検査の command が戻り先の output（成果物のファイル名）を含むときは、
        # 戻り先の成果物そのものを確かめていて、書き直せば直せるので出さない
        if s.check is not None and s.check.on_fail and s.check.on_fail != s.name:
            target = by_name.get(s.check.on_fail)
            names_output = bool(
                target is not None and target.output and s.check.command and target.output in s.check.command
            )
            if target is not None and target.access == "read" and not names_output:
                warnings.append(
                    at + f"不合格の戻り先「{target.name}」は access = \"read\" で、成果物のほかは書けず、指摘を直せません。"
                    "直せる段（docs・tests・code）に戻してください"
                )

        # W6: 指摘を出す段なのに、引用の指示も機械の照合（findings-check）も無い
        if (
            not has_findings_check
            and s.access in ("read", "docs")
            and any(w in text for w in FINDING_WORDS)
            and not any(w in text for w in QUOTE_WORDS)
        ):
            warnings.append(
                at + "指摘を出す段なのに、指摘ごとに原文をそのまま引かせる指示（引用）も、機械の照合（findings-check）もありません（D0053）。"
                "指摘ごとに原文の行を逐語で引用させ、pipe-in-gen findings-check（指摘の形 v1）を check.command に組んでください。ほかの照合を使うなら、指示文に引用の指示を書けば、この警告は出ません"
            )
        # W7: docs_dir・writes が、既定で守る場所と重なる（D0084）。重なった部分は書けない
        if s.access in ("docs", "code") and (_docs_dir_overlaps(s.docs_dir) or any(_glob_overlaps(w) for w in s.writes or [])):
            warnings.append(
                at + "docs_dir / writes は、既定で守る場所（.claude/・.git/・.pipe-in/・.mcp.json・pipeline.toml・前の版の置き場所）と重なります。"
                "重なった部分は書けません（D0084）。成果物は docs/ など別の場所に置いてください"
            )
    return warnings


def _docs_dir_overlaps(docs_dir: str | None) -> bool:
    """docs_dir が、プロジェクトそのものか、既定で守る場所の中か（文字の上だけで見る）。"""
    if docs_dir is None:
        return False
    d = docs_dir.strip().replace("\\", "/")
    while d.startswith("./"):
        d = d[2:]
    d = d.rstrip("/")
    return d in ("", ".") or _hits_default(d) or _hits_default(d + "/x")


def _glob_overlaps(glob: str) -> bool:
    """writes の glob の、最初のワイルドカードより前の固定の部分が、既定で守る場所の中か。
    固定の部分が空（*.md のように先頭がワイルドカード）は広すぎるので見ない。重なった部分は実行時に止まる。"""
    g = glob.strip().replace("\\", "/")
    while g.startswith("./"):
        g = g[2:]
    cut = len(g)
    for ch in "*?[":
        i = g.find(ch)
        if i != -1:
            cut = min(cut, i)
    prefix = g[:cut]
    if not prefix:
        return False
    return _hits_default(prefix) or _hits_default(prefix.rstrip("/") + "/x")


def _hits_default(path: str) -> bool:
    return any(fnmatch.fnmatch(path, g) for g in DEFAULT_PROTECTED_PATHS)
