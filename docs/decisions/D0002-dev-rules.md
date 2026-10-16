# D0002 開発のルール（docs/development/）と、それを守らせるテスト

## 目的

これから devpipe を直す・機能を足す人と Claude Code が、同じ原則・仕様の書き方・設計とテストの決まり・進め方に従えるようにする。検査できる決まりはテストにして、文書だけに頼らない。

## 機能要件と受け入れ基準

- FR-01 開発のルールを `docs/development/`（原則・仕様・設計・テスト・進め方）に置き、`CLAUDE.md` は要約と案内にする。`/pipe-in` はそこに従う
  - D0002-AC-06 文書がそろっていて、`CLAUDE.md` と `/pipe-in` から案内がある（`tests/test_rules.py::test_development_docs_exist`）
- FR-02 追跡しているファイルに、手元の事情と秘密のファイルを載せない
  - D0002-AC-01 ユーザー名の入ったパス・メールアドレス（決まったものを除く）・秘密のファイルが無い。見つけ方そのものも確かめる（`test_local_info_pattern`・`test_no_local_info_in_tracked_files`）
- FR-03 機能ごとの決定の記録を `docs/decisions/` に置き、AC の ID を `Dnnnn-AC-xx` にする
  - D0002-AC-02 記録の名前・番号・見出しの形（`test_decision_records_have_sections`）
  - D0002-AC-03 テストに出てくる `Dnnnn-AC-xx` が記録にある（`test_ac_ids_in_tests_exist_in_records`）
- FR-04 置き場所の表と実物を食い違わせない
  - D0002-AC-04 `CLAUDE.md` と `docs/development/design.md` の表のパスが実際にある（`test_table_paths_pattern`・`test_place_tables_point_to_real_paths`）
- FR-05 テストがリポジトリの実物を変えたら、テストが通っていても失敗にする
  - D0002-AC-05 `pipes/`・`.devpipe/`・`docs/pipeline/` の足し・消し・変更に気づく（`test_watch_detects_changes`・`test_watched_dirs`）
- FR-06 拡張の層ごとに使ってよい部品を決めて検査する
  - D0002-AC-07 domain・app は `node:path`、view・webview はなし、infra は `node:fs`・`node:os`・`node:path` だけ。検査そのものも確かめる（`vscode/src/architecture.test.ts`）

## 決めたことと理由

- **ルールは `docs/development/` に分け、`CLAUDE.md` には必ず守ることと案内だけを置く。** 毎回の会話で読まれる量を抑え、人にも読める文書にするため。拡張の層の表は `vscode/README.md` から `design.md` に移した（1つの知識は1か所）。
- **追跡して残すのは決定の記録だけ。** 段の文書を丸ごと残すと古くなりやすく、整える手間がかかる。あとから読む人が知りたいのは「何を、なぜ決めたか」なので、そこだけを残す。
- **段の成果物（`docs/pipeline/`）は、手元の作業の記録として扱う。** このルールを書いているあいだに、/pipe-in が段をサブエージェントに任せ、`devpipe record` で `docs/pipeline/` に段の文書と記録を書く形に変わった（49041c0）。段から段への受け渡しと VSCode で見るためにはファイルが要るので、書くこと自体は認め、追跡しない（`.gitignore` 済み）・決定の記録に中身をそのまま貼らない、という決まりにした。
- **AC の ID は記録の番号を頭に付ける（`Dnnnn-AC-xx`）。** 機能ごとに `AC-01` から振ると、テストの名前で番号が重なり、仕様をたどれなかったため。前からあるテストの番号は付け直さない（手間に比べて得るものが少ない）。
- **守らせ方はテストまで。CI（GitHub Actions）は足さない**（人の判断）。そのため、手元でテストを流すことが前提になる。
- **見張りは pytest のセッションの始めと終わりで、ファイルの大きさと更新の時刻を比べる。** 中身の比較より軽く、テストが書いたことには十分気づける。拡張のテストは `mkdtemp` の中だけに書いているので、見張りは Python だけにした。
- **機能ごとにブランチと worktree を切る。** 前の作業で、並行していた会話の変更が1つのコミットに混ざったため。このルール自体も `docs/dev-rules` のブランチで作り、並行していた /pipe-in の作り直し（49041c0）がコミットされてから、その上に載せ直した。
- 手元の事情の検査で、コミットの共著者の書き方（`noreply@anthropic.com`）と見本のドメイン（`example.com` など）のメールアドレスは許す。

## 対象外・残った課題

- CI（GitHub Actions）での実行。
- 前からあるテストの `AC-xx` を `Dnnnn-AC-xx` に付け直すこと。
- 守る範囲を狭める変更に「理由をコミットに書く」ことの検査（テストでは確かめられない）。

## 確かめたこと

- `tests/test_rules.py` は、文書と記録を書く前に、無いものの数だけ期待どおりに落ちた。手元の情報の検査と、`CLAUDE.md` の表の検査は、はじめから通った（今のリポジトリが決まりを守っている）。
- 拡張の層の検査は、今のコードが決まりを守っているので、はじめから通った。わざと違反を並べた見本で、検査が違反を見つけることを確かめた。
- 見張りは、わざとリポジトリの `pipes/` に書く使い捨てのテストで、テストが通っても終了コード 1 になり、変えたファイルの名前が出ることを確かめた（確かめたあと、テストと作ったフォルダは消した）。
