"""D0100：generator/ の2つの役（作る・プラグインの裏の道具）のあいだの import の向き。

generator/ は下位パッケージに分けず（案 B）、役の境目をこの検査で固める。
- 裏の道具 → 作る は、どこにあっても止める（関数の中でも）。裏の道具どうしは許す。
- 作る → 裏の道具 は止める。例外は入口 cli.py の、関数の中（コマンドの分岐）で読む import だけ。
- generator/ の直下の .py（__init__.py を除く）は、役の一覧にちょうど1回ずつ入る（GENERATOR_KINDS と D0099 の地図は直下だけ）。
- 下のフォルダの .py（templates/・schemas/ の中と __pycache__ を除く）は置かない（下位パッケージに分けない。D0100）。

役の一覧は D0099 の tests/test_repo_map.py の GENERATOR_KINDS 1つだけを元にし、ここには写さない（数も名前も GENERATOR_KINDS から作る）。
決定ごとの別ファイルの決まり（D0075）。共有の部品は tests/test_architecture.py のものを import する。
今の作りのままで通るテストは、名前の末尾を _守る にする。
ソースは読むだけで書かない。偽の generator/ は tmp_path に作る。SDK は呼ばない。
"""

from __future__ import annotations

import ast
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import pytest

from test_architecture import _imports, _module_name  # noqa: PLC2701
from test_readme import section
from test_repo_map import GENERATOR_KINDS

ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "generator"
DESIGN_MD = ROOT / "docs" / "development" / "design.md"
DECISIONS = ROOT / "docs" / "decisions"
THIS_FILE = "tests/test_architecture_generator_roles.py"

PACKAGE = "pipe_in_generator"
ROLES = {"作る": "build", "プラグイン": "tool"}  # GENERATOR_KINDS の品の名前 → 役
ENTRY = "cli.py"                                # 両方を読んでよい入口（関数の中だけ）
NOT_COUNTED = {"__init__.py"}                    # どちらの役にも入れない（パッケージの枠）
DATA_DIRS = {"templates", "schemas"}             # ひな形と Schema の置き場所（下のフォルダでも数えない）
NOT_SPLIT = "generator/ は下位パッケージに分けないと決めました（D0100）。分け直すなら決定の記録を書いてから"

FUNCTION_NODES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)


# ---- 検査の部品 -----------------------------------------------------------------------------------


def _placed_imports(path: Path, module: str) -> list[tuple[str, int, bool]]:
    """（読む先の名前, 行の番号, 関数の中か）。名前の作り方は test_architecture._imports と同じ。

    祖先に関数（def・async def・lambda）があれば「関数の中」。トップの if・try・with の中と、
    クラスの本体は、import したときに動くので「モジュールの先頭」に入れる。
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    is_package = path.name == "__init__.py"
    found: list[tuple[str, int, bool]] = []

    def visit(node: ast.AST, inside: bool) -> None:
        for child in ast.iter_child_nodes(node):
            child_inside = inside or isinstance(child, FUNCTION_NODES)
            if isinstance(child, ast.Import):
                found.extend((a.name, child.lineno, child_inside) for a in child.names)
            elif isinstance(child, ast.ImportFrom):
                if child.level:
                    base = module.split(".")
                    base = base if is_package else base[:-1]
                    base = base[: len(base) - (child.level - 1)]
                    target = ".".join([*base, child.module] if child.module else base)
                else:
                    target = child.module or ""
                found.append((target, child.lineno, child_inside))
                found.extend((f"{target}.{a.name}", child.lineno, child_inside) for a in child.names)
            visit(child, child_inside)

    visit(tree, False)
    return found


def _generator_files(gen_dir: Path) -> dict[str, Path]:
    """generator/ の直下の .py の名前（cli.py など）→ ファイル。__init__.py は除く（GENERATOR_KINDS と同じく直下だけ）。"""
    return {path.name: path for path in sorted(gen_dir.glob("*.py")) if path.name not in NOT_COUNTED}


def _nested_files(gen_dir: Path) -> list[str]:
    """下のフォルダの .py（generator/ からの相対のパス）。templates/・schemas/ の中と __pycache__ は除く。"""
    out: list[str] = []
    for path in sorted(gen_dir.rglob("*.py")):
        parts = path.relative_to(gen_dir).parts
        if len(parts) == 1 or parts[0] in DATA_DIRS or "__pycache__" in parts:
            continue
        out.append(path.relative_to(gen_dir).as_posix())
    return out


def _listing_problems(gen_dir: Path, kinds: Mapping[str, str]) -> list[str]:
    files = _generator_files(gen_dir)
    out: list[str] = []
    for rel in files:
        if rel not in kinds:
            out.append(
                f"generator/{rel} がどちらの役の一覧にもありません。tests/test_repo_map.py の GENERATOR_KINDS に"
                f"「作る」か「プラグイン」で足し、docs/development/design.md の「リポジトリの地図」の箇条書きにも書いてください（D0099・D0100）"
            )
    for rel in _nested_files(gen_dir):
        out.append(f"generator/{rel} が下のフォルダにあります。{NOT_SPLIT}にしてください")
    for rel, kind in kinds.items():
        if rel not in files:
            out.append(
                f"generator/{rel} が GENERATOR_KINDS にありますが、ファイルがありません。"
                f"GENERATOR_KINDS と地図の箇条書きから消してください（D0099・D0100）"
            )
        elif kind not in ROLES:
            out.append(f"generator/{rel} の品「{kind}」は、作るかプラグインのどちらかにしてください（GENERATOR_KINDS）")
    return out


@dataclass(frozen=True)
class Edge:
    """generator/ の中の、役から役への import の1件。"""

    source: str        # generator/ からの相対のパス
    source_role: str   # build・tool
    line: int
    inside: bool       # 関数の中か
    target: str        # 読む先のモジュールの名前（pipe_in_generator.cli など）
    target_role: str


def _edges(gen_dir: Path, kinds: Mapping[str, str]) -> list[Edge]:
    """役の一覧に入っているファイルどうしの import（同じ行・同じ読む先は1件にまとめる）。"""
    files = _generator_files(gen_dir)
    roles: dict[str, tuple[str, str]] = {}  # モジュールの名前 → (相対のパス, 役)
    for rel, path in files.items():
        role = ROLES.get(kinds.get(rel, ""))
        if role:
            roles[_module_name(path, gen_dir, PACKAGE)] = (rel, role)
    out: set[Edge] = set()
    for module, (rel, role) in roles.items():
        for name, line, inside in _placed_imports(files[rel], module):
            if name == PACKAGE:
                continue  # 枠だけの読み込みは、どちらの役にも数えない
            for target, (_, target_role) in roles.items():
                if name == target or name.startswith(target + "."):
                    out.add(Edge(rel, role, line, inside, target, target_role))
    return sorted(out, key=lambda e: (e.source, e.line, e.target, e.inside))


def _edge_problem(edge: Edge) -> str | None:
    where = f"generator/{edge.source}:{edge.line}"
    if edge.source_role == "tool" and edge.target_role == "build":
        return f"{where} 裏の道具が、作るの {edge.target} を読んでいます（裏の道具は作るに頼らない。D0100）"
    if edge.source_role == "build" and edge.target_role == "tool":
        if edge.source != ENTRY:
            return f"{where} 作るが、裏の道具の {edge.target} を読んでいます（裏の道具を読んでよいのは入口 cli.py の関数の中だけ。D0100）"
        if not edge.inside:
            return f"{where} 入口 cli.py が、モジュールの先頭で裏の道具の {edge.target} を読んでいます（コマンドの分岐の、関数の中で読む。D0100）"
    return None


def role_problems(gen_dir: Path, kinds: Mapping[str, str]) -> list[str]:
    """役の一覧と import の向きの問題を、1件1行で返す（決まった順）。"""
    problems = _listing_problems(gen_dir, kinds)
    problems += [p for p in (_edge_problem(e) for e in _edges(gen_dir, kinds)) if p]
    return sorted(set(problems))


def _show(problems: list[str]) -> str:
    return "\n".join(problems)


# ---- 偽の generator/ --------------------------------------------------------------------------------

FAKE_KINDS = {
    "cli.py": "作る", "design.py": "作る", "render.py": "作る", "detect.py": "作る",
    "guard_hook.py": "プラグイン", "chat_hook.py": "プラグイン", "judge_score.py": "プラグイン",
}


def _fake_generator(tmp_path: Path) -> Path:
    """違反の無い土台：どのファイルも import json だけ。__init__.py は docstring だけ。"""
    gen = tmp_path / "generator"
    gen.mkdir()
    (gen / "__init__.py").write_text('"""偽の generator。"""\n', encoding="utf-8")
    for name in FAKE_KINDS:
        (gen / name).write_text("import json\n", encoding="utf-8")
    return gen


# ---- D0100-AC-01：役の一覧 ---------------------------------------------------------------------------


def test_d0100_ac01_generatorのpyはどれか1つの役にちょうど1回ずつ入る_守る():
    """D0100-AC-01: 今の作りのままで通る。generator/ の直下の .py（__init__.py を除く）の集まりが GENERATOR_KINDS のキーと同じで、どれも作るか裏の道具のどちらかにちょうど1回ずつ入る。"""
    problems = _listing_problems(GENERATOR, GENERATOR_KINDS)
    assert problems == [], _show(problems)
    files = _generator_files(GENERATOR)
    assert set(files) == set(GENERATOR_KINDS)
    build = {rel for rel, kind in GENERATOR_KINDS.items() if ROLES.get(kind) == "build"}
    tool = {rel for rel, kind in GENERATOR_KINDS.items() if ROLES.get(kind) == "tool"}
    assert build & tool == set()
    assert build | tool == set(files)
    # 空振りでない：どちらの役にも1つ以上ある
    assert build and tool, f"作る {sorted(build)}・裏の道具 {sorted(tool)}"


def test_d0100_ac01_generatorの下のフォルダにpyが無い_守る():
    """D0100-AC-01: 今の作りのままで通る。generator/ の下のフォルダ（templates/・schemas/ と __pycache__ を除く）に .py が無い（下位パッケージに分けない）。"""
    nested = _nested_files(GENERATOR)
    assert nested == [], _show([p for p in _listing_problems(GENERATOR, GENERATOR_KINDS) if NOT_SPLIT in p])


def test_d0100_ac01_役の名前はGENERATOR_KINDSの作るとプラグインだけで入口cli_pyは作る_守る():
    """D0100-AC-01: 今の作りのままで通る。GENERATOR_KINDS の品の名前は「作る」と「プラグイン」だけで、入口 cli.py は「作る」。"""
    assert set(GENERATOR_KINDS.values()) == set(ROLES)
    assert GENERATOR_KINDS.get(ENTRY) == "作る", "入口 cli.py が役の一覧の「作る」から外れています"


# ---- D0100-AC-02・03：今の generator/ の向き --------------------------------------------------------


def test_d0100_ac02_裏の道具は作るを読まない_守る():
    """D0100-AC-02: 今の作りのままで通る。裏の道具のどれも、作るのどれも import しない（関数の中も含む。役は GENERATOR_KINDS から）。"""
    edges = _edges(GENERATOR, GENERATOR_KINDS)
    bad = [e for e in edges if e.source_role == "tool" and e.target_role == "build"]
    assert bad == [], _show([p for p in map(_edge_problem, bad) if p])
    # 空振りでない：裏の道具どうしの1件（chat_hook → guard_hook）は見えている
    assert any(e.source == "chat_hook.py" and e.target == f"{PACKAGE}.guard_hook" for e in edges)


def test_d0100_ac03_cli_py以外の作るは裏の道具を読まない_守る():
    """D0100-AC-03: 今の作りのままで通る。cli.py を除く作るのどれも、裏の道具のどれも import しない（関数の中も含む。役は GENERATOR_KINDS から）。"""
    edges = _edges(GENERATOR, GENERATOR_KINDS)
    bad = [e for e in edges if e.source_role == "build" and e.source != ENTRY and e.target_role == "tool"]
    assert bad == [], _show([p for p in map(_edge_problem, bad) if p])
    # 空振りでない：作るどうしの import（design → cli など）は見えている
    assert any(e.source == "design.py" and e.target == f"{PACKAGE}.cli" for e in edges)


def test_d0100_ac03_cli_pyは裏の道具を関数の中だけで読む_守る():
    """D0100-AC-03: 今の作りのままで通る。cli.py が裏の道具を読む import はどれも関数の中で、モジュールの先頭には無い。"""
    edges = [e for e in _edges(GENERATOR, GENERATOR_KINDS) if e.source == ENTRY and e.target_role == "tool"]
    top = [e for e in edges if not e.inside]
    assert top == [], _show([p for p in map(_edge_problem, top) if p])
    # 空振りでない：cli.py が関数の中で裏の道具を読む import は見えている（コマンドの分岐）
    assert edges, "cli.py が裏の道具を読む import が1つも見えません（読み方の誤り）"
    problems = role_problems(GENERATOR, GENERATOR_KINDS)
    assert problems == [], _show(problems)


# ---- D0100-AC-04：偽の裏の道具 ----------------------------------------------------------------------


def test_d0100_ac04_偽の土台は問題が無い_守る(tmp_path):
    """D0100-AC-04: 今の作りのままで通る。偽の generator/ の土台そのものは問題 0 件（下の確かめが空振りでないことの前提）。"""
    gen = _fake_generator(tmp_path)
    assert role_problems(gen, FAKE_KINDS) == []
    assert set(_generator_files(gen)) == set(FAKE_KINDS)


TOOL_READS_BUILD = [
    ("from .cli import main\n", 1, "cli"),
    ("from . import render\n", 1, "render"),
    ("import pipe_in_generator.design\n", 1, "design"),
    ("from pipe_in_generator import detect\n", 1, "detect"),
    ("import json\n\n\ndef run():\n    from .cli import main\n    return main\n", 5, "cli"),
]


@pytest.mark.parametrize(
    "source,line,target", TOOL_READS_BUILD,
    ids=["相対_from_cli", "相対_from点import", "絶対_import", "絶対_from_import", "関数の中"],
)
def test_d0100_ac04_偽の裏の道具が作るを読むと見つける_守る(tmp_path, source, line, target):
    """D0100-AC-04: 今の作りのままで通る。偽の裏の道具 chat_hook.py が、相対・絶対・関数の中のどの形で作るを読んでも見つける。"""
    gen = _fake_generator(tmp_path)
    (gen / "chat_hook.py").write_text(source, encoding="utf-8")
    assert role_problems(gen, FAKE_KINDS) == [
        f"generator/chat_hook.py:{line} 裏の道具が、作るの pipe_in_generator.{target} を読んでいます（裏の道具は作るに頼らない。D0100）"
    ]


TOOL_ALLOWED = [
    "from . import guard_hook\n",
    "import json\n",
    "from pipe_in.pipe import chat\n",
    "import pipe_in_generator\n",
]


@pytest.mark.parametrize("source", TOOL_ALLOWED, ids=["裏の道具どうし", "標準ライブラリ", "本体", "枠だけ"])
def test_d0100_ac04_偽の裏の道具の許す形は通す_守る(tmp_path, source):
    """D0100-AC-04: 今の作りのままで通る。裏の道具どうし・標準ライブラリ・本体 pipe_in.pipe・パッケージの枠だけの import は見逃す。"""
    gen = _fake_generator(tmp_path)
    (gen / "chat_hook.py").write_text(source, encoding="utf-8")
    assert role_problems(gen, FAKE_KINDS) == []


def test_d0100_ac04_読み方はtest_architectureの_importsと同じ_守る():
    """D0100-AC-04: 今の作りのままで通る。今の generator/ のどの .py でも、_placed_imports の名前の集まりが test_architecture._imports と同じ。"""
    paths = sorted(p for p in GENERATOR.rglob("*.py") if "__pycache__" not in p.parts)
    assert paths, "generator/ に .py が見つかりません"
    for path in paths:
        module = _module_name(path, GENERATOR, PACKAGE)
        placed = {name for name, _, _ in _placed_imports(path, module)}
        assert placed == set(_imports(path, module)), path.relative_to(ROOT).as_posix()


# ---- D0100-AC-05：偽の作る ---------------------------------------------------------------------------

BUILD_READS_TOOL = [
    ("from .guard_hook import decide\n", 1, "guard_hook"),
    ("from . import chat_hook\n", 1, "chat_hook"),
    ("import pipe_in_generator.judge_score\n", 1, "judge_score"),
    ("import json\n\n\ndef run():\n    from .guard_hook import decide\n    return decide\n", 5, "guard_hook"),
]


@pytest.mark.parametrize(
    "source,line,target", BUILD_READS_TOOL,
    ids=["相対_from_guard_hook", "相対_from点import", "絶対_import", "関数の中"],
)
def test_d0100_ac05_偽の作るが裏の道具を読むと見つける_守る(tmp_path, source, line, target):
    """D0100-AC-05: 今の作りのままで通る。偽の作る design.py が、相対・絶対・関数の中のどの形で裏の道具を読んでも見つける。"""
    gen = _fake_generator(tmp_path)
    (gen / "design.py").write_text(source, encoding="utf-8")
    assert role_problems(gen, FAKE_KINDS) == [
        f"generator/design.py:{line} 作るが、裏の道具の pipe_in_generator.{target} を読んでいます"
        "（裏の道具を読んでよいのは入口 cli.py の関数の中だけ。D0100）"
    ]


CLI_TOP_READS_TOOL = [
    ("import json\nfrom .chat_hook import main\n", 2, "chat_hook"),
    ("import sys\n\nif sys.argv:\n    from .guard_hook import quiet_exit_streams\n", 4, "guard_hook"),
    ("try:\n    from .judge_score import main\nexcept ImportError:\n    main = None\n", 2, "judge_score"),
    ("class Commands:\n    from . import chat_hook\n", 2, "chat_hook"),
]


@pytest.mark.parametrize(
    "source,line,target", CLI_TOP_READS_TOOL,
    ids=["トップのimport", "トップのifの中", "トップのtryの中", "クラスの本体"],
)
def test_d0100_ac05_偽のcli_pyが先頭で裏の道具を読むと見つける_守る(tmp_path, source, line, target):
    """D0100-AC-05: 今の作りのままで通る。偽の cli.py が、関数の外（トップ・トップの if・try・クラスの本体）で裏の道具を読むと見つける。"""
    gen = _fake_generator(tmp_path)
    (gen / "cli.py").write_text(source, encoding="utf-8")
    assert role_problems(gen, FAKE_KINDS) == [
        f"generator/cli.py:{line} 入口 cli.py が、モジュールの先頭で裏の道具の pipe_in_generator.{target} を読んでいます"
        "（コマンドの分岐の、関数の中で読む。D0100）"
    ]


def test_d0100_ac05_偽のcli_pyが関数の中で裏の道具を読むのは通す_守る(tmp_path):
    """D0100-AC-05: 今の作りのままで通る。偽の cli.py が、関数の中（どの関数でも。メソッド・async def も）で裏の道具を読む形は通す。作るの先頭の import も通す。"""
    gen = _fake_generator(tmp_path)
    (gen / "cli.py").write_text(
        "from .detect import detect\n"
        "from .render import render\n"
        "\n"
        "\n"
        "def main(argv=None):\n"
        "    if argv and argv[0] == 'guard-hook':\n"
        "        from .chat_hook import main as hook_main\n"
        "        from .guard_hook import quiet_exit_streams\n"
        "        return hook_main()\n"
        "    from .judge_score import main as judge_main\n"
        "    return judge_main()\n"
        "\n"
        "\n"
        "async def later():\n"
        "    from . import chat_hook\n"
        "\n"
        "\n"
        "class Runner:\n"
        "    def run(self):\n"
        "        import pipe_in_generator.guard_hook\n",
        encoding="utf-8",
    )
    assert role_problems(gen, FAKE_KINDS) == []
    # 空振りでない：関数の中の5件は読めている
    edges = [e for e in _edges(gen, FAKE_KINDS) if e.target_role == "tool"]
    assert {(e.line, e.inside) for e in edges} == {(7, True), (8, True), (10, True), (15, True), (20, True)}


# ---- D0100-AC-06：一覧とファイルの食い違い ------------------------------------------------------------


def test_d0100_ac06_直下の一覧に無いpyを一覧に足す案内つきで見つける_守る(tmp_path):
    """D0100-AC-06: 今の作りのままで通る。一覧に無い .py を直下（extra.py）に置くと、パスと直し方（GENERATOR_KINDS に足す・地図にも書く）つきで見つける。"""
    gen = _fake_generator(tmp_path)
    (gen / "extra.py").write_text("from .cli import main\n", encoding="utf-8")
    problems = role_problems(gen, FAKE_KINDS)
    assert problems == [
        "generator/extra.py がどちらの役の一覧にもありません。tests/test_repo_map.py の GENERATOR_KINDS に"
        "「作る」か「プラグイン」で足し、docs/development/design.md の「リポジトリの地図」の箇条書きにも書いてください（D0099・D0100）"
    ], _show(problems)


NESTED = [
    ("sub/x.py", ["sub/x.py"]),
    ("sub/__init__.py", ["sub/__init__.py"]),
    ("a/b/c.py", ["a/b/c.py"]),
]


@pytest.mark.parametrize("rel,expected", NESTED, ids=["下のフォルダのpy", "下のフォルダのinit", "深いフォルダのpy"])
def test_d0100_ac06_下のフォルダのpyを分けない決まりの案内つきで見つける_守る(tmp_path, rel, expected):
    """D0100-AC-06: 今の作りのままで通る。下のフォルダ（templates/・schemas/ を除く）に .py を置くと、一覧に足す案内でなく、下位パッケージに分けない決まり（D0100）の案内で見つける。"""
    gen = _fake_generator(tmp_path)
    path = gen / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("from pipe_in_generator import guard_hook\n", encoding="utf-8")
    problems = role_problems(gen, FAKE_KINDS)
    assert problems == [
        f"generator/{e} が下のフォルダにあります。generator/ は下位パッケージに分けないと決めました（D0100）。分け直すなら決定の記録を書いてからにしてください"
        for e in expected
    ], _show(problems)
    assert all("GENERATOR_KINDS" not in p for p in problems)


def test_d0100_ac06_一覧にあってファイルが無い名前を見つける_守る(tmp_path):
    """D0100-AC-06: 今の作りのままで通る。一覧にあってファイルが無い名前を、消す案内つきで見つける。"""
    gen = _fake_generator(tmp_path)
    assert role_problems(gen, {**FAKE_KINDS, "gone.py": "作る"}) == [
        "generator/gone.py が GENERATOR_KINDS にありますが、ファイルがありません。GENERATOR_KINDS と地図の箇条書きから消してください（D0099・D0100）"
    ]


def test_d0100_ac06_役の名前が分からない品を見つける_守る(tmp_path):
    """D0100-AC-06: 今の作りのままで通る。一覧の品の名前が「作る」でも「プラグイン」でもないと見つける（どちらの役にも入れない）。"""
    gen = _fake_generator(tmp_path)
    (gen / "render.py").write_text("from .guard_hook import decide\n", encoding="utf-8")
    assert role_problems(gen, {**FAKE_KINDS, "render.py": "開発用"}) == [
        "generator/render.py の品「開発用」は、作るかプラグインのどちらかにしてください（GENERATOR_KINDS）"
    ]


def test_d0100_ac06_initとpycacheとtemplatesとschemasは数えない_守る(tmp_path):
    """D0100-AC-06: 今の作りのままで通る。直下の __init__.py・__pycache__ の中・templates/ と schemas/ の下の .py は、一覧に無くても数えない。"""
    gen = _fake_generator(tmp_path)
    (gen / "__init__.py").write_text("from . import guard_hook\n", encoding="utf-8")
    stray = {
        "__pycache__/stray.py": "from pipe_in_generator import cli\n",
        "templates/spec-review/scaffold.py": "from pipe_in_generator import cli\n",
        "templates/__init__.py": "",
        "schemas/check.py": "import json\n",
        "sub/__pycache__/y.py": "import json\n",
    }
    for rel, text in stray.items():
        path = gen / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    problems = role_problems(gen, FAKE_KINDS)
    assert problems == [], _show(problems)
    assert set(_generator_files(gen)) == set(FAKE_KINDS)
    assert _nested_files(gen) == []


# ---- D0100-AC-07：決定の記録 --------------------------------------------------------------------------


def _decision_record() -> str:
    found = sorted(DECISIONS.glob("D0100-*.md"))
    assert found, "D0100 の決定の記録がありません（docs/decisions/D0100-<名前>.md）"
    assert len(found) == 1, [p.name for p in found]
    return found[0].read_text(encoding="utf-8")


def test_d0100_ac07_決定の記録に選んだ案と選ばなかった案と分け直す条件がある():
    """D0100-AC-07: 決定の記録 D0100-*.md がちょうど1つあり、「決めたことと理由」に、分けない案・何もしない案・下位パッケージに分ける案・分け直す条件・止めない失敗・packages がある。"""
    reason = section(_decision_record(), "決めたことと理由")
    assert reason, "D0100 の決定の記録に「## 決めたことと理由」がありません"
    for word in ("分けない", "何もしない", "下位パッケージ", "分け直す", "止めない失敗", "packages"):
        assert word in reason, f"D0100 の「決めたことと理由」に「{word}」がありません"


def test_d0100_ac07_決定の記録の一覧にD0100の行がある():
    """D0100-AC-07: 決定の記録の一覧 docs/decisions/README.md に D0100 の行がある。"""
    lines = (DECISIONS / "README.md").read_text(encoding="utf-8").splitlines()
    assert any(line.startswith("| [D0100](D0100-") for line in lines), "docs/decisions/README.md に D0100 の行がありません"


# ---- D0100-AC-08：design.md ---------------------------------------------------------------------------


def test_d0100_ac08_本体の依存の向きに役の向きと検査のファイルがある():
    """D0100-AC-08: design.md の「## 本体の依存の向き」の節に、作ると裏の道具の向きの文（入口 cli.py）と、検査のファイルの名前（実在する）がある。"""
    body = section(DESIGN_MD.read_text(encoding="utf-8"), "本体の依存の向き")
    assert body, "design.md に「## 本体の依存の向き」がありません"
    assert THIS_FILE in body, f"「本体の依存の向き」に {THIS_FILE} がありません"
    assert (ROOT / THIS_FILE).is_file()
    for word in ("作る", "裏の道具", "cli.py"):
        assert word in body, f"「本体の依存の向き」に「{word}」がありません"
