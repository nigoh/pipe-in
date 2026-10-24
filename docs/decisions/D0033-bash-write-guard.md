# D0033 段の Bash による書き込みを、段の書き込み範囲で止める（リダイレクト・tee・sed -i・cp・mv・touch・python -c など。先が読めなければ止める）

## 目的

パイプの段の `Bash` が、リダイレクト・`tee`・`sed -i`・`cp`・`mv`・`touch`・`python -c` などで、段の `access`・`writes` の範囲の外（テストだけ書ける段がコードを、コードだけ書ける段がテストを、`access = "read"` の段が成果物以外を、プロジェクトの外を）書き換えられないようにする。`Write`・`Edit` に掛けている範囲（`check_tool` の `can_write`）を、コマンドの文字列から書き込み先が読み取れる `Bash` にも掛ける。

きっかけ：isography の街並みの醸成のパイプで、`access = "tests"` の段と `access = "code"` の段が、`Bash` でテストやコードを書き換えた。

## 機能要件と受け入れ基準

### 機能要件

- FR-01 リダイレクト（`>`・`>>`・`>|`・`&>`・`&>>`・`N>`・`N>>`・`>&ファイル`・`<>`）の先を見る。先が段の範囲外なら止める。`/dev/null`・`/dev/stdout`・`/dev/stderr`・`/dev/tty`・`/dev/fd/N` と、fd の付け替え（`2>&1`・`>&2`・`>&-`・`N>&M`）は通す。
- FR-02 `tee`・`sed -i`（`-i.bak`・`-ni`・`--in-place`）・`perl -i`（`-pi`）の書き込み先のファイルを見る。
- FR-03 `cp`・`mv`・`ln`・`install` の宛先（`-t DIR`・ディレクトリ宛先を含む。`mv` は元も）、`touch`・`rm`・`unlink`・`rmdir`・`truncate`・`dd of=` の先、`find … -delete` の探す場所、`git restore`・`git rm`・`git mv` のパスを見る。
- FR-04 `python`・`python3`・`py` の `-c`（と、標準入力から読ませるヒアドキュメント・`<<<`）と、`node` の `-e`・`--eval` のコードの中の、書き込む形（`open(先, 'w'|'a'|'x'|'+')`・`Path(先).write_text/write_bytes/touch/unlink`・`os.remove/rename/replace/makedirs/mkdir/rmdir`・`shutil.copy/copy2/copyfile/copytree/move/rmtree`、`fs.writeFileSync/appendFileSync/writeFile/appendFile/unlinkSync/rmSync/mkdirSync/copyFileSync/renameSync`）の先が文字で書かれていれば見る。
- FR-05 先が文字で読み取れる場合の判定は、`Write`・`Edit` と同じ。プロジェクトの外なら「プロジェクトの外には書き込めません」、段の範囲外なら「この段で書き込めるのは {write_scope_hint} だけです（{rel} は対象外）」の形の理由で止める。相対パスは、そのときの作業フォルダ（`cd` を追う）から求める。
- FR-06 プロジェクトの外でも、一時の場所（`/tmp`・`/var/tmp`・`tempfile.gettempdir()`・書いた文字がそのまま `$TMPDIR/…`・`${TMPDIR}/…`）の下は通す。`..` を含めて一時の場所の外に出るものは通さない。プロジェクトの中のキャッシュ（`__pycache__`・`.pytest_cache` など）は特別扱いしない：コマンドの副作用は見ず、コマンドの文字列で明示した書き込み先だけを、ほかのパスと同じに判定する。
- FR-07 書き込みの形を見つけたのに先が読み取れない（変数・`$(...)`・バッククォート・`xargs` や `find -exec` が渡す `{}`・読めない `cd` のあとの相対パス・先が文字でない `open(変数, 'w')`）ときは止める（安全側）。理由に、先を文字で書くよう案内する。
- FR-08 コマンドの読み方：引用符（`'…'`・`"…"`・`\`）、`;`・`&&`・`||`・`|`・`&`・改行で続くコマンド、`( )` の部分シェル、ヒアドキュメント（本文は書き込みとして数えない。`cat > f <<EOF` の `f` は数える。引用符なしの区切りの本文の中の `$(...)` は調べる）、`$(...)`・バッククォート・`<(…)`・`>(…)` の中のコマンド、`bash -c`・`sh -c`・`eval` の文字列、`env`・`nohup`・`time`・`timeout`・`nice`・`command`・`exec` と `VAR=値` の接頭、`xargs`・`find -exec`。引用符の中の `>` は書き込みとみなさない。読み取りに使うのは標準ライブラリだけで、シェルそのものは起こさない。
- FR-09 読めない入力は止める：文字でないコマンド（空のコマンドは今までどおり通す）、引用符や `$(` が閉じていない、入れ子が 5 段を超える。
- FR-10 見分けられない形は止めない：`python file.py`・`make`・`sh script.sh`・`./gen.sh`・`npm run …`・パイプで `sh`・`python` に渡すコード・`git apply`・`patch`・`tar -x` など、コマンドの文字列から書き込み先が分からないもの。テストを流すコマンド（`pytest`・`npm test`・`sh check.sh` など）は、書く副作用があっても、今までどおり通る。
- FR-11 `cd`・`pushd`・`popd` を追う。呼び出しをまたいで作業フォルダが変わりうるので、ガード（段の1回の実行ごとに作る）が「ありうる作業フォルダ」の集まりを覚え、相対パスはその全部で判定する（1つでも範囲外なら止める）。`cd` の先が読めない・存在しないときは作業フォルダを「不明」にし、不明のあいだの相対パスの書き込みは止める。
- FR-12 `access = "read"` の段（書けるのは自分の成果物だけ）と、`writes` で絞った段も、同じ規則で絞る（`can_write` に任せる）。`protected_paths`・パイプのフォルダ（`_outside_pipe`）の除外もそのまま効く。
- FR-13 `DANGEROUS_BASH` の判定は、今までどおり先に効く。`allow_bash = false` の段は今までどおり `Bash` 自体を止める。
- FR-14 `.claude/hooks/pipe_in_guard.py` と `generator/guard_hook.py` は変えない（どちらも許すコマンドの一覧で、書き込みの形はもともと通らない）。同じ形が止まり続けることをテストで押さえる。
- FR-15 本体の依存の向きを守る。新しい部品は `pipe_in/engine/` に置き、標準ライブラリだけを使う。

### 受け入れ基準

- D0033-AC-01 `access = "code"` の段で `echo x > tests/test_a.py`・`echo x >> tests/test_a.py`・`echo x &> tests/log.txt`・`echo x >| tests/t.py` は止まり、理由は「この段で書き込めるのは … だけです（tests/test_a.py は対象外）」の形。
- D0033-AC-02 範囲の中への書き込み（`code` の段の `echo x > src/a.py`、`tests` の段の `echo x > tests/test_a.py`、開発フローの実装の段の `echo x > docs/pipeline/04_implementation.md`）は通る。
- D0033-AC-03 `/dev/null` への書き込みと fd の付け替え（`ls > /dev/null 2>&1`・`ls 2>&1`・`ls >&2`・`pytest -q 2>&1 | tail -20`）は、どの段でも通る。
- D0033-AC-04 `tee`（`-a` を含む）・`sed -i`（`-i.bak`・`-ni`・`--in-place=.bak`・`-e` つき）・`perl -pi -e` の書き込み先が範囲外なら止まる。`sed -n '1,5p' tests/a.py`（`-i` なし）と、先が範囲内のものは通る。
- D0033-AC-05 `cp`・`mv`・`ln -s`・`install` は宛先（`-t`・末尾 `/`・複数の元でのディレクトリ宛先を含む）が範囲外なら止まる。`mv` は元が範囲外でも止まる。`cp tests/a.py /tmp/a.py` や `cp src/a.py src/b.py`（`code` の段）は通る。
- D0033-AC-06 `touch`・`rm`・`unlink`・`rmdir`・`truncate`・`dd of=`・`git restore`・`git rm`・`git mv` の先が範囲外なら止まる。`rm build/tmp.txt`（実装の段）は今までどおり通る。
- D0033-AC-07 `find <範囲外のフォルダ> … -delete` は止まる。`find … -exec <書き込みの形> {} \;` と `… | xargs rm` は、渡す先が読めないので止まる。書き込みの形でない `find . -name x -exec grep y {} \;` は通る。
- D0033-AC-08 `mkdir` は、プロジェクトの外（一時の場所を除く）・読めない先のときだけ止め、プロジェクトの中は通す（空のフォルダを作るだけで、テストやコードの中身は変えられないため）。
- D0033-AC-09 `python -c`・`python3 -c`・`node -e` の中の書き込みの形（FR-04 の一覧）の先が文字で書かれ、範囲外なら止まる。範囲内・読み取り（`open('x')`・`open('x','r')`）は通る。
- D0033-AC-10 `python - <<'EOF' … open('tests/t.py','w') … EOF` のように、標準入力から読ませるコードも `-c` と同じに見る。コードに書き込みの形が無い `python - <<'EOF' print(1) EOF` は通る。
- D0033-AC-11 プロジェクトの外：`echo x > /etc/hosts`・`echo x > ../outside.txt`・`echo x > ~/note.txt`・`echo x > /tmp/../etc/passwd`・`tee /etc/x` は止まり、理由は「プロジェクトの外には書き込めません」。
- D0033-AC-12 一時の場所：`echo x > /tmp/a.txt`・`pytest -q 2>&1 | tee /tmp/out.log`・`echo x > $TMPDIR/a.txt`・`echo x > ${TMPDIR}/a.txt`・`mkdir -p /tmp/work` は通る。同じコマンドの中か前の呼び出しで `TMPDIR`・`TEMP`・`TMP`・`HOME` に代入があるときは、`$TMPDIR/…`・`~/…` は読めない先として止まる。
- D0033-AC-13 先が読み取れない書き込みの形は止まり、理由に「先を文字で書いてください」が入る：`echo x > $OUT`・`tee "$F"`・`cp a.py $(dirname b)/x`・`touch $(mktemp)`・`` echo x > `pwd`/a ``・`python -c "open(p,'w')"`。
- D0033-AC-14 続くコマンドと入れ子：`ls; echo x > tests/a.py`・`ls && cmd | tee tests/a.py`・改行区切り・`( … )`・`bash -c 'echo x > tests/a.py'`・`echo $(touch tests/a.py)`・`env FOO=1 timeout 10 tee tests/a.py` は、どこかに範囲外の書き込みがあれば止まる。範囲内だけなら通る。
- D0033-AC-15 引用符とヒアドキュメント：`echo "a > b"`・`grep '>' src/a.py`・`cat <<'EOF'`（本文に `> tests/a.py`）は書き込みでないので通る。`cat > src/app.py <<'EOF'`（`tests` の段）は止まる。引用符なしの区切りの本文の `$(touch tests/a.py)` は止まる。
- D0033-AC-16 `cd` を追う：`cd tests && touch a.py`（`code` の段）は止まり、`cd src && touch a.py` は通る。`cd tests` を通したあとの別の呼び出しの `touch a.py` も止まる（作業フォルダが変わった可能性を残す）。`cd $X` のあとの `touch a.py` は止まる。
- D0033-AC-17 `access = "read"` の段：自分の成果物（`echo x > docs/pipeline/xx.md`）への書き込みは通り、`echo x > src/a.py`・`cp a b`・`sed -i … src/a.py` は止まる。
- D0033-AC-18 `writes` で絞った段（`writes = ["out/*.svg"]` など）：絞りの中の先は通り、絞りの外は止まる。`protected_paths` に当たる先は止まる。
- D0033-AC-19 今までのコマンドは止まらない：`pytest -q`・`python -m pytest -q tests/ -x`・`npm test`・`npm --prefix vscode test`・`sh check.sh --fast`・`git status`・`pip install pytest`・`pytest --junitxml=report.xml`・`ls`・`pytest > /dev/null 2>&1`。既存のテスト（`tests/test_pipeline.py`・`test_pipe.py`・`test_agent_guard.py` など）が変更なしで通る。
- D0033-AC-20 見分けられない形は止めない：`python build.py`・`make test`・`./gen.sh`・`echo hi | python script.py`・`git apply x.patch`・`tar xf a.tar` は通る（すり抜けの道として決定の記録に書く）。
- D0033-AC-21 `DANGEROUS_BASH` が先に効く：`git push > /dev/null`・`rm -rf tests > /dev/null` は、書き込み先が範囲内でも今までの理由で止まる。`allow_bash = false` の段の `Bash` は「この段では Bash を使えません」のまま。
- D0033-AC-22 読めない入力：引用符が閉じていない（`echo "abc > x`）・`$(` が閉じていない・入れ子が 5 段を超える（`bash -c 'bash -c …'`）・`command` が文字でない（`None`・`[]`）ときは、落ちずに理由を返して止まる。空のコマンドは今までどおりの扱い。
- D0033-AC-23 止めた操作は、ほかの止めた操作と同じく `StageRun.denials` に `"Bash: <理由>"` の形で残る（`on_deny`）。段は失敗にならない。
- D0033-AC-24 `make_guard_hook` が作るガードを通る本物の経路でも、AC-01・AC-11・AC-16 が同じに止まる。2つのガードは作業フォルダの覚えを分け合わない。
- D0033-AC-25 `generator/guard_hook.py`（pipe-builder）と `.claude/hooks/pipe_in_guard.py`（tester・coder・verifier・analyst・documenter・読むだけの役）は変えず、`echo x > f`・`tee f`・`sed -i`・`cp`・`mv`・`touch`・`python -c …` が今も止まる。
- D0033-AC-26 新しい部品 `pipe_in/engine/bashwrite.py` は標準ライブラリだけを読み、`pipe_in.dev`・`pipe_in.pipe`・`pipe_in_generator` を読まない（`tests/test_architecture.py`）。
- D0033-AC-27 （古い形）記録（`state.json`・`99_summary.md`・`logs/*.jsonl`）・終了コード・`pipeline.toml`・`pipe.toml`・置き場所は変わらない。新しい設定項目は足さない。止めるようになった操作は、今の `denials` の形で残る。

監査のあとに足した受け入れ基準（`code` の段で確かめる）：

- D0033-AC-28 `tee --output-error tests/a.py` は止まる。`--output-error` は `=` つきのときだけ値を持つ（`tee --output-error=warn tests/a.py` も止まる）。
- D0033-AC-29 フォルダの `mv`・`rmdir`（`mv tests x`・`mv tests/ /tmp/x`・`rmdir tests`）は、フォルダそのものとその下の両方が書けるときだけ通す。`mv src/a.py src/b.py` は通る。
- D0033-AC-30 最後の部品に glob（`*`・`?`・`[`）を含む先は、本物のファイルを指さないので読めない先として止める（`rm *.py`・`rm ?est_a.py`・`git restore '*.py'`）。一時の場所の下（`rm /tmp/*.log`）は通す。`:` で始まる `git` の pathspec（`git restore :/tests`）は止める。
- D0033-AC-31 `node --eval=…` を `-e` と同じに読む。`Path(先).open('w')` のモードも見る（`Path('tests/a.py').open('w')` は止まり、`open()`・`open('r')` は通る）。
- D0033-AC-32 根や上を指すフォルダの操作（`find . -delete`・`git restore .`）は、プロジェクトの中に実際にあるファイルを下まで見て、1つでも段の範囲外があれば止める。`.git` の中は見ない。見るファイルが 5000 を超えたら止める（安全側）。

## 決めたことと理由

### 聞かずに決め、推しで確定したこと

- 要件メモに無い `rm`・`unlink`・`rmdir`・`ln`・`install`・`truncate`・`dd of=`・`find -delete`・`git restore/rm/mv`・`node -e`・`python` のヒアドキュメントも見る。テストの削除や書き換えも同じ被害で、同じ仕組みで足りるため。選ばなかった形：メモの一覧だけ。
- `mkdir` はプロジェクトの中なら通す。空のフォルダは中身を変えず、`writes = ["out/*.svg"]` の段が `mkdir -p out` で止まるのを避けるため。
- プロジェクトの中のキャッシュ（`__pycache__`・`.pytest_cache` など）は特別扱いしない。コマンドの副作用は見ず、文字で書いた書き込み先だけを、ほかのパスと同じに判定する。
- 書き込みの形を見つけたのに先が読めない（変数・`$(...)` など）ときは止める（安全側）。`out=$(mktemp); cmd > "$out"` も止まるので、理由で先を文字で書くよう案内する（一時の場所なら `/tmp/…` の文字の先は通る）。選ばなかった形：読めなければ通す。
- 読み方は自前の走査器にした。`shlex` は `"$x"` と `'$x'` を区別できず、ヒアドキュメントも読めないため。標準ライブラリだけで、シェルは起こさない。
- `cd` は、ガード（段の1回の実行ごとに作る）が「ありうる作業フォルダ」の集まりとして覚え、相対パスはその全部で判定する。Claude Code の `Bash` が呼び出しをまたいで `cd` を覚えるかどうかによらず、安全側になる。
- `find <フォルダ> -delete` などのフォルダの操作は、フォルダそのものとその下の両方が書ける段だけ通す（`find tests -delete` を止めるため）。
- この Bash の書き込みの判定だけは「止める形の一覧」にした。`guard.py` は許すものの一覧で書く決まり（`docs/development/principles.md`）だが、Bash は何を実行するかがコマンドの文字列から決まらないので、許す一覧では書けない。許す一覧の役は、段ごとの `allow_bash`（Bash そのものを使わせるか）と、`allowed_tools` が受け持つ。そのうえで、文字から書き込み先が読める形を止め、形は分かるのに先が読めないときも止めて安全側に倒す。
- 書いた形のほかに、安全側として止めるもの：`find` の `-fprint`・`-fprint0`・`-fls` は、書く先に加えて探す場所のフォルダも見る。`git -C`・`--git-dir`・`--work-tree` を付けた `restore`・`rm`・`mv` は、作業ツリーの場所が読めないので止める。
- `mkdir`（と `install -d`）は、プロジェクトの中なら `can_write`・`protected_paths`・パイプのフォルダの除外を見ずに通す（FR-12 の例外）。`python -c` の `os.makedirs` は普通の書き込みとして判定するので、`writes` で絞った段では止まることがある。
- `.claude/hooks/pipe_in_guard.py` と `generator/guard_hook.py` には入れない。どちらも許すコマンドの一覧で、`> ; | $` などの記号を含むコマンドは元から通らないため（`guard_hook.py` は本体を読み込まない決まりもある）。同じ形が今も止まることをテストで押さえる。
- 今まで通っていた範囲外への書き出し（例：テストの段の `pytest > out.log`）は止まるようになる。`/tmp/…` か `$TMPDIR/…` に書けば通る。止める範囲を広げるだけなので受け入れる。

## 止める範囲を広げることと、すり抜けの道

止める範囲を広げるだけで、今まで止めていたもので通るようになるものは無い（`DANGEROUS_BASH` は今までどおり先に効く）。依存は足さない。

ガードはサンドボックスではない。コマンドの文字列から決まった形で書き込み先が読めるものを止めるところまでで、次の道は残る（段の指示文で禁じ、批評や検証で差分を見る）。

- 書くコードが別のファイルにあるもの：`python file.py`・`make`・`sh script.sh`・`./gen.sh`・`npm run …`・pytest の fixture。
- 段が範囲の中に書いたスクリプトを、次の呼び出しで流す二段の書き方。
- パイプで渡すコード（`… | sh`・`… | python`）。
- 先を読まない道具：`git apply`・`patch`・`tar -x`・`unzip`・`awk -i inplace`・`sed` の `w` コマンド・`ed`・`ruby -e`・`perl -e` の中の書き込み・`pip install -t`。
- `python -c` で、`__import__`・`getattr`・`subprocess` などを使った見分けられない書き方。
- `eval "$x"`・`bash -c "$X"`・`python -c "$CODE"` のように実行する文字が展開だけのものと、コマンドの名前が変数のもの（`$CMD tests/a.py`）。書き込みの形が見えないので通る。
- 上に挙げた接頭（`env`・`nohup`・`time`・`timeout`・`nice`・`command`・`exec`）のほかの、コマンドを包む道具：`env -S '…'`・`setsid`・`flock`・`ionice`・`stdbuf`・`script -c`・`parallel` など。
- 同じコマンドの中で張ったリンク越しの書き込み（`ln -s /etc/hosts src/l && echo x > src/l`）。判定はその時点の実物でリンクを解くので、まだ無いリンクは見えない。
- 先がオプションなどにある、ほかの道具（`sort -o`・`awk` の `print > "…"`・`gzip`・`split`・`shred`・`gcc -o` など）と、作業ツリーを書き換える `git` のサブコマンド（`stash`・`merge`・`pull`・`revert`・`cherry-pick`・`am` など）。
- 公式の文書も、Bash の許可・拒否の規則は「コマンドの文字列に合うだけで、境界ではない。文字列によらない強制には sandbox を使う」と書いている（https://code.claude.com/docs/en/permissions）。このガードは公式の言う PreToolUse の使い方で、境界ではない。

## 受け入れたリスク

- 安全側の誤検知：`[[ a > b ]]` の `>` もリダイレクトとして読むので、`b` が範囲外なら止まる。Git Bash の `/c/…` 形式はプロジェクトの外とみなして止まる。
- 呼び出しをまたいだ `cd` を覚えるので、`cd tests` を通したあとは、`code` の段の相対パスの書き込みが止まることがある（絶対パスか `cd` で戻れば通る）。

## 対象外・残った課題

- 上のすり抜けの道を塞ぐこと。後の機能で、Agent SDK の `sandbox`（`ClaudeAgentOptions(sandbox=...)`）を重ねる。OS が Bash とその子プロセスの書き込みを止めるので、`python file.py`・`make` なども塞げる（https://code.claude.com/docs/en/sandboxing・https://code.claude.com/docs/en/agent-sdk/python）。そのときに決めること：
  - `failIfUnavailable: true`（Python SDK の既定は false で、起動できないと素のまま動く）と `allowUnsandboxedCommands: false`（既定は true で、モデルが sandbox の外で動かせる）を付ける。`bypassPermissions` と組まず、`excludedCommands` を広くしない。
  - 既定の書き込み先は作業フォルダ・一時フォルダなどで、`allowWrite` は足すだけ。段の範囲に狭めるには `filesystem.denyWrite` に範囲の外を並べる形になる。glob と優先の決まりは、実機で確かめてから決める。
  - sandbox は Bash（と PowerShell・Monitor）にだけ効き、`Write`・`Edit` には効かないので、`can_write` の判定は残す。ネイティブの Windows では使えない（WSL2 が要る）。
- 呼び出しをまたいだ `cd`：公式の文書では、メインのセッションでは範囲の中の `cd` が次の Bash に引き継がれ、サブエージェントでは引き継がれない（https://code.claude.com/docs/en/tools-reference）。段がどちらに当たるかで変わるので、ありうる作業フォルダを全部見る今の作りにした。`CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR=1` を段に渡せば単純にできるかは、後で確かめる。
- テストを流すコマンドが書く副作用の監視。
- Windows のコマンドプロンプト・PowerShell の書き方（PowerShell は今までどおり使えない道具）。
- VSCode の拡張（記録の形が変わらないため、触らない）。

## 番号

D0031・D0032 の次の空いた番号。D0032（段の中のサブエージェントの呼び方）の上に積んでいる。

## 確かめたこと

- `tests/test_bash_write_guard.py`（止める例・通す例を `check_tool` と `make_guard_hook` の両方の経路で）と、`tests/test_guard_hook.py`・`tests/test_pipe_in_guard.py`・`tests/test_architecture.py` の D0033 のテスト、全体のテストが通った（SDK は呼ばない）。
- 実機の SDK の段で止まるかは、まだ確かめていない。
- 監査と助言のあとに足した AC-28〜32 も、テストが通った。AC-32 のテストの前提（パイプのフォルダの `pipe.toml` は `code` の段の範囲外なので、根を指す削除で止まるのが正しい）は、実装の段の異議を受けて直した。

## 監査と助言

検証で合格したあと、矛盾監査（A-01〜A-14）と公式の文書と照らした助言（V-01〜V-09）を流した。助言の報告の審査は総合 0.94 で合格。人が「コードと文書を直し、sandbox は後の機能にする」を選んだ。
- コードで直した：A-01（`tee --output-error`）、A-02（フォルダの `mv`・`rmdir`）、A-04（glob と `:` の pathspec）、A-07（`node --eval=`・`Path().open(モード)`）、A-12（根を指すフォルダの操作は実際のファイルを見る）。テストは D0033-AC-28〜32。
- 文書で直した：A-03・A-05・A-06・A-13（すり抜けの道に足した）、A-08（止める形の一覧にした理由）、A-09（理由の文の書き方）、A-10・A-11（安全側に止めるもの・`mkdir` の例外）、A-14（開発の文書の検査の表）、V-07（公式の文書の出典）。
- 後の機能にした：V-01〜V-05（Agent SDK の `sandbox` を重ねる。「対象外・残った課題」に決めることを書いた）。V-06・V-08・V-09 は今のままでよいことの確認。

