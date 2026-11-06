# -*- coding: utf-8 -*-
"""日结算：收入与九项成本、贷款利息、破产、市值。

由 sim/simulate.py 拆分而来；只允许依赖更靠前的分层，不要反向 import。
"""

from config import ECON
from market import allocate, route_direct_cost
from products import cabin_split_for


# ============================================================
# 日结算
# ============================================================

def settle_day(world, airlines, params, day=0):
    # 先刷新航线运营指标（准点、取消率、口碑目标），因为产品座位与口碑都依赖它
    for al in airlines:
        if al.alive:
            al.update_route_stats()
    alloc, route_pax = allocate(world, airlines, params)

    for al in airlines:
        if not al.alive:
            continue
        t_pax = 0.0
        revenue = 0.0
        for cab in ("eco", "biz", "fst"):
            k = (al.name, cab)
            t_pax += alloc[k]["pax"]
            revenue += alloc[k]["revenue"]
        revenue /= 1e6          # 票价以人民币元计，收入换算为 ¥M

        fuel = landing = nav = maint = dep = lease = 0.0
        segments = 0
        op_routes = getattr(al, "active_routes", al.routes)
        for r in op_routes:
            t = world.ac(r.ac_type)
            flown = 0
            for i in range(r.n_segments):
                flown += world.airport_dist(r.segments[i], r.segments[i + 1])
            op = r.op_factor()
            # 燃油：往返 × 班次（此前漏了往返系数，成本被低估一半）
            fuel += (2 * r.daily_flights * t["seats"] * t["fuel"] * flown / 100.0) \
                * ECON["fuel_price_per_kg"] / 1e6 * op
            for i in range(r.n_segments):
                # FR-502-3：HUB 机场地面服务费 ×0.90
                disc = 0.90 if r.segments[i] in al.hubs else 1.0
                landing += 2 * r.daily_flights * ECON["landing_base_M"] * (t["mtow"] / 70.0) ** 0.7 * op * disc
                nav += 2 * r.daily_flights * world.airport_dist(r.segments[i], r.segments[i + 1]) * \
                    ECON["nav_rate_M_per_km"] * (t["mtow"] / 70.0) * op
            # 维护按「每日总飞行小时」计：单程飞行小时 × 2（往返）× 班次
            flight_h_day = 2 * r.daily_flights * (flown / t["speed"])
            # FR-502-3：以 HUB 为基地的飞机维护成本 ×0.92（用「航线至少一端是 HUB」近似）
            hub_disc = 0.92 if any(s in al.hubs for s in r.segments) else 1.0
            maint += flight_h_day * t["maint"] * ECON["maint_load_factor"] * op * hub_disc
            segments += 2 * r.n_segments * r.daily_flights * op

        for a in al.fleet:
            t = world.ac(a.type)
            if a.lease:
                lease += t["price"] * ECON["lease_rate_month"] / 30.0
            else:
                dep += t["price"] * (1 - ECON["residual"]) / (ECON["depreciation_years"] * 360)
        # 机龄修正（按在役飞机平均机龄放大维护成本）
        if al.fleet:
            avg_age = sum(a.age for a in al.fleet) / len(al.fleet)
            maint *= (1 + 0.04 * avg_age)

        staff = (ECON["staff_base_M_day"] + ECON["staff_per_aircraft_M_day"] * len(al.fleet)
                 + ECON["staff_per_segment_M_day"] * segments)
        distribution = revenue * ECON["distribution_pct"]
        ground = t_pax * ECON["ground_per_pax_M"]
        hub_fixed = sum(ECON["hub_fixed_by_scale"][world.airports[h]["scale"]] for h in al.hubs)
        interest = al.debt * al.interest_rate() / 360.0
        idle = ECON["idle_cost_M_day"] * max(0, len(al.fleet) - max(1, len(al.routes)))

        cost = (fuel + landing + nav + maint + dep + lease + staff + distribution + ground
                + hub_fixed + interest + idle)
        ebitda = revenue - (fuel + landing + nav + maint + lease + staff + distribution + ground
                            + hub_fixed + interest + idle)
        # 成本分项留档：供快照展示「为什么每条航线都赚、公司却亏」
        al.last_costs = {
            "fuel": fuel, "landing": landing, "nav": nav, "maint": maint,
            "depreciation": dep, "lease": lease, "staff": staff,
            "distribution": distribution, "ground": ground,
            "hub_fixed": hub_fixed, "interest": interest, "idle": idle,
            "fixed_total": staff + hub_fixed + dep + lease + interest + idle,
            "total": cost,
        }
        al.cash += revenue - cost
        al.ebitda_12m = getattr(al, "ebitda_12m", 0.0) * 0.9965 + ebitda * 0.0035
        # FR-1102 高质高效：公司级准点率按当日航线客流加权
        ot_pax = ot_sum = 0.0
        for r in op_routes:
            flow = sum(route_pax.get(id(r), {}).values())
            ot_pax += flow
            ot_sum += float(getattr(r, "on_time", 0.95)) * flow
        if ot_pax > 0:
            on_time = ot_sum / ot_pax
        elif op_routes:
            on_time = sum(float(getattr(r, "on_time", 0.95)) for r in op_routes) / len(op_routes)
        else:
            on_time = 0.0
        al.history.append({"pax": t_pax, "revenue": revenue, "cost": cost, "ebitda": ebitda,
                           "cash": al.cash, "debt": al.debt, "fleet": len(al.fleet),
                           "routes": len(al.routes), "on_time": on_time})

        # 航线载客率：客流与座位都按「航段」计，多段航线才不会超过 100%
        for r in al.routes:
            t = world.ac(r.ac_type)
            cap = (r.n_segments * r.daily_flights * t["seats"]
                   * sum(cabin_split_for(t).values()) * r.op_factor())
            pax = sum(route_pax[id(r)].values())
            if cap > 0:
                lf = pax / cap
                r.lf_ewma = 0.85 * r.lf_ewma + 0.15 * min(1.0, lf)
                # FR-404：时刻使用质量（用载客率作为「该时刻是否被有效使用」的代理）
                r.slot_low_days = r.slot_low_days + 1 if r.lf_ewma < 0.45 else 0
            # 航线看板用：最近结算日的客流与可归集损益（只读，不参与结算）
            r.last_pax = pax
            rev = getattr(r, "last_revenue", 0.0)
            r.last_cost = route_direct_cost(world, al, r, rev, pax)
            r.last_profit = rev - r.last_cost
            r.last_margin = (r.last_profit / rev) if rev > 1e-9 else None
            r.last_distance_km = r.total_km()
        # 口碑：按航线客流加权（R-617）
        al.refresh_reputation(route_pax)

        # 亏损计数与破产判定
        if ebitda < 0:
            al.neg_days += 1
        else:
            al.neg_days = max(0, al.neg_days - 2)

        if al.cash < 0 and al.borrow_capacity() <= 0:
            al.die("资金链断裂", day)
        elif al.debt > max(1.0, al.equity) * 3.0:
            al.die("资不抵债", day)
        elif al.cash < 0:
            take = min(-al.cash, al.borrow_capacity())
            al.debt += take
            al.cash += take

        al.rank_score = max(0.0, ebitda * 360 * 8 * (1 - 0.5 * al.debt / max(al.debt + max(al.equity, 1), 1))
                            + al.fleet_value() + al.cash - al.debt)
    return alloc



