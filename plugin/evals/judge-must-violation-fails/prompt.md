---
name: judge-must-violation-fails
description: pipe-judge は、must の項目に違反した報告を fail にし、根拠に違反の引用を書く
tags: [pipe-judge, agent, needs-bash, needs-pipe-in-gen]
expected_outcome: ほかが良い出来でも must 違反（禁止語）で verdict を fail にし、must_violations に禁止語の引用を入れる
max_turns: 40
timeout_seconds: 900
allowed_tools: [Read, Glob, Grep, Skill, Agent]
---
/pipe-in:pipe-judge report.md --request request.md --rubric rubric.md
