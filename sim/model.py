# -*- coding: utf-8 -*-
"""世界与公司模型：World / Aircraft / Route / Airline。

由 sim/simulate.py 拆分而来；只允许依赖更靠前的分层，不要反向 import。
"""

import math
from collections import defaultdict
from config import CAL, ECON, FLIGHT, ROOT
from util import clamp, gc_km, read_csv, sigmoid, slot_touches


# ============================================================
# 数据加载
# ============================================================

class World:
    def __init__(self, params):
        self.params = params
        self.airports = {}
        for r in read_csv(CAL / "airports.csv"):
            pax = float(r["pax_m"])
            self.airports[r["iata"].strip()] = {
                "iata": r["iata"].strip(), "city": r["city"].strip(),
                "country": r["country"].strip(), "region": r["region"].strip(),
                "tier": int(r["tier"]), "lat": float(r["lat"]), "lon": float(r["lon"]),
                "pax": pax, "transit": float(r["transit_share"]),
                "local": pax * (1 - float(r["transit_share"])),
                "scale": self._scale_of(pax),
                "runway": r["runway"].strip(),
                "slot_cap": max(60, int(pax * 16)),
            }

        self.cities = {}
        for a in self.airports.values():
            c = self.cities.setdefault(a["city"], {
                "name": a["city"], "pax": 0.0, "lat": 0.0, "lon": 0.0,
                "region": a["region"], "airports": [],
            })
            c["pax"] += a["pax"]
            c["lat"] += a["lat"] * a["pax"]
            c["lon"] += a["lon"] * a["pax"]
            c["airports"].append(a["iata"])
        for c in self.cities.values():
            c["lat"] /= c["pax"]
            c["lon"] /= c["pax"]
            c["scale"] = self._scale_of(c["pax"])

        self.city_list = sorted(self.cities)
        self._dist = {}
        self._demand_cache = {}
        self._aircraft_types = {}
        for r in read_csv(ROOT / "aircraft.csv"):
            self._aircraft_types[r["code"]] = {
                "code": r["code"], "name": r["name"], "class": r["class"],
                "seats": int(r["seats"]), "range": float(r["range_km"]),
                "speed": float(r["speed_kmh"]),
                "fuel": float(r["fuel_per_seat_100km"]),
                "mtow": float(r["mtow_t"]), "comfort": float(r["comfort"]),
                "price": float(r["price_M"]), "maint": float(r["maint_per_hour_M"]),
            }
        # 每机场每日已用时刻（按公司累加）
        self.slots_used = defaultdict(int)
        # 每机场在营航段数（用于 conn）
        self.routes_at = defaultdict(int)
        # 破产清算流入二手市场的累计价值
        self.secondhand_proceeds = 0.0
        # 全图 HUB 机场集合：决定时刻保留（FR-502-1）与地面服务折扣
        self.hub_airports = set()

    @staticmethod
    def _scale_of(pax):
        for name, thr in (("XL", 80.0), ("L", 45.0), ("M", 25.0), ("S", 10.0), ("R", 0.0)):
            if pax >= thr:
                return name
        return "R"

    def dist(self, ca, cb):
        key = tuple(sorted((ca, cb)))
        if key not in self._dist:
            a, b = self.cities[key[0]], self.cities[key[1]]
            self._dist[key] = gc_km(a, b)
        return self._dist[key]

    def airport_dist(self, a, b):
        """机场码 → 所在城市的距离"""
        return self.dist(self.airports[a]["city"], self.airports[b]["city"])

    def ac(self, code):
        return self._aircraft_types[code]

    # ---------- 需求 ----------

    def conn(self, airport_code):
        r = self.routes_at.get(airport_code, 0)
        k, nref, cap = 0.50, 100.0, 1.80
        return min(cap, 1.0 + k * math.log(1.0 + r / nref))

    def c0(self, d):
        s, w = -1.119, 1800.0
        return s + (2.442 - s) * clamp((d - 600.0) / w, 0.0, 1.0)

    def c_rep(self, d):
        return min(1.20, 0.25 + 0.000075 * d)

    def p_ref(self, d, cabin):
        return 3.704 * (d ** 0.7995) * {"eco": 1.0, "biz": 2.6, "fst": 4.5}[cabin]

    def region_factor(self, ca, cb):
        ra, rb = self.cities[ca]["region"], self.cities[cb]["region"]
        if ra == rb == "CN":
            return 1.0
        key = "CN-" + (rb if ra == "CN" else ra if rb == "CN" else rb)
        return self.params["region_factor"].get(key, 0.05)

    def demand_air(self, ca, cb):
        """返回 (D_total, D_air)，按日单向人次"""
        key = (ca, cb) if ca < cb else (cb, ca)
        if key in self._demand_cache:
            return self._demand_cache[key]
        A, B = self.cities[key[0]], self.cities[key[1]]
        w = self.params["scale"]["weight"]
        d = self.dist(*key)
        # 两端的连通度取该城市所有机场 conn 的均值
        conn_a = sum(self.conn(i) for i in A["airports"]) / len(A["airports"])
        conn_b = sum(self.conn(i) for i in B["airports"]) / len(B["airports"])
        total = (self.params["demand"]["C"] * w[A["scale"]] * w[B["scale"]]
                 * self.region_factor(*key) * conn_a * conn_b)
        air = total * sigmoid(self.c0(d))
        self._demand_cache[key] = (total, air)
        return total, air

    def invalidate_demand(self):
        self._demand_cache.clear()


# ============================================================
# 机队与航空公司
# ============================================================

class Aircraft:
    _next = 1

    def __init__(self, ac_type, age=0.0, lease=False, base=None, deposit=0.0):
        self.id = Aircraft._next
        Aircraft._next += 1
        self.type = ac_type
        self.age = age
        self.lease = lease
        self.base = base          # 基地机场：决定是否享受 HUB 成本乘数（FR-502）
        self.deposit = deposit    # 租赁押金：退租时原额退还（费率变动不影响老合同）
        self.hours_today = 0.0
        self.segments_today = 0
        self.airline = None

    def reset_day(self):
        self.hours_today = 0.0
        self.segments_today = 0


class Route:
    """一条航线：1–3 段，最多 2 个经停点"""

    def __init__(self, airline, segments, daily_flights, ac_type, price_index=1.0):
        self.airline = airline
        self.segments = segments            # [iata, iata, ...]，长度 2..4
        self.daily_flights = daily_flights  # 每日往返班次
        self.ac_type = ac_type
        # 价格指数：相对参考票价的倍数。参考价 p_ref(d) 按 OD 自身直线距离取，
        # 因此每条 OD 的单位里程票价天然不同（短途更贵），不需要航线级票价率。
        self.price_index = price_index
        self.rep = 50.0
        self.lf_ewma = 0.7
        self.low_lf_months = 0
        self.slot_low_days = 0          # FR-404：时刻使用质量连续偏低天数
        # 每日刷新的运营指标
        self.on_time = 0.95
        self.cancel_rate = 0.005
        self.rep_target = 50.0
        self.price_base = price_index

    def op_factor(self):
        """取消率折算的可用运力系数"""
        return max(0.5, 1.0 - self.cancel_rate)

    @property
    def n_segments(self):
        return len(self.segments) - 1

    def seg_list(self):
        return list(zip(self.segments[:-1], self.segments[1:]))

    def seg_km(self, i):
        s, e = self.segments[i], self.segments[i + 1]
        return self.airline.world.airport_dist(s, e)

    def total_km(self):
        return sum(self.airline.world.airport_dist(self.segments[i], self.segments[i + 1])
                   for i in range(self.n_segments))

    def od_km(self, i, j):
        """第 i 段起点到第 j 段终点的里程"""
        return sum(self.airline.world.airport_dist(self.segments[k], self.segments[k + 1])
                   for k in range(i, j + 1))

    def public_fares(self):
        """对外的公开票价（R-632）：每个 OD 按 参考价(两端直线距离, 舱位) × 价格指数。

        只给票价，不给成本与收入；经济/商务两舱，与玩家侧调价口径一致。
        """
        w = self.airline.world
        out = []
        for i in range(self.n_segments):
            for j in range(i + 1, self.n_segments + 1):
                a, b = self.segments[i], self.segments[j]
                ca, cb = w.airports[a]["city"], w.airports[b]["city"]
                if ca == cb:
                    continue
                d = w.dist(ca, cb)
                out.append({
                    "from": a, "to": b,
                    "eco": round(w.p_ref(d, "eco") * self.price_index),
                    "biz": round(w.p_ref(d, "biz") * self.price_index),
                })
        return out


class Airline:
    def __init__(self, name, world, cash, hub, is_player=False):
        self.name = name
        self.world = world
        self.cash = cash
        self.debt = 0.0
        self.hubs = [hub] if hub else []
        self.fleet = []
        self.routes = []
        self.rep = 50.0
        self.rank_score = 0.0
        self.alive = True
        self.is_player = is_player
        self.history = []
        self.neg_days = 0            # 连续亏损天数（EBITDA < 0）
        self.dead_reason = None
        self.dead_day = None
        self.contractions = 0        # 收缩次数（关线 + 卖机）
        self.monthly = []            # FR-706 月报表

    # ---------- 财务 ----------

    @property
    def equity(self):
        return self.cash + self.fleet_value() - self.debt

    def fleet_value(self):
        return sum(self.world.ac(a.type)["price"] *
                   max(0.10, 1 - 0.065 * a.age - 0.0015 * a.age ** 2) for a in self.fleet)

    def borrow_capacity(self):
        # 注意：必须用 max(0, EBITDA)，用 abs() 会让亏损航司反而获得更高授信额度
        ebitda12 = max(0.0, getattr(self, "ebitda_12m", 0.0))
        cap_by_assets = self.fleet_value() * 0.6 + ebitda12 * 3
        cap_by_equity = max(0.0, self.equity) * ECON["max_debt_to_equity"]
        return max(0.0, min(cap_by_assets, cap_by_equity) - self.debt)

    def interest_rate(self):
        eq = max(self.equity, 1e-6)
        lev = self.debt / (self.debt + eq)
        return clamp(ECON["loan_rate_base"] + lev * 0.06, ECON["loan_rate_base"], ECON["loan_rate_max"])

    # ---------- 机队 ----------

    def buy_aircraft(self, code, age=0.0, lease=False, base=None):
        t = self.world.ac(code)
        cost = t["price"] if not lease else 0.0
        if lease:
            deposit = t["price"] * ECON["lease_rate_month"] * 3
            if self.cash < deposit:
                return None
            self.cash -= deposit
        else:
            if self.cash < cost:
                return None
            self.cash -= cost
        ac = Aircraft(code, age=age, lease=lease,
                      base=base or (self.hubs[0] if self.hubs else None),
                      deposit=deposit if lease else 0.0)
        ac.airline = self
        self.fleet.append(ac)
        return ac

    def lease_deposit(self, ac_type):
        """租赁押金（与买入时同一口径：3 个月租金）"""
        return self.world.ac(ac_type)["price"] * ECON["lease_rate_month"] * 3

    def sell_aircraft(self, ac):
        """自有飞机：按市价 85% 立即出售回笼现金（§7.2）"""
        t = self.world.ac(ac.type)
        mv = t["price"] * max(0.10, 1 - 0.065 * ac.age - 0.0015 * ac.age ** 2)
        self.cash += mv * 0.85
        if ac in self.fleet:
            self.fleet.remove(ac)
        return mv * 0.85

    def return_lease(self, ac):
        """租赁飞机：退租，只退押金，不产生二手出售收入（飞机不是自己的）"""
        deposit = ac.deposit if getattr(ac, "deposit", 0) > 0 else self.lease_deposit(ac.type)
        self.cash += deposit
        if ac in self.fleet:
            self.fleet.remove(ac)
        return deposit

    def close_route(self, r):
        if r in self.routes:
            self.routes.remove(r)
            touches = slot_touches(r.segments)
            for code in set(r.segments):
                # FR-403：释放 2 × 触及航段数 × daily_flights 个时刻
                freed = 2 * touches.get(code, 0) * r.daily_flights
                self.world.slots_used[code] = max(
                    0, self.world.slots_used.get(code, 0) - freed)
                self.world.routes_at[code] = max(0, self.world.routes_at.get(code, 0) - 1)
            self.world.invalidate_demand()

    # ---------- HUB（FR-501 / FR-502）----------

    HUB_FEE = {"XL": 300.0, "L": 200.0, "M": 100.0, "S": 60.0, "R": 50.0}

    def routes_at_airport(self, code):
        return sum(1 for r in self.routes if code in r.segments)

    def aircraft_based(self, code):
        return sum(1 for a in self.fleet if a.base == code)

    def can_add_hub(self, code):
        if len(self.hubs) >= 3 or code in self.hubs:
            return False, "已达 HUB 上限或已存在"
        ap = self.world.airports[code]
        if ap["pax"] < 10.0:
            return False, "机场吞吐量不足 10 百万人次"
        if self.routes_at_airport(code) < 2:
            return False, "该机场航线少于 2 条"
        if self.aircraft_based(code) < 3:
            return False, "该机场基地飞机少于 3 架"
        fee = self.HUB_FEE[ap["scale"]]
        if not self.is_player and self.cash < fee * 1.5:
            return False, "现金不足以支付开设费"
        return True, fee

    def add_hub(self, code, fee):
        self.cash -= fee
        self.hubs.append(code)
        self.world.hub_airports.add(code)
        return fee

    def die(self, reason, day=None):
        """破产清算：航线与时刻回公共池，机队按 70% 二手市价流入市场（R-910）"""
        self.alive = False
        self.dead_reason = reason
        self.dead_day = day
        for r in list(self.routes):
            self.close_route(r)
        proceeds = 0.0
        for ac in self.fleet:
            t = self.world.ac(ac.type)
            mv = t["price"] * max(0.10, 1 - 0.065 * ac.age - 0.0015 * ac.age ** 2)
            proceeds += mv * 0.70
        self.world.secondhand_proceeds += proceeds
        self.fleet = []
        self.cash = 0.0

    def route_hours(self, r):
        """一条航线的每日往返占机小时"""
        w = self.world
        t = w.ac(r.ac_type)
        fly = sum(w.airport_dist(r.segments[i], r.segments[i + 1]) / t["speed"]
                  for i in range(r.n_segments))
        turn = FLIGHT["turnaround_min"][t["class"]] / 60.0
        stop = FLIGHT["stopover_extra_min"] / 60.0
        ground = 0.0
        for i in range(r.n_segments):
            # 非 HUB 机场过站更慢（R-541：飞往非 HUB 机场时 ×1.15）
            both_hub = (r.segments[i] in self.hubs and r.segments[i + 1] in self.hubs)
            ground += turn if both_hub else turn * 1.15
            if 0 < i < r.n_segments - 1:
                ground += stop
        # 往返：飞行 2 次、地面 2 次
        return 2 * (fly + ground) * r.daily_flights

    def route_segments_needed(self, r):
        return 2 * r.n_segments * r.daily_flights

    def total_hours(self):
        return sum(self.route_hours(r) for r in self.routes)

    def total_segments(self):
        return sum(self.route_segments_needed(r) for r in self.routes)

    def capacity_hours(self):
        return FLIGHT["max_hours_per_day"] * len(self.fleet)

    def capacity_segments(self):
        return FLIGHT["max_segments_per_day"] * len(self.fleet)

    def has_capacity(self, r):
        return (self.total_hours() + self.route_hours(r) <= self.capacity_hours()
                and self.total_segments() + self.route_segments_needed(r) <= self.capacity_segments())

    # ---------- 按机型 + 连通分量分池的运力 ----------
    # 一架飞机一天只能飞一条连续的航段链：A→B→C→A 是合法的转一圈，
    # 但从 PEK 飞 SHA 再飞 KMG 就必须有 SHA→KMG 的航段把链子接上。
    # 因此把航段看成无向图的边，连通分量就是一个「同一架飞机能串飞」的组；
    # 每组的上限是 16 h × 组内机场驻扎的该机型飞机数。
    # 这样 XIY-DEL、XIY-KMG、KMG-DEL 三条线可以被一架 XIY 的飞机串起来，
    # 而一条孤立的 KMG-DEL 则必须有一架停在 KMG 的飞机。

    def components(self, ac_type):
        """按机型把航线按航段连通性分组：root -> {hours, segs, cap_h, cap_s, airports}"""
        parent = {}

        def find(x):
            parent.setdefault(x, x)
            root = x
            while parent[root] != root:
                root = parent[root]
            while parent[x] != root:
                parent[x], x = root, parent[x]
            return root

        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[rb] = ra

        routes = [r for r in self.routes if r.ac_type == ac_type]
        for r in routes:
            for i in range(len(r.segments) - 1):
                union(r.segments[i], r.segments[i + 1])
        for a in self.fleet:
            if a.type == ac_type and a.base:
                find(a.base)

        groups = {}
        for r in routes:
            root = find(r.segments[0])
            g = groups.setdefault(root, {"hours": 0.0, "segs": 0,
                                         "cap_h": 0.0, "cap_s": 0, "airports": set()})
            g["hours"] += self.route_hours(r)
            g["segs"] += self.route_segments_needed(r)
            g["airports"].update(r.segments)
        for a in self.fleet:
            if a.type != ac_type or not a.base:
                continue
            root = find(a.base)
            g = groups.setdefault(root, {"hours": 0.0, "segs": 0, "cap_h": 0.0,
                                         "cap_s": 0, "airports": set()})
            g["airports"].add(a.base)
            g["cap_h"] += FLIGHT["max_hours_per_day"]
            g["cap_s"] += FLIGHT["max_segments_per_day"]
        return groups

    def excess_by_component(self, ac_type=None):
        """超出上限的 (小时, 航段) 合计；用于「允许补救、禁止恶化」的变更校验"""
        types = [ac_type] if ac_type else sorted({r.ac_type for r in self.routes}
                                                | {a.type for a in self.fleet})
        ex_h = ex_s = 0.0
        for t in types:
            for g in self.components(t).values():
                ex_h += max(0.0, g["hours"] - g["cap_h"])
                ex_s += max(0.0, g["segs"] - g["cap_s"])
        return ex_h, ex_s

    def fits_route(self, r):
        """把航线 r 加进来后，该机型的所有连通分量是否都不超载"""
        if r in self.routes:
            raise ValueError("fits_route 需要一条尚未加入 routes 的航线")
        self.routes.append(r)
        try:
            ex_h, ex_s = self.excess_by_component(r.ac_type)
        finally:
            self.routes.remove(r)
        return ex_h <= 1e-9 and ex_s <= 1e-9


    def can_cover(self, r):
        need_h = self.route_hours(r)
        need_s = self.route_segments_needed(r)
        free = [a for a in self.fleet if a.hours_today + need_h <= FLIGHT["max_hours_per_day"]
                and a.segments_today + need_s <= FLIGHT["max_segments_per_day"]]
        if not free:
            return False, None
        ac = free[0]
        ac.hours_today += need_h
        ac.segments_today += need_s
        return True, ac

    def reset_day(self):
        for a in self.fleet:
            a.reset_day()

    # ---------- 口碑（R-616 / R-617）----------

    def avg_age(self):
        return sum(a.age for a in self.fleet) / len(self.fleet) if self.fleet else 0.0

    def update_route_stats(self):
        """每日刷新每条航线的准点、取消率与口碑目标值

        R-616: rep_target = 50 + 25·准点分 + 10·机龄分 + 舒适度 × 距离权重
                            + 5·HUB 覆盖 − 15·取消率
        舒适度的权重随航距上升（D-40 的意图）：短途 10 分，远程最高 30 分。
        否则机型舒适度对口碑的影响只有约 3 分，在 logit 里几乎看不出来。
        """
        age = self.avg_age()
        on_time = clamp(0.985 - 0.005 * age, 0.80, 0.99)
        cancel = clamp(0.005 + 0.003 * max(0.0, age - 12), 0.0, 0.12)
        hub_routes = sum(1 for r in self.routes
                         if any(h in r.segments for h in self.hubs))
        hub_cov = (hub_routes / len(self.routes)) if self.routes else 0.0

        for r in self.routes:
            t = self.world.ac(r.ac_type)
            d = r.total_km()
            comfort_w = 10.0 + 20.0 * clamp((d - 1500.0) / 5000.0, 0.0, 1.0)
            r.on_time = on_time
            r.cancel_rate = cancel
            r.rep_target = (50.0
                            + 25.0 * clamp((on_time - 0.70) / 0.30, 0.0, 1.0)
                            + 10.0 * clamp(1.0 - age / 25.0, 0.0, 1.0)
                            + comfort_w * (t["comfort"] / 100.0)
                            + 5.0 * hub_cov
                            - 15.0 * cancel)
            r.rep = clamp(r.rep + (r.rep_target - r.rep) * 0.05, 0.0, 100.0)

    def refresh_reputation(self, route_flow):
        """R-617：按客流加权汇总为公司口碑"""
        num = den = 0.0
        for r in self.routes:
            f = sum(route_flow.get(id(r), {}).values())
            num += r.rep * f
            den += f
        if den > 0:
            self.rep = num / den
        elif self.routes:
            self.rep = sum(r.rep for r in self.routes) / len(self.routes)



