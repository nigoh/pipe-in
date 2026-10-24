# pipe-in の開発のルール

pipe-in（本体・ジェネレーター・プラグイン・VSCode 拡張）を直したり機能を足したりするときの決まりです。
人も Claude Code も、ここに従って進めます。Claude Code で進めるときは `/pipe-in <要件メモ>` が、この決まりどおりに段を進めます。

## どれを読むか

| こんなとき | 読むもの |
| --- | --- |
| はじめて触る・迷ったとき | [principles.md](principles.md)（原則） |
| 何を作るかを決める | [specs.md](specs.md)（仕様の書き方・決定の記録・AC の ID） |
| どこに何を置くか・形を変える | [design.md](design.md)（層・依存の向き・置き場所・互換・依存を足す基準） |
| テストを書く | [testing.md](testing.md)（テストの種類・偽物・やってはいけないこと・赤の確かめ方） |
| 始めてから終えるまで | [workflow.md](workflow.md)（ブランチと worktree・段の進め方・文書をそろえる・コミット） |
| 前に何をなぜ決めたか | [../decisions/](../decisions/)（機能ごとの決定の記録） |

## テストで守らせている決まり

文書だけでは守れないので、検査できるものはテストにしてあります。決まりを変えるときは、テストも一緒に変えます。

| 決まり | 検査するテスト |
| --- | --- |
| 依存の向き（本体・ジェネレーター） | `tests/test_architecture.py` |
| 前の名前が、決まったファイル（読み替え・移行の案内・歴史）にしか残っていない | `tests/test_rename.py` |
| プラグインの pipe-builder が書ける場所と Bash、pipe-judge が読む道具だけであること、/pipe-in のサブエージェント（監査と助言を含む）が書ける場所と Bash・助言の Web の行き先 | `tests/test_guard_hook.py`・`tests/test_pipe_in_guard.py` |
| パイプの段の Bash の書き込みが、段の書き込み範囲に収まること（決まった形で先が読めるもの） | `tests/test_bash_write_guard.py` |
| /pipe-in のサブエージェント用のフックが、内側で例外が出ても `pipe-in-*` の呼び出しを止める（読むだけの道具と報告は通す）こと。deny の JSON を書けないときは終了コード 2 で止めること（D0032） | `tests/test_pipe_in_guard.py` |
| 審査の総合点・合否・ばらつきの計算 | `tests/test_judge_score.py` |
| 段の検証の審査（`[stages.check.judge]`）の合否の計算と、プラグインの計算との一致・差し戻し | `tests/test_judge_calc.py`・`tests/test_check_judge.py` |
| 拡張の層ごとに使ってよい部品・`vscode` を import するのは入口だけ | `vscode/src/architecture.test.ts` |
| パネルの CSP（インラインの style を使わない） | `vscode/src/webview/csp.test.ts` |
| 手元の事情（ユーザー名の入ったパス・メールアドレス）と秘密のファイルを載せない | `tests/test_rules.py` |
| 決定の記録の形・テストの AC の ID が記録にある | `tests/test_rules.py` |
| CLAUDE.md と design.md の置き場所の表が実物と食い違わない | `tests/test_rules.py` |
| 調べた結果の目次がすべての調査を指し、本文に決めた節がある | `tests/test_research.py` |
| テストがリポジトリの実物（`pipes/`・`.pipe-in/`・前の版の置き場所・`docs/pipeline/`）を変えない | `tests/conftest.py`（テストが通っても、最後に失敗にする） |
