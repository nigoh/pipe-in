# 進め方

## 1. 始める：ブランチと worktree

機能ごとに、ブランチを切って、別の作業フォルダ（worktree）で進めます。いくつかの会話や人が同時に作業しても、変更が混ざらないようにするためです。

```bash
python -m pipe_in worktree new <名前>     # .claude/worktrees/<名前> に feat/<名前> を切る。文書だけなら --kind docs、直しなら --kind fix
cd .claude/worktrees/<名前>
```

`worktree new` は、origin の main を取って、その先頭から切ります（手元の main が古くても、最新の main から始まります）。origin から取れなければ、手元の main へ黙って切り替えず、止まります。手元の main から切りたいときは `--no-fetch` を付けます（origin の remote が無いリポジトリは、取らずに手元の main から切ります）。単独の機能は、いつも main から切り、ほかの機能の枝の上に積み重ねません。

夜のまとめ実行（D0074）だけは、1本のまとめの枝 `night/<日付>` を `python -m pipe_in worktree new <日付> --kind night` で切り、件ごとの 1 コミットをそこへ積みます。PR は、まとめの枝から main へ 1 つです（親の進め方は [docs/guide/develop.md](../guide/develop.md) の「夜のまとめ実行（親の進め方）」）。決定の記録の次の番号は `python -m pipe_in decision-number`（origin の main から出します）。

`/pipe-in` は、会話が main の作業フォルダで始まっていれば、これを人に聞かずに流して、`EnterWorktree` でその worktree に移ります（D0048）。

- このリポジトリでは、複数の会話を同時に動かすのがふつうです。1人で1つだけ進めるときも、worktree を切ります。
- 切る前に、main の作業フォルダの `git status` を見ます。まだコミットされていない変更（ほかの会話の作業）があれば、それがどのファイルかを覚えておきます（あとで main に入れるときに重なりを確かめるため）。
- 同じファイルを大きく触る機能は、同時に進めません（あとで合わせるのが難しくなる）。
- 終わったら、main に入れたあとで、main の作業フォルダで `python -m pipe_in worktree clean` を流して片付けます（`/pipe-in` は人に聞かずに流します）。消すのは `.claude/worktrees/` の下で、main に入った・まだコミットしていない変更が無い・一度はコミットしたものだけで、worktree とブランチを一緒に消します。ほかは理由を出して残します。消す前に見るなら `--dry-run`。GitHub で merge したなら、`--base` は要りません（origin の main を取って確かめます）。merge commit で入れたものだけ消えます。squash・rebase の merge は残るので、手で消します。
- Claude Code で `/pipe-in` を進めるときは、始める前に `python --version` で `python` が動くことを確かめます。段のサブエージェントを絞るフック（`.claude/hooks/pipe_in_guard.py`）は `python` で動き、動かないとフックが効かず、絞りが外れて通るためです（[D0032](../decisions/D0032-guard-fail-closed.md)。くわしくは [docs/guide/develop.md](../guide/develop.md) の「フックが働く条件」）。

### worktree で気をつけること

- 拡張を触るなら、その worktree で `cd vscode && npm ci` をします（`node_modules/` は worktree ごとに要る）。
- `pip install -e .` で入れた `pipe-in`・`pipe-in-gen` のコマンドは、入れたときのフォルダ（ふつうは main）のコードを動かします。worktree で直したコードを確かめるときは、その worktree の中で `python -m pipe_in …`・`python -m pytest` を使います。テストは、入れ込みがどこにあっても、その worktree の `generator/` を `pipe_in_generator` として読むので、worktree ごとに入れ直す必要はありません（`tests/gen_loader.py`。[D0086](../decisions/D0086-test-generator-loader.md)）。
- `/pipe-in` の記録（`docs/pipeline/`）は worktree ごとにできます。VSCode の拡張で進み具合を見るときは、その worktree のフォルダを開きます。

## 2. 進める：5つの段

Claude Code では `/pipe-in <要件メモ>` が、この順に進め、段の区切りで止まって確認を取ります（止まらずに進めるのは `--auto` のときだけ。人のいない無人の実行（`--auto` を付ける）では、止まって聞く場面が、推しで決めて朝に人が確かめる形に替わります。始め方は [docs/guide/develop.md](../guide/develop.md) の「無人の実行の始め方」）。
段の中身は段ごとのサブエージェント（`.claude/agents/pipe-in-*`）が受け持ち、書ける場所と Bash は `.claude/hooks/pipe_in_guard.py` が絞ります。人とのやり取りと、決定の記録を書くのはメインの会話です。
スキル（`.claude/skills/pipe-in/`）は、必ず守る決まりを `SKILL.md` の冒頭に置き、長い手順（記録のコマンド・`--artifact`・画面の確認・無人の実行）を同じフォルダの補助ファイル（`record.md`・`artifact.md`・`screen-check.md`・`unattended.md`）に分けています。

| 段 | 受け持つ | すること | 書けるもの |
| --- | --- | --- | --- |
| 1. 要件定義 | `pipe-in-analyst` | 目的・FR・AC・対象外・触る側を書く（[specs.md](specs.md)） | `docs/pipeline/01_requirements.md` |
| 2. 設計 | `pipe-in-analyst` | 変えるファイル・形が変わるか（互換）・AC とテストの対応表（[design.md](design.md)） | `docs/pipeline/02_design.md` |
| 3. テスト先行（赤） | `pipe-in-tester` | 対応表どおりにテストを書き、期待した理由で落ちることを確かめる（[testing.md](testing.md)） | テストと `03_red_tests.md` |
| 4. 実装（緑 → 整理） | `pipe-in-coder` | テストを通す最小の変更をしてから整える。承認されたテストは書き換えない | 製品コードと文書と `04_implementation.md` |
| 5. 検証 | `pipe-in-verifier` とメイン | 触った側のテストを全部流す。画面・手で・実機の確認。公開してよいかを見る。合格したら、決定の記録の前に文書係（もう一度文書をそろえる）、続けて監査と助言（助言を流したときは審査も）を流し、承認された項目だけをメインが直す。メインが決定の記録を書く | `05_test_report.md`、決定の記録（メイン） |

### 検証のあとの監査と助言

検証で合格したあと（`record verdict pass` のあと）、決定の記録を書く前に、メインが、先に文書係 `pipe-in-documenter` で文書をそろえ直してから（下の「4. そろえる」）、2つのサブエージェントを流します（助言を流したときは、続けて審査も流します）。不合格・blocked のときは流しません。段は5つのままで、記録（`state.json`）に段は足しません。

- `pipe-in-auditor`（矛盾監査）：文書・定義・コード・テストのあいだの食い違いを、「ファイル:行」の根拠付きで並べます。範囲は、このブランチで変えたファイル（`git diff --name-only main...HEAD` と `git status --short` を合わせたもの）と、それを指す・それが指すファイルに絞ります。
- `pipe-in-advisor`（助言）：Claude Code と Agent SDK の公式の文書と照らして、使いかたのずれを、出典の URL 付きで並べます。変えたファイルに `.claude/`・`plugin/`・`.claude-plugin/`・`pipe_in/engine/runner.py`・`pipe_in/engine/guard.py`・`generator/guard_hook.py` があるときだけ流し、無ければ流さなかった理由を書きます。
- `pipe-in-judge`（審査）：助言を流したときだけ、続けて流します。助言の報告を、事実の正確さ・引用の正確さ・網羅性・情報源の質・ツール効率の5項目で 0.0〜1.0 に採点し、JSON で返します。合否は人が読む材料で、fail でも自動で直さず、差し戻しません。助言を流さなかったとき、または助言が0件のときは審査も流さず、その旨を書きます。
- 3つとも読むだけで、どこにも書けず、直しません（報告は親に返すだけ）。Web はアドバイザーと審査役（WebFetch だけ）だけ、公式の文書の場所だけ（`.claude/hooks/pipe_in_guard.py` が絞ります）。
- 報告（と採点）を見せて止まります。`--auto` でも止まります（直す項目は人にしか選べないため）。`--auto` を付けた無人の実行では止まらず、直さずに、決定の記録の「対象外・残った課題」に要約を書きます。2つとも0件なら止まらずに進みます。
- 直すのはメインで、人が承認した項目だけです。直してよいのは文書・定義・コメントの食い違いまでで、コードの振る舞いを変える項目はテスト先行の段に戻すか、別の `/pipe-in` にします。直したら、触った側のテストを流し直します。
- このブランチで変えたファイルに関わらない項目は直さず、決定の記録の「対象外・残った課題」に書いて、別の `fix/`・`docs/` のブランチで直します（1つの機能を1つのコミットにするため）。
- 手で呼ぶときは `/pipe-audit [範囲]`・`/pipe-advise [テーマ]`・`/pipe-judge [ファイル]` を使います。監査と助言で承認した項目は、今のブランチで直します。`/pipe-judge` は採点を見せて止まるだけで、直しません。

### 段の成果物（docs/pipeline/）と決定の記録の分け方

| | 段の成果物 | 決定の記録 |
| --- | --- | --- |
| 置き場所 | `docs/pipeline/`（`01_requirements.md`〜`05_test_report.md`・`state.json`・`logs/`。`python -m pipe_in record` が書く） | `docs/decisions/Dnnnn-<名前>.md` |
| 追跡 | **しない**（`.gitignore` 済み）。手元の作業の記録 | する |
| 何のため | 段から段への受け渡しと、VSCode の拡張で進み具合を見るため | あとから読む人が「何を、なぜ決めたか」を知るため |
| 中身 | 段の文書そのもの。セッション ID・手元のパス・読んだコードの中身が入る | 目的・FR と AC・決めたことと理由・対象外・確かめたこと（[specs.md](specs.md)） |
| いつまで | 次の `record start` で `docs/pipeline/archive/` に移る。いらなくなったら消してよい | ずっと |

- 決定の記録には、段の成果物の中身をそのまま貼りません。要るところだけを、手元の事情を消して書き直します。
- 段の成果物は worktree ごとにできます（`docs/pipeline/` は作業フォルダの中にあるため）。

## 3. 載せ直す：main が進んだら

並列で動かしていると、作業のあいだに main が先へ進みます（ほかの会話の機能が入る）。古い main の上で作り続けると、最後にまとめてぶつかり、テストも古い main で確かめたことになるので、こまめに載せ直します（rebase）。

### いつ

| いつ | すること |
| --- | --- |
| 段の区切り（各段が終わって、人に確認を取る前） | `git log --oneline HEAD..origin/main` で main が進んだかを見る（先に `git fetch origin main`）。進んでいれば、何が入ったかを伝えて載せ直す |
| 検証の段の前 | **必ず**載せ直す。新しい main の上でテストを流すため |
| main に入れる直前 | **必ず**載せ直す。早送りで入れられる形にするため |

### どうやって

```bash
git fetch origin main                 # origin の main を取る
git log --oneline HEAD..origin/main   # main に入った、まだ取り込んでいないコミット
git rebase --autostash origin/main    # まだコミットしていない自分の変更は、いったんよけて戻す
```

この流れは `python -m pipe_in worktree sync` 1つでもできます（origin の main を取ってから、進んでいなければ何もせず、進んでいれば入ったコミットを出して載せ直し、ぶつかったら止まります）。取れなければ止まります。手元に取れている版（`origin/main`）で進めるときは `--no-fetch` を付けます。`/pipe-in` は段の区切りに、確認なしで通る形の `python -m pipe_in skill worktree sync` を流します（D0049）。

- `--autostash` がよけるのは、この worktree の中の自分の変更だけです。main の作業フォルダ（ほかの会話の作業）には触れません。
- ぶつかったら、その worktree の中で合わせます。どちらの意図も残すように合わせ、合わせ方に迷うとき（両方が同じ決まりを違う形で変えたなど）は人に聞きます。合わせたら `git add` → `git rebase --continue`。
- **載せ直したら**、触った側のテストを流し直します。テスト先行の段より後なら、承認されたテストが新しい main の上でも同じ理由で赤（または緑）のままかを確かめます。main の変更でテストの意味が変わっていたら、その段に戻ります。
- ぶつかって合わせたこと・main の変更に合わせて直したことは、決定の記録の「決めたことと理由」に短く書きます。
- **push したブランチ**（ほかの人も使っているブランチ）は、載せ直さず、`git merge main` で取り込みます（履歴を書き換えると、ほかの人の手元とずれるため）。このリポジトリの機能のブランチは、ふつう push しないので、載せ直してかまいません。
- main そのものは、載せ直しません。

## 4. そろえる：文書

変えたものに合わせて、次の文書も直します。

| 変えたもの | 直す文書 |
| --- | --- |
| 使い方（コマンド・オプション・設定） | `README.md`・`docs/guide/`、拡張なら `vscode/README.md`、`/pipe-help`（`.claude/skills/pipe-help/SKILL.md`） |
| 置き場所（ファイルを足した・動かした） | [design.md](design.md) の「置き場所」の表、必要なら `CLAUDE.md` |
| 層・依存の向き | [design.md](design.md) と、それを検査するテスト |
| 検査の決まり（`check_pipe`・`validatePipe`） | 両側と見本 `tests/fixtures/check_parity/`、[design.md](design.md) の「検査の二重化」の節 |
| 開発の決まり | `docs/development/` と、それを検査するテスト、`CLAUDE.md` の要約、`/pipe-in` |

- 文書をそろえるのは、`/pipe-docs [要点か範囲]` に任せられます。変えたファイル（`git diff --name-only main...HEAD` と `git status --short`）を集めて、文書係の `pipe-in-documenter` に上の表どおりに直させます。文書係が書けるのは `README.md`・`vscode/README.md`・`pipes/README.md`・`docs/assets/README.md` と `docs/guide/`・`docs/development/` の `.md` だけで、`CLAUDE.md`・`.claude/`（`/pipe-help` を含む）・決定の記録は、案を返して人の承認を得てからメインが直します。
- `/pipe-in` では、実装の段でそろえたうえで、検証で合格したあと、監査の前にもう一度 `pipe-in-documenter` に見てもらいます。
- 新しい節・行・テストを足す場所は、末尾でなく決まった所にします（「8. 並列の作業でぶつからない書き方」）。`docs/guide/` の節は、関連する節の隣か、決まった順の位置に足します。
- コード（`pipe_in/`・`generator/`・`vscode/src/`・`vscode/scripts/`・`plugin/`・`.claude-plugin/`・`.claude/` の定義・設定・フック、`pyproject.toml`・`vscode/package.json`）を変えたのに、上の文書が1つも変わっていないまま会話が止まろうとすると、Stop のフック `.claude/hooks/docs_reminder.py` が、同じ変更の組で1回だけ知らせます。直す文書が無いときは、その理由を一言伝えて終えます。

## 5. 終える：確かめてコミットし、main に入れる

1. main が進んでいれば載せ直す（上の「3. 載せ直す」）。
2. 触った側のテストを全部流す。Python と拡張の両方に触れたら両方。拡張なら `npm run typecheck` も。GitHub に出した PR があれば、その CI（`python`・`extension`）が緑であることも見る（下の「6. CI」）。
3. `git status` で、自分の変更だけがあることを確かめる（ほかの作業のファイルが無いか）。
4. `git add` してから `git diff --cached` を読み、[principles.md](principles.md) の「7. 公開する前提で書く」のものが入っていないかを見る。
5. **1つの機能を1つのコミット**にする。文の形は既存に合わせる：
   - `feat(pipe-in): …`・`feat(pipe-in-vscode): …`・`fix(…): …`・`docs: …`・`chore: …`
   - 1行目は日本語で、何ができるようになるか。本文に、変えた点を箇条書きで。決定の記録があれば、その番号を書く
6. main に入れる。**main に入れる直前**にもう一度 `python -m pipe_in skill worktree sync` で載せ直し、テストを流し直す。PR を出してあれば、載せ直したあとの CI が緑かを見る。PR を出さずに入れるなら、手元で Python と拡張の全テストを流した結果を見る。そのうえで、GitHub の PR で入れる（`gh pr merge` は確認が出る。main の保護が関所。下の「6. CI」の「ブランチの保護」）。入れ方は merge commit（squash・rebase の merge は、`worktree clean` が「入った」と見分けられず枝が残る）。入ったら、main の作業フォルダに戻り、`python -m pipe_in worktree clean` で片付ける。手元で main を動かさないので、ほかの会話の変更と同じファイルで断られることはない。
7. コミット・PR を出す・main に入れる・push は、どれも人に言われてからする。Claude Code は、言われるまでしない。例外は無人の実行（人が開始の指示で、無人であることと、commit・push・PR の作成の承認を書いた実行。定義と範囲は `CLAUDE.md`）だけで、その実行が切った枝への commit・push・PR の作成までする。夜のまとめ実行（D0074）では、開始の指示が名指しした `night/` のまとめの枝への早送りの push も、範囲に入る。main に入れること（`git merge`・`gh pr merge`・main への push）は、無人でもしない。`.claude/settings.json` の `ask` には、`git merge`・`gh pr merge`・main へ届きうる `git push` の形・`gh api` での merge と `refs/heads/main` の更新・publish・`gh issue create` を入れてある（commit・枝名を書く `git push`・`gh pr create` は入れていない）。実機で確かめたこと：`ask` に入れた操作は auto モードでも確認が出て、人が答えるまで進まない（2026-11-02 の夜の実行）。公式の文書によること（実機は未確認）：個人の許可・フックの許可も `ask` を越えない。

## 6. CI：main に入る前の確認

`.github/workflows/ci.yml` が、main 向けの PR と main への push で、`CLAUDE.md` の「コマンド」と同じテスト・型検査・ビルドを流す。ジョブは2つで、並べて動く。

| ジョブ名 | 流すもの |
| --- | --- |
| `python` | `pip install -e '.[dev]'` → `pytest -q`（Python 3.11） |
| `extension` | `vscode/` で `npm ci` → `npm test` → `npm run typecheck` → `npm run build`（Node 22） |

- OS は `ubuntu-24.04`。Windows は対象外で、通るかは確かめていない。`npm run preview` は Playwright が要るので流さない。
- 権限は `contents: read` だけ。`pull_request_target` を使わず、秘密（API キーなど）も使わず、SDK も呼ばないので、利用料はかからない。外からの PR でも同じ権限で動く。
- 使うアクションは `actions/checkout`・`actions/setup-python`・`actions/setup-node` だけで、40桁のコミットの SHA で固定し、後ろに版のコメントを付ける。更新は Dependabot（`github-actions`）が PR で出す。
- ジョブ名（`python`・`extension`）は、ブランチの保護の「必須のチェック」に出る名前になる。変えると保護が外れるので、変えたら保護の設定も直す。
- 落ちたときは、PR の Checks で `python` か `extension` を開き、落ちた手順のログを見る。手元で同じものを流して直す（コマンドは `CLAUDE.md` の「コマンド」と同じ）。
- `python` の Python と `extension` の Node の版は、`pyproject.toml` の `requires-python` と `vscode/package.json` の `engines.node` の下限に合わせる。下限を変えたら CI の版も直す（`tests/test_ci_workflow.py` が食い違いを見つける）。

### ブランチの保護（人が GitHub の設定でする）

初めての CI の実行が緑になってから行う。画面の名前は GitHub の更新で変わりうる。

main の本当の関所は、この保護である。`.claude/settings.json` の `ask` と `CLAUDE.md` の決まりは、Claude Code に向けた目安で、書かれた形にしか当たらず、別の書き方（下の「すり抜けの道」）は止められない。クラウドの Claude Code のプロキシは、push 先の枝を絞らない。無人の実行（`CLAUDE.md`）を使うなら、先にこの保護を入れる。

1. Settings → Rules（または Branches）で、main を対象に「Require a pull request before merging」と「Require status checks to pass」を有効にし、必須のチェックに `python` と `extension` を選ぶ。
2. 管理者が保護を回避できるか（「Do not allow bypassing the above settings」）は、人が GitHub で決める。保護は、迂回を許された人やアプリ（管理者・ルールセットの bypass の一覧）には効かない。無人の実行を使うなら、迂回を許す一覧を空にし、迂回できる権限のトークンを無人の実行に渡さない。
3. PR を必須にすると、main に入れるのは PR 経由になる。手元で `git merge --ff-only` して main に入れる運用は使えなくなる。PR の CI が緑になってから、GitHub で入れる。

#### すり抜けの道

`ask` が止められないもの。止めるのは、`CLAUDE.md` の決まりと、この保護である。

- git の別名（alias）・`sh -c` の中・スクリプトの中の git・フルパスの `git`・引用符で囲んだ書き方（`git push origin 'main'`）・短い旗をまとめた書き方（`git push -fu`）。
- `gh api` の、merge も `refs/heads/main` も含まない書き方（ファイルを書き込む contents の API など）。
- GitHub の MCP の `merge_pull_request`・`push_files`・`create_or_update_file`。サーバーの名前が人ごとに違い、規則で覆えない。
- PowerShell ツールでの git・gh（Bash の規則は PowerShell に当たらない）。
- `git -C <フォルダ> merge`・`gh -R <リポジトリ> pr merge` のように、push 以外の別の書き方。
- `git -C <フォルダ> push`・`git -c k=v push` は、`ask` の規則（`git -* push*`）で当てた。

### 外からの PR の承認

Settings → Actions → General の「Fork pull request workflows」で、初めて投稿する外部の人の PR は、承認してから CI が動くようにする。承認の前に、PR が `.github/` やテストを書き換えていないかを読む。

## 7. PR と issue：GitHub に出すときの形

あとから読み返したときに見やすいように、GitHub の PR と issue は決まった形で書く。

1. **置き場所**：PR のテンプレートは `.github/pull_request_template.md`（PR を開くと本文に入る）。issue のテンプレートは `.github/ISSUE_TEMPLATE/` の `bug.yml`（不具合）・`feature.yml`（機能の要望）・`config.yml`（白紙の issue を許す）。issue の form は、既定のブランチ（main）にあるものだけが使われる。
2. **PR のタイトル**：タイトルはコミットの1行目と同じ形にし、決定の記録があれば、その番号を後ろに（Dnnnn）として付ける（上の「5. 終える」の形。例：`feat(pipe-in): main に入れる前に、CI（GitHub Actions）でテストを流す（D0052）`）。コミットでは番号を本文に書くが、PR の一覧では題しか見えないので、題に付ける。Dependabot の PR は Dependabot がタイトルと本文を書くので、この形にも下のテンプレートにも沿わなくてよい。
3. **PR の本文**：テンプレートの6つの節（何を変えたか・なぜ・受け入れ基準と確かめたテスト・確かめたこと・図（任意）・公開してよいかの確認）を、この順で埋める。受け入れ基準の表には、`Dnnnn-AC-xx` と確かめたテストの名前と結果を書く。手で・実機で確かめていないものは「まだ」と書く。`pytest -q` は、文書だけの変更でも流す（文書の形と公開の注意を `tests/test_rules.py` などが見る）。Claude Code が PR を作ると、本文の終わりに「🤖 Generated with Claude Code」の行を足す。この行は残す（設定の `attribution` は変えない）。
4. **issue**：不具合と機能の要望の form を使う。文書の誤りは不具合、文書を足す・書き直したいものは機能の要望で出す（どちらも「触る側」で文書を選ぶ）。どちらにも当たらないもの（質問など）は、白紙の issue で書く。ラベルは form が `bug`・`enhancement` を付ける（GitHub の既定のラベル。リポジトリに無いラベルは付かない）。新しいラベルは作らない。
5. **図（mermaid）**：図は**任意**。GitHub は ```` ```mermaid ```` のコードブロックを図として描く。図を勧めるのは、変更の流れ（何が何を呼ぶか）・依存の向きや層・段や状態の移り変わりを示すとき。小さな直しには要らない。PR の本文と issue に加えて、**決定の記録**でも図を勧める（記録の形の検査は変えないので、図の無い記録もこれまでどおり通る）。HTML コメントの中に図を置くときは、矢印を `==>` で書く（細い矢印はコメントの終わりの印と同じ文字になり、そこでコメントが終わってしまう）。VSCode の拡張は図を描かない（コードのまま見える）。
6. **公開の注意**：PR・issue・コメントに、**秘密**（API キー・トークン・`.env`・鍵）と手元の事情（ユーザー名の入った絶対パス・社内や私的なプロジェクトの名前・メールアドレス）を書かない。ログやパスは消してから貼る。`docs/pipeline/` の記録は貼らない（[principles.md](principles.md) の「7. 公開する前提で書く」）。
7. **`/pipe-in` との関わり**：仕上げで、コミットの文の案と一緒に、PR の本文の案（テンプレートの節に沿う。図が向く変更なら Mermaid の図の案つき）を見せる。PR を出す・push するのは、人に言われてから（無人の実行だけ例外。`CLAUDE.md`）。

## 8. 並列の作業でぶつからない書き方

夜のまとめ実行や、ほかの会話と同時に進める作業では、「同じファイルの末尾に書き足す」所でぶつかりやすい（D0075）。書き足しが別々の場所に入るように、次のとおりにします。

| 足すもの | 足し先 | 守ること |
| --- | --- | --- |
| 決定の記録の一覧（`docs/decisions/README.md`） | 表の末尾に 1 記録 1 行 | 番号は `python -m pipe_in skill decision-number` で取る。番号の昇順。`.gitattributes` の `merge=union` で、別々の枝が足した行どうしは載せ直し・cherry-pick・merge で自動で解ける。順序・重複・リンク先は `tests/test_doc_shape.py` が見る（載せ直しで並び違いになったときは、行を並べ替える） |
| 置き場所の表（[design.md](design.md)） | 近い部品の隣に、1 部品 1 行 | design.md と CLAUDE.md の表の行は 800 字まで（`tests/test_doc_shape.py`）。長くなる前に行を割る。拡張の部品は「層ごとの部品」の表に 1 行足し、層の表の行は書き足さない（D0051 の検査が層の行で読む語は残す）。テストが読む語を持つ行（先頭の言葉）は変えない |
| ガイド（`docs/guide/`）の節 | 関連する節の隣か、決まった順の位置 | 文書の末尾に足さない。機械では見ない（節の位置は意味で決まるため） |
| アーキテクチャのテスト | `tests/test_architecture_<名前>.py`（決定ごとに新しいファイル） | `tests/test_architecture.py` の末尾に足さない。`_imports`・`_module_name`・`_outside_stdlib` は `from test_architecture import …` で使う |
| 確認用のページ | `docs/assets/README.md` の表に 1 行、`.claude/skills/pipe-in/screen-check.md` の頭の一覧に 1 行（1 行 1 頭） | screen-check.md の足し忘れは、`tests/test_skill_tidy_docs.py` の D0039-AC-17 が、足す頭の名前と足す場所を出して落ちる。README の表の足し忘れは `tests/test_guide.py` が落ちる |

- 載せ直し（`worktree sync`）のあと、`pytest -q` を流す。union で自動に解けた一覧が壊れていれば、上の検査が落ちる。
- `merge=union` が効くのは、git のマージの仕組みを使う手元の操作（`git rebase`・`git cherry-pick`・`git merge`）。GitHub の画面の merge で効くかは確かめていない。入れる直前に手元で載せ直す手順（「5. 終える」）なら、解けたものを GitHub に出せる。
- 同じ番号を取り合うことは、`decision-number` が防ぐ（`merge=union` は番号の取り合いを解かない）。
