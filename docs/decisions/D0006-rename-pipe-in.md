# D0006 製品の名前を devpipe から pipe-in に変える（前半：製品）

## 目的

製品の名前を、コマンド・Python の import 名・VSCode 拡張・Claude Code のプラグイン・パイプの置き場所まで含めて `pipe-in` にそろえる。
今 devpipe を使っている人の、作ったパイプ・記録・設定・入れたプラグインが、入れ直したあとも読めて、守りのフックが黙って外れないようにする。

## 機能要件と受け入れ基準

- FR-01 Python のパッケージ名を `pipe-in`、import 名を `pipe_in`（フォルダ `devpipe/` → `pipe_in/`）と `pipe_in_generator`（フォルダは `generator/` のまま）にし、版を 0.3.0 にする
  - D0006-AC-01 `pyproject.toml` の名前・版・コマンド・パッケージの名前（`tests/test_rename.py::test_pyproject_names_version_and_scripts`）
- FR-02 コマンドを `pipe-in`・`pipe-in-gen`（`pipe-in record`）にし、`python -m pipe_in` で動かす。ヘルプ・誤り・案内の文のコマンド名もそろえる
  - D0006-AC-02 古いフォルダが無く、ヘルプの usage が新しい名前で、`python -m pipe_in --help` に古い名前が出ない（`tests/test_rename.py::test_old_package_folder_is_gone`・`::test_help_shows_new_command_names`・`::test_python_m_pipe_in_help`）
  - D0006-AC-03 依存の向きの検査が新しい名前で行われ、古い名前を import しない（`tests/test_architecture.py`）
- FR-03 古いコマンド `devpipe`・`devpipe-gen` を 0.3 の間だけ別名で残す。中身は同じで、標準エラーに案内を1行出す。`devpipe-gen guard-hook` の標準出力は変えない
  - D0006-AC-04 別名の宣言・同じ終わり方・案内が1行・フックの標準出力がバイト単位で同じ（`tests/test_rename.py::test_pyproject_keeps_old_aliases`・`::test_devpipe_alias_runs_same_and_warns`・`::test_devpipe_gen_alias_runs_same_and_warns`・`::test_devpipe_gen_guard_hook_stdout_is_identical`）
- FR-04〜FR-07 パイプのフォルダ名を `pipe-in-<名前>/`、置き場所を `.pipe-in/pipes/`、環境変数を `PIPE_IN_PIPES_DIR` にする。前の版の `.devpipe/pipes/`・`devpipe-<名前>/`・`DEVPIPE_PIPES_DIR` も読む（新しいほうが先）。同じ名前がほかにあれば `new`・`design` は断る。`list` は前の版のものに「古い名前」と添える
  - D0006-AC-05 探す順と、頭を除いた名前（`tests/test_pipe.py::test_find_pipe_by_name_or_path`・`::test_find_pipe_explicit_dir_only`・`::test_find_pipe_prefers_new_place_then_old`・`::test_find_pipe_prefers_new_folder_name_in_same_place`・`::test_load_pipe_name_from_old_folder`・`::test_folder_names_and_prefixes`、`tests/test_pipe_flow.py`）
  - D0006-AC-06 `pipes_dirs` の順（`tests/test_pipe.py::test_find_pipe_prefers_project_pipes`・`::test_pipes_dirs_order`）
  - D0006-AC-07 作る場所（`tests/test_pipe.py::test_new_pipes_dir_order`・`::test_new_pipes_dir_prefers_new_env`、`tests/test_generator.py::test_new_makes_pipe_folder`・`::test_new_defaults_to_project_pipes`・`::test_new_respects_pipes_dir_and_env`）
  - D0006-AC-08 同じ名前が古い置き場所・古いフォルダ名にあれば、`--force` でも断り、何も書かない（`tests/test_generator.py::test_new_refuses_name_in_old_place`・`::test_new_refuses_old_folder_name_in_new_place`・`::test_design_refuses_existing_pipe`・`::test_design_refuses_name_in_old_place`）
  - D0006-AC-09 一覧に新旧の両方を出し、古いものに「古い名前」（`tests/test_generator.py::test_list_shows_project_and_shared_pipes`・`::test_list_marks_old_names`、`tests/test_pipe.py::test_is_legacy`）
  - D0006-AC-10 環境変数の順（`tests/test_pipe.py::test_default_pipes_dir_can_be_overridden`・`::test_env_pipes_dir_prefers_new_name`）
- FR-08 プラグインのフックは、`pipe-in-<名前>/` と `devpipe-<名前>/`（と2つの環境変数の下）の決まったファイルだけを pipe-builder に書かせ、Bash は `pipe-in-gen list / new / check` だけを許す
  - D0006-AC-11 書き込みの許可と拒否（`tests/test_guard_hook.py`）
  - D0006-AC-12 Bash・ほかの道具・3つの `agent_type`（`pipe-builder`・`pipe-in:pipe-builder`・`devpipe:pipe-builder`）（`tests/test_guard_hook.py`）
  - D0006-AC-13 2つの環境変数（`tests/test_guard_hook.py::test_env_pipes_dirs_reads_both_names`・`::test_main_allows_both_env_places` ほか）
- FR-09 プラグインの名前を `pipe-in`、版を 0.2.0 にし、フックのコマンドを `pipe-in-gen guard-hook` にする
  - D0006-AC-14 `tests/test_plugin.py`
- FR-10〜FR-13 VSCode 拡張の名前・コマンド・設定・作業台の置き場所を新しい名前にし、古い設定・古いコマンド ID・古い置き場所とフォルダ名も読む
  - D0006-AC-15 拡張の宣言（`vscode/src/manifest.test.ts`・`vscode/src/app/names.test.ts`）
  - D0006-AC-16 設定は新しい設定 → 古い設定 → 既定の順（`vscode/src/app/names.test.ts`）
  - D0006-AC-17 古いコマンド ID は登録だけしてパレットに出さない（`vscode/src/app/names.test.ts`・`vscode/src/manifest.test.ts`）
  - D0006-AC-18 作業台の置き場所の選び方（`vscode/src/app/pipeEditor.test.ts`）
  - D0006-AC-19 作業台の読み書き（`vscode/src/app/pipeEditor.test.ts`・`vscode/src/infra/fsPipes.test.ts`）
  - D0006-AC-20 README の下書きと保存先の文字（`vscode/src/app/pipeEditor.test.ts`）
  - D0006-AC-21 ステータスバーとパネルの題（`vscode/src/view/statusBar.test.ts`・`vscode/src/view/pipeHtml.test.ts`・`vscode/src/view/panelHtml.test.ts`）
- FR-14 開発用の記録の `driver` を `"pipe-dev"` にし、`pipe-in --review` は `driver` のある記録を値に関わらず断る
  - D0006-AC-22 記録の `driver`・ログの言葉・まとめの題（`tests/test_record.py`）
  - D0006-AC-23 `--review` が断る・`driver` の無い記録は続ける（`tests/test_record.py::test_review_refuses_records_with_a_driver`・`::test_review_continues_a_record_without_driver`）
  - D0006-AC-24 前の版の記録も拡張で同じに読める（`vscode/src/domain/pipeInRecord.test.ts`、`tests/test_record.py::test_old_fixture_differs_only_in_driver`）
- FR-15〜FR-17 文書を新しい名前にそろえ、`.gitignore` と見張りに新しい置き場所を足し、古い名前の残りをテストで確かめる
  - D0006-AC-25 見張りと `.gitignore`（`tests/test_rules.py`）
  - D0006-AC-26 古い名前は決まったファイルにしか残らない（`tests/test_rename.py::test_old_name_only_in_allowed_files`・`::test_readme_old_name_only_in_migration_section`、`tests/test_rules.py`）
  - D0006-AC-27（画面）作業台の保存先・README の下書きに新しい名前が出て、画面の文字に古い名前が無い
  - D0006-AC-28（手で）新しい `.vsix` で古い設定・古いコマンド ID のキー割り当てが効き、古い拡張を外せる
  - D0006-AC-29（手で）入れ直したあと、新しいプラグインでも古いプラグインのまま（別名）でも pipe-builder が止められる
- FR-18 GitHub のリポジトリ名の変更は、main に入ったあと、人に確認を取ってから人が行う
  - D0006-AC-30（手で・人の確認のあと）名前を変え、`git remote set-url` のあと `git fetch` が通る
- FR-19 この決定の記録を書き、表に1行足す（D0001〜D0005 は書き換えない）

## 決めたことと理由

- **古いコマンドは 0.3 の間だけ別名で残し、0.4 で消す。** 古いプラグインのフックは `devpipe-gen guard-hook` を呼ぶ。コマンドが無くなるとフックの失敗は「止めない誤り」になり、pipe-builder の書き込みの制限が黙って外れる。別名があれば、プラグインを登録し直すまでの間も守れる。別名の入口は `pipe_in/legacy.py` と `generator/legacy.py` に分けた（`pipe_in` から `pipe_in_generator` を読まない依存の向きを崩さないため）。案内は標準エラーにだけ出し、フックの JSON を壊さない。
- **`python -m devpipe` の別名は作らない。** `devpipe/` のフォルダを残すことになり、依存の検査がややこしくなる。
- **古い置き場所・フォルダ名・環境変数は読み続け、移す道具は作らない。** 利用者のファイルを動かすコマンドは守りの検査とテストが増える。読むだけなら壊れない。探す順は「置き場所の順（`.pipe-in/pipes` → `.devpipe/pipes` → 今までの場所）→ 同じ置き場所の中では `pipe-in-` → `devpipe-`」。探す順・名前の読み替えは `pipe_in/pipe/definition.py` の純粋な関数（`pipe_folders`・`name_of`・`is_legacy`・`env_pipes_dir`）に置いた。
- **同じ名前のパイプがほかにあれば、`new`・`design` は `--force` でも断る。** 新旧2つができて、どちらを直したか分からなくなるのを避ける。`--force` は、作る先そのものを作り直すときだけに効く（今と同じ）。検査は `generator/cli.py` の `_clash`・`refuse_clash` にまとめ、`design.py` からも使う。
- **フック（`generator/guard_hook.py`）の止める範囲は「同じ働きのものを新しい名前でも同じに扱う」だけにした。** 書けるフォルダに `pipe-in-<名前>/` を、置き場所の環境変数に `PIPE_IN_PIPES_DIR` を足した（許す所が増えるので、止める範囲を狭める変更）。理由は、新しく作るパイプと本体が読む置き場所に合わせるため。決まったファイル（`pipe.toml`・`README.md`・`prompts/*.md`）だけ・`..` を断る、は同じ。Bash は `pipe-in-gen` だけを許し、`devpipe-gen` は止める（別名は同じ中身なので、許す形を増やさない）。すり抜けの道（PowerShell・MCP・Agent・Task・Web・記号でつないだコマンドなど）が新旧どちらの名前でも開かないことは `tests/test_guard_hook.py` で確かめた。
- **記録の `driver` は `"pipe-dev"` にし、`--review` は値を見ずに `driver` があれば断る。** 製品名の `pipe-in` と見分けるため。値を並べるより、次に名前が変わっても漏れない。記録のほかの形は変えない（拡張は `driver` を読まない）。
- **古い VSCode のコマンド ID は、パレットに出さずに登録だけ残す。** キー割り当てが壊れない。古い設定 `devpipe.*` は宣言しないまま読む（読めなかったら、手での確認のあとで宣言を足す）。
- **拡張の保存場所（保存した版）は引き継がない。** 拡張の ID が変わると保存場所も変わる。その機能はまだ使われ始めたばかりで、写す手間と危うさに見合わない。版のフォルダは `pipe-in-<名前>/` だけにし、`fsVersions.ts` も古いフォルダ名を受け付けない。
- **拡張の名前と読み替えは `vscode/src/app/names.ts` の表と純粋な関数（`chooseSetting`・`settingKeys`）に置いた。** `extension.ts` は判断を持たず、表を使って新旧のコマンドを登録し、設定を読む。新しい設定を利用者が書いていれば、既定と同じ値でもそちらを使う（同じ側の中は workspaceFolder → workspace → global）。
- **作業台の保存先は、拡張が開いたパイプ（`PipeRef`）から決める。** 前の版のフォルダのパイプは、直して保存しても元のフォルダに書く。新しいパイプは最初の置き場所の `pipe-in-<名前>/`。ほかの置き場所に同じ名前があれば保存を断る（`pipe-in-gen new` と同じ決まり）。パネルから来た値ではフォルダを決めない（パネルには保存先のフォルダ名を見せるためだけに渡す）。

## 対象外・残った課題

- 開発用の名前替え（後半）：`.claude/skills/pipe-in/` → `pipe-dev/`、サブエージェント `pipe-in-*` → `pipe-dev-*`、フック `pipe_in_guard.py` → `pipe_dev_guard.py`、`settings.json`、`CLAUDE.md`・`docs/development/*`・`/pipe-help` の開発用の名前。この回が main に入ってから、別のコミットで行う。それまで、`--review` が断る文の「/pipe-dev」は、実際のスキルの名前（`/pipe-in`）と合わない。
- 古い別名（コマンド `devpipe`・`devpipe-gen`、VSCode の古いコマンド ID）を消すこと（0.4）。
- 古い置き場所のパイプを移すコマンド。PyPI と VSCode の Marketplace への公開。
- GitHub のリポジトリ名の変更（人が行う）。

## 確かめたこと

- テスト先行で、足したテストが期待した理由で落ちることを、失敗の文まで読んで確かめた。
- 実装（Python の側）のあと、`pytest -q` で本体・ジェネレーター・フック・プラグイン・記録のテストが通ることを確かめた。
- 実装（拡張と文書）のあと、`npm --prefix vscode test` で拡張のテストが通ることを確かめた。
- 検証の前に、ほかの機能（判定のスイッチ D0005・ケーブルの動き D0007）が入った main に載せ直し、もう一度流した：`pytest -q` 832 件、`npm --prefix vscode test` 349 件がすべて通り、`npm --prefix vscode run typecheck` は誤り0件、`build` も通った。
- 画面の確認（D0006-AC-27）：`npm --prefix vscode run preview` のページを Playwright で開いた。明るい・暗い・狭い幅（800×700）のどれも、保存先は `pipes/pipe-in-<名前>/` と出て、画面の文字と書き出しの中に古い名前は無く、はみ出しもブラウザのエラーも無かった。
- 手での確認（D0006-AC-28〜30：`.vsix` を入れた拡張・プラグインの登録し直し・リポジトリ名の変更）は、main に入れたあとで人が行う。
