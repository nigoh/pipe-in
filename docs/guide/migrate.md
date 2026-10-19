# devpipe から移る

[ガイドの目次](README.md) · [README](../../README.md) — 前の名前の版を使っていた人が、今の版へ移る手順です。

この道具の名前は devpipe から pipe-in に変わりました（0.3.0）。前の版を使っていたときは、次の手順で移ってください。パスは `<リポジトリ>`（このリポジトリのフォルダ）・`<対象>`（パイプを流すプロジェクト）に読み替えてください。

1. **入れ直す**：古いものを先に外してから入れます（順が逆だと、外すときに新しく入った別名のコマンドも消えます）。

   ```bash
   cd <リポジトリ>
   pip uninstall devpipe
   pip install -e '.[dev]'
   ```

2. **古いコマンド**：`devpipe`・`devpipe-gen` は 0.3 の間だけ別名として動き、標準エラーに「名前が変わりました」の案内を1行出します。**0.4 で消します。** `python -m devpipe` は無くなりました（`python -m pipe_in` を使います）。
3. **プラグイン**：古いマーケットプレイスを外して、登録し直します。スキルは `/pipe-in:pipe-build` になります。登録し直すまでの間も、古いプラグインのフックは別名の `devpipe-gen guard-hook` で動き、pipe-builder を止めます。

   ```
   /plugin marketplace remove devpipe
   /plugin marketplace add nigoh/pipe-in
   /plugin install pipe-in@pipe-in
   ```

4. **VSCode の拡張**：新しい `pipe-in-vscode.vsix` を入れ（[vscode/README.md](../../vscode/README.md)）、古い拡張を `code --uninstall-extension nok.devpipe-vscode` で外します。
   - 古い設定 `devpipe.workDir`・`devpipe.pipesDir` は、新しい設定 `pipe-in.workDir`・`pipe-in.pipesDir` を書いていない間は読みます。
   - 古いコマンド ID（`devpipe.showRun`・`devpipe.editPipe`）に付けたキー割り当ても効きます（パレットには出しません）。
   - 作業台の「保存した版」は引き継がれません（拡張の保存場所が変わるため）。
5. **パイプの置き場所**：前の版の `<対象>/.devpipe/pipes/devpipe-<名前>/` は、そのまま読めて流せます。作業台で直して保存しても、元のフォルダに書きます。新しい置き場所に移したいときは、次のようにします。

   ```bash
   cd <対象>
   mkdir -p .pipe-in/pipes
   git mv .devpipe/pipes/devpipe-<名前> .pipe-in/pipes/pipe-in-<名前>
   ```

   同じ名前のパイプが両方にあると新しいほうを使い、`pipe-in-gen new` はその名前では作りません。`pipe-in-gen list` は、古いものに「（古い名前）」と添えます。`<対象>` の `.gitignore` に `.devpipe/` を書いていたときは、`.pipe-in/` も足してください。
6. **環境変数**：パイプの置き場所は `PIPE_IN_PIPES_DIR` で変えます。`DEVPIPE_PIPES_DIR` も読みます（両方あれば新しいほう。プラグインのフックも同じ）。
7. **記録**：前の版が書いた記録（`docs/pipeline/` の `state.json` など）は、そのまま拡張で見られます。
8. **GitHub の URL**：リポジトリの名前が変わったあとは、手元の複製の向き先を直します（古い URL からも転送されます）。

   ```bash
   git remote set-url origin https://github.com/nigoh/pipe-in.git
   ```
