"""eval と LLM as judge の 2×2 実験を回す。

条件: A=どちらも無し / B=eval だけ / C=審査だけ / D=両方。
書き手は haiku、ループ内の審査と伏せた審査は sonnet。書き直しは最大2回（全部で3回）。
結果は trials.jsonl（--out で変えられる）に1試行1行で書く。すでにある試行は飛ばすので、止まっても続きから回せる。

使い方: python3 run.py [--per-cond 50] [--conc 8] [--out trials.jsonl]
"""
import argparse, asyncio, json, os, random, re, sys, time

from claude_agent_sdk import query, ClaudeAgentOptions, AssistantMessage, ResultMessage, TextBlock

sys.path.insert(0, os.path.dirname(__file__))
import topics
from topics import TOPICS, task_text
from evalcheck import run_eval

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = "trials.jsonl"  # 書き先。--out で変える（既定は今いるフォルダ）
WRITER, JUDGE = "haiku", "sonnet"
MAX_WRITES = 3
THRESHOLD = 0.8
STEPS = {0.0, 0.25, 0.5, 0.75, 1.0}
ITEMS = ["instruction_following", "factual_accuracy", "clarity", "structure", "style"]
CONDS = {"A": (False, False), "B": (True, False), "C": (False, True), "D": (True, True)}  # (eval, judge)

WRITER_SYS = "あなたは日本語の短い紹介文を書く。求められた紹介文だけを出力し、前置き・説明・かぎかっこでの囲みは付けない。道具は使えない。文字数は自分で数える。"
JUDGE_SYS = "あなたは LLM as judge（審査役）。渡された課題文と紹介文だけを読んで採点する。道具は使えない。文字は読んで数える。出力は JSON 1つだけ。"

RUBRIC = """# ルーブリック
点は 0.0・0.25・0.5・0.75・1.0 の5段階だけ。

| 項目 | キー | 見ること |
| --- | --- | --- |
| 指示の順守 | instruction_following | 課題の「決まり」（文字数・文の数・1文の長さ・常体・必ず入れる語・英字・数字・記号）を守っているか |
| 事実の正確さ | factual_accuracy | 「事実」に無いことを書いていないか、事実を曲げていないか |
| 分かりやすさ | clarity | 初めての人が読んで、何の道具で、何がうれしいかが分かるか |
| 構成 | structure | 3文の流れが自然で、何の道具か→どう動くか→何がうれしいかが伝わるか |
| 文体 | style | 常体で平易か、硬すぎ・宣伝くさくないか |

総合は5項目の平均、0.8 以上で合格。
reasons を先に書いてから scores を付ける。feedback には作者に返す直すべき点を重要な順に最大5つ（具体的に）。
出力の形（JSON 1つだけ）:
{"reasons": {"instruction_following": "…", "factual_accuracy": "…", "clarity": "…", "structure": "…", "style": "…"}, "scores": {"instruction_following": 0.0, "factual_accuracy": 0.0, "clarity": 0.0, "structure": 0.0, "style": 0.0}, "feedback": ["…"]}
"""


async def call(model, system, prompt, retries=3):
    opts = ClaudeAgentOptions(model=model, tools=[], allowed_tools=[], system_prompt=system,
                              setting_sources=[], max_turns=1, cwd=HERE)
    for attempt in range(retries):
        try:
            text, res = "", None
            async for m in query(prompt=prompt, options=opts):
                if isinstance(m, AssistantMessage):
                    text += "".join(b.text for b in m.content if isinstance(b, TextBlock))
                elif isinstance(m, ResultMessage):
                    res = m
            u = (res.usage or {}) if res else {}
            return text.strip(), {"model": model, "cost": res.total_cost_usd if res else None,
                                  "in": u.get("input_tokens", 0) + u.get("cache_creation_input_tokens", 0) + u.get("cache_read_input_tokens", 0),
                                  "out": u.get("output_tokens", 0)}
        except Exception as e:  # 一時的な失敗は少し待って取り直す
            if attempt == retries - 1:
                raise
            await asyncio.sleep(5 * (attempt + 1))


def parse_judge(text):
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        j = json.loads(m.group(0))
        s = {k: float(j["scores"][k]) for k in ITEMS}
    except Exception:
        return None
    # 総合と合否は審査役の計算に頼らず、ここで出す
    overall = round(sum(s.values()) / len(s), 4)
    return {"scores": s, "overall": overall, "pass": overall >= THRESHOLD,
            "off_scale": [k for k, v in s.items() if v not in STEPS],
            "feedback": [str(x) for x in j.get("feedback", [])][:5], "reasons": j.get("reasons", {})}


async def judge(topic, text):
    prompt = f"{RUBRIC}\n\n# 課題文\n\n{task_text(topic)}\n\n# 採点する紹介文\n\n{text}\n"
    for _ in range(3):
        raw, meta = await call(JUDGE, JUDGE_SYS, prompt)
        j = parse_judge(raw)
        if j:
            j["meta"] = meta
            return j
    return {"error": "parse", "raw": raw, "meta": meta}


def clean(text):
    # 書き手がかぎかっこやコードの囲みを付けたときだけ外す（中身は変えない）
    t = text.strip()
    t = re.sub(r"^```[^\n]*\n|\n?```$", "", t).strip()
    return t


def eval_feedback(ev):
    ng = [c for c in ev["checks"] if not c["ok"]]
    ok = [c["check"] for c in ev["checks"] if c["ok"]]
    lines = [f"【eval】{ev['total']}項目のうち{ev['passed']}項目が合格。"]
    lines += [f"不合格: {c['check']} → 実際: {json.dumps(c['actual'], ensure_ascii=False)}" for c in ng]
    lines.append("合格: " + "／".join(ok))
    return "\n".join(lines)


def judge_feedback(j):
    s = j["scores"]
    lines = [f"【審査】総合 {j['overall']:.2f}（しきい値 {THRESHOLD}）で{'合格' if j['pass'] else '不合格'}。",
             "点: " + "／".join(f"{k} {s[k]}" for k in ITEMS), "直すべき点:"]
    lines += [f"{i}. {f}" for i, f in enumerate(j["feedback"], 1)]
    return "\n".join(lines)


async def run_trial(tr):
    use_eval, use_judge = CONDS[tr["cond"]]
    task = task_text(tr["topic"])
    rounds = []
    prompt = f"{task}\n\n紹介文だけを出力してください。"
    for n in range(1, MAX_WRITES + 1):
        raw, meta = await call(WRITER, WRITER_SYS, prompt)
        text = clean(raw)
        ev = run_eval(tr["topic"], text)  # 測るために全条件で取る。返すのは B・D だけ
        r = {"n": n, "text": text, "eval": ev, "writer": meta}
        if use_judge:
            r["judge"] = await judge(tr["topic"], text)
        rounds.append(r)
        ok_eval = ev["all_ok"] if use_eval else True
        ok_judge = r["judge"].get("pass", False) if use_judge else True
        if (ok_eval and ok_judge) or n == MAX_WRITES or not (use_eval or use_judge):
            break
        fb = []
        if use_eval:
            fb.append(eval_feedback(ev))
        if use_judge:
            fb.append(judge_feedback(r["judge"]) if "scores" in r["judge"] else "【審査】採点に失敗した。")
        prompt = (f"{task}\n\n# あなたが前に書いた紹介文\n\n{text}\n\n# 返ってきた結果\n\n" + "\n\n".join(fb) +
                  "\n\n結果を読んで、決まりを守ったまま書き直してください。書き直した紹介文だけを出力してください。")
    final = rounds[-1]["text"]
    out = dict(tr, level=topics.LEVEL, rounds=rounds, final=final, final_eval=rounds[-1]["eval"], writes=len(rounds))
    return out


async def run_blind(rec):
    b1, b2 = await asyncio.gather(judge(rec["topic"], rec["final"]), judge(rec["topic"], rec["final"]))
    return [b1, b2]


def plan(per_cond, seed=20261019):
    rng = random.Random(seed)
    keys = list(TOPICS)
    trials = []
    for cond in CONDS:
        for i in range(per_cond):
            trials.append({"id": f"{cond}-{i:03d}", "cond": cond, "topic": keys[i % len(keys)]})
    rng.shuffle(trials)  # 条件と題材を混ぜた順に流す（時間帯の偏りを条件に乗せない）
    return trials


def load():
    if not os.path.exists(OUT):
        return {}
    return {json.loads(l)["id"]: json.loads(l) for l in open(OUT, encoding="utf-8") if l.strip()}


async def main(per_cond, conc):
    sem = asyncio.Semaphore(conc)
    done = load()
    todo = [t for t in plan(per_cond) if t["id"] not in done]
    print(f"試行 {len(done)} 件済み、残り {len(todo)} 件", flush=True)
    lock = asyncio.Lock()
    t0 = time.time()

    async def one(tr):
        # 1試行（書き直しと伏せた審査まで）を1つの枠で回し、終わりしだいファイルに書く
        async with sem:
            rec = await run_trial(tr)
            rec["blind"] = await run_blind(rec)
        async with lock:
            with open(OUT, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            done[rec["id"]] = rec
            print(f"[{len(done)}] {rec['id']} {rec['topic']} writes={rec['writes']} eval={rec['final_eval']['passed']}/{rec['final_eval']['total']} "
                  f"blind={[b.get('overall') for b in rec['blind']]} {time.time()-t0:.0f}s", flush=True)

    results = await asyncio.gather(*(one(t) for t in todo), return_exceptions=True)
    errs = [r for r in results if isinstance(r, Exception)]
    print(f"終わり。失敗 {len(errs)} 件", flush=True)
    for e in errs[:5]:
        print(repr(e), flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-cond", type=int, default=50)
    ap.add_argument("--conc", type=int, default=8)
    ap.add_argument("--out", default="trials.jsonl")
    a = ap.parse_args()
    OUT = a.out
    asyncio.run(main(a.per_cond, a.conc))
