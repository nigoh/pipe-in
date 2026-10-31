# D0056 壁打ちのスキル /pipe-talk を足し、区切りの要約から次の作業（issue・デザイン・/pipe-in・計画ボード）へ回す

## 目的

思いつきや迷いを、人と Claude で詰める場がなかった。`/pipe-in` は要件メモが固まってから使うもので、固まる前の考えは会話に流れて消えていた。壁打ちのスキル `/pipe-talk` を足し、区切りで要点（決まったこと・残った問い・やりたいこと）をまとめ、その中身に合わせて次の作業へ回せるようにする。回す先は GitHub の issue・デザイン・`/pipe-in`・計画ボードの4つ。

## 機能要件と受け入れ基準

### 機能要件

- FR-01：`.claude/skills/pipe-talk/SKILL.md` に置き、人が `/pipe-talk [話したいこと]` と呼んだときだけ動く（`disable-model-invocation: true`）。
- FR-02：冒頭（`# /pipe-talk` の次の節）に「必ず守ること」を置く（D0039 の形）。
- FR-03：壁打ちでは、問い返し・案の比較・前提の確かめをし、要約のファイルのほかは何も書かない・作らない。引数が空なら、何を話したいかを聞いてから始める。
- FR-04：区切り（人の「まとめて」か、Claude が人に確かめてから）で、「決まったこと」「残った問い」「やりたいこと」の3つの見出しの要約を見せる。
- FR-05・FR-06：要約は手元にだけ残す（`docs/talk/<日時>-<名前>.md`。1回の壁打ちで1つ）。書く前に `git check-ignore` で無視されているかを確かめ、無視されていなければ書かずに伝える。
- FR-07：要約に合わせて4つの回す先から候補を出し、人が選ぶまで行わない。
- FR-08・FR-09：外へ出す操作（issue を作る・Figma に書く・アーティファクトを公開する）は、中身を全文見せて人の承認を得てからだけ。GitHub の MCP の道具で issue を作るのも同じ。計画ボードには `/pipe-talk` の中では書かない（人が流す `/pipe-plan add` が書き、流すことを承認とみなす）。
- FR-10：issue の本文などに、秘密・手元の事情・要約のファイルのパスを入れない。
- FR-11：デザインは、画面・見た目の話のときだけ候補にする。Design のアーティファクトか Figma かを人が選び、道具が無ければ止まる。
- FR-12・FR-13：`/pipe-in`・`/pipe-plan` は Claude からは始めず、人が流す1行を示す。
- FR-14〜FR-17：`/pipe-help`・CLAUDE.md・`docs/development/design.md` の置き場所の表・`docs/guide/develop.md`・`.gitignore` に足す。
- FR-18：この記録を書く。番号は D0056（はじめ D0054 で進めたが、並列のほかの作業が D0053〜D0055 を使ったので、main に入れる前に付け替えた）。
- FR-19：`.claude/settings.json` の `ask` に `Bash(gh issue create:*)` を足し、`allow` には `gh` の規則を入れない（設計で人が決めて足した要件）。

### 受け入れ基準

- D0056-AC-01：SKILL.md があり、前置きの `name` が `pipe-talk`、`description`・`argument-hint` が空でなく、`disable-model-invocation` が `true`。（tests/test_pipe_talk.py）
- D0056-AC-02：前置きに `allowed-tools` が無い（あっても `Bash`・`gh`・`mcp__` を含まない）。（tests/test_pipe_talk.py）
- D0056-AC-03：最初の `##` 見出しが「必ず守ること」で、「承認」・「gh issue create」・「手元にだけ」・「公開リポジトリとしての注意」・「git check-ignore」がある。（tests/test_pipe_talk.py）
- D0056-AC-04：`$ARGUMENTS` が1回だけ、「必ず守ること」より後ろにあり、次の行が「（空なら」で始まる。（tests/test_pipe_talk.py）
- D0056-AC-05：要約の3つの見出しがある。（tests/test_pipe_talk.py）
- D0056-AC-06：要約の置き場所 `docs/talk/` と、ファイル名の形 `<日時>-<名前>.md` と、名前の決まり（英小文字）がある。（tests/test_pipe_talk.py）
- D0056-AC-07：`.gitignore` の行が `docs/talk/` の下のファイルを覆う。（tests/test_pipe_talk.py）
- D0056-AC-08（`.gitignore` に行が無い古い枝）：書く前に `git check-ignore` で確かめ、無視されていなければ書かずに伝える。（tests/test_pipe_talk.py）
- D0056-AC-09：要約のほかのファイルには書かず、コミット・push をしない。（tests/test_pipe_talk.py）
- D0056-AC-10：4つの回す先の語（issue・Design・Figma・`/pipe-in`・`/pipe-plan add`）がある。（tests/test_pipe_talk.py）
- D0056-AC-11：候補は人が選ぶまで行わない。（tests/test_pipe_talk.py）
- D0056-AC-12：issue の節で、本文を見せる → 承認 → `gh issue create` の順に書いてある。（tests/test_pipe_talk.py）
- D0056-AC-13：issue の節に、MCP の道具でも承認を得てから、とある。（tests/test_pipe_talk.py）
- D0056-AC-14：「必ず守ること」に、外へ出す操作の並びと承認がある。（tests/test_pipe_talk.py）
- D0056-AC-15：入れないものの語（秘密・絶対パス・メールアドレス）がある。（tests/test_pipe_talk.py）
- D0056-AC-16：デザインの節が、画面・見た目のときだけ・`docs/design/README.md` に沿う・道具が無ければ止まる。（tests/test_pipe_talk.py）
- D0056-AC-17：`/pipe-in`・`/pipe-plan add` の節は、人が流す行を示す。（tests/test_pipe_talk.py）
- D0056-AC-18：`.claude/settings.json` の `allow` に `gh` の Bash の規則が無い（守り続けるための検査）。（tests/test_pipe_talk.py）
- D0056-AC-19：SKILL.md とこの記録に、手元のパス・issue やアーティファクトの実際の URL・実際のセッション ID が無い。（tests/test_pipe_talk.py）
- D0056-AC-20：`/pipe-help` の表と前置きの `description` に `/pipe-talk` がある。（tests/test_pipe_talk.py）
- D0056-AC-21：CLAUDE.md に `/pipe-talk` と `.claude/skills/pipe-talk/` がある。（tests/test_pipe_talk.py）
- D0056-AC-22：`docs/development/design.md` の置き場所の表に `.claude/skills/pipe-talk/` がある。（tests/test_pipe_talk.py）
- D0056-AC-23：この記録があり、`docs/decisions/README.md` の表に載っている。（tests/test_pipe_talk.py）
- D0056-AC-24（手で）：`/pipe-talk` を呼んで壁打ちし、「まとめて」で3つの見出しの要約が出て、`docs/talk/` にファイルができ、`git status` に出ない。（まだ）
- D0056-AC-25（手で）：issue を選ぶと本文が見せられ、承認するまで `gh issue create` が流れない。（まだ）
- D0056-AC-26（手で）：`/pipe-in`・`/pipe-plan add` を選ぶと、Claude からは始まらず、人が流す1行が示される。（まだ）
- D0056-AC-27：`.claude/settings.json` の `ask` に `Bash(gh issue create:*)` があり、もとの6つが残る。（tests/test_pipe_talk.py）

## 決めたことと理由

### 人が決めたこと（要件定義と設計で聞いた点）

- **名前は `/pipe-talk`**。既存の `/pipe-*` にそろえる。
- **回す先は issue・デザイン・`/pipe-in`・計画ボードの4つ全部**。
- **要約は手元だけの `docs/talk/` に置き、`.gitignore` に `/docs/talk/` を足す**。壁打ちには手元の考えや事情が入りうるので追跡しない。`docs/pipeline/` の下は、`talk` という名前のパイプの記録の置き場所と重なるので使わなかった。
- **`.claude/settings.json` の `ask` に `Bash(gh issue create:*)` を足す**。会話の中の承認に加えて、Claude Code の確認の画面も出るようにする。確認が出る場面を増やす側（止める範囲を広げる側）の変更なので、狭める変更の手続きは要らない。
- **計画ボードは `/pipe-talk` の中では書かず、人が流す `/pipe-plan add` の1行を示す**。ボードへの書き方を `/pipe-plan` の1か所にとどめる。
- **要約のファイル名の `<名前>` は英小文字・数字・`-` だけ**（決定の記録の名前と同じ決まり）。
- **この記録の下書きを実装の段で書く**（設計の決めきれない点。検証のときに全体の pytest で合否を決められるように）。

### 聞かずに決めたこと

- 区切りは、人の「まとめて」か、Claude が人に確かめてから。要約は1回の壁打ちで1つのファイルにし、区切りのたびに書き足す。候補はいくつ選んでもよい。
- issue の本文には要約のファイルのパスを書かない。
- `/pipe-in`・`/pipe-plan` はどちらも `disable-model-invocation: true` なので、Claude からは始められない。人が貼って流せる1行を示す形にした。
- 前置きに `allowed-tools` を持たせない（`allowed-tools` は確認なしで通す道具を足すだけで、絞らないため）。`gh issue create`・`git check-ignore`・GitHub の MCP の道具は、ふつうは確認を通る。ただし、利用者が個人の `allow` に入れているときや auto モードでは、`ask` に入っていない道具（GitHub の MCP の道具など）は確認が出ないことがある。`allow` に `git check-ignore` も足さない（壁打ち1回につき確認1回で済み、`allow` を固定している検査も変えずに済む）。
- `tests/conftest.py` の見張りに `docs/talk` を足さない。D0056 のテストは `docs/talk/` を読みも書きもしない。
- 書く担当は D0015・D0039 と同じに分けた。`.claude/` と CLAUDE.md とこの記録はメイン、`.gitignore` と `docs/development/design.md` は `pipe-in-coder`、テストは `pipe-in-tester`。

- 要約の置き場所は追跡しないが、作業フォルダの中にある。作った issue の番号は要約に書いてよく、URL は要約にも書かない。
- `/pipe-in` と同じ順にせず、この記録の下書きを実装の段で書いた（テストがこの記録のあることを確かめるので、検証のときに全体の pytest で合否を決められるように）。ほかの機能でも同じことは起こりうるが、手順に例外として書くかは今回は決めない（監査 A-06）。

### 既存のテストを変えた理由

- `tests/test_wait_notify.py` の D0046-AC-27 は `ask` の並びを一字一句で固定している。`Bash(gh issue create:*)` を足したので、期待の並びの最後に1行足し、説明にもそのことを添えた。D0046 の AC の意味（`ask` を減らさない・フックを足さない）は変えていない。

### 受け入れたリスク

1. **GitHub の MCP の道具で issue を作る道は `ask` に入れていない**。SKILL.md の「承認を得てから」と、ふつうの道具の確認だけで守る。個人の `allow` や auto モードでは確認が出ないことがある。
2. **`Bash(gh issue create:*)` が当たるのは、Bash の道具で流す決まった形だけ**。PowerShell の道具・`bash -c '…'`・`gh api …/issues` からの作成は止めない（公式の文書：ask の規則はプログラムのまわりの守りの境ではない）。
3. **`ask` が個人の `allow` より強く確認を出すことは、公式の文書（deny → ask → allow の順で、先に当たったものが決める）で読んだだけ**。設定の場所をまたぐ組み合わせは文書に明記が無く、実機でも確かめていない。
4. 承認の決まりは SKILL.md の文で守るもので、Claude が決まりを外れたときにフックで止める仕組みはない（`ask` の確認の画面が最後の歯止め）。

## 対象外・残った課題

- 要約の一覧や検索、要約を VSCode の拡張で見ること。
- 壁打ちの要約から issue・ボードの項目を自動で更新すること。
- 別の `fix/` のブランチで扱うこと（助言。`.claude/settings.json` と、`ask` を字のまま固定しているテストが変わるため）：
  - GitHub の MCP の issue 作成の道具を、道具名のワイルドカード（例 `mcp__*__create_issue`）で `ask` に入れる（V-01）。実際の道具名（`create_issue` か `issue_write` か）を `/mcp` で確かめてから。
  - `PowerShell(gh issue create *)` を `ask` に足す（V-03）。
  - 規則の書き方を、確認の画面が書く空白の形（`Bash(gh issue create *)`）にそろえる（V-05。今の `:*` も同じ意味）。

## 確かめたこと

- テスト先行：`tests/test_pipe_talk.py` の 23 件が、期待した理由（SKILL.md が無い・`.gitignore` に行が無い・`ask` に無い・この記録が無い・一覧に無い）で落ちることを確かめた。
- 検証（1回で合格）：`python -m pytest -q` は 11602 件が通り、49 件が落ちた。落ちたのは `tests/test_bash_write_guard.py` の 48 件（`/dev/null`・`/tmp` への書き込みが「プロジェクトの外には書き込めません」で止まる）と `tests/test_live_answer_cli.py` の 1 件で、変更の前から同じく落ちていた。どちらのファイルも変えていない。この手元の環境で落ちる理由は調べていない。拡張には触れていないので npm は流していない。
- 公開してよいか：変えたファイルに、秘密・ユーザー名の入った絶対パス・メールアドレス・実際の URL・セッション ID は無い。
- 文書係：`docs/guide/develop.md` に `/pipe-talk` の段落を足した。書けない所の案は無かった。
- 矛盾監査（11 件）：人が承認して、A-01（一時ファイルの例外）・A-02（計画ボードは中で書かない）・A-03（入れないものを CLAUDE.md と同じ並びに）・A-04（`/pipe-plan add` を流すことを承認とみなす）・A-05（番号。そのあと D0056 に付け替えた）・A-07（FR-19 と `develop.md`）・A-08（AC-06・AC-08 の書き方）・A-09（テストの説明）・A-10（要約に issue の番号だけ）・A-11（壁打ちの「書かない」の例外）を直した。A-06 は上の「聞かずに決めたこと」に書いた。
- 公式の文書と照らした助言（6 件）：V-02（MCP の道具の確認の書き方）・V-04（メッセージの先頭に貼る）を直した。V-01・V-03・V-05 は「対象外・残った課題」に書いた。V-06 は問題なし。
- 審査（助言の報告の採点）：overall 0.88・verdict pass。V-03 の出典が主張を直接には書いていないこと（引用の正確さ 0.75）と、`/pipe-help` の一覧を照らしていないこと（網羅性 0.75）で下がった。ツール効率は回数が渡されず採点なし。
- AC-24〜26（手で）：まだ。
