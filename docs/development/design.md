# 設計の決まり

## 置き場所

| やりたいこと | 場所 |
| --- | --- |
| 入口（pipe-in コマンド） | `pipe_in/cli.py` |
| 前の名前のコマンドの別名（0.3 の間だけ。案内を出して新しい入口を呼ぶ） | `pipe_in/legacy.py`・`generator/legacy.py` |
| どのパイプにも共通：段の実行・記録・確認・まとめ | `pipe_in/engine/pipeline.py` |
| 段の設定の型・protected_paths | `pipe_in/engine/spec.py` |
| 止める操作（pipe-in が流す段の PreToolUse フック） | `pipe_in/engine/guard.py` |
| SDK の呼び出し（段のログの `Prompt` 行の形もここ） | `pipe_in/engine/runner.py` |
| 記録に書く時刻の書き方（UTC からのずれつき、秒まで） | `pipe_in/engine/clock.py` |
| 設定の読み込み | `pipe_in/engine/config.py` |
| セッション名の取り方と、セッション ID・受け持ちの検査（標準ライブラリだけ。拡張の `sessionName.ts` と同じ規則を、同じ表で確かめる） | `pipe_in/engine/session.py`・共通の表 `tests/fixtures/session_names.json` |
| 進み具合の写し（`state.json` などから、Claude のアーティファクトに出す JSON を作る。標準ライブラリだけ）と、そのページの HTML（外部の読み込みなし）、コマンド `pipe-in live`、記録を見張って変わったときだけ1行を出す `pipe-in live watch`（読むだけ。時計・眠り・読み・書きは引数で差し替える） | `pipe_in/engine/live.py`・`live_page.py`・`live_cmd.py`・`live_watch.py` |
| 使用量の集計と表 | `pipe_in/usage/` |
| 開発フロー（5段・差し戻し・指示文） | `pipe_in/dev/` |
| パイプ（定義の読み込み・検査・探す順番・流れ・権限の型） | `pipe_in/pipe/` |
| 検証の審査の計算（`[stages.check.judge]`。合否・平均・直す点。標準ライブラリだけ。`generator/judge_score.py` と決まりを同じにして二重に持つ） | `pipe_in/pipe/judge.py` |
| ジェネレーター（pipe-in-gen・環境の検出・ひな形） | `generator/`（Python では `pipe_in_generator`）・`generator/templates/` |
| Claude Code のプラグイン（スキル・エージェント・フックの定義。作る `pipe-build`・検査 `pipe-eval`・審査 `pipe-judge`・進み具合を見る `pipe-live` のスキル、エージェント `pipe-builder`・`pipe-judge`） | `.claude-plugin/marketplace.json`・`plugin/` |
| プラグインのフックの本体（pipe-builder と pipe-judge の操作を絞る） | `generator/guard_hook.py` |
| プラグインの採点の計算（総合点・合否・`--runs` のばらつき。標準ライブラリだけ） | `generator/judge_score.py` |
| VSCode 拡張 | `vscode/`（層は下の「拡張の層」） |
| 拡張の名前の表（コマンド ID・設定の節・パネルの型）と、前の版の設定・コマンド ID の読み替え | `vscode/src/app/names.ts` |
| このリポジトリを開発する Claude Code のスキル | `.claude/skills/pipe-in/`・`.claude/skills/pipe-help/`・矛盾監査 `.claude/skills/pipe-audit/`・助言 `.claude/skills/pipe-advise/`・審査 `.claude/skills/pipe-judge/`・文書をそろえる `.claude/skills/pipe-docs/`・計画ボード `.claude/skills/pipe-plan/`（ページのひな形 `board.html`） |
| /pipe-in の段を受け持つサブエージェントと、その書ける場所を絞るフック | `.claude/agents/`（`pipe-in-*`。監査と助言の `pipe-in-auditor`・`pipe-in-advisor` は読むだけで、助言は公式の文書を Web（WebFetch・WebSearch）で読める。助言の報告を採点する審査の `pipe-in-judge` も読むだけで、公式の文書を WebFetch だけで読める。文書係の `pipe-in-documenter` は文書だけを書ける）・`.claude/hooks/pipe_in_guard.py`（標準ライブラリだけ。表に無い `pipe-in-*` と、文字列でない `agent_type` は読むだけにする。判断の途中で例外が出ても止める） |
| コードを変えたのに文書が変わっていないまま止まるとき、1回だけ知らせる Stop のフック（標準ライブラリだけ。目印は一時フォルダに置く） | `.claude/hooks/docs_reminder.py` |
| /pipe-in の記録を書く（pipe-in record。`start` の `--name`・`--session-id`、`begin` の `--agent` もここ） | `pipe_in/dev/record.py` |
| 利用者向けの説明（使い方・拡張・パイプ・プラグイン・安全・記録・設定・移行・開発）。README は入口だけ | `docs/guide/`・目次 `docs/guide/README.md` |
| 開発のルール・決定の記録 | `docs/development/`・`docs/decisions/` |
| ロードマップ（目指す姿と段階） | `docs/roadmap.md` |
| 調べた結果（実験の方法・結果・やり直すためのスクリプトと集計の結果。生のデータは置かない） | `docs/research/`・目次 `docs/research/README.md` |
| 画面のデザインの土台（ブランド「プラグ」の色の決まり・部品と画面の見本。Claude のデザインのキャンバスの写し） | `docs/design/`・`docs/design/README.md` |
| ロゴ（README に載せる SVG。明るい表示用と暗い表示用）とロゴの動き（HTML と GIF。検査は `tests/test_plug_logo.py`）、README とガイドの画像（明暗の PNG）、撮り直しの手順 | `docs/assets/`・`docs/assets/README.md` |
| 画面用の見本の記録（本体の流れを差し替えた runner で作る。README とガイドの画像と確認用のページが読む。4つ：完了・動いている2つ（うち1つは、戻る矢印が光る描き直しの素材）・確認待ち） | `tests/fixtures/showcase/`・`tests/fixtures/showcase_running/`・`tests/fixtures/showcase_running_next/`・`tests/fixtures/showcase_waiting/`・作り方 `tests/showcase.py` |
| 画面の確認用のページ（開発用。`npm run preview`）。実行の一覧の見本は上の4つの見本の記録から、一時フォルダの中に「主の checkout＋別の worktree＋前の実行の置き場所」の木を組み立てて作る（`tests/fixtures/` には足さない）。更新なしの見本（`run-panel-stale-light`・`run-panel-stale-dark`・目安の手前の `run-panel-stale-soon-dark`）も同じ作りで、動いている・確認待ちの見本とあわせて、見本の記録を一時フォルダに写し、段のログの更新時刻を見本の「今」からの相対にそろえて読む（`tests/fixtures/` の更新時刻に左右されない）。成果物のタブの見本（`run-panel-artifacts-light`・`run-panel-artifacts-dark`）も同じ作りで、動いている開発フローと12個のパイプの2つの実行を持ち、成果物の更新時刻を固定の値にそろえる（見本の文章は長い Markdown・外から来た文字・上限を超える日本語） | `vscode/scripts/preview.ts`・ページを作る関数と木を組み立てる関数 `vscode/scripts/previewPages.ts`・見本の成果物の文章 `vscode/scripts/artifactSamples.ts` |
| 動画を作るパイプの見本（`pipe-in --pipe examples/video/pipes/pipe-in-video` で流し、`pipe-in-gen check video --pipes-dir examples/video/pipes` で確かめる。受付とテンプレートの2つ以外のコードは置かない） | `examples/video/pipes/pipe-in-video/`・`examples/video/` |
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

- 逆向きの import は `tests/test_architecture.py` が止めます。
- `pipe_in.engine` は、どのパイプにも共通の仕組みです。特定のパイプ（開発フロー・パイプの定義）や入口（`pipe_in.cli`）を知りません。
- `generator/guard_hook.py` と `.claude/hooks/pipe_in_guard.py` は、Claude Code が道具を呼ぶたびに動きます。起動を軽くし、本体が壊れていても動くように、**標準ライブラリだけ**を使います（`guard_hook.py` は `tests/test_architecture.py` が検査します）。`generator/judge_score.py`（`pipe-in-gen judge-score`）も、本体を読み込まず標準ライブラリだけです。

## 拡張の層

| 層 | パス | 置くもの | 使ってよい外の部品 |
| --- | --- | --- | --- |
| ドメイン | `vscode/src/domain/` | 段・実行の記録・段のログ・成果物（作った段・読んだ範囲と切れた印・更新時刻の文字・押していないときの既定の選び `defaultArtifactName` を決める `artifacts.ts`）・図の状態（「今」は `ViewClock` を引数で受ける）・時刻の読み方と書き方（`timestamp.ts`。記録の時刻を読むことと、手元の時刻の `MM/DD HH:mm` に書くこと）、パイプのモデル（`pipeModel.ts`）・ケーブルの通り道と曲線（`pipeWires.ts`）・抜き差しと間に挟む（`pipeLinks.ts`）・離した点から差す先を決める（`pipeDrop.ts`）・引いているケーブルのひもの動き（`cableRope.ts`）・複製や枠の出し入れなどの編集（`pipeEdit.ts`）・判定のスイッチと不合格の行き先（`pipeCheck.ts`）・右クリックのメニュー（`pipeMenu.ts`）・元に戻す（`editHistory.ts`）・保存した版の決まり（`pipeVersions.ts`）・小さな TOML の読み手（`toml.ts`）、実行の一覧（実行の目印と `archive` の id は `runs.ts`、1行の組み立て・状態・並び・状態ごとの件数・ステータスバーの件数に数える行・ボタンで先に出す確認待ちの判断・省く件数・覚えた値の検めは `runList.ts`、別の worktree の登録の読み方・ブランチ名や短い ID の取り方・受け入れの判断は `worktrees.ts`）、セッション名の取り方（`sessionName.ts`。本体の `session.py` と同じ規則）、時系列のモデル（`gantt.ts`。段の実行ごとの行・エージェントの帯・確認を待った帯・横軸。「今」は引数）、最後の更新からの秒（`quiet.ts`。段のログの更新時刻から「今」までの秒。「今」は引数。上限の 7 日は `timestamp.ts` の定数）。純粋な関数だけ（時計にも触れない） | `node:path` |
| アプリケーション | `vscode/src/app/` | 口 `WorkDirSource`・`PipeStore`・`VersionStore`・`RunsSource`・`MemoryStore` と、それを使う手順（`refreshView`・`resolveWorkDir`・作業台の読み込みと保存・置き場所と保存先の決め方・保存した版の記録と読み込み・実行の一覧を作って見る実行を決める（別の worktree の行があるかの旗も返す）`runList.ts`・選びを覚える `selection.ts`）、監視の対象と読み直しの間隔と読み直しの要否（別の worktree の行があるあいだは、パネルが見えていなくても読み直す）と小さなタイマー、古い読み込みの結果を捨てる世代の部品（`refreshPolicy.ts`）、止まっているかもしれない印の目安の秒（設定の分 → 秒。`staleness.ts`）、名前の表と前の版の名前の読み替え（`names.ts`） | `node:path` |
| 画面 | `vscode/src/view/` | 図の状態 → HTML の文字列（時間の書き方 `duration.ts`・図の枠の「時間」の節 `timesHtml.ts`・左の実行の一覧 `runListHtml.ts`・上のバー、右の詳細、タブの枠組み `shellHtml.ts`・時系列の SVG `ganttHtml.ts`・止まっているかもしれない印の共通部品 `staleMark.ts`（言葉・属性・時間の要素のほか、一覧の行と詳細が同じ「動いている行だけ」の判断を共有する `rowStaleAttrs` も持つ）、タブ「成果物」の左の一覧と右のプレビュー `artifactsHtml.ts`、成果物の Markdown を許すタグだけの HTML に直す `markdownHtml.ts`（リンクは `a` にせず、画像は読み込まない。外から来た文字は `escapeHtml` を1回だけ通す）を含む。CSP と style の束ねは `panelHtml.ts`）、パネルのスクリプト（`panelScript.ts`。数え上げ・目安に届いた印の要素への `is-stale` の付与・戻る矢印の光り・絞り込みとタブ・成果物の選び・描き直しをまたぐ保持）、ステータスバーの文字と説明（件数の形と、外から来た文字を 1 行にする関数を含む `statusBar.ts`）、パネルとの受け渡しの形 | なし |
| 基盤 | `vscode/src/infra/` | 口の実装（`fsWorkDirSource.ts`・`fsPipes.ts`・`fsVersions.ts`。`fsWorkDirSource.ts` は段のログの中身に加えて更新時刻（`stat`）も読み、成果物は通常のファイルだけを、更新時刻（`lstat`）と先頭 256 KiB まで読む。1 回の読みは、合計が 4 MiB に届いたら残りを読まない（最大でも 4 MiB + 256 KiB 未満））。別の worktree を `.git` の登録（ファイル）から見つけ、いまの checkout のブランチ名も読む `fsWorktrees.ts`。読み取りの口を6つの関数（`readFile`・`readdir`・`stat`・`lstat`・`realpath`・先頭だけ読む `readHead`。`00_input.md` の先頭と成果物の読みに使う。1 回の読みが短く返る（ネットワークや FUSE のファイル）ときも、頼んだ量かファイルの終わりまで読む）に絞る `readOnlyFs.ts`。触れる場所はここで絞る | `node:fs`・`node:fs/promises`・`node:os`・`node:path` |
| パネルの中 | `vscode/src/webview/` | 作業台の画面の操作（ビルドで1つの pipeEditor.js に束ねる）。判断は domain の関数に任せる | なし |
| 入口 | `vscode/src/extension.ts` | コマンド・パネル・ファイルの監視・エディタで開く。判断は持たない。拡張ホストの側で時計（今の時刻）を読むのもここだけ（パネルのスクリプトは、描き直しを受けた時刻からの差だけを数える） | `vscode` を import してよいのはここだけ |

- 層の決まりは `vscode/src/architecture.test.ts` が検査します（テストのファイルと `vscode/src/test/` の補助は除く）。
- 本体の記録の形の知識は `runRecord.ts`・`stageLog.ts`・`artifacts.ts`・`runs.ts` の中だけに置きます。本体の記録の形が変わったら、ここを直します。
- 拡張は work_dir を読むだけで書きません。書いてよいのは、作業台で「保存」を押したときの、パイプの置き場所の中のパイプのフォルダ（`pipe-in-<名前>/`。前の版のフォルダ名も）の決まったファイルだけです（`vscode/src/infra/fsPipes.ts` が場所を絞ります）。保存先は拡張が開いたパイプから決め、パネルから来た値では決めません。
- 実行の一覧のために、同じ git リポジトリの別の worktree の work_dir と、`.git` の中の worktree の登録も、**読むだけ**です（`fsWorkDirSource.ts`・`fsWorktrees.ts`。書き込みの関数を型に入れず、子プロセスは起こしません。`tests/test_decision_ui.py` と `vscode/src/architecture.test.ts` が検査します）。別の worktree で読むのは `state.json`・`logs/`（中身と、止まっているかもしれない印のための更新時刻 `stat`）・記録から作った成果物の一覧にあるもの（更新時刻と、1 つにつき先頭 256 KiB まで）・`00_input.md` の先頭 4 KiB（`state.json` に `name` が無い run だけ。セッション名の元）だけで、いまの checkout のブランチ名のために `.git/HEAD` も読みます。登録のパスが絶対パスで実在し、その worktree の `.git` が自分の登録を指し返し、work_dir がその worktree の中に収まるときだけ場所にします。パネルや覚えた値から来る実行の目印は、`runs.ts` で形を検め、拡張が作った一覧にあるものだけを通します（パスを作りません）。
- 成果物のプレビューのために読む成果物は、記録から作った一覧にある名前の、通常のファイルだけです（`lstat` で種類と更新時刻を見て、`readHead` で先頭 256 KiB まで読みます。1 回の読みは、合計が 4 MiB に届いたら残りを読みません。最大でも 4 MiB + 256 KiB 未満）。symlink・フォルダは読まず、「まだない」と同じ扱いです。確かめてから開くまでのあいだに通常のファイルが symlink へ差し替えられる競合は塞いでいません（口は `'r'` だけで開く6つのまま変えず、差し替えるには作業フォルダに書ける別のプロセスが要り、見えるのは使う人自身の画面だけだからです）。`00_input.md` の先頭 4 KiB と `state.json` は、これまでどおり symlink を辿ります。中身は `view/` の部品が許すタグだけの HTML に直して、描き直しの HTML に入れます（メッセージの種類と CSP は変えません）。変換でふくらむ HTML は出す側でも抑えます（表は 100 列・セル 20,000・HTML の長さが入力の約 20 倍（省略の一文も入ります）まで、1 回の描き直しのプレビューの中身は合計約 8 MiB 文字まで。超えたところから先は案内だけ）。成果物の選びとスクロールはパネルのスクリプトの変数だけで持ち、保存しません。
- 選んだ実行は、VSCode がワークスペースごとに用意する `workspaceState`（キー `pipe-in.selectedRun`）に、場所の目印と実行の目印だけを書きます（`vscode/src/app/selection.ts`。work_dir・プロジェクト・worktree には書きません）。
- 作業台の「保存した版」と、閉じたときの下書きは、VSCode が拡張に用意する保存場所（`storageUri`、無ければ `globalStorageUri`）の `pipe-versions/pipe-in-<名前>/<版の id>.json` にだけ書きます。プロジェクトには書きません（`vscode/src/infra/fsVersions.ts` が場所を絞ります）。
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
- D0034 で `pipe.toml` の `[[stages]]` に `max_agent_calls` を足しました。無ければ 20 として読みます。拡張の作業台は知らない項目として、書き出すときに落とします（上限は既定の 20 に戻ります）。
- 項目を足すときは、無くても読めるようにします（既定の値を決める）。
- 項目の意味を変える・消すときは、古いものを読んだときに、黙って違う動きをしないようにします（読めるようにするか、何をすればよいかを出して止まる）。
- どちらにしたかと、その理由を、決定の記録に書きます。

## 依存を足すとき

- 標準ライブラリや、今ある依存で済むなら足しません。
- 足すときは、必要な理由を決定の記録に書きます。`package-lock.json` も一緒にコミットします。
- 拡張は、パネルの中で外部から何も読み込みません（束ねたものだけを使います）。

## 外から来たものの扱い

- ログ・成果物・パイプの定義など、外から来た文字は、そのまま HTML に入れません（`escapeHtml`）。
- パスは、決まった場所の外に出ないことを確かめてから使います（`..` を含むもの、絶対パスでの指定など）。
- フックの入力のように「だれから来たか分からない」ものは、読めなければ止めます。
