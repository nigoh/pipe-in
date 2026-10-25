# D0043 仕様書レビューの指摘を決まった形（指摘の形 v1）で受け渡し、形・出典・引用の一致・役割ごとの決まりを `pipe-in-gen findings-check` で LLM を呼ばずに検査する

## 目的

仕様書・要求書をレビューする役割（品質・網羅・視点別・素人質問・根拠の確認・まとめ）どうしが、同じ形で指摘を受け渡せるようにする。出典の無い指摘や、仕様書に無い文を引いた指摘を、LLM を呼ばずに機械で見つけられるようにする。確定した指摘は、あとで要件（FR・AC）へ結び、テストと納品物まで1本の鎖で追えるようにする。

## 機能要件と受け入れ基準

テストは `tests/test_findings_check.py`・`tests/test_findings_check_cli.py`（下では `::` からの名前だけを書く。`_cli` が付くものは後者）と `tests/test_architecture.py`。

- FR-01 指摘の形 v1 を JSON Schema（`generator/schemas/finding.schema.json`）とコードの決まりで定める。ファイルは `{"v": 1, "findings": [...]}`。1つの指摘の欄は `id`（`F-` と3けた以上の数字）・`role`（`quality`・`gap`・`perspective`・`naive`）・`perspective`（`role` が `perspective` のときだけ。`user`・`tester`・`designer`・`operations`・`security`・`legal`）・`location`（`source`・`section`・`quote`）・`kind`（`missing`・`ambiguous`・`inconsistent`・`unverifiable`・`excess`・`risk`）・`statement`・`rationale`・`sources`・`guess`・`confidence`（`high`・`medium`・`low`）・`severity`（`critical`・`major`・`minor`）・`question`（`text`・`type`＝`yes_no`・`choice`・`free`・`choices`）・`risk`（`condition`・`impact`・`estimate`）・`verification`（`verdict`＝`supported`・`rejected`・`needs_human`・`reason`）・`status`（`open`・`confirmed`・`rejected`）・`links`（`requirements`・`acceptance`）。必須は `id`・`role`・`location`・`kind`・`statement`・`rationale`・`sources`・`guess`・`confidence`・`severity`・`status` の11欄。
  - D0043-AC-01 欄が全部そろった指摘は通り、必須の欄が1つ欠けた指摘は、その欄の名前を添えた行で落ちる（`::test_good_finding_passes`・`::test_missing_required_field_is_reported` ほか）
  - D0043-AC-02 決まった値の外の `kind`・`severity`・`confidence`・`status`・`role`・`perspective`・`question.type`・`verification.verdict` は、欄の名前と入れた値を添えて落ちる（`::test_value_outside_enum_is_reported`）
  - D0043-AC-03 `id` が `F-` の形でない、同じファイルの中で重なると落ちる（`::test_bad_id_shape_is_reported`・`::test_duplicate_id_is_reported`）
  - D0043-AC-04 `perspective` は `role` が `perspective` のときだけ要り、`choices` は `question.type` が `choice` のときだけ要る（`::test_perspective_pairs_with_role`・`::test_choices_pair_with_choice_type`）
  - D0043-AC-05 定義に無い欄（綴りの違いなど）と型の違い（`bool` を数として通さない）は落ちる（`::test_unknown_field_is_reported`・`::test_wrong_type_is_reported` ほか）
- FR-02 出典の台帳（`generator/schemas/sources.schema.json`）を定める。ファイルは `{"v": 1, "sources": [...]}`。1件は `id`（`SRC-` と3けた以上の数字）・`kind`（`spec`・`customer`・`law`・`standard`・`public_spec`・`past_case`）・`title`・`version`・`where`。`kind` が `spec` の件は `file`（仕様書のファイル名だけ）を持つ。
  - D0043-AC-06 `sources` と `location.source` が台帳に無い ID を指すと、その ID を添えて落ちる。台帳の `id` の重なり・形の違い・決まった値の外の `kind` も落ちる（`::test_unknown_source_id_is_reported`・`::test_unknown_location_source_is_reported` ほか）
  - D0043-AC-07 `sources` が空なのに `guess` が偽、`sources` があるのに `guess` が真だと落ちる（`::test_guess_must_match_sources`）
- FR-03 引用の一致を確かめる。`location.quote` は、`location.source` が指す仕様書の本文に含まれていなければならない。比べる前に、両方を NFKC にそろえ、空白（改行・タブ・全角空白を含む）を全部除く。
  - D0043-AC-08 CRLF・全角空白・空白の違いがあっても、同じ文なら通る（`::test_quote_ignores_whitespace_and_newline_kinds`・`::test_normalize` ほか）
  - D0043-AC-09 本文に無い文・言い換えた文・語を抜いた文を引いた指摘は落ちる。大文字と小文字は区別する（`::test_quote_in_body_passes`・`::test_quote_not_in_body_fails` ほか）
  - D0043-AC-10 `kind` が `missing` のときだけ `quote` を空にしてよく、そのとき `section` は要る（`::test_missing_kind_may_have_empty_quote`・`::test_missing_kind_needs_section` ほか）
  - D0043-AC-11 `location.source` が `spec` でない台帳の件を指すと、本文と照らせないので落とす（`::test_non_spec_location_source_cannot_be_checked`・`::test_spec_without_body_cannot_be_checked`）
- FR-04 役割ごとの決まりを確かめる。
  - D0043-AC-12 `role` が `naive`（素人質問者）の指摘は、`sources` に `spec` 以外の台帳の件を持てない（`::test_naive_cannot_use_non_spec_source`・`::test_naive_may_use_spec_or_guess` ほか）
  - D0043-AC-13 `kind` が `risk` のときだけ `risk` を持ち、`condition`・`impact`・`estimate` がそろう（`::test_risk_pairs_with_kind`・`::test_risk_parts_are_required`）
  - D0043-AC-14 `links` は `status` が `confirmed` のときだけ持ち、`confirmed` なら要る。`requirements` は `FR-` と数字、`acceptance` は `AC-` か `Dnnnn-AC-` と数字（`::test_links_only_when_confirmed`・`::test_link_values_must_match_shape` ほか）
- FR-05 `pipe-in-gen findings-check <指摘のファイル> --sources <台帳> --spec <仕様書>…` を作る。LLM も SDK も呼ばず、標準ライブラリだけで動く。パイプの `check.command` から呼べる。
  - D0043-AC-15 `--spec` は複数書け、ファイル名（`/` と `\` の両方で切ったパスの最後）で台帳の `file` と結ぶ。結べない・同じ名前が複数ある・`--spec` が無いのに `spec` の件があるときは終了コード 2。使われない `--spec` は許す（`_cli::test_multiple_spec_files_are_matched_by_name`・`_cli::test_spec_exit2_cases` ほか）
  - D0043-AC-16 誤りが無ければ「誤りなし」で終了コード 0。あれば `<id>: <欄>: <理由>` を誤りの数だけ、指摘の順 → 欄の決まった順に出し、最後に件数を出して終了コード 1（`::test_problem_order_is_stable_and_follows_field_order`・`::test_problem_line_has_three_parts` ほか）
  - D0043-AC-17 ファイルが無い・JSON でない・UTF-8 でない・一番上が辞書でないときは、理由を標準エラーに出して終了コード 2。BOM は許す（`_cli::test_unreadable_input_exits_2`・`_cli::test_bom_is_allowed` ほか）
- FR-06 形の版を持つ。指摘のファイルと台帳の頭に `"v": 1`。
  - D0043-AC-18 `v` が無い・1 でない（`2`・`"1"`・`true`・`null`）ファイルは「版が分かりません」で終了コード 2（`_cli::test_unknown_version_exits_2`）
  - D0043-AC-19 Schema の列挙・必須・欄・形の決まりと、コードの定数が食い違わない（`::test_finding_schema_matches_code`・`::test_sources_schema_matches_code` ほか）
- FR-07 終了コードは 0＝誤りなし、1＝誤りあり、2＝入力を受け取れない。テストと公開の決まりを守る。
  - D0043-AC-20 テストは SDK を呼ばず、見本は `tmp_path` に作り、リポジトリの実物に書かない（`_cli::test_findings_check_does_not_import_sdk`・`_cli::test_cases_write_only_under_tmp_path`）
  - D0043-AC-21 見本に手元の情報を入れない（`::test_samples_have_no_personal_info`）
  - D0043-AC-22 検査のコードは標準ライブラリだけを使い、依存は増えない（`tests/test_architecture.py::test_findings_check_uses_only_stdlib`・`::test_dependencies_unchanged`・`_cli::test_cli_dispatches_findings_check` ほか）
  - D0043-AC-23 入れた版にも Schema が入り（`package-data`）、Schema が無くても検査は動く（`::test_package_data_includes_schemas`・`::test_check_does_not_read_schema_files`）

## 決めたことと理由

- 前提（決定のページで決めたこと）：まず自分が職場の案件で使い、チーム、外部の順に広げる。レビューと納品物は並べて作り、この形で結ぶ。役割は7つすべて作る。作る場所は pipe-in のパイプ。ロジックは公開の pipe-in、知識・事例・評価は職場の非公開の置き場所に置く。
- 指摘の形は、2つの設計資料（Round 1 の役割とスキルの設計・新規参入ドメインの専門家エージェントの設計レポート。どちらもリポジトリの外）の指摘の形を合わせ、確定後に要件へ結ぶ `links` を足した。選ばなかった形：片方の資料の形だけ（機械で検査しにくい・要件へ結ぶ欄が無い）。
- 出典を必須にせず、「出典なし＝推測」を `guess` で明示させる。LLM の一般知識からの指摘を消すと網羅が落ち、出典を捏造させる圧にもなるため。
- 引用の一致は機械で確かめ、LLM には「根拠が主張を支えているか」だけを任せる。言い換えた引用も落とす（人が承認）。言い換えは、仕様書に無いことを書いた指摘と見分けられないため。
- 比べる前に NFKC にそろえ、空白を全部除く。日本語の仕様書には全角英数・半角カナ・全角空白が混ざるため。NFKC は全角英数と半角英数を同じとみなすので少し緩いが、語の違いは落ちる。選ばなかった形：空白と改行だけそろえる（表記の揺れで正しい引用まで落ちる）。
- 素人質問者（`naive`）は、仕様書以外の出典を使えない（人が承認）。知識ベースを読んでいない役のため。
- 欄の名前は英語、値の説明は日本語にする。CSV（Excel）に出すときに日本語の見出しに置き換える（人が承認）。
- 要・不要は判定させず、`kind` の `excess` で論点として出すだけにする。必要性は文書の外の情報（事業の目的・契約）で決まるため。
- リスクの欄は `condition`（発生条件）・`impact`（影響）・`estimate`（見積・契約への波及）の3つ。案では「見積・契約への波及」を別の欄にしかけたが、`estimate` 1つにまとめた。
- 依存（jsonschema）は足さない。標準ライブラリで v1 の形だけを検査し、Schema は他の道具（エディタ・他の言語）に渡す契約として置く。検査は実行時に Schema を読まず、食い違わないことはテスト（AC-19）が守る。引用・台帳・役割の決まりは Schema では書けず、どのみちコードが要るため。
- Schema の置き場所は `generator/schemas/`。案の `generator/templates/spec-review/schema/` は、`pipe-in-gen list`・`new` がひな形として歩く場所で、`pipe.toml` の無いフォルダが一覧や複製を乱すため変えた。
- 台帳の仕様書の件と本文は、台帳の `file` と `--spec` のファイル名で結ぶ。選ばなかった形：`--spec SRC-001=path`（書くのが手間で、台帳だけ見ても本文が分からない）。
- `location.source` が仕様書以外を指したら、本文と照らせないので落とす（安全側）。
- `links.acceptance` は `AC-xx` と `Dnnnn-AC-xx` の両方を許す。顧客の要件の AC と、このリポジトリの形の両方があるため。
- `check.command` から呼ぶと、pipe-in は終了コード 0 以外をすべて不合格として扱う。1 も 2 も、出力を添えて差し戻しになる。
- 監査の項目のうち、A-01〜A-07（この記録の案が実物と食い違っていた点：Schema の置き場所・リスクの欄・AC の番号・終了コード 2・台帳の `file`・NFKC などの決まり・「（案）」）は、この記録を書き上げて直した。A-08（Schema は空白だけの文字列を通すがコードは落とす）は、Schema の説明文に書いた。
- 受け入れたリスク：重大度の基準（`critical`・`major`・`minor` の分け方）は、根拠となる研究が薄い。実験と実案件1件で見直し、変えるときは新しい記録で v2 にする。

## 対象外・残った課題

- 役割（エージェント）とパイプそのもの（`spec-review` のひな形の段の並び・指示文）は、別の記録にする。
- 質問票の CSV の列と並びは、別の記録にする。
- 知識ベース（用語集・ドメインモデル・法規の候補）の形は、知識ビルダーの記録にする。
- 素人質問者に知識ベースを読ませない仕組み（読める範囲の絞り）は、ガードの変更になるので別の記録にし、すり抜けの道をテストで示す。
- 指摘の重なりをまとめる手順は、まとめ役の記録にする。
- 監査 A-09：Schema は `location.source` に `SRC-` の形を求めるが、コードは形を見ず台帳にあるかだけを見る。結果（落ちる）は同じで、誤りの文が「形が違います」でなく「台帳にない出典です」になる。直していない。

## 確かめたこと

- `tests/test_findings_check.py`（103件）・`tests/test_findings_check_cli.py`（38件）・`tests/test_architecture.py::test_findings_check_uses_only_stdlib` はすべて通った。テスト先行の段では、未実装・コマンドが無い・Schema が無いことで落ちるのを、失敗の文まで読んで確かめた。
- 全体の `pytest -q` では、この機能のテストは落ちていない。落ちたのは、main に入っている D0039 の作業途中のテスト（live 系など）だけ。
- 手で、架空の仕様書・台帳・指摘を一時フォルダに作り `pipe-in-gen findings-check` を流した。正しい指摘で終了コード 0、言い換えた引用と `guess` の食い違いで2行と終了コード 1、版の無いファイルで終了コード 2 になった。
- 文書（`docs/guide/pipes.md`・`docs/development/design.md`・README の目次）を実物と見比べ、`tests/test_guide.py`・`tests/test_readme.py` が通った。
- 監査を流した（9件。上の「決めたことと理由」と「残った課題」に書いた）。助言と審査は、変えたファイルに `.claude/` の定義・`plugin/`・ガード・runner が無いので流していない（`/pipe-help` の1行は文書だけ）。
- 実際の仕様書レビューのパイプから呼ぶのは、まだ（パイプが無い）。
