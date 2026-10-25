# D0047 worktree を自動で切って、main に入ったら自動で片付ける

## 目的

`/pipe-in` で機能を始めるたびに、worktree を手で切って `EnterWorktree` で移る承認に答え、main に入れたあとに `git worktree remove` と `git branch -d` を手で打つ手間をなくす。

## 機能要件と受け入れ基準

- FR-01 `python -m pipe_in worktree new <名前>` が、主の checkout の `.claude/worktrees/<名前>` に `<種類>/<名前>` のブランチを `main` から切り、切った絶対パスを出す（`pipe_in/dev/worktree.py`）。
  - D0047-AC-01 置き場所とブランチ名（`--kind` は `feat`・`fix`・`docs`。既定は `feat`）。
  - D0047-AC-02 worktree の中から呼んでも、置き場所は主の checkout の下（入れ子にしない）。
  - D0047-AC-03 名前は英数字と `.`・`_`・`-` だけ（先頭は英数字、64 字まで）。`/`・`..`・空白などは断る。
  - D0047-AC-04 同じ名前の worktree・ブランチがあれば断る。知らない種類も断る。
- FR-02 `python -m pipe_in worktree clean` が、`.claude/worktrees/` の下の worktree のうち、消してよいものをブランチごと消す。
  - D0047-AC-05 `main`（`--base` で変えられる）に入ったものは、worktree もブランチ（`git branch -d`）も消す。
  - D0047-AC-06 `main` に入っていない・まだコミットしていない変更（無視していない未追跡のファイルを含む）があるものは残し、理由を出す。`.claude/worktrees/` の外の worktree には触れない。
  - D0047-AC-07 呼んだ場所の worktree は残す。
  - D0047-AC-08 `--dry-run` は消す予定を出すだけ。
  - D0047-AC-09 無視しているファイル（`docs/pipeline/`・`node_modules/` など）だけなら、変更とみなさず消す。
  - D0047-AC-12 切ってから一度もコミットしていないブランチは残す（始めたばかりで、ほかの会話が使っているかもしれない）。
- FR-03 コマンドの口と置き場所。
  - D0047-AC-10 `python -m pipe_in worktree new|clean`。断るときは `pipe-in worktree: …` で終わる。
  - D0047-AC-11 このリポジトリの `.gitignore` に `/.claude/worktrees/`。
- FR-04 `/pipe-in` のスキルは、main の作業フォルダで始まったら人に聞かずに `worktree new` で切って `EnterWorktree`（`path`）で移り、main に入れたあとに人に聞かずに `worktree clean` で片付ける。文書（`docs/development/workflow.md`・`docs/development/design.md`）もそろえる。

## D0039 から置き換える点

- D0039-AC-13「移す前のバッククォートの語は全部残る」から、worktree の切り方の 3 語（`git worktree add …`・`../pipe-in-<名前>`・`git worktree add`）を除く（`tests/test_skill_tidy.py` の `REPLACED_BY_D0047`）。理由：切り方そのものを `python -m pipe_in worktree new` に置き換えたため。

## 決めたことと理由

- **置き場所は `.claude/worktrees/`。** 前の `../pipe-in-<名前>` は `.claude/worktrees/` の外なので、`EnterWorktree` が移るたびに人の承認を求めた。`.claude/worktrees/` は `EnterWorktree` が自分で作る場所で、ここなら承認なしで移れる見込み（公式の文書とツールの説明による。実機ではまだ確かめていない）。
- **`EnterWorktree` の `name` の形は使わない。** ブランチ名が `feat/<名前>` の決まりと合わないため。切るのはコマンドで、移るのは `path` で。
- **消すのは安全側に倒す。** main に入った・変更が無い・一度はコミットした、の 3 つがそろったものだけ。squash で入れたもの（ブランチの先が main の祖先にならない）は残る。ブランチは `-d` で消し、git が断れば止まる。
- **`git` は子プロセスで呼ぶ。** 本体の `pipe_in/dev/` の中に置き、依存は足さない。テストは一時フォルダの本物の git で確かめ、リポジトリの実物には触れない。
- **フックは変えない。** `pipe_in_guard.py` は `cwd` からいちばん近い `.git` を基準にするので、`.claude/worktrees/<名前>` の中でもその worktree が基準になる（D0004）。

## 対象外・残った課題

- squash や rebase で入れたブランチの片付け（今は残す。手で消す）。
- GitHub で PR を merge したあと、手元の `main` が古いと「入っていない」と判断される。`git fetch` してから `--base origin/main` で呼ぶ。
- main に入ったあとも、ほかの会話がその worktree を使い続けていると消してしまう（まれなので受け入れる）。
- `.claude/worktrees/` への `EnterWorktree` が承認なしで通るかは、実機ではまだ確かめていない。

## 確かめたこと

- `pytest -q`（`tests/test_worktree.py` の 18 件を含む）。
- 実機（実際の `/pipe-in` で切って移り、片付ける）：まだ。
