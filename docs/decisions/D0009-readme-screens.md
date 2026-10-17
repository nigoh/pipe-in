# D0009 README を分かりやすく作り直し、動いている画面とロゴを載せる

## 目的

はじめて README を開いた人が、冒頭だけで「何をする道具か・どう見えるか・どう試すか」をつかめるようにする。今ある説明は落とさずに並べ直し、VSCode の拡張の本物の画面（明るい・暗い）とロゴを載せる。

## 機能要件と受け入れ基準

- FR-01 冒頭を「ロゴ → 何をする道具かの一文 → 動いている画面 → 要点 → 目次」の順にする
  - D0009-AC-01 最初の `## ` より前に、ロゴの `<picture>`・パネルの画像の `<picture>`・要点・目次がこの順にある（`tests/test_readme.py::test_d0009_ac01_top_order`）
- FR-02 見出しを「すぐ試す → 使い方 → VSCode の拡張 → パイプ → 安全のしくみ → 記録と使用量 → 設定 → 終了コード → 前の名前から移る → 中身を直したいとき → 注意 → ライセンス」の順にする
  - D0009-AC-02 `## ` の並びが上の順と一致する（`::test_d0009_ac02_section_order`）
  - D0009-AC-03 README の中のアンカーへのリンクが、GitHub と同じ作り方のアンカーのどれかに当たる（`::test_d0009_ac03_no_broken_links`。作り方そのものは `::test_d0009_ac03_github_anchor`・`::test_d0009_ac03_github_anchor_duplicates`・`::test_d0009_ac03_broken_link_finder`）
  - D0009-AC-04 要点と目次から各節へリンクがあり、目次はすべての `## ` を含む。移行の節へは `#migrate`（`::test_d0009_ac04_points_link_to_sections`・`::test_d0009_ac04_toc_lists_all_sections`）
  - D0009-AC-05 ほかの文書が名指ししている見出し（使い方・パイプ・Claude Code のプラグイン・移行の節）が残る（`::test_d0009_ac05_named_headings_exist`）
  - D0009-AC-06 前の名前は移行の節の中だけ（今ある `tests/test_rename.py` が通り続ける）
- FR-03 今の情報を落とさない（長いものは `<details>` にたたむ）
  - D0009-AC-07 前の README のコマンドの行がすべて残る（`::test_d0009_ac07_commands_kept`）
  - D0009-AC-08 前の README の表の項目（終了コード・作られるファイル・access・ひな形・設定の項目・直す場所）が残る（`::test_d0009_ac08_table_items_kept`）
- FR-04 大事な注意を GitHub のアラートで目立たせ、すぐ試すを git clone から最初の実行まで追えるようにする
  - D0009-AC-09 アラートが3つ以上あり、費用は概算・`.pipe-in/` をコミットの前に見る・`--yes` の注意がそれぞれその中にある（`::test_d0009_ac09_alerts`・`::test_d0009_ac09_alert_finder`）
  - D0009-AC-10 すぐ試すに、git clone → venv を作る → Windows と macOS / Linux の入り方 → `pip install -e .` → 最初の `pipe-in --project` がこの順にある（`::test_d0009_ac10_quick_start_order`）
- FR-05 拡張の本物の画面を、明暗の `<picture>` で載せる
  - D0009-AC-11 README の画面の `<picture>` が暗い版と明るい版を持ち、alt が説明になっていて、指す画像4枚が実在する（`::test_d0009_ac11_pictures`）
  - D0009-AC-12 PNG は横 1600px 以下・600KB 以下（`::test_d0009_ac12_png_limits`。読み方は `::test_d0009_ac12_png_size_reader`）
  - D0009-AC-13 `vscode/README.md` にも同じ2つの画面がある（`::test_d0009_ac13_vscode_readme_pictures`）
- FR-06 「実行を見る」パネルの確認用ページを足し、画面用の見本の記録から本物の読み取りと本物の HTML で組み立てる
  - D0009-AC-14 パネルのページは明暗の2つで、本物の CSP を持ち、どの script・style にも nonce があり、段の名前と使用量の節が入り、使う `--vscode-*` の色をすべて決めている（`vscode/src/previewPages.test.ts`）
  - D0009-AC-15 画面用の見本の記録（`tests/fixtures/showcase/`）は今の本体で作り直したものと同じ形で、使用量を持ち、session_id は null、手元の情報が無い（`tests/test_showcase.py`、`vscode/src/previewPages.test.ts`）
  - D0009-AC-16（手で）画像4枚に、手元のパス・ユーザー名・セッション ID が写っていない
- FR-07 CLI の出力を本物どおりのコードブロックで見せ、撮り直しの手順と置き場所をそろえる
  - D0009-AC-17 README の `pipe-in-gen new` / `check` の出力が、tmp で流した本物の出力と一致する（`::test_d0009_ac17_cli_output_matches`）
  - D0009-AC-18 撮り直しの手順（`docs/assets/README.md`）があり、書いたファイルが実在する（`::test_d0009_ac18_retake_doc`）
  - D0009-AC-19 置き場所の表・CLAUDE.md・`/pipe-in` のスキルに、パネルのページが書かれている（`::test_d0009_ac19_docs_mention_panel_pages`）
  - D0009-AC-20 前の版の見本の記録が、今までどおり読める（今ある `tests/test_record.py`・`vscode/src/pipeInRecord.test.ts` が通り続ける）
  - D0009-AC-21（画面）README を開くと、冒頭がロゴ → 一文 → パネルの画像 → 要点 → 目次の順に見え、暗い表示に切り替えるとロゴと画像が暗い版に替わる
  - D0009-AC-22（画面）パネルのページを Playwright で開くと、明暗・狭い幅で崩れず、コンソールのエラーが無い
  - D0009-AC-23（画面）作業台の画像が、手順どおりに撮ったものと同じ
  - D0009-AC-24（手で）`npm run package` が画像のせいで失敗も警告もせず、`.vsix` に画像が入らない
  - D0009-AC-25 `pytest`・`npm test`・`npm run typecheck` が通る

## 決めたことと理由

- **README は1つのまま作り直す。** 開発の決まりで「使い方の説明は README にある」としているため、中身を別の文書へ移さず、並べ替え・言い換え・`<details>` で短く見せる。uv・bat・vhs の README を読み比べ、冒頭に一文と画面、要点から各節へのリンク、すぐ試すを前に、注意はアラート、という共通の形に寄せた。
- **画面は利用料のかからない本物だけ。** パイプ作業台は今ある確認用ページ、「実行を見る」パネルは新しい確認用ページ（`vscode/scripts/previewPages.ts`）から撮る。CLI は画像にせず、コピーできるコードブロックにした。
- **パネルに写す記録は、本物の流れを SDK なしで流した見本にする。** `pipe-in record` の記録には使用量が無いので、テストと同じ差し替えの runner で本物の開発フローを流し、使用量入りの記録を作った（`tests/showcase.py`）。数字は見本なので、画像の説明に「見本の記録（数字は見本）」と書いた。修正の依頼1回と差し戻し1回を入れ、確認・差し戻し・判定・使用量が1枚に写るようにした。
- **見本は `tests/fixtures/showcase/` に置き、テストと確認用ページの両方が読む。** 開発用の台本がテストのデータを読む向きは、`scripts/` が `.vsix` に入らないので受け入れた。形のずれは `tests/test_showcase.py` が、今の本体で作り直したものと比べて見張る。
- **画像は PNG・1280×800・明暗の対。** README からは `<picture>` で切り替える。`vscode/README.md` は `../docs/assets/` の相対パスにした（`npm run package` で警告が出ないことを確かめた）。
- **移行の節へは `<a id="migrate">` でリンクする。** 見出しに前の名前が入るので、アンカーをそのまま使うと前の名前を移行の節の外に書くことになる（`tests/test_rename.py` で落ちる）。
- **会話ごと worktree に移る。** main で始めた会話から worktree で /pipe-in を進めたところ、段のサブエージェントの作業フォルダが main のままで、フックが main を基準に判定し、要件定義の書き込みを止めた。フックが止めた書き込みをメインが代わりにすることはせず、EnterWorktree で会話を worktree に移して解決した。同じことが起きないよう、`/pipe-in` のスキルの「0. 始める前に」に移り方と理由を書いた（助言 V-01・V-02・V-03・V-05・V-06）。
- **監査で見つかった README の食い違いを直した。** 実在しない `feature.sh`・`feature.ps1` の記述を消した（A-01）。サブエージェントは `agents` を書いた段だけで使えること（A-02）、Web はパイプの `web` を書いた段では使えること（A-03）、テストファイルの判定のフォルダと名前（A-04）を本物に合わせた。拡張の開発の手順を `npm ci` にそろえ（A-06）、拡張の README の「プラグイン」を「拡張」にした（A-07）。
- 受け入れたリスク：作業台の画像は全体を縮尺 38% で撮っているので、README の幅ではブロックの文字までは読めない（並びと設定の欄は見える）。パネルの画像は、使用量の表の「合計」の行が下で切れる。

## 対象外・残った課題

- 英語版の README、GIF・動画、SDK を呼んだ実行の画面、撮る作業の自動化（Playwright を依存に足さない）。
- `generator/cli.py` のパイプの名前の文言が「logs は不可」のまま（本物は logs・end が不可。監査 A-05）。このブランチで触っていないコードなので、別の `fix/` ブランチで直す。
- 移ったあとの会話でも、動くフックは会話を始めた場所の版であること（助言 V-04）と、Windows では worktree での「今後は聞かない」が残らないこと（助言 V-07。追跡する設定の allow に何を置くかは人が決める）。
- `/pipe-in` のスキルに前の名前の書き方（前の名前のモジュールを `python -m` で呼ぶ行など）が残っている。名前替えの後半で直す（`tests/test_rename.py` の許す一覧に入っている）。
- 作業台の画像を読める縮尺で撮る・パネルの画像に合計の行まで入れる、の撮り方の見直し。

## 確かめたこと

- 新しいテストは、作る前に期待した理由で落ちた（README・画像・パネルのページがまだ無い）。作ったあと、`pytest` は全件、`npm test` は 357 件が通り、`npm run typecheck` も通った。
- パネルと作業台の確認用ページを、手元だけで配って Playwright で開いた。1280×800 の明暗と、パネルは 800×700 でも崩れず、4ページともコンソールのエラーは0件だった。撮った画像4枚を目で見て、写っているのが相対パスと見本の数字だけであることを確かめた。
- README を GitHub の Markdown の変換で HTML にして開き、冒頭の並びと、暗い表示でロゴと画像が暗い版に替わることを確かめた。目次のリンクで飛ぶことは、手元の静的な表示では見ていない（アンカーの正しさはテストで見ている）。
- `npm run package` は警告なしで終わり、`.vsix` の中身は `package.json`・`readme.md`・`out/` の2つのファイルだけだった。
