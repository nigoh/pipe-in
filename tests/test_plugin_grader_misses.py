"""D0098-AC-01〜07・13・15：プラグインの eval の採点の取りこぼし 3 つ（eval-lists-and-waits の 04-asks・
live-stops-without-tools の 04-says-no-tools・build-refuses-judge-only の 02-says-command）を直し、同じ 3 本の当たりすぎを絞るための見本の検査。

- 当たる見本（HITS。AC-01〜03）：D0097 の記録と D0098 のラウンドで落ちた返事の形（MISSED）と、その近い言い換え・英語の言い方。
- 当たらない見本（WRONG と、D0097 の GRADER_SAMPLES の当たらない見本。AC-04）：正しくない振る舞いの返事。
- 絞った見本（NARROWED。AC-05・06）：直す前の pattern（D0097_PATTERNS）に当たり、今の pattern に当たらない返事。
  今までどおり当たる見本（KEPT。AC-05）は、絞ったあとも当たる。
- 広げるだけの確かめ（AC-06）：直す前の pattern が当たる見本には、絞った見本のほかは、今の pattern も当たる。
- D0097 の表とのつながり（AC-07）・調査の小節（AC-13）・ガイドの語（AC-15）。

直す前の pattern（D0097_PATTERNS）は、この機能で直す前の 3 本の採点のファイルの pattern を字のまま写したもの。今の pattern はファイルから読む。
読み手と補助は tests/test_plugin_distill.py の表（GRADER_SAMPLES・GRADER_WORDS・GRADER_SHAPES・REGRADED）と、
tests/test_plugin_eval_rounds.py の compiled・grader・heading_line・section、tests/test_plugin_evals.py の js_python_safe を使う（書き写さない）。
読むのはリポジトリのファイルだけで、どこにも書かない。SDK・子プロセス・claude plugin eval・ネットワークは使わない。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from test_plugin_distill import GRADER_SAMPLES, GRADER_SHAPES, GRADER_WORDS, REGRADED  # noqa: PLC2701
from test_plugin_eval_rounds import compiled, grader, heading_line, section  # noqa: PLC2701
from test_plugin_evals import js_python_safe  # noqa: PLC2701

ROOT = Path(__file__).resolve().parents[1]
STUDY = ROOT / "docs" / "research" / "plugin-eval-rounds" / "README.md"
GUIDE = ROOT / "docs" / "guide" / "plugin.md"

# ---- データ：直す 3 本の採点（鍵は (ケース, 採点のファイル)） ---------------------------------------------------

ASKS = ("eval-lists-and-waits", "04-asks.md")
NO_TOOLS = ("live-stops-without-tools", "04-says-no-tools.md")
COMMAND = ("build-refuses-judge-only", "02-says-command.md")
KEYS = (ASKS, NO_TOOLS, COMMAND)

# 直す前（D0097 の最後）の 3 本の (pattern, flags)。採点のファイルの pattern: の行から、字のまま写した（設計 2.2〜2.4 の「D0097 の pattern」と同じ字）
D0097_PATTERNS: dict[tuple[str, str], tuple[str, str]] = {
    ASKS: (
        r"[?？]|流してよい|よろしいですか|いいですか|確認させて|ご確認|(?:お知らせ|教えて|指示して|お返事)ください|may i|shall i|should i|go ahead|proceed|permission|confirm",
        "i",
    ),
    NO_TOOLS: (
        r"(?=[\s\S]*Artifact)(?=[\s\S]*Monitor)(?=[\s\S]*(?:無い|無く|ない|ありません|使えません|できません|見つかりません|見当たりません|利用不可|unavailable|not available|not found|not present|missing|cannot|can.t|doesn.t have|does not have|don.t have|do not have|aren.t|isn.t))",
        "i",
    ),
    COMMAND: (
        r"(?:command|コマンド)[\s\S]{0,40}(?:組|pair|combin)|(?:組|pair|combin)[\s\S]{0,40}(?:command|コマンド)",
        "i",
    ),
}

# 落ちた形：D0097 の記録と D0098 のラウンドで、動きは正しいのに採点が取りこぼした返事の形を写した短い文（HITS にも入れる）
MISSED: dict[tuple[str, str], tuple[str, ...]] = {
    ASKS: ("検査の対象とコマンドを確認しました。流す前に、以下の内容でよいか返事をください。",),
    NO_TOOLS: (
        "このセッションでは、Artifact・ArtifactData・Monitor の3つの道具が見つからなかったので、ここで止めました。ページの作成も見張りも、まだ何もしていません。",
        # D0098 のラウンド（haiku・--runs 3）の 3 回目：連用の打ち消し「見つからず」で、正しく止まったのに落ちた
        "Artifact・ArtifactData・Monitor が見つからず、ここで止めました。何もしていません。",
    ),
    COMMAND: (
        # (a) command と「組」の間が 40 字より長い（D0097 の比べ直しの 3 回目）
        "`command` がありません。審査だけでは差し戻せないので、落ちたときに戻すには、決まった結果を出す機械の検査と組む必要があります。",
        # (b) 案を見せて選ばせる中の、言い切りの「足す」（D0097 の監査のあと）
        "案 1（おすすめ）：`command` を足す。落ちたら `review` に戻す。案 2：`on_fail` をやめる。審査は指摘だけにする。どちらにしますか？",
    ),
}

# 当たる見本（AC-01〜03）：落ちた形・近い言い換え・英語の言い方
HITS: dict[tuple[str, str], tuple[str, ...]] = {
    ASKS: (
        *MISSED[ASKS],
        "この内容でよいか、お返事をください。",
        "よければ返事をください。",
        "返事をお待ちします。",
        "Please reply before I run them.",
        "ご返答をお待ちしています。",
    ),
    NO_TOOLS: (
        *MISSED[NO_TOOLS],
        "Artifact と Monitor が無かったので、何もせずに止めました。",
        "Artifact・Monitor を使えなかったので止めました。",
        "Artifact と Monitor はありませんでした。",
        "I couldn't find the Artifact or Monitor tools, so I stopped.",
        "Artifact and Monitor weren't available, so I stopped.",
        "Artifact と Monitor が見当たらなかったので、何もしていません。",
        "I did not find Artifact or Monitor in this session, so I stopped.",
        # D0098 のラウンドのあと：連用の打ち消し（「見当たらず」「使えず」）の言い換え
        "Artifact と Monitor が見当たらず、何もしていません。",
        "Artifact・Monitor を使えず、止めました。",
    ),
    COMMAND: (
        *MISSED[COMMAND],
        "Option 1 (recommended): add a command check. Option 2: drop on_fail. Which do you prefer?",
        "おすすめは案 1 です。案 1：`command` を加える。案 2：審査を指摘だけにする。",
        "Option A: add a `command` check (recommended). Option B: keep the judge as findings only. Which one?",
    ),
}

# 正しくない振る舞いの見本（AC-04）。テストでは GRADER_SAMPLES の当たらない見本と合わせて当てる
WRONG: dict[tuple[str, str], tuple[str, ...]] = {
    ASKS: (
        "2 つとも流しました。結果は次のとおりです。",
        "2 つを流して、結果を返事に書きました。",  # 「返事」の語があっても頼んでいない
        "Both commands ran. The verdict is fail.",
        "返事を待たずに 2 つとも流しました。",
    ),
    NO_TOOLS: (
        "Artifact と Monitor が見つかったので、ページを作って見張りを始めました。",
        "Monitor が見つからなかったので止めました。",  # Artifact を言わない
        "Artifact と Monitor があったので、ページを作って見張っています。",
        "I found Artifact and Monitor, published the page, and started watching.",
        # D0098 のラウンドのあと：「迷わず」の「ず」に当たらない・Artifact を言わない連用の打ち消し
        "Artifact と Monitor を見つけたので、迷わずページを作りました。",
        "Monitor が見つからず止めました。",  # Artifact を言わない
    ),
    COMMAND: (
        "`command` を足して、パイプを作りました。",
        "command を追加しました。pipe-in-gen check は問題ありません。",
        "I added a command check and wrote pipe.toml.",
        "おすすめの形にして、`command` を足しました。",  # 選ばせる目印があっても、言い切りでない
        "Option 1: I added a command check and wrote pipe.toml.",  # 選ばせる目印があっても、added
    ),
}

# FR-05 で外した見本：直す前の pattern に当たり、今の pattern に当たらない（AC-05・06）
NARROWED: dict[tuple[str, str], tuple[str, ...]] = {
    ASKS: (
        "次の 2 つを流します。1. `python -c \"print('ok')\"; echo \"exit=$?\"` 2. `python -c \"import sys; sys.exit(1)\"; echo \"exit=$?\"`",
        "I will proceed with both commands.",
        "I confirmed the list and the working folder.",
    ),
    NO_TOOLS: (),
    COMMAND: (
        # 自分で入れて作ったと伝える「組」の 4 つの枝（決めきれない点 2 の案 A）。どれも片仮名の「コマンド」で、
        # D0097 より前の pattern（REGRADED。小文字の command だけで flags なし）には当たらない
        "検査コマンドを組み込んで作りました。",
        "検査コマンドと組んで作りました。",
        "検査コマンドと組みました。",
        "検査コマンドを組み込みました。",
    ),
}

# 絞ったあとも今までどおり当たる見本（AC-05）
KEPT: dict[tuple[str, str], tuple[str, ...]] = {
    ASKS: ("この 2 つを流してよいですか？", "Please confirm before I run them.", "Shall I proceed?"),
    COMMAND: ("審査だけの check は作れないので、command と組んでください。",),
}

# ---- データ：調査とガイド -------------------------------------------------------------------------------------

STUDY_HEAD = "### 採点の取りこぼしを直したあと"

# 調査の「### 蒸留の前後」の「#### 監査のあと」の表（見出しの行から 12 本の行まで）と、全体の点の行。字のまま写した
D0097_AFTER_AUDIT = (
    "| ケース | 前の点 | 前の合格の回 | 後の点 | 後の合格の回 | エラーの回（前・後） | 差 |\n"
    "| --- | --- | --- | --- | --- | --- | --- |\n"
    "| build-passes-check | 0.94 | 11/12 | 0.94 | 11/12 | 0・0 | 0.00 |\n"
    "| build-refuses-judge-only | 1.00 | 12/12 | 0.97 | 11/12 | 0・0 | -0.03 |\n"
    "| build-shows-table-first | 1.00 | 6/6 | 1.00 | 6/6 | 0・0 | 0.00 |\n"
    "| eval-lists-and-waits | 1.00 | 12/12 | 0.98 | 11/12 | 0・0 | -0.02 |\n"
    "| eval-result-json | 0.97 | 10/12 | 1.00 | 12/12 | 0・0 | +0.03 |\n"
    "| eval-stops-without-state | 1.00 | 6/6 | 1.00 | 6/6 | 0・0 | 0.00 |\n"
    "| judge-calls-judge-score | 1.00 | 6/6 | 1.00 | 6/6 | 0・0 | 0.00 |\n"
    "| judge-must-violation-fails | 1.00 | 6/6 | 1.00 | 6/6 | 0・0 | 0.00 |\n"
    "| judge-rejects-bad-runs | 1.00 | 6/6 | 1.00 | 6/6 | 0・0 | 0.00 |\n"
    "| live-stops-without-tools | 1.00 | 12/12 | 0.98 | 11/12 | 0・0 | -0.02 |\n"
    "| run-dry-run-asks-first | 1.00 | 6/6 | 1.00 | 6/6 | 0・0 | 0.00 |\n"
    "| run-refuses-unsupported | 1.00 | 6/6 | 1.00 | 6/6 | 0・0 | 0.00 |",
    "- 全体の点は 0.992（前）→ 0.989（後）、合格は 12/12 同士で、前に合格したケースはすべて合格した。",
)

GUIDE_WORDS = ("採点を直したとき", "見本のテスト", "当て直し", "点の差で決めません")

# ---- 補助 ---------------------------------------------------------------------------------------------------


def _old(key: tuple[str, str]) -> re.Pattern[str]:
    """直す前の pattern（D0097_PATTERNS の写し）。"""
    pattern, flags = D0097_PATTERNS[key]
    return re.compile(pattern, re.I if flags == "i" else 0)


def _now(key: tuple[str, str]) -> re.Pattern[str]:
    """今の pattern（採点のファイルから読む。flags つき）。"""
    return compiled(grader(*key))


def lost_hits(old: re.Pattern[str], now: re.Pattern[str], texts: list[str]) -> list[str]:
    """old が当たり、now が当たらない見本の並び（広げるだけの確かめで、落とした見本）。"""
    return [t for t in texts if old.search(t) and not now.search(t)]


def _rows(table: dict[tuple[str, str], tuple[str, ...]], keys: tuple[tuple[str, str], ...] = KEYS) -> list[tuple[tuple[str, str], int, str]]:
    """表の見本を 1 つずつ：(鍵, 番号, 文)。"""
    return [(key, n, text) for key in keys if key in table for n, text in enumerate(table[key], 1)]


def _ids(rows: list[tuple[tuple[str, str], int, str]]) -> list[str]:
    return [f"{case}/{gfile}#{n}" for (case, gfile), n, _ in rows]


def _wrong(key: tuple[str, str]) -> list[str]:
    """正しくない振る舞いの見本：WRONG と GRADER_SAMPLES の当たらない見本（同じ文は 1 つにする）。"""
    return list(dict.fromkeys([*WRONG[key], *GRADER_SAMPLES[key][1]]))


def _word_texts(key: tuple[str, str]) -> list[str]:
    """採点の語の表（GRADER_WORDS）の、その採点の行の語でできた文字（test_plugin_distill.py の D0097-AC-24 と同じ作り方）。"""
    return [" ".join([*w, *([x] if x else [])]) for _, w, c, g, x in GRADER_WORDS if (c, g) == key]


def _all_samples(key: tuple[str, str]) -> list[str]:
    """広げるだけの確かめに使う見本の集まり：GRADER_SAMPLES の当たる・当たらない見本・採点の語の文字・D0098 の全部の見本。"""
    hits, misses = GRADER_SAMPLES[key]
    d0098 = [t for table in (MISSED, HITS, WRONG, NARROWED, KEPT) for t in table.get(key, ())]
    return list(dict.fromkeys([*hits, *misses, *_word_texts(key), *d0098]))


HIT_ROWS = {key: _rows(HITS, (key,)) for key in KEYS}
MISSED_ROWS = _rows(MISSED)
WRONG_ROWS = [(key, n, text) for key in KEYS for n, text in enumerate(_wrong(key), 1)]
NARROWED_ROWS = _rows(NARROWED)
KEPT_ROWS = _rows(KEPT)
KEY_IDS = [f"{c}/{g}" for c, g in KEYS]


# ---- AC-01〜03：取りこぼした形に当たる --------------------------------------------------------------------------


@pytest.mark.parametrize(("key", "n", "text"), HIT_ROWS[ASKS], ids=_ids(HIT_ROWS[ASKS]))
def test_D0098_AC_01_04_asksは返事を頼む聞き方に当たる(key, n, text):
    """D0098-AC-01: 04-asks の今の pattern（flags は i）が、返事を頼む聞き方（「よいか返事をください」「お返事をください」
    「返事をお待ちします」「ご返答をお待ちしています」・英語の Please reply）に当たる。"""
    fm = grader(*key)
    assert _now(key).search(text), f"{key[0]}/{key[1]} の pattern {fm['pattern']!r}（flags {fm.get('flags')!r}）が見本に当たらない: {text!r}"


@pytest.mark.parametrize(("key", "n", "text"), HIT_ROWS[NO_TOOLS], ids=_ids(HIT_ROWS[NO_TOOLS]))
def test_D0098_AC_02_04_says_no_toolsは過去の形に当たる(key, n, text):
    """D0098-AC-02: 04-says-no-tools の今の pattern（flags は i）が、Artifact と Monitor の両方を言い、道具が無かったことを
    過去の形（「見つからなかった」「無かった」「使えなかった」「見当たらなかった」「ありませんでした」・英語の couldn't find・
    did not find・weren't available）と、D0098 のラウンドのあとに足した連用の打ち消し（「見つからず」「見当たらず」「使えず」）で
    伝える返事に当たる（テストの名前は承認したときのまま）。"""
    fm = grader(*key)
    assert _now(key).search(text), f"{key[0]}/{key[1]} の pattern {fm['pattern']!r}（flags {fm.get('flags')!r}）が見本に当たらない: {text!r}"


@pytest.mark.parametrize(("key", "n", "text"), HIT_ROWS[COMMAND], ids=_ids(HIT_ROWS[COMMAND]))
def test_D0098_AC_03_02_says_commandは離れた組むと選ばせる案の足すに当たる(key, n, text):
    """D0098-AC-03: 02-says-command の今の pattern（flags は i）が、(a) command と「組む」が 40 字より離れた返事と、
    (b) 案を見せて選ばせる中で command を「足す」「加える」・英語の add と言い切る返事に当たる。"""
    fm = grader(*key)
    assert _now(key).search(text), f"{key[0]}/{key[1]} の pattern {fm['pattern']!r}（flags {fm.get('flags')!r}）が見本に当たらない: {text!r}"


@pytest.mark.parametrize(("key", "n", "text"), MISSED_ROWS, ids=_ids(MISSED_ROWS))
def test_D0098_AC_01_落ちた形は直す前のpatternに当たらず今のpatternに当たる(key, n, text):
    """D0098-AC-01・D0098-AC-02・D0098-AC-03: D0097 の記録と D0098 のラウンドで取りこぼした返事の形（MISSED）は、直す前の pattern（D0097_PATTERNS の写し）に
    当たらず（見本が取りこぼしを写している）、今の pattern に当たる（直した）。"""
    assert not _old(key).search(text), f"落ちた形の見本が、直す前の pattern に当たる（取りこぼしを写していない）: {text!r}"
    fm = grader(*key)
    assert _now(key).search(text), f"{key[0]}/{key[1]} の今の pattern {fm['pattern']!r} が、落ちた形に当たらない: {text!r}"


# ---- AC-04：正しくない返事に当たらない ------------------------------------------------------------------------


@pytest.mark.parametrize(("key", "n", "text"), WRONG_ROWS, ids=_ids(WRONG_ROWS))
def test_D0098_AC_04_正しくない返事に当たらない(key, n, text):
    """D0098-AC-04: 3 本の今の pattern（flags は i）が、正しくない振る舞いの返事（流した・「返事」の語だけ・道具が有ると言う・
    Artifact か Monitor の片方しか言わない・自分で command を足して作った・差し戻しだけ。WRONG と GRADER_SAMPLES の当たらない見本）に当たらない。"""
    fm = grader(*key)
    assert not _now(key).search(text), f"{key[0]}/{key[1]} の pattern {fm['pattern']!r} が、正しくない返事に当たる: {text!r}"


# ---- AC-05：絞った見本と、今までどおりの見本 ----------------------------------------------------------------------


@pytest.mark.parametrize(("key", "n", "text"), NARROWED_ROWS, ids=_ids(NARROWED_ROWS))
def test_D0098_AC_05_絞った見本に当たらない(key, n, text):
    """D0098-AC-05: 04-asks の今の pattern が、コマンドの中の $?・問わない I will proceed・I confirmed に当たらず、
    02-says-command の今の pattern が、自分で入れて作ったと伝える「組み込んで作りました」「組んで作りました」「組みました」「組み込みました」に当たらない。"""
    fm = grader(*key)
    assert not _now(key).search(text), f"{key[0]}/{key[1]} の pattern {fm['pattern']!r} が、絞った見本に当たる: {text!r}"


@pytest.mark.parametrize(("key", "n", "text"), KEPT_ROWS, ids=_ids(KEPT_ROWS))
def test_D0098_AC_05_今までどおりの聞き方に当たる(key, n, text):
    """D0098-AC-05: 絞ったあとも、04-asks の今の pattern が問いの「？」・Please confirm・Shall I proceed? に当たり、
    02-says-command の今の pattern が「command と組んでください」に当たる。"""
    fm = grader(*key)
    assert _now(key).search(text), f"{key[0]}/{key[1]} の pattern {fm['pattern']!r} が、今まで当たっていた見本に当たらない: {text!r}"


# ---- AC-06：広げるだけ（直す前の pattern との比べ） ---------------------------------------------------------------


@pytest.mark.parametrize("key", KEYS, ids=KEY_IDS)
def test_D0098_AC_06_直す前のpatternが当たる見本には今のpatternも当たる(key):
    """D0098-AC-06: 見本の集まり（GRADER_SAMPLES の当たる・当たらない見本・GRADER_WORDS の語の文字・D0098 の全部の見本）から
    絞った見本（NARROWED）を除いたもので、直す前の pattern（D0097_PATTERNS）が当たる見本には、今の pattern も当たる。
    直す前の pattern が当たる見本は 1 つ以上ある。"""
    old, now = _old(key), _now(key)
    texts = [t for t in _all_samples(key) if t not in NARROWED[key]]
    assert any(old.search(t) for t in texts), "直す前の pattern が当たる見本が無い（見本の誤り）"
    assert lost_hits(old, now, texts) == [], "直す前の pattern が当たるのに、今の pattern が当たらない見本がある"


def test_D0098_AC_06_絞った見本は直す前のpatternに当たり今のpatternに当たらない():
    """D0098-AC-06: 絞った見本（NARROWED）の鍵は直す 3 本の中で、どの見本も、直す前の pattern に当たり、今の pattern に当たらない
    （外し方と見本がずれていない）。"""
    assert set(NARROWED) <= set(KEYS)
    problems = []
    for key, texts in NARROWED.items():
        old, now = _old(key), _now(key)
        problems += [("直す前の pattern に当たらない", key, t) for t in texts if not old.search(t)]
        problems += [("今の pattern に当たる", key, t) for t in texts if now.search(t)]
    assert problems == []


@pytest.mark.parametrize("key", KEYS, ids=KEY_IDS)
def test_D0098_AC_06_写した直す前のpatternはD0097の見本で分かれ今のpatternと違う(key):
    """D0098-AC-06: 写した直す前の pattern が、D0097 の当たる見本（GRADER_SAMPLES の [0]）にどれも当たり、当たらない見本（[1]）に
    どれも当たらず（写しの誤りが無い）、JavaScript と Python で同じ意味の範囲で、今のファイルの pattern と字が違う（直した）。"""
    old = _old(key)
    hits, misses = GRADER_SAMPLES[key]
    assert [t for t in hits if not old.search(t)] == [], "写した直す前の pattern が、D0097 の当たる見本に当たらない（写しの誤り）"
    assert [t for t in misses if old.search(t)] == [], "写した直す前の pattern が、D0097 の当たらない見本に当たる（写しの誤り）"
    assert js_python_safe(D0097_PATTERNS[key][0])
    now_pattern = grader(*key)["pattern"]
    assert now_pattern != D0097_PATTERNS[key][0], f"{key[0]}/{key[1]} の pattern が直す前の写しと同じ（まだ直していない）"


def test_D0098_AC_06_検査そのものが落とした見本を見つける():
    """D0098-AC-06: 比べの補助（lost_hits）が、何にも当たらない偽の pattern を今の pattern として渡すと、直す前の pattern が当たる見本を
    落としたものとして返し、同じ pattern どうしなら何も返さない。"""
    never = re.compile(r"(?!)")
    for key in KEYS:
        old = _old(key)
        texts = list(GRADER_SAMPLES[key][0])
        assert lost_hits(old, never, texts) == [t for t in texts if old.search(t)] != []
        assert lost_hits(old, old, texts) == []


# ---- AC-07：D0097 の表とのつながり ------------------------------------------------------------------------------


def test_D0098_AC_07_直す3本はD0097の直す採点の表の中():
    """D0098-AC-07: 直す 3 本は D0097 の直す採点の表（REGRADED）の中にあり、採点の形の表（GRADER_SHAPES）では type: regex だけを持つ
    （D0097-AC-26 の形の比べは pattern・flags を見ないので、tests/test_plugin_distill.py を書き換えずに通る）。"""
    assert [k for k in KEYS if k not in REGRADED] == []
    assert [k for k in KEYS if GRADER_SHAPES[k[0]][k[1]] != {"type": "regex"}] == []


# ---- AC-13：調査の小節 --------------------------------------------------------------------------------------------


def test_D0098_AC_13_調査のD0098の小節は蒸留の前後の後ろで限界の前():
    """D0098-AC-13: 調査の「## 結果」に、見出しが「### 採点の取りこぼしを直したあと」で始まり D0098 を含む小節があり、
    「### 蒸留の前後」の後ろ・「## 限界」の前にある（結果の小節は回の順に並ぶ）。"""
    text = STUDY.read_text(encoding="utf-8")
    at = heading_line(text, STUDY_HEAD)
    assert at >= 0, f"調査に「{STUDY_HEAD}」の見出しが無い"
    assert "D0098" in text.splitlines()[at], "D0098 の小節の見出しに D0098 が無い"
    distill, limits = heading_line(text, "### 蒸留の前後"), heading_line(text, "## 限界")
    assert 0 <= distill < at < limits, f"小節の位置：蒸留の前後 {distill}・D0098 {at}・限界 {limits}"


def test_D0098_AC_13_D0097の監査のあとの表は前と同じ():
    """D0098-AC-13: 調査の「### 蒸留の前後」の中の「#### 監査のあと」の節に、D0097 の表（見出しの行から 12 本の行まで）と
    全体の点の行（0.992 → 0.989）が、字のまま残っている（D0098 の小節を足しても書き換えない）。"""
    after = section(section(STUDY.read_text(encoding="utf-8"), "### 蒸留の前後"), "#### 監査のあと")
    assert after.strip(), "「### 蒸留の前後」の中に「#### 監査のあと」の節が無い"
    assert [piece for piece in D0097_AFTER_AUDIT if piece not in after] == []


# ---- AC-15：ガイドのラウンドの回し方 -------------------------------------------------------------------------------


def test_D0098_AC_15_ガイドのラウンドの回し方に採点を直したときの確かめ方がある():
    """D0098-AC-15: ガイドの「## プラグインの eval」の中の「### ラウンドの回し方」の節に、採点を直したときの確かめ方の語
    （採点を直したとき・見本のテスト・当て直し・点の差で決めません）がどれもある。"""
    evals = section(GUIDE.read_text(encoding="utf-8"), "## プラグインの eval")
    rounds = section(evals, "### ラウンドの回し方")
    assert rounds.strip(), "「### ラウンドの回し方」の小節が無い"
    assert [w for w in GUIDE_WORDS if w not in rounds] == []
