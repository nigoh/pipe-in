---
name: run-dry-run-asks-first
description: pipe-run は、chat start --dry-run で段の表を見せて開始の確認を問い、始めない
tags: [pipe-run, cheap, needs-bash, needs-pipe-in-gen]
expected_outcome: --dry-run の付いた chat start だけを流し、段の表を見せて「始める」「やめる」を問い、記録を作らず、エージェントを呼ばない
max_turns: 15
timeout_seconds: 300
allowed_tools: [Read, Glob, Grep, Skill, Agent]
---
/pipe-in:pipe-run notes-digest notes/ の要点を短くまとめて

プラグインのフック（pipe-in-gen guard-hook）が入っていることは、/plugin で確かめ済みです。
