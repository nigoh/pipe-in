"""架空のライセンス（task.md の「Tidewell 共有ソース許諾書 2.1」）の規則を実装し、27 社の正解を出す。

使い方: python key.py          （このフォルダの CSV を読み、会社ID と区分を出す）
        python key.py 答え.json （答えの JSON を採点する）
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = dt.date(2026, 11, 13)  # 判断の基準日
PUBLISHED = {"3.0": dt.date(2021, 6, 1), "3.4": dt.date(2023, 2, 15), "4.0": dt.date(2024, 9, 1)}
RANK = "FNDX"  # 軽い順


def rows(name: str) -> list[list[str]]:
    with open(HERE / name, newline="", encoding="utf-8") as fh:
        return list(csv.reader(fh))[1:]


COMPANIES = {r[0]: (r[2], int(r[3]), int(r[4])) for r in rows("companies.csv")}  # 種別・売上高（百万円）・従業員
SHARES = {(r[0], r[1]): int(r[2]) for r in rows("shares.csv")}
ACTS = rows("acts.csv")
DELIVERIES = [(r[0], r[1], r[2], int(r[3])) for r in rows("deliveries.csv")]
USAGE = [(r[0], r[1], r[2], int(r[3])) for r in rows("usage.csv")]
SUITS = rows("suits.csv")
IDS = list(COMPANIES)


def controlled_by(owner: str) -> set[str]:
    """第1条3：直接の分に、過半数を持つ者が持つ分の全部を加えて、過半数になる者。"""
    found: set[str] = set()
    changed = True
    while changed:
        changed = False
        for target in IDS:
            if target == owner or target in found:
                continue
            total = SHARES.get((owner, target), 0) + sum(SHARES.get((mid, target), 0) for mid in found)
            if total > 50:
                found.add(target)
                changed = True
    return found


CONTROL = {c: controlled_by(c) for c in IDS}


def group(company: str) -> set[str]:
    """企業集団：誰にも過半数を持たれていない者と、その者が過半数を持つ者の全体。"""
    top = company
    for owner in IDS:
        if company in CONTROL[owner] and not any(owner in CONTROL[other] for other in IDS):
            top = owner
    return {top} | CONTROL[top]


def is_third_party(company: str, who: str) -> bool:
    if who == "自社":
        return False
    if who.startswith("会社:"):
        return who[3:] not in group(company)
    if who.startswith("受託者"):
        return "30日以内" not in who  # 第1条4(b)
    return True


def is_modified(act: list[str]) -> bool:
    version, kind, point, lines = act[2], act[3], act[4], act[5]
    if kind == "ソース変更":
        return True
    if kind == "プラグイン":
        listed = ["入力プラグイン API", "出力プラグイン API"] + (["認証フック"] if version == "4.0" else [])
        return int(lines) >= 10 if point in listed else int(lines) >= 1  # 第1条5(b)
    return False


def modified_deliveries(company: str) -> list[tuple[str, int]]:
    return [
        (month, count)
        for act in ACTS
        if act[1] == company and is_modified(act)
        for act_id, month, who, count in DELIVERIES
        if act_id == act[0] and is_third_party(company, who)
    ]


def is_small(company: str) -> bool:
    """第1条8と改定覚書：集団で合算。2026年3月までに改変版を初めて提供した者は、5億円未満のまま。"""
    members = group(company)
    sales = sum(COMPANIES[m][1] for m in members)
    staff = sum(COMPANIES[m][2] for m in members)
    months = [month for month, _ in modified_deliveries(company)]
    limit = 500 if months and min(months) <= "2026-03" else 300
    return sales < limit and staff <= 50


def classify(company: str) -> str:
    for plaintiff, filed, kind, withdrawn in SUITS:  # 第7条
        if kind == "訴え" and plaintiff in group(company):
            start = dt.date.fromisoformat(filed)
            if not (withdrawn and (dt.date.fromisoformat(withdrawn) - start).days <= 60):
                return "X"
    total_modified = sum(count for _, count in modified_deliveries(company))
    worst = "F"
    for act in [a for a in ACTS if a[1] == company]:
        act_id, version, mode, paid, value, how = act[0], act[2], act[6], act[7], act[8], act[9]
        result = "F"
        if mode == "提供":
            given = sum(c for a, _, who, c in DELIVERIES if a == act_id and is_third_party(company, who))
            if given > 0:
                if is_modified(act):
                    result = "N" if is_small(company) and total_modified <= 100 else "D"  # 第4条
                elif act[3] == "プラグイン" and how == "本体は渡さない":
                    result = "F"  # 本ソフトウェアも改変版も渡していない
                else:
                    result = "N"  # 第3条
        elif mode == "ネットワーク":
            monthly: dict[str, int] = {}
            kinds: set[str] = set()
            for a, month, who, count in USAGE:
                if a == act_id and is_third_party(company, who):
                    monthly[month] = monthly.get(month, 0) + count
                    kinds.add(who)
            if monthly:
                majors = ["時系列データの保存と検索", "ダッシュボードの描画"] + (["アラート通知"] if version == "4.0" else [])
                pub = PUBLISHED[version]
                change_day = dt.date(pub.year + 4, pub.month, pub.day)
                exempt = COMPANIES[company][0] in ("学校", "非営利法人") and kinds == {"構成員"}  # 別紙
                if paid == "有償" and value in majors and change_day > BASE and not exempt:
                    result = "X"  # 第6条
                elif is_modified(act) and max(monthly.values()) > 10000:
                    result = "D"  # 第5条2
        if RANK.index(result) > RANK.index(worst):
            worst = result
    return worst


def key() -> dict[str, str]:
    return {company: classify(company) for company in sorted({a[1] for a in ACTS})}


if __name__ == "__main__":
    answers = key()
    if len(sys.argv) > 1:
        given = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
        wrong = {c: (given.get(c), v) for c, v in answers.items() if str(given.get(c, "")).strip() != v}
        print(f"{len(answers) - len(wrong)}/{len(answers)}", wrong)
    else:
        print(" ".join(f"{c}:{v}" for c, v in answers.items()))
