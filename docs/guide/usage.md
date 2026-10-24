# 使い方

[ガイドの目次](README.md) · [README](../../README.md) — pipe-in の流し方と、確認の答え方の説明です。

## 開発フローの流れ

- 要件定義・設計・テスト先行のあとに、人が内容を確認します（承認 / 修正を依頼 / 中止）。
- テスト先行の段は、製品コードより先に受け入れ基準（AC）ごとのテストを書き、落ちることを確かめます。テストのない AC が残れば差し戻します。
- 検証が不合格なら、検証報告を添えて実装へ差し戻します（既定で最大3回）。
- 段ごとに書き込める範囲を決めてあり、範囲外の書き込みや危ない操作は止めます。

テスト駆動（赤 → 緑 → 整理）とドメイン駆動の設計を前提にしています。

```
要件メモ ─▶ 要件定義 ─[確認]─▶ 設計 ─[確認]─▶ テスト先行（赤）─[確認]─▶ 実装（緑・整理）─▶ 検証 ─▶ 合格
                                                                         ▲                │
                                                                         └──── 不合格 ────┘（最大3回）
```

## 流す

```bash
# 要件メモをファイルで渡す
pipe-in --project ~/src/myapp --input request.md

# 直接書く
pipe-in --project ~/src/myapp --text "ユーザー一覧に CSV 出力ボタンを追加したい"

# 確認なしで最後まで流す
pipe-in --project ~/src/myapp --input request.md --yes

# テスト担当の判定に加えて、自分のテストコマンドでも裏付けを取る
pipe-in --project ~/src/myapp --input request.md --test-cmd "pytest -q"

# この実行にセッション名を付ける（VSCode の実行の一覧に出る）
pipe-in --project ~/src/myapp --input request.md --name "CSV 出力を足す"
```

`--name` は始めるときだけ付けられます（`--review` とは一緒に使えません）。付けなければ、要件メモの最初の行から作ります。名前は `state.json` の `name` に残り、確認待ちからの再開でも変わりません（[記録](records.md)）。

> [!WARNING]
> `--yes` は確認なしで最後まで流します。人が見ないままコードが書き換わり、費用もかかります。

`pipe-in` の代わりに `python -m pipe_in` でも動きます。

## 途中から再開する

前の段の文書が残っていれば、その次から始められます。

```bash
pipe-in --project ~/src/myapp --from design      # 要件定義書を手で直したあと
pipe-in --project ~/src/myapp --from red         # 設計書を手で直したあと
pipe-in --project ~/src/myapp --from implement   # 先に書いたテストを手で直したあと
pipe-in --project ~/src/myapp --from test        # 検証だけやり直す
```

## 確認の画面

要件定義・設計・テスト先行のあとに、文書の先頭60行を表示して止まります。テスト先行のあとは「このテストが通れば要件を満たすと言えるか」を見てください。ここが実装にとっての仕様になります。

- `Enter`：承認して次の段へ
- `r`：修正してほしい点を書く（空行で終わり）。同じ会話のまま直させて、もう一度確認します
- `q`：中止

## 確認で止めて、あとから答える（チャットから動かすとき）

対話できない所（Claude Code のチャット、CI など）から動かすときは `--pause` を付けます。確認の段まで流したら、入力を待たずに `state.json` の `pending_review`（段・文書・会話の ID）を残して止まります（終了コード 5）。文書を読んで、`--review` で答えると続きから流れます。

```bash
pipe-in --project ~/src/myapp --input request.md --pause --test-cmd "pytest -q"   # 要件定義のあとで止まる
pipe-in --project ~/src/myapp --review approve --test-cmd "pytest -q"             # 承認 → 設計のあとで止まる
pipe-in --project ~/src/myapp --review revise --feedback "AC-03 を分けて"          # 同じ会話のまま直させ、また止まる
pipe-in --project ~/src/myapp --review quit                                       # 中止
```

- 記録（`state.json` の `runs`・段のログの番号・費用の合計・注意）は、呼び出しをまたいで続きます。
- `--test-cmd`・`--max-retries` は記録に残らないので、`--review` のたびに同じものを渡してください。
- 止まっている間の `final` は空のままです（VSCode のパネルでは「次を待っている」と出ます）。

## 記録だけを書く（`pipe-in record`）

段を流さずに、開発フローと同じ形の記録（`state.json`・段のログ・`99_summary.md`）だけを書きます。SDK は呼ばず、利用料もかかりません。Claude Code の開発用スキル（このリポジトリの `/pipe-in`）が、会話の中で進めた段を VSCode の拡張で見られるように使います。

<details>
<summary>コマンドの一覧</summary>

```bash
pipe-in record start --text "要件メモ"            # 00_input.md と空の記録（途中の記録があれば断る。終わった記録は archive/ へ）
                                                  #   --name "…"（セッション名）・--session-id <ID> も付けられる
pipe-in record begin requirements                 # 段を始める（拡張に「動いている」と出る）
                                                  #   --agent <名前> を付けると、時系列の行に受け持ちが出る
pipe-in record done requirements --summary "…"    # 段を閉じる
pipe-in record wait requirements                  # 確認待ち
pipe-in record review requirements approved       # revise --feedback "…" / quit
pipe-in record red red --summary "…"              # テスト先行の結果
pipe-in record verdict pass --attempt 1 --summary "…"   # 検証の判定
pipe-in record finish PASSED                      # 記録を閉じる
```

</details>

- 記録には `"driver": "pipe-dev"` が入ります。`pipe-in --review` は、`driver` の入った記録（前の版の記録も）の続きを流しません。

## 進み具合を Claude のアーティファクトで見る（`pipe-in live`）

Claude Code（デスクトップアプリ・claude.ai/code）の会話から `/pipe-in --artifact <要件メモ>` で流すと、会話の横のページ（Claude のアーティファクト）に、どの段が動いている・確認待ちか、何回目か、どれだけ経ったかが出ます。ページは見るだけです。承認・修正の依頼・中止はできません（これまでどおり会話で答えます）。

- ターミナルで `pipe-in` を流しているときは、別の Claude Code の会話で `/pipe-in:pipe-live` を呼ぶと見られます（[下](#ターミナルで流している実行を見るpipe-in-live-watch)）。VSCode の拡張でも見られます。
- 会話が、`pipe-in record` で記録を書くたびに、記録から作った小さな JSON（写し）をアーティファクトのデータに書き、ページがそれを受けて描き直します。ページの HTML は最初に1回だけ公開します。
- 写しには、セッション名・段の名前と表示名・状態・回数・時刻・最後の結果・検証の判定・費用/ターン/時間の数字だけが入ります。要件メモの本文・`session_id`・パス・自由な文・ログの中身は入りません（[アーティファクトに出す写し](records.md#アーティファクトに出す写し)）。
- 画面の段の行は、状態を印（待ち＝枠の丸、動いている＝塗りの丸、確認待ち＝半分塗りの丸。完了・失敗・差し戻しは文字）と言葉で示します。費用とターンは 0 のとき出さず、時間は経過と同じ `m:ss`（1時間以上は `h:mm:ss`、上限は 99:59:59）で出します。
- 色はライト/ダークのどちらでも読めるようにしてあります。幅が狭くても横にはみ出しません。

写しとページを作るコマンドは次の2つです（見張る `watch` は[下](#ターミナルで流している実行を見るpipe-in-live-watch)）。記録は読むだけで、段は流さず、SDK も子プロセスも使いません（利用料はかかりません）。

```bash
pipe-in live snapshot [--project DIR] [--config FILE] [--work-dir DIR] [--out FILE]   # 写し（JSON）を出す
pipe-in live page [--out FILE]                                                         # ページ（HTML）を出す
```

- `--work-dir` を省くと、設定の `work_dir`（開発フローの `docs/pipeline/`）を読みます。パイプの記録は `--work-dir docs/pipeline/<パイプ名>` で読めます。
- `--out` を省くと標準出力に出します。`--out` のファイルは、親のフォルダがあり、シンボリックリンクでなく、`snapshot` では読み先の記録のフォルダの中でないときだけ書きます（断るときは終了コード 2、書けなかったときは 1）。
- 記録が無い・壊れている・大きすぎるときは、「記録なし」の形（`empty` が `true`）を出して終了コード 0 です。引数の誤りは終了コード 2 です。

### ターミナルで流している実行を見る（`pipe-in live watch`）

ターミナルで `pipe-in` を流したあと、別の Claude Code の会話で `/pipe-in:pipe-live`（[プラグイン](plugin.md)。claude.ai にログインした Claude Code で、Artifact・ArtifactData・Monitor が使えるときだけ）を呼ぶと、ページを1回だけ公開し、段の区切りごとに図が更新されます。裏で動くのが `pipe-in live watch` です。Monitor は1回の見張りが最長30分で止まるので、スキルは見張りを `--timeout 1750` ほどで起こし、`timeout` の行（終了コード 124）か Monitor の期限で止まったときに、実行が続いていれば起こし直します。起こし直すと `seq` は 1 からになりますが、アーティファクトへの書き込みは前の結果の `version` を引き継ぐので、図は続けて更新されます。

```bash
pipe-in live watch --out FILE [--project DIR] [--config FILE] [--work-dir DIR] [--interval 秒] [--timeout 秒]
```

- 記録を `--interval` 秒（0.5〜60、既定 2）ごとに読み、写しの中身が変わったときだけ、`--out` に写しを書いて標準出力に1行を出します。`generated_at` だけの違い、動いている段の経過時間だけの違いでは出ません。最初の1回は、記録が無くても必ず出ます。
- 記録を一瞬だけ読めなかったときは何も出さず、3回続けて読めなかったときだけ「記録なし」の行を出します。
- `--out` は必須です。読み先の記録のフォルダの中・シンボリックリンク・親のフォルダが無い所・既存のフォルダは断ります（終了コード 2）。書くときは同じフォルダの一時ファイルに全部書いてから置き換えるので、読む側は書きかけを見ません。
- 行は1行1つの JSON で、キーは `event`・`seq`・`final`・`empty` の4つだけです。`event` は `snapshot`（変わった）・`final`（final が入った写しを出した。この1行だけで、`snapshot` の行は別に出ません）・`timeout`（上限）。`seq` は出した写しの通し番号（1から）。`final` は写しの `final` か `null`、`empty` は写しの `empty` です。
- 止まる条件：final が入った写しを出したとき（終了コード 0。起動したときにすでに final の記録なら、最初の1回で出して止まります）、`--timeout` 秒（1〜86400、既定 21600＝6時間）に達したとき（`timeout` の行を出して 124）。`--pause` の確認待ちでは止まらず、見張り続けます。

| 終了コード | 意味 |
|---|---|
| 0 | final を出して止まった |
| 124 | `--timeout` に達した |
| 130 | Ctrl+C |
| 143 | 終了の合図（SIGTERM）を受けた |
| 1 | 設定が読めない（`--project` に無いフォルダを渡したときなど。文は標準エラー）、`--out` に3回続けて書けなかった、または標準出力が閉じられた・書けなくなった |
| 2 | 使い方の誤り（引数・`--out` の断り） |

見るだけです。ターミナルの実行は止められず、承認や直してほしい点の送信もできません（ターミナルでします）。実行が異常終了して final が入らなかったときは、`timeout` まで続きます。記録は読むだけで、段は流さず、SDK も子プロセスも使いません（利用料はかかりません）。

## 注意

> [!NOTE]
> 費用は SDK が返す概算です。実際の請求とはずれることがあります。

- Claude Code の中（Bash ツール）から起動しても、修正の依頼（同じ会話の続き）は使えます（Claude Code 2.1.119・claude-agent-sdk 0.2.168 で確認）。古い版で会話を引き継げないときは、普段のターミナルから実行してください。
- 対象プロジェクトの CLAUDE.md・`.claude/` の規約やフックを各段に効かせたいときは、`setting_sources = ["project"]` を設定してください。
- Windows で日本語の表示が崩れるときは `PYTHONUTF8=1` を設定してください。
- 動作を確認した環境：Python 3.13、claude-agent-sdk 0.2.159〜0.2.168、Claude Code 2.1.301。
