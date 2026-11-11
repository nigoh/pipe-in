# 決定の記録

機能ごとに、何を作り、何をなぜ決めたかを1つのファイルに残します。書き方は [../development/specs.md](../development/specs.md) の「決定の記録」にあります。

| 記録 | 題 |
| --- | --- |
| [D0001](D0001-plugin-pipe-build.md) | パイプを会話で作る・直すプラグイン（/devpipe:pipe-build と pipe-builder）と、対象の .devpipe/pipes/ |
| [D0002](D0002-dev-rules.md) | 開発のルール（docs/development/）と、それを守らせるテスト |
| [D0003](D0003-rebase-on-main-change.md) | main が進んだら、機能のブランチを載せ直す |
| [D0004](D0004-pipe-in-guard-worktree.md) | /pipe-in のサブエージェントが、報告を返し、worktree の中でも書けるようにする |
| [D0005](D0005-judge-switch.md) | 作業台の判定をスイッチで入り切りし、自分をやり直す判定はケーブルを描かずに札で示す |
| [D0006](D0006-rename-pipe-in.md) | 製品の名前を pipe-in に変える（前半：製品） |
| [D0007](D0007-cable-physics.md) | コンセントの上で離しても差さる・流線型のケーブル・引くときはひものように動く |
| [D0008](D0008-audit-advisor.md) | 読むだけの矛盾監査とアドバイザー（/pipe-audit・/pipe-advise と /pipe-in の検証のあと） |
| [D0009](D0009-readme-screens.md) | README を分かりやすく作り直し、動いている画面とロゴを載せる |
| [D0010](D0010-ui-records.md) | 作業台と実行パネルの初めの形と、読み取れる理由（あとから書く記録） |
| [D0011](D0011-video-pipe.md) | 人と確かめながら紹介動画を作るパイプの見本（examples/video）と、ボタンで答える手元の受付 |
| [D0012](D0012-headless-audit.md) | 会話を開かずに /pipe-audit・/pipe-advise を流す呼び方（claude -p）を決め、文書とテストで守る |
| [D0013](D0013-plug-logo-motion.md) | プラグのロゴの動きを、一拍おいて全体から寄るカメラと、上から差す立体のプラグにする |
| [D0014](D0014-readme-guide.md) | README を入口にし、くわしい説明を docs/guide/ に移す |
| [D0015](D0015-rubric-judge.md) | 調べもの型の報告を、1つの審査役がルーブリックで採点する（pipe-in-judge・/pipe-judge と /pipe-in の助言のあと） |
| [D0016](D0016-sendback-reasons.md) | 差し戻しと修正の依頼の理由を、図の節を選んで見られるようにする |
| [D0017](D0017-live-flow.md) | 実行の図で、動いている様子と各段の時間をリアルタイムで見られるようにする（アニメーション・経過時間） |
| [D0018](D0018-research-docs.md) | 調べた結果を docs/research/ に残す（最初は eval と LLM as judge の比較） |
| [D0019](D0019-run-list.md) | 実行パネルを Web アプリの形にし、並列・別の worktree・前の実行をセッション名で選べる一覧と、時系列・図の拡大縮小を足す |
| [D0020](D0020-docs-sync.md) | 何かを変えたら文書もそろえる（文書係 pipe-in-documenter・/pipe-docs・止まるときの知らせ） |
| [D0021](D0021-stale-runs.md) | 段のログが決まった時間更新されない「動いている」実行に、実行パネルの図・一覧・詳細・時系列で「⚠ 更新なし」の印を出す（設定 `pipe-in.staleAfterMinutes`） |
| [D0022](D0022-plugin-judge.md) | プラグインで成果物を検査・審査する（/pipe-in:pipe-eval・/pipe-in:pipe-judge と審査役 pipe-judge・pipe-in-gen judge-score） |
| [D0023](D0023-readme-media.md) | README の冒頭のロゴを動くロゴ（明暗の GIF。動きを減らす設定では止まったロゴ）にし、「すぐ試す」に本物の VSCode の中の画面と使い方の動画（明暗の GIF）を載せる |
| [D0024](D0024-status-counts.md) | ステータスバーに、並列で動いている実行と確認待ちの件数を出す。別の worktree の行があるあいだはパネルを閉じても約5秒ごとに読み直し、ボタンは確認待ちの実行を先に出す |
| [D0025](D0025-artifact-preview.md) | 実行パネルの「成果物」タブを、左に成果物の一覧・右に中身のプレビューの形にする（Markdown を許すタグだけの HTML に直す。1 つにつき先頭 256 KiB・合計 4 MiB までの上限つきで読み、symlink は読まない） |
| [D0026](D0026-sdk-buffer.md) | 段が大きい画像を Read しても落ちないようにする（SDK の受信バッファの上限 `[pipeline] max_buffer_mb`、既定 32MB。超えたら段の失敗にして直し方を出す） |
| [D0027](D0027-live-artifact.md) | Claude のアーティファクトで進み具合を見る（`pipe-in live snapshot`・`pipe-in live page` と `/pipe-in --artifact`。写しには要件メモの本文・セッション ID・パス・自由な文を入れない。見るだけ） |
| [D0028](D0028-check-judge.md) | 段の検証で、ルーブリックの審査から合否をエンジンが出す（`[stages.check.judge]`。must の違反は即不合格・作業台は judge を消さない） |
| [D0029](D0029-pipe-plan.md) | 計画ボード（`/pipe-plan`）：ロードマップの段階ごとに、できたこと・手で確かめること・やる予定・やりたいことを Claude のアーティファクトで並べ、GitHub のイシューと決定の記録に合わせる |
| [D0030](D0030-brand-plug.md) | ブランドを「プラグ」（今のロゴのコーラルとティール）に決め、画面のデザインの土台（部品と画面の見本、明暗の色の決まり）を `docs/design/` に残す |
| [D0031](D0031-live-watch.md) | ターミナルで流す pipe-in の進み具合もアーティファクトで見る（`pipe-in live watch` が記録を見張り、プラグインのスキル `/pipe-in:pipe-live` が Monitor で受けて写しを書く。見るだけ） |
| [D0032](D0032-guard-fail-closed.md) | サブエージェント用のフック（`pipe_in_guard.py`）が例外や想定外の入力で落ちても、pipe-in-* の呼び出しは止める側に倒す（入口を囲み、書けないときは終了コード 2。止める表と許す表は変えず、例外と型のおかしい `agent_type` では止める側に広げる） |
| [D0033](D0033-sdk-buffer-rest.md) | パイプと pipe-in-gen design でも、SDK の受信バッファの上限（D0026 の `max_buffer_mb`）を超えたら止める（パイプは終了コード 3。差し戻しもグループの後の段もしない。pipe-in-gen design はやり直さずに案内を出して終了コード 1。古い版で 1048576 bytes のトレースバックが出たら入れ直す） |
| [D0034](D0034-first-run-watch.md) | work_dir がまだ無いプロジェクトでも、最初の実行でパネルとステータスバーが進む（拡張が約 3 秒ごとに `stat` で有無だけを確かめ、できたら見張りを張って読み直す。消えたら外す。拡張は work_dir を作らない） |
| [D0035](D0035-stage-agent-guard.md) | 段の中のサブエージェントの呼び方を守る（裏で動かす形・入れ子を止め、1回の実行で呼べる数に上限 `max_agent_calls`、既定 20。超えたら止めて理由を返すだけ） |
| [D0036](D0036-bash-write-guard.md) | 段の Bash による書き込み（リダイレクト・tee・sed -i・cp・mv・touch・python -c など）を、段の書き込み範囲で止める。先が読めなければ止める。サンドボックスではない |
| [D0037](D0037-build-judge.md) | プラグインの pipe-build と `pipe-in-gen design` で、検査と審査の段を組めるようにする（`references/stage-rules.md`・ひな形 diagrams の例） |
| [D0038](D0038-pipe-lessons.md) | パイプを流して分かったこと（置き場所が要る段は docs、テストを書く段もあとの検査を流す、差し戻しは直せる段へ など）を、pipe-build のスキルと `pipe-in-gen check` の警告（`⚠`。誤りにはしない）に入れる |
| [D0039](D0039-skill-tidy.md) | /pipe-in のスキルを、長い会話でも決まりが残る形に整える（冒頭の決まり・補助ファイル 3 つ・許可の規則・前の名前の残り） |
| [D0040](D0040-live-watch-windows-pipe.md) | Windows でも、標準出力が閉じた `pipe-in live watch` が静かに終了コード 1 で止まる（標準出力の書き込みの `OSError` を errno を問わず受け、閉じたのか書けないのかで文を分ける。付け替えられないときは `sys.stdout` を外す） |
| [D0041](D0041-agent-limits.md) | 監査・助言・審査のサブエージェントの定義に回数の上限（`maxTurns` 100・80・50）を付け、会話を開かずに流す監査・助言の呼び方に `--disallowedTools "mcp__*"` を足して MCP の道具も見せない（D0012 の呼び方の2行を置き換える） |
| [D0042](D0042-pipe-plan-run.md) | 計画ボードのカードの「実行」から、確認を経て新しいセッションを作り `/pipe-in` を始める（ページが宣言する道具を `list_sessions` 1つから3つに。D0029 の「読むだけ」を置き換える） |
| [D0043](D0043-finding-schema.md) | 仕様書レビューの指摘を決まった形（指摘の形 v1。Schema は `generator/schemas/`）で受け渡し、形・出典・引用の一致（NFKC と空白を除いて比べる）・役割ごとの決まりを `pipe-in-gen findings-check` で LLM を呼ばずに検査する（終了コード 0・1・2） |
| [D0044](D0044-live-answer.md) | 進み具合のページの確認待ちの行に、承認・差し戻し・中止のボタンを出す（コメントの機能で決まった形の文を送り、会話が `pipe-in live answer` で読んでから記録する。`/pipe-in --artifact` だけ） |
| [D0045](D0045-plugin-evals.md) | プラグイン自身の eval のケースを `plugin/evals/` に 9 本置く（`claude plugin eval` 用。費用のかからない採点が中心で、`pytest` はファイルの形だけを見る。流すのは人に言われたときだけ） |
| [D0046](D0046-wait-notify.md) | 確認待ちになったら知らせる（拡張の知らせと設定 `pipe-in.notifyWhenWaiting`・`/pipe-in` の PushNotification・Claude Code の通知の設定の案内。D0024-AC-26 の設定の鍵を5つに） |
| [D0047](D0047-spec-review-template.md) | 仕様書レビューのパイプのひな形 `spec-review` を足す（素人の質問 → 知識の下ごしらえ → 6つの検査を同時に → 根拠の確認（`findings-check`）→ まとめと質問票。指摘は D0043 の形 v1） |
| [D0048](D0048-worktree-auto.md) | worktree を自動で切って、main に入ったら自動で片付ける（pipe-in worktree new・clean） |
| [D0049](D0049-skill-shell.md) | /pipe-in が打つシェルのコマンドを、確認なしで通る形にまとめる（pipe-in skill・worktree sync） |
| [D0050](D0050-run-tools.md) | 実行の詳細に「エージェント・スキル」のタブを足し、選んだ実行で使ったエージェント・スキル・道具の名前・種類・回数・使った段を表で見られるようにする（拡張が段のログを数えるだけ。本体と記録の形は変えない） |
| [D0051](D0051-stage-budget.md) | 実行の図の段の節に、費用を上限と比べた金額の対・棒・言葉（余裕・上限に近い・上限を超えた・上限で止まった）を出し、使用量のタブに段ごとの費用の表を足す（上限は本体が `runs[]` に残す。0 より大きい数でない上限は流す前に止める） |
| [D0052](D0052-ci-check.md) | main への PR と main への push で、GitHub Actions の CI が Python と拡張のテスト・型検査・ビルドを流す（権限は読むだけ・秘密なし・アクションは SHA で固定。D0002 の「CI は足さない」を改める） |
| [D0053](D0053-harness-lessons.md) | 段の組み方（ハーネス）の比較実験で分かった目安を、pipe-in-gen design の設計の決まり・pipe-build の stage-rules.md・パイプのガイドに入れ、指摘を出す段に引用の指示も findings-check も無いときの警告 W6 を足す（プラグインは 0.5.1） |
| [D0054](D0054-spec-review-source-kinds.md) | ひな形 spec-review の知識の段に、出典の台帳の `kind` に使える6つの値と振り分けを書き、`SOURCE_KINDS`・Schema と食い違わないことをテストで守る（D0047 の実機で見つかった不具合の直し） |
| [D0055](D0055-dependabot-types-node.md) | Dependabot に `@types/node` の大きい版の上げを出させない（拡張が動く Node の版に合わせておく型。小さい版は出す） |
| [D0056](D0056-pipe-talk.md) | 壁打ちのスキル `/pipe-talk` を足す。区切りで要点（決まったこと・残った問い・やりたいこと）をまとめ、次の作業（issue・デザイン・`/pipe-in`・計画ボード）の候補を出す。外へ出す操作は中身を見せて承認を得てから。要約は手元だけの `docs/talk/`。`ask` に `gh issue create` を足す |
| [D0057](D0057-ask-question.md) | 人に確認・質問・承認を求めるときは、質問欄（AskUserQuestion）で聞く決まりを CLAUDE.md の「必ず守ること」に足し、開発用の7つのスキルの人に聞く所から指す。質問欄が使えない会話では、番号つきの選択肢と推しを添えて会話の文で聞く |
| [D0058](D0058-pr-issue-format.md) | PR と issue の形をそろえる。PR のテンプレート（6つの節と Mermaid の図の見本）と、不具合・機能の要望の issue forms を `.github/` に置き、決まりを workflow.md の「7. PR と issue」に書き、/pipe-in の仕上げで PR の本文の案を見せる |
| [D0059](D0059-live-page-design.md) | 進み具合のページ（`/pipe-in --artifact`・`pipe-in live watch`）に、デザインの土台（ブランド「プラグ」）を入れる。色のトークン・書体・Lucide のアイコン・帯と札・カード。外部の読み込みは書体の `<link>` 2本と SVG の名前空間だけを許す。振る舞いは変えない |
| [D0060](D0060-live-page-rules.md) | 進み具合のページで、「N回目」を2回目から出し（板 S3 に合わせる）、「HH:MM 更新」を見ている人の時刻帯で出す。札の表示名が 80 文字で切れることをテストで固定する（閉じた PR #104 にだけあった決まりを移した） |
| [D0061](D0061-check-parity.md) | 作業台の検査（`validatePipe`）と `pipe-in-gen check` の結果がずれないように、同じ見本を両方に掛けて確かめる。ずれを直し、決まりを足すときは両方を直すことを文書に書く |
| [D0062](D0062-run-judge-view.md) | パイプの判定とやり直し（on_fail）を実行の図に出す。記録に `stages[].check` と検証の `attempt` を足し、図に判定の節・札・「N / 上限 回」・戻りの矢印・節を選んだときの欄を足す |
| [D0063](D0063-run-parallel-frame.md) | 並列の枠を実行の図に出す。記録に `stages[].group` を足し、図に枠・枠の中の段ごとの状態・節を押して選ぶログを出す。動いている段のログが先に済んだ段に落とされる不具合も直す。 |
| [D0064](D0064-wait-notice-open.md) | 確認待ちの知らせは「実行を見る」のままにし、開いたパネルの確認待ちの知らせに、確かめる文書を開くボタンと答え方を出す（#98。D0046 の残り）。 |
| [D0065](D0065-editor-reload.md) | 外で書き換わったパイプを、開いたままの作業台が読み直す。保存していない変更が無ければそのまま、あれば帯で選ばせ、取り込む前の形を版（`-external`）に残す（#17）。 |
| [D0066](D0066-cost-estimate.md) | 流す前に費用の目安（少なめ〜多め）を出す。段の数・モデル・ターンの上限・やり直しの上限から計算し、前の実績があれば別の欄で並べる。CLI（`pipe-in estimate`・本流の確認前）と作業台の「費用の目安」の節で見られる。単価は仮の値（#22）。 |
| [D0069](D0069-pipe-after.md) | パイプの成果物を次のパイプへ渡す（`--after <名前>`）。前が PASSED の記録だけを受け、全段の成果物の場所を後ろの各段に渡し、受けた元を `state.json` の `received_from` に書く。後ろの段は前の記録を書けない（#101）。 |
| [D0070](D0070-example-pipes.md) | 見本のパイプ集（図を作る・仕様とソースの突き合わせ・調べものをまとめる）を `examples/` に置き、作業台の「見本から作る」で下書きとして写せるようにする（#25）。 |
| [D0071](D0071-record-order-check.md) | 記録の順序の検査（`pipe-in record check`）。承認の前に次の段の `begin` が書かれていないかを、`state.json` と段のログから読むだけで確かめる。`review` の要素に時刻 `at` を足し、本体に残る `/pipe-dev` の言い方を `/pipe-in` に直す |
| [D0072](D0072-english-docs.md) | 初めての人向けの案内（VSCode の walkthrough）とコマンドを打たない人向けの文書を足し、`README.en.md`・`vscode/README.en.md` を並べて置く。食い違い（見出し・コードの塊・コマンド・画像・リンク）は `tests/test_english_docs.py` で止める（#26）。 |
| [D0073](D0073-unattended-run.md) | 人が開始の指示で commit・push・PR の作成を承認した無人の実行では、その枝への commit・push と PR の作成を確認で止めない。`ask` から `git commit`・`git push`・`gh pr create` を外し、main へ届きうる push の形を足す。main の本当の関所は GitHub のブランチ保護。手順は `.claude/skills/pipe-in/unattended.md` |
| [D0074](D0074-merge-unit.md) | merge の単位を「main 向けの PR 1つ」にそろえる。夜のまとめ実行は1本の `night/<日付>` の枝に件ごとの1コミットを早送りで積み、単独の機能は main から切って積まない。`worktree new`・`sync`・`clean` は土台を origin から取り、取れなければ止まる（`--no-fetch`）。決定の記録の番号は `skill decision-number` で取る。スキルの補助ファイルの字数は、合計をやめて1つずつ 3,500 字にした。 |
| [D0075](D0075-doc-shape.md) | 並列の作業でぶつかる文書とテストの形を、書き足しが別々の場所に入る形に直す。決定の記録の一覧は `merge=union` と検査で守り、design.md の表は 1 部品 1 行（1 行 800 字まで）に割り、アーキテクチャの新しい検査は決定ごとの別ファイルに置き、`screen-check.md` はページの種類の頭を 1 行 1 頭で書く。秘密・手元の事情の検査は、まだ追跡していない新しいファイルも見る。 |
| [D0076](D0076-review-quorum.md) | 同じ指示の2体の指摘から、両方が同じ節に挙げた指摘だけを残す `pipe-in-gen quorum`（LLM を呼ばない）と、ひな形 `review-quorum` を足し、比較実験 R7〜R14 の目安（2体の共通部分・強いモデルでは使わない）を入れる。W5 は検査が戻り先の成果物を名指しするとき出さない。プラグインは 0.5.2 |
| [D0077](D0077-chat-run.md) | パイプを会話の中で流せる（Claude Agent SDK を子として起こせない VS Code の Claude ハーネスなど向け）。入口はプラグインのスキル `/pipe-in:pipe-run`、段の順番・確認・差し戻し・記録は `pipe-in-gen chat` が持ち、段は `pipe-stage` で流す。プラグインのフックが本体と同じ判断で段の範囲を絞り、流す前に `pipe-probe` で守りを確かめ、通らなければ流さない。使用量は「取れない」と記録し、拡張も $ の数を出さない。実機の確かめは #123 |
| [D0078](D0078-run-from-editor.md) | VSCode の作業台から、保存したパイプを流せる（#21）。拡張が子プロセスを起こしてよいのは、作業台の「流す」が Tasks API の `ProcessExecution` で起こす、決まった形の `pipe-in` 1つだけ（実行ファイルは絶対パス。引数は `--pipe=`・`--project=`・依頼メモがあるときだけ `--text=`。シェルを通さない）。流してよいかは `decideRun` が理由を決まった順で1つ返し、パネルも入口も同じ関数を使う。設定 `pipe-in.command` はユーザーの設定だけ。信頼していないワークスペースでは動かない。D0072 の「流すコマンドは足さない」を置き換える。実機の確かめはまだ |
| [D0079](D0079-reply-from-panel.md) | 実行パネルから、端末で流している `pipe-in` の確認に 承認・修正の依頼・中止 を返せる（#19・#20）。拡張が work_dir に書いてよいのは、実行のフォルダの返事のファイル `reply.json` 1つだけ（新しく作るときだけ。`vscode/src/infra/fsReplies.ts`）。読んで動くのは本体だけで、本体は標準入力が端末のとき、標準入力と返事のファイルを 0.5 秒ごとに一緒に待つ。待っているあいだだけ `state.json` に印 `reply_wait` を書く。返事の動作は `approve`・`revise`・`quit`（`record review` の `approved` とは別）。`reply.json` は段の `output` に使えない |

## ひな形

ファイルの名前は `Dnnnn-<英小文字・数字・->.md`。番号は上の表の次（ほかのブランチで使っている番号は飛ばす）。足したら上の表にも1行足す。

```markdown
# Dnnnn <何ができるようになったか>

## 目的

<誰の何が良くなるかを1〜2文で>

## 機能要件と受け入れ基準

- FR-01 <すること>
  - Dnnnn-AC-01 <入力と、期待する結果>（`tests/test_xxx.py::test_yyy`）
  - Dnnnn-AC-02（手で）<手順と、期待する結果>

## 決めたことと理由

- <選んだ形>。<選ばなかった形>より<理由>。
- <受け入れたリスク>。<どこで補うか>。

## 対象外・残った課題

- <しなかったこと・あとでやること>

## 確かめたこと

- <テストの結果の要約>
- <手で・実機で確かめたこと。確かめていないものは「まだ」と書く>
```
| [D0080](D0080-state-schema.md) | 記録（`state.json`）の費用と使用量の「無い」の書き方を、測れた・取れないの2通りに決め、3つの書き手が同じ土台（`pipe_in/engine/state.py` の `new_state`）から作る。新しい記録の最初の鍵に `schema: 1` を足す（#130）。開発用の記録の費用は「$0.000」でなく「取れない」になる |
| [D0081](D0081-flow-counts.md) | SDK の道のパイプが、段を流した回数とやり直しの回数を `state.json` の `flow` に持つ（#133）。確認で止めて `--review` で続けても、`max_steps`・`max_retries` が効く。`revise` は段を流した回数に数えない |
| [D0082](D0082-capability-table.md) | 会話の道の「断る・効かない」の判断を、項目 × 実行役の能力表（`pipe_in/pipe/capability.py`）から作る（#131）。パイプと設定の全項目が表に載り、足し忘れはテストが落とす。出す文と順番は変えない |
| [D0083](D0083-guard-matrix.md) | 4つの守り（SDK の道・会話の道・プラグイン・開発用）の、道具ごとの 許す／止める を1つの表（`tests/guard_matrix.py`）でテストに固定する。プラグインのフックは、入力が読めない・大きすぎる・止める返事を書けない・`agent_type` の型がおかしいときも、止める側に倒す（#132） |
| [D0084](D0084-default-protected.md) | SDK の道（`pipe-in`）も、`.claude/`・`.git/`・`.pipe-in/`・`pipeline.toml`・前の版の置き場所への書き込みを、設定なしでどの段でも止める（#134）。守る場所は `pipe_in/engine/spec.py` の定数1つで、会話の道も同じ定数を使う。外す設定は無い |
| [D0085](D0085-test-generator-loader.md) | テストは、開発用の入れ込みがどこにあっても、作業フォルダの `generator/` を `pipe_in_generator` として読む（`tests/gen_loader.py`。#141）。読む場所が違えば、テストの始めに直し方つきの文で落ちる |
| [D0086](D0086-mcp-json-protected.md) | 既定で守る場所に、プロジェクトの直下の `.mcp.json` を足す（#136）。SDK の道と会話の道で、どの段も書けない。`CLAUDE.md` は入れず、守りたいときは `protected_paths` に書く |
