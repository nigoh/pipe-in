# D0082 能力表をデータにする（会話の道の「断る・効かない」を表から作る。#131）

## 目的

会話の道（`/pipe-in:pipe-run`）は、扱えない形のパイプを始める前に断り、効かない設定を一覧で見せる。この判断が、`pipe_in/pipe/chat.py` の `unsupported()` と `ineffective()` の中の条件として書かれていて、パイプや設定に項目を足したときに、会話の道での扱いを決め忘れても気づけなかった。

「項目 × 実行役（SDK・会話）」の能力表をデータとして持ち、断る文と一覧を表から作る。足し忘れはテストが落とす。あとで実行役を足すときは、表に列を足す。動きは変えない。

## 機能要件と受け入れ基準

- FR-01・06 能力表（`pipe_in/pipe/capability.py` の `TABLE`）は、項目ごとに、実行役ごとの動き（効く／断る／一覧に出す／黙る／関係しない）と理由の文を持つ。
  - D0082-AC-07：「断る」「黙る」の項目は、すべて空でない理由の文を持つ。理由が空の行は、検査が報告する（`tests/test_capability.py` の `test_d0082_ac07_*`）。
  - D0082-AC-11：`capability.py` は標準ライブラリだけを読む（`tests/test_architecture.py` の `test_d0082_ac11_capabilityは標準ライブラリだけ`）。
- FR-02 `unsupported()` と `ineffective()` は、表から作る。出す文と順番は、今と同じ。
  - D0082-AC-04：断る形（`tests/test_chat_start.py` の `BAD_SHAPES`）のそれぞれで、`unsupported()` の戻りが、今の文と1文字も変わらない（`tests/test_chat_capability_text.py` の `test_d0082_ac04_*`）。
  - D0082-AC-05：断る形が複数あるとき、文の順番が今と同じ（段ごとの順のあと、`pipeline.toml` の分が最後）。パイプに無い段の名前の `[stages.<段>]` でも断る（`test_d0082_ac05_*`）。
  - D0082-AC-06：`ineffective()` の戻りが、今と同じ内容と順番（`test_d0082_ac06_*`）。
  - D0082-AC-09：D0077-AC-01〜06 のテスト（`tests/test_chat_start.py` ほか）が、書き換えなしで通る。
  - D0082-AC-10：`chat.py` に、項目の名前で分ける条件（`s.group`・`s.routes` など）が残らない。検査そのものも確かめる（`tests/test_capability.py` の `test_d0082_ac10_*`）。
- FR-03・04 パイプの定義と設定の全項目（`PipeDef`・`PipeStage`・`StageCheck`・`StageJudge`・`JudgeItem`・`AgentDef`・`McpServerDef`・`StageConfig`・`Config`）と、実行の引数 `--after` が、表に載っている。過不足があれば、テストが落ちる。
  - D0082-AC-01：dataclass の `fields()` から集めた全項目が、表にある。表の内部の整合にも問題が無い（`test_d0082_ac01_*`）。
  - D0082-AC-02：表の鍵は、すべて実在する項目か `--after`（`test_d0082_ac02_表の鍵はすべて実在する`）。
  - D0082-AC-03：項目を1つ足した偽の dataclass を渡すと、検査が「表に無い」と報告する。実在しない鍵は「実在しない」と報告する（`test_d0082_ac03_*`）。
- FR-05 `docs/guide/pipes.md` の「会話の中で流すとき」の表に出る項目は、能力表の「断る」「一覧に出す」と同じ集合。
  - D0082-AC-08：`pipes.md` の2つの表の項目が、能力表と同じ集合（`test_d0082_ac08_*`）。
- FR-07 見つかった食い違いは直さず、表の注記（`caveat`）に書き留める。

## 決めたことと理由

- 表は `pipe_in/pipe/capability.py` に、標準ライブラリだけの Python のデータとして置く。JSON にすると、パッケージに入れる設定と、読み込みの検査が増える。拡張が読みたくなったら、`tests/fixtures/` の前例どおり JSON に書き出して、両側のテストで突き合わせる。
- `capability.py` は `definition`・`config` を import しない。項目は `"PipeStage.group"` の形の文字列で持ち、値は属性の名前で読む。全項目との突き合わせに使う dataclass は、呼ぶ側（テスト）が渡す。偽の dataclass で、検査そのものを確かめられる。
- 判断のしかたは、関数でなくデータで持つ（どこを見るか `scope`・どの項目か `path`・どう見るか `test`・出す文 `sentence`）。表の行の並びが、同じ `scope` の中の文の順番になる。
- 子の項目（`AgentDef.prompt`・`StageJudge.threshold`・`max_agent_calls`・`fetch_domains` など）は1項目ずつ表に書き、親の行（`via`）に結びつける。動きが親と違えば、検査が報告する。
- 設計から変えた点：行に `nested`（入れ子をたどる）を足した。`check.judge`（入れ子）と `web`・`fetch_domains`（どれか）が、`path` だけでは見分けられなかったため。
- `docs/guide/pipes.md` の表は、表から作らず、突き合わせる（文書は人の言い回しのまま）。
- 黙って無視している2項目（`setting_sources`・`auto_approve`）は、黙ったまま。表には理由の文を持たせた。一覧に出すかは別に決める。
- メモの表に無かった項目は、実物を読んで分類した：`PipeDef.description` は効く／`test_command`・`test_timeout_sec`・`max_retries`・`domain_dir`・`pause_for_review`・`max_buffer_mb` は関係しない／`Config.pipe`・`project_dir` は効く（内部の値）／`PipeStage.problems` は関係しない（検査用の内部の欄）。
- 表の注記に書き留めた、今の動き（直していない）：
  - 断る判断は、`pipeline.toml` の `[stages.<段>]` を、パイプに無い段の名前でも見る。一覧に出す判断は、パイプにある段だけを見る。
  - `kind` の文は、`dev` 以外の値でも「組み込みの開発フロー dev」の言い回しで出る。
  - `web = []`・`fetch_domains = []` は断らない。`add_dirs = []` は一覧に出さない。`pipeline.toml` の `max_budget_usd = 0` は断らない。
- 無人の実行（夜のまとめ実行）で進めた。次の点は推しの案で決めた（人の確認は朝）：表の置き場所と形／`pipes.md` は突き合わせる／黙る2項目は黙ったまま／子の項目の書き方／列の名前 `sdk`・`chat`／注記の持たせ方。

## 対象外・残った課題

- 黙って無視している項目を一覧に出すこと、拡張から表を読むこと、新しい実行役の実装、断る形を減らすこと、上の食い違いを直すことは、対象外。D0077 は書き換えていない。
- `docs/guide/pipes.md` の「そのほかは扱えます」の文は、項目を全部は挙げていない。突き合わせるのは2つの表だけ。
- `chat.py` の検査（D0082-AC-10）は、属性と文字列の並びを見る。辞書の鍵や `.get("…")` での読みは見ない。
- 監査の報告（1件。直していない）：A-01 `PipeDef.test_command`・`Config.max_retries`・`test_command`・`test_timeout_sec`・`domain_dir` は、SDK の道でも開発フロー（`kind = "dev"`）だけが読む。表は SDK の列を「効く」にしていて、理由の文は「会話の道だけが使わない」と読める。会話の列の「関係しない」は合っている。SDK の列を分けるか、理由の文を直すかは、朝に決める。
- 助言と審査は流さなかった（守り・プラグイン・`.claude/` に触れていないため）。

## 確かめたこと

- 本体 `python -m pytest -q`：全部通った。拡張は触っていない。
- 順番：先に、今の文と順番を書き写して固定するテスト（24 件）を足し、置き換える前の作りで通ることを確かめてから、表に置き換えた。置き換えのあとも、書き換えなしで通る。
- 赤の確かめ：表の検査のテストは、実装の前に「能力表が空」「検査の関数が無い」で落ちた。
- 置き換えの前後の突き合わせ：乱数で作った 20,000 通りのパイプと設定で、置き換える前の `chat.py` と後の `unsupported()`・`ineffective()` の戻りが、1 件も違わなかった。
- 画面の受け入れ基準は無い。会話の道の実機（`/pipe-in:pipe-run`）では、まだ確かめていない。
