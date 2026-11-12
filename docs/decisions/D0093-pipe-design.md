# D0093 画面の見本を触って比べて決めるスキル /pipe-design と、良さの条件の調べ係 pipe-in-ux-researcher を足す

## 目的

画面の「なんとなく気持ちよくない」は、言葉だけで詰めると、どこを直すかが決まらない。別のリポジトリの計算機の画面を見直したときに、つまみで組み合わせを切り替えられる見本を作り、良さの条件をウェブで調べて照らし合わせ、人が ★ を付けた案から形を決めて issue と見本を残す流れがうまく回った。この流れを、どの画面にも使えるスキル `/pipe-design` と、調べものを受け持つ読むだけのサブエージェント `pipe-in-ux-researcher` にして残す。

### 要求と前提

- UR-01 画面を直したい人として、言葉で詰める前に、触って比べられる見本から形を選びたい。
- UR-02 画面を直したい人として、選んだ形が良い UX・UI の条件に合うかを、出典を確かめた形で知りたい。
- UR-03 利用者のプロジェクトを守る者として、調べ係が書かず、決めた場所の Web だけを読むようにしたい。
- 前提：見本を公開する会話に、Artifact と ArtifactData のツールがある（無い会話では、見本を手元の HTML で見せ、★ は人に番号を貼ってもらう）。
- 前提：アーティファクトの保存先（db）を、見本のページから使える（使えない所では ★ がブラウザの中だけに残る）。
- 状態を持ち、操作や出来事で移り変わるか
  - 答え：いいえ
  - 理由：足すのはスキルの手順の文書と、読むだけのエージェントの定義と、フックの許す表で、pipe-in の本体に状態を足さない（見本のページの ★ は、そのページの保存先の中のこと）。

## 機能要件と受け入れ基準

- FR-01（UR-01）`.claude/skills/pipe-design/SKILL.md` に置き、人が `/pipe-design [直したい画面と、気になること]` と呼んだときだけ動く。
  - D0093-AC-01（FR-01）前置きの `name` が `pipe-design`、`description`・`argument-hint` が空でなく、`disable-model-invocation` が `true`。（tests/test_pipe_design.py）
  - D0093-AC-02（FR-01）前置きに `allowed-tools` が無い（あっても `Bash`・`gh`・`mcp__` を含まない）。（tests/test_pipe_design.py）
- FR-02（UR-01・UR-03）冒頭に「必ず守ること」を置く：外へ出す操作は見せて承認を得てから・聞くのは質問欄・見本は明るい画面と暗い画面の両方・公開リポジトリとしての注意・条件は確かめた出典だけ。
  - D0093-AC-03（FR-02）最初の `##` 見出しが「必ず守ること」で、「全文」・「承認」・「質問欄」・「明るい画面と暗い画面」・「公開リポジトリとしての注意」がある。（tests/test_pipe_design.py）
  - D0093-AC-04（FR-02）`$ARGUMENTS` が1回だけ、「必ず守ること」より後ろにあり、次の行が「（空なら」で始まる。（tests/test_pipe_design.py）
  - D0093-AC-11（FR-02）SKILL.md・補助ファイル・調べ係の定義に、ユーザー名の入った絶対パス・アーティファクトの実際の URL・メールアドレスが無い。（tests/test_pipe_design.py）
- FR-03（UR-01）流れを5つの節（不満を言葉にする・見本を作る・良さの条件を調べる・★ を読んで決める・まとめて残す）に分ける。
  - D0093-AC-05（FR-03）5つの節の見出しが、この順にある。（tests/test_pipe_design.py）
- FR-04（UR-01）見本の作り方（つまみ・案の番号・一覧の縮図・おすすめの案・1本ずつ変えた比べ・明暗）を補助ファイル `mock.md` に分ける。
  - D0093-AC-06（FR-04）`mock.md` に「つまみ」・「縮図」・「おすすめ」・「1本ずつ」・「番号」・「prefers-color-scheme」があり、「2. 見本を作る」が `mock.md` を指す。（tests/test_pipe_design.py）
- FR-05（UR-01）★ を見本の保存先（`favs`）に書き、Claude が ArtifactData で読む決まりを、補助ファイル `favs.md` に分ける。保存先が使えないときは `localStorage` に残す。
  - D0093-AC-07（FR-05）`favs.md` に「db」・「favs」・「ArtifactData」・「localStorage」があり、「4. ★ を読んで決める」が `favs.md` を指す。（tests/test_pipe_design.py）
- FR-06（UR-02）良さの条件は調べ係 `pipe-in-ux-researcher` に任せ、開いて確かめた出典の条件だけを使い、選択肢ごとに ○・△・× の見立てを付ける。
  - D0093-AC-08（FR-06）「3. 良さの条件を調べる」に、`pipe-in-ux-researcher`・「開いて確かめた」・○・△・× がある。（tests/test_pipe_design.py）
- FR-07（UR-01・UR-02）★ をつまみごとに数え、割れた所と、条件に外れる所だけを質問欄で聞く。
  - D0093-AC-09（FR-07）「4. ★ を読んで決める」に、「割れた」・「外れる」・「質問欄」がある。（tests/test_pipe_design.py）
- FR-08（UR-01）要約（`docs/talk/`。書く前に `git check-ignore`）・issue・見本（対象のリポジトリの `docs/design/`）を、承認を得てから残す。
  - D0093-AC-10（FR-08）「5. まとめて残す」に、`docs/design/`・`docs/talk/`・`git check-ignore`・「承認」・「issue」がある。（tests/test_pipe_design.py）
- FR-09（UR-02・UR-03）調べ係の定義 `.claude/agents/pipe-in-ux-researcher.md` を足す。道具は読むことと Web だけ、軽いモデル、回数の上限つき。
  - D0093-AC-12（FR-09・NFR-01）`tools` がちょうど Read・Grep・Glob・WebFetch・WebSearch、`model` が `sonnet`、`maxTurns` が 60。（tests/test_pipe_design.py）
  - D0093-AC-23（FR-09）エージェントの数を数える検査（D0041-AC-05・D0039-AC-23）を 9 つに直し、回数の上限の表に調べ係の 60 を足す。（tests/test_agent_limits.py・tests/test_skill_tidy.py）
- FR-10（UR-03）フック（`.claude/hooks/pipe_in_guard.py`）で、調べ係を書けない・Bash なしにし、Web は UX の出典の場所 `UX_HOSTS` の https:// だけにする。助言と審査の場所（`DOC_HOSTS`）とは混ぜない。
  - D0093-AC-13（FR-10）調べ係の Write・Edit・Bash を止め、Read・Grep を通す。（tests/test_pipe_design.py）
  - D0093-AC-14（FR-10）調べ係の WebFetch は、UX_HOSTS の https:// の URL を通す。（tests/test_pipe_design.py）
  - D0093-AC-15（FR-10）調べ係の WebFetch は、ほかのホスト・http・ポート・ユーザー情報・似せたホスト・道の正規化・空・公式の文書の場所を止める。（tests/test_pipe_design.py）
  - D0093-AC-16（FR-10）調べ係の WebSearch は、`allowed_domains` が空でなく全部 UX_HOSTS のときだけ通し、無い・空・ほかが混じると止める。（tests/test_pipe_design.py）
  - D0093-AC-17（FR-10・NFR-02）助言と審査の WebFetch は、UX_HOSTS の URL を今までどおり止め、公式の文書の URL は通す。（tests/test_pipe_design.py）
  - D0093-AC-18（FR-10）調べ係の定義の本文に、UX_HOSTS の全部のホストがある（フックの写し）。（tests/test_pipe_design.py）
- FR-11（UR-01）`/pipe-help`・CLAUDE.md・置き場所の表・開発のガイド・この記録の一覧に足す。
  - D0093-AC-19（FR-11）`/pipe-help` の表と前置きの `description` に `/pipe-design` がある。（tests/test_pipe_design.py）
  - D0093-AC-20（FR-11）CLAUDE.md に `/pipe-design`・`.claude/skills/pipe-design/`・`pipe-in-ux-researcher` がある。（tests/test_pipe_design.py）
  - D0093-AC-21（FR-11）`docs/development/design.md` の置き場所の表に `.claude/skills/pipe-design/` がある。（tests/test_pipe_design.py）
  - D0093-AC-22（FR-11）この記録があり、`docs/decisions/README.md` の表に載っている。（tests/test_pipe_design.py）
- D0093-AC-24（FR-03）（手で）`/pipe-design` を呼んで、見本の公開・良さの条件の照らし合わせ・★ の読み取り・要約と issue まで流れる。（まだ。もとになった流れは、別のリポジトリの計算機の見直しで手で流した）

### 非機能要件

- NFR-01（UR-02）調べものの利用料：良さの条件の調べものは、メインの会話のモデルでなく、軽いモデル（`model: sonnet`）の調べ係で回す。きっかけは「3. 良さの条件を調べる」、状況はテーマごとに同時に呼ぶとき、応答は調べ係の定義の `model` が `sonnet`、測り方は D0093-AC-12。
- NFR-02（UR-03）すり抜けの道を開けない：調べ係を足しても、ほかの役の Web の場所は広がらない。きっかけは調べ係を表に足すこと、状況は助言・審査の呼び出し、応答は UX_HOSTS の URL を止める、測り方は D0093-AC-17。

## 決めたことと理由

### 人が決めたこと

- **持ち込み方**：`/pipe-in` の段を踏まず、メインが作って push する（人が選んだ）。テストを先に書いて赤を確かめ、決定の記録と文書もそろえる。
- **作るもの**：スキル `/pipe-design` と調べ係 `pipe-in-ux-researcher`。見本のひな形（中身が空の HTML）は作らない（人が選ばなかった）。
- **調べものは軽いモデルで回す**（人の好み）。

### 選んだ形

- **`/pipe-talk` に足さず、別のスキルにした**。壁打ちは画面に限らず、流れも「まとめて回す」だけ。見本と ★ と条件の照らし合わせは手順が長く、補助ファイルが要るので分けた。要約の置き場所（`docs/talk/`）と書く前の `git check-ignore` は、`/pipe-talk` と同じ決まりにした。
- **手順を SKILL.md と補助ファイル2つに分けた**（D0039 の形）。冒頭の決まりと5つの流れは SKILL.md、見本の作り方は `mock.md`、★ の保存先と読み方は `favs.md`。
- **調べ係は読むだけ・書けない・Bash なし**（監査・助言・審査と同じ）。報告は返答で親に返す。回数の上限は 60（助言の 80 より少なく、テーマを分けて同時に呼ぶため）。
- **Web の場所は UX_HOSTS に絞り、公式の文書の場所とは混ぜない**。UX の条件の出典として、NN/g・Laws of UX・デジタル庁デザインシステム・W3C（WCAG）・MDN・web.dev・Material Design 3・Apple HIG・Baymard・Smashing Magazine を許した。WebSearch も `allowed_domains` をこの中に絞ったときだけ通す。判定の芯（https:// だけ・ユーザー情報とポートを止める・道の正規化を止める）は、公式の文書の判定と同じ関数を使い、ホストの組だけを役ごとに変えた。

### 選ばなかった形

- **調べ係の Web を広く（どのホストでも）許す**：見本の調べものは、どこでも読めると楽だが、読んだ文の指示に流される道と、利用料が読めない道が開く。出典の質も落ちる。足りないホストは、記録を足して表に加える。
- **助言の役（pipe-in-advisor）に UX の調べものもさせる**：助言は公式の文書との照らし合わせが役で、場所の表を混ぜると、助言が UX の場所を読める・調べ係が Claude の文書を読める、の両方の道が開く。

### 受け入れたリスク

- 調べ係の報告の正しさは、テストでは確かめていない（出典の URL を開いたかは、報告の文を信じる）。メインは、推測と書かれた条件を使わない決まりにした。
- UX_HOSTS に無い良い出典（ベンダーの解説・論文など）は読めない。

## 対象外・残った課題

- 見本のひな形（つまみ・一覧・★ の保存先だけを持つ空の HTML）。毎回の見本の作り直しが重ければ、別に足す。
- プラグイン（`plugin/`）への持ち込み。いまはこのリポジトリの開発用のスキルだけ。
- 手で流す確かめ（D0093-AC-24）。

## 確かめたこと

- 新しいテスト（tests/test_pipe_design.py）は、先に書いて 26 件が「まだ作っていない」理由で落ちることを確かめ、作ったあと全部が通った。止める側の検査（AC-13・15・17）は、作る前から通る（表に無い `pipe-in-*` は読むだけになるため）ことも確かめ、守る検査として残した。
- 全部の Python のテスト（`pytest -q`）が通った。
- 手で `/pipe-design` を流す確かめは、まだ。もとになった流れ（不満の聞き取り・見本 2 枚・調べ係を 3 つ同時に・★ の読み取り・issue 2 件・`docs/design/` への見本の置き場所）は、別のリポジトリの計算機の見直しで、このスキルを作る前に手で流した。
- 足した欄：要求 3・前提 2・非機能要件 2。差し戻しは 0 回（`/pipe-in` の段を踏まずに作った）。
