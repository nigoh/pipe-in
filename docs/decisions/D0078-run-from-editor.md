# D0078 作業台からパイプを流せる（#21）

## 目的

作業台で保存したパイプを、端末で `pipe-in --pipe …` を打たなくても、作業台の「流す」から流せるようにする。流すのは VSCode の端末で起こす `pipe-in` で、拡張そのものは段を流さない。

拡張の「子プロセスを起こさない・流す機能を持たない」の決まりを変える機能（ロードマップ段階3の1つ目）。変えるのは「決まった形の `pipe-in` を1つだけ起こしてよい」ことだけで、`child_process` を import しない決まり（D0019-AC-21）と、拡張が work_dir に書かない決まりは変えない。

## 機能要件と受け入れ基準

- FR-01〜04 コマンドの形（純粋な関数。`vscode/src/domain/runCommand.ts`）。
  - D0078-AC-01：`required`・`optional` で依頼メモがあると、`args` は `--pipe=`・`--project=`・`--text=` の3つ。`command` は渡した絶対パスのまま（`vscode/src/domain/runCommand.test.ts`）。
  - D0078-AC-02：`optional` で依頼メモが空（空白だけ）なら2つ。`none` は依頼メモがあっても2つ（同上・`vscode/src/app/runFlow.test.ts`）。
  - D0078-AC-03：旗・シェルの文字・引用符・複数行・日本語の依頼メモでも、`args` は3つで、3つ目は `--text=` ＋そのまま（同上。共通の表 `tests/fixtures/run_command.json` の全行）。
  - D0078-AC-04：パイプのフォルダ・プロジェクト・実行ファイルが絶対パスでない・NUL か改行を含む・空なら断る。空白・`=`・日本語・Windows の `C:\…` はそのまま1つの要素（同上・`vscode/src/app/runFlow.test.ts`）。
- FR-05〜07 実行ファイルの決め方。
  - D0078-AC-05：設定の値が未設定かちょうど `pipe-in` なら PATH から探す。絶対パスはそのまま通し、相対・`./pipe-in`・`pipe-in2`・`-` 始まり・NUL か改行・空・空白だけ・文字でない・名前だけに引数を付けた値（`pipe-in --yes`）は理由つきで断る。絶対パスは丸ごと 1 つのファイルの場所として扱い、引数には分けない（`vscode/src/domain/runExecutable.test.ts`）。
  - D0078-AC-06：PATH からは絶対の項目だけを順に見て、最初の通常のファイルを返す。空・相対・`.` の項目は飛ばす。無ければ見つからない理由（`vscode/src/domain/runExecutable.test.ts`・`vscode/src/app/runExecutable.test.ts`）。
  - D0078-AC-07：Windows の候補は `pipe-in.exe` → `pipe-in.com` だけ（`;` 区切り）。同じ項目に両方あれば `.exe` が先（同上）。
  - D0078-AC-08：Windows で `.exe`・`.com`（大小文字を問わない）以外の絶対パスは断る。macOS・Linux は拡張子を見ない（`vscode/src/domain/runExecutable.test.ts`）。
  - D0078-AC-09：ファイルがあるかの確かめは `vscode/src/infra/fsFileProbe.ts` だけで、`stat` を1回呼び、読むだけ。純粋な部品は `node:fs` を読まない（`vscode/src/infra/fsFileProbe.test.ts`・`vscode/src/architectureRun.test.ts`）。
- FR-03 流してよいかの判断（`vscode/src/domain/runDecision.ts`）。
  - D0078-AC-10：まだ一度も保存していないと、「先に保存」の理由で流さない（`vscode/src/domain/runDecision.test.ts`）。
  - D0078-AC-11：保存していない変更があると流さない（同上）。
  - D0078-AC-12：保存済みの形に検査の誤りがあると流さない。検査の対象は拡張が持つ保存済みの形（同上・`vscode/src/app/runFlow.test.ts`）。
  - D0078-AC-13：ワークスペースのフォルダが無いと流さない（同上）。
  - D0078-AC-14：信頼していないワークスペースでは流さない（同上）。
  - D0078-AC-15：`required` で依頼メモが空（全角空白・改行・タブだけも）なら流さない。`optional` は通る。`none` は見ない（同上）。
  - D0078-AC-16：依頼メモは UTF-16 の長さで 4,000 ちょうどなら通り、4,001 なら流さない。`none` は長さを見ない（同上）。
  - D0078-AC-17：NUL と、対にならないサロゲートを含むと流さない。対になったもの（絵文字）は通る（同上）。
  - D0078-AC-18：実行ファイルが決まらないと、その理由をそのまま返して流さない（同上・`vscode/src/app/runExecutable.test.ts`）。
  - D0078-AC-19：同じパイプのフォルダから起こした実行が終わっていないと流さない（`vscode/src/domain/runDecision.test.ts`・`vscode/src/app/runActive.test.ts`）。
  - D0078-AC-20：どれにも当たらないときだけ流してよい。複数に当たるときは決まった順（`RUN_BLOCK_ORDER`）の最初の理由を1つ返す（`vscode/src/domain/runDecision.test.ts`・`vscode/src/app/runFlow.test.ts`）。
- FR-04 パネルからの知らせ。
  - D0078-AC-21：`{ type: 'run', text }` だけを読む。`text` が文字でない・無いときは null（`vscode/src/view/runMessages.test.ts`）。
  - D0078-AC-22：ほかの鍵が付いても結果の鍵は `type` と `text` だけ（同上）。
- FR-08〜11 入口の配線（`vscode/src/extension.ts`。ソースを文字で読む検査）。
  - D0078-AC-23：`src/` に `ShellExecution`・`sendText(`・`createTerminal(`・`child_process` が無い。`new vscode.ProcessExecution(` と `vscode.tasks.executeTask(` は `extension.ts` に1か所ずつ（`vscode/src/extensionRun.test.ts`）。
  - D0078-AC-24：`ProcessExecution` に渡すのは `plan.command`・`plan.args`・`{ cwd: plan.cwd }` だけで、`env` を渡さない。`planRun` が断ったら進まない（同上・`vscode/src/app/runFlow.test.ts`）。
  - D0078-AC-25：「流す」の処理が読むパネル側の値は `text` だけ。プロジェクトは `workspaceFolders[0]` から（同上）。
  - D0078-AC-26：設定は `inspect` の `globalValue`・`defaultValue` だけを取り出す（同上・`vscode/src/domain/runExecutable.test.ts`・`vscode/src/app/runExecutable.test.ts`）。
  - D0078-AC-27：`currentRunContext` が `vscode.workspace.isTrusted` を読み、`startRun` の順は `currentRunContext` → `planRun` → `activeRuns.start` → `executeTask`。`planRun` と `start` の間に `await` が無い（同上）。
  - D0078-AC-28：流したパイプの実行の目印を作る関数がある（形に使えない名前は null）。起こした後に、その実行を選んで実行パネルを開く。起こせなかったときは選ばず、開かず、理由を見せる（`vscode/src/domain/pipeRunKey.test.ts`・`vscode/src/extensionRun.test.ts`）。
  - D0078-AC-29：実行中の記録は入口のモジュールの変数で、`onDidEndTask`・`onDidEndTaskProcess` の早いほうだけで外す。作業台を閉じても外さない。開き直しても最初の知らせに `running` が入る（`vscode/src/app/runActive.test.ts`・`vscode/src/extensionRun.test.ts`。知らせ `runContext` の型は `vscode/src/view/runMessages.test.ts`）。
- FR-05・09 設定と宣言。
  - D0078-AC-30：`pipe-in.command`（文字・既定 `pipe-in`・`"scope": "machine"`・説明に「絶対パス」）がある。タスクの宣言（`taskDefinitions` など）は足さない（`vscode/src/manifestRun.test.ts`）。
  - D0078-AC-31：`capabilities.untrustedWorkspaces.supported` は `false`（説明つき）（同上）。
- FR-13 書かない・層の決まり。
  - D0078-AC-32：新しい部品は `vscode`・`node:fs`・`child_process`・時計・乱数を読まない。ドメインの3つは外の部品を import しない（`vscode/src/architectureRun.test.ts`。既存の `vscode/src/architecture.test.ts` は変えずに通る）。
  - D0078-AC-33：「流す」の処理は書く呼び出しを持たない。書くのは既存の `chooseRun` の道だけ（`vscode/src/extensionRun.test.ts`・`vscode/src/app/runFlow.test.ts`）。
- FR-14 本体との共通の表。
  - D0078-AC-34：`tests/fixtures/run_command.json` の入力から作った `args` が表の期待と等しく、本体の `_parse_args` に渡せる（`vscode/src/domain/runCommand.test.ts`・`tests/test_run_command.py`）。
  - D0078-AC-35：表のどの行でも、`pipe`・`project`・`text` が期待どおりで、ほかの旗は既定のまま（`tests/test_run_command.py`）。
  - D0078-AC-36：旗は完全な名前で、省略形に頼らない（同上）。
  - D0078-AC-37：`cli.main` に表の `args` を渡すと、依頼メモがそのまま要件メモになる。`optional` の `--text` なしは `None`。`required` に `--text` なしは本体が断る（同上）。
  - D0078-AC-38：前の版の置き場所のパイプも、保存してあれば同じ形で流せる。保存前は流さない（`vscode/src/app/runFlow.test.ts`・`tests/test_run_command.py`）。
- 画面（確認用ページ `npm run preview` の作業台。確かめ方は `.claude/skills/pipe-in/screen-check.md` の「作業台の「流す」の節」。支えの自動のテストは `vscode/src/webview/pipeEditorRun.test.ts`・`vscode/src/webview/pipeEditorRunLayout.test.ts`・`vscode/src/view/runHtml.test.ts`・`vscode/src/domain/runCommand.test.ts`・`vscode/src/domain/runDecision.test.ts`。AC-45・50 は、番号を名前に持つ自動のテストは無く、判断そのものは AC-12・14 のテストが支える）。
  - D0078-AC-39（画面）：開いた直後、畳める節「流す」が開いていて、依頼メモの欄・ボタン・起こすコマンドの形が見える。見出しで畳める。
  - D0078-AC-40（画面）：依頼メモを書くと形が変わってボタンが押せ、押すと `{ type: 'run', text }` だけが送られる（その前に `state`）。
  - D0078-AC-41（画面）：`required` で空だとボタンが押せず、理由が見える。
  - D0078-AC-42（画面）：`optional` は空でも押せ、引数は2つ。書くと3つ。
  - D0078-AC-43（画面）：`none` は欄が出ず、押せて、引数は2つ。
  - D0078-AC-44（画面）：保存していない変更があると押せず、「先に保存」の理由が見える。
  - D0078-AC-45（画面）：検査の誤りがあると押せず、理由が見える。
  - D0078-AC-46（画面）：まだ保存していないパイプは押せず、理由が1回、形の欄には別の文が出る。
  - D0078-AC-47（画面）：4,000 文字を超えると文字数が超えた印を出し、押せない。
  - D0078-AC-48（画面）：`<script>` を書いても文字として出て、動かない。
  - D0078-AC-49（画面）：実行中は押せず、「実行中です」が見える。終わると押せる。
  - D0078-AC-50（画面）：信頼していないときは押せず、理由が見える。
  - D0078-AC-51（画面）：実行ファイルが決まらないときは押せず、理由が形の欄にだけ見える（理由の行には出ない）。
- 実機（VSCode の実物。まだ）。
  - D0078-AC-52（実機）：「流す」で端末が開き、`pipe-in` が絶対パスと3つの引数で起き、実行パネルが開いて流した実行が選ばれる（前に別の実行を選んでいても）。段の確認の入力を端末で受けられ、終わっても出力が残る。
  - D0078-AC-53（実機）：信頼していないワークスペースで拡張が動かない。
  - D0078-AC-54（実機）：ワークスペースの `.vscode/settings.json` の `pipe-in.command` が効かない。
  - D0078-AC-55（実機）：プロジェクト直下の目印だけの `pipe-in` ではなく PATH のものが起きる。Windows で `.cmd` だけのときは理由が出る（見つからないときの理由の文は、`vscode/src/domain/runExecutable.test.ts` の同じ番号のテストが支える）。
  - D0078-AC-56（実機）：空白・引用符・`$`・`;`・改行・日本語・先頭 `-` の依頼メモが、Windows と macOS か Linux で本体にそのまま届く。
  - D0078-AC-57（実機）：二重に流せない。開き直しても「実行中」。端末を閉じるか終わると流せる。窓の読み込み直しで記録が消える。
- 文書。
  - D0078-AC-58：拡張の README・ガイド・安全の文書・README・手順の説明が、新しい決まり（決まった形の `pipe-in` 1つだけ・絶対パス・依頼メモは引数・ユーザーの設定だけ・信頼していないワークスペースでは動かない）に直っている（`tests/test_run_docs.py`。既存の `tests/test_rules.py`・`tests/test_doc_shape.py`・`tests/test_english_docs.py` は変えずに通る）。

## 決めたことと理由

- **決まりをどこまで変えるか。** 拡張が起こしてよい子プロセスを、作業台の「流す」が起こす決まった形の `pipe-in` 1つだけにする。それ以外（git・任意のコマンド・端末への文字送り）は今までどおり起こさない。work_dir とパイプの置き場所には新しく何も書かない。依頼メモはどこにも残さない。ロードマップの段階3で、人が「作業台から流す」を求めたため。
- **D0072 の「流すコマンドは足さない」を置き換える。** D0072 は、初めての人向けの案内で「拡張は流さない」前提にした。この機能で、保存したパイプは作業台から流せるので、その前提だけを置き換える（D0072 の記録は書き換えない）。開発フロー（`--pipe` を付けない流れ）は作業台から流せないままで、案内には端末の1行を残した。
- **起こし方は Tasks API の `ProcessExecution`。** シェルを通さず、実行ファイルと引数の配列で起こす。`child_process`・`ShellExecution`・`terminal.sendText` は使わない（`child_process` を import しない決まり D0019-AC-21 は変えない）。起こす口は `extension.ts` の `startRun` ただ1つ。`env` は足さない。
- **実行ファイルは拡張が絶対パスに決めてから渡す。** 名前だけで渡すと、VSCode が cwd（プロジェクト）の下の同じ名前のファイルを起こしうる（公式の文書に無い振る舞いなので頼らない）。Windows の `.cmd`・`.bat` は `cmd.exe` が引数を解釈して依頼メモがコマンドとして働きうるので（いわゆる BatBadBut）、`.exe`・`.com` だけにする。設定 `pipe-in.command` は絶対パスだけ通し、既定の `pipe-in` なら PATH の絶対の項目だけから探す。断った設定は既定に黙って戻さない。
- **設定はユーザーの設定だけ。** `"scope": "machine"` にし、`inspect()` の `globalValue`・`defaultValue` だけを読む。リポジトリを開いただけで任意の実行ファイルが起きる道を作らない。前の版の節には `command` が無いので、読み替えない。
- **引数は `--text=` ＋依頼メモの1要素。** 依頼メモは旗として読まれない（本体の `argparse` の省略形にも頼らない。共通の表で確かめた）。`input = "none"` のパイプには `--text` を付けない（本体は断らず `00_input.md` に書くので、拡張が付けないことで防ぐ）。依頼メモは UTF-16 で 4,000 まで、NUL と壊れた文字は流さない。
- **流してよいかの判断は1つの関数 `decideRun`。** 理由は決まった順で1つ返す（環境の問題＝パネルで直せないものを先に、パネルで直せるものを後に）。作業台のパネルも入口も同じ関数を使い、入口は `run` を受けたら自分の持つ値でもう一度判断する（パネルの判断を信じない）。パネルから入口へ来る値は依頼メモだけ。同じ理由を2か所に出さない（実行ファイルの理由は形の欄に、保存前の理由は理由の行に1回）。
- **信頼していないワークスペースでは動かさない。** `capabilities.untrustedWorkspaces` を `{ "supported": false }` と明示する。宣言しない拡張も同じ扱いなので、今の振る舞いは変わらず、明示するだけ。`limited` は動く範囲を広げる（ワークスペースの設定 `pipe-in.pipesDir` が保存先を決める、など）ので使わない。それでも流す前に `vscode.workspace.isTrusted` を見る（二重の守り）。`pipe-in` を起こすと、プロジェクト直下の `pipeline.toml` や定義が決める段の動き（`test_cmd` など）が実行される。端末で手で打つのと同じで新しい道ではないが、信頼していない場所で動かさない理由の1つ。
- **実行中の記録は入口がメモリだけで持つ。** パイプのフォルダごと。作業台を閉じても外さない（外すと、実行が続いているのに開き直して二重に流せてしまう）。タスクの終わりとプロセスの終わりの早いほうだけで外す。判断と記録の追加の間に `await` を挟まない（連打や別の作業台からの割り込みを防ぐ）。
- **流したら、その実行を選んで実行パネルを開く。** `showRun` に `{ keepSelection: true }` を足し、別の実行が確認待ちでも、今流した実行の選びを上書きしない。書くのは既存の `chooseRun`（選んだ実行の目印）だけ。
- **`node:path` を使わない（設計で変えた点）。** 絶対パスの判断を、OS の種類（`'windows' | 'posix'`）を引数で受ける正規表現にした。作業台のパネルは `--platform=browser` で束ねるので、パネルが読む部品は `node:path` を import できない。`path.win32.isAbsolute('\\foo')` は「今のドライブの根」を絶対とみなすが、要件の「絶対パス（`C:\…`・`\\server\…`）」に合わない。正規表現なら Linux の CI でも同じ判断を確かめられる。パネルは実行ファイルのパスの形から OS を推す（Windows の絶対パスと posix の絶対パスは重ならない）。
- **すり抜けの道と止め方。**
  - 依頼メモの旗・`-` 始まり：`--text=` に包む。
  - シェルの文字：シェルを通さない。
  - NUL・壊れた文字・長すぎる文：`decideRun`（入口でも）と `buildRunCommand` の二重。
  - `none` に依頼メモ：`--text` を付けない。
  - パネルの知らせに値を入れる：`parseEditorMessage` が `type` と `text` だけを返す。
  - 別のパイプ・相対パス：開いたパイプの `ref` から `path.resolve` で作り、絶対パスでなければ断る。
  - ワークスペースの設定：`machine` ＋ `globalValue`・`defaultValue` だけ。
  - 危険な設定値：絶対パスだけ通す。
  - cwd の下の同名のファイル・PATH の相対の項目：絶対パスに決めてから渡す。
  - `.cmd`・`.bat`：`.exe`・`.com` だけ。
  - 定義で実行ファイルを決める：`pipe.toml` を読む道が無い。
  - 信頼していない場所・未保存・検査の誤り・二重起動：`decideRun` と `activeRuns`。
  - 逃げ道の API：`extensionRun.test.ts` と既存の `architecture.test.ts`。
  - ファイルに書く・画面に埋め込む：書く呼び出しを持たない、`escapeHtml`、style 属性なし。
- **止める範囲は狭めない。** `guard.py`・`guard_hook.py`・`.claude/hooks/pipe_in_guard.py` は触らない。依存は足さない（`package.json` の `dependencies`・`devDependencies`・`package-lock.json`・`pyproject.toml` は変えない）。本体（`pipe_in/`）も変えない。
- **検証の画面の確認で見つかった見た目の直し。** ボタン `#run-go` を `position: sticky; bottom: 0` で節の下の端に留める（長いパスや依頼メモでスクロールしても隠れない）。右の欄が図の下に回る狭い幅（`@media (max-width: 1000px)`）では、読み込みのとき1回だけ節を畳んで始める（`matchMedia` の幅は CSS と同じ数で、テストが食い違いを見つける）。節の中の部品の間に 6px のすき間を入れる。`<details>` 自体は grid/flex にしない。検証 2 回目の直し：理由と文字数を欄のすぐ下に出し（`order`）、ボタンを幅いっぱいの不透明な帯にした（無効は透かさず色で示す）。
- **設計で足した小さな判断。** 設定の絶対パスに通常のファイルが無いときも、`resolveExecutable` が理由（「`pipe-in.command` のファイルがありません：<path>」）を返して流さない（足さないと、無いファイルを起こして空の端末と空の実行パネルが残る）。
- **テストを変えたこと（理由つき）。** 設定の鍵が5つから6つになるので、鍵の一覧・件数を固定している既存のテスト4件（`vscode/src/manifest.test.ts` の3件と `vscode/src/exampleEntry.test.ts` の1件）を書き換えた。`tests/test_rename.py` の古い名前が出てよいファイルの表に、前の版の置き場所でも流せることなどを確かめる4つのテストを足した。承認したあとに直したテストは2つ。(1) `vscode/src/domain/runExecutable.test.ts` の PATH の空の項目の2行は、入力に `/bin` が無いのに期待に入っていて、どんな実装でも通らなかったので、入力を直した（期待と検査の意味は変えていない）。(2) `tests/test_run_docs.py` の README の一文の期待は、かぎかっこを『流す』から「流す」に直した（ほかの文に合わせた）。検証は3回流した。1回目と2回目は、自動のテストは通ったが、画面の確認で見た目の不具合が見つかり、テストで捕まえてから直した（`vscode/src/webview/pipeEditorRunLayout.test.ts`）。
- **人の確認。** 要件メモが広かったので、範囲（ロードマップの段階3を順に。まず #21）・commit と push と下書きの PR・止まらずに進めることを、始めに人に聞いて決めた。要件定義と設計の決めきれない点（起こし方・実行ファイルを絶対パスに決めること・信頼の宣言を `false` にすること・実行中の記録を作業台を閉じても外さないこと・節を畳める形にすること・見える順）は、メインが推しで決めた。人の確認は PR で。
- **監査で直したもの。** 監査は 12 件で、どれも文書・定義・コメントの食い違いだった。`CLAUDE.md` の拡張の決まりに例外を足し、`/pipe-help` と `.claude/skills/pipe-in/screen-check.md` に「流す」を足した。`start-without-commands.md` に、作業台から流した実行の確認は端末で答えることを書いた。選んだ実行を覚える場面に「作業台から流したとき」を足した。英語版の用語を request memo にそろえ、実機でまだ確かめていない動きに「まだ」と書き、`pipe-in.command` の「引数つきは断る」を実物に合う言い方に直した。テストのコメントと、この記録の支えのテストの欄も直した。助言と審査は流していない（変えたファイルに `.claude/`・`plugin/`・`runner.py`・`guard.py`・`guard_hook.py` が無かったため。`.claude/` の2つのスキルの文は、監査のあとに足した）。
- **受け入れたリスク。**
  - 窓の読み込み直しで実行中の記録が消え、実行が続いていても同じパイプをもう一度流せる（端末で手で打つのと同じ）。
  - Windows の引数の包み方（引用符・改行）は実機で確かめるまで「まだ」。依頼メモは使う人自身が書くもので、パスは使う人が開いたフォルダのもの。
  - 作業台に「外で書き換わった」帯が出ているあいだは、保存済みの形とディスクの中身が食い違う。流すのはディスクの中身で、検査は保存済みの形（端末で手で打つのと同じとして、判断に足さない）。
  - `pipeline.toml` の `work_dir` と設定 `pipe-in.workDir` が違うと、流した実行が実行パネルに出ない（端末で流すときと同じ。設定を合わせる）。
  - リモート（SSH・WSL・コンテナ）での `machine` の設定の入り方は、実機でまだ確かめていない。

## 対象外・残った課題

- パネルから承認・修正・中止を答えること（#19・#20。次の機能）。承認は端末で入力する。
- `--after`・`--from`・`--yes`・`--pause`・`--review`・`--config`・`--name`・`--max-retries`・`--test-cmd`・`--input` などの旗を作業台から付けること。
- 開発フロー（`--pipe` を省く流れ）を作業台から流すこと。
- 保存していない変更を流す前に自動で保存すること、流した実行を作業台から止めること。
- `pipe-in.command` に引数つき（`python -m pipe_in`）を書くこと。
- 実機の確かめ（AC-52〜57）。確かめる点：(1) 型 `pipe-in` を登録しないまま `executeTask` が動くか。(2) 端末で答えを入力できるか（動かなければ設計の前提が崩れる）。(3) 実行パネルを開いたあと、焦点が端末とパネルのどちらにあるか（パネルが取るなら、端末へ戻す手を足すか決める）。(4) 端末を閉じたとき `onDidEndTask` が来るか。(5) macOS で Dock から起動した VSCode の `PATH` がシェルの `PATH` と違って `pipe-in` が見つからないことがあるか。(6) Windows の引数の包み方。(7) リモートでの `machine` の設定の入り方。

## 確かめたこと

- 本体：`python -m pytest -q` で 13,445 件が通る（3 件は skip）。監査の直しと、この記録を足したあとに流し直した。足したのは `tests/test_run_command.py`・`tests/test_run_docs.py` と共通の表 `tests/fixtures/run_command.json`。
- 拡張：`npm --prefix vscode test` で 6,394 件が通る。`npm --prefix vscode run typecheck`・`build` も通る。足したテストは 15 ファイル（ドメイン 4・アプリ 3・基盤 1・画面 2・パネル 2・入口と宣言と構造 3）。
- 画面：確認用ページ `pipe-editor-dark.html`・`pipe-editor-light.html` を、幅 1280×800 と 800×700 で開いて確かめた。`window.__previewRun` で状態を送り、AC-39〜51 の動き（空・書いて押す・`optional`・`none`・保存していない変更・検査の誤り・保存前・4,000 文字超・`<script>`・実行中・信頼なし・実行ファイルなし）と、配置（広い幅ではスクロールが出ない・理由が欄のすぐ下・ボタンが下の端に幅いっぱいで留まり重ならない・狭い幅では畳んで始まる・長いパスでも横にはみ出さない）の 52 項目が合い、コンソールのエラーは 0 件だった。
- 守りの範囲：`pipe_in/`・`generator/`・`plugin/`・`.claude/hooks/`・`.claude/agents/`・`.claude/settings.json` に差分が無いこと、依存（`pyproject.toml`・`vscode/package.json` の `dependencies`・`devDependencies`・`package-lock.json`）が増えていないことを `git diff` で確かめた。
- 実機（VSCode の実物・Windows・リモート）：まだ（AC-52〜57。上の「対象外・残った課題」の確かめる点 7 つ）。作業に使った場所では、実物の VSCode を動かせなかった。
