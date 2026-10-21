---
name: pipe-docs
description: このリポジトリでコード・定義・設定を変えたあと、変えたものに合わせて文書（README.md・docs/guide/・docs/development/・vscode/README.md・/pipe-help・CLAUDE.md）をそろえる。変えたファイルを集めて文書係のサブエージェント pipe-in-documenter に任せ、書けない所の案は人の承認を得てからメインが直す。何かを直した・足したあと、文書をそろえる前に使う。
argument-hint: [変更の要点か範囲（空なら、このブランチで変えたファイル全部）]
allowed-tools: Agent(pipe-in-documenter)
---

# /pipe-docs — 変えたものに合わせて文書をそろえる

変更の要点・範囲: $ARGUMENTS（空なら、このブランチで変えたファイル全部）

CLAUDE.md の決まり、とくに「公開リポジトリとしての注意」を守る。そろえる先は `docs/development/workflow.md` の「4. そろえる」の表。

- 前置きの `allowed-tools` は、確認なしで文書係を呼べるようにする許しで、道具を絞るものではない。絞るのはフック（`.claude/hooks/pipe_in_guard.py`）と文書係の `tools:`。
- 文書係が書けるのは文書だけ（`README.md`・`vscode/README.md`・`pipes/README.md`・`docs/assets/README.md` と `docs/guide/`・`docs/development/` の `.md`）。`CLAUDE.md`・`.claude/`（`/pipe-help` を含む）・決定の記録は書けないので、案を返してくる。
- 止まるときの知らせ（`.claude/hooks/docs_reminder.py`）が「文書が変わっていない」と言ってきたときも、これを使う。

1. 変えたファイルの一覧を作る：`git diff --name-only main...HEAD`（このブランチのコミット）と `git status --short`（まだコミットしていない変更と新しいファイル）を合わせる。引数で範囲が渡されたら、その範囲に絞る。テスト・`docs/pipeline/` だけなら、「直す文書は無い」と書いて終える。
2. 変更の要点を短くまとめる（引数・この会話・`git diff` から。何ができるようになったか、名前・コマンド・オプション・置き場所の何が変わったか）。
3. `pipe-in-documenter` に Agent ツールで任せる。指示には、変えたファイルの一覧・変更の要点・作業フォルダ（今の worktree）・決定の記録の番号（あれば）を書く。サブエージェントはこの会話を見ていない。
4. 返ってきた「文書の報告」を会話に見せ、`git diff --stat` で文書係が直したファイルを見せる。直した文が実物と合っているかを `git diff` で読んで確かめる。
5. 「書けないので案にしたもの」（`CLAUDE.md`・`/pipe-help`・`.claude/` の定義・決定の記録）があれば、どれを入れるかを人に聞く。承認した案だけをメインが直す。
   - 決定の記録は、機能ごとにメインが書くもの（`/pipe-in` の「決定の記録と仕上げ」）。案は、そのときに使う。
   - コードの振る舞いを変えないと合わない食い違いは直さず、「`/pipe-in` で直す」と書いて残す。
6. 直したら、テストを流し直す（`python -m pytest -q`。文書は `tests/test_guide.py`・`tests/test_readme.py`・`tests/test_rules.py` などが検査する。拡張の文書に触れたら `npm --prefix vscode test` も）。
7. 直した文書と、直さなかったもの（と理由）を会話に書く。コミットはしない（人に言われるまで）。
