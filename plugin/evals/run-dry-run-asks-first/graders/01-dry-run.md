---
type: tool_used
tool: Bash
input_match: '"command"\s*:\s*"(?:[^"\\]|\\.)*?pipe-in-gen\s+chat\s+start\b(?:[^"\\]|\\.)*?--dry-run'
min: 1
weight: 2
---
--dry-run の付いた chat start を流した（段の表と断る理由を、記録を作らずに見た）。コマンドの文字列の中だけを読み、説明の文の --dry-run には当たらない。
