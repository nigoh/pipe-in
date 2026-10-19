# VSCode の拡張

[ガイドの目次](README.md) · [README](../../README.md) — 実行を図で見るパネルと、パイプを組み立てる作業台の説明です。

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../assets/run-panel-dark.png">
  <img src="../assets/run-panel-light.png" alt="VSCode のパネル。左に開発フローの段の図（要件定義 → 設計 → テスト先行 → 実装 → 検証。修正の依頼1回・差し戻し1回）、右に検証の出力・成果物・使用量" width="900">
</picture>

<sub>VSCode の拡張のパネル。見本の記録（数字は見本）を拡張の本物の画面で写したもの。</sub>

`vscode/` にある拡張で、実行の進み具合をパネルに図として見たり、パイプを作業台で組み立てたりできます。拡張は記録を読むだけで、記録には何も書きません。くわしい使い方は [vscode/README.md](../../vscode/README.md) にあります。

```bash
# 拡張を作って、普段の VSCode に入れる
cd vscode
npm install
npm run package                                        # pipe-in-vscode.vsix ができる
code --install-extension pipe-in-vscode.vsix --force
```

## 実行を見る

コマンドパレットの「pipe-in: 実行を見る」か、ステータスバーの `pipe-in` のボタンでパネルが開きます（冒頭の画像）。

- 左に段の図（要件メモ → 要件定義 → 確認 → … → 完了）。動いている段・確認待ち・差し戻しの回数が出ます。
- 右に、いま見ている段の出力・成果物の一覧（押すと開く）・使用量（段ごとのトークン・モデル別・利用枠）。
- `pipe-in --pipe` で流したパイプの記録も、開発フローと切り替えて見られます。

## パイプ作業台

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../assets/pipe-editor-dark.png">
  <img src="../assets/pipe-editor-light.png" alt="パイプ作業台。ブロックをケーブルでつないで段の並びを組み、右で選んだ段の設定を決める" width="900">
</picture>

<sub>パイプ作業台。見本のパイプを開き、段「ソースの調査」を選んだところ。</sub>

VSCode 拡張の「pipe-in: パイプ作業台を開く」で、パイプをフロー図として組み立てられます（[vscode/README.md](../../vscode/README.md)）。
形で見分けるブロックを置き、プラグをコンセントに差すようにつなぎ、各ブロックで Claude に頼むことと[パイプの設定](pipes.md#定義の書き方pipetoml)を決めて、`.pipe-in/pipes/pipe-in-<名前>/`（無ければ `pipes/`。前の版のフォルダのパイプは元のフォルダ）に保存します。
