# プラグインの eval のラウンド

プラグイン（`plugin/`）自身の eval（`plugin/evals/`・`claude plugin eval`。[D0045](../../decisions/D0045-plugin-evals.md)）を、下位のモデル（haiku。審査役も haiku）で回し、落ちた所を直してまた回した記録です。この 1 回を「ラウンド」と呼びます。回し方の手順は[ガイドの「ラウンドの回し方」](../../guide/plugin.md#ラウンドの回し方下位のモデルで)にもあります。

## 問い

- haiku（審査役も haiku）でプラグインの eval を回し、落ちた所を直してまた回すと、スキルとエージェントが手順どおりに動くようになるか。
- 落ちた採点は、スキルの不具合・ケースの不具合・環境のどれによるか。

## 結論

ラウンド 1a から 5 までと止める前の確かめ、蒸留の前後（D0097）、採点の取りこぼしの直し（D0098）の結論です（haiku・審査役も haiku）。

1. 9 本の 5/9（0.68）から始め、12 本の 12/12（1.00）まで上がった（ラウンド 4）。止める前の `--runs 3` では 11/12（0.96）で、judge-rejects-bad-runs が 3 回のうち 1 回だけ落ちた。監査と助言の直しのあとのラウンド 5 も 12/12（1.00）だった。1 回で 9〜12 本を回す費用（定価での見積もり。プランの利用枠の減り方とは別）は $0.11 前後（環境で早く落ちた 1a の $0.04 を除く）、`--runs 3` で $0.29。
2. 落ちた採点の原因は、環境（入れ方・root）・ケース（偽の合格・採点の誤り・言い回しと glob）・スキルの 3 つに分かれた。ラウンド 1a の 4 本は環境だけで、入れ直した 1b から、ほんとうに直す所が見えた。
3. スキルの不具合は、どれも「決まりを書いた所を読み飛ばす」型だった：範囲の外の `--runs` を断る（pipe-judge）・計算の JSON をそのまま返す（pipe-judge）・審査だけで差し戻す表を任せない（pipe-build）。手順の頭に短い文で置き、返す形の見本を書くと、ラウンドでは通るようになった。ただし `--runs 3` では、断る決まりを 3 回に 1 回読み飛ばした。文だけで頼る決まりは、haiku では揺れが残る。
4. 文の決まりの後ろに、機械の検査を置くと揺れに強い。審査だけで差し戻す形は、スキルと pipe-builder の文で止めるほか、`pipe-in-gen check` の警告 W8 で、書かれても分かるようにした。
5. Claude Code は、サブエージェントからの `report`・`summary`・`findings`・`analysis` で始まる `.md` の書き込みを断る（本体の決まり。公式の cookbook https://platform.claude.com/cookbook/claude-agent-sdk-08-dynamic-workflows に観察として 1 文あるが、語の一覧と判定の形は書かれていない）。pipe-builder の指示文と、会話の中で流す段の成果物が当たるので、名前の決まり（頭に番号）と、会話の道で流す前に断る形を足した。
6. 採点は「呼んだ」ではなく「通った」を見る。ラウンドを重ねると、書けない環境で隠れていた不具合（ラウンド 3 の審査だけの形）が、手書きへの切り替えで表に出た。採点を直すと、隠れていた不具合が見えるようになる。
7. 文を縮める（蒸留する）と、理由の 1 文が haiku の動きを決めていたことがある。D0097 では、pipe-builder の「Bash の中からは書けなくても、Write では書けることがある」を削ると、`new` の失敗のあと手で書かずに戻るようになり、ラウンドで見つかった。決まりの語だけでなく、動きを決める理由の文も残す。蒸留の前後を同じコマンドで比べると、こうした崩れが見える（最初は `--runs 3`、最後の比べは前後とも同じ採点・`--runs 6`）。決まりの一覧の目印の外で落ちた決まりは、監査が前後の文を突き合わせて見つけた。
8. 言い回しの採点の取りこぼしは、12 回に 1 回ほどの返事の形で起きるので、ラウンドの点だけでは確かめきれない。直す前と後の `pattern` を、残した記録の同じ返事に当てると、利用料なしで確かめられた（D0098。72 回で、直す前の `pattern` と記録の合否の食い違いが 0 回だったので、取り出し方も確かめられた）。直したあとのラウンドでも、新しい言い回し（「〜ず」）の取りこぼしが 1 回出た。

## 方法

- 環境：Linux のコンテナ（root）、Claude Code 2.1.323。`pipe-in-gen` は、1a は編集用の入れ方（`pip install -e .`）、1b からは `pip install --no-deps .` で入れ直した。
- コマンド：`claude plugin eval ./plugin --scaffold --trust-plugin --allow-tools Bash Write Edit --model haiku --judge-model haiku --runs 1 --ablation none -j 3〜4 --no-publish`。結果の JSON と `--output-dir` は `plugin/` の外に置き、コミットしない。
- 費用の上限：ラウンド 2 からは各回 `--max-cost-usd 0.5`。止める前の確かめ（`--runs 3 --threshold 0.8`）は `--max-cost-usd 1.5`。
- 止めどき：全ケースが合格した回が出るか、ラウンド 5 まで。止める前に、全ケースを `--runs 3 --threshold 0.8`（haiku・審査役 haiku）で 1 回流す。
- 落ちた採点の分け方：スキルの不具合（スキルやエージェントの文で直す）・ケースの不具合（採点の誤り・偽の合格。ケースで直す）・環境（入れ方・root・サンドボックス。直さずに書き残す）。スキルとケースは、テストを先に直してから直す。
- 集計：`rounds.py`（このフォルダ）で、結果の JSON からケースごとの点・合格の回・落ちた採点・前の回との差の表を出す。ラウンド 1 の表は、`rounds.py` を作る前の回なので、結果の数から手で写した。途中で止まった回（`partial`）のケースと、審査の採点を飛ばした回（`skippedPaidGraders`）を含むケースの差は「比べられない」と出し、途中で止まった回の次は、その前の途中で止まっていない一番近い回と比べる（公式の文書の勧め。ラウンド 1b〜4 と止める前の回の本物の結果では、どれも `false` だった）。
- 書かないもの：手元のパス・ユーザー名・メールアドレス・鍵・モデルの返事の生の文。ここに書くのはケース名・採点のファイル名・数・合否だけ。

## 結果

### ラウンド 1a

- 合格 5/9・全体の点 0.68・費用 $0.04・時間 57 秒（9 本・`pip install -e .` のまま）。

| ケース | 点 | 合否 | 原因 |
| --- | --- | --- | --- |
| build-passes-check | 0.17 | 不合格 | 環境：入れ方 |
| build-refuses-judge-only | 0.67 | 不合格 | 環境：入れ方 |
| judge-calls-judge-score | 0.25 | 不合格 | 環境：入れ方 |
| judge-must-violation-fails | 0.00 | 不合格 | 環境：入れ方 |
| ほかの 5 本 | — | 合格 | — |

- 落ちた 4 本は、サンドボックスの Bash から `pipe-in-gen` を起こすと `ModuleNotFoundError: No module named 'pipe_in_generator'` になった。編集用の入れ方は元のフォルダを指すだけで、そのフォルダがサンドボックスから見えないため。スキルは手順どおり、`pipe-in-gen` が動かないところで止まった。
- 直したこと：入れ方を `pip install --no-deps .` に替えて 1b を回した。ガイドの入れ方と、見本を作る `scaffold.py` の案内の文を `pip install .` にした。

### ラウンド 1b

- 合格 5/9・全体の点 0.84・費用 $0.11・時間 109 秒（9 本・`pip install --no-deps .` で入れ直した）。
- 1 本あたりの費用：安いケースは約 $0.004、エージェントを使うケースは約 $0.015〜$0.03。

| ケース | 点 | 合否 | 落ちた採点 | 原因 |
| --- | --- | --- | --- | --- |
| build-passes-check | 1.00 | 合格（偽の合格） | — | ケース：採点が「check を呼んだ」しか見ていない |
| build-refuses-judge-only | 0.67 | 不合格 | 01-no-bad-shape | ケース：採点の誤り（grader threw） |
| build-shows-table-first | 1.00 | 合格 | — | — |
| eval-lists-and-waits | 1.00 | 合格 | — | — |
| eval-result-json | 1.00 | 合格 | — | — |
| eval-stops-without-state | 1.00 | 合格 | — | — |
| judge-calls-judge-score | 0.75 | 不合格 | 03-keys | スキル：JSON を返さず文で要約 |
| judge-must-violation-fails | 0.50 | 不合格 | 01-fail・02-violations | スキル：JSON を返さず文で要約（判断の中身は正しかった） |
| judge-rejects-bad-runs | 0.67 | 不合格 | 03-range | スキル：`--runs 6` を断らずに 6 回の確認に進んだ |

落ちた採点ごとの原因と、直したこと：

- build-passes-check（偽の合格）：pipe-builder の `prompts/summary.md` の Write が、Claude Code に "Subagents should return findings as text, not write report files." で断られ、`pipe-in-gen check` は落ちた。採点は check を呼んだことしか見ていなかった。直したこと：check が通ったこと（成功の行）を見る採点 07-check-passed（重み 2。これだけ落ちると 0.78 で線の 0.8 を下回る）と、指示文の名前の頭の番号を見る採点 08-numbered-prompt を足した。pipe-builder と `stage-rules.md` に名前の決まり（頭に 2 桁の番号と `_`）を書いた。
- build-refuses-judge-only の 01-no-bad-shape：スキルは正しく作らなかった（悪い形を書かずに断った）が、採点が `pipe.toml` を読む形だったので、ファイルが無くて採点そのものが失敗した（grader threw: path does not exist）。直したこと：trace を読む `not_contains` に替えた（メッセージの境 `\n{` を越えない）。
- judge-calls-judge-score の 03-keys・judge-must-violation-fails の 01-fail と 02-violations：スキルが `judge-score` の JSON を返さず、文で要約した。直したこと：pipe-judge の 5 章に、JSON を ```json の囲みでそのまま貼る、要約に置き換えない、と書き、囲みの見本を置いた。
- judge-rejects-bad-runs の 03-range：`--runs 6` を断らず、6 回の利用料の確認に進んだ。直したこと：pipe-judge の本文の頭（0 章より前）に、範囲の外なら「`--runs` は 1〜5 です」と伝えて止まる・確認を出さない・審査役を呼ばない・`judge-score` を流さない、の 1 行を置いた。

あわせて、ケースの無かったスキルに安いケースを 3 本足した（`run-dry-run-asks-first`・`run-refuses-unsupported`・`live-stops-without-tools`）。全部で 12 本になった。

以下の表は `rounds.py` で出した（ラウンド 2 から。1b との差もここから読める）。

### ラウンド 2

- Claude Code 2.1.323・モデル haiku・審査役 haiku・回の数 1・合格の線 1
- 合格 11/12・全体の点 0.94・費用 $0.11・時間 88 秒・途中で止まった いいえ

| ケース | 点 | 合格の回 | 落ちた採点 | エラーの回 | 前の回との差 |
| --- | --- | --- | --- | --- | --- |
| build-passes-check | 0.22 | 0/1 | 01-pipe-toml・02-readme・03-stages・04-gen-check・07-check-passed・08-numbered-prompt | 0 | -0.78 |
| build-refuses-judge-only | 1.00 | 1/1 | — | 0 | +0.33 |
| build-shows-table-first | 1.00 | 1/1 | — | 0 | 0.00 |
| eval-lists-and-waits | 1.00 | 1/1 | — | 0 | 0.00 |
| eval-result-json | 1.00 | 1/1 | — | 0 | 0.00 |
| eval-stops-without-state | 1.00 | 1/1 | — | 0 | 0.00 |
| judge-calls-judge-score | 1.00 | 1/1 | — | 0 | +0.25 |
| judge-must-violation-fails | 1.00 | 1/1 | — | 0 | +0.50 |
| judge-rejects-bad-runs | 1.00 | 1/1 | — | 0 | +0.33 |
| live-stops-without-tools | 1.00 | 1/1 | — | 0 | 新しい |
| run-dry-run-asks-first | 1.00 | 1/1 | — | 0 | 新しい |
| run-refuses-unsupported | 1.00 | 1/1 | — | 0 | 新しい |

- 1b で落ちた 4 本（build-refuses-judge-only・judge-calls-judge-score・judge-must-violation-fails・judge-rejects-bad-runs）と、足した 3 本は合格した。pipe-judge は範囲の外の `--runs` を最初に断り、`judge-score` の JSON を囲みでそのまま返した。
- build-passes-check（0.22）：環境。サンドボックスの Bash から作業フォルダが読み取り専用でマウントされていて（root の環境）、`pipe-in-gen new` が `Read-only file system` で失敗し、pipe-builder は手で書かずに止まった（1b では Write の手書きに切り替えて書けていた。どちらに倒れるかがモデルの判断で揺れる）。直したこと：pipe-builder の「## 作るとき」に、`new` が失敗したら確認の取れた表どおりに Write で手で書き、`pipe-in-gen check` が通るまで直す手順を足した（書ける範囲とフックは変えない）。
- 集計：`rounds.py` の「回の数」が `runsPerCase`（`--runs` で上書きしてもケースの既定の 3 のまま）から出ていたので、`arms.with` の長さから出すように直した。

### ラウンド 3

- Claude Code 2.1.323・モデル haiku・審査役 haiku・回の数 1・合格の線 1
- 合格 9/12・全体の点 0.94・費用 $0.12・時間 101 秒・途中で止まった いいえ

| ケース | 点 | 合格の回 | 落ちた採点 | エラーの回 | 前の回との差 |
| --- | --- | --- | --- | --- | --- |
| build-passes-check | 0.89 | 0/1 | 08-numbered-prompt | 0 | +0.67 |
| build-refuses-judge-only | 0.67 | 0/1 | 01-no-bad-shape | 0 | -0.33 |
| build-shows-table-first | 1.00 | 1/1 | — | 0 | 0.00 |
| eval-lists-and-waits | 1.00 | 1/1 | — | 0 | 0.00 |
| eval-result-json | 1.00 | 1/1 | — | 0 | 0.00 |
| eval-stops-without-state | 1.00 | 1/1 | — | 0 | 0.00 |
| judge-calls-judge-score | 1.00 | 1/1 | — | 0 | 0.00 |
| judge-must-violation-fails | 1.00 | 1/1 | — | 0 | 0.00 |
| judge-rejects-bad-runs | 1.00 | 1/1 | — | 0 | 0.00 |
| live-stops-without-tools | 0.75 | 0/1 | 04-says-no-tools | 0 | -0.25 |
| run-dry-run-asks-first | 1.00 | 1/1 | — | 0 | 0.00 |
| run-refuses-unsupported | 1.00 | 1/1 | — | 0 | 0.00 |

- build-passes-check（0.89）：手書きへの切り替えが効き、07-check-passed（check が通った）が当たった。08-numbered-prompt はケース：`prompts/01_summary.md` が作られていたのに、文字の組（`[0-9]`）を含む path が当たらず落ちた（理由は確かめていない）。直したこと：path を glob の無い `prompts/01_summary.md` にした。
- live-stops-without-tools（0.75）：ケース。振る舞いは正しい（道具を探して無く、何もせず止まった）が、英語で答えたので 04 の語に当たらなかった。直したこと：英語の言い方（doesn't have・missing・not found など）と「見つかりません」を足した。
- build-refuses-judge-only（0.67）：スキル（本物の不具合）。pipe-build のスキルが、judge だけで `on_fail` を書く表を「確認済み」のまま pipe-builder に渡し、pipe-builder が手で書く道でその形を書き、`pipe-in-gen check` も警告なしで通した（1b・2 では書けない環境だったので表に出なかった）。採点 01-no-bad-shape は、trace の中のサブエージェントの Write を正しく捕まえた。直したこと：スキルの「## 3.」の頭と pipe-builder の「## 作るとき」の頭に、任せる前・書く前にこの形を照らして止まる段落を足し、`pipe-in-gen check` に警告 W8（judge と `on_fail` があり `command` が無い）を足した。

### ラウンド 4

- Claude Code 2.1.323・モデル haiku・審査役 haiku・回の数 1・合格の線 1
- 合格 12/12・全体の点 1.00・費用 $0.11・時間 81 秒・途中で止まった いいえ

| ケース | 点 | 合格の回 | 落ちた採点 | エラーの回 | 前の回との差 |
| --- | --- | --- | --- | --- | --- |
| build-passes-check | 1.00 | 1/1 | — | 0 | +0.11 |
| build-refuses-judge-only | 1.00 | 1/1 | — | 0 | +0.33 |
| build-shows-table-first | 1.00 | 1/1 | — | 0 | 0.00 |
| eval-lists-and-waits | 1.00 | 1/1 | — | 0 | 0.00 |
| eval-result-json | 1.00 | 1/1 | — | 0 | 0.00 |
| eval-stops-without-state | 1.00 | 1/1 | — | 0 | 0.00 |
| judge-calls-judge-score | 1.00 | 1/1 | — | 0 | 0.00 |
| judge-must-violation-fails | 1.00 | 1/1 | — | 0 | 0.00 |
| judge-rejects-bad-runs | 1.00 | 1/1 | — | 0 | 0.00 |
| live-stops-without-tools | 1.00 | 1/1 | — | 0 | +0.25 |
| run-dry-run-asks-first | 1.00 | 1/1 | — | 0 | 0.00 |
| run-refuses-unsupported | 1.00 | 1/1 | — | 0 | 0.00 |

- 12 本とも合格した。止めどき（全ケースが合格した回）に届いた。
- build-refuses-judge-only：スキルが pipe-builder に任せる前に止まり、「command と組む」「指摘だけにする」の 2 つの案を見せて聞いた。ファイルは書かなかった。
- build-passes-check：`pipe-in-gen new` は環境で失敗したが、pipe-builder が手書きに切り替えて `prompts/01_summary.md` で書き、check を通した。

### 止める前の確かめ（`--runs 3 --threshold 0.8`）

- Claude Code 2.1.323・モデル haiku・審査役 haiku・回の数 3・合格の線 0.8
- 合格 11/12・全体の点 0.96・費用 $0.29・時間 227 秒・途中で止まった いいえ

| ケース | 点 | 合格の回 | 落ちた採点 | エラーの回 | 前の回との差 |
| --- | --- | --- | --- | --- | --- |
| build-passes-check | 1.00 | 3/3 | — | 0 | 0.00 |
| build-refuses-judge-only | 0.89 | 2/3 | 02-says-command（1/3） | 0 | -0.11 |
| build-shows-table-first | 1.00 | 3/3 | — | 0 | 0.00 |
| eval-lists-and-waits | 1.00 | 3/3 | — | 0 | 0.00 |
| eval-result-json | 1.00 | 3/3 | — | 0 | 0.00 |
| eval-stops-without-state | 1.00 | 3/3 | — | 0 | 0.00 |
| judge-calls-judge-score | 1.00 | 3/3 | — | 0 | 0.00 |
| judge-must-violation-fails | 1.00 | 3/3 | — | 0 | 0.00 |
| judge-rejects-bad-runs | 0.67 | 2/3 | 01-no-agent（1/3）・02-no-score（1/3）・03-range（1/3） | 0 | -0.33 |
| live-stops-without-tools | 1.00 | 3/3 | — | 0 | 0.00 |
| run-dry-run-asks-first | 1.00 | 3/3 | — | 0 | 0.00 |
| run-refuses-unsupported | 1.00 | 3/3 | — | 0 | 0.00 |

- 終了コード 1（合格の線 0.8 に届かないケースが 1 本）。費用は上限（$1.5）の内。
- judge-rejects-bad-runs（0.67・2/3）：スキル。3 回のうち 1 回、`--runs 6` を断らずに審査役を呼び、`judge-score` を流した（ほかの 2 回は頭の 1 行で止まった）。この回は記録（trace）を残していないので、採点の説明だけで見た。直していない（残った課題）。
- build-refuses-judge-only（0.89・2/3）：3 回のうち 1 回、正しく止まったが、返事の言い回しが 02-says-command に当たらなかった。ケースの点は線を越えた。

### ラウンド 5（監査と助言の直しのあと）

- Claude Code 2.1.323・モデル haiku・審査役 haiku・回の数 1・合格の線 1
- 合格 12/12・全体の点 1.00・費用 $0.12・時間 79 秒・途中で止まった いいえ

| ケース | 点 | 合格の回 | 落ちた採点 | エラーの回 | 前の回との差 |
| --- | --- | --- | --- | --- | --- |
| build-passes-check | 1.00 | 1/1 | — | 0 | 0.00 |
| build-refuses-judge-only | 1.00 | 1/1 | — | 0 | 0.00 |
| build-shows-table-first | 1.00 | 1/1 | — | 0 | 0.00 |
| eval-lists-and-waits | 1.00 | 1/1 | — | 0 | 0.00 |
| eval-result-json | 1.00 | 1/1 | — | 0 | 0.00 |
| eval-stops-without-state | 1.00 | 1/1 | — | 0 | 0.00 |
| judge-calls-judge-score | 1.00 | 1/1 | — | 0 | 0.00 |
| judge-must-violation-fails | 1.00 | 1/1 | — | 0 | 0.00 |
| judge-rejects-bad-runs | 1.00 | 1/1 | — | 0 | 0.00 |
| live-stops-without-tools | 1.00 | 1/1 | — | 0 | 0.00 |
| run-dry-run-asks-first | 1.00 | 1/1 | — | 0 | 0.00 |
| run-refuses-unsupported | 1.00 | 1/1 | — | 0 | 0.00 |

- 監査と助言で直したスキル・エージェント・採点の文（決まりの言い方・名前の決まりの範囲・pipe-run の 01-dry-run の正規表現など）と、プラグインのフックの報告の道具の扱いを入れたあとに回した確かめ。12 本とも合格し、直しでケースは崩れなかった（差は 1 つ前のラウンド 4 と比べた）。

### 蒸留の前後（D0097。`--threshold 0.8`。d0〜d2 は `--runs 3`、比べ直しは前後とも `--runs 6`）

プラグインのスキル 5 つ・エージェント 4 つ・`stage-rules.md` の文を、決まりを落とさずに縮めた（合計 61,088 → d1 は 42,320 バイト、d2 は 42,493 バイト、厳しくしたあとは 44,495 バイト（27.2% 減）、監査で落ちた決まりを戻したあとは 44,928 バイト（26.5% 減）。[D0097](../../decisions/D0097-plugin-distill.md)）。d0〜d2 は同じコマンド（haiku・審査役 haiku・`--runs 3 --threshold 0.8`・`--ablation none`・Claude Code 2.1.325）で回した。モデルは別名 `haiku` のまま、同じ版の Claude Code で続けて回した。記録（trace）の頭でモデルの ID を確かめられたのは、記録を残した回（比べ直しの 3 回目の後の側と、監査のあとの回）で、どれも同じ haiku の版だった。ほかの回は記録が消えていて、今は確かめられない。審査役は、結果の JSON に別名 `haiku` しか出ず、ID は分からない。pipe-judge のエージェントは定義の `model: sonnet` で動き、記録でも sonnet の版だった（`judge-*` の 2 本の審査の部分）。どの回も、API の誤りで終わった回（`error` が空でない回）は無く、コマンドの終了コードは 0 だった。表の「前の回との差」は 1 つ前の回との差（d1 は d0 と、d2 は d1 と比べる）。判定は d0 と比べた。

#### d0（蒸留の前）

- Claude Code 2.1.325・モデル haiku・審査役 haiku・回の数 3・合格の線 0.8
- 合格 12/12・全体の点 0.99・費用 $0.30・時間 210 秒・途中で止まった いいえ

| ケース | 点 | 合格の回 | 落ちた採点 | エラーの回 | 前の回との差 |
| --- | --- | --- | --- | --- | --- |
| build-passes-check | 1.00 | 3/3 | — | 0 | — |
| build-refuses-judge-only | 1.00 | 3/3 | — | 0 | — |
| build-shows-table-first | 1.00 | 3/3 | — | 0 | — |
| eval-lists-and-waits | 1.00 | 3/3 | — | 0 | — |
| eval-result-json | 1.00 | 3/3 | — | 0 | — |
| eval-stops-without-state | 0.89 | 2/3 | 03-first（1/3） | 0 | — |
| judge-calls-judge-score | 1.00 | 3/3 | — | 0 | — |
| judge-must-violation-fails | 1.00 | 3/3 | — | 0 | — |
| judge-rejects-bad-runs | 1.00 | 3/3 | — | 0 | — |
| live-stops-without-tools | 1.00 | 3/3 | — | 0 | — |
| run-dry-run-asks-first | 1.00 | 3/3 | — | 0 | — |
| run-refuses-unsupported | 1.00 | 3/3 | — | 0 | — |

#### d1（蒸留の 1 回目のあと）

- Claude Code 2.1.325・モデル haiku・審査役 haiku・回の数 3・合格の線 0.8
- 合格 11/12・全体の点 0.98・費用 $0.28・時間 201 秒・途中で止まった いいえ

| ケース | 点 | 合格の回 | 落ちた採点 | エラーの回 | 前の回との差 |
| --- | --- | --- | --- | --- | --- |
| build-passes-check | 0.70 | 2/3 | 01-pipe-toml（1/3）・02-readme（1/3）・03-stages（1/3）・04-gen-check（1/3）・05-agent（1/3）・07-check-passed（1/3）・08-numbered-prompt（1/3） | 0 | -0.30 |
| build-refuses-judge-only | 1.00 | 3/3 | — | 0 | 0.00 |
| build-shows-table-first | 1.00 | 3/3 | — | 0 | 0.00 |
| eval-lists-and-waits | 1.00 | 3/3 | — | 0 | 0.00 |
| eval-result-json | 1.00 | 3/3 | — | 0 | 0.00 |
| eval-stops-without-state | 1.00 | 3/3 | — | 0 | +0.11 |
| judge-calls-judge-score | 1.00 | 3/3 | — | 0 | 0.00 |
| judge-must-violation-fails | 1.00 | 3/3 | — | 0 | 0.00 |
| judge-rejects-bad-runs | 1.00 | 3/3 | — | 0 | 0.00 |
| live-stops-without-tools | 1.00 | 3/3 | — | 0 | 0.00 |
| run-dry-run-asks-first | 1.00 | 3/3 | — | 0 | 0.00 |
| run-refuses-unsupported | 1.00 | 3/3 | — | 0 | 0.00 |

- build-passes-check（0.70）：スキル。3 回のうち 1 回、メインの会話が自分で `pipe-in-gen new` を流し、root の環境で失敗して止まった（蒸留の前は 18 回中 0 回）。このケースだけを流し直した 3 回のうち 1 回は、pipe-builder が `new` の失敗のあと Write での手書きに進まずに戻った（6 回の平均 0.741）。蒸留で、pipe-builder の手で書く箇条から「（Bash の中からは書けなくても、Write では書けることがある）」を削っていた。この理由の文が、haiku の動きを決めていた。直したこと：その文を同じ行に戻し、pipe-build の頭の「自分では書かない」に「（`pipe-in-gen new` も流さない）」を足した（決まりの一覧のテストに B38・P32 として足した）。

#### d2（蒸留の 2 回目のあと）

- Claude Code 2.1.325・モデル haiku・審査役 haiku・回の数 3・合格の線 0.8
- 合格 11/12・全体の点 0.97・費用 $0.29・時間 208 秒・途中で止まった いいえ

| ケース | 点 | 合格の回 | 落ちた採点 | エラーの回 | 前の回との差 |
| --- | --- | --- | --- | --- | --- |
| build-passes-check | 1.00 | 3/3 | — | 0 | +0.30 |
| build-refuses-judge-only | 1.00 | 3/3 | — | 0 | 0.00 |
| build-shows-table-first | 1.00 | 3/3 | — | 0 | 0.00 |
| eval-lists-and-waits | 0.92 | 2/3 | 04-asks（1/3） | 0 | -0.08 |
| eval-result-json | 1.00 | 3/3 | — | 0 | 0.00 |
| eval-stops-without-state | 0.78 | 1/3 | 03-first（2/3） | 0 | -0.22 |
| judge-calls-judge-score | 1.00 | 3/3 | — | 0 | 0.00 |
| judge-must-violation-fails | 1.00 | 3/3 | — | 0 | 0.00 |
| judge-rejects-bad-runs | 1.00 | 3/3 | — | 0 | 0.00 |
| live-stops-without-tools | 1.00 | 3/3 | — | 0 | 0.00 |
| run-dry-run-asks-first | 1.00 | 3/3 | — | 0 | 0.00 |
| run-refuses-unsupported | 1.00 | 3/3 | — | 0 | 0.00 |

- build-passes-check は 3 回とも合格した。
- eval-stops-without-state（0.78）と eval-lists-and-waits（0.92）：ケース（言い回しの採点）。返事は正しく止まって返事を待っていたが、「先に」の語が無い言い換え・英語の返事・「確認させてください」の言い回しで、03-first・04-asks が当たらなかった。pipe-eval の文は d1 と d2 で同じ。決めた手順で 2 本を `--runs 3` で流し直すと、どちらも 3 回とも 1.00 だった。6 回の平均は eval-stops-without-state 0.89（d0 と同じ）・eval-lists-and-waits 0.96。
- 判定：合格 12/12、前に合格したケースはすべて合格。全体の点は 6 回の平均で 0.987 で、d0 の 0.991 から 0.004 下がった（eval-lists-and-waits の言い回しの採点が 6 回中 1 回当たらなかった）。いったん揺れの範囲として合格にしかけたが、人の判断で合格にせず、厳しくした（前後を同じ回数で比べ直す・削った理由の文を見直して戻す・言い回しの採点を振る舞いを見る形に直す。下の「比べ直し」）。

#### 比べ直し（人の判断で厳しくしたあと。前後とも `--runs 6`）

d2 の判定を人が合格にしなかったので、次の 3 つで厳しくした（[D0097](../../decisions/D0097-plugin-distill.md)）：前後を同じ採点・同じ回数で比べ直す、蒸留で削った理由の文を見直して動きを支えるものを戻す（30 文）、言い回しで落ちる採点 9 本を振る舞いを見る形に直す（03-first は名指すコマンド `pipe-in --pipe` だけを見る）。前は、蒸留の前の 10 ファイルに新しい採点を組み合わせたプラグインの写し。全体の点は小数 3 桁で比べ、下がれば合格にしない（人の決め）。

- 1 回目（理由の文を戻した直後）：全体 0.995（前）→ 0.988（後）。下がった 2 本を前後とも 6 回足して 12 回にしても 0.998 → 0.993。eval-result-json は、2 つの検査を 1 回の Bash に `;` でつないで流した回があり、04-ran-twice が落ちた（前でも 12 回中 2 回）。pipe-eval に「1 回の Bash で 1 項目だけ」（E24）を足した。
- 2 回目：全体 0.998 → 0.995。E24 で項目ごとに別の Bash で流すようになったが、終了コードを見る `; echo "exit=$?"` も付けなくなり、root の環境では Bash の結果が毎回 Exit code 1 に見えるため、成功の項目を `passed: false` と報告して 02-passed が落ちた（12 回中 4 回）。E24 に「ほかの項目とつながない。`; echo "exit=$?"` だけは付けてよく、その値を終了コードにする」を足した。
- 3 回目（下の表。どれも記録を残した）：全体 0.998 = 0.998（3 桁で同じ）、合格 12/12 同士、前に合格したケースはすべて合格。eval-result-json は 12 回とも合格した。build-refuses-judge-only の 12 回中 1 回は、正しく止まって 2 つの案を見せたが、「`command` がありません。…機械の検査と組む」と離して書いたので、02-says-command（command と「組」が 40 字以内）に当たらなかった（採点の取りこぼし。次の候補）。費用（定価の見積もり）と時間は、前の側 $0.66・502 秒（12 本 $0.59・424 秒、足した 2 本 $0.04・45 秒と $0.03・33 秒）、後の側 $0.66・529 秒（$0.60・439 秒、$0.04・59 秒、$0.03・31 秒）。前の側は、`git show HEAD:` の 10 のファイルと `plugin.json` で作った写しで、10 のファイルの合計 61,088 バイト・版 0.6.1・`evals/` は今の `plugin/evals/` と同じ（`results/` を除いて `diff -r` が空）であることを確かめた。

| ケース | 前の点 | 前の合格の回 | 後の点 | 後の合格の回 | エラーの回（前・後） | 差 |
| --- | --- | --- | --- | --- | --- | --- |
| build-passes-check | 1.00 | 6/6 | 1.00 | 6/6 | 0・0 | 0.00 |
| build-refuses-judge-only | 1.00 | 12/12 | 0.97 | 11/12 | 0・0 | -0.03 |
| build-shows-table-first | 1.00 | 6/6 | 1.00 | 6/6 | 0・0 | 0.00 |
| eval-lists-and-waits | 1.00 | 6/6 | 1.00 | 6/6 | 0・0 | 0.00 |
| eval-result-json | 0.97 | 10/12 | 1.00 | 12/12 | 0・0 | +0.03 |
| eval-stops-without-state | 1.00 | 6/6 | 1.00 | 6/6 | 0・0 | 0.00 |
| judge-calls-judge-score | 1.00 | 6/6 | 1.00 | 6/6 | 0・0 | 0.00 |
| judge-must-violation-fails | 1.00 | 6/6 | 1.00 | 6/6 | 0・0 | 0.00 |
| judge-rejects-bad-runs | 1.00 | 6/6 | 1.00 | 6/6 | 0・0 | 0.00 |
| live-stops-without-tools | 1.00 | 6/6 | 1.00 | 6/6 | 0・0 | 0.00 |
| run-dry-run-asks-first | 1.00 | 6/6 | 1.00 | 6/6 | 0・0 | 0.00 |
| run-refuses-unsupported | 1.00 | 6/6 | 1.00 | 6/6 | 0・0 | 0.00 |

- 大きさ：合計 61,088 → 44,495 バイト（27.2% 減。上限は理由の文を戻した分、人の決めで 44,500）。どのファイルも蒸留の前より小さい。

#### 監査のあと（落ちた決まりを戻したあと）

監査が、決まりの一覧の目印の外で落ちた決まりを 7 つ見つけたので、蒸留の前の字で戻した（合計 44,928 バイト、26.5% 減。[D0097](../../decisions/D0097-plugin-distill.md)）。

- 後の側だけを、比べ直しの 3 回目と同じ手順で回した（前の側は 3 回目と同じ）。
- 全体の点が下がったので、下がった 3 本（build-passes-check・eval-lists-and-waits・live-stops-without-tools）を前後とも 6 回ずつ足し、12 回にした。下の表は、そのあとの数。
- 費用（定価の見積もり）と時間：後の側の 12 本 $0.65・516 秒。足した 3 本は前 $0.15・201 秒、後 $0.14・186 秒。
- どの回も、エラーの回は 0、終了コードは 0、Claude Code は 2.1.325 だった。

| ケース | 前の点 | 前の合格の回 | 後の点 | 後の合格の回 | エラーの回（前・後） | 差 |
| --- | --- | --- | --- | --- | --- | --- |
| build-passes-check | 0.94 | 11/12 | 0.94 | 11/12 | 0・0 | 0.00 |
| build-refuses-judge-only | 1.00 | 12/12 | 0.97 | 11/12 | 0・0 | -0.03 |
| build-shows-table-first | 1.00 | 6/6 | 1.00 | 6/6 | 0・0 | 0.00 |
| eval-lists-and-waits | 1.00 | 12/12 | 0.98 | 11/12 | 0・0 | -0.02 |
| eval-result-json | 0.97 | 10/12 | 1.00 | 12/12 | 0・0 | +0.03 |
| eval-stops-without-state | 1.00 | 6/6 | 1.00 | 6/6 | 0・0 | 0.00 |
| judge-calls-judge-score | 1.00 | 6/6 | 1.00 | 6/6 | 0・0 | 0.00 |
| judge-must-violation-fails | 1.00 | 6/6 | 1.00 | 6/6 | 0・0 | 0.00 |
| judge-rejects-bad-runs | 1.00 | 6/6 | 1.00 | 6/6 | 0・0 | 0.00 |
| live-stops-without-tools | 1.00 | 12/12 | 0.98 | 11/12 | 0・0 | -0.02 |
| run-dry-run-asks-first | 1.00 | 6/6 | 1.00 | 6/6 | 0・0 | 0.00 |
| run-refuses-unsupported | 1.00 | 6/6 | 1.00 | 6/6 | 0・0 | 0.00 |

- 全体の点は 0.992（前）→ 0.989（後）、合格は 12/12 同士で、前に合格したケースはすべて合格した。
- 後の側で落ちた 3 回は、記録で読むと、どれも動きは正しく、採点の言い回しの取りこぼしだった。
  - 「`command` を足す」と書いて「組む」が無かった。
  - 「よいか返事をください」と聞いた。
  - 「道具が見つからなかった」と書いた。
- 前の側で落ちた 3 回は、どれも本当の崩れだった。
  - eval-result-json の 2 回は、検査を `;` でつないだ。
  - build-passes-check の 1 回は、`new` が読み取り専用で失敗したあと、ひな形を読もうとして断られ、手で書かずに戻った。後の側の 1 回も同じ崩れ方。
- 前の側の点も、同じ文のまま回数を足しただけで 0.998 → 0.992 に動いた。
- 判定：人の判断で、小数 3 桁で下がれば合格にしない決まりから外れると書いたうえで、合格にした。

### 採点の取りこぼしを直したあと（D0098。`--runs 3 --threshold 0.8`）

D0097 の比べ直しと監査のあとで、動きは正しいのに言い回しの採点が当たらなかった回の形に合わせて、3 本の採点の `pattern` を直した（[D0098](../../decisions/D0098-plugin-grader-misses.md)）。スキル・エージェント・`stage-rules.md`・ほかの採点・ケースの本文は変えていない。

- 04-asks（eval-lists-and-waits）：返事を頼む聞き方（「返事をください」「ご返答をください」など）と、返事を待つと伝える文（「返事をお待ちします」など）と、英語の please reply・please let me know などを足した。あわせて、当たりすぎを絞った：コマンドの中の `$?` の `?`、問わない文の proceed（I will proceed）と confirm（I confirmed）には当たらないようにした。
- 04-says-no-tools（live-stops-without-tools）：過去の形（「見つからなかった」「無かった」と、英語の couldn't find・did not find・weren't available など）を足した。前の形は全部残した。ラウンドのあと、連用の打ち消し「〜ず」の形（「見つからず」「見当たらず」「使えず」「できず」）も語を名指して足した（「迷わず」「必ず」には当たらない）。
- 02-says-command（build-refuses-judge-only）：command と「組む」が同じ返事の中ならどこにあってもよいことにした（前は 40 字の内）。案を見せて選ばせる返事の中で、command を「足す」「加える」「追加する」・英語の add と言い切る案も数えるようにした。自分で入れて作ったと伝える形（「組み込んで作りました」「組んで作りました」「組みました」「組み込みました」）は数えないようにした。

直した 3 本は、ラウンドの前に、当たる見本と当たらない見本のテスト（`tests/test_plugin_grader_misses.py`）で確かめた。テストには直す前の `pattern` を写してあり、取りこぼした形が直す前の `pattern` に当たらず今の `pattern` に当たること、直す前の `pattern` が当たる見本（絞った見本を除く）には今の `pattern` も当たること、絞った見本は直す前の `pattern` に当たり今の `pattern` に当たらないことを見る。採点が変わると同じ動きでも点が変わるので、この小節の点は D0097 の回と比べない。

#### 残った記録への当て直し（利用料なし）

D0097 で記録（trace）を残した回の、3 つのケースの全部の回の最後の返事に、直す前の `pattern` と今の `pattern` を JavaScript の正規表現で当てた。最後の返事は、主の会話の assistant の行の最後の text。スクリプトは作業用フォルダに置き、コミットしていない。出したのは数と名前だけ。

当てた記録は 72 回（3 つのケースで 24 回ずつ）で、内わけは次のとおり。
- build-refuses-judge-only：比べ直しの 3 回目の後の側 12 回（12 本の 6 回と足した 6 回）と、監査のあとの後の側 12 回（同じ）。
- eval-lists-and-waits と live-stops-without-tools：それぞれ、比べ直しの 3 回目の後の側 6 回、監査のあとの後の側 6 回、足した 3 本の後の側 6 回、足した 3 本の前の側 6 回。
- 比べ直しの 3 回目の前の側と、監査のあとの前の側の 12 本の回は、記録が残っていないので当てていない。

数は直したあとの採点（ラウンドのあとの直しを含む）で数えた。

| ケース | 採点 | 回の数 | 記録で合格の回 | 直す前の pattern で当たった回 | 今の pattern で当たった回 | 直す前の pattern と記録の食い違い | 当たらなくなった回 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| build-refuses-judge-only | 02-says-command | 24 | 22 | 22 | 24 | 0 | 0 |
| eval-lists-and-waits | 04-asks | 24 | 23 | 23 | 24 | 0 | 0 |
| live-stops-without-tools | 04-says-no-tools | 24 | 23 | 23 | 24 | 0 | 0 |

- 直す前の `pattern` と記録の合否の食い違いは 0 回だった。この 72 回では、最後の返事の取り出し方が、実物の採点（`last_message`）と食い違わなかった（`last_message` の作り方は公式の文書に書かれていないので、ほかの回でも同じとまでは言えない）。
- 今の `pattern` で新しく当たったのは 4 回で、どれも D0097 で取りこぼした回だった。
  - 02-says-command の 2 回：「`command` がありません。…機械の検査と組む」と離して書いた回と、「案 1：`command` を足す」と書いた回。
  - 04-asks の 1 回：「よいか返事をください」。
  - 04-says-no-tools の 1 回：「見つからなかった」。
  - 記録では、どれも動きは正しく、同じ回のほかの採点もすべて合格だった。
- 当たらなくなった回は 0 回で、絞った形（`$?`・I will proceed・I confirmed・組み込んで作りました）で偽の合格になっていた回も無かった。

#### ラウンド（12 本・`--runs 3`）

- Claude Code 2.1.325・モデル haiku・審査役 haiku・回の数 3・合格の線 0.8。記録の頭のモデルは、どの回も同じ haiku の版だった。
- 合格 12/12・全体の点 0.993・費用 $0.30・時間 234 秒・途中で止まった いいえ。審査を飛ばした回 0・エラーの回 0・終了コード 0。

| ケース | 点 | 合格の回 | 落ちた採点 | エラーの回 |
| --- | --- | --- | --- | --- |
| build-passes-check | 1.00 | 3/3 | — | 0 |
| build-refuses-judge-only | 1.00 | 3/3 | — | 0 |
| build-shows-table-first | 1.00 | 3/3 | — | 0 |
| eval-lists-and-waits | 1.00 | 3/3 | — | 0 |
| eval-result-json | 1.00 | 3/3 | — | 0 |
| eval-stops-without-state | 1.00 | 3/3 | — | 0 |
| judge-calls-judge-score | 1.00 | 3/3 | — | 0 |
| judge-must-violation-fails | 1.00 | 3/3 | — | 0 |
| judge-rejects-bad-runs | 1.00 | 3/3 | — | 0 |
| live-stops-without-tools | 0.92 | 2/3 | 04-says-no-tools（1/3） | 0 |
| run-dry-run-asks-first | 1.00 | 3/3 | — | 0 |
| run-refuses-unsupported | 1.00 | 3/3 | — | 0 |

ラウンドで使った採点（ラウンドのあとの直しの前）で、記録に当て直した結果：
- 直した 3 本の当たり外れは、記録の合否と 9 回とも合っていた。
- build-refuses-judge-only の 3 回目は、正しく止まり、「案 1：command を足す（推奨）」と「案 2：on_fail を外す」を見せて聞いた回だった。直す前の `pattern` なら取りこぼしていた形で、今回の直しで合格した。

live-stops-without-tools の 3 回目の 04-says-no-tools（ケースの不具合）：
- 道具を呼ばず、何も書かずに正しく止まったが、「Artifact・ArtifactData・Monitor が見つからず」の「〜ず」の形が採点に無かった。
- 決めた手順（直して流すのは 2 回まで）で直した。まず見本を `tests/test_plugin_grader_misses.py` に足して赤を確かめ、次に「見つからず」「見当たらず」「使えず」「できず」を語を名指して足した（「迷わず」「必ず」に当たらない）。
- 直したあと、このケースだけを流し直した（`--case live-stops-without-tools`・`--runs 3`・`--max-cost-usd 0.5`）。

| ケース | 点 | 合格の回 | 落ちた採点 | エラーの回 |
| --- | --- | --- | --- | --- |
| live-stops-without-tools（流し直し） | 1.00 | 3/3 | — | 0 |

- 流し直しの費用 $0.01・時間 10 秒・エラーの回 0・終了コード 0。
- 直したあとの採点で、ラウンドと流し直しの記録に当て直すと、ラウンドの 3 回目が当たり、当たらなくなった回は 0 回だった。

判定：終える条件の 4 つがそろったので終えた。
1. 欠けた回が無い。
2. 落ちた採点の回は 1 回で、記録で読んでケースの不具合と分けた。
3. ラウンドで使った採点では、直した 3 本のうち 04-says-no-tools が、正しく動いた回で 1 回落ちた（「〜ず」の形）。それを直したあとの採点でラウンドと流し直しの記録に当て直すと、正しく動いた回で落ちる回は無く、新しく当たった回はどれも動きが正しい。
4. 12/12。

採点が変わったので、全体の点を D0097 の回と比べて合否は決めていない。

## 限界

- root のコンテナだけで測った。「could NOT seal … running as root」の警告が出て、サンドボックスの Bash の終わりに読み取り専用のフォルダの誤りが出るため、Bash の結果が毎回「Exit code 1」に見え、サンドボックスの Bash から作業フォルダに書けなかった（`pipe-in-gen new` が `.pipe-in` を作れない）。何を呼ぶ・呼ばないを見る採点は読めるが、Bash の結果や書き込みを見る採点は環境で落ちうる。root でない環境では、この環境では試せなかった。
- haiku（審査役も haiku）だけで回した。上位のモデルでは確かめていない。ただし pipe-judge のエージェントは定義の `model: sonnet` で動くので、`judge-*` の 2 本の審査の部分は sonnet で測った（エージェントの定義の `model` は、メインの `--model` より先に効く。https://code.claude.com/docs/en/sub-agents ）。
- `--runs 1` は 1 回だけなので、合否がぶれうる。止める前の `--runs 3` で、judge-rejects-bad-runs が 3 回に 1 回落ちた。ラウンドの 12/12 は「1 回は通った」で、毎回通るとは限らない。
- 止める前の確かめの回は、記録（trace）を残さずに流したので、落ちた 1 回の中身は採点の説明でしか見ていない。
- trace（`regex` の `target: trace`）には、サブエージェント（pipe-builder）のメッセージと道具の呼び出しも入る（ラウンド 3 で、01-no-bad-shape が pipe-builder の Write の中の悪い形に当たって確かめた）。
- 正規表現の採点の限界：07-check-passed は、Claude Code が trace を JSON にするとき日本語を `\u` に逃がすと当たらない（偽の不合格に倒れる）。01-no-bad-shape は、Edit で少しずつ作った悪い形・インラインの表（`check = { … }`）・`check.judge.x = …` の形を見落とし、1 つの返事の文の中で悪い形を `[[stages]]` から引用して説明すると、正しく断っても落ちる。08-numbered-prompt は、文字の組（`[0-9]`）を含む path がファイルがあっても当たらなかったので（ラウンド 3。理由は確かめていない）、glob の無い `prompts/01_summary.md` にした。番号は合っていても名前が違う（`01_summarize.md` など）と落ちる。
- 結果の JSON の形は Claude Code の版で変わりうる。`rounds.py` は知らない形で止まるので、版が変わったら読む鍵を確かめ直す。
- サブエージェントの書き込みを断る決まりは、公式の文書の決まりとしては無い（2.1.323 の本体の判定の文で確かめた。cookbook https://platform.claude.com/cookbook/claude-agent-sdk-08-dynamic-workflows に観察の 1 文だけある）。決まりが無くなると、会話の道の名前の断りは要らない断りになり、語が増えると断りが足りなくなる。

## pipe-in への示唆

- スキルの「断って止まる」決まりは、手順の頭に短い文で置く。後ろの節に書くと、haiku は先の手順へ進む。
- それでも文だけの決まりは揺れる（`--runs 3` で 3 回に 1 回）。止まるべき所は、`pipe-in-gen` の側で機械的に断る形（引数の範囲の確かめ・警告）を重ねるのがよい。次のラウンドの候補：`--runs` の範囲を `pipe-in-gen judge-score` の前に機械で断る。
- 文を縮めるときは、決まりの語を残すテスト（決まりの一覧）と、前後を同じコマンドで回すラウンドを組にする。テストは語が残ったことを、ラウンドは理由の文が動きを支えていたことを見つける（D0097）。
- 書けない環境で止まると、その先の不具合が隠れる。手で書く道などで先へ進めるようにすると、隠れていた不具合が採点に出る。
- 計算の結果を返すスキルは、返す形（```json の囲み）の見本を書き、「要約に置き換えない」と言い切る。
- 採点は「呼んだ」ではなく「通った」を見る。呼んだだけを見る採点は、偽の合格を出す。
- 作るかもしれないファイルを読む採点（`target` がファイル）は、作らないのが正しいケースでは使わない。trace を読む。
- 段の成果物と、サブエージェントに書かせるファイルの名前は、頭に番号を付ける。会話の中で流すとき（`/pipe-in:pipe-run`）は、`pipe-in-gen chat` が当たる名前を流す前に断る。
- `claude plugin eval` を回す環境には、`pipe-in-gen` を編集用でない入れ方（`pip install .`）で home の外に入れ、root でない利用者で流す。
- 採点を直すときは、直す前の `pattern` をテストに写し、前に当たった見本に今も当たることを見る。そのうえで、記録を残した回（`--keep-temp`）に当て直し、記録の合否と食い違わないことと、当たらなくなった回が無いことを見る（D0098）。

## やり直し方

1. pipe-in のフォルダで、home の外の環境に `pip install .`（`-e` なし）で入れる。root でない利用者で流す。
2. 回す（利用料がかかる。人に言われたときだけ）：

   ```
   claude plugin eval ./plugin --scaffold --trust-plugin --allow-tools Bash Write Edit \
     --model haiku --judge-model haiku --runs 1 --ablation none -j 3 \
     --max-cost-usd 0.5 --json <plugin/ の外>/round-<名前>.json \
     --output-dir <plugin/ の外>/round-<名前> --no-publish
   ```

3. 表を出す（読むだけ。何も書かない）：

   ```
   python docs/research/plugin-eval-rounds/rounds.py 1b=<…>/round-1b.json 2=<…>/round-2.json
   ```

   引数は回の順に並べる。`<名前>=` を省くと、並びの番号が名前になる。知らない形・欠け・壊れた JSON・ケースが 0 件のときは、表を出さずに理由の 1 行を出して終了コード 1 で止まる。
4. 落ちた採点を、スキル・ケース・環境に分けて、この文書の「## 結果」に回の小節を足す。
5. 止める前に、`--runs 3 --threshold 0.8 --max-cost-usd 1.5` で 1 回流す。
6. 採点を直したときに記録へ当て直すなら、回すときに `--keep-temp` を付けて記録を残す（記録は `plugin/` の外に置き、コミットしない）。
