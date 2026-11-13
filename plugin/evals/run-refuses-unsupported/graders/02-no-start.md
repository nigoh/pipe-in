---
type: tool_used
tool: Bash
input_match: '"command"\s*:\s*"(?:[^"\\]|\\.)*?pipe-in-gen\s+chat\s+start\b(?!(?:[^"\\]|\\.)*--(?:dry-run|help))'
min: 0
max: 0
weight: 2
---
--dry-run も --help も無い chat start を流していない（人の答えの前に実行を始めない）。--dry-run のあとに && でつないだ本当の start にも当たる。
