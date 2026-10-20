"""D0010（作業台と実行パネルの初めの形を、あとから書いた決定の記録）と、拡張の実物の食い違いの検査。

- 記録が挙げるファイル・メッセージの種類・設定とコマンドの名前・書ける場所・状態の名前・監視の対象と待ち時間・
  版の上限・前の名前が、vscode/ の実物（.ts と package.json を文字として読む）と合う
- 読み方そのものが、ずれた書き方を見つけられる（偽の記録・偽の .ts は tmp_path に置く）

リポジトリの実物は読むだけで、書かない。SDK は呼ばない。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RECORD = ROOT / "docs" / "decisions" / "D0010-ui-records.md"
DECISIONS_README = ROOT / "docs" / "decisions" / "README.md"
SRC = ROOT / "vscode" / "src"
NONE_REASON = "理由は記録に残っていない"


# ---- 補助：記録を読む ----------------------------------------------------------------------


def record_text() -> str:
    if not RECORD.is_file():
        pytest.fail("docs/decisions/D0010-ui-records.md が無い")
    return RECORD.read_text(encoding="utf-8")


def bullet(text: str, label: str) -> set[str]:
    """`- <label>：` で始まる行から、バッククォートで囲んだ語を取り出す。行が無ければ落とす。"""
    for line in text.splitlines():
        m = re.match(rf"\s*- {re.escape(label)}：(.*)$", line)
        if m:
            return set(re.findall(r"`([^`]+)`", m.group(1)))
    pytest.fail(f"記録に「- {label}：」の行が無い")


def bullet_line(text: str, label: str) -> str:
    for line in text.splitlines():
        if re.match(rf"\s*- {re.escape(label)}：", line):
            return line
    pytest.fail(f"記録に「- {label}：」の行が無い")


# ---- 補助：拡張の実物を読む ----------------------------------------------------------------


def src_text(rel: str) -> str:
    path = SRC / rel
    assert path.is_file(), f"vscode/src/{rel} が無い"
    return path.read_text(encoding="utf-8")


def strip_ts_comments(source: str) -> str:
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    return re.sub(r"(?m)(?<![:'\"])//.*$", "", source)


def ts_union_types(source: str, type_name: str) -> set[str]:
    """`export type <type_name> = …` のユニオンにある `{ type: 'x'; … }` の x の集合。読めなければ空の集合。"""
    code = strip_ts_comments(source)
    m = re.search(rf"export type {re.escape(type_name)}\s*=(.*?)(?=\n\S|\Z)", code, flags=re.DOTALL)
    if not m:
        return set()
    return set(re.findall(r"\{\s*type:\s*'([A-Za-z0-9_]+)'", m.group(1)))


def missing_files(text: str, root: Path) -> list[str]:
    """記録が `vscode/src/…` の形で挙げるファイルのうち、root に無いもの。1件も挙げていなければ落とす。"""
    named = re.findall(r"`(vscode/src/[^`\s]+)`", text)
    assert named, "記録が `vscode/src/…` の形でファイルを1つも挙げていない"
    return sorted({p for p in named if not (root / p).is_file()})


WRITE_CALL = re.compile(
    r"\b(writeFile|writeFileSync|appendFile|appendFileSync|mkdir|mkdirSync|rm|rmSync|rmdir|rmdirSync|"
    r"unlink|unlinkSync|rename|renameSync|copyFile|copyFileSync|createWriteStream|truncate|truncateSync)\s*\("
)


def write_calls(source: str) -> list[str]:
    return sorted({m.group(1) for m in WRITE_CALL.finditer(strip_ts_comments(source))})


# ---- D0010-AC-01 ---------------------------------------------------------------------------


def test_D0010_AC_01_記録が決まった名前で在る():
    """D0010-AC-01: docs/decisions/D0010-ui-records.md がある（形は test_rules.py の検査に任せる）。"""
    assert RECORD.is_file(), "docs/decisions/D0010-ui-records.md が無い"


# ---- D0010-AC-02 ---------------------------------------------------------------------------


def test_D0010_AC_02_記録が挙げる拡張のファイルは実在する():
    """D0010-AC-02: 記録が `vscode/src/…` の形で挙げるファイルは、すべてリポジトリにある。"""
    assert missing_files(record_text(), ROOT) == []


def test_D0010_AC_02_存在しないファイルを見つけられる(tmp_path):
    """D0010-AC-02: 検査そのものが、実在しない名前を見つけ、実在する名前は見逃す。"""
    (tmp_path / "vscode" / "src").mkdir(parents=True)
    (tmp_path / "vscode" / "src" / "a.ts").write_text("x", encoding="utf-8")
    record = "`vscode/src/a.ts` と `vscode/src/ghost.ts` を読む"
    assert missing_files(record, tmp_path) == ["vscode/src/ghost.ts"]
    with pytest.raises(AssertionError):
        missing_files("ファイルを挙げていない記録", tmp_path)


# ---- D0010-AC-03 ---------------------------------------------------------------------------

MESSAGE_ROWS = [
    ("実行パネル 拡張→パネル", "ToPanelMessage"),
    ("実行パネル パネル→拡張", "FromPanelMessage"),
    ("作業台 拡張→パネル", "ToEditorMessage"),
    ("作業台 パネル→拡張", "FromEditorMessage"),
]


@pytest.mark.parametrize("label,type_name", MESSAGE_ROWS)
def test_D0010_AC_03_メッセージの種類が型と一致する(label, type_name):
    """D0010-AC-03: 記録の4行のメッセージの種類は、messages.ts の型の type と過不足なく一致する。"""
    actual = ts_union_types(src_text("view/messages.ts"), type_name)
    assert actual, f"messages.ts から {type_name} の type を読めなかった"
    assert bullet(record_text(), label) == actual


def test_D0010_AC_03_型の読み方が型のユニオンを取れる(tmp_path):
    """D0010-AC-03: 型の読み方は、単独・「|」つき・複数行・コメントつきのユニオンを読み、ずれた書き方では空になる。"""
    ts = tmp_path / "m.ts"
    ts.write_text(
        "export type One = { type: 'render'; html: string };\n"
        "export type Many =\n"
        "  | { type: 'ready' }\n"
        "  /** 説明 { type: 'fake' } */\n"
        "  // { type: 'fake2' }\n"
        "  | { type: 'save'; model: PipeModel }\n"
        "  | {\n    type: 'state'; dirty: boolean }\n"
        "  | { type: 'x1'; url: 'http://a' };\n"
        "export function f() { return { type: 'outside' }; }\n"
        "type NotExported = { type: 'hidden' };\n",
        encoding="utf-8",
    )
    source = ts.read_text(encoding="utf-8")
    assert ts_union_types(source, "One") == {"render"}
    assert ts_union_types(source, "Many") == {"ready", "save", "state", "x1"}
    assert ts_union_types(source, "NotExported") == set()
    assert ts_union_types(source, "Missing") == set()


def test_D0010_AC_03_型の読み方は実物のmessages_tsを読める():
    """D0010-AC-03: 実物の messages.ts で、4つの型とも空にならない（型の書き方が変わったら気づく）。"""
    source = src_text("view/messages.ts")
    assert ts_union_types(source, "ToPanelMessage") == {"render"}
    for _, type_name in MESSAGE_ROWS:
        assert ts_union_types(source, type_name), type_name


# ---- D0010-AC-04 ---------------------------------------------------------------------------

SETTINGS = ["pipe-in.workDir", "pipe-in.pipesDir"]
COMMANDS = ["pipe-in.showRun", "pipe-in.editPipe"]


def package_names() -> tuple[set[str], set[str]]:
    pkg = json.loads((ROOT / "vscode" / "package.json").read_text(encoding="utf-8"))
    contributes = pkg["contributes"]
    conf = contributes["configuration"]
    confs = conf if isinstance(conf, list) else [conf]
    settings: set[str] = set()
    for c in confs:
        settings |= set(c.get("properties", {}))
    return settings, {c["command"] for c in contributes["commands"]}


def test_D0010_AC_04_設定名とコマンドIDがpackage_jsonにある():
    """D0010-AC-04: 記録が挙げる設定名とコマンド ID は、記録に書いてあり、package.json にある。"""
    settings, commands = package_names()
    assert set(SETTINGS) <= settings
    assert set(COMMANDS) <= commands
    text = record_text()
    for name in SETTINGS + COMMANDS:
        assert f"`{name}`" in text, f"記録に `{name}` が無い"


# ---- D0010-AC-05 ---------------------------------------------------------------------------


def test_D0010_AC_05_書ける場所が実物と一致する():
    """D0010-AC-05: 書ける場所（固定ファイル・指示文・版のファイル名）が fsPipes.ts・fsVersions.ts の実物と一致する。"""
    pipes = src_text("infra/fsPipes.ts")
    fixed = re.search(r"FIXED = new Set\(\[([^\]]*)\]", pipes)
    assert fixed, "fsPipes.ts から FIXED を読めなかった"
    prompt = re.search(r"PROMPT = /\^prompts\\/.*\\\.md\$/", pipes)
    assert prompt, "fsPipes.ts から PROMPT（prompts/…md）を読めなかった"
    file_re = re.search(r"const FILE = /\^(.*)\$/", src_text("infra/fsVersions.ts"))
    assert file_re, "fsVersions.ts から FILE を読めなかった"
    assert file_re.group(1) == r"\d{13}(-draft)?\.json", "版のファイル名の形が変わった。記録も直す"

    text = record_text()
    assert bullet(text, "固定ファイル") == set(re.findall(r"'([^']+)'", fixed.group(1)))
    assert bullet(text, "指示文") == {"prompts/*.md"}
    assert bullet(text, "版のファイル名") == {"<13桁>[-draft].json"}


def test_D0010_AC_05_版の上限が定数と一致する():
    """D0010-AC-05: 記録の「残す版の数」は pipeVersions.ts の VERSION_LIMIT と同じ。"""
    limit = re.search(r"VERSION_LIMIT\s*=\s*(\d+)", src_text("domain/pipeVersions.ts"))
    assert limit, "pipeVersions.ts から VERSION_LIMIT を読めなかった"
    assert bullet(record_text(), "残す版の数") == {limit.group(1)}


# ---- D0010-AC-06 ---------------------------------------------------------------------------


def test_D0010_AC_06_読むだけの口に書き込みの呼び出しが無い():
    """D0010-AC-06: fsWorkDirSource.ts に書き込みの呼び出しが無い。
    今の作りのままで通る（記録が無くても通る）。「work_dir には書かない」を守り続けるための検査として置く。"""
    assert write_calls(src_text("infra/fsWorkDirSource.ts")) == []


def test_D0010_AC_06_記録がwork_dirに書かないと書いている():
    """D0010-AC-06: 記録に、work_dir は書かない（読むだけ）と書いた行がある。"""
    lines = record_text().splitlines()
    assert any("work_dir" in ln and ("書かない" in ln or "読むだけ" in ln) for ln in lines)


def test_D0010_AC_06_書き込みの呼び出しの見つけ方():
    """D0010-AC-06: 見つけ方そのものが、書き込みの呼び出しを見つけ、コメントや読むだけの呼び出しは見逃す。
    今の作りのままで通る（読み方の確認）。"""
    assert write_calls("await writeFile(p, 'x');\nfs.promises.rm(p)\nmkdirSync(d)") == ["mkdirSync", "rm", "writeFile"]
    assert write_calls("// writeFile( は書かない\n/* mkdir( */\nconst r = await readFile(p); readdir(d)") == []


# ---- D0019-AC-32：実行の一覧が work_dir・.git を読む口にも、書き込みの呼び出しが無い --------------


READ_ONLY_SOURCES = ["infra/fsWorkDirSource.ts", "infra/fsWorktrees.ts", "infra/readOnlyFs.ts"]


@pytest.mark.parametrize("rel", READ_ONLY_SOURCES)
def test_D0019_AC_32_work_dirとgitの登録を読む口に書き込みの呼び出しが無い(rel):
    """D0019-AC-32: fsWorkDirSource.ts（archive・別の worktree の run を読む）と fsWorktrees.ts（.git の登録を読む）に、
    書き込みの呼び出しが無い。fsWorktrees.ts がまだ無いうちは、ファイルが無いことで落ちる（赤）。"""
    assert write_calls(src_text(rel)) == []


def test_D0019_AC_32_読み取りの口はreadHeadを持ち開き方はrだけ():
    """D0019-AC-32: 読み取りの口（readOnlyFs.ts）に、先頭だけを読む readHead があり、ファイルを開く呼び出しのフラグは 'r' だけ
    （書き込みのフラグ 'w'・'a'・'r+' などを使わない）。読み取りの口は 6 つになる（design の AC-32）。"""
    source = strip_ts_comments(src_text("infra/readOnlyFs.ts"))
    assert re.search(r"\breadHead\b", source), "readOnlyFs.ts に readHead が無い"
    opens = re.findall(r"\bopen\s*\(([^)]*)\)", source)
    assert opens, "readHead がファイルを開く open( の呼び出しが見つからない"
    for args in opens:
        assert re.search(r",\s*'r'\s*$", args.strip()), f"open の開き方が 'r' だけでない: {args}"
    interface = re.search(r"interface\s+ReadOnlyFs\s*\{(.*?)\}", source, flags=re.DOTALL)
    assert interface, "ReadOnlyFs の型が読めなかった"
    assert len(re.findall(r"^\s*\w+\s*:", interface.group(1), flags=re.MULTILINE)) == 6


def test_D0019_AC_32_子プロセスを起こさない():
    """D0019-AC-32: 読む口が child_process を import していない（別の worktree は .git のファイルを読んで見つける）。
    fsWorktrees.ts がまだ無いうちは、ファイルが無いことで落ちる（赤）。"""
    for rel in READ_ONLY_SOURCES:
        assert "child_process" not in src_text(rel), rel



# ---- D0010-AC-07 ---------------------------------------------------------------------------


def test_D0010_AC_07_節の状態の名前が一致する():
    """D0010-AC-07: 記録の「節の状態」は pipelineView.ts の NODE_STATUS_LABELS の値と過不足なく一致する。"""
    body = re.search(r"NODE_STATUS_LABELS[^=]*=\s*\{(.*?)\}", src_text("domain/pipelineView.ts"), flags=re.DOTALL)
    assert body, "pipelineView.ts から NODE_STATUS_LABELS を読めなかった"
    labels = set(re.findall(r":\s*'([^']+)'", body.group(1)))
    assert labels, "NODE_STATUS_LABELS の値を読めなかった"
    assert bullet(record_text(), "節の状態") == labels


def test_D0010_AC_07_監視の対象とまとめる時間が一致する():
    """D0010-AC-07: 記録の「監視の対象」は監視の対象の文字（WATCH_GLOB）にあり（1段下の `*/` つきも）、「まとめる時間」は DEBOUNCE_MS と同じ。

    D0019 で、この2つは extension.ts から app/refreshPolicy.ts に移った（読む場所だけを直した。期待は変えない）。
    extension.ts がその監視の対象を RelativePattern に渡していることも確かめる。
    """
    ext = src_text("extension.ts")
    policy = src_text("app/refreshPolicy.ts")
    pattern = re.search(r"WATCH_GLOB\s*=\s*'([^']*)'", policy)
    assert pattern, "refreshPolicy.ts から WATCH_GLOB の文字列を読めなかった"
    debounce = re.search(r"DEBOUNCE_MS\s*=\s*(\d+)", policy)
    assert debounce, "refreshPolicy.ts から DEBOUNCE_MS を読めなかった"
    assert re.search(r"RelativePattern\([^)]*WATCH_GLOB", ext, flags=re.DOTALL), "extension.ts が WATCH_GLOB を RelativePattern に渡していない"
    text = record_text()
    targets = bullet(text, "監視の対象")
    assert targets == {"state.json", "*.md", "logs/*.jsonl"}
    for t in targets:
        assert t in pattern.group(1), t
        assert f"*/{t}" in pattern.group(1), f"*/{t}"
    assert bullet(text, "まとめる時間") == {f"{debounce.group(1)}ms"}


# ---- D0010-AC-08 ---------------------------------------------------------------------------


def sections(text: str) -> list[str]:
    return re.split(r"(?m)^#{2,4} ", text)


def test_D0010_AC_08_理由が残っていない項目を挙げている():
    """D0010-AC-08: 「理由は記録に残っていない」が、200ms・50・「読むだけ」の項目と同じ小見出しの中にある。
    推測の理由が添えられていないかは意味の判断なので、検証の段で手で確かめる。"""
    text = record_text()
    assert NONE_REASON in text
    parts = sections(text)
    for key in ["200ms", "`50`", "読むだけ"]:
        assert any(key in s and NONE_REASON in s for s in parts), f"{key} の小見出しに「{NONE_REASON}」が無い"


def test_D0010_AC_08_小見出しの切り方():
    """D0010-AC-08: 小見出し（## から ####）で切り、別の小見出しの語は混ざらない。今の作りのままで通る（読み方の確認）。"""
    parts = sections("# t\n## a\n200ms\n### b\n" + NONE_REASON + "\n")
    assert not any("200ms" in s and NONE_REASON in s for s in parts)
    assert any(NONE_REASON in s for s in parts)


# ---- D0010-AC-09 ---------------------------------------------------------------------------


def test_D0010_AC_09_READMEの表にD0010の行がある():
    """D0010-AC-09: docs/decisions/README.md の表に D0010 の行がある。"""
    lines = DECISIONS_README.read_text(encoding="utf-8").splitlines()
    assert any(ln.startswith("|") and "[D0010](D0010-ui-records.md)" in ln for ln in lines)


# ---- D0010-AC-12 ---------------------------------------------------------------------------


def test_D0010_AC_12_前の名前を読み続けると書き実物にある():
    """D0010-AC-12: 記録の「前の名前」に devpipe の置き場所・フォルダ名・設定があり、names.ts・pipeEditor.ts の実物にある。"""
    assert re.search(r"LEGACY_SECTION\s*=\s*'devpipe'", src_text("app/names.ts"))
    editor = src_text("app/pipeEditor.ts")
    assert re.search(r"LEGACY_PREFIX\s*=\s*'devpipe-'", editor)
    assert re.search(r"\[\s*'\.devpipe'\s*,\s*'pipes'\s*\]", editor)
    line = bullet_line(record_text(), "前の名前")
    for word in [".devpipe/pipes/", "devpipe-<名前>/", "devpipe.*"]:
        assert word in line, word
