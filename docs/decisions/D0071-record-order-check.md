# D0071 記録の順序を検べる（`pipe-in record check`）と、本体の `/pipe-dev` の言い方の残り

## 目的

`/pipe-in` の記録（`docs/pipeline/state.json` と段のログ）が、「確認のある段は承認されてから次の段を始める」順序になっているかを、あとから確かめられるようにする。あわせて、本体に残っていた前の版の言い方 `/pipe-dev` を直す。GitHub の issue #71（D0039 が範囲の外にした項目）のうち、本体側の2つだけを扱う（`.claude/` とフックに触る残りの6つは扱わない）。

## 機能要件と受け入れ基準

- FR-01 記録に時刻を残す
  - D0071-AC-01 `review` の要素（`approved`・`revise`・`quit`）に、`Prompt` 行と同じ書き方の時刻 `at` を足す。
- FR-02 順序の検査
  - D0071-AC-02 承認のあとに次の段を `begin` した記録は、違反なし。
  - D0071-AC-03 承認の前に次の段を `begin` した記録は、違反を返す（段・時刻つき）。
  - D0071-AC-04 `revise` のあと承認され、承認のあとで次の段を始めた記録、同じ段のやり直しの `begin` は、違反にしない。
  - D0071-AC-05 `revise`・`quit` だけで承認が無いまま次の段が始まった記録は、違反を返す。
  - D0071-AC-06 承認と `begin` が同じ秒なら違反にしない。
  - D0071-AC-07 `at` の無い古い記録・読めない値・壊れた記録は、違反にせず「判定できなかった」とし、例外で落ちない。
  - D0071-AC-08 `begin` の無い（飛ばした）段と、確認の無い段は調べない。
- FR-03 コマンド
  - D0071-AC-09 `pipe-in record check` は、守られていれば「順序は守られています」で終了コード 0、違反があれば並べて終了コード 1。何も書き換えない。
  - D0071-AC-10 記録がまだ無いときは、`start` を促す文で終了コード 1。
  - D0071-AC-11 `python -m pipe_in skill record check` から流せる（`--project`・`--config` は今までどおり断る）。
- FR-04 `/pipe-dev` の言い方の残り
  - D0071-AC-12 `Prompt` 行の文と `99_summary.md` の1行目を `/pipe-in` にする。
  - D0071-AC-13 `--review` が断る文を `/pipe-in` にする（`driver` があれば値を見ずに断る動きは変えない）。
  - D0071-AC-14 古い形の記録・見本・拡張の読み方は変わらない。
  - D0071-AC-15 `driver` の値 `"pipe-dev"`（D0006）以外に `pipe-dev` を `pipe_in/` に残さない。
- FR-05 守ること
  - D0071-AC-16 `record_order.py` は `pipe_in.engine` と標準ライブラリだけを読み、書き込みの関数を使わない。依存の向きは変えない。

## 決めたことと理由

- 検査は、新しい `pipe_in/dev/record_order.py` の純粋な関数 `check_order` と、読むだけの `record check`（違反で終了コード 1）に置く。`begin` 自身が止める案は、書く側の動きを変えるので今回は採らない。
- 今の記録は順序が判定できない（`review` に時刻が無い）ので、`review` の要素に `at` を足す。足すだけで、`at` の無い古い記録は違反にせず「判定できなかった」として読む。ファイルの更新時刻や並びだけで見る案は、検出できない順（`begin` → `review` → `done`）や、移動で値が変わる問題があり採らない。
- 承認が複数あるときは「`begin` 以前に承認が1つでもあれば適合」とする。検査の対象は確認のある段（`requirements`・`design`・`red`）だけ。段のログは各ファイルの最初の `Prompt` 行を読む。
- 記録の `driver` の値 `"pipe-dev"` は、古い記録を見分けるのに要る（D0006）ので変えない。D0039・D0006 が残した「`/pipe-dev` の文言の残り」と「記録の順序の検査」は、この記録で解決した。
- guard は狭めない。依存を足さない。`.claude/`・フック・CLAUDE.md は触らない。
- 直した既存のテスト：`review` の要素を厳密に比べていたテスト（`tests/test_record_feedback_file.py`・`tests/test_live_answer_cli.py`・`tests/test_record.py`）は `at` を外してから比べる（期待値は弱めていない）。`tests/test_architecture.py::test_d0019_ac50_state_only_adds_keys` は、足した鍵 `at` を期待に加えた。

## 受け入れたリスク

- この変更より前の記録は検査できない（「判定できなかった」になる）。
- `record check` は呼ばれたときだけ働き、順序の違反を書く側では止めない。
- 監査の指摘で直していないもの：`docs/guide/records.md` の「最後の `Prompt` の行」は拡張の読み方で、`record check` は各ログの最初の行を読む（書き分けが無い）。段ごとにログが分かれるので結果は同じ。

## 対象外・残った課題

- #71 の残り6つ（`.claude/settings.json` の許可、`ask` の外れ、フックの exec 形と `onFailure`、`record` の許可の絞り、`pipe_in_guard.py` の止めた理由の文）は、`.claude/` とフックに触るので扱わない。
- `.claude/skills/pipe-help/SKILL.md` の一覧に `record check` を足す案は、`.claude/` なので書かない（`--help` に誘導してあり、足さなくても食い違いにはならない）。

## 確かめたこと

- `python -m pytest -q`：D0071 の AC は全部合格。失敗は、この件と関わりなく土台で落ちる `tests/test_skill_tidy_docs.py::test_D0039_AC_17` だけ（`.claude/skills/pipe-in/screen-check.md` にページの頭が無い）。
- `npm --prefix vscode test`・`npm --prefix vscode run typecheck`：通る。
- 実機の `/pipe-in` の流れの中での使い心地：まだ。
