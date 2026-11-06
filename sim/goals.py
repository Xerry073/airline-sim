# -*- coding: utf-8 -*-
"""目标模式：四目标判定、区域份额、月报质量、A–E 评级。

由 sim/simulate.py 拆分而来；只允许依赖更靠前的分层，不要反向 import。
"""

from collections import defaultdict
from config import GOAL_DEFS, GOAL_MONTHS, GOAL_RATINGS


def blank_goal_state():
    """目标模式的逐日追踪状态；可安全序列化。"""
    return {
        "market_top3": {"achieved": False, "day": None, "best_rank": None},
        "region_leader": {"achieved": False, "day": None,
                          "best_share": 0.0, "region": None},
        "high_quality": {"achieved": False, "day": None, "streak": 0,
                         "best_streak": 0, "last_month_day": None},
        "network_expansion": {"achieved": False, "day": None,
                              "best_segments": 0, "best_lf": 0.0},
    }


def weighted_load_factor(airline):
    """按最近结算日客流加权的平均客座率；无客流时退化为航线简单平均。"""
    routes = airline.routes
    if not routes:
        return 0.0
    weights = [max(0.0, float(getattr(r, "last_pax", 0.0) or 0.0)) for r in routes]
    total = sum(weights)
    if total > 0:
        return sum(r.lf_ewma * w for r, w in zip(routes, weights)) / total
    return 0.0


def month_quality_ok(month):
    """FR-1102 高质高效的单月判定：EBITDA 率 ≥15% 且准点率 ≥85%。"""
    revenue = float(month.get("revenue") or 0.0)
    ebitda = float(month.get("ebitda") or 0.0)
    rate = (ebitda / revenue) if revenue > 0 else -1.0
    on_time = float(month.get("on_time") or 0.0)
    return rate >= 0.15 and on_time >= 0.85, rate, on_time


def region_market_share(world, airlines, player):
    """按航线日客流在「航段端点所在区域」间均摊，返回 (最大份额, 区域, 各区份额)。

    这是一个可解释的近似：一条跨区航线（如 PEK–LAX）的客流按端点数量
    50/50 分到中国/美洲；同区航线全部计入该区。
    """
    mine = defaultdict(float)
    total = defaultdict(float)
    for al in airlines:
        if not al.alive:
            continue
        for r in al.routes:
            pax = max(0.0, float(getattr(r, "last_pax", 0.0) or 0.0))
            if pax <= 0:
                continue
            counts = defaultdict(int)
            for code in r.segments:
                counts[world.airports[code]["region"]] += 1
            n = sum(counts.values())
            if n <= 0:
                continue
            for reg, c in counts.items():
                value = pax * c / n
                total[reg] += value
                if al is player:
                    mine[reg] += value
    shares = {reg: mine[reg] / v for reg, v in total.items() if v > 0}
    if not shares:
        return 0.0, None, shares
    region, share = max(shares.items(), key=lambda kv: kv[1])
    return share, region, shares


def evaluate_goals(world, airlines, days):
    """批量报告的终局快照判定（无逐日追踪；交互对局见 Game._update_goals）。"""
    alive = [a for a in airlines if a.alive]
    if not alive:
        return [], "E"
    ranked = sorted(alive, key=lambda a: -a.rank_score)
    player = next((a for a in alive if a.is_player), ranked[0])

    rank = ranked.index(player) + 1 if player in ranked else None
    best_share, _, _ = region_market_share(world, alive, player)
    months = player.monthly[-GOAL_MONTHS:]
    high_ok = len(months) >= GOAL_MONTHS and all(month_quality_ok(m)[0] for m in months)
    network_ok = (player.total_segments() >= 100
                  and weighted_load_factor(player) >= 0.75)

    by_id = {
        "market_top3": bool(rank and rank <= 3),
        "region_leader": best_share >= 0.35,
        "high_quality": high_ok,
        "network_expansion": network_ok,
    }
    goals = [(name, by_id[gid]) for gid, name, _ in GOAL_DEFS]
    met = sum(1 for _, ok in goals if ok)
    return goals, GOAL_RATINGS[met]



