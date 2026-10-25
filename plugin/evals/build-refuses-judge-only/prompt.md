---
name: build-refuses-judge-only
description: 審査（judge）だけの検査で自分に戻す表を渡されても、command と組む形に直すか差し戻す
tags: [pipe-build, agent, needs-bash, needs-write, needs-pipe-in-gen]
expected_outcome: command の無い judge だけの検査で on_fail を書いたパイプを作らず、command と組む案内か差し戻しを返す
max_turns: 40
timeout_seconds: 900
allowed_tools: [Read, Glob, Grep, Skill, Agent]
---
/pipe-in:pipe-build notes/ の Markdown を見直すパイプを作りたい。聞かずに決められることは決めて。

段の表は確認済み。そのまま作って。作ったパイプは流さないで。

- パイプ名：notes-review
- 段は1つ

| 段 | 成果物 | 権限の拡大 | 検査 |
| --- | --- | --- | --- |
| review | 01_review.md | なし | check は審査（judge）だけ。落ちたら on_fail で review に戻す |
