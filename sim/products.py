# -*- coding: utf-8 -*-
"""行程产品构建：航线 → 直飞/经停/中转产品，含候选上限与去重。

由 sim/simulate.py 拆分而来；只允许依赖更靠前的分层，不要反向 import。
"""

import math
from collections import defaultdict
from config import FLIGHT


# ============================================================
# 行程产品构建
# ============================================================

CABINS = {"eco": 0.87, "biz": 0.13, "fst": 0.0}
CABIN_WIDE = {"eco": 0.76, "biz": 0.22, "fst": 0.02}


def cabin_split_for(t):
    return CABIN_WIDE if t["class"] == "宽体" else CABINS


def build_products(world, airlines):
    """返回 {(city_a, city_b): {cabin: [product, ...]}}"""
    prods = defaultdict(lambda: defaultdict(list))

    for al in airlines:
        if not al.alive:
            continue
        # 机队周转硬约束（R-509 / R-510）：超出机队能力的航线本日不执行
        used_h = 0.0
        used_s = 0
        cap_h = al.capacity_hours()
        cap_s = al.capacity_segments()
        active_routes = []
        for r in al.routes:
            h = al.route_hours(r)
            s = al.route_segments_needed(r)
            if used_h + h > cap_h or used_s + s > cap_s:
                continue
            used_h += h
            used_s += s
            active_routes.append(r)
        al.active_routes = active_routes

        for r in active_routes:
            t = world.ac(r.ac_type)
            split = cabin_split_for(t)
            n = r.n_segments
            # 每个 OD（i..j）
            for i in range(n):
                for j in range(i, n):
                    ca = world.airports[r.segments[i]]["city"]
                    cb = world.airports[r.segments[j + 1]]["city"]
                    if ca == cb:
                        continue
                    d_fly = r.od_km(i, j)              # 实际飞行里程：决定时间与成本
                    d_fare = world.dist(ca, cb)        # 两端直线距离：决定票价（F-01）
                    stops = j - i
                    fly = d_fly / t["speed"]
                    ground = stops * (FLIGHT["turnaround_min"][t["class"]] +
                                     FLIGHT["stopover_extra_min"]) / 60.0
                    time_h = fly + ground
                    freq = math.log(1 + r.daily_flights) + 0.6 * FLIGHT["peak_coverage"]
                    hub_flag = 1.0 if (r.segments[i] in al.hubs or r.segments[j + 1] in al.hubs) else 0.0
                    for cab, ratio in split.items():
                        if ratio <= 0:
                            continue
                        seats = r.daily_flights * t["seats"] * ratio * r.op_factor()
                        price = world.p_ref(d_fare, cab) * r.price_index
                        prods[(ca, cb) if ca < cb else (cb, ca)][cab].append({
                            "airline": al, "route": r, "type": "stop" if stops else "direct",
                            "seats": seats, "price": price, "time_h": time_h,
                            "freq": freq, "hub": hub_flag, "stops": stops,
                            "transfers": 0, "i": i, "j": j, "km": d_fare, "cabin": cab,
                            "rep": r.rep,
                            # 段容量占用：该产品实际压在这条航线的哪些航段上
                            "legs": [(r, k) for k in range(i, j + 1)],
                        })

        # 中转产品：本公司 HUB 换机，最多 1 次
        # 前段必须「到达 HUB」，后段必须「从 HUB 出发」
        for hub in al.hubs:
            inbound, outbound = [], []
            for r in active_routes:
                for k, code in enumerate(r.segments):
                    if code != hub:
                        continue
                    if k >= 1:                               # 可以飞到 HUB 并在此下机
                        inbound.append((r, k))
                    if k <= len(r.segments) - 2:             # 可以从 HUB 接着飞出去
                        outbound.append((r, k))
            for r1, k1 in inbound:
                for r2, k2 in outbound:
                    if r1 is r2:
                        continue
                    ap1, ap2 = r1.segments[0], r2.segments[-1]
                    if ap1 == ap2:
                        continue
                    ca = world.airports[ap1]["city"]
                    cb = world.airports[ap2]["city"]
                    if ca == cb:
                        continue
                    d1 = r1.od_km(0, k1 - 1)
                    d2 = r2.od_km(k2, r2.n_segments - 1)
                    if d1 <= 0 or d2 <= 0:
                        continue
                    d = d1 + d2
                    d_tr = world.dist(ca, cb)          # 中转票价同样按两端直线距离（F-01）
                    t1 = world.ac(r1.ac_type)
                    t2 = world.ac(r2.ac_type)
                    time_h = d1 / t1["speed"] + d2 / t2["speed"] + 1.5 + 0.75
                    s1 = cabin_split_for(t1)
                    s2 = cabin_split_for(t2)
                    idx_avg = (r1.price_index + r2.price_index) / 2.0
                    for cab in ("eco", "biz"):
                        if not s1.get(cab) or not s2.get(cab):
                            continue
                        seats = min(r1.daily_flights * t1["seats"] * s1[cab],
                                    r2.daily_flights * t2["seats"] * s2[cab])
                        if seats <= 0:
                            continue
                        price = world.p_ref(d_tr, cab) * idx_avg
                        freq = math.log(1 + min(r1.daily_flights, r2.daily_flights)) \
                            + 0.6 * FLIGHT["peak_coverage"]
                        key = (ca, cb) if ca < cb else (cb, ca)
                        prods[key][cab].append({
                            "airline": al, "route": None, "type": "transfer",
                            "seats": seats, "price": price, "time_h": time_h,
                            "freq": freq, "hub": 1.0, "stops": 0,
                            "transfers": 1, "i": 0, "j": 0, "km": d, "cabin": cab,
                            "rep": (r1.rep + r2.rep) / 2.0,
                            # 中转同样占用前段 0..k1-1 与后段 k2..n2-1 的真实座位
                            "legs": ([(r1, k) for k in range(0, k1)]
                                     + [(r2, k) for k in range(k2, r2.n_segments)]),
                        })
    # FR-308：每 OD 每公司每舱位最多 3 个候选产品，超出取「更直达、座位更多」者
    for key, cabins in prods.items():
        for cab, items in cabins.items():
            if len(items) <= 3:
                continue
            same = defaultdict(list)
            for it in items:
                same[it["airline"].name].append(it)
            keep = []
            for group in same.values():
                group.sort(key=lambda it: (it["transfers"] * 2 + it["stops"], -it["seats"]))
                keep.extend(group[:3])
            prods[key][cab] = keep
    return prods



