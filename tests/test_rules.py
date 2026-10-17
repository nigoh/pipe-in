"""開発のルール（docs/development/）のうち、テストで守らせられるものの検査。

- 追跡しているファイルに、手元の事情（ユーザー名の入った絶対パス・メールアドレス）や秘密のファイルが無い
- 決定の記録（docs/decisions/）が決まった形で、テストに出てくる Dnnnn-AC-xx が記録にある
- CLAUDE.md と docs/development/design.md の置き場所の表にあるパスが、実際にある
- テストを流しても、リポジトリの実物のフォルダが変わらない（conftest.py が見張る。ここでは見張り方を確かめる）
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DECISIONS = ROOT / "docs" / "decisions"
DEVELOPMENT = ROOT / "docs" / "development"

AC_ID = re.compile(r"\bD\d{4}-AC-\d{2}\b")


def tracked_files() -> list[Path]:
    if shutil.which("git") is None or not (ROOT / ".git").exists():
        pytest.skip("git が無い・リポジトリではないため、追跡しているファイルを調べられない")
    out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True).stdout
    return [ROOT / p for p in out.decode("utf-8").split("\0") if p]


def text_of(path: Path) -> str | None:
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if b"\0" in data[:4096]:
        return None  # 画像などの中身は見ない
    return data.decode("utf-8", errors="ignore")


# ---- D0002-AC-01: 手元の事情と秘密を載せない ----------------------------------------

LOCAL_INFO = [
    (re.compile(r"[A-Za-z]:[\\/]+Users[\\/]+[A-Za-z0-9_.-]"), "ユーザー名の入った Windows のパス"),
    (re.compile(r"(?<![A-Za-z0-9_.-])/Users/[A-Za-z0-9_.-]"), "ユーザー名の入った macOS のパス"),
    (re.compile(r"(?<![A-Za-z0-9_.-])/home/[A-Za-z0-9_.-]"), "ユーザー名の入った Linux のパス"),
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+\.[A-Za-z0-9.-]+"), "メールアドレス"),
]
# 載せてよいメールアドレス（コミットの共著者の決まった書き方・見本のドメイン）
ALLOWED_MAIL = re.compile(r"noreply@anthropic\.com|@example\.(com|org|net)|@users\.noreply\.github\.com")
SECRET_FILES = re.compile(r"(^|/)(\.env(\..*)?|id_rsa.*|id_ed25519.*|.*\.pem|.*\.key)$")


def local_info_in(text: str) -> list[str]:
    found = []
    for pattern, what in LOCAL_INFO:
        for m in pattern.finditer(text):
            if what == "メールアドレス" and ALLOWED_MAIL.search(m.group(0)):
                continue
            found.append(f"{what}: {m.group(0)}")
    return found


@pytest.mark.parametrize(
    "text,bad",
    [
        (r"C:\Users\taro\work", True),
        ("C:/Users/taro/work", True),
        ("/Users/hanako/src", True),
        ("/home/jiro/app", True),
        ("mail me: someone@corp.co.jp", True),
        (r"`C:\Users\…`", False),
        ("Co-Authored-By: Claude <noreply@anthropic.com>", False),
        ("~/src/myapp と /etc/passwd", False),
        ("D:/work/app", False),
    ],
)
def test_local_info_pattern(text, bad):
    """D0002-AC-01: 見つけ方そのものが、載せてはいけない書き方を見つけ、決まった書き方は見逃す。"""
    assert bool(local_info_in(text)) is bad


def test_no_local_info_in_tracked_files():
    """D0002-AC-01: 追跡しているファイルに、手元の事情と秘密のファイルが無い。"""
    found = []
    for path in tracked_files():
        rel = path.relative_to(ROOT).as_posix()
        if SECRET_FILES.search(rel):
            found.append(f"{rel}: 秘密のファイル")
        if rel == "tests/test_rules.py":
            continue  # この検査の見本を書いているファイル
        text = text_of(path)
        if text is None:
            continue
        found += [f"{rel}: {f}" for f in local_info_in(text)]
    assert found == []


# ---- D0002-AC-02: 決定の記録の形 -----------------------------------------------------

RECORD_NAME = re.compile(r"D(\d{4})-[a-z0-9][a-z0-9-]*\.md")
RECORD_SECTIONS = ["## 目的", "## 機能要件と受け入れ基準", "## 決めたことと理由", "## 対象外・残った課題", "## 確かめたこと"]


def records() -> list[Path]:
    return sorted(p for p in DECISIONS.glob("D*.md") if RECORD_NAME.fullmatch(p.name))


def test_decision_records_have_sections():
    """D0002-AC-02: 記録は Dnnnn-<名前>.md で、番号は重ならず、決まった見出しを持つ。"""
    found = records()
    assert found, "docs/decisions/ に記録が1つも無い"
    numbers = [RECORD_NAME.fullmatch(p.name).group(1) for p in found]
    assert len(numbers) == len(set(numbers)), "番号が重なっている"
    stray = [p.name for p in DECISIONS.glob("*.md") if p.name != "README.md" and not RECORD_NAME.fullmatch(p.name)]
    assert stray == [], "名前の形が違う記録がある"
    for p in found:
        text = p.read_text(encoding="utf-8")
        number = RECORD_NAME.fullmatch(p.name).group(1)
        assert text.startswith(f"# D{number} "), f"{p.name} の1行目は「# D{number} <題>」"
        missing = [s for s in RECORD_SECTIONS if s not in text]
        assert missing == [], f"{p.name} に無い見出し: {missing}"
        own = {i for i in AC_ID.findall(text) if i.startswith(f"D{number}-")}
        assert own, f"{p.name} に D{number}-AC-xx の受け入れ基準が無い"


def test_ac_ids_in_tests_exist_in_records():
    """D0002-AC-03: テストに出てくる Dnnnn-AC-xx は、その番号の記録の中にある。"""
    defined: set[str] = set()
    for p in records():
        defined |= set(AC_ID.findall(p.read_text(encoding="utf-8")))
    sources = [*(ROOT / "tests").glob("test_*.py"), *(ROOT / "vscode" / "src").rglob("*.test.ts")]
    missing = []
    for src in sources:
        for ac in set(AC_ID.findall(src.read_text(encoding="utf-8"))):
            if ac not in defined:
                missing.append(f"{src.relative_to(ROOT).as_posix()}: {ac}")
    assert sorted(missing) == []


# ---- D0002-AC-04: 置き場所の表と実物が食い違わない ----------------------------------------

TABLE_PATH = re.compile(r"`([^`\s<>*…]+/[^`\s<>*…]*)`")


def table_paths(text: str) -> list[str]:
    """表の行（| で始まる行）にある、/ を含むパス。対象プロジェクトの中を指すもの（.pipe-in/・.devpipe/ と ~/）と、node: の部品の名前は除く。"""
    out = []
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        for m in TABLE_PATH.finditer(line):
            p = m.group(1)
            if p.startswith((".pipe-in/", ".devpipe/", "~/", "/", "node:")) or "://" in p:
                continue
            out.append(p)
    return out


def test_table_paths_pattern():
    """D0002-AC-04・D0006-AC-25: 表のパスの拾い方。対象の中を指す .pipe-in/ と前の版の .devpipe/ は除く。"""
    text = (
        "| a | `pipe_in/cli.py`・`generator/` |\n"
        "| b | 対象の `.pipe-in/pipes/`、`.devpipe/pipes/`、`pipes/pipe-in-<名前>/`・`node:fs/promises` |\n"
        "本文の `x/y.py` は見ない"
    )
    assert table_paths(text) == ["pipe_in/cli.py", "generator/"]


@pytest.mark.parametrize("doc", ["CLAUDE.md", "docs/development/design.md"])
def test_place_tables_point_to_real_paths(doc):
    """D0002-AC-04: CLAUDE.md と design.md の表にあるパスが、リポジトリに実際にある。"""
    path = ROOT / doc
    assert path.is_file(), doc
    paths = table_paths(path.read_text(encoding="utf-8"))
    assert paths, f"{doc} の表にパスが無い"
    assert [p for p in paths if not (ROOT / p).exists()] == []


# ---- D0002-AC-05: テストがリポジトリの実物を変えたら気づく ---------------------------------


def test_watch_detects_changes(tmp_path):
    """D0002-AC-05: conftest.py の見張りは、足した・消した・中身を変えたファイルに気づく。"""
    import conftest

    (tmp_path / "pipes").mkdir()
    (tmp_path / "pipes" / "README.md").write_text("a", encoding="utf-8")
    before = conftest.snapshot(tmp_path)
    assert conftest.changes(before, conftest.snapshot(tmp_path)) == []
    (tmp_path / "pipes" / "devpipe-x").mkdir()
    (tmp_path / "pipes" / "devpipe-x" / "pipe.toml").write_text("x", encoding="utf-8")
    (tmp_path / ".devpipe").mkdir()
    (tmp_path / ".devpipe" / "a.md").write_text("x", encoding="utf-8")
    (tmp_path / "pipes" / "README.md").write_text("bb", encoding="utf-8")
    changed = conftest.changes(before, conftest.snapshot(tmp_path))
    assert "pipes/devpipe-x/pipe.toml" in changed and ".devpipe/a.md" in changed and "pipes/README.md" in changed


def test_watched_dirs():
    """D0002-AC-05・D0006-AC-25: 見張るのは pipes/・.pipe-in/・.devpipe/・docs/pipeline/。"""
    import conftest

    assert set(conftest.WATCHED) == {"pipes", ".pipe-in", ".devpipe", "docs/pipeline"}


def test_watch_detects_new_place(tmp_path):
    """D0006-AC-25: 見張りは、新しい置き場所 .pipe-in/ への書き込みにも気づく。"""
    import conftest

    before = conftest.snapshot(tmp_path)
    (tmp_path / ".pipe-in" / "pipes" / "pipe-in-x").mkdir(parents=True)
    (tmp_path / ".pipe-in" / "pipes" / "pipe-in-x" / "pipe.toml").write_text("x", encoding="utf-8")
    assert ".pipe-in/pipes/pipe-in-x/pipe.toml" in conftest.changes(before, conftest.snapshot(tmp_path))


def test_gitignore_has_both_places():
    """D0006-AC-25: .gitignore に新しい置き場所 /.pipe-in/ と、前の版の /.devpipe/ の両方がある。"""
    lines = [line.strip() for line in (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()]
    assert "/.pipe-in/" in lines
    assert "/.devpipe/" in lines


# ---- D0002-AC-06: 開発のルールの文書がそろっている -----------------------------------------


def test_development_docs_exist():
    """D0002-AC-06: docs/development/ の文書と、CLAUDE.md・/pipe-in からの案内がある。"""
    for name in ["README.md", "principles.md", "specs.md", "design.md", "testing.md", "workflow.md"]:
        assert (DEVELOPMENT / name).is_file(), name
    assert (DECISIONS / "README.md").is_file()
    claude = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    assert "docs/development/" in claude
    pipe_in = (ROOT / ".claude/skills/pipe-in/SKILL.md").read_text(encoding="utf-8")
    for word in ["docs/development/", "docs/decisions/", "worktree", "Dnnnn-AC-"]:
        assert word in pipe_in, word


# ---- D0003-AC-01〜02: main が進んだら載せ直す ---------------------------------------------


def test_workflow_documents_rebase():
    """D0003-AC-01・D0006-AC-26: workflow.md に、載せ直す時と方法・main へは早送りで入れること・worktree の注意がある（コマンドは新しい名前）。"""
    text = (DEVELOPMENT / "workflow.md").read_text(encoding="utf-8")
    for word in [
        "git rebase --autostash main",
        "git merge --ff-only",
        "段の区切り",
        "検証の段の前",
        "main に入れる直前",
        "載せ直したら",
        "push したブランチ",
        "python -m pipe_in",
        "stash しない",
    ]:
        assert word in text, word


def test_pipe_in_rebases_when_main_moves():
    """D0003-AC-02: /pipe-in は段の区切りで main が進んだかを見て、検証の前と入れる前には必ず載せ直す。"""
    text = (ROOT / ".claude/skills/pipe-in/SKILL.md").read_text(encoding="utf-8")
    for word in ["git log --oneline HEAD..main", "git rebase --autostash main", "検証の段の前", "--ff-only"]:
        assert word in text, word
