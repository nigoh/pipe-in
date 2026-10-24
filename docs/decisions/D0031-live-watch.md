# D0031 ターミナルで流す pipe-in の進み具合もアーティファクトで見る（`pipe-in live watch` と `/pipe-in:pipe-live`。第2段階）

## 目的

ターミナルで `pipe-in`（開発フローもパイプも）を流している人が、その進み具合を Claude のアーティファクト（claude.ai のページ）でも見られるようにする。D0027（第1段階）は、会話から流す `/pipe-in --artifact` だけだった。Python の処理からはアーティファクトのデータに書けないので、Claude Code の会話が記録を見張り、変わったら写しを書く。見るだけで、実行を止めたり進めたり承認したりはしない。

## 機能要件と受け入れ基準

本体に、記録を見張って写しが変わるたびに1行を出すコマンド `pipe-in live watch` を足し、プラグインに、会話がそれを Monitor で動かして写しを ArtifactData で書く手順のスキル `/pipe-in:pipe-live` を足す。テストの名前は `test_d0031_acNN_…`。

- FR-01 `pipe-in live watch` を足す。引数は `--project`・`--config`・`--work-dir`（`live snapshot` と同じ意味。パイプの記録は `docs/pipeline/<パイプ名>` を渡す）・`--out FILE`（必須）・`--interval 秒`・`--timeout 秒`。`python -m pipe_in live watch …` と `pipe-in live watch …` のどちらからも呼べる。
- FR-02 「変わった」の判定：写しから `generated_at` を除いた中身が、前に出した写しの中身と違うとき。バイト列ではなく中身で比べる。`generated_at` だけの違い、段の経過時間（ページが数えるので写しに入らない）だけの違いでは出さない。
- FR-03 最初の1回は、記録が無い・壊れているときも必ず出す（「記録なし」の写しと行）。
- FR-04 出すときの順番は、先に `--out` に写しを書き、書けてから行を出す（行を受けた側がファイルを開くと、必ずその行の写し以降の中身になる）。
- FR-05 `--out` への書き込みは、同じフォルダの一時ファイルに全部書いてから置き換える（`os.replace`）。読む側が途中の書きかけを読まない。失敗したときに一時ファイルを残さない。
- FR-06 `--out` の守りは D0027 と同じ：読み先の記録のフォルダの中・シンボリックリンク・親のフォルダが無い所・フォルダは断る（終了コード 2）。置き換えは、あとから `--out` がリンクに替えられても、リンクの先ではなくリンク自身を置き換える。
- FR-07 標準出力の行は、1行1つの JSON（`ensure_ascii`・隙間なし）で、キーは `event`・`seq`・`final`・`empty` の4つだけ。`event` は `snapshot`（変わった）・`final`（final が入った写しを出した。このとき `snapshot` の行は別に出さず、この1行だけ）・`timeout`（上限）。`seq` は出した写しの通し番号（1から）。`final` は写しの `final`（許すものの一覧か null）。`empty` は写しの `empty`。手元のパス・セッション名・段の名前・自由な文は行に入れない。行ごとに flush する。
- FR-08 final が入った写しを出したら、終了コード 0 で止まる。止まったあとは、記録が変わっても読まない・出さない。起動したときにすでに final が入っている記録なら、最初の1回で `final` の行を出して止まる。
- FR-09 記録が読めない（`state.json` が無い・空・壊れている・最上位が辞書でない・大きすぎる・読む権限が無い）ことは、毎回の読みで起こりうるものとして扱い、落ちない。直前に出した写しが「記録なし」でないときは、連続して読めなかった回数が閾値（設計で決める。推し：3回）に達するまで、何も出さず前の状態を保つ。達したら「記録なし」の写しと行を出す。読めるようになったら、そのときの写しが前に出したものと違えば出す。
- FR-10 `record start` で新しい実行に作り直された（名前・段・回・final が替わった）とき、`archive/<日時>/` に移って `state.json` が消えて新しく現れたとき、どちらも落ちず、写しが変わった回に出す。同じ中身に戻った場合も、前に出したものと違えば出す（比べるのは直前に出したものだけ）。
- FR-11 間隔は `--interval`（既定は設計で決める。推し：2秒。範囲は 0.5〜60 秒。範囲外・数でない・NaN・Infinity・0・負は使い方の誤りで終了コード 2）。上限は `--timeout`（既定は設計で決める。推し：6時間。範囲は 1秒〜24時間。範囲外は終了コード 2）。上限に達したら `timeout` の行を出して、終了コード 124 で止まる（写しは書き換えない）。眠る時間は残り時間を超えない。
- FR-12 時計と眠りは差し替えられる（引数で `clock`・`sleep`・`now`、本物の時間を待たない）。経過の計算は単調な時計で行う。時計が戻る（差し替えた時計が前より小さい値を返す）ときも、経過を負にせず、落ちず、上限を早めて終えたり延ばしたりしない。
- FR-13 Ctrl+C（KeyboardInterrupt）では、標準エラーに短い文を出して終了コード 130 で止まる。一時ファイルを残さず、最後に書いた写しは壊さず、トレースバックを出さない。SIGTERM（Monitor を止めたとき）も同じに扱う（終了コード 143。SIGTERM を扱えない環境では何もしない）。標準出力が閉じられた（BrokenPipe）ときも、落ちずに一時ファイルを残さず終了コード 1 で止まる。
- FR-14 `--out` に書けなかったとき（権限・ディスクなど）は、行を出さず、次の周期でやり直す。連続して設計で決める回数（推し：3回）書けなかったら、標準エラーに理由（パスは入れず、種類だけ）を出して終了コード 1 で止まる。1回成功したら数え直す。
- FR-15 `--pause` で確認待ちに止まっている実行（`pending_review` が入り、final は無い）では止まらずに見張り続ける。`--review` で続きが流れ、段が進めば、その回に出す。
- FR-16 設定（`pipeline.toml`）が読めない・`--work-dir` と `--project` の指定の誤りなど、使い方の誤りは `live snapshot` と同じ扱い（使い方か理由を出して終了コード 2）。記録の中身の問題では終了コード 2 にしない。
- FR-17 記録を書き換えない（`state.json`・`logs/`・`99_summary.md` のバイト列が前後で同じ）。書くのは `--out` と、その一時ファイルだけ。SDK を呼ばない。依存を足さない（標準ライブラリだけ）。
- FR-18 1回の読みで読む量と、見張っている間に覚えておく量に上限がある（D0027 の読みの上限をそのまま使い、覚えるのは直前に出した写しの文字列1つ＝最大32 KiB）。長く見張っても、メモリが増え続けない。
- FR-19 写しの形（schema 1）・ページ（`live_page.py`）・`live snapshot`/`live page` の出力・`record` の各コマンド・`state.json` の形・終了コード（`Exit`）は変えない。
- FR-20 手順（スキル）を、利用者向けのプラグインに足す（推し：`plugin/skills/pipe-live/SKILL.md`。呼び方 `/pipe-in:pipe-live [--work-dir 記録のフォルダ]`。「決めきれない点」の1）。内容：Artifact・ArtifactData・Monitor が使える会話か確かめる（なければ伝えて何もしない）→ ページを `pipe-in live page` で作って1回だけ公開 → Monitor で `pipe-in live watch --out <一時>` を起こす → 行を受けるたびに ArtifactData の `set`（D0027 と同じ `runs`/`current`・`if_version` の扱い）→ `final`・`timeout` の行で終わりを伝える。人が呼んだときだけ（`disable-model-invocation: true`）。見るだけで、承認などは会話・ターミナルでする。
- FR-21 文書をそろえる：`docs/guide/` の使い方（`usage.md`）・記録の説明（`records.md`）・プラグイン（`plugin.md`）・目次、`README.md` の必要な箇所、`/pipe-help`（`.claude/skills/pipe-help/`。メインが書く）、CLAUDE.md の一文（案をメインに返す）に、`pipe-in live watch` と `/pipe-in:pipe-live` の使い方、行の形、止まる条件、終了コード、できないこと（ターミナルの実行は止められない・承認はできない・Monitor が使えない環境では使えない）を書く。決定の記録 `docs/decisions/D0031-<名前>.md` を書く。
  - D0031-AC-01 最初の1回：正常な記録で見張りを始めると、`seq: 1` の行が1つ出て、`--out` にその写しが書かれる。（`tests/test_live_watch.py` の `test_d0031_ac01_*`）
  - D0031-AC-02 最初の1回は、`state.json` が無い・フォルダ自体が無い・空・壊れている記録でも、`empty: true` の行が1つ出る（落ちない）。（`tests/test_live_watch.py` の `test_d0031_ac02_*`）
  - D0031-AC-03 記録が替わらないまま何周期も過ぎても、2つ目の行は出ない（10周期、同じ記録）。（`tests/test_live_watch.py` の `test_d0031_ac03_*`）
  - D0031-AC-04 記録の `generated_at` 相当（「今」だけが進む）では出ない：偽の `now` を1周期ごとに進めても、記録が同じなら行は出ない。出た写しの `generated_at` は、その写しを書いた回の `now`。（`tests/test_live_watch.py` の `test_d0031_ac04_*`）
  - D0031-AC-05 段の状態が替わる（`record begin`→`done`→`begin` の順に書く偽の書き手）たびに、1回ずつ、その回の周期で行が出る。行の `seq` は 1, 2, 3… と抜け番なく増える。（`tests/test_live_watch.py` の `test_d0031_ac05_*`）
  - D0031-AC-06 1周期の間に記録が2回替わったときは、行は1つだけで、写しはその時点の最新の中身（途中の状態は出さなくてよい）。（`tests/test_live_watch.py` の `test_d0031_ac06_*`）
  - D0031-AC-07 動いている段の経過時間が進むだけでは出ない（写しに経過が入らないため）。`open` の段のログの最初の行（`started_at` の元）が現れたときは、写しが変わるので出る。（`tests/test_live_watch.py` の `test_d0031_ac07_*`）
  - D0031-AC-08 比べるのは中身で、キーの順や空白の違いでは出ない（`generated_at` 以外が同じ辞書は同じ扱い）。（`tests/test_live_watch.py` の `test_d0031_ac08_*`）
  - D0031-AC-09 `--out` のファイルの中身は、同じ記録・同じ「今」で `live snapshot` が出すバイト列と同じ（`live.dumps`）。（`tests/test_live_watch.py` の `test_d0031_ac09_*`）
  - D0031-AC-10 先に `--out` に書いてから行を出す：行を出す瞬間に `--out` を開いて読む偽の標準出力を使うと、その行の `seq` に対応する中身が読める。（`tests/test_live_watch.py` の `test_d0031_ac10_*`）
  - D0031-AC-11 書きかけを読まれない：書き込みの途中で（`os.replace` の直前に）`--out` を読む仕掛けで、読めるのは前の完全な写しだけ（空でも半分でもない）。最初の1回では、まだ無い。（`tests/test_live_watch.py` の `test_d0031_ac11_*`）
  - D0031-AC-12 置き換えに使う一時ファイルは `--out` と同じフォルダにあり、書き終わると残らない。書き込みに失敗した（偽の書き込みが `OSError`）あとも残らない。（`tests/test_live_watch.py` の `test_d0031_ac12_*`）
  - D0031-AC-13 `--out` が読み先の記録のフォルダの中（パイプの記録のフォルダ、`archive/…` を含む）・シンボリックリンク・親のフォルダが無い所・既存のフォルダのときは、見張りを始めず、使い方を出して終了コード 2。記録も `--out` も何も書かれない。（`tests/test_live_watch_cli.py` の `test_d0031_ac13_*`）
  - D0031-AC-14 `--out` が `..` を含む形や相対の形で読み先の中を指していても断る（`resolve` した形で比べる）。実行中に `--out` がシンボリックリンクに替えられても、リンクの先は書き換わらない。（`tests/test_live_watch_cli.py` の `test_d0031_ac14_*`）
  - D0031-AC-15 `--out` を付けない場合は使い方の誤り（終了コード 2）。（`tests/test_live_watch_cli.py` の `test_d0031_ac15_*`）
  - D0031-AC-16 行を出すたびに flush する（flush の回数を数える偽の標準出力）。（`tests/test_live_watch.py` の `test_d0031_ac16_*`）
  - D0031-AC-17 すべての行は1行の JSON で、`json.loads` の厳格な読みで通り、キーは `event`・`seq`・`final`・`empty` だけ。`event` は `snapshot`・`final`・`timeout` のどれか。改行は行の終わりの1つだけ。（`tests/test_live_watch.py` の `test_d0031_ac17_*`）
  - D0031-AC-18 記録のセッション名・段の名前・`session_id`・要件メモ・`result`/`errors`/`feedback` に目印の文字列と手元のパス（`/home/…`・`C:\Users\…`）を入れても、標準出力と標準エラーのどこにも出ない。（`tests/test_live_watch.py` の `test_d0031_ac18_*`）
  - D0031-AC-19 `final` の値は FINALS の一覧にあるものか null だけ。未知の文字・型違いの `final` では null の `snapshot` の行になる（`final` の行にならず、止まらない）。（`tests/test_live_watch.py` の `test_d0031_ac19_*`）
  - D0031-AC-20 行に `NaN`・`Infinity` の文字が出ない。（`tests/test_live_watch.py` の `test_d0031_ac20_*`）
  - D0031-AC-21 `final` が `PASSED`・`TEST_FAILED`・`STOPPED_BY_HUMAN`・`STAGE_ERROR`・`BLOCKED` のそれぞれで、その写しを `--out` に書き、`event: final` の行を1つ出し（`snapshot` の行は別に出さない）、終了コード 0 で止まる。（`tests/test_live_watch.py` の `test_d0031_ac21_*`）
  - D0031-AC-22 起動したときにすでに `final` が入っている記録は、1回目で `event: final`・`seq: 1` を出して終了コード 0。（`tests/test_live_watch.py` の `test_d0031_ac22_*`）
  - D0031-AC-23 `final` の行を出したあとは、記録を読まない（読みの回数が増えない）・眠らない・何も出さない。記録を書き換える偽の書き手が続いても、同じ。（`tests/test_live_watch.py` の `test_d0031_ac23_*`）
  - D0031-AC-24 `final` が入る回と同じ周期に、段の状態も変わっているときは、1つの行（`event: final`）で済み、`--out` はその最後の写し。（`tests/test_live_watch.py` の `test_d0031_ac24_*`）
  - D0031-AC-25 `pending_review` の記録（`--pause` の確認待ち。`final` は null）では止まらず、`review` の状態の写しを1回出す。続いて `review … approved` と次の段の `begin` を書くと、その回に出る。AWAITING_REVIEW のために止まる、ということはない。（`tests/test_live_watch.py` の `test_d0031_ac25_*`）
  - D0031-AC-26 上限：偽の時計が `--timeout` に達した周期で、`event: timeout` の行を1つ出して終了コード 124。写し（`--out`）は最後に出したものから変わらない。上限の1秒前までは止まらず、ちょうど上限の回で止まる（境目）。（`tests/test_live_watch.py` の `test_d0031_ac26_*`）
  - D0031-AC-27 上限に達する周期でも、先に記録を1回読み、変わっていれば写しを書いて行を出し（`final` ならそれで 0 で止まる）、そのあとで上限を調べる。（`tests/test_live_watch.py` の `test_d0031_ac27_*`）
  - D0031-AC-28 眠る時間は `--interval` で、残り時間より長く眠らない（`--interval 60 --timeout 5` なら、眠りの長さは 5 を超えない）。（`tests/test_live_watch.py` の `test_d0031_ac28_*`）
  - D0031-AC-29 間隔の境目：`--interval 0.5` と `60` は通り、`0.49`・`60.01`・`0`・`-1`・`abc`・`nan`・`inf` は終了コード 2。`--timeout` も `1` と `86400` は通り、`0.99`・`86401`・`0`・`-1`・`abc`・`nan`・`inf` は終了コード 2。既定値は定数で1か所に持つ。（`tests/test_live_watch_cli.py` の `test_d0031_ac29_*`）
  - D0031-AC-30 周期の数：偽の時計で `--interval 2 --timeout 10` のとき、読みは決まった回数（最初の1回＋眠りごと）で、その回数をテストで固定する（読み損ない・読みすぎの境目を確かめる）。（`tests/test_live_watch.py` の `test_d0031_ac30_*`）
  - D0031-AC-31 見張っている途中で `state.json` が消える（`archive/` に移った）と、閾値の回数だけ連続して読めなかったあとに、`empty: true` の行を1つだけ出す。閾値に達する前に戻れば、何も出さない（戻った中身が前に出したものと同じなら）。（`tests/test_live_watch.py` の `test_d0031_ac31_*`）
  - D0031-AC-32 1回だけ読めない（空・途中で切れた JSON・BOM つき・UTF-8 でないバイト列・権限なし・フォルダに替わった・切れたシンボリックリンク）のあと、すぐに読めて前と同じ中身なら、行は出ない。種類ごとにテストする。（`tests/test_live_watch.py` の `test_d0031_ac32_*`）
  - D0031-AC-33 「記録なし」を出したあと、同じ読めない状態が続いても、2つ目の「記録なし」の行は出ない。読めるようになったら、その写しの行が出る。（`tests/test_live_watch.py` の `test_d0031_ac33_*`）
  - D0031-AC-34 `record start` で作り直された（`archive/` に前の実行が移り、新しい `state.json` が現れる）ときの流れ（消える→新しい中身）で、落ちず、前の実行の `final` では止まらない（前の実行の `final` を出した時点で止まっているので、止まるのは新しい実行の final のとき、または起動時から新しい記録を見ているとき）。起動時に前の実行が final のまま残っていれば、AC-22 のとおり止まる。（`tests/test_live_watch.py` の `test_d0031_ac34_*`）
  - D0031-AC-35 作り直しで中身が前に出したものと完全に同じになった場合は出ない（比べるのは直前に出したものだけ）。違えば出る。（`tests/test_live_watch.py` の `test_d0031_ac35_*`）
  - D0031-AC-36 読み先のフォルダが最初は無く、あとで作られて `state.json` が現れると、その回に出る。それまでは最初の「記録なし」の1行だけ。（`tests/test_live_watch.py` の `test_d0031_ac36_*`）
  - D0031-AC-37 `state.json` が非常に大きい（4 MiB 超）・runs が数万行の記録でも、1回の読みが上限の中で終わり、落ちず、見張りの間に覚えている量が増えない（周期を重ねても保持する写しの文字列は1つ）。（`tests/test_live_watch.py` の `test_d0031_ac37_*`）
  - D0031-AC-38 動いている段のログが無い・壊れている・巨大・`open.log` の名前がおかしい（`../` を含む）でも、落ちず、work_dir の外を読まない（D0027 の読みを使うので、同じ性質を見張りの経路でも確かめる）。（`tests/test_live_watch.py` の `test_d0031_ac38_*`）
  - D0031-AC-39 記録の読み（`read_state`・`read_open_at`）が予期しない例外（`OSError` 以外）を投げる偽でも、見張りは落ちず、読めなかった扱いにして続ける。ただし `KeyboardInterrupt` は通す。（`tests/test_live_watch.py` の `test_d0031_ac39_*`）
  - D0031-AC-40 偽の単調な時計が前の値より小さい値を返しても、経過は負にならず、例外を出さず、上限の判定が早まらない（戻った分は進んでいないものとして扱う）。時計が戻ったあとに通常の進みが続けば、上限に達する。（`tests/test_live_watch.py` の `test_d0031_ac40_*`）
  - D0031-AC-41 偽の時計が大きく飛んで（周期の何倍も進んで）も、1回の周期で読みは1回で、行は多くても1つ。上限を越えていれば、その周期で `timeout`（または先に `final`）。（`tests/test_live_watch.py` の `test_d0031_ac41_*`）
  - D0031-AC-42 テストは本物の `time.sleep` を呼ばない（`sleep` を差し替えていない呼び出しはテストの中で失敗にする）。（`tests/test_live_watch.py` の `test_d0031_ac42_*`）
  - D0031-AC-43 眠りの最中・読みの最中・書きの最中のそれぞれで `KeyboardInterrupt` が起きても、終了コード 130、標準エラーに短い文（トレースバックなし）、一時ファイルが残らず、すでに書いた `--out` は完全な写しのまま。標準出力には行を足さない。（`tests/test_live_watch.py` の `test_d0031_ac43_*`）
  - D0031-AC-44 SIGTERM を受けたとき（実際に子プロセスで起動して送る。Windows では skip）、終了コード 143、一時ファイルが残らず、`--out` は完全な写しのまま。（`tests/test_live_watch_cli.py` の `test_d0031_ac44_*`）
  - D0031-AC-45 標準出力が閉じられている（`BrokenPipeError`）と、落ちずに一時ファイルを残さず終了コード 1。標準エラーにトレースバックを出さない。（`tests/test_live_watch.py` の `test_d0031_ac45_*`）
  - D0031-AC-46 `--out` に連続して書けない（偽の書き込みが `OSError`）：行は出さず、周期ごとにやり直し、閾値の回数で標準エラーに種類だけの文（パス・自由な文を含まない）を出して終了コード 1。途中で1回成功すれば数え直し、成功した回に行が出る。（`tests/test_live_watch.py` の `test_d0031_ac46_*`）
  - D0031-AC-47 見張りの前後で、`state.json`・`logs/`・`99_summary.md` のバイト列と、読み先の中のファイルの一覧が同じ。`--out` と一時ファイル以外は何も作られない。（`tests/test_live_watch.py` の `test_d0031_ac47_*`）
  - D0031-AC-48 見張りの経路で SDK が呼ばれない・子プロセスが起こされない（`subprocess`・`claude_agent_sdk` の使用を、ソースの検査と、偽に差し替えたテストの両方で確かめる）。（`tests/test_live_watch.py` の `test_d0031_ac48_*`）
  - D0031-AC-49 `live snapshot`・`live page` の出力（バイト列）、`record` の各コマンド、写しの `SCHEMA` と項目の一覧、ページの HTML は変わらない（D0027 のテストが通る。`SCHEMA` は 1 のまま）。（`tests/test_live_watch_cli.py` の `test_d0031_ac49_*`）
  - D0031-AC-50 `python -m pipe_in live watch …` と `pipe-in live watch …`（`pipe_in.cli.main`）のどちらからも同じ動きをする。実際に子プロセスで起動して、`--timeout 1` で `timeout` の行と終了コード 124 を確かめる（1件。数秒以内）。（`tests/test_live_watch_cli.py` の `test_d0031_ac50_*`）
  - D0031-AC-51 知らないサブコマンド・知らない引数・省略形（`--out` を `--ou` など）は使い方を出して終了コード 2。（`tests/test_live_watch_cli.py` の `test_d0031_ac51_*`）
  - D0031-AC-52 依存の向きの検査が通り、`pipe_in/engine/` の新しいコードは標準ライブラリと `pipe_in.engine`・`pipe_in.usage` 以外を import しない。`pyproject.toml` の dependencies は変わらない。（`tests/test_architecture.py` の `test_d0031_ac52_*`）
  - D0031-AC-53 `guard.py`・`guard_hook.py`・`pipe_in_guard.py` の止める範囲は変えない。（検証で差分を見る）（検証で `git diff` を見た）
  - D0031-AC-54 `vscode/` のファイルが変わらない。（検証で差分を見る）（検証で `git diff` を見た）
  - D0031-AC-55 古い形の記録（D0017 より前：`since`・`at` が無い。パイプの `state.json`。`archive/<日時>/` の中）を読み先に渡しても、見張りが始まり、1つ目の行が出る。`archive/<日時>/` を渡したときは、その記録が静的なものとして扱われ（`final` があれば1回で止まる）、書き込み先の判定が正しい。（`tests/test_live_watch.py` の `test_d0031_ac55_*`）
  - D0031-AC-56 プラグインのスキル（`plugin/skills/pipe-live/SKILL.md`）が、`name` がフォルダ名と同じ・`description` がある・`disable-model-invocation: true`・見る手順（ページを1回公開・Monitor で `pipe-in live watch`・行ごとに ArtifactData の `set` と `if_version`・`final`/`timeout` の行の扱い）を持つ。使う道具が無い会話で何もしない旨がある。`tests/test_plugin.py` の既存の検査（スキルの一覧・形）に通る。（テスト＋手で読んだ）（`tests/test_plugin.py` の `test_d0031_ac56_*`）
  - D0031-AC-57 スキルに、手元のパス・秘密を書かない。スキルが呼ぶコマンドは `pipe-in live page`・`pipe-in live watch`・`pipe-in live snapshot` のように、読むだけのものだけ（`record`・`pipe-in`（段を流す形）・`--review` を呼ぶ手順を含まない）。（`tests/test_plugin.py` で、禁止する語を見張る）（`tests/test_plugin.py` の `test_d0031_ac57_*`）
  - D0031-AC-58 スキルが示す `pipe-in` のコマンド名・引数が、本体の実際の引数（`--out`・`--interval`・`--timeout`・`--work-dir`）と一致する（スキルの中のコマンドを、本体の引数の一覧と突き合わせるテスト）。（`tests/test_plugin.py` の `test_d0031_ac58_*`）
  - D0031-AC-59 （手で）`docs/guide/usage.md`・`records.md`・`plugin.md`・`docs/guide/README.md`・`README.md`・`/pipe-help` に、使い方、行の形、終了コード（0・124・130・143・1・2）、止まる条件、できないこと（見るだけ・止められない・Monitor が要る）が書かれ、`tests/test_rules.py`・`tests/test_guide.py`・`tests/test_readme.py` が通る。（`tests/test_plugin.py` の `test_d0031_ac59_*`）
  - D0031-AC-60 （手で）`docs/decisions/D0031-<名前>.md` が書かれ、AC ごとにテストの名前が添えてある。（手で読んだ）
  - D0031-AC-61 （実機）claude.ai の Claude Code で `/pipe-in:pipe-live` を呼び、別のターミナルで `pipe-in` を流すと、ページが1回公開され、段の区切りごとに公開し直さずに図が更新され、final で Monitor が終わる。claude.ai と Monitor に頼るため手元の自動テストでは確かめきれない。（実機で確かめる）（claude.ai と Monitor で確かめた）

## 決めたことと理由

### 人に聞いて決めたこと

- 手順のスキルは、利用者向けのプラグインだけに置く（`plugin/skills/pipe-live/`、`/pipe-in:pipe-live`）。目的が利用者のターミナルの実行を見ることで、開発用の `.claude/skills/` にも置くと同じ手順が2か所になってずれるため。
- 会話が裏で `pipe-in` を流す手順（`--pause` で止めて会話で答え、`--review` で続ける）は含めない。見張りは読むだけで、流すと利用料と権限が増え、性質が違う。`--pause` で確認待ちの実行も見張りは止まらないので、あとで別の決定として足せる。
- 見張りを始めたときに、すでに終わった記録しか無ければ、その写しを1回出して止まる。次の実行を待ち続ける `--follow` は足さない。

### 見張り（`pipe-in live watch`）

- 置き場所は `pipe_in/engine/live_watch.py`（標準ライブラリと `engine.live` だけ）と、`live_cmd.py` の `watch` のサブコマンド。写しの作り方（`read_state`・`read_open_at`・`build_snapshot`・`dumps`）と `--out` の守り（`_check_out`）は D0027 のものを使い回し、同じ守りを2か所に書かない。`--out` が既存のフォルダのときだけは `watch` の経路で断る（要件どおり終了コード 2。`live snapshot` の動きは変えない。テスト先行の段で、要件と設計の食い違いとして人が決めた）。
- 純粋な判定（`decide`：前の写しと比べて出すか、連続の読み損ないの回数）と、時計・眠り・読み・書き・出力を差し替えられる回し役（`watch`）に分けた。テストは本物の時間を待たない。
- 比べるのは、写しから `generated_at` を除いた中身（キーを並べた JSON）。覚えるのは直前に出した写しの1つだけ。
- 写しは先に `--out` に書き、書けてから行を出す。書き方は、同じフォルダの一時ファイルに書いてから `os.replace`。途中で止まっても（`KeyboardInterrupt`・SIGTERM も）一時ファイルは消す。会話が読んだときに、書きかけの写しを読まない。
- 行は JSON 1行で、キーは `event`・`seq`・`final`・`empty` の4つだけ。`event` は `snapshot`・`final`・`timeout`。パス・名前・自由な文は入らない（会話がそのまま読むので、命令のような文が入り込む道を作らない）。
- 記録が一瞬読めないだけでは「記録なし」を出さない。3回続けて読めなかったときだけ出す。`record` の書き込みの最中の読み損ねで、ページが空に替わってすぐ戻る揺れを避けるため。
- 終了コード：0（final を出した）・124（上限）・130（Ctrl+C）・143（SIGTERM）・1（`--out` に3回続けて書けない・標準出力が閉じた・設定が読めない）・2（使い方の誤り）。124・130・143 は、よく使われる意味（`timeout` コマンド・信号）に合わせた。
- 既定の間隔は 2 秒（0.5〜60 秒）、上限は 6 時間（1 秒〜24 時間）。経過は単調な時計で数え、時計が戻った分は数えない。

### スキル（`/pipe-in:pipe-live`）

- Monitor の1回の見張りは最長 30 分なので、スキルでは Monitor の `timeout_ms` を最長にし、見張りの `--timeout` を 1750 にする。`timeout` の行か Monitor の期限で止まったら、実行が続いていれば起こし直す。起こし直すと行の `seq` は 1 からになるが、ArtifactData の `if_version` は前の書き込みの結果の `version` を引き継ぐ。初めは上限 6 時間で1回だけ起こす手順だったが、実機の確認で Monitor の上限に気づいて直した。
- 公開は D0027 と同じページを1回だけ（`capabilities` は `{"db": {}}`）。会話は見るだけで、記録を書き換えない・段を流さない・答えない。
- プラグインの版を 0.4.0 に上げた（スキルが増えたため）。

### 互換

- 写しの形（schema 1）・ページ・`live snapshot`・`live page`・`record`・`state.json` は変えない。
- 依存は足さない。guard（`pipe_in/engine/guard.py`・`generator/guard_hook.py`・`.claude/hooks/pipe_in_guard.py`）と VSCode の拡張は触らない。

## 対象外・残った課題

- 第3段階：ページから承認・直してほしい点・中止を押せるようにする。
- 会話が裏で `pipe-in` を流す手順。
- 実行が異常終了して `final` が入らないときは、見張りは上限（スキルでは 1750 秒）まで続く。
- `tests/test_plugin.py` の AC-58 のテストは、スキルの本文に既定の `--timeout 21600` の文字を求める。スキルでは 1750 を使うので、本文に「既定の 21600 は Monitor の 30 分を超えるので 1750 にする」と書いて満たしている。値の一致まで求めない形に直すかは、あとで決める。

## 監査と助言で直したこと

- 監査 A-1：プラグインの説明の文（`plugin/.claude-plugin/plugin.json`・`.claude-plugin/marketplace.json`）に `/pipe-in:pipe-live` を足した。A-2：`safety.md` の「標準エラーにパスを入れない」を、見張りの途中の文に絞り、始める前の断り（`--out` の親が無い・プロジェクトが無い）には渡したパスが出ると書いた。A-3：スキルの読みにくい文を整えた。A-4：この記録を書き、`/pipe-help` と CLAUDE.md に `pipe-in live watch` と `/pipe-in:pipe-live` を足した。
- 助言 V-01：スキルの前提に、Monitor が使えない条件と Windows の Git Bash を足した。V-02：`capabilities` を付けた公開の前に確認を聞かれることがあると書いた。V-03：「使えない」を、公式の言い方に合わせて「既定で切れている」とした（API キー・Bedrock・Vertex・Foundry は使えない）。V-07：更新のあとに `/reload-plugins` を勧めた。
- 直さなかった助言：V-04（ArtifactData の引数が公式の文書に無い。実機の道具の定義で確かめた）、V-05（プラグインの実験の仕組み `monitors` で見張りを自動で始める。実験の項目で、`--out` を決められない）、V-06（frontmatter と置き場所は問題なし）。
- 助言の報告の審査は、総合 0.85・合格（事実の正確さ 0.75・引用の正確さ 1.0・網羅性 0.75・情報源の質 1.0・ツール効率 0.75）。

## 確かめたこと

- `python -m pytest -q` がすべて通る（skip は root で権限なしを作れないものなど）。見張りのテストは本物の時間を待たず、本物の SIGTERM は子プロセスの1件だけ。
- テスト先行の段で、テストの担当が設計どおりの参照実装を一時フォルダに置いて全件が通ること、わざと壊した25通りが全部落ちることを確かめた。
- 実機（AC-61）：一時の記録で、claude.ai にページを db つきで1回公開し、Monitor で `pipe-in live watch --interval 1 --timeout 600` を動かした。`record` の begin → done・wait → finish PASSED で、`snapshot`（seq 1）・`snapshot`（seq 2）・`final`（seq 3、PASSED）の3行が出て終了コード 0。行のたびに ArtifactData の `set`（1回目は `if_version` なし、2・3回目は前の版）が通った。claude.ai の画面での見え方は、持ち主が開いて確かめる（まだ）。
