"""eval の見本づくり：judge-rejects-bad-runs。空のワークスペースに、依頼（request.md）と、ほぼ沿っている報告（report.md）を作る。

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


REQUEST_MD = """# 依頼

社内の読書会の案内文を、3行以内で書いてください。

- 日時と場所を入れる
- やさしい言い方にする
"""

REPORT_MD = """# 読書会のご案内

来週の金曜日の午後3時から、会議室Aで読書会を開きます。
今回は短い本を1冊読み、感想を気軽に話し合います。
初めての方も、どうぞ気軽にいらしてください。
"""


def build(target: Path) -> None:
    write(target, "request.md", REQUEST_MD)
    write(target, "report.md", REPORT_MD)


if __name__ == "__main__":
    sys.exit(main())
