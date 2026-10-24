---
name: pipe-in
description: devpipe（本体または VSCode 拡張）に新しい機能を足す。devpipe 自身の流れ（要件定義 → 設計 → テスト先行 → 実装 → 検証）を、段ごとにサブエージェントへ任せて進め、段の区切りで人の確認を取る。進み具合は devpipe と同じ形の記録（docs/pipeline/）に残り、VSCode の拡張で見られる。
argument-hint: [--auto] [--artifact] <足したい機能の要件メモ>
disable-model-invocation: true
---

# /pipe-in — 新しい機能をパイプに流し込む

足したい機能: $ARGUMENTS

（空なら、何を足したいかを一言で聞いてから始める）

devpipe が利用者のプロジェクトでやることを、devpipe 自身に対してこの会話の中でやる。
開発のルール（`docs/development/`）と CLAUDE.md の決まり、とくに「公開リポジトリとしての注意」を最初から最後まで守る。
段の成果物（`docs/pipeline/`）は手元の作業の記録で、追跡しない。追跡して残すのは、検証の段で書く決定の記録（`docs/decisions/`）だけ。
長い会話では、自動の要約のあとにこのスキルの後ろの方（検証の手順など）が抜けやすい。手順があやふやになったら、`.claude/skills/pipe-in/SKILL.md` の該当する節を読み直す。

## 0. 始める前に

- 機能ごとのブランチと worktree で作業する（`docs/development/workflow.md` の「1. 始める」）。
  - いちばん確かなのは、会話を worktree のフォルダで始めること。会話を worktree の中で始めたとき、または下の EnterWorktree で移ったあとは、そのまま進める。
  - 会話が main の作業フォルダで始まっていたら、先に下の `git status` を見てから、`git worktree add ../pipe-in-<名前> -b feat/<名前>` で切り、`EnterWorktree` に `path`（切った worktree の絶対パス）を渡して、会話ごと移る（切ったこと・移ったことを伝える）。`cd` では移れない（プロジェクトの外へ出ると戻される）。人が打つ `/cd <パス>` でも移れる。
  - 移るのは、段のサブエージェントが会話のその時の作業フォルダから始まり、フック（`.claude/hooks/pipe_in_guard.py`）がその `cwd` を基準に書ける場所を決めるため。移らずに任せると、main を基準に判定されて、worktree への書き込みが止まる。
  - `../pipe-in-<名前>` は `.claude/worktrees/` の外なので、EnterWorktree は移るたびに人の承認を求める（`--auto` でもここは人が答える）。EnterWorktree で新しく作る形（`name`）はブランチ名が決まりと合わないので使わず、`git worktree add` で切ってから `path` で移る。
  - `docs/pipeline/` の記録も、その worktree の中にできる。
- main の作業フォルダの `git status` で、ほかの会話のまだコミットしていない変更がないかを見る（EnterWorktree で移る前に見る。移ったあとは main の作業フォルダを指す git のコマンドが止められる）。あれば、どのファイルかを人に伝える（あとで main に入れるときに重なりを確かめる）。
- フック（`.claude/hooks/pipe_in_guard.py`）は `python` が動いて初めて働く。始める前に `python --version` で確かめる（動かないと、段のサブエージェントの書き込みと Bash の絞りが外れて通る。`docs/guide/develop.md` の「フックが働く条件」・D0032）。
- worktree の中では、直したコードを確かめるのに `python -m devpipe …`・`python -m pytest` を使う（`devpipe-gen` などのコマンドは main のコードを動かす）。拡張を触るなら、その worktree で `npm --prefix vscode ci` をする。

## main が進んだら載せ直す

並列で動かしているので、作業のあいだに main が進む。やり方は `docs/development/workflow.md` の「3. 載せ直す」。

- **段の区切り**（各段が終わって、人に確認を取る前）に `git log --oneline HEAD..main` を見る。コミットがあれば、何が入ったかを会話に書き、`git rebase --autostash main` で載せ直す。
- **検証の段の前**と、**main に入れる直前**には、必ず載せ直す。
- ぶつかったら、worktree の中で両方の意図を残すように合わせる。迷うときは人に聞く（`--auto` でも聞く）。
- 載せ直したら、触った側のテストを流し直す。テスト先行より後なら、承認されたテストが新しい main の上でも同じ理由で赤（または緑）のままかを確かめ、意味が変わっていたらその段に戻る。
- 合わせたこと・main に合わせて直したことは、決定の記録に短く書く。
- 決定の記録の番号 `Dnnnn` を決める（`docs/decisions/` の次の番号）。受け入れ基準の ID は `Dnnnn-AC-xx` にする（`docs/development/specs.md`）。

## 役割の分け方

段の中身は、段ごとのサブエージェント（`.claude/agents/`）に Agent ツールで任せる。メインエージェント（あなた）は、人とのやり取り・記録・段の区切りの判断を受け持つ。
段のサブエージェントに `isolation: worktree` は付けない（main から一時の worktree が切られ、機能のブランチの変更も `docs/pipeline/` の記録も見えなくなるため）。

| 段 | 任せる先 | 書けるもの（`.claude/hooks/pipe_in_guard.py` が止める） |
| --- | --- | --- |
| 1. 要件定義 | `pipe-in-analyst` | `docs/pipeline/01_requirements.md` |
| 2. 設計 | `pipe-in-analyst` | `docs/pipeline/02_design.md` |
| 3. テスト先行 | `pipe-in-tester` | テスト（`tests/**`・`*.test.ts`）と `03_red_tests.md` |
| 4. 実装 | `pipe-in-coder` | 製品コードと文書と `04_implementation.md`（テスト・`.claude/`・`.git/` は書けない） |
| 5. 検証 | `pipe-in-verifier` | `05_test_report.md`（コードは直さない） |

検証で合格したあとに流す文書をそろえること・監査と助言（と審査）は、段ではない（記録の段は5つのまま。`record` は書かない）。

| すること | 任せる先 | 書けるもの |
| --- | --- | --- |
| 文書をそろえる（変えたものに合わせる） | `pipe-in-documenter` | `README.md`・`vscode/README.md`・`pipes/README.md`・`docs/assets/README.md` と `docs/guide/`・`docs/development/` の `.md`（CLAUDE.md・`.claude/`・決定の記録は案を返す） |
| 監査（文書・定義・コードの食い違い） | `pipe-in-auditor` | どこにも書けない（報告を返すだけ） |
| 助言（公式の文書との照らし合わせ） | `pipe-in-advisor` | どこにも書けない（Web は公式の文書だけ） |
| 審査（助言の報告をルーブリックで採点） | `pipe-in-judge` | どこにも書けない（Web は公式の文書の WebFetch だけ） |

- サブエージェントは人に質問できない。決めきれない点は成果物に書いて返してくるので、メインが人に聞く。
- 会話から任せたサブエージェントは裏で動き、終わると返事（完了の通知）が次の番に届く。段の `record done` は、その返事を受けてから書く。
- サブエージェントへの指示には、段の名前・要件メモ・決定の記録の番号 `Dnnnn`・前の段の成果物の場所（`docs/pipeline/0N_*.md`）・人からの直してほしい点（あれば）・差し戻しなら不合格の中身を入れる。サブエージェントはこの会話を見ていない。
- サブエージェントは、段に合わせて `docs/development/` の決まりを読む（要件定義は `specs.md`、設計は `design.md`、テスト先行は `testing.md`、実装は `design.md` と `workflow.md` の「4. そろえる」）。指示にもその文書を書く。
- フックが止めたら、その理由がサブエージェントに返る。範囲を広げたくなったら、サブエージェントの仕事の分け方を見直す（フックや定義を緩めるのは、人に理由を言って承認されてから）。フック自体が失敗して止めたとき（理由が「フックの判断が失敗したため止めました」）は、サブエージェントが親に知らせてくるので、`.claude/hooks/pipe_in_guard.py` を人に見せて直す。
- 新しいモジュールが要るのにテスト先行で空の形が無いときは、メインが空の形（何もしない関数）を置いてから、テスト先行の段をやり直す。

## 記録（VSCode の拡張で見る）

段を進めるたびに、`python -m pipe_in record …` で devpipe と同じ形の記録を `docs/pipeline/`（`.gitignore` 済み）に書く。SDK は呼ばず、利用料もかからない。
拡張の「pipe-in: 実行を見る」とステータスバーに、動いている段・確認待ち・差し戻し・最後の結果が出る（並列の実行や別の worktree の確認待ちがあるときは、ステータスバーは `動き N・確認待ち M` の件数になり、段や結果は説明に出る）。

| いつ | コマンド |
| --- | --- |
| 始めるとき（要件メモを渡す） | `python -m pipe_in record start --text "<要件メモ>" --name "<セッション名>"`（長いときは `--input <ファイル>`。`--name` を省くと要件メモの最初の行から作る。今の会話の ID を `--session-id "${CLAUDE_SESSION_ID}"` で付ける（スキルが呼ばれたときに今の会話の ID に置き換わる）。空白や改行を含む値と 100 文字を超える値は断られる） |
| 段を任せる直前 | `python -m pipe_in record begin <段> --agent <サブエージェント>`（要件定義と設計は `pipe-in-analyst`、テスト先行は `pipe-in-tester`、実装は `pipe-in-coder`、検証は `pipe-in-verifier`。VSCode の時系列の行に出る。実装と検証は `--attempt N`。直してもらうときは `--note 指摘を反映`） |
| サブエージェントが返ったあと | `python -m pipe_in record done <段> --summary "<ひとこと>"`（失敗なら `--error`） |
| 人の確認を待つとき | `python -m pipe_in record wait <段>` |
| 人が答えたとき | `python -m pipe_in record review <段> approved`（`revise --feedback "<直してほしい点>"`・`quit`） |
| テスト先行の結果 | `python -m pipe_in record red red --summary "<要約>" --test Dnnnn-AC-01=<テスト> --command "<流したコマンド>"`（流せないなら `blocked`） |
| 検証の判定 | `python -m pipe_in record verdict pass --attempt N --summary "<要約>"`（不合格は `fail --failure Dnnnn-AC-01=<中身>`） |
| 終わるとき | `python -m pipe_in record finish PASSED`（`TEST_FAILED`・`STOPPED_BY_HUMAN`・`STAGE_ERROR`・`BLOCKED`） |

- 段の名前は `requirements`・`design`・`red`・`implement`・`test`。
- `start` は途中の記録があると断る。前の記録が途中のまま残っていたら、人にどうするか（`finish STOPPED_BY_HUMAN` で閉じるか）聞く。終わった記録は `docs/pipeline/archive/` に移る。
- この記録は `devpipe --review` では続けられない（devpipe が断る）。続きはこの会話で進める。
- 各段の結果は、記録とは別に、会話にも短く書く（人が読み返せるように）。

## 進み具合をアーティファクトで見る（`--artifact`）

引数に `--artifact` があるときだけ、進み具合を claude.ai のアーティファクト（会話の横のページ）でも見られるようにする（D0027）。`--auto` と一緒に使える。`--auto` と同じく、要件メモの中の「アーティファクトで」といった言葉では有効にしない（旗を付けたときだけ）。Artifact と ArtifactData のツールがある会話でだけ使える（claude.ai にログインした Claude Code の CLI・デスクトップアプリ・claude.ai/code。API キー・Bedrock・Vertex・`-p`・Agent SDK では使えない。https://code.claude.com/docs/en/artifacts ）。道具が無ければ、そう伝えて `--artifact` なしで進める。ページは見るだけで、承認・直してほしい点・中止は、これまでどおり会話で聞く。

1. `record start` の直後に、ページの HTML を作る：`python -m pipe_in live page --out <一時フォルダ>/pipe-in-live.html`。一時フォルダは会話の作業用の場所（scratchpad。無ければ OS の一時フォルダ）で、リポジトリの中には置かない。
2. その HTML を Artifact で1回だけ公開する。`capabilities` は `{"db": {}}`、`icon` は `chart`。HTML は書き換えない。公開した URL を覚えておき、人に伝える（はじめは持ち主だけが見られ、共有するかは人が決める、と添える）。公開し直さない（ページは db の変更を受けて自分で描き直す）。
3. `python -m pipe_in record …` を実行するたびに（`start`・`begin`・`done`・`wait`・`review`・`red`・`verdict`・`finish`）、すぐあとに写しを作る：`python -m pipe_in live snapshot --out <一時フォルダ>/pipe-in-live.json`（`--out` は `docs/pipeline/` の中を断る）。
4. その写しを ArtifactData の `set` で書く：`url` は 2. の URL、`collection` は `runs`、`doc_id` は `current`、`file_path` は 3. の JSON。毎回、同じドキュメントを丸ごと置き換える。最初の1回は `if_version` を付けず、2回目からは前の `set` の結果の `version` を `if_version` に渡す。版が合わないと断られたら、`get` で今の `version` を読んで1回だけやり直す。
5. 写しや書き込みに失敗しても段は止めず、人に一言伝えて続ける（記録の本体は `docs/pipeline/` にある）。
6. 写しには、要件メモの本文・セッション ID・パス・段の要約や差し戻しの理由などの自由な文・ログの中身は入らない（`docs/guide/records.md` の「アーティファクトに出す写し」）。中身を足したくなったら、写しの形を変える `/pipe-in` にする（ここで写しを手で書き足さない）。

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
- `pipe_in/engine/guard.py` の止める範囲を狭める変更・依存を足す変更・利用料のかかる本物での実行は、理由を書いてから行う。迷うときは止まって聞く。
- 検証で不合格が3回続いたら、止まって状況を報告する。
- 検証のあとの文書係の案（CLAUDE.md・`/pipe-help`・`.claude/` の定義）も、`--auto` でも見せて聞く（案が無ければ聞かない）。
- 検証のあとの監査と助言（と審査）は、`--auto` でも報告を見せて止まる（直す項目は人しか選べない）。2つとも0件なら止まらずに進む（助言の項目が無いので審査も流さない）。
- コミット・push は、人に言われるまでしない。

### 1. 要件定義（`pipe-in-analyst`）

- `record start` → `record begin requirements` → `pipe-in-analyst` に要件定義を任せる → `record done requirements`。
- 成果物（`01_requirements.md`）の要点を会話に書く：目的・FR・AC（`Dnnnn-AC-xx`。画面の AC は `Dnnnn-AC-xx（画面）：…`、手で・実機で確かめるものは `（手で）`・`（実機）`）・対象外・触る側。
- サブエージェントが「決めきれない点」を返したら、ここで質問にまとめて聞く（`--auto` でも聞く）。
- `record wait requirements` → 人に聞く → `record review requirements …`。

### 2. 設計（`pipe-in-analyst`）

- `record begin design` → `pipe-in-analyst` に設計を任せる（承認された 01 を渡す）→ `record done design`。
- 会話に書く：変えるファイル（`docs/development/design.md` の置き場所の表と層に沿って）、記録・設定・パイプ・置き場所の形が変わるか（古いものをどう扱うか）、AC とテストの対応表。guard.py・guard_hook.py・pipe_in_guard.py を狭める・依存を足すなら、その理由。
- `record wait design` → 人に聞く → `record review design …`。

### 3. テスト先行（`pipe-in-tester`）

- `record begin red` → `pipe-in-tester` にテストだけを書かせる → `record done red`。
- メインでテストを流し直し、**足したテストが期待した理由で落ちる**こと・既存のテストが通ったままであることを確かめる（本体 `python -m pytest -q`、拡張 `npm --prefix vscode test`）。やり方は `docs/development/testing.md` の「赤の確かめ方」：足したテストのファイルだけを流し、失敗を1件ずつ、出力を切らずに読む。構文・つづり・補助の誤りで落ちているのは赤ではない。import の失敗で落ちているなら、空の形を置いてやり直す。今の作りのままで通るテストは、そう書く。
- テストの名前（拡張）か docstring（Python）の頭に `Dnnnn-AC-xx:` が付いているか、リポジトリの実物（`pipes/`・`.devpipe/`・`docs/pipeline/` の記録の外）に書いていないかも見る。
- `record red red …`（流せないなら `blocked`）を書き、AC とテストの対応・落ちた様子・画面の確認の手順を会話に見せる。
- `record wait red` → 人に聞く → `record review red …`。ここで承認されたテストと画面の確認の手順が仕様になる。

### 4. 実装（`pipe-in-coder`）

- `record begin implement --attempt N`（1 から。差し戻しのたびに増やす）→ `pipe-in-coder` に任せる → `record done implement`。
- テストへの異議が 04 に書かれていたら、検証の段で人の判断を仰ぐ。
- 文書がそろっているか（`docs/development/workflow.md` の「4. そろえる」）を 04 で確かめる。足りなければ、同じ段で直してもらう。
- ここでは確認を取らず、そのまま検証へ進む。

### 5. 検証（`pipe-in-verifier` とメイン）

- 任せる前に、main が進んでいれば載せ直して、テストを流し直す（上の「main が進んだら載せ直す」）。
- `record begin test --attempt N` → `pipe-in-verifier` に任せる → `record done test`。
- 画面の AC があれば、メインが Playwright（MCP。道具の名前は、プラグイン版なら `mcp__plugin_playwright_playwright__*`、`claude mcp add` で入れた版なら `mcp__playwright__*`）で画面を開いて確かめる：
  1. 確認用のページを作る：`npm --prefix vscode run build` と `npm --prefix vscode run preview`（`out/preview/` に、本物の HTML・本物の CSP・本物のビルドで、明るい・暗い・ひな形 diagrams の作業台のページと、明るい・暗いのパネルのページ（`run-panel-light.html`・`run-panel-dark.html`。見本の記録 `tests/fixtures/showcase/` から）と、動いている・確認待ちのパネルのページ（`run-panel-running-*.html`・`run-panel-waiting-*.html`。`tests/fixtures/showcase_running/` などから）と、実行の一覧のパネルのページ（`run-panel-runs-light.html`・`run-panel-runs-dark.html`・`run-panel-runs-omitted-dark.html`。見本から一時フォルダに主の checkout・別の worktree・`archive/` の木を組み立てて作る）と、更新なしの印が出るパネルのページ（`run-panel-stale-light.html`・`run-panel-stale-dark.html`（目安を過ぎた見本）・`run-panel-stale-soon-dark.html`（目安の 5 秒手前の見本。`window.__previewNext()` で更新後の本体を送れる）。動いている見本は一時フォルダに写してログの更新時刻を「今」からの相対にそろえる）と、成果物のタブのパネルのページ（`run-panel-artifacts-light.html`・`run-panel-artifacts-dark.html`。動いている開発フローと 12 個のパイプの 2 つの実行を持つ。`window.__previewNext()` で動いている段が進んだ本体を送れ、`window.__posted` に送ったメッセージの種類が貯まる。成果物は一時フォルダに作り、更新時刻を固定の値にそろえる）ができる）
  2. 手元だけで配る：`python -m http.server 8765 --bind 127.0.0.1 --directory vscode/out/preview` を裏で動かす（`file:` では開けない。外には出さない）
  3. 開いて撮る：`http://127.0.0.1:8765/pipe-editor-dark.html` と `-light.html` を開き、`browser_take_screenshot` で撮る（保存先は `.playwright-mcp/`）。狭い幅（`browser_resize` で 800×700 など）も撮る。パネルのページ（`http://127.0.0.1:8765/run-panel-dark.html` と `-light.html`、動いている・確認待ち・実行の一覧・更新なしの `run-panel-*.html`）も同じように開いて撮る。実行の一覧のページは幅 1280×800・1000×700・800×600 で並び（3 領域・2 列・1 列）を見る。更新なしのページは、印の時間が 1 秒ごとに増えること、`run-panel-stale-soon-dark.html` で 5 秒待つと印が一度に現れ `window.__previewNext()` で消えること、既存のページには 15 秒待っても印が出ないことを見る。成果物のタブのページ（`run-panel-artifacts-*.html`）は「成果物」のタブを開き、幅 1280×800・1000×700・801 と 800 の幅、高さ 400 の低い窓でも開いて、ページに横スクロールが出ないこと、プレビューの枠が窓に収まること、行を押しても `window.__posted` が増えないこと、`window.__previewNext()` で既定の行が移ることを見る（パネルには保存が無いので、4. の `window.__saved` の確認は作業台のページだけ）
  4. 操作する：テスト先行の段で書いた手順どおりに押す・ドラッグする・入力する。保存の確認は `browser_evaluate` で `window.__saved` を見る
  5. 見る：撮った画面を読み、重なり・はみ出し・読めない色・崩れがないか、手順の「合格の見え方」になっているかを確かめる。`browser_console_messages` でエラーが0件かも見る
  6. 片付ける：配るのを止め（TaskStop）、`.playwright-mcp/` を消す（`.gitignore` 済みだが残さない）
  - 画面で見つかった不具合は、テスト先行と実装の段に戻して直す（純粋な関数のテストで捕まえてから）。
- サブエージェントの判定と画面の確認を合わせて `record verdict <pass|fail|blocked> --attempt N …` を書き、AC ごとの 合格 / 不合格 の表を会話に見せる。
- 不合格なら 4 に戻る（`--attempt` を増やす。最大3回。それでも通らなければ `finish TEST_FAILED` を書いて止め、状況を報告する）。
- 合格なら、下の「文書をそろえる」と「監査と助言」を流してから、決定の記録を書く。

### 文書をそろえる（検証で合格したあと、監査の前）

実装の段でも文書をそろえるが、見落としを拾うために、検証で合格したあと（`record verdict pass` のあと）、監査の前にもう一度 `pipe-in-documenter` に見てもらう（`/pipe-docs` と同じ）。不合格・blocked では流さない。監査は、そろえたあとの文書を見る。

1. 変えたファイルの一覧（下の「監査と助言」の 1. と同じ）と、変更の要点（承認された 01・02 から）と、決定の記録の番号 `Dnnnn` を渡して任せる。
2. 返ってきた「文書の報告」を会話に書き、文書係が直したファイルを `git diff` で読んで、実物と合っているかを確かめる。
3. 「書けないので案にしたもの」（CLAUDE.md・`/pipe-help`・`.claude/` の定義）は、監査と助言の報告と一緒に見せて、人に入れるかを聞く（`--auto` でも聞く。案が無ければ聞かない）。決定の記録の案は、決定の記録を書くときに使う。
4. 直したら、触った側のテストを流し直す（`python -m pytest -q`。文書は `tests/test_guide.py`・`tests/test_readme.py`・`tests/test_rules.py` などが検査する）。

### 監査と助言（検証で合格したあと、決定の記録の前）

検証で合格したあと（`record verdict pass` のあと）、決定の記録の前に流す。不合格・blocked では流さない。

1. 変えたファイルの一覧を作る：`git diff --name-only main...HEAD`（このブランチのコミット）と `git status --short`（まだコミットしていない変更と新しいファイル）を合わせる。
2. 監査：一覧と、それを指す・それが指すファイルを範囲として `pipe-in-auditor` に任せる。
3. 助言：一覧に `.claude/`・`plugin/`・`.claude-plugin/`・`pipe_in/engine/runner.py`・`pipe_in/engine/guard.py`・`generator/guard_hook.py` のどれかがあるときだけ、その部分をテーマにして `pipe-in-advisor` に任せる。無ければ流さず、「助言は流さなかった（理由：…）」と会話に書く。
4. 審査：助言を流したときは、続けて `pipe-in-judge` に助言の報告を採点させる（`/pipe-judge` と同じ。報告の全文・テーマ・advisor の道具の呼び出しの回数を渡す）。助言を流さなかったとき、または助言が0件のときは審査も流さず、「審査は流さなかった（理由：…）」と会話に書く。
   - 審査の合否は人が読む材料。fail でも自動で直さない・差し戻さない・決定の記録へ進むのを止めない。直す項目は、今までどおり監査・助言の ID で人が選ぶ。
5. 2つの報告と審査の採点（JSON）を会話に全文見せる。採点は助言の報告と一緒に見せて止まる。どの ID を直すかを人に聞く。--auto でも止まる。2つとも0件なら止まらずに決定の記録へ進む。
6. 人が承認した項目だけをメインが直す（サブエージェントは直さない）。直すのは、このブランチで変えたファイルに関わる項目の、文書・定義・コメントまで。関係の無い項目は直さず、決定の記録の「対象外・残った課題」に書く（別の `fix/`・`docs/` のブランチで直す）。コードの振る舞いを変える項目は、この機能の合格に要るなら人に聞いてテスト先行の段に戻し、そうでなければ「残った課題」に書く。
7. 直したら、触った側のテストを流し直す。
8. 決定の記録に、承認して直した項目と、直さなかった大事な項目の要約と、審査の採点の要約（overall・verdict）を書く（報告の全文は貼らない）。

### 決定の記録と仕上げ

- メインが決定の記録 `docs/decisions/Dnnnn-<名前>.md` を書き、`docs/decisions/README.md` の表に1行足す（形は `docs/development/specs.md`。`tests/test_rules.py` が検査するので、書いたらもう一度流す）。決めたことと理由・受け入れたリスク・確かめたこと（手で・実機で確かめていないものは「まだ」）を書く。`docs/pipeline/` の中身をそのまま貼らない（セッション ID や手元のパスが入っている）。
- `record finish PASSED`。`git status` で自分の変更だけであることを見て、`git diff` で公開してよいかを確かめる。最後に、変えたファイルの一覧と、コミットの文の案を見せる。
  形は既存に合わせる：`feat(devpipe): …` / `feat(devpipe-vscode): …`（日本語で、何ができるようになるかを書く。本文に決定の記録の番号）。1つの機能を1つのコミットにする。
  **コミット・main に入れる・push は、人に言われるまでしない。**
- main に入れるよう言われたら：もう一度 main が進んでいないかを見て、進んでいれば載せ直してテストを流し直す。EnterWorktree で移っていたら、先に `ExitWorktree`（`keep`）で main の作業フォルダに戻る。main の作業フォルダで `git merge --ff-only <ブランチ>` をする（早送りだけ）。ほかの会話のまだコミットしていない変更と同じファイルで断られたら、その作業を stash せず、自分のブランチ側からそのファイルの変更を外すか、待つかを人に聞く。入れたら worktree とブランチを片付ける。
