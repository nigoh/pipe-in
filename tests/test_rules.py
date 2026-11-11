"""開発のルール（docs/development/）のうち、テストで守らせられるものの検査。

- 追跡しているファイルと、まだ追跡していない新しいファイル（.gitignore の外。D0075）に、手元の事情（ユーザー名の入った絶対パス・メールアドレス）や秘密のファイルが無い
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

from pipe_in.dev import spec_check

ROOT = Path(__file__).resolve().parents[1]
DECISIONS = ROOT / "docs" / "decisions"
DEVELOPMENT = ROOT / "docs" / "development"

# D0051 で 3 桁（AC-100 以上）まで拾えるように広げた（厳しくする側。広げないと AC-100〜111 は、記録とテストの突き合わせから外れる）
AC_ID = re.compile(r"\bD\d{4}-AC-\d{2,3}\b")


def git_list(root: Path, *args: str) -> list[Path]:
    """`git ls-files -z <args>` のパス（root からの相対を root に付けたもの）。git が無い・リポジトリでなければ、そのテストを飛ばす。"""
    if shutil.which("git") is None or not (root / ".git").exists():
        pytest.skip("git が無い・リポジトリではないため、追跡しているファイルを調べられない")
    out = subprocess.run(["git", "ls-files", "-z", *args], cwd=root, capture_output=True, check=True).stdout
    return [root / p for p in out.decode("utf-8").split("\0") if p]


def tracked_files(root: Path = ROOT) -> list[Path]:
    return git_list(root)


def new_files(root: Path = ROOT) -> list[Path]:
    """まだ追跡していない新しいファイル（.gitignore の外）。D0075：追跡したあとの CI で初めて落ちないように、手元でも見る。"""
    return git_list(root, "--others", "--exclude-standard")


def checked_files(root: Path = ROOT) -> list[Path]:
    """秘密・手元の事情の検査が見るファイル：追跡しているファイルと、まだ追跡していない新しいファイル（重なりなし・並べて返す）。"""
    return sorted(set(tracked_files(root)) | set(new_files(root)))


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


def local_problems(files: list[Path], root: Path) -> list[str]:
    """files（root の下）にある、手元の事情と秘密のファイル。「<相対パス>: <中身>」の文で返す。"""
    found = []
    for path in files:
        rel = path.relative_to(root).as_posix()
        if SECRET_FILES.search(rel):
            found.append(f"{rel}: 秘密のファイル")
        if rel == "tests/test_rules.py":
            continue  # この検査の見本を書いているファイル
        text = text_of(path)
        if text is None:
            continue
        found += [f"{rel}: {f}" for f in local_info_in(text)]
    return found


def test_no_local_info_in_tracked_files():
    """D0002-AC-01・D0075: 追跡しているファイルと、まだ追跡していない新しいファイル（.gitignore の外）に、手元の事情と秘密のファイルが無い。"""
    found = local_problems(checked_files(), ROOT)
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


def test_ac_id_pattern():
    """D0002-AC-03: 受け入れ基準の ID の拾い方そのものの確かめ。2 桁（D0051-AC-26）と 3 桁（D0051-AC-100）の番号は拾い、
    1 桁（D0051-AC-1）と 4 桁（D0051-AC-1000）は拾わない。前の 2 桁だけの拾い方は D0051-AC-100 に当てはまらず、AC-100 以上が検査から外れていた。"""
    assert AC_ID.findall("D0051-AC-26 と D0051-AC-100 と D0002-AC-03") == ["D0051-AC-26", "D0051-AC-100", "D0002-AC-03"]
    assert AC_ID.findall("D0051-AC-1 と D0051-AC-1000 と Dnnnn-AC-xx") == []
    assert re.findall(r"\bD\d{4}-AC-\d{2}\b", "D0051-AC-100") == [], "前の拾い方は 3 桁を拾えなかった（広げた理由）"


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
    """D0003-AC-01・D0006-AC-26: workflow.md に、載せ直す時と方法・main へは早送りで入れること・worktree の注意がある（コマンドは新しい名前）。
    D0074：載せ直す先は origin の main（git rebase --autostash origin/main）。手元の git merge --ff-only と stash の段落は「5. 終える」から外れ、
    git merge --ff-only は「ブランチの保護」の節（手元では使えなくなる）に残る。"""
    text = (DEVELOPMENT / "workflow.md").read_text(encoding="utf-8")
    for word in [
        "git rebase --autostash origin/main",
        "git merge --ff-only",
        "段の区切り",
        "検証の段の前",
        "main に入れる直前",
        "載せ直したら",
        "push したブランチ",
        "python -m pipe_in",
    ]:
        assert word in text, word


def test_pipe_in_rebases_when_main_moves():
    """D0003-AC-02: /pipe-in は段の区切りで main が進んだかを見て、検証の前と入れる前には必ず載せ直す。
    D0074：載せ直しは worktree sync（origin の main を取ってから載せる）。手元の git merge --ff-only は書かず、PR と CI で入れる。"""
    text = (ROOT / ".claude/skills/pipe-in/SKILL.md").read_text(encoding="utf-8")
    for word in ["worktree sync", "origin", "検証の段の前"]:
        assert word in text, word


# ---- D0075-AC-17〜20: 秘密・手元の事情の検査は、まだ追跡していない新しいファイルも見る -----------------------
# きっかけ：D0074 の PR で、新しいテストの偽の URL（ユーザー名とトークンの形の文字をアドレスにつないだもの）がメールアドレスに見え、
# 手元では（まだ追跡していないので）通り、追跡したあとの CI で落ちた。
# 見本の文字（偽のメールアドレス・パス）は、組み立てて書く。このファイルだけが検査から除かれている（上の test_no_local_info_in_tracked_files）。
# 見るファイルの取り方は、上の git_list・tracked_files・new_files・checked_files、中身の検査は local_problems。


def make_repo(root: Path) -> None:
    """一時のフォルダを git のリポジトリにする（コミットはしない。git init と git ls-files はユーザー名の設定が要らない）。"""
    if shutil.which("git") is None:
        pytest.skip("git が無いため、一時のリポジトリを作れない")
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)


def rel_set(files: list[Path], root: Path) -> set[str]:
    return {p.relative_to(root).as_posix() for p in files}


def test_D0075_AC_17_検査のファイル一覧は追跡中と未追跡の新しいファイルの両方を含む(tmp_path):
    """D0075-AC-17: 一時のリポジトリで、git add した a.txt（追跡）と git add していない b.txt（未追跡）の両方が checked_files に出る。
    tracked_files は a.txt だけ、new_files は b.txt だけ。"""
    make_repo(tmp_path)
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    subprocess.run(["git", "add", "a.txt"], cwd=tmp_path, check=True)
    (tmp_path / "b.txt").write_text("b", encoding="utf-8")
    checked = checked_files(tmp_path)
    assert {"a.txt", "b.txt"} <= rel_set(checked, tmp_path)
    assert rel_set(tracked_files(tmp_path), tmp_path) == {"a.txt"}
    assert rel_set(new_files(tmp_path), tmp_path) == {"b.txt"}


def test_D0075_AC_17_既存の検査は追跡中と未追跡の両方の一覧を使う():
    """D0075-AC-17・D0075-AC-20: test_no_local_info_in_tracked_files（名前は変えない）は、見るファイルの取り方に checked_files を使う。"""
    import inspect

    source = inspect.getsource(test_no_local_info_in_tracked_files)
    assert "checked_files(" in source, "test_no_local_info_in_tracked_files が checked_files() を使っていない（追跡中のファイルしか見ていない）"


def test_D0075_AC_18_gitignoreの中のファイルは一覧に出ない(tmp_path):
    """D0075-AC-18: 一時のリポジトリで、.gitignore に書いた docs/pipeline/ の中のファイルは checked_files に出ない（.gitignore 自身は出る）。"""
    make_repo(tmp_path)
    (tmp_path / ".gitignore").write_text("docs/pipeline/\n", encoding="utf-8")
    (tmp_path / "docs" / "pipeline").mkdir(parents=True)
    (tmp_path / "docs" / "pipeline" / "x.md").write_text("x", encoding="utf-8")
    (tmp_path / "docs" / "note.md").write_text("n", encoding="utf-8")
    found = rel_set(checked_files(tmp_path), tmp_path)
    assert "docs/pipeline/x.md" not in found
    assert {".gitignore", "docs/note.md"} <= found


def test_D0075_AC_19_未追跡の新しいファイルの手元の事情と秘密の名前を見つけ_載せてよい書き方は見逃す(tmp_path):
    """D0075-AC-19: 未追跡の note.md の偽のメールアドレス（URL の形）とユーザー名の入った Linux のパス、未追跡の .env を見つける。
    載せてよい書き方（noreply@anthropic.com・@example.com）だけのファイルは見逃す。"""
    make_repo(tmp_path)
    fake_mail = "user:token" + "@" + "127.0.0.1"
    fake_path = "/ho" + "me/jiro/app"
    (tmp_path / "note.md").write_text(f"接続先 http://{fake_mail}:8080/ と {fake_path}\n", encoding="utf-8")
    (tmp_path / ".env").write_text("X=1\n", encoding="utf-8")
    (tmp_path / "ok.md").write_text("Co-Authored-By: Claude <noreply@anthropic.com> と dev@example.com\n", encoding="utf-8")
    problems = local_problems(checked_files(tmp_path), tmp_path)
    text = "\n".join(problems)
    assert "note.md: メールアドレス" in text, text
    assert "note.md: ユーザー名の入った Linux のパス" in text, text
    assert ".env: 秘密のファイル" in text, text
    assert not [p for p in problems if p.startswith("ok.md")], text


def test_D0075_AC_20_一時のリポジトリだけで確かめ_実物に書かない(tmp_path, monkeypatch):
    """D0075-AC-20: checked_files の戻りはすべて一時のフォルダの下で、リポジトリの実物（ROOT）の下のものを含まない。
    git が無い・リポジトリでないときは、今までどおり飛ばす（pytest.skip）。"""
    make_repo(tmp_path)
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    files = checked_files(tmp_path)
    assert files and all(p.is_relative_to(tmp_path) for p in files)
    assert not any(p.is_relative_to(ROOT) for p in files)
    plain = tmp_path / "plain"
    plain.mkdir()
    with pytest.raises(pytest.skip.Exception):
        checked_files(plain)  # .git が無いフォルダ
    monkeypatch.setattr(shutil, "which", lambda name: None)
    with pytest.raises(pytest.skip.Exception):
        checked_files(tmp_path)  # git が無い環境


# ---- D0085-AC-12・AC-13: 決定の記録の鎖の検査（D0085 以降だけ） ------------------------------------------

# 鎖の検査をかける最初の決定の番号（1か所。製品コードには置かない）。これより前の記録は検査しない（書き換えない）。
CHAIN_FROM = 85
# 新しい見出し → それが入る親の見出し（D0085 以降の記録は、5つの見出しはそのままで、親の節の中にこの2つの ### を持つ）
CHAIN_SECTIONS = {"### 要求と前提": "## 目的", "### 非機能要件": "## 機能要件と受け入れ基準"}


def record_chain_problems(number: int, text: str) -> list[str]:
    """決定の記録 Dnnnn の鎖の問題（D0085 以降だけ）。number が CHAIN_FROM より小さければ [] 。
    (1) CHAIN_SECTIONS の見出しが無い・親の節の外にある、(2) UR が無い（前の形）、(3) spec_check の問題の行。"""
    if number < CHAIN_FROM:
        return []
    problems: list[str] = []
    lines = text.splitlines()
    for child, parent in CHAIN_SECTIONS.items():
        at = next((i for i, line in enumerate(lines) if line.strip() == child), None)
        if at is None:
            problems.append(f"見出し「{child}」が無い（D{number:04d}）")
            continue
        owner = next((lines[i].strip() for i in range(at - 1, -1, -1) if lines[i].startswith("## ")), None)
        if owner != parent:
            problems.append(f"見出し「{child}」は「{parent}」の節の中に書く（D{number:04d}）")
    report = spec_check.check_record(text)
    if report.legacy:
        problems.append(f"UR が無い（D0085 以降は要る。D{number:04d}）")
    else:
        shown = spec_check.format_report(report)
        problems += [line for line in shown[1:] if not line.startswith("問題 ")]
    return problems


def record_text(number: int, *, ur: bool = True, children: bool = True, unpointed_ur: bool = False, nfr_outside: bool = False) -> str:
    """見本の決定の記録。既定は、5つの見出しと新しい2つの見出しを持ち、鎖が全部つながった形。"""
    ac = f"D{number:04d}-AC-"
    lines = [f"# D{number:04d} 見本", "", "## 目的", "", "見本の目的。", ""]
    if children:
        lines += ["### 要求と前提", ""]
    if ur:
        lines += ["- UR-01 開発者として、何かしたい。"]
        if unpointed_ur:
            lines += ["- UR-02 開発者として、もう1つしたい。"]
    lines += ["", "答え：いいえ", "理由：文書の形だけ。", "", "## 機能要件と受け入れ基準", ""]
    lines += ["- FR-01（UR-01）すること" if ur else "- FR-01 すること", f"  - {ac}01（FR-01）基準", ""]
    if children and not nfr_outside:
        lines += ["### 非機能要件", "", "- 無し", ""]
    lines += ["## 決めたことと理由", "", "- 見本。", ""]
    if children and nfr_outside:
        lines += ["### 非機能要件", "", "- 無し", ""]
    lines += ["## 対象外・残った課題", "", "- 無し", "", "## 確かめたこと", "", "- 見本。", ""]
    return "\n".join(lines)


def test_D0085_AC_12_D0084はURが無くても通り_D0085の形でURを欠くと落ちる():
    """D0085-AC-12: 一時の記録で、D0084 は UR が無くても（新しい見出しが無くても）通り、D0085 以降の形で UR を欠くと落ちる。つながりが切れていても落ちる。"""
    old_form = record_text(84, ur=False, children=False)
    assert record_chain_problems(84, old_form) == []
    assert record_chain_problems(CHAIN_FROM - 1, old_form) == []

    assert record_chain_problems(85, record_text(85)) == []  # 守る：つながった形は通る（今の作りでも通る）

    for number in (85, 86, 120):
        problems = record_chain_problems(number, record_text(number, ur=False))
        assert any("UR" in p for p in problems), (number, problems)

    broken = record_chain_problems(85, record_text(85, unpointed_ur=True))
    assert any("指されない要求" in p and "UR-02" in p for p in broken), broken


def test_D0085_AC_12_D0085以降の実物の記録は鎖の検査を通る():
    """D0085-AC-12: docs/decisions/ の実物の記録のうち CHAIN_FROM 以上のすべてが、鎖の検査を通る。
    （赤の確かめは一時の記録の文字列のテストで行う。）"""
    problems: dict[str, list[str]] = {}
    for p in records():
        number = int(RECORD_NAME.fullmatch(p.name).group(1))
        if number >= CHAIN_FROM:
            found = record_chain_problems(number, p.read_text(encoding="utf-8"))
            if found:
                problems[p.name] = found
    assert problems == {}


def test_D0085_AC_12_始まりの番号の定数は1つ():
    """D0085-AC-12: 鎖の検査の始まりの番号は、このファイルの定数 CHAIN_FROM の1か所だけにある（85）。製品コードには置かない。"""
    assert CHAIN_FROM == 85
    source = Path(__file__).read_text(encoding="utf-8")
    assert len(re.findall(r"^CHAIN_FROM\s*=", source, flags=re.M)) == 1
    assert not [p.as_posix() for p in (ROOT / "pipe_in").rglob("*.py") if "CHAIN_FROM" in p.read_text(encoding="utf-8")]


def test_D0085_AC_13_D0085以降は新しい2つの見出しが無いと落ち_親の節の外でも落ちる():
    """D0085-AC-13: D0085 以降の記録に `### 要求と前提` と `### 非機能要件` が無いと落ちる。親の節（## 目的・## 機能要件と受け入れ基準）の外に書いても落ちる。"""
    missing = record_chain_problems(85, record_text(85, children=False))
    assert any("### 要求と前提" in p for p in missing), missing
    assert any("### 非機能要件" in p for p in missing), missing

    outside = record_chain_problems(85, record_text(85, nfr_outside=True))
    assert any("### 非機能要件" in p and "節の中" in p for p in outside), outside
    assert not any("### 要求と前提" in p for p in outside), outside


def test_D0085_AC_13_D0085より前の記録は新しい見出し無しで通る():
    """D0085-AC-13: D0085 より前の記録は、新しい2つの見出しが無くても、UR が無くても通る（書き換えない）。
    D0085 の記録が書かれたあとは、その記録自身も、この検査と鎖の検査を通る。"""
    for number in (2, 50, 84):
        assert record_chain_problems(number, record_text(number, ur=False, children=False)) == []
    own = [p for p in records() if RECORD_NAME.fullmatch(p.name).group(1) == f"{CHAIN_FROM:04d}"]
    for p in own:
        text = p.read_text(encoding="utf-8")
        assert record_chain_problems(CHAIN_FROM, text) == []
        assert [s for s in RECORD_SECTIONS if s not in text] == []


def test_D0085_AC_13_5つの見出しの検査は全部の記録にかかる_守る():
    """D0085-AC-13: 今ある5つの見出し（RECORD_SECTIONS）は変わらず、D0085 より前の記録にも、以降の記録にもかかる。
    今の作りでも通る（守り続けるための検査）。"""
    assert RECORD_SECTIONS == ["## 目的", "## 機能要件と受け入れ基準", "## 決めたことと理由", "## 対象外・残った課題", "## 確かめたこと"]
    for p in records():
        text = p.read_text(encoding="utf-8")
        assert [s for s in RECORD_SECTIONS if s not in text] == [], p.name
    assert all(s in record_text(85) for s in RECORD_SECTIONS)
