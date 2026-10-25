---
name: judge-rejects-bad-runs
description: pipe-judge は、範囲外の --runs 6 を審査役にも計算にも回さず、1〜5 だと伝える
tags: [pipe-judge, cheap, needs-pipe-in-gen]
expected_outcome: 審査役を呼ばず、点の計算もせず、runs は 1〜5 だと伝えて止まる
max_turns: 15
timeout_seconds: 300
allowed_tools: [Read, Glob, Grep, Skill, Agent]
---
/pipe-in:pipe-judge report.md --request request.md --runs 6
