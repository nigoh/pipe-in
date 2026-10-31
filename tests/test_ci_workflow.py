"""CI のワークフロー（.github/workflows/ci.yml）と、その文書・Dependabot の検査（D0052）。

PyYAML は足さず、ワークフローと dependabot.yml が使う範囲だけを読む小さな読み手を、このファイルに置く
（tests/test_plugin_evals.py の read_case_yaml と同じ理由）。範囲外の書き方は読まずに例外にする。
リポジトリの実物は読むだけで、書かない。
"""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

import pytest

from test_skill_tidy import lacking, line_with, need_section, read_doc, section_text

ROOT = Path(__file__).resolve().parents[1]
CI_YML = ROOT / ".github" / "workflows" / "ci.yml"
DEPENDABOT = ROOT / ".github" / "dependabot.yml"
WORKFLOW_MD = ROOT / "docs" / "development" / "workflow.md"
DESIGN_MD = ROOT / "docs" / "development" / "design.md"
DEVELOP_MD = ROOT / "docs" / "guide" / "develop.md"
SKILL_MD = ROOT / ".claude" / "skills" / "pipe-in" / "SKILL.md"
CLAUDE_MD = ROOT / "CLAUDE.md"


# ---- YAML の小さな読み手 ----------------------------------------------------


class YamlUnsupported(ValueError):
    """読み手が扱う範囲の外の書き方。黙って読み違えず、例外にする。"""


KEY = re.compile(r"^(\"[^\"]*\"|'[^']*'|[^\s:#'\"\[{&*|>%@`!-][^:]*?):(?:\s+(.*))?$")


def strip_comment(s: str) -> str:
    quote = None
    for i, c in enumerate(s):
        if quote:
            if c == quote:
                quote = None
        elif c in "'\"" and (i == 0 or s[i - 1] in " [,"):
            quote = c
        elif c == "#" and (i == 0 or s[i - 1] in " \t"):
            return s[:i].rstrip()
    return s.rstrip()


def read_scalar(s: str):
    s = s.strip()
    if not s:
        return ""
    if s[0] in "&*{!":
        raise YamlUnsupported(f"範囲外の書き方: {s}")
    if s[0] == "[":
        if not s.endswith("]"):
            raise YamlUnsupported(f"1行の一覧が閉じていない: {s}")
        return [read_scalar(x) for x in s[1:-1].split(",") if x.strip()]
    if s[0] in "'\"" and len(s) >= 2 and s[-1] == s[0]:
        return s[1:-1]
    return s


class Reader:
    def __init__(self, text: str):
        self.lines = text.replace("\r\n", "\n").split("\n")
        for ln in self.lines:
            if ln.strip() in ("---", "..."):
                raise YamlUnsupported("複数の文書は読まない")
            if re.match(r"^ *\t", ln):
                raise YamlUnsupported("字下げのタブは読まない")
        self.pos = 0

    def peek(self):
        while self.pos < len(self.lines):
            cut = strip_comment(self.lines[self.pos])
            if cut.strip():
                return len(cut) - len(cut.lstrip()), cut.strip()
            self.pos += 1
        return None

    @staticmethod
    def is_item(content: str) -> bool:
        return content == "-" or content.startswith("- ")

    def node(self):
        p = self.peek()
        if p is None:
            return ""
        return self.read_list(p[0]) if self.is_item(p[1]) else self.read_map(p[0])

    def read_map(self, ind: int) -> dict:
        out: dict = {}
        while True:
            p = self.peek()
            if p is None or p[0] < ind or self.is_item(p[1]):
                break
            if p[0] > ind:
                raise YamlUnsupported(f"字下げが合わない: {p[1]}")
            m = KEY.match(p[1])
            if not m:
                raise YamlUnsupported(f"読めない行: {p[1]}")
            key = m.group(1).strip("'\"")
            rest = (m.group(2) or "").strip()
            if key in out:
                raise YamlUnsupported(f"鍵が重なっている: {key}")
            self.pos += 1
            if rest == "":
                q = self.peek()
                deeper = q is not None and (q[0] > ind or (q[0] == ind and self.is_item(q[1])))
                out[key] = self.node() if deeper else ""
            elif rest[0] == "|":
                out[key] = self.read_block(ind)
            elif rest[0] == ">":
                raise YamlUnsupported("折りたたみの文字は読まない")
            else:
                out[key] = read_scalar(rest)
        return out

    def read_block(self, ind: int) -> str:
        body: list[str] = []
        while self.pos < len(self.lines):
            ln = self.lines[self.pos]
            if ln.strip() and len(ln) - len(ln.lstrip()) <= ind:
                break
            body.append(ln)
            self.pos += 1
        while body and not body[-1].strip():
            body.pop()
        base = min((len(x) - len(x.lstrip()) for x in body if x.strip()), default=0)
        return "\n".join(x[base:] for x in body)

    def read_list(self, ind: int) -> list:
        out: list = []
        while True:
            p = self.peek()
            if p is None or p[0] != ind or not self.is_item(p[1]):
                break
            content = p[1]
            after = content[1:].lstrip()
            if after == "":
                self.pos += 1
                q = self.peek()
                out.append(self.node() if q is not None and q[0] > ind else "")
            elif KEY.match(after):
                off = len(content) - len(after)
                self.lines[self.pos] = " " * (ind + off) + after
                out.append(self.read_map(ind + off))
            else:
                self.pos += 1
                out.append(read_scalar(after))
        return out


def parse_yaml(text: str):
    reader = Reader(text)
    if reader.peek() is None:
        return {}
    result = reader.node()
    if reader.peek() is not None:
        raise YamlUnsupported(f"読み残した行: {reader.peek()[1]}")
    return result


# ---- 補助 -------------------------------------------------------------------

PINNED = re.compile(r"^(actions/(checkout|setup-python|setup-node))@[0-9a-f]{40}\s+#\s*v\d")


def load_ci() -> tuple[str, dict]:
    raw = read_doc(CI_YML)
    return raw, parse_yaml(raw)


def job_of(wf: dict, name: str) -> dict:
    jobs = wf.get("jobs")
    if not isinstance(jobs, dict) or name not in jobs:
        pytest.fail(f"ci.yml の jobs に「{name}」が無い（今のジョブ：{list(jobs) if isinstance(jobs, dict) else jobs}）", pytrace=False)
    return jobs[name]


def steps_of(job: dict) -> list[dict]:
    return job.get("steps") or []


def runs_of(job: dict) -> list[str]:
    return [s["run"] for s in steps_of(job) if "run" in s]


def uses_lines(raw: str) -> list[str]:
    out = []
    for line in raw.splitlines():
        m = re.match(r"^\s*(?:-\s+)?uses:\s*(\S.*)$", line)
        if m:
            out.append(m.group(1).strip())
    return out


def command_lines(claude_md: str) -> list[str]:
    body = need_section(claude_md, "コマンド", where="CLAUDE.md", depth=2)
    block = re.search(r"```bash\n(.*?)```", body, re.S)
    if not block:
        pytest.fail("CLAUDE.md の「コマンド」にコードブロックが無い", pytrace=False)
    out = []
    for line in block.group(1).splitlines():
        for part in strip_comment(line).split("&&"):
            if part.strip():
                out.append(part.strip())
    return out


# ---- AC-01 ------------------------------------------------------------------


def test_D0052_AC_01_pull_requestとmainへのpushで動く():
    """D0052-AC-01: .github/workflows/ に yml があり、on に main 向けの pull_request と main への push がある。"""
    wf_dir = ROOT / ".github" / "workflows"
    assert list(wf_dir.glob("*.yml")), ".github/workflows/ に *.yml が無い（まだ作っていない）"
    _, wf = load_ci()
    on = wf.get("on")
    assert isinstance(on, dict), f"on が対応表でない: {on!r}"
    assert "main" in on.get("pull_request", {}).get("branches", []), f"pull_request の branches に main が無い: {on}"
    assert on.get("push", {}).get("branches") == ["main"], f"push の branches が main だけでない: {on}"


# ---- AC-02 ------------------------------------------------------------------


def test_D0052_AC_02_pytestの前にpip_installがある():
    """D0052-AC-02: python ジョブで pip install -e '.[dev]' の手順が pytest -q より前にある。"""
    _, wf = load_ci()
    runs = runs_of(job_of(wf, "python"))
    pip = [i for i, r in enumerate(runs) if "pip install -e '.[dev]'" in r]
    test = [i for i, r in enumerate(runs) if r.strip() == "pytest -q"]
    assert pip, f"pip install -e '.[dev]' の手順が無い: {runs}"
    assert test, f"pytest -q の手順が無い: {runs}"
    assert pip[0] < test[0], f"pip install が pytest -q より後ろにある: {runs}"


# ---- AC-03 ------------------------------------------------------------------


def test_D0052_AC_03_拡張はnpm_ciから順に流す():
    """D0052-AC-03: extension ジョブが vscode で npm ci・npm test・npm run typecheck・npm run build をこの順に流す。"""
    _, wf = load_ci()
    job = job_of(wf, "extension")
    run_steps = [s for s in steps_of(job) if "run" in s]
    assert [s["run"].strip() for s in run_steps] == ["npm ci", "npm test", "npm run typecheck", "npm run build"]
    assert all(s.get("working-directory") == "vscode" for s in run_steps), f"working-directory が vscode でない手順がある: {run_steps}"


# ---- AC-04 ------------------------------------------------------------------


def test_D0052_AC_04_権限はcontents_readだけ():
    """D0052-AC-04: 先頭の permissions が contents: read だけで、ジョブはそれより広げず、write の語が無い。"""
    raw, wf = load_ci()
    assert wf.get("permissions") == {"contents": "read"}, f"先頭の permissions: {wf.get('permissions')!r}"
    for name, job in wf.get("jobs", {}).items():
        assert job.get("permissions") in (None, {"contents": "read"}), f"ジョブ {name} の permissions が広い: {job.get('permissions')!r}"
    assert "write" not in raw, "ci.yml に write の語がある"


def test_D0052_AC_04_checkoutはtokenを残さない():
    """D0052-AC-04: すべての actions/checkout の with に persist-credentials: false がある。"""
    _, wf = load_ci()
    checkouts = [s for j in wf.get("jobs", {}).values() for s in steps_of(j) if str(s.get("uses", "")).startswith("actions/checkout@")]
    assert checkouts, "actions/checkout の手順が無い"
    for s in checkouts:
        assert s.get("with", {}).get("persist-credentials") == "false", f"persist-credentials が false でない: {s}"


# ---- AC-05 ------------------------------------------------------------------


def test_D0052_AC_05_禁止の語が出てこない():
    """D0052-AC-05: コメントを含む元の文字に pull_request_target・secrets.・ANTHROPIC_API_KEY が無い。"""
    raw = read_doc(CI_YML)
    found = [w for w in ("pull_request_target", "secrets.", "ANTHROPIC_API_KEY") if w in raw]
    assert not found, f"ci.yml に禁止の語がある: {found}"


# ---- AC-06 ------------------------------------------------------------------


def test_D0052_AC_06_アクションはSHAで固定している():
    """D0052-AC-06: すべての uses が 3 つのアクションの 40 桁の SHA で、後ろに版のコメントがある。"""
    raw = read_doc(CI_YML)
    uses = uses_lines(raw)
    assert uses, "uses の行が無い"
    bad = [u for u in uses if not PINNED.match(u)]
    assert not bad, f"SHA（40 桁）と版のコメントで固定していない uses がある: {bad}"


def test_D0052_AC_06_dependabotにgithub_actionsがある():
    """D0052-AC-06: dependabot.yml の updates に github-actions（directory は /）があり、pip・npm が残っている。"""
    data = parse_yaml(read_doc(DEPENDABOT))
    updates = data.get("updates", [])
    eco = {u.get("package-ecosystem"): u for u in updates}
    assert "github-actions" in eco, f"github-actions が無い（今：{list(eco)}）"
    assert eco["github-actions"].get("directory") == "/"
    assert {"pip", "npm"} <= set(eco), f"pip・npm が消えている: {list(eco)}"



def test_D0055_AC_01_dependabotはtypes_nodeのメジャーを上げない():
    """D0055-AC-01: npm の ignore に @types/node のメジャーの上げがある（拡張が動く Node の版に合わせておく型）。"""
    data = parse_yaml(read_doc(DEPENDABOT))
    npm = next(u for u in data.get("updates", []) if u.get("package-ecosystem") == "npm")
    ignored = {i.get("dependency-name"): i.get("update-types", []) for i in npm.get("ignore", [])}
    assert "@types/node" in ignored, f"@types/node が ignore に無い（今：{list(ignored)}）"
    assert "version-update:semver-major" in ignored["@types/node"], f"メジャーの上げを止めていない: {ignored['@types/node']}"


# ---- AC-07 ------------------------------------------------------------------


def test_D0052_AC_07_Pythonの版はrequires_pythonの下限と同じ():
    """D0052-AC-07: setup-python の python-version が pyproject.toml の requires-python の下限と文字列で等しい。"""
    spec = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["requires-python"]
    m = re.search(r">=\s*(\d+\.\d+)", spec)
    assert m, f"requires-python の下限を読めない: {spec}"
    _, wf = load_ci()
    versions = [s["with"]["python-version"] for j in wf.get("jobs", {}).values() for s in steps_of(j) if str(s.get("uses", "")).startswith("actions/setup-python@")]
    assert versions, "setup-python の python-version が無い"
    assert all(v == m.group(1) for v in versions), f"python-version {versions} が下限 {m.group(1)} と違う"


def test_D0052_AC_07_Nodeの版はenginesの下限と同じ():
    """D0052-AC-07: setup-node の node-version の主な版が vscode/package.json の engines.node の下限と等しい。"""
    spec = json.loads((ROOT / "vscode" / "package.json").read_text(encoding="utf-8"))["engines"]["node"]
    m = re.search(r">=\s*(\d+)", spec)
    assert m, f"engines.node の下限を読めない: {spec}"
    _, wf = load_ci()
    versions = [s["with"]["node-version"] for j in wf.get("jobs", {}).values() for s in steps_of(j) if str(s.get("uses", "")).startswith("actions/setup-node@")]
    assert versions, "setup-node の node-version が無い"
    assert all(v.split(".")[0] == m.group(1) for v in versions), f"node-version {versions} が下限 {m.group(1)} と違う"


# ---- AC-08 ------------------------------------------------------------------


def test_D0052_AC_08_concurrencyで古い実行を取り消す():
    """D0052-AC-08: concurrency の group が空でなく、cancel-in-progress は PR のときだけ真になる式。"""
    _, wf = load_ci()
    c = wf.get("concurrency")
    assert isinstance(c, dict), f"concurrency が無い: {c!r}"
    assert c.get("group"), "concurrency.group が空"
    assert c.get("cancel-in-progress") == "${{ github.event_name == 'pull_request' }}", f"cancel-in-progress: {c.get('cancel-in-progress')!r}"


def test_D0052_AC_08_ジョブにtimeoutがあり_OSの版は固定():
    """D0052-AC-08: すべてのジョブに 1〜60 の timeout-minutes があり、runs-on が -latest で終わらない。"""
    _, wf = load_ci()
    jobs = wf.get("jobs")
    assert isinstance(jobs, dict) and jobs, f"jobs が無い: {jobs!r}"
    for name, job in jobs.items():
        t = job.get("timeout-minutes", "")
        assert str(t).isdigit() and 1 <= int(t) <= 60, f"ジョブ {name} の timeout-minutes: {t!r}"
        assert job.get("runs-on") and not str(job["runs-on"]).endswith("-latest"), f"ジョブ {name} の runs-on: {job.get('runs-on')!r}"


# ---- AC-09 ------------------------------------------------------------------


def test_D0052_AC_09_workflow_mdの終えるにCIの確認がある():
    """D0052-AC-09: workflow.md の「5. 終える」の節に CI・緑・手元がある。"""
    md = read_doc(WORKFLOW_MD)
    body = need_section(md, "5. 終える", where="workflow.md", depth=2)
    missing = lacking(body, ["CI", "緑", "手元"])
    assert not missing, f"「5. 終える」に足りない語: {missing}"


def test_D0052_AC_09_SKILLのmainに入れる行にCIの確認がある():
    """D0052-AC-09: SKILL.md の「main に入れるよう言われたら」の行に CI と緑がある。"""
    line = line_with(read_doc(SKILL_MD), "main に入れるよう言われたら", "SKILL.md")
    missing = lacking(line, ["CI", "緑"])
    assert not missing, f"その行に足りない語: {missing}"


# ---- AC-10 ------------------------------------------------------------------


def test_D0052_AC_10_workflow_mdにCIの節がある():
    """D0052-AC-10: workflow.md の「6. CI」の節に、流すもの・権限・秘密・手元・ブランチの保護が書いてある。"""
    md = read_doc(WORKFLOW_MD)
    body = need_section(md, "6. CI", where="workflow.md", depth=2)
    words = [
        "pytest -q", "npm ci", "npm test", "npm run typecheck", "npm run build",
        "contents: read", "秘密", "手元", "ブランチの保護", "python", "extension", ".github/workflows/ci.yml",
    ]
    missing = lacking(body, words)
    assert not missing, f"「6. CI」に足りない語: {missing}"


def test_D0052_AC_10_develop_mdにCIの節がある():
    """D0052-AC-10: docs/guide/develop.md に CI の説明（流すもの・秘密・手元・workflow.md への案内）がある。"""
    text = read_doc(DEVELOP_MD)
    missing = lacking(text, ["CI", "pytest -q", "npm ci", "秘密", "手元", "workflow.md"])
    assert not missing, f"develop.md に足りない語: {missing}"


def test_D0052_AC_10_designの置き場所の表にCIの行がある():
    """D0052-AC-10: design.md の表に .github/workflows/ci.yml を含む行がある。"""
    text = read_doc(DESIGN_MD)
    rows = [ln for ln in text.splitlines() if ln.lstrip().startswith("|") and ".github/workflows/ci.yml" in ln]
    assert rows, "design.md の表に .github/workflows/ci.yml の行が無い"


# ---- AC-11 ------------------------------------------------------------------


def test_D0052_AC_11_ワークフローのコマンドはCLAUDE_mdのコマンドと食い違わない():
    """D0052-AC-11: ワークフローの run（pip install を除く）がすべて CLAUDE.md の「コマンド」にあるコマンドと一致する。"""
    _, wf = load_ci()
    known = command_lines(read_doc(CLAUDE_MD))
    for need in ["pytest -q", "npm ci", "npm test", "npm run typecheck", "npm run build"]:
        assert need in known, f"CLAUDE.md の「コマンド」に {need} が無い: {known}"
    for job in wf.get("jobs", {}).values():
        for r in runs_of(job):
            if "pip install" in r:
                continue
            assert r.strip() in known, f"ワークフローの run「{r}」が CLAUDE.md のコマンドにない"


# ---- AC-12 ------------------------------------------------------------------


def test_D0052_AC_12_ワークフローは記録と設定の置き場所に触れない():
    """D0052-AC-12: ci.yml の元の文字に docs/pipeline・.pipe-in・pipeline.toml・pipe.toml・state.json が無い。"""
    raw = read_doc(CI_YML)
    found = [w for w in ("docs/pipeline", ".pipe-in", "pipeline.toml", "pipe.toml", "state.json") if w in raw]
    assert not found, f"ci.yml が記録・設定の置き場所に触れている: {found}"


# ---- 読み手と節の切り出しの見本（今のまま通る。守る） ---------------------------

SAMPLE = """\
# コメント
name: CI   # 後ろのコメント
on:
  pull_request:
    branches: [main]
  push:
    branches: [main, "dev"]
permissions:
  contents: read
jobs:
  python:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@abc # v4
        with:
          persist-credentials: false
      - run: pip install -e '.[dev]'
      - run: |
          echo a
          echo "# b"
        working-directory: vscode
      - name: x
        run: pytest -q
"""


def test_D0052_見本_正しい文は読める_守る():
    """D0052-AC-01: 読み手が、入れ子・一覧・1行の一覧・引用符・複数行・コメントを読める（今のまま通る。守る）。"""
    d = parse_yaml(SAMPLE)
    assert d["name"] == "CI"
    assert "on" in d and True not in d  # on を真偽値にしない
    assert d["on"]["push"]["branches"] == ["main", "dev"]
    steps = d["jobs"]["python"]["steps"]
    assert steps[0] == {"uses": "actions/checkout@abc", "with": {"persist-credentials": "false"}}
    assert steps[1] == {"run": "pip install -e '.[dev]'"}
    assert steps[2]["run"] == 'echo a\necho "# b"'
    assert steps[2]["working-directory"] == "vscode"
    assert steps[3] == {"name": "x", "run": "pytest -q"}


@pytest.mark.parametrize(
    "text",
    [
        "a: &x 1\n",
        "a: *x\n",
        "a: {b: 1}\n",
        "a:\n\tb: 1\n",
        "a: 1\n---\nb: 2\n",
        "a: 1\na: 2\n",
        "a: >\n  x\n",
    ],
    ids=["アンカー", "参照", "対応表の1行", "タブ", "複数文書", "鍵の重なり", "折りたたみ"],
)
def test_D0052_見本_範囲外の書き方は例外にする_守る(text):
    """D0052-AC-01: 読み手が範囲外の書き方を黙って読まず、例外にする（今のまま通る。守る）。"""
    with pytest.raises(YamlUnsupported):
        parse_yaml(text)


@pytest.mark.parametrize(
    ("value", "ok"),
    [
        ("actions/checkout@" + "a" * 40 + " # v4", True),
        ("actions/setup-node@" + "0123456789abcdef" * 2 + "01234567 # v4.1.0", True),
        ("actions/checkout@main # v4", False),
        ("actions/checkout@master", False),
        ("actions/checkout@v4", False),
        ("actions/checkout@" + "a" * 7 + " # v4", False),
        ("actions/checkout@" + "a" * 40, False),
        ("actions/checkout@" + "a" * 40 + " # latest", False),
        ("actions/cache@" + "a" * 40 + " # v4", False),
    ],
    ids=["40桁と版", "別のアクション", "main", "master", "タグだけ", "短いSHA", "コメント無し", "版でないコメント", "3つの外"],
)
def test_D0052_見本_固定の形の見分け_守る(value, ok):
    """D0052-AC-06: SHA 固定の形の見分けが、正しい形だけを通す（今のまま通る。守る）。"""
    assert bool(PINNED.match(value)) is ok


def test_D0052_見本_CLAUDE_mdのコマンドを読める_守る():
    """D0052-AC-11: CLAUDE.md の「コマンド」から、5 つのコマンドを行ごとに取り出せる（今のまま通る。守る）。"""
    known = command_lines(read_doc(CLAUDE_MD))
    for need in ["pytest -q", "npm ci", "npm test", "npm run typecheck", "npm run build"]:
        assert need in known, f"{need} が取り出せない: {known}"


def test_D0052_見本_節の切り出し_守る():
    """D0052-AC-09: 節の切り出しが、次の同じ階層の見出しの前までを返す（今のまま通る。守る）。"""
    md = "## 5. 終える：x\nCI 緑\n### 小\n手元\n## 6. CI：y\nほか\n"
    assert section_text(md, "5. 終える", depth=2) == "CI 緑\n### 小\n手元\n"
    assert section_text(md, "6. CI", depth=2) == "ほか\n"
    assert section_text(md, "7. なし", depth=2) is None
