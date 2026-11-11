# D0080 記録（state.json）の空の値の決まりを1つにし、版の鍵を足す（#130）

## 目的

`state.json` を書く所が3つあり（SDK で流す本体・開発用の `record`・会話の道）、費用や使用量が「無い」ときの書き方が食い違っていた。開発用の記録は、拡張の一覧では「$0.000」（実績 0 ドル）に、費用の目安では「実績なし」に見えた。

値の決まりを「測れた」「取れない」の2通りに決め、3つの書き手が同じ土台の関数から記録を作る。版の鍵 `schema` も足す。あとで司会役を1つにまとめるための足場にする。

## 機能要件と受け入れ基準

- FR-01 値の決まりを2通りにする。測れた（SDK の道）：費用は数・使用量は集計の辞書・`runs[].cost_usd` は数・`metrics` 有。取れない（開発用の `record`・会話の道）：`null`・`{available: false, reason}`・`null`・`metrics` の鍵なし。変わるのは開発用の `record` だけ。
  - D0080-AC-03：`record start` の直後、`total_cost_usd` は `null`、`usage_summary.available` は `false` で、理由は空でない（`tests/test_state_schema.py` の `test_d0080_ac03_record_start_is_unavailable`）。
  - D0080-AC-04：`record done` で足す `runs[]` の要素は、`cost_usd` が `null` で、`metrics` の鍵が無い（`test_d0080_ac04_record_done_run_has_null_cost_and_no_metrics`）。
  - D0080-AC-05：会話の道の記録は、`schema` のほかは今と同じ値（`test_d0080_ac05_chat_state_unchanged_but_schema`）。
  - D0080-AC-06：SDK の記録は、段を1つも流していなくても、`total_cost_usd` が数、`usage_summary` が集計の辞書。土台の関数は、理由が空・測れた値の片方が無い・2通りを同時に渡す、を断る（`test_d0080_ac06_*`）。
  - D0080-AC-10：取れない記録で、`estimate.actual_usd` は `None` を返す（`test_d0080_ac10_actual_usd_is_none_for_unavailable`）。
- FR-02 3つの書き手が、記録の土台を `pipe_in/engine/state.py` の `new_state` から作る。SDK の道は `driver` の鍵を書かない（`null` も書かない）。
  - D0080-AC-02：SDK の記録に `driver` の鍵が無く、確認で止めた記録を `pipe-in --review` で続けられる（`test_d0080_ac02_*`）。
- FR-03 新しく書く記録の最初の鍵に `schema: 1` を足す。
  - D0080-AC-01：SDK で流した記録は `schema` が 1 で、最初の鍵。`--review` で続けても残る（`test_d0080_ac01_*`）。
- FR-04 `schema` の無い記録は今のまま読み、書き換えない（`archive/` の中も同じ）。読む側は `schema` の有無で分岐しない。
  - D0080-AC-07：`schema` の無い古い記録（開発用の `0.0`・`None`・`metrics: {}`）を、拡張は今までと同じ表示で読む（`vscode/src/domain/stateRecord.test.ts` の `D0080-AC-07`）。
  - D0080-AC-08：`schema` の無い記録を `--review`・`record` の各コマンドで続けても、`schema` は足されない。`archive/` の中も変わらない（`test_d0080_ac08_*`）。
  - D0080-AC-12：`schema` が数でない・2 以上の記録も、本体と拡張は落ちずに読む（`test_d0080_ac12_odd_schema_values_still_read`・`stateRecord.test.ts` の `D0080-AC-12`）。
- FR-05 3つの書き手が書く鍵を、共通の表 `tests/fixtures/state_record.json` に置き、本体と拡張のテストが同じ表を読む。
  - D0080-AC-09：3つの書き手が書く鍵の並びと値の種類が、共通の表のとおり。`state.py` は標準ライブラリだけを読む（`test_d0080_ac09_*`・`test_d0080_state_module_uses_only_stdlib`・`stateRecord.test.ts` の `D0080-AC-09`）。
- 見た目
  - D0080-AC-11（画面）：取れない記録は、拡張の一覧と実行パネルの費用が「取れない」と出る（`stateRecord.test.ts` の `D0080-AC-11`。画面は下の「確かめたこと」）。
  - D0080-AC-13（手で）：開発用の記録で、実行パネル・一覧・進み具合のページの費用の欄を確かめる（写しの段の費用が 0 でなく `null` になることは `test_d0080_ac13_live_snapshot_of_new_dev_record_has_no_zero_cost`）。

## 決めたことと理由

- 開発用の記録を「取れない」にする。0 ドルは、測った結果のように読めてしまうため（issue で決定済み）。
- 土台の関数は、新しいファイル `pipe_in/engine/state.py` に置く。標準ライブラリだけで、`pipe_in.usage` も読まない（集計は呼ぶ側が渡す）。依存の向き（`pipe`・`dev` → `engine`）を守れる。
- 費用と使用量は、引数 `unavailable_reason` の有無で2通りに分ける。理由の文は書き手が渡す。会話の道の文（「会話の中で流したため…」）は開発用に合わず、`pipe_in/pipe/chat_record.py` にあって `engine` からは読めないため。開発用の文は `pipe_in/dev/record.py` の `UNAVAILABLE_REASON` に置いた。
- `metrics` は鍵なしにそろえる（会話の道がもともと鍵なし）。`schema` は最初の鍵に置く。
- SDK の道は `--review` のたびに記録を組み直すので、読み込んだ記録に `schema` が無かった実行では `schema` を書かない（`_load_pending` が覚え、`new_state(..., with_schema=False)` で作る）。
- SDK の道の費用の合計は、`runs[].cost_usd` が `null` の要素を 0 として数える。新しい開発用の記録から `driver` を外して `--review` で続ける既存のテスト（`test_review_continues_a_record_without_driver`）が、`null` の足し算で落ちたため。SDK の道が書く値は数のまま。
- 読む側（`runList.ts` の `costText`・`costUsd`、`runRecord.ts`、`estimate.actual_usd`、`live.py`）は直していない。どれも `usage_summary.available === false` を先に見るか、`null` を飛ばすので、会話の道と同じ道を通る。
- 見本 `tests/fixtures/pipe_dev/` は、古い記録の例として残した（設計では作り直す案だった）。作り直すと、古い見本との差を固定するテストと、拡張の図の固定が連鎖して壊れる。新しい形は `tests/test_state_schema.py` が受け持つ。
- 既存のテストの期待値を、新しい決まりに合わせた：`tests/test_architecture.py` の `test_d0019_ac50_state_only_adds_keys`（新しい鍵に `schema`、`runs[]` から `metrics` が無くなる）、`tests/test_live_answer_cli.py`（鍵の並びの先頭に `schema`）、`tests/test_stage_budget.py`（`cost_usd` は `None`・`metrics` なし）、`tests/test_record.py`（古い形に戻して見本と比べる補助）、画面用の見本 `tests/fixtures/showcase*/state.json`（先頭に `schema`）。
- 無人の実行（夜のまとめ実行）で進めた。次の点は推しの案で決めた（人の確認は朝）：`metrics` は鍵なし／`schema` は最初の鍵／土台の関数の置き場所と引数の形／`with_schema` の持たせ方／一覧の費用の文は今の「取れない」のまま。
- 受け入れたリスク：古い版の拡張は、開発用の新しい記録の費用を零で出すことがある（D0077 の会話の道の記録と同じ）。

## 対象外・残った課題

- 古い記録の変換・移行、`schema` を使った読み分け、会話の道の `chat` 節の名前、既存の共通の表を1つにまとめること、`live.py` の写しの `SCHEMA`（別物）は、対象外。
- issue の文は画面の文を「取れません」としていたが、一覧の費用の欄の実物は「取れない」（`runList.ts`）で、「取れません」はステータスバーと使用量の節の文。そろえるかは朝に決める。
- 監査の報告（4件。どれも軽い。直していない）：
  - A-01 `docs/guide/records.md`・`vscode.md` が「上のバーと一覧の費用が『取れない』」とまとめて書くが、ステータスバーの実物は「費用は取れません」。
  - A-02 `docs/guide/vscode.md` の「全部の段の費用が 0 の記録（`/pipe-in` の記録など）」の例が、新しい記録には当てはまらない。
  - A-03 開発用の段のログ行（`ResultMessage`）の `total_cost_usd` は `0.0` のまま。会話の道は `None`。
  - A-04 `chat_record.py` の `USAGE_UNAVAILABLE` は辞書のままで、使うのは理由の文だけ。開発用の定数と名前がそろっていない。
- 助言と審査は流さなかった（守り・プラグイン・`.claude/` に触れていないため）。

## 確かめたこと

- 本体 `python -m pytest -q`：全部通った。拡張 `npm --prefix vscode test`：6903 件が通った。型検査とビルドも通った。
- 赤の確かめ：足したテストは、実装の前に「`schema` が最初の鍵でない」「`0.0` が `None` でない」「土台の関数が無い」で落ちた。
- 画面（D0080-AC-11）：開発用の新しい記録と同じ形（`usage_summary.available` が `false`）の確認用ページ `run-panel-chat-dark`・`run-panel-chat-light` を開き、費用が「取れない」と出て「$0.000」が出ないこと、コンソールのエラーが 0 件であることを見た。開発用の新しい記録そのものの確認用ページは無いので、その記録での画面は、まだ。
- D0080-AC-13（手で）：VSCode の実機と進み具合のページでは、まだ確かめていない。
