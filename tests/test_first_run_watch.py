"""D0034（work_dir がまだ無いときの最初の実行でも、パネルとステータスバーが進む）の構造の検査。

拡張は work_dir を読むだけで書かない（D0034-AC-33）。新しい基盤層の部品（infra/fsPresence.ts）と app 層の部品（app/workDirWatch.ts）、
入口（extension.ts）に、書き込みの呼び出し（mkdir・writeFile・rm・rename ほか、tests/test_decision_ui.py の write_calls が見つける形）が無いことを、
ソースを文字として読んで確かめる。基盤層の確かめ（fsPresence.ts）は node:fs を直に import せず、読み取りの口 ./readOnlyFs.ts を通す。

既存の READ_ONLY_SOURCES（tests/test_decision_ui.py）の一覧は書き換えず、新しいファイル用の検査をここに足す。
リポジトリの実物は読むだけで、書かない。SDK は呼ばない。前の名前は、この文書に直接書かない（tests/test_rename.py の一覧に無いため）。
"""

from __future__ import annotations

import re

import pytest

from test_decision_ui import src_text, strip_ts_comments, write_calls

# 新しい部品と入口。ファイルが無ければ src_text が「無い」で落ちる（テスト先行のときは赤だった）。extension.ts はそのときから通っていた。
NEW_SOURCES = ["infra/fsPresence.ts", "app/workDirWatch.ts", "extension.ts"]

# node:fs（と node:fs/promises・前の書き方の fs）の読み込み。import・動的 import・require の形だけを見る（文字列の中の言葉は見ない）
NODE_FS_IMPORT = re.compile(r"""\b(?:from|import|require)\s*\(?\s*['"](?:node:)?fs(?:/promises)?['"]""")


def node_fs_imports(source: str) -> list[str]:
    """コメントを除いたソースにある、node:fs の読み込み。"""
    return [m.group(0) for m in NODE_FS_IMPORT.finditer(strip_ts_comments(source))]


# ---- AC-33：書き込みの呼び出しが無い ---------------------------------------------------------


@pytest.mark.parametrize("rel", NEW_SOURCES)
def test_D0034_AC_33_新しい部品と入口に書き込みの呼び出しが無い(rel):
    """D0034-AC-33: infra/fsPresence.ts・app/workDirWatch.ts・extension.ts に、書き込みの呼び出しが無い（work_dir・.git・別の worktree に書かない。
    空の docs/pipeline/ も作らない）。ファイルが無ければ、ファイルが無いことで落ちる（テスト先行のときは赤だった）。extension.ts はそのときから通っていた。"""
    assert write_calls(src_text(rel)) == []


def test_D0034_AC_33_有無の確かめはnode_fsを使わず読み取りの口を通す():
    """D0034-AC-33: infra/fsPresence.ts は node:fs を import せず、./readOnlyFs.ts（読み取りの 6 つの関数だけの口）を通して stat を呼ぶ。
    ファイルが無ければ、ファイルが無いことで落ちる（テスト先行のときは赤だった）。"""
    source = src_text("infra/fsPresence.ts")
    assert node_fs_imports(source) == []
    assert re.search(r"""from\s+['"]\./readOnlyFs\.ts['"]""", strip_ts_comments(source)), "fsPresence.ts が ./readOnlyFs.ts から読んでいない"


# ---- 検査そのもの（今のまま通る。守る）--------------------------------------------------------


def test_D0034_AC_33_書き込みの呼び出しの見つけ方は書き込みを見つけ_読む呼び出しとコメントは見逃す():
    """D0034-AC-33: 検査そのもの。書き込みの呼び出し（mkdir・writeFile・rm・rename）は見つけ、stat・readFile・readdir・lstat の呼び出しとコメントは見逃す。
    （今のまま通る。守る）"""
    assert write_calls("await mkdir(dir, { recursive: true });\nawait writeFile(p, 'x');\nawait rm(p);\nawait rename(a, b);") == ["mkdir", "rename", "rm", "writeFile"]
    assert write_calls("const info = await fs.stat(dir);\nawait readFile(p);\nawait readdir(d);\nawait lstat(p);") == []
    assert write_calls("// mkdir( は呼ばない\n/* writeFile( */") == []


@pytest.mark.parametrize(
    "source",
    [
        "import { stat } from 'node:fs/promises';",
        "import { readFileSync } from 'node:fs';",
        "import fs from 'fs';",
        'import { stat } from "fs/promises";',
        "const fs = await import('node:fs');",
        "const fs = require('fs/promises');",
    ],
)
def test_D0034_AC_33_node_fsの読み込みの見つけ方は読み込みを見つける(source):
    """D0034-AC-33: 検査そのもの。node:fs・node:fs/promises・前の書き方の fs の import・動的 import・require を見つける。（今のまま通る。守る）"""
    assert node_fs_imports(source) != []


@pytest.mark.parametrize(
    "source",
    [
        "import { nodeReadOnlyFs } from './readOnlyFs.ts';",
        "import type { ReadOnlyFs } from './readOnlyFs.ts';",
        "import type { Presence } from '../app/workDirWatch.ts';",
        "// import { stat } from 'node:fs/promises';",
        "/** node:fs は使わない（require('fs') も書かない） */",
        "const label = 'node:fs は使わない';",
        "import path from 'node:path';",
    ],
)
def test_D0034_AC_33_node_fsの読み込みの見つけ方は読み取りの口とコメントと別の部品を見逃す(source):
    """D0034-AC-33: 検査そのもの。./readOnlyFs.ts の import・app 層の型だけの import・コメントに書いただけの node:fs・文字列の中の言葉・node:path は見逃す。
    （今のまま通る。守る）"""
    assert node_fs_imports(source) == []
