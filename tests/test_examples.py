"""見本のパイプ集（examples/diagrams・spec-qa・research）の検査（D0070）。SDK は呼ばない。

見本の中身は読むだけで、書くのは tmp_path の中だけ（ひな形を埋めて比べるときも tmp_path に作る）。
README は節の見出しと表・金額の行の形だけを見る（言い回しは変えてよい）。
"""

from __future__ import annotations

import re
import shutil
from dataclasses import asdict
from pathlib import Path

import pytest

from pipe_in.pipe.definition import check_pipe, load_pipe
from pipe_in.pipe.lint import lint_pipe
from pipe_in_generator.cli import main as gen_main
from pipe_in_generator.render import render_template
from test_rules import SECRET_FILES, local_info_in

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"
TEMPLATES = ROOT / "generator" / "templates"
NAMES = ["diagrams", "spec-qa", "research"]
# ひな形の写しにする見本（research はひな形なし）
TEMPLATED = ["diagrams", "spec-qa"]
# ひな形を埋める決まった値（設計 4 節）
FILL = {
    "diagrams_dir": "docs/diagrams",
    "source_dirs": "プロジェクト全体",
    "docs_hint": "プロジェクトの中",
}
SECTIONS = ["何をするか", "向く場面と向かない場面", "必要なもの", "流し方", "段と書ける範囲", "費用の目安", "直し方"]

# 設計 2 節の上限の表：段 → (max_budget_usd, max_turns)
LIMITS = {
    "diagrams": {"survey": (1.0, 40), "draw": (2.0, 60), "verify": (1.0, 40)},
    "spec-qa": {"trace": (1.5, 50), "gaps": (1.5, 50), "qa": (1.5, 50)},
    "research": {"frame": (0.5, 20), "gather": (2.0, 60), "summarize": (1.0, 30), "verify": (1.5, 50)},
}
TOTAL = {"diagrams": 4.0, "spec-qa": 4.5, "research": 5.0}
RETRY_TOTAL = {"diagrams": 10.0, "research": 10.0}  # spec-qa は差し戻しなし

CODE_SUFFIXES = {".py", ".js", ".mjs", ".sh", ".html", ".ts", ".cjs"}
MEDIA_SUFFIXES = {".mp4", ".mov", ".webm", ".wav", ".mp3", ".m4a", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"}


def pipe_dir(name: str) -> Path:
    return EXAMPLES / name / "pipes" / f"pipe-in-{name}"


def need_dir(name: str) -> Path:
    d = pipe_dir(name)
    assert d.is_dir(), f"{d.relative_to(ROOT)} がありません（見本をまだ作っていない）"
    return d


def read(path: Path) -> str:
    assert path.is_file(), f"{path.relative_to(ROOT)} がありません（まだ作っていない）"
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def readme_section(name: str, heading: str) -> list[str]:
    """README の `## heading` の節の行（次の `## ` まで）。"""
    lines = read(need_dir(name) / "README.md").splitlines()
    for i, line in enumerate(lines):
        if line.startswith("## " + heading):
            out = []
            for rest in lines[i + 1 :]:
                if rest.startswith("## "):
                    break
                out.append(rest)
            return out
    raise AssertionError(f"{name} の README に「## {heading}」の節がありません")


def table_rows(lines: list[str]) -> list[list[str]]:
    """Markdown の表の、見出しと区切りを除いた行をセルに分ける。"""
    rows = []
    for line in lines:
        if not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if all(re.fullmatch(r":?-{2,}:?", c) for c in cells):
            continue
        rows.append(cells)
    return rows[1:]  # 先頭は見出しの行


def first_name(cell: str) -> str:
    m = re.match(r"`([^`]+)`", cell)
    assert m, f"第 1 列の先頭が `名前` の形ではありません：{cell!r}"
    return m.group(1)


def money(text: str) -> float:
    return float(text.replace("$", "").replace(",", "").strip())


# ---- D0070-AC-01〜04：置き場所・読める・上限 ------------------------------------------


@pytest.mark.parametrize("name", NAMES)
def test_d0070_ac01_見本の置き場所と必要なファイル(name):
    """D0070-AC-01: examples/<名前>/pipes/pipe-in-<名前>/ に pipe.toml・README.md・指示文（段の数だけ）がある。"""
    d = need_dir(name)
    assert (d / "pipe.toml").is_file()
    assert (d / "README.md").is_file()
    stages = len(load_pipe(d).stages)
    prompts = sorted((d / "prompts").glob("*.md"))
    assert len(prompts) == stages, f"指示文 {len(prompts)} 個、段 {stages} 個"


@pytest.mark.parametrize("name", NAMES)
def test_d0070_ac02_loadできcheckの誤りもlintの注意も0件(name, tmp_path):
    """D0070-AC-02: load_pipe で読めて、check_pipe の誤りが 0 件、lint_pipe の注意が 0 件。"""
    pipe = load_pipe(need_dir(name))
    assert check_pipe(pipe, tmp_path) == []
    assert lint_pipe(pipe) == []


@pytest.mark.parametrize("name", NAMES)
def test_d0070_ac03_pipe_in_gen_checkの終了コードが0(name, tmp_path, capsys):
    """D0070-AC-03: pipe-in-gen check <名前> --pipes-dir examples/<名前>/pipes の終了コードが 0。"""
    code = gen_main(["check", name, "--pipes-dir", str(EXAMPLES / name / "pipes"), "--project", str(tmp_path)])
    out = capsys.readouterr().out
    assert code == 0, out


@pytest.mark.parametrize("name", NAMES)
def test_d0070_ac04_全段にmax_budget_usdとmax_turns(name):
    """D0070-AC-04: すべての段に、0 より大きい max_budget_usd と max_turns がある（max_turns は既定の 100 より小さい）。"""
    for s in load_pipe(need_dir(name)).stages:
        assert s.max_budget_usd is not None and s.max_budget_usd > 0, f"{name}/{s.name}: max_budget_usd"
        assert s.max_turns is not None and 0 < s.max_turns < 100, f"{name}/{s.name}: max_turns"


@pytest.mark.parametrize("name", NAMES)
def test_d0070_ac04_上限の数字が設計どおり(name):
    """D0070-AC-04: 段ごとの上限が設計 2 節の表のとおり（段の名前と並びも）。"""
    stages = load_pipe(need_dir(name)).stages
    assert [s.name for s in stages] == list(LIMITS[name])
    assert {s.name: (s.max_budget_usd, s.max_turns) for s in stages} == LIMITS[name]


# ---- D0070-AC-05〜08：README --------------------------------------------------------


@pytest.mark.parametrize("name", NAMES)
def test_d0070_ac05_READMEの節がそろう(name):
    """D0070-AC-05: README に 7 つの節（何をするか・向く場面と向かない場面・必要なもの・流し方・段と書ける範囲・費用の目安・直し方）がある。"""
    text = read(need_dir(name) / "README.md")
    heads = [line[3:].strip() for line in text.splitlines() if line.startswith("## ")]
    for h in SECTIONS:
        assert any(x.startswith(h) for x in heads), f"{name}: 「## {h}」の節がありません（今ある節: {heads}）"


@pytest.mark.parametrize("name", NAMES)
def test_d0070_ac06_READMEの段の表がpipe_tomlと同じ(name):
    """D0070-AC-06: 「段と書ける範囲」の表の行の数・段の名前・access・docs_dir（無ければ —）・成果物が pipe.toml と同じ。"""
    stages = load_pipe(need_dir(name)).stages
    rows = table_rows(readme_section(name, "段と書ける範囲"))
    assert [first_name(r[0]) for r in rows] == [s.name for s in stages]
    for r, s in zip(rows, stages):
        assert s.output in r[1], f"{s.name}: 成果物 {s.output} が {r[1]!r} にない"
        assert r[2].strip("` ") == s.access, f"{s.name}: access"
        assert r[3].strip("` ") == (s.docs_dir or "—"), f"{s.name}: docs_dir"


def retry_extra(stages) -> float:
    """差し戻しを使い切ったときに、1 回通しの上限へ足す額（戻り先から判定の段までの上限の合計 × max_retries）。"""
    extra = 0.0
    names = [s.name for s in stages]
    for i, s in enumerate(stages):
        if s.check is not None and s.check.on_fail and s.check.on_fail != s.name:
            j = names.index(s.check.on_fail)
            extra += sum(x.max_budget_usd for x in stages[j : i + 1]) * s.check.max_retries
    return extra


@pytest.mark.parametrize("name", NAMES)
def test_d0070_ac07_READMEの費用の表と合計と差し戻しの合計(name):
    """D0070-AC-07: 費用の表の各段の上限が pipe.toml と同じで、1 回通しの合計・差し戻しを使い切ったときの合計が計算と等しい。"""
    stages = load_pipe(need_dir(name)).stages
    lines = readme_section(name, "費用の目安")
    rows = table_rows(lines)
    assert [first_name(r[0]) for r in rows] == [s.name for s in stages]
    for r, s in zip(rows, stages):
        assert money(r[1]) == pytest.approx(s.max_budget_usd), f"{s.name}: max_budget_usd"
        assert int(r[2]) == s.max_turns, f"{s.name}: max_turns"
    body = "\n".join(lines)
    once = re.search(r"1 回通しの上限の合計：\$(\d+\.\d+)", body)
    assert once, "「1 回通しの上限の合計：$N.N」の行がありません"
    total = sum(s.max_budget_usd for s in stages)
    assert float(once.group(1)) == pytest.approx(total)
    assert total == pytest.approx(TOTAL[name])
    used = re.search(r"差し戻しを使い切ったときの上限の合計：\$(\d+\.\d+)", body)
    if name in RETRY_TOTAL:
        assert used, "「差し戻しを使い切ったときの上限の合計：$N.N」の行がありません"
        assert float(used.group(1)) == pytest.approx(total + retry_extra(stages))
        assert float(used.group(1)) == pytest.approx(RETRY_TOTAL[name])
    else:
        assert retry_extra(stages) == 0
        assert used is None, "差し戻しのない見本に「差し戻しを使い切ったとき」の行は置かない"


@pytest.mark.parametrize("name", NAMES)
def test_d0070_ac08_READMEに実測はまだの文(name):
    """D0070-AC-08: 費用の節に、実測はまだであること・金額は上限であって見積りではないことを書いた文がある。"""
    body = "\n".join(readme_section(name, "費用の目安"))
    assert "実測はまだありません" in body
    assert "上限" in body and "見積り" in body
    assert "judge" in body, "審査の費用が検証の段の上限に入ることを書く"


# ---- D0070-AC-09〜11：research -----------------------------------------------------


def research():
    return load_pipe(need_dir("research"))


def test_d0070_ac09_researchの段の並びと権限():
    """D0070-AC-09（設計 0 節の改め）: frame・gather・summarize・verify の順。summarize だけ docs（docs/research）、ほかは read。"""
    pipe = research()
    assert [s.name for s in pipe.stages] == ["frame", "gather", "summarize", "verify"]
    assert pipe.input == "required"
    access = {"frame": "read", "gather": "read", "summarize": "docs", "verify": "read"}
    for s in pipe.stages:
        assert s.access == access[s.name], s.name
        assert s.docs_dir == ("docs/research" if s.name == "summarize" else None), s.name
        assert not s.web and not s.fetch_domains, f"{s.name}: Web を使わない"
        assert not s.mcp and not s.mcp_servers, f"{s.name}: mcp なし"
        assert not s.bash, f"{s.name}: bash なし"
        assert not s.writes, f"{s.name}: writes は書かない"
        assert s.review is (s.name in {"frame", "summarize"}), f"{s.name}: review"


def test_d0070_ac10_researchのverifyの検証():
    """D0070-AC-10（設計 0 節の改め）: verify の check は verdict・on_fail=summarize・max_retries=2・ASCII だけの command・must に「出典」。"""
    verify = research().stages[-1]
    assert verify.name == "verify"
    check = verify.check
    assert check is not None, "verify に [stages.check] がありません"
    assert check.verdict is True
    assert check.on_fail == "summarize"
    assert check.max_retries == 2
    assert check.command and "docs/research/report.md" in check.command
    assert check.command.isascii(), "command は ASCII だけ（cmd.exe に日本語を渡さない）"
    assert check.judge is not None and check.judge.must, "judge の must がありません"
    assert any("出典" in f"{m.name} {m.description}" for m in check.judge.must), "must に「出典のない断定がない」に当たる項目が要る"


def test_d0070_ac11_gatherの指示文に出典とWebなし():
    """D0070-AC-11: gather の指示文に、事実ごとの出典・出典が無いものは「分からない」・Web を使わないことがある。"""
    gather = next(s for s in research().stages if s.name == "gather")
    text = gather.prompt_text()
    assert "出典" in text
    assert "分からない" in text
    assert "Web" in text, "Web を使わないことを書く"


# ---- D0070-AC-12〜14：ひな形との重なり ------------------------------------------------


def _md_files(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): p.read_text(encoding="utf-8").replace("\r\n", "\n") for p in sorted(root.glob("prompts/*.md"))}


def render_pipe_dir(template: Path, dest: Path, values: dict[str, str | None]) -> Path:
    """ひな形（pipe.toml と prompts/*.md）を公開の render_template で dest に埋める。README は見ない。"""
    (dest / "prompts").mkdir(parents=True)
    for src in sorted(template.glob("prompts/*.md")):
        text = render_template(src.read_text(encoding="utf-8"), values, toml=False)
        (dest / "prompts" / src.name).write_text(text, encoding="utf-8")
    toml = render_template((template / "pipe.toml").read_text(encoding="utf-8"), values, toml=True)
    (dest / "pipe.toml").write_text(toml, encoding="utf-8")
    return dest


def normalized(pipe) -> dict:
    """max_budget_usd・max_turns・パスを外した定義の辞書。"""
    d = asdict(pipe)
    d.pop("dir", None)
    for s in d["stages"]:
        for k in ("max_budget_usd", "max_turns", "prompt_file"):
            s.pop(k, None)
    return d


def template_diff(template: Path, example: Path, name: str, workdir: Path) -> list[str]:
    """ひな形を埋めたものと見本の食い違い（空なら一致）。指示文は一字一句、pipe.toml は上限の 2 項目を除いて比べる。"""
    values = {"name": name, **FILL}
    rendered = render_pipe_dir(template, workdir / f"pipe-in-{name}", values)
    diffs: list[str] = []
    for rel, text in _md_files(rendered).items():
        left = re.findall(r"\{\{[^}]*\}\}", text)
        if left:
            diffs.append(f"{rel}: 置き換えのない {{{{…}}}} が残っている {left}")
    left = re.findall(r"\{\{[^}]*\}\}", (rendered / "pipe.toml").read_text(encoding="utf-8"))
    if left:
        diffs.append(f"pipe.toml: 置き換えのない {{{{…}}}} が残っている {left}")
    want, got = _md_files(rendered), _md_files(example)
    if sorted(want) != sorted(got):
        diffs.append(f"指示文のファイルが違う：ひな形 {sorted(want)} / 見本 {sorted(got)}")
    for rel in sorted(set(want) & set(got)):
        if want[rel] != got[rel]:
            diffs.append(f"{rel}: 指示文がひな形を埋めたものと違う")
    if normalized(load_pipe(rendered)) != normalized(load_pipe(example)):
        diffs.append("pipe.toml: 上限の 2 項目を除いて、ひな形を埋めたものと違う")
    return diffs


@pytest.mark.parametrize("name", TEMPLATED)
def test_d0070_ac12_指示文がひな形を埋めたものと一字も違わない(name, tmp_path):
    """D0070-AC-12: prompts/*.md が、ひな形を決まった値で埋めたものと一字も違わない（置き換え後に {{…}} が残らない）。"""
    example = need_dir(name)
    rendered = render_pipe_dir(TEMPLATES / name, tmp_path / f"pipe-in-{name}", {"name": name, **FILL})
    want, got = _md_files(rendered), _md_files(example)
    assert sorted(got) == sorted(want)
    for rel in want:
        assert not re.findall(r"\{\{[^}]*\}\}", want[rel]), f"{rel}: ひな形に新しい {{{{値}}}} が増えている"
        assert got[rel] == want[rel], f"{rel}: ひな形を埋めたものと違う"


@pytest.mark.parametrize("name", TEMPLATED)
def test_d0070_ac13_pipe_tomlが上限の2項目を除いてひな形と同じ(name, tmp_path):
    """D0070-AC-13: pipe.toml を読んだ値が、max_budget_usd・max_turns を除けば、ひな形を埋めたものを読んだ値と同じ。"""
    example = need_dir(name)
    rendered = render_pipe_dir(TEMPLATES / name, tmp_path / f"pipe-in-{name}", {"name": name, **FILL})
    assert normalized(load_pipe(example)) == normalized(load_pipe(rendered))


def test_d0070_ac14_ひな形を変えると見本の一致の検査が落ちる(tmp_path):
    """D0070-AC-14: 比べる関数は、ひな形を一字変えた・段を足した・{{新しい値}} を足したとき、不一致を返す（今のままで通る。検査そのものの検査）。"""
    name = "diagrams"
    # 見本の代わりに、本物のひな形を埋めて作った「正しい見本」を置く
    good = render_pipe_dir(TEMPLATES / name, tmp_path / "good" / f"pipe-in-{name}", {"name": name, **FILL})

    def broken(label: str) -> Path:
        copy = tmp_path / label / name
        shutil.copytree(TEMPLATES / name, copy)
        return copy

    assert template_diff(TEMPLATES / name, good, name, tmp_path / "w0") == []

    one_char = broken("onechar")
    first = sorted((one_char / "prompts").glob("*.md"))[0]
    first.write_text(first.read_text(encoding="utf-8") + "。", encoding="utf-8")
    assert template_diff(one_char, good, name, tmp_path / "w1") != []

    added_stage = broken("stage")
    with (added_stage / "pipe.toml").open("a", encoding="utf-8") as f:
        f.write('\n[[stages]]\nname = "extra"\nlabel = "足した段"\noutput = "09_extra.md"\naccess = "read"\nprompt_file = "prompts/09_extra.md"\n')
    (added_stage / "prompts" / "09_extra.md").write_text("足した段\n", encoding="utf-8")
    assert template_diff(added_stage, good, name, tmp_path / "w2") != []

    new_value = broken("newvalue")
    first = sorted((new_value / "prompts").glob("*.md"))[0]
    first.write_text(first.read_text(encoding="utf-8") + "\n{{新しい値}}\n", encoding="utf-8")
    shutil.copy(first, tmp_path / "good" / f"pipe-in-{name}" / "prompts" / first.name)  # 見本にも同じ文があっても、置き換わらない {{…}} は落とす
    assert any("{{" in d for d in template_diff(new_value, tmp_path / "good" / f"pipe-in-{name}", name, tmp_path / "w3"))


# ---- D0070-AC-15〜18：公開前提 -------------------------------------------------------


def files_of(name: str) -> list[Path]:
    root = EXAMPLES / name
    assert root.is_dir(), f"{root.relative_to(ROOT)} がありません（見本をまだ作っていない）"
    return sorted(p for p in root.rglob("*") if p.is_file() and "__pycache__" not in p.parts)


@pytest.mark.parametrize("name", NAMES)
def test_d0070_ac15_見本に手元の情報も秘密も無い(name):
    """D0070-AC-15: 全ファイルに、ユーザー名の入ったパス・メールアドレス・秘密のファイル名が無い（tests/test_rules.py と同じ規則）。"""
    found = []
    for p in files_of(name):
        rel = p.relative_to(ROOT).as_posix()
        if SECRET_FILES.search(rel):
            found.append(f"{rel}: 秘密のファイル")
        found += [f"{rel}: {f}" for f in local_info_in(p.read_text(encoding="utf-8", errors="ignore"))]
    assert found == []
    assert files_of(name), f"examples/{name}/ にファイルがありません"


@pytest.mark.parametrize("name", NAMES)
def test_d0070_ac16_置き換え前のマスタッシュが残らない(name):
    """D0070-AC-16: 見本に、置き換え前の {{…}} が残っていない。"""
    files = files_of(name)
    assert files, f"examples/{name}/ にファイルがありません"
    bad = [p.relative_to(ROOT).as_posix() for p in files if re.search(r"\{\{[^}]*\}\}", p.read_text(encoding="utf-8", errors="ignore"))]
    assert bad == []


@pytest.mark.parametrize("name", NAMES)
def test_d0070_ac17_見本のファイルはpipe_toml_README_promptsだけ(name):
    """D0070-AC-17: 見本の中のファイルは pipe.toml・README.md・prompts/*.md だけ（動画・画像・音声・コードを置かない。layout.json も置かない）。"""
    base = pipe_dir(name)
    files = files_of(name)
    assert files, f"examples/{name}/ にファイルがありません"
    for p in files:
        assert p.suffix not in CODE_SUFFIXES | MEDIA_SUFFIXES, p.relative_to(ROOT).as_posix()
    rels = sorted(p.relative_to(base).as_posix() for p in files if base in p.parents)
    assert len(rels) == len(files), "pipes/pipe-in-<名前>/ の外にファイルがあります"
    assert all(r in {"pipe.toml", "README.md"} or re.fullmatch(r"prompts/[^/]+\.md", r) for r in rels), rels


def test_d0070_ac18_video_truncateは変えない():
    """D0070-AC-18（今のままで通る。守る）: examples/video/ と examples/truncate/ があり、pipe-in-video の段の数が 5 のまま。"""
    assert (EXAMPLES / "video").is_dir() and (EXAMPLES / "truncate").is_dir()
    assert len(load_pipe(EXAMPLES / "video" / "pipes" / "pipe-in-video").stages) == 5


# ---- D0070-AC-37〜39：文書 ------------------------------------------------------------


def test_d0070_ac37_examples_READMEに3つの見本とリンク():
    """D0070-AC-37: examples/README.md に、3 つの見本の名前・流し方・各 README へのリンクがあり、リンク先が実在する。"""
    path = EXAMPLES / "README.md"
    text = read(path)
    targets = [t.split("#")[0] for t in re.findall(r"\]\(([^)\s]+)\)", text) if not re.match(r"[a-z]+:", t)]
    for name in NAMES:
        assert name in text, f"{name} がありません"
        assert f"pipe-in --pipe {name}" in text, f"{name}: 流し方（pipe-in --pipe {name} …）がありません"
        want = f"{name}/pipes/pipe-in-{name}/README.md"
        assert any(t.removeprefix("./") == want for t in targets), f"{want} へのリンクがありません"
    for t in targets:
        if t:
            assert (path.parent / t).exists(), f"リンク先がありません：{t}"


def test_d0070_ac38_designの表に見本の行と生成データの行():
    """D0070-AC-38: docs/development/design.md の置き場所の表に、3 つの見本と examples/README.md の行、見本のデータ（生成）の行がある。"""
    text = read(ROOT / "docs" / "development" / "design.md")
    rows = [line for line in text.splitlines() if line.lstrip().startswith("|")]

    def row_with(*needles: str) -> bool:
        return any(all(n in r for n in needles) for r in rows)

    for name in NAMES:
        assert row_with(f"examples/{name}/pipes/pipe-in-{name}/"), f"表に examples/{name}/pipes/pipe-in-{name}/ の行がありません"
    assert row_with("examples/README.md")
    assert row_with("vscode/src/domain/exampleData.ts", "vscode/src/domain/pipeExamples.ts", "vscode/src/app/exampleFlow.ts", "vscode/scripts/genExamples.ts")
    assert row_with("examples/video/"), "動画の見本の行は残す"


def test_d0070_ac39_pipes_mdとvscode_mdに見本の節とexamples_READMEへのリンク():
    """D0070-AC-39: docs/guide/pipes.md と vscode.md に「見本」の節と ../../examples/README.md へのリンクがある。"""
    pipes = read(ROOT / "docs" / "guide" / "pipes.md")
    vscode = read(ROOT / "docs" / "guide" / "vscode.md")
    for text in (pipes, vscode):
        assert "../../examples/README.md" in text
    for name in NAMES:
        assert f"`{name}`" in pipes or f"pipe-in-{name}" in pipes, f"pipes.md に見本 {name} がありません"
    assert re.search(r"^#{2,3} .*見本から作る", vscode, re.M), "vscode.md に「見本から作る」の節がありません"
    assert re.search(r"^#{2,3} .*見本", pipes, re.M), "pipes.md に見本の節がありません"
