# D0049 /pipe-in が打つシェルのコマンドを、確認なしで通る形にまとめる

## 目的

`/pipe-in` を1回流すと、記録のコマンド（`python -m pipe_in record …`）だけで20回ほど確認が出る。段の区切りの載せ直し（`git log` → `git rebase`）・`python --version`・`npm --prefix vscode ci` でも出る。人が決める所（段の区切りの承認・commit・merge・push）のほかは、確認なしで進むようにする。

## D0039・D0046 から置き換える点

D0039・D0046 は書き換えない。次の点だけを、この記録が置き換える。

- D0039-AC-27「allow の Bash の規則は 14 個ちょうど・`python -m pipe_in` に当たる規則は無い」→ 3 つ（`Bash(python -m pipe_in skill:*)`・`Bash(python --version)`・`Bash(npm --prefix vscode ci)`）を足した 17 個。`python -m pipe_in record` に当たる規則は今も無い。AC-29 の allow の全体は 22 個 → 25 個。D0039-AC-28 の「5 つのコマンド」の取り出しから `npm --prefix vscode ci` を除く。
- D0046-AC-27「permissions は今のまま」→ allow に上の 3 つを足した形。
- D0039 で「record の規則は足さない（`--input` で任意のファイルを読め、`--project` で別のフォルダに書けるため）」と決めた理由は今も正しいので、record そのものは許さず、その旗を断る入口を別に作った。

## 機能要件と受け入れ基準

- FR-01 段の区切りの載せ直しを `python -m pipe_in worktree sync` 1つにする（`pipe_in/dev/worktree.py`）。
  - D0049-AC-01 main が進んでいなければ何もしない。
  - D0049-AC-02 進んでいれば、入ったコミットを返し、`git rebase --autostash main` で載せ直す（まだコミットしていない変更も残る）。
  - D0049-AC-03 ぶつかったら、合わせ方（`git add` → `git rebase --continue`）を書いて止まる。載せ直しの途中のまま残す。
  - D0049-AC-04 主の checkout では断る。
  - D0049-AC-05 コマンドの口。
- FR-02 `python -m pipe_in skill record …`・`python -m pipe_in skill worktree …` を足す（`pipe_in/dev/skill_cmd.py`）。
  - D0049-AC-06 `record`・`worktree` と同じに働き、今のフォルダを相手にする。
  - D0049-AC-07・D0049-AC-08 `--input`・`--feedback-file`・`--project`・`--config` は、短くした形・`=` の形でも断る（読んだあとの値で検める）。
  - D0049-AC-09 `skill` の後ろは `record` と `worktree` だけ。
- FR-03 許可とスキル。
  - D0049-AC-10 `.claude/settings.json` の allow に 3 つを足す。`record`・`worktree` そのものの規則は足さない。
  - D0049-AC-11 スキルは、記録を `skill record` で、worktree を `skill worktree new|clean|sync` で流す。記録の表のコマンドの文は変えず、`record.md` の頭に「替えて流す」と1行書く（文を固定する検査を崩さないため）。

## 決めたことと理由

- **フックは足さない。** 「決まった形だけ allow を返す」フックも考えたが、`settings.json` の `hooks` は PreToolUse 1 つ・Stop 1 つと決めて検査している（D0039-AC-23・D0032-AC-18）。`pipe_in_guard.py` に混ぜると、サブエージェントを絞る仕組みに、メインを通す役が入る。旗を断る入口なら、許可の規則 1 つで済む。
- **`skill` の入口は、断る旗を読んだあとの値で検める。** argparse は `--proj` のような短くした形も受けるので、文字の並びでなく、読んだ値が既定のままかを見る。
- **`--feedback-file` も断る。** 任意のファイルを読めるため。revise で長い文を渡すときだけ、元の形で流して確認に答える。
- **ぶつかった載せ直しは止める。** 合わせるのは人かメイン（`workflow.md` の「3. 載せ直す」）。
- **commit・merge・push の確認は残す。** 人が決める所なので。

## 対象外・残った課題

- `python -m pipe_in live …`（`--artifact` のとき）は `--out`・`--text-file` で任意の場所を読み書きするので、許していない（確認が出る）。
- `npm --prefix vscode ci` を許すと、依存のインストールのスクリプトが確認なしで動く。`package-lock.json` を追跡しているので受け入れる。
- `$(…)` などで別のコマンドを差し込んだ形を Claude Code がどう判定するかは、実機ではまだ確かめていない（今ある `Bash(pytest:*)` などと同じ）。
- `.claude/settings.json` の書き換えは、auto モードの判定に「自分の権限を広げる変更」として止められた。人が承認し、auto モードを外してから直した。

## 確かめたこと

- `pytest -q`（11532 件。`tests/test_worktree.py`・`tests/test_skill_cmd.py` を含む）。
- 初めは D0048 で書いたが、main に先に D0048（worktree の自動化）が入ったので D0049 に付け替えた。
- 実機（実際の `/pipe-in` で確認が出ないこと）：まだ。
