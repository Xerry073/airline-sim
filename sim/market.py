# -*- coding: utf-8 -*-
"""需求分配：能级池 → 分舱 → logit → 段容量 yield 截断。

由 sim/simulate.py 拆分而来；只允许依赖更靠前的分层，不要反向 import。
"""

import math
from collections import defaultdict
from config import ECON
from products import build_products, cabin_split_for
from util import clamp


# ============================================================
# 需求分配（logit + 段容量）
# ============================================================

def cabin_demand(world, ca, cb, cabin):
    _, air = world.demand_air(ca, cb)
    d = world.dist(ca, cb)
    ta = max(world.airports[i]["tier"] for i in world.cities[ca]["airports"])
    tb = max(world.airports[i]["tier"] for i in world.cities[cb]["airports"])
    b = clamp(0.04 + 0.010 * (ta + tb) + 0.00004 * d, 0.04, 0.30)
    f = 0.02 if (ta + tb >= 7 and d >= 4000) else 0.0
    if cabin == "eco":
        return air * (1 - b - f)
    if cabin == "biz":
        return air * b
    return air * f


def allocate(world, airlines, params):
    """返回 (alloc, route_pax)

    alloc[(airline_name, cabin)] = {"pax": float, "revenue": float}
    route_pax[route_id][cabin] = 实际承运客流（已过段容量）
    """
    prods = build_products(world, airlines)
    U = params["utility"]
    alloc = defaultdict(lambda: {"pax": 0.0, "revenue": 0.0})
    route_pax = defaultdict(lambda: defaultdict(float))

    # 航线级收入：每个产品的收入按所占用航段的距离比例拆到航线上。
    # 只用于看板展示，不参与结算；直飞航线即 100% 归该航线。
    for al in airlines:
        for r in al.routes:
            r.last_revenue = 0.0

    # 第一步：分舱位 logit，得到每个产品的无约束需求
    demand_of = {}          # id(product) -> 需求
    product_of = {}         # id(product) -> product

    for (ca, cb), cabins in prods.items():
        d = world.dist(ca, cb)
        for cabin, items in cabins.items():
            D = cabin_demand(world, ca, cb, cabin)
            if D <= 0 or not items:
                continue
            pref = world.p_ref(d, cabin)
            tot = 0.0
            us = []
            for it in items:
                # FR-307：单日座位 < 30 座不进入分母（阻断「1 座占位」份额抑制）
                if it["seats"] < 30:
                    continue
                u = (world.c0(d)
                     - U["c_price"] * math.log(max(it["price"], 1e-6) / pref)
                     + U["c_time"] * (-it["time_h"] / 10.0)
                     + U["c_freq"] * it["freq"]
                     + world.c_rep(d) * (it["rep"] - 50.0) / 50.0
                     + U["c_hub"] * it["hub"]
                     - U["c_stop"] * it["stops"]
                     - U["c_trans"] * it["transfers"])
                us.append((it, u))
                tot += math.exp(u)
            denom = 1.0 + tot
            for it, u in us:
                dem = D * math.exp(u) / denom
                if dem > 0:
                    demand_of[id(it)] = min(dem, it["seats"])
                    product_of[id(it)] = it

    # 第二步：统一段容量分配（R-609 / R-610）
    # 关键：容量池按「航线 × 航段 × 舱位」建立，所有压在该航段上的产品
    # （直达 / 经停 / 中转）共享同一池，从而修掉两个漏洞：
    #   - 经停航线多个 OD 各自声称拥有整架飞机（座位重复出售）
    #   - 中转产品 route=None 被跳过、绕过全部容量约束
    remaining = {}
    for pid, it in product_of.items():
        for (r, k) in it["legs"]:
            key = (id(r), it["cabin"])
            if key not in remaining:
                t = world.ac(r.ac_type)
                cap = r.daily_flights * t["seats"] * cabin_split_for(t).get(it["cabin"], 0.0) * r.op_factor()
                remaining[key] = [cap] * r.n_segments

    by_cabin = defaultdict(list)
    for pid, it in product_of.items():
        by_cabin[it["cabin"]].append(it)

    for cabin, items in by_cabin.items():
        # yield = 票价 / 占用航段数，不足时优先保留高收益行程
        items.sort(key=lambda it: it["price"] / max(1, len(it["legs"])), reverse=True)
        for it in items:
            dem = demand_of.get(id(it), 0.0)
            if dem <= 0 or not it["legs"]:
                continue
            room = min(remaining[(id(r), cabin)][k] for (r, k) in it["legs"])
            take = min(dem, max(0.0, room))
            for (r, k) in it["legs"]:
                remaining[(id(r), cabin)][k] -= take
            if take < dem:
                demand_of[id(it)] = take

    # 第三步：汇总收入（客流按「航段」计，便于多段航线算载客率）
    for pid, it in product_of.items():
        dem = demand_of.get(pid, 0.0)
        if dem <= 0:
            continue
        al = it["airline"]
        cabin = it.get("cabin", "eco")
        alloc[(al.name, cabin)]["pax"] += dem
        alloc[(al.name, cabin)]["revenue"] += dem * it["price"]
        legs = it["legs"]
        leg_km = []
        for (r, k) in legs:
            leg_km.append(world.airport_dist(r.segments[k], r.segments[k + 1]))
        total_leg_km = sum(leg_km)
        for idx, (r, k) in enumerate(legs):
            route_pax[id(r)][cabin] += dem
            share = leg_km[idx] / total_leg_km if total_leg_km > 0 else 1.0 / max(1, len(legs))
            r.last_revenue += dem * it["price"] * share / 1e6

    return alloc, route_pax


def route_direct_cost(world, al, r, revenue, pax):
    """航线可归集成本（¥M/日）

    含燃油、起降、导航、维护、地面、分销、航段人员；
    不含飞机折旧/租赁、总部固定人员、枢纽固定费与利息。
    用于航线看板的「可归集利润率」，不是公司总利润。
    """
    t = world.ac(r.ac_type)
    flown = r.total_km()
    op = r.op_factor()

    fuel = (2 * r.daily_flights * t["seats"] * t["fuel"] * flown / 100.0) \
        * ECON["fuel_price_per_kg"] / 1e6 * op
    landing = nav = 0.0
    for i in range(r.n_segments):
        disc = 0.90 if r.segments[i] in al.hubs else 1.0
        landing += 2 * r.daily_flights * ECON["landing_base_M"] * (t["mtow"] / 70.0) ** 0.7 * op * disc
        nav += 2 * r.daily_flights * world.airport_dist(r.segments[i], r.segments[i + 1]) * \
            ECON["nav_rate_M_per_km"] * (t["mtow"] / 70.0) * op
    flight_h_day = 2 * r.daily_flights * (flown / t["speed"])
    hub_disc = 0.92 if any(s in al.hubs for s in r.segments) else 1.0
    maint = flight_h_day * t["maint"] * ECON["maint_load_factor"] * op * hub_disc
    if al.fleet:
        avg_age = sum(a.age for a in al.fleet) / len(al.fleet)
        maint *= (1 + 0.04 * avg_age)

    segments = 2 * r.n_segments * r.daily_flights * op
    staff_seg = ECON["staff_per_segment_M_day"] * segments
    distribution = revenue * ECON["distribution_pct"]
    ground = pax * ECON["ground_per_pax_M"]
    return fuel + landing + nav + maint + staff_seg + distribution + ground




