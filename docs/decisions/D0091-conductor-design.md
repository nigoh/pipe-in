# D0091 司会役を1つにまとめる設計：純粋な部品と薄い殻に分け、動きを変えない段で移す（#143）

## 目的

「次にどの段を流すか・確認で止めるか・不合格ならどこへ戻すか・上限で止めるか・記録に何を書くか」を決める司会役が、3つある（SDK の道のパイプと開発フロー・会話の道・開発用の記録）。同じ決まりを別々に書いているので、1つを直すと、ほかがずれる。D0080（記録の土台）・D0081 と D0090（回数）・D0082（能力表）・D0083 と D0084（守り）で足場はそろえたが、判断そのものは、まだ別々。

この記録は、まとめた形と、移す順番を決める**設計**。この件では、製品コードもテストも変えない。実装は、下の段ごとの issue で行う。

行の番号は、この版（D0090 が入ったあと）の実物のもの。直すと動くので、段で直すときは関数の名前で探す。

## 機能要件と受け入れ基準

受け入れ基準は、この記録を読むか、差分を見て確かめる（テストは足さない。テストの名前に ID は付けない）。

- FR-01 3つの司会役の判断を、項目ごとに並べた表を作る。同じ所と、違う所（理由があって違う／歴史で違う）を分ける。
  - D0091-AC-01：下の「1. 判断の表」が、11項目（次の段の決め方・確認の取り方・`revise`・検査と差し戻し・上限・並列の枠・分岐・`--from`・`--after`・終わり方・記録に書く鍵）をすべて含み、各行に司会役ごとの欄と「同じ／違う（理由）／違う（歴史）」の別がある。
- FR-02 まとめた形を決める（実行役に依らない純粋な部品と、実行役ごとの薄い殻。置き場所と依存の向き）。
  - D0091-AC-02：「2. 選んだ形」に、純粋な部品の入力と出力、殻ごとの受け持ち、置き場所が書いてある。
  - D0091-AC-03：「3. 選ばなかった形」が2つ以上あり（「会話の道を SDK の道の殻にする」「3つとも1つのクラスにする」を含む）、それぞれに理由がある。
  - D0091-AC-06：置く部品はすべて、依存の向き（`pipe_in_generator` → `pipe_in.pipe` / `pipe_in.dev` → `pipe_in.engine` → `pipe_in.usage`）の逆向きの import を要しない。「5. 依存の向き」に、部品ごとの表で示してある。
- FR-03 移す順番を、動きを変えない小さな段に切る。段ごとの issue の下書きを付ける。
  - D0091-AC-04：「4. 移す順番」の全部の段に、「先に足すテスト」「動きが変わらないことの確かめ」「大きさ」の3つが書いてある。
  - D0091-AC-05：各段に issue の下書きがある。#140（D0090）との前後が書いてある。
- FR-04 まとめない所と、その理由を書く。
  - D0091-AC-07：「6. まとめない所と理由」に1つ以上あり、各々に理由がある。
- FR-05 記録の形・`pipe.toml`・コマンドの引数は変えない。変えたい所は、別の案として分ける。
  - D0091-AC-08：「7. 変えないもの」に明記してあり、変えたい所は「9. 別の案」に分けてある。
- D0091-AC-09：この件のコミットの差分が `docs/` の文書だけで、`pipe_in/`・`generator/`・`plugin/`・`vscode/`・`tests/`・`.claude/` に差分が無い。
- D0091-AC-10：この記録が `docs/decisions/README.md` の一覧に1行あり、`tests/test_rules.py` と `tests/test_doc_shape.py` が通る。

## 決めたことと理由

無人の実行で進めた。決めきれない点は推しの案で決めた（人の確認は朝。「8. 決めきれない点と推し」にまとめた）。実装の issue（下の下書き）は、まだ GitHub に作っていない。人が設計を読んでから作る。

### 0. 実物を読んで分かったこと

- 能力表（D0082）は `pipe_in/pipe/capability.py` にある（`pipe_in/engine/` ではない）。標準ライブラリだけで、`chat.py` の `unsupported()`・`ineffective()` が使う。
- 会話の道（`Chat`）は、`start`・`probe`・`next`・`done`・`review`・`status`。1回の呼び出しで1つの出来事を受け、`state.json` を読んで書いて終わる。「出来事を受けて次の動きを返す」形に、もう近い。
- SDK の道は2つの司会役を持つ。`LinearPipeline`（`_flow`・`_step`・`_member`・`review`）と `DevPipeline`（`_stages_from`・`_doc_stage`・`_red_stage`・`_build_and_test`・`review`＝土台のもの）。土台 `BasePipeline` は確認・保存・要約・終了コードを持つが、「次の段」は子に任せている。
- `chat.py` は `verdict_outcome`・`command_outcome`・`stage_checks`・`exit_message`・`check_summary_lines` を `pipe_in.pipe.pipeline`（SDK の道の司会役）から読む（L38）。D0090 が「司会役をまとめる件で扱う」と残した所。
- 開発用の記録 `Recorder`（`record.py`）は、次の段も上限も決めない。段の表（`OUTPUTS`・`REVIEWED`・`STAGES`）と終わりの名前（`FINALS`）を持つだけ。判断は会話のスキルが持つ。
- 開発フローの差し戻しの回数は、記録の `flow` にも段の `check` にも無く、`cfg.max_retries`（`pipeline.toml`）を `_build_and_test` の `for` の範囲で使う。`load_config`（`config.py` L158）は負の数を検めない。

### 1. 判断の表（D0091-AC-01）

セルの根拠は関数の名前（と、この版の行）。「別」は 同じ／違う（理由）／違う（歴史）。1行に混ざるときは、混ざった所を分けて書いた。

| 項目 | SDK・パイプ（`LinearPipeline`） | SDK・開発フロー（`DevPipeline`） | 会話の道（`Chat`） | 開発用の記録（`Recorder`） | 別 |
| --- | --- | --- | --- | --- | --- |
| 次の段の決め方 | `_next_of`（`pipe/pipeline.py` L385-399）：`routes` の `choice` → `next` → 次の添字。`_flow` が添字で進む。 | `_stages_from`（`dev/pipeline.py` L252-274）：`if start <= N` の固定5段。定義は無い。 | `done`（`chat.py` L614-619）：`ps.next` か次の段名か `END` を `chat.next_stage` に保存。 | 持たない。`_stage`（L74-77）が名前を検めるだけ。 | パイプと会話は同じ（`next` → 次の段。書き方だけ違う）。開発は違う（歴史：固定の5段）。 |
| 確認の取り方 | `_step`（L329-349）：`review` の段で、`auto_approve` なら飛ばし、`pause_for_review` なら `pending`（`next` 付き）、それ以外は `_confirm`。検査に通ってから取る。 | `_doc_stage`（L311-334）・`_red_stage`（L157-173）：形は同じ。`_pause`（`engine/pipeline.py` L302-309）の `pending` に `next` が無い。 | `done`（L620-629）：`review` の段は必ず `pending_review`（`next` 付き）。`auto_approve` は黙って効かない（能力表）。 | `wait`（L218-227）・`review`（L229-244）：印と結果を書くだけ。止める段は `REVIEWED`（L32）。 | 待ち方は違う（理由：端末・返事のファイル・会話・スキルで入出力が別）。開発の `pending` に `next` が無いのは違う（歴史）。「検査のあとに `review` の旗で止める」は同じ。 |
| `revise` | `_step`（L348-349）：同じ会話の続き（`resume`）でその場でやり直す。`review()`（L225-229）は `first=` で `_flow` を再開。`steps` に数えない（L259）。 | `_doc_stage`（L331-334）・土台の `review`（L349-352）：同じ。数える物が無い。 | `review`（L674-678）が `chat["revise"]` に置き、`next`（L395-397）が `kind="revise"` で返す。`steps` に数えない。直す点が空なら断る（L657-660）。 | `review`（L229-244）：直す点が無ければ断り（L238）、履歴に足すだけ。 | 数えない・直す点が要るは同じ。会話の続き（`resume`）は違う（理由：会話の道の `session_id` は `None`）。 |
| 検査と差し戻し | `_check`（L351-383）：判定・審査・確認用コマンド → 履歴に `check` → `_flow`（L265-276）が `flow_retries` を見て `on_fail`（無ければ自分）へ戻す。 | `_test`（L177-202）・`_build_and_test`（L204-223）：判定は pass / fail / blocked の3値。`cfg.test_command` で pass を fail に直す。戻し先は常に実装。履歴は `verdict`。 | `done`（L585-612）：`verdict_outcome`・`command_outcome`（パイプと同じ関数）。審査は断る。直す点は `chat.notes` に保存。 | `verdict`（L264-284）・`red`（L248-262）：結果を書くだけ。 | パイプと会話は同じ（関数を共有）。開発は違う（歴史：3値・`verdict` の記録・`cfg.max_retries`）。審査は違う（理由：会話の道に構造化出力が無い）。 |
| 上限（`max_steps`・`max_retries`） | `max_steps`：増やしてから比べ（L260-262）、超えたら `_too_many_steps`（L305-308）で `STAGE_ERROR`。`max_retries`：段の `check.max_retries` を `flow_retries` と比べる（L267-270）。 | `max_steps` は無い。`cfg.max_retries` を試行の `for`（L206-223）で使う。回数は `flow` に書かない。 | `max_steps`：比べてから増やす（`next` L399-404）。同じ文・同じ `STAGE_ERROR`。`max_retries`：`done`（L601-605）。回数は `_counts`（L116-126）が `flow` と `chat.*` の大きいほうを採る。 | 持たない。 | 止まる回と文は同じ。止まった時点の `steps` が1違うのは違う（歴史：D0090 で固定）。開発は違う（歴史）。 |
| 並列の枠 | `_flow`（L245-256）・`_group_members`・`_member`（L289-303）：同じ `group` を `asyncio.gather`。枠の中は自分だけやり直す（その場の `tries`）。`steps` は人数分。 | 無い。 | 断る（能力表 `PipeStage.group`）。 | 無い。 | 違う（理由：会話の道は段を1つずつしか流せない）。 |
| 分岐 | `_next_of`（L387-396）：`choice` が `routes` に無ければ `_BadRoute`。履歴に `route`。 | 無い。 | 断る（能力表 `PipeStage.routes`。構造化出力が無い）。 | 無い。 | 違う（理由：同上）。 |
| `--from` | `run`（L179-206）：`from_stage` より前の成果物があるかを見る（`routes`・`next`・`group` のある段は除く）。回数は 0 から。受けた元は記録から。 | `run`（L239-250）・`_check_prereq`（L227-237）：段ごとに手で書いた必要なファイルの表。`skip_first_impl`。 | 無い。やり直しは `chat start`（途中の記録があれば断る。L302-306）。 | 無い。やり直しは `start`。 | 会話・記録は違う（理由：記録の続きで進める）。パイプと開発は違う（歴史：開発の表が手書き）。 |
| `--after` | `receive`（L139-148）：`after.check_received`・`guard_for`。 | 付けられない（`cli.py` L114）。 | 断る（能力表 `--after`）。 | 無い。 | 違う（理由：前の実行の受け取りは SDK の道の機能）。 |
| 終わり方（終了コード・`final`・まとめ） | 土台の `_finish`（L391-399）：`_save_state`・`_write_summary`。終了コードは `int(Exit)`。`final` は `result.name`（`AWAITING_REVIEW` は空。L258）。文は `exit_message`。 | 同じ `_finish`。文は「テストまで合格しました」。`BLOCKED` を使う。 | `_finish`（L719-724）：`final` を書き、`pending_review`・`open` を消す。まとめは別の `_summary`（L726-761）。`AWAITING_REVIEW` は返さない（`pending_review` で表す）。 | `finish`（L288-298）：`FINALS` は `Exit` から `AWAITING_REVIEW` を除いたもの。まとめは別の `_summary`（L300-326）。 | `Exit` の名前と `final` は同じ。まとめを書く所が3つなのは違う（歴史）。費用の表が無いのは違う（理由：使用量が取れない）。 |
| 記録に書く鍵 | `_save_state`（L235-270）：`new_state`（D0080）。`driver` 無し、`flow`・`stages[].check`・`stages[].group`・`received_from`・`reply_wait`・`runs[].metrics`。 | 同じ `_save_state`。`flow`・`check`・`group` が無い。 | `new_state` ＋ `driver: pipe-chat`・`chat` 節・`open`・`flow` と `chat.*` の両方。使用量は「取れない」。 | `new_state` ＋ `driver: pipe-dev`・`open`。`flow`・`check` は無い。使用量は「取れない」。 | 使用量・返事の待ち・受けた元は違う（理由）。開発系が `flow`・`check` を書かないのは違う（歴史）。土台と鍵の並びは `tests/fixtures/state_record.json` が結ぶ。 |

表から分かること：同じ決まり（`next` の次・検査の読み・差し戻しの上限・`revise` を数えない・確認の旗・終わりの名前）が、パイプと会話で2回書かれている。開発フローは「歴史で違う」所が多く、パイプの定義に載せ直せる（5段の固定・`test` の検査・`implement` へ戻す）。

### 2. 選んだ形（D0091-AC-02）

#### 2.1 考え方

**「次にすることを決める」ところだけを、実行役に依らない純粋な部品にする。** 入力は「定義から要る分」「回数」「今起きたこと」、出力は「次の動き」。時計・ファイル・SDK・シェル・標準出力に触れない。

**実行役ごとの「殻」は、動きを実行するところだけを持つ。** 殻は出来事を作って部品に渡し、返った動きを実行する。

```
殻（SDK・パイプ / SDK・開発 / 会話 / 記録）
   │  出来事（Ran・Checked・Answered・Begin）
   ▼
decide(plan, counts, event, policy) ──→ 次の動き（RunStage・CheckStage・AskReview・Finish）
   ▲
   └ plan（定義から写した小さな型）　counts（read_flow の結果）
```

#### 2.2 置き場所

`pipe_in/engine/conductor.py`（新しい。標準ライブラリだけ。`pipe_in` の他の部品を import しない）。`flow.py`・`state.py` と同じ「葉」の部品。

理由：3つの道が共に使える最下層は `engine`。ただし `engine` は `PipeDef` を知らない（依存の向き）ので、入力は `engine` 側の小さな型にして、定義から型への写しは各層に置く。

#### 2.3 型と関数

入力の型（どれも `frozen=True` の dataclass）：

| 型 | 欄 | 写し元 |
| --- | --- | --- |
| `CheckPlan` | `on_fail: str \| None`・`max_retries: int` | `PipeStage.check` の2欄。開発は `cfg.max_retries` |
| `StagePlan` | `name: str`・`review: bool`・`next: str \| None`・`routes: Mapping[str, str]`・`check: CheckPlan \| None`・`group: str \| None` | `PipeStage` の同名の欄 |
| `FlowPlan` | `stages: tuple[StagePlan, ...]`・`max_steps: int \| None` | `PipeDef`。開発は `max_steps=None`（上限なし） |
| `Counts` | `steps: int`・`retries: Mapping[str, int]` | `read_flow` の戻り（`engine/flow.py`）。壊れた記録の読みは今のまま |
| `Policy` | `auto_approve: bool`・`pause_for_review: bool`・`count_refused_step: bool` | 殻が決める。SDK は設定の値と `True`、会話は `False`・`True`・`False` |

`END = "end"` も `conductor.py` に置く（`definition.END` と同じ値。テストで同じと確かめる）。`Exit`・`EXIT_MESSAGES` もここへ移し、`engine/pipeline.py` から同じ名前で読めるようにする（`IntEnum` の同じ物。`from pipe_in.engine.pipeline import Exit` は変わらず通る）。

出来事（直前の結果）：

| 出来事 | 欄 | いつ |
| --- | --- | --- |
| `Begin` | `stage: str \| None` | 始め・`--from`・承認のあとの続き。`None` は最初の段 |
| `Ran` | `stage`・`ok: bool`・`choice: str \| None` | 段を流し終えた。`ok` が偽なら、失敗か成果物が無い |
| `Checked` | `stage`・`status: "pass" \| "fail" \| "blocked"`・`choice` | 検査の結果（直す点を集めるのは殻） |
| `Answered` | `stage`・`action: "approve" \| "revise" \| "quit"`・`next: str` | 人の答え。`next` は止まったときに決まっていた次 |

出力（次の動き）：

| 動き | 欄 | 殻のすること |
| --- | --- | --- |
| `RunStage` | `stage`・`kind: "stage" \| "retry" \| "revise"`・`counts` | 段を流す。`retry`＝戻す（直す点の文は殻が持つ）。`revise` は数えない |
| `CheckStage` | `stage` | 殻が検査して `Checked` を返す |
| `AskReview` | `stage`・`mode: "pause" \| "ask"`・`next` | `pause`＝止めて待つ（SDK は `AWAITING_REVIEW`、会話は `pending_review`）、`ask`＝その場で聞く |
| `Finish` | `exit: Exit`・`counts`・`warning: str \| None` | 終える。`warning` は、`max_steps` で止めたときと、分岐の飛び先が合わない（`BadRoute`）とき |

関数（どれも副作用が無い。群のときは殻が直接呼べるように公開）：

| 関数 | 決めること | 今の元 |
| --- | --- | --- |
| `decide(plan, counts, event, policy) -> Move` | 上の出来事から次の動き。下の4つを組み合わせる | 各殻の `_flow`・`done`・`review` |
| `next_target(plan, stage, choice) -> str \| BadRoute` | `routes` → `next` → 次の段 → `END`。`choice` が合わなければ `BadRoute(message)` | `_next_of`・`done` L614-619 |
| `admit_steps(plan, counts, n, policy) -> tuple[bool, int]` | `steps + n <= max_steps` か。拒んだときの `steps` は `count_refused_step` で決める | `_flow` L247-249・L260-262、`next` L399-404 |
| `after_failed_check(stage, counts) -> Retry \| Exhausted` | `used >= max_retries` なら尽きた。そうでなければ戻し先（`on_fail` か自分）と `retries + 1` | `_flow` L267-275、`done` L601-612 |
| `retry_left(used, max_retries) -> bool` | 枠の中の自分だけのやり直し | `_member` L299 |
| `review_mode(stage, policy) -> "none" \| "pause" \| "ask"` | 確認を取るか、止めるか、聞くか | `_step` L329-331、`done` L620 |

`decide` の決まり（今の動きを写す）：
- `Begin` → 段を流す前に `admit_steps`。通れば `RunStage(kind="stage")`、通らなければ `Finish(STAGE_ERROR, warning="段を流した回数が max_steps（N）を超えたため止めました")`。
- `Ran(ok=False)` → `Finish(STAGE_ERROR)`。`Ran(ok=True)`：`check` があれば `CheckStage`、無ければ `next_target` → `review_mode` → `AskReview`か次へ。`next_target` が `BadRoute` を返したら `Finish(STAGE_ERROR, warning=その文)`（今の `_step` が `_BadRoute` を受けて `STAGE_ERROR` にするのと同じ）。
- `Checked(blocked)` → `Finish(BLOCKED)`。`Checked(fail)` → `after_failed_check`。尽きたら `Finish(TEST_FAILED)`、そうでなければ `RunStage(kind="retry")`（戻し先に飛ぶ。ここでは `admit_steps` を通す）。`Checked(pass)` → `Ran(ok=True)` の「検査なし」と同じ道。
- `Answered(approve)` → `next` が `END` なら `Finish(PASSED)`、そうでなければ `RunStage`。`Answered(revise)` → `RunStage(kind="revise")`（`admit_steps` を通さず、`steps` も増やさない）。`Answered(quit)` → `Finish(STOPPED_BY_HUMAN)`。

#### 2.4 殻が持つもの

| 殻 | 持つもの（部品に入れないもの） |
| --- | --- |
| SDK・パイプ（`LinearPipeline`） | 段を流す（`runner`・`resume`・`first`）、検査の中身（`_check`：判定・審査・確認用コマンドを集めて `Checked` にする）、`_confirm`（端末と返事のファイル）、群の `asyncio.gather`、`routes` の `choice` を構造化出力から読む、履歴と `state.json` の書き方・順番、`--from`・`--after`、`notes`（メモリ） |
| SDK・開発フロー（`DevPipeline`） | 赤の段の中身（`parse_red`・抜けた AC・確認用コマンドで「落ちること」）、検査の3値と `test_command` の上書き、受信バッファの上限、`--from` の必要なファイルの表 |
| 会話の道（`Chat`） | JSON の返事、`state.json` の読み書き（`_counts` の「大きいほう」の合成も）、`probe`・指紋、`open`・`chat.notes`・`chat.revise`、`start` の断りと `archive`、`status` |
| 開発用の記録（`Recorder`） | 記録を書くだけ。`decide` は呼ばない。段の名前の並びと確認の旗は `dev_plan()` から読み（成果物 `OUTPUTS` と表示の名前は、今までどおり `dev.specs` から）、終わりの名前は `Exit` から読む |

殻に定義を渡す写し：
- `pipe_in/pipe/plan.py`：`plan_of(pipe: PipeDef) -> FlowPlan`。`pipe` 層。パイプと会話の道が使う。
- `pipe_in/dev/plan.py`：`dev_plan(max_retries: int) -> FlowPlan`。`dev` 層。開発フローの5段（確認 `requirements`・`design`・`red`）と `test` の `CheckPlan(on_fail="implement", max_retries=cfg.max_retries)`、`max_steps=None`。`Recorder` もここから段の表を読む。

#### 2.5 開発用の記録（`record.py`）をどこまで含めるか

含める。ただし範囲は「同じ表を読む」までで、`decide` は呼ばない。

- `Recorder` の `REVIEWED`（確認の旗）・`STAGES`（名前の並び）を `dev_plan()` から、`FINALS` を `Exit` から作る。成果物の表 `OUTPUTS` と表示の名前は `StagePlan` に載せず、今までどおり `dev.specs` から読む。これで開発フローの段の決まりが、`DevPipeline` と `Recorder` で1か所になる。
- 判断（次にどの段を流すか・差し戻すか）は、これまでどおり会話のスキルが持つ。`Recorder` が判断を持つと、スキルと二重になる。
- 含めない案と、`pipe-in record next` を足す案は「9. 別の案」に分けた。

#### 2.6 `chat.py` が SDK の司会役を読まなくする

`verdict_outcome`・`command_outcome`・`stage_checks`・`exit_message`・`check_summary_lines`（とその補助 `_judge_line`）を、新しい `pipe_in/pipe/outcome.py` へ移す。`pipe/pipeline.py` からは同じ名前で読めるまま（D0090 の `read_flow` と同じやり方）。`chat.py` は `outcome.py` と `engine/conductor.py` を読み、`pipe/pipeline.py` を読まない。

### 3. 選ばなかった形（D0091-AC-03）

| 形 | 理由（選ばなかった） |
| --- | --- |
| **A. 会話の道を SDK の道の殻にする**（`LinearPipeline` を会話の道から使う） | `LinearPipeline` の `_flow` は、1回の `await` の中で最後まで（または確認まで）走るループ。会話の道は、1つの出来事ごとにプロセスが終わり、`state.json` から再開する。ループを「1歩ずつ」に割ると、`runner`・`ask`・`asyncio.gather` を持つ SDK の道そのものを作り直すことになる。会話の道は SDK を読まない（D0077-AC-35、`tests/test_architecture_chat.py`）ので、`BasePipeline`（`engine.runner` を読む）を継ぐ形も取れない。 |
| **B. 3つとも1つのクラスにする** | 3つの道は、入出力が違う（SDK・JSON・記録だけ）。1つのクラスに `if 実行役 ==` を入れると、能力表（D0082）が追い出した「項目の名前で分ける条件」が戻る。開発用の記録は判断を持たない設計（スキルが持つ）で、クラスにまとめると判断を持たされる。 |
| **C. 今のまま、足場（D0080〜D0090）だけで続ける** | 記録の形・回数・断る形は共通になった。だが「次の段」「上限」「差し戻し」「確認の旗」の判断は、`_flow` と `done` と `review` に2回書かれたまま。直すたびにずれる（#143 の困りごと）が残る。 |
| **D. 能力表（D0082）に判断を入れる** | 表は「項目 × 実行役の動き」のデータ。順番・回数・分岐は状態を持つ判断で、表のデータにすると表が手続きになる。能力表は「この形は扱えるか」を答え、部品は「扱えるとして次に何をするか」を答える、と分ける。 |
| **E. 純粋な部品を `pipe/` に置いて `dev` が読む** | `dev → pipe` は向きとして逆（`RULES` で `pipe_in.dev` は `pipe_in.pipe` を import できない）。`dev` が部品を読めるようにするには `engine` に置くしかない。 |

### 4. 移す順番（D0091-AC-04・05）

どの段も「動きを変えない」。先にテストを足し、今の動きで通ることを確かめてから移す。段の途中でも `pytest -q` が全部通る状態でコミットする（1つの機能を1コミット）。

#140（D0090。済み）は先。段3 以降は、D0090 の `read_flow`・`_counts`・二つの道の台本（`tests/test_chat_flow_counts.py` の `SCRIPTS`）の上に立つ。

D0090 で残した「`max_steps` で止まった時点の `steps` が1違う」は、本線では**そのまま保つ**（`Policy.count_refused_step`：SDK は `True`、会話は `False`。`test_d0090_ac02_max_stepsで止まった時点のstepsは…` が固定している）。そろえるのは段7（任意。記録の値が1変わるので人の確認が要る）。

#### 段の一覧

| 段 | 題 | 大きさ |
| --- | --- | --- |
| 1 | 台本を固定する（テストだけ） | 小 |
| 2 | 部品の足場を作る（`conductor.py`・`plan.py`・`outcome.py`） | 中 |
| 3 | 会話の道を部品に任せる | 中 |
| 4 | SDK・パイプを部品に任せる | 大 |
| 5 | 開発フローと開発用の記録を部品に任せる | 中 |
| 6 | 仕上げ：判断が殻に残らない検査と文書 | 小 |
| 7（任意） | 数える順をそろえる | 小 |

#### 段1 台本を固定する（テストだけ）

- すること：製品コードは変えない。「3つの司会役の台本表」のテストを足す。1つの台本を、流せる道に流して、止まる所・`final`・終了コード・`flow`・`runs` の `check`・`review`・`route` の並び・`state.json` の鍵の並びを、そのまま期待値にして固定する。
- 先に足すテスト：`tests/test_conductor_script.py`。
  - 二つの道の共通の台本：D0090 の `SCRIPTS`（通る／不合格で戻す／上限／承認／直しを頼む）に、`on_fail` が前の段・自分・`max_steps` ちょうど・`max_retries = 0`・`end` への飛び先・最後の段で確認を足す。SDK の道は `runner` と `ask` を、会話の道は `chat next`・`done`・`review` を差し替えて流す。
  - SDK だけの台本：`routes`（合う・合わない `BadRoute`）、並列の枠（steps が人数分・枠の中のやり直し）、`--from`（前の成果物が無ければ断る）、`--after`、`--review` の古い記録（`pending` に `next` が無い）。
  - 開発フローの台本：既存の `tests/test_pipeline.py` の `test_all_pass`・`test_retry_then_pass`・`test_retry_limit`・`test_blocked_stops_without_retry` を台本表に載せる。`cfg.max_retries = 0` と、負の数（今の動きを固定。「10. 危ない所」）を足す。
- 動きが変わらないことの確かめ：製品コードに差分が無い（`git diff` が `tests/` だけ）。足したテストが、今の版で全部通る。赤は無い（固定のテストなので、期待どおりに「始めから通る」ことを確かめる）。
- 大きさ：小。
- 触るファイル：`tests/test_conductor_script.py`（新）。

#### 段2 部品の足場を作る

- すること：`pipe_in/engine/conductor.py`（型・出来事・動き・関数・`END`・`Exit`・`EXIT_MESSAGES`）、`pipe_in/pipe/plan.py`（`plan_of`）、`pipe_in/dev/plan.py`（`dev_plan`）、`pipe_in/pipe/outcome.py`（`verdict_outcome` ほかを移す）を足す。`engine/pipeline.py` と `pipe/pipeline.py` は同じ名前で読めるように再び出す。まだ殻は部品を使わない。
- 先に足すテスト：`tests/test_conductor.py`（`decide` と4つの関数を表で。値は、段1の台本の「今の動き」から書き写す。`next_target` の3つの順・`BadRoute`・`admit_steps` の境界（`max_steps` ちょうどと+1・`count_refused_step` の両方）・`after_failed_check`（尽きる境界）・`review_mode` の組み合わせ・`Answered(revise)` が `steps` を増やさないこと）、`tests/test_conductor_plan.py`（`plan_of` が `PipeStage` の欄を写す。`PipeStage` に欄を足したら、写す必要の有無を能力表と同じやり方で検査する：`plan_of` が読む欄の一覧と、`routes`・`next`・`group`・`check`・`review` の欄の突き合わせ）、`tests/test_architecture_conductor.py`（「5. 依存の向き」の検査のうち、足場の分）。
- 動きが変わらないことの確かめ：既存のテストが書き換えなしで全部通る。`pipe_in.engine.pipeline.Exit is pipe_in.engine.conductor.Exit` を確かめるテストを足す。`pipe_in.pipe.pipeline.verdict_outcome is pipe_in.pipe.outcome.verdict_outcome` も。誰も部品を呼ばないので、本体の動きは変わりえない。
- 大きさ：中。
- 触るファイル：`pipe_in/engine/conductor.py`（新）・`pipe_in/engine/pipeline.py`（`Exit`・`EXIT_MESSAGES` を再び出す）・`pipe_in/pipe/plan.py`（新）・`pipe_in/pipe/outcome.py`（新）・`pipe_in/pipe/pipeline.py`（移した関数を再び出す）・`pipe_in/dev/plan.py`（新）、テスト3つ、`docs/development/design.md`（置き場所の表に近い部品の隣へ1〜2行）。

#### 段3 会話の道を部品に任せる

- すること：`Chat.next`・`done`・`review` の判断を `decide` への出来事に置き換える。`chat.py` は `pipe/pipeline.py` を読まず、`outcome.py` を読む。`_counts`・`_set_counts`・`_save`・`chat.notes`・`chat.revise`・`next_stage` は殻に残す。`Policy(auto_approve=False, pause_for_review=True, count_refused_step=False)`。
- 先に足すテスト：段1の台本表が、そのまま段3の確かめ。さらに、`tests/test_chat_flow.py`・`test_chat_flow_counts.py`・`test_chat_start.py`・`test_chat_capability_text.py` を書き換えない。足すのは、`tests/test_architecture_conductor.py` の「`chat.py` は `.pipeline` から何も読まない」（D0090-AC-08 を広げる）と、「`chat.py` に `max_steps`・`max_retries` の比べる式が残らない」（D0082-AC-10 と同じやり方）。この2つは、移す前は落ちる（赤）ことを確かめる。
- 動きが変わらないことの確かめ：段1の台本表・既存の会話の道のテスト（`test_chat_*.py` 全部）・`tests/test_state_schema.py` の鍵の並びが、書き換えなしで通る。`state.json` のバイト列が、同じ台本・同じ時計で前後で同じ（段1の表に「バイト列の一致」の列を入れておく）。
- 大きさ：中。
- 触るファイル：`pipe_in/pipe/chat.py`、テスト（`tests/test_architecture_conductor.py` に検査を足す）、`docs/guide/` は変えない（見える動きが無い）。

#### 段4 SDK・パイプを部品に任せる

- すること：`LinearPipeline._flow`・`_step`・`_member`・`_next_of`・`review` の判断を部品に置き換える。`_BadRoute` は `BadRoute` の戻りに置き換える。`Policy(auto_approve=cfg.auto_approve, pause_for_review=cfg.pause_for_review, count_refused_step=True)`。履歴を書く順番（`check` → `route` → `review`）と画面の出力は変えない。
- 先に足すテスト：段1の台本表（SDK だけの台本を含む）。加えて、`LinearPipeline` の判断の呼び出しが、群のとき `admit_steps(n=len(members))` を1回だけ呼ぶこと、`revise` の流し直しが `steps` を増やさないことを、`tests/test_conductor_script.py` の中で足す。
- 動きが変わらないことの確かめ：既存の `tests/test_pipe_flow.py`・`test_pipe_flow_counts.py`・`test_pipe_group_record.py`・`test_pipe_check_record.py`・`test_reply_pipeline.py`・`test_pipe_after_flow.py` が書き換えなしで通る。段1の台本で `state.json` と `99_summary.md` が前後で同じ。`test_d0090_ac02_*`（二つの道で `flow` が一致・止まった時点の `steps` の違い）が通る。
- 大きさ：大。`_flow` は群・分岐・`first`・差し戻し・上限を1つのループに持つ。この段だけは、`_member`（群）と `review()` を別のコミットで先に移し、最後に `_flow` の本体を移すこともできる（段の中で割ってよい。コミットは機能ごと）。
- 触るファイル：`pipe_in/pipe/pipeline.py`、必要なら `pipe_in/engine/pipeline.py`（`pending` の作り）。

#### 段5 開発フローと開発用の記録を部品に任せる

- すること：`DevPipeline._build_and_test` の「尽きたか」と、`_doc_stage`・`_red_stage` の「確認の旗」を、`dev_plan()` と `after_failed_check`・`review_mode` に置き換える（ループの形はそのまま。部品を呼ぶだけ）。`_check_prereq` の表はそのまま（まとめない。「6.」）。`Recorder` は `dev_plan()` から段の名前の並びと確認の旗を、`Exit` から `FINALS` を読む（成果物と表示の名前は `dev.specs` のまま）。`decide` は呼ばない。
- 先に足すテスト：`cfg.max_retries` が 0・1・負の数のときの試行の回数と終わり（今の動きを固定。段1にも入れておく）と、`Recorder` の `REVIEWED`・`STAGES`・`FINALS` が `dev_plan()`・`Exit` と同じ集合であること。「`record.py` が `decide` を import しない」検査。
- 動きが変わらないことの確かめ：`tests/test_pipeline.py`・`test_record.py`・`test_record_order.py`・`test_record_check_cli.py`・`test_state_schema.py` が書き換えなしで通る。`pipe-in record` の各コマンドの出力と `state.json` のバイト列が同じ。
- 大きさ：中。
- 触るファイル：`pipe_in/dev/pipeline.py`・`pipe_in/dev/record.py`・`pipe_in/dev/plan.py`、テスト。

#### 段6 仕上げ：判断が殻に残らない検査と文書

- すること：3つの殻に、判断の条件（`max_steps`・`max_retries` を比べる式、`.routes` の読み、`review` と `auto_approve` の組み合わせ）が残らないことを検査する。`docs/development/design.md`（置き場所の表・「形を変えるとき」の項目を足すときの注意）、`docs/guide/`（開発の節に、司会役の部品の1段落）、決定の記録を整える。
- 先に足すテスト：`tests/test_architecture_conductor.py` の判断が残らない検査（3つの殻）と、検査そのものが残った式を見つけられること（D0082-AC-10 と同じ形）。
- 動きが変わらないことの確かめ：文書と検査だけの変更。本体のテストが全部通る。
- 大きさ：小。
- 触るファイル：`tests/test_architecture_conductor.py`、`docs/development/design.md`、`docs/guide/`、`docs/decisions/`。

#### 段7（任意）数える順をそろえる

- すること：SDK の道の `Policy.count_refused_step` を `False` にして、`max_steps` で止まった時点の `steps` を `max_steps` にそろえる（会話の道と同じ）。**`state.json` の `flow.steps` の値が、止まった時だけ1変わる**。人の確認が要る（D0091 の本線に入れない）。
- 先に足すテスト：`test_d0090_ac02_max_stepsで止まった時点のstepsは…` を「両方の道で `max_steps`」に書き換える（意図した変更）。群の途中で拒んだときに `steps` が増えないことを足す。
- 動きが変わらないことの確かめ：止まる回・文・`final`・終了コードは同じ。変わるのは `flow.steps` の値だけ。終わった記録（`final` あり）は `--review` で続けないので、続きの上限には効かない。拡張は `flow` を読まない。
- 大きさ：小。
- 触るファイル：`pipe_in/pipe/pipeline.py`・テスト・`docs/development/design.md`（「形を変えるとき」に1項目）。

#### issue の下書き

形は `.github/ISSUE_TEMPLATE/feature.yml`（困っていること／してほしいこと／対象外／触る側／ほかに）。受け入れ基準はその issue の中での番号。

**段1：司会役の動きを台本の表で固定する（テストだけ）**
- 困っていること：司会役を1つにまとめる（#143・D0091）前に、今の動きを固定したい。そうしないと、移したときに動きが変わったかを確かめられない。
- してほしいこと：FR-01 同じ台本を SDK の道・会話の道・開発フローに流す表のテストを足す（止まる所・`final`・`flow`・履歴の並び・`state.json` の鍵の並び）。FR-02 SDK だけの台本（分岐・並列・`--from`・`--after`・古い `pending`）と、開発の `cfg.max_retries` の境界も固定する。
- 受け入れ基準：AC-01 今の版で全部通る。AC-02 製品コードの差分が無い。AC-03 止まった時点の `steps` の違い（D0090）も表に載っている。
- 対象外：製品コードの変更。 触る側：本体のテスト。 大きさ：小。

**段2：司会役の部品の足場を作る（`conductor.py`・`plan.py`・`outcome.py`）**
- 困っていること：「次の段・上限・差し戻し・確認の旗」の判断が、`_flow` と `done` で2回書かれている。
- してほしいこと：FR-01 `pipe_in/engine/conductor.py` に型・出来事・動き・関数を足す（`Exit` もここへ。`engine/pipeline.py` から同じ名前で読める）。FR-02 `pipe/plan.py`・`dev/plan.py` に定義の写しを足す。FR-03 `pipe/outcome.py` へ検査の読みを移す（`pipe/pipeline.py` から同じ名前で読める）。
- 受け入れ基準：AC-01 `conductor.py` は標準ライブラリだけ。AC-02 `decide` と4つの関数が表のテストで固定されている。AC-03 既存のテストが書き換えなしで通る。AC-04 まだ誰も部品を呼ばない。
- 対象外：殻の置き換え。 触る側：本体・文書。 大きさ：中。

**段3：会話の道を部品に任せる**
- 困っていること：会話の道が、パイプと同じ判断を別に書いていて、SDK の司会役のモジュールも読んでいる。
- してほしいこと：FR-01 `Chat.next`・`done`・`review` の判断を `decide` に任せる。FR-02 `chat.py` は `pipe/pipeline.py` を読まない。
- 受け入れ基準：AC-01 台本の表と既存の会話の道のテストが書き換えなしで通る。AC-02 同じ台本で `state.json` のバイト列が前後で同じ。AC-03 `chat.py` に `max_steps`・`max_retries` を比べる式が無い。
- 対象外：数える順をそろえること。 触る側：本体。 大きさ：中。

**段4：SDK・パイプを部品に任せる**
- 困っていること：`LinearPipeline._flow` に、次の段・上限・差し戻し・確認の判断が直に書かれている。
- してほしいこと：FR-01 `_flow`・`_step`・`_member`・`_next_of`・`review` の判断を部品に任せる。FR-02 履歴を書く順番と画面の出力は変えない。
- 受け入れ基準：AC-01 パイプ関係の既存のテストが書き換えなしで通る。AC-02 台本の表で `state.json` と `99_summary.md` が前後で同じ。AC-03 止まった時点の `steps`（`max_steps + 1`）が同じ。
- 対象外：並列・分岐を会話の道で流すこと。 触る側：本体。 大きさ：大。

**段5：開発フローと開発用の記録を部品に任せる**
- 困っていること：開発フローの段の表が `DevPipeline` と `Recorder` の2か所にあり、差し戻しの尽きる判断も別に書いている。
- してほしいこと：FR-01 `DevPipeline` が `dev_plan()` と部品を使う。FR-02 `Recorder` が段の表を `dev_plan()` から、終わりの名前を `Exit` から読む。判断は持たない。
- 受け入れ基準：AC-01 `test_pipeline.py`・`test_record*.py` が書き換えなしで通る。AC-02 `cfg.max_retries` が 0・1・負の数のときの動きが同じ。AC-03 `record.py` が `decide` を import しない。
- 対象外：`pipe-in record next` を足すこと。 触る側：本体。 大きさ：中。

**段6：判断が殻に残らない検査と文書**
- 困っていること：まとめたあと、また殻に判断が書き足されると、ずれが戻る。
- してほしいこと：FR-01 3つの殻に判断の式が残らない検査を足す。FR-02 置き場所の表・ガイド・決定の記録を整える。
- 受け入れ基準：AC-01 検査が残った式を見つけられる。AC-02 文書が実物に合う。AC-03 全テストが通る。
- 対象外：動きの変更。 触る側：本体のテスト・文書。 大きさ：小。

**段7（任意）：`max_steps` で止まった時点の `steps` をそろえる**
- 困っていること：SDK の道は `max_steps + 1`、会話の道は `max_steps` を記録する（D0090）。
- してほしいこと：FR-01 SDK の道も `max_steps` にそろえる。
- 受け入れ基準：AC-01 止まる回・文・終了コードは同じ。AC-02 `flow.steps` が両方の道で `max_steps`。
- 対象外：記録のほかの値。 触る側：本体。 大きさ：小。 ほかに：記録の値が1変わる。人の確認が要る。

### 5. 依存の向き（D0091-AC-06）

依存の向きは `pipe_in_generator` → `pipe_in.pipe` / `pipe_in.dev` → `pipe_in.engine` → `pipe_in.usage`。新しい部品は、どれも矢印の向きに読むだけ。

| 部品 | 置き場所 | 読むもの | 読まれるもの | 逆向き？ |
| --- | --- | --- | --- | --- |
| `conductor.py`（型・`decide`・`Exit`） | `pipe_in/engine/` | 標準ライブラリだけ（`dataclasses`・`enum`・`typing`・`collections.abc`） | `engine/pipeline.py`（再び出す）、`pipe/plan.py`・`pipe/pipeline.py`・`pipe/chat.py`・`dev/plan.py`・`dev/pipeline.py`・`dev/record.py` | 無し（`engine` の葉。`pipe`・`dev`・`usage` を読まない） |
| `plan.py`（`plan_of`） | `pipe_in/pipe/` | `engine.conductor`・`pipe.definition` | `pipe/pipeline.py`・`pipe/chat.py` | 無し（`pipe` → `engine`） |
| `outcome.py`（検査の読み） | `pipe_in/pipe/` | `engine.pipeline`（`ShellResult`・`one_line`・`Exit`・`EXIT_MESSAGES`）・`pipe.definition`（`PipeDef`。`stage_checks` が読む）・標準ライブラリ | `pipe/pipeline.py`（再び出す）・`pipe/chat.py` | 無し（`pipe` → `engine`）。`chat.py` が `pipe/pipeline.py` を読まなくなる |
| `plan.py`（`dev_plan`） | `pipe_in/dev/` | `engine.conductor`・`dev.specs` | `dev/pipeline.py`・`dev/record.py` | 無し（`dev` → `engine`。`pipe` を読まない） |
| `engine/pipeline.py`（`Exit` を再び出す） | `pipe_in/engine/` | `engine.conductor` を足す | 今までどおり | 無し（同じ層の中） |
| `generator/chat_cmd.py` | `generator/` | 変えない | | 無し |

守りの部品（`engine/guard.py`・`generator/guard_hook.py`・`.claude/hooks/pipe_in_guard.py`）は触らない。止める範囲を狭めない（すり抜けの道を塞ぐテストは要らない）。会話の道の `tests/test_architecture_chat.py` の禁止（SDK・`engine.runner`・`subprocess`・`pipe_in.dev`・`pipe_in.cli`）は、`chat.py` が `engine.conductor`・`pipe.plan`・`pipe.outcome` を読んでも保たれる（どれも禁止の外）。

#### `tests/test_architecture_conductor.py` に足す検査の案

新しい検査は決定ごとの別ファイル（`docs/development/workflow.md` の「8.」）。`_imports`・`_module_name`・`_outside_stdlib` は `from test_architecture import …` で使う。

1. `conductor.py` は標準ライブラリだけで、読んでよいのは `__future__`・`dataclasses`・`enum`・`typing`・`collections.abc` の範囲（`os`・`subprocess`・`datetime`・`time`・`random`・`json`・`pathlib` を読まない＝ファイル・時計・乱数に触れない）。
2. `conductor.py` が `pipe_in` の他の部品を import しない。
3. `chat.py` が `pipe_in.pipe.pipeline` から何も読まない（D0090-AC-08 は `read_flow` についてだけ見ている。それを、全部の名前に広げる）。
4. 3つの殻（`chat.py`・`pipe/pipeline.py`・`dev/pipeline.py`）に、`max_steps`・`max_retries` を含む比較の式と、`.routes` の読みが無い（`plan_of`・`dev_plan` の中は除く。D0082-AC-10 と同じ、属性と比較の並びを AST で見る）。
5. `record.py` は `engine.conductor` から `Exit` だけを読む（`decide` ほかを読まない）。
6. `dev/plan.py` は `pipe_in.pipe` を読まない。
7. 検査そのものが違反を見つけられること（偽のソースで、`os` の import・`pipe_in.pipe` の import・残った式を見つける）。
8. `conductor.END == definition.END`、`conductor.Exit is engine.pipeline.Exit`。

### 6. まとめない所と理由（D0091-AC-07）

| まとめない所 | 理由 |
| --- | --- |
| 並列の枠の実行（`asyncio.gather`）と、枠の中のやり直しの回し方 | 会話の道は段を1つずつしか流せない（能力表で断る）。部品は `admit_steps(n)` と `retry_left` を出すだけで、同時に流すのは SDK の殻が持つ。 |
| 分岐の `choice` を構造化出力から読むこと | 会話の道に構造化出力が無い（能力表で断る）。部品は `choice` を受けて飛び先を決めるだけで、読むのは殻。 |
| `--from`・`--after` | 会話の道は記録の続きで進み（始め直しは `chat start`）、前の実行の受け取りは SDK の道の機能。開発フローの `_check_prereq` の表は手書きの歴史で、挙動を変えずに写すのが難しいのでそのまま（「9. 別の案」）。 |
| 確認の待ち方（`_confirm`・返事のファイル・端末の入力・`chat review`・`record wait`/`review`） | 入出力が実行役ごとに違う。部品は「止めるか・聞くか」だけを決める。 |
| 検査の中身（判定・審査・確認用コマンドを集める）と、開発の3値（`blocked`）・`test_command` での上書き・赤の段（`parse_red`・抜けた AC・赤の確認用コマンド） | 内容の判断で、順番の判断ではない。開発フロー専用で、パイプの `check` に載せ直すと意味が変わる。 |
| 直す点の文（`notes`）の置き場所 | SDK はメモリ、会話の道は `state.json` の `chat.notes`（呼び出しごとにプロセスが終わるため）。 |
| `revise` のときの会話の続き（`resume`） | SDK の道だけの機能（会話の道は `session_id` が `None`）。 |
| まとめ（`99_summary.md`）を書く3つの関数 | 書式が違い（費用の表の有無）、今回の「判断」ではなく表示。まとめるなら別の件にする。 |
| 開発用の記録の判断 | 判断は会話のスキルが持つ設計。`Recorder` は表を読むだけで、`decide` を呼ばない。 |
| `state.json` を読んで書くこと（`_counts` の「大きいほう」の合成・`read_flow` 以外の読み） | 記録の読み書きは殻の仕事。壊れた記録の読みは `read_flow` のまま。 |
| 費用・使用量・`reply_wait`・`received_from` | SDK の道だけの記録の鍵（使用量は会話・記録では取れない）。 |

### 7. 変えないもの（D0091-AC-08）

この設計では、次のものは**変えない**。

- 記録の形：`state.json` の鍵の並びと値の種類、`logs/*.jsonl`、`99_summary.md`、`flow`、`chat.*`、終了コード 0〜5、`final` の値。`tests/fixtures/state_record.json` の共通の表は変えない。段の最後まで「バイト列が前後で同じ」を確かめる。
- `pipe.toml`・`pipeline.toml` の形（項目の追加も削除もしない）。能力表 `capability.py` も変えない。
- コマンドの引数：`pipe-in`（`--pipe`・`--from`・`--after`・`--review`・`--pause`・`--yes` ほか）、`pipe-in-gen chat`、`pipe-in record`。
- 守り：`guard.py`・`guard_hook.py`・`pipe_in_guard.py`。依存は足さない（標準ライブラリだけ）。`package-lock.json` は触らない。
- 画面（拡張）：拡張のコードも、画面の受け入れ基準も無い。

変えたい所（記録の値が変わるもの・足すもの）は、すべて次の節。

### 8. 決めきれない点と推し（人の確認は朝）

| # | 点 | 案 | 推しで決めた |
| --- | --- | --- | --- |
| 1 | 純粋な部品の置き場所 | (a) `engine/conductor.py`、(b) `pipe/` に置く | (a)。`dev` が読める最下層が `engine` だけ（選ばなかった形 E） |
| 2 | 入力の渡し方 | (a) `engine` 側の小さな型＋各層の写し、(b) `capability.py` のように属性を名前で読む | (a)。型の欄が見え、`plan_of` の突き合わせの検査で欄の足し忘れを拾える。(b) は誤字を実行まで拾えない |
| 3 | `Exit` の置き場所 | (a) `conductor.py` に移して `engine/pipeline.py` から再び出す、(b) 葉の `exit.py`、(c) `conductor` が文字列を返す | (a)。ファイルが増えず、`Exit` が `Move` の欄に出る。再び出すので `from pipe_in.engine.pipeline import Exit` は通る |
| 4 | 出口の形 | (a) `decide` ＋ 4つの関数を公開、(b) 関数だけ、(c) `decide` だけ | (a)。会話の道は出来事ごとに `decide` を呼ぶのが自然。群のやり直しは `retry_left` を直接使う |
| 5 | 記録だけの道 | (a) 表だけ読む（`decide` は呼ばない）、(b) 含めない、(c) `record next` を足す | (a)。段の表が1か所になる。判断はスキルのまま |
| 6 | 数える順 | (a) 本線では保つ（`count_refused_step`）。そろえるのは段7（任意）、(b) 本線でそろえる | (a)。記録の値が変わる（FR-05）ので、人の確認がある別の段にする |
| 7 | 移す順番 | (a) 会話 → パイプ → 開発、(b) パイプ → 会話 → 開発 | (a)。会話の道は出来事ごとの形で、`decide` と合う。D0090 の二道比較がある。いちばん大きい `_flow` は最後に回す |
| 8 | 検査の読みの置き場所 | (a) `pipe/outcome.py`、(b) `engine/` | (a)。`verdict_outcome` は `ShellResult` と `PipeStage` の言葉に近く、`engine` に置くと範囲が広がる |
| 9 | 設計の文書の置き場所 | (a) 決定の記録 D0091 に全部、(b) `docs/guide/` に別の文書 | (a)。長ければ記録の中の節で分ける |

### 9. 別の案（本線に入れない）

本線には入れない。人が選んだら、別の件で行う。

- **B-1 数える順をそろえる**：段7。記録の `flow.steps` の止まった時点の値が、SDK の道だけ `max_steps + 1` → `max_steps` に変わる。
- **B-2 `pipe-in record next` を足す**：開発用の記録に、「次にすることを返す」コマンドを足す。スキルが `decide` に問い合わせる形になる。コマンドの引数が増える（FR-05 に触れる）。スキルの文も変わる。
- **B-3 開発フローを `kind = "linear"` のパイプとして定義し直す**：`_stages_from` を無くして `LinearPipeline` で流す。`blocked`・`verdict` の記録・赤の段の中身が変わるので、記録と挙動が変わる。やるなら、赤の段を `check` の外に出す設計が先に要る。
- **B-4 まとめ（`99_summary.md`）の3つの書き手を1つにする**：書式の差（費用の表の有無）を残す形で。
- **B-5 `_check_prereq` の表を `dev_plan()` から作る**：開発の `--from` の必要なファイルを、段の `output` から導く。
- **B-6 `chat.steps`・`chat.retries` を消して `flow` だけにする**：D0081 が「寄せるのは司会役をまとめるときに」と残し、D0090 で `flow` にも書くようにした（`chat.*` は写しとして残した）。写しを消すと記録の形が変わる（古い版の本体が続きを読めなくなる）ので、本線には入れない。

### 10. 危ない所

1. **`Exit` の移動**：`IntEnum` の同じ物を再び出す（作り直さない）。`isinstance`・比較・`int(Exit)`・`Exit[final]` が変わらないことを、段2のテストで確かめる。
2. **数える順**：SDK は増やしてから比べ、会話の道は比べてから増やす。群は人数分を先に足す（`_flow` L247）。`count_refused_step` で表すが、`Begin`（最初の段）・`retry`・群・`revise` の4つの入口で、増える所と比べる所の順を、台本に入れて固定する。
3. **履歴を書く順番と画面の出力**：`check` の記録 → `route` の記録 → `review` の記録の順、`_save_state` を呼ぶ位置、`print` の文が、拡張と `pipe-in record check`（`record_order.py`）の読みに効く。部品は何も書かず、殻が今の順で書く。
4. **古い記録**：`pending` に `next` が無い記録を `--review` で続ける道（`pipe/pipeline.py` L220-223）と、`flow` の無い記録（`read_flow`）は、殻に残す。
5. **開発の `cfg.max_retries`**：負の数のとき、今は `range(1, max+2)` が空で、実装も検証も流さずに `TEST_FAILED` で終わる。0 のときは1回だけ試す。部品の「`used >= max_retries`」に直すと、負の数では1回流してから尽きる。段1で今の動きを固定し、段5で `Policy` か殻の前置きで同じにするか、意図した変更として決定の記録に書く。
6. **能力表との二重**：会話の道は `routes`・`group` を `start` で断るので、`decide` に `choice=None` のまま `routes` のある段が来ることは無い。この前提は `unsupported` のテスト（`tests/test_chat_start.py`・`test_chat_capability_text.py`）に頼る。万一来たら、`decide` は `next_target` の `BadRoute` を `Finish(STAGE_ERROR)` にして返すので、会話の道も落ちずに終わる（多重の防ぎ）。
7. **`decide` が太る**：4つの関数に割り、`decide` は組み合わせだけにする。型が増えたら `Policy` に押し込まず、殻の側に置く。
8. **段4は大きい**：`_flow` を一度に置き換えず、`_member`・`review()`・`_flow` の順に、コミットを割ってよい（機能は1つのまま）。
9. **会話の道の `done` の順**：成果物が無ければ、検査の前に `STAGE_ERROR`。検査の記録は、尽きる判断の前に書く（L597-599）。この順を台本に入れる。

## 対象外・残った課題

- 実装（上の段1〜6 の issue で行う）。段7 と「9. 別の案」の B-1〜B-6 は、人が選んだら別の件で行う。
- 新しい実行役（専用のアプリなど）、並列の枠・分岐を会話の道で流せるようにすることは、対象外。
- 段ごとの issue は、この記録に下書きを置いただけで、GitHub にはまだ作っていない（`gh issue create` は人の承認が要る）。
- 開発フローの `cfg.max_retries` が負の数のときの動き（何も流さずに `TEST_FAILED`）を、そのまま保つか直すかは、段5で決める（「10. 危ない所」の 5）。

## 確かめたこと

- 表と形は、実物（`pipe_in/engine/pipeline.py`・`pipe_in/pipe/pipeline.py`・`pipe_in/dev/pipeline.py`・`pipe_in/pipe/chat.py`・`pipe_in/dev/record.py`・`pipe_in/engine/state.py`・`flow.py`・`pipe_in/pipe/capability.py`）を読んで、関数の名前と行を根拠に書いた。
- 監査で、この記録の食い違いが4件見つかり、どれもこの記録の文を直した：`dev_plan()` から読むのは名前の並びと確認の旗までで、成果物と表示の名前は `dev.specs` のまま／`BadRoute` は `decide` が `Finish(STAGE_ERROR)` にする／`outcome.py` の読むものに `pipe.definition` と `Exit` を足した／`chat.*` を消す案を B-6 に足した。動きの説明（数える順・`revise`・`pending` の `next`・負の `max_retries`）と依存の向きの表は、実物と合っていた。
- この件の差分は `docs/decisions/` の2ファイルだけ（D0091-AC-09）。`tests/test_rules.py`・`tests/test_doc_shape.py` が通った（D0091-AC-10）。助言と審査は流さなかった（製品コード・守り・`.claude/` に触れていない）。
