# プラグインの eval のラウンド

プラグイン（`plugin/`）自身の eval（`plugin/evals/`・`claude plugin eval`。[D0045](../../decisions/D0045-plugin-evals.md)）を、下位のモデル（haiku。審査役も haiku）で回し、落ちた所を直してまた回した記録です。この 1 回を「ラウンド」と呼びます。回し方の手順は[ガイドの「ラウンドの回し方」](../../guide/plugin.md#ラウンドの回し方下位のモデルで)にもあります。

## 問い

- haiku（審査役も haiku）でプラグインの eval を回し、落ちた所を直してまた回すと、スキルとエージェントが手順どおりに動くようになるか。
- 落ちた採点は、スキルの不具合・ケースの不具合・環境のどれによるか。

## 結論

ラウンド 1a から 4 までと、止める前の確かめの結論です（haiku・審査役も haiku）。

1. 9 本の 5/9（0.68）から始め、12 本の 12/12（1.00）まで上がった（ラウンド 4）。止める前の `--runs 3` では 11/12（0.96）で、judge-rejects-bad-runs が 3 回のうち 1 回だけ落ちた。監査と助言の直しのあとのラウンド 5 も 12/12（1.00）だった。1 回で 9〜12 本を回す費用（定価での見積もり。プランの利用枠の減り方とは別）は $0.11 前後（環境で早く落ちた 1a の $0.04 を除く）、`--runs 3` で $0.29。
2. 落ちた採点の原因は、環境（入れ方・root）・ケース（偽の合格・採点の誤り・言い回しと glob）・スキルの 3 つに分かれた。ラウンド 1a の 4 本は環境だけで、入れ直した 1b から、ほんとうに直す所が見えた。
3. スキルの不具合は、どれも「決まりを書いた所を読み飛ばす」型だった：範囲の外の `--runs` を断る（pipe-judge）・計算の JSON をそのまま返す（pipe-judge）・審査だけで差し戻す表を任せない（pipe-build）。手順の頭に短い文で置き、返す形の見本を書くと、ラウンドでは通るようになった。ただし `--runs 3` では、断る決まりを 3 回に 1 回読み飛ばした。文だけで頼る決まりは、haiku では揺れが残る。
4. 文の決まりの後ろに、機械の検査を置くと揺れに強い。審査だけで差し戻す形は、スキルと pipe-builder の文で止めるほか、`pipe-in-gen check` の警告 W8 で、書かれても分かるようにした。
5. Claude Code は、サブエージェントからの `report`・`summary`・`findings`・`analysis` で始まる `.md` の書き込みを断る（本体の決まり。公式の cookbook https://platform.claude.com/cookbook/claude-agent-sdk-08-dynamic-workflows に観察として 1 文あるが、語の一覧と判定の形は書かれていない）。pipe-builder の指示文と、会話の中で流す段の成果物が当たるので、名前の決まり（頭に番号）と、会話の道で流す前に断る形を足した。
6. 採点は「呼んだ」ではなく「通った」を見る。ラウンドを重ねると、書けない環境で隠れていた不具合（ラウンド 3 の審査だけの形）が、手書きへの切り替えで表に出た。採点を直すと、隠れていた不具合が見えるようになる。

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

## 限界

- root のコンテナだけで測った。「could NOT seal … running as root」の警告が出て、サンドボックスの Bash の終わりに読み取り専用のフォルダの誤りが出るため、Bash の結果が毎回「Exit code 1」に見え、サンドボックスの Bash から作業フォルダに書けなかった（`pipe-in-gen new` が `.pipe-in` を作れない）。何を呼ぶ・呼ばないを見る採点は読めるが、Bash の結果や書き込みを見る採点は環境で落ちうる。root でない環境では、この環境では試せなかった。
- haiku（審査役も haiku）だけで回した。上位のモデルでは確かめていない。
- `--runs 1` は 1 回だけなので、合否がぶれうる。止める前の `--runs 3` で、judge-rejects-bad-runs が 3 回に 1 回落ちた。ラウンドの 12/12 は「1 回は通った」で、毎回通るとは限らない。
- 止める前の確かめの回は、記録（trace）を残さずに流したので、落ちた 1 回の中身は採点の説明でしか見ていない。
- trace（`regex` の `target: trace`）には、サブエージェント（pipe-builder）のメッセージと道具の呼び出しも入る（ラウンド 3 で、01-no-bad-shape が pipe-builder の Write の中の悪い形に当たって確かめた）。
- 正規表現の採点の限界：07-check-passed は、Claude Code が trace を JSON にするとき日本語を `\u` に逃がすと当たらない（偽の不合格に倒れる）。01-no-bad-shape は、Edit で少しずつ作った悪い形・インラインの表（`check = { … }`）・`check.judge.x = …` の形を見落とし、1 つの返事の文の中で悪い形を `[[stages]]` から引用して説明すると、正しく断っても落ちる。08-numbered-prompt は、文字の組（`[0-9]`）を含む path がファイルがあっても当たらなかったので（ラウンド 3。理由は確かめていない）、glob の無い `prompts/01_summary.md` にした。番号は合っていても名前が違う（`01_summarize.md` など）と落ちる。
- 結果の JSON の形は Claude Code の版で変わりうる。`rounds.py` は知らない形で止まるので、版が変わったら読む鍵を確かめ直す。
- サブエージェントの書き込みを断る決まりは、公式の文書の決まりとしては無い（2.1.323 の本体の判定の文で確かめた。cookbook https://platform.claude.com/cookbook/claude-agent-sdk-08-dynamic-workflows に観察の 1 文だけある）。決まりが無くなると、会話の道の名前の断りは要らない断りになり、語が増えると断りが足りなくなる。

## pipe-in への示唆

- スキルの「断って止まる」決まりは、手順の頭に短い文で置く。後ろの節に書くと、haiku は先の手順へ進む。
- それでも文だけの決まりは揺れる（`--runs 3` で 3 回に 1 回）。止まるべき所は、`pipe-in-gen` の側で機械的に断る形（引数の範囲の確かめ・警告）を重ねるのがよい。次のラウンドの候補：`--runs` の範囲を `pipe-in-gen judge-score` の前に機械で断る。
- 書けない環境で止まると、その先の不具合が隠れる。手で書く道などで先へ進めるようにすると、隠れていた不具合が採点に出る。
- 計算の結果を返すスキルは、返す形（```json の囲み）の見本を書き、「要約に置き換えない」と言い切る。
- 採点は「呼んだ」ではなく「通った」を見る。呼んだだけを見る採点は、偽の合格を出す。
- 作るかもしれないファイルを読む採点（`target` がファイル）は、作らないのが正しいケースでは使わない。trace を読む。
- 段の成果物と、サブエージェントに書かせるファイルの名前は、頭に番号を付ける。会話の中で流すとき（`/pipe-in:pipe-run`）は、`pipe-in-gen chat` が当たる名前を流す前に断る。
- `claude plugin eval` を回す環境には、`pipe-in-gen` を編集用でない入れ方（`pip install .`）で home の外に入れ、root でない利用者で流す。

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
