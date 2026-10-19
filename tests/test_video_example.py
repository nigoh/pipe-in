"""動画を作るパイプの見本（examples/video/）の検査。SDK は呼ばない。

見本の中身は読むだけで、書くのは tmp_path の中だけ。
指示文は文の一致ではなく、「入っているべき短い語」が全部あるかだけを見る（言い回しは変えてよい）。
"""

from __future__ import annotations

import ast
import re
import shutil
import sys
import tomllib
from pathlib import Path

import pytest

from pipe_in.engine.pipeline import run_shell
from pipe_in.pipe.definition import (
    LEGACY_PIPES_DIR_ENV,
    LEGACY_PREFIX,
    LEGACY_PROJECT_PIPES_DIR,
    PIPES_DIR_ENV,
    PROJECT_PIPES_DIR,
    _dangerous,
    check_pipe,
    find_pipe,
    load_pipe,
)
from pipe_in.pipe.specs import build_pipe_specs
from test_pipe import pipe_cfg
from test_rules import SECRET_FILES, local_info_in

ROOT = Path(__file__).resolve().parents[1]
VIDEO = ROOT / "examples" / "video"
PIPES = VIDEO / "pipes"
PIPE_DIR = PIPES / "pipe-in-video"
SCRIPT_SAMPLE = VIDEO / "pipe-in-intro-script.md"
README = PIPE_DIR / "README.md"
TEMPLATE = VIDEO / "compare-template.html"
SERVER = VIDEO / "review_server.py"

# examples/video/ に置いてよいコード・HTML は、名前を決め打ちにした2つだけ（AC-14・24・51 で同じものを使う）
ALLOWED_CODE = {"review_server.py", "compare-template.html"}
CODE_SUFFIXES = {".js", ".mjs", ".py", ".sh", ".html"}
MEDIA_SUFFIXES = {".mp4", ".mov", ".webm", ".wav", ".mp3", ".m4a", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"}

STAGE_NAMES = ["ask", "script", "mock", "render", "verify"]
PROMPT_FILES = {
    "ask": "01_ask.md",
    "script": "02_script.md",
    "mock": "03_mock.md",
    "render": "04_render.md",
    "verify": "05_verify.md",
}


def example_files() -> list[Path]:
    assert VIDEO.is_dir(), f"{VIDEO.relative_to(ROOT)} がありません（見本をまだ作っていない）"
    return sorted(p for p in VIDEO.rglob("*") if p.is_file() and "__pycache__" not in p.parts)


def prompt_of(stage: str) -> str:
    path = PIPE_DIR / "prompts" / PROMPT_FILES[stage]
    assert path.is_file(), f"{path.relative_to(ROOT)} がありません（指示文をまだ作っていない）"
    return path.read_text(encoding="utf-8")


def read_readme() -> str:
    assert README.is_file(), f"{README.relative_to(ROOT)} がありません"
    return README.read_text(encoding="utf-8")


def read_template() -> str:
    assert TEMPLATE.is_file(), f"{TEMPLATE.relative_to(ROOT)} がありません"
    return TEMPLATE.read_text(encoding="utf-8")


def raw_toml() -> dict:
    path = PIPE_DIR / "pipe.toml"
    assert path.is_file(), f"{path.relative_to(ROOT)} がありません"
    return tomllib.loads(path.read_text(encoding="utf-8"))


def load_video():
    assert (PIPE_DIR / "pipe.toml").is_file(), f"{(PIPE_DIR / 'pipe.toml').relative_to(ROOT)} がありません"
    return load_pipe(PIPE_DIR)


def stage_of(pipe, name: str):
    return next(s for s in pipe.stages if s.name == name)


def missing_words(text: str, words: list) -> list[str]:
    """入っているべき語のうち、text に無いもの。語が (a, b) の組なら、どれか1つあればよい。"""
    out = []
    for w in words:
        alts = w if isinstance(w, tuple) else (w,)
        if not any(a in text for a in alts):
            out.append(" / ".join(alts))
    return out


def assert_has_words(label: str, text: str, words: list) -> None:
    missing = missing_words(text, words)
    assert missing == [], f"{label} に入っているべき語が足りません: {missing}"


def can_write_of(tmp_path: Path):
    """段の名前 → 書いてよいかの関数（プロジェクトからの相対パスを渡す）。"""
    pipe = load_video()
    cfg = pipe_cfg(tmp_path, pipe)
    specs = build_pipe_specs(cfg, pipe)
    own = {s.name: f"{cfg.rel(cfg.work_dir)}/{s.output}" for s in pipe.stages}
    return {name: spec.can_write for name, spec in specs.items()}, own


# ---- 検査の関数そのものが効いている確かめ（AC-07〜12 の補助） ---------------------------------


def test_required_words_check_fails_when_a_word_is_missing():
    """D0011-AC-07: 語を1つ抜いた文では、検査の関数が足りない語を名指しで失敗にする。"""
    words = ["意図", "ffprobe", ("curl", "wget")]
    assert_has_words("見本", "意図を聞く。ffprobe を使う。wget は使わない", words)
    with pytest.raises(AssertionError) as e:
        assert_has_words("見本", "意図を聞く。wget は使わない", words)
    assert "ffprobe" in str(e.value)
    with pytest.raises(AssertionError) as e:
        assert_has_words("見本", "ffprobe を使う", words)
    assert "意図" in str(e.value) and "curl / wget" in str(e.value)


# ---- パイプの定義（AC-01〜06・25・31・32・64） ---------------------------------------------


def test_video_pipe_passes_check(tmp_path):
    """D0011-AC-01: 見本のパイプは、定義の読み込みと検査（pipe-in-gen check と同じ）を通る。AC-32：案を出す指示文を入れた最終の形でも同じ。"""
    pipe = load_video()
    assert pipe.name == "video" and pipe.kind == "linear"
    assert check_pipe(pipe, tmp_path) == []


def test_video_pipe_stage_order_and_review():
    """D0011-AC-02: 段は ask・script・mock・render・verify の順で、verify 以外は review。"""
    pipe = load_video()
    assert [s.name for s in pipe.stages] == STAGE_NAMES
    assert [s.review for s in pipe.stages] == [True, True, True, True, False]


def test_ask_is_read_only_and_script_writes_only_choices(tmp_path):
    """D0011-AC-03: ask は read で何も足せない。script が書けるのは自分の成果物と video/choices.md（と案のデータ）だけ。"""
    pipe = load_video()
    ask = stage_of(pipe, "ask")
    assert ask.access == "read" and ask.writes == []
    script = stage_of(pipe, "script")
    assert script.writes == ["video/choices.md", "video/script/options.json"]

    can, own = can_write_of(tmp_path)
    assert can["ask"](own["ask"]) is True
    assert can["ask"]("video/choices.md") is False
    assert can["script"](own["script"]) is True
    assert can["script"]("video/choices.md") is True
    # 台本の前に見本を作り込めない
    assert can["script"]("video/mock/1/index.html") is False
    assert can["script"]("src/x.py") is False


def test_choices_write_scope(tmp_path):
    """D0011-AC-31: video/choices.md を書けるのは script と mock だけ。mock は video/mock/ の下も書ける。"""
    can, own = can_write_of(tmp_path)
    assert can["script"]("video/choices.md") is True
    assert can["mock"]("video/choices.md") is True
    for name in ("ask", "render", "verify"):
        assert can[name]("video/choices.md") is False, name
    assert can["script"]("video/mock/x") is False
    assert can["script"](own["render"]) is False
    assert can["mock"](own["mock"]) is True
    assert can["mock"]("video/mock/2/index.html") is True
    assert can["mock"]("video/mock/options.json") is True
    assert can["mock"]("video/out/a.mp4") is False
    assert can["mock"]("video/script/options.json") is False
    assert can["mock"]("src/x.py") is False


def test_options_json_write_scope(tmp_path):
    """D0011-AC-64: 案のデータは script が video/script/options.json、mock が video/mock/options.json にだけ書ける。render は見本の崩れの手直しだけ。"""
    can, _ = can_write_of(tmp_path)
    assert can["script"]("video/script/options.json") is True
    assert can["script"]("video/mock/options.json") is False
    assert can["mock"]("video/mock/options.json") is True
    assert can["mock"]("video/script/options.json") is False
    for name in ("ask", "render", "verify"):
        assert can[name]("video/script/options.json") is False, name
        assert can[name]("video/mock/options.json") is False, name
    assert can["render"]("video/mock/1/index.html") is True


def test_verify_has_verdict_command_and_retry():
    """D0011-AC-04: verify に verdict と command があり、差し戻し先は render（または mock）、回数の上限が整数。"""
    check = stage_of(load_video(), "verify").check
    assert check is not None
    assert check.verdict is True and check.command
    assert check.on_fail in ("render", "mock")
    assert isinstance(check.max_retries, int) and not isinstance(check.max_retries, bool) and check.max_retries >= 0


def test_bash_only_on_allowed_stages():
    """D0011-AC-05: Bash を持つのは mock・render・verify だけ。ask・script は持たない。"""
    pipe = load_video()
    bash_stages = {s.name for s in pipe.stages if s.bash}
    assert bash_stages <= {"mock", "render", "verify"}
    assert "ask" not in bash_stages and "script" not in bash_stages
    assert {"render", "verify"} <= bash_stages


def test_bash_stage_prompts_forbid_downloads():
    """D0011-AC-05: Bash を持つ段の指示文に、curl・wget を使わないことが書いてある。"""
    for s in load_video().stages:
        if s.bash:
            assert_has_words(PROMPT_FILES[s.name], prompt_of(s.name), ["curl", "wget"])


def test_video_pipe_opens_no_outside_route(tmp_path):
    """D0011-AC-06: 外へ出る道（web・mcp・mcp_servers・agents・add_dirs）を開かず、WebFetch・WebSearch・PowerShell は使えない。"""
    raw = raw_toml()
    keys = {"web", "mcp", "mcp_servers", "agents", "add_dirs"}
    assert keys & set(raw.get("pipe", {})) == set()
    for s in raw["stages"]:
        assert keys & set(s) == set(), f"{s.get('name')} に外へ出る道がある"
    pipe = load_video()
    for name, spec in build_pipe_specs(pipe_cfg(tmp_path, pipe), pipe).items():
        for tool in ("WebFetch", "WebSearch", "PowerShell"):
            assert tool in spec.disallowed_tools, f"{name}: {tool}"


def test_budget_limits():
    """D0011-AC-25: max_budget_usd は ask 0.5、script 1.5、mock 3.0、render 2.0、verify 1.0。"""
    pipe = load_video()
    assert {s.name: s.max_budget_usd for s in pipe.stages} == {
        "ask": 0.5,
        "script": 1.5,
        "mock": 3.0,
        "render": 2.0,
        "verify": 1.0,
    }


# ---- 指示文の語（AC-07〜12・26〜30・63） ----------------------------------------------------

ASK_WORDS = [
    "意図", "見せたい", "長さ", "画面の形", "縦長", "横長", "正方形", "音", "終わりの文", "ロゴ",
    "ファイルの大きさ", "推し", "番号", "video/assets/logo.svg", "宣伝文句", "ロゴを置いてください",
]  # fmt: skip
SCRIPT_WORDS = ["開始秒", "終わり秒", "見せるもの", "字幕", "1.5", "3.5", "表", "「、」の後ろ", "改行"]
MOCK_WORDS = ["台本", "足さない", "外部", "読み込まない", "時刻", "引数", "PNG", "curl", "wget", "video/mock/"]
RENDER_WORDS = [
    "1こまずつ", "時刻", "H.264", "yuv420p", "ビットレート", "2パス", "ffmpeg", "ffprobe", "Playwright",
    "止まって", "入れ方", "curl", "wget", "video/out/",
]  # fmt: skip
VERIFY_WORDS = [
    "取り出", "字幕の切り替わり", "場面の境目", "切れ", "重なり", "はみ出し", "ロゴの端", "ダーク", "ffprobe",
    "curl", "wget", "直す点", "render",
]  # fmt: skip
COMMON_WORDS = ["ロゴ", "描かない", "描き直さない", "人が渡した", "録音", "サンプル", "既定", "## ロゴと音の決まり"]


def test_ask_prompt_mentions_required_words():
    """D0011-AC-07: ask の指示文に、意図・見せたいもの・長さ・画面の形・音・終わりの文・ロゴ・大きさの上限・推しを聞くことが書いてある。"""
    assert_has_words("01_ask.md", prompt_of("ask"), ASK_WORDS)


def test_ask_prompt_asks_logo_rules_every_time():
    """D0011-AC-26: ask は、ロゴの使い方の決まりの文書の場所を毎回聞く。"""
    assert_has_words("01_ask.md", prompt_of("ask"), ["video/assets/logo.svg", "決まり", "毎回"])


def test_script_prompt_mentions_required_words():
    """D0011-AC-08: script の指示文に、開始秒・終わり秒・見せるもの・字幕の表と、字幕を 1.5〜3.5 秒に収めることが書いてある。"""
    assert_has_words("02_script.md", prompt_of("script"), SCRIPT_WORDS)


def test_mock_prompt_mentions_required_words():
    """D0011-AC-09: mock の指示文に、台本に無い場面を足さないことと、外部を読み込まない HTML にすることが書いてある。"""
    assert_has_words("03_mock.md", prompt_of("mock"), MOCK_WORDS)


def test_render_prompt_mentions_required_words():
    """D0011-AC-10: render の指示文に、1こまずつ撮ること・H.264・yuv420p・ビットレート・2パス・事前の環境確認が書いてある。"""
    assert_has_words("04_render.md", prompt_of("render"), RENDER_WORDS)


def test_verify_prompt_mentions_required_words():
    """D0011-AC-11: verify の指示文に、こまの取り出し・切れ・重なり・はみ出し・ffprobe での確認が書いてある。"""
    assert_has_words("05_verify.md", prompt_of("verify"), VERIFY_WORDS)


@pytest.mark.parametrize("stage", STAGE_NAMES)
def test_every_prompt_forbids_drawing_logo_and_borrowed_audio(stage):
    """D0011-AC-12: 全部の指示文に、ロゴを描かず人が渡したものだけ使うこと、他人の録音・サンプルを使わないことが書いてある。"""
    assert_has_words(PROMPT_FILES[stage], prompt_of(stage), COMMON_WORDS)


def test_script_prompt_asks_for_options():
    """D0011-AC-27: script は、初めの回に流れの違う案を2〜3つ番号付きで出し、次の回は選ばれた案だけを直す。"""
    words = ["初めの回", "案", "2", "3", "流れの違う", "番号", "この案の流れ", "次の回", "選ばれた案"]
    assert_has_words("02_script.md", prompt_of("script"), words)


def test_mock_prompt_asks_for_three_options_and_compare_page():
    """D0011-AC-28（AC-40 の進み具合を含む）: mock は、初めの回に見せ方の違う3案を比較ページ用のデータで出し、次の回は選ばれた案だけを作り込む。"""
    words = [
        "初めの回", "3案", "見せ方の違う", "比較ページ", "video/mock/options.json", "主な場面", "この案の特徴",
        "進み具合", "次の回", "選ばれた案",
    ]  # fmt: skip
    assert_has_words("03_mock.md", prompt_of("mock"), words)


@pytest.mark.parametrize("stage", ["script", "mock"])
def test_script_and_mock_prompts_redo_when_none_chosen(stage):
    """D0011-AC-29: どの案も選ばれなかった（どれもびみょう）ときは、別の方向で出し直すことが書いてある。"""
    assert_has_words(PROMPT_FILES[stage], prompt_of(stage), ["どれもびみょう", "別の方向", "出し直す"])


def test_prompts_use_choices_record():
    """D0011-AC-30: script・mock は選んだ記録を回の始めに読み、選んだ案と直した点を書く。render・verify は選ばれた1案だけを扱い、無ければ止まる。"""
    for stage in ("script", "mock"):
        assert_has_words(PROMPT_FILES[stage], prompt_of(stage), ["video/choices.md", "回の始め", "選んだ案", "直した点"])
    for stage in ("render", "verify"):
        assert_has_words(
            PROMPT_FILES[stage], prompt_of(stage), ["video/choices.md", "選ばれた案", "1案だけ", "止まる", "案が選ばれていません"]
        )


def test_script_and_mock_prompts_write_data_not_html():
    """D0011-AC-63: script・mock は比較ページの HTML を書かずデータ（options.json）だけを書く。mock は場面の HTML は書く。"""
    assert_has_words("02_script.md", prompt_of("script"), ["video/script/options.json", "データ", "HTML", "書かない"])
    assert_has_words("03_mock.md", prompt_of("mock"), ["video/mock/options.json", "データ", "HTML", "書かない", "場面"])


def test_verify_reads_small_frames():
    """D0011-AC-68: verify はこまを縮めて（幅 540 以下の JPEG）取り出してから読む。原寸の PNG を読むと SDK の1通の上限（1MB）を超えて落ちるため。"""
    assert_has_words("05_verify.md", prompt_of("verify"), ["540", "JPEG", "1MB"])


@pytest.mark.parametrize("stage", ["render", "verify"])
def test_render_and_verify_treat_approved_last_round_as_chosen(stage):
    """D0011-AC-67: 見本の最後の回の「選んだ案」が空でも、その回が1案だけなら、人が承認して進めたものとして扱う（承認では誰も記録を埋めないため）。"""
    name = {"render": "04_render.md", "verify": "05_verify.md"}[stage]
    assert_has_words(name, prompt_of(stage), ["最後の回", "空", "1案だけ", "承認"])


@pytest.mark.parametrize("stage", ["ask", "script", "mock", "render", "verify"])
def test_prompts_do_not_send_stage_to_readme(stage):
    """D0011-AC-66: 指示文は README を見に行かせない（利用者のプロジェクトに見本の README は無い）。データの形は指示文の中に書く。"""
    text = prompt_of(stage)
    assert "README" not in text, f"{stage} の指示文が README を指している"
    if stage == "script":
        assert_has_words("02_script.md", text, ['"options"', '"scenes"', '"caption"', "| 段 | 回 |"])
    if stage == "mock":
        assert_has_words("03_mock.md", text, ['"options"', '"frames"', "video/mock/1/frames/"])


# ---- 確認用のコマンド（AC-13） ------------------------------------------------------------


@pytest.mark.parametrize(
    "limit,limited_size,expected",
    [
        ("100\n", 101, 1),  # 上限を超える
        ("100\n", 100, 0),  # ちょうど上限
        ("100\n", 50, 0),  # 上限以内
        (None, 5000, 0),  # 上限の指定なし
        ("100\n", None, 1),  # 上限があるのに limited.mp4 が無い
    ],
    ids=["over", "exact", "under", "no-limit-file", "no-limited-mp4"],
)
def test_size_command_exit_codes(tmp_path, limit, limited_size, expected):
    """D0011-AC-13: 大きさの確認用コマンドは、上限を超える MP4 で 0 以外、上限以内・上限なしで 0 になる（小さなダミーのファイルで確かめる）。"""
    command = stage_of(load_video(), "verify").check.command
    assert command.startswith("python "), command
    out = tmp_path / "video" / "out"
    out.mkdir(parents=True)
    if limit is not None:
        (out / "size_limit_bytes.txt").write_text(limit, encoding="utf-8")
    if limited_size is not None:
        (out / "limited.mp4").write_bytes(b"0" * limited_size)
    result = run_shell(command.replace("python", f'"{sys.executable}"', 1), tmp_path, 30)
    assert result.returncode == expected, result.output_tail


def test_size_command_is_not_dangerous(tmp_path):
    """D0011-AC-13: 確認用コマンドは「危ない操作」の検査に掛からず、check_pipe も通る。"""
    pipe = load_video()
    assert check_pipe(pipe, tmp_path) == []
    assert _dangerous(stage_of(pipe, "verify").check.command) is None


# ---- 置いてよいもの・いけないもの（AC-14・15・24・51・58） ---------------------------------


def test_no_media_or_logo_files_in_video_example():
    """D0011-AC-14: examples/video/ に、動画・音声・画像のファイルと、ロゴの実ファイルが無い（コードは例外の2つの名前だけ）。"""
    files = example_files()
    assert files, "examples/video/ に何も無い"
    media = [p.relative_to(ROOT).as_posix() for p in files if p.suffix.lower() in MEDIA_SUFFIXES]
    assert media == []
    logos = [p.name for p in files if "logo" in p.name.lower() and p.suffix.lower() in MEDIA_SUFFIXES | {".ai", ".eps"}]
    assert logos == []
    stray_code = [p.name for p in files if p.suffix.lower() in {".py", ".html"} and p.name not in ALLOWED_CODE]
    assert stray_code == []


def test_video_example_has_no_local_info():
    """D0011-AC-15: examples/video/ の全ファイルに、手元の事情（パス・メール）も秘密のファイルも無い。"""
    found = []
    for p in example_files():
        rel = p.relative_to(ROOT).as_posix()
        if SECRET_FILES.search(rel):
            found.append(f"{rel}: 秘密のファイル")
        found += [f"{rel}: {f}" for f in local_info_in(p.read_text(encoding="utf-8", errors="ignore"))]
    assert found == []
    assert any(p.suffix == ".md" for p in example_files())


def test_no_scripts_or_html_in_video_example():
    """D0011-AC-24: examples/video/ の .js・.mjs・.py・.sh・.html は、受付とテンプレートの2つだけ（どちらかが無くなる・増えると落ちる）。"""
    found = {p.name for p in example_files() if p.suffix.lower() in CODE_SUFFIXES}
    assert found == ALLOWED_CODE


def test_template_is_single_html():
    """D0011-AC-58: 比較・答えるページのテンプレートの HTML が1枚だけある。"""
    assert TEMPLATE.is_file()
    assert {p.name for p in example_files() if p.suffix.lower() == ".html"} == {"compare-template.html"}


def test_server_uses_only_standard_library():
    """D0011-AC-51: 受付は標準ライブラリだけを import し、pipe_in に依存せず、shell=True を使わない。.py は受付の1本だけ。"""
    assert SERVER.is_file(), f"{SERVER.relative_to(ROOT)} がありません"
    source = SERVER.read_text(encoding="utf-8")
    names: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, "相対 import は使わない"
            names.add((node.module or "").split(".")[0])
    assert names, "import が1つも見つからない"
    assert sorted(n for n in names if n not in sys.stdlib_module_names) == []
    assert not [n for n in names if n.startswith("pipe_in")]
    assert "shell=True" not in source.replace(" ", "")
    assert {p.name for p in example_files() if p.suffix == ".py"} == {"review_server.py"}


# ---- 台本の見本（AC-24） ------------------------------------------------------------------


def script_rows(text: str) -> list[list[str]]:
    rows = []
    for line in text.splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if cells and re.fullmatch(r"\d+", cells[0]):
            rows.append(cells)
    return rows


def test_script_rows_parser_reads_a_table():
    """D0011-AC-24: 台本の表の読み方そのものの確かめ（見出しと区切りの行は読み飛ばす）。"""
    text = "| No | 開始秒 | 終わり秒 | 見せるもの | 字幕 |\n| --- | --- | --- | --- | --- |\n| 1 | 0 | 3 | a | b |\n"
    assert script_rows(text) == [["1", "0", "3", "a", "b"]]


def test_script_sample_table_is_valid():
    """D0011-AC-24: 台本の見本の各行が開始・終わり・見せるもの・字幕を持ち、字幕は 1.5〜3.5 秒で、0 秒から 15 秒まですきまなく続く。"""
    assert SCRIPT_SAMPLE.is_file(), f"{SCRIPT_SAMPLE.relative_to(ROOT)} がありません"
    rows = script_rows(SCRIPT_SAMPLE.read_text(encoding="utf-8"))
    assert rows, "表の行が無い"
    cursor = 0.0
    for cells in rows:
        assert len(cells) >= 5, cells
        _no, start, end, show, caption = cells[:5]
        assert show and caption, cells
        s, e = float(start), float(end)
        assert s == cursor, f"前の行の終わりと続いていない: {cells}"
        assert 1.5 <= round(e - s, 6) <= 3.5, f"字幕の長さが 1.5〜3.5 秒でない: {cells}"
        cursor = e
    assert cursor == 15.0


# ---- 置き場所（AC-16・23） ----------------------------------------------------------------


def test_video_pipe_found_with_pipes_dir():
    """D0011-AC-23: --pipes-dir examples/video/pipes で video が見つかり、pipe.toml を持つフォルダを返す。"""
    found = find_pipe("video", PIPES)
    assert found is not None and (found / "pipe.toml").is_file()
    assert found.name == "pipe-in-video"


def test_video_example_does_not_change_pipe_lookup(tmp_path, monkeypatch):
    """D0011-AC-16: 見本は、既定の探す場所のどれにも無い（--pipes-dir で指したときだけ読まれる）。今の作りのままで通る（守り続けるための検査）。"""
    monkeypatch.delenv(PIPES_DIR_ENV, raising=False)
    monkeypatch.delenv(LEGACY_PIPES_DIR_ENV, raising=False)
    assert find_pipe("video", None, project=tmp_path) is None


@pytest.mark.parametrize(
    "place,folder",
    [(PROJECT_PIPES_DIR.as_posix(), "pipe-in-video"), (LEGACY_PROJECT_PIPES_DIR.as_posix(), LEGACY_PREFIX + "video")],
    ids=["new-place", "legacy-place"],
)
def test_video_pipe_found_in_old_and_new_places(tmp_path, monkeypatch, place, folder):
    """D0011-AC-16: 見本のフォルダを、今の置き場所にも前の版の置き場所にも写すと、find_pipe で見つかり check_pipe が空になる。"""
    monkeypatch.delenv(PIPES_DIR_ENV, raising=False)
    monkeypatch.delenv(LEGACY_PIPES_DIR_ENV, raising=False)
    assert PIPE_DIR.is_dir(), "見本のパイプのフォルダがありません"
    dst = tmp_path / place / folder
    shutil.copytree(PIPE_DIR, dst, ignore=shutil.ignore_patterns("__pycache__"))
    found = find_pipe("video", None, project=tmp_path)
    assert found == dst
    assert check_pipe(load_pipe(found), tmp_path) == []


# ---- README（AC-26・33・62） --------------------------------------------------------------


def test_video_readme_has_input_example_and_paths():
    """D0011-AC-26: README に、ロゴの既定の置き場所・--pipes-dir の付け方・要件メモの入力例（意図の文を含む）がある。"""
    text = read_readme()
    assert_has_words("README.md", text, ["video/assets/logo.svg", "--pipes-dir examples/video/pipes", "意図"])
    assert re.search(r"^#+ .*入力例", text, re.MULTILINE), "要件メモの「入力例」の見出しがありません"


def test_readme_has_choices_example():
    """D0011-AC-33: README に、選んだ記録 video/choices.md の書き方（段・回・出した案・選んだ案・直した点の表）の例がある。"""
    text = read_readme()
    assert "video/choices.md" in text
    header = [line for line in text.splitlines() if line.lstrip().startswith("|") and "出した案" in line]
    assert header, "表の見出しの行がありません"
    assert_has_words("README.md の表の見出し", header[0], ["段", "回", "出した案", "選んだ案", "直した点"])


def test_readme_shows_options_json_shapes():
    """D0011-AC-62: README に、案のデータ video/script/options.json・video/mock/options.json の形の例がある。"""
    words = ["video/script/options.json", "video/mock/options.json", '"options"', '"number"', '"scenes"', '"frames"']
    assert_has_words("README.md", read_readme(), words)


# ---- テンプレート（AC-49・59・60・61・65） -----------------------------------------------

EXTERNAL_LOADS = [
    r"""(src|href)\s*=\s*["']?(https?:)?//""",
    r"@import",
    r"""url\(\s*["']?(https?:)?//""",
    r"http://",
    r"https://",
    r"<link",
    r"<iframe",
]
HTML_INJECTION = ["innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(", "new Function"]


def test_external_load_patterns_catch_bad_html():
    """D0011-AC-59: 外部の読み込みの見つけ方そのものが、外のものを読む書き方を見つける。"""
    bad = [
        '<script src="https://cdn.example/x.js"></script>',
        '<img src="//cdn.example/a.png">',
        "<style>@import 'a.css';</style>",
        "<div style=\"background:url('//cdn.example/a.png')\">",
        '<link rel="stylesheet" href="a.css">',
        '<iframe src="x"></iframe>',
    ]
    for html in bad:
        assert any(re.search(p, html) for p in EXTERNAL_LOADS), html
    assert not any(re.search(p, "<style>a{color:red}</style><script>var a = 1 / 2;</script>") for p in EXTERNAL_LOADS)


def test_template_has_no_external_loads():
    """D0011-AC-49・AC-59: テンプレートに、外部の読み込み（CDN・外部のフォント・スクリプト・http(s)）が無い。"""
    text = read_template()
    found = [p for p in EXTERNAL_LOADS if re.search(p, text)]
    assert found == []


def test_template_never_uses_html_injection():
    """D0011-AC-60: テンプレートは、外から来た文字を HTML として入れる書き方（innerHTML など）を使わない。"""
    text = read_template()
    assert [w for w in HTML_INJECTION if w in text] == []
    assert "textContent" in text and "createElement" in text


def test_template_has_validation_and_alert():
    """D0011-AC-61: テンプレートに、データの形を検査する validateOptions と、原因を出す role="alert" の場所がある。"""
    text = read_template()
    assert "validateOptions" in text
    assert 'role="alert"' in text
    assert "<!--PAGE-DATA-->" in text, "受付がデータを入れる目印がありません"


def test_template_rejects_images_outside_video():
    """D0011-AC-65: テンプレートは、video/ で始まらない画像（.. を含むものも）を img にせず、検査でエラーの文にする。静的な確かめ（動きは手で）。"""
    text = read_template()
    assert "validateOptions" in text
    assert re.search(r"""["']video/["']""", text), "video/ で始まるかの検査の語がありません"
    assert ".." in text, ".. を含むものを断る検査の語がありません"
    assert "createElement" in text and "img" in text
