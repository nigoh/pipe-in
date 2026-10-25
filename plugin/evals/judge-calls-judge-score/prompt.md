---
name: judge-calls-judge-score
description: pipe-judge は、審査役を呼び、点の計算は pipe-in-gen judge-score にさせる
tags: [pipe-judge, agent, needs-bash, needs-pipe-in-gen]
expected_outcome: 審査役（pipe-judge）に採点させ、合計は pipe-in-gen judge-score で計算し、overall・verdict・threshold を含む結果を返す。成果物は直さない
max_turns: 40
timeout_seconds: 900
allowed_tools: [Read, Glob, Grep, Skill, Agent]
---
/pipe-in:pipe-judge report.md --request request.md
