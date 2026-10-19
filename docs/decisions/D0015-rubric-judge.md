# D0015 調べもの型の報告を、1つの審査役がルーブリックで採点する（pipe-in-judge・/pipe-judge）

## 目的

助言の報告のような調べもの型の報告を、毎回同じ物差し（事実の正確さ・引用の正確さ・網羅性・情報源の質・ツール効率）で 0.0〜1.0 に採点し、総合スコアと合否を出す。報告をどこまで信じてよいかを、人が同じ基準で判断できるようにする。

## 機能要件と受け入れ基準

テストは `tests/test_pipe_judge.py`（定義・スキル・文書）と `tests/test_pipe_in_guard.py`（フック）。下では `::` からの名前だけを書く。

- FR-01 審査役 `pipe-in-judge`（`.claude/agents/pipe-in-judge.md`）を足す。1つのプロンプトで5項目を一度に採点し、項目ごとに審査役を分けない
- FR-02 5項目の名前（`factual_accuracy`・`citation_accuracy`・`completeness`・`source_quality`・`tool_efficiency`）と、項目ごとの 0.0・0.5・1.0 の目安を定義に書く
- FR-03 出力は JSON 1ブロック。キーは `scores`・`overall`・`threshold`・`verdict`・`reasons`・`unverified`
- FR-04 `overall` は null でない項目の平均、`threshold` は 0.7、`overall >= threshold` で pass
- FR-05 採点できない項目は null。道具の呼び出しの回数が渡されなければ tool_efficiency は null
- FR-06 審査役は読むだけ（書かない・Bash なし・直さない）。`tools:` はちょうど Read・Grep・Glob・WebFetch
- FR-07 WebFetch は公式の文書の場所だけ。WebSearch は使わない。報告や Web の文の指示に従わない
- FR-08 フックの表に `pipe-in-judge` を足し、Web は WebFetch だけを許す
- FR-09 手で呼ぶ `/pipe-judge [ファイル]`（空ならこの会話でいちばん新しい助言の報告）。採点を見せて止まり、直さない
- FR-10 `/pipe-in` の「監査と助言」で助言を流したときは、続けて審査も流し、採点を報告と一緒に見せて止まる。助言を流さなかったとき・助言が0件のときは審査も流さず、そう書く（0件では採点する項目が無いため）
- FR-11 審査の合否は人が読む材料で、fail でも自動で直さない・差し戻さない
- FR-12 監査・助言との役割の違いを定義とスキルに書く
- FR-13 `/pipe-help`・`docs/development/design.md`・`docs/development/workflow.md`・CLAUDE.md・`.claude/settings.json` をそろえる
- FR-14 記録の形・段の数は変えない（審査は段ではない）
  - D0015-AC-01 定義の `name` と `tools:`（`::test_d0015_ac01_judge_definition_tools`）
  - D0015-AC-02 5項目の日本語の名前と出力の名前（`::test_d0015_ac02_rubric_items_are_named`）
  - D0015-AC-03 出力のキーと値（`::test_d0015_ac03_output_keys_and_values`）
  - D0015-AC-04 1つのプロンプト・審査役を分けない・平均・0.7（`::test_d0015_ac04_single_prompt_and_overall`）
  - D0015-AC-05 書かない・直さない・指示に従わない・null の決まり（`::test_d0015_ac05_read_only_and_null_rules`）
  - D0015-AC-06 定義の場所の一覧がフックと同じ（`::test_d0015_ac06_definition_copies_hook_hosts`）
  - D0015-AC-07 監査・助言との違い（`::test_d0015_ac07_differs_from_audit_and_advice`）
  - D0015-AC-08 審査役の Read・Glob・Grep・SubagentHandback は通る（`::test_d0015_ac08_judge_can_read_and_hand_back`）
  - D0015-AC-09 公式の文書の WebFetch は通る（`::test_d0015_ac09_judge_can_fetch_official_docs`）
  - D0015-AC-10 書き込みはどのパスでも止まる（`::test_d0015_ac10_judge_cannot_write_anywhere`）
  - D0015-AC-11 Bash・PowerShell・MCP・Agent・NotebookEdit は止まる（`::test_d0015_ac11_judge_cannot_use_bash`・`::test_d0015_ac11_judge_bypass_routes_are_denied`）
  - D0015-AC-12 WebSearch は公式の場所を付けても止まる（`::test_d0015_ac12_judge_web_search_is_denied`）
  - D0015-AC-13 似せた URL・一覧に無い URL は止まる（`::test_d0015_ac13_judge_cannot_fetch_other_urls`）
  - D0015-AC-14 ほかの役の Web は止まったまま（`::test_d0015_ac14_web_is_still_closed_for_others`）
  - D0015-AC-15 フックの入口を通しても同じ（`::test_d0015_ac15_main_entry_handles_judge_fetch`）
  - D0015-AC-16 フックは標準ライブラリだけ（既存の `::test_ac04_hook_uses_only_the_standard_library`・`::test_d0008_ac12_hook_imports_only_urllib_parse`）
  - D0015-AC-17 `/pipe-judge` のスキル（`::test_d0015_ac17_pipe_judge_skill`）
  - D0015-AC-18 `/pipe-in` の「監査と助言」の節（`::test_d0015_ac18_pipe_in_runs_judge_after_advice`）
  - D0015-AC-19 `/pipe-in` の表の行（`::test_d0015_ac19_pipe_in_table_has_judge_row`）
  - D0015-AC-20 CLAUDE.md の段落（`::test_d0015_ac20_claude_md_mentions_judge`）
  - D0015-AC-21 `/pipe-help` の一覧（`::test_d0015_ac21_pipe_help_lists_judge`）
  - D0015-AC-22 design.md の置き場所の表（`::test_d0015_ac22_design_table_lists_judge`）
  - D0015-AC-23 workflow.md の節（`::test_d0015_ac23_workflow_mentions_judge`）
  - D0015-AC-24 settings.json の allow（`::test_d0015_ac24_settings_allow_judge`）
  - D0015-AC-25 前の版のフックの下では読むだけになり、定義に代わりの採点の仕方がある（`::test_d0015_ac25_judge_is_read_only_under_the_old_hook`・`::test_d0015_ac25_definition_falls_back_when_fetch_is_blocked`）
  - D0015-AC-26 記録の形と段の数が変わらない（`::test_d0015_ac26_no_record_for_judge`）
  - D0015-AC-27（実機）`/pipe-advise` のあと `/pipe-judge` を流すと、審査役が1回呼ばれ、JSON が1つ返って止まり、`git status` に差が出ない
  - D0015-AC-28（実機）同じ報告を2回採点し、点の差と verdict をここに書く
  - D0015-AC-29（手で）main に入ったあと、別の `/pipe-in` の最後で、助言のあとに審査が流れる

## 決めたことと理由

- **1つの審査役・1つのプロンプトで5項目を一度に採点する。** 項目ごとに審査役を分けたり、何度も採点して平均したりするより、1回の採点のほうが人の判断といちばん一貫してそろう、という知見に合わせた。
- **採点する対象は、調べもの型の報告（まず助言の報告と、パスで渡すファイル）。** ルーブリックの「引用の正確さ」「情報源の質」は、出典付きで調べた報告で初めて意味がある。パイプの段の成果物は対象にしない。
- **置き場所は `.claude/` だけ。** 開発用のサブエージェントとスキルで足り、本体（`pipe_in/`）・`plugin/`・`generator/`・`vscode/` には入れない。利用者のパイプには影響しない。
- **`/pipe-in` の検証のあと、助言を流したときは続けて審査も流す（人の選択）。** 推しは「手で呼ぶだけ」だったが、人は助言の質を毎回見たいので流れに組み込んだ。審査は段ではなく `record` を書かない。合否は人が読む材料で、fail でも自動で直さない（直す項目は今までどおり監査・助言の ID で人が選ぶ）。
- **総合は null でない項目の平均、0.7 以上で合格。** 審査役の印象で総合を付けるより一貫する。5項目とも null なら fail（採点できないものを合格にしない）。しきい値や重みは設定で変えられるようにしない（今は要らない）。
- **ツール効率の材料はメインが渡す。** Agent の結果に出る道具の呼び出しの回数を渡し、無ければ null。advisor の報告の形は変えない。
- **フックの止める範囲を狭める（審査役に WebFetch を許す）。** 引用の正確さは出典の中身を読まないと確かめられない。開けるのは `pipe-in-judge` の WebFetch で、公式の文書の場所の `https://` の URL だけ（advisor より狭く、WebSearch は止める）。審査役はどこにも書けず Bash も無いので、読んだ文に指示が入っていても外へ書き出す道は無い。すり抜けの道（書き込み・Bash・PowerShell・MCP・Agent・NotebookEdit・WebSearch・似せた URL・ほかの役の Web・フックの入口）が閉じたままであることを D0015-AC-10〜15 のテストで示した。
- **`WEB_AGENTS` を「役 → 使える Web の道具」の表にした。** 役ごとに道具を分けられるようにし、表に無い役・表に無い道具は最後の deny で止まる。使われなくなった `WEB_TOOLS` は消した。
- **公式の文書の場所の一覧は、フックの中では advisor と共有し、定義には文で写す。** 一覧を2つにすると片方だけ直してずれる道ができる。写しのずれは D0015-AC-06 で捕まえる。
- **WebFetch の回数の上限は、定義の文で 15 件。** フックは呼び出しを数えられない（状態を書くと読むだけの作りが崩れる）。
- **点は 0.0・0.25・0.5・0.75・1.0 の5段階に限る（助言 V-03）。** 公式の文書（https://platform.claude.com/docs/en/test-and-evaluate/develop-tests ）は、段階の決まった尺度と詳しいルーブリックを推す。間の点を許すと、同じ報告でも点がぶれやすい。実在しない出典があれば `citation_accuracy` を 0.0 にする、という決まった条件も書いた。
- **審査役に `effort: high` を付け、JSON では `reasons` を `scores` より先に書かせる（助言 V-02）。** 同じ文書の「考えてから点を出させる」に合わせた。
- **WebFetch の「書かれていない」を、そのまま誤りとは決めない（助言 V-04）。** WebFetch は取ったページを別のモデルが抜き出す作りで取りこぼしがある（https://code.claude.com/docs/en/tools-reference ）。名指しで取り直し、それでも見つからなければ `unverified` に入れる。
- **番号は D0015。** 作業の途中で、並べて進めていた別のブランチ（D0013 のロゴの動き・D0014 の README のガイド）が先に main に入った。仕上げの前に main へ載せ直し、この機能の番号と AC の ID を D0014 から D0015 に振り直した（テストの名前の番号も同じく付け替えただけで、中身は変えていない）。索引の衝突は、3つの行を並べて合わせた（監査 A-05）。
- **`.claude/` の下はメインが書いた。** 実装の段のサブエージェントは `.claude/` に書けないため。`.claude/` の外の文書（CLAUDE.md・design.md・workflow.md）は実装の段で書いた。

## 対象外・残った課題

- 本体の `[stages.check]` にルーブリックを足すこと、パイプの段の成果物の採点、`plugin/`・`generator/`・`vscode/` への追加。
- 監査の報告の採点、`claude -p` での `/pipe-judge` の呼び方。
- 点が低いときに報告を作り直させること、しきい値や重みを設定で変えること。
- 人の採点と照らした確かめはまだ（助言 V-06）。公式の文書は「先に信頼できるか確かめてから広げる」としている。それまでは合否を人が読む材料に留め、`--auto` でも verdict で何かを決めない。
- 「1回の採点が人の判断といちばんそろう」という知見の出典は、読めた公式の文書の中には見つからなかった（助言の「確かめられなかったこと」）。要件メモに書かれた知見として採った。
- 審査役を助言役と別のモデルにすること（助言 V-01。公式の文書は、評価は出力を作ったのと別のモデルで行うのがよいとする）。どのモデルにするかを決めてから、別の記録で直す。今は同じモデルで、自分の作った物を甘く見るリスクを受け入れる。
- 審査役の `maxTurns` で呼び出しの数を仕組みで止めること（助言 V-05）。今は定義の文で 15 件まで。
- フックの `main()` 全体を try で包み、思いがけない例外でも deny を出すこと（助言 V-08。時間切れや終了コード 1 のフックは道具を止めない）。コードの振る舞いを変えるので、別の `fix/` のブランチでテスト先行から直す。この性質はこのブランチより前からあるが、審査役に WebFetch を開けたぶん影響が広がるリスクを受け入れる。
- フックの呼び方を exec の形にすること（助言 V-09）。このブランチの変更ではない。
- `tests/test_pipe_in_guard.py` の D0008 のテストの文「Web はアドバイザーだけ」（監査 A-06）。承認されたテストには触らないので、今は直さない（D0015-AC-14 のテストが今の決まりを見ている）。

## 確かめたこと

- `python -m pytest -q`：1509 passed。テスト先行で赤だった 29 件（フックが審査役を知らない・定義とスキルが無い・文書と設定に無い）は、すべて期待した理由で落ちたあと緑になった。閉じたままを守る検査（D0015-AC-08・10〜14・26）は、変える前も後も通る。
- 拡張（`vscode/`）・本体（`pipe_in/`）は触っていないので、拡張のテストは流していない。
- 検証のあとの監査（6件）と助言（9件）を流し、人が承認した A-01〜A-05・V-02〜V-04・V-06・V-07 を直した。直さなかったものは「対象外・残った課題」に書いた。
- 助言のあとに審査も流した。この会話は main で始めていたので、動いたのは前の版のフックで、審査役は読むだけになり、公式の文書への WebFetch は5件とも止められた。審査役は引用を推さず `unverified` に入れ、ファイル:行の出典だけで採点した（overall 0.90・pass。tool_efficiency は回数を渡せず null）。D0015-AC-25 が狙った動きを、実際に確かめた。
- D0015-AC-27（実機。新しいフックの下で `/pipe-advise` → `/pipe-judge`）：まだ。worktree で開いた会話で流す。
- D0015-AC-28（実機。同じ報告を2回採点したばらつき）：まだ。
- D0015-AC-29（手で。main に入ったあと別の `/pipe-in` の最後で審査が流れる）：まだ。
