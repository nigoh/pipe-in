# D0004 /pipe-in のサブエージェントが、報告を返し、worktree の中でも書けるようにする

## 目的

/pipe-in の段を受け持つサブエージェントが、報告を親に返せず、worktree の中ではテストも成果物も書けなかった。フック（`.claude/hooks/pipe_in_guard.py`）を直し、決まりどおり worktree で /pipe-in を進められるようにする。

## 機能要件と受け入れ基準

- FR-01 報告を親に渡す道具 `SubagentHandback` を止めない
  - D0004-AC-01 4つのサブエージェントのどれでも、`SubagentHandback` は止められない（`tests/test_pipe_in_guard.py::test_d0004_ac01_subagents_can_hand_back_their_report`）
- FR-02 書いてよい場所の基準を、サブエージェントがいる git の作業フォルダ（`.git` のあるいちばん近い上のフォルダ。worktree ならその worktree）にする。見つからなければ、今までどおり `CLAUDE_PROJECT_DIR`
  - D0004-AC-02 worktree の中・その下のフォルダにいるときは worktree が、ふつうの作業フォルダにいるときはそこが基準になる（`::test_d0004_ac02_root_is_the_checkout_the_agent_works_in`）
  - D0004-AC-03 `.git` が見つからなければ `CLAUDE_PROJECT_DIR` が基準になる（`::test_d0004_ac03_without_git_falls_back_to_project_dir`）
  - D0004-AC-04 worktree にいるテストの段は、その worktree の中のテストにだけ書ける。製品コード・会話を始めた場所・ほかの worktree には書けない（`::test_d0004_ac04_worktree_agent_writes_only_inside_its_worktree`）

## 決めたことと理由

- **`SubagentHandback` を許す。** フックは許すものの一覧で書いていて、この道具が一覧に無かった。報告の文を親に渡すだけで、ファイルにも外にも書かないので、すり抜けの道にはならない。止めていたせいで、/pipe-in を足してから、どの段のサブエージェントも報告を返せず、親が成果物のファイルを読んで代わりにまとめていた。
- **基準を、サブエージェントがいる git の作業フォルダにする。** worktree で進める決まり（D0003）では、会話は main の作業フォルダで始まり、段は worktree で進む。基準が `CLAUDE_PROJECT_DIR`（会話を始めた場所）のままだと、worktree の下はすべて「プロジェクトの外」になり、テストの段は28回止められて1つも書けなかった。
- **止める範囲は広げていない。** 基準が変わっても、書けるのはその作業フォルダの中の、段ごとに決めた場所だけ。会話を始めた場所やほかの worktree への書き込みは、今までどおり止める（D0004-AC-04）。サブエージェントは `cd` を使えない（Bash は決まったコマンドだけ）ので、いる場所を変えて基準をずらすこともできない。PowerShell・MCP・Agent・Web を止めるのも今のまま（既存のテスト）。
- **`git` を呼ばずに `.git` を探す。** フックは道具を呼ぶたびに動くので、標準ライブラリだけで速く済ませる。`.git` はふつうの clone ではフォルダ、worktree ではファイルなので、どちらも「ある」で見る。

## 対象外・残った課題

- 動いているフックは、会話を始めた場所（ふつうは main）の写しなので、この直しが main に入るまで、ほかの worktree の /pipe-in には効かない。
- サブエージェントの定義（`.claude/agents/pipe-in-*`）の `tools:` に `SubagentHandback` を書くかどうか。今の定義でも呼べている（フックに止められていただけ）ので、変えていない。

## 確かめたこと

- 新しいテスト7件は、直す前に期待した理由で落ちた（`SubagentHandback` が止められる・`project_root` が無い・worktree の中のテストへの書き込みが止められる）。直したあと、`tests/test_pipe_in_guard.py` の114件がすべて通った。
- 不具合そのものは、名前替え（pipe-in）の /pipe-in で見つけた。テストの段のサブエージェントの記録に、止められた理由（「pipe-in-tester が書けるのは テスト（tests/・*.test.ts）と docs/pipeline/03_red_tests.md だけです（<worktree>\tests\fixtures\…）」「pipe-in-tester は SubagentHandback を使えません」）が残っていた。
