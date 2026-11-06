# D0077 パイプを会話の中で流せる（SDK を子として起こせない場所向け。#123）

## 目的

Copilot の契約で使う VS Code の Claude ハーネスなど、Claude Agent SDK を子として起こせない場所でも、pipe-in のパイプ（`pipe.toml`）を流せるようにする。段の順番・確認・差し戻し・記録は Python の pipe-in が持ち、会話は「次の段の指示」をサブエージェントで流して結果を返すだけにする。書ける範囲は、段ごとにフックが止める。

## 機能要件と受け入れ基準

- FR-01〜03 始める・断る：`pipe-in-gen chat start` が定義を読んで検査し、扱える形なら記録を始め、扱えない形は理由を全部出して断る。会話では効かない設定は断らずに一覧で見せる。
  - D0077-AC-01：扱える形（linear・access の4種・writes・bash・review・check の verdict と command・next）で始めると、`driver: "pipe-chat"` で段の並びどおりの記録ができる（`tests/test_chat_start.py`）。
  - D0077-AC-02：group・routes・check.judge・agents・mcp・mcp_servers・web（true とドメインの一覧）・max_budget_usd・前の実行の受け取り・kind = "dev" を1つ持つパイプは、記録を作らず、形の名前と理由で断る（同上）。
  - D0077-AC-03：断る形が複数あると、理由が全部出る（同上）。
  - D0077-AC-04：model・max_turns・permission_mode などの効かない設定は断らず、「効かない設定」の一覧に出る（同上）。
  - D0077-AC-05：`check_pipe` の誤りがあると、記録を作らずに断る（同上）。
  - D0077-AC-06：途中の記録があると断り、終わった記録は `archive/` へ移す（同上）。
- FR-04 流す前の守りの確かめ（`chat probe`）。
  - D0077-AC-07：確かめが済むまで、`chat next` は段の指示を出さない（`tests/test_chat_probe.py`）。
  - D0077-AC-08：確かめの1回目は乱数入りの範囲外のパスを出し、どの access の範囲にも入らない。失敗のあとに出し直すと乱数が変わる（同上）。
  - D0077-AC-09：範囲外のファイルが無く、フックの跡に pipe-probe を止めた行があり、乱数が合うときだけ確かめ済みになる（同上）。
  - D0077-AC-10：ファイルがある・跡が無い・乱数違い・agent_type が違う・道具が違う、のどれかなら確かめ済みにならず理由を返す（同上）。
  - D0077-AC-11：確かめ済みの印は、その実行だけに効く（同上）。
- FR-05〜07 順番・確認・差し戻し・終わり（`chat next / done / review`）。
  - D0077-AC-12：`chat next` は最初の段を返し、開いている間に呼び直しても二重に始めない（`tests/test_chat_flow.py`）。
  - D0077-AC-13：review = true の段が閉じると確認待ちになり、承認の前に次の段は始まらない（同上）。
  - D0077-AC-14：approved で進み、revise は直す点が要り同じ段を直す点つきで返し、quit で中止になる（同上）。
  - D0077-AC-15：確認待ちでない review、開いていない・別の段への done は断る（同上）。
  - D0077-AC-16：成果物が無いまま done すると失敗になる（同上）。
  - D0077-AC-17：check.command の合否で進む・戻り、max_retries を超えると本体と同じ終了の種類で終わる（同上）。
  - D0077-AC-18：verdict の段は `--status` と `--problems` で戻り・進み、`--status` が無い・誤りなら断る（同上）。
  - D0077-AC-19：next で飛び、end で終わり、max_steps を超えると本体と同じ終了の種類で終わる（同上）。
  - D0077-AC-20：全段が終わると `99_summary.md` ができ、final が入る（同上）。
  - D0077-AC-21：`chat status` が段・何回目・確認待ちを返し、記録が無ければ始め方を伝えて断る（同上）。
- FR-08・09・16 記録と使用量。
  - D0077-AC-22：記録は `record check` を通り、`pipe-in --review` はこの記録の続きを流さない（`tests/test_chat_record.py`）。
  - D0077-AC-23：`usage_summary` は available = false と理由を持ち、費用は 0 ではなく null。`99_summary.md` に合計が出ない（同上・`vscode/src/domain/usageUnavailable.test.ts`）。
  - D0077-AC-24（画面）：拡張で、段の流れ・確認待ち・差し戻しが本体の記録と同じ形で出て、使用量は「取れない」と読め、`$` の数も「0 ターン」も出ない。確認待ちの答え方は会話の道のもの（`vscode/src/domain/usageUnavailable.test.ts`・`pipelineViewChat.test.ts`・`vscode/src/view/usageUnavailableHtml.test.ts`・`chatNotice.test.ts`。画面はプレビュー `run-panel-chat-*` で確かめた）。
  - D0077-AC-25：古い記録は、拡張でも `record check` でも今までどおり読める（`tests/test_chat_record.py`・`vscode/src/domain/usageUnavailable.test.ts`）。
- FR-10〜13 フック（`pipe-in-gen guard-hook`）。
  - D0077-AC-26：pipe-stage の書ける範囲は、本体の `guard.check_tool` と同じ結果になる（`tests/test_chat_hook.py`）。
  - D0077-AC-27：すり抜けの道（Bash・危険なコマンド・PowerShell・MCP・Agent・Task・Web・ノートブック・`..`・パイプのフォルダ・記録・前のパイプの記録・`.claude/`）は止まる（同上）。
  - D0077-AC-28：読む道具は、どの段でも通る（同上）。
  - D0077-AC-29：入力が読めない・agent_type が文字でない・開いている段が無い・記録が壊れている・`pipe.toml` が変わった・段が定義に無い、のときは止める（同上）。
  - D0077-AC-30：段の間は pipe-stage・pipe-probe 以外のエージェントを止め、会話本体と会話の道の記録の無い作業フォルダには何もしない（同上）。
  - D0077-AC-31：`pipe-in:pipe-stage` も pipe-stage と同じに扱い、前方・部分一致は pipe-stage と扱わない（同上）。
  - D0077-AC-32：pipe-builder・pipe-judge の判断と、`.claude/hooks/pipe_in_guard.py`・`guard.py` は変わらない（同上・`tests/test_guard_hook.py`・検証の段の `git diff`）。
- FR-13〜15 道具・プラグイン・依存。
  - D0077-AC-33：pipe-stage・pipe-probe の `tools` は決めたとおりで、Agent・Task・PowerShell・Web・MCP を含まない。前書きの鍵は name・description・tools・model だけ（`tests/test_chat_plugin.py`）。
  - D0077-AC-34：`hooks.json` の形は変えず、スキル `pipe-run` は chat の順と人の確認を書いている（同上）。
  - D0077-AC-35：司会役とフックは SDK を読まず、依存の向きを守り、依存が増えない（`tests/test_architecture_chat.py`）。
  - D0077-AC-36：テストは SDK を呼ばず、リポジトリの実物に書かない（`tests/test_chat_flow.py`・`tests/conftest.py`）。
- 実機・手で（#123）。
  - D0077-AC-37（実機）：VS Code の Claude ハーネスで `/pipe-in:pipe-run` を呼ぶと守りの確かめが走り、効いていれば最初の段が流れ、効いていなければ理由を伝えて流れない。
  - D0077-AC-38（実機）：確かめが通った実行で、access = "docs" の段の範囲外への書き込みが止まり、範囲内は書ける。
  - D0077-AC-39（実機）：人の確認（質問欄か会話の文か）・サブエージェントの呼び出し・プラグインのスキルが、ハーネスで動くか。
  - D0077-AC-40（手で）：Claude Code（端末）でも、小さなパイプが最後まで流れ、拡張で記録が見える。

## 決めたことと理由

- **入口はプラグインのスキル `/pipe-in:pipe-run`、司会役は `pipe-in-gen chat start / probe / next / done / review / status`。** Claude ハーネスは VS Code のチャットの中にしかなく、端末の `pipe-in` からは呼べないため、会話を入口にした。司会役を `pipe-in` に置くと「端末の pipe-in から使う」ように見えるので、プラグインがもともと頼っている `pipe-in-gen` に置いた。
- **選ばなかった形。** (1) VS Code の拡張が Copilot のモデルを借りて中継する：拡張は読むだけ・子プロセスを起こさない決まりを崩し、利用規約に触れるおそれがある。(2) Copilot の SDK で段を流す：依存が増え、動くのは Copilot 側の仕組みでガードを道具の名前から作り直すことになる。(3) Copilot 本来の Local ハーネス：フックの入力に `agent_type` が無く、段ごとの守りが効かない。
- **最初の版は小さく絞り、扱えない形は流す前に断る。** 守れない設定を黙って無視しない。`max_budget_usd` は費用が取れないので守れず、断る。`model`・`max_turns` などは会話では効かないが、守りに関わらないので断らずに一覧で見せる。
- **判断を二重に持たない。** フックの段の範囲は本体の SDK の道と同じ `build_pipe_specs` から作り、判断は `guard.check_tool` をそのまま呼ぶ。本体の検査の判定・終わりの文・まとめ・記録の保管は、中身を変えずに関数へ取り出して使い回した（`pipe_in/pipe/pipeline.py`・`pipe_in/engine/archive.py`）。
- **`generator/guard_hook.py` は標準ライブラリだけのまま。** 本体を読む判断は `generator/chat_hook.py` に分け、会話本体（agent_type なし）の呼び出しは記録も本体も読まずに今の `decide` へ渡す。`guard_hook.py` には名前の判定と `main(decide_fn)` の引数を足しただけで、`decide`・`check_*` は変えていない。
- **止める範囲は狭めない。** `guard.py`・`bashwrite.py`・`.claude/hooks/pipe_in_guard.py` は変えていない。会話の道だけ、記録・`.claude/`・`.git/`・`.pipe-in/`・`pipeline.toml` への書き込みと `Skill` と、段の間のほかのエージェントを足して止める。読めない・分からない・例外のときは止める側に倒す。流しているパイプのフォルダは、本体の道と同じ `_outside_pipe` が置き場所によらず守る。
- **守りの確かめは、司会役が自分で読めるものだけを信じる。** 確かめ役 `pipe-probe` に乱数入りの範囲外のパスへ `Write` させ、(1) ファイルができていないこと、(2) フックが残した跡（`hook/trace.jsonl`。agent_type の生の値入り）の両方がそろったときだけ確かめ済みにする。確かめ役の返事は読まない。そろわなければ流さない（守りなしで流す道は作らない）。
- **数え方は本体に合わせた。** `steps`（max_steps）は段を始めるたびに数え、`retries`（max_retries）は検査の不合格だけを数える。人の revise はどちらも増やさず、revise のあとも検査はかかる。会話が途切れても数は記録に持ち続け、戻さない。
- **使用量は「取れない」と書く。** `usage_summary = {available: false, reason}`、費用は null（0 と書いて誤解させない）。拡張は「取れない」と出し、段の節の2行目は時間だけ（取れないターン数を「0 ターン」と出さない）。
- **確認待ちの答え方。** 会話の道の記録では「`/pipe-in:pipe-run` を流している会話で返す。コマンドなら `pipe-in-gen chat review --pipe <パイプ名> approved`」と出し、開発用の `python -m pipe_in record review` は出さない。
- **テストの変更（人の承認済み）。** (1) 承認したテストのうち AC-08 の「確かめるたびに乱数が変わる」は、AC-10（出したあとに続けて呼ぶと読んで失敗）と両立しなかったため、「失敗のあとに出し直すと乱数が変わる」形に直した。(2) 検証の1回目の画面の確認で、段の2行目に「0 ターン」が出ることと確認待ちの答え方の誤りが見つかり、AC-24 のテストを足し、「ターン・時間」を求めていた1件を「時間だけ」に直した（要件 FR-09 の「0 と書かない」に合わせた）。
- **監査と助言で直したもの（人が選んだ項目）。** A-01：CLAUDE.md・`/pipe-help`・`.claude-plugin/marketplace.json` に `/pipe-in:pipe-run` を載せた。A-02：`records.md` の archive の説明の食い違い。A-03：「パイプのフォルダ」を「流しているパイプのフォルダ」に（実物は置き場所によらず守っている）。A-05：`pipe-in --review` の断りの文に `--pipe <パイプ名>` を足した。V-01：フックが起動できない・時間切れのときは止まらず、会話の道は確かめで拾うことをガイドに書いた。V-05：エージェントの前書きの鍵をテストで固定した。V-06：スキルに `subagent_type` の書き方を明記した。V-08：`/plugin` が無い場所では確かめで守りを見ることをスキルに書いた。審査の採点は overall 0.9・verdict pass（引用の正確さと網羅性が 0.75）。
- **受け入れたリスク。** フックが起動できない・時間切れのときは、Claude Code はその呼び出しを止めない（公式の文書）。確かめの前に起きれば流れないが、確かめのあとの段の途中で起きた場合は防げない。古い拡張でこの記録を開くと、図の段に `$0.000` が出うる（記録は壊れない）。

## 対象外・残った課題

- 実機の確かめ（AC-37〜40）は #123 で人がする。手順には、Agent SDK の init メッセージの `plugins`・`plugin_errors` を見る項目も入れる（助言 V-08）。PreToolUse の入力の `agent_type` がプラグインのエージェントで `pipe-in:pipe-stage` の形になるかも、そこで確かめる（助言 V-03）。
- プラグインの `hooks.json` に `onFailure: "block"` を足すか（助言 V-01）。既存の pipe-builder・pipe-judge のフックの振る舞いと、Claude Code の版の前提が変わるので、別の決定にする。
- プラグインの版（`plugin.json` の `version`）を上げるのは公開のとき（監査 A-04）。GitHub から入れた人は版が変わったときだけ入れ直される。
- 扱わない形（group・routes・check.judge・agents・mcp・web・after）の対応、使用量の見積もり、Copilot 本来の Local ハーネスでの実行、無人の実行での利用。
- 端末の `pipe-in` で流した記録の確認待ちの知らせにも、開発用の答え方（`python -m pipe_in record review`）が出る（この機能より前からの振る舞い）。別の `fix/` の枝で直す。

## 確かめたこと

- 本体：`python -m pytest -q` で 13142 件が通る（監査と助言の直しと、この記録を足したあとに流し直した）。足したテストは司会役・確かめ・流れ・記録・フック・プラグイン・依存の向きの 8 ファイル。
- 拡張：`npm --prefix vscode test` で 5719 件が通る。`npm --prefix vscode run typecheck`・`build` も通る。
- 画面：プレビュー `run-panel-chat-light`・`run-panel-chat-dark` を開き、上のバーと使用量のタブが「取れない」と理由を出し、`$` の数も「ターン」も出ず、確認待ちの答え方が会話の道のものになり、明暗とも崩れが無く、コンソールのエラーが 0 件であることを確かめた。
- 守りの範囲：`guard.py`・`bashwrite.py`・`.claude/hooks/pipe_in_guard.py` に差分が無いこと、依存（`pyproject.toml`・`vscode/package.json`・`package-lock.json`）が増えていないことを `git diff` で確かめた。
- 実機（VS Code の Claude ハーネス）：まだ（#123）。
- 手で（Claude Code の端末で最後まで流す）：まだ。
