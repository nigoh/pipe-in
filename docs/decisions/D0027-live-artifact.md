# D0027 Claude のアーティファクトで進み具合を見る（`pipe-in live` と `/pipe-in --artifact`。第1段階）

## 目的

Claude Code の会話（デスクトップアプリ・claude.ai/code）から `/pipe-in` を流す人が、進み具合を会話の横の Claude のアーティファクト（claude.ai のページ）で見られるようにする。どの段が動いている・確認を待っているか、何回目か、どれだけ時間がかかっているかを、ページが1秒ごとに数えて出す。ページは見るだけで、承認・直してほしい点・中止は、これまでどおり会話で答える。VSCode の拡張を開いていないとき（スマホの Claude アプリなど）でも進み具合が見えるようにするのがねらい。

## 機能要件と受け入れ基準

本体（`pipe_in/engine/`）に、記録から「写し」（JSON）を作るコマンド `pipe-in live snapshot` と、進み具合のページの HTML を作るコマンド `pipe-in live page` を足す。`/pipe-in --artifact` では、メインの会話がページを最初に1回だけ公開し、`record` の各コマンドのあとで写しをページのデータ（db のコレクション `runs`・ドキュメント `current`）に書く。テストの名前は `test_d0027_acNN_…`。

- FR-01 work_dir の記録（`state.json`、`logs/*.jsonl` の最初の `Prompt` 行の `at`、`pending_review.since`）から、写し（JSON）を作る純粋な関数を足す。ファイルを読む部分と、写しを組み立てる部分を分ける。
- FR-02 写しを標準出力かファイルに出すコマンドを足す。読み先のフォルダを引数で渡せる（既定は今の対象プロジェクトの work_dir）。
- FR-03 写しに入れるのは次だけ。
- FR-04 写しに入れないもの：要件メモの本文（`00_input.md`）、`session_id`、手元の絶対パス・work_dir のパス、段の要約・差し戻しの理由・feedback・エラー文などの自由な文、ログの中身。
- FR-05 セッション名・段の表示名は、制御文字を除き、長さを切る。
- FR-06 記録がどう壊れていても、例外で落ちず、決まった形の写しを返す。読めない項目は null にするか、省く。
- FR-07 写しの大きさに上限を設ける（段の数・回の数・文字の長さ）。
- FR-08 写しは同じ記録・同じ「今」なら同じ中身になる（「今」は引数で受ける。関数の中で時計を読まない）。
- FR-09 進み具合のページの HTML を作る関数とコマンドを足す。1枚で完結し、外部の読み込みは無い。
- FR-10 ページのスクリプトは `await claude.use("db")` で db を取る。null なら「この画面では読めない」旨を出す。
- FR-11 ページは写しを db から読み、HTML に埋め込まない。HTML に外から来た文字は入らない。
- FR-12 db の値は `textContent` で出し、`innerHTML` などに差し込まない。
- FR-13 db の変更（onSnapshot）で描き直す。値が欠けていても、壊れた値でも、描き直しで例外を出さない。
- FR-14 動いている段・確認待ちの経過秒は、写しの時刻と「今」から1秒ごとに数える（D0017 と同じ数え方）。隠れたらタイマーを止め、戻ったら直す。時計が戻っても負にしない。数える要素が無ければタイマーを回さない。
- FR-15 ライト・ダークの両方の配色を `:root` のトークンで持ち、`prefers-color-scheme` と `data-theme` で切り替える。
- FR-16 幅 360px でも横にはみ出さない。
- FR-17 動き（脈打ちなど）は `prefers-reduced-motion: no-preference` のときだけ。
- FR-18 `/pipe-in` のスキルに `--artifact` の手順を足す（ページを最初に1回公開する、record の各コマンドのあとで写しを作って ArtifactData の set で書く、公開し直さない）。メインが `.claude/skills/pipe-in/SKILL.md` に書く。
- FR-19 文書をそろえる：`docs/guide/` の該当ページ（記録の説明の `records.md`、使い方の入口、目次 `docs/guide/README.md`）と、`README.md` の必要な箇所に、`--artifact` の使い方と、写しに入れるもの・入れないものを書く。
  - D0027-AC-01 正常な記録（開発フローの途中の記録）から作った写しは、`schema`（整数）・`generated_at`・`name`・`final`・`stages[]`（`name`・`label`・`status`・`attempt`・`started_at`・`pending_since`・`verdict`・`cost_usd`・`turns`・`duration_sec`）を持つ。決まったキーだけで、ほかのキーは無い。（`tests/test_live_snapshot.py` の `test_d0027_ac01_*`）
  - D0027-AC-02 段の並びは `state.json` の `stages` の順で、同じ段が複数回動いたときは、段ごとに1つにまとめ、`attempt` は最後の回を持つ。（`tests/test_live_snapshot.py` の `test_d0027_ac02_*`）
  - D0027-AC-03 段の状態は次の表のとおりになる：まだ始まっていない＝`waiting`、`open` の段＝`running`、`pending_review` の段＝`review`、閉じて成功＝`done`、閉じて失敗＝`failed`、確認の結果が revise＝`revised`。（`tests/test_live_snapshot.py` の `test_d0027_ac03_*`）
  - D0027-AC-04 検証の判定が `pass` / `fail` / `blocked` のとき、`test` の段の `verdict` に入る。それ以外の値（未知の文字・型違い）は null。（`tests/test_live_snapshot.py` の `test_d0027_ac04_*`）
  - D0027-AC-05 `final`（最後の結果）は、`Exit` の名前のときだけ入る。未知の文字・型違いは null。終わっていない記録では null。（`tests/test_live_snapshot.py` の `test_d0027_ac05_*`）
  - D0027-AC-06 `schema` の番号は定数で1か所に持ち、写しの形（キーの一覧）を変えたときにテストが落ちる（形を固定するテスト）。（`tests/test_live_snapshot.py` の `test_d0027_ac06_*`）
  - D0027-AC-07 パイプの記録（`docs/pipeline/<パイプ名>/`、段の並びが開発フローと違う）を読み先に渡しても、`stages` の `name`・`label` を記録から取り、同じ形の写しになる。（`tests/test_live_snapshot.py` の `test_d0027_ac07_*`）
  - D0027-AC-08 同じ記録・同じ「今」で2回作ると、バイト列まで同じ（キーの順も決まっている）。（`tests/test_live_snapshot.py` の `test_d0027_ac08_*`）
  - D0027-AC-09 費用・ターン・時間は、段ごとの `runs[]` の `cost_usd`・`num_turns`・`duration_sec` を、同じ段の回で合計する。回が無ければ null。（`tests/test_live_snapshot.py` の `test_d0027_ac09_*`）
  - D0027-AC-10 要件メモ（`00_input.md`）に目印の文字列を書いておき、その文字列が写しに出ない。（`tests/test_live_snapshot.py` の `test_d0027_ac10_*`）
  - D0027-AC-11 `session_id`（`state.json` の最上位と `runs[]`・`pending_review` の中）に目印を入れても、写しに出ない。（`tests/test_live_snapshot.py` の `test_d0027_ac11_*`）
  - D0027-AC-12 `runs[]` の `result`・`errors`、`review` の `feedback`、`verdict` の `summary`・`failures`、`pending_review.doc`、`warnings` に目印を入れても、写しに出ない。（`tests/test_live_snapshot.py` の `test_d0027_ac12_*`）
  - D0027-AC-13 work_dir の絶対パス（読み先のフォルダ、`/home/…` や `C:\Users\…` の形）が、写しの文字列のどこにも出ない（入力に手元のパスが混じっていても出ない）。（`tests/test_live_snapshot.py` の `test_d0027_ac13_*`）
  - D0027-AC-14 `logs/*.jsonl` の `Prompt` 行の `prompt`・その他の行の中身に目印を入れても、写しに出ない（読むのは最初の `Prompt` 行の `at` だけ）。（`tests/test_live_snapshot.py` の `test_d0027_ac14_*`）
  - D0027-AC-15 写しのキーは許すものの一覧で作る。`state.json` に知らないキー（例 `secret`）を足しても写しに出ない。（`tests/test_live_snapshot.py` の `test_d0027_ac15_*`）
  - D0027-AC-16 `Prompt` 行の `at` がずれつき（`+09:00`）でも、ずれなしでも、`Z` でも、写しの `started_at` は同じ瞬間なら同じ書き方（UTC のずれつき ISO 8601）になる。（`tests/test_live_snapshot.py` の `test_d0027_ac16_*`）
  - D0027-AC-17 `at` が無い古い記録・壊れた時刻（`"abc"`、空、数、null、型違い）では、`started_at` は null で、例外を出さない。`running` の段でも、状態は `running` のまま。（`tests/test_live_snapshot.py` の `test_d0027_ac17_*`）
  - D0027-AC-18 `pending_review.since` が無い古い記録・壊れた時刻では、`pending_since` は null で、状態は `review` のまま。（`tests/test_live_snapshot.py` の `test_d0027_ac18_*`）
  - D0027-AC-19 未来の時刻（「今」より後）の `at`・`since` は、そのまま写しに入れる（写しは時刻を直さない）。経過を負にしない役目はページ側が持つ（D0027-AC-48）。（`tests/test_live_snapshot.py` の `test_d0027_ac19_*`）
  - D0027-AC-20 ずれつきとずれなしの時刻が混ざった記録でも、例外なく作れる。ずれなしの時刻は、読み先の記録の書き方に合わせた扱いを設計で決め、その扱いをテストで固定する。（`tests/test_live_snapshot.py` の `test_d0027_ac20_*`）
  - D0027-AC-21 `generated_at` は、引数で渡した「今」から作る。ずれつき ISO 8601 になる。（`tests/test_live_snapshot.py` の `test_d0027_ac21_*`）
  - D0027-AC-22 `state.json` が無い（フォルダはある）とき、写しは「記録なし」の決まった形（`schema`・`generated_at`・`stages` が空・`final` が null・`empty: true` など設計で決める印）になり、終了コードは 0。（`tests/test_live_snapshot.py`・`tests/test_live_cli.py` の `test_d0027_ac22_*`）
  - D0027-AC-23 読み先のフォルダ自体が無いときも、同じ「記録なし」の形になり、例外で落ちない。（`tests/test_live_snapshot.py`・`tests/test_live_cli.py` の `test_d0027_ac23_*`）
  - D0027-AC-24 `state.json` が空ファイル・壊れた JSON（途中で切れた・文字化け・BOM つき・UTF-8 でないバイト列）のとき、「記録なし」の形になる。（`tests/test_live_snapshot.py` の `test_d0027_ac24_*`）
  - D0027-AC-25 `state.json` が JSON だが最上位が配列・null・数・文字列・真偽のとき、「記録なし」の形になる。（`tests/test_live_snapshot.py` の `test_d0027_ac25_*`）
  - D0027-AC-26 `stages` が無い・null・配列でない・空のとき、`stages` は空の配列で、`name` や `final` は読めれば入れる。（`tests/test_live_snapshot.py` の `test_d0027_ac26_*`）
  - D0027-AC-27 `stages` の要素が、辞書でない（数・null・文字列・配列）・`name` が無い・`name` が文字列でないとき、その要素を飛ばして、残りで作る。（`tests/test_live_snapshot.py` の `test_d0027_ac27_*`）
  - D0027-AC-28 `stages` に同じ `name` が重複するとき、最初の1つだけを使う。（`tests/test_live_snapshot.py` の `test_d0027_ac28_*`）
  - D0027-AC-29 `runs[]` に、`stages` に無い段の名前（未知の段）があるとき、その行は無視する（写しに段を足さない）。`open`・`pending_review` が未知の段を指すときも、同じ。（`tests/test_live_snapshot.py` の `test_d0027_ac29_*`）
  - D0027-AC-30 項目の型違い（`attempt` が文字列、`num_turns` が真偽、`cost_usd` が文字列、`duration_sec` が配列、`label` が数、`runs` が辞書、`open` が文字列、`pending_review` が配列）では、その項目だけを null か省いて、ほかは読む。（`tests/test_live_snapshot.py` の `test_d0027_ac30_*`）
  - D0027-AC-31 数の項目：NaN・Infinity・-Infinity・負の数・巨大な数（1e308、10 の 30 乗の整数）・真偽（`true` を 1 と見なさない）は、null にするか決まった範囲に収める。写しの JSON に `NaN`・`Infinity` の文字が出ない（`json.loads` の厳格な読みでも通る）。（`tests/test_live_snapshot.py` の `test_d0027_ac31_*`）
  - D0027-AC-32 `attempt` は 1 以上の整数のときだけ入る。0・負・小数・巨大な数は null。（`tests/test_live_snapshot.py` の `test_d0027_ac32_*`）
  - D0027-AC-33 `state.json` が非常に大きい（例：`runs` が数万行、文字列が数 MB）とき、時間と大きさに上限があり、例外なく作れる（読むファイルの大きさに上限を設け、超えたときの形は「決めきれない点」の4で決め、テストで固定する）。（`tests/test_live_snapshot.py` の `test_d0027_ac33_*`）
  - D0027-AC-34 古い記録（`since`・`at`・`name`・`usage_summary`・`pipe`・`driver` が無い）でも、読めた項目だけで写しができる。（`tests/test_live_snapshot.py` の `test_d0027_ac34_*`）
  - D0027-AC-35 `state.json` の読みで例外が出る種類（権限なし・フォルダが `state.json` の名前・シンボリックリンクの切れ）でも、落ちずに「記録なし」の形になる。（`tests/test_live_snapshot.py` の `test_d0027_ac35_*`）
  - D0027-AC-36 `logs/` が無い・空のとき、`started_at` は全部 null で、状態は `state.json` から決まる。（`tests/test_live_snapshot.py` の `test_d0027_ac36_*`）
  - D0027-AC-37 ログの行が壊れた JSON・空行・最上位が配列や数の行・最初の行が `Prompt` でない行のときは、その行を飛ばすか、その段の `started_at` を null にして、例外を出さない。（`tests/test_live_snapshot.py` の `test_d0027_ac37_*`）
  - D0027-AC-38 ログの1行が巨大（数 MB）でも、読む長さに上限があり、時間がかからず、例外を出さない（巨大な行は飛ばす）。（`tests/test_live_snapshot.py` の `test_d0027_ac38_*`）
  - D0027-AC-39 ログの数が非常に多い（数千ファイル）とき、読むのは動いている段の1ファイルに絞るなど、読む量に上限がある。（`tests/test_live_snapshot.py` の `test_d0027_ac39_*`）
  - D0027-AC-40 ログのファイル名が `open.log` の指す名前と違う・パスの区切り（`../`）を含むとき、work_dir の外を読まない。（`tests/test_live_snapshot.py` の `test_d0027_ac40_*`）
  - D0027-AC-41 セッション名・段の表示名に `<script>alert(1)</script>`、`</script>`、`"`、`'`、`` ` ``、`\u2028`、制御文字（`\x00`〜`\x1f`、`\x7f`、C1）、RTL 記号（U+202E ほか）、ゼロ幅の文字、絵文字、結合文字の列、孤立したサロゲート（`\ud800`）が入っても、写しは例外なく作れ、制御文字と方向を変える記号は取り除かれる。（`tests/test_live_snapshot.py` の `test_d0027_ac41_*`）
  - D0027-AC-42 孤立したサロゲートが入っていても、写しを UTF-8 で書き出せる（書き出しで `UnicodeEncodeError` を出さない）。（`tests/test_live_snapshot.py` の `test_d0027_ac42_*`）
  - D0027-AC-43 セッション名は 60 文字、表示名は 40 文字（どちらも設計で最終に決める）を超えるとき、切る。切るのは文字の単位で、絵文字や結合文字の途中で割らない。切ったことは `…` で分かる。（`tests/test_live_snapshot.py` の `test_d0027_ac43_*`）
  - D0027-AC-44 写し全体の大きさが上限（設計で決める。例 32 KB）を超えない。段の数・回の数が多くても、段は上限の数まで、超えた分は捨てる。（`tests/test_live_snapshot.py` の `test_d0027_ac44_*`）
  - D0027-AC-45 写しのコマンドの出力は、JSON として常に読み直せる（`ensure_ascii` の扱いを固定し、`</script>` が出力の中に生で出ない）。（`tests/test_live_snapshot.py` の `test_d0027_ac45_*`）
  - D0027-AC-46 ページの HTML を作る関数は、引数に外の文字を取らない（記録・写し・パスを受けない）。同じ呼び出しは同じ HTML を返す。（`tests/test_live_page.py` の `test_d0027_ac46_*`）
  - D0027-AC-47 HTML に、`<script src=`、`<link`、`@import`、`url(http`、`http://`・`https://` で始まる読み込み、`<iframe>`、`<img src=`、`fetch(`、`XMLHttpRequest`、`WebSocket` が無い。外部の読み込みがない。（`tests/test_live_page.py` の `test_d0027_ac47_*`）
  - D0027-AC-48 ページのスクリプトに、`innerHTML`・`outerHTML`・`insertAdjacentHTML`・`document.write`・`eval(`・`new Function` が無く、db の値は `textContent` か `createTextNode` で出す。（`tests/test_live_page.py` の `test_d0027_ac48_*`）
  - D0027-AC-49 HTML に、写しの値や、記録に書かれた文字が含まれない（テストで悪意のある文字を入れた記録から写しを作っても、ページの HTML は変わらない）。（`tests/test_live_page.py` の `test_d0027_ac49_*`）
  - D0027-AC-50 スクリプトが `claude.use("db")` を `await` で呼び、その結果が null のときの「この画面では読めない」旨の文字がある。（`tests/test_live_page.py` の `test_d0027_ac50_*`）
  - D0027-AC-51 HTML は `<!doctype html>`・`lang="ja"`・`<meta name="viewport">`・`<title>` を持つ。（`tests/test_live_page.py` の `test_d0027_ac51_*`）
  - D0027-AC-52 ライト・ダークの色が `:root` のトークンで定義され、`prefers-color-scheme: dark` と `[data-theme="dark"]`・`[data-theme="light"]` の両方がある。色の指定は、トークンの定義以外では直接書かない。（`tests/test_live_page.py` の `test_d0027_ac52_*`）
  - D0027-AC-53 動き（`animation`・`transition`）の CSS は、すべて `@media (prefers-reduced-motion: no-preference)` の中にある。（`tests/test_live_page.py` の `test_d0027_ac53_*`）
  - D0027-AC-54 幅の指定に、360px を超える固定の幅（`width: 400px` など）が無く、`overflow-x` を隠して逃げず、長い名前の折り返し（`overflow-wrap`）の指定がある。（`tests/test_live_page.py` の `test_d0027_ac54_*`）
  - D0027-AC-55 ページの HTML の大きさは上限（設計で決める。例 40 KB）以下。（`tests/test_live_page.py` の `test_d0027_ac55_*`）
  - D0027-AC-56 写しから経過秒を求める関数は「今」を引数で受け、動いている段は「今 − `started_at`」、確認待ちは「今 − `pending_since`」になる。（`tests/test_live_page_js.py` の `test_d0027_ac56_*`）
  - D0027-AC-57 経過は、未来の時刻・時計が戻ったとき・時刻が null のとき・壊れた時刻のときに、負にならず、時刻が無いときは数え上げない。（`tests/test_live_page_js.py` の `test_d0027_ac57_*`）
  - D0027-AC-58 経過は `m:ss`（1時間以上は `h:mm:ss`）で出す。境目（0・59・60・3599・3600・巨大な数）が決まった書き方になる。（`tests/test_live_page_js.py` の `test_d0027_ac58_*`）
  - D0027-AC-59 描き直しは、写しが null・配列・文字列・`stages` が無い・`stages` の要素が壊れている・未知の `status` のときも例外を出さず、直前の画面を残すか「まだ記録がありません」を出す。（`tests/test_live_page_js.py` の `test_d0027_ac59_*`）
  - D0027-AC-60 描き直しのたびにタイマーは1つのまま。数える要素が無ければタイマーを回さない。（`tests/test_live_page_js.py` の `test_d0027_ac60_*`）
  - D0027-AC-61 隠れる（`visibilitychange`）とタイマーが止まり、戻ると今の時刻から求め直す。（`tests/test_live_page_js.py` の `test_d0027_ac61_*`）
  - D0027-AC-62 db の値に `<script>` や HTML の文字があっても、DOM に要素が増えない（`textContent` の確認）。（`tests/test_live_page_js.py` の `test_d0027_ac62_*`）
  - D0027-AC-63 写しのコマンドは、読み先のフォルダの引数（`--dir` など。設計で決める）を取り、パイプの記録のフォルダも読める。標準出力か `--out` のファイルに出す。（`tests/test_live_cli.py` の `test_d0027_ac63_*`）
  - D0027-AC-64 ファイルに出すときは、読み先の記録を書き換えず、出力は決まった場所の外には書かない。読み先の `state.json` のバイト列が前後で同じ。（`tests/test_live_cli.py` の `test_d0027_ac64_*`）
  - D0027-AC-65 ページのコマンドも、標準出力か `--out` のファイルに HTML を出す。（`tests/test_live_cli.py` の `test_d0027_ac65_*`）
  - D0027-AC-66 どちらのコマンドも、SDK を呼ばない。（`tests/test_live_cli.py` の `test_d0027_ac66_*`）
  - D0027-AC-67 `python -m pipe_in …` と `pipe-in …` のどちらからも呼べる。（`tests/test_live_cli.py` の `test_d0027_ac67_*`）
  - D0027-AC-68 引数の誤り（読み先のフォルダの指定が無い・知らない引数）は、使い方を出して終了コード 2。記録の中身の問題では終了コード 0 で「記録なし」の形を出す。（`tests/test_live_cli.py` の `test_d0027_ac68_*`）
  - D0027-AC-69 既存の `pipe-in record` の各コマンドの動き・`state.json` の形・終了コードは変わらない（既存のテストが通る）。写しのコマンドは記録に何も書かない。（`tests/test_live_cli.py` の `test_d0027_ac69_*`）
  - D0027-AC-70 依存の向きと層の検査（`tests/test_architecture.py`）が通る。新しいコードは、`pipe_in.usage` と標準ライブラリの外に新しい依存を足さない。（`tests/test_architecture.py` の `test_d0027_ac70_*`）
  - D0027-AC-71 外部のパッケージの依存を足さない（`pyproject.toml` の dependencies が変わらない）。（`tests/test_live_cli.py` の `test_d0027_ac71_*`）
  - D0027-AC-72 `guard.py`・`guard_hook.py`・`pipe_in_guard.py` の止める範囲は変えない（狭めない）。（検証で `git diff` を見た）
  - D0027-AC-73 VSCode の拡張（`vscode/`）のファイルが変わらない。（検証で `git diff` を見た）
  - D0027-AC-74 古い版の `state.json`（D0017 より前：`since`・`at` が無い）、パイプの `state.json`、`archive/<日時>/` の中の記録を読み先に渡しても、写しが作れる。（`tests/test_live_snapshot.py` の `test_d0027_ac74_*`）
  - D0027-AC-75 本体が将来、`state.json` にキーを足しても、写しの `schema` と中身は変わらない（知らないキーを無視する。AC-15 と同じ）。（`tests/test_live_snapshot.py` の `test_d0027_ac75_*`）
  - D0027-AC-76 （手で）`.claude/skills/pipe-in/SKILL.md` に `--artifact` の手順（ページを最初に1回公開・各 record のあとに写しを set・公開し直さない・使えない環境では何もせず通常どおり進む）がある。（手で読んだ）
  - D0027-AC-77 （手で）`docs/guide/` の該当ページと `README.md` に、使い方、写しに入れるもの・入れないもの、できないこと（見るだけ・ターミナルでは使えない）が書かれ、`tests/test_rules.py` が通る。（手で読んだ）
  - D0027-AC-78 （手で）`docs/decisions/D0027-<名前>.md` が書かれ、AC ごとにテストの名前が添えてある。（手で読んだ）
  - D0027-AC-79 （画面）書き出したページの HTML を、db を差した偽物の `claude` 付きで（プレビュー用のページ）Playwright で開くと、段が並び、動いている段の経過が1秒ごとに増え、確認待ちの段が見分けられる。（Playwright で確かめた）
  - D0027-AC-80 （画面）`claude.use("db")` が null を返す状態で開くと、「この画面では読めない」旨が出て、コンソールにエラーが出ない。（Playwright で確かめた）
  - D0027-AC-81 （画面）幅 360px で開いても、横にスクロールが出ず、長いセッション名（60 文字）は折り返される。（Playwright で確かめた）
  - D0027-AC-82 （画面）ライト・ダークの両方で、文字と背景の差が読める。`data-theme` の切り替えで色が替わる。（Playwright で確かめた）
  - D0027-AC-83 （画面）`<script>alert(1)</script>` を名前に入れた写しを db に入れて開くと、文字としてそのまま見え、警告も要素も出ない。（Playwright で確かめた）
  - D0027-AC-84 （画面）動きを減らす設定にすると、脈打ちなどの動きが止まり、経過は数え続ける。隠して戻すと、隠れていた時間を足した値になる。（Playwright で確かめた）
  - D0027-AC-85 （実機）claude.ai の Claude Code（デスクトップアプリか claude.ai/code）で、`/pipe-in --artifact <要件メモ>` を流すと、最初にページが1枚公開され、段の区切りごとに公開し直さずに図が更新される。これは claude.ai の機能に頼るため、手元では確かめきれない。（claude.ai で確かめた）
  - D0027-AC-86 （検証の画面の確認で見つけた崩れから足した）状態の印の幅と形：印の列の幅は、どの状態でも同じ。`.mark` は固定の幅と高さを持ち、中央に寄り、縮まない。待ち・動いている・確認待ちの印は、書体の字形に頼らず CSS の形（枠線・塗り・半分の塗りなど）で描く。この 3 つの印の要素の `textContent` は空（意味は隣の言葉 `待ち`・`実行中`・`確認待ち` が伝える）で、`aria-hidden="true"` のまま。終わり・失敗・差し戻し（と未知）の印は今の 1 文字のままで、同じ固定の幅に収まる。（`tests/test_live_page.py`・`tests/test_live_page_js.py` の `test_d0027_ac86_*`）
  - D0027-AC-87 （検証の画面の確認で見つけた崩れから足した）0 の費用・ターンは出さない：段の usage で、費用が正の数のときだけ費用を、ターンが正の数のときだけターンを出す（0・負・NaN・Infinity・null・文字・真偽・配列は出さない）。費用・ターン・時間のどれも出ないときは `.usage` の要素を作らない。（`tests/test_live_page_js.py` の `test_d0027_ac87_*`）
  - D0027-AC-88 （検証の画面の確認で見つけた崩れから足した）段の時間は経過と同じ書き方：段の時間は `fmtElapsed` の結果そのもの（`m:ss`、1 時間以上は `h:mm:ss`、小数は切り捨て、0 以上 1 未満は `0:00`、上限は `99:59:59`、負・NaN・Infinity・文字・真偽は `0:00`）。null なら出さない。時間が `0` のときは `0:00` を出す（0 を隠すのは費用とターンだけ）。「秒」の単位の文字は出さない。（`tests/test_live_page_js.py` の `test_d0027_ac88_*`）

## 決めたことと理由

### 段階に分けた（第1段階だけ）

- 第1段階は、会話から流す `/pipe-in --artifact` だけにした。アーティファクトのデータに書けるのは Claude Code の会話のツール（ArtifactData）だけで、Python の処理からは書けない。会話は段の区切りで `record` をもう呼んでいるので、その直後に写しを書けば、本体の流れを変えずに済む。
- 選ばなかった形：ターミナルで流す `pipe-in` から直接書く（書く手段が無い。第2段階で、会話が `state.json` を見張って写す形を考える）、段ごとにページを公開し直す（版が増え、毎回承認が要る）、ページから承認・差し戻しを押す（押しても会話が起きないので、結局会話で答えることになる。第3段階）。

### 置き場所と形

- 置き場所は `pipe_in/engine/`（`live.py`・`live_page.py`・`live_cmd.py`）。写しは開発フローの記録（`docs/pipeline/`）にもパイプの記録（`docs/pipeline/<パイプ名>/`）にも使うので、どのパイプにも共通の engine に置いた。どれも標準ライブラリだけで、依存の向きは変わらない（`tests/test_architecture.py`）。入口は `pipe_in/cli.py` の先頭の分岐で、`record` と同じく関数の中で import する。選ばなかった形：`record` のサブコマンドにする（記録を書くコマンドと読むだけのコマンドが混ざる）、`pipe_in/dev/` に置く（パイプでも使う）。
- 写しを作る部分は、ファイルを読む関数（`read_state`・`read_open_at`）と、時計を読まない純粋な組み立て（`build_snapshot`。例外を出さない）と、決まった書き方の JSON（`dumps`）に分けた。壊れた記録でも、決まった形の写しを返す。
- ページは Python の文字列（`_CSS`・`_BODY`・`_JS`）から作る。パッケージに同梱するファイル（`package-data`）を増やさず、入れ方による取りこぼしを避けるため。

### 写し（schema 1）に入れるもの・入れないもの

- 写しは、許すものの一覧で作る。入れるのは、セッション名・段の名前と表示名・状態（`waiting`・`running`・`review`・`done`・`failed`・`revised`）・回数・動いている段の始まり・確認待ちの始まり・最後の結果・検証の判定・費用/ターン/時間の数字・`empty`（記録なしの印）・作った時刻だけ。
- 入れないのは、要件メモの本文・`session_id`・手元のパス・段の要約や差し戻しの理由などの自由な文・ログの中身。アーティファクトは最初は持ち主だけが見られるが、データは claude.ai に送られるので、安全側に倒した（`docs/guide/safety.md` に書いた）。
- セッション名は入れる（要件の決めきれない点 2 を推しの A で決めた）。人が付けた見分けのための名前で、これが無いとページで何の実行か分からない。長さを 60 文字で切り、制御文字を除く。載せたくない言葉があれば `--name` で付け替える。
- 差し戻しは `revised` の状態と回数だけで出す（決めきれない点 1）。理由の文は入れない。
- ずれなしの時刻は、書いた機械の時刻帯と見なして UTC に直す（決めきれない点 3）。前の版の `record begin` がずれなしで書いていたため。
- 上限を超える `state.json`（4 MiB）は「記録なし」の形にする（決めきれない点 4）。写し全体は 32 KiB まで、段は 24 まで、ログは動いている段の1つだけを先頭から上限つきで読む。
- JSON は `ensure_ascii` で、`<`・`>`・`&` もエスケープする。写しをどこに置いても HTML として解釈されない。
- `schema` の番号は1か所に持つ。キーを足すだけなら 1 のまま。意味を変えるときは上げ、ページは知らない版を描かず「この写しの版には対応していません」と出す。
- `started_at` は動いている段だけに入れる。ページが使うのはそれだけで、開くログが1つで済む。

### ページ

- ページは1枚で完結し、外部から何も読み込まない。写しは HTML に埋め込まず、db から読む（`claude.use("db")` → `db.doc("runs/current").onSnapshot(next, error)` → `snap.exists`・`snap.data()`。公式の型定義で確かめた）。`window.claude` が無い（保存したファイルを直接開いた）・`use` が null のときは「この画面では読めません」と出す。ページは書き込まない。
- 外から来た文字は `textContent` だけで出す。`innerHTML` などは使わない（テストが禁止語で見張る）。
- 経過は「閲覧側の今 − 記録の時刻」で数える。D0017 の「描き直しを受けた時刻からの差」にしなかったのは、写しを書いてから何分もあとにページが開かれることがあり、受けた時刻から数えると短く出るため。書いた側と閲覧側の時計が数秒ずれる環境では、その分ずれる（受け入れたリスク）。未来の時刻や時計の戻りでは負にしない。隠れたらタイマーを止め、戻ったら今の時刻から求め直す。
- 状態の印は、待ち・動いている・確認待ちを CSS の形（枠線の丸・塗りの丸・半分塗りの丸）で描き、終わり・失敗・差し戻しは文字（✓ ✕ ↩）。印の列の幅はどれも同じ。初めは ○ ● ◐ の文字だったが、検証で画面を撮ると ◐ が書体しだいで細い欠片になり、その行の表示名がずれたので直した（AC-86）。意味は隣の言葉（実行中・確認待ち・待ち）で伝わる。
- 費用とターンは正の数のときだけ出す。`/pipe-in` の記録は会話で進めるので費用とターンが 0 で、「$0 ・ 0ターン」が雑音になっていた（AC-87）。段の時間は経過と同じ `m:ss`（1時間以上は `h:mm:ss`）にそろえた（AC-88）。
- 色は `:root` のトークンで、ライトとダークの両方を持つ（`prefers-color-scheme` と `data-theme`）。動きは `prefers-reduced-motion: no-preference` のときだけ。幅 360px でも横にはみ出さない。

### テストの方法

- ページの JS は、pytest から Node（22 以上）を呼び、`tests/fixtures/live_page_harness.mjs` が `node:vm` の中で、偽の `document`・仮想の時計とタイマー・偽の db を渡して本物の JS を動かす。Python に同じ規則の表を作らなかったのは、実装が JS に1つしかなく、タイマーや DOM の動きは表で確かめられないため。Node が無ければ skip するので、検証では `-rs` で skip が無いことを見る。
- テストは 1400 件あまり。壊れた記録・欠けた項目・型違い・NaN/Infinity・巨大な値・未来の時刻・ずれあり/なし・悪意のある文字（`</script>`・制御文字・RTL・孤立サロゲート・絵文字・結合文字）・上限の境目を細かく確かめる（人の要望）。

### `/pipe-in` のスキル

- `.claude/skills/pipe-in/SKILL.md` に「進み具合をアーティファクトで見る（`--artifact`）」の節を足した。ArtifactData の `set` は、すでにあるドキュメントには `if_version` が要るので、2回目からは前の結果の `version` を渡す。写しや書き込みに失敗しても段は止めない。

### 互換

- `state.json`・`logs/*.jsonl`・`99_summary.md`・終了コード・設定・パイプ・置き場所は変えない。`live` は記録を読むだけで、書くのは `--out` のファイルだけ（読み先の中・シンボリックリンク・親の無い場所は断る）。
- 依存は足さない。guard（`pipe_in/engine/guard.py`・`generator/guard_hook.py`・`.claude/hooks/pipe_in_guard.py`）と VSCode の拡張は触らない。
- `stages` の無い古い記録は、`stages` を空にして出す（拡張のように開発の5段を補わない）。

## 対象外・残った課題

- 第2段階：ターミナルで流す `pipe-in` の進み具合を、会話が `state.json` を見張ってアーティファクトに写す。
- 第3段階：ページから承認・直してほしい点・中止を押せるようにする。
- 段の途中（ツール呼び出し）の表示。写しに `logs/*.jsonl` の中身を入れることになり、利用料と漏れの心配が増える。
- `/pipe-in:pipe-build` などプラグインのスキルや、`pipe-in --pipe` から `--artifact` を使うこと。
- 書いた側と閲覧側の時計のずれは直さない。

## 監査と助言で直したこと

- 監査 A-1：決定の記録が無かった（この記録を書いた）。A-2：`/pipe-help` に `/pipe-in --artifact` と `pipe-in live` の行を足し、CLAUDE.md に一文足した。A-3：`records.md` に、ページは知らない状態を「不明（？）」で出すことを書いた。A-4：`usage.md` の時間の書き方に `h:mm:ss` と上限を書いた。A-5：テストの1つの説明の AC の番号を、関数名に合わせて AC-17 にした。
- 助言 V-1：`--artifact` が使える場所を公式の文書に合わせて書いた（claude.ai にログインした CLI・デスクトップアプリ・claude.ai/code。API キー・Bedrock・Vertex・`-p`・Agent SDK では使えない）。V-3：URL を伝えるとき、はじめは持ち主だけが見られることを添える。V-5：`--artifact` は旗を付けたときだけ有効で、要件メモの中の言葉では有効にしないと書いた。
- 直さなかった助言：V-2（`--auto` でも公開の許可を聞かれうる。根拠が推測で、pipe-in の `--auto` と Claude Code の auto mode を混ぜていた）、V-4（`allowed-tools` で写しのコマンドを前もって許す。スキルを呼んだ番だけしか効かない）、V-6（db が使えないときに公開し直す逃げ道。手順が複雑になる）。
- 助言の報告の審査は、総合 0.85・合格（事実の正確さ 0.75・引用の正確さ 1.0・網羅性 0.75・情報源の質 1.0・ツール効率 0.75）。Artifact の `capabilities` と ArtifactData の引数は公式の文書に無く、実機のツールの定義で確かめた。

## 確かめたこと

- `python -m pytest -q` がすべて通る（JS のテストは Node 22 で動かし、skip は root で権限のテストが成り立たない2件だけ）。
- 画面（Playwright。偽の db を差し込んだ確認用のページを一時フォルダで作った）：動いている段の経過が1秒ごとに増え、写しを替えると描き直されて購読は1つのまま（AC-79）。db が無い・記録なし・知らない版でそれぞれの文が出て、コンソールのエラーは 0 件（AC-80）。幅 360px で横にはみ出さず、60 文字の名前が折り返される（AC-81）。ライト・ダークと `data-theme` の切り替えで、文字と背景の差は 5 以上（AC-82）。名前の `<script>` と `<img onerror>` が文字のまま見え、要素もダイアログも増えない（AC-83）。動きを減らす設定で脈打ちが止まり、隠すと止まって戻すと隠した分を足した値になる（AC-84）。印の列がそろい、0 の費用とターンが出ず、時間が `m:ss` になる（AC-86〜88）。
- 実機（AC-85）：claude.ai で、この機能を作った `/pipe-in` の実行そのものの進み具合のページを公開し（1回）、ArtifactData の `set` で写しを書いた（1回目は `if_version` なし、2回目は前の版を渡して成功）。claude.ai の画面での見え方は、持ち主が開いて確かめる（まだ）。
