"""README を入口にし、くわしい説明を docs/guide/ に移す（D0014）：README の形・ガイドの文書・情報を落とさない・リンクと画像・名指しの直し・決定の記録。

文書は読むだけで書かない（偽の文書は tmp_path に作る）。SDK は呼ばない。
前の名前は、この文書に直接書かない（tests/test_rename.py の一覧に無いファイルなので）。要るときは test_readme.OLD でつないで作る。
補助の関数は tests/test_readme.py のものを使う（test_showcase.py が test_rules を import するのと同じ形）。
"""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote

import pytest

import test_headless_audit
from test_readme import (
    IMAGES,
    OLD,
    _picture_problems,
    _used_names,
    alerts,
    anchors,
    code_blocks,
    github_anchor,
    headings,
    pictures,
    section,
    text_outside_code,
    top_part,
)

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
GUIDE = ROOT / "docs" / "guide"
GUIDE_DOCS = [
    "README.md",
    "usage.md",
    "vscode.md",
    "pipes.md",
    "plugin.md",
    "safety.md",
    "records.md",
    "config.md",
    "migrate.md",
    "develop.md",
]
MIGRATION_TITLE = f"{OLD} から移る"
README_SECTIONS = ["すぐ試す", "文書", MIGRATION_TITLE, "ライセンス"]
MAX_README_LINES = 120


# ---- 補助 ------------------------------------------------------------------


def read_doc(path: Path) -> str:
    if not path.is_file():
        pytest.fail(f"{path.relative_to(ROOT).as_posix()} が無い")
    return path.read_text(encoding="utf-8")


def all_docs() -> list[Path]:
    """リポジトリの README.md と、ガイドの文書の全部（まだ無いものも並べる）。"""
    return [README] + [GUIDE / name for name in GUIDE_DOCS]


def combined() -> str:
    """README とガイドのうち、あるものの中身をつないだもの（「README かガイドのどれかに残る」の検査で使う）。"""
    return "\n".join(p.read_text(encoding="utf-8") for p in all_docs() if p.is_file())


def combined_headings() -> set[str]:
    return {title for p in all_docs() if p.is_file() for _, title in headings(p.read_text(encoding="utf-8"))}


def all_code_lines(md: str) -> list[str]:
    """``` で囲まれた中の行（言語の有無と字下げを問わない）を、前後の空白を除いて返す。空の行は除く。"""
    out = []
    in_code = False
    for line in md.splitlines():
        if line.lstrip().startswith("```"):
            in_code = not in_code
            continue
        if in_code and line.strip():
            out.append(line.strip())
    return out


LINK = re.compile(r"\]\(([^)\s]+)\)|href=\"([^\"]*)\"")
INLINE_CODE = re.compile(r"`[^`\n]*`")


def links(md: str) -> list[str]:
    """](…) と href="…" の行き先を、文書の順に。囲みのコードとインラインのコードの中は見ない。外の URL は除く。"""
    text = INLINE_CODE.sub("", text_outside_code(md))
    out = []
    for m in LINK.finditer(text):
        target = m.group(1) if m.group(1) is not None else m.group(2)
        if target.startswith(("http://", "https://", "mailto:")):
            continue
        out.append(target)
    return out


def link_problems(doc: Path, root: Path) -> list[str]:
    """文書の中のリンクのうち、行き先のファイル・フォルダ・アンカーが無いもの、root の外へ出るもの。"""
    md = doc.read_text(encoding="utf-8")
    base = root.resolve()
    problems = []
    for target in links(md):
        path, _, anchor = unquote(target).partition("#")
        if not path:
            if anchor not in anchors(md):
                problems.append(f"{doc.name}: {target}")
            continue
        dest = (doc.parent / path).resolve()
        if not dest.is_relative_to(base) or not dest.exists():
            problems.append(f"{doc.name}: {target}")
            continue
        if anchor and dest.is_file() and dest.suffix == ".md":
            if anchor not in anchors(dest.read_text(encoding="utf-8")):
                problems.append(f"{doc.name}: {target}")
    return problems


def link_paths(md: str) -> set[str]:
    """リンクの行き先のパスの部分（# の前）。"""
    return {unquote(t).partition("#")[0] for t in links(md)}


# ---- 固める一覧（移す前の README.md から書き写したもの） --------------------------------------

# 移す前の README の ## と ### の見出し（上から）
OLD_HEADINGS = [
    "すぐ試す",
    "必要なもの",
    "入れる",
    "最初の1回",
    "使い方",
    "開発フローの流れ",
    "流す",
    "途中から再開する",
    "確認の画面",
    "確認で止めて、あとから答える（チャットから動かすとき）",
    "記録だけを書く（`pipe-in record`）",
    "Claude Code で開発するとき",
    "VSCode の拡張",
    "実行を見る",
    "パイプ作業台",
    "パイプ（目的に合わせた段の並び）",
    "Claude Code のプラグイン",
    "ひな形",
    "見本のパイプ",
    "定義の書き方（`pipe.toml`）",
    "検証と差し戻し",
    "分岐・飛び先・並列",
    "Agent SDK の設定",
    "安全のしくみ",
    "段ごとの役割と書き込める範囲",
    "どの段でも止める操作",
    "記録と使用量",
    "作られるファイル",
    "まとめに出る使用量",
    "設定（pipeline.toml）",
    "終了コード",
    MIGRATION_TITLE,
    "中身を直したいとき",
    "注意",
    "ライセンス",
]

# 移す前の README の <summary> の文（「書き方の例」は2つあるが1つとして）
OLD_SUMMARIES = [
    "コマンドの一覧",
    "<code>pipe-in-gen new</code> が見るもの",
    "書き方の例",
    "節ごとの中身",
]

# 移す前の README のコードブロックの中の、空でない行（前後の空白を除く）
OLD_CODE_LINES = [
    # すぐ試す › 入れる
    "# リポジトリを手元に写す",
    "git clone https://github.com/nigoh/pipe-in.git",
    "cd pipe-in",
    "# 仮想環境を作る",
    "python -m venv .venv",
    "# 仮想環境に入る（どちらか1つ）",
    ". .venv/Scripts/activate        # Windows の Git Bash",
    "source .venv/bin/activate       # macOS / Linux",
    "# 入れる",
    "pip install -e .                # pipe-in と pipe-in-gen が入る",
    # すぐ試す › 最初の1回
    "# 対象のプロジェクトで、要件メモから開発フローを流す",
    'pipe-in --project ~/src/myapp --text "ユーザー一覧に CSV 出力ボタンを追加したい"',
    # 開発フローの流れ
    "要件メモ ─▶ 要件定義 ─[確認]─▶ 設計 ─[確認]─▶ テスト先行（赤）─[確認]─▶ 実装（緑・整理）─▶ 検証 ─▶ 合格",
    "▲                │",
    "└──── 不合格 ────┘（最大3回）",
    # 流す
    "# 要件メモをファイルで渡す",
    "pipe-in --project ~/src/myapp --input request.md",
    "# 直接書く",
    'pipe-in --project ~/src/myapp --text "ユーザー一覧に CSV 出力ボタンを追加したい"',
    "# 確認なしで最後まで流す",
    "pipe-in --project ~/src/myapp --input request.md --yes",
    "# テスト担当の判定に加えて、自分のテストコマンドでも裏付けを取る",
    'pipe-in --project ~/src/myapp --input request.md --test-cmd "pytest -q"',
    # 途中から再開する
    "pipe-in --project ~/src/myapp --from design      # 要件定義書を手で直したあと",
    "pipe-in --project ~/src/myapp --from red         # 設計書を手で直したあと",
    "pipe-in --project ~/src/myapp --from implement   # 先に書いたテストを手で直したあと",
    "pipe-in --project ~/src/myapp --from test        # 検証だけやり直す",
    # 確認で止めて、あとから答える
    'pipe-in --project ~/src/myapp --input request.md --pause --test-cmd "pytest -q"   # 要件定義のあとで止まる',
    'pipe-in --project ~/src/myapp --review approve --test-cmd "pytest -q"             # 承認 → 設計のあとで止まる',
    'pipe-in --project ~/src/myapp --review revise --feedback "AC-03 を分けて"          # 同じ会話のまま直させ、また止まる',
    "pipe-in --project ~/src/myapp --review quit                                       # 中止",
    # 記録だけを書く
    'pipe-in record start --text "要件メモ"            # 00_input.md と空の記録（途中の記録があれば断る。終わった記録は archive/ へ）',
    "pipe-in record begin requirements                 # 段を始める（拡張に「動いている」と出る）",
    'pipe-in record done requirements --summary "…"    # 段を閉じる',
    "pipe-in record wait requirements                  # 確認待ち",
    'pipe-in record review requirements approved       # revise --feedback "…" / quit',
    'pipe-in record red red --summary "…"              # テスト先行の結果',
    'pipe-in record verdict pass --attempt 1 --summary "…"   # 検証の判定',
    "pipe-in record finish PASSED                      # 記録を閉じる",
    # Claude Code で開発するとき
    'claude -p "/pipe-audit <範囲>" --max-budget-usd 5 --permission-mode dontAsk '
    '--tools "Agent,Read,Grep,Glob" --allowedTools "Agent(pipe-in-auditor)" Read Grep Glob',
    'claude -p "/pipe-advise <テーマ>" --max-budget-usd 5 --permission-mode dontAsk '
    '--tools "Agent,Read,Grep,Glob,WebFetch,WebSearch" --allowedTools "Agent(pipe-in-advisor)" Read Grep Glob WebSearch '
    '"WebFetch(domain:code.claude.com)" "WebFetch(domain:docs.claude.com)" "WebFetch(domain:docs.anthropic.com)" '
    '"WebFetch(domain:platform.claude.com)" "WebFetch(domain:github.com)" "WebFetch(domain:raw.githubusercontent.com)"',
    # VSCode の拡張
    "# 拡張を作って、普段の VSCode に入れる",
    "cd vscode",
    "npm install",
    "npm run package                                        # pipe-in-vscode.vsix ができる",
    "code --install-extension pipe-in-vscode.vsix --force",
    # パイプ（置き場所の図）
    "~/src/myapp/                対象プロジェクト",
    "└─ .pipe-in/pipes/         作ったパイプ（1パイプ＝1フォルダ）",
    "└─ pipe-in-diagrams/",
    "├─ pipe.toml         段の並び・書き込める範囲・確認の有無",
    "├─ prompts/          段ごとの指示文",
    "└─ README.md         何をするパイプか・流し方",
    "pipe-in のリポジトリ",
    "├─ generator/              ジェネレーター（環境の検出・ひな形・パイプの生成と検査）",
    "│  └─ templates/           ひな形（dev / diagrams / spec-qa）",
    "└─ plugin/                 Claude Code のプラグイン（/pipe-in:pipe-build と pipe-builder）",
    # パイプ（コマンド）
    "pipe-in-gen list --project ~/src/myapp                          # ひな形と、作ったパイプの一覧",
    "pipe-in-gen new diagrams --from diagrams --project ~/src/myapp  # ひな形から .pipe-in/pipes/pipe-in-diagrams/ を作る",
    'pipe-in-gen design apidoc --purpose "ソースから API の文書を作り、突き合わせたい" --project ~/src/myapp',
    "# 目的から段を組んで作る（Claude が設計する）",
    "pipe-in-gen check diagrams --project ~/src/myapp                # 定義の誤りを調べる",
    'pipe-in --pipe diagrams --project ~/src/myapp --text "注文の流れを中心に"   # 作ったパイプを流す',
    # パイプ（出力の例）
    "$ pipe-in-gen new diagrams --from diagrams",
    "✓ <対象>/.pipe-in/pipes/pipe-in-diagrams を作りました（ひな形: diagrams）",
    "見つけた環境: 言語 python・テスト pytest -q・ソース src・文書 docs",
    "✓ パイプ「diagrams」: 問題ありません",
    "中身は自由に直せます（段の並び・権限・確認は pipe.toml、指示は prompts/）。直したら pipe-in-gen check で確かめてください。",
    '流す: pipe-in --pipe diagrams --project <対象のフォルダ> [--text "依頼メモ"]',
    "$ pipe-in-gen check diagrams",
    "✓ パイプ「diagrams」: 問題ありません",
    # Claude Code のプラグイン
    "/plugin marketplace add <pipe-in のリポジトリのフォルダか GitHub の nigoh/pipe-in>",
    "/plugin install pipe-in@pipe-in",
    # 定義の書き方（pipe.toml）
    "[pipe]",
    'kind = "linear"            # "linear"（下の段を順に流す）か "dev"（組み込みの開発フロー）',
    'label = "ソースから図を作る"',
    'input = "optional"         # 依頼メモが required / optional / none',
    "[[stages]]",
    'name = "survey"            # 英小文字・数字・-',
    'label = "ソースの調査"',
    'output = "01_survey.md"    # 成果物（記録の置き場所の中のファイル名）',
    'access = "read"            # 書き込める範囲の型（下の表）',
    "review = true              # この段のあとで人の確認を取る",
    'prompt_file = "prompts/01_survey.md"   # パイプのフォルダの中。短ければ prompt = "..." で直接書いてもよい',
    "# bash = true              # Bash を使わせる（危ない操作はいつも止める）",
    '# writes = ["src/api/**"]  # docs / tests / code の範囲を、さらに場所で絞る（* は / もまたぐ）',
    '# web = true               # WebFetch と WebSearch を使わせる。web = ["docs.python.org"] ならそのドメインへの WebFetch だけ',
    '# mcp = ["mcp__jira__get_issue", "mcp__figma__*"]   # 使わせる MCP の道具（サーバーの名前は必ず書く）',
    '# model = "sonnet" / max_turns = 100 / max_budget_usd = 1.0',
    # 検証と差し戻し
    "[[stages]]",
    'name = "verify"',
    "# ...",
    "[stages.check]",
    "verdict = true                 # 段に pass / fail と直す点（problems）を返させる",
    'command = "python -m pytest -q tests/test_docs.py"   # pipe-in が流す確認用のコマンド（終了コード 0 で合格）',
    'on_fail = "draw"               # 不合格のときに戻す段（自分か前の段。省くと自分）',
    "max_retries = 2                # 戻す回数の上限。超えたら終了コード 1",
    # 分岐・飛び先・並列（書き方の例）
    "[[stages]]",
    'name = "classify"',
    "# ...",
    '[stages.routes]                # 段に choice を返させ、行き先を選ぶ（"end" で終わり）',
    'api = "api-doc"',
    'ui = "ui-doc"',
    'none = "end"',
    "[[stages]]",
    'name = "api-doc"',
    'next = "report"                # 次の段を決める（"end" で終わり）。省くと定義の次の段',
    "# ...",
    "[[stages]]",
    'name = "flow"',
    'group = "draw"                 # 同じ group の続いた段は同時に流す',
    "# ...",
    "[[stages]]",
    'name = "sequence"',
    'group = "draw"',
    # Agent SDK の設定（書き方の例）
    "[[stages]]",
    'name = "survey"',
    "# ...",
    'permission_mode = "plan"          # default / acceptEdits / plan（確認を省くモードは安全のため使えません）',
    "max_thinking_tokens = 16000       # 考える量",
    'fallback_model = "sonnet"         # 予備のモデル',
    'system_append = "表を使って書く"   # この段の決まり（system prompt に足す）',
    'add_dirs = ["../shared-docs"]     # 追加で読めるフォルダ（プロジェクトからの相対パス。書き込みはできない）',
    'mcp = ["mcp__jira__get_issue"]    # 使う MCP の道具',
    "[stages.agents.module-reader]     # サブエージェント",
    'description = "1つのモジュールを読んで要点を返す"',
    'prompt = "渡されたモジュールだけを読む"',
    'tools = ["Read", "Grep"]          # 段で使える道具の範囲だけ（Task・Agent・PowerShell は不可）',
    'model = "haiku"',
    "[stages.mcp_servers.jira]         # この段だけで使う MCP サーバー",
    'type = "http"                     # stdio（command・args）/ http・sse（url）',
    'url = "https://mcp.example.com/jira"',
    # 設定（pipeline.toml）
    "[pipeline]",
    'work_dir = "docs/pipeline"',
    "max_retries = 3                 # 実装への差し戻しの上限（3 なら実装は最大4回）",
    'test_command = "pytest -q"      # テストの段のあとに実行する確認用コマンド（任意）',
    "[stages.requirements]",
    'model = "opus"                  # 段ごとにモデルを変えられる',
    "max_turns = 40",
    "max_budget_usd = 1.0            # 段ごとの費用の上限（概算）",
    "[stages.implement]",
    'model = "sonnet"',
    # 前の名前から移る
    "cd <リポジトリ>",
    f"pip uninstall {OLD}",
    "pip install -e '.[dev]'",
    f"/plugin marketplace remove {OLD}",
    "/plugin marketplace add nigoh/pipe-in",
    "/plugin install pipe-in@pipe-in",
    "cd <対象>",
    "mkdir -p .pipe-in/pipes",
    f"git mv .{OLD}/pipes/{OLD}-<名前> .pipe-in/pipes/pipe-in-<名前>",
    "git remote set-url origin https://github.com/nigoh/pipe-in.git",
    # 中身を直したいとき
    "# テストを流す（SDK を呼ばずに、段の順番・確認・差し戻し・書き込み制限を確かめる）",
    "pip install -e '.[dev]' && pytest",
]

# 移す前の README のコマンドの行（D0009-AC-07 の一覧と、claude -p の2行。test_readme.py から移した）
COMMANDS = [
    "pipe-in --project ~/src/myapp --input request.md",
    'pipe-in --project ~/src/myapp --text "ユーザー一覧に CSV 出力ボタンを追加したい"',
    "pipe-in --project ~/src/myapp --input request.md --yes",
    'pipe-in --project ~/src/myapp --input request.md --test-cmd "pytest -q"',
    "python -m pipe_in",
    "pipe-in --project ~/src/myapp --from design",
    "pipe-in --project ~/src/myapp --from red",
    "pipe-in --project ~/src/myapp --from implement",
    "pipe-in --project ~/src/myapp --from test",
    'pipe-in --project ~/src/myapp --input request.md --pause --test-cmd "pytest -q"',
    'pipe-in --project ~/src/myapp --review approve --test-cmd "pytest -q"',
    'pipe-in --project ~/src/myapp --review revise --feedback "AC-03 を分けて"',
    "pipe-in --project ~/src/myapp --review quit",
    'pipe-in record start --text "要件メモ"',
    "pipe-in record begin requirements",
    'pipe-in record done requirements --summary "…"',
    "pipe-in record wait requirements",
    "pipe-in record review requirements approved",
    'pipe-in record red red --summary "…"',
    'pipe-in record verdict pass --attempt 1 --summary "…"',
    "pipe-in record finish PASSED",
    "pipe-in-gen list --project ~/src/myapp",
    "pipe-in-gen new diagrams --from diagrams --project ~/src/myapp",
    'pipe-in-gen design apidoc --purpose "ソースから API の文書を作り、突き合わせたい" --project ~/src/myapp',
    "pipe-in-gen check diagrams --project ~/src/myapp",
    'pipe-in --pipe diagrams --project ~/src/myapp --text "注文の流れを中心に"',
    "/plugin marketplace add <pipe-in のリポジトリのフォルダか GitHub の nigoh/pipe-in>",
    "/plugin install pipe-in@pipe-in",
    "pip install -e .",
    "pip install -e '.[dev]' && pytest",
    f"pip uninstall {OLD}",
    "pip install -e '.[dev]'",
    f"/plugin marketplace remove {OLD}",
    "/plugin marketplace add nigoh/pipe-in",
    f"code --uninstall-extension nok.{OLD}-vscode",
    "mkdir -p .pipe-in/pipes",
    f"git mv .{OLD}/pipes/{OLD}-<名前> .pipe-in/pipes/pipe-in-<名前>",
    "git remote set-url origin https://github.com/nigoh/pipe-in.git",
    'claude -p "/pipe-audit',
    'claude -p "/pipe-advise',
]

# 移す前の README の表の行の頭の項目（D0009-AC-08 の一覧。test_readme.py から移した）
TABLE_ITEMS = [
    # 作られるファイル
    "`00_input.md`", "`01_requirements.md`", "`02_design.md`", "`03_red_tests.md`", "`04_implementation.md`",
    "`05_test_report.md`", "`99_summary.md`", "`state.json`", "`logs/*.jsonl`",
    # 段ごとの役割と書き込める範囲
    "要件定義", "設計", "テスト先行", "実装", "検証",
    # access
    "`read`", "`docs`", "`tests`", "`code`",
    # pipeline.toml のほかの項目
    "`domain_dir`", "`setting_sources`", "`protected_paths`", "`extra_test_globs`",
    # 終了コード
    "0", "1", "2", "3", "4", "5", "130",
    # まとめに出る使用量
    "トークンの内訳", "モデル別", "環境", "利用枠",
    # プラグインで入るもの
    "スキル `/pipe-in:pipe-build`", "エージェント `pipe-builder`", "フック（`pipe-in-gen guard-hook`）",
    # ひな形
    "`dev`", "`diagrams`", "`spec-qa`",
    # 中身を直したいとき
    "開発フローの各段への指示（文書の構成、守ること）",
    "開発フローの段の順番、確認、差し戻しの流れ",
    "開発フローの段ごとのツールと書き込み範囲",
    "どのパイプにも共通の流れ（記録・確認・まとめ）",
    "止める操作",
    "SDK の呼び出し",
    "パイプの読み込み・検査・流れ・権限の型",
    "パイプの生成・環境の検出・ひな形",
]


# ---- D0014-AC-01〜06: README を短くする ------------------------------------------------------


def test_D0014_AC_01_READMEの節は決めた4つの並び():
    """D0014-AC-01: README の ## の見出しを上から並べると、すぐ試す・文書・前の名前から移る・ライセンス の4つと一致する。"""
    assert [t for d, t in headings(read_doc(README)) if d == 2] == README_SECTIONS


def test_D0014_AC_01_目次はREADMEの節のアンカーの並び():
    """D0014-AC-01: 冒頭の「**目次**」の行のリンクが、README の4つの節のアンカーの並び（移行の節は #migrate）と同じ。"""
    toc = next((line for line in top_part(read_doc(README)).splitlines() if line.startswith("**目次**")), None)
    assert toc is not None, "冒頭に「**目次**」の行が無い"
    expected = ["migrate" if t == MIGRATION_TITLE else github_anchor(t) for t in README_SECTIONS]
    assert [unquote(a) for a in re.findall(r"\]\(#([^)\s]+)\)", toc)] == expected


def test_D0014_AC_02_冒頭はロゴ_一文_パネル_要点_目次の順():
    """D0014-AC-02: 最初の ## の前に、ロゴの <picture> → 一文 → パネルの <picture> → ガイドを指す要点の箇条書き → 目次、がこの順にある。"""
    top = top_part(read_doc(README))
    pics = pictures(top)
    logo = next((p for p in pics if "pipe-in-logo" in p["src"]), None)
    panel = next((p for p in pics if "run-panel-" in p["src"]), None)
    assert logo is not None, "冒頭にロゴの <picture> が無い"
    assert panel is not None, "冒頭にパネルの画像の <picture> が無い"
    sentence = re.search(r"^pipe-in は.*要件定義 → 設計 → テスト先行 → 実装 → 検証", top, re.M)
    assert sentence is not None, "冒頭に「pipe-in は、要件メモから 要件定義 → … → 検証 …」の一文が無い"
    bullet = re.search(r"^- .*\]\(docs/guide/", top, re.M)
    assert bullet is not None, "冒頭に、docs/guide/ の文書へのリンクのある要点の箇条書きが無い"
    toc = re.search(r"^\*\*目次\*\*", top, re.M)
    assert toc is not None, "冒頭に「**目次**」の行が無い"
    assert logo["end"] <= sentence.start() < panel["start"], "ロゴ → 一文 → パネルの画像 の順になっていない"
    assert panel["end"] <= bullet.start() < toc.start(), "パネルの画像 → 要点 → 目次 の順になっていない"


def test_D0014_AC_03_要点は5から7項目でどれもガイドの実在する文書を指す():
    """D0014-AC-03: 冒頭の要点は5〜7項目で、どの項目にも docs/guide/ の文書へのリンクがあり、そのファイルが実在する。"""
    points = [line for line in top_part(read_doc(README)).splitlines() if line.startswith("- ")]
    assert 5 <= len(points) <= 7, points
    problems = []
    for p in points:
        targets = [t for t in link_paths(p) if t.startswith("docs/guide/")]
        if not targets:
            problems.append(f"ガイドへのリンクが無い: {p}")
        problems += [f"無いファイル: {t}" for t in targets if not (ROOT / t).is_file()]
    assert problems == []


def test_D0014_AC_04_READMEは120行以下():
    """D0014-AC-04: README の行数が 120 行以下。"""
    n = len(read_doc(README).splitlines())
    assert n <= MAX_README_LINES, f"README が {n} 行ある"


def test_D0014_AC_05_すぐ試すに利用料のIMPORTANTのアラートがある():
    """D0014-AC-05: README の「すぐ試す」の中に、利用料がかかることの > [!IMPORTANT] のアラートがある（順は test_readme.py::test_d0009_ac10_quick_start_order）。"""
    sec = section(read_doc(README), "すぐ試す")
    assert sec, "## すぐ試す が無い"
    assert any(kind == "IMPORTANT" and "利用料" in body for kind, body in alerts(sec)), alerts(sec)


def test_D0014_AC_06_文書の節にガイドの全部と拡張_開発のルール_決定の記録へのリンクがある():
    """D0014-AC-06: README の「文書」の節に、docs/guide/ のすべての文書と vscode/README.md・docs/development/・docs/decisions/ へのリンクがある。"""
    sec = section(read_doc(README), "文書")
    assert sec, "README に ## 文書 が無い"
    have = link_paths(sec)
    want = [f"docs/guide/{name}" for name in GUIDE_DOCS] + ["vscode/README.md", "docs/development/", "docs/decisions/"]
    assert [w for w in want if w not in have] == []


# ---- D0014-AC-07・08: docs/guide/ の文書 ------------------------------------------------------


@pytest.mark.parametrize("name", GUIDE_DOCS)
def test_D0014_AC_07_ガイドの文書がそろい1行目が見出し(name):
    """D0014-AC-07: docs/guide/ に決めた文書があり、1行目が # の見出し。"""
    first = read_doc(GUIDE / name).splitlines()[:1]
    assert first and first[0].startswith("# "), first


def test_D0014_AC_08_目次からガイドの全部の文書へ行けて余分な文書が無い():
    """D0014-AC-08: docs/guide/README.md からガイドのほかの文書すべてへリンクがあり、docs/guide/*.md は決めた文書だけ。"""
    have = link_paths(read_doc(GUIDE / "README.md"))
    assert [n for n in GUIDE_DOCS if n != "README.md" and n not in have] == []
    assert sorted(p.name for p in GUIDE.glob("*.md")) == sorted(GUIDE_DOCS)


# ---- D0014-AC-09〜14: 情報を落とさない ----------------------------------------------------------


@pytest.mark.parametrize("title", OLD_HEADINGS)
def test_D0014_AC_09_前の見出しがREADMEかガイドに残る(title):
    """D0014-AC-09: 移す前の README の ## ・### の見出しが、README かガイドのどれかの見出しとして（深さは問わず）残る。"""
    assert title in combined_headings()


@pytest.mark.parametrize("summary", OLD_SUMMARIES)
def test_D0014_AC_09_前のsummaryが残る(summary):
    """D0014-AC-09: 移す前の README の <summary> の文が、README かガイドに残る。"""
    assert f"<summary>{summary}</summary>" in combined()


@pytest.mark.parametrize("command", COMMANDS)
def test_D0014_AC_10_前のコマンドがREADMEかガイドに残る(command):
    """D0014-AC-10: 移す前の README のコマンドの行が、README かガイドに残る。"""
    assert command in combined()


@pytest.mark.parametrize("item", TABLE_ITEMS)
def test_D0014_AC_11_前の表の項目がREADMEかガイドの表に残る(item):
    """D0014-AC-11: 移す前の README の表の行の頭の項目が、README かガイドの表に残る。"""
    assert re.search(rf"^\|\s*{re.escape(item)}\s*\|", combined(), re.M), item


def test_D0014_AC_12_前のコードブロックの行がREADMEかガイドのコードブロックに残る():
    """D0014-AC-12: 移す前の README のコードブロックの中の行が、README かガイドのコードブロックの中にすべて残る。"""
    have = {line for p in all_docs() if p.is_file() for line in all_code_lines(p.read_text(encoding="utf-8"))}
    assert sorted(set(OLD_CODE_LINES) - have) == []


def test_D0014_AC_12_コードの行の拾い方は字下げした囲みも言語なしも拾う():
    """D0014-AC-12: all_code_lines そのものが、言語なし・言語あり・字下げした ``` の中の行を拾い、外の行と空の行は拾わない。"""
    md = "外\n```\n  a  \n\n```\n1. 手順\n\n   ```bash\n   b\n   ```\n```toml\nc = 1\n```\n外2\n"
    assert all_code_lines(md) == ["a", "b", "c = 1"]


def test_D0014_AC_13_アラートが3つ以上で概算_pipe_inのコミット_yesがある():
    """D0014-AC-13: README とガイドを合わせてアラートが3つ以上あり、「概算」「.pipe-in/ をコミットの前に見る」「--yes」がそれぞれアラートの中にある。"""
    found = [a for p in all_docs() if p.is_file() for a in alerts(p.read_text(encoding="utf-8"))]
    assert len(found) >= 3, found
    bodies = [body for _, body in found]
    assert any("概算" in b for b in bodies), "費用が概算であることのアラートが無い"
    assert any(".pipe-in/" in b and "コミット" in b for b in bodies), ".pipe-in/ をコミットの前に見るアラートが無い"
    assert any("--yes" in b for b in bodies), "--yes のアラートが無い"


def python_project(tmp_path: Path) -> Path:
    project = tmp_path / "myapp"
    (project / "src").mkdir(parents=True)
    (project / "docs").mkdir()
    (project / "pyproject.toml").write_text(
        '[project]\nname = "myapp"\n[project.optional-dependencies]\ndev = ["pytest>=8"]\n', encoding="utf-8"
    )
    return project


def _normalize(out: str, project: Path) -> list[str]:
    for p in {str(project), project.as_posix()}:
        out = out.replace(p, "<対象>")
    lines = [line.rstrip() for line in out.replace("\\", "/").splitlines()]
    while lines and not lines[-1]:
        lines.pop()
    return lines


def test_D0014_AC_14_パイプの文書のpipe_in_genの出力が本物と一致(tmp_path, monkeypatch, capsys):
    """D0014-AC-14: docs/guide/pipes.md の pipe-in-gen new / check の出力の例が、tmp_path で流した本物の出力と（手元のパスの置き換えを除いて）一致する。"""
    import os

    from pipe_in.pipe import definition as pd
    from pipe_in_generator import cli

    md = read_doc(GUIDE / "pipes.md")
    monkeypatch.delenv("PIPE_IN_PIPES_DIR", raising=False)
    monkeypatch.delenv(OLD.upper() + "_PIPES_DIR", raising=False)

    def fake_default() -> Path:
        env = pd.env_pipes_dir(os.environ)
        return Path(env) if env else tmp_path / "repo-pipes"

    monkeypatch.setattr(pd, "default_pipes_dir", fake_default)
    project = python_project(tmp_path).resolve()
    monkeypatch.chdir(project)

    blocks = [b for b in code_blocks(md, "text") if b and b[0].startswith("$ pipe-in-gen ")]
    assert [b[0][len("$ pipe-in-gen "):].strip() for b in blocks] == ["new diagrams --from diagrams", "check diagrams"]
    for block in blocks:
        argv = block[0][len("$ pipe-in-gen "):].split()
        capsys.readouterr()
        assert cli.main(argv) == 0, argv
        got = _normalize(capsys.readouterr().out, project)
        want = [line.rstrip() for line in block[1:]]
        while want and not want[-1]:
            want.pop()
        assert got == want, argv


# ---- D0014-AC-16〜20: リンクと画像 ----------------------------------------------------------------


@pytest.mark.parametrize("doc", all_docs(), ids=lambda p: p.relative_to(ROOT).as_posix())
def test_D0014_AC_16_17_文書の中のリンクとアンカーが切れていない(doc):
    """D0014-AC-16・17: README とガイドの中の相対リンクがすべて実在するファイルかフォルダを指し、アンカーが行き先の文書の見出しか <a id> に当たる。"""
    read_doc(doc)
    assert link_problems(doc, ROOT) == []


def test_D0014_AC_18_リンクの検査そのものが切れたリンクを見つけコードの中は見ない(tmp_path):
    """D0014-AC-18: link_problems が、無いアンカー・無いファイル・外へ出るパスを見つけ、囲みとインラインのコードの中と外の URL は見ない。"""
    a = tmp_path / "a.md"
    a.write_text(
        "## 自分\n\n"
        "[1](b.md#ok) [2](b.md#ng) [3](c.md) [4](#自分) [5](#無い) [6](sub/) [7](https://example.com/x.md)\n\n"
        "```\n[8](d.md)\n```\n\n"
        "`[9](e.md)` と <a href=\"#無い2\">x</a> と [10](../../外.md)\n",
        encoding="utf-8",
    )
    (tmp_path / "b.md").write_text("## ok\n", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    assert link_problems(a, tmp_path) == ["a.md: b.md#ng", "a.md: c.md", "a.md: #無い", "a.md: #無い2", "a.md: ../../外.md"]


def test_D0014_AC_19_READMEとガイドのpictureは明暗とalt_widthがあり実在し4枚を使う():
    """D0014-AC-19: README とガイドの <picture> はどれも暗い表示の <source> と alt・width のある <img> を持ち、指すファイルが実在し（ガイドからは ../assets/…）、パネルと作業台の明暗4枚がどこかで使われている。"""
    used: set[str] = set()
    problems = []
    for doc in all_docs():
        md = read_doc(doc)
        pics = pictures(md)
        resolve = (lambda ref, base=doc.parent: base / ref)
        problems += [f"{doc.name} {p}" for p in _picture_problems(pics, resolve)]
        if doc.parent == GUIDE:
            refs = [s["srcset"] for p in pics for s in p["sources"]] + [p["src"] for p in pics]
            problems += [f"{doc.name}: ../assets/ で始まらない {r!r}" for r in refs if not r.startswith("../assets/")]
        used |= _used_names(pics, resolve)
    assert problems == []
    assert sorted(set(IMAGES) - used) == []


def test_D0014_AC_19_ガイドのVSCodeの文書に作業台の明暗の画像がある():
    """D0014-AC-19: docs/guide/vscode.md に、作業台の明るい版（img の src）と暗い版（暗い表示の source）の <picture> がある。"""
    pics = pictures(read_doc(GUIDE / "vscode.md"))
    editor = [p for p in pics if p["src"] == "../assets/pipe-editor-light.png"]
    assert editor, "作業台の明るい版の <img> が無い"
    assert any(
        s["srcset"] == "../assets/pipe-editor-dark.png" and "prefers-color-scheme: dark" in s["media"]
        for p in editor
        for s in p["sources"]
    ), "作業台の暗い版の <source> が無い"


def test_D0014_AC_20_拡張のREADMEの移行へのリンクはガイドを指す():
    """D0014-AC-20: vscode/README.md に ../docs/guide/migrate.md へのリンクがあり、../README.md#migrate へのリンクが無い。"""
    md = read_doc(ROOT / "vscode" / "README.md")
    targets = links(md)
    assert "../docs/guide/migrate.md" in targets, targets
    assert "../README.md#migrate" not in targets


# ---- D0014-AC-21〜25: 名指しを直す ------------------------------------------------------------

NAMING = re.compile(r"README\s*の[「『]|README\s*の移行の節|README\.md\s*の[「『]")

# README の節を名指ししていたファイル（決定の記録を除く）
NAMING_FILES = [
    "CLAUDE.md",
    ".claude/skills/pipe-help/SKILL.md",
    ".claude/agents/pipe-in-auditor.md",
    ".claude/agents/pipe-in-coder.md",
    ".claude/agents/pipe-in-analyst.md",
    "docs/development/workflow.md",
    "docs/development/README.md",
    "docs/assets/README.md",
    "pipes/README.md",
    "plugin/skills/pipe-build/SKILL.md",
    "generator/templates/dev/README.md",
    "vscode/README.md",
]
# そのうち、移した先の docs/guide/ を書くもの（docs/development/README.md は「README の」と言っていないので言葉だけ直す）
GUIDE_NAMING_FILES = [f for f in NAMING_FILES if f != "docs/development/README.md"]


@pytest.mark.parametrize("name", NAMING_FILES)
def test_D0014_AC_21_READMEの節を名指しする言い方が残っていない(name):
    """D0014-AC-21: README の「〜」・README の移行の節・README.md の「〜」 と名指しする言い方が残っていない。"""
    lines = [line for line in read_doc(ROOT / name).splitlines() if NAMING.search(line)]
    assert lines == []


@pytest.mark.parametrize("name", GUIDE_NAMING_FILES)
def test_D0014_AC_21_名指しを直したファイルはガイドを書きそのパスが実在する(name):
    """D0014-AC-21: 名指しを直したファイルに docs/guide/ が書いてあり、そこに出る docs/guide/<名前>.md が実在する。"""
    text = read_doc(ROOT / name)
    has_guide = "docs/guide/" in text
    assert has_guide, f"{name} に docs/guide/ が書いてない"
    paths = set(re.findall(r"docs/guide/[\w-]+\.md", text))
    assert sorted(p for p in paths if not (ROOT / p).is_file()) == []


def test_D0014_AC_21_検査そのものが名指しを見つける():
    """D0014-AC-21: 名指しの検査そのものが、README の「パイプ」の節・README の移行の節・README.md の「使い方」を見つけ、README の画像・README.md・vscode/README.md は見逃す。"""
    for found in ["pipe-in の README の「パイプ」の節", "README の移行の節を参照", "README.md の「使い方」", "README の『使い方』"]:
        assert NAMING.search(found), found
    for missed in ["README の画像の撮り直し", "README.md・vscode/README.md", "pipes/README.md の該当する節"]:
        assert not NAMING.search(missed), missed


def test_D0014_AC_22_pipe_helpの答え方ともっと詳しくがガイドを案内する():
    """D0014-AC-22: /pipe-help の「答え方」と「もっと詳しく」の節のどちらにも docs/guide/ がある。"""
    text = read_doc(ROOT / ".claude" / "skills" / "pipe-help" / "SKILL.md")
    missing = [h for h in ("答え方", "もっと詳しく") if "docs/guide/" not in test_headless_audit.section(text, h)]
    assert missing == [], f"docs/guide/ が無い節: {missing}"


def test_D0014_AC_23_そろえる表の使い方の行にガイドがある():
    """D0014-AC-23: docs/development/workflow.md の「そろえる」の表の「使い方」の行に docs/guide/ がある。"""
    rows = [line for line in read_doc(ROOT / "docs" / "development" / "workflow.md").splitlines() if line.startswith("| 使い方")]
    assert rows, "「| 使い方」で始まる行が無い"
    assert any("docs/guide/" in r for r in rows), rows


def test_D0014_AC_24_置き場所の表にガイドの行がある():
    """D0014-AC-24: docs/development/design.md の置き場所の表に `docs/guide/` の行がある（パスの実在は tests/test_rules.py が見る）。"""
    rows = [line for line in read_doc(ROOT / "docs" / "development" / "design.md").splitlines() if line.startswith("|")]
    assert any("`docs/guide/`" in r for r in rows)


def test_D0014_AC_25_監査の対象にガイドがある():
    """D0014-AC-25: pipe-in-auditor.md の「対象」の節に docs/guide/ がある。"""
    text = read_doc(ROOT / ".claude" / "agents" / "pipe-in-auditor.md")
    has_guide = "docs/guide/" in test_headless_audit.section(text, "対象")
    assert has_guide, "pipe-in-auditor.md の「対象」の節に docs/guide/ が無い"


# ---- D0019-AC-76: VSCode のガイドに、新しい並び（一覧・タブ・時系列）を書く ------------------------------------


def test_D0019_AC_76_ガイドに新しい並びの説明がある():
    """D0019-AC-76: docs/guide/vscode.md に、実行の一覧が常に出ること・状態のタブと絞り込み・詳細のタブ・時系列・
    狭い幅の並び・セッション名（--name）の説明があり、「1 つだけのときは出ません」という前の版の文が残っていない。"""
    md = read_doc(GUIDE / "vscode.md")
    assert "1 つだけのときは出ません" not in md
    for word in ("時系列", "絞り込み", "セッション名", "セッション ID", "--name", "図と出力", "タブ", "狭い"):
        assert word in md, f"docs/guide/vscode.md に「{word}」の説明が無い"
    assert "実行がありません" in md or "0 件" in md, "run が 0 のときの一覧の説明が無い"


def test_D0019_AC_76_ガイドに全体の経過が詳細にあると書く():
    """D0019-AC-76: D0017-AC-18「バナーに全体の経過」は「詳細のメタに全体の経過」として満たす。ガイドの「時間と動き」が、
    全体の経過の場所を「パネルの上」でなく詳細の欄として書く。"""
    md = read_doc(GUIDE / "vscode.md")
    assert "パネルの上には全体の経過が出ます" not in md
    part = md.split("### 時間と動き", 1)[1].split("\n## ", 1)[0]
    assert "全体の経過" in part and "詳細" in part


def test_D0019_AC_50_記録のガイドにname_session_id_agentがある():
    """D0019-AC-50: docs/guide/records.md に、記録の新しい項目 name・session_id・agent（足すだけで、無い古い記録も読める）が書いてある。"""
    md = read_doc(GUIDE / "records.md")
    for word in ("name", "session_id", "agent"):
        assert f"`{word}`" in md, f"docs/guide/records.md に `{word}` が無い"


# ---- D0021-AC-38: VSCode のガイドに、止まっているかもしれない実行の印を書く ------------------------------------

STALE_TITLE = "止まっているかもしれない実行"

# （pytest の id, 何の説明か, 節の中を探す正規表現）。言葉は要件定義の AC-38 の列挙に合わせる。説明の言い方は文書を書く人が決める
STALE_GUIDE_WORDS = [
    ("setting-name", "設定 pipe-in.staleAfterMinutes", r"pipe-in\.staleAfterMinutes"),
    ("what-log", "何を見るか：段のログ", r"段のログ"),
    ("what-mtime", "何を見るか：更新時刻", r"更新時刻"),
    ("when-10min", "いつ出るか：目安（既定 10 分）", r"10 ?分"),
    ("not-process", "何を意味しないか：プロセスは調べない", r"プロセス[^。\n]*調べ"),
    ("not-sdk", "何を意味しないか：SDK の静かな長い段", r"SDK"),
    ("not-record", "何を意味しないか：record 経由の長い段", r"record"),
    ("not-clock", "何を意味しないか：書いた機械と見る機械の時計", r"時計"),
    ("vs-last-moved", "「最後に動いた」（段が終わった時刻）との違い", r"最後に動いた"),
    ("absent-first-stage", "出ない場合：最初の段のあいだ", r"最初の段"),
    ("absent-rerun", "出ない場合：再実行で前の記録が残るとき（再実行／流し直し）", r"再実行|流し直し"),
    ("absent-just-started", "出ない場合：起動直後でログがまだ空のとき", r"起動直後"),
    ("absent-parallel", "出ない場合：並列で先に終わった段があるあと", r"先に終わった"),
    ("absent-omitted", "出ない場合：省いた別の worktree", r"省いた"),
    ("absent-archive", "出ない場合：archive/", r"archive/"),
    ("disappears", "いつ消えるか", r"消え"),
    ("range-10080", "設定の範囲（10080 分）", r"10080"),
]


def heading_part(md: str, word: str) -> str:
    """見出しの文に word を含む節の本文：その見出しの行から、次の同じか浅い見出しの前まで。コードの中の # は見出しにしない。無ければ空。"""
    out: list[str] = []
    depth = None
    in_code = False
    for line in md.splitlines():
        if line.lstrip().startswith("```"):
            in_code = not in_code
        m = None if in_code else re.match(r"^(#{1,6})\s+(.*?)\s*#*\s*$", line)
        if depth is None:
            if m and word in m.group(2):
                depth = len(m.group(1))
                out.append(line)
            continue
        if m and len(m.group(1)) <= depth:
            break
        out.append(line)
    return "\n".join(out)


def test_D0021_AC_38_ガイドの実行を見るの中に止まっているかもしれない実行の節がある():
    """D0021-AC-38: docs/guide/vscode.md の「実行を見る」の中に、「止まっているかもしれない実行」の見出し（### 以下）がある。"""
    md = read_doc(GUIDE / "vscode.md")
    titles = [title for depth, title in headings(section(md, "実行を見る")) if depth >= 3]
    assert any(STALE_TITLE in title for title in titles), f"「実行を見る」の中に「{STALE_TITLE}」の節が無い（今ある小見出し：{titles}）"


@pytest.mark.parametrize("label,pattern", [(label, pattern) for _, label, pattern in STALE_GUIDE_WORDS], ids=[i for i, _, _ in STALE_GUIDE_WORDS])
def test_D0021_AC_38_ガイドの節に止まっているかもしれない実行の説明がある(label, pattern):
    """D0021-AC-38: 「止まっているかもしれない実行」の節に、何を見るか（段のログの更新時刻）・いつ出るか（目安の時間）・何を意味しないか
    （プロセスは調べない。SDK の静かな長い段と record 経由の長い段は動いていても出る。書いた機械と見る機械の時計）・出ない場合・
    「最後に動いた」との違い・設定 pipe-in.staleAfterMinutes（範囲 10080 分）・いつ消えるか、が書いてある。"""
    part = heading_part(read_doc(GUIDE / "vscode.md"), STALE_TITLE)
    assert part, f"docs/guide/vscode.md に「{STALE_TITLE}」の節が無い"
    assert re.search(pattern, part), f"docs/guide/vscode.md の「{STALE_TITLE}」の節に、{label} の説明が無い（探した形：{pattern}）"


def test_D0021_AC_38_節の取り出しは見出しから次の同じか浅い見出しの前まで_コードの中の井桁は見出しにしない():
    """D0021-AC-38: 節の取り出し（heading_part）そのものの確かめ。節の外の言葉を拾わず、節が無ければ空になる。（今のまま通る。守る）"""
    md = "\n".join(
        [
            "## 実行を見る",
            "前置き SDK",
            "### 止まっているかもしれない実行",
            "本文 段のログ",
            "#### 小見出し",
            "小見出しの本文 更新時刻",
            "```",
            "# コードの中の井桁",
            "```",
            "コードのあとの本文 消える",
            "### 時間と動き",
            "別の節の本文 10080",
        ]
    )
    part = heading_part(md, STALE_TITLE)
    for inside in ("本文 段のログ", "小見出しの本文 更新時刻", "# コードの中の井桁", "コードのあとの本文 消える"):
        assert inside in part, inside
    for outside in ("前置き SDK", "別の節の本文 10080", "時間と動き"):
        assert outside not in part, outside
    assert heading_part("## 実行を見る\n本文 SDK\n", STALE_TITLE) == "", "節が無ければ空（ほかの場所の言葉を拾わない）"


def test_D0021_AC_38_拡張のREADMEに設定名がある():
    """D0021-AC-38: vscode/README.md にも、設定 pipe-in.staleAfterMinutes の名前がある。"""
    md = read_doc(ROOT / "vscode" / "README.md")
    assert "pipe-in.staleAfterMinutes" in md, "vscode/README.md に pipe-in.staleAfterMinutes が無い"


# ---- D0014-AC-27: 古いリンク --------------------------------------------------------------------


def test_D0014_AC_27_READMEの移行の節の直前にmigrateのアンカーがありガイドを指す():
    """D0014-AC-27: README の前の名前から移る節の直前に <a id="migrate"></a> があり、その節に docs/guide/migrate.md へのリンクがある。"""
    md = read_doc(README)
    lines = md.splitlines()
    assert f"## {MIGRATION_TITLE}" in lines, "README に前の名前から移る節が無い"
    at = lines.index(f"## {MIGRATION_TITLE}")
    before = [line for line in lines[:at] if line.strip()]
    assert before and before[-1].strip() == '<a id="migrate"></a>'
    assert "docs/guide/migrate.md" in link_paths(section(md, MIGRATION_TITLE))


# ---- D0014-AC-31: 決定の記録 ------------------------------------------------------------------


def test_D0014_AC_31_決定の記録D0014があり索引に行がありD0009を置き換えると書く():
    """D0014-AC-31: docs/decisions/D0014-*.md が1つあり、索引に D0014 の行があり、記録に D0009 を置き換えることと、変えたテストのファイルが書いてある。"""
    decisions = ROOT / "docs" / "decisions"
    records = sorted(decisions.glob("D0014-*.md"))
    assert len(records) == 1, [p.name for p in records]
    assert any("D0014" in line for line in read_doc(decisions / "README.md").splitlines() if line.startswith("|"))
    text = records[0].read_text(encoding="utf-8")
    missing = [w for w in ["D0009", "置き換える", "test_readme.py", "test_headless_audit.py", "test_rename.py"] if w not in text]
    assert missing == []
