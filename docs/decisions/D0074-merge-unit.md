# D0074 merge の単位を「main 向けの PR 1つ」にそろえ、worktree の土台を origin から取る

## 目的

夜のまとめ実行（人が居ない間に複数の機能を `/pipe-in` で流す）と、ふだんの単独の機能で、merge の単位を「main 向けの PR 1つ」にそろえる。件ごとの枝・PR の積み重ねをやめ、下の PR を merge したときに上の PR が閉じられる事故（2026-11-02 の夜）と、出し直し・載せ直しを無くす。あわせて、決定の記録の番号の重なり（D0060 が main にあったのに夜の割り振りが D0060 から始めた）と、クラウドの入れ物で手元の main が古いまま枝を切る問題を直す。

2026-11-02 の夜は、件ごとの枝を前の件の枝の上に積み、PR の base も前の枝にした。下の PR を merge して枝が消えると、上の PR が閉じられた。最後は cherry-pick で1本の枝に集めて1つの PR で入れた。`worktree new`・`sync`・`clean` は手元の `main` を土台にしていて、クラウドの入れ物では手元の `main` が古いままだった。スキルの「main に入れるよう言われたら」は手元の `git merge --ff-only` を書いていたが、実際は GitHub の PR と CI で入れていた。

## 機能要件と受け入れ基準

- FR-01〜03 単位の決まり：夜のまとめ実行は1本のまとめの枝 `night/<YYYY-MM-DD>` に件ごとの1コミットを順に積み、main 向けの PR はその1つだけ。単独の機能は main から切り、ほかの機能の枝の上に積まない。`worktree new` に `--kind night` を足す。
- FR-04〜09 worktree の土台：`new`・`sync`・`clean` は土台を origin から取ってから使う（`--base` が枝の名前なら `git fetch origin <枝>` をして `origin/<枝>`）。origin が無ければ手元の枝。取れなければ黙って手元に切り替えず、失敗で止まる。`--no-fetch` で今までの動き。`skill worktree` の入口でも同じ。
  - D0074-AC-01 origin（一時の bare）がある。origin の main が、手元の main より進んでいる。`worktree new X` を流すと、切った枝の先頭が origin の main の先頭と同じになる。
  - D0074-AC-02 同じ条件で、`new X --base night/2026-11-02` は origin の `night/2026-11-02` を取ってその先頭から切る（手元に `night/2026-11-02` の枝が無くてよい）。`new X --base origin/main` も取ってからそのまま使う。
  - D0074-AC-03 origin の remote が無い一時のリポジトリでは、`new X` は今までどおり手元の main から切る（取らず、失敗しない）。
  - D0074-AC-04 remote はあるが、取れない（origin のパスが無い・その枝が origin に無い）とき、`new`・`sync`・`clean` は、手元の枝へ切り替えずに終了コード 0 でない失敗で止まり、文に「取れなかった」と `--no-fetch` が入る。枝・worktree は作られない。
  - D0074-AC-05 同じ取れない条件でも、`--no-fetch` を付けると、手元の `<枝>` を土台にして今までどおり動く。
  - D0074-AC-06 `sync`：origin の main に新しいコミットが1つ入っているとき、worktree の枝がそれに載り（`git log` に入る）、入ったコミットの行が出る。手元の main は動いていなくてよい。コミットされていない変更は残る。
  - D0074-AC-07 `sync`：origin の main が進んでいなければ「進んでいません」と出して、何も変えない。ぶつかるときは今までどおりの文で止まる。主の checkout では今までどおり断る。
  - D0074-AC-08 `clean`：枝が origin の main に入っている（origin の main へ push して取れる）とき、手元の main が古いままでも、その worktree とブランチを消す。origin の main に入っていない枝は残し、理由に `origin/main` が入る。
  - D0074-AC-09 `pipe-in skill worktree new X`・`sync`・`clean` が、AC-01・06・08 と同じに働く。`--no-fetch` は通り、`--project` は今までどおり断られる。
  - D0074-AC-10 `new X --kind night` は `night/X` の枝を origin の main から切る。`--kind` の一覧にない値は断る（今までどおり）。
  - D0074-AC-11 互換：`--base main` を明示した古い呼び方は、`--base` を省いたのと同じに動く（origin の main から取る）。`pipe-in worktree` の既存のテスト（取らない前提のもの）は、remote の無い一時のリポジトリなので、そのまま通る。
- FR-10〜12 決定の記録の番号：`python -m pipe_in skill decision-number`（元の形 `python -m pipe_in decision-number`）が、origin の main と `--branch night/<名前>` の `docs/decisions/` と、今いる作業フォルダの `docs/decisions/` を見て、いちばん大きい番号の次を出す。出すだけで作らない・予約しない。取れなければ止まる。
  - D0074-AC-12 origin の main に `D0001`〜`D0072` の記録があり、手元の main には `D0060` までしか無いとき、`decision-number` は `D0073` を出す。
  - D0074-AC-13 `--branch night/<名前>` を付け、まとめの枝にだけ `D0075` の記録があるとき、`D0076` を出す（origin の main と、まとめの枝の両方を見る）。まとめの枝が origin に無ければ失敗で止まる。
  - D0074-AC-14 `--branch` に `night/` で始まらない枝（`main`・`feat/x`・`--upload-pack=…` のような旗の形）を渡すと、断る。
  - D0074-AC-15 remote が無い・取れないとき、番号を出さず失敗の終了コードで止まり、文に理由と `--no-fetch` が入る。`--no-fetch` なら、取れている `origin/main` の版から出す。
  - D0074-AC-16 `decision-number` はファイルを作らず・書き換えず、リポジトリの状態（枝・作業フォルダ・`docs/`）を変えない（流す前後で `git status` と枝の先頭が同じ）。
  - D0074-AC-17 `docs/decisions/` に `D` で始まらない名前（`README.md`）や、4けたでない名前の `D12-x.md` があっても、数えずに最大を出す。決定の記録が1つも無いときは `D0001` を出す。
  - D0074-AC-18 `pipe-in skill decision-number` が元の形と同じに働き、`--project` を断る（`GUARDED` に足す）。
- FR-13〜17 まとめの枝への積み方と、無人の実行の範囲：子はまとめの枝の最新から切り、1コミットにしてまとめの枝へ早送りだけで push する（件ごとの枝は push せず PR も作らない）。断られたら載せ直して1回だけ push し直し、それでも断られたら `BLOCKED`。CLAUDE.md の無人の実行の範囲を、名指しされたまとめの枝1本への早送りの push だけ広げる。親の進め方は `docs/guide/develop.md`。
  - D0074-AC-19 CLAUDE.md に、まとめの枝 `night/<名前>` の名指し・その枝への早送りの push の承認・その1本だけに効くこと・`night/` 以外と main と強制と削除は今までどおりしないこと、が書かれている。ほかの項目（無人の実行の見分け方・親が起こす子の実行）の文は、範囲を変えずに写す決まりのまま。
  - D0074-AC-20 `.claude/settings.json` の `ask`（main へ届きうる push の形）は、狭めない。`git push origin HEAD:main`・`git push origin feat/x:main`・`git push origin HEAD:refs/heads/main`・`git push --force origin HEAD:night/x`・`git push origin :night/x`（削除）は、今までどおり `ask` に当たる。
  - D0074-AC-21 `.claude/settings.json` の `allow` に足すものがあっても、`git push origin <枝>:night/<名前>` の形だけ（main・強制・削除・`--all`・`--mirror` を含まない）で、`ask` と重ならない（今回は足さない）。
  - D0074-AC-22 `unattended.md` に、まとめの枝へ積む子の手順（枝の切り方・早送りの push・断られたときの載せ直しと1回だけの再 push・`BLOCKED`）と、子は件ごとの枝を push せず PR も作らないこと、が書かれている。
  - D0074-AC-23 （手で）まとめの枝を使わない（今までの）無人の実行の手順は変わっていない：その実行が切った `feat/` の枝へ push し、PR を作る。
- FR-18〜20 スキルと文書：「main に入れるよう言われたら」を PR と CI で入れる形にそろえ、worktree の記述を新しい既定（origin から取る）と `--no-fetch`・`night`・`decision-number` にそろえる。
  - D0074-AC-24 `SKILL.md` の「main に入れるよう言われたら」に `git merge --ff-only` が無く、PR・CI・`worktree sync`・`worktree clean` が書かれている。`SKILL.md` の字数の上限と、補助ファイルの字数の上限の検査は通る（補助ファイルは合計をやめ、1つずつの上限に替えた。下の「決めたことと理由」）。
  - D0074-AC-25 `SKILL.md` の始めの手順（枝を切る所）に、単独の機能は main から切って積み重ねないこと、決定の記録の番号は `skill decision-number` で取ること、が書かれている。
  - D0074-AC-26 夜のまとめ実行の親の進め方（FR-17 の 6 点）が `docs/guide/develop.md` にあり、`docs/guide/README.md` の目次から辿れる。
  - D0074-AC-27 `workflow.md` の worktree の節に、origin から取ること・`--no-fetch`・まとめの枝が書かれ、`design.md` の置き場所の表（`pipe_in/dev/` の行）に `decision-number` が入っている。
  - D0074-AC-28 `/pipe-help` の worktree と `--auto` の行が新しい形（`--no-fetch`・`night`・`decision-number`）とそろっている。
  - D0074-AC-29 リポジトリの規則のテスト（`tests/test_rules.py`・`tests/test_architecture.py`）が通る。`decision-number` の実装は `pipe_in/dev/` の中にあり、依存の向きを破らない。
  - D0074-AC-30 （実機）クラウドの入れ物で、手元の main が古いまま、`python -m pipe_in skill worktree new X` が origin の main の先頭から切り、`skill decision-number` が main の最新の次を出す。
  - D0074-AC-31 （実機）人が書いた開始の指示（まとめの枝の名指しと push の承認入り）で親が子を1件ずつ起こし、子がまとめの枝へ早送りの push をして、確認で止まらずに終える。名指ししていない `night/` の枝へは push しない。auto モードの子（クラウド・ルーチン）と、auto でない起こし方の子を分けて確かめる（auto でないときは、`allow` に無い push・fetch・commit が確認になる見込み）。

## 決めたことと理由

- **まとめの枝は1本、PR は1つ。** 件ごとの枝を積み重ねると、下の枝が merge のあとに消えたとき上の PR が閉じられる。1本の枝に件ごとの1コミットを積めば、PR は1つで、件の区切りはコミットに残る。名前は `night/<YYYY-MM-DD>`（同じ日の2回目は `-2`）。`--kind night` で同じ名前の枝が origin にあれば断る。
- **子の枝は push しない。** 子はまとめの枝へ `git push origin HEAD:night/<名前>` で早送りだけの push をする。枝と PR が増えず、消す手間も出ない。
- **`allow` に夜の push の規則を足さない。** `ask` は `allow` より強いので、`allow` が `ask` を破ることは無い。危ないのは、`Bash(git push origin HEAD:night/*)` のような `*` が空白もまたぎ、2つ目の refspec（`HEAD:night/a HEAD:release`）や `--tags`・`--no-verify` まで通すこと（助言の V-04）。足すなら `*` を含まない厳密一致にするが、名前が毎晩変わるので `.claude/settings.json` には置かない。`ask` の27本は変えていない（狭めていない）。夜の push の形がどの規則にも当たらず、main・強制・削除の形は当たったままであることは、27本を1本ずつ突き合わせて確かめた（助言の V-01）。
- **確認が出ないのは auto モードのときだけ。** `ask` に当たらないことと、確認が出ないことは同じではない（助言の V-02）。auto モードでは、どの規則にも当たらない操作は判定（classifier）に回り、作業しているリポジトリの枝への push は既定で許される側に入る。手動のモード・`claude -p` の既定・auto が使えないときは、`allow` に無い `git push`・`git fetch`・`git commit` が確認になる（`claude -p` では断られる）。そこで、夜の子は auto モードで起こし、確認になって断られたら別の書き方で通そうとせず `BLOCKED` で止める、と `unattended.md` と `develop.md` に書いた。
- **開始の指示に、動作と相手を具体的に書く。** auto の判定は CLAUDE.md を読むが、許す向きの文が判定に効くとは公式の文書に書かれていない。承認として読まれるのは、人の書いた文で動作と相手を名指ししたもの（助言の V-03）。夜の開始の指示の例に、無人であること・commit・push・PR の作成の承認・枝の名前・早送りだけ・`git push origin HEAD:night/<名前>` の形・`claude/` の枝を作らないこと（ルーチンは指示が無いと `claude/` の枝に push する。助言の V-06）を書いた。CLAUDE.md の文は、Claude 自身が守る決まりとして残す。
- **取れなければ止まる。** 手元の古い枝へ黙って切り替えると、今回の元の問題（古い main から切る）と同じ事故になる。`--no-fetch` で今までの動きを選べる。origin という名前の remote が無いリポジトリは、今までどおり手元の枝を使う。
- **`--base` の見分け。** `origin/` で始まるものは取ってからそのまま、ほかの枝の名前（`main`・`night/…`・`feat/…`）は `git fetch origin <枝>` をして `origin/<枝>`。`HEAD`・`HEAD~2`・コミットの略号のような枝の名前に見えない形は、取らずにそのまま使う（前の呼び方を壊さない）。`-` で始まる値は断る。
- **`new` は `--no-track` で切る。** 追跡の枝から切ると上流が `origin/main` に結ばれ、素の `git push` が main へ向かう形になりかねない。前の手元の main から切る形と同じに、上流を付けない。
- **`clean` は確かめてから `git branch -D`。** 手元の main が古いと `-d` は、origin の main に入った枝でも断る。消す前に `git merge-base --is-ancestor <枝> origin/<土台>` で入ったかを確かめ、通った枝だけを消す。
- **番号は出すだけ。** `decision-number` は origin の main と、名指しのまとめの枝と、今いる作業フォルダの `docs/decisions/D<4けた>-*.md` の最大の次を出す。作業フォルダも見るので、同じ作業フォルダで記録を書いたあとに流し直すと、番号が1つ進む。ファイルを作らず、予約もしない。夜のまとめ実行は1件ずつ順に流すので、各件が自分の始めに取れば重ならない。
- **朝は merge commit で入れる。** squash や rebase の merge では件ごとのコミットが変わり、`clean` が「入った」と見分けられず枝が残る（人が GitHub で選ぶ。`develop.md` に書いた）。
- **スキルの字数は、補助ファイルの合計の上限をやめ、1つずつ 3,500 字にした**（人が決めた）。補助ファイルは要るときにだけ読まれるので、合計は一度に読む量と結びつかない。合計の上限は補助ファイルを足すたびに上げてきた（D0046・D0050・D0051・D0063・D0073）。1つずつの上限なら、1つが読みきれない長さに育つことだけを止められる。SKILL.md の 12,300 字は残す（長い会話の要約のあとに戻る先頭が限られるため）。英語にして字数を減らす案は、文書・スキルを日本語で書く決まりと合わないので取らない。
- 「main に入れるよう言われたら」から手元の `git merge --ff-only` と stash の文を外した。実際は GitHub の PR と CI で入れていて、ブランチ保護（D0073）が関所になっている。
- **監査と助言で直したこと**（人が承認した項目）：
  - 監査の A-01：夜の開始の指示の例に、commit・push・PR の作成の承認がなかった（CLAUDE.md の無人の実行の条件を満たさない）。足した。
  - 監査の A-02：子が段の区切りで `--base` を付けずに `sync` を流すと、origin の main に載せ直してしまう。そうなると前の件のコミットまで作り直され、早送りの push が通らなくなる。`unattended.md` に「段の区切りの載せ直しも `--base night/<名前>`」と書いた。
  - 監査の A-03：親が流すコマンドを `skill worktree …` の形にした（`allow` にある入口）。人が端末で流す元の形の行は、そのまま残した。
  - 監査の A-04：`cli.py` のコメントと `develop.md` の入口の一覧に、`skill decision-number` を足した。
  - 監査の A-05：番号の数え方に、作業フォルダも見ることを書いた。
  - 助言の V-01〜V-06・V-08：上の各項目と、「受け入れたリスク」「対象外・残った課題」に書いた。
- 助言の報告の審査（ルーブリックの5項目）は、総合 0.80（合格の線 0.70）で合格。減点は、`claude -p` の既定が手動のモードになるのは v2.1.302 以降という条件が抜けていたことと、引用1つが元のページで見つからなかったこと。

## 受け入れたリスク

- `decision-number` は予約しないので、別々の worktree で同時に始めた単独の機能は、同じ番号を取りうる。夜のまとめ実行は順に流すので起きない。重なったら、あとから入れる側が番号を取り直す。
- 朝の merge のあと、まとめの枝の worktree は、手元でコミットしていないので `clean` が「始めたばかりかもしれない」と残すことがある。自動では消さず、`develop.md` に手で消す手順を書いた。
- `ask` に当たらない形の push は、auto モードの判定と CLAUDE.md の決まりだけが守る（D0073 の V-04 と同じ）。`ask` は文の形にしか当たらないので、引用符つきの書き方・`sh -c` などは素通りしうる。main の本当の関所は GitHub のブランチ保護。
- クラウドの入れ物の中継は、どの枝へ push するかを限らない。つないだ GitHub のアカウントが規則を迂回できると、main の保護も効かない（助言の V-05）。人がする設定を `develop.md` に書いた。

## 対象外・残った課題

- ぶつかりやすい文書の形（`docs/decisions/README.md` の表の末尾・`design.md` の置き場所の表の長い行・`usage.md`・`vscode.md`・`tests/test_architecture.py` の末尾）の直し（D0075）。
- 子の並列実行・止まった子の自動の再開・まとめの枝の PR の自動 merge・`night/` 枝の自動の片付け・番号の予約。
- GitHub の設定（人がする）：main は PR を必須にして、規則を迂回できる人・アプリを空にする。`night/*` には ruleset で強制の push と削除を禁じる。つないだアカウントが迂回できる権限を持っていないかを確かめる（助言の V-05）。
- 助言の V-07：push の全文を見て、まとめの枝への早送りの形（refspec が1つで `HEAD:night/<名前>` か `<子の枝>:night/<名前>`。強制・削除・`--all`・`--mirror`・`+`・main が無い）以外を止める PreToolUse のフック。守る向きの追加だけで、別の機能としてテスト先行で進める（D0073 の V-02 と同じ）。
- 助言の V-09：auto の判定に止められた操作と理由を、`PermissionDenied` のフックで記録に残す（AC-31 の確かめと朝の報告に使える）。別の機能。
- 手元の子だけなら、起こすときの `--settings` で、厳密一致の `allow` や `autoMode` を渡せる（助言の V-04・V-08。リポジトリの設定では渡せず、クラウドの子にも渡せない）。今は使わない。

## 確かめたこと

- テスト：`pytest -q` で 12,833 件通過・3 件スキップ・失敗 0（監査と助言の直しのあとにもう一度流す）。拡張（`vscode/`）は触っていない。
- AC-23（手で）：`git diff` で、`unattended.md` の「仕上げ」の 1〜5 が1字も変わらず、夜のまとめの子の節が後ろに足されただけであることを見た。
- AC-30（実機）：クラウドの入れ物で、手元の main が古い版のまま、`python -m pipe_in skill worktree new` で切った枝の先頭が origin の main の先頭と同じになり、上流が付かないことを確かめた。`skill worktree sync` は origin の main を取って「進んでいません」と出した。`skill decision-number` が「main の最新の次」を出すことは、作業フォルダにこの記録があるため実機では切り分けていない（テストの AC-12 は通る）。
- AC-31（実機）：まだ。
