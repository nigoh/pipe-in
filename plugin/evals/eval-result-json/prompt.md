---
name: eval-result-json
description: pipe-eval は、流してよいと言われたら2つのコマンドを流し、結果を JSON で返す
tags: [pipe-eval, cheap, needs-bash]
expected_outcome: 2つとも流し、exit_code・passed・output_tail を持つ結果と、全体の verdict が fail であることを返す。ファイルは書かない
max_turns: 15
timeout_seconds: 300
allowed_tools: [Read, Glob, Grep, Skill]
---
/pipe-in:pipe-eval sample "python -c \"print('ok')\"" "python -c \"import sys; sys.exit(1)\""

一覧は確認済みで、2つとも流してよい。
