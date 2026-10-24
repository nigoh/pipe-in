"""パイプを作る・見る・検査するコマンド:

  pipe-in-gen list / new <名前> --from <ひな形> / design <名前> --purpose "目的" / check <名前>

パイプは対象の .pipe-in/pipes/pipe-in-<名前>/ に作る（--pipes-dir か PIPE_IN_PIPES_DIR があればそこ）。
探すときは、対象の .pipe-in/pipes/ → 前の版の置き場所 → 今までの場所（環境変数か、このリポジトリの pipes/）の順。
同じ名前のパイプがほかの置き場所や前の版のフォルダ名であれば、作らずに断る（どちらを使うか迷わないように）。
guard-hook は、Claude Code のプラグイン（plugin/hooks/hooks.json）から呼ぶフック。
judge-score は、プラグインの pipe-judge が審査役の採点（標準入力の JSON）から総合点・合否を計算させるのに呼ぶ。
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from pipe_in.pipe import definition as pd
from pipe_in.pipe.lint import lint_pipe

from .detect import detect
from .render import render_template, template_values

RENDERED_SUFFIXES = {".toml": True, ".md": False}  # 拡張子 → TOML として埋めるか


def templates_dir() -> Path:
    return Path(__file__).resolve().parent / "templates"


def _templates() -> list[Path]:
    d = templates_dir()
    return sorted(p for p in d.iterdir() if (p / pd.PIPE_FILE).is_file()) if d.is_dir() else []


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="pipe-in-gen", description="pipe-in のパイプ（<対象>/.pipe-in/pipes/pipe-in-<名前>/）を作る・見る・検査します。")
    sub = p.add_subparsers(dest="command", required=True)

    def common(sp: argparse.ArgumentParser, *, project: bool) -> None:
        sp.add_argument(
            "--pipes-dir",
            type=Path,
            help=f"パイプを置くフォルダ。指定するとそこだけを使う（既定: 作るのは {pd.PIPES_DIR_ENV} か対象の .pipe-in/pipes/、"
            "探すのは対象の .pipe-in/pipes/ → 前の版の置き場所 → 今までの場所）",
        )
        if project:
            sp.add_argument("--project", type=Path, default=Path("."), help="対象プロジェクトのフォルダ（既定: 今のフォルダ）")

    common(sub.add_parser("list", help="ひな形と、作ったパイプの一覧"), project=True)
    sub.add_parser("guard-hook", help="Claude Code のプラグインから呼ぶフック（標準入力の JSON を見て、pipe-builder と pipe-judge の操作を絞る）")
    sub.add_parser("judge-score", help="審査役の採点（標準入力の JSON）から総合点・合否・ばらつきを出す（プラグインの pipe-judge が呼ぶ）")

    new = sub.add_parser("new", help="ひな形から .pipe-in/pipes/pipe-in-<名前>/ を作る")
    new.add_argument("name", help="作るパイプの名前（英小文字・数字・-）")
    new.add_argument("--from", dest="template", required=True, help="もとにするひな形（pipe-in-gen list で一覧）")
    new.add_argument("--force", action="store_true", help="同じ名前のパイプがあっても作り直す")
    common(new, project=True)

    ds = sub.add_parser("design", help="目的から段を組んで .pipe-in/pipes/pipe-in-<名前>/ を作る（Claude が対象を読んで設計する。利用料がかかる）")
    ds.add_argument("name", help="作るパイプの名前（英小文字・数字・-）")
    ds.add_argument("--purpose", required=True, help="何のためのパイプか（例: 仕様書から API の文書を作り、ソースと突き合わせたい）")
    ds.add_argument("--model", help="設計に使うモデル（既定: Claude Code の既定）")
    ds.add_argument("--force", action="store_true", help="同じ名前のパイプがあっても作り直す")
    common(ds, project=True)

    ck = sub.add_parser("check", help="パイプの定義を検査する")
    ck.add_argument("name", help="パイプの名前かフォルダのパス")
    common(ck, project=True)
    return p.parse_args(argv)


def _project(path: Path) -> Path:
    project = path.expanduser().resolve()
    if not project.is_dir():
        raise SystemExit(f"プロジェクトのフォルダが見つかりません: {project}")
    return project


def _label(pipe_dir: Path) -> str:
    try:
        return pd.load_pipe(pipe_dir).label
    except pd.PipeError:
        return "（読めません）"


def cmd_list(dirs: list[Path]) -> int:
    print("ひな形（pipe-in-gen new <名前> --from <ひな形> で使う）:\n")
    for t in _templates():
        print(f"  {t.name:<12}  {_label(t)}")
    print("\n作ったパイプ（pipe-in --pipe <名前> で流す。同じ名前なら上の場所が先）:")
    for pipes_dir in dirs:
        pipes = pd.list_pipes(pipes_dir)
        print(f"\n  {pipes_dir}\n")
        if not pipes:
            print("    （まだありません）")
        for d in pipes:
            name = pd.name_of(d.name) or d.name
            mark = "  （古い名前）" if pd.is_legacy(d) else ""
            print(f"    {name:<12}  {_label(d)}{mark}")
    return 0


def _clash(name: str, dest: Path, project: Path) -> list[Path]:
    """作る先（dest）のほかにある、同じ名前のパイプのフォルダ（作る置き場所の古いフォルダ名・ほかの置き場所）。"""
    found = pd.existing_pipes(name, [dest.parent, *pd.pipes_dirs(project)])
    return [d for d in found if d.resolve() != dest.resolve()]


def refuse_clash(name: str, dest: Path, project: Path) -> bool:
    """同じ名前のパイプがほかにあれば、場所を示して True（作らない）。--force でも作らない。"""
    others = _clash(name, dest, project)
    for d in others:
        print(f"✗ 同じ名前のパイプが {d} にあります。そちらを直すか、別の名前にしてください")
    return bool(others)


def _report(pipe: pd.PipeDef, errors: list[str], warnings: list[str] | None = None) -> int:
    warnings = warnings or []
    if errors:
        print(f"✗ パイプ「{pipe.name}」に誤りがあります:")
        for e in errors:
            print(f"  - {e}")
        for w in warnings:
            print(f"⚠ {w}")
        return 1
    if warnings:
        print(f"✓ パイプ「{pipe.name}」: 誤りはありません（注意 {len(warnings)} 件）")
        for w in warnings:
            print(f"⚠ {w}")
        return 0
    print(f"✓ パイプ「{pipe.name}」: 問題ありません")
    return 0


def cmd_check(pipes_dir: Path | None, project: Path, name: str) -> int:
    path = pd.find_pipe(name, pipes_dir, project=project)
    if path is None:
        print(f"✗ パイプ「{name}」が見つかりません（pipe-in-gen list で一覧を出せます）")
        return 1
    try:
        pipe = pd.load_pipe(path)
    except pd.PipeError as e:
        print(f"✗ {e}")
        return 1
    return _report(pipe, pd.check_pipe(pipe, project), lint_pipe(pipe))


def _write_from_template(template: Path, dest: Path, values: dict[str, str | None]) -> None:
    for src in sorted(template.rglob("*")):
        if not src.is_file() or "__pycache__" in src.parts:
            continue
        out = dest / src.relative_to(template)
        out.parent.mkdir(parents=True, exist_ok=True)
        if src.suffix in RENDERED_SUFFIXES:
            text = render_template(src.read_text(encoding="utf-8"), values, toml=RENDERED_SUFFIXES[src.suffix])
            out.write_text(text, encoding="utf-8")
        else:
            shutil.copyfile(src, out)


def cmd_new(pipes_dir: Path, project: Path, name: str, template_name: str, force: bool) -> int:
    if not pd.is_valid_name(name):
        print(f"✗ パイプの名前「{name}」は使えません（英小文字・数字・- だけ。logs は不可）")
        return 1
    template = templates_dir() / template_name
    if not pd.is_valid_name(template_name) or not (template / pd.PIPE_FILE).is_file():
        names = ", ".join(t.name for t in _templates())
        print(f"✗ ひな形「{template_name}」はありません（{names}）")
        return 1
    dest = pipes_dir / f"{pd.PREFIX}{name}"
    if refuse_clash(name, dest, project):
        return 1
    if dest.exists():
        if not force:
            print(f"✗ {dest} はもうあります。作り直すなら --force を付けてください")
            return 1
        if not (dest / pd.PIPE_FILE).is_file():
            print(f"✗ {dest} はパイプのフォルダではないため、作り直しません")
            return 1
        shutil.rmtree(dest)

    env = detect(project)
    _write_from_template(template, dest, template_values(env, name))
    print(f"✓ {dest} を作りました（ひな形: {template_name}）")
    print(
        f"  見つけた環境: 言語 {', '.join(env.languages) or '不明'}・テスト {env.test_command or 'なし'}・"
        f"ソース {', '.join(env.source_dirs)}・文書 {', '.join(env.docs_dirs) or 'なし'}"
    )
    try:
        pipe = pd.load_pipe(dest)
    except pd.PipeError as e:
        print(f"✗ {e}")
        return 1
    result = _report(pipe, pd.check_pipe(pipe, project), lint_pipe(pipe))
    if result == 0:
        print("\n中身は自由に直せます（段の並び・権限・確認は pipe.toml、指示は prompts/）。直したら pipe-in-gen check で確かめてください。")
        need = {"required": ' --text "依頼メモ"', "optional": ' [--text "依頼メモ"]'}.get(pipe.input, "")
        print(f"流す: pipe-in --pipe {name} --project <対象のフォルダ>{need}")
    return result


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["guard-hook"]:
        # 道具を呼ぶたびに動くので、引数の解釈もせずにすぐ答える
        from .guard_hook import main as hook_main

        return hook_main()
    if argv[:1] == ["judge-score"]:
        # 標準入力の JSON だけで動く（--project は持たないので、プロジェクトの検めより前に分ける）
        from .judge_score import main as judge_main

        return judge_main()
    args = _parse_args(argv)
    given = args.pipes_dir.expanduser() if args.pipes_dir else None
    project = _project(args.project)
    if args.command == "list":
        return cmd_list(pd.pipes_dirs(project, given))
    if args.command == "check":
        return cmd_check(given, project, args.name)
    pipes_dir = pd.new_pipes_dir(project, given)
    if args.command == "design":
        from .design import design_pipe

        return design_pipe(project, args.name, args.purpose, pipes_dir=pipes_dir, force=args.force, model=args.model)
    return cmd_new(pipes_dir, project, args.name, args.template, args.force)

