"""D0076-AC-10：generator/quorum.py の依存と、cli からの呼ばれ方。

決定ごとの別ファイルの決まり（D0075）。共有の部品は tests/test_architecture.py のものを import する。
今の作りのままで通るテストは、名前の末尾を _守る にする。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from test_architecture import _imports, _module_name, _outside_stdlib  # noqa: PLC2701

ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "generator"
MODULE = "pipe_in_generator.quorum"
ALLOWED_INTERNAL = {"pipe_in_generator.findings_check"}


def disallowed_imports(path: Path, module: str) -> list[str]:
    """標準ライブラリと generator/findings_check.py のほかを読み込んでいる import。"""
    out = []
    for target in _imports(path, module):
        if not target:
            continue
        top = target.split(".")[0]
        # from .findings_check import X は "pipe_in_generator.findings_check.X" と読まれる
        if top in sys.stdlib_module_names or top == "__future__" or any(target == a or target.startswith(a + ".") for a in ALLOWED_INTERNAL):
            continue
        out.append(target)
    return sorted(set(out))


def test_d0076_ac10_quorum_uses_only_stdlib_and_findings_check():
    """D0076-AC-10: generator/quorum.py は標準ライブラリと generator/findings_check.py のほかを読み込まない（本体 pipe_in.* も SDK も読まない）。"""
    path = GENERATOR / "quorum.py"
    assert path.is_file(), "generator/quorum.py がありません（まだ作っていない）"
    assert disallowed_imports(path, _module_name(path, GENERATOR, "pipe_in_generator")) == []
    assert _outside_stdlib(path, MODULE) in ([], ["pipe_in_generator"])  # 外側は findings_check だけ（上の検査が名前まで見る）


def test_d0076_ac10_quorum_does_not_call_sdk_or_child_process():
    """D0076-AC-10: quorum.py の文に SDK の名前も子プロセスの呼び出しも無い。"""
    path = GENERATOR / "quorum.py"
    assert path.is_file(), "generator/quorum.py がありません（まだ作っていない）"
    source = path.read_text(encoding="utf-8")
    for word in ("claude_agent_sdk", "anthropic", "subprocess", "os.system", "asyncio"):
        assert word not in source, word


def test_d0076_ac10_import_check_finds_forbidden_imports_守る(tmp_path):
    """D0076-AC-10: 今の作りのままで通る。検査そのものが、本体・SDK・findings_check 以外の兄弟を読み込む import を見つける。"""
    ok = tmp_path / "ok.py"
    ok.write_text("from __future__ import annotations\nimport json\nfrom .findings_check import InputError\n", encoding="utf-8")
    assert disallowed_imports(ok, "pipe_in_generator.ok") == []
    bad = tmp_path / "bad.py"
    bad.write_text(
        "import json\nimport claude_agent_sdk\nfrom pipe_in.engine import guard\nfrom .cli import main\nfrom .detect import x\n",
        encoding="utf-8",
    )
    found = disallowed_imports(bad, "pipe_in_generator.bad")
    assert "claude_agent_sdk" in found
    assert any(t.startswith("pipe_in.engine") for t in found)
    assert "pipe_in_generator.cli" in found and "pipe_in_generator.detect" in found


def test_d0076_ac10_cli_dispatches_quorum_without_project(tmp_path, capsys, monkeypatch):
    """D0076-AC-10: pipe-in-gen quorum が cli.py から呼ばれ、--project を必要としない（存在しない対象でも、対象を探さずに動く）。"""
    from pipe_in_generator import cli

    def doc(*secs):
        findings = [
            {"id": f"F-{i + 1:03d}", "role": "quality", "location": {"source": "SRC-001", "section": s, "quote": "x"}, "kind": "missing"}
            for i, s in enumerate(secs)
        ]
        return json.dumps({"v": 1, "findings": findings}, ensure_ascii=False)

    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    a.write_text(doc("1", "2"), encoding="utf-8")
    b.write_text(doc("1", "2"), encoding="utf-8")
    work = tmp_path / "cwd-without-project"
    work.mkdir()
    monkeypatch.chdir(work)  # .pipe-in も pyproject.toml も無いフォルダ
    capsys.readouterr()
    code = cli.main(["quorum", str(a), str(b), "--out", str(tmp_path / "out.json")])
    cap = capsys.readouterr()
    assert code == 0, cap.err
    assert (tmp_path / "out.json").is_file()
    assert "共通部分" in cap.out


def test_d0076_ac10_help_lists_quorum(capsys):
    """D0076-AC-10: pipe-in-gen --help のコマンドの一覧に quorum が出る。"""
    from pipe_in_generator import cli

    capsys.readouterr()
    try:
        cli.main(["--help"])
    except SystemExit:
        pass
    assert "quorum" in capsys.readouterr().out
