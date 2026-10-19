"""難しさの調整。書き手の1回目だけを流して、eval に落ちる割合を見る。"""
import asyncio, json, sys
from run import call, WRITER, WRITER_SYS, clean
from topics import TOPICS, task_text
from evalcheck import run_eval

async def main(levels, k):
    sem = asyncio.Semaphore(10)
    async def one(lv, tp):
        async with sem:
            raw, meta = await call(WRITER, WRITER_SYS, f"{task_text(tp, lv)}\n\n紹介文だけを出力してください。")
        ev = run_eval(tp, clean(raw), lv)
        return lv, tp, ev, meta["cost"]
    jobs = [one(lv, tp) for lv in levels for tp in TOPICS for _ in range(k)]
    res = await asyncio.gather(*jobs)
    for lv in levels:
        rs = [r for r in res if r[0] == lv]
        fails = {}
        for _, _, ev, _ in rs:
            for c in ev["checks"]:
                if not c["ok"]:
                    fails[c["check"]] = fails.get(c["check"], 0) + 1
        print(lv, "1回目の不合格", sum(not r[2]["all_ok"] for r in rs), "/", len(rs), fails)
    print("cost", round(sum(r[3] or 0 for r in res), 3))

asyncio.run(main(sys.argv[1].split(","), int(sys.argv[2])))
