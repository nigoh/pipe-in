# D0049 実行の詳細に、使ったエージェント・スキル・道具の表を出す

## 目的

実行パネルの詳細に「エージェント・スキル」のタブを足し、選んだ実行で、どのエージェント（サブエージェント）・スキル・道具が、何回、どの段で使われたかを表で見られるようにする。イシュー #46（親は #4 のロードマップ段階1「見る」）。D0019 の「対象外」にあった「エージェント・スキルの表（#46）」を、この機能が扱う。

拡張が段のログ（`logs/*.jsonl`）を数えるだけで、本体（`pipe_in/`）・記録の形・依存・メッセージ・CSP は変えない。

## 機能要件と受け入れ基準

拡張のテストは `vscode/src/` の node:test、文書のテストは `tests/test_tools_tab_docs.py`。どのテストも名前（Python は docstring）の頭が `D0049-AC-xx:`。画面は確認用ページ（`run-panel-tools-light`・`-dark`）を Playwright で開いて確かめた。

#### 数える元と範囲
- FR-01 数える元は、選んだ実行の段のログの道具の呼び出し。新しく読む場所は増やさない
  - D0049-AC-01 数える呼び出しの判定を出力と共有する（tests/test_tools_tab_docs.py・vscode/src/domain/stageLogToolCalls.test.ts）
  - D0049-AC-02 数と出力の道具の行が同じ（vscode/src/domain/pipelineViewTools.test.ts・vscode/src/domain/stageLogToolCalls.test.ts）
  - D0049-AC-03 読むファイル・口を増やさない（vscode/src/app/refreshViewTools.test.ts）
  - D0049-AC-04 別の worktree・archive も同じ表（vscode/src/app/refreshViewTools.test.ts）
#### 種類と名前
- FR-02 呼び出しを、エージェント・スキル・道具の 3 つの種類に分け、名前を付ける
  - D0049-AC-05 エージェント・スキル・道具の見分け（vscode/src/domain/pipelineViewTools.test.ts・vscode/src/domain/stageLogToolCalls.test.ts）
  - D0049-AC-06 名前の決まりと読めない名前（vscode/src/domain/toolsTable.test.ts）
  - D0049-AC-07 同じ種類・名前は 1 行（vscode/src/domain/toolsTable.test.ts）
#### 入力の中身は出さない
- FR-03 呼び出しの入力のうち、表に使うのは名前だけ
  - D0049-AC-08 入力の中身は出さない（vscode/src/domain/pipelineViewTools.test.ts・vscode/src/domain/stageLogToolCalls.test.ts）
#### サブエージェントの中の呼び出し
- FR-04 サブエージェントの中の呼び出しも数える
  - D0049-AC-09 parent_tool_use_id は数え方に使わない（vscode/src/domain/pipelineViewTools.test.ts・vscode/src/domain/stageLogToolCalls.test.ts・vscode/src/domain/toolsTable.test.ts）
  - D0049-AC-10 サブエージェントの中も数える（vscode/src/domain/pipelineViewTools.test.ts）
#### 回数
- FR-05 各行に回数を出す
  - D0049-AC-11 回数は呼んだ数（vscode/src/domain/pipelineViewTools.test.ts・vscode/src/domain/stageLogToolCalls.test.ts）
#### 使った段
- FR-06 各行に、使った段を出す
  - D0049-AC-12 使った段（3 つまで・title）（vscode/src/domain/pipelineViewTools.test.ts・vscode/src/domain/toolsTable.test.ts・vscode/src/view/toolsHtml.test.ts）
  - D0049-AC-13 段の表示名は時系列と同じ元（vscode/src/domain/pipelineViewTools.test.ts・vscode/src/domain/toolsTable.test.ts）
#### 時間
- FR-07 時間は、記録に正しい値がある行だけ出す
  - D0049-AC-14 道具ごとの時間は出さない（vscode/src/domain/pipelineViewTools.test.ts・vscode/src/domain/stageLogToolCalls.test.ts・vscode/src/domain/toolsTable.test.ts・vscode/src/view/toolsHtml.test.ts）
  - D0049-AC-15 受け持ちの行の時間（vscode/src/domain/toolsTable.test.ts・vscode/src/view/toolsHtml.test.ts）
  - D0049-AC-16 時間の列は有るときだけ（vscode/src/domain/pipelineViewTools.test.ts・vscode/src/domain/toolsTable.test.ts・vscode/src/view/toolsHtml.test.ts）
#### 段の受け持ち
- FR-08 `/pipe-in` の記録の段の受け持ち（`agent`）を、エージェントの行として出す
  - D0049-AC-17 受け持ちをエージェントの行に（vscode/src/domain/pipelineViewTools.test.ts・vscode/src/domain/toolsTable.test.ts）
  - D0049-AC-18 同じ段の実行は 1 回だけ（vscode/src/domain/toolsTable.test.ts）
  - D0049-AC-19 受け持ちと subagent_type が同じ名前なら 1 行（vscode/src/domain/toolsTable.test.ts）
#### `/pipe-in` の記録の案内
- FR-09 `/pipe-in` の記録には、呼び出しが残らないことを案内で伝える
  - D0049-AC-20 driver の有無（vscode/src/domain/runRecordDriver.test.ts）
  - D0049-AC-21 案内 A（vscode/src/domain/pipelineViewTools.test.ts・vscode/src/domain/toolsTable.test.ts・vscode/src/view/toolsHtml.test.ts）
  - D0049-AC-22 案内 B（vscode/src/domain/pipelineViewTools.test.ts・vscode/src/domain/toolsTable.test.ts・vscode/src/view/toolsHtml.test.ts）
#### 表
- FR-10 表の形・並び・上限・空のとき
  - D0049-AC-23 列・並び（vscode/src/domain/toolsTable.test.ts・vscode/src/view/toolsHtml.test.ts）
  - D0049-AC-24 要約（vscode/src/domain/toolsTable.test.ts・vscode/src/view/toolsHtml.test.ts）
  - D0049-AC-25 100 行の上限（vscode/src/domain/toolsTable.test.ts・vscode/src/view/toolsHtml.test.ts）
  - D0049-AC-26 空の文（vscode/src/domain/pipelineViewTools.test.ts・vscode/src/domain/toolsTable.test.ts・vscode/src/view/toolsHtml.test.ts）
  - D0049-AC-27 パネルと枠の属性（vscode/src/view/panelScriptTools.test.ts・vscode/src/view/shellHtmlTools.test.ts・vscode/src/view/toolsHtml.test.ts）
#### タブ
- FR-11 詳細のタブに「エージェント・スキル」を足す
  - D0049-AC-28 詳細のタブが 4 つ（vscode/src/view/shellHtml.test.ts・vscode/src/view/shellHtmlTools.test.ts）
  - D0049-AC-29 タブ・パネルの数や位置を固定したテストの直し（直した既存のテスト：vscode/src/view/shellHtml.test.ts・vscode/src/view/artifactsPanel.test.ts・vscode/src/view/panelScriptUi.test.ts・vscode/src/previewPagesArtifacts.test.ts。下の「既存のテストを変えた理由」）
  - D0049-AC-30 タブを押すと切り替わる（vscode/src/view/panelScriptTools.test.ts）
  - D0049-AC-31 描き直しをまたぐ保持（vscode/src/view/panelScriptTools.test.ts）
  - D0049-AC-32 図と出力・使用量の HTML は変わらない（vscode/src/view/shellHtmlTools.test.ts）
#### 動いている実行
- FR-12 描き直しのたびに、選んだ実行のログから作り直す
  - D0049-AC-33 同じ写しから同じ HTML（vscode/src/architecture.test.ts・vscode/src/domain/pipelineViewTools.test.ts・vscode/src/view/toolsHtml.test.ts）
  - D0049-AC-34 動いている実行は描き直しで増える（vscode/src/domain/pipelineViewTools.test.ts）
#### 外から来た文字・約束を増やさない
- FR-13 外から来た文字は `escapeHtml` を通す
  - D0049-AC-35 escapeHtml を 1 回だけ（vscode/src/domain/pipelineViewTools.test.ts・vscode/src/view/toolsHtml.test.ts）
  - D0049-AC-36 style・on…・src・href を増やさない（vscode/src/view/shellHtmlTools.test.ts・vscode/src/view/toolsHtml.test.ts）
- FR-14 拡張は読むだけで、メッセージ・設定・依存を増やさない
  - D0049-AC-37 メッセージ・設定・依存を増やさない（既存の vscode/src/manifest.test.ts・vscode/src/view/messages.test.ts・vscode/src/webview/csp.test.ts が変えずに通り、vscode/package.json・package-lock.json は変わらない）
  - D0049-AC-38 書かない・child_process なし・層を守る（vscode/src/architecture.test.ts）
#### 本体を変えない・一覧を重くしない
- FR-15 本体と記録の形は変えず、一覧の行の組み立てに表の計算を入れない
  - D0049-AC-39 本体・記録の形・守りを変えない（手で）確かめた：検証の段で、載せ直した main からの git diff --name-only と git status --short を合わせて見た。本体・generator/・plugin/・.claude/hooks/・.claude/agents/・infra/・extension.ts・webview/・package*.json・pyproject.toml は無変更。app/ に出るのはテストのファイル vscode/src/app/refreshViewTools.test.ts だけで、製品のコードは変えていない
  - D0049-AC-40 一覧の行の項目を増やさない（vscode/src/domain/runListTools.test.ts）
  - D0049-AC-41 一覧の行の組み立ては表を数えない（vscode/src/app/refreshViewTools.test.ts・vscode/src/architecture.test.ts・vscode/src/domain/pipelineViewTools.test.ts）
#### 古い形・壊れた値
- FR-16 古い記録・壊れた値でも、例外を出さない
  - D0049-AC-42 壊れた部品・行でも例外なし（vscode/src/domain/stageLogToolCalls.test.ts）
  - D0049-AC-43 古い記録・壊れた state.json でも読める（vscode/src/domain/pipelineViewTools.test.ts）
  - D0049-AC-44 __proto__ などの名前（vscode/src/domain/pipelineViewTools.test.ts・vscode/src/domain/toolsTable.test.ts・vscode/src/view/toolsHtml.test.ts）
  - D0049-AC-45 極端な入力（vscode/src/domain/pipelineViewTools.test.ts・vscode/src/domain/toolsTable.test.ts）
#### 確認用ページ
- FR-17 `npm run preview` で、タブを画面で確かめられるようにする
  - D0049-AC-46 確認用ページ（vscode/src/previewPagesArtifacts.test.ts・vscode/src/previewPagesTools.test.ts）
#### 文書
- FR-18 使う人向けの説明と、開発の文書をそろえる
  - D0049-AC-47 ガイド（tests/test_tools_tab_docs.py）
  - D0049-AC-48 拡張の README（tests/test_tools_tab_docs.py）
  - D0049-AC-49 設計の文書（tests/test_tools_tab_docs.py）
  - D0049-AC-50 確認用ページの持ち場（tests/test_tools_tab_docs.py）
  - D0049-AC-51 決定の記録の表（tests/test_tools_tab_docs.py）
#### 画面・手で・実機
- FR-19 確認用ページ・手・実機で確かめる（画面は Playwright で開いて確かめる）
  - D0049-AC-52 （画面）表と要約が見える（画面）確かめた：1280×800 で要約「125 種類・合計 190 回」、列見出し 名前・種類・回数・使った段、エージェント → スキル → 道具の順、「ほか N 件」と title
  - D0049-AC-53 （画面）外から来た文字が文字のまま（画面）確かめた：<script>・<img onerror>・"・& を含む名前が文字のまま。パネルに script・img・iframe 0、外への通信 0、コンソールのエラー 0
  - D0049-AC-54 （画面）100 行を超えると省略の文（画面）確かめた：行 100・「ほか 25 種類を省いています」
  - D0049-AC-55 （画面）/pipe-in の記録・案内・空の文（画面）確かめた：(b) 案内 A・受け持ちの行・時間の列、(c) 案内 B だけ、(d) 空の文だけ、(a) に戻すと時間の列なし。タブの選びは行を替えても残る
  - D0049-AC-56 （画面）描き直しのあとも位置と焦点が残る（画面）確かめた：縦（1280×800）の位置 120 と横（360×800）の位置と焦点が __previewNext() のあとも残り、別の実行で先頭に戻る。__posted は ready と selectRun だけ（横の位置は 40 を書いて 39 に丸められ、39 のまま残った）
  - D0049-AC-57 （画面）明暗で読める（画面）確かめた：明暗で見出しの背景が本文と違い、読める。1 回目は列見出し「回数」が 2 行に折れたので attempt 2 で直した（vscode/src/view/toolsHtml.test.ts の D0049-AC-57 のテスト）
  - D0049-AC-58 （画面）幅と高さで崩れない（画面）確かめた：幅 1280・1101・1100・1000・801・800・360 × 高さ 800・400 で横スクロール無し・タブが切れない・長い名前が折り返す。縦は 1101px 以上でパネル、801〜1100px で詳細の枠、800px 以下でページ全体
  - D0049-AC-59 （画面）既存のページが変わらない（画面）確かめた：run-panel-light・run-panel-running-dark・run-panel-artifacts-light・run-panel-runs-dark でタブ 4 つが 1 行、エラー 0、新しいタブに見本の記録の道具の表
  - D0049-AC-60 （手で）SDK を呼ばずに（手で）確かめた：一時フォルダの記録で start のあと案内 B、begin --agent のあいだ受け持ちの行（時間の列なし）、done のあと時間の列。見本の写しで Write 7・Bash 5・Edit 4・Read 4・Grep 1、行を足すと次の読み直しで増えた
  - D0049-AC-61 （実機）実際の SDK で数が合う（実機）確かめていない（利用料がかかるので、人に言われたときだけ。tests/test_tools_tab_docs.py は文書だけを見る）

## 決めたことと理由

### 人が決めたこと（要件定義と設計で聞いた点。どれも推しの案）

- **拡張だけを変える。** 本体・記録の形・テストの見本の形は変えない。表の数・使った段・受け持ちの時間は、今の記録だけで出せる。
- **時間は、受け持ちの行だけ。** 道具ごとの時刻はログに無い（時刻 `at` が付くのは各ログの `Prompt` の行だけ）。段の時間で代えると「Read に 4 分かかった」と誤って読めるので、代えない。`/pipe-in` の記録の受け持ち（`record begin --agent`）の行だけ、段の実行の長さの合計を `m:ss` で出し、時間のある行が無ければ列ごと出さない。
- **`/pipe-in` の記録は、受け持ちだけをエージェントの行にし、案内を出す。** `state.json` に `driver` がある記録には、呼び出しが残らないことの案内（行があれば A、無ければ B）を出す。段の名前から受け持ちを補わない（記録に無いものを出さない）。`SKILL.md` の手順の行に `--agent` を足すことは、この機能に入れない。
- **サブエージェントの中の呼び出しは同じ行に足し、内訳は出さない。入力の中身（コマンド・引数・プロンプト）は出さない**（読むのは `Agent`・`Task` の `subagent_type` と `Skill` の `skill` だけ。入力自身が持つ鍵だけを読む）。**時系列の行との行き来は入れない**（使った段を時系列と同じ「段の表示名 N 回目」の書き方にして、目で突き合わせられるようにした）。
- **入口は、既定で表を作り、一覧の行だけ止める。** `buildPipelineView(snapshot, clock, { tools })` は既定で表を作り、一覧の行の組み立て（`summarizeRun`）だけが `{ tools: false }` を渡す。`app/`・`extension.ts` を変えずに済む。パネルが閉じていてもステータスバーのために図の状態を作るので、表の計算も毎回走る（重さは AC-45 で上限を測った）。
- **AC-31 の「別のタブを見ていて隠れている状態でも焦点が残る」は、「そのとき焦点があった要素（別のタブのボタンなど）が、描き直しのあとも同じ要素に戻る」と読む。** 隠れた表の枠は、本物のブラウザでは焦点を持てない。枠の焦点は見えている間だけ残す。
- **既存のテストの直しは、承認した 4 ファイルに加えて 2 つ**（下の「既存のテストを変えた理由」）。`panelsOf` の重複も、テスト先行の段の確認のときに人が承認して import に替えた。
- **D0039-AC-11 の合計の上限を 17,800 字から 18,000 字に置き換える。** main に入った D0046（確認待ちの知らせ。上限を 17,500 字から 17,800 字に上げた）で、/pipe-in のスキルと補助ファイルの合計が 17,758 字になり、この機能で足す 3 か所（`screen-check.md` の確認用ページの 2 行と `record.md` の `begin` の行の追記。合わせて 228 字）が入らなかった。手順を削るより上限を上げると人が決め、`tests/test_skill_tidy.py` の上限を 18,000 字にした（そのときの合計は 17,986 字。あとから main に入った D0048 で `SKILL.md` が短くなり、main を取り込んだあとは 17,959 字）。D0039・D0046 の記録は書き換えない。
- **画面の確認で見つけた不具合（列見出し「回数」が 2 行に折れる）は、テスト先行と実装に戻して直した（attempt 2）。** `.tools-table th` に `white-space: nowrap` を足した。
- **main の作業途中のテスト（#79。イシュー #85）が落ちていたあいだは、それと一字違わず同じ失敗はベースの赤とする**と人が決めた（そのあと #84 で main が緑に戻ったので、最後の検証ではベースの赤は無い）。

### 聞かずに決めたこと

- タブの名前はイシューと D0019 の呼び名のとおり「エージェント・スキル」。位置は「成果物」と「使用量」の間（実行の中身を見るタブの次に、使われ方を見るタブを並べる。既存の「図と出力」「使用量」のパネルの HTML を変えずに D0025-AC-75 の SHA-256 の検査を通せる位置）。
- 種類は 3 つで、MCP の道具（`mcp__…`）は「道具」に入れる。名前の決まりは 3 つの種類で同じ（空でない・空白や制御文字を含まない・100 文字まで）。読めない値は「（読めない名前）」、鍵を省いた呼び出しは「（指定なし）」。
- 数える範囲と部品の判定は、出力の道具の行と同じ（1 つのログの最後の `Prompt` より後ろ。`parseStageLog` の 1 つの判定 `partOf` から出力の行と `calls` の両方を出す）。
- 結果の成否は見ない（呼んだ回数）。行は 100 まで、使った段は 3 つまで（`title` は 200 文字まで）。並びは種類 → 回数の多い順 → 名前のコードポイントの順 → 読める・指定なし・読めないの順。
- 段の表示名と受け持ちの決め方は、時系列と同じ関数を使う（`gantt.ts` の `labelOf`・`firstLogBySeq`・`ownerOf` を共有）。共有するときに、`labelOf` を `Object.hasOwn` で引く形に直した（段の名前が `constructor` のような記録で、表示名の代わりに関数が入る穴が時系列にもあった）。
- 時間の列を出すかは、表に出す先頭 100 行で決める（01 の AC-16 の文言から少し狭めた読み）。縦のスクロールの場所は、実物の CSS に合わせて 1101px 以上はパネル・801〜1100px は詳細の枠・800px 以下はページ全体と読んだ（01 の AC-58 は「1100px 以下は詳細の枠」と書いていた）。AC-45 の伸びの比は、揺れを避けるため、表を作る部品だけを測る形にした（テスト先行の読み手が、全体の時間の比が 30 回に 1 回ほど揺れることを見つけた）。
- 番号は D0040 → D0042 → D0043 → D0044 → D0046 → D0047 → D0049 と振り直した（作業のあいだに main に D0040〜D0048 が入った。D0045 はプラグインの eval、D0046 は確認待ちの知らせ、D0047 は仕様書レビューのひな形、D0048 は worktree を自動で切る仕組み。PR を立てたあとに D0047・D0048 が先に入ったので、main を取り込んで付け替えた）。

### 既存のテストを変えた理由

タブが 3 つから 4 つになったので、タブ・パネルの数や位置を固定した既存のテストを、意味を変えずに件数と位置だけ直した（D0025 と同じ扱い）。

- `vscode/src/view/shellHtml.test.ts`：D0019-AC-62 のタブ 3 つの並びの 2 件を、タブ 4 つの D0049-AC-28 に置き換える。パネルを番号で取る補助を、`data-detail-panel` の値で取る形（`vscode/src/test/panelParts.ts`）に替えた。
- `vscode/src/view/artifactsPanel.test.ts`：D0025-AC-70 の隠れているパネルの配列を 3 つから 4 つにした。パネルを取る補助は同じく `panelParts.ts` から。
- `vscode/src/view/panelScriptUi.test.ts`：見えているパネルを番号でなく名前で見る形にした（使用量は 2 番目から 3 番目へ）。
- `vscode/src/previewPagesArtifacts.test.ts`：D0025-AC-73 の「`PANEL_PAGES` の 13 件目以降は成果物の 2 件だけ」を、成果物の 2 件とエージェント・スキルの 2 件に置き換える。文字を読む補助を `vscode/src/test/previewText.ts` へ中身を変えずに移し、新しいテストと共有した。
- `vscode/src/architecture.test.ts`：新しい部品の構造の検査を足しただけ（既存の検査は変えていない）。
- `tests/test_skill_tidy.py`：上の D0039-AC-11 の上限（17,800 → 18,000 字）と、そのテストの名前・説明の文だけ。

### 受け入れたリスク

1. **呼んだ回数で、動いた回数ではない。** 本体の守りに止められた呼び出しや失敗した呼び出しも数えるので、`Agent` の回数が上限（`max_agent_calls`）より多く出ることがある。`id` で重複を除かないので、同じ呼び出しがログに重ねて出る記録は二重に数える（出力の道具の行と数を合わせるため）。
2. **動いている SDK の段は、数が少し遅れて増える。** SDK の段のログは、バッファが溢れるまでファイルに出ない（D0021）。
3. **入力の鍵の名前は、実物のログでは確かめていない**（AC-61）。`Agent` の `subagent_type` は公式の文書（SDK の `AgentInput`）で、`Skill` の `skill` は同梱の CLI と Claude Code の `Skill` の道具の定義で確かめた。`subagent_type` を省いた呼び出しは正当に「（指定なし）」になるので、鍵の名前の違いは表からは気づけない。
4. **表の計算は、パネルが閉じていても描き直しのたびに走る**（ステータスバーと同じ図の状態を使うため）。呼び出し 10 万回・名前 1 万種類でも 5000ms 未満で終わることを AC-45 で確かめた。

### 確かめていないこと

- 実機（AC-61）：実際の SDK のログで、`Agent` の `subagent_type`・`Skill` の `skill`・入れ子の `parent_tool_use_id`・`TaskNotificationMessage` の形と数。
- 公式の文書に `Skill` の入力の型が無い（tools-reference・hooks・SDK の文書を見た）。

## 対象外・残った課題

- 道具・スキルごとの時間。材料（検証のあとの助言 V-01・V-02・V-05・V-07）：SDK の文書では、`Agent` の結果に `totalDurationMs` と `agentType` があり、`TaskStarted`・`TaskProgress`・`TaskNotification` は裏で動く作業の知らせ（pipe-in は裏を切っているので出ないかもしれない）、フックの PostToolUse に `duration_ms` がある。`subagent_type` に明示の null が来るかも未確認。どれも AC-61 の実機で確かめてから、別のイシューで決める。
- `TaskCreate` などの道具（名前が `Task` に似ているが別の道具）が「道具」になることを見るテスト（助言 V-08）。今の一致の仕方は正しく、前方一致への改悪を防ぐためのもの。
- README とガイドの画像（`run-panel-*.png`・`run-list-*.png`・`run-list.gif`）は撮り直していない。タブは 3 つのまま写っている（監査 A-03。人が望めば別に撮る）。
- `stageLabels[stage] ?? stage` の形でプロトタイプの鍵も引く穴が、`shellHtml.ts`・`runList.ts`・`statusBar.ts` にも残っている（`gantt.ts` の `labelOf` だけ直した）。
- `/pipe-in` の記録に、スキル・道具の呼び出しを残すこと。段の名前から受け持ちを補うこと。`SKILL.md` の手順の行に `--agent` を足すこと。時系列の行との行き来。内訳（どのエージェントの中か）。並べ替え・絞り込み。一覧・ステータスバーへの数。
- main の作業途中のテストと D0039 の番号の重なり（イシュー #85。#84 で main は緑に戻った）。

## 確かめたこと

- 検証（2 回目で合格）：
  - 拡張：`npm --prefix vscode test` は 4834 件すべて通り、型検査とビルドも通る。
  - Python：`pytest -q -p no:cacheprovider` の失敗は、この記録の本体を待つ 13 件だけだった（この記録を書いて 0 件）。main（`5d258f1`）のベースは失敗 0。
  - 1 回目は、画面の確認で列見出しの折れを見つけて不合格にした。
  - main（`91ad7f8`。D0045・D0046 が入った）に載せ直したあと：拡張の 4913 件と Python の 11510 件（飛ばす 6 件を除く）がすべて通り、型検査とビルドも通る。
  - main（`51c2346`。D0047・D0048 が入った）を取り込み、番号を D0049 に付け替えたあと：拡張の 4913 件と Python の 11583 件（飛ばす 6 件を除く）がすべて通り、型検査とビルドも通る。
- 画面（AC-52〜59）と手で（AC-60）は、上の AC の行のとおり。
- 公開してよいか：変えたファイルに、秘密・ユーザー名の入った絶対パス・メールアドレス・`docs/pipeline/` の中身は無い。
- 文書係（検証のあと）：`docs/guide/vscode.md`（並び・`m:ss`・時間の列が出る条件）・`vscode/README.md`（タブの節）・`docs/guide/usage.md`（`--agent`・`driver`）・`docs/guide/records.md`（`agent`）を直した。案にした `/pipe-help` の一覧の行と `record.md` の `--agent` の行は、人が承認してメインが直した。
- 矛盾監査（11 件）：人が承認して、A-01（この記録に D0039-AC-11 の置き換えを書いた）・A-02（テストの説明の件数）・A-04（design.md の言い方）・A-05（コメントの列挙）・A-06（テストの説明）・A-07（ガイドの「制御文字」）・A-08（番号を飛ばした理由）・A-09（AC の行のテストの名前）・A-10（records.md の「最後の Prompt の行」）・A-11（duration.ts のコメント）を直した。A-03（画像）は撮り直さず、上の「対象外・残った課題」に書いた。
- 公式の文書と照らした助言（8 件。重さ「高」は無し）：人が承認して、V-03（「（指定なし）」は `general-purpose` に当たる・`fork`）と V-04（スキルが始めたサブエージェントの中も同じ行）をガイドに、V-06（Python の SDK の形だけを読む）を `stageLog.ts` のコメントに書いた。V-01・02・05・07・08 は上の「対象外・残った課題」に書いた。
- 審査（助言の報告の採点）：overall 0.9・verdict pass（事実の正確さ 1.0・引用の正確さ 1.0・網羅性 0.75・情報源の質 1.0・道具の効率 0.75）。網羅性が下がったのは、`Skill` の入力の鍵が公式の文書で確かめられなかったため。
