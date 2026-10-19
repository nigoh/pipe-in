"""機械の検査（eval）。決まりを数えて、項目ごとの合否と実際の値を返す。"""
import re
import topics
from topics import TOPICS, LEVELS


def run_eval(key, raw, level=None):
    tp = TOPICS[key]
    lv = LEVELS[level or topics.LEVEL]
    t = re.sub(r"\s", "", raw)
    checks = []
    def add(name, ok, actual): checks.append({"check": name, "ok": bool(ok), "actual": actual})
    add(f"文字数が {lv['min']}〜{lv['max']} 字（空白・改行を除く）", lv["min"] <= len(t) <= lv["max"], len(t))
    sents = [s for s in t.split("。") if s]
    add("ちょうど3文で、「。」で終わる", len(sents) == 3 and t.endswith("。"), {"文の数": len(sents), "最後の文字": t[-1:]})
    lens = [len(s) + 1 for s in sents]
    if lv["sent_min"] <= 1:
        add(f"1文が {lv['sent_max']} 字以内", all(n <= lv["sent_max"] for n in lens), lens)
    else:
        add(f"1文が {lv['sent_min']}〜{lv['sent_max']} 字", all(lv["sent_min"] <= n <= lv["sent_max"] for n in lens), lens)
    add("「です」「ます」を使わない", "です" not in t and "ます" not in t, re.findall(r"です|ます", t))
    for w in tp["required"]:
        if lv["once"]:
            add(f"「{w}」をちょうど1回使う", t.count(w) == 1, t.count(w))
        else:
            add(f"「{w}」を含む", w in t, w in t)
    rest = t
    for w in tp["english"]:
        rest = rest.replace(w, "")
    other = re.findall(r"[A-Za-zＡ-Ｚａ-ｚ]+", rest)
    add("英字は " + " と ".join(tp["english"]) + " の中だけ", not other, other)
    digits = re.findall(r"[0-9０-９]", t)
    add(f"数字は「{tp['digit']}」をちょうど1回だけ", digits == [tp["digit"]], digits)
    bad = re.findall(r"[!！?？\U0001F000-\U0001FAFF☀-➿]", t)
    add("！・？・絵文字を使わない", not bad, bad)
    if lv["max_comma"] is not None:
        cm = [s.count("、") for s in sents]
        add(f"読点は1文に{lv['max_comma']}つまで", all(c <= lv["max_comma"] for c in cm), cm)
    if lv.get("ban"):
        add(f"「{lv['ban']}」を使わない", lv["ban"] not in t, t.count(lv["ban"]))
    add("見出し・箇条書き・Markdown の記号を使わない", not re.search(r"^\s*(#|-|\*|>)|`|\*\*", raw, re.M), None)
    passed = sum(c["ok"] for c in checks)
    return {"passed": passed, "total": len(checks), "all_ok": passed == len(checks), "checks": checks}
