"""段の Bash による書き込みを、段の書き込み範囲で止める（D0033）。

Write・Edit に掛けている can_write・write_scope_hint を、コマンドの文字列から読み取れる Bash の書き込み先にも掛ける。
段の範囲は tmp_path に作ったパイプの段（pipe_in.pipe.specs.build_pipe_specs）と開発フローの実装の段（pipe_in.dev.specs.build_specs）で作り、
check_tool と、make_guard_hook が作る本物のガードの両方を通す。SDK は呼ばない。

新しい部品（pipe_in.engine.bashwrite・check_tool の bash_state）は、使うテストの中で読み込む
（ほかのテストまで import で落とさないため。落ちる理由が、まだ無い部品の名前で読める）。
"""

from __future__ import annotations

import asyncio
import dataclasses
import shlex
from pathlib import Path

import pytest

from pipe_in.engine.config import load_config
from pipe_in.engine.guard import check_tool, make_guard_hook
from pipe_in.pipe import definition as pd
from pipe_in.pipe import specs as ps

SCOPE = "この段で書き込めるのは"
OUT = "プロジェクトの外には書き込めません"
UNREAD = "先を文字で書いてください"
UNPARSE = "Bash のコマンドを読み取れなかったため止めました"
NOBASH = "この段では Bash を使えません"

VIAS = ["check_tool", "hook"]


# ---- 段の範囲の補助 ---------------------------------------------------------


def _stage(name: str, access: str, extra: str = "") -> str:
    return f'\n[[stages]]\nname = "{name}"\nlabel = "{name}の段"\noutput = "{name}.md"\naccess = "{access}"\nprompt = "{name}をする"\n{extra}'


PIPE = (
    '[pipe]\nkind = "linear"\nlabel = "試し"\n'
    + _stage("code", "code", "bash = true\n")
    + _stage("tests", "tests", "bash = true\n")
    + _stage("read", "read", "bash = true\n")
    + _stage("writes", "code", 'bash = true\nwrites = ["out/*.svg"]\n')
    + _stage("nobash", "code")
)

# 種類 → （段の名前, protected_paths）。impl は開発フローの実装の段
KINDS = {
    "code": ("code", []),
    "tests": ("tests", []),
    "read": ("read", []),
    "writes": ("writes", []),
    "nobash": ("nobash", []),
    "prot": ("code", ["secrets/*"]),
    "impl": ("implement", []),
}


def make_env(tmp_path: Path, kind: str):
    """（cfg, spec）。作業フォルダは tmp_path/proj。tests・src・out・build・secrets のフォルダを作っておく。"""
    project = (tmp_path / "proj").resolve()
    for d in ("tests", "src", "out", "build", "secrets", "docs/pipeline"):
        (project / d).mkdir(parents=True, exist_ok=True)
    stage, protected = KINDS[kind]
    cfg = load_config(project, None, auto_approve=True)
    if protected:
        cfg = dataclasses.replace(cfg, protected_paths=protected)
    if kind == "impl":
        from pipe_in.dev.specs import build_specs

        return cfg, build_specs(cfg)[stage]
    d = project / "pipes" / "pipe-in-p"
    d.mkdir(parents=True, exist_ok=True)
    (d / "pipe.toml").write_text(PIPE, encoding="utf-8")
    pipe = pd.load_pipe(d)
    pcfg = cfg.for_pipe(pipe.name, own_work_dir=False)
    return pcfg, ps.build_pipe_specs(pcfg, pipe)[stage]


def make_guard(cfg, spec, denied: list | None = None):
    """本物の経路：make_guard_hook が作るガード（段の1回の実行ぶん）。"""
    return make_guard_hook(
        project_dir=cfg.project_dir, can_write=spec.can_write, allow_bash=spec.allow_bash,
        write_scope_hint=spec.write_scope_hint, allowed_tools=spec.allowed_tools,
        on_deny=(lambda t, r: denied.append(f"{t}: {r}")) if denied is not None else None,
    )


def hook_reason(guard, tool_input) -> str | None:
    out = asyncio.run(guard({"tool_name": "Bash", "tool_input": tool_input}, "t-1", None))
    if out == {}:
        return None
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    return out["hookSpecificOutput"]["permissionDecisionReason"]


def tool_reason(cfg, spec, tool_input) -> str | None:
    return check_tool(
        "Bash", tool_input, project_dir=cfg.project_dir, can_write=spec.can_write, allow_bash=spec.allow_bash,
        write_scope_hint=spec.write_scope_hint, allowed_tools=spec.allowed_tools,
    )


def reason_of(tmp_path: Path, kind: str, tool_input, via: str) -> str | None:
    cfg, spec = make_env(tmp_path, kind)
    if via == "check_tool":
        return tool_reason(cfg, spec, tool_input)
    return hook_reason(make_guard(cfg, spec), tool_input)


# ---- 止める例・通す例の表（設計の S01〜S60・P01〜P42） -------------------------------------
# （段の種類, コマンド, 理由に入る文字。通すものは None）。「どれも」は code・tests・read。

ANY = ("code", "tests", "read")
CODE = ("code",)
TESTS = ("tests",)
READ = ("read",)
IMPL = ("impl",)

ROWS: dict[str, tuple] = {
    "S01": (CODE, "echo x > tests/test_a.py", (SCOPE, "（tests/test_a.py は対象外）")),
    "S02": (CODE, "echo x >> tests/test_a.py", (SCOPE, "（tests/test_a.py は対象外）")),
    "S03": (CODE, "echo x &> tests/log.txt", (SCOPE, "（tests/log.txt は対象外）")),
    "S04": (CODE, "echo x >| tests/t.py", (SCOPE, "（tests/t.py は対象外）")),
    "S05": (TESTS, "cat > src/app.py <<'EOF'\nx = 1\nEOF", (SCOPE, "（src/app.py は対象外）")),
    "S06": (CODE, "printf a | tee tests/test_a.py", (SCOPE,)),
    "S07": (CODE, "tee -a tests/a.py < in.txt", (SCOPE,)),
    "S08": (CODE, "sed -i 's/a/b/' tests/test_a.py", (SCOPE,)),
    "S09": (CODE, "sed -i.bak -e 's/a/b/' tests/test_a.py", (SCOPE,)),
    "S10": (CODE, "sed --in-place=.bak 's/a/b/' tests/test_a.py", (SCOPE,)),
    "S11": (CODE, "sed -ni 's/a/b/p' tests/test_a.py", (SCOPE,)),
    "S12": (TESTS, "perl -pi -e 's/a/b/' src/app.py", (SCOPE,)),
    "S13": (CODE, "cp src/a.py tests/test_a.py", (SCOPE,)),
    "S14": (CODE, "cp -t tests src/a.py", (SCOPE, "（tests/a.py は対象外）")),
    "S15": (CODE, "cp src/a.py src/b.py tests/", (SCOPE,)),
    "S16": (CODE, "mv src/a.py tests/test_a.py", (SCOPE,)),
    "S17": (TESTS, "mv src/app.py src/old.py", (SCOPE,)),
    "S18": (CODE, "ln -s ../src/a.py tests/test_link.py", (SCOPE,)),
    "S19": (CODE, "touch tests/test_new.py", (SCOPE,)),
    "S20": (CODE, "rm tests/test_a.py", (SCOPE,)),
    "S21": (TESTS, "truncate -s 0 src/app.py", (SCOPE,)),
    "S22": (CODE, "dd if=/dev/zero of=tests/test_a.py count=1", (SCOPE,)),
    "S23": (CODE, "git restore tests/test_a.py", (SCOPE,)),
    "S24": (CODE, "find tests -name '*.py' -delete", (SCOPE,)),
    "S25": (CODE, r"find . -name '*.py' -exec rm {} \;", (UNREAD,)),
    "S26": (CODE, "ls | xargs rm", (UNREAD,)),
    "S27": (CODE, """python -c "open('tests/test_a.py','w').write('x')\"""", (SCOPE,)),
    "S28": (CODE, """python3 -c "from pathlib import Path; Path('tests/t.py').write_text('x')\"""", (SCOPE,)),
    "S29": (CODE, """python -c "import os; os.remove('tests/test_a.py')\"""", (SCOPE,)),
    "S30": (CODE, """python -c "import shutil; shutil.copy('src/a.py','tests/test_a.py')\"""", (SCOPE,)),
    "S31": (CODE, "python - <<'EOF'\nopen('tests/t.py','w').write('x')\nEOF", (SCOPE,)),
    "S32": (CODE, """node -e "require('fs').writeFileSync('tests/a.test.js','x')\"""", (SCOPE,)),
    "S33": (CODE, """python -c "open(p,'w')\"""", (UNREAD,)),
    "S34": (ANY, "echo x > /etc/hosts", (OUT,)),
    # 設計は ../outside.txt。テストの作業フォルダは /tmp の下なので、1つ上は一時の場所になってしまう。根まで上がって外に出す
    "S35": (ANY, "echo x > " + "../" * 12 + "outside.txt", (OUT,)),
    "S36": (ANY, "echo x > ~/note.txt", (OUT,)),
    "S37": (ANY, "echo x > /tmp/../etc/passwd", (OUT,)),
    "S38": (CODE, "echo x > $OUT", (UNREAD,)),
    "S39": (CODE, 'tee "$F"', (UNREAD,)),
    "S40": (CODE, "cp a.py $(dirname b)/x", (UNREAD,)),
    "S41": (CODE, "echo x > `pwd`/a.py", (UNREAD,)),
    "S42": (CODE, "touch $(mktemp)", (UNREAD,)),
    "S43": (CODE, "export TMPDIR=tests; echo x > $TMPDIR/a.py", (UNREAD,)),
    "S44": (CODE, "bash -c 'echo x > tests/a.py'", (SCOPE,)),
    "S45": (CODE, "echo $(touch tests/a.py)", (SCOPE,)),
    "S46": (CODE, "env FOO=1 timeout 10 tee tests/a.py", (SCOPE,)),
    "S47": (CODE, "ls; echo x > tests/a.py", (SCOPE,)),
    "S48": (CODE, "ls && cat a | tee tests/a.py", (SCOPE,)),
    "S49": (CODE, "ls\ntouch tests/a.py", (SCOPE,)),
    "S50": (CODE, "(cd x; true); echo x > tests/a.py", (SCOPE,)),
    "S51": (CODE, "cd tests && touch a.py", (SCOPE, "（tests/a.py は対象外）")),
    "S53": (CODE, "cd $X && touch a.py", (UNREAD,)),
    "S54": (READ, "echo x > src/a.py", (SCOPE, "docs/pipeline/read.md")),
    "S55": (READ, "sed -i 's/a/b/' src/a.py", (SCOPE,)),
    "S56": (("writes",), "echo x > out/a.txt", (SCOPE,)),
    "S57": (("prot",), "echo x > secrets/k.txt", (SCOPE,)),
    "S58": (CODE, "cat <<EOF\n$(touch tests/a.py)\nEOF", (SCOPE,)),
    "S59": (CODE, 'echo "abc > x', (UNPARSE,)),
    "S60": (CODE, "git push > /dev/null", ("git push",)),
    "P01": (IMPL, "pytest -q", None),
    "P02": (IMPL, "python -m pytest -q tests/ -x", None),
    "P03a": (IMPL, "npm test", None),
    "P03b": (IMPL, "npm --prefix vscode test", None),
    "P04": (TESTS, "sh check.sh --fast", None),
    "P05": (ANY, "ls > /dev/null 2>&1", None),
    "P06": (ANY, "ls 2>&1", None),
    "P07": (ANY, "echo err >&2", None),
    "P08": (ANY, "pytest -q 2>&1 | tail -20", None),
    "P09": (CODE, "echo x > src/a.py", None),
    "P10": (TESTS, "echo x > tests/test_a.py", None),
    "P11": (IMPL, "echo x > docs/pipeline/04_implementation.md", None),
    "P12": (IMPL, "rm build/tmp.txt", None),
    "P13a": (IMPL, "git status", None),
    "P13b": (IMPL, "pip install pytest", None),
    "P14": (ANY, "pytest -q 2>&1 | tee /tmp/out.log", None),
    "P15": (ANY, "echo x > $TMPDIR/a.txt", None),
    "P16": (ANY, "echo x > ${TMPDIR}/a.txt", None),
    "P17": (ANY, "mkdir -p /tmp/work", None),
    "P18": (TESTS, "mkdir -p build/out", None),
    "P19": (ANY, 'echo "a > b"', None),
    "P20": (ANY, "grep '>' src/a.py", None),
    "P21": (CODE, "cat <<'EOF'\nx > tests/a.py\nEOF", None),
    "P22": (CODE, "python build.py", None),
    "P23": (CODE, "make test", None),
    "P24": (CODE, "./gen.sh", None),
    "P25": (CODE, "echo hi | python script.py", None),
    "P26": (CODE, """python -c "print(open('tests/a.py').read())\"""", None),
    "P27": (CODE, """python -c "open('src/a.py','w').write('x')\"""", None),
    "P28": (CODE, "python - <<'EOF'\nprint(1)\nEOF", None),
    "P29": (CODE, "sed -n '1,5p' tests/a.py", None),
    "P30": (CODE, "sed 's/a/b/' tests/a.py > /tmp/x", None),
    "P31": (CODE, "cd src && touch a.py", None),
    "P32": (CODE, "cp tests/a.py /tmp/a.py", None),
    "P33": (CODE, "cp src/a.py src/b.py", None),
    "P34": (CODE, "echo $(date)", None),
    "P35": (CODE, "diff a b > /dev/null", None),
    "P36": (IMPL, "pytest --junitxml=report.xml", None),
    "P37": (IMPL, "pytest --basetemp=.cache/t", None),
    "P38": (CODE, "git diff > /tmp/d.patch", None),
    "P39a": (CODE, "git apply x.patch", None),
    "P39b": (CODE, "tar xf a.tar", None),
    "P40": (CODE, "bash -c 'echo x > src/a.py'", None),
    "P42": (CODE, r"find . -name x -exec grep y {} \;", None),
    # ---- 設計の表のほかに、受け入れ基準の例から足したもの ----
    "E01": (CODE, "unlink tests/a.py", (SCOPE,)),
    "E02": (CODE, "rmdir tests/old", (SCOPE,)),
    "E03": (CODE, "git rm tests/a.py", (SCOPE,)),
    "E04": (CODE, "git mv src/a.py tests/a.py", (SCOPE,)),
    "E05": (CODE, "install src/a.py tests/a.py", (SCOPE,)),
    "E06": (CODE, "install -t tests src/a.py", (SCOPE,)),
    "E07": (CODE, "mv tests/a.py src/a.py", (SCOPE,)),
    "E08": (CODE, "sed -n 's/a/b/p' tests/a.py > tests/b.py", (SCOPE,)),
    "E09": (CODE, "perl -i.bak -pe 's/a/b/' tests/a.py", (SCOPE,)),
    "E10": (CODE, "ln -s src/a.py tests/l.py", (SCOPE,)),
    "E11": (CODE, "find tests -fprint out.txt", (SCOPE,)),
    "E12": (CODE, "cp -r src/a tests", (SCOPE,)),
    "E13": (CODE, "echo x 2> tests/err.log", (SCOPE,)),
    "E14": (CODE, "echo x 1>> tests/out.log", (SCOPE,)),
    "E15": (CODE, "echo x >&tests/o.log", (SCOPE,)),
    "E16": (CODE, "echo x 1<> tests/o.log", (SCOPE,)),
    "E17": (CODE, "echo x &>> tests/log.txt", (SCOPE,)),
    "E18": (CODE, "tee /etc/x", (OUT,)),
    "E19": (CODE, "ls >&-", None),
    "E20": (CODE, "sed -i -e 's/a/b/' src/a.py", None),
    "E21": (CODE, "tee -a src/a.py", None),
    "E22": (CODE, "python -c \"open('src/a.py','r').read()\"", None),
    "E23": (CODE, """python -c "open('tests/a.py','r').read()\"""", None),
    "E24": (CODE, """python -c "open('tests/a.py','rb').read()\"""", None),
    "E25": (CODE, """node -e "require('fs').writeFileSync('src/a.js','x')\"""", None),
    "E26": (CODE, """python3 -c "from pathlib import Path; Path('src/t.py').write_text('x')\"""", None),
    "E27": (CODE, """python -c "import os; os.rename('src/a.py','tests/a.py')\"""", (SCOPE,)),
    "E28": (CODE, """python -c "open('tests/a.py', mode='w')\"""", (SCOPE,)),
    "E29": (CODE, """python -c "open('tests/a.py', mode=m)\"""", (UNREAD,)),
    "E30": (CODE, """python -c "from pathlib import Path; p.write_text('x')\"""", (UNREAD,)),
    "E31": (CODE, "python <<< \"open('tests/t.py','w').write('x')\"", (SCOPE,)),
    "E32": (CODE, """python -c "import shutil; shutil.copy(a,'tests/test_a.py')\"""", (SCOPE,)),
    "E33": (CODE, """python -c "import shutil; shutil.move('tests/a.py', 'src/a.py')\"""", (SCOPE,)),
    "E34": (CODE, "mkdir /etc/x", (OUT,)),
    "E35": (CODE, "mkdir $D", (UNREAD,)),
    "E36": (CODE, "mkdir -p tests/new", None),
    "E37": (CODE, "mkdir -p /tmp/a/b", None),
    "E38": (CODE, "tee $TMPDIR/a.log", None),
    "E39": (CODE, "echo x > ${TMPDIR}/../etc/x", (OUT,)),
    "E40": (CODE, "TMPDIR=tests; echo x > $TMPDIR/a.py", (UNREAD,)),
    "E41": (CODE, "HOME=tests; echo x > ~/a.py", (UNREAD,)),
    "E42": (CODE, "echo x > ~root/a", (UNREAD,)),
    "E43": (CODE, "echo x > tests/*.py", (SCOPE,)),
    "E44": (CODE, "echo x > t*/a.py", (UNREAD,)),
    "E45": (CODE, "echo x > src/\\../tests/a.py", (SCOPE,)),
    "E46": (CODE, "echo x >'tests/a.py'", (SCOPE,)),
    "E47": (CODE, 'echo x > "tests/a.py"', (SCOPE,)),
    "E48": (CODE, "echo x > tests/a\\ b.py", (SCOPE,)),
    "E49": (CODE, "echo x > tests/a.py # src/a.py", (SCOPE,)),
    "E50": (CODE, "echo x # > tests/a.py", None),
    "E51": (CODE, "ls &\ntouch tests/a.py", (SCOPE,)),
    "E52": (CODE, "ls || touch tests/a.py", (SCOPE,)),
    "E53": (CODE, "{ touch tests/a.py; }", (SCOPE,)),
    "E54": (CODE, "ls `touch tests/a.py`", (SCOPE,)),
    "E55": (CODE, "cat <(touch tests/a.py)", (SCOPE,)),
    "E56": (CODE, "ls > >(tee tests/a.py)", (SCOPE,)),
    "E57": (CODE, "ls\\\n> tests/a.py", (SCOPE,)),
    "E58": (CODE, "nohup touch tests/a.py", (SCOPE,)),
    "E59": (CODE, "time touch tests/a.py", (SCOPE,)),
    "E60": (CODE, "command touch tests/a.py", (SCOPE,)),
    "E61": (CODE, "exec touch tests/a.py", (SCOPE,)),
    "E62": (CODE, "nice -n 5 touch tests/a.py", (SCOPE,)),
    "E63": (CODE, "FOO=1 touch tests/a.py", (SCOPE,)),
    "E64": (CODE, "eval 'touch tests/a.py'", (SCOPE,)),
    "E65": (CODE, "sh -c \"echo x > tests/a.py\"", (SCOPE,)),
    "E66": (CODE, "eval \"$X\"", None),
    "E67": (CODE, "ls | xargs -I {} touch {}", (UNREAD,)),
    "E68": (CODE, "xargs touch tests/a.py", ()),
    "E69": (CODE, "find tests -exec touch {} +", (UNREAD,)),
    "E70": (CODE, "cat > tests/a.py <<EOF\nbody\nEOF", (SCOPE,)),
    "E71": (CODE, "cat <<-EOF\n\techo\n\tEOF\necho x > tests/a.py", (SCOPE,)),
    "E72": (CODE, "echo 'x > tests/a.py'", None),
    "E73": (CODE, "echo \"it's\" > tests/a.py", (SCOPE,)),
    "E74": (CODE, "echo x > 'src/a.py'", None),
    "E75": (CODE, "(cd src; touch a.py)", None),
    "E76": (CODE, "(cd tests; touch a.py)", (SCOPE,)),
    "E77": (CODE, "cd src; cd ..; touch a.py", None),
    "E78": (CODE, "cd nodir && touch a.py", (UNREAD,)),
    "E79": (CODE, "cd; touch a.py", (UNREAD,)),
    "E80": (CODE, "cd - && touch a.py", (UNREAD,)),
    "E81": (CODE, "pushd tests && touch a.py", (SCOPE,)),
    "E82": (CODE, "popd && touch a.py", (UNREAD,)),
    "E83": (READ, "cp a b", (SCOPE,)),
    "E84": (READ, "echo x > docs/pipeline/read.md", None),
    "E85": (("writes",), "echo x > out/a.svg", None),
    "E86": (("writes",), "mkdir -p out", None),
    "E87": (("prot",), "echo x > src/a.py", None),
    "E88": (CODE, "rm -rf tests > /dev/null", ("再帰的な削除は禁止です",)),
    "E89": (CODE, "echo x > /dev/stderr", None),
    "E90": (CODE, "echo x > /dev/tty", None),
    "E91": (CODE, "echo x > /dev/fd/2", None),
    "E92": (CODE, "echo x > /dev/stdout", None),
    "E93": (CODE, "pytest -q > /dev/null 2>&1", None),
    "E94": (CODE, "ls", None),
    "E95": (CODE, "cat in.txt | sort > out.txt", None),
    "E96": (TESTS, "cat in.txt | sort > out.txt", (SCOPE,)),
    "E97": (CODE, "cp src/a.py /etc/a.py", (OUT,)),
    "E98": (CODE, "cp /etc/hosts src/hosts", None),
    "E99": (CODE, "mv tests/a.py /tmp/a.py", (SCOPE,)),
    # ---- 監査のあとの差し戻し（AC-28〜AC-32） ----
    "F01": (CODE, "tee --output-error tests/a.py", (SCOPE,)),
    "F02": (CODE, "tee --output-error=warn tests/a.py", (SCOPE,)),
    "F03": (CODE, "mv tests x", (SCOPE,)),
    "F04": (CODE, "mv tests/ /tmp/x", (SCOPE,)),
    "F05": (CODE, "rmdir tests", (SCOPE,)),
    "F06": (CODE, "mv src/a.py src/b.py", None),
    "G01": (CODE, "rm *.py", (UNREAD,)),
    "G02": (CODE, "rm ?est_a.py", (UNREAD,)),
    "G03": (CODE, "git restore '*.py'", (UNREAD,)),
    "G04": (CODE, "rm /tmp/*.log", None),
    "G05": (CODE, "git restore :/tests", (UNREAD,)),
    "G06": (CODE, "git rm ':(glob)**/t.py'", (UNREAD,)),
    "G07": (CODE, "rm src/a.py", None),
    "H01": (CODE, """node --eval="require('fs').writeFileSync('tests/a.js','')\"""", (SCOPE,)),
    "H02": (CODE, """python3 -c "from pathlib import Path; Path('tests/a.py').open('w')\"""", (SCOPE,)),
    "H03": (CODE, """python3 -c "from pathlib import Path; Path('src/a.py').open()\"""", None),
    "H04": (CODE, """python3 -c "from pathlib import Path; Path('tests/a.py').open('r')\"""", None),
}


def _params(ids, vias=VIAS):
    out = []
    for rid in ids:
        kinds, command, expect = ROWS[rid]
        for kind in kinds:
            for via in vias:
                out.append(pytest.param(kind, command, expect, via, id=f"{rid}-{kind}-{via}"))
    return out


def _check(tmp_path, kind, command, expect, via):
    reason = reason_of(tmp_path, kind, {"command": command}, via)
    if expect is None:
        assert reason is None, f"{kind}/{via} `{command!r}` は通るはずが止まった: {reason}"
        return
    assert reason is not None, f"{kind}/{via} `{command!r}` は止まるはずが通った"
    for s in expect:
        assert s in reason, f"{kind}/{via} `{command!r}`: 理由に {s!r} が無い: {reason}"


def _rows(ids):
    return pytest.mark.parametrize("kind,command,expect,via", _params(ids))


# ---- AC-01〜AC-08 ----------------------------------------------------------------


@_rows(["S01", "S02", "S03", "S04", "E13", "E14", "E15", "E16", "E17", "E43", "E46", "E47", "E48", "E49", "E50", "E96"])
def test_d0033_ac01_リダイレクトの範囲外は止まる(tmp_path, kind, command, expect, via):
    """D0033-AC-01: code の段のリダイレクト（> >> &> >| N> N>> >&ファイル <> &>>）の先が範囲外なら止まり、理由は「この段で書き込めるのは … だけです（… は対象外）」の形。"""
    _check(tmp_path, kind, command, expect, via)


@_rows(["P09", "P10", "P11", "E74", "E95"])
def test_d0033_ac02_範囲の中の書き込みは通る(tmp_path, kind, command, expect, via):
    """D0033-AC-02: 範囲の中への書き込み（code の src・tests の段の tests・実装の段の 04_implementation.md）は通る。"""
    _check(tmp_path, kind, command, expect, via)


@_rows(["P05", "P06", "P07", "P08", "E19", "E89", "E90", "E91", "E92"])
def test_d0033_ac03_devnullとfdの付け替えは通る(tmp_path, kind, command, expect, via):
    """D0033-AC-03: /dev/null への書き込みと fd の付け替え（2>&1・>&2・>&-）は、どの段でも通る。"""
    _check(tmp_path, kind, command, expect, via)


@_rows(["S06", "S07", "S08", "S09", "S10", "S11", "S12", "P29", "P30", "E08", "E09", "E20", "E21"])
def test_d0033_ac04_tee_sed_perlの先を見る(tmp_path, kind, command, expect, via):
    """D0033-AC-04: tee（-a）・sed -i（-i.bak・-ni・--in-place・-e）・perl -pi の先が範囲外なら止まる。-i なしの sed と範囲内は通る。"""
    _check(tmp_path, kind, command, expect, via)


@_rows(["S13", "S14", "S15", "S16", "S17", "S18", "P32", "P33", "E05", "E06", "E07", "E10", "E12", "E97", "E98", "E99"])
def test_d0033_ac05_cp_mv_ln_installの宛先を見る(tmp_path, kind, command, expect, via):
    """D0033-AC-05: cp・mv・ln・install は宛先（-t・末尾 /・複数の元）が範囲外なら止まり、mv は元が範囲外でも止まる。一時の場所への cp と範囲内は通る。"""
    _check(tmp_path, kind, command, expect, via)


@_rows(["S19", "S20", "S21", "S22", "S23", "P12", "E01", "E02", "E03", "E04"])
def test_d0033_ac06_touch_rm_truncate_dd_gitの先を見る(tmp_path, kind, command, expect, via):
    """D0033-AC-06: touch・rm・unlink・rmdir・truncate・dd of=・git restore・git rm・git mv の先が範囲外なら止まる。実装の段の rm build/tmp.txt は通る。"""
    _check(tmp_path, kind, command, expect, via)


@_rows(["S24", "S25", "S26", "P42", "E11", "E67", "E68", "E69"])
def test_d0033_ac07_find_xargsは先が読めないので止まる(tmp_path, kind, command, expect, via):
    """D0033-AC-07: find 範囲外 -delete は止まり、find -exec 書き込みの形 {} と xargs rm は先が読めないので止まる。書き込みの形でない find -exec grep は通る。"""
    _check(tmp_path, kind, command, expect, via)


@_rows(["P17", "P18", "E34", "E35", "E36", "E37", "E86"])
def test_d0033_ac08_mkdirは中なら通り外と読めない先は止まる(tmp_path, kind, command, expect, via):
    """D0033-AC-08: mkdir は、プロジェクトの外（一時の場所を除く）・読めない先のときだけ止め、中は通す（can_write は見ない）。"""
    _check(tmp_path, kind, command, expect, via)


# ---- AC-09・AC-10 ----------------------------------------------------------------


@_rows(["S27", "S28", "S29", "S30", "S32", "P26", "P27", "E22", "E23", "E24", "E25", "E26", "E27", "E28", "E32", "E33"])
def test_d0033_ac09_python_node_のコードの書き込み(tmp_path, kind, command, expect, via):
    """D0033-AC-09: python -c・node -e の中の書き込みの形（open の w・Path.write_text・os.remove・shutil.copy・fs.writeFileSync など）の先が範囲外なら止まる。範囲内と読み取りは通る。"""
    _check(tmp_path, kind, command, expect, via)


@_rows(["S31", "P28", "E31"])
def test_d0033_ac10_標準入力のコードもcと同じに見る(tmp_path, kind, command, expect, via):
    """D0033-AC-10: python - <<'EOF' … EOF と python <<< '…' の標準入力のコードも -c と同じに見る。書き込みの形が無いコードは通る。"""
    _check(tmp_path, kind, command, expect, via)


# ---- AC-11〜AC-13 ----------------------------------------------------------------


@_rows(["S34", "S35", "S36", "S37", "E18", "E39"])
def test_d0033_ac11_プロジェクトの外は止まる(tmp_path, kind, command, expect, via):
    """D0033-AC-11: プロジェクトの外（/etc・.. の先・~・/tmp/.. で一時の場所から出る先・tee /etc/x）は止まり、理由は「プロジェクトの外には書き込めません」。"""
    _check(tmp_path, kind, command, expect, via)


@pytest.mark.parametrize("via", VIAS)
def test_d0033_ac11_symlinkでプロジェクトの外を指す先は止まる(tmp_path, via):
    """D0033-AC-11: プロジェクトの中の symlink が外（/etc）を指すとき、その下への書き込みは外として止まる。"""
    cfg, spec = make_env(tmp_path, "code")
    (cfg.project_dir / "src" / "etclink").symlink_to("/etc")
    command = "echo x > src/etclink/hosts"
    reason = tool_reason(cfg, spec, {"command": command}) if via == "check_tool" else hook_reason(make_guard(cfg, spec), {"command": command})
    assert reason is not None and OUT in reason, reason


@_rows(["P14", "P15", "P16", "P17", "E37", "E38"])
def test_d0033_ac12_一時の場所は通る(tmp_path, kind, command, expect, via):
    """D0033-AC-12: 一時の場所（/tmp・$TMPDIR/…・${TMPDIR}/…）への書き込みは通る。"""
    _check(tmp_path, kind, command, expect, via)


@_rows(["S43", "E40", "E41"])
def test_d0033_ac12_TMPDIRの書き換えは止まる(tmp_path, kind, command, expect, via):
    """D0033-AC-12: 同じコマンドの中で TMPDIR・HOME に代入があるとき、$TMPDIR/…・~/… は読めない先として止まる。"""
    _check(tmp_path, kind, command, expect, via)


@pytest.mark.parametrize("via", VIAS)
def test_d0033_ac12_前の呼び出しでTMPDIRを書き換えたら止まる(tmp_path, via):
    """D0033-AC-12: 前の呼び出しで TMPDIR に代入があったら、あとの呼び出しの $TMPDIR/… は読めない先として止まる（覚えは BashState。ガードの経路）。"""
    cfg, spec = make_env(tmp_path, "code")
    if via == "check_tool":
        from pipe_in.engine.bashwrite import BashState

        state = BashState.new(cfg.project_dir)

        def call(cmd):
            return check_tool(
                "Bash", {"command": cmd}, project_dir=cfg.project_dir, can_write=spec.can_write, allow_bash=True,
                write_scope_hint=spec.write_scope_hint, allowed_tools=spec.allowed_tools, bash_state=state,
            )
    else:
        guard = make_guard(cfg, spec)

        def call(cmd):
            return hook_reason(guard, {"command": cmd})

    assert call("export TMPDIR=tests") is None
    reason = call("echo x > $TMPDIR/a.txt")
    assert reason is not None and UNREAD in reason, reason


@_rows(["S33", "S38", "S39", "S40", "S41", "S42", "E29", "E30"])
def test_d0033_ac13_先が読めない書き込みは止まる(tmp_path, kind, command, expect, via):
    """D0033-AC-13: 先が読み取れない書き込みの形（変数・$(…)・バッククォート・open(変数,'w')）は止まり、理由に「先を文字で書いてください」が入る。"""
    _check(tmp_path, kind, command, expect, via)


# ---- AC-14〜AC-16 ----------------------------------------------------------------


@_rows(["S44", "S45", "S46", "S47", "S48", "S49", "S50", "P34", "P40", "E51", "E52", "E53", "E54", "E55", "E56", "E57", "E58",
        "E59", "E60", "E61", "E62", "E63", "E64", "E65", "E75", "E76", "E77", "E73"])
def test_d0033_ac14_続くコマンドと入れ子を調べる(tmp_path, kind, command, expect, via):
    """D0033-AC-14: ; && || | & 改行・( )・{ }・$(…)・バッククォート・<(…)・>(…)・bash -c・eval・env/timeout/nohup/time/nice/command/exec と VAR=値の接頭は、どこかに範囲外の書き込みがあれば止まる。範囲内だけなら通る。"""
    _check(tmp_path, kind, command, expect, via)


@_rows(["S05", "S58", "P19", "P20", "P21", "E70", "E71", "E72"])
def test_d0033_ac15_引用符とヒアドキュメント(tmp_path, kind, command, expect, via):
    """D0033-AC-15: 引用符の中の > とヒアドキュメントの本文は書き込みでない。cat > f <<EOF の f は数える。引用符なしの区切りの本文の $(…) は調べる。"""
    _check(tmp_path, kind, command, expect, via)


@_rows(["S51", "S53", "P31", "E78", "E79", "E80", "E81", "E82"])
def test_d0033_ac16_cdを追う(tmp_path, kind, command, expect, via):
    """D0033-AC-16: cd tests && touch a.py は止まり、cd src && touch a.py は通る。cd $X・cd だけ・cd -・実在しない先・popd のあとの相対パスは止まる。"""
    _check(tmp_path, kind, command, expect, via)


@pytest.mark.parametrize("via", VIAS)
def test_d0033_ac16_呼び出しをまたぐcd(tmp_path, via):
    """D0033-AC-16: cd tests を通したあとの別の呼び出しの touch a.py も止まる（作業フォルダが変わった可能性を残す）。cd src のあとの touch a.py は通る。"""
    cfg, spec = make_env(tmp_path, "code")
    if via == "check_tool":
        from pipe_in.engine.bashwrite import BashState

        state = BashState.new(cfg.project_dir)

        def call(cmd):
            return check_tool(
                "Bash", {"command": cmd}, project_dir=cfg.project_dir, can_write=spec.can_write, allow_bash=True,
                write_scope_hint=spec.write_scope_hint, allowed_tools=spec.allowed_tools, bash_state=state,
            )
    else:
        guard = make_guard(cfg, spec)

        def call(cmd):
            return hook_reason(guard, {"command": cmd})

    assert call("cd tests") is None
    reason = call("touch a.py")
    assert reason is not None and SCOPE in reason, reason


def test_d0033_ac16_cd_srcのあとの呼び出しは通る(tmp_path):
    """D0033-AC-16: cd src を通したあとの touch a.py は、プロジェクトの直下でも src でも範囲内なので通る（止めすぎない）。"""
    cfg, spec = make_env(tmp_path, "code")
    guard = make_guard(cfg, spec)
    assert hook_reason(guard, {"command": "cd src"}) is None
    assert hook_reason(guard, {"command": "touch a.py"}) is None


# ---- AC-17・AC-18 ----------------------------------------------------------------


@_rows(["S54", "S55", "E83", "E84"])
def test_d0033_ac17_readの段は成果物だけ(tmp_path, kind, command, expect, via):
    """D0033-AC-17: access = "read" の段は、自分の成果物への書き込みだけ通り、src への書き込み・cp・sed -i は止まる。"""
    _check(tmp_path, kind, command, expect, via)


@_rows(["S56", "S57", "E85", "E87"])
def test_d0033_ac18_writesとprotected_paths(tmp_path, kind, command, expect, via):
    """D0033-AC-18: writes で絞った段は絞りの外を止め、protected_paths に当たる先は止める。絞りの中は通る。"""
    _check(tmp_path, kind, command, expect, via)


# ---- AC-19〜AC-22 ----------------------------------------------------------------


@_rows(["P01", "P02", "P03a", "P03b", "P04", "P13a", "P13b", "P36", "P37", "E93", "E94"])
def test_d0033_ac19_今までのコマンドは止まらない(tmp_path, kind, command, expect, via):
    """D0033-AC-19: 今までのコマンド（pytest・npm test・sh check.sh・git status・pip install・--junitxml・ls・> /dev/null 2>&1）は止まらない。今も通る（守り続けるための検査）。"""
    _check(tmp_path, kind, command, expect, via)


@_rows(["P22", "P23", "P24", "P25", "P35", "P38", "P39a", "P39b", "E66"])
def test_d0033_ac20_見分けられない形は通る(tmp_path, kind, command, expect, via):
    """D0033-AC-20: 見分けられない形（python build.py・make・./gen.sh・パイプで渡すコード・git apply・tar xf・eval "$x"）は止めない。今も通る（すり抜けの道として残す検査）。"""
    _check(tmp_path, kind, command, expect, via)


@_rows(["S60", "E88"])
def test_d0033_ac21_危ないコマンドの判定が先に効く(tmp_path, kind, command, expect, via):
    """D0033-AC-21: git push > /dev/null・rm -rf tests > /dev/null は、書き込み先が範囲内でも今までの理由で止まる。今も止まる（順番を守る検査）。"""
    _check(tmp_path, kind, command, expect, via)


@pytest.mark.parametrize("via", VIAS)
def test_d0033_ac21_allow_bashがfalseの段はBashを使えない(tmp_path, via):
    """D0033-AC-21: allow_bash = false の段の Bash は「この段では Bash を使えません」のまま。今も止まる。"""
    reason = reason_of(tmp_path, "nobash", {"command": "echo x > src/a.py"}, via)
    assert reason is not None and NOBASH in reason, reason


def _deep(n: int) -> str:
    cmd = "echo x"
    for _ in range(n):
        cmd = "bash -c " + shlex.quote(cmd)
    return cmd


@pytest.mark.parametrize("via", VIAS)
@pytest.mark.parametrize(
    "command",
    [
        'echo "abc > x',
        "echo 'abc > x",
        "echo $(touch src/a.py",
        "echo `touch src/a.py",
        _deep(6),
        _deep(7),
        None,
        [],
        {"a": 1},
        5,
    ],
    ids=["引用符1", "引用符2", "dollar-paren", "backtick", "深さ6", "深さ7", "None", "空の配列", "辞書", "数"],
)
def test_d0033_ac22_読めない入力は落ちずに止まる(tmp_path, command, via):
    """D0033-AC-22: 引用符・$( が閉じない・入れ子が 5 段を超える・command が文字でない（None・[]・辞書・数）は、落ちずに理由を返して止まる。"""
    reason = reason_of(tmp_path, "code", {"command": command}, via)
    assert isinstance(reason, str) and reason, f"止まるはずが通った: {reason!r}"


@pytest.mark.parametrize("via", VIAS)
def test_d0033_ac22_入れ子が5段なら読める(tmp_path, via):
    """D0033-AC-22: 入れ子が 5 段までなら読んで判定する（範囲内だけなので通る）。今も通る（上限の境目を守る検査）。"""
    command = "echo x > src/a.py"
    for _ in range(5):
        command = "bash -c " + shlex.quote(command)
    assert reason_of(tmp_path, "code", {"command": command}, via) is None


@pytest.mark.parametrize("via", VIAS)
def test_d0033_ac22_空のコマンドは今までどおり通る(tmp_path, via):
    """D0033-AC-22: 空のコマンド（""）は今までどおり通る。今も通る。"""
    assert reason_of(tmp_path, "code", {"command": ""}, via) is None


# ---- AC-23・AC-24 ----------------------------------------------------------------


def test_d0033_ac23_denialsに残る(tmp_path):
    """D0033-AC-23: 止めた Bash は、ほかの止めた操作と同じく on_deny に（runner が StageRun.denials に "Bash: <理由>" と残す形で）渡り、通したものは渡らない。"""
    cfg, spec = make_env(tmp_path, "code")
    denied: list[str] = []
    guard = make_guard(cfg, spec, denied)
    assert hook_reason(guard, {"command": "echo x > src/a.py"}) is None
    assert denied == []
    reason = hook_reason(guard, {"command": "echo x > tests/a.py"})
    assert reason is not None
    assert denied == [f"Bash: {reason}"]
    assert denied[0].startswith("Bash: ") and SCOPE in denied[0]


@pytest.mark.parametrize(
    "rid", ["S01", "S11", "S34", "S35", "S36", "S37", "S38", "S44", "S51"]
)
def test_d0033_ac24_本物のガードの経路(tmp_path, rid):
    """D0033-AC-24: make_guard_hook が作るガードを通る本物の経路でも、AC-01・AC-11・AC-16 の止める例が止まり、理由の文は check_tool と同じ。"""
    kinds, command, expect = ROWS[rid]
    for kind in kinds:
        cfg, spec = make_env(tmp_path / kind, kind)
        denied: list[str] = []
        via_hook = hook_reason(make_guard(cfg, spec, denied), {"command": command})
        via_tool = tool_reason(cfg, spec, {"command": command})
        assert via_hook is not None, f"{kind} `{command!r}` は止まるはずが通った"
        assert via_hook == via_tool
        for s in expect:
            assert s in via_hook, via_hook
        assert denied == [f"Bash: {via_hook}"]


def test_d0033_ac24_ガードごとに覚えを分ける(tmp_path):
    """D0033-AC-24: 2つのガードは作業フォルダの覚えを分け合わない。片方で cd tests を通しても、もう片方の touch a.py は（直下で）通る。"""
    cfg, spec = make_env(tmp_path, "code")
    a = make_guard(cfg, spec)
    b = make_guard(cfg, spec)
    assert hook_reason(a, {"command": "cd tests"}) is None
    assert hook_reason(b, {"command": "touch a.py"}) is None, "b は a の cd を知らないはず"
    reason = hook_reason(a, {"command": "touch a.py"})
    assert reason is not None and SCOPE in reason, "a は自分の cd を覚えている"


def test_d0033_ac24_bash_stateなしのcheck_toolは覚えない(tmp_path):
    """D0033-AC-24: check_tool を bash_state なしで呼ぶときは、cd を覚えない（毎回プロジェクトの直下から判定する）。cd tests のあとの touch a.py も通る。"""
    cfg, spec = make_env(tmp_path, "code")
    assert tool_reason(cfg, spec, {"command": "cd tests"}) is None
    assert tool_reason(cfg, spec, {"command": "touch a.py"}) is None
    # 引数の bash_state は新しい部品なので、受け付けること自体も確かめる
    from pipe_in.engine.bashwrite import BashState

    state = BashState.new(cfg.project_dir)
    assert (
        check_tool(
            "Bash", {"command": "echo x > tests/a.py"}, project_dir=cfg.project_dir, can_write=spec.can_write, allow_bash=True,
            write_scope_hint=spec.write_scope_hint, allowed_tools=spec.allowed_tools, bash_state=state,
        )
        is not None
    )


def test_d0033_ac24_Bash以外のツールは今までどおり(tmp_path):
    """D0033-AC-24: Write・Edit の判定は変わらない（範囲内は通り、範囲外は止まる）。今も同じ。"""
    cfg, spec = make_env(tmp_path, "code")
    ok = check_tool("Write", {"file_path": "src/a.py"}, project_dir=cfg.project_dir, can_write=spec.can_write, allow_bash=True,
                    write_scope_hint=spec.write_scope_hint, allowed_tools=spec.allowed_tools)
    ng = check_tool("Write", {"file_path": "tests/a.py"}, project_dir=cfg.project_dir, can_write=spec.can_write, allow_bash=True,
                    write_scope_hint=spec.write_scope_hint, allowed_tools=spec.allowed_tools)
    assert ok is None and ng and SCOPE in ng


# ---- AC-28〜AC-32（監査のあとの差し戻し） -------------------------------------------------


@_rows(["F01", "F02"])
def test_d0033_ac28_tee_output_errorは等号つきのときだけ値を持つ(tmp_path, kind, command, expect, via):
    """D0033-AC-28: tee --output-error tests/a.py は、--output-error が値を取らないので tests/a.py を先として止める。--output-error=warn tests/a.py も止まる。"""
    _check(tmp_path, kind, command, expect, via)


@_rows(["F03", "F04", "F05", "F06"])
def test_d0033_ac29_フォルダの元と先は下の両方で判定する(tmp_path, kind, command, expect, via):
    """D0033-AC-29: mv tests x・mv tests/ /tmp/x・rmdir tests は、フォルダそのものとその下の両方を調べて止まる。mv src/a.py src/b.py は通る。"""
    _check(tmp_path, kind, command, expect, via)


@_rows(["G01", "G02", "G03", "G04", "G05", "G06", "G07"])
def test_d0033_ac30_globと_pathspecは読めない先として止める(tmp_path, kind, command, expect, via):
    """D0033-AC-30: 最後の部品に glob（* ? [）を含む先と、git の : で始まる pathspec は読めない先として止まる。tmp の下の glob と rm src/a.py は通る。"""
    _check(tmp_path, kind, command, expect, via)


@_rows(["H01", "H02", "H03", "H04"])
def test_d0033_ac31_node_evalとPath_openの形(tmp_path, kind, command, expect, via):
    """D0033-AC-31: node --eval=… と Path(…).open('w') の範囲外は止まる。open() と open('r') は通る。"""
    _check(tmp_path, kind, command, expect, via)


ROOT_COMMANDS = [
    "find . -delete",
    "find . -name '*.pyc' -delete",
    "git restore .",
]


def _env_with_files(tmp_path: Path, kind: str, files: list[str]):
    cfg, spec = make_env(tmp_path, kind)
    for rel in files:
        p = cfg.project_dir / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x", encoding="utf-8")
    return cfg, spec


def _env_clean(tmp_path: Path, kind: str, files: list[str]):
    """範囲外のファイルが本当に無いプロジェクト：make_env が作る pipes/（pipe.toml）を消してから files を置く。"""
    import shutil

    cfg, spec = make_env(tmp_path, kind)
    shutil.rmtree(cfg.project_dir / "pipes", ignore_errors=True)
    for rel in files:
        p = cfg.project_dir / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x", encoding="utf-8")
    return cfg, spec


def _reason_in(cfg, spec, command: str, via: str):
    if via == "check_tool":
        return tool_reason(cfg, spec, {"command": command})
    return hook_reason(make_guard(cfg, spec), {"command": command})


@pytest.mark.parametrize("via", VIAS)
@pytest.mark.parametrize("command", ROOT_COMMANDS)
def test_d0033_ac32_根を指すフォルダ操作は範囲外のファイルがあれば止まる_code(tmp_path, command, via):
    """D0033-AC-32: 根を指すフォルダ操作は、下に tests/test_a.py がある code の段では止まる。"""
    cfg, spec = _env_with_files(tmp_path, "code", ["src/a.py", "tests/test_a.py"])
    reason = _reason_in(cfg, spec, command, via)
    assert reason is not None and SCOPE in reason, f"`{command}` は止まるはずが通った: {reason}"


@pytest.mark.parametrize("via", VIAS)
@pytest.mark.parametrize("command", ROOT_COMMANDS)
def test_d0033_ac32_根を指すフォルダ操作は範囲外のファイルが無ければ通る(tmp_path, command, via):
    """D0033-AC-32: 根を指すフォルダ操作は、tests フォルダにファイルが無い（src の中だけ）code の段では通る。今も通る（止めすぎない検査）。"""
    cfg, spec = _env_clean(tmp_path, "code", ["src/a.py"])
    reason = _reason_in(cfg, spec, command, via)
    assert reason is None, f"`{command}` は通るはずが止まった: {reason}"


@pytest.mark.parametrize("via", VIAS)
def test_d0033_ac32_パイプのフォルダがあればcodeの段のfind_deleteは止まる(tmp_path, via):
    """D0033-AC-32: pipes/…/pipe.toml（code の段では書けないパイプのフォルダ）が下にあれば、find . -delete は止まる。"""
    cfg, spec = _env_with_files(tmp_path, "code", ["src/a.py"])
    assert (cfg.project_dir / "pipes" / "pipe-in-p" / "pipe.toml").exists()
    reason = _reason_in(cfg, spec, "find . -delete", via)
    assert reason is not None and SCOPE in reason, f"止まるはずが通った: {reason}"


@pytest.mark.parametrize("via", VIAS)
@pytest.mark.parametrize("command", ROOT_COMMANDS)
def test_d0033_ac32_testsの段ではsrcがあるので止まる(tmp_path, command, via):
    """D0033-AC-32: 根を指すフォルダ操作は、tests の段（テストだけ書ける）では src/a.py があるので止まる。"""
    cfg, spec = _env_with_files(tmp_path, "tests", ["src/a.py", "tests/test_a.py"])
    reason = _reason_in(cfg, spec, command, via)
    assert reason is not None and SCOPE in reason, f"`{command}` は止まるはずが通った: {reason}"


@pytest.mark.parametrize("via", VIAS)
def test_d0033_ac32_git_rm_rは今までの理由で止まる(tmp_path, via):
    """D0033-AC-32: git rm -r . は再帰的な削除として今までの理由で止まる（今も止まる。順番を守る検査）。"""
    cfg, spec = _env_with_files(tmp_path, "code", ["src/a.py"])
    reason = _reason_in(cfg, spec, "git rm -r .", via)
    assert reason is not None and "再帰的な削除は禁止です" in reason, reason


@pytest.mark.parametrize("via", VIAS)
def test_d0033_ac32_gitの中は見ない(tmp_path, via):
    """D0033-AC-32: .git の中のファイルは見ない。tests にファイルが無く .git の中だけにあるなら通る。"""
    cfg, spec = _env_clean(tmp_path, "code", ["src/a.py", ".git/objects/tests/x"])
    reason = _reason_in(cfg, spec, "find . -delete", via)
    assert reason is None, reason


@pytest.mark.parametrize("via", VIAS)
def test_d0033_ac32_見るファイルが上限を超えたら止める(tmp_path, via):
    """D0033-AC-32: 見るファイルの数が上限（5000）を超えたら、全部が範囲内でも安全側に倒して止める。"""
    cfg, spec = _env_with_files(tmp_path, "code", [f"src/f{i}.txt" for i in range(5001)])
    reason = _reason_in(cfg, spec, "find . -delete", via)
    assert reason is not None, "上限を超えたのに通った"


# ---- AC-27 ----------------------------------------------------------------------


def test_d0033_ac27_記録と設定は変わらない():
    """D0033-AC-27: StageSpec と Config に新しい項目を足さない（記録・pipeline.toml・pipe.toml の形が変わらない）。今も同じ（守り続けるための検査）。"""
    from pipe_in.engine.config import Config
    from pipe_in.engine.spec import StageSpec

    assert [f.name for f in dataclasses.fields(StageSpec)] == [
        "name", "label", "allowed_tools", "disallowed_tools", "allow_bash", "can_write", "write_scope_hint", "system_append",
        "output_format", "output", "review", "fetch_domains", "permission_mode", "max_thinking_tokens", "fallback_model",
        "add_dirs", "agents", "mcp_servers", "model", "max_turns", "max_budget_usd", "max_agent_calls",
    ]
    assert [f.name for f in dataclasses.fields(Config)] == [
        "project_dir", "work_dir", "max_retries", "test_command", "test_timeout_sec", "auto_approve", "pause_for_review",
        "extra_test_globs", "stages", "domain_dir", "setting_sources", "protected_paths", "pipe", "max_buffer_mb",
    ]
