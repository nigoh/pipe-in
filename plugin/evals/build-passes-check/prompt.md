---
name: build-passes-check
description: 確認済みの表を渡すと、pipe-builder に任せて pipe.toml と README.md を作り、pipe-in-gen check で検査する
tags: [pipe-build, agent, needs-bash, needs-write, needs-pipe-in-gen]
expected_outcome: pipe-builder がパイプを書き、pipe-in-gen check で検査し、パイプは流さない
max_turns: 40
timeout_seconds: 900
allowed_tools: [Read, Glob, Grep, Skill, Agent]
---
/pipe-in:pipe-build notes/ の Markdown を要約するパイプを作りたい。聞かずに決められることは決めて。

段の表は確認済み。そのまま pipe-builder に任せて。作ったパイプは流さないで。

- パイプ名：notes-summary
- 段は1つ

| 段 | 成果物 | 権限の拡大 | 検査 |
| --- | --- | --- | --- |
| summary | 01_summary.md | なし | なし |
