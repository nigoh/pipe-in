# D0045 確認待ちになったら知らせる

## 目的

`/pipe-in` や `pipe-in` の実行が人の確認を待って止まったことに、パネルやステータスバーを見に行かなくても気づけるようにする。D0024 で先送りにした「通知（#14）」を扱う。

## D0024・D0039 から置き換える点

D0024・D0039 は書き換えない。次の2点だけを、この記録が置き換える。

- D0024-AC-26「設定の鍵は4つ」→ `pipe-in.notifyWhenWaiting` を足した5つ。`vscode/src/manifest.test.ts` の同じ検査も5つに直した（コマンドは2つのまま）。理由：この機能の要件で設定が1つ増えるため。
- D0039-AC-11「SKILL.md と補助ファイルの合計は 17,500 字以下」→ 17,800 字以下（`tests/test_skill_tidy.py`。SKILL.md の 12,300 字は変えない）。理由：main に入った D0044（`--artifact` の手順の追加）で合計が 17,496 字になり、この記録の決まり（約 260 字）が入らなくなった。決まりの文を削るより上限を上げると、人が決めた。

## 機能要件と受け入れ基準

- FR-01 VSCode の拡張は、一覧の行が新しく確認待ちになったときに、知らせ（`showInformationMessage`）を1回出す。
  - D0045-AC-01・D0045-AC-02・D0045-AC-03・D0045-AC-04・D0045-AC-05・D0045-AC-06・D0045-AC-07 判断は `domain/waitingNotice.ts` の純粋な関数 `newlyWaitingKeys`。前に無い／確認待ちでなかった行だけを返す。確認待ち → 動く → 確認待ちならもう一度返す。`archive/` と終わった行は返さない。基準が無い（開いた直後）なら返さない。別の worktree の行も返す。壊れた入力でも例外を出さない。
  - D0045-AC-08・D0045-AC-09 文は `view/waitNotice.ts`。1件は「<セッション名>（<段>）が確認待ちです」、2件以上は件数だけ。外から来た文字は `plainLine` で1行のプレーンな文字にする。
  - D0045-AC-10・D0045-AC-11・D0045-AC-12・D0045-AC-13 ボタンは「実行を見る」だけで、押すと既存の `pipe-in.showRun` を実行する。設定 `pipe-in.notifyWhenWaiting` が false なら出さない（型が違う値は既定の true）。パネルで見ている実行は外す。
  - D0045-AC-14・D0045-AC-15・D0045-AC-16 知らせは `render()` の本体の外の `notifyWaiting` から出す（D0024-AC-15 は変えずに通る）。`retarget()` で基準を捨て、古い世代の読み込みでは何もしない。ステータスバーの色・コマンド・メッセージの種類・CSP は変えない。
  - D0045-AC-17・D0045-AC-18・D0045-AC-19・D0045-AC-20 設定の鍵は5つ。前の名前の節の設定も読む。新しい部品は `vscode` もファイルも時計も使わず、基準は拡張のメモリだけ（`workspaceState` に書かない）。本体・記録・3つのガードは変えない。
- FR-02 `/pipe-in` スキルは、`record wait` を書くときと `--auto` でも止まって聞くとき、人に聞く前に PushNotification で知らせる。
  - D0045-AC-21・D0045-AC-22・D0045-AC-23 `SKILL.md` の「必ず守ること」に1行、`record.md` に文の決まり（段の名前と固定の言葉だけ・要件メモ・パス・秘密を入れない・`--auto` で止まらずに進むところでは知らせない）。ツールが無い会話では何もしない。
  - D0045-AC-24（手で）知らせが届くこと。
- FR-03 Claude Code の Notification フックは足さず、Claude Code 自身の通知の設定を案内する。
  - D0045-AC-25・D0045-AC-26・D0045-AC-27 `docs/guide/develop.md` に `preferredNotifChannel`（`/config` の「Local notifications」）の案内とフックを足さない理由。`.claude/settings.json` の `hooks` は `PreToolUse` と `Stop` のまま。
- FR-04 文書をそろえる。
  - D0045-AC-28・D0045-AC-29 `docs/guide/vscode.md`・`vscode/README.md`・`docs/guide/develop.md`。
  - D0045-AC-30・D0045-AC-31（手で）・D0045-AC-32（実機）2つの worktree での知らせ・出さない場合・実際の `/pipe-in`。

## 決めたことと理由

- **手段は3つ。** 拡張の知らせ（VSCode を開いている人）、スキルの PushNotification（デスクトップの通知。Remote Control がつながっていればスマホにも届く）、Claude Code 自身の通知の案内（端末で流す人）。
- **開いた直後にすでにある確認待ちは知らせない。** 件数はステータスバーで見える。開くたびに出ると邪魔になる。
- **パネルで見ている実行は知らせない。** もう目の前にある。
- **Notification フックは足さない。** フックの標準出力は端末に出ず（公式の文書では、ほとんどのイベントで debug のログに行く）、鳴らすには `terminalSequence` が要る。組み込みの `preferredNotifChannel` で足り、重なる。利用者のプロジェクトにも配らない。
- **スキルの知らせは拡張の設定では切れない。** 別の仕組みで、文に手元の情報を入れないので、切る設定は足さない。
- **依存は足さない。** 拡張が書く場所も増えない。

## 対象外・残った課題

- 音・OS の通知コマンド・ステータスバーの色、確認待ち以外（失敗・終了）の知らせ、再通知と履歴、`pipe-in live` での知らせ。
- 別の worktree の記録を一度読み損ねてから戻ると、同じ確認待ちを2回知らせることがある（まれなので受け入れる）。
- PushNotification があること・働き（デスクトップの通知。Remote Control がつながっていればスマホへも）・許可が要らないことは、公式の文書（tools-reference）で確かめた。引数（`message`・`status`）はツールの説明で確かめた（公式の文書には載っていない）。Bedrock・Vertex などではスマホに届かない。
- スキルの知らせはスキルの指示で出すので、フックのように決まった動きではない。本筋は記録と拡張の知らせで、PushNotification は補助。
- スマホに知らせる Claude Code の設定 `inputNeededNotifEnabled` は、型と既定を確かめていないので、まだ案内していない（助言 V-03）。
- `/config` の画面での「Local notifications」の見え方は、実機では確かめていない。

## 監査と助言

- 人が承認して直した項目：監査 A-01（design.md の「`notifyWaiting` だけ」を実物に合わせた）・A-02（スキルの知らせのきっかけを `--auto` で止まって聞くときにも広げ、段でないときの文の形を書いた）・A-03（テストの ID とコメント）・A-04（`vscode/README.md` の設定の表に `pipe-in.pipesDir` を足した）。助言 V-01・V-02（確かめた範囲とスマホに届く条件）・V-04（PushNotification は補助）・V-05（フックは組み込みの通知と並んで動く。各自の設定に書ける任意の例）。文書係の案（`/pipe-help`・CLAUDE.md に1行ずつ）も入れた。
- 直さなかった項目：助言 V-03（`inputNeededNotifEnabled` の案内。型と既定を確かめていない）。
- 審査（助言の報告の採点）：overall 0.95・pass（網羅性 0.75。PushNotification が使える条件の確かめが抜けていた）。

## 確かめたこと

- `npm --prefix vscode test`・`npm --prefix vscode run typecheck`・`pytest -q`。
- 手で（AC-24・30・31）：AC-24 はこの機能を作った会話で、段の区切りごとに PushNotification を送った（届いたかは人が見る）。AC-30・31 はまだ。
- 実機（AC-32）：まだ。
- main を取り込んだとき、main に D0043（指摘の形）と D0044（ページから答える）が先に入っていたので、この記録を D0043 から D0045 に付け替えた（AC の ID・テストの名前・文書の参照も合わせた）。
