---
type: regex
target: trace
weight: 2
pattern: '✓ パイプ「notes-summary」: (?:問題ありません|誤りはありません（注意 [0-9]+ 件）)'
---
pipe-in-gen check が通った（成功の行が出た）。check を呼んだだけでは当たらない。この採点だけが落ちると、点が合格の線 0.8 を下回る（重み 2。合計 9 のうち 7）。
