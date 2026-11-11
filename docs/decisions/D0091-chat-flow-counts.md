# D0091 会話の道の回数を、記録の `flow` に寄せる（#140）

## 目的

D0081 で、SDK の道（`pipe-in --pipe`）は、段を流した回数（`steps`）とやり直しの回数（`retries`）を、記録の `flow` に持つようになった。会話の道（`pipe-in-gen chat`）は、同じ回数を `chat.steps`・`chat.retries` に持ったままで、置き場所と読み方が2つあった。

会話の道も `flow` に書き、読み方（`read_flow`）を1つにする。司会役を1つにまとめる前の地ならし。止まる回・終わりの形・`chat status` の値は変えない。

### 要求と前提

- UR-01 開発者として、2つの道（SDK の道・会話の道）の回数を、記録の同じ鍵・同じ読み方で扱いたい。
- 前提：古い版の本体は `flow` を知らず、`chat.steps`・`chat.retries` を読む。
- 状態を持ち、操作や出来事で移り変わるか
  - 答え：いいえ
  - 理由：回数の置き場所を寄せるだけで、新しい状態も移り変わりも足さない（止まる回は今と同じ）。

## 機能要件と受け入れ基準

テストは、断りの無いかぎり `tests/test_chat_flow_counts.py`。

- FR-01（UR-01）`chat start` は、記録に `flow`（`steps` が 0、`retries` が空）を書く。
  - D0091-AC-01（FR-01）`flow` が 0 と空で書かれ、鍵の位置は `warnings` の後ろ・`open` の前。`chat.steps`・`chat.retries` にも同じ値がある。
- FR-02（UR-01）2つの道は、同じ台本で同じ回数になる。
  - D0091-AC-02（FR-02）同じパイプ・同じ台本（通る／不合格で戻す／上限に達する／確認で承認／確認で直しを頼む）を2つの道で流すと、`flow` が各時点で一致する。止まる回も同じ。違うのは1点だけで、`max_steps` を超えて止まった時点の `steps` が、SDK の道は `max_steps + 1`、会話の道は `max_steps`（テストで固定）。
- FR-03（UR-01）会話の道は、`flow` の鍵が無ければ古い `chat.steps`・`chat.retries` を読む。鍵があれば、`flow` と `chat.*` の大きいほうを採る。保存のたびに、`flow` と `chat.*` に同じ値を書く。
  - D0091-AC-03（FR-03）`flow` の無い古い記録を `next`・`review` で続けると、数が引き継がれて `flow` が足される。古い記録の上限（`max_steps`・`max_retries`）は、続けたあとも効く。
  - D0091-AC-07（FR-03）壊れた `flow`（辞書でない・負の数・文字・真偽値・小数）は、壊れた部分だけ 0 と読み、落ちない。`flow` と `chat.*` が食い違う記録は大きいほうを採り、上限が甘くならない。
- FR-04（UR-01）止まる回・文・終わりの形は今と同じ。
  - D0091-AC-04（FR-04）`max_retries` で止まる文・`final`・`99_summary.md` が今と同じ。既存の `tests/test_chat_*.py` は書き換えなしで通る。
- FR-05（UR-01）`chat status` の `steps`・`retries` と文は、今と同じ値を返す。
  - D0091-AC-05（FR-05）新しい記録・古い記録で同じ値と文を返し、`status` は記録を書き換えない（`state.json` のバイトが前後で同じ）。
- FR-06（UR-01）拡張は `flow` を読まない（コードを変えない）。
  - D0091-AC-06（FR-06）`flow` の入った会話の道の記録を、落ちずに読み、`flow` の無い記録と同じ結果になる（`vscode/src/domain/stateRecord.test.ts`）。
- FR-07（UR-01）`read_flow` を、標準ライブラリだけの小さな部品 `pipe_in/engine/flow.py` に移す。
  - D0091-AC-08（FR-07）`flow.py` は標準ライブラリだけ。`chat.py` は `read_flow` を SDK の道のモジュール（`pipe_in.pipe.pipeline`）から読まない（`tests/test_architecture.py`）。`pipe_in.pipe.pipeline` からも同じ名前で読める。
- FR-08（UR-01）共通の表（`tests/fixtures/state_record.json`）の `chat` の行に、任意の鍵 `flow` を足す。
  - D0091-AC-09（FR-08）`flow` のある記録と、`flow` を消した古い記録の両方が、表の検査を通る。
- D0091-AC-10（FR-01）文書（`docs/guide/records.md`・`docs/guide/pipes.md`・`docs/development/design.md`）が、会話の道も `flow` を書くことに合っている（この番号の付いたテストは無い。人が読んで確かめる）。

### 非機能要件

- 無し

## 決めたことと理由

- **`chat.steps`・`chat.retries` は消さず、同じ値を写して残す。** 既存のテスト（D0077）と `chat` の節の鍵の並びを変えないため。古い版の本体は `flow` を知らないが、`chat.*` を読んで上限を続けられる。
- **読み書きは1か所。** `chat.py` の `_counts`（読む）・`_set_counts`（書く）にまとめ、`_save` の先頭で毎回呼ぶ。`next`・`done`・`review`・終わりはどれも `_save` を通るので、書き忘れの道が無い。
- **食い違う記録は、大きいほうを採る。** 要件定義は初め「`flow` の鍵があれば `chat.*` に戻さない」だったが、設計で改めた。古い版の本体が `chat.*` だけを進めた記録を新しい版で続けると、「`flow` が正」では数が戻って、上限が甘くなるため。普通の記録は両方に同じ値を書くので、結果は変わらない。壊れた `flow` は 0 と読んだうえで比べるので、`chat.*` が正しければ、その数が効く。
- **`read_flow` の置き場所は `pipe_in/engine/flow.py`。** 回数の読み方は、SDK の道にも会話の道にも属さない。`engine/state.py` は記録を「書く側」（D0081）なので混ぜない。`chat.py` は、ほかの関数（`verdict_outcome`・`command_outcome`）のために `pipe_in.pipe.pipeline` をまだ読む。それは司会役をまとめる件（#143）で扱う。
- **数える順はそろえない。** `max_steps` の判定は、SDK の道が「増やしてから比べる」、会話の道が「比べてから増やす」。止まる回は同じで、止まった時点の `steps` の値だけが 1 違う。動きを変えないために、そのままにして、表とテストで固定した。
- **`probe` は古い記録に `flow` を足す。** `probe` は元から記録を保存するので、そのとき `flow` が足される（値は `chat.*` と同じ）。記録を書き換えないのは、保存しない `status` だけ。
- **既存のテストを2件直した**（意図した変更）：`tests/test_state_schema.py` の、会話の道の記録の鍵の並び（`warnings` と `open` の間に `flow`）と、`tests/test_pipe_flow_counts.py` の「`flow` を任意の鍵に持つのは sdk だけ」（sdk と chat。dev は持たない）。
- 記録の `schema` は上げない（任意の鍵を足すだけ）。守り（`guard.py`・`guard_hook.py`）は触らない。依存は足さない。
- 無人の実行で進めた。次の点は推しの案で決めた（人の確認は朝）：`chat.*` を写して残すこと／食い違いは大きいほうを採ること／`read_flow` の置き場所／`probe` が古い記録に `flow` を足すこと／数える順をそろえないこと／既存のテスト2件の直し。

## 対象外・残った課題

- 開発フロー（`pipe_in/dev/`）の回数を `flow` に寄せること、拡張で `flow` を画面に出すこと、`chat.steps`・`chat.retries` を消すことは、対象外。
- 数える順（`max_steps` で止まった時点の `steps` が 1 違う）は、司会役をまとめるとき（#143）にそろえるかを決める。
- 監査の報告（直していない。人の確認は朝）：A-01 `tests/test_pipe_flow_counts.py` の D0081 のテストの docstring に、「`new_state` は `flow` を渡さなければ鍵を書かない（DevPipeline・会話の道の記録を変えない守り）」という言い方が1か所残っている。会話の道は D0091 で `flow` を渡すようになったので、「会話の道」は外すのが正しい。
- 助言と審査は流さなかった（守り・プラグイン・`.claude/` に触れていない）。

## 確かめたこと

- 本体 `python -m pytest -q`：18160 件が通った（失敗 0）。拡張 `npm --prefix vscode test`：6958 件が通った。型検査とビルドも通った。
- 赤の確かめ：足したテストのうち 44 件は、実装の前に「`state.json` に `flow` が無い」「壊れた `flow`・食い違う `flow` を読まない」「`pipe_in/engine/flow.py` が無い」で落ちた。止まる回・`status` の値・終わりの文のテストは、始めから通った（今の動きの固定）。
- 実装の確かめ：`chat.steps`・`chat.retries` を直接読み書きするのは `_counts`・`_set_counts` の中だけ。`max_steps`・`max_retries` の判定の式と順は元のまま。守りに差分は無い。
