# D0020 何かを変えたら文書もそろえる（文書係 pipe-in-documenter・/pipe-docs・止まるときの知らせ）

## 目的

pipe-in を開発していて、コード・定義・設定を変えたときに、README.md・`docs/guide/`・`docs/development/`・`/pipe-help` などの文書が古いまま残らないようにする。直す文書を探して直す役を決め、忘れたときにも気づけるようにする。

## 機能要件と受け入れ基準

テストは `tests/test_pipe_docs.py`。下では `::` からの名前だけを書く。

- FR-01 文書係のサブエージェント `pipe-in-documenter`（`.claude/agents/pipe-in-documenter.md`）を足す。`docs/development/workflow.md` の「4. そろえる」の表どおりに、変えたものに合わせて文書を直し、「文書の報告」を返す
- FR-02 文書係が書けるのは `README.md`・`vscode/README.md`・`pipes/README.md`・`docs/assets/README.md` と `docs/guide/`・`docs/development/` の `.md` だけ。CLAUDE.md・`.claude/`・決定の記録は書けず、案を返す。Bash・Web は使えない（`.claude/hooks/pipe_in_guard.py` が止める）
- FR-03 `/pipe-docs [要点か範囲]` を足す。変えたファイルを集めて文書係に任せ、案は人の承認を得てからメインが直し、テストを流し直す。モデルからも呼べる
- FR-04 `/pipe-in` で、検証で合格したあと、監査の前に文書係を流す（段ではなく、記録は書かない）
- FR-05 Stop のフック `.claude/hooks/docs_reminder.py` を足す。コードを変えたのに文書が1つも変わっていないまま止まろうとすると、同じ変更の組で1回だけ止まるのをとめて知らせる
- FR-06 `.claude/settings.json`・CLAUDE.md・`/pipe-help`・`docs/development/design.md`・`docs/development/workflow.md`・`docs/guide/develop.md` をそろえる
  - D0020-AC-01 定義の `name` と `tools:`（`::test_d0020_ac01_documenter_definition_tools`）
  - D0020-AC-02 定義に、そろえる表・書ける文書・書けないもの（案を返す）・コードは直さない・報告の形がある（`::test_d0020_ac02_documenter_definition_states_scope_and_report`）
  - D0020-AC-03 文書係は文書を書ける（`::test_d0020_ac03_documenter_can_write_docs`）
  - D0020-AC-04 文書係は、CLAUDE.md・`.claude/`・決定の記録・`docs/pipeline/`・コード・テスト・プロジェクトの外・`..` を含むパスを書けない（`::test_d0020_ac04_documenter_cannot_write_elsewhere`）
  - D0020-AC-05 Bash・PowerShell・NotebookEdit・Agent・MCP・Web は止まり、読む道具と報告は通る（`::test_d0020_ac05_documenter_bypass_routes_are_denied`・`::test_d0020_ac05_documenter_can_read_and_hand_back`）
  - D0020-AC-06 フックの入口を通しても同じで、フックの説明に文書係がある（`::test_d0020_ac06_main_entry_denies_documenter_code_write`・`::test_d0020_ac06_guard_docstring_lists_documenter`）
  - D0020-AC-07 `/pipe-docs` のスキル（`::test_d0020_ac07_pipe_docs_skill`）
  - D0020-AC-08 `/pipe-in` の「文書をそろえる」の節が「監査と助言」の前にあり、役割の表に行がある（`::test_d0020_ac08_pipe_in_runs_documenter_before_audit`）
  - D0020-AC-09 変えたファイルを、コード・文書・どちらでもないに分ける（`::test_d0020_ac09_classify`）
  - D0020-AC-10 `git status --porcelain -z` の出力を読む（`::test_d0020_ac10_parse_porcelain`）
  - D0020-AC-11 コードを変えて文書が変わっていなければ知らせる（`::test_d0020_ac11_reminds_when_code_changed_without_docs`）
  - D0020-AC-12 文書も変えた・コードを変えていない・知らせのあとの止まりでは知らせない（`::test_d0020_ac12_stays_quiet`）
  - D0020-AC-13 同じ変更の組では1回だけ（`::test_d0020_ac13_reminds_once_per_change_set`）
  - D0020-AC-14 入口は block の JSON を1回だけ出し、目印はリポジトリの外に置き、git や入力が読めなければ何も出さない（`::test_d0020_ac14_main_blocks_once`・`::test_d0020_ac14_main_is_quiet_when_git_fails`・`::test_d0020_ac14_state_path_is_outside_the_repo`）
  - D0020-AC-15 知らせのフックは標準ライブラリだけ（`::test_d0020_ac15_reminder_uses_only_the_standard_library`）
  - D0020-AC-16 settings.json の Stop のフックと allow（`::test_d0020_ac16_settings_register_stop_hook_and_allow_documenter`）
  - D0020-AC-17 `/pipe-help`・design.md・workflow.md・CLAUDE.md をそろえた（`::test_d0020_ac17_docs_mention_the_new_parts`）
  - D0020-AC-18（実機）コードだけを変えた会話で止まろうとすると知らせが1回出て、`/pipe-docs` で文書係が文書を直し、2回目は出ない

## 決めたことと理由

- **文書係は文書だけを書ける役にした。** 実装の段の `pipe-in-coder` も文書を書けるが、コードを書く役に「見落としを探す」ことまで任せると漏れる。書ける場所を文書に絞った別の役にすれば、コードを書き換える心配なしに任せられる。
- **CLAUDE.md・`.claude/`（`/pipe-help` を含む）・決定の記録は書かせず、案を返させる。** CLAUDE.md と `.claude/` は Claude への指示と、サブエージェント自身の定義・フックで、サブエージェントが書けると自分の絞りを緩める道ができる。決定の記録は「何をなぜ決めたか」で、メインが人とのやり取りを踏まえて書くもの。どれも人の承認を得てからメインが直す。
- **フックの表に足すのは書ける範囲を広げる変更だが、利用者のプロジェクトを守る `pipe_in/engine/guard.py`・`generator/guard_hook.py` には触れない。** 文書係は Bash・PowerShell・MCP・Agent・Web を使えず、書けるのは `.md` の文書だけ。すり抜けの道が閉じたままであることを D0020-AC-04〜06 で示した。
- **`/pipe-docs` はモデルからも呼べるようにした。** ほかの開発用スキル（`/pipe-in`・`/pipe-audit` など）は人が呼ぶものだが、「何かを変えたら文書もそろえる」をふだんの流れにするには、Claude が変更のあとに自分で呼べるほうがよい。書けるのは文書だけで、案は人の承認を待つので、自分で呼んでも人の知らないうちに大事な所が変わることは無い。
- **`/pipe-in` では、検証で合格したあと、監査の前に流す。** 実装の段のあとだと、検証で差し戻されたときにやり直しになる。監査の前に流せば、監査がそろえたあとの文書を見られる。案は監査と助言の報告と一緒に見せ、止まる回数を増やさない。
- **忘れたときのために、Stop のフックで知らせる。** 「そろえる」を文に書くだけでは忘れる。止まるときに `git status` を見て、コードが変わっていて文書が1つも変わっていなければ、止まるのを1回とめて理由を返す。テスト・記録・lock のファイルは数えない。
- **知らせは同じ変更の組で1回だけにした。** 文書が要らない変更（中だけの直しなど）でも、止まるたびに知らせると邪魔になる。コードの変更の組の目印を一時フォルダに置き（リポジトリには書かない）、同じ組なら黙る。知らせのあとの止まり（`stop_hook_active`）でも黙る。git や入力が読めないときも、人の作業を止めないよう何もしない（安全側＝止めない側。守る仕組みではなく知らせなので）。
- **見るのは、まだコミットしていない変更だけ。** コミットしたものは、コミットの前に一度知らせを通っている。main との差まで見ると、ブランチの間ずっと「文書を変えた」扱いになって知らせが役に立たない。

## 対象外・残った課題

- 文書の中身が実物と合っているかの検査（それは `/pipe-audit` と、文書を検査する既存のテストの受け持ち）。
- 本体・プラグインの利用者のプロジェクトへの同じ仕組み（このリポジトリの開発用だけ）。
- `claude -p` で `/pipe-docs` を流す呼び方。
- 知らせの言葉や、数えるパスを設定で変えること。

## 確かめたこと

- `python -m pytest -q`：すべて通った。テスト先行で足した 90 件（あとで監査 A-01 の1件を足して 91 件）のうち、フックが文書係を知らない・定義とスキルとフックと節が無い・設定と文書に無い、で 78 件が期待した理由で落ちたあと緑になった。閉じたままを守る検査（D0020-AC-05 のすり抜けの道）は、変える前（表に無い `pipe-in-*` は読むだけ）も後も通る。
- 拡張（`vscode/`）・本体（`pipe_in/`）は触っていないので、拡張のテストは流していない。
- 知らせのフックを、一時フォルダに作った git の作業フォルダで流し、コードだけを変えたときに1回だけ block が出て、2回目と文書も変えたときは何も出ないことを確かめた。
- 文書係を、この変更そのものに対して1回流した（定義はこの会話の途中で足したので、読み込まれたあと）。`docs/development/workflow.md` の「5. 検証」の行と「検証のあとの監査と助言」の導入の2か所の抜けを見つけて直し、書ける範囲の外には触れなかった。
- 検証のあとの監査（4件）と助言（2件）を流し、助言を採点した審査は overall 0.95・pass（網羅性 0.75：allow の `Agent(...)` の書き方を確かめきっていない）。人が承認した A-01（知らせのフックが `docs/assets/README.md` を文書に数えていなかった。テストを足して赤を確かめてから直した）・A-02（workflow.md のコードの例を実物に合わせた）・A-03（`/pipe-in` の `--auto` の節に文書係の案を足した）を直した。A-04（件数）は確かめて合っていたので直していない。助言の V-02（Stop の block の上限）はフックの説明に1行足し、V-01（`additionalContext` で知らせる形）は、止まるのを1回とめて文書を見させたいので block のままにした。
- D0020-AC-18（実機）：まだ。main に入ったあと、コードだけを変えた会話で確かめる。
