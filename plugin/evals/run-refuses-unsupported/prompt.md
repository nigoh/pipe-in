---
name: run-refuses-unsupported
description: pipe-run は、会話の中で流せない形（group）のパイプでは、断る理由を見せて止まる
tags: [pipe-run, cheap, needs-bash, needs-pipe-in-gen]
expected_outcome: --dry-run の付いた chat start だけを流し、断る理由（group）を見せて止まる。記録を作らず、エージェントを呼ばない
max_turns: 15
timeout_seconds: 300
allowed_tools: [Read, Glob, Grep, Skill, Agent]
---
/pipe-in:pipe-run notes-parallel notes/ を並べて読んで

プラグインのフック（pipe-in-gen guard-hook）が入っていることは、/plugin で確かめ済みです。
