# D0051 実行の図に、段ごとの費用を上限と比べて出す

## 目的

実行を VSCode の拡張で見る人が、段ごとに「上限に対してどれだけ使ったか」「上限に近い・上限を超えた・上限で止まった」「どの段が費用の多くを占めるか」を、図と表で分かるようにする（イシュー #42）。流したあとの実績を出すもので、流す前の目安（#22）ではない。

## 機能要件と受け入れ基準

### 機能要件

- FR-01 本体は、上限が効いた SDK の段の実行（`BasePipeline._run` が書く `runs[]` の要素。`pipe-in record` が書く要素は含めない）に、効いた上限 `max_budget_usd` を残す。上限が無い実行・確認の要素・`pipe-in record` の要素には書かない（`null` も書かない）。
- FR-02 SDK に渡す上限と、記録する上限は、1 つの関数が決めた同じ値にする。`pipeline.toml` の段の値が正の数ならそれ。0 または無いときは、段の定義（`pipe.toml` など）の値。どちらも無ければ上限なし。0 より大きい有限な数でない値は、この関数に届く前に FR-21・FR-22 が止める。
- FR-03 本体は、上限が効いた実行のうち、SDK へ resume（続きの会話）を渡した実行に、続きの会話の印を残す。印は `true` だけを書く（偽や `null` は書かない）。上限が無い実行・resume を渡さない実行には書かない。`cost_usd` は変えず、今回分の費用のような別の項目は作らない。（Q-6）
- FR-04 本体のほかの出力（`99_summary.md`・終了コード・端末の完了行・`pipe-in live` の写し・`total_cost_usd`・`cost_usd` を含む、上限と印以外の項目・`pipe-in record`）は変えない。例外は 1 つ：`pipeline.toml` の `max_budget_usd` が不正なとき（FR-21）の `pipe-in record`・`pipe-in live` の止まり方で、FR-24 が決める。
- FR-21 `pipeline.toml` の `[stages.<段>]` の `max_budget_usd` が、0（`0.0` も）ではなく、しかも 0 より大きい有限な数でもないとき（負の数・文字・真偽・`nan`・`inf` など）、本体は SDK を呼ぶ前に `SystemExit` で止まり、直す項目と書き方を出す（`load_config`。`max_buffer_mb` の検査と同じ形）。0 は今までどおり未設定として読む。検査は `load_config` の中にあるので、`load_config` を呼ぶ入口のどれでも同じ文で止まる（FR-24）。（Q-7）
- FR-22 `pipe.toml` の段に `max_budget_usd` が書いてあって、0 より大きい有限な数として読めないとき（0・負の数・文字・真偽・`nan`・`inf` など）、定義の検査（`check_pipe`）がその段の誤りとして返し、パイプを流す入口は SDK を呼ぶ前に止まる。直す段と書き方を出す（`max_agent_calls` の検査と同じ形）。`max_budget_usd` を書かない段は今までどおり。（Q-7）
- FR-24 `pipeline.toml` の `max_budget_usd` が FR-21 の不正な値のとき、`pipe-in record`（SDK を呼ばない）と `pipe-in live` の `snapshot`・`watch`・`answer`（`--work-dir` を渡さないとき。SDK を呼ばない）、`pipe-in-gen design`（SDK を呼ぶ）も、`load_config` で FR-21 と同じ文で `SystemExit` になる。`pipe-in live` の `page` と、`--work-dir` を渡す `pipe-in live` は `load_config` を呼ばないので、今までどおり止まらない。`max_budget_usd` が正しい値・無い・0 のときは、これらのコマンドは今までどおり動く。`max_buffer_mb` が不正なときに、これらがすでに同じように止まるのと同じ形（検査を `load_config` に置いた結果。聞かずに決めたこと）。
- FR-05 拡張は、`runs[]` から上限・続きの会話の印・結果の種類（`subtype`）を読む。読めない値・無い値は、「上限なし」「続きでない」「不明」として、例外を出さない。
- FR-06 続きの会話の印の無い実行について、拡張は、終わった実行ごとに、使った割合（費用 ÷ 上限）と状態を決める。状態は4つ：止まった（`subtype` が `error_max_budget_usd`）・超えた（止まっていなくて、費用が上限より大きい）・近い（費用が上限の 8 割以上）・余裕（それ未満）。上限が無く、止まってもいない実行は、状態を持たない。費用と上限の比べ方（丸め方）は「決めたこと」の「金額の書き方と比べ方」。（Q-2・Q-3）
- FR-07 続きの会話の印のある実行について、拡張は、割合も「余裕」「近い」「超えた」も決めない（`cost_usd` が前の回までを含む累計のおそれがあるため）。`subtype` が上限で止まったことを示すときだけ、状態「止まった」（割合なし）を決める。止まっていなければ、状態を持たない。（Q-6）
- FR-08 同じ段が複数回流れたときは、状態を持つ回の中から、状態が重い回（止まった > 超えた > 近い > 余裕）、同じなら割合の高い回、同じなら後の回を、節に出す。（Q-8）
- FR-09 図は、割合のある状態（余裕・近い・超えた・割合のある止まった）の終わった段の節に、「使った費用 / 上限」の金額の対と、割合が分かる細い棒を出す。
- FR-10 図は、近い・超えた・止まった節を、色と言葉で分かるようにする。色だけに頼らず、言葉は節の読み上げ（`<title>`・`aria-label`）にも入れる。
- FR-11 状態を持たない節（上限の無い段・古い記録・`/pipe-in` の記録・続きの会話の回で止まらなかった段・動いている段）は、今までどおりにする。例外は1つ：状態が「止まった」で割合が無い節（上限の値が記録に無い実行、続きの会話の印のある実行）には、「上限で止まった」の言葉だけを出す。金額の対と棒は出さない。（Q-5・Q-6）
- FR-12 図は、金額の対か言葉を出す節が、複数回流れた段のものであるとき、節に出した回が何回目の実行かを、文字で添える。状態を持たない節には添えない。
- FR-13 実行の詳細に、段ごとの費用を、費用の多い順に並べた表を出す。（場所は設計。D-1）
- FR-14 拡張は、work_dir を読むだけで書かず、新しいファイルを読まない。
- FR-15 外から来た文字は `escapeHtml` を通し、記録の値を HTML にそのまま出さない。
- FR-16 CSP は変えず、外部から何も読み込まず、色は `var(--vscode-*)` だけにする。
- FR-17 本体の依存の向きと依存を変えず、`guard.py`・`guard_hook.py`・`pipe_in_guard.py` を狭めない。
- FR-23 拡張は、状態バー・実行の一覧の行・確認待ちの知らせに、上限の話を出さず、今までどおりにする。図の節の色と言葉だけで見せる。（Q-4）
- FR-18 確認用のページ（`npm run preview`）に、各状態の節が並ぶ見本と、費用の表を足す。
- FR-19 利用者向けの文書（記録・拡張・設定・パイプの書き方）をそろえる。
- FR-20 開発の決まりの文書（互換の節・層の表・置き場所の表・確認用ページの一覧・決定の記録の索引）をそろえる。

### 受け入れ基準

#### 本体の記録（FR-01〜FR-04）

- D0051-AC-01 開発フロー（`pipeline.toml` の `[stages.requirements]` に `max_budget_usd = 0.6`）を、`runner` を差し替えて流すと、その段の `runs[]` の要素に `max_budget_usd` が 0.6 で残る。（tests/test_stage_budget.py）
- D0051-AC-02 パイプ（`pipe.toml` の段に `max_budget_usd = 1.5`）を流すと、その段の要素に 1.5 が残る。`pipeline.toml` の `[stages.<同じ段名>]` に 0.6 も書いたときは、そちらが優先で、記録も 0.6。（tests/test_stage_budget.py）
- D0051-AC-03 上限が無い実行（`pipeline.toml` にも段の定義にも無い）の要素に、`max_budget_usd` も続きの会話の印も無い（`null` も書かない）。（tests/test_stage_budget.py）
- D0051-AC-04 上限が無く、resume を渡した実行（要件定義の修正の依頼など）の要素にも、続きの会話の印は無い。（tests/test_stage_budget.py）
- D0051-AC-05 上限なしで流す見本の記録（要件定義の修正の依頼＝resume の回を含む）で、`tests/test_showcase.py`（D0009-AC-15）が、見本を作り直さずに通る。（既存の tests/test_showcase.py が変更なしで通る）
- D0051-AC-06 確認の要素（`review`）・検証の判定の要素（`verdict`）・テスト先行の結果の要素（`result`）など `seq` の無い要素と、`pipe-in record done` が書く要素には、上限の項目も続きの会話の印も入らない。（tests/test_stage_budget.py）
- D0051-AC-07 `pipeline.toml` の上限が 0 または `0.0` のときは、止まらず、未設定として扱う（今までどおり）。`pipeline.toml` が 0・`pipe.toml` が 1.5 なら、SDK に渡す値も記録も 1.5。`pipeline.toml` が 0・`pipe.toml` が無いなら、SDK に渡す値は `None`、記録に項目は無い。（tests/test_stage_budget.py）
- D0051-AC-08 次の6つの場合で、`sdk_options` が SDK に渡す `max_budget_usd` と、記録される値が同じ：（pipeline.toml, pipe.toml）＝（0.6, 1.5）→ 0.6、（なし, 1.5）→ 1.5、（0.6, なし）→ 0.6、（なし, なし）→ なし、（0, 1.5）→ 1.5、（0, なし）→ なし。（tests/test_stage_budget.py）
- D0051-AC-09 `--pause` で止めたあと、`pipeline.toml` の上限を 0.6 から 1.0 に変えて `--review revise` で続けると、前の回の要素は 0.6、続きの回の要素は 1.0 を持つ（流したときの値を残す）。（tests/test_stage_budget.py）
- D0051-AC-10 `--pause` で止めたあと、`--review approve` で続けても、前の回の要素の上限はそのまま残る。（tests/test_stage_budget.py）
- D0051-AC-11 （Q-6）上限 1.0 で、1回目（resume を渡さない・会話 s1）のあと、2回目（`resume` = s1）を、runner を差し替えて流すと、2回目の要素にだけ続きの会話の印が `true` で付き、1回目の要素には付かない（どちらも `max_budget_usd` は 1.0）。（tests/test_stage_budget.py）
- D0051-AC-12 （Q-6）`--pause` で止めたあと `--review revise` で続けた回（会話の続きを渡す）の要素にだけ印が付き、前の回の要素には付かない（上限は両方 1.0）。（tests/test_stage_budget.py）
- D0051-AC-13 （Q-6）開発フローの要件定義の確認で、端末の問いに「修正」と答えて流れる再実行（人の指摘を反映。resume を渡す）の要素に、印が付く（上限あり）。（tests/test_stage_budget.py）
- D0051-AC-14 （Q-6）開発フローのテスト先行の再実行（人の指摘を反映する回と、抜けた受け入れ基準を補う回。どちらも resume を渡す）の要素に、どちらも印が付く（上限あり）。（tests/test_stage_budget.py）
- D0051-AC-15 （Q-6）パイプの段で、人の指摘を反映する再実行（resume を渡す）の要素に、印が付く（上限あり）。（tests/test_stage_budget.py）
- D0051-AC-16 （Q-6）resume を渡さない再実行（開発フローの実装の差し戻し、パイプの検証の指摘を反映する再実行）の要素には、上限が効いていても印が付かない。（tests/test_stage_budget.py）
- D0051-AC-17 上限を付けた実行と付けない実行で、`99_summary.md`・`total_cost_usd`・終了コード・`runs[]` の上限と印以外の項目が同じ。（tests/test_stage_budget.py）
- D0051-AC-18 `pipe-in record done` が書く要素のほかの項目（`cost_usd` 0.0・`num_turns` 0・`subtype`・`metrics`）は今までと同じ（`pipeline.toml` の `max_budget_usd` が無い・正しい値・0 のとき。不正な値のときの止まり方は AC-109）。（tests/test_stage_budget.py）
- D0051-AC-19 （Q-9）開発フローの検証（`test`）の段の runner の差し替えが、判定（`structured`）を返さず、`is_error` が真で `subtype` が `error_max_budget_usd` の結果を返して終わるとき、判定は `Verdict(status="blocked")` になり、終了コードは今のまま 4（`BLOCKED`）。終了コードと `99_summary.md` の文言は、この変更の前と同じ。パイプの段が同じ終わり方をしたときは、今のまま 3（`STAGE_ERROR`）のまま（対象外に書いた）。（tests/test_stage_budget.py）
- D0051-AC-107 （Q-4）同じ結果を返す runner で、上限を付けて流した実行と付けずに流した実行を比べると、端末に出る段の完了行の文と、`pipe-in live` の写しが作る段ごとの値（費用・ターン数など）が同じ。結果が `error_max_budget_usd` で終わるもの（`is_error` が真）でも同じ。（tests/test_stage_budget.py）

#### 上限の値の検査（FR-21・FR-22。Q-7）

- D0051-AC-20 （Q-7）`max_budget_usd` が負の数（`-1`・`-0.5`）のとき、`load_config` は基準 A のとおり止まる。（tests/test_budget_check.py）
- D0051-AC-89 （Q-7）`max_budget_usd` が文字（`"1.0"`・`""`）のとき、`load_config` は基準 A のとおり止まる。空の文字は偽だが、数ではないので、未設定にしない。（tests/test_budget_check.py）
- D0051-AC-90 （Q-7）`max_budget_usd` が真偽（`true`・`false`）のとき、`load_config` は基準 A のとおり止まる。`false` は偽だが 0 ではなく数でもないので、未設定にしない。（tests/test_budget_check.py）
- D0051-AC-91 （Q-7）`max_budget_usd` が `nan` のとき、`load_config` は基準 A のとおり止まる（文は「今の値: nan」）。（tests/test_budget_check.py）
- D0051-AC-92 （Q-7）`max_budget_usd` が `inf`・`-inf`、または float にできないほど大きい整数（10 の 400 乗）のとき、`load_config` は基準 A のとおり止まる。`OverflowError` などの例外で落ちない。（tests/test_budget_check.py）
- D0051-AC-93 （Q-7）`max_budget_usd` が 0 より大きい有限な数（整数の `1`・小数の `0.6`・`0.001`）のときは止まらない。`sdk_options` が SDK に渡す値と記録される値は、その数に等しい（0 と `0.0` は未設定。AC-07）。`max_budget_usd` の無い前の版の `pipeline.toml` も、今までどおり読める。（tests/test_budget_check.py）
- D0051-AC-94 （Q-7）負の数の `pipeline.toml` で、runner を差し替えて `cli.main` から流す（`--pipe` で `pipe.toml` の上限が正しいパイプを流す場合も）と、`SystemExit` で止まり、runner は 1 回も呼ばれず、`state.json` は作られない。（tests/test_budget_check.py）
- D0051-AC-95 （Q-7）不正な値のある `[stages.<名前>]` が、流さない段でも止まる：開発フローを `--from design` で流すときの `[stages.requirements]` と、どの段にも無い名前の `[stages.nothing]`。どちらも基準 A のとおり止まる。（tests/test_budget_check.py）
- D0051-AC-96 （Q-7）`0` と `0.0` のとき、`check_pipe` は基準 B の文を返す。本物の CLI は 0 を断る（`--max-budget-usd must be a positive number greater than 0`）。`pipeline.toml` の 0（未設定。AC-07）とは別。（tests/test_budget_check.py）
- D0051-AC-97 （Q-7）負の数（`-1`・`-0.5`）のとき、`check_pipe` は基準 B の文を返す。（tests/test_budget_check.py）
- D0051-AC-98 （Q-7）文字（`"1.0"`・`""`）のとき、`check_pipe` は基準 B の文を返す。今までは黙って「上限なし」に読んでいた。（tests/test_budget_check.py）
- D0051-AC-99 （Q-7）真偽（`true`・`false`）のとき、`check_pipe` は基準 B の文を返す。今までは黙って「上限なし」に読んでいた。（tests/test_budget_check.py）
- D0051-AC-100 （Q-7）`nan` のとき、`check_pipe` は基準 B の文を返す（文は「今の値: nan」）。（tests/test_budget_check.py・tests/test_rules.py）
- D0051-AC-101 （Q-7）`inf`・`-inf`、または float にできないほど大きい整数（10 の 400 乗）のとき、`check_pipe` は基準 B の文を返す。`OverflowError` などの例外で落ちない。（tests/test_budget_check.py）
- D0051-AC-102 （Q-7）0 より大きい有限な数（`1.5`・整数の `2`・`0.001`）の段と、`max_budget_usd` を書かない段は、誤りを返さない。前の版の名前の頭のフォルダ（`docs/guide/migrate.md`）の `pipe.toml` も同じ。`examples/` のパイプと、既存のテストが使うパイプ（`tests/test_video_example.py` など）は、変更なしで `check_pipe` が空のまま。（tests/test_budget_check.py）
- D0051-AC-103 （Q-7）不正な値のある `pipe.toml` のパイプを、runner を差し替えて `cli.main` から `--pipe` で流すと、`SystemExit` で止まり、文は「パイプ「<名前>」に誤りがあります:」で始まって基準 B の文を含み、runner は 1 回も呼ばれず、`state.json` は作られない。不正な値のある段が、`--from` で飛ばす段でも、分岐（`routes`）で通らない段でも、同じように止まる。（tests/test_budget_check.py）
- D0051-AC-104 （Q-7）`pipe.toml` に不正な値（0 の段）があるとき、`pipeline.toml` の同じ段の値が「無い」「0」「0.6」のどれでも、AC-103 のとおり止まる。`pipeline.toml` の 0.6 が実行時には勝つ場合でも、定義の誤りは直させる。逆に、`pipeline.toml` が不正で `pipe.toml` が正しいときは、AC-94 のとおり止まる。（tests/test_budget_check.py）
- D0051-AC-105 （Q-7）`pipe-in-gen check <パイプ>` は、不正な値の `pipe.toml` で基準 B の文を出して終了コード 1、正しい値と書かない場合は、`max_budget_usd` の誤りを出さず、ほかに誤りが無ければ終了コード 0（`check_pipe` を共有するので、`generator/` のコードは変えない）。（tests/test_budget_check.py）
- D0051-AC-109 （Q-7）`pipeline.toml` に `[stages.requirements]` の `max_budget_usd = -1` があるフォルダで、`pipe-in record start`（`pipe_in.dev.record.main`）を流すと、基準 A のとおり `SystemExit` で止まり、`state.json` は作られない。`--config` で別の `pipeline.toml` を渡したときも、渡したほうの値で止まる。`max_budget_usd` が無い・`1.0`・`0` の `pipeline.toml` では、`record start` は今までどおり動き、`state.json` が作られる。（tests/test_budget_check.py）
- D0051-AC-110 （Q-7）同じ負の数の `pipeline.toml` で、`pipe-in live snapshot`・`pipe-in live watch`・`pipe-in live answer`（どれも `--work-dir` を渡さない）を流すと、どれも基準 A のとおり `SystemExit` で止まる。`snapshot` は写しを出さず、`watch` は見張りを始めず、`answer` は答えを読まない（`--out`・`--feedback-out` のファイルを作らない）。`--work-dir` を渡す形と `pipe-in live page` は、同じ `pipeline.toml` でも今までどおり止まらず動く。（tests/test_budget_check.py）
- D0051-AC-111 （Q-7）同じ負の数の `pipeline.toml` があるプロジェクトで、`pipe-in-gen design` の設計の流れ（`generator/design.py` の `_design`）を、runner を差し替えて呼ぶと、基準 A のとおり `SystemExit` で止まり、runner は 1 回も呼ばれない。（tests/test_budget_check.py）

#### 拡張が読む（FR-05）

- D0051-AC-21 `runs[].max_budget_usd` は、0.001 以上 10000 以下の有限な数のときだけ上限として読む。0・負の数・その範囲の外の数・文字・真偽・`null`・項目なしは「上限なし」。（vscode/src/domain/runRecordBudget.test.ts）
- D0051-AC-22 続きの会話の印は、真（`true`）のときだけ「続きの会話」として読む。偽・文字・数・`null`・項目なしは「続きでない」。（vscode/src/domain/runRecordBudget.test.ts）
- D0051-AC-23 `runs[].cost_usd` が負の数・数でない（文字・`null`・項目なし）ときは、0 として扱う。（vscode/src/domain/runRecordBudget.test.ts）
- D0051-AC-24 `runs[].subtype` は、文字のときだけ読む。文字でない・項目なしは「不明」。（vscode/src/domain/runRecordBudget.test.ts）
- D0051-AC-25 前の版の形の記録（`tests/fixtures/pipe_in/`）と、上限と印を持たない今の形の記録（`tests/fixtures/pipe_dev/`・`tests/fixtures/showcase*`）を読んでも、例外が出ず、すべての節が「上限なし」で、段の節の文字が今までと同じ。（vscode/src/domain/runRecordBudget.test.ts・vscode/src/view/flowSvgBudget.test.ts）

#### 割合と状態（FR-06）

- D0051-AC-26 費用 0.42・上限 1.0 の実行は、割合 0.42・状態「余裕」。費用 0・上限 1.0 は、割合 0・状態「余裕」（0 で割らない）。（tests/test_rules.py・vscode/src/domain/stageBudget.test.ts）
- D0051-AC-27 次の実行は、どれも「近い」になる：0.8 / 1.0、0.4 / 0.5、0.24 / 0.3、0.16 / 0.2、0.64 / 0.8（素朴な割り算では 0.16 / 0.2 と 0.64 / 0.8 が 0.7999999999999999 になる値を含む）。（vscode/src/domain/stageBudget.test.ts）
- D0051-AC-28 0.799 / 1.0 は「余裕」。0.7996 / 1.0 は、1/1000 ドルに丸めると 0.800 になるので「近い」（表示 `$0.80 / $1.00` と状態がそろう）。（vscode/src/domain/stageBudget.test.ts）
- D0051-AC-29 上限ちょうど（1.0 / 1.0）は「近い」。0.1 + 0.2 を費用、0.3 を上限にした実行も「近い」（浮動小数点の誤差で「超えた」にならない）。1.0004 / 1.0 は「近い」（1/1000 ドル未満の差は見ない）。1.001 / 1.0 と 1.01 / 1.0 は「超えた」。（vscode/src/domain/stageBudget.test.ts）
- D0051-AC-30 （Q-3）`subtype` が `error_max_budget_usd` の実行は、費用が上限より小さくても（0.3 / 1.0）、8 割以上でも（0.9 / 1.0）、超えていても（1.2 / 1.0）「止まった」。実際の記録では、止まった実行の費用は上限にほぼ届いているはずだが、記録の上限と SDK の判定がずれても `subtype` を信じるための、防御のテスト。（vscode/src/domain/stageBudget.test.ts）
- D0051-AC-31 （Q-3）上限が記録に無い実行でも、`subtype` が `error_max_budget_usd` なら、状態は「止まった」（割合は無い）。（vscode/src/domain/stageBudget.test.ts）
- D0051-AC-32 （Q-3）費用の上限以外の止まり方は、「止まった」にならず、費用の割合だけで状態が決まる：`error_max_turns` の 0.95 / 1.0 は「近い」、`error_during_execution` の 0.3 / 1.0 は「余裕」、pipe-in 独自の `error_max_buffer_size` の 0.3 / 1.0 は「余裕」、`success` で `is_error` が真の 0.3 / 1.0 は「余裕」。（vscode/src/domain/stageBudget.test.ts）

#### 続きの会話の印のある実行（FR-07）

- D0051-AC-33 （Q-6）続きの会話の印のある実行で、`subtype` が `error_max_budget_usd` なら、費用が 0.3 / 1.0 でも 1.2 / 1.0 でも、状態は「止まった」。割合は無い。（vscode/src/domain/stageBudget.test.ts）
- D0051-AC-34 （Q-6）続きの会話の印のある実行で、`subtype` が止まったことを示さないもの（`success` の 0.3 / 1.0・0.9 / 1.0・1.2 / 1.0、`error_max_turns` の 0.95 / 1.0）は、どれも状態を持たない。「余裕」「近い」「超えた」のどれにもならず、割合も無い。（vscode/src/domain/stageBudget.test.ts）

#### 複数回流れた段（FR-08）

- D0051-AC-35 「N 回目」は、その段の実行を `runs[]` に現れる順に 1 から数えた番号。上限の無い回・印のある回も数える。`attempt` は使わない（`attempt` が `null` の段でも数える）。（vscode/src/domain/stageBudget.test.ts）
- D0051-AC-36 状態の重い回を選ぶ：1回目 0.9 / 1.0（近い）・2回目 0.4 / 1.0（余裕）なら 1回目。近い（1回目）と超えた（2回目 1.2 / 1.0）なら 2回目。止まったと超えたなら止まった。（vscode/src/domain/stageBudget.test.ts）
- D0051-AC-37 状態が同じなら、割合の高い回を選ぶ（後の回ではない）：1回目 0.5 / 0.5（割合 1.0）・2回目 0.9 / 1.0（割合 0.9）は、どちらも「近い」なので 1回目。（vscode/src/domain/stageBudget.test.ts）
- D0051-AC-38 状態も割合も同じなら、後の回を選ぶ：1回目 0.5 / 1.0・2回目 0.25 / 0.5（どちらも割合 0.5・余裕）は 2回目。（vscode/src/domain/stageBudget.test.ts）
- D0051-AC-39 回ごとに上限が違うとき、割合は回ごとの上限で決める。段の合計の費用は上限と比べない：0.4 / 0.5 の回が2回（合計 0.8 は 0.5 より大きい）でも、どちらも「近い」で、「超えた」にならない。（vscode/src/domain/stageBudget.test.ts）
- D0051-AC-40 上限のある回と無い回が混ざるとき（止まった回が無いとき）、上限の無い回は選び方に入らない：1回目 上限なし（費用 0.9）・2回目 0.2 / 1.0 なら、2回目（「余裕」）。（vscode/src/domain/stageBudget.test.ts）
- D0051-AC-41 （Q-5）上限の無い「止まった」回と、上限のある「近い」回が混ざるときは、「止まった」回を選び、言葉だけを出す（金額の対と棒は出さない）。（vscode/src/domain/stageBudget.test.ts）
- D0051-AC-42 「止まった」回が複数あり、割合のある回と無い回が混ざるときは、割合のある回を選ぶ（金額と棒を出せるほうを先にする）。実際の記録では、止まった回は流れの最後に1つだけなので、防御のテスト。（vscode/src/domain/stageBudget.test.ts）
- D0051-AC-43 状態を持つ回が1つも無いとき、その節は「上限なし」。例は3つ：（a）印の無い回だけで、どれも上限が無く止まってもいない（0.9 と 0.2）、（b）印のある回だけで、止まっていない（`success` の 1.2 / 1.0）、（c）上限の無い印の無い回（0.9）と、印のある止まっていない回（0.3 / 1.0）。（vscode/src/domain/stageBudget.test.ts）
- D0051-AC-44 （Q-6）印のある回で止まっていない回は、選び方に入らない：1回目 0.9 / 1.0（印なし・近い）・2回目 印あり・`success`・1.2 / 1.0 なら、1回目（「近い」）。2回目の「超えた」にならない。（vscode/src/domain/stageBudget.test.ts）
- D0051-AC-45 （Q-6）印のある回で止まった回は、選び方に入る：1回目 0.4 / 1.0（印なし・余裕）・2回目 印あり・止まった なら、2回目（「止まった」）。（vscode/src/domain/stageBudget.test.ts）

#### 図の節（FR-09〜FR-12）

- D0051-AC-46 金額は、1/1000 ドル単位に四捨五入して書く。小数第3位が 0 なら小数2桁、そうでなければ3桁：0.42 → `$0.42`、1.0 → `$1.00`、0.004 → `$0.004`、0.125 → `$0.125`、12.3456 → `$12.346`。10000 ドル（丸めて 10000.000）を超える費用は `$10000+`（10000.5 でも 1e21 でも）。指数表記・`NaN`・`Infinity` は出ない。（vscode/src/view/money.test.ts）
- D0051-AC-47 割合のある、終わった段の節の SVG に、`$<費用> / $<上限>` の形で金額の対が入る：0.42 / 1.0 → `$0.42 / $1.00`、0.004 / 0.01 → `$0.004 / $0.01`、123.456 / 200 → `$123.456 / $200.00`。（vscode/src/view/flowSvgBudget.test.ts）
- D0051-AC-48 棒の長さは割合に比例する（0.42 → 枠の幅の 42%）。0 は空の枠、1.0 以上（1.5 でも）は枠いっぱいで、枠からはみ出さない。棒は SVG の属性（`width` など）で描き、`style` 属性は使わない。（vscode/src/view/flowSvgBudget.test.ts）
- D0051-AC-49 （Q-3）「近い」「超えた」「止まった」の節に、それぞれ「上限に近い」「上限を超えた」「上限で止まった」の言葉が入る。「余裕」の節には、この3つの言葉のどれも入らない。（vscode/src/view/flowSvgBudget.test.ts）
- D0051-AC-50 節の `<g>` は状態のクラス（`is-budget-ok`・`is-budget-near`・`is-budget-over`・`is-budget-stopped`）を持ち、色はそのクラスから CSS で決める。状態を持たない節には、どのクラスも付かない。（vscode/src/view/flowSvgBudget.test.ts）
- D0051-AC-51 「近い」「超えた」「止まった」の節の `<title>` に、同じ言葉が入る。SVG 全体の `aria-label` にも、その節の名前と言葉が入る。（vscode/src/view/flowSvgBudget.test.ts）
- D0051-AC-52 節に金額の対（または言葉だけの「止まった」）を出すとき、その段が2回以上流れていれば、脇に「N 回目」（N は節に出した回の番号）が文字で見える（`<title>` にも入る）。1回だけの段・状態を持たない節には出ない。（vscode/src/view/flowSvgBudget.test.ts）
- D0051-AC-53 選んだ回の値が出て、別の回の値は出ない：1回目 0.90 / 1.00・2回目 0.40 / 1.00 の段の SVG に、`$0.90 / $1.00`・「上限に近い」・「1 回目」が入り、`$0.40 / $1.00` は入らない。既存の2行目（`N ターン・$費用・時間`）は全部の回の合計のまま（費用は `$1.300`）。（vscode/src/view/flowSvgBudget.test.ts）
- D0051-AC-54 （Q-5）上限が記録に無く「止まった」の節は、「上限で止まった」の言葉（と、2回以上流れた段なら「N 回目」）だけを出し、金額の対と棒は出さない。（vscode/src/view/flowSvgBudget.test.ts）
- D0051-AC-55 （Q-6）続きの会話の印のある回で止まった節も、「上限で止まった」の言葉（と、2回以上流れた段なら「N 回目」）だけを出す。その回の費用（例：0.9）の金額の対も、棒も出ない。（vscode/src/view/flowSvgBudget.test.ts）
- D0051-AC-56 状態を持つ回が1つも無い段（上限のある回が無い・印のある回が止まっていない・止まった回も無い）の節の SVG は、今までと同じ。既存の `flowSvg` のテストが、変更なしで通る。（vscode/src/view/flowSvgBudget.test.ts）
- D0051-AC-57 高さが増えるのは、金額の対・棒・言葉のどれかを出す節だけ（増える量は設計）。それを出さない節の高さは 50 のまま。後ろの節と矢印は、増えた分だけ下にずれ、`viewBox` の高さも同じだけ増える。（vscode/src/view/flowSvgBudget.test.ts）
- D0051-AC-58 動いていると判定された段の節には、金額の対も棒も言葉も出さない（今までの経過のまま）。並列の段のうち動いていると判定されない段は、今までの動きのまま（前の回の状態で出る。変えない）。（vscode/src/domain/stageBudget.test.ts・vscode/src/view/flowSvgBudget.test.ts）
- D0051-AC-59 `/pipe-in` の記録（`driver` があり、費用 0・ターン 0）の図は、今までと同じ。（vscode/src/view/flowSvgBudget.test.ts）
- D0051-AC-60 記録の上限・`subtype` に、文字（例：`<script>`）や数でない値が入っていても、HTML にそのまま出ない（上限は数として読み、言葉は固定の文だけを出す）。（vscode/src/view/flowSvgBudget.test.ts）
- D0051-AC-61 SVG に `style` 属性が無く、外部の読み込みが無く、色は `var(--vscode-*)` だけ。`vscode/src/webview/csp.test.ts` が通る。（vscode/src/view/flowSvgBudget.test.ts）

#### 費用の表（FR-13）

- D0051-AC-62 実行の詳細に、「段ごとの費用」の表が1つ出る。テストは、表を設計で決める印（属性）で探し、タブの位置の添字では探さない（PR #87 が足すタブと取り違えないため）。（vscode/src/view/stageCostsHtml.test.ts）
- D0051-AC-63 行は段ごと。同じ段の複数回は合算して1行で、2回以上なら「N 回」を添える。列は、段の名前・費用・全体に占める割合。（vscode/src/domain/stageCosts.test.ts・vscode/src/view/stageCostsHtml.test.ts）
- D0051-AC-64 並べ方は、段の合計の費用の多い順。同額のときだけ段の並びの順。段の並びが（0.396 の段、0.404 の段、0.2 の段）のとき、表は 0.404 の段・0.396 の段・0.2 の段の順になる（割合は 40%・40%・20% で、四捨五入した値では並べない）。（vscode/src/domain/stageCosts.test.ts）
- D0051-AC-65 割合は「その段の費用 ÷ 全段の費用の合計」を四捨五入した整数％。合計が 1.0 のとき、0.125 の段は 13%、0.001 の段は 0%。同額の3段は 33%・33%・33%（合計を 100% に合わせる補正はしない）。（vscode/src/domain/stageCosts.test.ts）
- D0051-AC-66 合計の行は費用だけで、割合は出さない。（vscode/src/view/stageCostsHtml.test.ts）
- D0051-AC-67 行の費用は、図の節の合計（4桁に丸めた値）と同じ値で、金額の書き方は AC-46 と同じ。費用が 0 の段（まだ流れていない・`/pipe-in` の記録）は行に出ない。全部の段が 0、または記録が無いときは、表そのものを出さない。（vscode/src/domain/stageCosts.test.ts・vscode/src/view/stageCostsHtml.test.ts）
- D0051-AC-68 （D-1 が使用量のタブのとき）`usage_summary` が無い古い記録でも、`runs[]` の費用があれば表が出る。（vscode/src/view/stageCostsHtml.test.ts）
- D0051-AC-69 段の名前は `escapeHtml` を通す（`<img onerror=…>` のような名前で、生の HTML が出ない）。（vscode/src/view/stageCostsHtml.test.ts）

#### 守る決まり（FR-14〜FR-17・FR-23）

- D0051-AC-70 拡張は work_dir に書かず、新しいファイルを読まない。読み取りの口（6つの関数）と、`fsWorkDirSource.ts` の読む範囲は変わらず、書き込みの関数も足さない。`vscode/src/architecture.test.ts` と `tests/test_decision_ui.py` が通る。（既存の vscode/src/architecture.test.ts が通る）
- D0051-AC-71 `vscode` を import するのは `vscode/src/extension.ts` だけのまま（`vscode/src/architecture.test.ts` が通る）。（既存の vscode/src/architecture.test.ts が通る）
- D0051-AC-72 本体の依存の向きは変わらない（`tests/test_architecture.py` が通る）。（既存の tests/test_architecture.py が通る）
- D0051-AC-73 依存を足さない：`git diff main...HEAD -- pyproject.toml vscode/package.json vscode/package-lock.json` に依存の行の差が無い。（確かめた：依存のファイルに差が無い）
- D0051-AC-74 `pipe_in/engine/guard.py`・`generator/guard_hook.py`・`.claude/hooks/pipe_in_guard.py` を変更しない（`git diff --stat main...HEAD` に出ない）。狭めないので、すり抜けの道のテストは足さない。`tests/test_guard_hook.py`・`tests/test_pipe_in_guard.py`・`tests/test_bash_write_guard.py` が、変更なしで通る。（確かめた：守りの仕組みのファイルに差が無い）
- D0051-AC-108 （Q-4）上限・続きの会話の印・止まった実行（`subtype` が `error_max_budget_usd`）を持つ記録から作った、状態バーの文字とツールチップ（`statusBarLabel`）・実行の一覧の行（`summarizeRun`）・確認待ちの知らせ（`planWaitingNotice`）は、同じ記録から上限と印と `subtype` を除いたものから作ったものと等しい。関数の名前は今のもの（設計で変わってよい）。（vscode/src/app/budgetUnchanged.test.ts）

#### 画面・実機（FR-18）

- D0051-AC-75 （画面）：確認用のページ（`npm run preview` でできる新しい種類のページ。名前は設計。D-5）の明るい版を開く。図に、余裕・近い・超えた・止まった・上限なし・上限なしで止まった・続きの会話の回で止まらなかった・続きの会話の回で止まった、の8種類の節と、複数回流れた段の節が1つ並ぶ。上限のある節（余裕・近い・超えた・止まった）に金額の対と細い棒が見え、近い・超えた・止まった・上限なしで止まった・続きの会話の回で止まった節に言葉が見え、複数回の節に「N 回目」が見える。続きの会話の回で止まらなかった節は、上限なしの節と同じ見た目（金額の対も棒も言葉も無い）。ブラウザのコンソールのエラーが 0 件。（画面）確かめた：Playwright で 10 段の状態・金額の対・言葉が設計どおり、コンソールのエラー 0
- D0051-AC-76 （画面）：同じページの暗い版を開く。AC-75 と同じものが読める。Playwright で `getComputedStyle` を計り、明るい版・暗い版の両方で、文字の色と節の塗りの色のコントラストが 4.5:1 以上、棒の塗りと枠の色が背景に対して 3:1 以上。（画面）確かめた：文字と塗り 明 4.88・暗 6.08 以上、棒の枠と塗り 明 3.12・暗 4.61 以上
- D0051-AC-77 （画面）（手で）：AC-75 のページの画像をグレースケールにしても、「近い」「超えた」「止まった」の3つが言葉で区別でき、「余裕」の節と続きの会話の回で止まらなかった節に警告の言葉が無い。（手で）確かめた：白黒にしても 3 つの言葉で見分けられる
- D0051-AC-78 （画面）：費用 `$9999.999`・上限 `$10000.00`、「上限で止まった」と「N 回目」が同時に出る節が、100% の表示で、節の枠（幅 176）からはみ出さない（各文字の右端が節の右端以内。`getBBox` で計る）。（画面）確かめた：最大の組の文字が節の右端以内
- D0051-AC-79 （画面）：確認用のページで、費用の表が出る場所（D-1）を開く。「段ごとの費用」の表が、割合の高い順に出る（明るい版・暗い版の両方で読める）。（画面）確かめた：費用の表が高い順、既存のページでも出る、横スクロール無し
- D0051-AC-80 （実機）（手で）：利用料のかかる実行はせず、手で作った記録を使う。work_dir に、上限のある段が4つの節（余裕 0.2 / 1.0・近い 0.9 / 1.0・超えた 1.2 / 1.0・止まった＝`subtype` が `error_max_budget_usd`）になる `state.json` を置き、本物の VSCode の「実行を見る」で開く。近い・超えた・止まったの節に金額の対・棒・言葉が見え、余裕の節には金額の対と棒だけで警告の言葉が無い。開発者ツールのコンソールに CSP の違反が出ない。（実機）まだ（本物の VSCode で開く。この入れ物では開けない）

#### 文書（FR-19・FR-20）

- D0051-AC-83 `docs/guide/records.md` の `runs[]` の項目の説明に、`max_budget_usd` と続きの会話の印の項目がある（上限が効いた実行にだけ書く・印は resume を渡した実行にだけ `true` を書く・無い記録は上限なしとして読む・`null` は書かない）。（tests/test_stage_budget_docs.py）
- D0051-AC-84 `docs/guide/vscode.md` に、図の上限の見方（金額の対・棒・4つの状態と言葉・「近い」は上限の 8 割以上・「N 回目」・動いている段には出ない・上限の無い段は今までどおり・続きの会話の回は金額の対を出さず、止まったときだけ言葉を出す・状態バー・実行の一覧・知らせには出ない（Q-4））と、費用の表（並び・割合・費用 0 の段は出ない）の説明がある。（tests/test_stage_budget_docs.py）
- D0051-AC-85 `docs/guide/config.md` の `max_budget_usd` の説明に、記録に残り図に出ること・目安で超えることがある（サブエージェントの費用も数える）・`pipeline.toml` の 0 は未設定として読むこと・0 より大きい数でない値（負の数・文字・真偽など）は SDK を呼ぶ前に止まり、直し方が出ること（Q-7）・`pipe-in record`・`pipe-in live`（`--work-dir` を渡さないとき）も `pipeline.toml` を読むので同じ文で止まること（FR-24）がある。見本の1行（`max_budget_usd = 1.0            # 段ごとの費用の上限（概算）`。`tests/test_guide.py` が固定している）は変えない。（tests/test_stage_budget_docs.py）
- D0051-AC-86 `vscode/README.md` の「### 使用量」の「古い記録では節を出さない（今までどおり）」が、費用の表の出方に合うように直っている（`usage_summary` の無い古い記録でも、費用の表は出る）。（tests/test_stage_budget_docs.py）
- D0051-AC-87 `docs/development/design.md` に、「形を変えるとき（互換）」の D0051 の1行（足すだけの項目。無い古い記録は上限なしとして読む）、拡張の層の表のドメイン・画面の行の新しい部品、置き場所の表の確認用ページの行の新しいページがある。（tests/test_stage_budget_docs.py）
- D0051-AC-88 `docs/assets/README.md` の確認用ページの一覧、`.claude/skills/pipe-in/screen-check.md` のページの種類の頭、`docs/decisions/README.md` の索引に、D0051 と新しいページの行がある。`tests/test_guide.py`・`tests/test_skill_tidy_docs.py`・`tests/test_rules.py` が通る。（tests/test_stage_budget_docs.py）
- D0051-AC-106 `docs/guide/pipes.md` の `pipe.toml` の `max_budget_usd` の説明に、0 より大きい数で書くこと・0（`pipeline.toml` と違い未設定にならない）・負の数・文字・真偽は流す前に止まり、直し方が出ること（Q-7）・書かなければ上限なしのこと・効いた上限が記録に残り図に出ること（`config.md` を指す）がある。見本のコードブロックの行（`# model = "sonnet" / max_turns = 100 / max_budget_usd = 1.0`。`tests/test_guide.py` が固定している）は変えない。（tests/test_stage_budget_docs.py）

## 決めたことと理由

### 人が決めたこと（要件定義・設計・テスト先行・検証で聞いた点）

- **上限は本体が記録に残す（Q-1）。** 上限が効いた SDK の段の実行にだけ、`runs[]` の要素に `max_budget_usd`（SDK に渡したのと同じ値）を書く。拡張は記録だけを読み、`pipeline.toml`・`pipe.toml` は読まない（優先の計算を二重に持たない。設定を書き換えたあとの古い記録でも比べ違えない）。この変更より前の記録には効かない。
- **「近い」は上限の 8 割以上で固定（Q-2）。** 定数は `vscode/src/domain/stageBudget.ts` の 1 か所。比べるのは 1/1000 ドルの整数どうし（5c ≥ 4L）で、浮動小数点の誤差で境目がずれない。
- **状態は 4 つ（Q-3）：余裕・上限に近い・上限を超えた・上限で止まった。** 「止まった」は SDK の結果の `subtype` が `error_max_budget_usd` のとき。上限は目安なので、止まらずに「超えた」で終わる実行もある。
- **状態バー・知らせ・実行の一覧には出さない（Q-4）。** 図の節と使用量のタブだけ（D0024 の状態バーは静かにする決め、D0046 の知らせは確認待ちだけ、に合わせた）。
- **上限が記録に無い古い記録でも、`subtype` が上限で止まった印なら「上限で止まった」の言葉だけ出す（Q-5）。** 金額の対と棒は出さない。
- **続きの会話（resume）の回は「止まった」だけ（Q-6）。** 本体は、上限が効いた実行のうち `resume` を渡した回に `resumed: true` を書く。拡張はその回の割合も余裕・近い・超えたも決めず、止まったときだけ言葉を出す。実機（利用料がかかる）では確かめないと決めた。検証のあとの助言で、公式の文書（cost-tracking）に「resume した結果の費用はセッションの累計（Claude Code v2.1.277 以降）」とあることが分かり、この扱いが合っていると確かめた。
- **0 より大きい有限な数でない上限は、流す前に止める（Q-7）。** `pipeline.toml` の `0` は今までどおり未設定。それ以外（負の数・文字・真偽・`nan`・`inf`、`pipe.toml` の `0`）は、SDK を呼ぶ前に、直す項目・書き方・今の値を出して止まる（`max_buffer_mb`・`max_agent_calls` の検査と同じ形）。検査は `load_config` の中にあるので、`pipe-in record`・`pipe-in skill record`・`pipe-in live`（`--work-dir` なし）・`pipe-in-gen design` も同じ文で止まる（要件定義の承認で人が認めた）。今まで偶然効いていた文字の `"1.0"` も止まる。
- **複数回流れた段は、状態の重い回を節に出す（Q-8）。** 同じなら割合の高い回、それも同じなら後の回。金額の対の脇に「N 回目」を添える。
- **検証の段が上限で止まったときの終了コードは変えない（Q-9）。** 今のまま 4（BLOCKED）で、図の「上限で止まった」と端末の文言が食い違う（下の「残った課題」）。
- **鍵の名前は `resumed`、`/pipe-in` のスキルと補助ファイルの合計の上限（D0039-AC-11）は 18,000 字から 18,300 字に上げる、作業台の保存前の検査 `validatePipe` には足さない**（設計の承認のとき）。上限は、確認用ページの頭 `run-panel-budget` の行を `screen-check.md` に足すと収まらなかったため（main の合計は 17,799 字だった。足したあとは 18,150 字）。
- **承認したテストの誤り 2 つは、メインが直す**（実装のあと、検証の前）。`tests/test_stage_budget_docs.py` の AC-85 が見本の行を空白 11 個で探していた（文書と既存の `tests/test_guide.py` は 12 個）。`vscode/src/previewPagesBudget.test.ts` の AC-75 が「作業フォルダ docs/pipeline」の表示を求めていたが、その表示は実行の一覧があるページの上のバーにだけ出て、設計どおりの 1 つの実行のページ（既存の完了のページも同じ）には出ないので、その 1 行を外した。
- **検証のあとの監査（A-02・04・05・06）と助言（V-01・03）を直す。** V-02・04・05 は下に書く。

### 聞かずに決めたこと

- 費用の表は、使用量のタブの先頭に新しい節「段ごとの費用」として置く（費用の多い順・同額は段の順・割合は整数どうしで四捨五入）。行の費用は図の節の 2 行目と同じ式で、必ず同じ値になる。
- 節の高さは、表示の無い節 50（今のまま）、金額の対と棒 74、言葉か「N 回目」も出る節 88、言葉だけの節 64。幅 176 は変えない。「超えた」と「止まった」はどちらも赤で、言葉と枠の太さで見分ける（橙は明るい版で 3:1 に届かない）。
- 金額は 1/1000 ドル単位で、2 桁で足りれば `$0.42`、そうでなければ 3 桁、10000 ドルを超えると `$10000+`（`vscode/src/view/money.ts`）。拡張が上限として読むのは 0.001〜10000 ドルの範囲だけで、外の値は上限なしとして読む。
- 本体の鍵と拡張の鍵は、共通の表 `tests/fixtures/budget_record.json` を本体と拡張のテストが読んで結ぶ（見本の記録は上限なしで鍵を持たないため。見本の記録の形は変えない）。
- 確認用ページ `run-panel-budget-light`・`-dark` は、止まった段を 4 つ並べる 10 段の見本で、記録は一時フォルダに書いて読む（`tests/fixtures/` には足さない）。本物の流れでは止まったら終わるので起きない並び。
- `pipe_in/pipe/definition.py` の使わなくなった `_opt_float` を消した。`stage_budget_usd` は、`StageSpec` を直に組んで `0.0` を入れても `None` に落とし、SDK に渡す値と記録の値がずれないようにした。
- `run-list.gif` は撮り直さない（使用量のタブの絵は、費用の表が足される前の見た目のまま。`docs/assets/README.md` に書いた）。
- 番号は D0048 → D0050 → D0051 と振り直した（作業のあいだに main に D0047〜D0050 が入った）。main（`3557262`。#87 の D0050 が入った）に載せ直したとき、#87 と同じ場所に足した文書の表・確認用ページの一覧・`shellHtml.ts` の 8 ファイルが食い違ったので、両方を残すように合わせた。

### 既存のテストを変えた理由

- `tests/test_rules.py`：AC の ID を拾う形 `AC_ID` を 2 桁から 2〜3 桁に広げた（この記録の AC が 100 を超えるため。広げると、3 桁の ID もテストと記録の突き合わせに入るので、厳しくする側。広げた形そのものの確かめも足した）。
- `tests/test_skill_tidy.py`：D0039-AC-11 の合計の上限を 18,000 字から 18,300 字に（人が決めた）。
- `vscode/src/previewPagesArtifacts.test.ts`：D0025-AC-73 は、確認用ページがあとの機能で増えてよいように、成果物の 2 件を位置（13・14 件目）で見る形のまま、名前の文を合わせた。
- `vscode/src/test/previewText.ts`（D0050 で移った補助）：D0025-AC-75 の `panelsOf` が、使用量のパネルから「段ごとの費用」の節を取り除いてから SHA-256 を測るようにした。**これは検査を緩める直し**（既存のページの使用量のパネルのうち、費用の節の中身はこの固定では測らなくなる）。理由は、使用量のパネルに費用の表を足すのが仕様で、既存のページの使用量のパネルは必ず変わるため。取り除いて測れば、値が今のまま通ることで「費用の表のほかは何も変わらない」を示せる。補う確かめは、見本の記録の費用の表を `runs[]` から別に集計して比べるテスト（`vscode/src/view/stageCostsHtml.test.ts`）と、上限のページの表の並びのテスト（`vscode/src/previewPagesBudget.test.ts`）。SHA-256 の値は測り直していない。
- `vscode/src/previewPagesTools.test.ts`：D0050-AC-46 の「先頭 14 件のあとは tools の 2 件だけ」を、15・16 件目に tools の 2 件が続く形にした（上限のページが末尾に足されるため。意味は変わらない）。

### 受け入れたリスク

1. **上限は目安。** SDK は最後の 1 回の応答の分（と、止まる前のサブエージェントの分）だけ上限を超えることがあるので、「超えた」は異常ではない（公式の文書 agent-loop）。図はそのまま「上限を超えた」と出す。
2. **続きの会話の回の費用は版で意味が変わる。** Claude Code v2.1.277 より前は、resume した回の費用は今回分だけだった（公式の文書 cost-tracking）。どちらでも、続きの会話の回は割合を出さないので、誤った「近い」「超えた」は出ない。
3. **この変更より前の記録には、金額の対と棒が出ない**（上限が記録に無いため）。止まった印だけは言葉で出る。
4. **`pipeline.toml` の書き間違いで、`pipe-in record`・`pipe-in live` も止まる。** SDK を呼ばないコマンドだが、`load_config` を通るため。直し方の文が出る。
5. **止まった回のトークン数は少なく出る。** 上限で止まった回は、`usage` に上限を超えた応答が入らない（公式の文書 cost-tracking）。費用の根拠は `total_cost_usd` だけにしているので、図と表の費用はずれない（助言 V-02）。

### 確かめていないこと

- 実機（AC-80）：本物の VSCode の「実行を見る」で、手で作った記録（`vscode/scripts/budgetSamples.ts` の `fourStagesStateJson()`）を開き、近い・超えた・止まったの節の表示と、開発者ツールのコンソールに CSP の違反が出ないことを見る。この入れ物では本物の VSCode を開けないので、まだ。
- 実機で上限を小さくして段を止め、`ClaudeSDKClient` が `error_max_budget_usd` の結果のあとに例外を投げないか（助言 V-05。公式の文書に書いていない。投げると `subtype` が記録に残らないおそれがある）。利用料がかかるので、人に言われたときだけ。
- `max_budget_usd` の 0 以下の値の SDK での意味は、公式の文書に書いていない（助言 V-04）。pipe-in は SDK を呼ぶ前に止めるので、SDK の扱いには頼らない。
- 同梱の CLI が v2.1.277 以上か（`pyproject.toml` の `claude-agent-sdk` の下限が同梱する版）。

## 対象外・残った課題

- 流す前の費用の目安（#22）。動いている最中の費用の表示。状態バー・知らせ・実行の一覧への表示。`99_summary.md`・端末の完了行・`pipe-in live` の写し。
- 検証の段が上限で止まったときの終了コード（今は 4。図の「上限で止まった」と端末の「環境などの問題」が食い違う。D0026 と同じ受け皿で直せる）。
- 作業台（`pipeModel.ts` の `validatePipe`・入力欄の `min="0"`）は `max_budget_usd = 0` を保存できる。保存した `pipe.toml` は流す前に止まる。
- 実機の確かめ（AC-80・助言 V-05）。`run-list.gif` の撮り直し。
- 明るい版の節の状態の文字（「✓ 完了」など）は、節の塗りとの差が 4.33:1 で 4.5:1 に少し届かない（画面の確認で測った。上限の表示の前からある文字で、この機能では変えていない）。

## 確かめたこと

- テスト先行：本体 90 件・拡張 272 件が、期待した理由（assert の不一致・止まらない）で落ちることを、失敗の文まで読んで確かめた。既存のテストは通ったまま。
- 検証（1 回で合格）：main（`3557262`）に載せ直したあと、`pytest -q -p no:cacheprovider` は決定の記録を待つ 2 件のほか 11732 件が通り、`npm --prefix vscode test` は 5222 件すべて通り、型検査とビルドも通る。この記録を書いて、残りの 2 件も通る（最後に全体で流して、Python は 11734 件・拡張は 5222 件すべて通った。記録に前の名前が入って `tests/test_rename.py` が 1 件落ちたので、言い方を直した）。
- 画面（AC-75〜79）：`run-panel-budget-light`・`-dark` を Playwright で開いた。10 段の節の状態（余裕 1・近い 2・超えた 1・止まった 4・表示なし 2）と高さ（50・64・74・88）が設計どおり、最大の組 `$9999.999 / $10000.00` も節の中に収まる、コンソールのエラー 0。上限の表示の文字と節の塗りの差は明るい版 4.88・暗い版 6.08 以上、棒の枠と塗りは明るい版 3.12・暗い版 4.61 以上。白黒にしても「上限に近い」「上限を超えた」「上限で止まった」が言葉で見分けられる（AC-77）。使用量のタブの「段ごとの費用」の表が高い順に出て、既存のページ（`run-panel-light`・`-dark`）でも出る。1280×800 と 800×600 で横スクロールが無い。
- AC-73・74：`pyproject.toml`・`vscode/package.json`・`package-lock.json`、`pipe_in/engine/guard.py`・`generator/guard_hook.py`・`.claude/hooks/pipe_in_guard.py` に差が無い。
- 公開してよいか：変えたファイルに、秘密・ユーザー名の入った絶対パス・メールアドレス・`docs/pipeline/` の中身は無い。
- 文書係（検証のあと）：直す文書は無かった。案にした CLAUDE.md の `npm run preview` の行の直しは、実物がページの名前を並べない一般形なので採らなかった。
- 矛盾監査（6 件）：人が承認して、A-02（`screen-check.md` の手順 3 に上限のページの行）・A-04（`specs.md` に 3 桁の AC の番号）・A-05（ガイドに拡張が読む上限の範囲）・A-06（ガイドの使用量のタブの説明）を直した。A-01 は実物と違う指摘（CLAUDE.md の行は一般形）で直さなかった。A-03 はこの記録。
- 公式の文書と照らした助言（5 件）：人が承認して、V-01（続きの会話の費用が累計なのは v2.1.277 以降と、ガイドと `stageBudget.ts` のコメントに書いた）・V-03（「ごく少し超える」を、最後の 1 回の応答の分だけ超えることがある、に直した）を直した。V-02・04・05 は上の「受け入れたリスク」「確かめていないこと」に書いた。
- 審査（助言の報告の採点）：overall 0.95・verdict pass（事実の正確さ 1.0・引用の正確さ 0.75・網羅性 1.0・情報源の質 1.0・道具の効率 1.0）。引用が下がったのは、まだ無かったこの記録の文を引いたのと、出典の 1 か所の取り違え。
