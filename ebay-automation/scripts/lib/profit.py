"""利益計算・送料算出・仕入れ上限算出。

純利益(JPY) = 売価(USD) × (1 - r_fee) × E_rate - C_buy - C_ship
"""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class ProfitResult:
    sell_price_usd: float
    revenue_jpy: float          # 手数料控除後の受取額(JPY)
    gross_sales_jpy: float      # 売価 × 為替（利益率の分母）
    buy_cost_jpy: float
    ship_cost_jpy: float
    profit_jpy: float
    profit_rate: float
    passes: bool


def shipping_cost_jpy(cfg: dict, weight_kg: float | None = None,
                      dims_cm: tuple[float, float, float] | None = None) -> int:
    """実重量と容積重量の大きい方でテーブルを引く。"""
    s = cfg["shipping"]
    w = weight_kg if weight_kg else s["default_kg"]
    if dims_cm and all(dims_cm):
        vol = dims_cm[0] * dims_cm[1] * dims_cm[2] / s["volumetric_divisor"]
        w = max(w, vol)
    for row in sorted(s["table"], key=lambda r: r["max_kg"]):
        if w <= row["max_kg"]:
            return int(row["cost_jpy"])
    raise ValueError(f"重量 {w:.2f}kg が送料テーブルの上限を超えています")


def passes_criteria(cfg: dict, profit_jpy: float, profit_rate: float) -> bool:
    p = cfg["profit"]
    a = profit_jpy >= p["min_profit_jpy"]
    b = profit_rate >= p["min_profit_rate"]
    return (a and b) if p.get("criteria_mode", "or") == "and" else (a or b)


def calc_profit(cfg: dict, sell_price_usd: float, buy_cost_jpy: float,
                ship_cost_jpy: float) -> ProfitResult:
    p = cfg["profit"]
    gross = sell_price_usd * p["exchange_rate"]
    revenue = sell_price_usd * (1 - p["fee_rate"]) * p["exchange_rate"]
    profit = revenue - buy_cost_jpy - ship_cost_jpy
    rate = profit / gross if gross else 0.0
    return ProfitResult(sell_price_usd, round(revenue), round(gross), buy_cost_jpy,
                        ship_cost_jpy, round(profit), round(rate, 4),
                        passes_criteria(cfg, profit, rate))


def max_buy_price_jpy(cfg: dict, sell_price_usd: float, ship_cost_jpy: float) -> int:
    """利益基準を満たす仕入れ上限額（円）。

    "or" モード: 利益額基準・利益率基準のどちらかを満たせば良いので、緩い方（大きい方）。
    "and" モード: 両方満たす必要があるので厳しい方（小さい方）。
    """
    p = cfg["profit"]
    revenue = sell_price_usd * (1 - p["fee_rate"]) * p["exchange_rate"]
    gross = sell_price_usd * p["exchange_rate"]
    by_amount = revenue - ship_cost_jpy - p["min_profit_jpy"]
    by_rate = revenue - ship_cost_jpy - gross * p["min_profit_rate"]
    limit = min(by_amount, by_rate) if p.get("criteria_mode", "or") == "and" else max(by_amount, by_rate)
    return max(0, int(math.floor(limit / 100) * 100))  # 100円単位で切り捨て


def suggest_sell_price_usd(cfg: dict, rival_min_usd: float | None, sold_median_usd: float | None) -> float | None:
    """ライバル最安値から少し下げた価格。なければ落札中央値。"""
    if rival_min_usd:
        price = rival_min_usd * (1 - cfg["profit"].get("undercut_rate", 0))
    elif sold_median_usd:
        price = sold_median_usd
    else:
        return None
    return round(math.floor(price) - 0.01, 2) if price >= 1 else round(price, 2)
