# D0001 パイプを会話で作る・直すプラグイン（/devpipe:pipe-build と pipe-builder）と、対象の .devpipe/pipes/

## 目的

devpipe の利用者が、自分のプロジェクトで Claude Code に話しかけるだけでパイプを作る・直せるようにする。手を動かすエージェントが書けるのは、パイプのフォルダの中だけに仕組みで絞る。

## 機能要件と受け入れ基準

この記録は、機能を作ったあとに D0002 の決まりで書いた。テストの名前（docstring・見出しのコメント）は `D0001-AC-xx` に付け直してある。ただし `vscode/src/app/pipeEditor.test.ts` の D0001-AC-17 のテストは、並行していた作業がそのファイルを直している途中だったため、名前を `AC-17` のままにしてある。

- FR-01〜03 リポジトリをプラグインのマーケットプレイス（`.claude-plugin/marketplace.json` → `plugin/`）にし、スキル `pipe-build`・エージェント `pipe-builder`・フックを配る。`/pipe-craft` は消す
  - D0001-AC-01 マーケットプレイスとプラグインの名前と置き場所（`tests/test_plugin.py::test_marketplace_points_to_plugin`）
  - D0001-AC-02 スキルの frontmatter と節（`test_skill_frontmatter_and_sections`）
  - D0001-AC-03 エージェントの道具がちょうど Read・Glob・Grep・Write・Edit・Bash で、プラグインでは無視される項目を書いていない（`test_agent_tools_and_ignored_fields`）
  - D0001-AC-04 フックが `devpipe-gen guard-hook` をシェルなしで呼ぶ（`test_hooks_call_guard_hook_without_shell`）
  - D0001-AC-05 `/pipe-craft` が残っていない（`test_pipe_craft_is_gone`）
- FR-12・13 フックは pipe-builder の呼び出しだけを検査し、許すものの一覧で絞る
  - D0001-AC-06 ほかのエージェントには何もしない（`tests/test_guard_hook.py::test_other_agents_pass`）
  - D0001-AC-07 パイプのフォルダの `pipe.toml`・`README.md`・`prompts/*.md` には書ける。`agent_type` が `devpipe:pipe-builder` でも `pipe-builder` でも（`test_builder_can_write_pipe_files`）
  - D0001-AC-08 それ以外の場所・`layout.json`・`..` は止める（`test_builder_cannot_write_outside`）
  - D0001-AC-09 Bash は `devpipe-gen list / new / check` の1つのコマンドだけ。記号・`--force`・`design` は止める（`test_builder_bash_*`）
  - D0001-AC-10 PowerShell・NotebookEdit・Web・MCP・Agent は止める（`test_builder_other_tools_denied`）
  - D0001-AC-11 `DEVPIPE_PIPES_DIR` の下にも書ける（`test_builder_can_write_env_pipes_dir`）
  - D0001-AC-12 読めない入力は止める（`test_broken_json_denies`）
- FR-14〜16 パイプは対象の `.devpipe/pipes/` に作り、対象 → 今までの場所の順に探す。作図台も同じ
  - D0001-AC-13 探す順番（`tests/test_pipe.py::test_find_pipe_prefers_project_pipes`・`test_find_pipe_explicit_dir_only`）
  - D0001-AC-14 `devpipe --pipe` が対象から読む（`tests/test_pipe_flow.py::test_cli_loads_pipe_from_project`）
  - D0001-AC-15 作る場所は `--pipes-dir` → `DEVPIPE_PIPES_DIR` → 対象の `.devpipe/pipes/`（`test_new_pipes_dir_order`・`test_new_defaults_to_project_pipes`・`test_new_respects_pipes_dir_and_env`）
  - D0001-AC-16 `devpipe-gen list --project` が両方の場所を出す（`test_list_shows_project_and_shared_pipes`）
  - D0001-AC-17 作図台の置き場所の決め方（`vscode/src/app/pipeEditor.test.ts`）
  - D0001-AC-18 どこを根にしても、決まったファイルだけを読み書きする（`vscode/src/infra/fsPipes.test.ts`）
- FR-12 フックは標準ライブラリだけで書く
  - D0001-AC-19 （`tests/test_architecture.py::test_guard_hook_uses_only_stdlib`）
  - D0001-AC-20（手で）Git Bash と PowerShell から `devpipe-gen guard-hook` を呼んで、テストと同じ結果になる
  - D0001-AC-21（実機）プラグインを入れて pipe-builder を呼び、`agent_type` の実際の値と、外への Write が止まることを確かめる

## 決めたことと理由

- **止める仕組みは、プラグインの `hooks/hooks.json` の PreToolUse に置き、`agent_type` で pipe-builder を見分ける。** プラグインのエージェントの定義では `hooks`・`permissionMode`・`mcpServers` が黙って無視されるため、エージェントの定義には書けない。
- **フックの本体は Python のスクリプトではなく `devpipe-gen guard-hook` にした。** `python` / `python3` の呼び名の違いに左右されず、テストしやすい。シェルを通さない形（`command` と `args`）で呼ぶので、Git Bash と PowerShell の違いも受けない。
- **`agent_type` は `pipe-builder` と `*:pipe-builder` の両方に合わせる。** プラグインのエージェントの名前が `devpipe:pipe-builder` になることは文書から推せるが、フックに渡る値の形は文書で確かめられなかったため。
- **受け入れたリスク：`devpipe-gen` が無い環境では、フックが失敗して素通りになる。** Claude Code は、失敗したフックを「止めない」として扱う。スキルがはじめに `devpipe-gen` を確かめて止まることで補う。
- **受け入れたリスク：フックはどの道具の呼び出しでも動き、手元の Windows で1回あたり約0.5秒かかる**（ほとんどは Python を起こす時間）。減らすには Node など別の形にする必要があり、今回はしない。
- pipe-builder には `layout.json`（作図台の配置）を触らせない。段の名前を変えると配置は古くなるが、作図台が開き直したときに並べ直す。
- 作る場所は、明示された指定（`--pipes-dir`・`DEVPIPE_PIPES_DIR`）を、対象の `.devpipe/pipes/` より優先する。
- 前の版で `pipes/` に作ったパイプも流せるように、探すときは今までの場所も見る。作図台も、`.devpipe/pipes` が無くて `pipes` があれば、そちらを開く。

## 対象外・残った課題

- 作図台から pipe-builder を呼ぶ連携。
- `.claude/settings.json` の `extraKnownMarketplaces` で、このリポジトリを開いた人にプラグインを勧める設定（ローカルのフォルダを指す書き方を、文書で確かめられなかった）。
- シンボリックリンクを通した書き込み（pipe-builder は Bash が `devpipe-gen` に絞られていて、自分でリンクを作れないため）。
- D0001-AC-21 の実機の確認。

## 確かめたこと

- テスト：Python 416件・拡張 211件がすべて通った。型検査とビルドも通った。
- D0001-AC-20：手元の Windows で、作業用の venv に `pip install --no-deps -e .` で入れ、Git Bash と PowerShell の両方から呼んだ。外への Write・`;` でつないだ Bash・PowerShell では deny の JSON が出て、パイプのファイルへの Write とほかのエージェントの呼び出しでは何も出なかった。日本語の入ったパスも読めた。
- D0001-AC-21：**まだ**（プラグインを入れると Claude Code と Python の手元の設定が変わるため、人に言われてから行う）。
- 作業の途中で、テストが本物の `pipes/` にパイプを作ってしまった。消してから、テストが今までの場所を仮のフォルダに向けるようにした（この反省から D0002 で見張りを足した）。
