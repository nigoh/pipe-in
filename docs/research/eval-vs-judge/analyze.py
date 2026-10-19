"""trials.jsonl を集計して、検定の結果を summary.json に書く。標準ライブラリだけ。

使い方: python3 analyze.py [trials.jsonl] [summary.json]（既定は今いるフォルダ）
"""
import json, math, os, random, re, statistics as st, sys
from itertools import combinations

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
IN = sys.argv[1] if len(sys.argv) > 1 else "trials.jsonl"
OUT = sys.argv[2] if len(sys.argv) > 2 else "summary.json"
from topics import TOPICS

R = random.Random(1)
NPERM = int(os.environ.get("NPERM", 20000))
NBOOT = int(os.environ.get("NBOOT", 10000))
CONDS = ["A", "B", "C", "D"]
FACT = {"A": (0, 0), "B": (1, 0), "C": (0, 1), "D": (1, 1)}  # (eval, judge)
ITEMS = ["instruction_following", "factual_accuracy", "clarity", "structure", "style"]


def load():
    recs = [json.loads(l) for l in open(IN, encoding="utf-8") if l.strip()]
    for r in recs:
        b = [x for x in r["blind"] if "overall" in x]
        r["blind_mean"] = st.mean(x["overall"] for x in b) if b else None
        r["blind_items"] = {k: st.mean(x["scores"][k] for x in b) for k in ITEMS} if b else None
        r["y_eval"] = 1 if r["final_eval"]["all_ok"] else 0
        r["y_eval1"] = 1 if r["rounds"][0]["eval"]["all_ok"] else 0
        r["cost"] = sum((x["writer"]["cost"] or 0) + ((x.get("judge") or {}).get("meta", {}).get("cost") or 0) for x in r["rounds"])
        r["calls_writer"] = len(r["rounds"])
        r["calls_judge"] = sum(1 for x in r["rounds"] if "judge" in x)
    return recs


# ---- 検定 ----
def fisher_two_sided(a, b, c, d):
    """2×2 表 [[a,b],[c,d]] の Fisher の正確検定（両側）。"""
    n1, n2, k, n = a + b, c + d, a + c, a + b + c + d
    def p(x):
        return math.comb(n1, x) * math.comb(n2, k - x) / math.comb(n, k)
    p0 = p(a)
    lo, hi = max(0, k - n2), min(k, n1)
    return min(1.0, sum(p(x) for x in range(lo, hi + 1) if p(x) <= p0 * (1 + 1e-9)))


def wilson(x, n, z=1.96):
    if n == 0:
        return (None, None)
    ph = x / n
    den = 1 + z * z / n
    c = (ph + z * z / (2 * n)) / den
    h = z * math.sqrt(ph * (1 - ph) / n + z * z / (4 * n * n)) / den
    return (round(c - h, 3), round(c + h, 3))


def boot_ci_mean(xs):
    ms = sorted(st.mean(R.choices(xs, k=len(xs))) for _ in range(NBOOT))
    return (round(ms[int(.025 * NBOOT)], 4), round(ms[int(.975 * NBOOT)], 4))


def boot_ci_diff(xs, ys):
    ds = sorted(st.mean(R.choices(xs, k=len(xs))) - st.mean(R.choices(ys, k=len(ys))) for _ in range(NBOOT))
    return (round(ds[int(.025 * NBOOT)], 4), round(ds[int(.975 * NBOOT)], 4))


def perm_diff(xs, ys):
    obs = st.mean(xs) - st.mean(ys)
    pool = xs + ys
    n = len(xs)
    cnt = 0
    for _ in range(NPERM):
        R.shuffle(pool)
        if abs(st.mean(pool[:n]) - st.mean(pool[n:])) >= abs(obs) - 1e-12:
            cnt += 1
    return (cnt + 1) / (NPERM + 1)


def cliffs_delta(xs, ys):
    gt = sum(1 for x in xs for y in ys if x > y)
    lt = sum(1 for x in xs for y in ys if x < y)
    return round((gt - lt) / (len(xs) * len(ys)), 3)


def holm(ps):
    order = sorted(range(len(ps)), key=lambda i: ps[i])
    adj = [0] * len(ps)
    run = 0
    for rank, i in enumerate(order):
        run = max(run, min(1.0, ps[i] * (len(ps) - rank)))
        adj[i] = run
    return adj


def factorial(recs, key):
    """主効果（eval・審査）と交互作用。題材ごとの層の中で因子のラベルを並べ替えて p を出す。"""
    rows = [(r["topic"], *FACT[r["cond"]], r[key]) for r in recs if r[key] is not None]
    def stats(rs):
        m = {}
        for e in (0, 1):
            for j in (0, 1):
                v = [y for _, ee, jj, y in rs if ee == e and jj == j]
                m[(e, j)] = st.mean(v)
        eff_e = (m[(1, 0)] + m[(1, 1)]) / 2 - (m[(0, 0)] + m[(0, 1)]) / 2
        eff_j = (m[(0, 1)] + m[(1, 1)]) / 2 - (m[(0, 0)] + m[(1, 0)]) / 2
        inter = (m[(1, 1)] - m[(0, 1)]) - (m[(1, 0)] - m[(0, 0)])
        return eff_e, eff_j, inter
    obs = stats(rows)
    def permuted(which):
        # which=0: eval を (題材, 審査) の層の中で並べ替え / 1: 審査を (題材, eval) の層で / 2: 条件を題材の層で
        groups = {}
        for i, (t, e, j, y) in enumerate(rows):
            g = (t, j) if which == 0 else (t, e) if which == 1 else t
            groups.setdefault(g, []).append(i)
        out = list(rows)
        for idx in groups.values():
            if which == 2:
                labels = [(rows[i][1], rows[i][2]) for i in idx]
                R.shuffle(labels)
                for i, (e, j) in zip(idx, labels):
                    out[i] = (rows[i][0], e, j, rows[i][3])
            else:
                labels = [rows[i][1 + which] for i in idx]
                R.shuffle(labels)
                for i, lab in zip(idx, labels):
                    t, e, j, y = rows[i]
                    out[i] = (t, lab, j, y) if which == 0 else (t, e, lab, y)
        return out
    ps = []
    for w in range(3):
        cnt = 0
        n = 5000
        for _ in range(n):
            s = stats(permuted(w))
            if abs(s[w]) >= abs(obs[w]) - 1e-12:
                cnt += 1
        ps.append((cnt + 1) / (n + 1))
    return {"eval_main": round(obs[0], 4), "p_eval": round(ps[0], 4),
            "judge_main": round(obs[1], 4), "p_judge": round(ps[1], 4),
            "interaction": round(obs[2], 4), "p_interaction": round(ps[2], 4)}


def kappa(a, b):
    n = len(a)
    po = sum(1 for x, y in zip(a, b) if x == y) / n
    pa, pb = sum(a) / n, sum(b) / n
    pe = pa * pb + (1 - pa) * (1 - pb)
    return round((po - pe) / (1 - pe), 3) if pe < 1 else None


def pearson(xs, ys):
    mx, my = st.mean(xs), st.mean(ys)
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    sy = math.sqrt(sum((y - my) ** 2 for y in ys))
    return round(sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (sx * sy), 3) if sx and sy else None


def main():
    recs = load()
    by = {c: [r for r in recs if r["cond"] == c] for c in CONDS}
    S = {"n_total": len(recs), "conds": {}}
    for c in CONDS:
        rs = by[c]
        n = len(rs)
        bm = [r["blind_mean"] for r in rs if r["blind_mean"] is not None]
        S["conds"][c] = {
            "n": n,
            "eval1_pass": sum(r["y_eval1"] for r in rs), "eval1_ci": wilson(sum(r["y_eval1"] for r in rs), n),
            "eval_pass": sum(r["y_eval"] for r in rs), "eval_ci": wilson(sum(r["y_eval"] for r in rs), n),
            "eval_items_mean": round(st.mean(r["final_eval"]["passed"] for r in rs), 3),
            "blind_mean": round(st.mean(bm), 4), "blind_sd": round(st.pstdev(bm), 4), "blind_ci": boot_ci_mean(bm),
            "blind_pass": sum(1 for x in bm if x >= 0.8),
            "blind_items": {k: round(st.mean(r["blind_items"][k] for r in rs if r["blind_items"]), 3) for k in ITEMS},
            "writes_mean": round(st.mean(r["writes"] for r in rs), 3),
            "writes_dist": {k: sum(1 for r in rs if r["writes"] == k) for k in (1, 2, 3)},
            "calls_judge": sum(r["calls_judge"] for r in rs),
            "cost_mean": round(st.mean(r["cost"] for r in rs), 5),
            "by_topic": {t: {"n": sum(1 for r in rs if r["topic"] == t),
                             "eval_pass": sum(r["y_eval"] for r in rs if r["topic"] == t),
                             "blind_mean": round(st.mean([r["blind_mean"] for r in rs if r["topic"] == t] or [0]), 3)} for t in TOPICS},
        }
    # 2条件ずつの比較
    pairs = list(combinations(CONDS, 2))
    pe, pb = [], []
    rows = []
    for a, b in pairs:
        xa, xb = by[a], by[b]
        sa, sb = sum(r["y_eval"] for r in xa), sum(r["y_eval"] for r in xb)
        p1 = fisher_two_sided(sa, len(xa) - sa, sb, len(xb) - sb)
        ya = [r["blind_mean"] for r in xa]
        yb = [r["blind_mean"] for r in xb]
        p2 = perm_diff(ya, yb)
        pe.append(p1)
        pb.append(p2)
        rows.append({"pair": f"{a} vs {b}", "eval_rate_diff": round(sa / len(xa) - sb / len(xb), 3), "p_eval": p1,
                     "blind_diff": round(st.mean(ya) - st.mean(yb), 4), "blind_diff_ci": boot_ci_diff(ya, yb),
                     "cliffs_delta": cliffs_delta(ya, yb), "p_blind": p2})
    for row, h1, h2 in zip(rows, holm(pe), holm(pb)):
        row["p_eval_holm"] = round(h1, 5)
        row["p_blind_holm"] = round(h2, 5)
        row["p_eval"] = round(row["p_eval"], 5)
        row["p_blind"] = round(row["p_blind"], 5)
    S["pairs"] = rows
    S["factorial_eval_pass"] = factorial(recs, "y_eval")
    S["factorial_blind"] = factorial(recs, "blind_mean")
    S["factorial_eval1"] = factorial(recs, "y_eval1")  # 1回目は条件で差が無いはず（割り付けの確かめ）
    # 審査役の一致度（伏せた審査の1回目と2回目）
    pairs_b = [(r["blind"][0], r["blind"][1]) for r in recs if all("overall" in x for x in r["blind"])]
    o1 = [x["overall"] for x, _ in pairs_b]
    o2 = [y["overall"] for _, y in pairs_b]
    S["judge_reliability"] = {
        "n": len(pairs_b), "pearson_overall": pearson(o1, o2),
        "mean_abs_diff": round(st.mean(abs(a - b) for a, b in zip(o1, o2)), 4),
        "same_overall": sum(1 for a, b in zip(o1, o2) if abs(a - b) < 1e-9),
        "pass_agree": sum(1 for a, b in zip(o1, o2) if (a >= .8) == (b >= .8)),
        "pass_kappa": kappa([a >= .8 for a in o1], [b >= .8 for b in o2]),
        "item_exact": {k: sum(1 for x, y in pairs_b if x["scores"][k] == y["scores"][k]) for k in ITEMS},
        "off_scale_runs": sum(1 for r in recs for x in r["blind"] if x.get("off_scale")),
        "parse_errors": sum(1 for r in recs for x in r["blind"] if "error" in x),
    }
    # 審査役は決まりの違反に気づくか（伏せた審査の指示の順守と eval の比較。全最終版×2回）
    tab = {"eval_ng_if1": 0, "eval_ng_iflt1": 0, "eval_ok_if1": 0, "eval_ok_iflt1": 0,
           "eval_ng_pass": 0, "eval_ng_n": 0}
    for r in recs:
        for x in r["blind"]:
            if "scores" not in x:
                continue
            ok = r["final_eval"]["all_ok"]
            full = x["scores"]["instruction_following"] == 1.0
            tab[("eval_ok_" if ok else "eval_ng_") + ("if1" if full else "iflt1")] += 1
            if not ok:
                tab["eval_ng_n"] += 1
                tab["eval_ng_pass"] += 1 if x["overall"] >= .8 else 0
    S["judge_vs_eval"] = tab
    # ループ内の審査（最終回）と伏せた審査の平均の一致
    lp = [(r["rounds"][-1]["judge"]["overall"], r["blind_mean"]) for r in recs
          if r["cond"] in "CD" and "overall" in r["rounds"][-1].get("judge", {})]
    S["loop_vs_blind"] = {"n": len(lp), "pearson": pearson([a for a, _ in lp], [b for _, b in lp]),
                          "loop_mean": round(st.mean(a for a, _ in lp), 4), "blind_mean": round(st.mean(b for _, b in lp), 4),
                          "pass_agree": sum(1 for a, b in lp if (a >= .8) == (b >= .8))}
    # 書き直しの中身：返した結果のあとで eval の合否がどう変わったか
    trans = {c: {"ng_to_ok": 0, "ng_to_ng": 0, "ok_to_ng": 0, "ok_to_ok": 0} for c in "BCD"}
    for r in recs:
        if r["cond"] == "A":
            continue
        for x, y in zip(r["rounds"], r["rounds"][1:]):
            k = ("ok" if x["eval"]["all_ok"] else "ng") + "_to_" + ("ok" if y["eval"]["all_ok"] else "ng")
            trans[r["cond"]][k] += 1
    S["eval_transitions"] = trans
    # 1回目に落ちた項目
    fails = {}
    for r in recs:
        for ch in r["rounds"][0]["eval"]["checks"]:
            if not ch["ok"]:
                k = re.sub(r"「[^」]+」を含む", "必須語を含む", ch["check"])
                k = re.sub(r"英字は .*", "英字の決まり", k)
                k = re.sub(r"数字は「.」.*", "数字の決まり", k)
                fails[k] = fails.get(k, 0) + 1
    S["round1_fail_items"] = dict(sorted(fails.items(), key=lambda kv: -kv[1]))
    # 審査の指摘に、英字の決まりに反する語（許されていない英字）が入っている割合
    bad_adv = 0
    adv_n = 0
    for r in recs:
        allowed = TOPICS[r["topic"]]["english"]
        for x in r["rounds"]:
            fb = (x.get("judge") or {}).get("feedback")
            if not fb:
                continue
            adv_n += 1
            txt = " ".join(fb)
            for w in allowed:
                txt = txt.replace(w, "")
            if re.search(r"(Claude|SDK|Python|CLI|Agent|Web|App)", txt):
                bad_adv += 1
    S["judge_advice_with_banned_english"] = {"rounds": adv_n, "with_banned_word": bad_adv}
    S["cost_total"] = round(sum(r["cost"] for r in recs) + sum((x.get("meta") or {}).get("cost") or 0 for r in recs for x in r["blind"]), 3)
    json.dump(S, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps(S, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
