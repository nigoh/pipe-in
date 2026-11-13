# D0096 プラグインの eval を下位のモデルでラウンドとして回し、落ちた所を直して育てる（pipe-judge・名前の決まり・会話の道の名前の断り・警告 W8・ケース 12 本・調査と集計・報告の道具を止めない）

## 目的

プラグインのスキルとエージェントが、下位のモデル（haiku）でも手順どおりに動くように、プラグイン自身の eval（`plugin/evals/`・`claude plugin eval`。[D0045](D0045-plugin-evals.md)）を haiku（審査役も haiku）で「ラウンド」として回し、落ちた所を直してまた回した。要件メモは「ラウンドを回して、pipe-in のプラグイン用にラウンドを回して醸成してください」（`--auto`）。「ラウンド」は、過去の比較実験（[docs/research/harness-compare](../research/harness-compare/README.md) の R3〜R14。Haiku 中心）と同じく、下位のモデルで回す実験の 1 回と読んだ（人の設定「ラウンドは下位モデルで回す」に合わせた）。結果と回し方は調査 [docs/research/plugin-eval-rounds](../research/plugin-eval-rounds/README.md) にある。

### 要求と前提

- UR-01 プラグインを直す人として、下位のモデル（haiku。審査役も haiku）でプラグインの eval をラウンドとして回し、落ちた所を直してまた回すことで、スキルとエージェントが手順どおりに動くように育てたい。
- UR-02 `/pipe-in:pipe-judge` を使う人として、範囲の外の `--runs` は最初に断られ、結果は計算（`pipe-in-gen judge-score`）の JSON のまま受け取りたい。
- UR-03 `/pipe-in:pipe-build` を使う人として、作るパイプの指示文と成果物が、Claude Code に断られない名前で書かれてほしい。
- UR-04 会話の中でパイプを流す人（`/pipe-in:pipe-run`）として、段の成果物の名前が Claude Code に断られるパイプは、段の途中で失敗する前に、流す前に理由と直し方を知りたい。
- UR-05 プラグインを直す人として、eval の採点が偽の合格や採点そのものの誤り（grader threw）を出さず、ケースの無いスキル（pipe-run・pipe-live）も安く確かめたい。
- UR-06 あとから読む人として、ラウンドの回し方・結果・費用・確かめられたこと・限界を文書で読み、同じ形で回し直したい。
- UR-07 プラグインを入れている人として、動きが変わった版を、更新で受け取りたい。
- UR-08 パイプを作る・書く人として、審査（judge）だけで差し戻す形（`command` が無いのに `on_fail` がある検査）を、「確認済み」と言っても作られずに直し方の案を見せてほしいし、手で書いたときも `pipe-in-gen check` で決まりと直し方を知りたい。
- UR-09 プラグインを auto モードで使う人として、pipe-judge・pipe-builder・pipe-stage・pipe-probe などのエージェントの報告を、プラグインのフックに止められずに受け取りたい。
- 前提：Claude Code（2.1.323 で本体の判定の文を確かめた）は、サブエージェント（agentId がある）からの Write で、ファイル名（basename）が `REPORT`・`SUMMARY`・`FINDINGS`・`ANALYSIS` で始まり `.md` で終わる（大文字と小文字を区別しない）ものを、"Subagents should return findings as text, not write report files." で断る。公式の文書の決まりとしては書かれていない（公式の cookbook https://platform.claude.com/cookbook/claude-agent-sdk-08-dynamic-workflows に、workflow の中で見たこととして「`SUMMARY.md` のような報告の形のファイルを書こうとすると、内容を返すよう言われた」の 1 文があるだけで、語の一覧と判定の形は無い）。決まりが無くなると会話の道の新しい断りは要らない断りになり、語が増えると断りが足りなくなる。
- 前提：端末の `pipe-in`（SDK の道）の段は SDK のメインのエージェントなので、この断りに当たらない。ただし段の中のサブエージェント（`agents`）は当たりうる。
- 前提：haiku（審査役も haiku）で手順どおりに動くスキルの文は、上位のモデルでも手順どおりに動く見込みが高い。haiku で見つかった読み飛ばし・要約での置き換えは、上位のモデルでも起こりうる、直す価値のある崩れである。
- 前提：`claude plugin eval` の中では、Artifact・ArtifactData・Monitor が使えない（ラウンド 1 の init の道具の一覧に無かった）。使えると、pipe-live のケースは「道具が無い」の枝を通らない。公式の文書（https://code.claude.com/docs/en/plugin-evals ）にも「The Artifact tool is off.」とあり、使える道具は `allowed_tools` の読む道具と `--allow-tools` で許したものだけ（Monitor は `--allow-tools` に足さなければ使えない。ArtifactData は文書に無く、観察だけ）。`--allow-tools` に Monitor を足すと、live-stops-without-tools の前提が崩れる。
- 前提：ケースの点は採点の重みつきの平均で、ケースの合否の線は `--threshold`（ラウンド 1b の点 0.67・0.75・0.50 は、重み 1 の平均と合う）。公式の文書にも「A run's score is the fraction of its graders that passed, weighted if you set weights, and the case's score is the mean across its runs.」とある。
- 前提：regex の `target: trace` は、セッションの全部のメッセージを JSON の 1 行ずつで見る（公式の文書 https://code.claude.com/docs/en/plugin-evals ）。サブエージェント（pipe-builder）のメッセージと道具の呼び出しも入ることは、文書には書かれておらず、ラウンド 3 で見たこと（観察）。
- 前提：ラウンドの間、Claude Code の版と結果の JSON の形を変えない。変わると、前の回との差は比べられない。
- 前提：root のコンテナで流した測り（Bash の結果が毎回「Exit code 1」に見え、サンドボックスから作業フォルダに書けない）でも、スキルの手順（何を呼ぶ・呼ばない・何を返す）を見る採点は読める。環境のせいで落ちた採点は、スキルやケースの不具合と分けて書く。
- 前提：（追記 2）pipe-in の本体（SDK の道）は、検査の不合格で `on_fail` の段へ戻し、`on_fail` を省くと自分の段へ戻す。審査（judge）の不合格も同じに戻す（`pipe_in/pipe/pipeline.py`）。会話の道は今も `check.judge` を断る。崩れると（たとえば審査の不合格で戻さない型が本体に入ると）、警告 W8 の条件と直し方の文を見直すことになる。
- 前提：（追記 2）haiku は、長い手順から離れた所に書いた 1 文の決まりを読み飛ばしうる（ラウンド 3 で、pipe-builder が「## 権限の拡大は差し戻す」の決まりを、手で書く道で読み飛ばした）。決まりは、それを使うその場の手順の中に置くと読まれやすい。崩れると、FR-18 の置き場所を変えても止まらない。
- 前提：（追記 2）`claude plugin eval` の `file_exists` は、glob の無い `path`（01-pipe-toml・02-readme）なら作業フォルダからの位置で読む（ラウンド 1・3 で当たった）。文字の組（`[0-9]`）を含む `path` は、ファイルがあっても当たらなかった（ラウンド 3）。`*` を読むかは確かめていない。
- 前提：（追記 3）Claude Code（v2.1.271 以降）は、auto モードのとき、Agent の道具が手元で動かすサブエージェント（fork を除く）に `SubagentHandback` を渡す。定義の `tools` に無くても、`disallowedTools` にあっても渡す。PreToolUse のフックがこの呼び出しを止めると、3 回まで呼び直させ、それでも止まると、サブエージェントは報告を渡さずに終わり、待っている会話には「届かなかった」という知らせだけが行く（公式の文書 tools-reference・hooks・sub-agents）。メインの会話が auto モードなら、サブエージェントも auto モードで動く。崩れる（名前が変わる・auto モードの外でも渡される・止めても報告が届く）と、FR-20 の許す名前と理由を見直す。
- 前提：（追記 3）`SubagentHandback` は、報告の文を、そのサブエージェントの結果を受け取る会話に渡すだけで、ファイルにも外にも書かない。auto モードでないときは、最後の返答の文が同じ会話に届く。崩れる（この道具に書き込みや外への送り出しの働きが付く）と、許すことがすり抜けの道になる。
- 前提：（追記 3）SDK の道（端末の `pipe-in`）の段は auto モードで動かない（段の `permission_mode` は `default`・`acceptEdits`・`plan` だけ）。そのため、段もその中のサブエージェント（`agents`）も `SubagentHandback` を受け取らない。崩れる（SDK の段を auto で動かせるようになる）と、`pipe_in/engine/guard.py` にも同じ許しが要る。
- 前提：（追記 3）`claude plugin eval` の結果の JSON で、`partial: true` の回と、`cases[].arms.with[].skippedPaidGraders` が真の回は、点が前の回と比べられない（公式の文書 plugin-evals：「leave `partial: true` documents and runs with `skippedPaidGraders` out of any trend you chart」）。結果の JSON を読むスクリプトは、知らない鍵を読み飛ばしてよい（同じ文書）。
- 状態を持ち、操作や出来事で移り変わるか
  - 答え：いいえ
  - 理由：変えるのはスキルとエージェントの文・能力表の 1 行（断るかを決めるだけ）・eval のケースのファイル・文書・読むだけの集計のスクリプトで、記録（`state.json`）の移り変わりや新しい状態を足さない。ラウンドをくり返すのは人（メイン）の作業の手順で、ソフトの状態ではない。

## 機能要件と受け入れ基準

テストは `tests/test_plugin_eval_rounds.py`（スキル・ケース・ガイド・版）、`tests/test_chat_output_name.py`（会話の道の名前の断り）、`tests/test_lint_judge_on_fail.py`（警告 W8）、`tests/test_guard_report_tool.py`（報告の道具とすり抜けの道）と `tests/guard_matrix.py` の `report-handback` の行、`tests/test_research_plugin_eval_rounds.py`（調査と集計）と、D0045 の決め打ちを置き換えた `tests/test_plugin_evals.py`。

### 機能要件

- FR-01（UR-02）pipe-judge のスキル（`plugin/skills/pipe-judge/SKILL.md`）は、`--runs` の範囲（1〜5）を、2 章の利用料の確認・3 章の審査役・4 章の計算より前に確かめる。範囲の外なら「`--runs` は 1〜5」と伝えて止まり、確認の問いを出さず、審査役を呼ばず、`judge-score` を流さない。
- FR-02（UR-02）pipe-judge のスキルは、最後の返事に、`judge-score` が出した JSON を、文の要約に置き換えず、```json の塊でそのまま貼る。先頭の一言（合否は人が読む材料）と短い添え書きは、塊の外に書いてよい。
- FR-03（UR-03）pipe-builder の定義（`plugin/agents/pipe-builder.md`）と段の決め方（`plugin/skills/pipe-build/references/stage-rules.md`）に、名前の決まりを書く。指示文（`prompts/`）と成果物（`output`）の名前は、頭に段の順の 2 桁の番号と `_` を付ける（例 `prompts/01_summary.md`・`01_summary.md`）。段の指示文で書かせるほかのファイルと、段の中のサブエージェント（`agents`）に書かせるファイルも、`report`・`summary`・`findings`・`analysis` で始まる `.md` にしない。理由（Claude Code は、サブエージェントからのその名前の Write を断る。pipe-builder はサブエージェントで、会話の道では段もサブエージェントで流れる）を添える。
- FR-04（UR-04）会話の道の能力表（`pipe_in/pipe/capability.py`）に、段の成果物の名前の行を足す。`output` が上の断られる形（頭が report・summary・findings・analysis で `.md` で終わる。大文字と小文字を区別しない）に当たる段は、会話の道で断る。断る文には、段の名前・理由（Claude Code がサブエージェントの書き込みを断る）・直し方（頭に番号を付ける。例 `01_summary.md`）を入れる。SDK の道の列は「効く」のままにする。
- FR-05（UR-04）`docs/guide/pipes.md` の「会話の中で流すとき」の断る表に、その形と理由を足す。
- FR-06（UR-05）eval のケース build-passes-check に、`pipe-in-gen check` が通ったこと（成功の行が出たこと）を見る採点を足す。check を呼んだだけでは合格にしない。その採点が落ちたら、ケースの点が合格の線（0.8）を下回る重みにする。
- FR-07（UR-05・UR-03）build-passes-check に、指示文が頭に番号の付いた名前で書かれたことを見る採点を足す。
- FR-08（UR-05）build-refuses-judge-only の「悪い形（command が無いのに on_fail と judge）が無い」採点を、`pipe.toml` が作られなかったときに grader threw で落ちない形にする。悪い形が書かれたときは落ちる。
- FR-09（UR-05）pipe-run のケースを 2 本足す（どちらも cheap）。(a) `chat start --dry-run` の段の表を見せて開始の確認を問い、始めない（`--dry-run` の無い `chat start` を流さない・エージェントを呼ばない）。(b) 会話の中で流せない形（例：`group`）のパイプでは、断る理由を見せて止まる（始めない・エージェントを呼ばない）。
- FR-10（UR-05）pipe-live のケースを 1 本足す（cheap）。Artifact・ArtifactData・Monitor が無い会話では、`pipe-in live page --out`・`pipe-in live watch` を流さず、何も書かず、道具が無いことを伝えて止まる。D0045 の対象外（pipe-live のケース）のうち、この「道具が無い」の枝だけを足す。
- FR-11（UR-05）ケースの形の検査（`tests/test_plugin_evals.py`）を、スキル 5 つとケースの数の表（pipe-build 3・pipe-eval 3・pipe-judge 3・pipe-run 2・pipe-live 1。全部で 12 本）に合わせる。D0045 の「9 本・スキルごとに 3 本」と、変えた採点に合わせて D0045 のテストの決め打ち（数・`SKILLS`・`CASES`・見本のファイルの表・build-refuses-judge-only の target・ガイドの語）を置き換え、docstring に D0096 を書く。ほかの決まり（費用のかからない型が各ケースに 3 つ以上・`llm` は全体で 2 つ以下・`allowed_tools`・見本の作り方など）は今のまま。
- FR-12（UR-06・UR-01）`docs/guide/plugin.md` の「プラグインの eval」に、ラウンドの回し方を書く：haiku と審査役 haiku・`--runs 1`・`--ablation none`・`-j`・`--json` と `--output-dir` を `plugin/` の外へ・`--max-cost-usd` の目安と測った費用。非編集の入れ方（`pip install .` を home の外へ。編集用の `-e` だとサンドボックスから元のフォルダが見えず `ModuleNotFoundError` になる）。root で流さないこと（理由つき）。実機で確かめられたこと（D0045 の「まだ」の一覧のうち確かめたもの）。12 本の表。まだ確かめていないことは、そう書く。
- FR-13（UR-06）調査 `docs/research/plugin-eval-rounds/README.md` を作る（問い・結論・方法・結果・限界・pipe-in への示唆・やり直し方）。ラウンドごとの節（1a・1b・2 から）に、ケースごとの点・合否・落ちた採点と原因の切り分け・費用・時間を書く。目次 `docs/research/README.md` に 1 行足す。
- FR-14（UR-06・UR-01）集計のスクリプトを調査のフォルダに置く。`claude plugin eval` の結果の JSON を回の順に 1 つ以上読み、ケースごとの点・合否・落ちた採点の名前と、前の回との差を、Markdown の表で標準出力に出す。標準ライブラリだけで、LLM・子プロセス・ネットワークを使わず、ファイルを書かない。
- FR-15（UR-01）ラウンドを回す（検証の段でメインが回す）。haiku（審査役も haiku）・`--runs 1`・`--ablation none`・`--max-cost-usd 0.5` で全ケースを流し、落ちた採点を、スキルの不具合・ケースの不具合・環境のどれかに分け、直して（テスト先行で）、また回す。止めどきは、全ケースが合格した回が出るか、ラウンド 5 まで。止める前に、全ケースを `--runs 3 --threshold 0.8`（haiku・審査役 haiku・`--max-cost-usd 1.5`）で 1 回流す。回の数と上限は推しの案で決めた（`--auto` のため人の確認は無し）。
- FR-16（UR-07）`plugin/.claude-plugin/plugin.json` の `version` を 0.6.1 に上げる。ガイドの「版を上げる決まり」と更新の節に、0.6.1 で変わったこと（pipe-judge の断り方と返し方・pipe-builder の名前の決まり、会話の道の新しい断りは `pipe-in-gen` を入れ直すと効くこと）を書く。版を見張る今のテスト（`tests/test_plugin.py`・`tests/test_chat_plugin.py`・`tests/test_plugin_directory.py`・`tests/test_plugin_evals.py` の 4 か所）を 0.6.1 に合わせ、docstring に D0096 を書く。
- FR-17（UR-01）pipe-builder の定義（`plugin/agents/pipe-builder.md`）の「## 作るとき」に、`pipe-in-gen new` が失敗したとき（書けない・ひな形が合わないなど）の進め方を書く。ひな形を使わずに、確認の取れた表どおりに Write で `pipe.toml`・`prompts/NN_<段>.md`（名前の決まりどおり）・`README.md` を手で書き、`pipe-in-gen check` が通るまで直す（直すのは今までどおり 3 回まで）。`new` の失敗の理由と、手で書いたことは返事に書く。同じ名前のパイプがあって止まったとき（手で書くと上書きになる）と、フックに止められたときは、今までどおり差し戻す（すり抜けない）。Write も書けなければ、書けたファイルと理由を返して止まる。`--force` を付けて流し直さず、Bash で書く道を探さない。書ける範囲（フックが許す、パイプのフォルダの `pipe.toml`・`README.md`・`prompts/*.md`）は広げない。（検証の 1 回目のラウンド 2 で、同じ `new` の失敗のあと、止まって差し戻すか手で書くかがモデルの判断で揺れたため）
- FR-18（UR-08・UR-01）審査だけで差し戻す形（`check` に `judge` と `on_fail` があるのに `command` が無い段）を、任せる前と書く前に止める。pipe-build のスキル（`plugin/skills/pipe-build/SKILL.md`）は、「## 3.」で pipe-builder を呼ぶ前に、表（依頼に「確認済み」とあっても）にその形の段が無いかを見て、あれば任せず、`references/stage-rules.md` の決まり（審査で差し戻すなら必ず `command` と組む）と、`command` と組む案・`on_fail` をやめて指摘だけにする案を見せて、どちらにするかを聞く。pipe-builder の定義（`plugin/agents/pipe-builder.md`）は、「## 作るとき」で書く前（`pipe-in-gen new` を流す前と、`new` が失敗して手で書く前）にその形を見て、当たれば `new` も Write も使わずに差し戻す（「## 権限の拡大は差し戻す」の 2 段落目の決まりを、作る手順の中から指す）。`stage-rules.md` の決まりの文は変えない。（検証の 2 回目のラウンド 3 で、スキルが「確認済み」の表をそのまま任せ、pipe-builder が手で書く道でその形を書いたため）
- FR-19（UR-08）`pipe_in/pipe/lint.py` の警告に W8 を足す。`check` に `judge` と `on_fail`（ほかの段を指しても、自分を指しても）があり `command` が無い段で、1 件出す（`verdict` の有無によらない。`on_fail` を書かない段・`judge` の無い段・`command` のある段には出さない）。誤りにはしない（`check_pipe` の返り値・終了コード・SDK の道と会話の道の流れは変えない）。文は「段 i（名前）: 」で始め、決まり（審査で差し戻すなら `command` と組む）と直し方（`command` と組む・組めないなら `on_fail` を書かずに指摘だけにする）を書く。W8 は段ごとの警告の最後に出し、今の警告（W1・W3・W5・W6・W7）の文と順は変えない。ひな形と見本には出ない。`pipe-in-gen check` と `pipe-in-gen new` は今の出し方（`⚠` の行）で出す。`docs/guide/pipes.md` の「検査の警告」を 6 つにして W8 の説明を足す。
- FR-20（UR-09）プラグインのフック（`generator/guard_hook.py`・`generator/chat_hook.py`）は、道具の名前がちょうど `SubagentHandback`（報告を親の会話に渡すだけの道具）で、`agent_type` が文字列の呼び出しを止めない。pipe-judge・pipe-builder・pipe-probe・pipe-stage（段が開いているか・記録が読めるかによらない）と、会話の中で段が開いている間・記録が読めないときのほかのエージェントに効く（通す範囲は推しの案で書いた。決めきれない点 5）。許す名前は `guard_hook.py` の 1 つの定数に置き、`chat_hook.py` はそれを使う。`agent_type` が文字列でも null でもない呼び出し・入力が読めないとき・判断の途中の例外では、今までどおり止める。`agent_type` が無い・null の呼び出し（会話本体）には、今までどおり何もしない。名前の違う道具（大文字と小文字の違い・前後の空白・似た名前・`mcp__` の形）と、ほかの道具の判断は変えない。`pipe_in/engine/guard.py`（SDK の道と共有）と `.claude/hooks/pipe_in_guard.py`（開発用。D0004 から通している）は変えない。（検証のあとの助言 V-01。auto モードでは、pipe-judge の JSON などの報告が親に届かずに終わるため）
- FR-21（UR-01・UR-06）集計のスクリプト（`docs/research/plugin-eval-rounds/rounds.py`）は、比べられない回を前の回との差に入れない。(1) `partial` が真の回は、その回のどのケースも差を「比べられない」と出し、表の下にそう書き、次の回の差の基準にしない。次の回は、前の回のうち途中で止まっていない一番近い回と比べ、それが直前の回でないときは、表の下に基準の回の名前を書く（比べ方は推しの案で書いた。決めきれない点 6）。(2) `cases[].arms.with[]` の `skippedPaidGraders` が真の回を含むケースは、その回でも、その回を基準にする次の回でも、そのケースの差を「比べられない」と出し、表の下にそのケースの名前を書く。この鍵は、無ければ偽と読み、真偽でなければ場所を示して止まる。(3) `cases[].runsPerCase` は読まない（無くても、形が違っても止まらない。推しの案で書いた。決めきれない点 7）。表の列・頭の 2 行の形・ほかの止まる条件と終了コード（NFR-04）は変えない。（検証のあとの助言 V-07）

### 受け入れ基準

- D0096-AC-01（FR-01）pipe-judge の SKILL.md で、`--runs` の範囲を確かめて断る文が、2 章（利用料の確認）・3 章（審査役を呼ぶ）より前にあり、範囲の外なら確認を出さない・審査役を呼ばない・`judge-score` を流さないと書かれている（pytest）。
- D0096-AC-02（FR-02）pipe-judge の SKILL.md の 5 章に、`judge-score` の JSON を要約に置き換えず、```json の塊でそのまま貼ることが書かれている（pytest）。
- D0096-AC-03（FR-03）pipe-builder.md と stage-rules.md に、頭に 2 桁の番号と `_` を付ける名前の決まりと、避ける 4 つの語（report・summary・findings・analysis）と、Claude Code がサブエージェントの Write を断るという理由が書かれている（pytest）。
- D0096-AC-04（FR-03）ひな形（`generator/templates/`）と見本（`examples/`）のパイプの `output` と `prompt_file` の名前が、断られる形に当たらない（pytest。今の作りのままで通る。守る）。
- D0096-AC-05（FR-04・NFR-03）成果物の名前が `summary.md`・`Report.md`・`FINDINGS_x.md`・`analysis-1.md` の段を持つパイプで、`chat start --dry-run` と `chat start` が断り（`ok: false`）、文に段の名前と直し方（頭に番号を付ける）が入る。作業フォルダに何も増えない（pytest）。
- D0096-AC-06（FR-04・NFR-03）成果物の名前が `01_summary.md`・`10_report.md`・`summary.txt`・`my_report.md`・`summarize.md` の段は、会話の道で断られない（pytest）。
- D0096-AC-07（FR-04・NFR-03）`summary.md` の段を持つパイプは、`check_pipe` が誤りを返さず、能力表の SDK の列は「効く」のまま。SDK の道の流れのテストは書き換えずに通る（pytest）。
- D0096-AC-08（FR-04）能力表の検査（D0082-AC-01・02・07・10 のテスト）と、今の断る文のテスト（D0082-AC-04・05）が通る。新しい断る文は、段ごとの文の決まった位置に出て、今ある断る文は 1 文字も変わらない（pytest）。
- D0096-AC-09（FR-05）`docs/guide/pipes.md` の断る表と、能力表の「断る」の集合が同じ（D0082-AC-08 のテストが通る）（pytest）。
- D0096-AC-10（FR-06）build-passes-check の新しい採点の正規表現は、`✓ パイプ「notes-summary」: 問題ありません` と `✓ パイプ「notes-summary」: 誤りはありません（注意 1 件）` に当たり、`✗` の誤りの行・pipe-builder.md の説明の文（「問題ありません」か「誤りはありません（注意 N 件）」になるまで）・`pipe-in-gen check notes-summary` のコマンドの文字だけには当たらない。その採点だけが落ちたときの、重みつきの点が 0.8 を下回る（pytest）。
- D0096-AC-11（FR-07）build-passes-check に、`.pipe-in/pipes/pipe-in-notes-summary/prompts/` の下に頭が番号の指示文があることを見る採点がある（pytest で形を見る）。
- D0096-AC-12（FR-08）build-refuses-judge-only の悪い形の採点は、`target` にファイルを指さず（ファイルが無くても grader threw にならない）、悪い形の文字（JSON の文字列にしたものも）に当たり、良い形（`command` と組んだ形）・stage-rules.md の例・ひな形の `pipe.toml` の文字には当たらない（pytest）。
- D0096-AC-13（FR-09）pipe-run のケース 2 本があり、本文は `/pipe-in:pipe-run` で始まり、tags は cheap。`--dry-run` の付いた `chat start` を呼んだことを見る採点・`--dry-run` の無い `chat start` を呼ばない採点・エージェントを呼ばない採点を持つ（pytest）。
- D0096-AC-14（FR-09）pipe-run の 2 本の見本を tmp_path に作って司会役の `start`（`dry_run`）に渡すと、(a) は断られずに段の表が返り、(b) は断られる（子プロセスを起こさない）（pytest）。
- D0096-AC-15（FR-10）pipe-live のケース 1 本があり、本文は `/pipe-in:pipe-live` で始まり、tags は cheap。`live page --out`・`live watch` を呼ばない採点・Write を呼ばない採点・道具が無いことを伝える語の採点を持つ（pytest）。
- D0096-AC-16（FR-11）ケースの検査が、スキル 5 つ・12 本の表で通る。表に無いケースのフォルダ・ケースの無いスキル・数の違うスキルを、壊した入力で落とす。D0045 のほかの検査（AC-02〜12）は、新しい 3 本にもかかる（pytest）。
- D0096-AC-17（FR-12）ガイドの「プラグインの eval」の節に、ラウンドの語（`--model haiku`・`--judge-model haiku`・`--max-cost-usd`・`pip install .`・root・測った費用）と 12 本のケース名がある（pytest）。
- D0096-AC-18（FR-13）調査の本文に 7 つの節（問い・結論・方法・結果・限界・pipe-in への示唆・やり直し方）があり、目次の表がそのフォルダを指し、ラウンド 1 の数字（5/9・0.68・0.84・$0.11）がある（pytest）。
- D0096-AC-19（FR-14・NFR-04）集計のスクリプトに偽の結果の JSON を 2 つ渡すと、ケースごとの点と前の回との差の表を出して終了コード 0。鍵の欠け・壊れた JSON・ケースが 0 件の JSON は、理由の 1 行と終了コード 1（pytest）。
- D0096-AC-20（FR-14・NFR-02）偽の結果の JSON に入れた絶対パス・メールアドレス・モデルの返事の文が、集計の出力に出ない。調査のフォルダに手元のパス・鍵・メールアドレスが無い（pytest）。
- D0096-AC-21（FR-14）集計のスクリプトは標準ライブラリだけを import し、子プロセス・ネットワーク・ファイルの書き込みを使わない（pytest。import と呼び出しの検査）。
- D0096-AC-22（FR-16）`plugin.json` の `version` が 0.6.1 で、ガイドの「版を上げる決まり」に 0.6.1 があり、更新の節に 0.6.1 で変わることと `pipe-in-gen` の入れ直しがある（pytest）。
- D0096-AC-23（FR-15・NFR-01）（実機）ラウンド 2 から、haiku・審査役 haiku・`--runs 1`・`--ablation none`・`--max-cost-usd 0.5` で全ケースを回し、どの回も上限で止まらない。回ごとのケースの点・合否・費用・時間・前の回との差を調査に書く。
- D0096-AC-24（FR-15・FR-01・FR-02・FR-08）（実機）最後のラウンドで、1b で落ちた 4 本（build-refuses-judge-only・judge-calls-judge-score・judge-must-violation-fails・judge-rejects-bad-runs）の落ちた採点が通る。通らない本は、スキル・ケース・環境（root）のどれによるかを調査に書く。
- D0096-AC-25（FR-03・FR-06・FR-07）（実機）build-passes-check の回で、pipe-builder の指示文の Write が断られず、新しい check の採点が当たる（check が通った）。当たらなければ理由を調査に書く。
- D0096-AC-26（FR-09・FR-10）（実機）足した 3 本が読み込みエラーなしに読まれ、点が出る。pipe-live のケースの回で、Artifact・ArtifactData・Monitor が無かった（ToolSearch でも出なかった）ことを trace で確かめる。
- D0096-AC-27（FR-15・NFR-01）（実機）止める前に、全ケースを `--runs 3 --threshold 0.8`（haiku・審査役 haiku・`--max-cost-usd 1.5`）で 1 回流し、終了コード・各ケースの合否・費用を調査に書く。
- D0096-AC-28（FR-06）（手で）1b の結果（build-passes-check の trace）が `plugin/` の外に残っていれば、新しい check の採点の正規表現を当て、当たらない（偽の合格を捕まえる）ことを確かめる。残っていなければ、確かめていないと書く。
- D0096-AC-29（FR-17）pipe-builder.md の「## 作るとき」に、`pipe-in-gen new` が失敗したときは、ひな形を使わずに確認の取れた表どおりに Write で `pipe.toml`・`prompts/`・`README.md` を書き、`pipe-in-gen check` が通るまで直し、失敗の理由を返事に書くことと、同じ名前のパイプがあって止まったとき・フックに止められたときは差し戻すことが書かれている。その節は `--force` での流し直しも Bash で書く形（`mkdir`・`cat`・`tee`・`echo`・`python -c`）も勧めず、「## 触ってよい範囲」の Bash のコマンド（`pipe-in-gen list` / `new` / `check` だけ）とすり抜けない決まりは今のまま（pytest）。
- D0096-AC-30（FR-18）pipe-build の SKILL.md の「## 3.」で、pipe-builder を呼ぶ行（「確認が取れたら」で始まる行）より前に、表を見ること（依頼に「確認済み」とあっても）・`check` に `judge` と `on_fail` があり `command` が無い段があれば任せないこと・`stage-rules.md` の決まり・`command` と組む案と `on_fail` をやめて指摘だけにする案を見せて聞くことが書かれている。「確認が取れたら」の行は残る（pytest）。
- D0096-AC-31（FR-18）pipe-builder.md の「## 作るとき」で、「1. `pipe-in-gen new` …」の行より前に、書く前に表を「権限の拡大は差し戻す」に照らし、`judge` のある `check` に `on_fail` があり `command` が無い段があれば（「確認済み」とあっても）`new` も Write も使わずに差し戻すことが書かれている。手で書く箇条（「1.」と「2.」の間）にも、その形（`judge`・`on_fail`・`command`）なら手で書く前に差し戻すことが書かれている。「## 権限の拡大は差し戻す」の 2 段落目は残る（pytest）。
- D0096-AC-32（FR-18）足した文を含む pipe-build の SKILL.md と pipe-builder.md の全文は、生のままでも JSON の文字列にしても、build-refuses-judge-only の 01-no-bad-shape と build-passes-check の 07-check-passed に当たらず、`evals` の語を持たない。名前の決まりと手で書く道のテスト（D0096-AC-03・29）は書き換えずに通る（pytest）。
- D0096-AC-33（FR-19）`check` に `judge` と `on_fail` があり `command` が無い段（`on_fail` がほかの段を指すとき・自分を指すとき・`verdict` もあるとき）に、`lint_pipe` が W8 を 1 件だけ出す。文は「段 i（名前）: 」で始まり、`judge`・`on_fail`・`command` と、直し方の 2 つ（`command` と組む・`on_fail` を書かずに指摘だけにする）を含む（pytest）。
- D0096-AC-34（FR-19）`on_fail` を書かない段（`judge` だけ・`judge` と `verdict`）・`judge` の無い段（`verdict` と `on_fail`・`command` と `on_fail`）・`command` のある段（`judge` と `on_fail` と `command`）には、W8 が出ない（pytest）。
- D0096-AC-35（FR-19・NFR-05）W1・W3・W5・W6・W7 が出る定義の 1 つの段に `judge` を足して W8 の条件を満たすと、足す前の警告の文と順は変わらず、W8 はその段の警告の最後に、段の順を保って出る。`check_pipe` は誤りを返さず、`pipe-in-gen check` は終了コード 0 で「誤りはありません（注意 N 件）」の行と、W8 を含む `⚠` の行を出す（pytest）。
- D0096-AC-36（FR-19）ひな形 5 つ（`pipe-in-gen new` で写したもの）と見本（`examples/` の 4 つ）は、W8 を含めて警告 0 件のまま。審査を持つ段（`diagrams` のひな形と見本・`research` の見本）は `command` と `on_fail` を両方持つ（pytest）。
- D0096-AC-37（FR-19）`docs/guide/pipes.md` の「検査の警告」の節が「警告は6つ」と書き（「警告は5つ」は残らない）、W8 の説明（`judge`・`on_fail`・`command`・指摘だけ）を持つ（pytest）。
- D0096-AC-38（FR-20・NFR-06）pipe-judge と pipe-builder（`pipe-in:`・`xyz:` の付いた名前も）の `SubagentHandback` は、入力が `{"message": "報告"}`・空・無い・辞書でないのどれでも、`guard_hook.decide` で止まらない。`pipe-in-gen guard-hook` の入口（標準入力）でも、deny の JSON を出さずに終了コード 0 で終わる（pytest）。
- D0096-AC-39（FR-20・NFR-06）会話の道（`chat_hook`）で、pipe-stage（段が開いているとき・段が開いていないとき・`state.json` が壊れているとき・`pipe.toml` が始めたときから変わったとき）、pipe-probe（確かめの前と後）、段が開いている間と記録が読めないときのほかのエージェント（`general-purpose`・`Explore`・`pipe-in:pipe-builder`・`pipe-in:pipe-judge`・`xyz:other`）の `SubagentHandback` は止まらず、跡（`hook/trace.jsonl`）の行が増えない。確かめ（`chat probe`）は、確かめ役が報告の道具を呼んでも、今までどおり、確かめ用のパスへの pipe-probe の Write を止めた跡があるときだけ通り、報告の道具だけでは通らない（pytest）。
- D0096-AC-40（FR-20・NFR-06）同じ相手（pipe-judge・pipe-builder・pipe-probe・開いた段の pipe-stage・段が開いている間のほかのエージェント）でも、似た名前（`subagenthandback`・`SUBAGENTHANDBACK`・`SubAgentHandback`・`SubagentHandback `・` SubagentHandback`・`SubagentHandbackX`・`Subagent_Handback`・`SubagentHand`・`mcp__x__SubagentHandback`・`mcp__SubagentHandback`）と、すり抜けの道（範囲外への Write・Edit・MultiEdit・NotebookEdit、範囲外の Bash、PowerShell、`mcp__x__y`、Agent、Task、WebFetch）は今までどおり止まる。道具の名前が文字列でない（無い・数・list・dict）呼び出しも止まる（pytest）。
- D0096-AC-41（FR-20・NFR-06）`agent_type` が文字列でも null でもない呼び出し（数・真偽・list・dict）の `SubagentHandback` は、記録が無いとき・段が開いているときのどちらでも、`guard_hook.decide`・`chat_hook` の入口・`pipe-in-gen guard-hook` の入口で今までどおり止まる。`agent_type` が無い・null の呼び出しは、今までどおり何もされない。判断の途中で例外が出たとき（報告の道具の判定を例外を出すものに替える）は、`SubagentHandback` も止まる（pytest）。
- D0096-AC-42（FR-20・NFR-06）4 つの守りの表（`tests/guard_matrix.py`）に `SubagentHandback` の行があり、実測の結果が、SDK の道の 2 列は止める、会話の道・プラグインの 2 役・開発用の 4 役の 7 列は許す、になる（`pipe_in/engine/guard.py` は変えない）。今ある行は、期待を書き換えずに通る（pytest）。
- D0096-AC-43（FR-20）許す名前は `guard_hook.REPORT_TOOLS`（`SubagentHandback` の 1 つだけ）にあり、`chat_hook.py` はそれを使って、同じ名前を自分で書かない。`pipe_in/engine/guard.py` の `ALWAYS_ALLOWED` に `SubagentHandback` は無く、開発用のフックの `REPORT_TOOLS` と同じ集まりである（pytest）。
- D0096-AC-44（FR-20）`plugin/hooks/hooks.json` の `description`・`docs/guide/plugin.md` のフックの行・`docs/guide/safety.md` の「会話の中で流すときの守り」と「4つの守りの比較」の表に、報告の道具（`SubagentHandback`）を止めないことが書かれ、`description` の pipe-stage・pipe-probe・pipe-builder・pipe-judge の語は残る（pytest）。
- D0096-AC-45（FR-20）（実機）auto モードの Claude Code で `/pipe-in:pipe-judge` を 1 回流し、審査役の報告（JSON）がフックに止められずに親に届き、`judge-score` まで進む。確かめられなければ、確かめていないと決定の記録に書く。
- D0096-AC-46（FR-21）`partial` が真の回は、その回のどのケースも「前の回との差」が「比べられない」になり、表の下に、途中で止まったので差を比べず次の回の基準にもしない、という注意の行が出る。頭の 2 行と、点・合格の回・落ちた採点・エラーの回の列は今までどおり出る（pytest。偽の結果の JSON）。
- D0096-AC-47（FR-21）途中で止まった回の次の回は、その前の、途中で止まっていない一番近い回と比べる（差の値・「新しい」・前の回にあってこの回に無いケース・版の違いの注意が、その回に対して出る）。表の下に、基準の回の名前と、基準にしなかった回の名前が出る。前の回がどれも途中で止まっていれば、どのケースも「比べられない」になる。注意の行に出るのは、回とケースの名前と決まった文だけ（pytest）。
- D0096-AC-48（FR-21・NFR-04）`skippedPaidGraders` が真の回を含むケースは、その回でも、その回を基準にする次の回でも差が「比べられない」になり、その回の表の下にケースの名前が出る（最初の回でも出る）。この鍵が無い・偽のケースは今までどおり差が出る。真偽でない値（文字・数・null）は、場所（`cases[i].arms.with[j].skippedPaidGraders`）を示す 1 行と終了コード 1 で止まり、標準出力に何も出さない（pytest）。
- D0096-AC-49（FR-21）`cases[].runsPerCase` が無い・0・文字・null の結果も、止まらずに表を出し、頭の行の回の数は `arms.with` の長さのまま。途中で止まっていない・`skippedPaidGraders` の無い結果の出力は今と変わらない（D0096-AC-19 と D0096-AC-20 の今のテストが、途中で止まった回の差の期待と「回の数が 0」の壊した入力のほかは書き換えずに通る）（pytest）。

### 非機能要件

- NFR-01（UR-01）
  - きっかけ：ラウンドを 1 回回す。
  - 状況：haiku・審査役 haiku・`--runs 1`・`--ablation none`・全 12 本（エージェントを呼ぶケースを含む）。
  - 応答：1 回の費用が $0.50 以下で、`--max-cost-usd 0.5` で途中で止まらない（ラウンド 1b は 9 本で $0.11）。止める前の確かめ（`--runs 3`）は $1.50 以下。
  - 測り方：回ごとの費用を調査に書き、上限で止まった回が無いことを見る。
- NFR-02（UR-06）
  - きっかけ：調査の文書と集計の出力をコミットする。
  - 状況：結果の JSON には、作業フォルダの絶対パス・モデルの返事の文・道具の出力が入っている。
  - 応答：調査の文書と集計の出力に、手元のパス・ユーザー名・鍵・メールアドレス・モデルの返事の生の文が入らない（出すのはケース名・採点のファイル名・数・合否だけ）。生の結果は `plugin/` の外に置き、コミットしない。
  - 測り方：パス・メールアドレス・長い文を入れた偽の結果の JSON を集計に通し、出力に出ないことを pytest で見る。調査のフォルダに手元のパス・鍵・メールアドレスが無いことを pytest で見る。
- NFR-03（UR-04）
  - きっかけ：前からある、成果物の名前が `summary.md`・`report.md` などのパイプを流す。
  - 状況：端末の `pipe-in --pipe`（SDK の道）か、会話の道（`chat start`・`chat start --dry-run`）。
  - 応答：SDK の道は今までどおり流れ、`pipe-in-gen check` も誤りにしない。会話の道は、記録を作る前に断り、何も書かない。番号の付いた名前（`01_summary.md` など）は、どちらの道でも今までどおり。
  - 測り方：pytest（D0096-AC-05・06・07）。今ある SDK の道のテスト（段の名前 `report` のものを含む）が書き換えなしで通る。
- NFR-04（UR-01）
  - きっかけ：Claude Code の版が変わり、結果の JSON の形が変わる。
  - 状況：集計のスクリプトが、知らない形・壊れた JSON・ケースが 0 件の JSON を読む。
  - 応答：0 点や空の表を黙って出さず、どのファイルの何が読めないかを 1 行で出し、終了コード 1 で終わる。
  - 測り方：pytest で、鍵の欠けた JSON・壊れた JSON・ケースが 0 件の JSON を渡す。
- NFR-05（UR-08）
  - きっかけ：前からある、`judge` と `on_fail` があり `command` の無い段を持つパイプを、`pipe-in-gen check`・`pipe-in-gen new`・端末の `pipe-in --pipe` で扱う。
  - 状況：W8 の入った `pipe-in-gen`（本体）。
  - 応答：`check`・`new` は `⚠` の行を 1 つ足して出すだけで、ほかに誤りが無ければ終了コードは 0 のまま。`check_pipe` の返り値・今の警告の文と順・SDK の道の流れ・記録は変わらない。
  - 測り方：pytest（D0096-AC-35）。今の警告と検査のテスト（`tests/test_pipe_lint.py`・`tests/test_generator.py` の警告の出力・`tests/test_check_judge.py`）が書き換えずに通る。
- NFR-06（UR-09）
  - きっかけ：プラグインのフック（`pipe-in-gen guard-hook`）が、道具の呼び出しを 1 つ受ける。
  - 状況：auto モードで、pipe-judge・pipe-builder・pipe-probe・pipe-stage、または会話の中で段が開いている間のほかのエージェントが、報告を返す（`SubagentHandback`）か、ほかの道具・似た名前の道具を呼ぶ。
  - 応答：止める範囲を狭めるのは、`agent_type` が文字列で、道具の名前がちょうど `SubagentHandback` の呼び出しだけ。似た名前・ほかの道具・文字列でも null でもない `agent_type`・読めない入力・判断の途中の例外は今までどおり止め、4 つの守りの表（`tests/guard_matrix.py`）の今ある行の結果は 1 つも変わらない。狭める理由（書かずに報告の文を親の会話へ渡すだけで、auto モードでないときは最後の返答の文が同じ会話に届くので、新しくできることは無い。止めると、auto モードでは報告が親に届かず、会話の道では止めた操作の跡に同じ道具が最大 4 回残る）を、決定の記録に書く。
  - 測り方：pytest（D0096-AC-38・39・40・41・42）。今ある守りのテスト（`tests/test_guard_hook.py`・`tests/test_chat_hook.py`・`tests/test_chat_probe.py`・`tests/test_guard_hook_input.py`・`tests/test_guard_hook_symlink.py`・`tests/test_guard_matrix.py` の今ある行）が書き換えずに通る。

## 決めたことと理由

- **ラウンドの回し方**：haiku・審査役 haiku・`--runs 1`・`--ablation none`・各回 `--max-cost-usd 0.5`。止めどきは、全ケースが合格した回が出るか、ラウンド 5 まで。止める前に `--runs 3 --threshold 0.8`（`--max-cost-usd 1.5`）を 1 回。要件定義の決めきれない点で推しの案を採った（`--auto`。費用が小さく、人の設定に沿うため）。ガイドのふだんの流し方の例（sonnet）は残し、ラウンドは別の小節に書いた。
- **ラウンドの経過**（調査の表のとおり）：1a 5/9・0.68 → 1b 5/9・0.84 → 2 11/12・0.94 → 3 9/12・0.94 → 4 12/12・1.00。止める前の `--runs 3` は 11/12・0.96（$0.29）。1 回あたり $0.11 前後。1a は `pip install -e .` のまま流し、サンドボックスから `pipe-in-gen` が動かなかった（環境）。
- **pipe-judge**：範囲の外の `--runs` を断る 1 行を本文の頭（0 章より前）に置き、5 章は `judge-score` の JSON を ```json の囲みにそのまま貼る形と見本にした。後ろの節に書いた決まりを haiku が読み飛ばしたため。
- **名前の決まりと会話の道の断り**：Claude Code（2.1.323 で本体の判定の文を確かめた。公式の cookbook に観察として 1 文あるが、語の一覧と判定の形は文書に無い）は、サブエージェントからの Write で、名前が `report`・`summary`・`findings`・`analysis` で始まり `.md` で終わるもの（大文字と小文字を区別しない）を断る。pipe-builder と stage-rules に「頭に 2 桁の番号と `_`」の決まりを書き、能力表の `PipeStage.output` を「SDK の道は効く・会話の道は名前の形で断る」行にした（判断の種類 `subagent_report_name` を足した）。SDK の道の段はサブエージェントでないので断らない（今まで流せたパイプを流せなくしない）。断る形は Claude Code の判定に合わせ、狭めない。実物は安全側に少しだけ広い（大文字と小文字を Unicode で区別しない・改行を含む名前も断る）。
- **D0082-AC-10 の検査を狭めた**：値の形で断る行の項目（表から取る。今は `output` だけ）を、`chat.py` に属性として出ることの検査から除いた。`chat.py` は段の表と成果物の場所のために `s.output` を読むため。代わりに、`chat.py` がその項目を条件の中で読まない・`.startswith` などを付けない検査（`tests/test_chat_output_name.py`）を足した。
- **pipe-builder の手書きへの切り替え**：`pipe-in-gen new` が失敗したら、確認の取れた表どおりに Write で手で書き、`pipe-in-gen check` を通す（同じ名前があって止まったとき・フックに止められたときは今までどおり差し戻す）。ラウンド 1b と 2 で、同じ失敗のあとに止まるか手で書くかがモデルの判断で揺れたため。書ける範囲（フックが許す `pipe.toml`・`README.md`・`prompts/*.md`）とフックは変えていない。
- **審査だけで差し戻す形（judge と on_fail があり command が無い）**：ラウンド 3 で、pipe-build のスキルが「確認済み」の表をそのまま任せ、pipe-builder が手で書く道でその形を書き、`pipe-in-gen check` も通した（1b・2 は書けない環境だったので表に出なかった）。スキルの「## 3.」の頭（任せる前）と pipe-builder の「## 作るとき」の頭（書く前）に照らす段落を足し、スキルは自分で `command` を足さず、2 つの案（`command` と組む／`on_fail` を書かず指摘だけにする）を見せて聞く。あわせて `pipe-in-gen check`・`new` に警告 W8 を足した（誤りにはしない。前からあるパイプが SDK の道で流れなくならないように）。W8 は書いた `on_fail` だけを見る（省いた段は決まりの「指摘だけ」の形なので出さない）。
- **ケースの直し**：build-passes-check に、check が通ったこと（trace の成功の行）を見る 07（重み 2。これだけ落ちると 0.78 で線の 0.8 を下回る）と、指示文の名前を見る 08 を足した。08 の `path` は、文字の組 `[0-9]` を含む形がファイルがあっても当たらなかったので（ラウンド 3。理由は確かめていない）、glob の無い `prompts/01_summary.md` にした。build-refuses-judge-only の 01 は、ファイルが無いと採点そのものが失敗する（grader threw）ので、trace を読む `not_contains`（メッセージの境 `\n{` を越えない）にした。live の 04 は英語の言い方も拾う。
- **ケースを 12 本に**：pipe-run に 2 本（dry-run の表を見せて聞く・流せない形なら理由を見せて止まる）、pipe-live に 1 本（道具が無ければ何もせず止まる。eval の中には Artifact・ArtifactData・Monitor が無いので安く測れる）。D0045 の「9 本・スキルごとに 3 本」をテストで置き換えた。9 本の `scaffold.py` の案内の文は `pip install .` にそろえた（編集用の入れ方はサンドボックスから見えないため）。
- **調査と集計**：結果は `docs/research/plugin-eval-rounds/` に置き、集計 `rounds.py`（標準ライブラリだけ・読むだけ・知らない形は終了コード 1）で、回ごとの表と前の回との差を出す。生の結果の JSON は手元のパスとモデルの返事を含むので、コミットしない。検証の 1 回目で、`runsPerCase` は `--runs` で上書きしてもケースの既定の 3 のままと分かり、回の数を `arms.with` の長さから出すように直した。
- **報告の道具を止めない（守りを狭めた。助言 V-01）**：auto モードでは、サブエージェントの報告は `SubagentHandback` で親に届く（Claude Code v2.1.271 以降。`tools` に書かなくても渡される）。プラグインのフックは pipe-judge・pipe-builder・pipe-probe・pipe-stage・段が開いている間のほかのエージェントでこの道具を止めていたので、auto モードでは報告が親に届かず（止めると 3 回まで呼び直させたあと報告なしで終わる）、会話の道では止めた操作の跡に同じ道具が最大 4 回残っていた。`generator/guard_hook.py` に許す名前の一覧 `REPORT_TOOLS = frozenset({"SubagentHandback"})` と判定 `is_report_tool` を置き、`agent_type` が文字列で、道具の名前がちょうどその名前のときだけ、段や記録の状態によらず通す（`decide` と `chat_hook._agent` の頭の 2 か所）。狭める理由：書かず、外へも出さず、報告の文を親の会話へ渡すだけで、auto モードでないときは最後の返答の文が同じ会話に届くので、新しくできることは無い。開発用のフック（`.claude/hooks/pipe_in_guard.py` の `REPORT_TOOLS`）は前からこの扱い。すり抜けの道が開かないこと（似た名前 10 通り・大文字小文字・`mcp__` の形・範囲外の Write・Edit・MultiEdit・NotebookEdit・Bash・PowerShell・MCP・Agent・Task・WebFetch・文字列でない道具の名前・型のおかしい `agent_type`・判断の途中の例外・報告の道具で確かめ（`chat probe`）を偽れないこと）を `tests/test_guard_report_tool.py` で、4 つの守りの表の今ある行の結果が 1 つも変わらないことを `tests/guard_matrix.py` で見る（新しい行 `report-handback` は SDK の 2 列だけ止める `DDAAAAAAA`）。`pipe_in/engine/guard.py`（SDK の道と共有。SDK の道の段は auto モードで動かず、この道具を受け取らない）と止める文は変えていない。
- **集計の比べられない回（助言 V-07）**：公式の文書の「leave `partial: true` documents and runs with `skippedPaidGraders` out of any trend you chart」に合わせ、`rounds.py` は途中で止まった回のケースと、審査の採点を飛ばした回を含むケースの差を「比べられない」と出し、途中で止まった回の次は、その前の途中で止まっていない一番近い回と比べる（表の下に基準の回の名前）。`runsPerCase` は読まない（使っていない値の形で止まらない）。`skippedPaidGraders` が真偽でなければ止まる。ラウンド 1b〜4 と止める前の回の本物の結果では、`partial` も `skippedPaidGraders` もどれも `false` で、表は変わらなかった。
- **版**：`plugin.json` を 0.6.0 → 0.6.1。スキル・エージェントの直しで、新しいスキルは無い。会話の道の断り・W8・報告の道具を止めないことは、`pipe-in-gen` を入れ直すと効く（フックは `pipe-in-gen guard-hook` で動くため）。

選ばなかった形：

- 上位のモデル（sonnet）でラウンドを回す：人の設定が下位のモデル。haiku で通る文は上位のモデルでも通る見込みが高い。
- 非 root のユーザーを作って測る：この環境の権限の判定で止められた。root の測りの限界は調査に書いた。
- W8 を誤りにする：前からあるパイプが SDK の道で流れなくなる。
- 会話の道の断りを SDK の道にも入れる：SDK の道の段はサブエージェントでなく、断ると今まで流せたパイプが流せなくなる。
- build-refuses-judge-only の 01 を Write の `input_match` にする：Edit で段を足す道を全く見ない。trace は Write・Edit・返事を同じ形で見る。
- 判断を `chat.py` に置く：D0082 の「`chat.py` に項目の名前の条件を足さない」に反する。
- 報告の道具を `pipe_in/engine/guard.py` の `ALWAYS_ALLOWED` に足す：SDK の道と共有で、SDK の道の段はこの道具を受け取らないので要らず、変える範囲が広がる。
- 報告の道具を、読む道具を通している所だけで通す：止まった段やエージェントが、止められた訳を親に返せない。
- check が通ったことを、公式の文書の勧める形（結果をファイルに書かせ、そのファイルを採点する）で見る：pipe-builder が書けるのはパイプのフォルダの `pipe.toml`・`README.md`・`prompts/*.md` だけ（フック）なので取れない。代わりに 04（`pipe-in-gen check` を呼んだ）と 07（trace の成功の行）を組にした。07 は trace の全部を見るので、モデルが返事に写した成功の行にも当たる（モデルが成功の行を作り出したときだけ偽の合格になる）。

受け入れたリスク：

- サブエージェントの書き込みを断る決まりは、公式の文書の決まりとしては無い（cookbook に観察の 1 文だけ）。決まりが無くなると会話の道の断りは要らない断りになり、語が増えると断りが足りなくなる。判断は `capability.py` の `SUBAGENT_REFUSED_HEADS` と `subagent_refused_name` の 1 か所にまとめた。ただし 4 つの語は、断る文・理由の文（同じファイル）と、`pipes.md`・`plugin.md`・`stage-rules.md`・`pipe-builder.md` にも書いてあるので、決まりが変わったら一緒に直す。
- 01-no-bad-shape（trace の正規表現）は、Edit で少しずつ作った悪い形・インラインの表の形を見落とす。W8 が機械の側で拾う。
- 08 は、番号は合っていても違う名前（`01_summarize.md` など）だと落ちる。
- 報告の道具の名前（`SubagentHandback`）が Claude Code の版で変わると、また止まる（そのときは `REPORT_TOOLS` の 1 か所を直す）。似た名前の新しい道具は、一覧に無いので止まる側に倒れる。

## 対象外・残った課題

- `claude plugin eval` を CI で流すこと（利用料。D0045 のまま）。上位のモデルでのラウンド。
- **judge-rejects-bad-runs の揺れ**：止める前の `--runs 3` で、3 回のうち 1 回、haiku が頭の「最初に `--runs` を見る」を読み飛ばし、審査役を呼んで `judge-score` を流した。この回は記録（trace）を残さずに流したので、採点の説明でしか見ていない。文だけの決まりは揺れが残る。次のラウンドの候補：`--runs` の範囲を `pipe-in-gen` の側で機械的に断る（例：`judge-score` の前に範囲を確かめるコマンド）。
- build-refuses-judge-only は、`--runs 3` で 1 回だけ、正しく止まったのに言い回しが 02-says-command に当たらなかった（ケースの点は線を越えた）。言い回しの採点の広げ方は次のラウンドで見る。
- root でない環境での測り。root のコンテナでは、サンドボックスの Bash から作業フォルダに書けず（`pipe-in-gen new` が失敗する）、Bash の結果が毎回「Exit code 1」に見えた。`new` が通る環境での build のケースは、まだ確かめていない。
- 決まりの言い方の食い違い：`stage-rules.md` は「`on_fail` を書かず指摘だけにする」と言うが、本体は `on_fail` を省いても審査の不合格で自分の段をやり直す。W8 の文と直し方に注意を添えたが、決まりの言い方の見直しはしていない。
- pipe-live の、道具がある会話での動きのケース。pipe-run で段を実際に流すケース。
- 拡張の作業台の検査（`validatePipe`）と `generator/design_rules.md` への W8 と名前の決まりの追記。
- W8 を、`on_fail` を省いた審査だけの段にも出すか（監査 A-01。本体は省いても自分の段をやり直すので、決まりの言い方は直したが、警告の条件は変えていない）。
- `--runs` の範囲を機械で断る道の候補として、スキルの `` !`command` ``（Claude が読む前にコマンドを流す）を調べる（助言 V-09。`!` の中で `$ARGUMENTS` が展開されるかは文書に無く、確かめていない）。
- 段の指示文が書かせるほかのファイルや、段の中のサブエージェント（`agents`）が書くファイルの名前を、流す前に見ること（定義から分からない。stage-rules に書くだけ）。

## 確かめたこと

- 監査と助言の直しのあと、ラウンド 5（haiku・`--runs 1`・上限 $0.5）を回し、12 本とも合格した（1.00・$0.12・79 秒）。
- 実機（D0096-AC-45）：auto モードの Claude Code で `/pipe-in:pipe-judge` を流し、審査役の報告が届くこと・止めた操作の跡に報告の道具が残らないことは、まだ（eval の回は auto モードでなく、ラウンドでは見られない）。

- D0045 で「まだ」だった AC-17〜21 のうち、ラウンドで確かめたもの：AC-17（ケースが読まれ、スラッシュ呼びが展開され、`file_exists` の基準と `not_contains` の扱いが分かった）・AC-18（安いケース 1 本の費用 約 $0.004）・AC-19（`--runs 3 --threshold 0.8` を 12 本で流した）・AC-20 の前半（フックが pipe-builder のパイプのフォルダへの正しい書き込みを止めなかった）。AC-20 の後半（範囲の外を止める）と AC-21（手での確かめ）は、まだ。

- テスト：全体の `python -m pytest -q`（決定の記録を書く前）は 1 failed・18544 passed・5 skipped で、落ちたのは決定の記録が無いための `tests/test_rules.py::test_ac_ids_in_tests_exist_in_records` だけ（この記録で通る）。拡張は触っていないので流していない。`python -m pipe_in skill spec-check` は UR 8・FR 19・NFR 5・AC 37・問題 0 件。
- 実機（D0096-AC-23〜27）：ラウンド 2・3・4 を haiku・`--runs 1`・`--max-cost-usd 0.5` で回し、どの回も上限に届かなかった（$0.11・$0.12・$0.11）。最後のラウンド 4 で、1b で落ちた 4 本・build-passes-check（pipe-builder の Write が断られず、07・08 が当たった）・足した 3 本（live の回の道具の一覧に Artifact・ArtifactData・Monitor が無く、ToolSearch でも出なかった）が合格した。止める前の `--runs 3 --threshold 0.8` は終了コード 1・11/12・0.96・$0.29（上の残った課題）。
- 手で（D0096-AC-28）：ラウンド 1b の記録（trace）に、新しい 07 と 01 の正規表現を当てた。07 は当たらず（偽の合格を捕まえる）、01 も当たらなかった（正しく断った回を落とさない）。1b の trace にもサブエージェントのメッセージが入っていた。
### 監査と助言で直したもの

監査 14 件・助言 9 件（審査役の採点：overall 0.85・pass。事実の正確さ 1.0・引用の正確さ 0.75・網羅性 0.75・情報源の質 1.0・ツール効率 0.75）。人がすべてを直すと選んだ。

- 監査：A-01（stage-rules の表の「差し戻さず」を直し、pipe-builder に「`on_fail` を省いても自分の段をやり直す」を添えた。W8 の条件は残った課題）・A-02（上の D0045 の AC の行）・A-03・A-04（判断の 1 か所と、安全側に少し広いことをこの記録に書いた）・A-05（ガイドの tag の説明）・A-06（build-refuses-judge-only の説明）・A-07（pipe-run の 01-dry-run を `"command"` の鍵に結んだ）・A-08（ガイドと CLAUDE.md の pytest の説明。CLAUDE.md は人が承認した案）・A-09（名前の決まりの「指示文が書かせるほかのファイル」を会話の道で流すパイプに絞り、見本 research の `report.md` は SDK の道なので当たらないと書いた）・A-10（テスト名と、evals/ に頼らないことを見るファイルの一覧）・A-11（テストの docstring）・A-12（design.md の lint.py の読み先）・A-13（pipe-build の権限の一覧に許可の型）・A-14（ガイドのケースを足した版）。
- 助言：V-01・V-07（上の決めたこと。テスト先行に戻した）・V-02（ガイドに完全なモデルの ID を書く勧め）・V-03（cookbook の観察の 1 文を出典に）・V-04（前提の文書と観察を分けた）・V-05（`[0-9]` の原因を言い切らない）・V-06（費用は定価の見積もり）・V-08（07 を勧めの形にしなかった理由と限界）・V-09（残った課題に書いた）。

- 検証の不合格：1 回目（ラウンド 2）は `rounds.py` の回の数と、pipe-builder が `new` の失敗で止まること。2 回目（ラウンド 3）は 08 の glob・live の 04 の英語・審査だけの形。どちらもテスト先行に戻して直した（attempt 3 まで）。
