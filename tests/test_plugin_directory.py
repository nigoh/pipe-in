"""プラグインを Anthropic のディレクトリの事前チェックに通る形にする（D0095）。

検査の関数はこのファイルの中に置く（本番のコードではない）。実物（plugin/・README・ガイド）を渡して違反が空であることと、
tmp_path に作った偽の入力で関数が違反を見つけることを、それぞれ確かめる。決まり（上限の数・禁止の名前・フックのイベント名）は
2026-11-12 に読んだ公式の文書による。変わったら、このファイルの先頭の定数と docs/guide/plugin.md の申請の節だけ直す。
"""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path

import pytest

from test_readme import png_size  # noqa: F401  （PNG の幅・高さの読み方。tests/test_english_docs.py と同じ使い方）

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugin"
README = PLUGIN / "README.md"
ICON = PLUGIN / ".claude-plugin/icon.png"
PLUGIN_JSON = PLUGIN / ".claude-plugin/plugin.json"
MARKET_JSON = ROOT / ".claude-plugin/marketplace.json"
HOOKS_JSON = PLUGIN / "hooks/hooks.json"
GUIDE = ROOT / "docs/guide/plugin.md"

INSTALL_ONE_LINE = "/plugin install pipe-in --marketplace nigoh/pipe-in"
AUTHOR_URL = "https://github.com/nigoh"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

# ---- 公式の決まり（2026-11-12 に取り直した一覧） ------------------------------------------------------

HOOK_EVENTS = {
    "SessionStart", "Setup", "UserPromptSubmit", "UserPromptExpansion", "PreToolUse", "PermissionRequest", "PermissionDenied",
    "PostToolUse", "PostToolUseFailure", "PostToolBatch", "Notification", "MessageDisplay", "SubagentStart", "SubagentStop",
    "TaskCreated", "TaskCompleted", "Stop", "StopFailure", "TeammateIdle", "InstructionsLoaded", "ConfigChange", "CwdChanged",
    "DirectoryAdded", "FileChanged", "WorktreeCreate", "WorktreeRemove", "PreCompact", "PostCompact", "PreModelSwitch",
    "PostModelSwitch", "Elicitation", "ElicitationResult", "SessionEnd",
}
HOOK_TYPES = {"command", "http", "mcp_tool", "prompt", "agent"}
COMMAND_HOOK_KEYS = {"type", "if", "timeout", "statusMessage", "once", "command", "args", "async", "asyncRewake", "shell", "onFailure"}
INLINE_PROGRAMS = {"python", "python3", "node", "sh", "bash", "zsh", "pwsh", "powershell", "cmd", "ruby", "perl", "deno", "bun"}
INLINE_FLAGS = {"-c", "-e", "--eval", "-Command", "/c", "-command", "-p", "--print"}
RESERVED_NAMES = {"claude", "anthropic", "claude-code", "claude-plugin", "anthropic-official", "claude-official"}
IMAGE_FONT_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".woff", ".woff2", ".ttf", ".otf"}
JUNK_NAMES = {".DS_Store", "Thumbs.db", "desktop.ini", "__MACOSX"}
WINDOWS_RESERVED = {"con", "prn", "aux", "nul"} | {f"com{i}" for i in range(1, 10)} | {f"lpt{i}" for i in range(1, 10)}
NETWORK_WORDS = ["WebFetch", "WebSearch", "ArtifactData", "Artifact"]

EN_HEADINGS = ["Install", "What's included", "What it runs", "Where it works"]
JA_HEADINGS = ["入れ方", "入るもの", "動かすもの", "使える場所"]


# ---- 検査の関数（入力を読んで違反の文の一覧を返す。空なら合う） ----------------------------------------


def readme_words(md: str) -> int:
    """コードの囲み（```）を除いた、空白区切りの語数。"""
    out: list[str] = []
    fenced = False
    for line in md.splitlines():
        if line.strip().startswith("```"):
            fenced = not fenced
            continue
        if not fenced:
            out.append(line)
    return len("\n".join(out).split())


def split_languages(md: str) -> tuple[str, str]:
    """（英語の節, 日本語の節）。見出し行 `## English` と `## 日本語` で分ける。無い節は空。"""
    lines = md.splitlines()
    en_at = next((i for i, ln in enumerate(lines) if ln.strip() == "## English"), None)
    ja_at = next((i for i, ln in enumerate(lines) if ln.strip() == "## 日本語"), None)
    en = ""
    ja = ""
    if en_at is not None:
        end = ja_at if ja_at is not None and ja_at > en_at else len(lines)
        en = "\n".join(lines[en_at + 1 : end])
    if ja_at is not None:
        end = en_at if en_at is not None and en_at > ja_at else len(lines)
        ja = "\n".join(lines[ja_at + 1 : end])
    return en, ja


def language_headings(section: str) -> list[str]:
    """節の中の `### ` 見出しの文字。"""
    return [m.group(1).strip() for m in re.finditer(r"^###\s+(.+)$", section, re.M)]


def heading_problems(section: str, required: list[str], label: str) -> list[str]:
    heads = language_headings(section)
    return [f"{label}の節に「{w}」の見出しが無い" for w in required if not any(w in h for h in heads)]


def subsection(section: str, word: str) -> str:
    """`### ` 見出しに word を含む小節の本文（次の `## `・`### ` の手前まで）。無ければ空。"""
    lines = section.splitlines()
    for i, ln in enumerate(lines):
        if re.match(r"^###\s", ln) and word in ln:
            body: list[str] = []
            for nxt in lines[i + 1 :]:
                if re.match(r"^#{2,3}\s", nxt):
                    break
                body.append(nxt)
            return "\n".join(body)
    return ""


def readme_install_lines(section: str) -> list[str]:
    problems = []
    if INSTALL_ONE_LINE not in section:
        problems.append(f"「{INSTALL_ONE_LINE}」の行が無い")
    if not any("pip install -e ." in ln for ln in section.splitlines()):
        problems.append("「pip install -e .」の行が無い")
    return problems


def plugin_names(plugin_dir: Path) -> tuple[list[str], list[str]]:
    """（スキル名, エージェント名）。スキルは skills/*/SKILL.md のフォルダ名、エージェントは agents/*.md のファイル名。"""
    skills = sorted(p.parent.name for p in (plugin_dir / "skills").glob("*/SKILL.md"))
    agents = sorted(p.stem for p in (plugin_dir / "agents").glob("*.md"))
    return skills, agents


def plugin_doc_text(plugin_dir: Path) -> str:
    parts = [p.read_text(encoding="utf-8") for p in sorted((plugin_dir / "skills").rglob("*.md"))]
    parts += [p.read_text(encoding="utf-8") for p in sorted((plugin_dir / "agents").glob("*.md"))]
    return "\n".join(parts)


def _has_word(text: str, name: str) -> bool:
    return re.search(r"(?<![\w-])" + re.escape(name) + r"(?![\w-])", text) is not None


def readme_drift(section: str, skills: list[str], agents: list[str], gen_subcommands: set[str], live_subcommands: set[str], doc_text: str) -> list[str]:
    """README の言語の節（英語か日本語のどちらか1つ）と、実物のずれ。"""
    problems: list[str] = []
    for name in skills:
        if not _has_word(section, name):
            problems.append(f"スキル {name} が README に無い")
    for name in agents:
        if not _has_word(section, name):
            problems.append(f"エージェント {name} が README に無い")
    for ref in sorted(set(re.findall(r"/pipe-in:([a-z][a-z0-9-]*)", section))):
        if ref not in skills:
            problems.append(f"README の /pipe-in:{ref} は実物のスキルに無い")
    included = subsection(section, "What's included") or subsection(section, "入るもの")
    for first in re.findall(r"^\|\s*`([^`]+)`", included, re.M):
        name = first.removeprefix("/pipe-in:")
        if name not in set(skills) | set(agents):
            problems.append(f"README の表の {first} は実物のスキル・エージェントに無い")
    runs = subsection(section, "What it runs") or subsection(section, "動かすもの")
    if not runs:
        problems.append("「動かすもの」の小節が無い")
    needed = {f"pipe-in-gen {s}" for s in re.findall(r"pipe-in-gen\s+([a-z][a-z-]*)", doc_text) if s in gen_subcommands}
    needed |= {f"pipe-in live {s}" for s in re.findall(r"pipe-in live\s+([a-z][a-z-]*)", doc_text) if s in live_subcommands}
    needed |= {"pipe-in-gen guard-hook", "pipe-in live watch"}
    for cmd in sorted(needed):
        if cmd not in runs:
            problems.append(f"「動かすもの」に {cmd} が無い")
    for sub in re.findall(r"`pipe-in-gen\s+([a-z][a-z-]*)[^`]*`", runs):
        if sub not in gen_subcommands:
            problems.append(f"README の pipe-in-gen {sub} は本物のサブコマンドではない")
    sends = runs
    external = [u for u in re.findall(r"https?://[^\s)`>\]]+", doc_text) if "github.com/nigoh/pipe-in" not in u]
    words = [w for w in NETWORK_WORDS if w in doc_text] + (["https://"] if external else [])
    for w in words:
        if w not in sends:
            problems.append(f"スキル・エージェントの文に {w} があるのに「送るもの・取ってくるもの」に無い")
    return problems


def png_problems(path: Path) -> list[str]:
    if not path.is_file():
        return [f"{path.name} が無い"]
    data = path.read_bytes()
    if data[:8] != PNG_SIGNATURE:
        return ["PNG の署名で始まらない"]
    try:
        width, height = png_size(path)
    except ValueError as e:
        return [str(e)]
    problems = []
    if width != height:
        problems.append(f"正方形でない（{width}x{height}）")
    if not (512 <= width <= 2048 and 512 <= height <= 2048):
        problems.append(f"512〜2048 の範囲でない（{width}x{height}）")
    if len(data) >= 2_000_000:
        problems.append(f"2,000,000 バイト以上（{len(data)}）")
    return problems


def _nonempty_str(v: object) -> bool:
    return isinstance(v, str) and bool(v.strip())


def _keywords_ok(v: object) -> bool:
    return isinstance(v, list) and bool(v) and all(_nonempty_str(k) for k in v)


def manifest_problems(m: dict) -> list[str]:
    problems = []
    name = m.get("name")
    if not isinstance(name, str) or not re.fullmatch(r"[a-z0-9-]+", name) or len(name) > 64:
        problems.append("name が小文字・数字・ハイフンの64字以下でない")
    elif name in RESERVED_NAMES:
        problems.append(f"name {name} は予約された単語")
    for key in ("description", "version", "displayName"):
        if not _nonempty_str(m.get(key)):
            problems.append(f"{key} が無いか空")
    author = m.get("author")
    if not isinstance(author, dict) or not _nonempty_str(author.get("name")):
        problems.append("author.name が無いか空")
    elif "url" in author and not str(author["url"]).startswith("https://"):
        problems.append("author.url が https:// でない")
    for key in ("homepage", "repository"):
        if not (_nonempty_str(m.get(key)) and m[key].startswith("https://")):
            problems.append(f"{key} が https:// で始まる文字列でない")
    if not _keywords_ok(m.get("keywords")):
        problems.append("keywords が空でない文字列の配列でない")
    return problems


def market_problems(m: dict) -> list[str]:
    problems = []
    if not _nonempty_str(m.get("name")):
        problems.append("name が無い")
    owner = m.get("owner")
    if not isinstance(owner, dict) or not _nonempty_str(owner.get("name")):
        problems.append("owner.name が無い")
    elif "url" in owner and not str(owner["url"]).startswith("https://"):
        problems.append("owner.url が https:// でない")
    plugins = m.get("plugins")
    if not isinstance(plugins, list) or not plugins:
        return problems + ["plugins が空"]
    for i, e in enumerate(plugins):
        tag = f"plugins[{i}]"
        if not _nonempty_str(e.get("name")):
            problems.append(f"{tag}.name が無い")
        if not (_nonempty_str(e.get("source")) and e["source"].startswith("./")):
            problems.append(f"{tag}.source が ./ で始まらない")
        for key in ("displayName", "category", "description"):
            if not _nonempty_str(e.get(key)):
                problems.append(f"{tag}.{key} が無いか空")
        for key in ("homepage", "repository"):
            if not (_nonempty_str(e.get(key)) and e[key].startswith("https://")):
                problems.append(f"{tag}.{key} が https:// で始まる文字列でない")
        if not _keywords_ok(e.get("keywords")):
            problems.append(f"{tag}.keywords が空でない文字列の配列でない")
        if not _keywords_ok(e.get("tags")):
            problems.append(f"{tag}.tags が空でない文字列の配列でない")
    return problems


PLUGIN_ONLY_FIELDS = ("icon", "documentationUrl", "supportUrl", "privacyPolicyUrl", "termsOfServiceUrl")
SHARED_LISTING_FIELDS = ("displayName", "homepage", "repository", "keywords", "license", "author")
DOCUMENTATION_URL = "https://github.com/nigoh/pipe-in/blob/main/docs/guide/plugin.md"
SUPPORT_URL = "https://github.com/nigoh/pipe-in/issues"


def icon_problems(manifest: dict, plugin_dir: Path) -> list[str]:
    """plugin.json の icon が、プラグインのフォルダの中の実在する PNG（AC-07 の形）を指しているか。"""
    icon = manifest.get("icon")
    if not _nonempty_str(icon):
        return ["icon が無いか空"]
    if not icon.startswith("./"):
        return ["icon が ./ で始まらない"]
    if ".." in Path(icon).parts or ".." in icon.split("/"):
        return ["icon に .. がある"]
    target = (plugin_dir / icon).resolve()
    try:
        target.relative_to(plugin_dir.resolve())
    except ValueError:
        return ["icon がプラグインのフォルダの外を指す"]
    if target.suffix.lower() != ".png":
        return ["icon が .png でない"]
    return png_problems(target)


def listing_url_problems(manifest: dict) -> list[str]:
    """documentationUrl・supportUrl が https:// で始まる文字列か。privacyPolicyUrl・termsOfServiceUrl は書かない。"""
    problems = []
    for key in ("documentationUrl", "supportUrl"):
        if not (_nonempty_str(manifest.get(key)) and manifest[key].startswith("https://")):
            problems.append(f"{key} が https:// で始まる文字列でない")
    for key in ("privacyPolicyUrl", "termsOfServiceUrl"):
        if key in manifest:
            problems.append(f"{key} は書かない（書く先が無い）")
    return problems


def market_plugin_only_problems(market: dict) -> list[str]:
    """marketplace の項目に plugin.json だけに書く欄（icon など）がある違反。"""
    problems = []
    for i, e in enumerate(market.get("plugins", [])):
        for key in PLUGIN_ONLY_FIELDS:
            if key in e:
                problems.append(f"plugins[{i}].{key} は plugin.json にだけ書く")
    return problems


def listing_mismatch_problems(market: dict, manifest: dict) -> list[str]:
    """両方にある表示の欄（description は比べない）の値が食い違う違反。片方にしか無い欄は比べない。"""
    problems = []
    for i, e in enumerate(market.get("plugins", [])):
        for key in SHARED_LISTING_FIELDS:
            if key in e and key in manifest and e[key] != manifest[key]:
                problems.append(f"plugins[{i}].{key} が plugin.json と違う")
    return problems


def _files(root: Path) -> list[Path]:
    out = []
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root).parts
        if "__pycache__" in rel or ("evals" in rel and "results" in rel[rel.index("evals") + 1 :]):
            continue
        if p.is_file() and not p.is_symlink():
            out.append(p)
    return out


def size_problems(root: Path, text_limit: int = 256 * 1024, file_limit: int = 5 * 1024 * 1024, count_limit: int = 512) -> list[str]:
    files = _files(root)
    problems = []
    for p in files:
        size = p.stat().st_size
        rel = p.relative_to(root).as_posix()
        if size >= file_limit:
            problems.append(f"{rel} が {file_limit} バイト以上（{size}）")
        elif p.suffix.lower() not in IMAGE_FONT_EXTS and size >= text_limit:
            problems.append(f"{rel}（画像・フォント以外）が {text_limit} バイト以上（{size}）")
    if len(files) >= count_limit:
        problems.append(f"ファイルが {count_limit} 個以上（{len(files)}）")
    return problems


def junk_problems(root: Path) -> list[str]:
    problems = []
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root).as_posix()
        if p.is_symlink():
            problems.append(f"{rel} はシンボリックリンク")
        elif p.name in JUNK_NAMES:
            problems.append(f"{rel} は不要なファイル")
    return problems


def filename_problems(root: Path) -> list[str]:
    problems = []
    folders = [root] + [p for p in root.rglob("*") if p.is_dir() and not p.is_symlink()]
    for folder in folders:
        seen: dict[str, str] = {}
        for p in sorted(folder.iterdir()):
            name = p.name
            rel = p.relative_to(root).as_posix()
            if re.search(r'[<>:"|?*\\\x00-\x1f]', name):
                problems.append(f"{rel} に使えない文字がある")
            if name.endswith(".") or name.endswith(" "):
                problems.append(f"{rel} の末尾がドットか空白")
            if name.split(".")[0].lower() in WINDOWS_RESERVED:
                problems.append(f"{rel} は Windows の予約名")
            if name.lower() in seen:
                problems.append(f"{rel} は {seen[name.lower()]} と大文字小文字だけ違う")
            seen[name.lower()] = name
    return problems


def license_problems(plugin_dir: Path) -> list[str]:
    if (plugin_dir / "LICENSE").is_file():
        return []
    try:
        data = json.loads((plugin_dir / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    return [] if _nonempty_str(data.get("license")) else ["LICENSE も plugin.json の license も無い"]


def gitattributes_problems(text: str) -> list[str]:
    problems = []
    for n, line in enumerate(text.splitlines(), 1):
        code = line.split("#", 1)[0]
        if re.search(r"(?:^|\s)[-!]?(export-ignore|export-subst|filter)(?:=|\s|$)", code):
            problems.append(f"{n} 行目に export-ignore・export-subst・filter がある")
    return problems


def hook_problems(data: object) -> list[str]:
    if not isinstance(data, dict) or not isinstance(data.get("hooks"), dict):
        return ["最上位に hooks（オブジェクト）が無い"]
    problems = []
    for event, groups in data["hooks"].items():
        if event not in HOOK_EVENTS:
            problems.append(f"知らないイベント名 {event}")
        for group in groups if isinstance(groups, list) else []:
            for h in group.get("hooks", []):
                typ = h.get("type")
                if typ not in HOOK_TYPES:
                    problems.append(f"{event}: 知らない型 {typ}")
                    continue
                if typ != "command":
                    continue
                for key in h:
                    if key not in COMMAND_HOOK_KEYS:
                        problems.append(f"{event}: command の型に知らない項目 {key}")
                command = h.get("command", "")
                args = h.get("args", [])
                if not isinstance(command, str) or not isinstance(args, list) or not all(isinstance(a, str) for a in args):
                    problems.append(f"{event}: command か args の型が違う")
                    continue
                for s in [command, *args]:
                    plain = s.replace("${CLAUDE_PLUGIN_ROOT}", "")
                    if "$" in plain:
                        problems.append(f"{event}: {s!r} に ${{CLAUDE_PLUGIN_ROOT}} 以外の変数かコマンド置換がある")
                    if "`" in s:
                        problems.append(f"{event}: {s!r} にバッククォートがある")
                    if re.search(r"[*?\[\]]", s):
                        problems.append(f"{event}: {s!r} にワイルドカードがある")
                    if re.search(r"[;&|<>\n]", s):
                        problems.append(f"{event}: {s!r} にシェルの制御の文字がある")
                tokens = command.split() + args
                program = Path(tokens[0]).name.lower().removesuffix(".exe") if tokens else ""
                if program in INLINE_PROGRAMS and any(t in INLINE_FLAGS for t in tokens[1:]):
                    problems.append(f"{event}: {program} でその場のプログラムを起こしている")
    return problems


def description_problems(text: str) -> list[str]:
    """前書きの description だけを見る（ほかの欄は見ない）。"""
    m = re.match(r"^---\n(.*?)\n---(?:\n|$)", text, re.S)
    if not m:
        return ["前書きが --- で始まって閉じていない"]
    lines = m.group(1).splitlines()
    idx = [i for i, ln in enumerate(lines) if re.match(r"description\s*:", ln)]
    if len(idx) != 1:
        return [f"description が {len(idx)} 回ある（1回だけ）"]
    value = lines[idx[0]].split(":", 1)[1].strip()
    if value[:1] in ("|", ">"):
        block = []
        for ln in lines[idx[0] + 1 :]:
            if ln[:1] in (" ", "\t") or not ln.strip():
                block.append(ln)
            else:
                break
        return [] if any(b.strip() for b in block) else ["description の塊が空"]
    if not value:
        return ["description が空"]
    if value[0] in ('"', "'"):
        return [] if len(value) >= 2 and value[-1] == value[0] else ["description の引用符が閉じていない"]
    problems = []
    if ": " in value:
        problems.append("description に「: 」がある（引用符で囲む）")
    if " #" in value:
        problems.append("description に「 #」がある（引用符で囲む）")
    if value[0] in "[{&*!%@`#":
        problems.append(f"description が {value[0]} で始まる（引用符で囲む）")
    return problems


def section_between(md: str, start: str, end_pattern: str) -> str:
    """見出し行（start で始まる）から、end_pattern に当たる行の手前まで。無ければ空。"""
    lines = md.splitlines()
    at = next((i for i, ln in enumerate(lines) if ln.startswith(start)), None)
    if at is None:
        return ""
    out = [lines[at]]
    for ln in lines[at + 1 :]:
        if re.match(end_pattern, ln):
            break
        out.append(ln)
    return "\n".join(out)


def guide_section(md: str) -> str:
    return section_between(md, "## ディレクトリへの申請", r"^## ")


def gen_subcommand_names() -> set[str]:
    """pipe-in-gen の本物のサブコマンド名（引数の構文解析器から取る）。"""
    from pipe_in_generator import cli as gen_cli

    class Stop(Exception):
        def __init__(self, parser: argparse.ArgumentParser):
            super().__init__("stop")
            self.parser = parser

    def grab(self, *args, **kwargs):
        raise Stop(self)

    original = argparse.ArgumentParser.parse_args
    argparse.ArgumentParser.parse_args = grab
    try:
        gen_cli._parse_args([])
    except Stop as stop:
        parser = stop.parser
    finally:
        argparse.ArgumentParser.parse_args = original
    sub = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    return set(sub.choices)


def live_subcommand_names() -> set[str]:
    from pipe_in.engine import live_cmd

    sub = next(a for a in live_cmd._parser()._actions if isinstance(a, argparse._SubParsersAction))
    return set(sub.choices)


# ---- 補助 -------------------------------------------------------------------------------------------


def _need(path: Path) -> str:
    assert path.is_file(), f"{path.relative_to(ROOT).as_posix()} がまだ無い"
    return path.read_text(encoding="utf-8")


def _fake_png(path: Path, width: int, height: int, total: int = 100, signature: bytes = PNG_SIGNATURE) -> Path:
    import struct

    head = signature + struct.pack(">I", 13) + b"IHDR" + struct.pack(">II", width, height) + b"\x08\x06\x00\x00\x00"
    path.write_bytes(head + b"\x00" * max(0, total - len(head)))
    return path


def _fake_plugin(root: Path, skills: list[str], agents: list[str], extra: str = "") -> Path:
    for s in skills:
        d = root / "skills" / s
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(f"---\nname: {s}\ndescription: x\n---\n本文 `pipe-in-gen check` と `pipe-in live watch`。{extra}\n", encoding="utf-8")
    (root / "agents").mkdir(parents=True, exist_ok=True)
    for a in agents:
        (root / "agents" / f"{a}.md").write_text(f"---\nname: {a}\ndescription: x\n---\n本文\n", encoding="utf-8")
    return root


GEN_SUBS = {"list", "guard-hook", "chat", "judge-score", "new", "design", "check"}
LIVE_SUBS = {"page", "watch", "snapshot"}


def _en_section(skills: list[str], agents: list[str], runs: str = "`pipe-in-gen guard-hook`, `pipe-in-gen check`, `pipe-in live watch`.", sends: str = "", table_extra: str = "") -> str:
    skill_rows = "\n".join(f"| `/pipe-in:{s}` | one |" for s in skills)
    agent_rows = "\n".join(f"| `{a}` | one |" for a in agents)
    return f"""
### Install

```
{INSTALL_ONE_LINE}
pip install -e .
```

### What's included

| Skill | Use |
| --- | --- |
{skill_rows}
{table_extra}

| Agent | Use |
| --- | --- |
{agent_rows}

### What it runs, sends, and fetches

{runs} {sends}

### Where it works

Only Claude Code.
"""


# ---- AC-01: 語数 --------------------------------------------------------------------------------------


def test_d0095_ac01_readme_word_counts():
    """D0095-AC-01: plugin/README.md の語数（コードの囲みを除く）が 40 以上で、英語の節だけでも 60 以上ある。"""
    md = _need(README)
    en, _ = split_languages(md)
    assert readme_words(md) >= 40
    assert readme_words(en) >= 60, "英語の節が 60 語に足りない"


def test_d0095_ac01_word_counter(tmp_path):
    """D0095-AC-01: 語数の数え方は空白区切りで、コードの囲みの中は数えず、英語の節だけも数えられる。"""
    md = "# T\none two three\n```\nskipped words here ok\n```\nfour\n## English\nalpha beta\n## 日本語\ngamma delta epsilon\n"
    assert readme_words(md) == 15  # 見出しの語も数える（囲みの中の4語は数えない）
    assert readme_words("a b\n```\nx y z\n```\nc\n") == 3
    en, ja = split_languages(md)
    assert readme_words(en) == 2 and readme_words(ja) == 3


# ---- AC-02: 見出し ------------------------------------------------------------------------------------


def test_d0095_ac02_readme_headings_per_language():
    """D0095-AC-02: 英語の節と日本語の節があり、それぞれに「入れ方」「入るもの」「動かすもの・送るもの・取ってくるもの」「使える場所」の見出しがある。"""
    en, ja = split_languages(_need(README))
    assert en and ja, "## English か ## 日本語 の節が無い"
    assert heading_problems(en, EN_HEADINGS, "英語") == []
    assert heading_problems(ja, JA_HEADINGS, "日本語") == []


def test_d0095_ac02_missing_heading_found():
    """D0095-AC-02: 見出しが1つ欠けた偽の節で、検査の関数が欠けた見出しを言う。"""
    section = "### Install\nx\n### What's included\nx\n### Where it works\nx\n"
    problems = heading_problems(section, EN_HEADINGS, "英語")
    assert len(problems) == 1 and "What it runs" in problems[0]
    assert heading_problems(_en_section(["a"], ["b"]), EN_HEADINGS, "英語") == []


# ---- AC-03: 入れ方の行 --------------------------------------------------------------------------------


def test_d0095_ac03_readme_install_lines():
    """D0095-AC-03: plugin/README.md の英語の節にも日本語の節にも、1行の入れ方と pip install -e . の行がある。"""
    en, ja = split_languages(_need(README))
    assert readme_install_lines(en) == [] and readme_install_lines(ja) == []


def test_d0095_ac03_missing_install_line_found():
    """D0095-AC-03: 入れ方の行が欠けた偽の節で、検査の関数が違反を言う。"""
    assert len(readme_install_lines("nothing")) == 2
    assert readme_install_lines(f"{INSTALL_ONE_LINE}\n") == ["「pip install -e .」の行が無い"]
    assert readme_install_lines(f"{INSTALL_ONE_LINE}\npip install -e .\n") == []


# ---- AC-04: スキル・エージェントの名前 ----------------------------------------------------------------


def test_d0095_ac04_readme_lists_real_skills_and_agents():
    """D0095-AC-04: 実物のスキル5つ・エージェント4つの名前が README の英語の節と日本語の節の両方に出て、README に実物に無い名前が無い。"""
    skills, agents = plugin_names(PLUGIN)
    assert len(skills) == 5 and len(agents) == 4
    en, ja = split_languages(_need(README))
    doc = plugin_doc_text(PLUGIN)
    gens, lives = gen_subcommand_names(), live_subcommand_names()
    for label, section in (("英語", en), ("日本語", ja)):
        names_only = [p for p in readme_drift(section, skills, agents, gens, lives, doc) if "が README に無い" in p or "実物" in p]
        assert names_only == [], label


def test_d0095_ac04_drift_found(tmp_path):
    """D0095-AC-04: 一時のフォルダの偽のプラグインで、README に無い名前・実物に無い名前を出すと違反になる。"""
    plugin = _fake_plugin(tmp_path / "p", ["alpha", "beta"], ["gamma"])
    skills, agents = plugin_names(plugin)
    assert (skills, agents) == (["alpha", "beta"], ["gamma"])
    doc = plugin_doc_text(plugin)
    good = _en_section(skills, agents)
    assert readme_drift(good, skills, agents, GEN_SUBS, LIVE_SUBS, doc) == []
    missing = _en_section(["alpha"], agents)
    assert any("beta" in p and "README に無い" in p for p in readme_drift(missing, skills, agents, GEN_SUBS, LIVE_SUBS, doc))
    ghost = _en_section(skills, agents, table_extra="| `/pipe-in:ghost` | none |")
    problems = readme_drift(ghost, skills, agents, GEN_SUBS, LIVE_SUBS, doc)
    assert any("ghost" in p and "実物" in p for p in problems)
    ghost_agent = _en_section(skills, agents + ["phantom"])
    assert any("phantom" in p and "実物" in p for p in readme_drift(ghost_agent, skills, agents, GEN_SUBS, LIVE_SUBS, doc))


# ---- AC-05: 動かすもの --------------------------------------------------------------------------------


def test_d0095_ac05_readme_lists_commands_it_runs():
    """D0095-AC-05: README の「動かすもの」に、pipe-in-gen guard-hook・pipe-in live watch と、スキル・エージェントの文に出る pipe-in-gen のサブコマンド・pipe-in live の形がすべてあり、書かれた pipe-in-gen のサブコマンドは本物である（英語・日本語とも）。"""
    skills, agents = plugin_names(PLUGIN)
    en, ja = split_languages(_need(README))
    doc = plugin_doc_text(PLUGIN)
    gens, lives = gen_subcommand_names(), live_subcommand_names()
    assert {"guard-hook", "chat", "judge-score", "check"} <= gens and "watch" in lives
    for label, section in (("英語", en), ("日本語", ja)):
        problems = [p for p in readme_drift(section, skills, agents, gens, lives, doc) if "動かすもの" in p or "サブコマンド" in p]
        assert problems == [], label


def test_d0095_ac05_unknown_subcommand_found(tmp_path):
    """D0095-AC-05: 「動かすもの」の欠け・本物でない pipe-in-gen のサブコマンドを、偽の README で見つける。"""
    plugin = _fake_plugin(tmp_path / "p", ["alpha"], ["gamma"])
    doc = plugin_doc_text(plugin)
    skills, agents = plugin_names(plugin)
    no_watch = _en_section(skills, agents, runs="`pipe-in-gen guard-hook`, `pipe-in-gen check`.")
    assert any("pipe-in live watch" in p for p in readme_drift(no_watch, skills, agents, GEN_SUBS, LIVE_SUBS, doc))
    no_check = _en_section(skills, agents, runs="`pipe-in-gen guard-hook`, `pipe-in live watch`.")
    assert any("pipe-in-gen check" in p for p in readme_drift(no_check, skills, agents, GEN_SUBS, LIVE_SUBS, doc))
    bogus = _en_section(skills, agents, runs="`pipe-in-gen guard-hook`, `pipe-in-gen check`, `pipe-in live watch`, `pipe-in-gen frobnicate`.")
    assert any("frobnicate" in p and "サブコマンド" in p for p in readme_drift(bogus, skills, agents, GEN_SUBS, LIVE_SUBS, doc))


def test_d0095_ac05_network_words_found(tmp_path):
    """D0095-AC-05: スキルの文に WebFetch・ArtifactData・外部の URL があるのに「送るもの・取ってくるもの」に無いと、違反になる。"""
    plugin = _fake_plugin(tmp_path / "p", ["alpha"], ["gamma"], extra="WebFetch と ArtifactData と https://example.org/x を使う")
    doc = plugin_doc_text(plugin)
    skills, agents = plugin_names(plugin)
    bare = _en_section(skills, agents)
    problems = readme_drift(bare, skills, agents, GEN_SUBS, LIVE_SUBS, doc)
    for word in ("WebFetch", "ArtifactData", "https://"):
        assert any(word in p and "送るもの" in p for p in problems), word
    written = _en_section(skills, agents, sends="It uses WebFetch, writes ArtifactData, and reads https://example.org/x.")
    assert readme_drift(written, skills, agents, GEN_SUBS, LIVE_SUBS, doc) == []
    ours = _fake_plugin(tmp_path / "q", ["alpha"], ["gamma"], extra="https://github.com/nigoh/pipe-in/blob/main/x.md")
    assert readme_drift(bare, skills, agents, GEN_SUBS, LIVE_SUBS, plugin_doc_text(ours)) == []


# ---- AC-06: 根の README ------------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["README.md", "README.en.md"])
def test_d0095_ac06_readmes_have_install_line(name):
    """D0095-AC-06: README.md と README.en.md の両方に、プラグインの1行の入れ方がある。"""
    assert INSTALL_ONE_LINE in (ROOT / name).read_text(encoding="utf-8")


# ---- AC-07: アイコン ---------------------------------------------------------------------------------


def test_d0095_ac07_icon_png():
    """D0095-AC-07: plugin/.claude-plugin/icon.png が PNG で、1024x1024 の正方形で、2,000,000 バイト未満。"""
    assert ICON.is_file(), "plugin/.claude-plugin/icon.png がまだ無い"
    assert png_problems(ICON) == []
    assert png_size(ICON) == (1024, 1024)


def test_d0095_ac07_png_problems(tmp_path):
    """D0095-AC-07: 署名違い・縦横違い・小さすぎ・大きすぎ・2 MB 以上の偽の PNG を見つけ、良い PNG は通す。"""
    assert png_problems(_fake_png(tmp_path / "ok.png", 1024, 1024)) == []
    assert png_problems(_fake_png(tmp_path / "ok2.png", 512, 512)) == []
    assert png_problems(_fake_png(tmp_path / "ok3.png", 2048, 2048)) == []
    assert png_problems(_fake_png(tmp_path / "sig.png", 1024, 1024, signature=b"GIF89a\x00\x00"))
    assert png_problems(_fake_png(tmp_path / "rect.png", 1024, 512))
    assert png_problems(_fake_png(tmp_path / "small.png", 256, 256))
    assert png_problems(_fake_png(tmp_path / "large.png", 4096, 4096))
    assert png_problems(_fake_png(tmp_path / "heavy.png", 1024, 1024, total=2_000_000))
    assert png_problems(_fake_png(tmp_path / "light.png", 1024, 1024, total=1_999_999)) == []
    assert png_problems(tmp_path / "none.png")


def test_d0095_ac07_manifest_icon_points_to_real_png():
    """D0095-AC-07: plugin.json の icon が "./.claude-plugin/icon.png" で、./ 始まり・.. なしで、プラグインの中の実在する PNG（今の形を満たす）を指す。"""
    data = json.loads(PLUGIN_JSON.read_text(encoding="utf-8"))
    assert data.get("icon") == "./.claude-plugin/icon.png", "plugin.json に icon がまだ無い"
    assert icon_problems(data, PLUGIN) == []


def test_d0095_ac07_icon_problems(tmp_path):
    """D0095-AC-07: icon の欠け・./ 始まりでない・..・外を指す・PNG でない・実在しない・形の違う PNG を偽の入力で見つけ、良い形は通す。"""
    plugin = tmp_path / "p"
    (plugin / ".claude-plugin").mkdir(parents=True)
    _fake_png(plugin / ".claude-plugin/icon.png", 1024, 1024)
    _fake_png(plugin / ".claude-plugin/rect.png", 1024, 512)
    _fake_png(tmp_path / "outside.png", 1024, 1024)
    (plugin / "note.txt").write_text("x", encoding="utf-8")
    assert icon_problems({"icon": "./.claude-plugin/icon.png"}, plugin) == []
    for icon in (
        None, "", "./.claude-plugin/missing.png", ".claude-plugin/icon.png", "/abs/icon.png", "./../outside.png",
        "./.claude-plugin/../../outside.png", "./note.txt", "./.claude-plugin/rect.png", 3,
    ):
        data = {} if icon is None else {"icon": icon}
        assert icon_problems(data, plugin), icon


# ---- AC-08: plugin.json -------------------------------------------------------------------------------


def test_d0095_ac08_plugin_manifest():
    """D0095-AC-08: plugin.json に displayName・homepage・repository・keywords があり、author.url が決めた URL で、manifest_problems が空。"""
    data = json.loads(PLUGIN_JSON.read_text(encoding="utf-8"))
    assert manifest_problems(data) == []
    assert data["author"]["url"] == AUTHOR_URL
    assert data["displayName"] == "pipe-in"
    assert data["homepage"] == data["repository"] == "https://github.com/nigoh/pipe-in"


def test_d0095_ac08_manifest_listing_urls():
    """D0095-AC-08: plugin.json に documentationUrl と supportUrl が決めた URL で（https://）あり、privacyPolicyUrl・termsOfServiceUrl は無い。"""
    data = json.loads(PLUGIN_JSON.read_text(encoding="utf-8"))
    assert data.get("documentationUrl") == DOCUMENTATION_URL, "documentationUrl がまだ無い"
    assert data.get("supportUrl") == SUPPORT_URL, "supportUrl がまだ無い"
    assert listing_url_problems(data) == []


def test_d0095_ac08_listing_url_problems():
    """D0095-AC-08: URL の欠け・https:// でない・空・型の違い・書かない欄がある偽の plugin.json を見つけ、良い形は通す。"""
    good = {"documentationUrl": DOCUMENTATION_URL, "supportUrl": SUPPORT_URL}
    assert listing_url_problems(good) == []
    for key in ("documentationUrl", "supportUrl"):
        assert listing_url_problems({k: v for k, v in good.items() if k != key}), key
        assert listing_url_problems({**good, key: "http://example.org"}), key
        assert listing_url_problems({**good, key: ""}), key
        assert listing_url_problems({**good, key: 3}), key
    assert listing_url_problems({**good, "privacyPolicyUrl": "https://example.org/p"})
    assert listing_url_problems({**good, "termsOfServiceUrl": "https://example.org/t"})


GOOD_MANIFEST = {
    "name": "pipe-in", "version": "1.0.0", "description": "d", "author": {"name": "a"}, "displayName": "pipe-in",
    "homepage": "https://example.org", "repository": "https://example.org/r", "keywords": ["k"],
}


def test_d0095_ac08_manifest_problems():
    """D0095-AC-08: 名前の形・予約語・欠けた項目・型の違いを、偽の plugin.json で見つけ、良い形は通す。"""
    assert manifest_problems(GOOD_MANIFEST) == []
    bad = [
        {**GOOD_MANIFEST, "name": "Pipe_In"},
        {**GOOD_MANIFEST, "name": "a" * 65},
        {**GOOD_MANIFEST, "name": "claude"},
        {**GOOD_MANIFEST, "description": ""},
        {**GOOD_MANIFEST, "version": ""},
        {**GOOD_MANIFEST, "author": {}},
        {**GOOD_MANIFEST, "homepage": "http://example.org"},
        {**GOOD_MANIFEST, "repository": 3},
        {**GOOD_MANIFEST, "keywords": []},
        {**GOOD_MANIFEST, "keywords": ["ok", ""]},
        {k: v for k, v in GOOD_MANIFEST.items() if k != "displayName"},
    ]
    for m in bad:
        assert manifest_problems(m), m


# ---- AC-09: marketplace.json -------------------------------------------------------------------------


def test_d0095_ac09_marketplace_entry():
    """D0095-AC-09: marketplace.json の項目に displayName・homepage・repository・keywords・tags・category があり、category は development、owner.url が決めた URL、source は ./plugin のまま。"""
    data = json.loads(MARKET_JSON.read_text(encoding="utf-8"))
    assert market_problems(data) == []
    assert data["owner"]["url"] == AUTHOR_URL
    entry = data["plugins"][0]
    assert entry["source"] == "./plugin" and entry["category"] == "development"


GOOD_ENTRY = {
    "name": "pipe-in", "source": "./plugin", "description": "d", "displayName": "pipe-in", "homepage": "https://example.org",
    "repository": "https://example.org/r", "keywords": ["k"], "tags": ["t"], "category": "development",
}


def test_d0095_ac09_market_problems():
    """D0095-AC-09: 項目の欠け・型の違い・URL の形の違いを偽の marketplace.json で見つけ、良い形は通す。"""
    good = {"name": "m", "owner": {"name": "o", "url": "https://example.org"}, "plugins": [GOOD_ENTRY]}
    assert market_problems(good) == []
    for key in ("displayName", "homepage", "repository", "keywords", "tags", "category"):
        broken = {**good, "plugins": [{k: v for k, v in GOOD_ENTRY.items() if k != key}]}
        assert market_problems(broken), key
    assert market_problems({**good, "plugins": [{**GOOD_ENTRY, "tags": "x"}]})
    assert market_problems({**good, "plugins": [{**GOOD_ENTRY, "homepage": "ftp://x"}]})
    assert market_problems({**good, "plugins": [{**GOOD_ENTRY, "category": 1}]})
    assert market_problems({**good, "plugins": [{**GOOD_ENTRY, "source": "plugin"}]})
    assert market_problems({**good, "plugins": []})
    assert market_problems({**good, "owner": {"name": "o", "url": "x"}})


def test_d0095_ac09_real_entry_has_no_plugin_only_fields():
    """D0095-AC-09: 実物の marketplace.json の項目に icon・documentationUrl・supportUrl・privacyPolicyUrl・termsOfServiceUrl が無い。（今の作りのままで通る。守る）"""
    market = json.loads(MARKET_JSON.read_text(encoding="utf-8"))
    assert market_plugin_only_problems(market) == []


def test_d0095_ac09_plugin_only_fields_found():
    """D0095-AC-09: 項目に plugin.json だけの欄がある偽の marketplace.json を、欄ごとに見つける。"""
    good = {"plugins": [GOOD_ENTRY]}
    assert market_plugin_only_problems(good) == []
    for key in PLUGIN_ONLY_FIELDS:
        found = market_plugin_only_problems({"plugins": [{**GOOD_ENTRY, key: "x"}]})
        assert len(found) == 1 and key in found[0], key


def test_d0095_ac09_real_entry_matches_manifest_listing():
    """D0095-AC-09: 実物で、項目と plugin.json の両方にある displayName・homepage・repository・keywords・license・author が同じ値。（今の作りのままで通る。守る）"""
    market = json.loads(MARKET_JSON.read_text(encoding="utf-8"))
    manifest = json.loads(PLUGIN_JSON.read_text(encoding="utf-8"))
    assert listing_mismatch_problems(market, manifest) == []


def test_d0095_ac09_listing_mismatch_found():
    """D0095-AC-09: 両方にある欄の値が違うと見つけ、description の違い・片方にしか無い欄は見逃す（誤検出しない）。"""
    manifest = {
        "displayName": "pipe-in", "homepage": "https://example.org", "repository": "https://example.org/r",
        "keywords": ["k"], "license": "MIT", "author": {"name": "a"}, "description": "long long long",
    }
    entry = {"name": "pipe-in", **{k: v for k, v in manifest.items() if k != "description"}, "description": "short"}
    assert listing_mismatch_problems({"plugins": [entry]}, manifest) == []
    only_one = {k: v for k, v in entry.items() if k not in ("license", "author")}
    assert listing_mismatch_problems({"plugins": [only_one]}, manifest) == []
    assert listing_mismatch_problems({"plugins": [entry]}, {k: v for k, v in manifest.items() if k != "license"}) == []
    changed = {
        "displayName": "other", "homepage": "https://example.org/h", "repository": "https://example.org/x",
        "keywords": ["k", "z"], "license": "Apache-2.0", "author": {"name": "b"},
    }
    for key, value in changed.items():
        found = listing_mismatch_problems({"plugins": [{**entry, key: value}]}, manifest)
        assert len(found) == 1 and key in found[0], key


# ---- AC-10: 版 ---------------------------------------------------------------------------------------


def test_d0095_ac10_version_is_bumped():
    """D0095-AC-10: plugin.json の版が 0.5.2 より上で、marketplace.json の項目に version を書かない。
    D0096 で pipe-judge の断り方と返し方・pipe-builder の名前の決まりを直したので、0.6.0 から 0.6.1 に上げた。
    D0097-AC-17: スキルとエージェントの文を縮めたので 0.6.2（D0096 の 0.6.1 の決め打ちを置き換えた）。"""
    version = json.loads(PLUGIN_JSON.read_text(encoding="utf-8"))["version"]
    parts = tuple(int(x) for x in version.split("."))
    assert parts > (0, 5, 2), f"版が {version}（0.5.2 より上にする）"
    assert version == "0.6.2"
    entry = json.loads(MARKET_JSON.read_text(encoding="utf-8"))["plugins"][0]
    assert "version" not in entry


# ---- AC-11: 大きさと数 -------------------------------------------------------------------------------


def test_d0095_ac11_folder_sizes():
    """D0095-AC-11: 今の plugin/ は、画像・フォント以外の各ファイルが 256 KiB 未満、各ファイルが 5 MiB 未満、ファイル数が 512 未満。（今の作りのままで通る。守る）"""
    assert size_problems(PLUGIN) == []


def test_d0095_ac11_limits_found(tmp_path):
    """D0095-AC-11: 小さな上限で、各ファイル・画像以外のファイル・ファイル数の3つの違反を見つける（境界は「未満」）。"""
    (tmp_path / "text.md").write_bytes(b"x" * 100)
    (tmp_path / "image.png").write_bytes(b"x" * 100)
    assert size_problems(tmp_path, text_limit=101, file_limit=1000, count_limit=3) == []
    assert any("text.md" in p for p in size_problems(tmp_path, text_limit=100, file_limit=1000, count_limit=3))
    assert not any("image.png" in p for p in size_problems(tmp_path, text_limit=100, file_limit=1000, count_limit=3))
    assert any("image.png" in p for p in size_problems(tmp_path, text_limit=1000, file_limit=100, count_limit=3))
    assert any("個以上" in p for p in size_problems(tmp_path, text_limit=1000, file_limit=1000, count_limit=2))
    skipped = tmp_path / "evals" / "results"
    skipped.mkdir(parents=True)
    (skipped / "big.json").write_bytes(b"x" * 5000)
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "c.pyc").write_bytes(b"x" * 5000)
    assert size_problems(tmp_path, text_limit=1000, file_limit=1000, count_limit=3) == []


def test_d0095_ac11_real_folder_fails_with_tiny_limit():
    """D0095-AC-11: 実物の plugin/ に小さな上限を渡すと3つとも落ちる（NFR-01 の測り方）。（今の作りのままで通る）"""
    problems = size_problems(PLUGIN, text_limit=10, file_limit=10, count_limit=5)
    assert any("個以上" in p for p in problems) and any("バイト以上" in p for p in problems)


# ---- AC-12: 不要なファイルと名前 ---------------------------------------------------------------------


def test_d0095_ac12_no_junk_and_safe_names():
    """D0095-AC-12: 今の plugin/ に、シンボリックリンク・不要なファイルが無く、ファイル名に使えない文字・予約名・大文字小文字だけの違いが無い。（今の作りのままで通る。守る）"""
    assert junk_problems(PLUGIN) == []
    assert filename_problems(PLUGIN) == []


def test_d0095_ac12_junk_found(tmp_path):
    """D0095-AC-12: 一時のフォルダに置いたシンボリックリンク・.DS_Store・Thumbs.db・desktop.ini・__MACOSX を見つける。"""
    for name in (".DS_Store", "Thumbs.db", "desktop.ini"):
        (tmp_path / name).write_text("x", encoding="utf-8")
    (tmp_path / "__MACOSX").mkdir()
    (tmp_path / "real.txt").write_text("x", encoding="utf-8")
    try:
        os.symlink(tmp_path / "real.txt", tmp_path / "link.txt")
    except (OSError, NotImplementedError):
        pytest.skip("シンボリックリンクを作れない環境")
    found = " ".join(junk_problems(tmp_path))
    for name in (".DS_Store", "Thumbs.db", "desktop.ini", "__MACOSX", "link.txt"):
        assert name in found, name
    assert "real.txt" not in found


def test_d0095_ac12_bad_names_found(tmp_path):
    """D0095-AC-12: コロン・末尾のドット・予約名・大文字小文字だけ違う2つの名前を見つけ、普通の名前は通す。"""
    (tmp_path / "ok-name.md").write_text("x", encoding="utf-8")
    try:
        (tmp_path / "a:b.md").write_text("x", encoding="utf-8")
        (tmp_path / "dot.").write_text("x", encoding="utf-8")
        (tmp_path / "CON.txt").write_text("x", encoding="utf-8")
        (tmp_path / "Lpt1.md").write_text("x", encoding="utf-8")
        (tmp_path / "Case.md").write_text("x", encoding="utf-8")
        (tmp_path / "case.md").write_text("x", encoding="utf-8")
    except OSError:
        pytest.skip("この名前を作れない環境")
    if len(list(tmp_path.iterdir())) < 7:
        pytest.skip("大文字小文字を区別しない環境")
    found = " ".join(filename_problems(tmp_path))
    for name in ("a:b.md", "dot.", "CON.txt", "Lpt1.md", "大文字小文字"):
        assert name in found, name
    assert "ok-name.md" not in found


# ---- AC-13: LICENSE と .gitattributes ----------------------------------------------------------------


def test_d0095_ac13_license_present_and_same_as_root():
    """D0095-AC-13: plugin/LICENSE があり、中身が根の LICENSE と同じ。"""
    text = _need(PLUGIN / "LICENSE")
    assert text == (ROOT / "LICENSE").read_text(encoding="utf-8")
    assert license_problems(PLUGIN) == []


def test_d0095_ac13_license_problems(tmp_path):
    """D0095-AC-13: LICENSE も license も無いプラグインを見つけ、どちらかがあれば通す。"""
    (tmp_path / ".claude-plugin").mkdir()
    (tmp_path / ".claude-plugin/plugin.json").write_text('{"name": "x"}', encoding="utf-8")
    assert license_problems(tmp_path)
    (tmp_path / ".claude-plugin/plugin.json").write_text('{"name": "x", "license": "MIT"}', encoding="utf-8")
    assert license_problems(tmp_path) == []
    (tmp_path / ".claude-plugin/plugin.json").write_text('{"name": "x", "license": ""}', encoding="utf-8")
    assert license_problems(tmp_path)
    (tmp_path / "LICENSE").write_text("MIT", encoding="utf-8")
    assert license_problems(tmp_path) == []


def test_d0095_ac13_gitattributes_clean():
    """D0095-AC-13: 根の .gitattributes と（あれば）plugin/.gitattributes に export-ignore・export-subst・filter の行が無い。（今の作りのままで通る。守る）"""
    for path in (ROOT / ".gitattributes", PLUGIN / ".gitattributes"):
        if path.is_file():
            assert gitattributes_problems(path.read_text(encoding="utf-8")) == [], path.name


def test_d0095_ac13_gitattributes_problems():
    """D0095-AC-13: 偽の行で export-ignore・export-subst・filter を見つけ、コメントの中と別の属性は見逃す（誤検出しない）。"""
    for line in ("docs export-ignore", "*.md export-subst", "*.bin filter=lfs diff=lfs", "* -filter"):
        assert gitattributes_problems(line + "\n"), line
    assert gitattributes_problems("# export-ignore は使わない\nREADME.md merge=union\n") == []
    assert gitattributes_problems("*.txt text eol=lf  # filter は書かない\n") == []


# ---- AC-14: フック ----------------------------------------------------------------------------------


def _hooks(command: str, args: list[str] | None = None, event: str = "PreToolUse", typ: str = "command") -> dict:
    h: dict = {"type": typ, "command": command}
    if args is not None:
        h["args"] = args
    return {"hooks": {event: [{"matcher": "*", "hooks": [h]}]}}


def test_d0095_ac14_hooks_shape():
    """D0095-AC-14: 今の hooks.json が正しい JSON で、フックの検査に通る（pipe-in-gen guard-hook の今の形を許す）。（今の作りのままで通る。守る）"""
    data = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))
    assert hook_problems(data) == []
    handler = data["hooks"]["PreToolUse"][0]["hooks"][0]
    assert handler["command"] == "pipe-in-gen" and handler["args"] == ["guard-hook"]


def test_d0095_ac14_hook_allowed_forms():
    """D0095-AC-14: 公式の33のイベント名・5つの型・${CLAUDE_PLUGIN_ROOT} の下のコマンドは通る。"""
    assert hook_problems(_hooks("pipe-in-gen", ["guard-hook"])) == []
    assert hook_problems(_hooks("${CLAUDE_PLUGIN_ROOT}/bin/guard", ["--mode", "${CLAUDE_PLUGIN_ROOT}/x"])) == []
    assert hook_problems(_hooks("node", ["${CLAUDE_PLUGIN_ROOT}/hook.js"])) == []
    assert len(HOOK_EVENTS) == 33 and len(HOOK_TYPES) == 5
    for event in sorted(HOOK_EVENTS):
        assert hook_problems(_hooks("pipe-in-gen", ["guard-hook"], event=event)) == [], event
    for typ in sorted(HOOK_TYPES - {"command"}):
        assert hook_problems(_hooks("ignored", typ=typ)) == [], typ


@pytest.mark.parametrize(
    "case",
    [
        _hooks("$HOME/bin/guard"),
        _hooks("pipe-in-gen", ["$HOME"]),
        _hooks("pipe-in-gen", ["${HOME}/x"]),
        _hooks("pipe-in-gen", ["$(whoami)"]),
        _hooks("pipe-in-gen", ["`whoami`"]),
        _hooks("pipe-in-gen", ["*"]),
        _hooks("pipe-in-gen", ["a?b"]),
        _hooks("pipe-in-gen", ["[ab]"]),
        _hooks("pipe-in-gen", ["a;b"]),
        _hooks("pipe-in-gen", ["a&b"]),
        _hooks("pipe-in-gen", ["a|b"]),
        _hooks("pipe-in-gen", ["a>b"]),
        _hooks("pipe-in-gen", ["a<b"]),
        _hooks("pipe-in-gen", ["a\nb"]),
        _hooks("python3", ["-c", "print(1)"]),
        _hooks("python", ["-c", "print(1)"]),
        _hooks("node", ["-e", "1"]),
        _hooks("node", ["--eval", "1"]),
        _hooks("bash", ["-c", "ls"]),
        _hooks("sh", ["-c", "ls"]),
        _hooks("pwsh", ["-Command", "ls"]),
        _hooks("cmd", ["/c", "dir"]),
        _hooks("pipe-in-gen", ["guard-hook"], event="Bogus"),
        _hooks("pipe-in-gen", ["guard-hook"], typ="wasm"),
        {"hooks": [], "x": 1},
        {"nohooks": {}},
    ],
    ids=[
        "var-command", "var-home", "var-braces", "substitution", "backtick", "star", "question", "bracket", "semicolon", "ampersand",
        "pipe", "redirect-out", "redirect-in", "newline", "python3-c", "python-c", "node-e", "node-eval", "bash-c", "sh-c", "pwsh-command",
        "cmd-c", "unknown-event", "unknown-type", "hooks-not-object", "no-hooks",
    ],
)
def test_d0095_ac14_hook_problems(case):
    """D0095-AC-14: 別の変数・コマンド置換・バッククォート・ワイルドカード・シェルの制御の文字・その場のプログラム・知らないイベント名と型・形の違いを、偽の hooks.json で見つける。"""
    assert hook_problems(case)


# ---- AC-15: 前書きの description --------------------------------------------------------------------


def test_d0095_ac15_frontmatter_descriptions():
    """D0095-AC-15: 実物のスキル5つ・エージェント4つの前書きの description が、1つの文字列として読める。（今の作りのままで通る。守る）"""
    files = sorted(PLUGIN.glob("skills/*/SKILL.md")) + sorted(PLUGIN.glob("agents/*.md"))
    assert len(files) == 9
    for f in files:
        assert description_problems(f.read_text(encoding="utf-8")) == [], f.relative_to(ROOT).as_posix()


@pytest.mark.parametrize(
    "text",
    [
        "no frontmatter\n",
        "---\nname: a\ndescription: ok\n",
        "---\nname: a\n---\nbody\n",
        "---\ndescription: one\ndescription: two\n---\nbody\n",
        "---\ndescription: 注意: コロンと空白\n---\nbody\n",
        "---\ndescription: 注意 # コメントになる\n---\nbody\n",
        "---\ndescription: [配列になる]\n---\nbody\n",
        "---\ndescription: *anchor\n---\nbody\n",
        "---\ndescription:\n---\nbody\n",
        "---\ndescription: \"閉じていない\n---\nbody\n",
        "---\ndescription: >\nname: a\n---\nbody\n",
    ],
    ids=["no-frontmatter", "unclosed", "missing", "twice", "colon-space", "hash", "bracket", "star", "empty", "open-quote", "empty-block"],
)
def test_d0095_ac15_description_problems(text):
    """D0095-AC-15: 前書きの欠け・閉じていない・description の欠けや2回・素の文字の「: 」や「 #」や記号始まり・空を見つける。"""
    assert description_problems(text)


@pytest.mark.parametrize(
    "text",
    [
        "---\nname: a\ndescription: 普通の説明。コロンは全角：です\n---\nbody\n",
        "---\ndescription: \"注意: 引用符で囲めばよい\"\n---\nbody\n",
        "---\ndescription: '注意 # 引用符'\n---\nbody\n",
        "---\ndescription: >\n  折りたたむ塊: 中は自由\n  続き\n---\nbody\n",
        "---\ndescription: |\n  塊\n---\nbody\n",
    ],
    ids=["plain", "double-quoted", "single-quoted", "folded", "literal"],
)
def test_d0095_ac15_description_allowed_forms(text):
    """D0095-AC-15: 普通の文字・引用符つき・塊の description は通る（誤検出しない）。"""
    assert description_problems(text) == []


# ---- AC-16・AC-17: ガイドの申請の節 ----------------------------------------------------------------


PORTAL_ORDER = ["Submit new", "Plugin bundle", "Repository", "Plugin path", "Validate", "Data handling", "Compliance", "Review and submit"]


def test_d0095_ac16_guide_has_submission_section():
    """D0095-AC-16: docs/guide/plugin.md に「ディレクトリへの申請」の節が、プラグインの eval の節と更新の節の間にあり、ポータルの順番・答えの下書き4項目・版を上げる決まり・同期の方法の語を含む。"""
    md = GUIDE.read_text(encoding="utf-8")
    section = guide_section(md)
    assert section, "「## ディレクトリへの申請」の節がまだ無い"
    at = md.index("## ディレクトリへの申請")
    assert md.index("## プラグインの eval") < at < md.index("から更新するとき")
    order = subsection(section, "ポータルでの順番")
    assert order, "「### ポータルでの順番」が無い"
    pos = -1
    for word in PORTAL_ORDER:
        nxt = order.find(word, pos + 1)
        assert nxt > pos, f"ポータルの順番に {word} が順番どおりに出ない"
        pos = nxt
    draft = subsection(section, "データの扱いの問いへの答えの下書き")
    assert draft, "「### データの扱いの問いへの答えの下書き」が無い"
    assert len(re.findall(r"^\d+\. ", draft, re.M)) == 4
    versioning = subsection(section, "版を上げる決まり")
    assert versioning, "「### 版を上げる決まり」が無い"
    for word in ("plugin/.claude-plugin/plugin.json", "version", "marketplace.json"):
        assert word in versioning, word
    for word in ("webhook", "決まった間隔", "最初の保存", "連絡先", "同意"):
        assert word in section, word
    for heading in ("申請の前の確かめ", "アイコン", "事前チェックを pytest で見張る範囲"):
        assert subsection(section, heading), heading


def test_d0095_ac16_section_finder():
    """D0095-AC-16: 節の取り出しが、次の ## の手前までと、### の小節を正しく分ける。"""
    md = "## A\na\n## ディレクトリへの申請\nbody\n### 小1\nx\n### 小2\ny\n## 次\nz\n"
    section = guide_section(md)
    assert "body" in section and "z" not in section and "a\n" not in section.replace("## ディレクトリへの申請", "")
    assert subsection(section, "小1").strip() == "x" and subsection(section, "小2").strip() == "y"
    assert guide_section("## 別の節\n") == ""


def test_d0095_ac17_guide_has_manual_validate_steps():
    """D0095-AC-17: 申請の節に、claude plugin validate --strict の2つのコマンド（./plugin と .）の行が、コードの囲みの中にある。"""
    section = guide_section(GUIDE.read_text(encoding="utf-8"))
    assert section, "「## ディレクトリへの申請」の節がまだ無い"
    lines = [ln.strip() for ln in section.splitlines()]
    assert "claude plugin validate --strict ./plugin" in lines
    assert "claude plugin validate --strict ." in lines


def test_d0095_ac17_ci_does_not_run_validate():
    """D0095-AC-17: CI（.github/workflows/ci.yml）では claude plugin validate を流さない（手で流すと決めた）。（今の作りのままで通る。守る）"""
    assert "claude plugin validate" not in (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
