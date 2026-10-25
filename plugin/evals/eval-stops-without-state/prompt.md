---
name: eval-stops-without-state
description: pipe-eval は、実行の記録（state.json）が無ければ検査せず、先にパイプを流すよう伝える
tags: [pipe-eval, cheap]
expected_outcome: コマンドを流さず、state.json が無いことを理由に、先にパイプを流すよう伝える
max_turns: 15
timeout_seconds: 300
allowed_tools: [Read, Glob, Grep, Skill]
---
/pipe-in:pipe-eval sample "python -c \"print('ok')\""
