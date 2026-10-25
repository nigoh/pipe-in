"""eval の見本づくり：build-shows-table-first。空のワークスペースに、要約したい Markdown の置き場がある対象プロジェクトを作る。

標準ライブラリだけ。コマンドは起こさない。pipe-in-gen が PATH に無い、または作業フォルダが空でないときは、書かずに 1 で終わる。
"""

from __future__ import annotations

# --- common ---
import shutil
import sys
from pathlib import Path

# 実物のプロジェクトに似た印（あれば書かずに断る）
REAL_TREE_MARKERS = (".git", "plugin", "docs/pipeline", "pipes", ".pipe-in")


def require_pipe_in_gen() -> None:
    """pipe-in-gen が PATH に無ければ、利用料を使う前に気づけるよう 1 で終わる（作りはしない）。"""
    if shutil.which("pipe-in-gen") is None:
        print("pipe-in-gen が PATH にありません。pipe-in のフォルダで pip install -e . をしてから流してください。", file=sys.stderr)
        sys.exit(1)


def refuse_real_tree(target: Path) -> None:
    """空でない、または実物に似た木には書かずに 1 で終わる。"""
    if not target.is_dir():
        print(f"作業フォルダがありません: {target}", file=sys.stderr)
        sys.exit(1)
    if any(target.iterdir()) or any((target / m).exists() for m in REAL_TREE_MARKERS):
        print("作業フォルダが空ではありません。空のワークスペースで流してください。", file=sys.stderr)
        sys.exit(1)


def write(target: Path, rel: str, text: str) -> None:
    """target の中だけに書く。"""
    path = Path(rel)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"target の外には書けません: {rel}")
    dest = target / path
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    target = Path(argv[0]) if argv else Path.cwd()
    require_pipe_in_gen()
    refuse_real_tree(target)
    build(target)
    return 0
# --- /common ---


def build(target: Path) -> None:
    write(target, "README.md", "# メモ置き場\n\n日々のメモを notes/ に Markdown で置いている小さなプロジェクト。\n")
    write(target, "notes/a.md", "# 会議のメモ\n\n- 来週の予定を決めた\n- 担当を分けた\n")
    write(target, "notes/b.md", "# 読んだ本のメモ\n\n- 章ごとの要点を3行でまとめた\n- 気になった点に印をつけた\n")


if __name__ == "__main__":
    sys.exit(main())
