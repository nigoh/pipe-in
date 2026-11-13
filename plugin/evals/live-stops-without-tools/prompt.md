---
name: live-stops-without-tools
description: pipe-live は、Artifact・ArtifactData・Monitor が無い会話では、何も流さず書かずに、道具が無いことを伝えて止まる
tags: [pipe-live, cheap]
expected_outcome: pipe-in live page --out と pipe-in live watch を流さず、ファイルを書かず、Artifact・ArtifactData・Monitor が無いことを伝えて止まる
max_turns: 15
timeout_seconds: 300
allowed_tools: [Read, Glob, Grep, Skill]
---
/pipe-in:pipe-live --work-dir docs/pipeline/sample
