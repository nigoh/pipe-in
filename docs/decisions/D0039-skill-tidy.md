# D0039 /pipe-in のスキルを、長い会話でも決まりが残る形に整える

## 目的

/pipe-in のスキル（`.claude/skills/pipe-in/SKILL.md`）を、長い会話で自動の要約がされても、大事な決まりが残る形に整える。スキルの内容は呼び出したときに会話に入り、自動の要約のあとは、直近の呼び出しの先頭 5,000 トークンだけが戻る（スキル全部で 25,000 トークンまで。公式の文書。日本語 1 字のトークン数は確かめていない）。イシュー #48（親イシュー #3。`docs/roadmap.md` の段階0「足場」）。#43（D0021）・#52（D0032）の助言で「#48 で」とした項目も見た。

- 必ず守る決まり（承認されるまで次の段に進まない・`--auto` は引数に書いたときだけ・コミットと push は言われるまでしない・あやふやなら読み直す）を、SKILL.md の冒頭の「必ず守ること」に置く。
- 長い手順（記録のコマンドの表・`--artifact` の手順・画面の確認の手順）を、同じフォルダの補助ファイル `record.md`・`artifact.md`・`screen-check.md` に分ける。SKILL.md は 15,333 字から約 1.2 万字になる。
- 確認用ページの一覧の持ち場を `docs/assets/README.md` の 1 か所にする。
- 前の名前の残り（スキルと定義の 5 つ）と、報告の言い方（D0032 の助言 V-07）を直す。
- `.claude/settings.json` の許可の規則を、実際に使う形に合わせる（`ask` に 2 つ、`allow` に完全一致の 5 つ）。

## 機能要件と受け入れ基準

`.claude/` のスキル・定義・設定と、テストと文書だけを変える。本体（`pipe_in/`）・ジェネレーター・プラグイン・拡張・`.claude/hooks/`・記録と設定の形は変えない。テストは `tests/test_skill_tidy.py`（定義・設定）・`tests/test_skill_tidy_docs.py`（文書・決定の記録）・`tests/test_pipe_in_guard.py` の末尾（`test_d0039_ac28_…`。フックの判断の総当たり）。どのテストも docstring の頭が `D0039-AC-xx:`。

#### 冒頭の決まり
- FR-01 SKILL.md の冒頭に「必ず守ること」の節を置き、決まりの本文はそこ 1 か所にする
  - D0039-AC-01 `# /pipe-in` の次の `## ` の見出しが「必ず守ること」、その次が「0. 始める前に」。`$ARGUMENTS` は「0. 始める前に」の中。（tests/test_skill_tidy.py）
  - D0039-AC-02 節に 4 つの決まり（承認・`--auto` と止まる場面・コミットと push・読み直し）。（tests/test_skill_tidy.py）
  - D0039-AC-03 節の本文は 800 字以内、先頭から節の終わりまでは 1,600 字以内。（tests/test_skill_tidy.py）
  - D0039-AC-04 承認の決まりの本文は冒頭の節に 1 か所だけ。（tests/test_skill_tidy.py）
#### 補助ファイル
- FR-02 長い手順を補助ファイル 3 つに分け、SKILL.md から読む合図を出す
  - D0039-AC-05 補助ファイルは `record.md`・`artifact.md`・`screen-check.md` の 3 つだけで、「0. 始める前に」が指す。（tests/test_skill_tidy.py）
  - D0039-AC-06 `record.md` に記録のコマンド 8 つと旗。SKILL.md の手順の 3 か所が旗を `record.md` で指す。（tests/test_skill_tidy.py）
  - D0039-AC-07 `artifact.md` に `--artifact` の手順。SKILL.md の節は 400 字以内で、写しの更新を続けることを書く。（tests/test_skill_tidy.py）
  - D0039-AC-08 `screen-check.md` に画面の確認の手順 1〜6。（tests/test_skill_tidy.py）
  - D0039-AC-09 `${CLAUDE_SESSION_ID}` と `$ARGUMENTS` は SKILL.md にだけ書く。（tests/test_skill_tidy.py）
  - D0039-AC-10 補助ファイルが読めないときは止まり、載せ直しを案内する（1 行）。（tests/test_skill_tidy.py）
  - D0039-AC-11 SKILL.md は 12,300 字以下、補助ファイルとの合計は 17,500 字以下（初めは 17,100 字。下の「決めたことと理由」）。（tests/test_skill_tidy.py）
  - D0039-AC-12 既存の検査が見ている語句は SKILL.md に残る。（tests/test_skill_tidy.py・既存の tests/test_readme.py・tests/test_guide.py）
  - D0039-AC-13 移す前のバッククォートの語は、SKILL.md と補助ファイルのどこかに同じ文字で残る（6 字以下の語は囲んだ形で）。（tests/test_skill_tidy.py）
  - D0039-AC-14 見出しの並びは、移す前の並びの 2 番目に「必ず守ること」が入るだけ。（tests/test_skill_tidy.py）
#### ページの一覧の持ち場
- FR-03 確認用ページの一覧の持ち場を `docs/assets/README.md` の 1 か所にする
  - D0039-AC-15 `docs/assets/README.md` に全部のページの種類の頭と作業台の 3 ページ。（tests/test_skill_tidy_docs.py）
  - D0039-AC-16 CLAUDE.md と `design.md` の行は、完全なページ名を並べない。（tests/test_skill_tidy_docs.py・tests/test_guide.py）
  - D0039-AC-17 `screen-check.md` は完全なページ名を並べず、種類の頭を全部書き、一覧を指す。（tests/test_skill_tidy_docs.py・tests/test_readme.py）
  - D0039-AC-18 読む先が移る既存の検査（D0025-AC-77・D0025-AC-78・D0009-AC-19）を置き換える。（tests/test_readme.py・tests/test_guide.py）
#### 前の名前の残り
- FR-04 スキルと定義から前の名前（devpipe）の残りを直す
  - D0039-AC-19 SKILL.md と定義 8 つと補助ファイルに前の名前が無く、`tests/test_rename.py` の許す一覧から 5 行を外す。（tests/test_skill_tidy.py・tests/test_rename.py）
  - D0039-AC-20 直した文は、旧い語が無く新しい語がある組で見る。（tests/test_skill_tidy.py）
  - D0039-AC-21 前の名前で作られたもの（記録・設定・置き場所・コマンドの別名）は今までどおり読め、動く。（既存の tests/test_record.py・tests/test_rename.py）
#### 報告の言い方
- FR-05 読むだけの係の定義の「報告の返し方」を直す
  - D0039-AC-22 auditor・advisor・judge の行が「最後の返答の文が親に渡る」「SubagentHandback が渡されるのは auto モードのときだけ」。（tests/test_skill_tidy.py）
#### フックで守るか
- FR-06 決まりをフックで守らない。新しいフックを足さない
  - D0039-AC-23 `.claude/hooks/` は 2 つのまま、定義の前置きに `hooks:` が無い、settings.json の `hooks` は今のまま。（tests/test_skill_tidy.py）
  - D0039-AC-24 フックで守らないと決めた理由と、代わりの手立てを記録に書く。（tests/test_skill_tidy_docs.py）
#### 許可の規則
- FR-07 `ask` と `allow` を、実際に使う形に合わせる。止める範囲は変えない
  - D0039-AC-25 `ask` に `git commit`・`git merge` が加わる。（tests/test_skill_tidy.py）
  - D0039-AC-26（実機）個人の `allow` より `ask` が先に効くか：公式の文書にはある（規則は deny → ask → allow の順で、個人の `allow` は共有の `ask` より上にならない）。実機ではまだ（確かめていない。利用料がかかるので、人に言われたときだけ）。
  - D0039-AC-27 `allow` の Bash は既存の 9 つと完全一致の 5 つ。（tests/test_skill_tidy.py）
  - D0039-AC-28 フックの判断は変わらない（5 つのコマンド × 9 つの pipe-in-* と、フックが見ない呼び出し元、`main()` 経由）。（tests/test_pipe_in_guard.py の test_d0039_ac28_…）
  - D0039-AC-29 規則を広げすぎない（広い規則・Bash でない規則を足さない。deny は 12 行のまま）。（tests/test_skill_tidy.py）
  - D0039-AC-30（実機）新しい worktree で `allow` が効くか：公式の文書では、その枝の `.claude/settings.json` が読まれ、共有の `allow` は信頼のあとに効き、信頼は main の作業フォルダの場所で見る。実機ではまだ（確かめていない）。規則は入れたままにする。
  - D0039-AC-31（実機）フックの deny が `allow` より先に効くか：公式の文書にはある（終了コード 2 のフックは許可の規則より先に止め、JSON の deny も同じ道を通る）。実機ではまだ（確かめていない）。
  - D0039-AC-32 足した理由と受け入れたリスクを記録に書く。（tests/test_skill_tidy_docs.py）
#### 文書
- FR-08 文書をそろえる
  - D0039-AC-33 `docs/guide/develop.md` に、スキルの構成と許可の規則。（tests/test_skill_tidy_docs.py）
  - D0039-AC-34 `docs/development/workflow.md` に、スキルの構成と `ask`。（tests/test_skill_tidy_docs.py）
  - D0039-AC-35 `docs/development/design.md` のスキルの行に補助ファイルのパス。（tests/test_skill_tidy_docs.py）
  - D0039-AC-36 CLAUDE.md の `npm run preview` の行・`/pipe-in` の段落・コミットの行。（tests/test_skill_tidy_docs.py）
  - D0039-AC-37 `docs/assets/README.md` の一覧の表の行に、画像に撮るか。（tests/test_skill_tidy_docs.py）
#### 決定の記録
- FR-09 この記録を書き、表に載せる
  - D0039-AC-38 この記録があり、表に番号の順で載り、AC の行にテストか結果がある。（tests/test_skill_tidy_docs.py）
#### 手で・実機
- FR-10 テストで見られないことを、手で・実機で確かめる
  - D0039-AC-39（手で・コミットの前）別のイシューにした項目を、イシューに立てるか：確かめた（コミットの前に人に聞き、1 つにまとめて #71 に立てた）。
  - D0039-AC-40（手で・検証の段）変えたファイルが決めた範囲だけか：確かめた（検証の段で 26 のパスが設計の一覧どおりで、`pipe_in/`・`generator/`・`vscode/`・`plugin/`・`.claude/hooks/` は変えていない。そのあと文書係の `docs/development/README.md` と、承認した直しの `.claude/skills/pipe-help/SKILL.md` が増えた）。
  - D0039-AC-41（手で・検証の段）`screen-check.md` の手順を 1 回なぞる：確かめた（手順 1・2・6 は書いたとおりに 1 つずつ流し、17 ページが `docs/assets/README.md` の表と一致した。この会話には Playwright の MCP が無かったので、3・5 は入っている Playwright のライブラリで 5 ページを 8 つの大きさで開き、コンソールのエラー 0・横のスクロール無し）。
  - D0039-AC-42（実機）長い要件メモと `/compact` のあとに、冒頭の決まりが残るか：まだ（確かめていない。利用料がかかるので、人に言われたときだけ）。

## 決めたことと理由

### 人が決めたこと（要件定義と設計で聞いた点。どれも推しの案）

- **範囲は案 B。** 冒頭の決まり・補助ファイル 3 つ・ページの一覧の持ち場・前の名前・報告の言い方と、settings.json の `ask` 2 つ・`allow` の完全一致 5 つ。
- **長い部分は 3 つのファイルに分ける**（`record.md`・`artifact.md`・`screen-check.md`）。検証のあとの手順（文書係・監査・助言・仕上げ）は分けない。補助ファイルは、リポジトリからの相対パスで指す。
- **確認用ページの一覧の持ち場は `docs/assets/README.md`。** CLAUDE.md・`design.md`・`screen-check.md` は、完全なページ名を並べずに、ここを指す。
- **決まりはフックで守らない。** 承認や「言われた」は会話の中にあり、フックに渡る入力（道具の名前と引数）からは見分けられない。フックで止めると、人に言われたあとの正しいコミットまで止まり、`--auto` とも両立しない。スキルの前置きの `hooks:` でも同じで、しかも呼んだあと会話の終わりまで動き続ける（公式の文書）。公式の文書は「毎回守る決まりはフックへ」と勧めるが、承認は会話の中にあるので当てはまらない。代わりの手立てとして、`git commit`・`git merge` を `ask` に足した（公式の文書では、個人の許可があっても確認が出る。実機では確かめていない）。記録の順序（承認の前に次の段の `begin` が書かれていないか）を検査する案は、別のイシューにした。
- **`allow` に完全一致の 5 つを足す**（`npm --prefix vscode test`・`npm --prefix vscode run typecheck`・`npm --prefix vscode run build`・`npm --prefix vscode run preview`・`python -m http.server 8765 --bind 127.0.0.1 --directory vscode/out/preview`）。スキル・検証役・フックが使う形はこれで、今の `Bash(npm test:*)` などには当たらず、毎回確認が出ていた。確認を機械的に押すくせがつくと、本当に危ない確認を見落とす。スキルの前置きの `allowed-tools` は次の人のメッセージで切れる（公式の文書）ので、段ごとに人が返事する /pipe-in には足りず、settings.json に置いた。フックが見ない呼び出し元（メイン・pipe-in-* 以外のサブエージェント）でも確認が出なくなることは、人が受け入れた（下の受け入れたリスク）。
- **`record:*` のような幅広い規則は足さない。** `record start` は `--input` で任意のファイルを読め、`--project` で別のフォルダに書け、前の記録を `archive/` へ移す。`begin` は確認待ちの印を消す。個人で許したいときは `.claude/settings.local.json` に書く（`.gitignore` 済み）。
- **字数が収まらないときは、合計の上限を 17,500 字に上げてよい**（設計の段で人が決めた）。実装では SKILL.md が約 11,700 字、合計も 17,100 字以内に収まった。検証のあとの監査と助言で人が承認した直し（A-01・V-01・V-02・V-09 など）で合計が 17,100 字を超えたので、足した文を短くしたうえで、上限を 17,500 字に上げた（`tests/test_skill_tidy.py` の AC-11。SKILL.md は約 11,900 字、合計は約 17,200 字）。
- **ベースの赤**：main（851c1e3）では、`tests/test_rules.py::test_ac_ids_in_tests_exist_in_records` が、#65・#67 の D0033 の ID 8 つ（`tests/test_guide.py` の AC-08 と `tests/test_sdk_buffer.py` の AC-01〜07）に記録が無いため落ちている。合格の基準は「D0033 の件と一字違わず同じ失敗のほかは通る」にした。D0033 以外が混じったら止めて知らせる、と決めた（混じらなかった）。
- **既存のテストの書き換え（5 か所）を認める**：読む先が `docs/assets/README.md` と `screen-check.md` に移るため。`test_D0025_AC_77_…` は中身が 1 語になるが、名前は変えない（承認した 5 か所の外に広げないため）。AC-13 の 6 字以下の語は、バッククォートで囲んだ形で探す（`reset` の中の `set` で満たされないように）。

### 置き換える AC

D0039-AC-18 で、次の既存の検査を置き換える（前の記録は書き換えない）：D0025-AC-77（design.md の行の 3 語を 1 語に）・D0025-AC-78（CLAUDE.md と SKILL.md の列挙の 2 つを削る。代わりに D0039-AC-17 が `screen-check.md` に全部の種類の頭が載ることを見る）・D0009-AC-19（SKILL.md の `run-panel-light/dark` の部分を外す）。D0027-AC-76（SKILL.md の `--artifact` の節の中身）は、手順が `artifact.md` に移るので、D0039-AC-07 で読み替える。

### 聞かずに決めたこと

- 冒頭の節は約 500 字。4 つ目の決まりに補助ファイルの名前まで書く（長い要件メモで「0. 始める前に」の案内が押し出されたあとでも、読み直す先が分かるように）。
- `足したい機能: $ARGUMENTS` の行は「0. 始める前に」の先頭へ移す（要件メモが長くても、冒頭の決まりが先頭から押し出されないように）。
- 補助ファイルには、移す文章だけを入れ、足さない。`screen-check.md` のコマンドは 1 行に 1 つ、`allow` と一字違わない形で書く（つないだときは、どの部分も規則に当たらないと確認が出る。公式の文書）。
- 旗の綴りが `record.md` にしか無いコマンド（`review <段> revise`・`record red`・`record verdict`）には、SKILL.md の手順の中で「（旗は `record.md`）」と指す。
- 定義の「最後の返答の文が親に渡る」は、フックの先頭の説明と意味が合う言い方で、字面は同じではない。
- 実装は、`.claude/` の中と CLAUDE.md をメインが書いた（`pipe-in-coder` は `.claude/` を書けないため。D0008・D0032 と同じ）。文書は `pipe-in-coder`、テストは `pipe-in-tester` が書いた。
- 番号は D0035 → D0038 → D0039 と振り直した（作業のあいだに main に D0035・D0036・D0037 が入り、別のブランチ（#70）が D0038 を先に使ったため）。

### 受け入れたリスク

1. **補助ファイルの読み忘れ**：補助ファイルを読み忘れると、手順が欠ける。「0. 始める前に」の案内・手順の中の旗の指し・読めないときに止まる 1 行（AC-10）で補う。機能の枝が補助ファイルを持たない古い worktree では、新しい SKILL.md の案内で止まり、載せ直しを促す。
2. **`allow` の足し**：フックが失敗して素通りのとき（python が無い・時間切れ・構文エラー。D0032）と、フックが見ない呼び出し元（メイン・pipe-in-* 以外のサブエージェント）では、5 つのコマンドが確認なしで流れる。どれもテスト・型検査・ビルド・確認用ページ・手元だけで配るサーバーで、書き込みは `vscode/out/` などに限られる。この変更より前の main から切った worktree では、その枝の settings.json が読まれるので、5 つの `allow` は無い（公式の文書。害は無く、確認が今までどおり出るだけ）。
3. **`ask` の外れ**：つないだコマンド（`git add . && git commit`）は、どれか 1 つが当たれば `ask` が効く（公式の文書）。外れるのは別の書き方（`git -C . commit`・`git -c … commit`・引用符で囲んだ語・絶対パス・`sh -c`）で、公式の文書も `ask` は守りの境目ではないと書く。
4. **コミットの禁止の文が 3 か所に出る**：SKILL.md の冒頭・CLAUDE.md・workflow.md（と develop.md）。重ねてよい（どこから読んでも同じ決まりに着く）とした。

### 確かめていないこと

- 日本語 1 字のトークン数（自動の要約のあとに先頭 5,000 トークンだけが戻ることは、検証のあとの助言で公式の文書を確かめた）。
- `${CLAUDE_SESSION_ID}`・`$ARGUMENTS` の置き換えが補助ファイルで効かないこと（公式の文書は、置き換えをスキルの内容についてしか書いていない。効かないものとして SKILL.md にだけ置いた）。
- 実機での動き：`ask` が個人の `allow` より先に効くか（AC-26）・新しい worktree で `allow` が効くか（AC-30）・フックの deny が `allow` より先に効くか（AC-31）・長い要件メモと `/compact` のあとに冒頭の決まりが残るか（AC-42）。AC-26・30・31 は、公式の文書には書いてある。
- 定義の「最後の返答の文が親に渡る」という言い方（公式の文書は final report・last_assistant_message と書き、そのとおりの 1 文は無い）。「SubagentHandback が渡されるのは auto モードのときだけ」は、公式の文書で確かめた。

## 対象外・残った課題

別のイシューにした項目（AC-39 で人に聞き、1 つにまとめて #71 に立てた）：

- `Agent(…)` の allow の 8 行を消すかと、段のサブエージェントに `isolation: worktree` を付けない決まりを `Agent(isolation:worktree)` の deny で守れるか（この形は deny と ask で書け、呼び出しの引数に `isolation` を付けたものに当たる。定義の前置きの `isolation` に当たるかは、公式の文書に無い。助言 V-14）。
- `ask` の外れ（`git -C . commit` などの別の書き方）を塞ぐ手：`ask` に `Bash(git * commit *)`・`Bash(git * commit)` を足す（公式の文書の表からの推定で、確かめていない）か、全文を見て `ask` を返すだけのフック（止めずに確認を出すだけなので、上の「フックで守らない」理由には当たらない）。助言 V-05。
- フックを exec 形（`"command": "python"` と `"args"`）にする（D0032 の助言 V-02）。
- 定義の前置きに `"onFailure": "block"` を付けたフックを足す（D0032 の助言 V-01。実機で確かめてから）。
- `record` の幅広い許可（`record:*`。上の理由で足していない）。
- 記録の順序の検査（承認の前に次の段に進んでいないかを、記録から確かめる）。
- 本体の `/pipe-dev` の文言の残り（前の版のコマンドの言い方）。
- `.claude/hooks/pipe_in_guard.py` の止めた理由の文にある「SubagentHandback で親に返す」の言い方（守る仕組みのファイルなので、ここでは直していない）。

## 確かめたこと

- 検証（1 回目で合格）：全体の `pytest` は 1 failed, 7575 passed, 6 skipped。落ちた 1 件はベースの赤（`tests/test_rules.py::test_ac_ids_in_tests_exist_in_records`）で、`missing` の 8 件は D0033 の控えと一字違わず同じ。D0039 のテストと書き換えたテストの失敗は 0 件。`npm --prefix vscode test` は 4415 pass。AC の合格は 01〜25・27〜29・32〜38。手で確かめた AC-40・41 は上の行のとおり。
- 公開してよいか：変えたファイルに、秘密・ユーザー名の入った絶対パス・メールアドレス・`docs/pipeline/` の中身は無い。
- 文書係（検証のあと）：`docs/development/README.md` の「テストで守らせている決まり」の表に 1 行足した。案にした `/pipe-help` の `/pipe-in --auto` の行（止まる場面を SKILL.md の冒頭にそろえる。前からある食い違い）は、人が承認してメインが直した。
- 矛盾監査（7 件）：人が承認して直したのは、A-01（`record.md` で、セッション ID と受け持ちの断りの文が `--name` に付いて読めた。移すときに生んだずれ）・A-03（置き換えの理由を言い切らない）・A-04（テストの古いコメント 2 つ）・A-05（`--auto` の節のコミットの行に「main に入れる」。守る検査が「コミット・push」の語で見ているので、その語を残した）・A-07（`develop.md` と `/pipe-help` の「信頼していない作業フォルダ（新しい worktree など）」の例。worktree の信頼は main の作業フォルダの場所で見るので、例を直した）。A-02（`.claude/hooks/pipe_in_guard.py` の止めた理由の文）は守る仕組みのファイルなので直さず、上の「対象外・残った課題」のまま。A-06 は、この節と AC-40・41 の行を書いて済ませた。
- 公式の文書と照らした助言（14 件。重さ「高」は無し）：人が承認して、V-01〜12・14 を文書・決定の記録・SKILL.md の文で直した。主なものは、受け入れたリスク 3 の前半が文書と逆だったこと（V-03。つないだコマンドは、どれか 1 つが当たれば `ask` が効く）、AC-26・30・31 が文書に書いてあること（V-06・07・10）、要約のあとに戻るのはスキルの先頭 5,000 トークンだけなこと（V-01）、Read で読み直した SKILL.md では置き換えが効かないこと（V-02）。V-05・14 は「対象外・残った課題」に候補として書いた。V-13（補助ファイルを `${CLAUDE_SKILL_DIR}` で指す）は採らない。古い worktree でも main の版を読んでしまい、補助ファイルが無いときに止まって載せ直す決まりが働かなくなるため。スキルの文にはプロジェクトのフォルダの変数名を書かない（スキルの内容では実際のパスに置き換わるため。公式の文書）。
- 審査（助言の報告の採点）：overall 0.9・verdict pass（事実の正確さ 1.0・引用の正確さ 1.0・網羅性 0.75・情報源の質 1.0・道具の効率 0.75）。網羅性が下がったのは、allow の `Agent(name)` の規則の仕様が取れていないため。
- 直したあと、触った側のテストと全体をもう一度流し、ベースの赤（D0033 の 8 件）のほかに失敗が無いことを確かめた。
