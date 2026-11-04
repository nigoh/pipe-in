# 無人の実行の手順（/pipe-in）

無人の実行（CLAUDE.md の「必ず守ること」の例外）のときに、最初の `record start` の前に1回読む（迷ったら読み直す。長い会話では、自動の要約のあとに読み直す）。

何が無人の実行か、してよいこと・しないことは CLAUDE.md が決める。ここには手順だけを書く。承認は、名指しされた操作だけに効く。承認が足りないとき（無人の宣言が無い・名指しが足りない）は、この手順を使わず、今までどおり案を見せて止まる。

**止まって聞く場面の代わり。** AskUserQuestion は使わない（答える人が居ないと、答えが来るまで止まったままになる）。`--auto` でも止まって聞く場面（SKILL.md の `--auto` の節と、各段の「`--auto` でも」）を、次に替える。無人の実行には `--auto` を付ける。`--auto` が引数に無ければ、最初の段の区切りで聞かずに `record finish BLOCKED` で止め、終わりの報告に「`--auto` が無い」と書く。

- 要件定義の決めきれない点は、推しの案で決め、決定の記録に「人の確認は朝」と書く。
- 文書係の案（CLAUDE.md・`/pipe-help`・`.claude/` の定義）は入れず、決定の記録の「対象外・残った課題」に案を書く。
- 監査と助言（と審査）の報告は直さず、同じ所に要約を書く。
- 検証の不合格が3回続いたら、`record finish TEST_FAILED` で止め、commit・push・PR の作成はしない（変更は commit せずに残す）。次の要件メモがあれば次へ進む。
- 取り返しのつかない操作（CLAUDE.md の「しない」）はせず、残して終わりの報告に書く。
- 上のほかに人に聞く場面（載せ直しのぶつかりで迷う・`record start` が途中の記録に断られたときなど）は、聞かずに `record finish BLOCKED` で止め、終わりの報告に書く。

**仕上げ。** 承認がそろっていれば、「決定の記録と仕上げ」の、案を見せて止まる所を、次に替える。

1. `record finish PASSED` のあと、`git status` で自分の変更だけであることを見る。`git add` で自分の変更のファイルだけを加え、commit の前に `git diff --cached` で公開してよいか（秘密・手元の事情が入っていないか）を見る。
2. その実行が切った枝（`feat/`・`fix/`・`docs/`）に commit する。commit の文の形は、SKILL.md の「決定の記録と仕上げ」と同じ。main の作業フォルダ（`.claude/worktrees/` の外）では commit しない。
3. `git push -u origin <その枝>` で push する（`git -C` を付けない。強制の push・main への push・push 済みの枝の載せ直しはしない）。
4. PR を作る（`gh pr create`。`gh pr` が動かない環境では GitHub の MCP の PR 作成）。本文は `.github/pull_request_template.md` の節に沿い、タイトルは commit の1行目の形に（Dnnnn）を付ける。base は main でよい（出すだけで入れない）。
5. 終わりの報告を会話に書く。した操作（commit・push した枝・PR）と、しなかったこと（承認の足りない操作・推しで決めた点・直さなかった監査と助言）を分けて書く。

**夜のまとめの子（まとめの枝へ積む）。** 親の開始の指示が、まとめの枝 `night/<名前>` を名指しして、その枝への早送りの push を承認しているときの、子の手順。上の「仕上げ」の 2〜4 を、次に替える。

- 枝は `python -m pipe_in skill worktree new <件の名前> --base night/<名前>` で、まとめの枝の最新から切る。決定の記録の番号は、始めに `python -m pipe_in skill decision-number --branch night/<名前>` で取る（前の件が積んだ番号の次になる）。
- 段の区切りと検証の前の載せ直しも `python -m pipe_in skill worktree sync --base night/<名前>` で流す（`--base` が無いと origin の main に載せ、前の件が積んだコミットまで作り直して、早送りの push が通らなくなる）。
- 検証が通ったら、自分の変更を 1 コミットにする（commit の前に `git diff --cached`）。件ごとの枝は push せず、PR も作らない。
- `git push origin HEAD:night/<名前>` で、まとめの枝へ早送りだけで push する（強制はしない。`git -C` を付けない。名指しされた枝のほかへは push しない）。
- 早送りでなく断られたら（ほかの子が先に積んだ）、`python -m pipe_in skill worktree sync --base night/<名前>` で載せ直し、テストを流し直して、もう 1 回だけ push する。それでも断られたら `record finish BLOCKED` で止め、変更は commit のまま残して終わりの報告に書く。
- `BLOCKED`・`TEST_FAILED` で止まった子は、まとめの枝に積まれない。終わりの報告に、止まった理由と、積まなかったことを書く。
- 子は auto モードで動く前提。`git fetch`・`git commit`・`git push` が確認になって断られたら（auto でない起こし方）、別の書き方で通そうとせず `record finish BLOCKED` で止め、終わりの報告に書く。リポジトリの設定からは、auto の判定に `night/` の枝を教えられない。判定が承認として読むのは、人の書いた開始の指示の名指し。
