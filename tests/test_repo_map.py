"""リポジトリの地図を作り、品ごとに整理する（D0099）：README と design.md の地図・置き場所の表の5つの品・4枚の SVG の安全と配色・/pipe-help の印。

文書と画像は読むだけで書かない（偽の文書と偽の SVG は文字列で組み立てる）。SDK は呼ばない。
使うのは標準ライブラリ（re・xml.etree.ElementTree・pathlib・collections）と pytest と、tests/ の補助（test_readme）だけ。
色の値はこのファイルに写さず、docs/design/README.md の「色の決まり」の表から読む。
前の名前は、この文書に直接書かない（tests/test_rename.py の一覧に無いファイルなので）。要るときは test_readme.OLD を使う。
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from urllib.parse import unquote

import pytest

from test_readme import OLD, headings, pictures, section

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
README_EN = ROOT / "README.en.md"
DESIGN_MD = ROOT / "docs" / "development" / "design.md"
WORKFLOW_MD = ROOT / "docs" / "development" / "workflow.md"
CLAUDE_MD = ROOT / "CLAUDE.md"
PIPE_HELP = ROOT / ".claude" / "skills" / "pipe-help" / "SKILL.md"
DESIGN_SYSTEM = ROOT / "docs" / "design" / "README.md"
ASSETS = ROOT / "docs" / "assets"
ASSETS_README = ASSETS / "README.md"

MAP_JA = "## リポジトリの地図"
README_MAP_JA = "### リポジトリの地図"
README_MAP_EN = "### Repository map"

# （言語, 表示）→ ファイル名。英語の名前は、日本語の名前の -light・-dark の前に -en を足したもの（FR-13）
SVGS = {
    ("ja", "light"): "repo-map-light.svg",
    ("ja", "dark"): "repo-map-dark.svg",
    ("en", "light"): "repo-map-en-light.svg",
    ("en", "dark"): "repo-map-en-dark.svg",
}
KINDS_JA = ("アプリ", "作る", "プラグイン", "開発用")
KINDS_EN = ("App", "Build", "Plugin", "Dev")
PLACES = ("pipe_in/", "vscode/", "pipes/", "generator/", "plugin/", ".claude/", "docs/development/", "docs/decisions/")
LEGEND_JA = ("import", "コマンドを起こす", "読むだけ")
LEGEND_EN = ("import", "runs a command", "reads only")
NAME_FORMS = ("/pipe-*", "pipe-in-*", "/pipe-in:*", "pipe-*")
VERSION = re.compile(r"(?<![\w.])\d+\.\d+\.\d+(?![\w.])")

# 置き場所の表の5つの品（この順。FR-08）
PLACE_KINDS = ["アプリ", "作る", "プラグイン", "開発用", "共通"]
PLACE_HEADER = "| やりたいこと | 場所 |"
PLACE_SEPARATOR = "| --- | --- |"

# 分ける前の design.md の「置き場所」の表の 87 行の第1列（分ける前の design.md の 7〜93 行目から写した固定の一覧。D0099-AC-11）
PLACE_ROWS_BEFORE = tuple(
    line
    for line in r"""
入口（pipe-in コマンド）
前の名前のコマンドの別名（0.3 の間だけ。案内を出して新しい入口を呼ぶ）
どのパイプにも共通：段の実行・記録・確認・まとめ
記録（`state.json`）の土台：鍵の並び・`schema`・費用と使用量の「測れた」「取れない」の2通りを決める `new_state`（標準ライブラリだけ。3つの書き手が呼ぶ）
流れの回数 `flow` の読み方 `read_flow`（壊れた部分は 0。標準ライブラリだけ。SDK の道と会話の道が読む）
段の設定の型・protected_paths・既定で守る場所 `DEFAULT_PROTECTED_PATHS`・段の費用の上限を決める `stage_budget_usd`（SDK に渡す値と記録に残す値は、必ずこの関数から取る）
止める操作（pipe-in が流す段の PreToolUse フック）と、Bash のコマンドの文字列から書き込み先を読む部品（標準ライブラリだけ。シェルは起こさない）
SDK の呼び出し（段のログの `Prompt` 行の形もここ）
記録に書く時刻の書き方（UTC からのずれつき、秒まで）
設定の読み込み（`max_budget_usd` の値の検査もここ。`pipe.toml` 側も同じ判定と文を使う）
セッション名の取り方と、セッション ID・受け持ちの検査（標準ライブラリだけ。拡張の `sessionName.ts` と同じ規則を、同じ表で確かめる）
テストが `generator/` を `pipe_in_generator` として読む補助（入れ込みの場所によらず作業フォルダの `generator/` を読み、違えば直し方つきで落とす。`conftest.py` と、子プロセスを起こすテストの `CHILD_PRELUDE` が使う）
記録の鍵 `max_budget_usd`・`resumed` を、本体が書く側と拡張が読む側で結ぶ共通の表（見本の記録ではない。本体と拡張のテストが同じ表を読む）
記録の鍵 `stages[].check`・`runs[]` の `check` の `attempt` を、本体が書く側と拡張が読む側で結ぶ共通の表（見本の記録ではない。本体と拡張のテストが同じ表を読む）
記録の鍵 `stages[].group`（並列の枠の名前）を、本体が書く側と拡張が読む側で結ぶ共通の表（見本の記録ではない。本体と拡張のテストが同じ表を読む）
記録の土台（`schema`・鍵の並び・費用と使用量の値の種類）を、3つの書き手（SDK・開発用・会話）と拡張が読む側で結ぶ共通の表（見本の記録ではない。本体と拡張のテストが同じ表を読む）
検査の二重化（`check_pipe` と `validatePipe`）の見本と、両側のテスト
進み具合の写し（`state.json` などから、Claude のアーティファクトに出す JSON を作る。標準ライブラリだけ）と、そのページの HTML（外部の読み込みは書体の Google Fonts の `<link>` 2本だけ）、コマンド `pipe-in live`、記録を見張って変わったときだけ1行を出す `pipe-in live watch`（読むだけ。時計・眠り・読み・書きは引数で差し替える）、ページから来た答えの文を作る・読む・記録と照らす `live_answer.py`（ほかの部品を読まない葉。`live.py` は識別子と段の形のためにこれだけを読む）とコマンド `pipe-in live answer`（記録は変えない）
実行パネルの返事のファイル（D0079。実行のフォルダの `reply.json`）を読む・今の待ちと照らす・消す部品と、端末の行の元（標準ライブラリと `live_answer.py` の定数だけ。返事を作る関数は持たない。リンクは辿らない。断る理由は決まった一覧で、入力の文字は入れない。端末の行は、錠を持たない読み方で、頼まれたときだけ 1 行読む）。人の確認の待ち方は `checkpoint.py` が持ち、標準入力が端末のときだけ、標準入力と返事のファイルを 0.5 秒ごとに一緒に待つ
使用量の集計と表
流す前の費用の目安：モデルの系統ごとの「1ターンの費用」の表（`prices.py`。直すのはここだけ）と、段のリスト → 少なめ・多め・前の実績・注意の文の計算（`estimate.py`）。どちらも標準ライブラリだけで、ファイル・SDK・時計に触れない（今日は引数）。入口 `pipe-in estimate` と本流の確認前の 2 行は、段のリストの組み立てと `state.json` の読み出しも含めて `estimate_cmd.py`（読むだけで書かない）
費用の目安の単価表・計算のケース・注意の文を、本体（`prices.py`・`estimate.py`）と拡張（`costEstimate.ts`）で結ぶ共通の表（見本の記録ではない。本体と拡張のテストが同じ表を読む。単価表を直すときは3か所を一緒に直す）
開発フロー（5段・差し戻し・指示文）
パイプ（定義の読み込み・検査・探す順番・流れ・権限の型）
前のパイプの記録を受ける（`--after`。前の記録を読んで受けてよいかを決める・断る文・後ろの段が前の記録を書けない守りの判定・流す前の1行。記録の受け渡しは `pipeline.py` と `specs.py` が行う）
検証の審査の計算（`[stages.check.judge]`。合否・平均・直す点。標準ライブラリだけ。`generator/judge_score.py` と決まりを同じにして二重に持つ）
ジェネレーター（pipe-in-gen・環境の検出・ひな形）
Claude Code のプラグイン（スキル・エージェント・フックの定義。作る `pipe-build`・検査 `pipe-eval`・審査 `pipe-judge`・進み具合を見る `pipe-live` のスキル、エージェント `pipe-builder`・`pipe-judge`。`plugin/skills/pipe-build/references/stage-rules.md` は段の決め方と検査・審査の組み方と比較実験から分かった組み方の目安で、pipe-build が自分で Read して pipe-builder への依頼文に貼る（絶対パスも添え、貼られていなければ pipe-builder がそれを Read する）。プラグイン自身の確かめのケースは `plugin/evals/` に、ケースごとのフォルダで置く（`claude plugin eval` 用の `prompt.md`・採点の `graders`・`case.yaml`・`scaffold.sh`・`scaffold.py`。ケースの形の検査は `tests/test_plugin_evals.py`））
プラグインのディレクトリ申請の備え（D0095）：入れた人に届く `plugin/README.md`（英語・日本語）・`plugin/LICENSE`（根と同じ）・アイコン `plugin/.claude-plugin/icon.png`、`plugin.json` と `marketplace.json` の表示の項目。事前チェックの決まりを見張るテスト（検査の関数は同じファイルの中）と、申請の手順の文書
プラグインのフックの本体（pipe-builder と pipe-judge の操作を絞る。入力が読めない・16 MiB の上限超え・文字列でも null でもない `agent_type`（読む道具以外）は止め、止める返事を書けないときは標準エラーと終了コード 2。D0083。書き込み先はリンクの先もたどり、文字の上の判断とたどった判断の両方が通るときだけ通す。壊れた・輪のリンクは止める。D0088。報告を親に渡す `SubagentHandback` は、`agent_type` が文字列なら止めない（許す名前は `REPORT_TOOLS`。D0096））
会話の中で流す段のフック（pipe-stage を開いている段の範囲に、pipe-probe を読む道具だけに絞り、段の間のほかのエージェントを止める。報告の道具は段や記録の状態によらず止めない。残りは `guard_hook.decide` に渡す）
会話の中でパイプを流す入口（`pipe-in-gen chat start / probe / next / done / review / status`。引数の解釈と JSON の出力だけ）
守りの比較表（同じ呼び出しを SDK の道・会話の道・プラグインの 2 役・開発用の 4 役の 9 列に通した今の結果。表のデータは `tests/guard_matrix.py`、固定するのは `tests/test_guard_matrix.py`。結果が動くと落ちる。D0083）と、リンクを経た道のテスト（フックのリンクの扱い。D0088）で使うリンクの補助（`tests/symlink_support.py`。リンクを作れない環境では skip する）
会話の中でパイプを流す司会役（段の順番・検査・差し戻し・人の確認・記録。SDK を呼ばない）
会話の道の能力表（項目 × 実行役の動き：効く・断る・一覧に出す・黙る・関係しない。断る文と効かない設定の一覧を作り、全項目が載っているかを検査する。判断は、値がある・None でない・値が違う・Claude Code にサブエージェントの書き込みを断られる名前（D0096）。標準ライブラリだけ。`chat.py` が使う）
会話の道の記録の読み書き（指紋・段の範囲 `chat_specs`・フックの跡・Bash の覚え。司会役とフックが共有）
終わった記録を `archive/<日時>/` へ移す（開発フローの記録と会話の道が共有）
会話の中で段を受け持つ・守りを確かめるエージェントと、流すスキル `/pipe-in:pipe-run`
プラグインの採点の計算（総合点・合否・`--runs` のばらつき。標準ライブラリだけ）
仕様書レビューの指摘の検査（指摘の形 v1。形・出典・引用の一致・役割の決まりを LLM なしで調べる `pipe-in-gen findings-check`。標準ライブラリだけ。Schema は他の道具に渡す契約で、実行時には読まない。ひな形 `generator/templates/spec-review/` の `verify` 段が呼ぶ）
2体の共通部分（指摘の形 v1 のファイル2つか3つから、`location.source` と正規化した `location.section` が合う指摘を残す `pipe-in-gen quorum`。標準ライブラリと findings_check だけ。ひな形 `generator/templates/review-quorum/` の `quorum` 段が呼ぶ）
VSCode 拡張
拡張の名前の表（コマンド ID・設定の節・パネルの型）と、前の版の設定・コマンド ID の読み替え
このリポジトリを開発する Claude Code のスキル
画面の見本を触って比べて決めるスキル `/pipe-design`
/pipe-in の段を受け持つサブエージェントと、その書ける場所を絞るフック
`/pipe-design` の良さの条件の調べ係
コードを変えたのに文書が変わっていないまま止まるとき、1回だけ知らせる Stop のフック（標準ライブラリだけ。目印は一時フォルダに置く）
/pipe-in の記録を書く（pipe-in record。`start` の `--name`・`--session-id`、`begin` の `--agent` もここ）
/pipe-in の記録の順序を読むだけで検べる（pipe-in record check。承認より前に次の段が始まっていないか）
機能ごとの worktree を切る・main に入ったものを片付ける・main に載せ直す（pipe-in worktree new・clean・sync。origin の main を取って使う。D0048・D0049・D0074）と、決定の記録の次の番号を出す（pipe-in decision-number。D0074）
/pipe-in が打つ記録・worktree・decision-number・spec-check のコマンドを、今のフォルダだけを相手にする形で流す入口（pipe-in skill。allow に入れる。D0049・D0085）
要件定義・設計・決定の記録の ID のつながり（要求 → 機能要件・非機能要件 → 受け入れ基準 → 状態遷移のマス）を数えて問題を出す検査（pipe-in skill spec-check。標準ライブラリだけ・読むだけで書かない・旗も引数も取らない。読み方の正規表現と問題の種類はこの 1 ファイルに閉じ込め、`tests/test_rules.py` が D0085 以降の決定の記録にかける。D0085）
利用者向けの説明（使い方・拡張・パイプ・プラグイン・安全・記録・設定・移行・開発・コマンドを打たない人向けの案内）。README は入口だけ
初めての人向けの案内（VSCode の「ようこそ」から開く walkthrough。宣言は `contributes.walkthroughs`、手順ごとの本文は Markdown。外から何も読み込まず、自動では開かない。D0072）
英語の入口（`README.md`・`vscode/README.md` の英語版。人が書き、見出し・コードの塊・コマンドの行・画像の食い違いは `tests/test_english_docs.py` が見る。ほかの文書は日本語だけ。D0072）
CI（main に入る前のテスト・型検査・ビルド。権限は contents: read だけで、秘密を使わない）と、その更新（Dependabot）
GitHub の PR と issue のテンプレート（PR の本文の節・issue forms の不具合と機能の要望・白紙の issue の許可。決まりは workflow.md の「7. PR と issue」）
開発のルール・決定の記録
文書の形の検査（決定の記録の一覧の昇順・表の行の長さ・.gitattributes の union。D0075）
アーキテクチャの検査（依存の向き・標準ライブラリだけ。新しい検査は決定ごとの別ファイル。D0075）
ロードマップ（目指す姿と段階）
調べた結果（実験の方法・結果・やり直すためのスクリプトと集計の結果。生のデータは置かない）
プラグインの eval のラウンド（下位のモデルで回した回ごとの点・落ちた採点・費用と回し方）と、結果の JSON からケースごとの点と前の回との差の表を出す集計（標準ライブラリだけ・読むだけ・書かない・知らない形で止まる。D0096）
確認用ページ：会話の道の記録の見本（`driver: "pipe-chat"`・使用量が取れない記録を一時フォルダに書いて、`run-panel-chat-*` を出す）
確認用ページ：開発用の新しい記録の見本（`driver: "pipe-dev"`・費用と使用量が取れない・段が 1 秒ほどで終わる短い記録を一時フォルダに書いて、`run-panel-dev-*` を出す）
時系列の確認待ちの字の置き場所（右・左・帯の下。純粋な関数。`ganttHtml.ts` だけが使う）
確認用ページ：返事を受け付けている確認待ちの見本（印 `reply_wait` のある記録・ボタンの出ない記録を一時フォルダに書いて、`run-panel-reply-runs-*` を出す。`window.__previewReply(name)` で、描き直しと送ったあとを送る）
画面のデザインの土台（ブランド「プラグ」の色の決まり・部品と画面の見本。Claude のデザインのキャンバスの写し）
ロゴ（README に載せる SVG。明るい表示用と暗い表示用）とロゴの動き（HTML と GIF。検査は `tests/test_plug_logo.py`）、README とガイドの画像（明暗の PNG）、撮り直しの手順
画面用の見本の記録（本体の流れを差し替えた runner で作る。README とガイドの画像と確認用のページが読む。4つ：完了・動いている2つ（うち1つは、戻る矢印が光る描き直しの素材）・確認待ち）
画面の確認用のページ（開発用。`npm run preview`）。ページの種類と名前の一覧は `docs/assets/README.md`、確かめる手順は `.claude/skills/pipe-in/screen-check.md`。ページごとの作り方（見本の記録の持ち方）は、次の「確認用ページ：…」の行に 1 ページ 1 行で書く
確認用ページ：実行の一覧の見本
確認用ページ：更新なしの見本
確認用ページ：成果物のタブの見本
確認用ページ：エージェント・スキルのタブの見本
確認用ページ：上限と費用の表の見本
確認用ページ：判定とやり直しの見本
確認用ページ：並列の枠の見本
確認用ページ：スタブでの確かめ
動画を作るパイプの見本（`pipe-in --pipe examples/video/pipes/pipe-in-video` で流し、`pipe-in-gen check video --pipes-dir examples/video/pipes` で確かめる。受付とテンプレートの2つ以外のコードは置かない）
流せる見本のパイプ（図を作る・仕様とソースの突き合わせ・調べものをまとめる）と、見本の案内。`diagrams`・`spec-qa` は `generator/templates/` のひな形を決まった値で埋めた写しに上限を足したもので、`tests/test_examples.py` がひな形との食い違いを見張る。`pipe-in-gen check <名前> --pipes-dir examples/<名前>/pipes` で確かめる
作業台の「見本から作る」の見本のデータ（`examples/` から `npm run examples:gen` で作って、コミットする。拡張は実行時に `examples/` を読まない。`pipe.toml` と `prompts/*.md` だけを持つ）と、見本の一覧とモデル作り、名前の確かめと見本から未保存のモデルを作る手順（書く口を受け取らない）、生成の道具
作業台から流す（D0078。拡張が起こしてよい子プロセスは、決まった形の `pipe-in` 1つだけ。実行ファイルは絶対パスに決めてから Tasks API の `ProcessExecution` で起こし、`child_process` は使わない）。コマンドの形と依頼メモの検め・実行ファイルの決め方の純粋な部分・流してよいかの判断（理由は決まった順で1つ）はドメイン、実行ファイルを探す手順・実行中の記録（入口が持つ）・流す計画はアプリ、`stat` で通常のファイルかを返すのは基盤、「流す」の節は画面
作業台から流す引数の形を、拡張（`buildRunCommand`）と本体（`pipe_in.cli._parse_args`）で結ぶ共通の表（見本の記録ではない。拡張と本体のテストが同じ表を読む）
返事のファイルの中身を、拡張が作る関数（`buildReplyText`）と本体の読み取り（`parse_reply`）で結ぶ共通の表（見本の記録ではない。拡張と本体のテストが同じ表を読む。直してほしい点の長さはコードポイント）
作ったパイプ（どれも .gitignore 済み）
""".strip().splitlines()
)

# 同じ名前のエージェント（名前は変えない。D0099-AC-08）
DEV_AGENTS = (
    "pipe-in-advisor", "pipe-in-analyst", "pipe-in-auditor", "pipe-in-coder", "pipe-in-documenter",
    "pipe-in-judge", "pipe-in-tester", "pipe-in-ux-researcher", "pipe-in-verifier",
)
PLUGIN_AGENTS = ("pipe-builder", "pipe-judge", "pipe-probe", "pipe-stage")

# generator/ の直下の部品の品（FR-03。使う入口で分ける）
GENERATOR_KINDS = {
    "guard_hook.py": "プラグイン", "chat_cmd.py": "プラグイン", "chat_hook.py": "プラグイン", "judge_score.py": "プラグイン",
    "cli.py": "作る", "design.py": "作る", "render.py": "作る", "detect.py": "作る", "legacy.py": "作る",
    "findings_check.py": "作る", "quorum.py": "作る",
}
DEV_TOOLS = ("record.py", "record_order.py", "worktree.py", "decision_number.py", "skill_cmd.py", "spec_check.py")
CHAT_PARTS = ("chat.py", "capability.py", "chat_record.py")

# ---- SVG の安全の決まり（許すものの一覧。D0099 の設計の SVG の安全の決まり） -----------------------------------------------

SVG_NS = "http://www.w3.org/2000/svg"
XML_NS = "http://www.w3.org/XML/1998/namespace"
SVG_XMLNS = f'xmlns="{SVG_NS}"'
ALLOWED_TAGS = {"svg", "title", "desc", "defs", "marker", "g", "rect", "circle", "line", "polyline", "path", "text", "tspan"}
ALLOWED_ATTRS = {
    # 形
    "x", "y", "width", "height", "rx", "ry", "cx", "cy", "r", "x1", "y1", "x2", "y2", "points", "d", "dx", "dy",
    # 塗りと線
    "fill", "stroke", "stroke-width", "stroke-dasharray", "stroke-linecap", "stroke-linejoin",
    # 文字
    "font-family", "font-size", "font-weight", "text-anchor", "dominant-baseline", "xml:lang",
    # 矢印の先
    "marker-end", "viewBox", "refX", "refY", "markerWidth", "markerHeight", "markerUnits", "orient",
    # 根と見出し
    "role", "aria-labelledby", "id",
}
FONT_STACKS = (
    "system-ui, -apple-system, 'Segoe UI', 'Hiragino Sans', 'Yu Gothic', 'Noto Sans CJK JP', sans-serif",
    "ui-monospace, SFMono-Regular, Menlo, Consolas, 'Noto Sans Mono', monospace",
)
# 文字の上で先に止めるもの（見せる名前, 小文字で探す文字）
TEXT_BANNED = (
    ("<!DOCTYPE", "<!doctype"),
    ("<!ENTITY", "<!entity"),
    ("<?xml-stylesheet", "<?xml-stylesheet"),
    ("javascript:", "javascript:"),
    ("http:", "http:"),
    ("https:", "https:"),
    ("//", "//"),
    ("@import", "@import"),
)
MAX_SVG_BYTES = 100 * 1024
MIN_CONTRAST = 4.5
COLOR_ATTRS = ("fill", "stroke")
LOCAL_URL = re.compile(r"url\(#[A-Za-z][\w-]*\)")


# ---- 補助 ------------------------------------------------------------------


def need(path: Path) -> str:
    if not path.is_file():
        pytest.fail(f"{path.relative_to(ROOT).as_posix()} が無い")
    return path.read_text(encoding="utf-8")


HEADING_LINE = re.compile(r"^(#{1,6})\s+\S")


def heading_part(md: str, heading: str) -> str:
    """見出しの行（heading と同じ文字の行）から、次の同じか浅い見出しの前まで。コードの中の # は見出しにしない。無ければ空。"""
    depth = len(HEADING_LINE.match(heading).group(1))
    out: list[str] | None = None
    in_code = False
    for line in md.splitlines():
        fence = line.lstrip().startswith("```")
        if out is None:
            if fence:
                in_code = not in_code
            elif not in_code and line.strip() == heading:
                out = [line]
            continue
        if fence:
            in_code = not in_code
        elif not in_code:
            m = HEADING_LINE.match(line)
            if m and len(m.group(1)) <= depth:
                break
        out.append(line)
    return "\n".join(out) if out else ""


def map_section(md: str, heading: str = MAP_JA) -> str:
    """地図の節：design.md は「## リポジトリの地図」から次の ## の前まで、README は「### リポジトリの地図」（英語は「### Repository map」）から次の見出しの前まで。"""
    return heading_part(md, heading)


def need_part(md: str, heading: str, where: str) -> str:
    part = heading_part(md, heading)
    if not part:
        pytest.fail(f"{where} に「{heading}」の節が無い")
    return part


def bullets(part: str) -> str:
    """箇条書きの行（字下げした行も）だけをつないだもの。"""
    return "\n".join(line for line in part.splitlines() if line.lstrip().startswith("- "))


def backticks(text: str) -> list[str]:
    return re.findall(r"`([^`\n]+)`", text)


def bullet_paths(part: str) -> list[str]:
    """箇条書きのバッククォートの語のうち、パスの形のもの（/ を含み、/ で始まらず、* と空白を含まない）。"""
    return [w for w in backticks(bullets(part)) if "/" in w and not w.startswith("/") and "*" not in w and " " not in w]


def has_name(text: str, name: str) -> bool:
    """ファイル名が語として出るか（パスの末尾でもよい。名前の一部だけ・別の拡張子は数えない）。"""
    return re.search(r"(?<![\w.-])" + re.escape(name) + r"(?![\w])", text) is not None


def generator_name_count(text: str, name: str) -> int:
    """generator/ の直下の名前が出る回数（`generator/` を前に付けた形も数え、pipe_in/ などほかのフォルダの同じ名前は数えない）。"""
    return len(re.findall(r"(?<![\w./-])(?:generator/)?" + re.escape(name) + r"(?![\w])", text))


def kind_blocks(part: str, kinds=KINDS_JA) -> dict[str, str]:
    """「- **品の名前**」で始まる箇条書きと、その下の字下げした行を、品ごとにまとめる。"""
    blocks: dict[str, str] = {}
    current = None
    for line in part.splitlines():
        m = re.match(r"^- \*\*(.+?)\*\*", line)
        if m:
            current = m.group(1) if m.group(1) in kinds else None
            if current:
                blocks[current] = blocks.get(current, "") + line
            continue
        if line.startswith("- ") or (line and not line[0].isspace()):
            current = None
            continue
        if current and line.strip():
            blocks[current] += "\n" + line
    return blocks


def in_order(text: str, parts: list[str]) -> bool:
    """parts が text の中にこの順で出るか。"""
    pos = 0
    for p in parts:
        i = text.find(p, pos)
        if i < 0:
            return False
        pos = i + len(p)
    return True


def table_rows(part: str) -> list[str]:
    return [line for line in part.splitlines() if line.startswith("|")]


def first_cell(row: str) -> str:
    return row[2:].split(" | ")[0] if row.startswith("| ") else ""


def place_section(md: str) -> str:
    return heading_part(md, "## 置き場所")


def place_tables(md: str) -> list[tuple[str, list[list[str]]]]:
    """「## 置き場所」の中の ### ごとに（見出しの文, 表の並び）。表は | で始まる行の続き。"""
    out: list[tuple[str, list[list[str]]]] = []
    tables: list[list[str]] | None = None
    current: list[str] | None = None
    for line in place_section(md).splitlines()[1:]:
        if line.startswith("### "):
            tables = []
            out.append((line[4:].strip(), tables))
            current = None
            continue
        if tables is None:
            continue
        if line.startswith("|"):
            if current is None:
                current = []
                tables.append(current)
            current.append(line)
        else:
            current = None
    return out


def place_head(md: str) -> str:
    """「## 置き場所」の頭（見出しの次から、最初の ### の前まで）。"""
    lines = place_section(md).splitlines()[1:]
    head = []
    for line in lines:
        if line.startswith("### "):
            break
        head.append(line)
    return "\n".join(head)


def palette() -> dict[str, tuple[str, str]]:
    """docs/design/README.md の「色の決まり」の表から、役 → （明るい, 暗い）。"""
    part = need_part(need(DESIGN_SYSTEM), "## 色の決まり", "docs/design/README.md")
    out = {}
    for m in re.finditer(r"^\| ([^|]+?) \| `--[\w-]+` \| `(#[0-9a-f]{6})` \| `(#[0-9a-f]{6})` \|", part, re.M):
        out[m.group(1)] = (m.group(2), m.group(3))
    return out


def _luminance(color: str) -> float:
    def channel(c: float) -> float:
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (int(color[i : i + 2], 16) / 255 for i in (1, 3, 5))
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def contrast(a: str, b: str) -> float:
    """WCAG の相対輝度から出すコントラスト比（1〜21）。"""
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def _local(tag: str) -> tuple[str, str]:
    ns, _, name = tag.rpartition("}")
    return ns.lstrip("{"), name


def _attr_name(key: str) -> str:
    ns, name = _local(key)
    if ns == XML_NS:
        return f"xml:{name}"
    return name if not ns else key


def svg_problems(text: str, colors: set[str] | None = None) -> list[str]:
    """D0099 の設計の SVG の安全の決まりの外を、文の並びで返す（空なら通る）。colors は許す色（省くと色の表の全部の値）。"""
    if colors is None:
        colors = {c for pair in palette().values() for c in pair}
    out = []
    low = text.lower().replace(SVG_XMLNS, "")
    for label, needle in TEXT_BANNED:
        if needle in low:
            out.append(f"文字に {label} がある")
    if "<!doctype" in low or "<!entity" in low:
        return out
    try:
        root = ET.fromstring(text.encode("utf-8"))
    except ET.ParseError as e:
        out.append(f"XML として読めない：{e}")
        return out
    for el in root.iter():
        if not isinstance(el.tag, str):
            continue
        ns, name = _local(el.tag)
        if ns != SVG_NS:
            out.append(f"要素 {el.tag} が SVG の名前空間でない")
        elif name not in ALLOWED_TAGS:
            out.append(f"要素 {name} は許す一覧に無い")
        for key, value in el.attrib.items():
            attr = _attr_name(key)
            if attr not in ALLOWED_ATTRS:
                out.append(f"属性 {attr}（要素 {name}）は許す一覧に無い")
            if "url(" in value.lower() and not LOCAL_URL.fullmatch(value.strip()):
                out.append(f"属性 {attr} の値 {value!r} が # で始まらない url( を持つ")
            if attr in COLOR_ATTRS and value != "none" and value not in colors:
                out.append(f"属性 {attr} の色 {value!r} が色の表に無い")
            if attr == "marker-end" and not LOCAL_URL.fullmatch(value):
                out.append(f"属性 marker-end の値 {value!r} が url(#…) でない")
            if attr == "font-family" and value not in FONT_STACKS:
                out.append(f"属性 font-family の値 {value!r} が決めた2つの並びのどちらでもない")
    return out


def svg_path(lang: str, mode: str) -> Path:
    p = ASSETS / SVGS[(lang, mode)]
    if not p.is_file():
        pytest.fail(f"docs/assets/{SVGS[(lang, mode)]} が無い")
    return p


def svg_root(lang: str, mode: str) -> ET.Element:
    return ET.fromstring(svg_path(lang, mode).read_bytes())


def svg_texts(root: ET.Element) -> list[str]:
    """<text> ごとに、中の tspan を含む文字をつないだものを、文書の順に。"""
    return ["".join(el.itertext()) for el in root.iter(f"{{{SVG_NS}}}text")]


CODE_WORD = re.compile(r"[A-Za-z0-9_.*/:\-]+")


def code_words(texts: list[str]) -> list[str]:
    """文字の中のコードの形の語（パス・コマンド・名前の形・モジュールの名前）を順に。
    英数字と _ . - * / : だけからなる語のうち、/ を含むもの、または pipe で始まり - _ . : * のどれかを含むもの。末尾の . , : ; は外す。"""
    out = []
    for t in texts:
        for m in CODE_WORD.finditer(t):
            w = m.group(0).rstrip(".,:;")
            if "/" in w or (w.startswith("pipe") and any(c in w for c in "-_.:*")):
                out.append(w)
    return out


def path_words(words: list[str]) -> list[str]:
    """code_words のうち、パスの形の語（/ を含み、/ で始まらず、* を含まない）と、pipe_in. で始まるモジュールの名前。"""
    return [w for w in words if ("/" in w and not w.startswith("/") and "*" not in w) or w.startswith("pipe_in.")]


def exists_in_repo(word: str) -> bool:
    rel = word.replace(".", "/") if word.startswith("pipe_in.") else word
    return (ROOT / rel).exists()


def pair_problems(light: str, dark: str, pal: dict[str, tuple[str, str]]) -> list[str]:
    """同じ言語の明暗の2枚の食い違い：要素の並び・色のほかの属性・文字が同じで、色は同じ役の（明るい値, 暗い値）の組か。"""
    a = list(ET.fromstring(light.encode("utf-8")).iter())
    b = list(ET.fromstring(dark.encode("utf-8")).iter())
    pairs = set(pal.values())
    lights = {l for l, _ in pairs}
    darks = {d for _, d in pairs}
    out = []
    if [e.tag for e in a] != [e.tag for e in b]:
        return [f"要素の並びが違う（明るい {len(a)} 個、暗い {len(b)} 個）"]
    for i, (x, y) in enumerate(zip(a, b)):
        name = _local(x.tag)[1]
        rest_x = {k: v for k, v in x.attrib.items() if _attr_name(k) not in COLOR_ATTRS}
        rest_y = {k: v for k, v in y.attrib.items() if _attr_name(k) not in COLOR_ATTRS}
        if rest_x != rest_y:
            out.append(f"{i} 番目の {name}：色のほかの属性が違う（{rest_x} と {rest_y}）")
        if (x.text or "") != (y.text or "") or (x.tail or "") != (y.tail or ""):
            out.append(f"{i} 番目の {name}：文字が違う")
        for attr in COLOR_ATTRS:
            cx, cy = x.attrib.get(attr), y.attrib.get(attr)
            if cx is None and cy is None:
                continue
            if cx is None or cy is None:
                out.append(f"{i} 番目の {name}：{attr} が片方にしか無い")
            elif cx == "none" or cy == "none":
                if cx != cy:
                    out.append(f"{i} 番目の {name}：{attr} の none が片方だけ（{cx} と {cy}）")
            elif cx not in lights:
                out.append(f"{i} 番目の {name}：明るい版の {attr} {cx} が色の表の明るい値に無い")
            elif cy not in darks:
                out.append(f"{i} 番目の {name}：暗い版の {attr} {cy} が色の表の暗い値に無い")
            elif (cx, cy) not in pairs:
                out.append(f"{i} 番目の {name}：{attr} の {cx} と {cy} が同じ役の組でない")
    return out


def help_mark_problems(md: str) -> list[str]:
    """/pipe-help の「Claude Code のコマンド」の表で、印が違う行。/pipe-in: の行は「**プラグイン**」、ほかは「**開発用**」で「すること」の列が始まる。"""
    head = next((line for line in md.splitlines() if line.startswith("### Claude Code のコマンド")), None)
    if head is None:
        return ["「### Claude Code のコマンド」の見出しが無い"]
    part = heading_part(md, head)
    rows = [line for line in part.splitlines() if line.startswith("| `/")]
    if not rows:
        return ["コマンドの行が無い"]
    out = []
    for row in rows:
        cells = [c.strip() for c in re.split(r"(?<!\\)\|", row)[1:-1]]
        command, doing = cells[0], cells[1] if len(cells) > 1 else ""
        mark = "**プラグイン**" if command.startswith("`/pipe-in:") else "**開発用**"
        if not doing.startswith(mark):
            out.append(f"{command} の「すること」の列が {mark} で始まらない")
    return out


# ---- README の地図（D0099-AC-01〜03） ------------------------------------------------------------------


def test_D0099_AC_01_READMEの文書の節にリポジトリの地図の小節がある():
    """D0099-AC-01: README.md の ## は今の4つ（すぐ試す・文書・前の名前から移る・ライセンス）のままで、「## 文書」の節の中に「### リポジトリの地図」がある。"""
    md = need(README)
    assert [t for d, t in headings(md) if d == 2] == ["すぐ試す", "文書", f"{OLD} から移る", "ライセンス"]
    docs = section(md, "文書")
    assert docs, "README.md に「## 文書」が無い"
    assert README_MAP_JA in [line.strip() for line in docs.splitlines()], "「## 文書」の節の中に「### リポジトリの地図」が無い"


def test_D0099_AC_02_READMEの地図はpictureと箇条書きとdesignへのリンクを持つ():
    """D0099-AC-02: README.md の地図の小節に <picture> が1つあり、箇条書きに品の名前4つ・置き場所・名前の形（/pipe-in:・pipe-in-）・向きの3種（import・コマンドを起こす・読むだけ）があり、
    design.md の地図（#リポジトリの地図）へのリンクがある。"""
    part = need_part(need(README), README_MAP_JA, "README.md")
    assert len(pictures(part)) == 1, f"地図の小節の <picture> は1つ（今 {len(pictures(part))} 個）"
    items = bullets(part)
    assert items, "地図の小節に箇条書きが無い"
    missing = [k for k in KINDS_JA if k not in items]
    missing += [f"`{p}`" for p in PLACES if f"`{p}`" not in items]
    missing += [w for w in ("/pipe-in:", "pipe-in-") if w not in items]
    if "import" not in items:
        missing.append("import")
    if not re.search(r"コマンド[^。\n]*を起こす", items):
        missing.append("コマンドを起こす")
    if "読むだけ" not in items:
        missing.append("読むだけ")
    assert missing == [], f"地図の箇条書きに無い語：{missing}"
    anchors_ = [unquote(a) for a in re.findall(r"\]\(docs/development/design\.md#([^)\s]+)\)", part)]
    assert "リポジトリの地図" in anchors_, f"design.md の地図へのリンクが無い（今のリンクのアンカー：{anchors_}）"


def test_D0099_AC_03_英語版の地図は同じ深さで英語の画像と箇条書きを持つ():
    """D0099-AC-03: README.en.md に、日本語版と同じ位置・同じ深さの見出し「### Repository map」の小節があり、<picture> が英語の2枚を指し、
    alt は英語（日本語の字が無い）で、箇条書きに英語の品の名前と置き場所がある。"""
    ja = need(README)
    en = need(README_EN)
    part = need_part(en, README_MAP_EN, "README.en.md")
    ja_h = headings(ja)
    en_h = headings(en)
    ja_i = next((i for i, (d, t) in enumerate(ja_h) if d == 3 and t == "リポジトリの地図"), None)
    en_i = next((i for i, (d, t) in enumerate(en_h) if d == 3 and t == "Repository map"), None)
    assert ja_i is not None, "README.md に「### リポジトリの地図」が無い"
    assert ja_i == en_i, f"見出しの位置が日本語版と違う（日本語版 {ja_i} 番目、英語版 {en_i} 番目）"
    pics = pictures(part)
    assert len(pics) == 1, f"英語版の地図の <picture> は1つ（今 {len(pics)} 個）"
    names = [Path(s["srcset"]).name for s in pics[0]["sources"]] + [Path(pics[0]["src"]).name]
    assert names == [SVGS[("en", "dark")], SVGS[("en", "light")]], f"英語版の地図の画像が英語の2枚でない：{names}"
    alt = pics[0]["alt"]
    assert alt.strip(), "英語版の地図の alt が空"
    assert not re.search(r"[぀-ヿ一-鿿]", alt), f"英語版の alt に日本語の字がある：{alt}"
    items = bullets(part)
    missing = [k for k in KINDS_EN if not re.search(rf"\b{k}\b", items)]
    missing += [f"`{p}`" for p in PLACES if f"`{p}`" not in items]
    assert missing == [], f"英語版の地図の箇条書きに無い語：{missing}"


# ---- design.md の地図（D0099-AC-04〜07・14） -----------------------------------------------------------


def test_D0099_AC_04_designの最初の節が地図で置き場所より前にある():
    """D0099-AC-04: design.md の最初の ## が「リポジトリの地図」で「## 置き場所」より前にあり、節の箇条書きに品の名前4つ・pipe_in_generator から pipe_in.pipe・pipe_in.engine への向き・向きの3種がある。"""
    md = need(DESIGN_MD)
    h2 = [t for d, t in headings(md) if d == 2]
    assert h2 and h2[0] == "リポジトリの地図", f"design.md の最初の ## が「リポジトリの地図」でない（今 {h2[:1]}）"
    assert "置き場所" in h2 and h2.index("リポジトリの地図") < h2.index("置き場所")
    items = bullets(need_part(md, MAP_JA, "docs/development/design.md"))
    missing = [k for k in KINDS_JA if f"**{k}**" not in items]
    if not re.search(r"`pipe_in_generator`[^\n]*→[^\n]*`pipe_in\.pipe`[^\n]*`pipe_in\.engine`", items):
        missing.append("pipe_in_generator → pipe_in.pipe・pipe_in.engine")
    missing += [w for w in LEGEND_JA if w not in items]
    assert missing == [], f"design.md の地図の箇条書きに無いもの：{missing}"


DEPENDENCY_FIGURE = """pipe_in_generator（generator/）
   ↓
pipe_in.pipe / pipe_in.dev
   ↓
pipe_in.engine
   ↓
pipe_in.usage"""


def test_D0099_AC_04_本体の依存の向きの図は今の文字のまま_守る():
    """D0099-AC-04: 「## 本体の依存の向き」の文字の図（モジュールの向き）が今の文字のまま残る。（今のまま通る。守る）"""
    part = need_part(need(DESIGN_MD), "## 本体の依存の向き", "docs/development/design.md")
    assert f"```\n{DEPENDENCY_FIGURE}\n```" in part, "「本体の依存の向き」の図が今の文字と違う"


def test_D0099_AC_05_generatorの直下のpyはどれか1つの品に1回ずつ出る():
    """D0099-AC-05: design.md の地図の品の箇条書きに、generator/ の直下の .py（__init__.py を除く）がどれもどれか1つの品にちょうど1回ずつ出て、
    guard_hook.py・chat_cmd.py・chat_hook.py・judge_score.py はプラグイン、cli.py・design.py・render.py・detect.py・legacy.py・findings_check.py・quorum.py は作るに出る。"""
    names = sorted(p.name for p in (ROOT / "generator").glob("*.py") if p.name != "__init__.py")
    assert len(names) >= 11, names
    assert set(GENERATOR_KINDS) <= set(names), "決めた品の一覧の名前が generator/ に無い（テストの誤り）"
    blocks = kind_blocks(need_part(need(DESIGN_MD), MAP_JA, "docs/development/design.md"))
    assert set(blocks) == set(KINDS_JA), f"地図の箇条書きに品の項目がそろわない（今 {sorted(blocks)}）"
    problems = []
    for name in names:
        found = {k: generator_name_count(b, name) for k, b in blocks.items()}
        total = sum(found.values())
        if total != 1:
            problems.append(f"{name} が品の箇条書きに {total} 回出る（{found}）")
            continue
        kind = next(k for k, n in found.items() if n)
        if name in GENERATOR_KINDS and kind != GENERATOR_KINDS[name]:
            problems.append(f"{name} が {kind} に出る（{GENERATOR_KINDS[name]} に置く）")
    assert problems == [], "\n".join(problems)


def test_D0099_AC_05_pipe_inの添え書きに開発用とプラグインの部品がある():
    """D0099-AC-05: design.md の地図に、pipe_in/dev/ の record.py・record_order.py・worktree.py・decision_number.py・skill_cmd.py・spec_check.py を「開発用」とする句と、
    pipe_in/pipe/ の chat.py・capability.py・chat_record.py を「プラグイン」とする句がある。"""
    part = need_part(need(DESIGN_MD), MAP_JA, "docs/development/design.md")
    clauses = re.split(r"[、。\n]", part)
    dev = [c for c in clauses if "pipe_in/dev/" in c and all(has_name(c, n) for n in DEV_TOOLS) and "開発用" in c]
    chat = [c for c in clauses if "pipe_in/pipe/" in c and all(has_name(c, n) for n in CHAT_PARTS) and "プラグイン" in c]
    assert dev, f"pipe_in/dev/ の {DEV_TOOLS} を開発用とする句が無い"
    assert chat, f"pipe_in/pipe/ の {CHAT_PARTS} をプラグインとする句が無い"


def test_D0099_AC_06_地図に版の数字が無く箇条書きのパスが実在する():
    """D0099-AC-06: README.md・README.en.md・design.md の地図の節と、4枚の SVG の文字に、版の数字（数.数.数）が無い。
    3つの文書の地図の箇条書きに出るパス（/ を含むバッククォートの語）が、どれもリポジトリに実在する。"""
    parts = {
        "README.md": need_part(need(README), README_MAP_JA, "README.md"),
        "README.en.md": need_part(need(README_EN), README_MAP_EN, "README.en.md"),
        "docs/development/design.md": need_part(need(DESIGN_MD), MAP_JA, "docs/development/design.md"),
    }
    problems = []
    for where, part in parts.items():
        problems += [f"{where} の地図に版の数字 {v}" for v in VERSION.findall(part)]
        paths = bullet_paths(part)
        if not paths:
            problems.append(f"{where} の地図の箇条書きにパスが無い")
        problems += [f"{where} の地図のパス {p} が実在しない" for p in paths if not (ROOT / p).exists()]
    for lang, mode in SVGS:
        words = "".join(svg_root(lang, mode).itertext())
        problems += [f"{SVGS[(lang, mode)]} の文字に版の数字 {v}" for v in VERSION.findall(words)]
    assert problems == [], "\n".join(problems)


def test_D0099_AC_06_見本_版の数字とパスの拾い方_守る():
    """D0099-AC-06: 検査そのものの確かめ。数.数.数 は拾い、数.数 と語の中の数は拾わない。パスは箇条書きのバッククォートの / を含む語だけで、コマンドと名前の形は拾わない。（今のまま通る。守る）"""
    assert VERSION.findall("名前は 0.3.0 で変わった") == ["0.3.0"]
    assert VERSION.findall("0.3 の間・v12・a1.2.3b") == []
    sample = "本文の `not/bullet/`\n- `pipe_in/`・`/pipe-in:*`・`/plugin install`・`pipe-*`\n  - `docs/decisions/`・`pipe-in-gen`"
    assert bullet_paths(sample) == ["pipe_in/", "docs/decisions/"]


def test_D0099_AC_07_同じ名前の組が印と置き場所つきで出る():
    """D0099-AC-07: design.md の地図の箇条書きに、/pipe-judge（開発用・.claude/skills/pipe-judge/）と /pipe-in:pipe-judge（プラグイン・plugin/skills/pipe-judge/）、
    pipe-in-*（開発用・.claude/agents/）と pipe-*（プラグイン・plugin/agents/）の組が、名前 → 印 → 置き場所の順で1行ずつ出る。"""
    lines = bullets(need_part(need(DESIGN_MD), MAP_JA, "docs/development/design.md")).splitlines()
    skills = ["`/pipe-judge`", "開発用", "`.claude/skills/pipe-judge/`", "`/pipe-in:pipe-judge`", "プラグイン", "`plugin/skills/pipe-judge/`"]
    agents = ["`pipe-in-*`", "開発用", "`.claude/agents/`", "`pipe-*`", "プラグイン", "`plugin/agents/`"]
    assert any(in_order(line, skills) for line in lines), f"スキルの組の行が無い（この順の語：{skills}）"
    assert any(in_order(line, agents) for line in lines), f"エージェントの組の行が無い（この順の語：{agents}）"


def test_D0099_AC_07_見本_組の行の順を見分ける_守る():
    """D0099-AC-07: 検査そのものの確かめ。名前 → 印 → 置き場所の順の行は通し、印の入れ替わった行は見つける。（今のまま通る。守る）"""
    good = "- `/pipe-judge` は開発用（`.claude/skills/pipe-judge/`）、`/pipe-in:pipe-judge` はプラグイン（`plugin/skills/pipe-judge/`）"
    swapped = "- `/pipe-judge` はプラグイン（`.claude/skills/pipe-judge/`）、`/pipe-in:pipe-judge` は開発用（`plugin/skills/pipe-judge/`）"
    parts = ["`/pipe-judge`", "開発用", "`.claude/skills/pipe-judge/`", "`/pipe-in:pipe-judge`", "プラグイン", "`plugin/skills/pipe-judge/`"]
    assert in_order(good, parts)
    assert not in_order(swapped, parts)


def _front_name(path: Path) -> str | None:
    m = re.search(r"^name:\s*(\S+)\s*$", path.read_text(encoding="utf-8").split("\n---", 1)[0], re.M)
    return m.group(1) if m else None


def test_D0099_AC_08_同じ名前のスキルとエージェントは今の名前のまま_守る():
    """D0099-AC-08: .claude/skills/pipe-judge/SKILL.md・plugin/skills/pipe-judge/SKILL.md・.claude/agents/ の pipe-in-*.md の9つ・plugin/agents/ の pipe-*.md の4つが今の名前のまま実在し、
    前書きの name がファイル名（スキルはフォルダ名）と同じ。（今のまま通る。守る）"""
    files = {ROOT / ".claude/skills/pipe-judge/SKILL.md": "pipe-judge", ROOT / "plugin/skills/pipe-judge/SKILL.md": "pipe-judge"}
    files |= {ROOT / ".claude/agents" / f"{n}.md": n for n in DEV_AGENTS}
    files |= {ROOT / "plugin/agents" / f"{n}.md": n for n in PLUGIN_AGENTS}
    problems = []
    for path, name in files.items():
        rel = path.relative_to(ROOT).as_posix()
        if not path.is_file():
            problems.append(f"{rel} が無い")
        elif _front_name(path) != name:
            problems.append(f"{rel} の name が {_front_name(path)!r}（{name} のはず）")
    assert problems == [], "\n".join(problems)
    assert sorted(p.stem for p in (ROOT / ".claude/agents").glob("pipe-in-*.md")) == sorted(DEV_AGENTS)
    assert sorted(p.stem for p in (ROOT / "plugin/agents").glob("pipe-*.md")) == sorted(PLUGIN_AGENTS)


def test_D0099_AC_14_designの地図の節に表の行が無い():
    """D0099-AC-14: design.md の地図の節（「## リポジトリの地図」から「## 置き場所」の前まで）に、| で始まる行（表の行）が無い。"""
    part = need_part(need(DESIGN_MD), MAP_JA, "docs/development/design.md")
    rows = [line for line in part.splitlines() if line.startswith("|")]
    assert rows == [], f"地図の節に表の行がある（design.md を読む今のテストが先に当たる）：{rows}"


# ---- /pipe-help の印（D0099-AC-09） --------------------------------------------------------------------


def test_D0099_AC_09_pipe_helpのコマンドの行に開発用かプラグインの印がある():
    """D0099-AC-09: /pipe-help の「Claude Code のコマンド」の表で、/pipe-in: で始まる行は「**プラグイン**」、ほかの行は「**開発用**」で「すること」の列が始まり、
    どの行も | `/ で始まったまま。見出しは「（このリポジトリで開発するとき）」でなく、プラグインの行も入っていることが分かる言い方になる。"""
    md = need(PIPE_HELP)
    head = next((line for line in md.splitlines() if line.startswith("### Claude Code のコマンド")), "")
    assert head, "「### Claude Code のコマンド」の見出しが無い"
    assert "このリポジトリで開発するとき" not in head and "プラグイン" in head, f"見出しがプラグインの行も入っている言い方になっていない：{head}"
    rows = [line for line in heading_part(md, head).splitlines() if line.startswith("| `/")]
    assert len(rows) >= 16, f"コマンドの行が少ない（今 {len(rows)} 行。行の頭は | `/ のまま）"
    problems = help_mark_problems(md)
    assert problems == [], "\n".join(problems)


HELP_SAMPLE = """### Claude Code のコマンド（開発用はこのリポジトリだけ・プラグインはどのプロジェクトでも）

| コマンド | すること |
| --- | --- |
| `/pipe-in <要件メモ>` | **開発用**。機能を足す |
| `/pipe-plan [sync \\| add <やりたいこと>]` | **開発用**。計画ボード |
| `/pipe-in:pipe-judge <成果物>` | **プラグイン**。成果物の審査。開発用の `/pipe-judge` とは別物 |

### pipe-in（流す）

| `/not-a-command` | 次の節の行は見ない |
"""


def test_D0099_AC_09_見本_印の誤りを見つけ正しい表は通す_守る():
    """D0099-AC-09: 検査そのものの確かめ。正しい表は通し、プラグインの行に開発用の印・開発用の行に印なし・見出しが無い表を、それぞれ見つける。
    行の中の「開発用」の語や \\| のある行・次の節の行には惑わされない。（今のまま通る。守る）"""
    assert help_mark_problems(HELP_SAMPLE) == []
    wrong = HELP_SAMPLE.replace("| **プラグイン**。成果物の審査", "| **開発用**。成果物の審査")
    assert [p for p in help_mark_problems(wrong) if "/pipe-in:pipe-judge" in p and "**プラグイン**" in p]
    unmarked = HELP_SAMPLE.replace("| **開発用**。機能を足す", "| 機能を足す")
    assert [p for p in help_mark_problems(unmarked) if "/pipe-in <要件メモ>" in p]
    assert help_mark_problems("# 何も無い\n") == ["「### Claude Code のコマンド」の見出しが無い"]


# ---- 置き場所の表（D0099-AC-10〜12） ---------------------------------------------------------------------


def test_D0099_AC_10_置き場所の下に5つの品の見出しと表がこの順にある():
    """D0099-AC-10: design.md の「## 置き場所」が残り、その下に ### の見出し「アプリ」「作る」「プラグイン」「開発用」「共通」がこの順に1つずつあり、
    それぞれの下に表（頭の行は | やりたいこと | 場所 |）が1つずつある。"""
    md = need(DESIGN_MD)
    assert place_section(md), "design.md に「## 置き場所」が無い"
    tables = place_tables(md)
    assert [h for h, _ in tables] == PLACE_KINDS, f"「## 置き場所」の ### の並びが違う（今 {[h for h, _ in tables]}）"
    problems = []
    for heading, ts in tables:
        if len(ts) != 1:
            problems.append(f"### {heading} の下の表が {len(ts)} 個")
        elif ts[0][:2] != [PLACE_HEADER, PLACE_SEPARATOR]:
            problems.append(f"### {heading} の表の頭が {ts[0][:2]}")
        elif len(ts[0]) < 3:
            problems.append(f"### {heading} の表に行が無い")
    assert problems == [], "\n".join(problems)


def test_D0099_AC_11_分ける前の87行はどれか1つの表にちょうど1回ずつ残る():
    """D0099-AC-11: 分ける前の置き場所の表の 87 行の第1列（PLACE_ROWS_BEFORE）が、分けたあとの5つの品の表のどれか1つに、ちょうど1回ずつ同じ文字で出る
    （前の版の行：前の名前のコマンドの別名・作ったパイプ（対象の .pipe-in/pipes/ と今までの pipes/）も残る）。"""
    tables = place_tables(need(DESIGN_MD))
    assert [h for h, _ in tables] == PLACE_KINDS, f"「## 置き場所」の ### の並びが違う（今 {[h for h, _ in tables]}）"
    cells = Counter(first_cell(row) for _, ts in tables for t in ts for row in t[2:])
    problems = [f"{n} 回：{row[:40]}…" for row in PLACE_ROWS_BEFORE if (n := cells[row]) != 1]
    assert problems == [], "分ける前の行が、5つの表にちょうど1回ずつ出ない：\n" + "\n".join(problems)


def test_D0099_AC_11_分ける前の行の一覧は87行で今の置き場所の表に1回ずつある_守る():
    """D0099-AC-11: 検査そのものの確かめ。固定の一覧 PLACE_ROWS_BEFORE は重なりの無い 87 行で、どれも今の design.md の「## 置き場所」の表の行の第1列にちょうど1回ずつある
    （写し間違いが無い。分ける前も分けたあとも通る。守る）。"""
    assert len(PLACE_ROWS_BEFORE) == 87
    assert len(set(PLACE_ROWS_BEFORE)) == 87
    cells = Counter(first_cell(row) for row in table_rows(place_section(need(DESIGN_MD))))
    problems = [f"{n} 回：{row[:40]}…" for row in PLACE_ROWS_BEFORE if (n := cells[row]) != 1]
    assert problems == [], "\n".join(problems)


PLACE_SAMPLE = """## 置き場所

頭の文。

### アプリ

| やりたいこと | 場所 |
| --- | --- |
| 入口 | `a.py` |

### 作る

| やりたいこと | 場所 |
| --- | --- |
| 作る | `b.py` |

| やりたいこと | 場所 |
| --- | --- |
| 二つ目の表 | `c.py` |

## 本体の依存の向き

| 外の表 | 数えない |
"""


def test_D0099_AC_10_見本_品の見出しと表の拾い方_守る():
    """D0099-AC-10: 検査そのものの確かめ。### ごとの表を数え、「## 置き場所」の外の表と頭の文は数えない。（今のまま通る。守る）"""
    tables = place_tables(PLACE_SAMPLE)
    assert [h for h, _ in tables] == ["アプリ", "作る"]
    assert [len(ts) for _, ts in tables] == [1, 2]
    assert [first_cell(r) for r in tables[0][1][0][2:]] == ["入口"]
    assert place_head(PLACE_SAMPLE).strip() == "頭の文。"


def test_D0099_AC_12_置き場所の頭に品を決める決まりがある():
    """D0099-AC-12: design.md の「## 置き場所」の頭（最初の ### の前）に、品を決める決まり（使う入口の品に入れる・2つ以上の品から使うものは共通）の文がある。"""
    md = need(DESIGN_MD)
    assert [h for h, _ in place_tables(md)], "「## 置き場所」の下に ### の見出しが無い（頭が決まらない）"
    head = place_head(md)
    missing = [w for w in ("使う入口", "2つ以上の品", "共通") if w not in head]
    assert missing == [], f"「## 置き場所」の頭に無い語：{missing}"


# ---- workflow.md と CLAUDE.md（D0099-AC-13・15） ---------------------------------------------------------------


def test_D0099_AC_13_workflowの8の置き場所の行は品の表の近い部品の隣に足す():
    """D0099-AC-13: workflow.md の「8. 並列の作業でぶつからない書き方」の表の置き場所の行に「品の見出し」「近い部品の隣」「1 部品 1 行」「共通」があり、
    節の中に、地図は品・配るもの・向きが変わったときだけ直すことと、直すときは4枚と箇条書きを一緒に直すことが書かれている。"""
    part = need_part(need(WORKFLOW_MD), "## 8. 並列の作業でぶつからない書き方", "docs/development/workflow.md")
    row = next((line for line in part.splitlines() if line.startswith("| 置き場所の表")), None)
    assert row is not None, "「8.」の表に置き場所の行が無い"
    missing = [w for w in ("品の見出し", "近い部品の隣", "1 部品 1 行", "共通") if w not in row]
    assert missing == [], f"置き場所の行に無い語：{missing}"
    rule = next((s for s in re.split(r"(?<=。)|\n", part) if "地図" in s and "ときだけ" in s), None)
    assert rule is not None, "「8.」の節に、地図を直すときの決まり（〜が変わったときだけ直す）の文が無い"
    missing = [w for w in ("品", "配るもの", "向き") if w not in rule]
    assert missing == [], f"地図を直すときの文に無い語：{missing}（{rule}）"
    assert re.search(r"4\s*枚[^\n]*箇条書き[^\n]*一緒に", part), "「8.」の節に、4枚の SVG と箇条書きを一緒に直すことが書かれていない"


def test_D0099_AC_15_CLAUDEのdesignの行に地図があり800字以内():
    """D0099-AC-15: CLAUDE.md の「開発のルール」の表の design.md の行に「地図」の語があり、その行は 800 字以内。"""
    rows = [line for line in need(CLAUDE_MD).splitlines() if line.startswith("| `docs/development/design.md` |")]
    assert len(rows) == 1, f"CLAUDE.md の design.md の行が {len(rows)} 行"
    assert "地図" in rows[0], f"CLAUDE.md の design.md の行に「地図」が無い：{rows[0]}"
    assert len(rows[0]) <= 800, f"CLAUDE.md の design.md の行が {len(rows[0])} 字"


# ---- 4枚の SVG（D0099-AC-19〜24・28） -----------------------------------------------------------------------


def _map_picture_problems(md: str, doc: Path, heading: str, lang: str) -> list[str]:
    where = doc.relative_to(ROOT).as_posix()
    part = map_section(md, heading)
    if not part:
        return [f"{where} に「{heading}」の節が無い"]
    pics = pictures(part)
    if len(pics) != 1:
        return [f"{where} の地図の <picture> が {len(pics)} 個"]
    p = pics[0]
    out = []
    darks = [s for s in p["sources"] if s["media"] == "(prefers-color-scheme: dark)"]
    want = {"dark": SVGS[(lang, "dark")], "light": SVGS[(lang, "light")]}
    if len(darks) != 1:
        out.append(f"{where}：暗い表示の <source media=\"(prefers-color-scheme: dark)\"> が {len(darks)} 個")
    else:
        ref = darks[0]["srcset"]
        if (doc.parent / ref).resolve() != (ASSETS / want["dark"]).resolve():
            out.append(f"{where}：暗い表示の <source> が {want['dark']} を指さない（{ref}）")
    if (doc.parent / p["src"]).resolve() != (ASSETS / want["light"]).resolve():
        out.append(f"{where}：<img> が {want['light']} を指さない（{p['src']}）")
    if not p["alt"].strip():
        out.append(f"{where}：<img> の alt が空")
    if not p["width"].strip():
        out.append(f"{where}：<img> に width が無い")
    return out


def test_D0099_AC_19_4枚のSVGがあり3つの文書のpictureが言語に合う2枚を指す():
    """D0099-AC-19: docs/assets/ に4枚の SVG があり、README.md・design.md の地図の <picture> は日本語の2枚を、README.en.md は英語の2枚を、
    暗い表示の <source media="(prefers-color-scheme: dark)"> に暗い版、<img> に明るい版として指し、<img> に alt と width がある。"""
    problems = [f"docs/assets/{n} が無い" for n in SVGS.values() if not (ASSETS / n).is_file()]
    problems += _map_picture_problems(need(README), README, README_MAP_JA, "ja")
    problems += _map_picture_problems(need(DESIGN_MD), DESIGN_MD, MAP_JA, "ja")
    problems += _map_picture_problems(need(README_EN), README_EN, README_MAP_EN, "en")
    assert problems == [], "\n".join(problems)


def test_D0099_AC_20_同じ言語の明暗の2枚は色のほかが同じで色は色の表の同じ役():
    """D0099-AC-20: 同じ言語の明暗の2枚で、要素の並び・色のほかの属性・文字が同じで、色はどれも色の表の値（明るい版は明るい値、暗い版は暗い値）で、
    同じ場所の色が同じ役の（明るい値, 暗い値）の組になっている。"""
    pal = palette()
    problems = []
    for lang in ("ja", "en"):
        light = svg_path(lang, "light").read_text(encoding="utf-8")
        dark = svg_path(lang, "dark").read_text(encoding="utf-8")
        problems += [f"{lang}: {p}" for p in pair_problems(light, dark, pal)]
    assert problems == [], "\n".join(problems)


def _sample_svg(pal: dict[str, tuple[str, str]], mode: int, x: str = "10") -> str:
    """見本の SVG（mode 0 は明るい値、1 は暗い値）。色は色の表から読む。"""
    c = {role: pair[mode] for role, pair in pal.items()}
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg {SVG_XMLNS} viewBox="0 0 200 100" width="200" height="100" role="img" aria-labelledby="t d">'
        '<title id="t">見本</title><desc id="d">見本の図</desc>'
        '<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto">'
        f'<path d="M0 0 L10 5 L0 10 z" fill="{c["控えめな文字"]}"/></marker></defs>'
        f'<rect x="0" y="0" width="200" height="100" fill="{c["地"]}"/>'
        f'<rect x="{x}" y="10" width="80" height="40" rx="12" fill="{c["面"]}" stroke="{c["押せる所の枠"]}" stroke-width="2"/>'
        f'<line x1="100" y1="30" x2="150" y2="30" stroke="{c["控えめな文字"]}" stroke-width="2.5" stroke-dasharray="10 6" marker-end="url(#arrow)"/>'
        f'<text x="20" y="30" font-size="16" fill="{c["文字"]}" font-family="{FONT_STACKS[1]}" xml:lang="ja">'
        f'<tspan fill="{c["流れる（ティール）"]}">pipe_in/</tspan></text>'
        f'<text x="20" y="80" font-size="14" fill="{c["控えめな文字"]}" font-family="{FONT_STACKS[0]}">読むだけ</text>'
        "</svg>"
    )


def test_D0099_AC_20_見本_明暗の組の食い違いを見つける_守る():
    """D0099-AC-20: 検査そのものの確かめ。色の表から作った明暗の見本の組は通し、座標の違い・役の違う色・暗い版に明るい値・片方だけ none を、それぞれ見つける。（今のまま通る。守る）"""
    pal = palette()
    light, dark = _sample_svg(pal, 0), _sample_svg(pal, 1)
    assert pair_problems(light, dark, pal) == []
    assert any("色のほかの属性" in p for p in pair_problems(light, _sample_svg(pal, 1, x="12"), pal))
    wrong_role = dark.replace(f'fill="{pal["面"][1]}"', f'fill="{pal["線"][1]}"', 1)
    assert any("同じ役の組でない" in p for p in pair_problems(light, wrong_role, pal))
    light_in_dark = dark.replace(f'fill="{pal["面"][1]}"', f'fill="{pal["面"][0]}"', 1)
    assert any("暗い値に無い" in p for p in pair_problems(light, light_in_dark, pal))
    half_none = dark.replace(f'fill="{pal["面"][1]}"', 'fill="none"', 1)
    assert any("none" in p for p in pair_problems(light, half_none, pal))


def test_D0099_AC_20_色の表は地と面と文字の役を明暗の組で持つ_守る():
    """D0099-AC-20: docs/design/README.md の「色の決まり」の表から、地図に使う役（地・面・線・押せる所の枠・文字・控えめな文字・コーラル・ティール・青）の明暗の値が読める。（今のまま通る。守る）"""
    pal = palette()
    roles = ["地", "面", "線", "押せる所の枠", "文字", "控えめな文字", "差す（コーラル）", "流れる（ティール）", "見てほしい"]
    assert [r for r in roles if r not in pal] == [], f"色の表から読めない役：{[r for r in roles if r not in pal]}（今 {sorted(pal)}）"


def test_D0099_AC_21_SVGは許す要素と属性だけで外を読まず100KiB以下():
    """D0099-AC-21: 4枚の SVG が XML として読め、要素と属性がどれも許す一覧の中にあり、外を読む形（script・foreignObject・image・style・href・on…・# で始まらない url(…)・
    <!DOCTYPE・<!ENTITY・http など）が無く、色は色の表の値か none で、1枚の大きさは 100 KiB 以下。"""
    problems = []
    for lang, mode in SVGS:
        p = svg_path(lang, mode)
        size = p.stat().st_size
        if size > MAX_SVG_BYTES:
            problems.append(f"{p.name}：{size} バイト（{MAX_SVG_BYTES} まで）")
        problems += [f"{p.name}：{x}" for x in svg_problems(p.read_text(encoding="utf-8"))]
    assert problems == [], "\n".join(problems)


def _insert(svg: str, piece: str) -> str:
    return svg.replace("</svg>", piece + "</svg>")


def _bad_samples(pal: dict[str, tuple[str, str]]) -> list[tuple[str, str, str]]:
    """（名前, 見本, 問題の文に出るはずの語）。どれも許す見本に1つだけ足したもの。"""
    good = _sample_svg(pal, 0)
    fg = pal["文字"][0]
    rect = f'x="0" y="0" width="1" height="1" fill="{fg}"'
    return [
        ("script の要素", _insert(good, "<script>alert(1)</script>"), "script"),
        ("foreignObject の要素", _insert(good, '<foreignObject width="1" height="1"></foreignObject>'), "foreignObject"),
        ("image の要素", _insert(good, '<image width="1" height="1"/>'), "image"),
        ("use の要素", _insert(good, '<use x="0" y="0"/>'), "use"),
        ("style の要素", _insert(good, "<style>text{fill:red}</style>"), "style"),
        ("style の属性", _insert(good, f'<rect {rect} style="opacity:1"/>'), "style"),
        ("href の属性", _insert(good, f'<rect {rect} href="#t"/>'), "href"),
        (
            "xlink:href の属性",
            _insert(good.replace("<svg ", '<svg xmlns:xlink="http://www.w3.org/1999/xlink" ', 1), f'<rect {rect} xlink:href="#t"/>'),
            "href",
        ),
        ("onload の属性", _insert(good, f'<rect {rect} onload="go()"/>'), "onload"),
        ("transform の属性", _insert(good, f'<rect {rect} transform="rotate(1)"/>'), "transform"),
        ("http の参照", _insert(good, f'<text x="0" y="0" fill="{fg}" font-family="{FONT_STACKS[0]}">https://example.com/x</text>'), "http"),
        ("url(http…) の値", good.replace('marker-end="url(#arrow)"', 'marker-end="url(http://example.com/a.svg#m)"'), "url("),
        ("<!DOCTYPE", good.replace("<svg ", '<!DOCTYPE svg [<!ENTITY x "y">]>\n<svg ', 1), "<!DOCTYPE"),
        ("<!ENTITY", good.replace("<svg ", '<!ENTITY x "y">\n<svg ', 1), "<!ENTITY"),
        ("<?xml-stylesheet", good.replace("<svg ", '<?xml-stylesheet href="a.css"?>\n<svg ', 1), "xml-stylesheet"),
        ("javascript:", _insert(good, f'<text x="0" y="0" fill="{fg}" font-family="{FONT_STACKS[0]}">javascript:go()</text>'), "javascript:"),
        ("@import", _insert(good, f'<text x="0" y="0" fill="{fg}" font-family="{FONT_STACKS[0]}">@import a</text>'), "@import"),
        ("知らない色", _insert(good, '<rect x="0" y="0" width="1" height="1" fill="#123456"/>'), "#123456"),
        ("大文字の色", _insert(good, f'<rect x="0" y="0" width="1" height="1" fill="{fg.upper()}"/>'), fg.upper()),
        ("決めていない書体", _insert(good, f'<text x="0" y="0" fill="{fg}" font-family="Comic Sans MS">a</text>'), "font-family"),
        ("url( でない marker-end", good.replace('marker-end="url(#arrow)"', 'marker-end="#arrow"'), "marker-end"),
        ("SVG の外の名前空間の要素", _insert(good, '<x:thing xmlns:x="urn:x"/>'), "名前空間"),
        ("読めない XML", _insert(good, "<rect"), "読めない"),
    ]


def test_D0099_AC_21_見本_許す形は通し止める形を1つずつ見つける():
    """D0099-AC-21: 検査そのものの確かめ。色の表から作った許す形の見本は通し、止める形（script・foreignObject・image・use・style の要素、style・href・xlink:href・onload・transform の属性、
    http の参照、url(http…)、<!DOCTYPE、<!ENTITY、<?xml-stylesheet、javascript:、@import、知らない色、決めていない書体、SVG の外の名前空間、読めない XML）を1つずつ入れた見本は、その語の問題として見つける。"""
    pal = palette()
    assert "#123456" not in {c for pair in pal.values() for c in pair}, "見本の知らない色が色の表にある（テストの誤り）"
    assert svg_problems(_sample_svg(pal, 0)) == []
    assert svg_problems(_sample_svg(pal, 1)) == []
    missed = []
    for name, sample, word in _bad_samples(pal):
        found = svg_problems(sample)
        if not any(word in p for p in found):
            missed.append(f"{name}：「{word}」の問題が出ない（出た問題：{found}）")
    assert missed == [], "\n".join(missed)


def test_D0099_AC_22_SVGの文字に品と凡例と名前の形がありパスが実在する():
    """D0099-AC-22: 4枚の SVG の文字に、品の名前4つ（英語の2枚は App・Build・Plugin・Dev）・凡例の3種・名前の形（/pipe-*・pipe-in-*・/pipe-in:*・pipe-*）があり、
    文字に出るパスの形の語とモジュールの名前（pipe_in.pipe・pipe_in.engine）がどれもリポジトリに実在する。"""
    problems = []
    for (lang, mode), name in SVGS.items():
        texts = svg_texts(svg_root(lang, mode))
        joined = "\n".join(texts)
        kinds = KINDS_JA if lang == "ja" else KINDS_EN
        legend = LEGEND_JA if lang == "ja" else LEGEND_EN
        problems += [f"{name}：品の名前 {k} が無い" for k in kinds if not re.search(rf"(?<![A-Za-z]){re.escape(k)}(?![A-Za-z])", joined)]
        problems += [f"{name}：凡例の {w} が無い" for w in legend if w not in joined]
        words = code_words(texts)
        problems += [f"{name}：名前の形 {f} が無い" for f in NAME_FORMS if f not in words]
        problems += [f"{name}：モジュールの名前 {m} が無い" for m in ("pipe_in.pipe", "pipe_in.engine") if m not in words]
        problems += [f"{name}：{w} が実在しない" for w in path_words(words) if not exists_in_repo(w)]
    assert problems == [], "\n".join(problems)


def test_D0099_AC_23_日本語のSVGのパスはdesignの地図の節にも出る():
    """D0099-AC-23: 日本語の SVG の文字に出るパスの形の語とモジュールの名前が、どれも design.md の地図の節のバッククォートの語の中にも出る（画像と箇条書きの中身がずれない）。"""
    tokens = backticks(need_part(need(DESIGN_MD), MAP_JA, "docs/development/design.md"))
    problems = []
    for mode in ("light", "dark"):
        words = path_words(code_words(svg_texts(svg_root("ja", mode))))
        if not words:
            problems.append(f"{SVGS[('ja', mode)]} の文字にパスが無い")
        problems += [f"{SVGS[('ja', mode)]} の {w} が design.md の地図の節に無い" for w in words if not any(w in t for t in tokens)]
    assert problems == [], "\n".join(problems)


def test_D0099_AC_23_READMEと英語版のaltと箇条書きに品と置き場所がある():
    """D0099-AC-23: README.md と README.en.md の地図の <img> の alt が空でなく、箇条書きに品の名前（英語版は英語の品の名前）と置き場所がある。"""
    problems = []
    for doc, heading, kinds in ((README, README_MAP_JA, KINDS_JA), (README_EN, README_MAP_EN, KINDS_EN)):
        where = doc.name
        part = need_part(need(doc), heading, where)
        pics = pictures(part)
        if not pics or not pics[0]["alt"].strip():
            problems.append(f"{where}：地図の <img> の alt が空か、<picture> が無い")
        items = bullets(part)
        problems += [f"{where}：箇条書きに {k} が無い" for k in kinds if k not in items]
        problems += [f"{where}：箇条書きに `{p}` が無い" for p in PLACES if f"`{p}`" not in items]
    assert problems == [], "\n".join(problems)


def test_D0099_AC_24_SVGの文字の色は地と面の両方に4_5以上():
    """D0099-AC-24: 4枚の SVG のどの <text> も色（fill）を自分で持ち、その色（と、色を持つ tspan の色）と、その版の地の色・面の色のどちらとのコントラスト比も 4.5 以上。"""
    pal = palette()
    problems = []
    for (lang, mode), name in SVGS.items():
        i = 0 if mode == "light" else 1
        bg, panel = pal["地"][i], pal["面"][i]
        root = svg_root(lang, mode)
        texts = list(root.iter(f"{{{SVG_NS}}}text"))
        if not texts:
            problems.append(f"{name}：<text> が無い")
        for el in texts:
            label = "".join(el.itertext())[:20]
            if "fill" not in el.attrib:
                problems.append(f"{name}：<text>「{label}」が fill を持たない")
                continue
            colored = [el, *[t for t in el.iter(f"{{{SVG_NS}}}tspan") if "fill" in t.attrib]]
            for t in colored:
                color = t.attrib["fill"]
                if not re.fullmatch(r"#[0-9a-f]{6}", color):
                    problems.append(f"{name}：「{label}」の色 {color} が #rrggbb でない")
                    continue
                for base_name, base in (("地", bg), ("面", panel)):
                    ratio = contrast(color, base)
                    if ratio < MIN_CONTRAST:
                        problems.append(f"{name}：「{label}」の色 {color} と{base_name} {base} の比が {ratio:.2f}")
    assert problems == [], "\n".join(problems)


def test_D0099_AC_24_見本_コントラスト比の計算は黒と白で21_同じ色で1_守る():
    """D0099-AC-24: 検査そのものの確かめ。黒と白の比は 21、同じ色の比は 1、向きを入れ替えても同じ。（今のまま通る。守る）"""
    assert contrast("#000000", "#ffffff") == pytest.approx(21.0)
    assert contrast("#ffffff", "#000000") == pytest.approx(21.0)
    assert contrast("#6b625c", "#6b625c") == pytest.approx(1.0)
    assert contrast("#777777", "#ffffff") < MIN_CONTRAST < contrast("#595959", "#ffffff")


def test_D0099_AC_28_日英の同じ表示の2枚は要素の数とコードの語の並びが同じ():
    """D0099-AC-28: 日本語と英語の同じ表示の2枚で、要素の種類ごとの数（<text> を含む）が同じで、文字の中のコードの形の語（パス・コマンド・名前の形・モジュールの名前）の並びが同じ。"""
    problems = []
    for mode in ("light", "dark"):
        ja, en = svg_root("ja", mode), svg_root("en", mode)
        ja_count = Counter(_local(e.tag)[1] for e in ja.iter() if isinstance(e.tag, str))
        en_count = Counter(_local(e.tag)[1] for e in en.iter() if isinstance(e.tag, str))
        if ja_count != en_count:
            problems.append(f"{mode}：要素の種類ごとの数が違う（日本語 {dict(ja_count)}、英語 {dict(en_count)}）")
        ja_words, en_words = code_words(svg_texts(ja)), code_words(svg_texts(en))
        if not ja_words:
            problems.append(f"{mode}：日本語の文字にコードの語が無い")
        if ja_words != en_words:
            problems.append(f"{mode}：コードの語の並びが違う（日本語 {ja_words}、英語 {en_words}）")
    assert problems == [], "\n".join(problems)


def test_D0099_AC_28_見本_コードの語の抜き方は説明の文の語を拾わない_守る():
    """D0099-AC-28: 検査そのものの確かめ。説明の文の語（import・runs a command・pipes・guard-hook・state.json）は拾わず、パス・名前の形・コマンド・モジュールの名前だけを順に拾い、
    文の末尾の . は外す。パスの形とモジュールの名前だけが path_words に残る。（今のまま通る。守る）"""
    texts = [
        "import（コードを読み込む）",
        "reads only (records and pipes)",
        "pipe-in のリポジトリの地図",
        "generator/ の裏の道具（guard-hook・chat・judge-score）",
        "/pipe-in:*・pipe-*",
        "pipe_in.engine.",
        "実行の記録（state.json）",
    ]
    words = code_words(texts)
    assert words == ["pipe-in", "generator/", "/pipe-in:*", "pipe-*", "pipe_in.engine"]
    assert path_words(words) == ["generator/", "pipe_in.engine"]
    assert exists_in_repo("pipe_in.engine") and not exists_in_repo("pipe_in.nothing")


# ---- docs/assets/README.md（D0099-AC-25） ----------------------------------------------------------------


def test_D0099_AC_25_assetsのREADMEに4枚の行がある():
    """D0099-AC-25: docs/assets/README.md の「ここにあるもの」の表に、4枚の SVG の名前を第1列に持つ行があり、その行に「撮らない」と D0099 がある。"""
    part = need_part(need(ASSETS_README), "## ここにあるもの", "docs/assets/README.md")
    rows = table_rows(part)
    problems = []
    for name in SVGS.values():
        row = next((r for r in rows if f"`{name}`" in first_cell(r)), None)
        if row is None:
            problems.append(f"{name} を第1列に持つ行が無い")
            continue
        problems += [f"{name} の行に「{w}」が無い" for w in ("撮らない", "D0099") if w not in row]
    assert problems == [], "\n".join(problems)
