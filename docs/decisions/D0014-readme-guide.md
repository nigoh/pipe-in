# D0014 README を入口にし、くわしい説明を docs/guide/ に移す

## 目的

はじめて来た人が README だけで「何をする道具か・どう見えるか・どう試すか・どこを読めばよいか」を短く読めるようにし、くわしい使い方・設定・安全のしくみなどは `docs/guide/` の文書に分けて、読みたい所だけを開けるようにする。今の説明は書き換えずに移すだけにし、情報を落とさない。

**D0009 の「README は1つのまま作り直す（中身を別の文書へ移さない）」を、この記録で置き換える。** D0009 の記録そのものは書き換えない。

## 機能要件と受け入れ基準

テストは、書いていなければ `tests/test_guide.py`（下では `::` からの名前だけを書く）。

- FR-01 README を、冒頭（ロゴ → 一文 → パネルの画像 → 要点 → 目次）・すぐ試す・文書の案内・前の名前から移る人への短い案内・ライセンス、だけにする
  - D0014-AC-01 README の `## ` の見出しが、すぐ試す・文書・前の名前から移る・ライセンス の並びと一致し、目次のリンクがその4つの節のアンカー（移行は `#migrate`）の並び（`::test_D0014_AC_01_READMEの節は決めた4つの並び`・`::test_D0014_AC_01_目次はREADMEの節のアンカーの並び`）
  - D0014-AC-02 最初の `## ` より前に、ロゴ → 一文 → パネルの画像 → ガイドを指す要点 → 目次 がこの順にある（`::test_D0014_AC_02_冒頭はロゴ_一文_パネル_要点_目次の順`）
  - D0014-AC-03 要点は5〜7項目で、どれも実在する `docs/guide/` の文書へのリンクを持つ（`::test_D0014_AC_03_要点は5から7項目でどれもガイドの実在する文書を指す`）
  - D0014-AC-04 README は 120 行以下（`::test_D0014_AC_04_READMEは120行以下`）
  - D0014-AC-05 「すぐ試す」に git clone → venv → 両方の activate → pip install → 最初の `pipe-in --project` の順と、利用料の `> [!IMPORTANT]` がある（`tests/test_readme.py::test_d0009_ac10_quick_start_order`・`::test_D0014_AC_05_すぐ試すに利用料のIMPORTANTのアラートがある`）
  - D0014-AC-06 「文書」の節に、ガイドのすべての文書と `vscode/README.md`・`docs/development/`・`docs/decisions/` へのリンクがある（`::test_D0014_AC_06_文書の節にガイドの全部と拡張_開発のルール_決定の記録へのリンクがある`）
- FR-02 `docs/guide/` を作り、README から外した節を9つの文書（`usage`・`vscode`・`pipes`・`plugin`・`safety`・`records`・`config`・`migrate`・`develop`）に移し、目次 `docs/guide/README.md` を置く
  - D0014-AC-07 決めた10のファイルがあり、どれも1行目が `# ` の見出し（`::test_D0014_AC_07_ガイドの文書がそろい1行目が見出し`）
  - D0014-AC-08 目次からガイドのすべての文書へ行け、`docs/guide/*.md` は決めたものだけ（`::test_D0014_AC_08_目次からガイドの全部の文書へ行けて余分な文書が無い`）
- FR-03 移すときは中身を書き換えず・消さない
  - D0014-AC-09 移す前の README の `## `・`### ` の見出しと `<summary>` が、README かガイドに残る（`::test_D0014_AC_09_前の見出しがREADMEかガイドに残る`・`::test_D0014_AC_09_前のsummaryが残る`）
  - D0014-AC-10 移す前の README のコマンドの行が残る（`::test_D0014_AC_10_前のコマンドがREADMEかガイドに残る`）
  - D0014-AC-11 移す前の README の表の行の頭の項目が、README かガイドの表に残る（`::test_D0014_AC_11_前の表の項目がREADMEかガイドの表に残る`）
  - D0014-AC-12 移す前の README のコードブロックの中の行が、README かガイドのコードブロックにすべて残る（`::test_D0014_AC_12_前のコードブロックの行がREADMEかガイドのコードブロックに残る`・`::test_D0014_AC_12_コードの行の拾い方は字下げした囲みも言語なしも拾う`）
  - D0014-AC-13 アラートが合わせて3つ以上あり、「概算」・「`.pipe-in/` をコミットの前に見る」・「`--yes`」がある（`::test_D0014_AC_13_アラートが3つ以上で概算_pipe_inのコミット_yesがある`）
  - D0014-AC-14 `docs/guide/pipes.md` の `pipe-in-gen new` / `check` の出力の例が、本物の出力と一致する（`::test_D0014_AC_14_パイプの文書のpipe_in_genの出力が本物と一致`）
  - D0014-AC-15（手で）移す前の README と、移したあとの README＋ガイドを見比べ、変わったのが許したもの（見出しの深さ・リンクの行き先・目次と要点の行・各文書の頭の案内文・下の「位置を指す語の4か所」と「監査のあとに直した語」・ガイドの VSCode の文書の頭のパネルの画像）だけ
- FR-04 リンクと画像のパスを、移した先から正しく指すようにする
  - D0014-AC-16 README とガイドの相対リンクが、実在するファイルかフォルダを指す（`::test_D0014_AC_16_17_文書の中のリンクとアンカーが切れていない`）
  - D0014-AC-17 アンカーへのリンクが、行き先の文書の見出しのアンカーか `<a id>` に当たる（同上）
  - D0014-AC-18 リンクの検査そのものが、切れたリンクを見つけ、コードの中は見ない（`::test_D0014_AC_18_リンクの検査そのものが切れたリンクを見つけコードの中は見ない`）
  - D0014-AC-19 README とガイドの `<picture>` は明暗と alt・width を持ち、指すファイルが実在し（ガイドからは `../assets/…`）、パネルと作業台の明暗4枚がどこかで使われる（`::test_D0014_AC_19_READMEとガイドのpictureは明暗とalt_widthがあり実在し4枚を使う`・`::test_D0014_AC_19_ガイドのVSCodeの文書に作業台の明暗の画像がある`）
  - D0014-AC-20 `vscode/README.md` の画像は今までどおりで、移行へのリンクは `../docs/guide/migrate.md` を指す（`tests/test_readme.py::test_d0009_ac13_vscode_readme_pictures`・`::test_D0014_AC_20_拡張のREADMEの移行へのリンクはガイドを指す`）
- FR-05 README の節を名指ししている所（決定の記録を除く）を、移した先を指すように直す
  - D0014-AC-21 名指しの言い方が残らず、直したファイルが実在する `docs/guide/…` を書いている（`::test_D0014_AC_21_READMEの節を名指しする言い方が残っていない`・`::test_D0014_AC_21_名指しを直したファイルはガイドを書きそのパスが実在する`・`::test_D0014_AC_21_検査そのものが名指しを見つける`）
  - D0014-AC-22 `/pipe-help` の「答え方」と「もっと詳しく」が `docs/guide/` を案内する（`::test_D0014_AC_22_pipe_helpの答え方ともっと詳しくがガイドを案内する`）
  - D0014-AC-23 `docs/development/workflow.md` の「そろえる」の表の使い方の行に `docs/guide/` がある（`::test_D0014_AC_23_そろえる表の使い方の行にガイドがある`）
  - D0014-AC-24 `docs/development/design.md` の置き場所の表に `docs/guide/` の行があり、パスが実在する（`::test_D0014_AC_24_置き場所の表にガイドの行がある`・`tests/test_rules.py::test_place_tables_point_to_real_paths`）
  - D0014-AC-25 監査（`pipe-in-auditor`）の対象に `docs/guide/` がある（`::test_D0014_AC_25_監査の対象にガイドがある`）
  - D0014-AC-26（手で）D0001〜D0012 の記録の中身は変わらない（`git diff main --stat -- docs/decisions/` で、変わったのがこの記録と索引の1行だけ）
- FR-06 前の版の README の `#migrate` へのリンクで来た人が、移した先へ行けるようにする
  - D0014-AC-27 README に `<a id="migrate"></a>` が残り、その直後の前の名前から移る節に `docs/guide/migrate.md` へのリンクがある（`::test_D0014_AC_27_READMEの移行の節の直前にmigrateのアンカーがありガイドを指す`）
  - D0014-AC-28 前の名前は、README では移行の節の中、ガイドでは `docs/guide/migrate.md` の中にしか出ない（`tests/test_rename.py::test_old_name_only_in_allowed_files`・`tests/test_rename.py::test_readme_old_name_only_in_migration_section`）
  - D0014-AC-29 拡張の古い呼び名の検査が `docs/guide/` の文書も見る（`vscode/src/manifest.test.ts` の `AC-57・D0014-AC-29: …`）
- FR-07 README の形を固めていたテスト（D0009・D0012・D0006 のもの）を、新しい形に合わせて直す
  - D0014-AC-30 D0012 の呼び方の2行と説明が `docs/guide/develop.md` の「Claude Code で開発するとき」にあり、`/pipe-help` のものと空白をそろえて同じ。呼び方の行は `/pipe-help` とその文書の2か所だけ（`tests/test_headless_audit.py` の `test_D0014_AC_30_…` の3つと、見る文書を変えた D0012 のテスト）
- FR-08 この決定の記録を書き、索引と置き場所の表を直す
  - D0014-AC-31 この記録があり、索引に行があり、D0009 を置き換えることと変えたテストのファイルが書いてある（`::test_D0014_AC_31_決定の記録D0014があり索引に行がありD0009を置き換えると書く`）
  - D0014-AC-32（画面）README を Markdown の表示で開くと、冒頭がロゴ → 一文 → パネルの画像 → 要点 → 目次の順に見え、リンクでガイドの文書が開き、暗い表示でロゴと画像が暗い版になる
  - D0014-AC-33（画面）`docs/guide/vscode.md` を開くと、パネルと作業台の画像が明るい版・暗い版とも出る
  - D0014-AC-34 `pytest -q`・`npm test`・`npm run typecheck` が通る

## 決めたことと理由

- **README は入口だけ（120 行まで）。** 冒頭・すぐ試す・文書の案内・移行の短い案内・ライセンス。使い方の例や拡張の入れ方も残す案（200 行）は、ガイドと重なるので選ばなかった。すぐ試すまで削る案は、GitHub で最初に読む所から試し方が消えるので選ばなかった。
- **置き場所は `docs/guide/`。** `docs/development/`（開発のルール）・`docs/decisions/` と並び、利用者向けと分かる。`docs/` の直下に並べると `docs/roadmap.md` などと混ざる。
- **9つの文書と目次。** CLAUDE.md とプラグインのスキルが名指しする「プラグイン」と「移行」は単独の文書にした。「中身を直したいとき」と「Claude Code で開発するとき」は開発する人向けなので `docs/guide/develop.md`（題は「pipe-in を開発する」）にまとめた。`docs/development/` はルールの文書なので置かない。
- **中身は書き換えずに移す。** 変えたのは、見出しの深さ・リンクの行き先・目次と要点の行・各文書の頭の案内文と、次の「位置を指す語」の4か所だけ。コードブロックの中は1文字も変えない。
- **位置を指す語の4か所。** 移すと前の README の中の位置を指していた語がうそになるので、ここだけ直した。
  - 「…パネルが開きます（冒頭の画像）。」：文は変えず、`docs/guide/vscode.md` の頭に README と同じパネルの画像を写した（その文書の冒頭の画像になる）。
  - パイプの節の「（下の「Claude Code のプラグイン」）」：「下の」を消し、行き先を `plugin.md` にした。
  - ひな形の表の `dev` の行の「上の開発フローそのもの。」：「開発フロー（`usage.md#開発フローの流れ` へのリンク）そのもの。」にした。
  - 設定の「見本はこのフォルダの `pipeline.toml` です。」：「見本はリポジトリの直下の `pipeline.toml`（`../../pipeline.toml` へのリンク）です。」にした。
  - 同じ文書の中で「下の」「上の」と言っている所（pipe.toml の例の「下の表」、「下の「Agent SDK の設定」」、「下の見分け方」）は、移したあとも同じ文書の下にあるので変えていない。
- **監査のあとに直した語。** 移したあとにうそになる語が、監査で2つ見つかったので直した。
  - README と `docs/guide/pipes.md` の「[移行の節](…)」：移行は1つの文書になったので、リンクの文字を「前の名前から移る」にした（監査 A-03）。
  - `docs/guide/develop.md` の「README の画像の撮り直し方は」：作業台の画像はガイドにだけあるので、「README とガイドの画像の撮り直し方は」にした（監査 A-04。`CLAUDE.md`・`docs/development/design.md`・`docs/assets/README.md` の言い方にそろえた）。
- **README に残す古いアンカーは `#migrate` だけ。** `vscode/README.md`・`pipes/README.md`・前の版の案内が指していたため。ほかの節（使い方・安全のしくみなど）のアンカーは無くなるが、README の「文書」の節で行き先が分かるので、空の見出しは残さない。
- **`pipe-in-gen new --from dev` が書くパイプの README の1文を直した。** `generator/templates/dev/README.md` の「pipe-in の README の『使い方』」を「pipe-in のリポジトリの `docs/guide/usage.md`」にした。README から「使い方」が無くなるので、直さないとうそになる。利用者のプロジェクトに写されるので、リンクにせずパスで書いた。前に作ったパイプは変わらない。
- **プラグインのスキルは、ガイドを「人が読む場所」として URL で書く。** プラグインとして写されるのは `plugin/` の中だけで、`docs/guide/` は入らない。利用者のプロジェクトでは Claude がそのパスを開けないので（助言 V-02）、`plugin/skills/pipe-build/SKILL.md` では、Claude が確かめるのは `pipe-in-gen --help` だけにし、`docs/guide/pipes.md` は公開リポジトリの URL で人に案内する。同じ理由で、入れ方の「pipe-in のリポジトリで `pip install -e .`」も、`git clone` の URL を書いた形にした（助言 V-03）。説明をスキルの補助ファイルに写す案は、`docs/guide/pipes.md` と二重に持つことになるので選ばなかった。
- **名指しの直し。** `CLAUDE.md`・`docs/development/workflow.md`・`docs/development/README.md`（言葉だけ）・`docs/development/design.md`（画像の言い方と置き場所の表の1行）・`docs/assets/README.md`・`vscode/README.md`・`pipes/README.md`・`plugin/skills/pipe-build/SKILL.md`・`generator/templates/dev/README.md` を直した。`.claude/` の中（`pipe-help`・`pipe-in-auditor`・`pipe-in-coder`・`pipe-in-analyst`）は、実装の段のサブエージェントが書けない（フックが止める）ので、メインが直す。
- **英語版は作らない。** 作るなら別の機能で、日本語版を元にする。
- **依存は足さない。** Markdown の変換の部品も入れない。リンク・アンカー・画像の検査は、`tests/test_readme.py` の補助（GitHub と同じアンカーの作り方）をそのまま使った。

### テストの直し方（D0009・D0012・D0006・拡張）

「中身を書き換えない」は、見出し・コマンド・表の項目・コードブロックの行をテストで固め、本文の文は人が差分で見る（AC-15）。本文まで固める案（前の README を `tests/fixtures/` に写して全行を突き合わせる）は、写しに前の名前が入って `tests/test_rename.py` の一覧が増え、リンクを直した行の扱いも要るので選ばなかった。

`tests/test_readme.py`（D0009）：形が変わるものを消して、`tests/test_guide.py` の D0014 のテストに置き換えた。補助の関数は残し、`test_guide.py` が import して使う。

| 消したテスト | 置き換えた先 | 理由 |
| --- | --- | --- |
| `test_d0009_ac01_top_order` | `test_D0014_AC_02_…` | 要点のリンクが README の中ではなくガイドを指すようになり、形が変わる |
| `test_d0009_ac02_section_order` | `test_D0014_AC_01_…` | 節が12から4に変わる |
| `test_d0009_ac03_no_broken_links` | `test_D0014_AC_16_17_…` | README の中だけでなく、文書をまたいで見る必要がある |
| `test_d0009_ac04_points_link_to_sections` | `test_D0014_AC_03_…` | 要点のリンクの行き先が変わる |
| `test_d0009_ac04_toc_lists_all_sections` | `test_D0014_AC_01_目次…`・`test_D0014_AC_27_…` | 目次の中身が変わる |
| `test_d0009_ac05_named_headings_exist` | `test_D0014_AC_09_…`・`test_D0014_AC_21_…` | 名指しされる見出しが README から出ていく |
| `test_d0009_ac07_commands_kept` | `test_D0014_AC_10_…`（一覧は移した） | README だけでなく README とガイドを見る |
| `test_d0009_ac08_table_items_kept` | `test_D0014_AC_11_…`（一覧は移した） | 同上 |
| `test_d0009_ac09_alerts` | `test_D0014_AC_13_…` | 同上 |
| `test_d0009_ac11_pictures` | `test_D0014_AC_19_…` | 作業台の画像が README から出ていく |
| `test_d0009_ac17_cli_output_matches` | `test_D0014_AC_14_…` | 出力の例が `docs/guide/pipes.md` に移る |

残したもの：アンカーの作り方（`test_d0009_ac03_github_anchor`・`…_duplicates`・`…_broken_link_finder`）、アラートの見つけ方（`test_d0009_ac09_alert_finder`）、すぐ試すの順（`test_d0009_ac10_quick_start_order`。README に残るので今のまま通る）、PNG の上限（`ac12` の2つ）、拡張の README の画像（`ac13`）、撮り直しの手順（`ac18`）、置き場所の表と CLAUDE.md（`ac19`）。どれも今も成り立つ。

`tests/test_headless_audit.py`（D0012）：見る文書を README から `docs/guide/develop.md` に変えた。D0012 の AC は「README」を名指ししていたので、D0014-AC-30 として付け直した。

- 消した：`test_readmeに会話を開かない呼び方の例がある`・`test_readmeとpipe_helpの呼び方が空白をそろえて同じ`（README にはもう呼び方が無いため）。
- 足した：`test_D0014_AC_30_ガイドの開発の文書に会話を開かない呼び方の例がある`・`test_D0014_AC_30_ガイドとpipe_helpの呼び方が空白をそろえて同じ`・`test_D0014_AC_30_呼び方の行はpipe_helpと開発の文書の2か所だけ`。
- 見る文書を変えた：付けないオプション・読むだけ・説明・見分け方の D0012 のテスト（中身の検査は同じ）。

`tests/test_rename.py`（D0006）：前の名前が出てよいファイルの一覧に `docs/guide/migrate.md` を足し、`README.md` の理由を「短い案内」にした。README の節の中だけに絞る検査は今のまま。

`vscode/src/manifest.test.ts`：古い呼び名の検査に `docs/guide/*.md` を足し、10個あることも確かめるようにした。

### 監査と助言で直したこと

検証で合格したあと、矛盾監査（A-01〜04）と公式の文書と照らした助言（V-01〜05）を流し、人が承認したものを全部直した（V-05 は「今のままでよい」なので直す所なし）。

- A-01：`tests/test_headless_audit.py` の D0012 のテストの説明の「pipe-help と README に1か所ずつ」を「pipe-help と docs/guide/develop.md に1か所ずつ」にした（説明の文だけ。検査は変えていない）。
- A-02：`docs/development/design.md` の動画の見本の行の「`--pipes-dir examples/video/pipes` で流す」は、`pipe-in` に無いオプションだった（この変更より前からの食い違い。D0011 の記録と合わせた）。`pipe-in --pipe examples/video/pipes/pipe-in-video` で流し、`pipe-in-gen check video --pipes-dir examples/video/pipes` で確かめる、と書き直した。
- A-03・A-04：上の「監査のあとに直した語」。
- V-01：`pipe-in-analyst` の description に書いていた「`docs/guide/` を読み」は、サブエージェント自身には渡らない（description は親が任せる先を決めるための文）。読む文書は本文に書き、description は受け持つ段と呼ばれる条件だけにした。
- V-02・V-03：上の「プラグインのスキルは…」。
- V-04：`/pipe-help` の「もっと詳しく」で `docs/guide/pipes.md` が2回出ていたので、プラグインの行を `docs/guide/plugin.md` だけにした。

### main に合わせたこと

- 作業のあいだに main へ、プラグのロゴの動き（D0013）と動画のパイプの直しが入った。決定の記録の番号がぶつかったので、この記録と AC の ID・テストの名前を D0013 から D0014 に振り直した。
- `docs/development/design.md` の置き場所の表の `docs/assets/` の行は、main の「ロゴの動き（HTML と GIF）」と、この記録の「README とガイドの画像」を合わせた。

## 対象外・残った課題

- 説明の中身を書き直す・言い換える・短くする・古い記述を消すこと（今回は移すだけ）。
- 英語版の README・ガイド。
- `vscode/README.md` と `docs/guide/vscode.md` の重なりを1つにまとめること（今回は移すだけなので重なりは残る）。
- `pipes/README.md`・`examples/` の README・`docs/development/` の文書の中身の作り直し（名指しの直しだけをした）。
- 文書のサイト（MkDocs など）を作ること・依存を足すこと。
- 過去の決定の記録（D0001〜D0012）を書き換えること。`examples/video/pipe-in-intro-script.md` の README への言及（台本を作ったときの事実）と、`tests/showcase.py` の説明（README の画像はまだ README にある）は直していない。

## 確かめたこと

- テストは、足したものが期待した理由（ガイドが無い・README がまだ 618 行・名指しが古い・この記録が無い）で落ちることを確かめてから実装した。
- 検証の段：`python -m pytest -q` は 1482 件、`npm --prefix vscode test` は 357 件がすべて通った。`npm --prefix vscode run typecheck` はエラー 0（拡張の製品コードは変えていない。変えたのはテストの `manifest.test.ts` だけ）。監査と助言で直したあとにも流し直した。
- AC-15（手で）：合格。前の README と、今の README・ガイド10文書を節ごとに見比べ、変わったのが許したものだけであることを確かめた。
- AC-26（手で）：合格。`docs/decisions/` で変わったのはこの記録と索引の1行だけ。
- AC-32・AC-33（画面）：まだ（VSCode の Markdown のプレビューで人が見る。リンク・アンカー・画像のパスはテストで確かめている）。
