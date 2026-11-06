# -*- coding: utf-8 -*-
"""AI 决策：定价枚举、开线/关线、枢纽扩张、经停延伸。

由 sim/simulate.py 拆分而来；只允许依赖更靠前的分层，不要反向 import。
"""

import math
from config import ECON, FLIGHT, STOP
from market import cabin_demand
from model import Route
from products import cabin_split_for
from util import clamp, runway_allows


# ============================================================
# AI 决策
# ============================================================

def route_variable_cost_per_pax(world, r):
    """航线的单位旅客变动成本（燃油/起降/导航/维护/地面）"""
    d = r.total_km()
    if d <= 0:
        return 0.0
    t = world.ac(r.ac_type)
    f = 2 * r.daily_flights
    fuel = f * t["seats"] * t["fuel"] * d / 100.0 * ECON["fuel_price_per_kg"] / 1e6
    landing = f * r.n_segments * ECON["landing_base_M"] * (t["mtow"] / 70.0) ** 0.7
    nav = f * r.n_segments * (d / max(1, r.n_segments)) * ECON["nav_rate_M_per_km"] * (t["mtow"] / 70.0)
    maint = f * (d / t["speed"]) * t["maint"] * ECON["maint_load_factor"]
    ground = 0.0
    pax = max(1.0, r.lf_ewma * f * t["seats"] * r.op_factor())
    return (fuel + landing + nav + maint) / pax + ECON["ground_per_pax_M"]


def best_fare_multiplier(world, al, r, params):
    """在「降价填满」与「涨价降载客」之间比较利润，返回最优涨价倍数

    用 logit 的单选项替换恒等式估计需求响应：
        某选项效用变化 Δ 后，份额 s' = s·e^Δ / (1 − s + s·e^Δ)
        其中 Δ = −c_price · ln(价格倍数)
    然后比较 (价格 − 单位变动成本) × 客流，取利润最大者。
    """
    d = r.total_km()
    if d <= 0:
        return 1.0
    t = world.ac(r.ac_type)
    ca = world.airports[r.segments[0]]["city"]
    cb = world.airports[r.segments[-1]]["city"]
    D = cabin_demand(world, ca, cb, "eco")
    seats = 2 * r.daily_flights * t["seats"] * sum(cabin_split_for(t).values()) * r.op_factor()
    if D <= 0 or seats <= 0:
        return 1.0
    pax_now = clamp(r.lf_ewma * seats, 1.0, seats)
    s = clamp(pax_now / D, 0.01, 0.99)

    price_now = world.p_ref(d, "eco") * r.price_index     # 元/人（经济舱）
    vc = route_variable_cost_per_pax(world, r)      # ¥M/人

    c_price = params["utility"]["c_price"]
    best_m, best_profit = 1.0, None
    for m in (0.90, 1.00, 1.05, 1.10, 1.15, 1.20, 1.30, 1.40):
        delta = -c_price * math.log(m)
        e = math.exp(delta)
        s2 = s * e / (1.0 - s + s * e)
        pax2 = min(D * s2, seats)
        # 座位利用率越高，单位固定成本摊得越薄，用简单加成来体现
        profit = (price_now * m / 1e6 - vc) * pax2
        if best_profit is None or profit > best_profit:
            best_m, best_profit = m, profit
    return best_m


def validate_stopover(world, segments, ac_type, daily_flights=1):
    """校验一条经停航线是否满足 §5.2（R-531~R-541）

    返回 (ok, reason)。reason 用于调试与报告。
    """
    if not (2 <= len(segments) - 1 <= 3):
        return False, "航段数必须为 2–3"
    if len(set(segments)) != len(segments):
        return False, "经停点重复"
    cities = [world.airports[s]["city"] for s in segments]
    if len(set(cities)) != len(cities):
        return False, "同城机场不能互相经停"

    t = world.ac(ac_type)
    if max(world.airports[s]["pax"] for s in segments) <= 0:
        return False, "机场无效"
    for s in segments:
        if not runway_allows(world.airports[s], t["class"]):
            return False, f"{s} 跑道等级不满足 {ac_type}"

    total = sum(world.airport_dist(segments[i], segments[i + 1]) for i in range(len(segments) - 1))
    if total < STOP["min_total_km"]:
        return False, f"总航程 {total:.0f} < {STOP['min_total_km']:.0f} km"
    for i in range(len(segments) - 1):
        d = world.airport_dist(segments[i], segments[i + 1])
        if d < STOP["min_segment_km"]:
            return False, f"单段 {d:.0f} < {STOP['min_segment_km']:.0f} km"
        if d > t["range"] * 1.05:
            return False, f"单段 {d:.0f} 超出机型航程"
    direct = world.airport_dist(segments[0], segments[-1])
    if direct > 0 and total / direct > STOP["max_detour"]:
        return False, f"绕行系数 {total / direct:.2f} > {STOP['max_detour']:.2f}"
    if total > t["range"] * STOP["max_range_factor"]:
        return False, f"总航程超出 {STOP['max_range_factor']}× 航程"

    # F-08：必须同时满足机队周转上限，避免「开得出但飞不了」
    hrs = 0.0
    turn = FLIGHT["turnaround_min"][t["class"]] / 60.0
    for i in range(len(segments) - 1):
        hrs += world.airport_dist(segments[i], segments[i + 1]) / t["speed"] + turn
        if 0 < i < len(segments) - 2:
            hrs += FLIGHT["stopover_extra_min"] / 60.0
    if 2 * hrs * daily_flights > FLIGHT["max_hours_per_day"]:
        return False, f"往返占机 {2 * hrs:.1f}h 超出 16h 上限"
    if 2 * (len(segments) - 1) * daily_flights > FLIGHT["max_segments_per_day"]:
        return False, "单机航段数超出 8 段"
    return True, "ok"





def usable_slots(world, airline, code):
    """FR-502-1：HUB 机场保留 30% 容量，非 HUB 公司只能用 70%。"""
    cap = world.airports[code]["slot_cap"]
    if code in world.hub_airports and code not in airline.hubs:
        return cap * 0.70
    return cap


def try_add_stopover(world, al, params):
    """尝试给一条直飞航线加挂一个经停点（F-09：受限枚举，不做组合搜索）

    v1.0 明确：AI 只生成 2 段（1 个经停点）航线，不生成 3 段。
    见 STOP["ai_max_segments"]。
    """
    max_segs = STOP["ai_max_segments"]
    for r in sorted(al.routes, key=lambda x: x.n_segments):
        if r.n_segments >= max_segs:
            continue
        a, b = r.segments
        base_hours = al.route_hours(r)
        cands = []
        for code, ap in world.airports.items():
            if code in r.segments:
                continue
            if ap["city"] in (world.airports[a]["city"], world.airports[b]["city"]):
                continue
            d = world.airport_dist(b, code)
            if not (STOP["min_segment_km"] <= d <= 1500):
                continue
            segs = [a, b, code]
            ok, _ = validate_stopover(world, segs, r.ac_type, r.daily_flights)
            if not ok:
                continue
            _, air = world.demand_air(world.airports[b]["city"], ap["city"])
            if air < 120:
                continue
            cands.append((air, code))
        cands.sort(reverse=True)
        for _, code in cands[:3]:
            segs = [a, b, code]
            newr = Route(al, segs, r.daily_flights, r.ac_type, r.price_index)
            # 换线前后按机型分池核对运力（旧线换掉、新线加进来）
            al.routes.remove(r)
            fits = al.fits_route(newr)
            if not fits:
                al.routes.append(r)
                continue
            # 换掉旧航线
            for s in set(r.segments):
                world.routes_at[s] = max(0, world.routes_at.get(s, 0) - 1)
            al.routes.append(newr)
            for s in set(segs):
                world.routes_at[s] = world.routes_at.get(s, 0) + 1
            world.invalidate_demand()
            return True
    return False


def ai_decide(world, al, rng, params):
    if not al.alive:
        return
    # 1. 关停长期低载客率航线（保留最后一条，否则会变成无收入的僵尸航司）
    for r in list(al.routes):
        if len(al.routes) <= 1:
            break
        if r.lf_ewma < 0.40:
            r.low_lf_months += 1
            if r.low_lf_months >= 2:
                al.close_route(r)
    # 1b. 连续亏损 60 天 → 强制收缩：先砍最差航线，再卖一架飞机
    if al.neg_days >= 60 and not al.is_player:
        if len(al.routes) > 1:
            worst = min(al.routes, key=lambda r: r.lf_ewma)
            al.close_route(worst)
        if len(al.fleet) > 1:
            oldest = max(al.fleet, key=lambda a: a.age)
            al.sell_aircraft(oldest)
        al.neg_days = 0
        al.contractions += 1
    # 2. 票价：比较「降价填满」与「涨价降载客」两种策略的利润，取更优者
    #    票价 = 参考价(OD 直线距离) × 价格指数；指数即策略变量
    for r in al.routes:
        d = r.total_km()
        if d <= 0:
            continue
        m = best_fare_multiplier(world, al, r, params)
        target = clamp(r.price_base * m, 0.50, 1.50)
        # 平滑移动，避免需求估计噪声导致票价来回抖动
        r.price_index = clamp(r.price_index * 0.4 + target * 0.6, 0.50, 1.50)
    # 3. 高载客率航线加班次（现实中航司主要靠加密而非不断开新航线）
    for r in al.routes:
        if r.lf_ewma > 0.85 and r.daily_flights < 14:
            saved = r.daily_flights
            r.daily_flights += 1
            key = (r.ac_type, r.segments[0])
            hours, segs = al.usage_by_base()
            cap_h, cap_s = al.base_capacity(*key)
            over = (hours.get(key, 0.0) > cap_h + 1e-9
                    or segs.get(key, 0) > cap_s + 1e-9)
            if over:
                if not (al.cash >= world.ac(r.ac_type)["price"] * 1.6 and al.buy_aircraft(r.ac_type)):
                    r.daily_flights = saved
    # 4. 扩张（连续亏损中不扩张；但完全没有航线时必须自救）
    if not al.routes:
        al.neg_days = 0
    if al.cash < 120 or al.neg_days >= 30:
        return
    cands = []
    for ca in world.city_list:
        for cb in world.city_list:
            if ca >= cb:
                continue
            ta, tb = world.cities[ca]["scale"], world.cities[cb]["scale"]
            if ta in ("R",) and tb in ("R",):
                continue
            d = world.dist(ca, cb)
            if d < 300 or d > 6000:
                continue
            _, air = world.demand_air(ca, cb)
            if air < 150:
                continue
            served = any(r for r in al.routes
                         if ca in [world.airports[s]["city"] for s in r.segments]
                         and cb in [world.airports[s]["city"] for s in r.segments])
            if served:
                continue
            # 网络延伸约束：只能从自有 HUB 或已服务城市延伸（航司不会凭空到处开线）
            touched = {world.airports[h]["city"] for h in al.hubs}
            for r in al.routes:
                for code in r.segments:
                    touched.add(world.airports[code]["city"])
            if ca not in touched and cb not in touched:
                continue
            hub_bonus = 2.5 if any(h in world.cities[ca]["airports"] or
                                   h in world.cities[cb]["airports"] for h in al.hubs) else 1.0
            cands.append((air * hub_bonus * rng.uniform(0.85, 1.15), ca, cb, d))
    cands.sort(reverse=True)
    opened = 0
    for air, ca, cb, d in cands:
        if opened >= 2:
            break
        bases = {(a.base or "") for a in al.fleet}
        a1 = next((ap for ap in world.cities[ca]["airports"] if ap in bases),
                  world.cities[ca]["airports"][0])
        a2 = next((ap for ap in world.cities[cb]["airports"] if ap in bases),
                  world.cities[cb]["airports"][0])
        # FR-502-1：HUB 机场保留 30% 容量，非 HUB 公司只能用 70%
        if world.slots_used[a1] + 2 > usable_slots(world, al, a1):
            continue
        if world.slots_used[a2] + 2 > usable_slots(world, al, a2):
            continue
        code = "A320" if d <= 3200 else ("A321" if d <= 5200 else "A333")
        t = world.ac(code)
        if d > t["range"] * 0.95:
            continue
        # 跑道等级不允许（宽体只能落 W 级机场）就降级到窄体，否则放弃
        if not (runway_allows(world.airports[a1], t["class"])
                and runway_allows(world.airports[a2], t["class"])):
            if (d <= world.ac("A320")["range"] * 0.95
                    and runway_allows(world.airports[a1], "窄体")
                    and runway_allows(world.airports[a2], "窄体")):
                code, t = "A320", world.ac("A320")
            else:
                continue
        r = Route(al, [a1, a2], 1, code, 0.97)
        # 运力按机型分池：不够就先买同型机（最多补 2 架）
        for _ in range(2):
            if al.fits_route(r):
                break
            price = world.ac(code)["price"]
            shortfall = price - al.cash
            if shortfall > 0:
                # 允许部分债务融资：这是「过度扩张 → 破产」的真实来源
                room = al.borrow_capacity()
                if room < shortfall * 0.5:
                    break
                loan = min(shortfall, room)
                al.debt += loan
                al.cash += loan
            if not al.buy_aircraft(code, base=a1):
                break
        if not al.fits_route(r):
            continue
        al.routes.append(r)
        world.routes_at[a1] += 1
        world.routes_at[a2] += 1
        world.slots_used[a1] += 2 * r.daily_flights
        world.slots_used[a2] += 2 * r.daily_flights
        opened += 1
    world.invalidate_demand()

    # 5. 经停：有闲置运力时，尝试把一条直飞航线延伸为「A→B→C」
    if al.total_hours() < al.capacity_hours() * 0.85 and rng.random() < 0.5:
        try_add_stopover(world, al, params)

    # 6. 新增 HUB：在某机场已有 2+ 航线、3+ 基地飞机时可以考虑（FR-501）
    if len(al.hubs) < 3:
        seen = set()
        for r in al.routes:
            for code in r.segments:
                if code in seen or code in al.hubs:
                    continue
                seen.add(code)
                ok, fee = al.can_add_hub(code)
                if ok:
                    al.add_hub(code, fee)
                    break



