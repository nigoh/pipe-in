# D0051 ひな形 spec-review の知識の段に、出典の台帳の kind に使える6つの値と振り分けを書く

## 目的

ひな形 `spec-review`（D0047）を本物で流したとき、`knowledge` の段が台帳に決まりの外の `kind`（`guideline`・`plan`）を書き、`pipe-in-gen findings-check` で落ちた。`verify` の段は台帳を書けないので直せず、人が知識の確認で差し戻した。`knowledge` の指示文に使える値と振り分けを書き、この差し戻しを要らなくする。

## 機能要件と受け入れ基準

テストは `tests/test_template_spec_review.py`（下では `::` からの名前だけを書く）。

- FR-01 `generator/templates/spec-review/prompts/02_knowledge.md` に節「## kind に使える値」を足し、`spec`・`customer`・`law`・`standard`・`public_spec`・`past_case` の6つを、意味を添えた箇条書きで並べる。`spec` は `SRC-001` の1件だけに使う。
  - D0051-AC-01 6つの値が全部、一覧に入っている（`::test_d0051_ac01_prompt_lists_all_six_kinds`）
- FR-02 振り分けを書く：法令は `law`、ガイドライン・標準・政府の計画・業界団体の指針は `standard`、公開の仕様書は `public_spec`、社内規程は `customer`、過去の議事録や事例は `past_case`。それでも迷うものは台帳に入れず `issues.md` の論点にとどめる。
  - D0051-AC-02 振り分けの語と値の組が書かれている（`::test_d0051_ac02_prompt_has_routing_examples`）
- FR-03 指示文の一覧は、`findings_check.py` の `SOURCE_KINDS` と Schema の enum と食い違わない。
  - D0051-AC-03 一覧が `SOURCE_KINDS` と同じ集合で、`SOURCE_KINDS` に仮の値を足すと差が出る（`::test_d0051_ac03_listed_kinds_match_source_kinds` ほか）
  - D0051-AC-04 一覧・`SOURCE_KINDS`・`sources.schema.json` の enum の3つが同じ（`::test_d0051_ac04_listed_kinds_match_schema_enum`）
- FR-04 台帳の決まりに「`guideline`・`plan` のような値を作らない」を足す。
  - D0051-AC-05 `guideline`・`plan` は使える値として一覧に入らない（`::test_d0051_ac05_guideline_and_plan_are_not_listed_values`）
- FR-05 ほかのファイルは変えない。すでに写したパイプは書き換えない。
  - D0051-AC-06 ほかの指示文・README・`pipe.toml` に、この節も一覧も無い（`::test_d0051_ac06_other_prompts_and_files_unchanged`）
  - D0051-AC-07 写したあとのパイプの指示文は書き換わらない。新しい指示文は新しく写すパイプから効く（`::test_d0051_ac07_copied_prompt_is_not_rewritten`）
  - D0051-AC-08（手で）本物で `spec-review` を流し、台帳の `kind` が6つのどれかになり、知識の確認で差し戻さずに済む

## 決めたことと理由

- D0047 の「確かめたこと」に書いた不具合の直し。指示文だけを直した。選ばなかった形：`guideline` などを `findings-check` と Schema の値に足す（D0043 の形・すべての指示文・既存のパイプの検査に影響が広がる）。また起きたら別の記録で考える。
- 迷いやすい例は3つ（社内規程・業界団体の指針・過去の議事録や事例）だけを書いた。例を増やすと指示文が長くなり、それでも漏れる。迷うものは台帳に入れず論点にとどめる。
- 一覧は決まった見出しの下の箇条書きにした。テストがそこから値を取り出し、`SOURCE_KINDS` と Schema と照らせる。片方にだけ値を足すとテストが落ちる。
- 監査は0件、文書係が直すところも無かった。助言と審査は流していない（変えたファイルに `.claude/`・`plugin/`・ガード・runner が無い）。

## 対象外・残った課題

- 指示文は「`spec` の件は `file` も書く」とだけ言い、`spec` 以外の件に `file` を付けてはいけないことは書いていない（コードと Schema は付けると落とす）。監査で低い重さの言い足りなさとして挙がった。今回は直していない。
- 実験 E1（品質の検査に弱い表現の辞書とチェックリストを渡す）は別に行う。

## 確かめたこと

- テスト先行では、足した9件のうち5件が「指示文に節と一覧が無い」ことで落ちるのを、失敗の文まで読んで確かめた。残る4件は守りの検査で、今の作りでも通る。
- 実装のあと、全体の `pytest -q` で 11610 件が通り、落ちたのはこの記録が無いことを見る1件だけだった（この記録で直る）。承認されたテストは、テスト先行のあと書き換えていない。差分は指示文とテストだけ。
- 本物で流すこと（AC-08）は、まだ。利用料がかかるので、人に言われたときに流す。
