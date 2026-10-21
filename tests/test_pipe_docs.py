"""D0020: 何かを変えたら文書もそろえる仕組み（文書係 pipe-in-documenter・/pipe-docs・Stop の知らせ）。

- 文書係は文書だけを書ける（.claude/hooks/pipe_in_guard.py が絞る）。CLAUDE.md・.claude/・決定の記録は書けず、案を返す
- /pipe-docs は変えたファイルから直す文書を探して文書係に任せる。/pipe-in では検証で合格したあと、監査の前に流す
- Stop のフック（.claude/hooks/docs_reminder.py）は、コードを変えたのに文書が変わっていないとき、同じ変更の組では1回だけ知らせる
"""

from __future__ import annotations

import importlib.util
import io
import json
import re
import sys
from pathlib import Path

import pytest

import test_headless_audit

REPO = Path(__file__).parents[1]
ROOT = str(REPO)
GUARD = REPO / ".claude" / "hooks" / "pipe_in_guard.py"
REMINDER = REPO / ".claude" / "hooks" / "docs_reminder.py"
DOCUMENTER = "pipe-in-documenter"


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def guard():
    return load(GUARD, "pipe_in_guard")


@pytest.fixture(scope="module")
def reminder():
    return load(REMINDER, "docs_reminder")


def read(rel: str) -> str:
    return (REPO / rel).read_text(encoding="utf-8")


def front(rel: str) -> str:
    return read(rel).split("---")[1]


def call(guard, tool, **tool_input):
    payload = {"tool_name": tool, "tool_input": tool_input, "cwd": ROOT, "agent_type": DOCUMENTER}
    return guard.decide(payload, root=ROOT)


# ---- 文書係の定義 ---------------------------------------------------------------------------


def test_d0020_ac01_documenter_definition_tools():
    """D0020-AC-01: pipe-in-documenter の定義があり、tools: がちょうど Read・Grep・Glob・Write・Edit（Bash・Web なし）。"""
    head = front(f".claude/agents/{DOCUMENTER}.md")
    assert re.search(rf"^name:\s*{DOCUMENTER}\s*$", head, re.M)
    tools = {t.strip() for t in re.search(r"^tools:\s*(.+)$", head, re.M).group(1).split(",")}
    assert tools == {"Read", "Grep", "Glob", "Write", "Edit"}


DOCUMENTER_WORDS = [
    "workflow.md", "4. そろえる",
    "README.md", "docs/guide/", "docs/development/", "vscode/README.md", "pipes/README.md",
    "CLAUDE.md", ".claude/", "docs/decisions/", "書けない", "案",
    "コードは直さない", "文書の報告", "直さなくてよい", "公開",
]


def test_d0020_ac02_documenter_definition_states_scope_and_report():
    """D0020-AC-02: 定義に、そろえる表・書ける文書・書けないもの（案を返す）・コードは直さない・報告の形が書いてある。"""
    text = read(f".claude/agents/{DOCUMENTER}.md")
    missing = [w for w in DOCUMENTER_WORDS if w not in text]
    assert missing == []


# ---- フック：文書係は文書だけを書ける ---------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "README.md",
        "vscode/README.md",
        "pipes/README.md",
        "docs/assets/README.md",
        "docs/guide/usage.md",
        "docs/guide/new-page.md",
        "docs/development/design.md",
        f"{ROOT}/docs/guide/vscode.md",
    ],
)
def test_d0020_ac03_documenter_can_write_docs(guard, path):
    """D0020-AC-03: 文書係は README.md・docs/guide/・docs/development/ の .md・vscode/README.md・pipes/README.md・docs/assets/README.md を書ける。"""
    assert call(guard, "Write", file_path=path, content="x") is None
    assert call(guard, "Edit", file_path=path, old_string="a", new_string="b") is None


@pytest.mark.parametrize(
    "path",
    [
        "CLAUDE.md",
        "CLAUDE.local.md",
        ".claude/skills/pipe-help/SKILL.md",
        ".claude/agents/pipe-in-documenter.md",
        ".claude/settings.json",
        ".claude/hooks/pipe_in_guard.py",
        "docs/decisions/D0020-docs-sync.md",
        "docs/decisions/README.md",
        "docs/pipeline/05_test_report.md",
        "docs/research/README.md",
        "docs/guide/script.py",
        "docs/development/x.json",
        "docs/assets/logo.svg",
        "pipe_in/cli.py",
        "generator/guard_hook.py",
        "vscode/src/extension.ts",
        "vscode/package.json",
        "tests/test_x.py",
        "plugin/skills/pipe-build/SKILL.md",
        ".env",
        ".git/config",
        "/etc/passwd",
        "../outside/README.md",
        "docs/guide/../../pipe_in/cli.py",
    ],
)
def test_d0020_ac04_documenter_cannot_write_elsewhere(guard, path):
    """D0020-AC-04: 文書係は、文書のほか（CLAUDE.md・.claude/・決定の記録・記録・コード・テスト・プロジェクトの外）は書けない。"""
    reason = call(guard, "Write", file_path=path, content="x")
    assert reason and "書けるのは" in reason


@pytest.mark.parametrize(
    "tool,tool_input",
    [
        ("Bash", {"command": "python -m pytest -q"}),
        ("Bash", {"command": "git status"}),
        ("PowerShell", {"command": "Set-Content README.md x"}),
        ("NotebookEdit", {"notebook_path": "x.ipynb", "new_source": "x"}),
        ("Agent", {"subagent_type": "pipe-in-coder", "prompt": "x"}),
        ("mcp__github__create_or_update_file", {"path": "README.md"}),
        ("WebFetch", {"url": "https://code.claude.com/docs/ja/sub-agents", "prompt": "x"}),
        ("WebSearch", {"query": "x", "allowed_domains": ["code.claude.com"]}),
    ],
)
def test_d0020_ac05_documenter_bypass_routes_are_denied(guard, tool, tool_input):
    """D0020-AC-05: 文書係の Bash・PowerShell・NotebookEdit・Agent・MCP・Web は止まる（すり抜けの道を開けない）。"""
    assert call(guard, tool, **tool_input)


@pytest.mark.parametrize("tool", ["Read", "Glob", "Grep", "SubagentHandback"])
def test_d0020_ac05_documenter_can_read_and_hand_back(guard, tool):
    """D0020-AC-05: 文書係の読む道具と報告を返す道具は通る。"""
    assert call(guard, tool, file_path="README.md", pattern="x") is None


def test_d0020_ac06_main_entry_denies_documenter_code_write(guard, monkeypatch):
    """D0020-AC-06: フックの入口を通しても、文書係のコードへの書き込みは deny の JSON になり、文書への書き込みは何も出さない。"""

    def run(path: str) -> str:
        payload = {"tool_name": "Write", "tool_input": {"file_path": path, "content": "x"}, "cwd": ROOT, "agent_type": DOCUMENTER}
        raw = io.BytesIO()
        monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(json.dumps(payload).encode("utf-8")), encoding="utf-8"))
        monkeypatch.setattr(sys, "stdout", io.TextIOWrapper(raw, encoding="utf-8"))
        assert guard.main() == 0
        sys.stdout.flush()
        return raw.getvalue().decode("utf-8")

    out = json.loads(run("pipe_in/cli.py"))
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert run("docs/guide/usage.md") == ""


def test_d0020_ac06_guard_docstring_lists_documenter():
    """D0020-AC-06: フックの説明（先頭の docstring）に文書係の書ける場所が書いてある。"""
    doc = read(".claude/hooks/pipe_in_guard.py").split('"""')[1]
    assert DOCUMENTER in doc


# ---- /pipe-docs のスキル ---------------------------------------------------------------------


def test_d0020_ac07_pipe_docs_skill():
    """D0020-AC-07: /pipe-docs があり、モデルからも呼べ（何か変えたあとに自分で流せる）、任せる先・変えたファイルの集め方・テストの流し直し・コミットしないことが書いてある。"""
    head = front(".claude/skills/pipe-docs/SKILL.md")
    assert re.search(r"^name:\s*pipe-docs\s*$", head, re.M)
    assert not re.search(r"^disable-model-invocation:\s*true\s*$", head, re.M)
    assert re.search(r"^allowed-tools:.*Agent\(pipe-in-documenter\)", head, re.M)
    text = read(".claude/skills/pipe-docs/SKILL.md")
    words = [
        DOCUMENTER, "git diff --name-only main...HEAD", "git status --short", "4. そろえる",
        "CLAUDE.md", "/pipe-help", "承認", "決定の記録", "テストを流し直す", "コミットはしない",
    ]
    missing = [w for w in words if w not in text]
    assert missing == []


# ---- /pipe-in に組み込む ------------------------------------------------------------------------


def test_d0020_ac08_pipe_in_runs_documenter_before_audit():
    """D0020-AC-08: /pipe-in で、検証で合格したあと、監査の前に文書係を流す節があり、役割の表にも行がある。"""
    text = read(".claude/skills/pipe-in/SKILL.md")
    part = test_headless_audit.section(text, "文書をそろえる")
    for word in (DOCUMENTER, "合格したあと", "監査の前", "--auto", "テストを流し直す"):
        assert word in part, word
    assert text.index("### 文書をそろえる") < text.index("### 監査と助言")
    assert any(line.startswith("|") and DOCUMENTER in line for line in text.splitlines())


# ---- Stop の知らせ -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path,kind",
    [
        ("pipe_in/cli.py", "code"),
        ("generator/guard_hook.py", "code"),
        ("vscode/src/extension.ts", "code"),
        ("vscode/scripts/preview.ts", "code"),
        ("vscode/package.json", "code"),
        ("pyproject.toml", "code"),
        ("plugin/skills/pipe-build/SKILL.md", "code"),
        (".claude-plugin/marketplace.json", "code"),
        (".claude/settings.json", "code"),
        (".claude/agents/pipe-in-coder.md", "code"),
        (".claude/skills/pipe-in/SKILL.md", "code"),
        (".claude/hooks/pipe_in_guard.py", "code"),
        ("README.md", "doc"),
        ("CLAUDE.md", "doc"),
        ("vscode/README.md", "doc"),
        ("pipes/README.md", "doc"),
        ("docs/assets/README.md", "doc"),  # 文書係が書ける文書はすべて文書に数える（監査 A-01）
        ("docs/guide/usage.md", "doc"),
        ("docs/development/design.md", "doc"),
        ("docs/decisions/D0020-docs-sync.md", "doc"),
        (".claude/skills/pipe-help/SKILL.md", "doc"),
        ("tests/test_x.py", None),
        ("vscode/src/domain/runs.test.ts", None),
        ("vscode/src/test/helpers.ts", None),
        ("docs/pipeline/state.json", None),
        ("docs/research/README.md", None),
        ("package-lock.json", None),
    ],
)
def test_d0020_ac09_classify(reminder, path, kind):
    """D0020-AC-09: 変えたファイルを、コード（文書をそろえる元）・文書・どちらでもない（テスト・記録など）に分ける。"""
    assert reminder.classify(path) == kind


def test_d0020_ac10_parse_porcelain(reminder):
    """D0020-AC-10: git status --porcelain -z の出力から、変わった・足した・消した・名前を変えた先のパスを取る。"""
    out = " M pipe_in/cli.py\0?? docs/guide/new.md\0R  vscode/src/new.ts\0vscode/src/old.ts\0 D README.md\0"
    assert reminder.parse_porcelain(out) == ["pipe_in/cli.py", "docs/guide/new.md", "vscode/src/new.ts", "README.md"]
    assert reminder.parse_porcelain("") == []


def test_d0020_ac11_reminds_when_code_changed_without_docs(reminder):
    """D0020-AC-11: コードを変えて文書が変わっていなければ、理由（変えたファイル・そろえる表・/pipe-docs・要らないときの扱い）を返す。"""
    reason, mark = reminder.decide(["pipe_in/cli.py", "tests/test_x.py"], stop_hook_active=False, seen=None)
    assert reason and mark
    for word in ("pipe_in/cli.py", "4. そろえる", "/pipe-docs", "理由"):
        assert word in reason, word
    assert "tests/test_x.py" not in reason


@pytest.mark.parametrize(
    "changed,active",
    [
        (["pipe_in/cli.py", "docs/guide/usage.md"], False),  # 文書も変えた
        (["pipe_in/cli.py", "docs/decisions/D0020-docs-sync.md"], False),  # 決定の記録も文書に数える
        (["tests/test_x.py", "docs/pipeline/state.json"], False),  # コードを変えていない
        ([], False),
        (["pipe_in/cli.py"], True),  # 知らせのあとの止まり（くり返さない）
    ],
)
def test_d0020_ac12_stays_quiet(reminder, changed, active):
    """D0020-AC-12: 文書も変えた・コードを変えていない・知らせのあとの止まり（stop_hook_active）のときは知らせない。"""
    reason, _ = reminder.decide(changed, stop_hook_active=active, seen=None)
    assert reason is None


def test_d0020_ac13_reminds_once_per_change_set(reminder):
    """D0020-AC-13: 同じ変更の組では1回だけ知らせ、コードの変更の組が変わったらまた知らせる。"""
    reason, mark = reminder.decide(["pipe_in/cli.py"], stop_hook_active=False, seen=None)
    assert reason
    again, _ = reminder.decide(["pipe_in/cli.py", "tests/test_x.py"], stop_hook_active=False, seen=mark)
    assert again is None
    other, other_mark = reminder.decide(["pipe_in/cli.py", "pipe_in/dev/record.py"], stop_hook_active=False, seen=mark)
    assert other and other_mark != mark


def run_main(reminder, monkeypatch, tmp_path, payload, changed):
    state = tmp_path / "state.txt"
    monkeypatch.setattr(reminder, "changed_files", lambda root: changed)
    monkeypatch.setattr(reminder, "state_path", lambda root: state)
    raw = io.BytesIO()
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(json.dumps(payload).encode("utf-8")), encoding="utf-8"))
    monkeypatch.setattr(sys, "stdout", io.TextIOWrapper(raw, encoding="utf-8"))
    assert reminder.main() == 0
    sys.stdout.flush()
    return raw.getvalue().decode("utf-8"), state


def test_d0020_ac14_main_blocks_once(reminder, monkeypatch, tmp_path):
    """D0020-AC-14: 入口は Stop の block の JSON を1回だけ出し、目印をリポジトリの外（渡された場所）に書く。2回目は何も出さない。"""
    payload = {"hook_event_name": "Stop", "cwd": ROOT, "stop_hook_active": False}
    out, state = run_main(reminder, monkeypatch, tmp_path, payload, ["pipe_in/cli.py"])
    data = json.loads(out)
    assert data["decision"] == "block" and "/pipe-docs" in data["reason"]
    assert state.is_file()
    out2, _ = run_main(reminder, monkeypatch, tmp_path, payload, ["pipe_in/cli.py"])
    assert out2 == ""


def test_d0020_ac14_main_is_quiet_when_git_fails(reminder, monkeypatch, tmp_path):
    """D0020-AC-14: git が読めない（None）・入力が読めないときは、何も出さずに 0 で終える（知らせのために人の作業を止めない）。"""
    payload = {"hook_event_name": "Stop", "cwd": ROOT}
    out, state = run_main(reminder, monkeypatch, tmp_path, payload, None)
    assert out == "" and not state.exists()
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(b"not json"), encoding="utf-8"))
    raw = io.BytesIO()
    monkeypatch.setattr(sys, "stdout", io.TextIOWrapper(raw, encoding="utf-8"))
    assert reminder.main() == 0
    sys.stdout.flush()
    assert raw.getvalue() == b""


def test_d0020_ac14_state_path_is_outside_the_repo(reminder):
    """D0020-AC-14: 目印の置き場所は、リポジトリの外（一時フォルダ）で、作業フォルダごとに分かれる。"""
    a = reminder.state_path(ROOT)
    b = reminder.state_path(ROOT + "-other")
    assert REPO.resolve() not in a.resolve().parents
    assert a != b


def test_d0020_ac15_reminder_uses_only_the_standard_library():
    """D0020-AC-15: 知らせのフックは標準ライブラリだけを使う（Stop のたびに動くので軽くする）。"""
    src = read(".claude/hooks/docs_reminder.py")
    imports = set(re.findall(r"^(?:from|import) ([a-zA-Z_]+)", src, re.M))
    assert imports <= {"__future__", "hashlib", "json", "os", "subprocess", "sys", "tempfile", "pathlib", "typing"}


def test_d0020_ac16_settings_register_stop_hook_and_allow_documenter():
    """D0020-AC-16: settings.json に Stop のフック（docs_reminder.py）と Agent(pipe-in-documenter) の許可がある。"""
    settings = json.loads(read(".claude/settings.json"))
    stops = settings["hooks"]["Stop"]
    assert any("docs_reminder.py" in h.get("command", "") for e in stops for h in e["hooks"])
    assert f"Agent({DOCUMENTER})" in settings["permissions"]["allow"]


# ---- 文書をそろえる ----------------------------------------------------------------------------


def test_d0020_ac17_docs_mention_the_new_parts():
    """D0020-AC-17: /pipe-help・design.md の置き場所の表・workflow.md の「4. そろえる」・CLAUDE.md に、新しいものが書いてある。"""
    assert "/pipe-docs" in read(".claude/skills/pipe-help/SKILL.md")
    rows = "\n".join(line for line in read("docs/development/design.md").splitlines() if line.startswith("|"))
    for word in (".claude/skills/pipe-docs/", DOCUMENTER, ".claude/hooks/docs_reminder.py"):
        assert word in rows, word
    sync = test_headless_audit.section(read("docs/development/workflow.md"), "4. そろえる")
    for word in ("/pipe-docs", DOCUMENTER, "docs_reminder.py"):
        assert word in sync, word
    claude = read("CLAUDE.md")
    for word in ("/pipe-docs", DOCUMENTER):
        assert word in claude, word
