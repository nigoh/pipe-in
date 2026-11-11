# D0081 やり直しの回数を記録に持たせ、確認のあとも上限が効く（#133）

## 目的

SDK の道（`pipe-in --pipe`）は、やり直しの回数（`retries`）と段を流した回数（`steps`）を、プロセスの中だけで数えていた。確認で止めて `pipe-in --review` で続けると数え直しになり、`max_retries`・`max_steps` より多く回りえた（`max_retries = 2` なのに、検証の通し番号 `attempt` が 3 を超える）。

回数を `state.json` に持たせ、確認をはさんでも上限が効くようにする。司会役を1つにまとめる前の地ならしにもなる。

## 機能要件と受け入れ基準

テストは、断りの無いかぎり `tests/test_pipe_flow_counts.py`。

- FR-01 SDK の道のパイプ（`LinearPipeline`）が、`steps` と `retries` を `state.json` の `flow: {steps, retries}` に書く。`notes` は持たない（確認待ちになるのは検証に通ったあとで、そのとき `notes` は空のため）。
  - D0081-AC-02：確認で止めた時点の `state.json` に、`flow.steps` と `flow.retries` が入っている（`test_d0081_ac02_paused_state_has_flow_steps_and_retries`）。
- FR-02 `--review` で続けるとき、記録から読んで、続きから数える。
  - D0081-AC-01：`max_retries = 1` のパイプで、不合格 → 前の段へ戻る → 確認で止まる → `--review` で承認 → もう一度不合格、のとき、差し戻しの上限で終わる（`test_d0081_ac01_review_approve_keeps_retry_count_so_limit_holds`）。
  - D0081-AC-03：止めて続けた回をまたいで数えて `max_steps` を超えたら、`max_steps` を超えたときの終わり方になる（`test_d0081_ac03_steps_count_across_review_and_max_steps_stops`）。
  - D0081-AC-08：検査のある1つの段が不合格を繰り返すとき、続けたあとも `attempt` が `max_retries + 1` を超えない（`test_d0081_ac08_check_attempt_never_exceeds_max_retries_plus_one_across_review`）。
- FR-03 `--review` の `revise` で同じ段をやり直すとき、その段は `steps` に数えない（端末の中での `revise` と、会話の道に合わせる）。
  - D0081-AC-04：`revise` で続けても、`flow.steps` は増えない。`max_steps` ちょうどで止めた実行の `revise` は止まらず、次の段で止まる（`test_d0081_ac04_revise_does_not_add_steps`・`test_d0081_ac04_revise_at_max_steps_is_not_stopped`）。
- FR-04 `flow` の無い記録を `--review` で続けたときは、0 から数える。
  - D0081-AC-05：`flow` の無い古い記録を続けると、今までと同じに 0 から流れる。`schema` の無い記録では、`flow` は書くが `schema` は足さない（`test_d0081_ac05_*`）。
- FR-05 `--from` で途中から流すときは、記録を作り直すので、回数も 0 から。
  - D0081-AC-07：`--from` で流し直すと、`flow` は 0 に戻る（`test_d0081_ac07_from_restarts_counts_from_zero`）。
- FR-06 壊れた `flow` は、壊れた部分だけ 0 として読む。
  - D0081-AC-06：辞書でない・負の数・文字・真偽値・小数の `flow` は、その部分を 0 として読み、落ちない（`test_d0081_ac06_broken_flow_reads_broken_parts_as_zero`・`test_d0081_ac06_read_flow_is_pure`）。
- FR-07 並列の枠の中のやり直しは、今のまま（`test_d0081_fr07_group_steps_land_in_flow_steps`）。
- FR-08 共通の表 `tests/fixtures/state_record.json` の `sdk` の行の任意の鍵に `flow` を足す。
  - D0081-AC-09：パイプの記録が共通の表の `sdk` の行に合う。開発フロー（`DevPipeline`）の記録に `flow` は無い。`new_state` は `flow` を渡したときだけ書く（`test_d0081_ac09_*`）。
  - D0081-AC-10：拡張は `flow` を読み飛ばし、`flow` の無い記録と同じ結果になる（`vscode/src/domain/stateRecord.test.ts` の `D0081-AC-10`）。

## 決めたことと理由

- 鍵の名前は `flow`。会話の道の `chat.steps`・`chat.retries` とは共用しない（足すだけにして、寄せるのは司会役をまとめるときに行う）。
- 回数は `LinearPipeline` のインスタンスの値（`flow_steps`・`flow_retries`）で持ち、保存のたびに書く。本体の土台（`pipe_in/engine/pipeline.py`）にはフック `_flow_record()`（既定は `None`）を置き、`LinearPipeline` だけが上書きする。開発フローは `flow` を書かず、依存の向き（`pipe` → `engine`）も変わらない。
- `flow` の位置は、`warnings` の後ろ・`runs` の前（`new_state` の引数 `flow`。D0080 の土台に載せた）。
- 読む関数 `read_flow` は `pipe_in/pipe/pipeline.py` に置く。壊れた部分だけ 0 にして、壊れていない部分は使う。上限を甘くする方向の読みだが、記録は利用者の手元のファイルで、読めない記録で止めるより `--review` を続けられることを選んだ。
- `revise` は、流し直しの1回目だけを `steps` に数えず、`max_steps` の検査もしない。`revise` は人の操作で、端末の中の `revise` も元から数えないため。そのあとの段と差し戻しは、今までどおり数える。
- `schema` の無い古い記録を続けたときも、`flow` は書く（`schema` は足さない。D0080 のまま）。`flow` は足すだけの鍵で、古い版の本体と拡張は読み飛ばす。
- `retries` の鍵は、戻し先でなく、不合格になった段の名前。合格しても 0 に戻さない（今までの数え方のまま）。
- 意味が変わる所：同じ `pipe.toml` で、`--review` をはさむと上限が早く効く。`--review` の `revise` は `steps` に数えなくなる。
- 無人の実行（夜のまとめ実行）で進めた。次の点は推しの案で決めた（人の確認は朝）：鍵の名前／`chat` 節と共用しない／`revise` を数えない／壊れた部分だけ 0／保存のたびに書く／開発フローは書かない／フックで渡す形／鍵の位置／読む関数の置き場所。
- 受け入れたリスク：`attempt` は合格した回も数えるので、別々の段から何度も差し戻される段では、`max_retries + 1` を超えうる（数え方は変えていない。D0081-AC-08 は、1つの検査のある段が不合格を繰り返す場面に限った）。

## 対象外・残った課題

- 開発フロー（`pipe_in/dev/`）の差し戻しの回数、段の中のサブエージェントの回数（`max_agent_calls`）、会話の道の `chat.steps`・`chat.retries` を同じ鍵に寄せること、拡張で `flow` を画面に出すことは、対象外。
- `revise` を数えない判断は、`_flow` に `first` が渡されたかどうかだけを見る。今は `review` の `revise` からしか渡らない。別の所から `first` つきで呼ぶ道を足すときは、数え方を見直す。
- 監査の報告は 0 件だった。助言と審査は流さなかった（守り・プラグイン・`.claude/` に触れていないため）。

## 確かめたこと

- 本体 `python -m pytest -q`：全部通った。拡張 `npm --prefix vscode test`：6905 件が通った。型検査も通った。
- 赤の確かめ：足したテストは、実装の前に「`state.json` に `flow` が無い」「差し戻しの上限で終わらず確認待ちになる」「`attempt` が 8 まで増える」で落ちた。
- 検証の1回目は不合格だった（`docs/guide/pipes.md` のコードブロックの行を書き換えて、文書のテストが落ちた）。行を元に戻し、説明をコードブロックの外に移して、2回目で合格した。
- 既存のテスト（`tests/test_pipe_flow.py`・`test_pipe_check_record.py`・`test_reply_pipeline.py`・`test_state_schema.py`）は、書き換えなしで通る。
- 画面の受け入れ基準は無い。本物の SDK を呼ぶ実行では、まだ確かめていない。
