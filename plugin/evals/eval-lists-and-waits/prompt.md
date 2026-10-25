---
name: eval-lists-and-waits
description: pipe-eval は、渡されたコマンドの一覧を見せて、流してよいかの返事を待つ
tags: [pipe-eval, cheap]
expected_outcome: 渡されたコマンドを1つも流さず、一覧（コマンド・作業フォルダ・timeout_sec）を見せて、流してよいかを問う
max_turns: 15
timeout_seconds: 300
allowed_tools: [Read, Glob, Grep, Skill]
---
/pipe-in:pipe-eval sample "python -c \"print('ok')\"" "python -c \"import sys; sys.exit(1)\""
