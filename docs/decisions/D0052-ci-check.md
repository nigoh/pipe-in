# D0052 main に入れる前に、CI（GitHub Actions）でテストを流す

## 目的

main に入る変更で `pytest` や拡張のテストが落ちるのを、入る前に機械で見つける（イシュー #33 の 3 つ目）。テストだけを先に足した途中のコミットが main に入って 161 件落ちた件（#33）と、作業途中のテストで main が赤になった件（#79・#85）を繰り返さないため。

## 機能要件と受け入れ基準

### 機能要件

- FR-01：GitHub Actions のワークフローを `.github/workflows/` に足し、Python のテスト（`pip install -e '.[dev]'` のあと `pytest -q`）を流す。
- FR-02：同じワークフローで、拡張のテスト・型検査・ビルド（`npm ci` のあと `npm test`・`npm run typecheck`・`npm run build`、`working-directory: vscode`）を流す。
- FR-03：動く契機は、main に入れる PR と、main への push（Q-3 で決める）。
- FR-04：ワークフローは秘密を使わず、権限は `contents: read` だけにする。SDK を呼ばず、`ANTHROPIC_API_KEY` などの環境変数も渡さない（利用料がかからない）。
- FR-05：`pull_request_target` を使わない。外から出された PR のコードを書き込み権限つきで流さない。
- FR-06：使うアクションと、Python・Node の版を固定する（固定の仕方は Q-5）。版は `pyproject.toml` の下限と `engines.node` に合わせる。
- FR-07：同じ PR や同じ枝で続けて push されたら、古い実行を取り消す（`concurrency`）。
- FR-08：`docs/development/workflow.md` の「5. 終える」と `.claude/skills/pipe-in/SKILL.md` に、「main に入れる前に CI（または手元の全テスト）が通っていることを確かめる」手順を足す。main の作業フォルダでの `git merge --ff-only` の前に、PR の CI の結果か、手元で全テストを流した結果を見る。
- FR-09：Dependabot の PR（`.github/dependabot.yml` が出す）にも同じ CI が流れ、ビルドの確認が前の「ビルドが通るかを確かめてから入れる」に代わって機械で見える。
- FR-10：CI の説明を文書に書く（何を流すか・流す版・秘密を使わないこと・落ちたときの見かた・手元で同じものを流す方法）。

### 受け入れ基準

- D0052-AC-01：`.github/workflows/` にワークフローが 1 つ以上あり、`on:` に `pull_request` と、main への `push` がある。（tests/test_ci_workflow.py）
- D0052-AC-02：ワークフローに `pytest -q` を流すステップがあり、その前に `pip install -e '.[dev]'` がある。（tests/test_ci_workflow.py）
- D0052-AC-03：ワークフローに、`vscode` で `npm ci`・`npm test`・`npm run typecheck`・`npm run build` を流すステップがある。この順で、`npm ci` が最初。（tests/test_ci_workflow.py）
- D0052-AC-04：ワークフローの `permissions` が `contents: read` だけである（ワークフローの先頭か、すべてのジョブに書いてある）。`write` を含む権限が無い。（tests/test_ci_workflow.py）
- D0052-AC-05：ワークフローに `pull_request_target`・`secrets.`・`ANTHROPIC_API_KEY` が出てこない。（tests/test_ci_workflow.py）
- D0052-AC-06：ワークフローで使う `uses:` のアクションが、固定した形（Q-5 の決めた形）で書かれている。浮いた版（`@main`・`@master`）が無い。（tests/test_ci_workflow.py）
- D0052-AC-07：Python の版が `pyproject.toml` の `requires-python` の下限を満たし、Node の版が `vscode/package.json` の `engines.node` を満たす。どちらかを変えたら、この検査が落ちる。（tests/test_ci_workflow.py）
- D0052-AC-08：ワークフローに `concurrency` があり、`cancel-in-progress` は PR の実行のときだけ真になる式（`${{ github.event_name == 'pull_request' }}`）で、main への push の実行は取り消さない（人の答え P-5）。（tests/test_ci_workflow.py）
- D0052-AC-09：`docs/development/workflow.md` の「5. 終える」に CI の結果を確かめる手順があり、`.claude/skills/pipe-in/SKILL.md` の「main に入れるよう言われたら」にも同じ趣旨がある。文言は `tests/test_rules.py` か `tests/test_skill_tidy.py` の並びで検査する。（tests/test_ci_workflow.py）
- D0052-AC-10：`docs/development/workflow.md` と `docs/guide/` の該当する文書（`docs/guide/develop.md`）に、CI が流すもの・秘密を使わないこと・手元で同じものを流す方法が書いてある。（tests/test_ci_workflow.py）
- D0052-AC-11：ワークフローのコマンドが、`CLAUDE.md` の「コマンド」と食い違わない（`pytest -q`、`npm ci`、`npm test`、`npm run typecheck`、`npm run build`）。（tests/test_ci_workflow.py）
- D0052-AC-12：古い形の扱い。`.github/workflows/` が無かった頃の PR・ブランチには影響せず、ワークフローを足しても `pipeline.toml`・`pipe.toml`・`state.json`・pipe-in の置き場所は変わらない（変えていないことを、`git diff --name-only main...HEAD` が `.github/`・`docs/`・`.claude/skills/`・`tests/`・`CLAUDE.md` の中だけであることで示す）。（tests/test_ci_workflow.py。変えたファイルが範囲の中だけなのは、検証の段で git status で確かめた）
- D0052-AC-13（実機）：この変更の PR を GitHub に出すと、ワークフローが動き、Python と拡張のジョブが緑になる。（まだ。この変更の PR を GitHub に出してから確かめる）
- D0052-AC-14（実機）：わざと落ちるテストを入れた PR で、チェックが赤になる（確かめたら PR は閉じる。main に入れない）。（まだ。この変更の PR を GitHub に出してから確かめる）
- D0052-AC-15（実機）：フォークからの PR で、ワークフローが秘密と書き込み権限なしで動く（実行ログの `GITHUB_TOKEN Permissions` が Contents: read だけ）。（まだ。この変更の PR を GitHub に出してから確かめる）
- D0052-AC-16（実機）：全体の所要時間が、決めた上限（Q-2 の案の見積もりより長くならない。設計で測って決める）に収まる。（まだ。この変更の PR を GitHub に出してから確かめる）

## 決めたことと理由

### 人が決めたこと（要件定義と設計で聞いた点）

- **CI を足し、Python の `pytest -q` と、拡張の `npm ci`・`npm test`・`npm run typecheck`・`npm run build` を全部流す**（Q-1・Q-2）。確認用ページ（`npm run preview`）は流さない。公開リポジトリなので、GitHub Actions の利用料はかからない。**これは D0002 の「守らせ方はテストまで。CI（GitHub Actions）は足さない」を改める決め**。D0002 の本文は、そのときの判断として書き換えない。
- **契機は main への PR と main への push**（Q-3）。
- **ブランチの保護（CI を必須のチェックにする）は、CI が緑になってから人が GitHub の設定でする**（Q-4）。リポジトリのファイルでは変えられない。手順は `docs/development/workflow.md` の「6. CI」に、PR を必須にする場合としない場合の両方を書いた（P-4）。
- **アクションはコミットの SHA で固定し、後ろに版のコメントを付け、Dependabot に `github-actions` を足して更新を知らせる**（Q-5）。使うのは `actions/checkout` v7.0.1・`actions/setup-python` v7.1.0・`actions/setup-node` v7.1.0 で、SHA はメインが公式のリポジトリのタグ（`git ls-remote`）で確かめた。
- **OS は Ubuntu 24.04 だけ、Python 3.11・Node 22**（Q-6。`pyproject.toml`・`vscode/package.json` の下限と同じ）。Windows は手元で通るかを確かめてから決める。
- **古い実行を取り消すのは PR の実行だけ**（P-5。設計の推しと違う答え）。main への push の実行は取り消さず、入ったものごとに結果を残す（並列のセッションが次々に入れるので、どれで赤になったかを見分けるため）。
- **YAML を読むのに PyYAML を足さない**（P-1）。テストのファイルに小さな読み手を置き、範囲の外の書き方は例外にして読み違えを防ぐ。依存を増やさず、CI が `.[dev]` だけで動く。
- **`/pipe-in` のスキルの「main に入れる」行に、PR があればその CI が緑か、無ければ手元の全テストを見る、を足す**（P-2。同じ行を縮めて、合計の上限 18,000 字に収めた。17,987 字）。
- **CLAUDE.md に CI の 1 文を足す**（検証のあとの監査 A-03・文書係の案を、人が承認した）。

### 聞かずに決めたこと

- 秘密・書き込みの権限・SDK は使わない。権限は `contents: read` だけで、`pull_request_target` は使わない。checkout は資格情報を残さない（`persist-credentials: false`）。外から出された PR でも安全に動く形にした（公式の文書の推奨とも合う。助言 V-04）。
- ジョブは `python` と `extension` の 2 つを並べる。名前はブランチの保護の必須のチェックになるので固定した。
- タイムアウトは `python` 20 分・`extension` 10 分の見積もり（測っていない）。最初の実行で測って直す（監査 A-07）。
- キャッシュ（pip・npm）は最初は使わない。
- CI のインストールは `python -m pip install` と書く（文書の `pip install` と書き方が違うが、同じこと。監査 A-06 はそのままにした）。
- Claude Code の「Auto-fix pull requests」（PR を見張って CI の失敗に自動で直しを push する仕組み）は使わない。「人に言われるまで push しない」「直すのは人が承認した項目だけ」の決まりと合わないため（助言 V-03）。

### 既存のテストを変えた理由

変えていない（`tests/test_ci_workflow.py` を足しただけ。読む補助は `tests/test_skill_tidy.py` の関数を import して使う）。

### 受け入れたリスク

1. **CI が通るかは、GitHub の上で流すまで分からない**（AC-13〜16）。読みでは、git を使うテストは一時フォルダで用意し、時計は差し替えているので通る見込み。本物の子プロセスや HTTP を使う 3 つのテスト（`test_live_watch_cli`・`test_live_answer_cli`・`test_video_review`）は、遅い入れ物で揺れるかもしれない。
2. **ブランチの保護を人が設定するまでは、CI が赤でも main に入れられる。**
3. **アクションの SHA は手で更新する**（Dependabot が知らせる）。

### 確かめていないこと

- AC-13〜16（実機）：この変更の PR で CI が動いて緑になるか、わざと落とした PR で赤になるか、外からの PR で権限が読むだけになるか、所要時間。
- Windows で全部のテストが通るか。

## 対象外・残った課題

- リリースやデプロイの自動化、SDK を呼ぶテスト、Dependabot の自動マージ、lint や網羅率、GitHub Actions 以外の CI。
- ブランチの保護の設定そのもの（人が GitHub の画面でする）。
- Windows のジョブ。キャッシュ。タイムアウトの見直し（最初の実行のあと）。

## 確かめたこと

- テスト先行：`tests/test_ci_workflow.py` の 19 件が、期待した理由（`ci.yml` が無い・文書に語が無い・Dependabot に github-actions が無い）で落ちることを確かめた。
- 検証（1 回で合格）：`pytest -q -p no:cacheprovider` は、この記録を待つ 1 件のほか 11639 件が通った（この記録を書いて通る）。拡張のコードは変えていないので、拡張のテストは流していない。
- `ci.yml` を読み、権限は `contents: read` だけ、`pull_request_target`・`secrets.`・API キーが無いこと、checkout が資格情報を残さないこと、アクション 3 つが 40 桁の SHA で固定されていることを確かめた。
- 公開してよいか：変えたファイルに、秘密・ユーザー名の入った絶対パス・メールアドレス・`docs/pipeline/` の中身は無い。
- 文書係（検証のあと）：直す文書は無かった。案の CLAUDE.md の 1 文は、人が承認して入れた。
- 矛盾監査（7 件）：人が承認して、A-04（スキルの行に PR が無いときの扱い）・A-05（`develop.md` を `pytest -q` に）は直したが、その行は前の版の README から残すことを既存のテスト（D0014-AC-12）が求める行だったので元に戻し、A-03（CLAUDE.md）を入れた。A-01（D0002 を改める）・A-02（この記録）・A-07（タイムアウト）はこの記録に書いた。A-06 はそのまま。
- 公式の文書と照らした助言（4 件）：V-01・V-02（「CI が緑か」の前提）は A-04 の直しで解いた。V-03 は上の「聞かずに決めたこと」に書いた。V-04 は問題なし。
- 審査（助言の報告の採点）：overall 0.75・verdict pass（5 項目とも 0.75）。V-02 の根拠が公式の文書でなくリポジトリの推論だったことなどで下がった。
