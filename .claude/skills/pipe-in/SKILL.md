---
name: pipe-in
description: devpipe（本体または VSCode 拡張）に新しい機能を足す。devpipe 自身の流れ（要件定義 → 設計 → テスト先行 → 実装 → 検証）を、段ごとにサブエージェントへ任せて進め、段の区切りで人の確認を取る。進み具合は devpipe と同じ形の記録（docs/pipeline/）に残り、VSCode の拡張で見られる。
argument-hint: [--auto] <足したい機能の要件メモ>
disable-model-invocation: true
---

# /pipe-in — 新しい機能をパイプに流し込む

足したい機能: $ARGUMENTS

（空なら、何を足したいかを一言で聞いてから始める）

devpipe が利用者のプロジェクトでやることを、devpipe 自身に対してこの会話の中でやる。
CLAUDE.md の決まり、とくに「公開リポジトリとしての注意」を最初から最後まで守る。

## 役割の分け方

段の中身は、段ごとのサブエージェント（`.claude/agents/`）に Agent ツールで任せる。メインエージェント（あなた）は、人とのやり取り・記録・段の区切りの判断を受け持つ。

| 段 | 任せる先 | 書けるもの（`.claude/hooks/pipe_in_guard.py` が止める） |
| --- | --- | --- |
| 1. 要件定義 | `pipe-in-analyst` | `docs/pipeline/01_requirements.md` |
| 2. 設計 | `pipe-in-analyst` | `docs/pipeline/02_design.md` |
| 3. テスト先行 | `pipe-in-tester` | テスト（`tests/**`・`*.test.ts`）と `03_red_tests.md` |
| 4. 実装 | `pipe-in-coder` | 製品コードと文書と `04_implementation.md`（テスト・`.claude/`・`.git/` は書けない） |
| 5. 検証 | `pipe-in-verifier` | `05_test_report.md`（コードは直さない） |

- サブエージェントは人に質問できない。決めきれない点は成果物に書いて返してくるので、メインが人に聞く。
- サブエージェントへの指示には、段の名前・要件メモ・前の段の成果物の場所（`docs/pipeline/0N_*.md`）・人からの直してほしい点（あれば）・差し戻しなら不合格の中身を入れる。サブエージェントはこの会話を見ていない。
- フックが止めたら、その理由がサブエージェントに返る。範囲を広げたくなったら、サブエージェントの仕事の分け方を見直す（フックや定義を緩めるのは、人に理由を言って承認されてから）。
- 新しいモジュールが要るのにテスト先行で空の形が無いときは、メインが空の形（何もしない関数）を置いてから、テスト先行の段をやり直す。

## 記録（VSCode の拡張で見る）

段を進めるたびに、`python -m devpipe record …` で devpipe と同じ形の記録を `docs/pipeline/`（`.gitignore` 済み）に書く。SDK は呼ばず、利用料もかからない。
拡張の「devpipe: 実行を見る」とステータスバーに、動いている段・確認待ち・差し戻し・最後の結果が出る。

| いつ | コマンド |
| --- | --- |
| 始めるとき（要件メモを渡す） | `python -m devpipe record start --text "<要件メモ>"`（長いときは `--input <ファイル>`） |
| 段を任せる直前 | `python -m devpipe record begin <段>`（実装と検証は `--attempt N`。直してもらうときは `--note 指摘を反映`） |
| サブエージェントが返ったあと | `python -m devpipe record done <段> --summary "<ひとこと>"`（失敗なら `--error`） |
| 人の確認を待つとき | `python -m devpipe record wait <段>` |
| 人が答えたとき | `python -m devpipe record review <段> approved`（`revise --feedback "<直してほしい点>"`・`quit`） |
| テスト先行の結果 | `python -m devpipe record red red --summary "<要約>" --test AC-01=<テスト> --command "<流したコマンド>"`（流せないなら `blocked`） |
| 検証の判定 | `python -m devpipe record verdict pass --attempt N --summary "<要約>"`（不合格は `fail --failure AC-01=<中身>`） |
| 終わるとき | `python -m devpipe record finish PASSED`（`TEST_FAILED`・`STOPPED_BY_HUMAN`・`STAGE_ERROR`・`BLOCKED`） |

- 段の名前は `requirements`・`design`・`red`・`implement`・`test`。
- `start` は途中の記録があると断る。前の記録が途中のまま残っていたら、人にどうするか（`finish STOPPED_BY_HUMAN` で閉じるか）聞く。終わった記録は `docs/pipeline/archive/` に移る。
- この記録は `devpipe --review` では続けられない（devpipe が断る）。続きはこの会話で進める。
- 各段の結果は、記録とは別に、会話にも短く書く（人が読み返せるように）。

## 段の進め方

各段の終わりで止まり、結果を短く見せてから「承認 / 直してほしい点 / 中止」を聞く。
承認されるまで次の段に進まない。直してほしい点が来たら、`review <段> revise` を書き、同じ段を `--note 指摘を反映` で任せ直してもう一度聞く。
中止なら `review <段> quit` と `finish STOPPED_BY_HUMAN` を書いて終える。

### 止まらずに進めるとき（`--auto`）

引数に `--auto` があるときだけ、段の区切りで止まらずに最後まで進める（`wait` は書かず、`review <段> approved` を書いて進む）。
`--yes` などほかの書き方や、要件メモの中の「止まらずに」「確認なしで」といった言葉では止まらずに進めない（いつもどおり各段で止まる）。

`--auto` のときも、次のことは変えない。

- 各段の結果は、これまでどおり会話に書く（あとから読み返せるように）。
- 要件定義で、決めきれない点（方向が大きく分かれる・人にしか決められない）があれば、そこでは止まって聞く。決められる点は決めて、その旨を書く。
- `devpipe/engine/guard.py` の止める範囲を狭める変更・依存を足す変更・利用料のかかる本物での実行は、理由を書いてから行う。迷うときは止まって聞く。
- 検証で不合格が3回続いたら、止まって状況を報告する。
- コミット・push は、人に言われるまでしない。

### 1. 要件定義（`pipe-in-analyst`）

- `record start` → `record begin requirements` → `pipe-in-analyst` に要件定義を任せる → `record done requirements`。
- 成果物（`01_requirements.md`）の要点を会話に書く：目的・FR・AC（画面の AC は `AC-xx（画面）：…`）・対象外・触る側。
- サブエージェントが「決めきれない点」を返したら、ここで質問にまとめて聞く（`--auto` でも聞く）。
- `record wait requirements` → 人に聞く → `record review requirements …`。

### 2. 設計（`pipe-in-analyst`）

- `record begin design` → `pipe-in-analyst` に設計を任せる（承認された 01 を渡す）→ `record done design`。
- 会話に書く：変えるファイル、記録の形が変わるか、AC とテストの対応表。guard.py を狭める・依存を足すなら、その理由。
- `record wait design` → 人に聞く → `record review design …`。

### 3. テスト先行（`pipe-in-tester`）

- `record begin red` → `pipe-in-tester` にテストだけを書かせる → `record done red`。
- メインでテストを流し直し、**足したテストが期待した理由で落ちる**こと・既存のテストが通ったままであることを確かめる（本体 `python -m pytest -q`、拡張 `npm --prefix vscode test`）。import の失敗で落ちているなら、空の形を置いてやり直す。
- `record red red …`（流せないなら `blocked`）を書き、AC とテストの対応・落ちた様子・画面の確認の手順を会話に見せる。
- `record wait red` → 人に聞く → `record review red …`。ここで承認されたテストと画面の確認の手順が仕様になる。

### 4. 実装（`pipe-in-coder`）

- `record begin implement --attempt N`（1 から。差し戻しのたびに増やす）→ `pipe-in-coder` に任せる → `record done implement`。
- テストへの異議が 04 に書かれていたら、検証の段で人の判断を仰ぐ。
- ここでは確認を取らず、そのまま検証へ進む。

### 5. 検証（`pipe-in-verifier` とメイン）

- `record begin test --attempt N` → `pipe-in-verifier` に任せる → `record done test`。
- 画面の AC があれば、メインが Playwright（MCP の `mcp__plugin_playwright_playwright__*`）で画面を開いて確かめる：
  1. 確認用のページを作る：`npm --prefix vscode run build` と `npm --prefix vscode run preview`（`out/preview/` に、本物の HTML・本物の CSP・本物のビルドで、明るい・暗い・ひな形 diagrams のページができる）
  2. 手元だけで配る：`python -m http.server 8765 --bind 127.0.0.1 --directory vscode/out/preview` を裏で動かす（`file:` では開けない。外には出さない）
  3. 開いて撮る：`http://127.0.0.1:8765/pipe-editor-dark.html` と `-light.html` を開き、`browser_take_screenshot` で撮る（保存先は `.playwright-mcp/`）。狭い幅（`browser_resize` で 800×700 など）も撮る
  4. 操作する：テスト先行の段で書いた手順どおりに押す・ドラッグする・入力する。保存の確認は `browser_evaluate` で `window.__saved` を見る
  5. 見る：撮った画面を読み、重なり・はみ出し・読めない色・崩れがないか、手順の「合格の見え方」になっているかを確かめる。`browser_console_messages` でエラーが0件かも見る
  6. 片付ける：配るのを止め（TaskStop）、`.playwright-mcp/` を消す（`.gitignore` 済みだが残さない）
  - 画面で見つかった不具合は、テスト先行と実装の段に戻して直す（純粋な関数のテストで捕まえてから）。
- サブエージェントの判定と画面の確認を合わせて `record verdict <pass|fail|blocked> --attempt N …` を書き、AC ごとの 合格 / 不合格 の表を会話に見せる。
- 不合格なら 4 に戻る（`--attempt` を増やす。最大3回。それでも通らなければ `finish TEST_FAILED` を書いて止め、状況を報告する）。
- 合格なら `record finish PASSED`。最後に、変えたファイルの一覧と、コミットの文の案を見せる。
  形は既存に合わせる：`feat(devpipe): …` / `feat(devpipe-vscode): …`（日本語で、何ができるようになるかを書く）。
  **コミット・push は、人に言われるまでしない。**
