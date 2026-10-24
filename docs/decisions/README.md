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
| [D0034](D0034-first-run-watch.md) | work_dir がまだ無いプロジェクトでも、最初の実行でパネルとステータスバーが進む（拡張が約 3 秒ごとに `stat` で有無だけを確かめ、できたら見張りを張って読み直す。消えたら外す。拡張は work_dir を作らない） |
| [D0035](D0035-build-judge.md) | プラグインの pipe-build と `pipe-in-gen design` で、検査と審査の段を組めるようにする（`references/stage-rules.md`・ひな形 diagrams の例） |

## ひな形

ファイルの名前は `Dnnnn-<英小文字・数字・->.md`。番号は上の表の次。足したら上の表にも1行足す。

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
