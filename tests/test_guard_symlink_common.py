"""D0087 共通：4つの守りの比較の表（tests/guard_matrix.py）で、リンクを経た道の2行がどの列でも止まる。

表の評価（実際の結果が表のとおりか）は tests/test_guard_matrix.py が見る。ここは、リンクの行の「期待」そのものと、
リンク以外の行の期待が書き換わっていないことを固定する。
"""

from __future__ import annotations

from guard_matrix import COLUMNS, EXPECT, LINK_ROWS, ROWS

# リンク以外の行の期待（D0083・D0084・D0086 の実測。書き換えないことの固定）
UNCHANGED = {
    "write-code-ok": "AAADDDDAD",
    "write-test-ok": "AAADDDADD",
    "write-docs-ok": "AAADDDDAD",
    "write-output-ok": "AAADDDDDD",
    "read-ok": "AAAAAAAAA",
    "bash-pytest-ok": "AAADDDAAA",
    "bash-git-add": "AAADDDDDD",
    "bash-git-commit": "AAADDDDDD",
    "bash-git-push": "DDDDDDDDD",
    "bash-pipe-in-gen-list": "AAAADDDDD",
    "write-pipes-prompt": "AAAADDDAD",
    "write-pipes-toml": "AAAADDDAD",
    "write-pipes-readme": "AAAADDDAD",
    "skill": "AADDDDDDD",
    "agent-listed": "AA-DDDDDD",
    "task-listed": "AA-DDDDDD",
    "agent-not-listed": "DDDDDDDDD",
    "agent-background": "DD-DDDDDD",
    "agent-nested": "DD-DDDDDD",
    "write-dotclaude": "DDDDDDDDD",
    "write-dotgit": "DDDDDDDDD",
    "write-dotpipein": "DDDDDDDAD",
    "write-pipelinetoml": "DDDDDDDAD",
    "write-mcpjson": "DDDDDDDAD",
    "write-running-pipe-toml": "DDDADDDAD",
    "write-running-pipe-prompt": "DDDADDDAD",
    "write-record": "DDDDDDDDD",
    "write-outside": "DDDDDDDDD",
    "bypass-rel": "DDDDDDDDD",
    "bypass-dotdot-abs": "DDDDDDDDD",
    "bypass-dotdot-rel": "DDDDDDDDD",
    "bypass-edit": "DDDDDDDDD",
    "bypass-multiedit": "DDDDDDDDD",
    "bypass-notebookedit": "DDDDDDDDD",
    "bypass-subagent-write": "DDDDDDDDD",
    "bypass-powershell": "DDDDDDDDD",
    "bypass-mcp": "DDDDDDDDD",
    "bypass-bash-redirect": "DDDDDDDDD",
    "bypass-bash-tee": "DDDDDDDDD",
    "bypass-bash-cp": "DDDDDDDDD",
    "bypass-bash-sed-i": "DDDDDDDDD",
    "bypass-bash-python-c": "DDDDDDDDD",
    "bypass-bash-bash-c": "DDDDDDDDD",
    "bypass-bash-subst": "DDDDDDDDD",
}


def test_d0087_ac13_link_rows_expect_all_deny():
    """D0087-AC-13: リンクを経た道の2行（bypass-link-src・bypass-link-pipe-prompt）は、9 つの列のすべてで止める（D）。
    プラグインのフックと開発用のフックも先をたどるので、期待は全部の列で止める（DDDDDDDDD）。表の評価は既存の
    test_d0083_ac02_symlink_row_records_actual_result が見る。"""
    assert LINK_ROWS == {"bypass-link-src", "bypass-link-pipe-prompt"}
    for rid in sorted(LINK_ROWS):
        assert EXPECT[rid] == "D" * len(COLUMNS), f"{rid}: {EXPECT[rid]}"
    assert {r.id: r.expect for r in ROWS if r.id in LINK_ROWS} == {rid: "D" * len(COLUMNS) for rid in LINK_ROWS}


def test_d0087_ac14_other_rows_unchanged():
    """D0087-AC-14: リンク以外の行の期待は書き換えない（今の値のまま。表に行が足されても落ちないよう、ここにある行の値だけを固定する）。"""
    for rid, want in UNCHANGED.items():
        assert EXPECT[rid] == want, f"{rid}: 表 {EXPECT[rid]} / 固定 {want}"
    assert not (LINK_ROWS & set(UNCHANGED))
