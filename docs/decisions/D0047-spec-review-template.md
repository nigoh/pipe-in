# D0047 仕様書レビューのパイプのひな形 `spec-review` を足す（素人の質問 → 知識の下ごしらえ → 6つの検査を同時に → 根拠の確認 → まとめと質問票）

## 目的

受け取った仕様書・要求書を、役割を分けたエージェントでレビューし、顧客への質問票まで出せるようにする。新規参入の業界でも、知識の下ごしらえと比べる基準を渡して網羅を拾い、指摘は D0043 の形 v1 で受け渡して、引用と出典を機械で確かめる。

## 機能要件と受け入れ基準

テストは `tests/test_template_spec_review.py`（下では `::` からの名前だけを書く）。

- FR-01 公開のひな形 `generator/templates/spec-review/`（`pipe.toml`・`README.md`・`prompts/` の10個）を足す。`pipe-in-gen list` に出て、`pipe-in-gen new <名前> --from spec-review` で写せる。
  - D0047-AC-01 ひな形のファイルがあり、`list` に `spec-review` が出る（`::test_d0047_ac01_template_files_exist`・`::test_d0047_ac01_list_shows_spec_review`）
  - D0047-AC-02 `new` と `check` が終了コード 0 で、警告が 0 件。写したパイプに `{{` と前の名前が残らない（`::test_d0047_ac02_new_and_check_pass_without_warnings`・`::test_d0047_ac02_no_placeholder_or_old_name_left`）
- FR-02 段は `naive`（素人の質問）・`knowledge`（知識の下ごしらえ）・`quality`・`gap`・`user`・`tester`・`designer`・`operations`（品質・網羅・視点別4つ）・`verify`（根拠の確認）・`report`（まとめと質問票）の10段をこの順に置く。
  - D0047-AC-03 段の名前と成果物の名前の並び（`::test_d0047_ac03_stage_names_and_outputs`）
  - D0047-AC-04 `access` は `knowledge` と `report` が `docs`、ほかが `read`。どの段も Bash・Web・MCP・サブエージェントを使えない（`::test_d0047_ac04_access_and_tools`）
- FR-03 人の確認は `knowledge` と `report` だけ。検査の6段は同じ group（`inspect`）で同時に流す。
  - D0047-AC-05 `review` と `group` の置き方（`::test_d0047_ac05_review_and_group`）
- FR-04 モデルは `naive` と検査の6段が `haiku`、`knowledge`・`verify`・`report` が `sonnet`。
  - D0047-AC-06 段ごとの `model`（`::test_d0047_ac06_models`）
- FR-05・06 仕様書は対象の `docs/spec-review/spec.md`（Markdown 1ファイル。台帳では `SRC-001`）。指摘は各段が自分の成果物（`.json`）として書き、ガードは広げない。
  - D0047-AC-07 書ける範囲が、自分の成果物と決まった置き場（`docs/spec-review/knowledge/`・`docs/spec-review/out/`）を超えず、仕様書にも届かない（`::test_d0047_ac07_read_stages_write_only_own_output`・`::test_d0047_ac07_knowledge_write_scope` ほか）
- FR-07 `verify` の確認は `pipe-in-gen findings-check` で、不合格なら自分を2回までやり直す。
  - D0047-AC-08 `verify` の `check` の欄（`::test_d0047_ac08_verify_check_fields`）
  - D0047-AC-09 その `command` を一時フォルダの見本で流すと、正しい指摘で 0、引用の誤りで 1（`::test_d0047_ac09_findings_command_passes`・`::test_d0047_ac09_findings_command_fails_on_bad_quote` ほか）
- FR-08・09 `report` の確認は、質問票 `questionnaire.csv`（UTF-8・BOM 付き）の見出しが8列（指摘ID・重大度・質問・回答の型・選択肢・場所・引用・回答）であることを、ASCII だけの `python -c` で見る。
  - D0047-AC-10 `report` の `command` が ASCII だけで、8列なら通る（`::test_d0047_ac10_report_command_is_ascii_python`・`::test_d0047_ac10_report_command_passes_with_8_columns` ほか）
  - D0047-AC-11 引用符を使うコマンドは、外側が `"`・中が `'` で、cmd.exe と sh の両方で崩れない（`::test_d0047_ac11_commands_are_quote_safe`）
- FR-10 指示文に、D0043 の形 v1 の決まりを入れる。指摘を書く8段は、同じ文の節「指摘の形（v1）」を持つ。
  - D0047-AC-12 8段の指示文に形 v1 の決まりがあり、共通の節が一字一句同じ（`::test_d0047_ac12_common_section_is_identical` ほか）
  - D0047-AC-13 `naive` は仕様書だけを読み、`SRC-001` だけを使い、知識の置き場を読まない（`::test_d0047_ac13_naive_prompt`）
  - D0047-AC-14 視点別4段と品質・網羅の段の `role`・`perspective`（`::test_d0047_ac14_perspective_prompts`・`::test_d0047_ac14_quality_and_gap_roles`）
  - D0047-AC-15 `knowledge` は用語集・ドメインモデル・論点・台帳の4つを書き、`SRC-001` を仕様書にする（`::test_d0047_ac15_knowledge_prompt`）
  - D0047-AC-16 `verify` は確認の判定を書き、`F-001` から振り直す（`::test_d0047_ac16_verify_prompt`）
  - D0047-AC-17 `report` の質問票の見出しが、`command` の見る8列と同じ（`::test_d0047_ac17_report_prompt_headers_match_command`）
  - D0047-AC-18 指示文に埋め残し・絶対パス・業界や会社の名前が無い（`::test_d0047_ac18_prompts_have_no_placeholders_paths_or_bad_words`）
- FR-11・12 README に、段の表・仕様書の置き場所・流し方・成果物の置き場所・役割の入れ外し（段の塊を消す。`naive` と検査の6段は消せ、`knowledge`・`verify`・`report` は消せない）・素人質問者の注意・費用を書く。
  - D0047-AC-19 README の項目（`::test_d0047_ac19_readme_has_required_items`）
  - D0047-AC-20 README の手順で段を消した `pipe.toml` も `check` を通る（`::test_d0047_ac20_remove_naive_still_checks` ほか）
- FR-13 本体・ガード・`render.py`・既存のひな形は変えない。
  - D0047-AC-21 既存のひな形は変わらない（`tests/test_generator.py`・`tests/test_pipe_lint.py` の既存のテスト）
  - D0047-AC-22 前の版の置き場所・写したパイプの読み方は変わらない（`::test_d0047_ac22_new_refuses_old_place_name`・`::test_d0047_ac22_readme_mentions_old_copies_and_old_gen`）
  - D0047-AC-23 `pipe_in/`・`render.py`・ガードに差分が無く、依存も増えない（`tests/test_architecture.py`。検証の段で `git diff` も見た）
  - D0047-AC-24（実機）本物の SDK で10段を通して流し、`09_findings.json` が `findings-check` を通り、質問票ができる
  - D0047-AC-25（実機）`naive` が知識の置き場を読まない
  - D0047-AC-26（実機）検査の6段が同時に流れ、段ごとの費用が記録に残る
  - D0047-AC-27（手で）質問票を Excel で開くと、日本語の見出しが文字化けせず8列に分かれる
  - D0047-AC-28（画面）（手で）VSCode の拡張で、10段と group の枠と `.json` の成果物が見える

## 決めたことと理由

- 前提（決定のページで決めたこと）：まず自分が職場の案件で使う。役割は2つの設計資料の7役割をすべて作る。作る場所は pipe-in のパイプ。
- 公開のひな形にした。指示文には特定の業界・会社の知識を入れず、知識は対象ごとに `knowledge` の段が顧客の資料から作る（ペルソナで専門家らしく見せない）。
- 素人質問者を、知識の下ごしらえより先に流す。読む知識ベースがまだ無いので、ガードを変えずに「知識を読ませない」が成り立つ。選ばなかった形：読める範囲をガードで絞る（ガードの変更は別の記録にする）。
- 視点別は視点ごとに別の段にした。段ごとに費用が記録に残り、役割を外して比べる（アブレーション）ときに使える。
- 役割の入れ外しは、`pipe.toml` の段の塊を消す形にした。エンジンに入れ外しの設定は足さない（比べる実験で切り替えが多くなったら考える）。
- 仕様書は固定の `docs/spec-review/spec.md` にした。検査のコマンドに変数を使わず、cmd.exe でも動かすため。
- 指摘は段の成果物そのものを JSON にした。`access = "read"` のままで書けるので、ガードを広げない。
- 共通の節「指摘の形（v1）」は、8つの指示文に写して持つ。段は別のファイルを読めないため。ずれはテストが見張る。
- `verify` は重なった指摘をまとめず、`confirmed` も `links` も付けない。根拠が主張と合わない指摘は消さずに `rejected` で残す。
- 要件の AC-11 の「両方のコマンドは外側 `"`・中 `'`」は、「引用符を使うコマンドは」と読み替えた。`findings-check` のコマンドには空白を含む引数が無く、引用符が要らないため。
- 監査（7件）で直したもの：
  - A-01（高）：`verify` の指示文が「引用を直せない指摘は `rejected` で残す」と言っていたが、`findings-check` は `rejected` でも引用を確かめるので、検査を必ず通らなかった。言い換えた引用は仕様書から写し直し、写し直せる文が仕様書に無い指摘は `09_findings.json` に入れない形に直した。選ばなかった形：`rejected` の指摘は引用を確かめないように `findings-check` を変える（D0043 の決まりの変更になる）。
  - A-02：共通の節に、`location.source` はいつも仕様書（`SRC-001`）で、法令や標準などは `sources` に書くことを足した。
  - A-03：README の「仕様書が複数なら `--spec` を足す」は成り立たない（台帳と検査役がそのファイルを知らない）ので、「1つにまとめる」だけにした。
  - A-04：`/pipe-help` のひな形の一覧に `spec-review` を足した。
  - A-06：README の素人質問者の注意を、「知識の置き場を空にしてから最初から流す」に直した（前の実行の知識の置き場が残るため）。
- 受け入れたリスク：指示文が実際にうまく働くか（指摘の質・haiku で足りるか・BOM が付くか）は、本物で流すまで分からない。公開の調達仕様書での実験と実案件1件で見直す。

## 対象外・残った課題

- Word・Excel・PDF の仕様書を文字にする段。
- 素人質問者に知識の置き場を読ませない仕組み（ガードで読める範囲を絞る）。今は段の順と指示文だけ。
- 重なった指摘をまとめる手順、質問票の詳しい列（期限・関連条項など）、顧客の回答を知識に戻す手順（CP3）。
- 役割の入れ外しの設定、`max_turns`・`max_budget_usd` の既定。
- `findings-check` で `rejected` の指摘の引用をどう扱うか（A-01 の別案）。
- 監査 A-05：プラグインの `/pipe-in:pipe-build` のひな形の一覧（`plugin/skills/pipe-build/SKILL.md`）に `spec-review` が無い。今回は `plugin/` を触らない範囲にしたので直していない。
- 監査 A-07：検査役に `verification` を書かないと段ごとの節では言っていない。共通の節に「`verify` の段だけが書く」とあるので、そのままにした。

## 確かめたこと

- `tests/test_template_spec_review.py`（51件）と、直した `tests/test_generator.py`・`tests/test_pipe_lint.py`・`tests/test_guide.py` はすべて通った。テスト先行の段では、ひな形が無いことで落ちるのを、失敗の文まで読んで確かめた。
- 全体の `pytest -q`：11491 件が通り、落ちたのはこの記録が無いことを見る `tests/test_rules.py` の1件だけ（この記録で直る）。承認されたテストは、テスト先行のあと書き換えていない。
- 監査の直しのあと、ひな形と文書のテストを流し直して通った。
- 助言と審査は流していない（変えたファイルに `.claude/` の定義・`plugin/`・ガード・runner が無い。`/pipe-help` の1行は文書だけ）。
- 本物の SDK で、デジタル庁の公開の調達仕様書（公共データ利用規約 第1.0版）の1章〜4.3節を文字に起こしたものを流した（人が依頼して承認した。合計 $2.94）。
  - AC-24：10段を通して流れ、`09_findings.json`（指摘 104 件）が `findings-check` を1回で通った。質問票は84行・8列で、BOM が付いた。
  - AC-25：`naive` は知識の置き場ができる前に流れ、読まなかった。
  - AC-26：検査の6段が同時に流れ、段ごとの費用が記録に残った（haiku の7段で合わせて約 $0.19、sonnet の3段が残り）。
  - 不具合が1つ見つかった：`knowledge` の指示文が台帳の `kind` に使える値を並べておらず、`guideline`・`plan` を書いたため、知識の確認で差し戻して直した（差し戻しで $0.77）。指示文の直しは別の記録にする。
  - 人が先に書いた論点15件と言葉で突き合わせると、11件が指摘にあった。拾えなかったのは、誤記（「体制体制」）・表の中の時期の写し違い・基準の無い言葉・調達範囲の調整の4件。
- Excel で開くこと（AC-27）と VSCode の画面（AC-28）は、まだ。
