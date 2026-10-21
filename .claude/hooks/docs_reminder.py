"""メインエージェントが止まる（Stop）たびに呼ぶフック：コードを変えたのに文書が変わっていなければ、1回だけ知らせる（D0020）。

.claude/settings.json の Stop から呼ぶ。作業フォルダの git status（まだコミットしていない変更と新しいファイル）を見て、
コード（pipe_in/・generator/・vscode/src/・plugin/・.claude/ の定義など）が変わっていて、文書（README.md・docs/guide/・
docs/development/・決定の記録・/pipe-help など）が1つも変わっていないときだけ、止まるのを1回とめて理由を返す。
- 同じコードの変更の組では1回だけ（目印はリポジトリの外の一時フォルダに置く）。知らせのあとの止まり（stop_hook_active）でも出さない
- テスト・記録（docs/pipeline/）・lock のファイルは数えない
- git が読めない・入力が読めないときは何もしない（知らせのために人の作業を止めない）
- 公式の Stop フックには、続けさせる block が続いたときに打ち切る上限もあるが、このフックは1回しか出さないので届かない
道具を呼ぶたびではないが、止まるたびに動くので、標準ライブラリだけを使う。
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

# 変えたら文書をそろえる元になるもの
CODE_DIRS = ("pipe_in/", "generator/", "vscode/src/", "vscode/scripts/", "plugin/", ".claude-plugin/", ".claude/")
CODE_FILES = ("pyproject.toml", "vscode/package.json")
# そろえる先の文書（docs/development/workflow.md の「4. そろえる」の表）
DOC_FILES = ("README.md", "CLAUDE.md", "vscode/README.md", "pipes/README.md", "docs/assets/README.md", ".claude/skills/pipe-help/SKILL.md")
DOC_DIRS = ("docs/guide/", "docs/development/", "docs/decisions/")
# 知らせに並べるファイルの数
SHOWN = 10


def classify(rel: str) -> str | None:
    """'code'（文書をそろえる元）・'doc'（文書）・None（テスト・記録など、どちらでもない）。"""
    if rel in DOC_FILES or rel.startswith(DOC_DIRS):
        return "doc"
    if rel.startswith("vscode/src/test/") or rel.endswith(".test.ts"):
        return None
    if rel in CODE_FILES or rel.startswith(CODE_DIRS):
        return "code"
    return None


def parse_porcelain(out: str) -> list[str]:
    """git status --porcelain -z の出力 → 変わったパス（名前を変えたものは新しいほう）。"""
    parts = out.split("\0")
    paths: list[str] = []
    i = 0
    while i < len(parts):
        entry = parts[i]
        i += 1
        if len(entry) < 4:
            continue
        paths.append(entry[3:])
        if entry[0] in "RC":
            i += 1  # 次の項目は元の名前
    return paths


def decide(changed: list[str], *, stop_hook_active: bool, seen: str | None) -> tuple[str | None, str | None]:
    """（知らせる理由, この変更の組の目印）。知らせないときの理由は None。"""
    code = sorted({p for p in changed if classify(p) == "code"})
    if not code or any(classify(p) == "doc" for p in changed):
        return None, None
    mark = hashlib.sha256("\n".join(code).encode("utf-8")).hexdigest()
    if stop_hook_active or mark == seen:
        return None, mark
    shown = "・".join(code[:SHOWN]) + (f" ほか {len(code) - SHOWN} 件" if len(code) > SHOWN else "")
    reason = (
        f"コードや定義を変えましたが、文書が1つも変わっていません（{shown}）。"
        "docs/development/workflow.md の「4. そろえる」の表で、直す文書（README.md・docs/guide/・docs/development/・"
        "vscode/README.md・/pipe-help・CLAUDE.md・決定の記録）があるかを見てください。"
        "あれば /pipe-docs で文書係に任せるか、直してください。要らなければ、その理由を人に一言伝えて終えてください。"
        "この知らせは、同じ変更の組では1回だけ出ます。"
    )
    return reason, mark


def project_root(cwd: str, project_dir: str | None) -> str:
    """git の作業フォルダ（.git のあるいちばん近い上のフォルダ）。見つからなければ CLAUDE_PROJECT_DIR。"""
    here = os.path.normpath(os.path.abspath(cwd)) if cwd else ""
    while here:
        if os.path.exists(os.path.join(here, ".git")):
            return here
        parent = os.path.dirname(here)
        if parent == here:
            break
        here = parent
    return project_dir or cwd or os.getcwd()


def changed_files(root: str) -> list[str] | None:
    """まだコミットしていない変更と新しいファイル。git が読めなければ None。"""
    try:
        done = subprocess.run(
            ["git", "-C", root, "status", "--porcelain", "-z", "--untracked-files=all"],
            capture_output=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if done.returncode != 0:
        return None
    return parse_porcelain(done.stdout.decode("utf-8", errors="replace"))


def state_path(root: str) -> Path:
    """最後に知らせた変更の組の目印。リポジトリには書かず、一時フォルダに作業フォルダごとに置く。"""
    key = hashlib.sha256(os.path.normcase(os.path.abspath(root)).encode("utf-8")).hexdigest()[:16]
    return Path(tempfile.gettempdir()) / "pipe-in-docs-reminder" / f"{key}.txt"


def _read_seen(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def _write(text: str) -> None:
    # Claude Code は UTF-8 で読む。Windows の標準出力（cp932）のまま書くと文字化けするので、バイトで書く
    buffer = getattr(sys.stdout, "buffer", None)
    if buffer is not None:
        sys.stdout.flush()
        buffer.write(text.encode("utf-8"))
        buffer.flush()
    else:
        sys.stdout.write(text)


def main() -> int:
    """知らせるときだけ Stop の block の JSON を出す。終了コードはいつも 0。"""
    buffer = getattr(sys.stdin, "buffer", None)
    try:
        payload = json.loads(buffer.read().decode("utf-8") if buffer is not None else sys.stdin.read())
    except (ValueError, UnicodeDecodeError):
        return 0
    if not isinstance(payload, dict):
        return 0
    root = project_root(str(payload.get("cwd") or ""), os.environ.get("CLAUDE_PROJECT_DIR"))
    changed = changed_files(root)
    if changed is None:
        return 0
    state = state_path(root)
    reason, mark = decide(changed, stop_hook_active=bool(payload.get("stop_hook_active")), seen=_read_seen(state))
    if reason and mark:
        try:
            state.parent.mkdir(parents=True, exist_ok=True)
            state.write_text(mark, encoding="utf-8")
        except OSError:
            return 0  # 目印を残せないと毎回知らせてしまうので、知らせない
        _write(json.dumps({"decision": "block", "reason": reason}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
