# テストの決まり

## テストの種類

| 種類 | 何を確かめるか | 置き場所・例 |
| --- | --- | --- |
| 単体 | 純粋な関数（判断） | `choosePipesDir`（`vscode/src/app/pipeEditor.test.ts`）・`check_bash`（`tests/test_guard_hook.py`） |
| 組み合わせ | 偽物の口（runner・PipeStore など）で、流れを最初から最後まで通す | `tests/test_pipeline.py` の `FakeRunner`、`tests/test_pipe_flow.py` の `ScriptedRunner` |
| 構造 | 依存の向き・層・公開してよいか・文書と実物の食い違い | `tests/test_architecture.py`・`tests/test_rules.py`・`vscode/src/architecture.test.ts` |
| 画面 | 見た目（重なり・はみ出し・読めない色）と操作 | Playwright（MCP）で確認用のページを開いて撮る（`/pipe-in` の「5. 検証」）。判断は純粋な関数に置いて、そちらは単体で確かめる |
| 手で | 単体では確かめられない、手元の環境での動き（例：Git Bash と PowerShell から呼ぶ） | 手順と結果を決定の記録に書く |
| 実機 | SDK を呼ぶ・Claude Code にプラグインを入れる | **人に言われたときだけ**（利用料や、手元の設定が変わる）。結果を決定の記録に書く |

- 本体：`python -m pytest -q`（`tests/`）
- 拡張：`cd vscode && npm test`（`vscode/src/**/*.test.ts`、node:test）と `npm run typecheck`

## 偽物の使い方

- **モックのライブラリは使わず、手で書いた偽物を使います。** 口（runner・`PipeStore`・`WorkDirSource`）を満たす小さなクラスや関数を、テストの中か、そのテストのファイルの頭に書きます。
- ファイルは `tmp_path`（Python）・`mkdtemp(tmpdir())`（拡張）の中に作ります。
- 環境変数は `monkeypatch.setenv` / `delenv` で変えます（テストのあとに戻ります）。
- 時計や乱数が判断に入るなら、引数で渡せる形にします。

## やってはいけないこと

- **リポジトリの実物に書く**：`pipes/`・`.pipe-in/`・前の版の置き場所・`docs/pipeline/`。既定の置き場所がリポジトリの中を指す関数（`default_pipes_dir` など）を通るテストは、置き場所を `tmp_path` に向けます（`tests/test_generator.py` の `no_repo_pipes` を参照）。書いてしまったら、テストが通っていても `tests/conftest.py` が最後に失敗にします。
- ホームのフォルダ（`~`）や、テストの外のフォルダに書く。
- ネットワークにつなぐ・SDK を呼ぶ。
- `sleep` で待つ。テストの順番に頼る（1つずつ流しても通るように書く）。
- 手元のパスやユーザー名を、テストの中に書く（見本のパスは `D:/work/app`・`~/src/myapp` のように書く）。

## 赤の確かめ方

テスト先行の段では、足したテストが**期待した理由で**落ちていることを確かめます。

1. 足したテストのファイルだけを流す（`python -m pytest -q tests/test_xxx.py`・`node --experimental-strip-types --test src/xxx.test.ts`）。
2. 失敗を1件ずつ読み、例外の型と文が「まだ作っていないから」になっているかを見る。**出力を `head` などで切らない。** 切ると、ファイルごと読めずに落ちているものを見落とす。
3. 次のものは赤と認めない（テストを直す）：
   - 構文の誤り・つづりの誤り・テストの補助の誤りで落ちている
   - 「新しい部品がまだ無い」以外の理由で import が失敗している
4. 今の作りのままで通るテストは、そう書く（守り続けるための検査として置く、など理由も）。
5. 既存のテストが通ったままであることを確かめる。

スクリプトでテストのファイルを書き換えたときは、とくに 1・2 を省かない（文字列の `\n` が本物の改行になる、などの誤りが入りやすい）。

## 名前と粒度

- 1つのテストで1つのことを確かめます。名前は、何を確かめるかが分かる日本語の文にします。
- 頭に受け入れ基準の ID（`Dnnnn-AC-xx`）を付けます（[specs.md](specs.md)）。
- 同じ確かめ方で入力だけが違うもの、とくに**すり抜けの道**は、パラメータ化して並べます（`tests/test_guard_hook.py` の形）。新しい道に気づいたら、まず1行足して赤を見てから直します。
- 検査のテスト（構造・ルール）には、「検査そのものが違反を見つけられる」ことを確かめるテストも付けます（`test_rule_catches_reverse_import` の形）。

## テストを変える・消すとき

- 承認されたテストを、実装の段で書き換えません。
- 仕様が変わったときだけ、テストを書き換えたり消したりします。そのときは決定の記録に、何をなぜ変えたかを書きます。
- 検査を緩める（許す範囲を広げる）ときは、[principles.md](principles.md) の「4. 安全側に倒す」に従います。
