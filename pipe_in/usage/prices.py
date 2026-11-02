"""1ターンあたりの費用の目安の表（D0066）。流す前の費用の目安（estimate.py）が引く、たった1か所の定数。

- 精密な単価（トークン単位）ではなく、モデルの系統（haiku・sonnet・opus）ごとの「1ターンの目安」を1つずつ持つ。粗い数字なので、
  目安は少なめ・多め・実績で幅を見せる。
- 単位は units（1/10000 ドル。整数）。小数の丸めが本体と拡張で食い違わないように、整数で計算する。
- 拡張の vscode/src/domain/costEstimate.ts にも同じ表がある。2つの中身が同じことは、tests/fixtures/cost_estimate.json を
  両側のテストが読んで検査する。直すときは、この表・拡張の表・共通の表（と、その計算の期待）を一緒に直す。
- 標準ライブラリだけを使う（usage は一番下の層）。
"""

from __future__ import annotations

from typing import Any

# as_of は、この表の数字を決めた年月。180 日より古くなると、目安に「単価表が古いかもしれません」が付く。
PRICES: dict[str, Any] = {
    "as_of": "2026-10",
    "per_turn": {"haiku": 150, "sonnet": 500, "opus": 2500},
    "note": "仮の値。公式の価格表を見て手で直す（自動では更新しない）。直したら as_of も直す。",
}

FAMILIES = ("haiku", "sonnet", "opus")
DEFAULT_FAMILY = "sonnet"


def family_of(model: Any) -> tuple[str, bool]:
    """モデルの名前から系統を決める。（系統, 不明か）を返す。

    名前（小文字にしたもの）に haiku・sonnet・opus のどれかの語を含めば、その系統。
    含まない・書いていない・文字列でないときは、既定の系統（sonnet）で、不明の印を付ける。
    """
    if isinstance(model, str):
        name = model.lower()
        for family in FAMILIES:
            if family in name:
                return family, False
    return DEFAULT_FAMILY, True
