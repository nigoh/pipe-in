# 設計の決まり

## 置き場所

| やりたいこと | 場所 |
| --- | --- |
| 入口（pipe-in コマンド） | `pipe_in/cli.py` |
| 前の名前のコマンドの別名（0.3 の間だけ。案内を出して新しい入口を呼ぶ） | `pipe_in/legacy.py`・`generator/legacy.py` |
| どのパイプにも共通：段の実行・記録・確認・まとめ | `pipe_in/engine/pipeline.py` |
| 記録（`state.json`）の土台：鍵の並び・`schema`・費用と使用量の「測れた」「取れない」の2通りを決める `new_state`（標準ライブラリだけ。3つの書き手が呼ぶ） | `pipe_in/engine/state.py` |
| 段の設定の型・protected_paths・段の費用の上限を決める `stage_budget_usd`（SDK に渡す値と記録に残す値は、必ずこの関数から取る） | `pipe_in/engine/spec.py` |
| 止める操作（pipe-in が流す段の PreToolUse フック）と、Bash のコマンドの文字列から書き込み先を読む部品（標準ライブラリだけ。シェルは起こさない） | `pipe_in/engine/guard.py`・`bashwrite.py` |
| SDK の呼び出し（段のログの `Prompt` 行の形もここ） | `pipe_in/engine/runner.py` |
| 記録に書く時刻の書き方（UTC からのずれつき、秒まで） | `pipe_in/engine/clock.py` |
| 設定の読み込み（`max_budget_usd` の値の検査もここ。`pipe.toml` 側も同じ判定と文を使う） | `pipe_in/engine/config.py` |
| セッション名の取り方と、セッション ID・受け持ちの検査（標準ライブラリだけ。拡張の `sessionName.ts` と同じ規則を、同じ表で確かめる） | `pipe_in/engine/session.py`・共通の表 `tests/fixtures/session_names.json` |
| 記録の鍵 `max_budget_usd`・`resumed` を、本体が書く側と拡張が読む側で結ぶ共通の表（見本の記録ではない。本体と拡張のテストが同じ表を読む） | `tests/fixtures/budget_record.json` |
| 記録の鍵 `stages[].check`・`runs[]` の `check` の `attempt` を、本体が書く側と拡張が読む側で結ぶ共通の表（見本の記録ではない。本体と拡張のテストが同じ表を読む） | `tests/fixtures/check_record.json` |
| 記録の鍵 `stages[].group`（並列の枠の名前）を、本体が書く側と拡張が読む側で結ぶ共通の表（見本の記録ではない。本体と拡張のテストが同じ表を読む） | `tests/fixtures/group_record.json` |
| 記録の土台（`schema`・鍵の並び・費用と使用量の値の種類）を、3つの書き手（SDK・開発用・会話）と拡張が読む側で結ぶ共通の表（見本の記録ではない。本体と拡張のテストが同じ表を読む） | `tests/fixtures/state_record.json` |
| 検査の二重化（`check_pipe` と `validatePipe`）の見本と、両側のテスト | `tests/fixtures/check_parity/`・`tests/test_check_parity.py`・`vscode/src/app/pipeCheckParity.test.ts` |
| 進み具合の写し（`state.json` などから、Claude のアーティファクトに出す JSON を作る。標準ライブラリだけ）と、そのページの HTML（外部の読み込みは書体の Google Fonts の `<link>` 2本だけ）、コマンド `pipe-in live`、記録を見張って変わったときだけ1行を出す `pipe-in live watch`（読むだけ。時計・眠り・読み・書きは引数で差し替える）、ページから来た答えの文を作る・読む・記録と照らす `live_answer.py`（ほかの部品を読まない葉。`live.py` は識別子と段の形のためにこれだけを読む）とコマンド `pipe-in live answer`（記録は変えない） | `pipe_in/engine/live.py`・`live_page.py`・`live_cmd.py`・`live_watch.py`・`live_answer.py` |
| 実行パネルの返事のファイル（D0079。実行のフォルダの `reply.json`）を読む・今の待ちと照らす・消す部品と、端末の行の元（標準ライブラリと `live_answer.py` の定数だけ。返事を作る関数は持たない。リンクは辿らない。断る理由は決まった一覧で、入力の文字は入れない。端末の行は、錠を持たない読み方で、頼まれたときだけ 1 行読む）。人の確認の待ち方は `checkpoint.py` が持ち、標準入力が端末のときだけ、標準入力と返事のファイルを 0.5 秒ごとに一緒に待つ | `pipe_in/engine/reply.py`・`pipe_in/engine/checkpoint.py` |
| 使用量の集計と表 | `pipe_in/usage/` |
| 流す前の費用の目安：モデルの系統ごとの「1ターンの費用」の表（`prices.py`。直すのはここだけ）と、段のリスト → 少なめ・多め・前の実績・注意の文の計算（`estimate.py`）。どちらも標準ライブラリだけで、ファイル・SDK・時計に触れない（今日は引数）。入口 `pipe-in estimate` と本流の確認前の 2 行は、段のリストの組み立てと `state.json` の読み出しも含めて `estimate_cmd.py`（読むだけで書かない） | `pipe_in/usage/prices.py`・`pipe_in/usage/estimate.py`・`pipe_in/estimate_cmd.py` |
| 費用の目安の単価表・計算のケース・注意の文を、本体（`prices.py`・`estimate.py`）と拡張（`costEstimate.ts`）で結ぶ共通の表（見本の記録ではない。本体と拡張のテストが同じ表を読む。単価表を直すときは3か所を一緒に直す） | `tests/fixtures/cost_estimate.json` |
| 開発フロー（5段・差し戻し・指示文） | `pipe_in/dev/` |
| パイプ（定義の読み込み・検査・探す順番・流れ・権限の型） | `pipe_in/pipe/`（警告は `lint.py`。誤りの検査 `check_pipe` とは別で、`definition` だけを読む） |
| 前のパイプの記録を受ける（`--after`。前の記録を読んで受けてよいかを決める・断る文・後ろの段が前の記録を書けない守りの判定・流す前の1行。記録の受け渡しは `pipeline.py` と `specs.py` が行う） | `pipe_in/pipe/after.py` |
| 検証の審査の計算（`[stages.check.judge]`。合否・平均・直す点。標準ライブラリだけ。`generator/judge_score.py` と決まりを同じにして二重に持つ） | `pipe_in/pipe/judge.py` |
| ジェネレーター（pipe-in-gen・環境の検出・ひな形） | `generator/`（Python では `pipe_in_generator`）・`generator/templates/` |
| Claude Code のプラグイン（スキル・エージェント・フックの定義。作る `pipe-build`・検査 `pipe-eval`・審査 `pipe-judge`・進み具合を見る `pipe-live` のスキル、エージェント `pipe-builder`・`pipe-judge`。`plugin/skills/pipe-build/references/stage-rules.md` は段の決め方と検査・審査の組み方と比較実験から分かった組み方の目安で、pipe-builder に絶対パスで渡して Read させる。プラグイン自身の確かめのケースは `plugin/evals/` に、ケースごとのフォルダで置く（`claude plugin eval` 用の `prompt.md`・採点の `graders`・`case.yaml`・`scaffold.sh`・`scaffold.py`。ケースの形の検査は `tests/test_plugin_evals.py`）） | `.claude-plugin/marketplace.json`・`plugin/` |
| プラグインのフックの本体（pipe-builder と pipe-judge の操作を絞る） | `generator/guard_hook.py` |
| 会話の中で流す段のフック（pipe-stage を開いている段の範囲に、pipe-probe を読む道具だけに絞り、段の間のほかのエージェントを止める。残りは `guard_hook.decide` に渡す） | `generator/chat_hook.py` |
| 会話の中でパイプを流す入口（`pipe-in-gen chat start / probe / next / done / review / status`。引数の解釈と JSON の出力だけ） | `generator/chat_cmd.py` |
| 会話の中でパイプを流す司会役（段の順番・検査・差し戻し・人の確認・記録。SDK を呼ばない） | `pipe_in/pipe/chat.py` |
| 会話の道の能力表（項目 × 実行役の動き：効く・断る・一覧に出す・黙る・関係しない。断る文と効かない設定の一覧を作り、全項目が載っているかを検査する。標準ライブラリだけ。`chat.py` が使う） | `pipe_in/pipe/capability.py` |
| 会話の道の記録の読み書き（指紋・段の範囲 `chat_specs`・フックの跡・Bash の覚え。司会役とフックが共有） | `pipe_in/pipe/chat_record.py` |
| 終わった記録を `archive/<日時>/` へ移す（開発フローの記録と会話の道が共有） | `pipe_in/engine/archive.py` |
| 会話の中で段を受け持つ・守りを確かめるエージェントと、流すスキル `/pipe-in:pipe-run` | `plugin/agents/pipe-stage.md`・`pipe-probe.md`、`plugin/skills/pipe-run/SKILL.md` |
| プラグインの採点の計算（総合点・合否・`--runs` のばらつき。標準ライブラリだけ） | `generator/judge_score.py` |
| 仕様書レビューの指摘の検査（指摘の形 v1。形・出典・引用の一致・役割の決まりを LLM なしで調べる `pipe-in-gen findings-check`。標準ライブラリだけ。Schema は他の道具に渡す契約で、実行時には読まない。ひな形 `generator/templates/spec-review/` の `verify` 段が呼ぶ） | `generator/findings_check.py`・`generator/schemas/` |
| 2体の共通部分（指摘の形 v1 のファイル2つか3つから、`location.source` と正規化した `location.section` が合う指摘を残す `pipe-in-gen quorum`。標準ライブラリと findings_check だけ。ひな形 `generator/templates/review-quorum/` の `quorum` 段が呼ぶ） | `generator/quorum.py` |
| VSCode 拡張 | `vscode/`（層は下の「拡張の層」） |
| 拡張の名前の表（コマンド ID・設定の節・パネルの型）と、前の版の設定・コマンド ID の読み替え | `vscode/src/app/names.ts` |
| このリポジトリを開発する Claude Code のスキル | `.claude/skills/pipe-in/`（必ず守る決まりは `SKILL.md` の冒頭に置き、長い手順は補助ファイルに分けた：記録のコマンド `.claude/skills/pipe-in/record.md`・`--artifact` の手順 `.claude/skills/pipe-in/artifact.md`・画面の確認の手順 `.claude/skills/pipe-in/screen-check.md`・無人の実行の手順 `.claude/skills/pipe-in/unattended.md`）・`.claude/skills/pipe-help/`・矛盾監査 `.claude/skills/pipe-audit/`・助言 `.claude/skills/pipe-advise/`・審査 `.claude/skills/pipe-judge/`・文書をそろえる `.claude/skills/pipe-docs/`・計画ボード `.claude/skills/pipe-plan/`（ページのひな形 `board.html`）・壁打ち `.claude/skills/pipe-talk/`（要約は手元だけの `docs/talk/<日時>-<名前>.md`。`.gitignore` 済み） |
| /pipe-in の段を受け持つサブエージェントと、その書ける場所を絞るフック | `.claude/agents/`（`pipe-in-*`。監査と助言の `pipe-in-auditor`・`pipe-in-advisor` は読むだけで、助言は公式の文書を Web（WebFetch・WebSearch）で読める。助言の報告を採点する審査の `pipe-in-judge` も読むだけで、公式の文書を WebFetch だけで読める。文書係の `pipe-in-documenter` は文書だけを書ける）・`.claude/hooks/pipe_in_guard.py`（標準ライブラリだけ。表に無い `pipe-in-*` と、文字列でない `agent_type` は読むだけにする。判断の途中で例外が出ても止める） |
| コードを変えたのに文書が変わっていないまま止まるとき、1回だけ知らせる Stop のフック（標準ライブラリだけ。目印は一時フォルダに置く） | `.claude/hooks/docs_reminder.py` |
| /pipe-in の記録を書く（pipe-in record。`start` の `--name`・`--session-id`、`begin` の `--agent` もここ） | `pipe_in/dev/record.py` |
| /pipe-in の記録の順序を読むだけで検べる（pipe-in record check。承認より前に次の段が始まっていないか） | `pipe_in/dev/record_order.py` |
| 機能ごとの worktree を切る・main に入ったものを片付ける・main に載せ直す（pipe-in worktree new・clean・sync。origin の main を取って使う。D0048・D0049・D0074）と、決定の記録の次の番号を出す（pipe-in decision-number。D0074） | `pipe_in/dev/worktree.py`・`pipe_in/dev/decision_number.py` |
| /pipe-in が打つ記録・worktree・decision-number のコマンドを、今のフォルダだけを相手にする形で流す入口（pipe-in skill。allow に入れる。D0049） | `pipe_in/dev/skill_cmd.py` |
| 利用者向けの説明（使い方・拡張・パイプ・プラグイン・安全・記録・設定・移行・開発・コマンドを打たない人向けの案内）。README は入口だけ | `docs/guide/`・目次 `docs/guide/README.md`・`docs/guide/start-without-commands.md` |
| 初めての人向けの案内（VSCode の「ようこそ」から開く walkthrough。宣言は `contributes.walkthroughs`、手順ごとの本文は Markdown。外から何も読み込まず、自動では開かない。D0072） | `vscode/package.json`・`vscode/walkthrough/` |
| 英語の入口（`README.md`・`vscode/README.md` の英語版。人が書き、見出し・コードの塊・コマンドの行・画像の食い違いは `tests/test_english_docs.py` が見る。ほかの文書は日本語だけ。D0072） | `README.en.md`・`vscode/README.en.md`・`tests/test_english_docs.py` |
| CI（main に入る前のテスト・型検査・ビルド。権限は contents: read だけで、秘密を使わない）と、その更新（Dependabot） | `.github/workflows/ci.yml`・`.github/dependabot.yml` |
| GitHub の PR と issue のテンプレート（PR の本文の節・issue forms の不具合と機能の要望・白紙の issue の許可。決まりは workflow.md の「7. PR と issue」） | `.github/pull_request_template.md`・`.github/ISSUE_TEMPLATE/` |
| 開発のルール・決定の記録 | `docs/development/`・`docs/decisions/` |
| 文書の形の検査（決定の記録の一覧の昇順・表の行の長さ・.gitattributes の union。D0075） | `tests/test_doc_shape.py`・`.gitattributes` |
| アーキテクチャの検査（依存の向き・標準ライブラリだけ。新しい検査は決定ごとの別ファイル。D0075） | `tests/test_architecture.py`・新しい検査は `tests/test_architecture_<名前>.py`（例：`tests/test_architecture_doc_shape.py`） |
| ロードマップ（目指す姿と段階） | `docs/roadmap.md` |
| 調べた結果（実験の方法・結果・やり直すためのスクリプトと集計の結果。生のデータは置かない） | `docs/research/`・目次 `docs/research/README.md` |
| 確認用ページ：会話の道の記録の見本（`driver: "pipe-chat"`・使用量が取れない記録を一時フォルダに書いて、`run-panel-chat-*` を出す） | `vscode/scripts/chatSamples.ts` |
| 確認用ページ：返事を受け付けている確認待ちの見本（印 `reply_wait` のある記録・ボタンの出ない記録を一時フォルダに書いて、`run-panel-reply-runs-*` を出す。`window.__previewReply(name)` で、描き直しと送ったあとを送る） | `vscode/scripts/replySamples.ts` |
| 画面のデザインの土台（ブランド「プラグ」の色の決まり・部品と画面の見本。Claude のデザインのキャンバスの写し） | `docs/design/`・`docs/design/README.md` |
| ロゴ（README に載せる SVG。明るい表示用と暗い表示用）とロゴの動き（HTML と GIF。検査は `tests/test_plug_logo.py`）、README とガイドの画像（明暗の PNG）、撮り直しの手順 | `docs/assets/`・`docs/assets/README.md` |
| 画面用の見本の記録（本体の流れを差し替えた runner で作る。README とガイドの画像と確認用のページが読む。4つ：完了・動いている2つ（うち1つは、戻る矢印が光る描き直しの素材）・確認待ち） | `tests/fixtures/showcase/`・`tests/fixtures/showcase_running/`・`tests/fixtures/showcase_running_next/`・`tests/fixtures/showcase_waiting/`・作り方 `tests/showcase.py` |
| 画面の確認用のページ（開発用。`npm run preview`）。ページの種類と名前の一覧は `docs/assets/README.md`、確かめる手順は `.claude/skills/pipe-in/screen-check.md`。ページごとの作り方（見本の記録の持ち方）は、次の「確認用ページ：…」の行に 1 ページ 1 行で書く | `vscode/scripts/preview.ts`・ページを作る関数と木を組み立てる関数 `vscode/scripts/previewPages.ts`・見本の成果物の文章 `vscode/scripts/artifactSamples.ts`・見本の呼び出しの記録 `vscode/scripts/toolsSamples.ts`・上限と費用の表の見本の記録の中身 `vscode/scripts/budgetSamples.ts`・判定とやり直しの見本の記録の中身 `vscode/scripts/checkSamples.ts`・並列の枠の見本の記録の中身 `vscode/scripts/groupSamples.ts` |
| 確認用ページ：実行の一覧の見本 | 上の4つの見本の記録から、一時フォルダの中に「主の checkout＋別の worktree＋前の実行の置き場所」の木を組み立てて作る（`tests/fixtures/` には足さない）。`vscode/scripts/previewPages.ts` |
| 確認用ページ：更新なしの見本 | 実行の一覧の見本と同じ作りで、動いている・確認待ちの見本とあわせて、見本の記録を一時フォルダに写し、段のログの更新時刻を見本の「今」からの相対にそろえて読む（`tests/fixtures/` の更新時刻に左右されない）。`vscode/scripts/previewPages.ts` |
| 確認用ページ：成果物のタブの見本 | 同じ作りで、動いている開発フローと12個のパイプの2つの実行を持ち、成果物の更新時刻を固定の値にそろえる（見本の文章は長い Markdown・外から来た文字・上限を超える日本語）。`vscode/scripts/artifactSamples.ts` |
| 確認用ページ：エージェント・スキルのタブの見本 | 見本の記録（ログと `state.json`）を一時フォルダの中に生成して作り（`tests/fixtures/` には足さない）、動いている SDK の実行・`/pipe-in` の記録・受け持ちを付けなかった `/pipe-in` の記録・呼び出しがまだ無い実行の4つを持つ。`vscode/scripts/toolsSamples.ts` |
| 確認用ページ：上限と費用の表の見本 | 上限と費用の表の見本のページ（`run-panel-budget-*`）は、10 段のパイプの記録を一時フォルダに書いて本物の読み取りで読む（`tests/fixtures/` には見本の記録を足さない）。`vscode/scripts/budgetSamples.ts` |
| 確認用ページ：判定とやり直しの見本 | 判定とやり直しの見本のページ（`run-panel-check-*`）。判定のある段が fail → pass した記録・前の段へ戻す判定が上限まで落ちた記録・判定の情報の無い古い記録を一時フォルダに書いて読む。`vscode/scripts/checkSamples.ts` |
| 確認用ページ：並列の枠の見本 | 並列の枠の見本のページ（`run-panel-group-*`）も同じ作りで、枠の中が同時に動く記録・完了と失敗と判定のやり直しの記録・`group` の無い古い記録を一時フォルダに書いて読む（`tests/fixtures/` には足さない）。`vscode/scripts/groupSamples.ts` |
| 確認用ページ：スタブでの確かめ | 作業台の外で書き換わったときの見本のページ（名前は `docs/assets/README.md`）は、スタブの `window.__previewExternal(kind)` で拡張からの知らせを送る。作業台の「費用の目安」の節の確かめも、ページは足さず、今の作業台のページのスタブの `window.__previewEstimate({ today, actualUsd })` で今日と前の実績を送る。作業台の「流す」の節の確かめも、ページは足さず、スタブの `window.__previewRun(ctx)` で、入力の種類・保存前・実行中・信頼・実行ファイルの有無を送る。`vscode/scripts/preview.ts` |
| 動画を作るパイプの見本（`pipe-in --pipe examples/video/pipes/pipe-in-video` で流し、`pipe-in-gen check video --pipes-dir examples/video/pipes` で確かめる。受付とテンプレートの2つ以外のコードは置かない） | `examples/video/pipes/pipe-in-video/`・`examples/video/` |
| 流せる見本のパイプ（図を作る・仕様とソースの突き合わせ・調べものをまとめる）と、見本の案内。`diagrams`・`spec-qa` は `generator/templates/` のひな形を決まった値で埋めた写しに上限を足したもので、`tests/test_examples.py` がひな形との食い違いを見張る。`pipe-in-gen check <名前> --pipes-dir examples/<名前>/pipes` で確かめる | `examples/diagrams/pipes/pipe-in-diagrams/`・`examples/spec-qa/pipes/pipe-in-spec-qa/`・`examples/research/pipes/pipe-in-research/`・`examples/README.md` |
| 作業台の「見本から作る」の見本のデータ（`examples/` から `npm run examples:gen` で作って、コミットする。拡張は実行時に `examples/` を読まない。`pipe.toml` と `prompts/*.md` だけを持つ）と、見本の一覧とモデル作り、名前の確かめと見本から未保存のモデルを作る手順（書く口を受け取らない）、生成の道具 | `vscode/src/domain/exampleData.ts`・`vscode/src/domain/pipeExamples.ts`・`vscode/src/app/exampleFlow.ts`・`vscode/scripts/genExamples.ts` |
| 作業台から流す（D0078。拡張が起こしてよい子プロセスは、決まった形の `pipe-in` 1つだけ。実行ファイルは絶対パスに決めてから Tasks API の `ProcessExecution` で起こし、`child_process` は使わない）。コマンドの形と依頼メモの検め・実行ファイルの決め方の純粋な部分・流してよいかの判断（理由は決まった順で1つ）はドメイン、実行ファイルを探す手順・実行中の記録（入口が持つ）・流す計画はアプリ、`stat` で通常のファイルかを返すのは基盤、「流す」の節は画面 | `vscode/src/domain/runCommand.ts`・`vscode/src/domain/runExecutable.ts`・`vscode/src/domain/runDecision.ts`・`vscode/src/app/runExecutable.ts`・`vscode/src/app/runActive.ts`・`vscode/src/app/runFlow.ts`・`vscode/src/infra/fsFileProbe.ts`・`vscode/src/view/runHtml.ts` |
| 作業台から流す引数の形を、拡張（`buildRunCommand`）と本体（`pipe_in.cli._parse_args`）で結ぶ共通の表（見本の記録ではない。拡張と本体のテストが同じ表を読む） | `tests/fixtures/run_command.json` |
| 返事のファイルの中身を、拡張が作る関数（`buildReplyText`）と本体の読み取り（`parse_reply`）で結ぶ共通の表（見本の記録ではない。拡張と本体のテストが同じ表を読む。直してほしい点の長さはコードポイント） | `tests/fixtures/reply_file.json` |
| 作ったパイプ（どれも .gitignore 済み） | 対象の `.pipe-in/pipes/`（前の版の置き場所も読む）、今までの `pipes/` |

新しいものを置く場所に迷ったら、まずこの表の近いものの隣に置き、表に1行足します（表のパスが実物と合っているかは `tests/test_rules.py` が検査します）。

## 本体の依存の向き

```
pipe_in_generator（generator/）
   ↓
pipe_in.pipe / pipe_in.dev
   ↓
pipe_in.engine
   ↓
pipe_in.usage
```

- 逆向きの import は `tests/test_architecture.py` が止めます。新しい検査は `tests/test_architecture_<名前>.py` に足します（`tests/test_architecture.py` の末尾には足しません）。
- `pipe_in.engine` は、どのパイプにも共通の仕組みです。特定のパイプ（開発フロー・パイプの定義）や入口（`pipe_in.cli`）を知りません。
- `generator/guard_hook.py` と `.claude/hooks/pipe_in_guard.py` は、Claude Code が道具を呼ぶたびに動きます。起動を軽くし、本体が壊れていても動くように、**標準ライブラリだけ**を使います（`guard_hook.py` は `tests/test_architecture.py` が検査します）。`generator/judge_score.py`（`pipe-in-gen judge-score`）と `generator/findings_check.py`（`pipe-in-gen findings-check`）・`generator/quorum.py`（`pipe-in-gen quorum`。findings_check の部品だけは読む）も、本体を読み込まず標準ライブラリだけです。

## 拡張の層

| 層 | パス | 置くもの | 使ってよい外の部品 |
| --- | --- | --- | --- |
| ドメイン | `vscode/src/domain/` | 段・実行の記録・段のログ・成果物・図の状態・パイプのモデルと編集・実行の一覧・時系列・表の元・費用の判断。部品ごとの役割は下の「層ごとの部品」の表。主な部品：成果物の既定の選び（`artifacts.ts`）・時刻の読み方と書き方（`timestamp.ts`）・段の費用を上限と比べる判断（`stageBudget.ts`）・段ごとの費用の表の元（`stageCosts.ts`）・使ったエージェント・スキル・道具の表（`toolsTable.ts`）・ステータスバーの件数に数える行とボタンで先に出す確認待ちの判断（`runList.ts`）。純粋な関数だけ（時計にも触れない） | `node:path` |
| アプリケーション | `vscode/src/app/` | 口（作業台の保存・保存した版・実行の一覧・覚える先）と、それを使う手順。部品ごとの役割は下の「層ごとの部品」の表。主な部品：古い読み込みの結果を捨てる世代の部品（`refreshPolicy.ts`）・実行の一覧を作って見る実行を決める（別の worktree の行があるかの旗も返す。`runList.ts`）・いまの work_dir の見張り（`workDirWatch.ts`。有無の判断が張る・外す・そのままを決める） | `node:path` |
| 画面 | `vscode/src/view/` | 図の状態 → HTML の文字列。部品ごとの役割は下の「層ごとの部品」の表。主な部品：成果物の Markdown を許すタグだけの HTML に直す（`markdownHtml.ts`）・タブ「成果物」（`artifactsHtml.ts`）・タブ「エージェント・スキル」（`toolsHtml.ts`）・金額の書き方（`money.ts`）・使用量のタブの先頭の「段ごとの費用」の表（`usageHtml.ts`）・ステータスバーの文字と説明（件数の形を含む `statusBar.ts`）。外から来た文字は `escapeHtml` を通す | なし |
| 基盤 | `vscode/src/infra/` | 口の実装・別の worktree の登録の読み・work_dir の有無の確かめ・読み取りの口の絞り込み。部品ごとの役割は下の「層ごとの部品」の表。成果物は通常のファイルだけを先頭 256 KiB まで読む。有無の確かめ（`fsPresence.ts`）は `stat` を 1 回呼ぶだけ。触れる場所はここで絞る | `node:fs`・`node:fs/promises`・`node:os`・`node:path` |
| パネルの中 | `vscode/src/webview/` | 作業台の画面の操作（ビルドで1つの pipeEditor.js に束ねる）。判断は domain の関数に任せる | なし |
| 入口 | `vscode/src/extension.ts` | コマンド・パネル・ファイルの監視・エディタで開く。有無の確かめのタイマーを始めて止め、見張りを作る口・確かめの口・読み直しを部品に渡す。判断は持たない。部品ごとの役割は下の「層ごとの部品」の表。拡張ホストの側で時計（今の時刻）を読むのもここだけ。作業台の「流す」で、決まった形の `pipe-in` を Tasks API で起こす（`startRun`。D0078）。実行パネルの返事の知らせを受けて、返事のファイルを書く口を呼ぶ（`handleReply`。呼ぶのはここ 1 か所。D0079） | `vscode` を import してよいのはここだけ |

### 層ごとの部品（1 部品 1 行）

新しい部品は、ここに 1 行足します。層の表の行は、層の役割が変わったときだけ直します。ただし、D0051 の検査（`tests/test_stage_budget_docs.py`）が層の行で読む部品の名前は、層の行にも残します。この文書と `CLAUDE.md` の表の行は 800 字までです（`tests/test_doc_shape.py` が見ます）。`vscode/src/extension.ts` だけは、役割ごとに複数の行に分けています。第 1 列は部品の完全なパスで、`tests/test_rules.py` が実在を見ます。

| 部品 | 層 | 役割 |
| --- | --- | --- |
| `vscode/src/domain/runRecord.ts` | ドメイン | 段・実行の記録（`driver` の有無 `hasDriver` を持つ） |
| `vscode/src/domain/replyFile.ts` | ドメイン | 返事のファイルの決まり：ファイル名・版・動作 `approve`・`revise`・`quit`・直してほしい点の検め（コードポイントで 1,000 まで・使えない文字）と、返事の中身を作る `buildReplyText`。本体の `reply.py` と同じ決まりを共通の表で結ぶ（D0079） |
| `vscode/src/domain/stageLog.ts` | ドメイン | 段のログ：出力の道具の行と、頼んだときだけ返す呼び出しの記録 `calls` を、同じ部品の判定から作る。`Agent`・`Task`・`Skill` の見分けと入力の鍵 `subagent_type`・`skill` の読みはここに閉じる |
| `vscode/src/domain/artifacts.ts` | ドメイン | 成果物：作った段・読んだ範囲と切れた印・更新時刻の文字・押していないときの既定の選び `defaultArtifactName` を決める |
| `vscode/src/domain/pipelineView.ts` | ドメイン | 図の状態（「今」は `ViewClock` を引数で受ける） |
| `vscode/src/domain/replyWait.ts` | ドメイン | 返事を受け付けている確認待ちの判断 `canReply`、帯に出す `ReplyView`、送ってから 30 秒の判断 `isReplyStalled`、読み直しを続けるかの `isLive`（D0079） |
| `vscode/src/domain/timestamp.ts` | ドメイン | 時刻の読み方と書き方：記録の時刻を読むことと、手元の時刻の `MM/DD HH:mm` に書くこと |
| `vscode/src/domain/pipeModel.ts` | ドメイン | パイプのモデル |
| `vscode/src/domain/pipeWires.ts` | ドメイン | ケーブルの通り道と曲線 |
| `vscode/src/domain/pipeLinks.ts` | ドメイン | 抜き差しと間に挟む |
| `vscode/src/domain/pipeDrop.ts` | ドメイン | 離した点から差す先を決める |
| `vscode/src/domain/cableRope.ts` | ドメイン | 引いているケーブルのひもの動き |
| `vscode/src/domain/pipeEdit.ts` | ドメイン | 複製や枠の出し入れなどの編集 |
| `vscode/src/domain/pipeCheck.ts` | ドメイン | 判定のスイッチと不合格の行き先 |
| `vscode/src/domain/pipeMenu.ts` | ドメイン | 右クリックのメニュー |
| `vscode/src/domain/editHistory.ts` | ドメイン | 元に戻す |
| `vscode/src/domain/pipeVersions.ts` | ドメイン | 保存した版の決まり（種別は保存・下書き・外で書き換わる前の `-external`） |
| `vscode/src/domain/pipeExternal.ts` | ドメイン | 外で書き換わったパイプの判断：見るべきファイル・読み直す／選ばせる／何もしない・パネルへの知らせの型 |
| `vscode/src/domain/pipeDiff.ts` | ドメイン | 差分の一覧 |
| `vscode/src/domain/toml.ts` | ドメイン | 小さな TOML の読み手 |
| `vscode/src/domain/runs.ts` | ドメイン | 実行の一覧：実行の目印と `archive` の id。流したパイプの実行の目印 `pipeRunKey`（D0078） |
| `vscode/src/domain/runList.ts` | ドメイン | 実行の一覧：1行の組み立て・状態・並び・状態ごとの件数・ステータスバーの件数に数える行・ボタンで先に出す確認待ちの判断・省く件数・覚えた値の検め |
| `vscode/src/domain/worktrees.ts` | ドメイン | 実行の一覧：別の worktree の登録の読み方・ブランチ名や短い ID の取り方・受け入れの判断 |
| `vscode/src/domain/sessionName.ts` | ドメイン | セッション名の取り方。本体の `session.py` と同じ規則 |
| `vscode/src/domain/gantt.ts` | ドメイン | 時系列のモデル：段の実行ごとの行・エージェントの帯・確認を待った帯・横軸。「今」は引数。段の表示名の書き方 `labelOf`・通し番号ごとの最初のログ `firstLogBySeq`・受け持ちの決め方 `ownerOf` は、使ったエージェント・スキル・道具の表と共有して `export` する |
| `vscode/src/domain/toolsTable.ts` | ドメイン | 使ったエージェント・スキル・道具の表：名前の決まり・同じ名前の合算・使った段・受け持ちの行と時間・並び・100 行の上限。段のログの呼び出し `calls` と、`/pipe-in` の記録の段の受け持ちから作る。「今」を引数に取らず、時計にも触れない |
| `vscode/src/domain/quiet.ts` | ドメイン | 最後の更新からの秒：段のログの更新時刻から「今」までの秒。「今」は引数。上限の 7 日は `timestamp.ts` の定数 |
| `vscode/src/domain/waitingNotice.ts` | ドメイン | 新しく確認待ちになった行の判断：前の一覧の行と今の一覧の行を比べて key を返す。前の実行の行と終わった行は返さない |
| `vscode/src/domain/stageBudget.ts` | ドメイン | 段の費用を上限と比べる判断：実行ごとの状態と、節に出す回の選び方。比べるのは 1/1000 ドルの整数 |
| `vscode/src/domain/stageCosts.ts` | ドメイン | 段ごとの費用の表の元：段ごとの合算・費用の多い順・割合 |
| `vscode/src/domain/costEstimate.ts` | ドメイン | 流す前の費用の目安：単価表 `PRICES`・注意の文 `DISCLAIMER`・系統の見分け・少なめと多め。本体の `pipe_in/usage/estimate.py` と同じ決まりで、今日は引数 |
| `vscode/src/domain/exampleData.ts` | ドメイン | 作業台の見本：生成物のデータ。何も import しない |
| `vscode/src/domain/pipeExamples.ts` | ドメイン | 作業台の見本：一覧と見本からのモデル作り |
| `vscode/src/domain/runCommand.ts` | ドメイン | 作業台から流すコマンドの形：引数の配列（`--pipe=`・`--project=`・`--text=`）と依頼メモの検め（空・4,000 文字・NUL・壊れた文字）、絶対パスの判断（OS の種類は引数）。作業台のパネルも読むので、外の部品（`node:`・`vscode`・パッケージ）を import しない（同じドメイン層の `InputMode` などは相対 import する） |
| `vscode/src/domain/runExecutable.ts` | ドメイン | 実行ファイルの決め方の純粋な部分：設定の値の判断（`globalValue`・`defaultValue` だけ）、PATH の候補の並び（絶対の項目だけ。Windows は `.exe`・`.com`）、Windows の拡張子の判断 |
| `vscode/src/domain/runDecision.ts` | ドメイン | 流してよいかの判断：今の事実 `RunContext` と、理由を決まった順で1つ返す `decideRun`。パネルも入口も同じ関数を使う |
| `vscode/src/app/refreshView.ts` | アプリケーション | 口 `WorkDirSource` と、それを使う手順（`refreshView`・`resolveWorkDir`） |
| `vscode/src/app/replyFlow.ts` | アプリケーション | 口 `ReplyStore` と、返事を送る手順 `sendReply`（最後に描いた印と、書く直前に読み直した印が同じときだけ書く）・`replyOfferOf`（D0079） |
| `vscode/src/app/pipeEditor.ts` | アプリケーション | 口 `PipeStore` と、作業台の読み込みと保存・置き場所と保存先の決め方（`saveTarget`） |
| `vscode/src/app/pipeVersions.ts` | アプリケーション | 口 `VersionStore` と、保存した版の記録と読み込み |
| `vscode/src/app/externalReload.ts` | アプリケーション | 外で書き換わったパイプの読み直しの手順：読む→判断→読み直す／選ばせる。取り込む前に版へ残す。見張りの対象 `PIPE_WATCH_GLOB` |
| `vscode/src/app/debounce.ts` | アプリケーション | デバウンス。時計は呼ぶ側が渡す |
| `vscode/src/app/runList.ts` | アプリケーション | 口 `RunsSource` と、実行の一覧を作って見る実行を決める（別の worktree の行があるかの旗も返す） |
| `vscode/src/app/selection.ts` | アプリケーション | 口 `MemoryStore` と、選びを覚える手順 |
| `vscode/src/app/refreshPolicy.ts` | アプリケーション | 監視の対象と読み直しの間隔と読み直しの要否（別の worktree の行があるあいだは、パネルが見えていなくても読み直す）と小さなタイマー、古い読み込みの結果を捨てる世代の部品。有無を確かめる間隔 `PRESENCE_CHECK_MS` もここ |
| `vscode/src/app/staleness.ts` | アプリケーション | 止まっているかもしれない印の目安の秒（設定の分 → 秒。`staleness.ts`） |
| `vscode/src/app/names.ts` | アプリケーション | 名前の表と前の版の名前の読み替え |
| `vscode/src/app/costContext.ts` | アプリケーション | 作業台に渡す今日と前の実績：既に読んだ実行の一覧の写しから選ぶだけ。今の時刻は引数 |
| `vscode/src/app/notifyWaiting.ts` | アプリケーション | 確認待ちの知らせの対象の行の絞り込み（パネルで見ている実行を外す）と設定の値の読み（引数で受ける純粋な関数） |
| `vscode/src/app/workDirWatch.ts` | アプリケーション | いまの work_dir の見張り：有無の判断 `decideWatch` が張る・外す・そのままを、`finishStep` が読み直すか・追い読みの番かを決める。見張りを 0 個か 1 個に保つ部品 `createWatchHolder`。有無の確かめの手順 `createWorkDirChecker`。`vscode` も `node:` も使わない |
| `vscode/src/app/exampleFlow.ts` | アプリケーション | 「見本から作る」の手順：名前の確かめは保存と同じ `saveTarget` に任せ、見本から未保存のモデルを作る。`PipeStore`・`VersionStore` を受け取らない |
| `vscode/src/app/runExecutable.ts` | アプリケーション | 実行ファイルを絶対パスに決める手順：口（そのパスに通常のファイルがあるか）を受け取り、候補を順に確かめる |
| `vscode/src/app/runActive.ts` | アプリケーション | 実行中の記録（パイプのフォルダごと。メモリだけ）。持つのは入口で、作業台のパネルは持たない |
| `vscode/src/app/runFlow.ts` | アプリケーション | 流す計画：保存済みの形と開いたパイプから `RunContext` を作り、`decideRun` と `buildRunCommand` を通して、起こす値（command・args・cwd）か理由を返す |
| `vscode/src/view/duration.ts` | 画面 | 時間の書き方 |
| `vscode/src/view/timesHtml.ts` | 画面 | 図の枠の「時間」の節 |
| `vscode/src/view/runListHtml.ts` | 画面 | 左の実行の一覧 |
| `vscode/src/view/shellHtml.ts` | 画面 | 上のバー、右の詳細、タブの枠組み |
| `vscode/src/view/ganttHtml.ts` | 画面 | 時系列の SVG |
| `vscode/src/view/staleMark.ts` | 画面 | 止まっているかもしれない印の共通部品：言葉・属性・時間の要素のほか、一覧の行と詳細が同じ「動いている行だけ」の判断を共有する `rowStaleAttrs` も持つ |
| `vscode/src/view/frameStyle.ts` | 画面 | 並列の枠の色の定数 `frameStyle.ts`（`PAR_COLOR` だけ）。作業台 `pipeEditorHtml.ts` と実行パネルの図 `panelHtml.ts` が同じ値を読む |
| `vscode/src/view/artifactsHtml.ts` | 画面 | タブ「成果物」の左の一覧と右のプレビュー |
| `vscode/src/view/toolsHtml.ts` | 画面 | タブ「エージェント・スキル」の表と案内と空の文 |
| `vscode/src/view/markdownHtml.ts` | 画面 | 成果物の Markdown を許すタグだけの HTML に直す。リンクは `a` にせず、画像は読み込まない。外から来た文字は `escapeHtml` を1回だけ通す |
| `vscode/src/view/panelHtml.ts` | 画面 | CSP と style の束ね。パネルとの受け渡しの形 |
| `vscode/src/view/panelScript.ts` | 画面 | パネルのスクリプト：数え上げ・目安に届いた印の要素への `is-stale` の付与・戻る矢印の光り・絞り込みとタブ・成果物の選び・並列の枠の中の段のログの選び・描き直しをまたぐ保持 |
| `vscode/src/view/money.ts` | 画面 | 金額の書き方。図の節と表の両方で使う |
| `vscode/src/view/usageHtml.ts` | 画面 | 使用量のタブの先頭の「段ごとの費用」の表と使用量の表 |
| `vscode/src/view/costEstimateHtml.ts` | 画面 | 作業台の「費用の目安」の節：段の名前・モデルの名前は `escapeHtml` を通し、style 属性は書かない |
| `vscode/src/view/runHtml.ts` | 画面 | 作業台の「流す」の節の中身（起こすコマンドの形・理由・文字数）。外から来た文字は `escapeHtml` を通し、style 属性は書かない |
| `vscode/src/view/statusBar.ts` | 画面 | ステータスバーの文字と説明：件数の形と、外から来た文字を 1 行にする関数を含む |
| `vscode/src/view/waitNotice.ts` | 画面 | 確認待ちの知らせの文とボタンの文字 |
| `vscode/src/view/replyHtml.ts` | 画面 | 確認待ちの帯の、返事の部分（承認・修正を依頼・中止のボタン、修正の入力、中止の確かめ、送ったあと）の HTML と CSS、断った理由の文。外から来た文字は `escapeHtml` を通し、style 属性は書かない（D0079） |
| `vscode/src/view/externalHtml.ts` | 画面 | 外で書き換わったときの帯：差分の文字は `escapeHtml` を通す |
| `vscode/src/infra/fsWorkDirSource.ts` | 基盤 | 口 `WorkDirSource` の実装：段のログの中身に加えて更新時刻（`stat`）も読み、成果物は通常のファイルだけを、更新時刻（`lstat`）と先頭 256 KiB まで読む。1 回の読みは、合計が 4 MiB に届いたら残りを読まない（最大でも 4 MiB + 256 KiB 未満） |
| `vscode/src/infra/fsPipes.ts` | 基盤 | 口 `PipeStore` の実装：書いてよい場所を絞る |
| `vscode/src/infra/fsVersions.ts` | 基盤 | 口 `VersionStore` の実装：書いてよい場所を絞る |
| `vscode/src/infra/fsReplies.ts` | 基盤 | 口 `ReplyStore` の実装：いまの work_dir の実行のフォルダ（直下か直下 1 段の決まった名前）の `reply.json` 1 つだけを、排他で新しく作る。リンクを辿らず、一時ファイルを作らない（D0079） |
| `vscode/src/infra/fsWorktrees.ts` | 基盤 | 別の worktree を `.git` の登録（ファイル）から見つけ、いまの checkout のブランチ名も読む。work_dir の確かめは `fsPresence.ts` と同じ判定を使う |
| `vscode/src/infra/fsPresence.ts` | 基盤 | work_dir の有無の確かめ：`stat` を 1 回呼ぶだけで、有る・無い・分からないに分ける。`fsWorktrees.ts` の work_dir の確かめも同じ判定を使う |
| `vscode/src/infra/fsFileProbe.ts` | 基盤 | 通常のファイルかの確かめ：`stat` を 1 回呼ぶだけで、読むだけ。失敗は false |
| `vscode/src/infra/readOnlyFs.ts` | 基盤 | 読み取りの口を6つの関数（`readFile`・`readdir`・`stat`・`lstat`・`realpath`・先頭だけ読む `readHead`。`00_input.md` の先頭と成果物の読みに使う）に絞る。1 回の読みが短く返る（ネットワークや FUSE のファイル）ときも、頼んだ量かファイルの終わりまで読む |
| `vscode/src/extension.ts` | 入口 | 有無の確かめのタイマー（約3秒）を始めて止め、見張りを作る口・確かめの口・読み直しを部品に渡す。張る・外す・読み直すの判断は部品に任せ、ここでは判断を持たない |
| `vscode/src/extension.ts` | 入口 | パイプの作業台ごとに、パイプのフォルダの見張り（`PIPE_WATCH_GLOB`）とデバウンスのタイマーを作って部品に渡す（外で書き換わったときの判断と手順は `pipeExternal.ts`・`externalReload.ts`） |
| `vscode/src/extension.ts` | 入口 | 確認待ちの知らせを出す：確認待ちの知らせの `vscode.window.showInformationMessage` は、`render()` の外の別の関数 `notifyWaiting` から出す。前の一覧の行はメモリの変数に持ち、どこにも書かない |
| `vscode/src/extension.ts` | 入口 | 拡張ホストの側で時計（今の時刻）を読むのもここだけ（パネルのスクリプトは、描き直しを受けた時刻からの差だけを数える） |
| `vscode/src/extension.ts` | 入口 | 作業台から流す：`startRun` が `planRun` の結果だけで `vscode.tasks.executeTask`（`new vscode.ProcessExecution(`）を呼ぶ。実行中の記録 `activeRuns` はモジュールの変数（パイプのフォルダごと）で、`onDidEndTask`・`onDidEndTaskProcess` の早いほうだけで外す。設定 `pipe-in.command` は `globalValue`・`defaultValue` だけを渡す。信頼は `vscode.workspace.isTrusted` を見る |

- 層の決まりは `vscode/src/architecture.test.ts` が検査します（テストのファイルと `vscode/src/test/` の補助は除く）。
- 本体の記録の形の知識は `runRecord.ts`・`stageLog.ts`・`artifacts.ts`・`runs.ts` の中だけに置きます。本体の記録の形が変わったら、ここを直します。
- 拡張は work_dir を読むだけで書きません。書いてよいのは、作業台で「保存」を押したときの、パイプの置き場所の中のパイプのフォルダ（`pipe-in-<名前>/`。前の版のフォルダ名も）の決まったファイルだけです（`vscode/src/infra/fsPipes.ts` が場所を絞ります）。保存先は拡張が開いたパイプから決め、パネルから来た値では決めません。作業台の「流す」も、work_dir にもパイプの置き場所にも書きません（依頼メモはどこにも残しません）。例外は 1 つだけで、実行パネルの返事（承認・修正の依頼・中止）を、いまの work_dir の実行のフォルダ（直下か直下 1 段）の返事のファイル `reply.json` に、新しく作るときだけ書きます（`vscode/src/infra/fsReplies.ts` が場所とファイル名を絞ります。場所は拡張が作った一覧から、段と識別子は読み直した記録から決め、パネルから来る値は動作と直してほしい点の文字だけです。読んで動くのは本体だけで、拡張は段を流しません。D0079）。
- 実行の一覧のために、同じ git リポジトリの別の worktree の work_dir と、`.git` の中の worktree の登録も、**読むだけ**です（`fsWorkDirSource.ts`・`fsWorktrees.ts`。書き込みの関数を型に入れず、子プロセスは起こしません。`tests/test_decision_ui.py` と `vscode/src/architecture.test.ts` が検査します）。別の worktree で読むのは `state.json`・`logs/`（中身と、止まっているかもしれない印のための更新時刻 `stat`）・記録から作った成果物の一覧にあるもの（更新時刻と、1 つにつき先頭 256 KiB まで）・`00_input.md` の先頭 4 KiB（`state.json` に `name` が無い run だけ。セッション名の元）だけで、いまの checkout のブランチ名のために `.git/HEAD` も読みます。登録のパスが絶対パスで実在し、その worktree の `.git` が自分の登録を指し返し、work_dir がその worktree の中に収まるときだけ場所にします。パネルや覚えた値から来る実行の目印は、`runs.ts` で形を検め、拡張が作った一覧にあるものだけを通します（パスを作りません）。
- 拡張が起こしてよい子プロセスは、作業台の「流す」が起こす決まった形の `pipe-in` 1つだけです（D0078）。起こし方は Tasks API の `ProcessExecution`（シェルを通さず、実行ファイルと引数の配列で起こす）で、`child_process` は import しません（D0019-AC-21 は変わりません）。実行ファイルは拡張が絶対パスに決めてから渡します（設定 `pipe-in.command` はユーザーの設定の値だけ。名前だけなら PATH の絶対の項目から探し、Windows では `.exe`・`.com` だけ）。引数は `--pipe=`・`--project=`・依頼メモがあるときだけ `--text=` で、パネルから来る値は依頼メモだけです。信頼していないワークスペースでは拡張が動かず（`capabilities.untrustedWorkspaces`）、流す前にも `vscode.workspace.isTrusted` を見ます。`env` は足しません。
- 成果物のプレビューのために読む成果物は、記録から作った一覧にある名前の、通常のファイルだけです（`lstat` で種類と更新時刻を見て、`readHead` で先頭 256 KiB まで読みます。1 回の読みは、合計が 4 MiB に届いたら残りを読みません。最大でも 4 MiB + 256 KiB 未満）。symlink・フォルダは読まず、「まだない」と同じ扱いです。確かめてから開くまでのあいだに通常のファイルが symlink へ差し替えられる競合は塞いでいません（口は `'r'` だけで開く6つのまま変えず、差し替えるには作業フォルダに書ける別のプロセスが要り、見えるのは使う人自身の画面だけだからです）。`00_input.md` の先頭 4 KiB と `state.json` は、これまでどおり symlink を辿ります。中身は `view/` の部品が許すタグだけの HTML に直して、描き直しの HTML に入れます（メッセージの種類と CSP は変えません）。変換でふくらむ HTML は出す側でも抑えます（表は 100 列・セル 20,000・HTML の長さが入力の約 20 倍（省略の一文も入ります）まで、1 回の描き直しのプレビューの中身は合計約 8 MiB 文字まで。超えたところから先は案内だけ）。成果物の選びとスクロールはパネルのスクリプトの変数だけで持ち、保存しません。
- 選んだ実行は、VSCode がワークスペースごとに用意する `workspaceState`（キー `pipe-in.selectedRun`）に、場所の目印と実行の目印だけを書きます（`vscode/src/app/selection.ts`。work_dir・プロジェクト・worktree には書きません）。書くのは、行を押したとき・ボタンが確認待ちの実行を先に選んだとき・作業台の「流す」で流したとき（流したパイプの実行を選ぶ。D0078）です。
- 作業台の「保存した版」と、閉じたときの下書きは、VSCode が拡張に用意する保存場所（`storageUri`、無ければ `globalStorageUri`）の `pipe-versions/pipe-in-<名前>/<版の id>.json` にだけ書きます。プロジェクトには書きません（`vscode/src/infra/fsVersions.ts` が場所を絞ります）。外で書き換わったパイプを取り込む前の形も、同じ場所に `-external`（取り込む前の保存済みの形）と `-draft`（保存していない変更があったとき）で残します。書き込み先は増えません。パイプのフォルダの `pipe.toml`・`layout.json`・`prompts/*.md` は見張って読み直すだけで、書きません（`vscode/src/app/externalReload.ts`）。
- 色はすべて `var(--vscode-*)`。外部の読み込みはしません。ログから来た文字は必ず `escapeHtml` を通します。
- パネルの CSP はインラインの `style="…"` 属性を捨てます。位置や大きさは描いたあとに `el.style.*` で入れ、決まった見た目はクラスにします（`vscode/src/webview/csp.test.ts` が検査します）。

## 形を変えるとき（互換）

次のものは、利用者の手元にすでにある、前の版で作られたものを読みます。形を変えるときは、設計の段で、古いものをどう扱うかを決めます。

| もの | 読む所 |
| --- | --- |
| 実行の記録（`state.json`・`99_summary.md`・`logs/*.jsonl`）と終了コード | 本体の `pipe_in/engine/`・`pipe_in/dev/record.py`、拡張の `runRecord.ts`・`stageLog.ts`・`artifacts.ts`・`runs.ts`。見本の記録 `tests/fixtures/pipe_dev/`（今の形）と `tests/fixtures/pipe_in/`（前の版の形）を両方のテストで読み、形がずれないようにしている。画面用の見本 `tests/fixtures/showcase/`（本体が今書く形。`tests/test_showcase.py` が今の本体で作り直したものと形を比べる） |
| 設定（`pipeline.toml`） | `pipe_in/engine/config.py` |
| パイプ（`pipe.toml`・`prompts/*.md`・`layout.json`） | `pipe_in/pipe/definition.py`、拡張の `pipeModel.ts` |
| パイプの置き場所 | `pipe_in/pipe/definition.py` の `pipes_dirs`・`new_pipes_dir`、拡張の `choosePipesDirs` |
| 前の名前（devpipe）のもの：置き場所 `.devpipe/pipes/`・フォルダ名 `devpipe-<名前>/`・環境変数 `DEVPIPE_PIPES_DIR`・VSCode の設定 `devpipe.*` とコマンド ID・記録の `driver` | `pipe_in/pipe/definition.py`・`generator/guard_hook.py`・拡張の `names.ts`・`pipeEditor.ts`・`fsPipes.ts`、`pipe_in/engine/pipeline.py`（`driver` があれば `--review` で流さない）。新しい名前があればそちらを先に使う。コマンドの別名は 0.4 で消す（D0006） |

- 実行の記録に D0019 で足した項目：`state.json` の `name`・`session_id`、`runs[]` の要素と `Prompt` 行の `agent`。どれも足すだけで、無い古い記録は今までどおり読める（拡張は `name` が無ければ `00_input.md` の最初の行から名前を作る）。
- D0021 は記録の形（`state.json`・`logs/*.jsonl`・`99_summary.md`）を変えません。拡張の内側の記録の写しに、省ける項目（段のログの更新時刻 `mtimeMs`・前の実行の目印 `previous`・最後の更新からの秒 `quietSec`）を足しただけです。`mtimeMs` を持たない写しは「印なし」として読み、`previous` を持たない写しは前の実行でないものとして読みます。
- D0025 は記録の形（`state.json`・`logs/*.jsonl`・`99_summary.md`）を変えません。拡張の内側の記録の写しの成果物の項目を、文字だけの形から `{ text, mtimeMs, cut }`（中身・更新時刻・先頭 256 KiB で切れた印）に広げ、HTML に成果物のタブ（一覧とプレビュー）を足しました。文字だけの形の写しも読みます（時刻は「—」、切れた印なし）。意味が変わるのは次の 3 つです。(1) symlink の成果物：今まで辿って読めたものを読まなくなり、「まだない」と同じ見た目にします（理由は画面に出しません。外のファイルを画面に出さないためで、読めるようにはしません。確かめてから開くまでのあいだの差し替えは塞いでいません）。`00_input.md` が symlink だと、図の依頼メモ（開発フローでは要件メモ）の節が「まだ」になり、`state.json` もログも無い実行は「記録がありません」にもなります。(2) 「ある」かどうかを、全文でなく読んだ範囲（先頭 256 KiB）で決めるので、先頭 256 KiB が空白だけで後ろに文字がある成果物は「まだない」になります。(3) 1 回の読みの合計が 4 MiB に届くと、一覧の後ろの成果物は読まず「まだない」と同じ見た目になります（今までは全部読んでいました。開発フローの 7 つでは届きません）。
- D0026 で `pipeline.toml` の `[pipeline]` に `max_buffer_mb` を足しました。無ければ 32（MB）として読みます。足すだけで、ほかの項目の意味は変えません。
- D0035 で `pipe.toml` の `[[stages]]` に `max_agent_calls` を足しました。無ければ 20 として読みます。拡張の作業台は知らない項目として、書き出すときに落とします（上限は既定の 20 に戻ります）。
- D0050 は記録の形（`state.json`・`logs/*.jsonl`・`99_summary.md`）を変えません。拡張の内側の写しに、図の状態の表の項目 `tools`（省ける。無い写しは表が空として読み、一覧の行の組み立ては作らない `null`）・段のログの呼び出し `calls`（頼んだときだけ。頼まない読み方は今までと同じ）・`RunRecord` の `driver` の有無 `hasDriver`（`driver` が項目として有り null でないこと。無い・読めない写しは false）を足し、HTML に詳細のタブ「エージェント・スキル」とパネルを足しただけです。意味が変わるのは次の 2 つです。(1) 詳細のタブが 3 つから 4 つになり、D0019-AC-62 のタブ 3 つ（図と出力・成果物・使用量）の並びを置き換えます。(2) 段の名前が `constructor` のような `Object` のプロパティ名と同じ記録で、時系列の行の表示名が、段の名前そのままになります（今までは関数の文字が入っていました。ふつうの記録の出力は同じです）。
- D0051 で `state.json` の `runs[]` に `max_budget_usd`（効いた上限）と `resumed`（会話の続きの印。`true` だけ）を足しました。足すだけで、上限が効いた SDK の段の実行にだけ書き、無い古い記録は上限なしとして読みます。鍵は共通の表 `tests/fixtures/budget_record.json` を本体と拡張のテストが読んで結びます。意味が変わるのは `pipeline.toml` と `pipe.toml` の `max_budget_usd` の検査で、0 より大きい有限な数でない値は、流す前に直し方つきで止まります（`pipeline.toml` の `0` は今までどおり未設定）。
- D0062 で `state.json` の `stages[]` に `check`（`on_fail`・`max_retries`。判定のある段だけ）と、`runs[]` の `check` の要素に `attempt`（その段の何回目の検証か）を足しました。どちらも足すだけで、無い古い記録は、判定の節を出さない／並びの番号で読みます。古い版の拡張は知らない項目を読まずに捨てます。鍵は共通の表 `tests/fixtures/check_record.json` を本体と拡張のテストが読んで結びます。`pipeline.toml`・`pipe.toml` と `guard` は変えません。意味が変わるのは、`check` の要素の鍵の集まりに `attempt` が増えることだけです（鍵の集まりをそのまま比べているテスト 3 件は、`attempt` を含める形に直す）。
- D0063 で `state.json` の `stages[]` に `group`（並列の枠の名前。枠の中の段だけ）を足しました。足すだけで、無い古い記録は枠なしで読みます（段は一列に出る）。古い版の拡張は知らない項目を読まずに捨てるので、新しい記録でも段が一列に出ます。鍵は共通の表 `tests/fixtures/group_record.json` を本体と拡張のテストが読んで結びます。意味が変わるものはありません（`stages[]` の鍵の集まりをそのまま比べているテストは、`group` の無い段を比べているので変わりません）。
- D0065 は記録の形・設定・パイプの形を変えません。作業台の「保存した版」のファイル名の種別に `-external`（外で書き換わる前）を足しただけです（`<13桁の時刻>-external.json`。中身は同じ `PipeModel` の JSON）。今の拡張は `-external` の無い古い版をそのまま読みます。`-external` を知らない前の拡張は、形の違うファイルとして読み飛ばし、50 版の数にも入れず消しません（前の拡張に戻すと残るだけで、害は容量だけ。手で消せます）。内側の型 `VersionEntry` に `external?: true`（省ける）を足しました。
- D0069 で `state.json` に `received_from`（`--after` で前のパイプの記録を受けた実行だけ。前の名前・終わった日時・種類・成果物の場所）を足しました。足すだけで、無い古い記録は受けた元の無い実行として読みます。続きの `--review`・`--from` は、この項目をそのまま使い、前の記録を読み直しません。拡張は知らない項目として読み捨てるので、拡張の画面は変えません。
- D0071 で `state.json` の `runs[]` の `review` の要素に `at`（書いた時刻。`Prompt` 行の `at` と同じ書き方）を足しました。足すだけで、無い古い記録は `record check` が「判定できなかった」として読みます。ほかの読み手（`--review`・`live`・拡張）は `at` を使いません。古い版の拡張は知らない項目を読まずに捨てます。`driver` の値 `"pipe-dev"` は変えません。`Prompt` 行の `prompt` と `99_summary.md` の1行目の呼び名が `/pipe-dev` から `/pipe-in` に変わりますが、文字として読むだけなので古い記録もそのまま読めます。`runs[]` の要素の鍵の集まりを比べているテスト（`test_d0019_ac50_state_only_adds_keys`）は、`at` を含める形に直しました。
- D0077 で、会話の中でパイプを流す道（`pipe-in-gen chat`）の記録を足しました。`state.json` の `driver` に `"pipe-chat"`、`chat` の節、`usage_summary` の `available: false` と理由（`total_cost_usd`・`runs[]` の `cost_usd` は `null`）、実行のフォルダの `hook/`・`probe/` です。足すだけで、無い古い記録は今までどおり読めます。拡張は `usage_summary.available === false` のときだけ「取れない」を出し、それ以外は変わりません。`available` を知らない古い拡張は、使用量の表を零で出し、図の段に `$0.000` が出ることがあります（見た目だけで、記録は壊れません）。`--review` は `driver` があれば続きを流さず、`pipe-chat` のときは `chat next` を案内します。`guard_hook.py` の `decide` と `engine/guard.py` は変えません。
- D0079 で、`state.json` に `reply_wait`（段・識別子・始めた時刻。端末の `pipe-in` が確認の段で人の入力を待っているあいだだけ）を足しました。足すだけで、無い古い記録は印なしとして読みます。古い版の拡張は知らない項目を読まずに捨てるのでボタンが出ず、古い本体で流した実行にもボタンは出ません。`pipe.toml`・`pipeline.toml` の形は変えません。`RESERVED_OUTPUTS` に `reply.json` が入り、`output = "reply.json"` の既存のパイプは検査で止まります（`check_pipe`・`validatePipe`）。`--pause` で止めた実行の案内は、`pipe-in --review` に変わりました。
- D0080 で、`state.json` を作る3つの書き手（SDK の `_save_state`・`record start`・`chat start`）の土台を `pipe_in/engine/state.py` の `new_state` に1つにし、新しい記録の最初の鍵に `schema: 1` を足しました。開発用の新しい記録だけ値が変わります：`total_cost_usd` は `null`、`usage_summary` は `{available: false, reason}`、`runs[].cost_usd` は `null`、`runs[].metrics` は鍵なし（今までは `0.0`・`null`・`0.0`・`{}`）。SDK の道は `driver` を書かず、会話の道は値を変えません。`schema` の無い古い記録は読むだけで、変換も書き換えもしません（`archive/` の中も）。`--review` で続ける実行も `schema` を足さず、`record` で続けても古い値は残ります。読む側は `schema` を見て読み分けず、2 以上や数でない値でも落ちずに読みます。拡張は `usage_summary.available === false` で「取れない」を出す道が D0077 からあるので、直しません（古い版の拡張は零で出すことがあります）。鍵と値の種類は共通の表 `tests/fixtures/state_record.json` を本体と拡張のテストが読んで結びます。`runs[]` の `cost_usd` が `null` の記録を SDK の `--review` が続けても、合計は 0 として数えます。`test_d0019_ac50_state_only_adds_keys` は `schema` を含める形に直しました。
- D0081 で、`state.json` に任意の鍵 `flow`（`steps`・`retries`）を足しました。書くのはパイプ（`LinearPipeline`）だけで、開発フロー・会話の道は書きません。`--review` で続けるときに読んで、`max_steps`・`max_retries` の回数を引き継ぎます。無い記録は 0 から、壊れた部分は 0 として読みます。共通の表の `sdk` 行の `optional_keys` に足しました。拡張は読み飛ばします。意味が変わるのは2つだけです：`--review` をはさむと上限が早く効く、人の `revise` を `steps` に数えない。`pipe.toml`・`pipeline.toml`・`guard` は変えません。
- 項目を足すときは、無くても読めるようにします（既定の値を決める）。
- パイプの定義（`PipeDef`・`PipeStage` など）や設定（`StageConfig`・`Config`）に項目を足すときは、会話の道の能力表 `pipe_in/pipe/capability.py` にも 1 行足します（実行役 `sdk`・`chat` ごとに、効く・断る・一覧に出す・黙る・関係しない を決める）。足し忘れは `tests/test_capability.py` が落とします。断る文と効かない設定の一覧は表から作るので、`chat.py` に項目の名前の条件を足さないでください。
- 項目の意味を変える・消すときは、古いものを読んだときに、黙って違う動きをしないようにします（読めるようにするか、何をすればよいかを出して止まる）。
- どちらにしたかと、その理由を、決定の記録に書きます。

## 検査の二重化（Python と拡張）

パイプの定義の検査は、Python と拡張の2か所にあります。拡張は検査のために子プロセスを起こさない（起こすのは流すための `pipe-in` だけ。D0078）ので、一本にはしません。代わりに、同じ見本を両側に掛けるテストで、ずれを見張ります。

- 相手：`pipe_in/pipe/definition.py` の `check_pipe` と、`vscode/src/domain/pipeModel.ts` の `validatePipe`。警告（`lint.py`）と `pipeCheck.ts`（段の判定スイッチ）は対象外です。
- 決まりを足す・変えるとき：`check_pipe` と `validatePipe` の両方を直し、見本のケースを足します。誤りの見本は `err-` で始めます。片側だけが見る決まりは `expected.json` に `only`（`"python"` か `"extension"`）と `reason` を書きます。拡張が読まない項目や、読み込みで直る項目は `only: "python"` と理由で残します。
- 見本は `tests/fixtures/check_parity/<ケース名>/`。`pipe-in-<名前>/pipe.toml`（必要なら `prompts/`）と `expected.json`（`note`・`valid`・`errors`・`keywords`、`only` があれば `reason`）からなります。文は両側で違うので、件数とキーワードで比べます。誤りの件数が `errors` と等しく、`keywords` の各要素（配列ならどれか1つ）を含む誤りがあり、どの誤りもどれかのキーワードを含むときに合います。この規則は `_matcher.json` で両側が確かめます。
- テスト：Python は `tests/test_check_parity.py`、拡張は `vscode/src/app/pipeCheckParity.test.ts`（見本を読む偽の `PipeStore` を `loadPipe` に渡す）。
- 写しの見張り：拡張の `DANGEROUS_COMMANDS` と `RESERVED_OUTPUTS` は、本体の `DANGEROUS_BASH`（`guard.py`）と `RESERVED_OUTPUTS` の写しです。守る側の `guard.py` は変えません。本体の表に語を足すと Python のテストが「見本に無い」と落ち、見本を足すと拡張のテストが落ちるので、写しを直します。

### 意図した差

| 種類 | 中身 | 見本 |
| --- | --- | --- |
| 作業台にない項目 | `kind`・`input`（読み込みで直る）・`timeout_sec`・`max_agent_calls`（読まず、保存で落ちる。D0035） | `err-pipe-kind-input`・`err-check-timeout-agent-calls`（`only: python`） |
| 読み込みで直る項目 | access の型違い・MCP の type・写しの型違い・`next` と `routes` の併用・存在しない行き先や `on_fail`・枠の中の `next`・`routes`・`prompt` と `prompt_file` の両方。保存すると直った形で書かれる | `err-values-fixed-on-load`・`err-flow-targets-fixed-on-load`・`err-prompt-both`・`err-prompt-file-outside`（`only: python`） |
| 拡張が厳しい側 | 前の段へのつなぎ、空の指示ファイル、docs_dir の途中の `..`（Python は解決して中なら通す）、JS の語境界（Unicode より厳しい）。流す側は狭めも広げもしない | `ext-flow-backward`・`ext-prompt-empty-file`（`only: extension`） |
| 作業台が開けないもの | `kind = "dev"` のパイプ、使えないフォルダ名 | `err-kind-dev-stages`・`err-pipe-name-bad-folder`・`ok-kind-dev`（`only: python`） |

## 依存を足すとき

- 標準ライブラリや、今ある依存で済むなら足しません。
- 足すときは、必要な理由を決定の記録に書きます。`package-lock.json` も一緒にコミットします。
- 拡張は、パネルの中で外部から何も読み込みません（束ねたものだけを使います）。

## 外から来たものの扱い

- ログ・成果物・パイプの定義など、外から来た文字は、そのまま HTML に入れません（`escapeHtml`）。
- パスは、決まった場所の外に出ないことを確かめてから使います（`..` を含むもの、絶対パスでの指定など）。
- フックの入力のように「だれから来たか分からない」ものは、読めなければ止めます。
