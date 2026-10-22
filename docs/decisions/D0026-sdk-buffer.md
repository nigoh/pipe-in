# D0026 段が大きい画像を Read しても落ちないようにする（SDK の受信バッファの上限 `[pipeline] max_buffer_mb`）

## 目的

pipe-in の利用者が、段に大きい画像（PNG など）を読ませても、Agent SDK の受信バッファの上限（SDK の既定は 1MB）を超えて pipe-in ごと落ちないようにする。超えたときも、何を変えればよいかが日本語で分かるようにする。

## 機能要件と受け入れ基準

- FR-01 各段を SDK で動かすとき、受信バッファの上限を必ず `ClaudeAgentOptions.max_buffer_size` に渡す。設定に書かなければ既定の 32MB（33554432 バイト）を使う。
  - D0026-AC-01 `pipeline.toml` に `max_buffer_mb` が無い（ファイル自体が無いときも含む）とき、`load_config` の上限は 32MB（33554432 バイト）で、`sdk_options` の `max_buffer_size` は 33554432。入っている SDK の `ClaudeAgentOptions` に `max_buffer_size` がある（`tests/test_sdk_buffer.py::test_D0026_AC_01_*`）。
- FR-02 `pipeline.toml` の `[pipeline]` の `max_buffer_mb`（1 以上の整数。単位は MB＝1024×1024 バイト）で上限を変えられる。どの段・どのパイプにも同じ値が効く。
  - D0026-AC-02 `max_buffer_mb = 64` のとき、開発フローの段（`requirements`）でもパイプの段（`pipe_in/pipe/specs.py` で作った段）でも、`sdk_options` の `max_buffer_size` は 67108864（`tests/test_sdk_buffer.py::test_D0026_AC_02_*`）。
- FR-03 `max_buffer_mb` に 1 以上の整数でない値が書かれていたら、段を流す前に、日本語で何がいけないかと直し方を出して止める（`SystemExit`）。
  - D0026-AC-03 `0`・`-1`・`1.5`・`"32"`・`true` のとき、`load_config` は `SystemExit` で止まり、文に `max_buffer_mb` と「1 以上の整数」が入る（`tests/test_sdk_buffer.py::test_D0026_AC_03_1以上の整数でない値は止める`）。
- FR-04 段の実行中に受信バッファの上限を超えたら、トレースバックで落とさず、その段を失敗（`is_error`）として返し、案内を `errors` と画面に出す。パイプラインは終了コード 3 で止まり、`state.json` にその段の実行が残る。
  - D0026-AC-04 上限を超えたことを表す SDK の文と今の上限から、今の上限（MB）・`max_buffer_mb`・`pipeline.toml`・SDK の元の文の入った案内を返す。ただの JSON の読み誤りの文には `None`。入っている SDK の `CLIJSONDecodeError` の文も見分けられる（`tests/test_sdk_buffer.py::test_D0026_AC_04_*`）。
  - D0026-AC-05 上限を超えた例外が出ても `run_stage_sdk` は外へ出さず、`is_error=True`・`subtype="error_max_buffer_size"`・`errors=[案内]` の `StageRun` を返し、画面にも案内を出す。`ClaudeAgentOptions` には `max_buffer_size` が渡る（`tests/test_sdk_buffer.py::test_D0026_AC_05_*`。SDK は偽物に差し替える）。
  - D0026-AC-07 要件定義の段が AC-05 の形の `StageRun` を返すと、終了コード 3 で止まり、`state.json` の `runs` にその段の実行と案内が残る（`tests/test_sdk_buffer.py::test_D0026_AC_07_上限を超えた段で終了コード3になりstate_jsonに残る`）。
  - D0026-AC-11 案内には、上限によらず、画像を小さくする道と、必要な所を切り出してから読ませる道が入る。今の上限が 32MB 未満なら `max_buffer_mb = <倍の値>` を勧める。32MB 以上なら倍の値は出さず、API のリクエストの上限も 32MB なので上げても通らないおそれがあると書く（`tests/test_sdk_buffer.py::test_D0026_AC_11_*`）。
  - D0026-AC-12 開発フローの検証（`test`）の段が AC-05 の形の `StageRun` を返すと、終了コード 4（テストを実行できなかった）でなく 3 で止まり、`state.json` の `runs` にその段の実行と案内が残る。`--from test`・`--from implement`・確認用コマンドありのどれでも同じ（`tests/test_sdk_buffer.py::test_D0026_AC_12_検証の段で上限を超えると終了コード3になりstate_jsonに残る`）。
- FR-05 上限を超えた以外の SDK の例外は、今までどおり外へ出す（握りつぶさない）。
  - D0026-AC-06 `CLIConnectionError` は `run_stage_sdk` から外へ出る（`tests/test_sdk_buffer.py::test_D0026_AC_06_ほかのSDKの例外は外へ出る`）。
  - D0026-AC-10 `run_stage_sdk` が段の失敗に変えるのは、型が SDK の `CLIJSONDecodeError` か、ちょうど素の `Exception`（`type(e) is Exception`）で、文に `maximum buffer size` があるときだけ。`ProcessError`・`MessageParseError`・`ClaudeSDKError`・`CLIConnectionError`・`RuntimeError`・`ValueError`・`Exception` の子は、文に `maximum buffer size` があっても外へ出る。受け止める2つの型でも、文に無ければ外へ出る（`tests/test_sdk_buffer.py::test_D0026_AC_10_*`）。
- FR-06 既定の値・キー・直し方を、`docs/guide/config.md` と見本の `pipeline.toml` に書く。
  - D0026-AC-08 前の版の `pipeline.toml`（`max_buffer_mb` が無く、`[stages.<段>]` に `model`・`max_turns`・`max_budget_usd` だけ）を読むと、段の設定は今までどおり効き、上限は 32MB（`tests/test_sdk_buffer.py::test_D0026_AC_08_前の版のpipeline_tomlは今までどおり読める`）。
  - D0026-AC-09 `docs/guide/config.md` と見本の `pipeline.toml` に `max_buffer_mb = 32` があり、`config.md` の表に `max_buffer_mb` の行がある（`tests/test_guide.py::test_D0026_AC_09_設定のガイドと見本にmax_buffer_mbと既定の32がある`）。

## 決めたことと理由

### 聞かずに決め、人が承認したこと

- 既定の上限は 32MB。Claude の API に渡せる画像は1枚 5MB までで、base64 にすると約 6.7MB。4枚ほどが1つのメッセージにまとまっても入る。上限は前もって確保する量ではなく、大きいメッセージが来たときだけ使うので、ふだんのメモリは増えない。選ばなかった形：10MB（大きい画像を2枚並べて読んだだけで超えうる）、64MB 以上。
- キーは `[pipeline] max_buffer_mb`（全体で1つ、MB の整数）。上限が要るかどうかは「プロジェクトに大きい画像があるか」で決まり、段ごとに変える理由が薄い。バイトで書かせると桁を間違えやすいので MB にし、単位をキー名に入れた。選ばなかった形：段ごとの `[stages.<段>] max_buffer_mb`、SDK と同じ名前・単位の `max_buffer_size`（バイト）、設定にせず既定だけを広げる（32MB でも足りないときに逃げ道が無い）。
- 上限を超えたら段の失敗（終了コード 3）にする。今までは例外がトレースバックで終わり、終了コードが Python の既定の 1 で「テストが通らなかった」と区別できず、`state.json` にも段の実行が残らなかった。上限を超えたとき以外の例外は外へ出すので、ほかの失敗は隠れない。選ばなかった形：案内だけを出して例外はそのまま外へ出す。
- 段のログ（`logs/*.jsonl`）には新しい行を書かない。ログの形と拡張の読み方を変えずに済む。案内は `state.json` の `runs[].errors` と画面に出る。
- 案内の最後に「SDK の文: …」として SDK の元の文（頭の 200 字まで）を付ける。実際に効いていた上限のバイト数が見え、設定が効いたかを確かめられる。`errors` は1つのまま。

### 見分け方

- 上限を超えたことは、例外の型と文の両方で見る（監査と助言の V-02 で、文だけで見ていた形から絞った）。受け止める型は、SDK の `CLIJSONDecodeError` と、ちょうど素の `Exception` の2つだけ。今の SDK では上限を超えると `CLIJSONDecodeError` のまま届くが、SDK の中の予備の経路で `Exception(str)` に平らにして投げ直されることもあるので、素の `Exception` も受ける。`CLIJSONDecodeError` はただの JSON の読み誤りにも使われるので、型に加えて文に `maximum buffer size` が入るかも見る。ほかの型（`ProcessError` など）は、文にこの言葉が混じっていても上限を超えたとは限らないので外へ出す。選ばなかった形：文だけで見る（ほかの失敗まで段の失敗に変えてしまう）、`ClaudeSDKError` の子をすべて受ける。
- SDK が文を変えたら気づけるように、入っている SDK の `CLIJSONDecodeError` を作ってその文を通すテストを置いた（D0026-AC-04）。
- `subtype` の `error_max_buffer_size` は SDK の `ResultMessage.subtype` の値ではなく、pipe-in が段の失敗に付ける値（監査と助言の V-05。名前は変えない）。
- 受け止めるのは `Exception` だけで、Ctrl+C や取り消し（`BaseException`）は受けない。`try` は `async with` の外に置き、SDK が子プロセスを閉じてから受け止める。
- `1 以上の整数` は `type(v) is int` で見る。TOML の `true` は Python では `bool`（`int` の子）になり、`isinstance` では通ってしまうため。

### 案内の文（監査と助言の V-03）

- 案内には、いつも、画像を小さくする道と必要な所だけを切り出してから読ませる道を入れる。上限を上げるより先に試せて、費用も下がるため。
- 倍の値（`max_buffer_mb = <倍>`）を勧めるのは、今の上限が 32MB 未満のときだけ。Claude の API の1つのリクエストの上限も 32MB なので、受信バッファをそれより上げても、その大きさのメッセージは API で通らないおそれがある。32MB 以上のときは倍の値を出さず、そのことを書く。`max_buffer_mb` と `pipeline.toml` の語は、上限によらず残す（D0026-AC-04）。

### 検証の段で超えたとき（監査の A-01）

- 開発フローの検証（`test`）の段で上限を超えたときも終了コード 3（段の失敗）にする。前は判定が返らない失敗として `parse_verdict` が blocked にし、終了コード 4（テストを実行できなかった。環境の問題など）になっていて、ほかの段と食い違っていた。`DevPipeline._test` が `subtype` が `error_max_buffer_size` の失敗を見分けて判定を作らずに返し、`_build_and_test` が `Exit.STAGE_ERROR` を返す。確認用コマンドは流さない。ほかの blocked（テストを実行できなかった）の意味と終了コード 4 は変えない。

### 互換

- `runner.py` は SDK の `CLIJSONDecodeError` を名前で import する。依存の下限 0.2.159 でも `claude_agent_sdk` の直下から取れることを、その版の配布物で確かめた。
- `pipeline.toml` に `[pipeline] max_buffer_mb` を足しただけで、無ければ 32 として読む。ほかの項目の意味は変えない（`docs/development/design.md` の「形を変えるとき（互換）」）。
- `state.json` の形は変えない。`runs[].subtype` に新しい値 `error_max_buffer_size` が入りうるだけ。
- 依存は足さない。`claude-agent-sdk>=0.2.159,<0.3` の下限の版にも `ClaudeAgentOptions.max_buffer_size` があり、上限を超えたときの文も同じ。

### 受け入れたリスク

- 上限の上の制限は付けない。とても大きい値を書くと、大きいメッセージが来たときにメモリを多く使いうる。要るとなったら足す。
- SDK が上限を超えたときの文を変えると、見分けられずに今までどおりトレースバックで落ちる。D0026-AC-04 のテストが SDK の文で落ちて気づける。

## 対象外・残った課題

- パイプの `pipe.toml` の `[[stages]]` に上限を書けるようにすること（VSCode の作業台が `pipe.toml` を書き直すので、拡張も直す必要がある）。
- `[stages.<段>]` ごとに上限を変えること。
- 画像を縮める・分けるなど、読ませる前に画像に手を入れること。
- `pipe-in-gen design`（`generator/`）の設定から上限を変えること。`generator/design.py` は `run_stage_sdk` と `load_config` を使うので、既定の 32MB と `pipeline.toml` の値は効く。ただし上限を超えたときの案内は使われない。`design.py` は段の失敗を「設計の段が失敗しました」とだけ扱ってやり直しを続け、やり直しの上限に達すると終了コード 1 で終わる（監査の A-03。コードは直していない。案内を出し、やり直さずに止めるのは残った課題）。
- 拡張の表示（`state.json` の `errors` は今の形のまま入るので、直さない）。

## 監査と助言で直したこと

検証で合格したあと、矛盾監査（`pipe-in-auditor`）と助言（`pipe-in-advisor`）を流し、人が承認した項目だけを直した。

- 直した：V-02（受け止める例外の型を絞る。D0026-AC-10）、V-03（案内の文。D0026-AC-11）、A-01（検証の段で超えても終了コード 3。D0026-AC-12）、V-01（`runner.py` の見分け方のコメント）、V-04（SDK の既定の 1MB の出どころ。公式の文書では `max_buffer_size` の既定は `None` で、1MB は SDK のソースの中の定数 `_DEFAULT_MAX_BUFFER_SIZE`。`runner.py`・`config.py` のコメント）、V-05（`error_max_buffer_size` は pipe-in が付ける値）、A-02（番号を D0026 に付け直した。下の「番号」）、A-03（`pipe-in-gen design` の実際の動きをこの記録に書いた）、A-04・A-05（テストの直し。テストは実装の段では書けないのでメインが直した）、A-06（`docs/guide/config.md` の表の見出し）。
- 直さなかった：A-03 のコード（`generator/design.py` で案内を出して止めること。残った課題）。A-03 は、人が「記録に実際の動きを書く」形で承認したので、コードは直していない。ほかの項目はすべて上のとおり直した。
- 助言の報告の審査（`pipe-in-judge`）の採点は overall 0.85・pass。

## 番号

この記録は、はじめ D0023 で書いていた。D0022 が D0023〜D0025 を予約していたので、重ならないよう D0026 に付け替えた。AC の ID も `D0026-AC-xx` にそろえた。

## 確かめたこと

- `tests/test_sdk_buffer.py`（AC-01〜08、監査と助言のあとに足した AC-10〜12）と `tests/test_guide.py` の AC-09 が通った。SDK の入った環境で流し、入っている SDK を見る2つのテスト（AC-01・AC-04）も飛ばずに通った。全体のテストも通った。
- 実機で大きい画像を段に読ませ、32MB の上限で止まらないこと・上限を小さくして案内が出ることは、まだ確かめていない。
