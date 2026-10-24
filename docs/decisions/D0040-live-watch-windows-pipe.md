# D0040 Windows でも、標準出力が閉じた `pipe-in live watch` が静かに終了コード 1 で止まる

## 目的

`pipe-in live watch` の標準出力の受け側（Monitor など）が閉じたとき、Windows では今までトレースバックと「Exception ignored on flushing sys.stdout」が出て、終了コード 120 で止まっていた。D0031-AC-45 の決まり（落ちずに、一時ファイルを残さず、終了コード 1。標準エラーは短い1文だけ）を Windows でも守り、見張りを起こす側が止まり方を終了コードで見分けられるようにする。

原因：Windows では、読み手のいないパイプへの書き込みが `BrokenPipeError` ではなく `OSError: [Errno 22] Invalid argument`（EINVAL）になる。`live_watch._emit` は `BrokenPipeError` と `ValueError` しか捕まえていなかったので、例外が `watch` の外へ抜け、標準出力の付け替え（`live_cmd._detach_stdout`）も走らず、Python の終了処理の flush がまた失敗していた。

番号について：はじめは D0034 で書いたが、載せ直すたびに main に D0033〜D0039 の記録が入ったので、空いている D0040 に付け直した。

## 機能要件と受け入れ基準

本体の `pipe_in/engine/live_watch.py`・`pipe_in/engine/live_cmd.py` と文書だけを変える。テストは `tests/test_live_watch.py`（LW）と `tests/test_live_watch_cli.py`（LC）。

- FR-01 標準出力への `write`・`flush` で出た `OSError`（`BrokenPipeError` を含む。errno を問わない）と `ValueError` を、標準出力が使えなくなったこととして扱い、`watch` は落ちずに終了コード 1 を返す。行の途中・`timeout` の行・`final` の行のどこで起きても同じ。`KeyboardInterrupt`（130）と `Terminated`（143）は今までどおり通す
  - D0040-AC-01 `flush` が `OSError(errno.EINVAL, …)` を出す偽の標準出力で、1つ目の行・2つ目の行のどちらでも、終了コード 1・標準エラーはちょうど「pipe-in live watch: 標準出力が閉じられました」・トレースバックなし・一時ファイルなし・`--out` は完全な写し。（LW `test_d0040_ac01_einval_on_flush_exits1_quietly`）
  - D0040-AC-02 `write` が EINVAL を出しても AC-01 と同じ。（LW `test_d0040_ac02_einval_on_write_exits1_quietly`）
  - D0040-AC-03 `timeout` の行で EINVAL なら 124 でなく 1、`final` の行で EINVAL なら 0 でなく 1。（LW `test_d0040_ac03_einval_on_the_timeout_line_exits1`・`test_d0040_ac03_einval_on_the_final_line_exits1`）
  - D0040-AC-06 標準出力の `flush` の最中の `KeyboardInterrupt` は 130、`Terminated` は 143（止める合図を飲み込まない）。（LW `test_d0040_ac06_interrupts_on_stdout_flush_are_not_swallowed`）
- FR-02 標準エラーの文は1行だけ。閉じた出力（`BrokenPipeError`・errno が EPIPE か EINVAL の `OSError`・`ValueError`）は「標準出力が閉じられました」。そのほかの `OSError` は「標準出力に書けませんでした（<例外の型の名前>）」で、パスや `strerror` は入れない
  - D0040-AC-04 ENOSPC・EIO・errno の無い `OSError` では、終了コード 1・標準エラーはちょうど「pipe-in live watch: 標準出力に書けませんでした（OSError）」で、例外の文・パスを含まない。一時ファイルなし。文を決める関数 `_stdout_failure_text` の単体の表も確かめる。（LW `test_d0040_ac04_other_oserror_says_could_not_write`・`test_d0040_ac04_stdout_failure_text_by_error`）
  - D0040-AC-05 errno が EPIPE の素の `OSError` も閉じた文になる。（LW `test_d0040_ac05_plain_oserror_with_epipe_is_closed`）
- FR-03 `live_cmd._detach_stdout` は、標準出力の記述子を `os.devnull` に付け替え、付け替えられない（`fileno`・`open`・`dup2` が失敗する）ときは `sys.stdout` を `None` にして終了処理の flush を止める。例外は出さない。呼ぶ条件は変えない
  - D0040-AC-08 標準出力の受け側を先に閉じた実際の子プロセスが、Windows でも Linux・macOS でも、終了コード 1（Linux・macOS ではまだ流していない。「確かめたこと」）・標準エラーは閉じた文の1行だけ（トレースバックも「Exception ignored」も無い）・一時ファイルなし。（LC `test_d0031_ac45_closed_stdout_in_a_real_process_exits1_quietly`。名前は D0031 のまま）
  - D0040-AC-09 偽の `os` と偽の `sys.stdout` で直接呼ぶ。付け替えられるときは `os.devnull` の番号から `fileno()` へ1回付け替えて閉じ、`sys.stdout` は替えない。`dup2`・`open`・`fileno` が失敗する・`sys.stdout` が `None` のときは例外を出さず `sys.stdout` が `None`。`os.devnull` を開いた番号が標準出力と同じなら、付け替えも閉じもしない。（LC `test_d0040_ac09_detach_stdout_redirects_to_devnull`・`test_d0040_ac09_detach_stdout_falls_back_to_none`）
  - D0040-AC-10 テストが `stdout` を差し替えたときは付け替えない。本物の標準出力で終了コード 1 のときだけ1回付け替え、0・124 では付け替えない。（LC `test_d0040_ac10_injected_stdout_skips_detach`・`test_d0040_ac10_real_stdout_detaches_once_on_exit1`）
- FR-04 `--out` への書き込みの失敗の扱いは変えない。標準出力の失敗と混ざらない
  - D0040-AC-07 `--out` への書き込みが EINVAL を出しても、標準出力が閉じた扱いにならず、3回続けば「--out に書けませんでした（OSError）」で 1。（LW `test_d0040_ac07_einval_on_out_write_is_not_stdout_closed`）
- FR-05 行の形・写しの形（schema 1）・`state.json`・`live snapshot`・`live page`・終了コードの一覧（0・1・2・124・130・143）は変えない
  - D0040-AC-11 前からの `tests/test_live_watch.py`・`tests/test_live_watch_cli.py`・`tests/test_live_snapshot.py` がそのまま通る。
  - D0040-AC-12（手で・検証の段）`pipe_in/engine/guard.py`・`generator/guard_hook.py`・`.claude/hooks/pipe_in_guard.py`・`vscode/`・`pyproject.toml` に差分が無い（`git diff` で見る）。
- FR-06 文書をそろえる
  - D0040-AC-13（手で）`docs/guide/usage.md` の終了コードの表の 1 の行に「標準出力が閉じられた・書けなくなった」が書かれ、`plugin/skills/pipe-live/SKILL.md` の終了コード 1 の説明にも標準出力が閉じた・書けないことが入り、この記録に AC ごとのテストの名前がある。`tests/test_rules.py`・`tests/test_guide.py` が、main にもとからある D0033 の分（D0033 の記録がまだ無いための AC の ID の欠けと、D0033-AC-08 の赤）のほかは通る。

## 決めたことと理由

- **標準出力の `write`・`flush` の `OSError` は errno を問わず全部捕まえる。** EINVAL だけに絞ると、ディスクがいっぱい（ENOSPC）・EIO・別の環境の別の errno で、またトレースバックと 120 になる。包むのは標準出力への `write` と `flush` の2つの呼び出しだけで、`--out` への書き込みは別の所で捕まえているので、ほかの失敗を飲み込まない。終了コード 1 はもともと「書けない・出力が閉じた」の意味なので、意味も変わらない。
- **閉じたのか書けないのかで、標準エラーの文を分ける**（明示する）。EINVAL は閉じた以外でも出うるが、標準出力への書き込みではまず閉じたパイプなので、閉じた扱いにする。書けないときの文は `--out` の文と同じ作りで、例外の型の名前だけを入れる（パス・`strerror` を出さない決まりを守る）。どの `OSError` も「閉じられました」にする案は、ディスクがいっぱいのときなどに事実と違う文になるので選ばなかった。
- **付け替えに失敗したら `sys.stdout` を `None` にする逃げ道を足した。** D0032 の `_quiet_exit_streams` と同じ考え。無いと、付け替えに失敗した環境で 120 に戻る。
- **`os.devnull` を開いた番号が標準出力の番号と同じなら、付け替えも閉じもしない。** 標準出力の記述子がもう閉じていたときに起きる。今までの作りでは、そのあとの `close` で標準出力の記述子を自分で閉じてしまい、終了処理の flush が失敗しうる。
- `_StdoutClosed` の名前は変えず、標準エラーに出す文を持たせた（外から使われていない内側の型で、名前を替えると差分が増えるだけ）。
- 実プロセスのテストは、子に `PYTHONIOENCODING=utf-8` を渡す（テストの `child_env()`）。Windows で UTF-8 モードでないと、子は日本語の1文を手元の文字コードで書き、テストの UTF-8 の読みと合わない。製品の標準エラーの文字コードは変えない。
- D0031 の記録は書き換えない。D0031-AC-45 の決まりを、Windows と、閉じた以外の書けない場合に広げたのがこの記録。
- 依存は足さない（新しい import は標準ライブラリの `errno` だけ）。守る仕組み（`guard.py`・`guard_hook.py`・`pipe_in_guard.py`）は触らず、止める範囲も変えない。
- 受け入れたリスク：`sys.stdout = None` の逃げ道を通ったときは、`sys.__stdout__` が書けなかったバイトを持ったまま残る。終了処理の flush は `sys.stdout` しか見ないので終了コードは 1 のままだが、そのあとの片付けで「Exception ignored」が標準エラーに出るかもしれない。この道は付け替え（`os.open`・`dup2`）が失敗する珍しい環境だけで、D0032 も同じ形を選んでいる。単体のテスト（AC-09）で関数の動きを確かめ、終了処理までは確かめない。

## 対象外・残った課題

- `live snapshot`・`live page` を標準出力に出すときの、閉じた出力の扱い（`live_cmd._emit`。受け側が閉じると今もトレースバックが出る。1回出して終わるコマンドで、D0027 に決まりが無い）。
- `generator/guard_hook.py`・`.claude/hooks/docs_reminder.py`・`generator/judge_score.py`・段を流す本体・`record` の標準出力の扱い。`.claude/hooks/pipe_in_guard.py` は D0032 で扱った。
- `pipe-in live watch` の標準エラーの文字コード（Windows で UTF-8 モードでないときは手元の文字コードで書かれる）。
- Windows の SIGTERM（D0031-AC-44 は Windows で skip のまま）。
- 拡張（`vscode/`）。

## 確かめたこと

- テスト：`tests/test_live_watch.py`・`tests/test_live_watch_cli.py`・`tests/test_live_snapshot.py` がすべて通る（skip は前からの Windows の skip だけ）。テスト先行では、足したテストのうち 25 件が期待した理由（偽の出力が出した `OSError` が `watch` から抜ける・まだ無い関数・`sys.stdout` が `None` にならない・同じ番号で `close` が呼ばれる・実プロセスで終了コード 120 とトレースバック）で落ち、守るためのテストは前の作りでも通ることを、失敗の文まで読んで確かめた。
- Windows の実プロセス（AC-08）：直す前は終了コード 120 と、標準エラーにトレースバックと「Exception ignored on flushing sys.stdout」が出た。直したあとは終了コード 1 と閉じた文の1行だけになった。Linux・macOS の実プロセスでは、この段ではまだ流していない（前から通っていたテスト）。
- `sys.stdout = None` の逃げ道を通ったときの、実際の終了処理の様子は確かめていない（上の受け入れたリスク）。
- 検証のあとの監査で4件（AC-13 の確かめと D0033 の今の事実のずれ・AC-08 の Linux・macOS がまだのこと・AC-13 の文言・`pipe-live` のスキルの終了コード 1 の説明の抜け）が挙がり、人が4件とも承認して直した。助言と審査は、機能の変更に `.claude/`・`plugin/`・`runner.py`・guard 類が無かったので流していない（監査で直した `pipe-live` のスキルの1文は、終了コードの説明だけ）。
