---
name: build-shows-table-first
description: pipe-build は、書き始める前に段の表を見せて確認を待つ
tags: [pipe-build, cheap, needs-bash, needs-pipe-in-gen]
expected_outcome: ファイルを書かず、パイプを流さず、pipe-builder にも任せずに、段の表を見せて確認を問う
max_turns: 15
timeout_seconds: 300
allowed_tools: [Read, Glob, Grep, Skill, Agent]
---
/pipe-in:pipe-build notes/ の Markdown を要約するパイプを作りたい。聞かずに決められることは決めて、段の表を見せて。
