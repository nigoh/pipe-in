---
type: regex
flags: i
pattern: '(?=[\s\S]*(?:始め|開始|start (?:it|the|now)|begin|proceed|go ahead))(?=[\s\S]*(?:やめ|中止|キャンセル|cancel|abort|stop))'
weight: 1
---
最後の返事で、始めるかやめるかを問うている（始める側の語とやめる側の語の両方がある）。「開始」「中止」と英語の言い方（start the run・cancel など）も数える。`pipe-in-gen chat start <パイプ名>` のコマンドの字だけでは、始める側の語に数えない。始めたと伝えるだけの返事は数えない。
