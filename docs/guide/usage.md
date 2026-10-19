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
```

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
pipe-in record begin requirements                 # 段を始める（拡張に「動いている」と出る）
pipe-in record done requirements --summary "…"    # 段を閉じる
pipe-in record wait requirements                  # 確認待ち
pipe-in record review requirements approved       # revise --feedback "…" / quit
pipe-in record red red --summary "…"              # テスト先行の結果
pipe-in record verdict pass --attempt 1 --summary "…"   # 検証の判定
pipe-in record finish PASSED                      # 記録を閉じる
```

</details>

- 記録には `"driver": "pipe-dev"` が入ります。`pipe-in --review` は、`driver` の入った記録（前の版の記録も）の続きを流しません。

## 注意

> [!NOTE]
> 費用は SDK が返す概算です。実際の請求とはずれることがあります。

- Claude Code の中（Bash ツール）から起動しても、修正の依頼（同じ会話の続き）は使えます（Claude Code 2.1.119・claude-agent-sdk 0.2.168 で確認）。古い版で会話を引き継げないときは、普段のターミナルから実行してください。
- 対象プロジェクトの CLAUDE.md・`.claude/` の規約やフックを各段に効かせたいときは、`setting_sources = ["project"]` を設定してください。
- Windows で日本語の表示が崩れるときは `PYTHONUTF8=1` を設定してください。
- 動作を確認した環境：Python 3.13、claude-agent-sdk 0.2.159〜0.2.168、Claude Code 2.1.301。
