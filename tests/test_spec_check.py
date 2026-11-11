"""要件定義・設計・決定の記録の ID のつながりを数える検査 `pipe_in/dev/spec_check.py` と、入口 `python -m pipe_in skill spec-check`（D0085）。

偽の 01・02 は文字列で組み立て、一時のフォルダで流す。SDK は呼ばない。リポジトリの docs/pipeline/ には書かない。
見本の受け入れ基準の ID は、本物の記録と取り違えないよう、番号の頭を定数から作る（tests/test_rules.py が、テストの中の ID を記録と突き合わせるため）。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pipe_in import cli
from pipe_in.dev import spec_check

FIRST_LINE = "UR {ur}・FR {fr}・NFR {nfr}・DS {ds}・AC {ac}"
PREFIX = "D0099-AC-"


def ac(n: int) -> str:
    return f"{PREFIX}{n:02d}"


def build01(*, answer: str = "いいえ", urs=("UR-01",), frs=("FR-01（UR-01）すること",), nfrs=("NFR-01（UR-01）",), acs=None, extra: str = "") -> str:
    """新しい形の 01。acs が None なら、FR-01 と NFR-01 を指す基準を2つ付ける。"""
    if acs is None:
        acs = [f"{ac(1)}（FR-01）1つめを確かめる", f"{ac(2)}（NFR-01）2つめを確かめる"]
    lines = ["# 要件定義 D0099 見本", "", "## 要求と前提", ""]
    lines += [f"- {u} 開発者として、何かしたい。" if u.startswith("UR-") else f"- {u}" for u in urs]
    lines += ["", "前提", "", "- 無し", "", "## 機能要件", ""]
    lines += [f"- {f}" for f in frs]
    lines += ["", "## 非機能要件", ""]
    if nfrs:
        for n in nfrs:
            lines += [f"- {n}", "  - きっかけ：流す。", "  - 状況：どこでも。", "  - 応答：返す。", "  - 測り方：数える。"]
    else:
        lines += ["- 無し"]
    lines += ["", "## 問い：状態を持ち、操作や出来事で移り変わるか", "", f"答え：{answer}", "理由：文書の形だけ。", ""]
    lines += ["## 受け入れ基準", ""]
    lines += [f"- {a}" for a in acs]
    if extra:
        lines += ["", extra]
    return "\n".join(lines) + "\n"


def kinds(report: spec_check.Report) -> set[str]:
    return {p.kind for p in report.problems}


def pairs(report: spec_check.Report) -> set[tuple[str, str]]:
    return {(p.kind, p.target) for p in report.problems}


# ---- D0085-AC-01 ----------------------------------------------------------------


def test_D0085_AC_01_つながった01は数を返し_問題0件_終了コード0():
    """D0085-AC-01: UR・FR・NFR・AC が全部つながった 01 は、数が返り、問題は 0 件、終了コードは 0。出力の1行目は数。"""
    report = spec_check.check(build01())
    assert list(report.counts) == ["UR", "FR", "NFR", "DS", "AC"]
    assert report.counts == {"UR": 1, "FR": 1, "NFR": 1, "DS": 0, "AC": 2}
    assert report.problems == ()
    assert report.legacy is False
    assert report.answer == "いいえ"
    assert spec_check.exit_code(report) == 0
    lines = spec_check.format_report(report)
    assert lines[0] == FIRST_LINE.format(ur=1, fr=1, nfr=1, ds=0, ac=2)
    assert lines[-1] == "問題 0 件"


def test_D0085_AC_01_入れ子の箇条書きと半角の括弧と区切りの違いも読む():
    """D0085-AC-01: 入れ子の `- ` も定義として読み、指し先は半角の括弧・`、`・`,` 区切りでもよい。"""
    text = build01(
        urs=("UR-01", "UR-02"),
        frs=("FR-01（UR-01）a", "  * FR-02(UR-02) b"),
        nfrs=("NFR-01（UR-01、UR-02）",),
        acs=[f"{ac(1)}(FR-01, FR-02)x", f"  - {ac(2)}（NFR-01）y"],
    )
    report = spec_check.check(text)
    assert report.counts == {"UR": 2, "FR": 2, "NFR": 1, "DS": 0, "AC": 2}
    assert report.problems == ()


# ---- D0085-AC-02 ----------------------------------------------------------------


@pytest.mark.parametrize("kind", ["FR", "NFR"])
@pytest.mark.parametrize("line_tail", ["", "（UR-77）", "（FR-01）"])
def test_D0085_AC_02_URを持たないFRと無いURを指す要件はつながらないとして出る(kind, line_tail):
    """D0085-AC-02: UR-xx を持たない FR・NFR、または 01 に無い UR（や UR 以外）を指す FR・NFR は「つながらない」として出て、終了コードは 1。"""
    new = f"{kind}-05{line_tail}"
    text = build01(
        frs=("FR-01（UR-01）すること", new) if kind == "FR" else ("FR-01（UR-01）すること",),
        nfrs=("NFR-01（UR-01）", new) if kind == "NFR" else ("NFR-01（UR-01）",),
        acs=[f"{ac(1)}（FR-01）a", f"{ac(2)}（NFR-01）b", f"{ac(3)}（{kind}-05）c"],
    )
    report = spec_check.check(text)
    assert pairs(report) == {("つながらない", f"{kind}-05")}
    assert spec_check.exit_code(report) == 1
    lines = spec_check.format_report(report)
    assert any(line.startswith(f"つながらない：{kind}-05") for line in lines)
    assert lines[-1].startswith("問題 1 件")


# ---- D0085-AC-03 ----------------------------------------------------------------


def test_D0085_AC_03_どの要件からも指されないURが出る():
    """D0085-AC-03: どの FR・NFR からも指されない UR は「指されない要求」として出て、終了コードは 1。"""
    text = build01(urs=("UR-01", "UR-02"))
    report = spec_check.check(text)
    assert pairs(report) == {("指されない要求", "UR-02")}
    assert spec_check.exit_code(report) == 1


# ---- D0085-AC-04 ----------------------------------------------------------------


@pytest.mark.parametrize(
    "tail,bad",
    [
        ("だけ書いて指し先なし", True),
        ("（FR-99）定義の無い FR を指す", True),
        ("（UR-01）UR を指す", True),
        (f"（{PREFIX}01）AC を指す", True),
        ("（画面）印だけで指し先なし", True),
        ("：（FR-01）ID の直後が「：」だと後ろの括弧は指し先ではない", True),
        ("（画面）（FR-01）印のあとに指し先が続く", False),
        ("（FR-01・NFR-01）2つを指す", False),
        (" (FR-01) 空白を挟んだ半角の括弧", False),
    ],
)
def test_D0085_AC_04_ACの指し先が無い_または定義の無いIDを指すと出る(tail, bad):
    """D0085-AC-04: AC の（…）が無い、または 01 に無い ID（や FR・NFR・DS 以外）を指すと「基準の指し先が違う」で出る。印（画面）だけの括弧は指し先に数えない。"""
    text = build01(acs=[f"{ac(1)}（FR-01）a", f"{ac(2)}（NFR-01）b", f"{ac(3)}{tail}"])
    report = spec_check.check(text)
    if bad:
        assert pairs(report) == {("基準の指し先が違う", ac(3))}
        assert spec_check.exit_code(report) == 1
    else:
        assert report.problems == ()
        assert spec_check.exit_code(report) == 0


# ---- D0085-AC-05 ----------------------------------------------------------------


def test_D0085_AC_05_基準の無い要件が出る_無しと書いたNFRは数えない():
    """D0085-AC-05: どの AC からも指されない FR・NFR は「基準の無い要件」で出る。「無し」と書いた NFR は数えない（NFR 0）。"""
    text = build01(
        frs=("FR-01（UR-01）a", "FR-02（UR-01）b"),
        nfrs=("NFR-01（UR-01）", "NFR-02（UR-01）"),
        acs=[f"{ac(1)}（FR-01）a", f"{ac(2)}（NFR-01）b"],
    )
    report = spec_check.check(text)
    assert pairs(report) == {("基準の無い要件", "FR-02"), ("基準の無い要件", "NFR-02")}
    assert spec_check.exit_code(report) == 1

    for none_nfr in ((), ("NFR-01 無し",), ("NFR-01 なし。",)):
        text = build01(nfrs=none_nfr, acs=[f"{ac(1)}（FR-01）a"])
        report = spec_check.check(text)
        assert report.counts["NFR"] == 0, none_nfr
        assert report.problems == (), none_nfr
        assert spec_check.exit_code(report) == 0


# ---- D0085-AC-06 ----------------------------------------------------------------


@pytest.mark.parametrize("dup", ["UR-01", "FR-01", "NFR-01", ac(1)])
def test_D0085_AC_06_同じIDの定義は重なりとして出る_欠番は問題にしない(dup):
    """D0085-AC-06: 同じ ID を2回定義すると「重なり」で出る。UR-01 と UR-03 だけで UR-02 が無い（欠番）は問題にしない。"""
    base = build01()
    again = {
        "UR-01": "- UR-01 もう一度。",
        "FR-01": "- FR-01（UR-01）もう一度。",
        "NFR-01": "- NFR-01（UR-01）もう一度。",
        ac(1): f"- {ac(1)}（FR-01）もう一度。",
    }[dup]
    report = spec_check.check(base + again + "\n")
    assert ("重なり", dup) in pairs(report)
    assert spec_check.exit_code(report) == 1


def test_D0085_AC_06_欠番は問題にしない():
    """D0085-AC-06: 番号が連続でなくても（欠番）、つながっていれば問題 0 件。"""
    text = build01(
        urs=("UR-01", "UR-03"),
        frs=("FR-01（UR-01）a", "FR-04（UR-03）b"),
        nfrs=("NFR-02（UR-01）",),
        acs=[f"{ac(1)}（FR-01）a", f"{ac(5)}（FR-04）b", f"{ac(9)}（NFR-02）c"],
    )
    report = spec_check.check(text)
    assert report.counts == {"UR": 2, "FR": 2, "NFR": 1, "DS": 0, "AC": 3}
    assert report.problems == ()


# ---- D0085-AC-07 ----------------------------------------------------------------

DS_TABLE = """## 状態遷移の表

| ID | 状態 | 出来事 | 次の状態 | 基準 |
| --- | --- | --- | --- | --- |
| DS-01 | 待ち | 開始 | 実行中 | {a1} |
| DS-02 | 待ち | 終了 | 起きない | {a2} |
"""


def ds_table(a1: str = "", a2: str = "") -> str:
    return DS_TABLE.format(a1=a1, a2=a2)


def test_D0085_AC_07_答えがはいで表が無い_いいえで表がある_を出し_はいで基準つきの表は通る():
    """D0085-AC-07: 答えが はい で DS の行が無い 02 は「状態遷移の表が無い」、いいえ なのに DS の行がある 02 は「いいえ なのに表がある」。はい で DS の行がすべて AC を持つなら問題 0 件。"""
    yes = build01(answer="はい", acs=[f"{ac(1)}（FR-01・DS-01）a", f"{ac(2)}（NFR-01・DS-02）b"])
    no_table = "# 設計\n\n状態：はい\n\n表は書いていない。\n"
    r = spec_check.check(yes, no_table)
    assert pairs(r) == {("状態遷移の表が無い", "")}
    assert spec_check.exit_code(r) == 1

    with_table = "# 設計\n\n" + ds_table(ac(1), ac(2))
    r = spec_check.check(yes, with_table)
    assert r.problems == ()
    assert r.counts["DS"] == 2
    assert spec_check.exit_code(r) == 0

    no = build01(answer="いいえ")
    r = spec_check.check(no, with_table)
    assert kinds(r) == {"いいえ なのに表がある"}
    assert spec_check.exit_code(r) == 1

    r = spec_check.check(no, "# 設計\n\n状態：いいえ\n")
    assert r.problems == ()


def test_D0085_AC_07_02が無ければDSの検査はしない_答えが無いと出る_答えの読み方():
    """D0085-AC-07: 02 が与えられない（design なし）ときは DS の検査をしない。UR があるのに `答え：` が無いと「答えが無い」。`答え:`（半角）も読み、最初の1行を使う。"""
    yes = build01(answer="はい", acs=[f"{ac(1)}（FR-01・DS-01）a", f"{ac(2)}（NFR-01）b"])
    r = spec_check.check(yes)
    assert r.problems == ()
    assert r.answer == "はい"

    lines = build01().splitlines()
    without = "\n".join(line for line in lines if not line.startswith("答え：")) + "\n"
    r = spec_check.check(without)
    assert r.answer is None
    assert [p.kind for p in r.problems] == ["答えが無い"]
    assert spec_check.exit_code(r) == 1

    half = build01().replace("答え：いいえ", "答え:はい。あとで直す") + "\n答え：いいえ\n"
    r = spec_check.check(half)
    assert r.answer == "はい"


def test_D0085_AC_07_決定の記録は1つの文書に両方を書く_check_recordは同じ文を01と02に渡す():
    """D0085-AC-07: check_record(text) は check(text, text) と同じ結果になる（決定の記録は 01 と 02 の内容が1つの文書にある）。"""
    text = build01(answer="はい", acs=[f"{ac(1)}（FR-01・DS-01）a", f"{ac(2)}（NFR-01・DS-02）b"]) + "\n" + ds_table(ac(1), ac(2))
    assert spec_check.check_record(text) == spec_check.check(text, text)
    assert spec_check.check_record(text).problems == ()
    assert spec_check.check_record(text).counts["DS"] == 2


# ---- D0085-AC-08 ----------------------------------------------------------------


def test_D0085_AC_08_基準の無いマスを件数とDSのIDで出す_起きないマスも数える():
    """D0085-AC-08: DS の行に AC が無く、どの AC の（…）もその DS を指さないと「基準の無いマス」で数える（件数と DS の ID が出る）。「起きない」のマスも同じに数える。"""
    table = "\n".join(
        [
            "| ID | 状態 | 出来事 | 次の状態 | 基準 |",
            "| --- | --- | --- | --- | --- |",
            f"| DS-01 | 待ち | 開始 | 実行中 | {ac(1)} |",
            "| DS-02 | 待ち | 終了 | 待ち | |",
            "| DS-03 | 実行中 | 開始 | 起きない | |",
            "| DS-04 | 実行中 | 終了 | 待ち | |",
            "| DS-05 | 待ち | 中止 | 起きない | |",
            "｜ DS-06 ｜ 全角の縦線は表の行ではない ｜",
            "",
        ]
    )
    yes = build01(answer="はい", acs=[f"{ac(1)}（FR-01・DS-01）a", f"{ac(2)}（NFR-01・DS-02）b", f"{ac(3)}（DS-04）c"])
    report = spec_check.check(yes, "# 設計\n\n" + table)
    assert report.counts["DS"] == 5
    assert pairs(report) == {("基準の無いマス", "DS-03"), ("基準の無いマス", "DS-05")}
    assert spec_check.exit_code(report) == 1
    lines = spec_check.format_report(report)
    assert lines[0] == FIRST_LINE.format(ur=1, fr=1, nfr=1, ds=5, ac=3)
    assert lines[-1].startswith("問題 2 件")
    assert "基準の無いマス 2" in lines[-1]
    assert any(line.startswith("基準の無いマス：DS-03") for line in lines)


def test_D0085_AC_08_表の行に書いたACが01に無いと指し先が違うとして出る():
    """D0085-AC-08: DS の行に書いた AC が 01 に無いときは、DS の行の指し先が違うとして出る（基準の指し先が違う）。"""
    yes = build01(answer="はい", acs=[f"{ac(1)}（FR-01）a", f"{ac(2)}（NFR-01）b"])
    table = "| ID | 基準 |\n| --- | --- |\n" + f"| DS-01 | {ac(77)} |\n"
    report = spec_check.check(yes, table)
    assert ("基準の指し先が違う", ac(77)) in pairs(report)
    assert spec_check.exit_code(report) == 1


# ---- D0085-AC-09 ----------------------------------------------------------------


def test_D0085_AC_09_小さな直しの01は問題0件_終了コード0():
    """D0085-AC-09: 小さな直し（UR 1・前提「無し」・NFR「無し」・答え いいえ・FR 2・AC 2）の 01 は、問題 0 件・終了コード 0。02 は状態：いいえ の1行でもよい。"""
    text = build01(
        frs=("FR-01（UR-01）a", "FR-02（UR-01）b"),
        nfrs=(),
        acs=[f"{ac(1)}（FR-01）a", f"{ac(2)}（FR-02）b"],
    )
    for design in (None, "# 設計\n\n状態：いいえ\n"):
        report = spec_check.check(text, design)
        assert report.counts == {"UR": 1, "FR": 2, "NFR": 0, "DS": 0, "AC": 2}
        assert report.problems == ()
        assert report.legacy is False
        assert spec_check.exit_code(report) == 0
        assert spec_check.format_report(report)[0] == FIRST_LINE.format(ur=1, fr=2, nfr=0, ds=0, ac=2)


# ---- D0085-AC-10 ----------------------------------------------------------------


def snapshot(root: Path) -> dict[str, tuple[bytes, int]]:
    return {p.relative_to(root).as_posix(): (p.read_bytes(), p.stat().st_mtime_ns) for p in sorted(root.rglob("*")) if p.is_file()}


@pytest.fixture
def work(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "proj"
    (root / "docs" / "pipeline").mkdir(parents=True)
    monkeypatch.chdir(root)
    return root


def put(work: Path, name: str, text: str) -> None:
    (work / "docs" / "pipeline" / name).write_text(text, encoding="utf-8")


def test_D0085_AC_10_skill_spec_checkは今のフォルダの01と02を読み_書かない(work, capsys):
    """D0085-AC-10: skill spec-check は、今のフォルダの docs/pipeline/01_requirements.md と 02_design.md を読んで結果を出し、ファイルを変えない。問題があれば終了コード 1。"""
    put(work, "01_requirements.md", build01(answer="はい", acs=[f"{ac(1)}（FR-01・DS-01）a", f"{ac(2)}（NFR-01・DS-02）b"]))
    put(work, "02_design.md", "# 設計\n\n" + ds_table(ac(1), ac(2)))
    before = snapshot(work)
    assert cli.main(["skill", "spec-check"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0] == FIRST_LINE.format(ur=1, fr=1, nfr=1, ds=2, ac=2)
    assert out[-1] == "問題 0 件"
    assert snapshot(work) == before

    put(work, "01_requirements.md", build01(urs=("UR-01", "UR-02")))
    put(work, "02_design.md", "# 設計\n\n状態：いいえ\n")
    before = snapshot(work)
    assert cli.main(["skill", "spec-check"]) == 1
    out = capsys.readouterr().out
    assert "指されない要求：UR-02" in out
    assert snapshot(work) == before


def test_D0085_AC_10_02が無ければ01だけ_01が無ければ案内と終了コード1(work, capsys):
    """D0085-AC-10: 02 が無いときは 01 だけを検査する。01 が無いときは終了コード 1 と案内の文を出し、何も作らない。"""
    put(work, "01_requirements.md", build01(answer="はい", acs=[f"{ac(1)}（FR-01・DS-01）a", f"{ac(2)}（NFR-01）b"]))
    assert cli.main(["skill", "spec-check"]) == 0
    assert capsys.readouterr().out.splitlines()[0] == FIRST_LINE.format(ur=1, fr=1, nfr=1, ds=0, ac=2)

    (work / "docs" / "pipeline" / "01_requirements.md").unlink()
    before = snapshot(work)
    assert cli.main(["skill", "spec-check"]) == 1
    captured = capsys.readouterr()
    assert "01" in captured.out + captured.err
    assert snapshot(work) == before


@pytest.mark.parametrize(
    "argv",
    [
        ["--project", ".."],
        ["--proj=.."],
        ["--input", "memo.md"],
        ["--config", "other.toml"],
        ["extra.md"],
    ],
)
def test_D0085_AC_10_旗と引数を断る(work, argv):
    """D0085-AC-10: spec-check は旗も引数も取らない。--project・--input・--config・位置引数は、元のコマンドが無いための断りではなく spec-check 自身の断りで止まり、何も書かない。"""
    put(work, "01_requirements.md", build01())
    before = snapshot(work)
    with pytest.raises(SystemExit) as raised:
        cli.main(["skill", "spec-check", *argv])
    message = str(raised.value)
    assert message.startswith("pipe-in skill")
    assert "後ろに" not in message, "skill の入口が spec-check を知らないための断り（まだ登録されていない）"
    assert snapshot(work) == before


# ---- D0085-AC-11 ----------------------------------------------------------------


def test_D0085_AC_11_URの無い前の形の01は鎖を検査せず終了コード0(work, capsys):
    """D0085-AC-11: UR が1つも無い 01（前の形）は、数だけ出し「前の形のため、鎖は検査しない」と添えて、終了コード 0。FR や AC に指し先が無くてもエラーにしない。"""
    old = "\n".join(
        [
            "# 要件定義 D0099 古い形",
            "",
            "- FR-01 すること",
            "- FR-02 もう1つ",
            f"- {ac(1)} 指し先の無い基準",
            "",
        ]
    )
    report = spec_check.check(old)
    assert report.legacy is True
    assert report.counts == {"UR": 0, "FR": 2, "NFR": 0, "DS": 0, "AC": 1}
    assert report.problems == ()
    assert spec_check.exit_code(report) == 0
    lines = spec_check.format_report(report)
    assert lines[0] == FIRST_LINE.format(ur=0, fr=2, nfr=0, ds=0, ac=1)
    assert lines[1] == "前の形のため、鎖は検査しない"

    put(work, "01_requirements.md", old)
    assert cli.main(["skill", "spec-check"]) == 0
    assert "前の形のため、鎖は検査しない" in capsys.readouterr().out


def test_D0085_AC_11_DSも答えも無い02は検査しない():
    """D0085-AC-11: DS の行も `答え：` の行も無い 02 は、前の形の 01 と一緒なら DS の検査をしない。コードの囲みの中の ID は読まない。"""
    old = "- FR-01 すること\n"
    assert spec_check.check(old, "# 設計\n\n古い書き方の設計。\n").problems == ()
    assert spec_check.exit_code(spec_check.check(old, "# 設計\n")) == 0

    fenced = "```\n- UR-01 囲みの中\n- FR-01（UR-01）囲みの中\n```\n\n- FR-02 外\n"
    report = spec_check.check(fenced)
    assert report.legacy is True
    assert report.counts["UR"] == 0
    assert report.counts["FR"] == 1

    table_in_fence = build01(answer="いいえ") + "\n```\n| DS-01 | 囲みの中 | |\n```\n"
    assert spec_check.check(table_in_fence, table_in_fence).counts["DS"] == 0
