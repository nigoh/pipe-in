"""プラグイン自身の eval のケース（plugin/evals/）：claude plugin eval 用のファイルの形をファイルだけで確かめる（D0043）。

ケースを流す（claude plugin eval）のは実機で、利用料がかかる。ここでは流さず、ファイルを読むだけ。
frontmatter の読み手と検査関数（check_case・check_suite）は、このテストのファイルの中に置く（PyYAML は使わない）。
"""

from __future__ import annotations

import importlib.util
import json
import re
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugin"
EVALS = PLUGIN / "evals"

# ---- 公式の値（docs/pipeline/02_design.md の 0 章・7.1 章。https://code.claude.com/docs/en/plugin-evals） ----------

KNOWN_PROMPT_KEYS = {
    "schema_version", "name", "description", "tags", "plugins", "runs", "expected_outcome", "model",
    "max_turns", "timeout_seconds", "allowed_tools", "append_system_prompt", "env",
}
KNOWN_GRADER_TYPES = {"regex", "tool_used", "tool_order", "file_exists", "llm", "baseline"}
COMMON_GRADER_KEYS = {"type", "weight", "arm"}
KNOWN_ARM = {"with-only", "both"}
GRADER_KEYS = {
    "regex": {"pattern", "flags", "match", "target"},
    "tool_used": {"tool", "input_match", "min", "max"},
    "tool_order": {"before", "after"},
    "file_exists": {"path", "exists"},
    "llm": {"criteria", "focus"},
    "baseline": {"baseline_file", "criteria"},
}
REQUIRED_GRADER_KEYS = {
    "regex": {"pattern"}, "tool_used": {"tool"}, "file_exists": {"path"},
    "tool_order": {"before", "after"}, "baseline": {"baseline_file"}, "llm": set(),
}
KNOWN_REGEX_FLAGS = {"i"}
KNOWN_REGEX_MATCH = {"contains", "not_contains"}
KNOWN_TARGETS = {"last_message", "trace", "files", "mock_calls"}
CASE_ALLOWED_TOOLS = {"Read", "Glob", "Grep", "NotebookRead", "Skill", "AskUserQuestion", "Agent", "TodoWrite"}
NEEDS_ALLOW_TOOLS = {"Bash", "Write", "Edit", "WebFetch", "WebSearch"}
SCHEMA_VERSION = "1.1"
SKILLS = ("pipe-build", "pipe-eval", "pipe-judge")
COST_TAGS = {"cheap", "agent"}
NEEDS_TAGS = {"needs-bash", "needs-write", "needs-pipe-in-gen"}

CASES = {
    "pipe-build": ["build-shows-table-first", "build-passes-check", "build-refuses-judge-only"],
    "pipe-eval": ["eval-lists-and-waits", "eval-result-json", "eval-stops-without-state"],
    "pipe-judge": ["judge-calls-judge-score", "judge-must-violation-fails", "judge-rejects-bad-runs"],
}
CASE_NAMES = [name for names in CASES.values() for name in names]

# tests/test_plugin.py の FORBIDDEN_IN_SKILL と同じ（tests/ は import し合わないのでコピー）
FORBIDDEN_IN_SKILL = [
    (r"/home/", "手元のパス"), (r"/Users/", "手元のパス"), (r"[A-Za-z]:\\Users", "手元のパス"), (r"[A-Za-z]:/Users", "手元のパス"),
    (r"sk-[A-Za-z0-9_-]{8,}", "鍵"), (r"ANTHROPIC_API_KEY", "鍵の名前"), (r"ghp_[A-Za-z0-9]{10,}", "トークン"),
    (r"BEGIN [A-Z ]*PRIVATE KEY", "秘密鍵"), (r"[\w.+-]+@[\w-]+\.[\w.]+", "メールアドレス"),
]


# ---- 読み手（3.1 の範囲だけ。範囲外は ValueError。黙って読み飛ばさない） ------------------------------------


def parse_scalar(raw: str):
    raw = raw.strip()
    if raw == "":
        raise ValueError("値が空、または複数行の値（対応しない）")
    if raw[0] in "|>&*!%@`":
        raise ValueError(f"対応しない書き方: {raw[:12]}")
    if raw[0] == "{":
        # 1 行の「{名前: 値, 名前: 値}」だけ（regex の target: {source: file, path: ...} に使う）
        if raw[-1] != "}":
            raise ValueError(f"対応表が 1 行で閉じていない: {raw[:20]}")
        mapping: dict = {}
        for item in raw[1:-1].split(","):
            key, sep, value = item.strip().partition(": ")
            if not sep or not re.fullmatch(r"[A-Za-z_][\w-]*", key) or key in mapping:
                raise ValueError(f"対応表の項目が「名前: 値」ではない: {item.strip()[:20]}")
            mapping[key] = parse_scalar(value)
        return mapping
    if raw[0] == "'":
        if len(raw) < 2 or raw[-1] != "'":
            raise ValueError(f"引用符が閉じていない: {raw[:20]}")
        inner = raw[1:-1].replace("''", "\0")
        if "'" in inner:
            raise ValueError(f"引用符の中の ' は '' と書く: {raw[:20]}")
        return inner.replace("\0", "'")
    if raw[0] == '"':
        if len(raw) < 2 or raw[-1] != '"':
            raise ValueError(f"引用符が閉じていない: {raw[:20]}")
        inner = raw[1:-1]
        if "\\" in inner or '"' in inner:
            raise ValueError("ダブルクォートの中に \\ や \" は書かない（シングルクォートを使う）")
        return inner
    if raw[0] == "[":
        if raw[-1] != "]":
            raise ValueError(f"リストが 1 行で閉じていない: {raw[:20]}")
        inner = raw[1:-1].strip()
        return [parse_scalar(item) for item in inner.split(",")] if inner else []
    if raw == "true":
        return True
    if raw == "false":
        return False
    if re.fullmatch(r"-?\d+", raw):
        return int(raw)
    if re.fullmatch(r"-?\d+\.\d+", raw):
        return float(raw)
    if ": " in raw or " #" in raw or raw.endswith(":"):
        raise ValueError(f"引用符なしの値に : や # は書けない: {raw[:20]}")
    return raw


def _parse_lines(lines: list[str], allow_context: bool) -> dict:
    data: dict = {}
    current_context: dict | None = None
    for line in lines:
        if "\t" in line:
            raise ValueError("タブは使えない")
        if not line.strip():
            continue
        indented = line.startswith("  ") and not line.startswith("   ")
        if line.startswith(" "):
            if not (allow_context and indented and current_context is not None):
                raise ValueError(f"入れ子・複数行は使えない: {line[:30]}")
            key, sep, value = line.strip().partition(":")
            if not sep or not re.fullmatch(r"[A-Za-z_][\w-]*", key):
                raise ValueError(f"1 行 1 項目の「名前: 値」ではない: {line[:30]}")
            if key in current_context:
                raise ValueError(f"キーが重複: {key}")
            current_context[key] = parse_scalar(value)
            continue
        key, sep, value = line.partition(":")
        if not sep or not re.fullmatch(r"[A-Za-z_][\w-]*", key):
            raise ValueError(f"1 行 1 項目の「名前: 値」ではない: {line[:30]}")
        if key in data:
            raise ValueError(f"キーが重複: {key}")
        if allow_context and key == "context" and value.strip() == "":
            current_context = data[key] = {}
            continue
        current_context = None
        data[key] = parse_scalar(value)
    return data


def read_front(text: str) -> tuple[dict, str]:
    m = re.match(r"\A---\n(.*?)\n---[ \t]*(?:\n(.*))?\Z", text, re.S)
    if not m:
        raise ValueError("frontmatter（--- で囲んだ頭）がない")
    return _parse_lines(m.group(1).splitlines(), allow_context=False), m.group(2) or ""


def read_case_yaml(text: str) -> dict:
    return _parse_lines(text.splitlines(), allow_context=True)


# ---- 検査関数（エラーの文は "AC-xx:" で始める） ------------------------------------------------------


def starts_with_skill(body: str, skill: str) -> bool:
    """0.2 の (b)（文で頼む形）に替えるときは、ここだけ直す。"""
    return body.lstrip().startswith(f"/pipe-in:{skill}")


def js_python_safe(pattern: str) -> bool:
    """JavaScript と Python の re で同じ意味になる範囲か（インラインの記号・名前つきグループ・\\A \\Z を含まない）。"""
    if re.search(r"\(\?(?![:=!])", pattern):
        return False
    return not re.search(r"\\[AZ]", pattern)


def _regex_errors(label: str, pattern: object, flags: object = None) -> list[str]:
    errors: list[str] = []
    if not isinstance(pattern, str) or pattern == "":
        return [f"AC-04: {label}: pattern が文字ではない"]
    if not js_python_safe(pattern):
        errors.append(f"AC-04: {label}: JavaScript と Python で意味が変わる書き方（インラインの記号など）: {pattern[:40]}")
    re_flags = re.I if flags == "i" else 0
    try:
        re.compile(pattern, re_flags)
    except re.error as e:
        errors.append(f"AC-04: {label}: 正規表現として読めない: {e}")
    return errors


def _known_target(target: object) -> bool:
    """既知の名前か、{source: file, path: ワークスペースの中の相対パス}。files はパスの一覧で、中身ではない。"""
    if isinstance(target, dict):
        path = target.get("path")
        return (
            set(target) == {"source", "path"} and target["source"] == "file" and isinstance(path, str)
            and path != "" and not path.startswith(("/", "\\")) and ".." not in Path(path).parts
        )
    return target in KNOWN_TARGETS


def check_grader(path: Path, tags: list, allowed: list) -> list[str]:
    errors: list[str] = []
    label = f"{path.parent.parent.name}/graders/{path.name}"
    try:
        fm, body = read_front(path.read_text(encoding="utf-8"))
    except ValueError as e:
        return [f"AC-11: {label}: {e}"]
    kind = fm.get("type")
    if kind not in KNOWN_GRADER_TYPES:
        return [f"AC-03: {label}: 知らない type: {kind!r}"]
    unknown = set(fm) - COMMON_GRADER_KEYS - GRADER_KEYS[kind]
    if unknown:
        errors.append(f"AC-03: {label}: 知らないキー: {sorted(unknown)}")
    missing = REQUIRED_GRADER_KEYS[kind] - set(fm)
    if missing:
        errors.append(f"AC-03: {label}: 必須のキーがない: {sorted(missing)}")
    if kind == "llm" and "criteria" not in fm and not body.strip():
        errors.append(f"AC-03: {label}: llm の criteria（キーか本文）がない")
    if "weight" in fm and not (isinstance(fm["weight"], (int, float)) and not isinstance(fm["weight"], bool) and fm["weight"] > 0):
        errors.append(f"AC-03: {label}: weight は正の数")
    if "arm" in fm and fm["arm"] not in KNOWN_ARM:
        errors.append(f"AC-03: {label}: arm は with-only か both: {fm['arm']!r}")
    if kind == "regex":
        errors += _regex_errors(label, fm.get("pattern"), fm.get("flags")) if "pattern" in fm else []
        if "flags" in fm and fm["flags"] not in KNOWN_REGEX_FLAGS:
            errors.append(f"AC-04: {label}: flags は i だけ: {fm['flags']!r}")
        if "match" in fm and not (fm["match"] in KNOWN_REGEX_MATCH or re.fullmatch(r"count:\d+", str(fm["match"]))):
            errors.append(f"AC-04: {label}: match が知らない値: {fm['match']!r}")
        if "target" in fm and not _known_target(fm["target"]):
            errors.append(f"AC-04: {label}: target が知らない値: {fm['target']!r}")
    elif kind == "tool_used":
        if "input_match" in fm:
            errors += _regex_errors(label + " input_match", fm["input_match"])
        for key in ("min", "max"):
            if key in fm and not (isinstance(fm[key], int) and not isinstance(fm[key], bool) and fm[key] >= 0):
                errors.append(f"AC-03: {label}: {key} は 0 以上の整数")
        tool, eff_min = fm.get("tool"), fm.get("min", 1)
        if tool == "Skill":
            errors.append(f"AC-07: {label}: tool_used: Skill は使わない（/名前 で起動すると Skill の呼び出しにならないおそれ）")
        if fm.get("max") == 0 and fm.get("min") != 0:
            errors.append(f"AC-05: {label}: max: 0 のときは min: 0 も書く（min の既定は 1）")
        if isinstance(eff_min, int) and eff_min >= 1:
            need = {"Bash": "needs-bash", "Write": "needs-write", "Edit": "needs-write"}.get(tool)
            if need and need not in tags:
                errors.append(f"AC-07: {label}: {tool} を min 1 以上で採点するので tags に {need} が要る")
        if tool == "Agent" and "Agent" not in allowed:
            errors.append(f"AC-07: {label}: Agent を採点するので allowed_tools に Agent が要る")
    elif kind == "file_exists":
        p = str(fm.get("path", ""))
        if p.startswith(("/", "~")) or re.match(r"[A-Za-z]:", p) or ".." in Path(p).parts or "\\" in p:
            errors.append(f"AC-08: {label}: file_exists の path は相対パスで .. を含まない: {p}")
    elif kind == "llm":
        if fm.get("focus", "last_message") != "last_message":
            errors.append(f"AC-05: {label}: llm の focus は last_message だけ")
    return errors


def check_case(case_dir: Path) -> list[str]:
    name = case_dir.name
    errors: list[str] = []
    if not re.fullmatch(r"[a-z0-9-]+", name):
        errors.append(f"AC-01: {name}: フォルダ名は英小文字・数字・- だけ")
    prompt = case_dir / "prompt.md"
    if not prompt.is_file():
        return errors + [f"AC-01: {name}: prompt.md がない"]
    try:
        fm, body = read_front(prompt.read_text(encoding="utf-8"))
    except ValueError as e:
        return errors + [f"AC-11: {name}/prompt.md: {e}"]
    unknown = set(fm) - KNOWN_PROMPT_KEYS
    if unknown:
        errors.append(f"AC-02: {name}: 知らない prompt のキー: {sorted(unknown)}")
    if fm.get("schema_version", SCHEMA_VERSION) != SCHEMA_VERSION:
        errors.append(f"AC-02: {name}: schema_version は {SCHEMA_VERSION}")
    if fm.get("name") != name:
        errors.append(f"AC-02: {name}: name がフォルダ名と違う: {fm.get('name')!r}")
    for key in ("description", "expected_outcome"):
        if not (isinstance(fm.get(key), str) and fm[key].strip()):
            errors.append(f"AC-02: {name}: {key} が空")
    for key in ("model", "env", "runs", "plugins"):
        if key in fm:
            errors.append(f"AC-02: {name}: {key} は書かない（流し方か既定で決める）")
    for key, high in (("max_turns", 200), ("timeout_seconds", 3600)):
        v = fm.get(key)
        if not (isinstance(v, int) and not isinstance(v, bool) and 1 <= v <= high):
            errors.append(f"AC-02: {name}: {key} は 1〜{high} の整数: {v!r}")
    tags, allowed = fm.get("tags"), fm.get("allowed_tools")
    if not (isinstance(tags, list) and all(isinstance(t, str) for t in tags)):
        errors.append(f"AC-01: {name}: tags は文字のリスト")
        tags = []
    if not (isinstance(allowed, list) and all(isinstance(t, str) for t in allowed)):
        errors.append(f"AC-07: {name}: allowed_tools は文字のリスト")
        allowed = []
    skills = [t for t in tags if t in SKILLS]
    if len(skills) != 1:
        errors.append(f"AC-01: {name}: tags にスキル名が 1 つ要る: {tags}")
    if len([t for t in tags if t in COST_TAGS]) != 1:
        errors.append(f"AC-01: {name}: tags に cheap か agent が 1 つ要る: {tags}")
    other = set(tags) - set(SKILLS) - COST_TAGS - NEEDS_TAGS
    if other:
        errors.append(f"AC-01: {name}: tags に知らない語: {sorted(other)}")
    bad_tools = set(allowed) - CASE_ALLOWED_TOOLS
    if bad_tools:
        errors.append(f"AC-07: {name}: allowed_tools にケースでは許せない道具: {sorted(bad_tools)}（Bash・Write・Edit は --allow-tools で許す）")
    if skills and not starts_with_skill(body, skills[0]):
        errors.append(f"AC-06: {name}: 本文が /pipe-in:{skills[0]} で始まっていない")
    graders = sorted((case_dir / "graders").glob("*.md")) if (case_dir / "graders").is_dir() else []
    if not graders:
        errors.append(f"AC-01: {name}: graders/ に採点が 1 つもない")
    kinds: list[str] = []
    for g in graders:
        errors += check_grader(g, tags, allowed)
        try:
            kinds.append(read_front(g.read_text(encoding="utf-8"))[0].get("type", ""))
        except ValueError:
            pass
    if sum(k in ("regex", "tool_used", "file_exists") for k in kinds) < 3:
        errors.append(f"AC-05: {name}: 費用のかからない型（regex・tool_used・file_exists）が 3 つ以上要る")
    if kinds.count("llm") > 1:
        errors.append(f"AC-05: {name}: llm は 1 ケースに 1 つまで")
    case_yaml = case_dir / "case.yaml"
    if case_yaml.is_file():
        try:
            cy = read_case_yaml(case_yaml.read_text(encoding="utf-8"))
        except ValueError as e:
            errors.append(f"AC-11: {name}/case.yaml: {e}")
        else:
            if cy.get("schema_version") != SCHEMA_VERSION:
                errors.append(f"AC-08: {name}: case.yaml の schema_version は {SCHEMA_VERSION}")
            if cy.get("name") != name:
                errors.append(f"AC-08: {name}: case.yaml の name がフォルダ名と違う")
            script = (cy.get("context") or {}).get("scaffold_script")
            if script is not None:
                target = (case_dir / str(script)).resolve()
                if case_dir.resolve() not in target.parents or not target.is_file():
                    errors.append(f"AC-08: {name}: scaffold_script がケースの中に実在しない: {script}")
    return errors


def check_suite(evals_dir: Path) -> list[str]:
    if not evals_dir.is_dir():
        return [f"AC-01: {evals_dir} がない（9 本のケースが無い）"]
    errors: list[str] = []
    children = sorted(p for p in evals_dir.iterdir() if p.name != "results")
    for p in children:
        if not p.is_dir():
            errors.append(f"AC-01: evals/ 直下にフォルダでないものがある: {p.name}")
        elif not (p / "prompt.md").is_file():
            errors.append(f"AC-01: results 以外のフォルダはケースでなければならない（prompt.md がない）: {p.name}")
    names = sorted(p.name for p in children if p.is_dir())
    if names != sorted(CASE_NAMES):
        errors.append(f"AC-01: ケースが 9 本そろっていない: {names}")
    per_skill = {s: 0 for s in SKILLS}
    llm_total = 0
    for p in children:
        if not p.is_dir():
            continue
        errors += check_case(p)
        try:
            tags = read_front((p / "prompt.md").read_text(encoding="utf-8"))[0].get("tags", [])
        except (ValueError, OSError):
            continue
        for s in SKILLS:
            per_skill[s] += s in tags
        for g in (p / "graders").glob("*.md") if (p / "graders").is_dir() else []:
            try:
                llm_total += read_front(g.read_text(encoding="utf-8"))[0].get("type") == "llm"
            except ValueError:
                pass
    if any(n != 3 for n in per_skill.values()):
        errors.append(f"AC-01: スキルごとに 3 本ずつ要る: {per_skill}")
    if llm_total > 2:
        errors.append(f"AC-05: llm は全体で 2 つ以下: {llm_total}")
    return errors


def _only(errors: list[str], *prefixes: str) -> list[str]:
    return [e for e in errors if e.split(":", 1)[0] in prefixes]


def suite_errors(*prefixes: str) -> list[str]:
    errors = check_suite(EVALS)
    return _only(errors, *prefixes)


def _case_dir(name: str) -> Path:
    path = EVALS / name
    assert path.is_dir(), f"plugin/evals/{name}/ がない"
    return path


def _graders(name: str) -> list[tuple[Path, dict, str]]:
    out = []
    for g in sorted((_case_dir(name) / "graders").glob("*.md")):
        fm, body = read_front(g.read_text(encoding="utf-8"))
        out.append((g, fm, body))
    assert out, f"{name}/graders/ に採点がない"
    return out


# ---- AC-01：9 本のケース -----------------------------------------------------------------------------


def test_D0043_AC_01_suite_has_nine_cases():
    """D0043-AC-01: plugin/evals/ に 9 本のケース（スキルごとに 3 本）があり、results 以外の子はすべてケースで、どれにも prompt.md と graders/ の採点がある。"""
    assert suite_errors("AC-01") == []


@pytest.mark.parametrize("name", CASE_NAMES)
def test_D0043_AC_01_case_exists_with_prompt_and_graders(name):
    """D0043-AC-01: 設計の表のケース名ごとに、prompt.md と graders/*.md（1 つ以上）がある。"""
    case = _case_dir(name)
    assert (case / "prompt.md").is_file()
    assert list((case / "graders").glob("*.md"))


def test_D0043_AC_01_tags_have_skill_and_cost_and_known_needs():
    """D0043-AC-01: tags はスキル名 1 つ＋ cheap か agent ＋ 知っている needs-* だけ。スキル名はケース名の表と同じ。"""
    for skill, names in CASES.items():
        for name in names:
            tags = read_front((_case_dir(name) / "prompt.md").read_text(encoding="utf-8"))[0]["tags"]
            assert skill in tags, (name, tags)
    assert suite_errors("AC-01") == []


# ---- AC-02〜AC-08：各ファイルの形 ---------------------------------------------------------------------


def test_D0043_AC_02_prompt_frontmatter_keys_and_values():
    """D0043-AC-02: prompt.md のキーは公式の既知のものだけ。name はフォルダ名、model・env・runs・plugins は書かず、max_turns・timeout_seconds は上限の内。"""
    for name in CASE_NAMES:
        _case_dir(name)
    assert suite_errors("AC-02", "AC-11") == []


def test_D0043_AC_03_grader_types_and_required_keys():
    """D0043-AC-03: グレーダーの type・型ごとのキー・必須のキー・weight（正）・arm が正しい。llm は criteria か本文を持つ。"""
    for name in CASE_NAMES:
        _graders(name)
    assert suite_errors("AC-03", "AC-11") == []


def test_D0043_AC_04_regex_patterns_compile_and_known_values():
    """D0043-AC-04: regex の pattern は flags つきでコンパイルでき、JavaScript と Python で意味が同じ範囲。match・target は既知の値。input_match も読める。"""
    for name in CASE_NAMES:
        _graders(name)
    assert suite_errors("AC-04", "AC-11") == []


GOOD_BAD_SHAPE = (
    '[[stages]]\nname = "review"\naccess = "docs"\n\n[stages.check]\nverdict = true\n'
    'command = "python -m pytest -q"\non_fail = "review"\nmax_retries = 2\n\n[stages.check.judge]\nmodel = "haiku"\n'
)
BAD_BAD_SHAPE = (
    '[[stages]]\nname = "review"\naccess = "docs"\n\n[stages.check]\nverdict = true\n'
    'on_fail = "review"\nmax_retries = 2\n\n[stages.check.judge]\nmodel = "haiku"\n'
)
BAD_AFTER_GOOD = '[[stages]]\nname = "a"\n\n[stages.check]\ncommand = "true"\n\n' + BAD_BAD_SHAPE


def test_D0043_AC_04_bad_shape_regex_matches_only_the_bad_example():
    """D0043-AC-04: build-refuses-judge-only の「command が無いのに on_fail と judge」を探す正規表現は、悪い例の文字に当たり、良い例の文字には当たらない。"""
    fm = next(fm for _, fm, _ in _graders("build-refuses-judge-only") if fm.get("type") == "regex" and fm.get("match") == "not_contains")
    pattern = re.compile(fm["pattern"])
    assert pattern.search(BAD_BAD_SHAPE)
    assert pattern.search(BAD_AFTER_GOOD)
    assert not pattern.search(GOOD_BAD_SHAPE)
    assert not pattern.search("[[stages]]\nname = \"a\"\n\n[stages.check]\nverdict = true\non_fail = \"a\"\n")


def test_D0043_AC_04_content_regex_reads_the_pipe_file_not_the_path_list():
    """D0043-AC-04: 書かれたパイプの中身を見る regex は target: files（作られたパスの一覧）ではなく、そのパイプの pipe.toml を読む。"""
    for name, pipe in [("build-passes-check", "notes-summary"), ("build-refuses-judge-only", "notes-review")]:
        content = [fm for _, fm, _ in _graders(name) if fm.get("type") == "regex" and "stages" in fm.get("pattern", "")]
        assert content, name
        for fm in content:
            assert fm.get("target") == {"source": "file", "path": f".pipe-in/pipes/pipe-in-{pipe}/pipe.toml"}, name
    files_regex = [(n, g.name) for n in CASE_NAMES for g, fm, _ in _graders(n) if fm.get("type") == "regex" and fm.get("target") == "files"]
    assert files_regex == []


def test_D0043_AC_04_narrow_words_for_judge_score_and_command_hint():
    """D0043-AC-04: 「judge-score を呼ばない」は pipe-in-gen --help の確かめに当たらない。「command と組む案内」は、関係ない「差し戻」に当たらない。"""
    no_score = next(fm for g, fm, _ in _graders("judge-rejects-bad-runs") if g.name == "02-no-score.md")
    assert not re.search(no_score["input_match"], '{"command": "pipe-in-gen --help | grep judge-score"}')
    assert re.search(no_score["input_match"], '{"command": "pipe-in-gen judge-score < runs.json"}')
    says = next(fm for g, fm, _ in _graders("build-refuses-judge-only") if g.name == "02-says-command.md")
    assert not re.search(says["pattern"], "pipe-builder が差し戻してきたら、直して渡し直します。")
    assert re.search(says["pattern"], "審査だけの check は作れないので、command と組んでください。")


def test_D0043_AC_05_llm_budget_and_cheap_graders():
    """D0043-AC-05: llm は全体で 2 つ以下・1 ケースに 1 つまで・focus は last_message。費用のかからない型が各ケースに 3 つ以上ある。"""
    for name in CASE_NAMES:
        _graders(name)
    assert suite_errors("AC-05") == []
    llms = [(n, g.name) for n in CASE_NAMES for g, fm, _ in _graders(n) if fm.get("type") == "llm"]
    assert llms == [("judge-must-violation-fails", "04-quote.md")]


def test_D0043_AC_05_no_negative_tool_used_without_min_and_max():
    """D0043-AC-05: 「呼ばない」採点は max: 0 と min: 0 の両方を書く（min の既定は 1 なので、max だけだと必ず落ちる）。"""
    zero_max = 0
    for name in CASE_NAMES:
        for g, fm, _ in _graders(name):
            if fm.get("type") == "tool_used" and fm.get("max") == 0:
                zero_max += 1
                assert fm.get("min") == 0, g
    assert zero_max > 0, "呼ばないことを測る採点が 1 つも無い"


def test_D0043_AC_06_prompt_starts_with_own_skill():
    """D0043-AC-06: どの prompt.md の本文も /pipe-in:<tags のスキル名> で始まる。"""
    for skill, names in CASES.items():
        for name in names:
            _, body = read_front((_case_dir(name) / "prompt.md").read_text(encoding="utf-8"))
            assert body.lstrip().startswith(f"/pipe-in:{skill}"), (name, body[:40])
    assert suite_errors("AC-06") == []


def test_D0043_AC_07_allowed_tools_are_read_only_and_needs_tags_match():
    """D0043-AC-07: allowed_tools は公式がケースで許す道具だけ（Bash・Write・Edit・WebFetch・WebSearch・mcp__ は無い）。Bash・Write・Edit を min 1 以上で採点するケースは needs-* の tags を持ち、Agent を採点するなら Agent を許す。tool_used: Skill は無い。"""
    for name in CASE_NAMES:
        _graders(name)
        allowed = read_front((_case_dir(name) / "prompt.md").read_text(encoding="utf-8"))[0]["allowed_tools"]
        assert not set(allowed) & NEEDS_ALLOW_TOOLS, name
        assert not [t for t in allowed if t.startswith("mcp__")], name
    assert suite_errors("AC-07") == []


@pytest.mark.parametrize("name", CASE_NAMES)
def test_D0043_AC_08_case_yaml_and_scaffold_paths(name):
    """D0043-AC-08: case.yaml は schema_version "1.1"・name がフォルダ名・scaffold_script が scaffold.sh（ケースの中に実在）。scaffold.py もある。"""
    case = _case_dir(name)
    cy = read_case_yaml((case / "case.yaml").read_text(encoding="utf-8"))
    assert cy["schema_version"] == SCHEMA_VERSION
    assert cy["name"] == name
    assert cy["context"] == {"scaffold_script": "scaffold.sh"}
    assert (case / "scaffold.sh").is_file() and (case / "scaffold.py").is_file()
    assert _only(check_case(case), "AC-08") == []


@pytest.mark.parametrize("name", CASE_NAMES)
def test_D0043_AC_08_scaffold_sh_is_thin_bash(name):
    """D0043-AC-08: scaffold.sh は set -eu で scaffold.py を呼ぶだけの薄い Bash。pipe-in-gen を作る文（ここには pipe-in-gen の名前自体）を書かない。"""
    text = (_case_dir(name) / "scaffold.sh").read_text(encoding="utf-8")
    assert "set -eu" in text
    assert "scaffold.py" in text
    assert "pipe-in-gen" not in text
    assert "pip install" not in text


def _load_scaffold(name: str):
    path = _case_dir(name) / "scaffold.py"
    assert path.is_file(), f"{name}/scaffold.py がない"
    spec = importlib.util.spec_from_file_location(f"scaffold_{name.replace('-', '_')}", path)
    module = importlib.util.module_from_spec(spec)
    # 配るプラグインのフォルダに __pycache__ を作らない（AC-09 が evals 下の全ファイルを文字として読むため）。
    before = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = before
    return module


def _files(root: Path) -> set[str]:
    return {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}


def _run_main(module, args: list[str]) -> int:
    try:
        rc = module.main(args)
    except SystemExit as e:
        rc = e.code
    return 0 if rc in (None, 0) else (rc if isinstance(rc, int) else 1)


EXPECTED_SCAFFOLD_FILES = {
    "build-shows-table-first": {"README.md", "notes/a.md", "notes/b.md"},
    "build-passes-check": {"README.md", "notes/a.md", "notes/b.md"},
    "build-refuses-judge-only": {"README.md", "notes/a.md", "notes/b.md"},
    "eval-lists-and-waits": {"pipeline.toml", "docs/pipeline/sample/state.json"},
    "eval-result-json": {"pipeline.toml", "docs/pipeline/sample/state.json"},
    "eval-stops-without-state": {"pipeline.toml"},
    "judge-calls-judge-score": {"request.md", "report.md"},
    "judge-must-violation-fails": {"request.md", "report.md", "rubric.md"},
    "judge-rejects-bad-runs": {"request.md", "report.md"},
}


@pytest.mark.parametrize("name", CASE_NAMES)
def test_D0043_AC_08_scaffolds_build_in_tmp(name, tmp_path):
    """D0043-AC-08: scaffold.py の build(target) は、空の tmp_path に見本だけを書く（target の外に書かない・コマンドを起こさない）。state.json は JSON として読める。"""
    mod = _load_scaffold(name)
    target = tmp_path / "ws"
    target.mkdir()
    mod.build(target)
    assert _files(tmp_path) == {f"ws/{f}" for f in EXPECTED_SCAFFOLD_FILES[name]}
    for rel in EXPECTED_SCAFFOLD_FILES[name]:
        text = (target / rel).read_text(encoding="utf-8")
        assert text.strip(), rel
        for pattern, what in FORBIDDEN_IN_SKILL:
            assert not re.search(pattern, text), (rel, what)
    state = target / "docs/pipeline/sample/state.json"
    if state.exists():
        data = json.loads(state.read_text(encoding="utf-8"))
        assert isinstance(data, dict) and {"pipe", "stages"} <= set(data)
    source = (_case_dir(name) / "scaffold.py").read_text(encoding="utf-8")
    for word in ["sub" + "process", "os." + "system", "Pop" + "en"]:
        assert word not in source, word


def test_D0043_AC_08_judge_must_report_has_forbidden_term_once(tmp_path):
    """D0043-AC-08: judge-must-violation-fails の見本は、report.md に禁止語 FORBIDDEN-TERM-7 を 1 回だけ含み、rubric.md に must の行がある。"""
    mod = _load_scaffold("judge-must-violation-fails")
    mod.build(tmp_path)
    assert (tmp_path / "report.md").read_text(encoding="utf-8").count("FORBIDDEN-TERM-7") == 1
    assert "FORBIDDEN-TERM-7" in (tmp_path / "rubric.md").read_text(encoding="utf-8")
    assert "must" in (tmp_path / "rubric.md").read_text(encoding="utf-8")


REAL_TREE_SHAPES = {
    "nonempty": ["note.txt"],
    "git": [".git/HEAD"],
    "plugin": ["plugin/skills/x.md"],
    "docs-pipeline": ["docs/pipeline/state.json"],
    "pipes": ["pipes/a/pipe.toml"],
    "dot-pipe-in": [".pipe-in/pipes/a/pipe.toml"],
}


@pytest.mark.parametrize("shape", sorted(REAL_TREE_SHAPES))
@pytest.mark.parametrize("name", CASE_NAMES)
def test_D0043_AC_08_scaffold_refuses_real_looking_tree(name, shape, tmp_path, monkeypatch):
    """D0043-AC-08: 空でない作業フォルダ・実物に似た形（.git・plugin/・docs/pipeline/・pipes/・.pipe-in/）には何も書かず、終了コード 1 で断る。"""
    mod = _load_scaffold(name)
    monkeypatch.setattr(shutil, "which", lambda cmd, *a, **k: "/usr/local/bin/" + cmd)
    target = tmp_path / "ws"
    for rel in REAL_TREE_SHAPES[shape]:
        (target / rel).parent.mkdir(parents=True, exist_ok=True)
        (target / rel).write_text("x", encoding="utf-8")
    before = _files(tmp_path)
    assert _run_main(mod, [str(target)]) == 1
    assert _files(tmp_path) == before


@pytest.mark.parametrize("name", CASE_NAMES)
def test_D0043_AC_08_scaffold_main_needs_pipe_in_gen_and_builds_in_empty_dir(name, tmp_path, monkeypatch):
    """D0043-AC-08: main は pipe-in-gen が PATH に無ければ書かずに終了コード 1。あれば空の作業フォルダに見本を作って 0。"""
    mod = _load_scaffold(name)
    target = tmp_path / "ws"
    target.mkdir()
    monkeypatch.setattr(shutil, "which", lambda cmd, *a, **k: None)
    assert _run_main(mod, [str(target)]) == 1
    assert _files(target) == set()
    monkeypatch.setattr(shutil, "which", lambda cmd, *a, **k: "/usr/local/bin/" + cmd)
    assert _run_main(mod, [str(target)]) == 0
    assert _files(target) == EXPECTED_SCAFFOLD_FILES[name]


def test_D0043_AC_08_scaffold_common_block_is_identical():
    """D0043-AC-08: 各 scaffold.py の「# --- common ---」から「# --- /common ---」までの共通の囲みが、9 本で同じ。"""
    blocks = set()
    for name in CASE_NAMES:
        text = (_case_dir(name) / "scaffold.py").read_text(encoding="utf-8")
        m = re.search(r"# --- common ---\n(.*?)# --- /common ---", text, re.S)
        assert m and m.group(1).strip(), f"{name}: 共通の囲みがない"
        blocks.add(m.group(1))
    assert len(blocks) == 1


def test_D0043_AC_08_file_exists_paths_are_relative():
    """D0043-AC-08: file_exists の path は相対パスで、.. や手元のパスを含まない（glob は * を使える）。"""
    found = 0
    for name in CASE_NAMES:
        for g, fm, _ in _graders(name):
            if fm.get("type") == "file_exists":
                found += 1
                p = fm["path"]
                assert not p.startswith(("/", "~")) and ".." not in Path(p).parts, g
                assert not re.match(r"[A-Za-z]:", p) and "\\" not in p, g
    assert found >= 2


# ---- AC-09・10：公開してよいか・結果は追跡しない ---------------------------------------------------------


def test_D0043_AC_09_no_local_paths_or_secrets_in_evals():
    """D0043-AC-09: plugin/evals/ の下のすべてのファイルに、手元のパス・鍵・メールアドレスが無い。"""
    assert EVALS.is_dir(), "plugin/evals/ がない"
    files = [p for p in EVALS.rglob("*") if p.is_file()]
    assert files, "plugin/evals/ にファイルが 1 つもない"
    for path in files:
        text = path.read_text(encoding="utf-8")
        for pattern, what in FORBIDDEN_IN_SKILL:
            assert not re.search(pattern, text), (path.relative_to(ROOT).as_posix(), what, pattern)


def test_D0043_AC_10_gitignore_has_results():
    """D0043-AC-10: .gitignore の行に /plugin/evals/results/ がある（結果は追跡しない）。"""
    lines = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "/plugin/evals/results/" in [line.strip() for line in lines]


# ---- AC-11：壊した入力を落とす（実物のケースは書き換えず、tmp_path に作る） ---------------------------------


def _w(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def make_good_case(root: Path, name: str = "build-shows-table-first") -> Path:
    case = root / name
    _w(case / "prompt.md", (
        f"---\nname: {name}\ndescription: 段の表を見せて確認を待つ\ntags: [pipe-build, cheap]\n"
        "expected_outcome: 書かずに表を見せる\nmax_turns: 15\ntimeout_seconds: 300\n"
        "allowed_tools: [Read, Glob, Grep, Skill, Agent]\n---\n"
        "/pipe-in:pipe-build notes/ を要約するパイプを作りたい。\n"
    ))
    _w(case / "graders/01-no-write.md", "---\ntype: tool_used\ntool: Write\nmin: 0\nmax: 0\n---\n書かない。\n")
    _w(case / "graders/02-words.md", "---\ntype: regex\npattern: 'access'\n---\n表の語。\n")
    _w(case / "graders/03-ask.md", "---\ntype: regex\npattern: '確認'\nflags: i\n---\n確認の問い。\n")
    _w(case / "case.yaml", f'schema_version: "1.1"\nname: {name}\ncontext:\n  scaffold_script: scaffold.sh\n')
    _w(case / "scaffold.sh", "set -eu\n")
    return case


def _sub(rel: str, old: str, new: str):
    def apply(case: Path) -> None:
        path = case / rel
        text = path.read_text(encoding="utf-8")
        assert old in text, (rel, old)
        path.write_text(text.replace(old, new, 1), encoding="utf-8")
    return apply


def _remove_graders(case: Path) -> None:
    for g in (case / "graders").glob("*.md"):
        g.unlink()


def _add(rel: str, text: str):
    return lambda case: _w(case / rel, text)


BROKEN = {
    "case.yaml が schema 1.0": _sub("case.yaml", '"1.1"', '"1.0"'),
    "prompt に schema_version 1.0": _sub("prompt.md", "name: build", 'schema_version: "1.0"\nname: build'),
    "知らない prompt のキー": _sub("prompt.md", "max_turns: 15", "max_turns: 15\nfoo: 1"),
    "model を書いた": _sub("prompt.md", "max_turns: 15", "max_turns: 15\nmodel: sonnet"),
    "name がフォルダ名と違う": _sub("prompt.md", "name: build-shows-table-first", "name: other"),
    "max_turns が上限超え": _sub("prompt.md", "max_turns: 15", "max_turns: 201"),
    "timeout が上限超え": _sub("prompt.md", "timeout_seconds: 300", "timeout_seconds: 3601"),
    "allowed_tools に Bash": _sub("prompt.md", "Grep, Skill", "Grep, Bash, Skill"),
    "allowed_tools に WebFetch": _sub("prompt.md", "Grep, Skill", "Grep, WebFetch, Skill"),
    "本文がスキルで始まらない": _sub("prompt.md", "/pipe-in:pipe-build", "pipe-in:pipe-build"),
    "本文が別のスキル": _sub("prompt.md", "/pipe-in:pipe-build", "/pipe-in:pipe-eval"),
    "tags にスキルが無い": _sub("prompt.md", "[pipe-build, cheap]", "[cheap]"),
    "tags に cost が無い": _sub("prompt.md", "[pipe-build, cheap]", "[pipe-build]"),
    "複数行の値": _sub("prompt.md", "description: 段の表を見せて確認を待つ", "description: |\n  段の表"),
    "知らない型": _add("graders/04-x.md", "---\ntype: magic\n---\nx\n"),
    "必須のキー欠け（regex の pattern）": _add("graders/04-x.md", "---\ntype: regex\n---\nx\n"),
    "必須のキー欠け（tool_used の tool）": _add("graders/04-x.md", "---\ntype: tool_used\n---\nx\n"),
    "グレーダーの知らないキー": _add("graders/04-x.md", "---\ntype: regex\npattern: 'a'\nfoo: 1\n---\nx\n"),
    "グレーダー無し": _remove_graders,
    "flags: s": _add("graders/04-x.md", "---\ntype: regex\npattern: 'a'\nflags: s\n---\nx\n"),
    "(?s) を含む pattern": _add("graders/04-x.md", "---\ntype: regex\npattern: '(?s)a.b'\n---\nx\n"),
    "名前つきグループ": _add("graders/04-x.md", "---\ntype: regex\npattern: '(?P<a>b)'\n---\nx\n"),
    "コンパイルできない pattern": _add("graders/04-x.md", "---\ntype: regex\npattern: '(abc'\n---\nx\n"),
    "知らない match": _add("graders/04-x.md", "---\ntype: regex\npattern: 'a'\nmatch: maybe\n---\nx\n"),
    "知らない target": _add("graders/04-x.md", "---\ntype: regex\npattern: 'a'\ntarget: everything\n---\nx\n"),
    "target のファイルが外を指す": _add("graders/04-x.md", "---\ntype: regex\npattern: 'a'\ntarget: {source: file, path: ../x.toml}\n---\nx\n"),
    "target の source が file でない": _add("graders/04-x.md", "---\ntype: regex\npattern: 'a'\ntarget: {source: url, path: x.toml}\n---\nx\n"),
    "input_match がコンパイルできない": _add("graders/04-x.md", "---\ntype: tool_used\ntool: Read\ninput_match: '(a'\nmin: 0\nmax: 0\n---\nx\n"),
    "weight が 0": _add("graders/04-x.md", "---\ntype: regex\npattern: 'a'\nweight: 0\n---\nx\n"),
    "arm が知らない値": _add("graders/04-x.md", "---\ntype: regex\npattern: 'a'\narm: only\n---\nx\n"),
    "max: 0 だけで min が無い": _add("graders/04-x.md", "---\ntype: tool_used\ntool: Read\nmax: 0\n---\nx\n"),
    "Bash を採点するのに needs-bash が無い": _add("graders/04-x.md", "---\ntype: tool_used\ntool: Bash\n---\nx\n"),
    "tool_used: Skill": _add("graders/04-x.md", "---\ntype: tool_used\ntool: Skill\n---\nx\n"),
    "file_exists が .. を含む": _add("graders/04-x.md", "---\ntype: file_exists\npath: ../x.md\n---\nx\n"),
    "file_exists が絶対パス": _add("graders/04-x.md", "---\ntype: file_exists\npath: /tmp/x.md\n---\nx\n"),
    "llm の focus が trace": _add("graders/04-x.md", "---\ntype: llm\nfocus: trace\n---\n基準\n"),
    "llm が 2 つ": lambda case: (_w(case / "graders/04-x.md", "---\ntype: llm\n---\n基準\n"), _w(case / "graders/05-x.md", "---\ntype: llm\n---\n基準\n")),
    "scaffold_script が実在しない": _sub("case.yaml", "scaffold.sh", "nothing.sh"),
    "scaffold_script がケースの外": _sub("case.yaml", "scaffold.sh", "../x.sh"),
    "case.yaml の name が違う": _sub("case.yaml", "name: build-shows-table-first", "name: other"),
}


def test_D0043_AC_11_good_minimal_case_passes_check(tmp_path):
    """D0043-AC-11: 検査の土台。壊す前の最小のケースは検査を通る（今の作りのままで緑。壊したものだけが落ちることを示す）。"""
    assert check_case(make_good_case(tmp_path)) == []


@pytest.mark.parametrize("label", sorted(BROKEN))
def test_D0043_AC_11_broken_inputs_are_rejected(label, tmp_path):
    """D0043-AC-11: 古い形・知らない形・壊れた形（schema 1.0・知らないキー・知らない型・採点無し・必須のキー欠け・Bash を許す・flags: s・(?s) など）を検査が落とす。"""
    case = make_good_case(tmp_path)
    BROKEN[label](case)
    assert check_case(case), f"壊したのに検査が通った: {label}"


@pytest.mark.parametrize("text", [
    "---\nname: a\ndescription: |\n  long\n---\nbody",
    "---\nname: a\nname: b\n---\nbody",
    "---\nname: a\n\ttags: [x]\n---\nbody",
    "---\nname: a\n  nested: 1\n---\nbody",
    '---\npattern: "a\\sb"\n---\nbody',
    "---\ntags: [a, b\n---\nbody",
    "---\npattern: 'abc\n---\nbody",
    "---\nname: &anchor a\n---\nbody",
    "---\nname: {a: 1\n---\nbody",
    "---\nname: {a 1}\n---\nbody",
    "---\nname: {a: 1, a: 2}\n---\nbody",
    "name: a\nbody",
])
def test_D0043_AC_11_reader_subset_rejects_unsupported_syntax(text):
    """D0043-AC-11: 読み手は範囲外の書き方（複数行・重複キー・タブ・入れ子・ダブルクォート内の \\・閉じない引用符やリスト・アンカー・frontmatter なし）を黙って読み飛ばさず ValueError にする。"""
    with pytest.raises(ValueError):
        read_front(text)


def test_D0043_AC_11_reader_subset_reads_supported_syntax():
    """D0043-AC-11: 読み手は範囲内の書き方（文字・数・真偽・1 行のリスト・シングルクォートの '' ・case.yaml の context 1 段）を正しく読む。"""
    fm, body = read_front("---\nname: a\nruns: 3\nok: true\ntags: [x, y]\npattern: 'it''s \\d+'\nq: \"1.1\"\n---\n本文\n")
    assert fm == {"name": "a", "runs": 3, "ok": True, "tags": ["x", "y"], "pattern": "it's \\d+", "q": "1.1"}
    assert body == "本文\n"
    fm, _ = read_front("---\ntarget: {source: file, path: .pipe-in/pipes/x/pipe.toml}\n---\n")
    assert fm == {"target": {"source": "file", "path": ".pipe-in/pipes/x/pipe.toml"}}
    assert read_case_yaml('schema_version: "1.1"\nname: a\ncontext:\n  scaffold_script: scaffold.sh\n') == {
        "schema_version": "1.1", "name": "a", "context": {"scaffold_script": "scaffold.sh"},
    }


@pytest.mark.parametrize("pattern,safe", [
    (r"(?=[\s\S]*a)(?=[\s\S]*b)", True),
    (r"((?!x)[\s\S])*?", True),
    (r"(?:a|b)", True),
    (r"(?s)a.b", False),
    (r"(?i)a", False),
    (r"(?P<n>a)", False),
    (r"(?<=a)b", False),
    (r"\Aabc", False),
])
def test_D0043_AC_04_js_python_safe(pattern, safe):
    """D0043-AC-04: js_python_safe は、JavaScript と Python で意味が変わる書き方（インラインの記号・名前つきグループ・後読み・\\A）を見つける。"""
    assert js_python_safe(pattern) is safe


def test_D0043_AC_11_check_suite_rejects_stray_folder_and_wrong_count(tmp_path):
    """D0043-AC-11: check_suite は、prompt.md の無いフォルダ（results 以外）・9 本に足りない・名前違いを落とし、results/ は許す。"""
    make_good_case(tmp_path)
    (tmp_path / "results/2026").mkdir(parents=True)
    errors = check_suite(tmp_path)
    assert any("9 本" in e for e in errors)
    assert not any("results" in e for e in errors)
    (tmp_path / "fixtures").mkdir()
    assert any("fixtures" in e for e in check_suite(tmp_path))
    assert check_suite(tmp_path / "nothing")


# ---- AC-12：流さない・AC-13/14：動きと版を変えない ---------------------------------------------------------


def test_D0043_AC_12_eval_tests_do_not_run_claude():
    """D0043-AC-12: このテストのファイルは、子プロセス・SDK・ネットワークを使わない（ファイルを読むだけ。検査する語はつなげて作る）。"""
    text = Path(__file__).read_text(encoding="utf-8")
    words = ["sub" + "process", "claude_agent" + "_sdk", "anthro" + "pic", "os." + "system", "Pop" + "en", "url" + "lib.request", "soc" + "ket"]
    imports = re.findall(r"^\s*(?:import|from)\s+([\w.]+)", text, re.M)
    for word in words:
        assert word not in imports, word
    assert ("Pop" + "en(") not in text and ("os." + "system(") not in text


def test_D0043_AC_14_skills_and_hooks_do_not_depend_on_evals():
    """D0043-AC-14: スキル・エージェント・フックの文は evals/ を読まない（evals/ を持たない 0.5.0 までのプラグインもそのまま動く）。"""
    texts = [
        PLUGIN / "skills/pipe-build/SKILL.md", PLUGIN / "skills/pipe-build/references/stage-rules.md",
        PLUGIN / "skills/pipe-eval/SKILL.md", PLUGIN / "skills/pipe-judge/SKILL.md", PLUGIN / "skills/pipe-live/SKILL.md",
        PLUGIN / "agents/pipe-builder.md", PLUGIN / "agents/pipe-judge.md", PLUGIN / "hooks/hooks.json",
    ]
    for path in texts:
        assert "evals" not in path.read_text(encoding="utf-8"), path.name


def test_D0043_AC_14_plugin_version_stays_0_5_0():
    """D0043-AC-14: プラグインの版は 0.5.0 のまま（evals/ を足しても動きは変わらない）。"""
    manifest = json.loads((PLUGIN / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))
    assert manifest["version"] == "0.5.0"


def test_D0043_AC_14_guide_update_notes_still_say_0_5_0():
    """D0043-AC-14: ガイドの「0.4.0 以前から更新するとき」の節は 0.5.0 のまま。"""
    guide = (ROOT / "docs/guide/plugin.md").read_text(encoding="utf-8")
    section = guide.split("## 0.4.0 以前から更新するとき")[1].split("\n## ")[0]
    assert "0.5.0" in section


# ---- AC-15・16：文書 ------------------------------------------------------------------------------------


GUIDE_WORDS = [
    "claude plugin eval", "--scaffold", "--allow-tools", "--model", "--judge-model", "--max-cost-usd", "--threshold",
    "--trust-plugin", "--no-publish", "--case", "--tag", "--output-dir", "plugin/evals/results/", "人に言われたとき",
    "利用料", "サンドボックス", "pipe-in-gen", "--ablation none", "WSL2", *CASE_NAMES,
]


def test_D0043_AC_15_guide_has_eval_section():
    """D0043-AC-15: docs/guide/plugin.md に節「プラグインの eval」があり（検査と審査の節と 0.4.0 以前の節の間）、流し方・注意・9 本のケース名が書かれている。"""
    guide = (ROOT / "docs/guide/plugin.md").read_text(encoding="utf-8")
    assert "\n## プラグインの eval\n" in guide
    start = guide.index("## プラグインの eval")
    assert guide.index("## 検査と審査") < start < guide.index("## 0.4.0 以前から更新するとき")
    section = guide[start:].split("\n## ", 1)[0]
    missing = [w for w in GUIDE_WORDS if w not in section]
    assert missing == []


def test_D0043_AC_16_dev_docs_mention_evals():
    """D0043-AC-16: design.md の置き場所の表の plugin/ の行に evals/ が出て、testing.md に pytest はケースの形だけ・流すのは人に言われたときだけと書かれている。"""
    design = (ROOT / "docs/development/design.md").read_text(encoding="utf-8")
    row = next(line for line in design.splitlines() if "`plugin/`" in line and line.startswith("|"))
    assert "evals/" in row
    testing = (ROOT / "docs/development/testing.md").read_text(encoding="utf-8")
    assert "plugin/evals/" in testing and "tests/test_plugin_evals.py" in testing
    assert "人に言われたとき" in testing.split("plugin/evals/", 1)[1][:400]
