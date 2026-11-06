# -*- coding: utf-8 -*-
"""游戏实例：时刻回收、逐日推进、玩家指令 apply、快照、存档序列化。

由 sim/simulate.py 拆分而来；只允许依赖更靠前的分层，不要反向 import。
"""

import json
import random
import re
from ai import ai_decide, usable_slots, validate_stopover
from collections import defaultdict
from config import CAL, DAYS_PER_YEAR, GOAL_DEADLINE_DAYS, GOAL_DEFS, GOAL_MONTHS, GOAL_RATINGS, HISTORY_DAYS, MONTHLY_KEEP, REGION_NAMES, SAVE_FORMAT, SAVE_VERSION, STOP
from goals import blank_goal_state, month_quality_ok, region_market_share, weighted_load_factor
from model import Aircraft, Airline, Route, World
from names import pick_ai_names
from settle import settle_day
from util import runway_allows, slot_touches

# 旧版 AI 名字形如 "AI-07"：读档时替换成名字池里的公司名
LEGACY_AI_NAME = re.compile(r"^AI-\d{2}$")


# ============================================================
# 主循环
# ============================================================

def reclaim_stale_slots(world, airlines):
    """FR-404 时刻回收（近似实现）

    规则原文以「实际执飞 / 已获批班次」定义时刻使用率，但本内核里获批即执飞，
    该比值恒为 100%，无法反映「占了时刻却飞得很空」的囤积行为。
    因此改用「载客率」作为时刻被有效使用的代理：某航线连续 60 日载客率 < 45%
    即视为这些时刻被浪费，强制削减 1 个每日班次（保留至少 1 班，不砍死航线）。
    """
    reclaimed = 0
    for al in airlines:
        if not al.alive:
            continue
        for r in al.routes:
            if r.slot_low_days >= 60 and r.daily_flights > 1:
                r.daily_flights -= 1
                r.slot_low_days = 0
                reclaimed += 1
    return reclaimed


def capacity_pools(airline):
    """按 (机型, 连通分量) 汇总运力占用：同组的航线可以由组内基地的飞机串飞。"""
    rows = []
    types = sorted({r.ac_type for r in airline.routes}
                   | {a.type for a in airline.fleet})
    for ac_type in types:
        for g in airline.components(ac_type).values():
            rows.append({
                "type": ac_type,
                "airports": sorted(g["airports"]),
                "count": sum(1 for a in airline.fleet
                             if a.type == ac_type and a.base in g["airports"]),
                "hours_used": round(g["hours"], 1), "hours_cap": round(g["cap_h"], 1),
                "segments_used": g["segs"], "segments_cap": g["cap_s"],
                "over": g["hours"] > g["cap_h"] + 1e-9 or g["segs"] > g["cap_s"],
            })
    return rows


def pool_for_route(airline, r):
    """把 r 临时算进来，返回 r 所在连通分量的占用行（用于报错提示）"""
    airline.routes.append(r)
    try:
        pools = capacity_pools(airline)
    finally:
        airline.routes.remove(r)
    return next((x for x in pools
                 if x["type"] == r.ac_type and r.segments[0] in x["airports"]), None)



class Game:
    """可逐日推进的游戏实例。

    - 批量模拟（run）与 API 服务（server/app.py）共用同一个类，避免两套逻辑
    - with_player=False 时行为与旧版 run() 完全一致（用于回归与报告）
    - with_player=True 时创建 1 家玩家公司，玩家不跑 AI 决策，只能通过 apply() 下指令
    """

    def __init__(self, n_ai=50, seed=42, start_cash=3000.0,
                 player_hub="PEK", player_name="玩家航空", with_player=False):
        self.params = json.loads((CAL / "params.json").read_text(encoding="utf-8"))
        self.world = World(self.params)
        self.rng = random.Random(seed)
        self.seed = seed
        self.day = 0
        self.paused = True
        self.speed = 0
        self.log = []
        self.snapshots = []
        self._next_rid = 1

        # FR-1101 / FR-1102：默认沙盒；目标模式由 configure_mode 显式开启
        self.mode = "sandbox"
        self.mode_chosen = True
        self.goal_start_day = 0
        self.goal_deadline_day = GOAL_DEADLINE_DAYS
        self.goal_state = blank_goal_state()
        self.settlement = None

        world = self.world
        hub_pool = [a["iata"] for a in sorted(world.airports.values(), key=lambda x: -x["pax"])
                    if a["scale"] in ("XL", "L", "M")]

        self.airlines = []
        self.player = None
        if with_player:
            self.player = Airline(player_name, world, start_cash, player_hub, is_player=True)
            self.player.buy_aircraft("A320", base=player_hub)
            world.hub_airports.add(player_hub)
            self.airlines.append(self.player)

        # 名字用独立随机数流抽取：不消耗 self.rng，同一 seed 的 AI 行为与旧版一致
        ai_names = pick_ai_names(n_ai, seed,
                                 taken=(self.player.name if self.player else "",))
        for i in range(n_ai):
            hub = hub_pool[i % len(hub_pool)]
            al = Airline(ai_names[i], world, start_cash, hub)
            al.buy_aircraft("A320", base=hub)
            world.hub_airports.add(hub)
            self.airlines.append(al)

        self.log_event("新游戏开始", f"对手 {n_ai} 家，种子 {seed}")

    # ---------- 日志 ----------

    def log_event(self, title, detail=""):
        self.log.append({"day": self.day, "title": title, "detail": detail})
        if len(self.log) > 200:
            self.log = self.log[-200:]

    def new_route_id(self):
        rid = self._next_rid
        self._next_rid += 1
        return rid

    # ---------- 推进 ----------

    def advance_day(self):
        self.day += 1
        day = self.day
        world = self.world
        airlines = self.airlines

        for al in airlines:
            al.reset_day()
            for a in al.fleet:
                a.age += 1.0 / 360.0
        if day % 7 == 1:
            for al in airlines:
                if al.is_player or not al.alive:
                    continue
                ai_decide(world, al, self.rng, self.params)
        settle_day(world, airlines, self.params, day)

        # 全局时刻占用重算（FR-403：经停中间机场按 2 个航段计）
        world.slots_used.clear()
        for al in airlines:
            if not al.alive:
                continue
            for r in al.routes:
                touches = slot_touches(r.segments)
                for code, t in touches.items():
                    world.slots_used[code] += 2 * t * r.daily_flights

        if day % 30 == 0:
            world.slots_reclaimed = getattr(world, "slots_reclaimed", 0) + \
                reclaim_stale_slots(world, airlines)
            for al in airlines:
                if al.alive and len(al.history) >= 30:
                    h = al.history[-30:]
                    rev_sum = sum(x["revenue"] for x in h)
                    pax_sum = sum(x["pax"] for x in h)
                    ebi_sum = sum(x["ebitda"] for x in h)
                    on_time = (sum(float(x.get("on_time") or 0.0) * x["pax"] for x in h)
                               / pax_sum) if pax_sum > 0 else (
                        sum(float(x.get("on_time") or 0.0) for x in h) / len(h))
                    al.monthly.append({
                        "day": day,
                        "pax": pax_sum,
                        "revenue": rev_sum,
                        "cost": sum(x["cost"] for x in h),
                        "ebitda": ebi_sum,
                        "on_time": on_time,
                        "ebitda_rate": (ebi_sum / rev_sum) if rev_sum > 0 else 0.0,
                        "cash": al.cash, "debt": al.debt,
                        "fleet": len(al.fleet), "routes": len(al.routes),
                    })
                    # 月报只留最近 36 条：目标判定最多回看 24 个月
                    if len(al.monthly) > MONTHLY_KEEP:
                        del al.monthly[:-MONTHLY_KEEP]

        if day % 30 == 0 or day == 1:
            alive = [a for a in airlines if a.alive]
            snap = {
                "day": day, "alive": len(alive),
                "pax": sum(a.history[-1]["pax"] for a in alive) if alive else 0,
                "rev": sum(a.history[-1]["revenue"] for a in alive) if alive else 0,
                "routes": sum(len(a.routes) for a in alive),
                "fleet": sum(len(a.fleet) for a in alive),
                "cash": sum(a.cash for a in alive),
            }
            self.snapshots.append(snap)

        if self.player and self.player.alive:
            h = self.player.history[-1]
            if h["ebitda"] < 0 and day % 30 == 0:
                self.log_event("本月亏损", f"EBITDA {h['ebitda']:.2f} ¥M")
        self._update_goals()
        return self.snapshots[-1] if self.snapshots else None

    # ---------- 玩家指令（FR-1001）----------

    def apply(self, action, args):
        p = self.player
        if p is None:
            return {"ok": False, "reason": "当前对局没有玩家公司"}
        if not p.alive:
            return {"ok": False, "reason": "公司已破产"}
        w = self.world
        args = args or {}

        if action == "open_route":
            segs = [str(x).upper() for x in args.get("segments", [])]
            flights = int(args.get("daily_flights", 1))
            ac = args.get("ac_type", "A320")
            if len(segs) < 2 or len(segs) > 3:
                return {"ok": False, "reason": "Ver 1.0 只支持 1–2 个航段（0 或 1 个经停点）"}
            if any(s not in w.airports for s in segs):
                return {"ok": False, "reason": "机场代码不存在"}
            if ac not in w._aircraft_types:
                return {"ok": False, "reason": "机型不存在"}
            if not any(a.type == ac for a in p.fleet):
                return {"ok": False, "reason": f"机队没有 {ac}，请先购买或租赁"}
            if not (1 <= flights <= 14):
                return {"ok": False, "reason": "班次须在 1–14 之间"}
            if len(segs) == 3:
                ok, why = validate_stopover(w, segs, ac, flights)
                if not ok:
                    return {"ok": False, "reason": why}
            else:
                d = w.airport_dist(segs[0], segs[1])
                if d < STOP["min_segment_km"]:
                    return {"ok": False, "reason": f"航段距离 {d:.0f} km 过短"}
                if d > w.ac(ac)["range"] * 0.95:
                    return {"ok": False, "reason": "超出机型航程"}
                for code in segs:
                    if not runway_allows(w.airports[code], w.ac(ac)["class"]):
                        return {"ok": False,
                                "reason": f"{code} 跑道等级不满足 {ac}"}
            r = Route(p, segs, flights, ac, 0.97)
            # 运力按机型分池：E190 空闲的时间不能给 A320 航线用
            if not p.fits_route(r):
                pool = pool_for_route(p, r)
                where = "/".join(pool["airports"]) if pool else segs[0]
                used_h = pool["hours_used"] if pool else 0.0
                cap_h = pool["hours_cap"] if pool else 0.0
                used_s = pool["segments_used"] if pool else 0
                cap_s = pool["segments_cap"] if pool else 0
                return {"ok": False, "reason": (
                    f"{where} 这组的 {ac} 运力不足：已占 {used_h:.1f}/{cap_h:.0f} h、"
                    f"{used_s}/{cap_s} 段，本次需要 "
                    f"{p.route_hours(r):.1f} h / {p.route_segments_needed(r)} 段；"
                    f"可以调机到该组机场、换机型或再买一架 {ac}")}
            # FR-403：每机场占用 2 × 触及航段数 × daily_flights
            touches = slot_touches(segs)
            slot_need = {}
            for code in set(segs):
                need = 2 * touches[code] * flights
                if w.slots_used[code] + need > usable_slots(w, p, code):
                    return {"ok": False, "reason": f"{code} 时刻不足"}
                slot_need[code] = need
            r.rid = self.new_route_id()
            p.routes.append(r)
            for code, need in slot_need.items():
                w.routes_at[code] = w.routes_at.get(code, 0) + 1
                w.slots_used[code] += need
            w.invalidate_demand()
            self.log_event("开通航线", f"{'＝'.join(segs)} 每日 {flights} 班 {ac}")
            return {"ok": True, "route_id": r.rid}

        if action == "close_route":
            rid = args.get("route_id")
            r = next((x for x in p.routes if x.rid == rid), None)
            if not r:
                return {"ok": False, "reason": "航线不存在"}
            p.close_route(r)
            self.log_event("关闭航线", "＝".join(r.segments))
            return {"ok": True}

        if action == "set_price":
            rid, idx = args.get("route_id"), float(args.get("price_index", 1.0))
            r = next((x for x in p.routes if x.rid == rid), None)
            if not r:
                return {"ok": False, "reason": "航线不存在"}
            if not (0.50 <= idx <= 1.50):
                return {"ok": False, "reason": "价格指数须在 0.50–1.50"}
            r.price_index = idx
            return {"ok": True, "price_index": idx}

        if action == "set_flights":
            rid, n = args.get("route_id"), int(args.get("daily_flights", 1))
            r = next((x for x in p.routes if x.rid == rid), None)
            if not r:
                return {"ok": False, "reason": "航线不存在"}
            if not (1 <= n <= 14):
                return {"ok": False, "reason": "班次须在 1–14 之间"}
            old = r.daily_flights
            ex0 = p.excess_by_component()
            r.daily_flights = n
            ex1 = p.excess_by_component()
            if ex1[0] > ex0[0] + 1e-9 or ex1[1] > ex0[1] + 1e-9:
                r.daily_flights = old
                pool = pool_for_route(p, r)
                where = "/".join(pool["airports"]) if pool else r.segments[0]
                return {"ok": False, "reason": (
                    f"{where} 这组的 {r.ac_type} 运力不足：已占 "
                    f"{pool['hours_used']:.1f}/{pool['hours_cap']:.0f} h、"
                    f"{pool['segments_used']}/{pool['segments_cap']} 段，请先购机或减班")}
            return {"ok": True, "daily_flights": n}

        if action == "set_aircraft":
            rid = args.get("route_id")
            ac = str(args.get("ac_type", "")).upper()
            r = next((x for x in p.routes if x.rid == rid), None)
            if not r:
                return {"ok": False, "reason": "航线不存在"}
            if ac not in w._aircraft_types:
                return {"ok": False, "reason": "机型不存在"}
            if ac == r.ac_type:
                return {"ok": True, "ac_type": ac, "changed": False}
            # 只能换成机队里已有的机型（自己运营过的才谈得上「调机」）
            if not any(a.type == ac for a in p.fleet):
                return {"ok": False, "reason": f"机队没有 {ac}，请先购买或租赁"}
            t = w.ac(ac)
            if len(r.segments) == 3:
                ok, why = validate_stopover(w, list(r.segments), ac, r.daily_flights)
                if not ok:
                    return {"ok": False, "reason": why}
            else:
                for i in range(r.n_segments):
                    a, b = r.segments[i], r.segments[i + 1]
                    d = w.airport_dist(a, b)
                    if d < STOP["min_segment_km"]:
                        return {"ok": False, "reason": f"航段距离 {d:.0f} km 过短"}
                    if d > t["range"] * 0.95:
                        return {"ok": False, "reason": f"{ac} 航程不足（{d:.0f} km）"}
                    for code in (a, b):
                        if not runway_allows(w.airports[code], t["class"]):
                            return {"ok": False, "reason": f"{code} 跑道等级不满足 {ac}"}
            old = r.ac_type
            ex0 = p.excess_by_component()
            r.ac_type = ac
            ex1 = p.excess_by_component()
            # 换更慢/过站更久的机型可能吃穿该机型的运力
            if ex1[0] > ex0[0] + 1e-9 or ex1[1] > ex0[1] + 1e-9:
                r.ac_type = old
                pool = pool_for_route(p, r)
                where = "/".join(pool["airports"]) if pool else r.segments[0]
                return {"ok": False, "reason": (
                    f"{where} 这组的 {ac} 运力不足：换机后已占 "
                    f"{pool['hours_used']:.1f}/{pool['hours_cap']:.0f} h、"
                    f"{pool['segments_used']}/{pool['segments_cap']} 段")}
            self.log_event("更换机型", f"#{r.rid} {'＝'.join(r.segments)} {old} → {ac}")
            return {"ok": True, "ac_type": ac, "changed": True}

        if action == "rebase_aircraft":
            aid = args.get("aircraft_id")
            base = str(args.get("base", "")).upper()
            a = next((x for x in p.fleet if x.id == aid), None)
            if not a:
                return {"ok": False, "reason": "飞机不存在"}
            if base not in w.airports:
                return {"ok": False, "reason": "机场不存在"}
            old_base = a.base
            if (old_base or "") == base:
                return {"ok": True, "base": base, "fee": 0.0, "changed": False}
            t = w.ac(a.type)
            d = w.airport_dist(old_base, base) if old_base else 0.0
            fee = round(d / 1000.0 * 0.25 * (t["mtow"] / 70.0), 2)
            if p.cash < fee:
                return {"ok": False, "reason": f"调机费 {fee:.2f} ¥M，现金不足"}
            ex0 = p.excess_by_component()
            a.base = base
            ex1 = p.excess_by_component()
            if ex1[0] > ex0[0] + 1e-9 or ex1[1] > ex0[1] + 1e-9:
                a.base = old_base
                return {"ok": False,
                        "reason": "调机后原基地运力不足，先给那边的航线减班或关线"}
            p.cash -= fee
            self.log_event("调机", f"{a.type} 基地 {old_base or '—'} → {base}，调机费 {fee:.2f} ¥M")
            return {"ok": True, "base": base, "fee": fee, "changed": True}

        if action == "add_hub":
            code = str(args.get("airport", "")).upper()
            ok, fee = p.can_add_hub(code)
            if not ok:
                return {"ok": False, "reason": fee}
            p.add_hub(code, fee)
            self.log_event("新设枢纽", f"{code}，开设费 {fee:.0f} ¥M")
            return {"ok": True, "fee": fee}

        if action == "buy_aircraft":
            ac = args.get("ac_type", "A320")
            base = str(args.get("base", "")).upper() or (p.hubs[0] if p.hubs else None)
            lease = bool(args.get("lease", False))
            if ac not in w._aircraft_types:
                return {"ok": False, "reason": "机型不存在"}
            need = 0.0 if lease else w.ac(ac)["price"]
            if p.cash < need:
                return {"ok": False, "reason": f"现金不足，需要 {need:.0f} ¥M"}
            a = p.buy_aircraft(ac, lease=lease, base=base)
            if not a:
                return {"ok": False, "reason": "购买失败"}
            self.log_event("购入飞机", f"{ac}（基地 {base}）{'租赁' if lease else '自有'}")
            return {"ok": True, "aircraft_id": a.id}

        if action == "sell_aircraft":
            aid = args.get("aircraft_id")
            a = next((x for x in p.fleet if x.id == aid), None)
            if not a:
                return {"ok": False, "reason": "飞机不存在"}
            # 卖掉/退租会减少 (机型, 基地) 运力：不允许把已经在飞的池子吃穿
            ex0 = p.excess_by_component()
            p.fleet.remove(a)
            ex1 = p.excess_by_component()
            p.fleet.append(a)
            if ex1[0] > ex0[0] + 1e-9 or ex1[1] > ex0[1] + 1e-9:
                return {"ok": False, "reason": (
                    f"卖掉/退租后 {a.type} 的运力会被吃穿：先给该组航线减班或关线")}
            if a.lease:
                got = p.return_lease(a)
                self.log_event("飞机退租", f"{a.type}（{a.base or '—'}），退还押金 {got:.2f} ¥M")
                return {"ok": True, "cash": got, "kind": "return"}
            got = p.sell_aircraft(a)
            self.log_event("出售飞机", f"{a.type}（{a.base or '—'}），回笼 {got:.1f} ¥M")
            return {"ok": True, "cash": got, "kind": "sell"}

        if action == "take_loan":
            amt = float(args.get("amount", 0))
            room = p.borrow_capacity()
            if amt <= 0 or amt > room:
                return {"ok": False, "reason": f"可贷额度 {room:.0f} ¥M"}
            p.debt += amt
            p.cash += amt
            self.log_event("新增贷款", f"{amt:.0f} ¥M")
            return {"ok": True, "debt": p.debt}

        if action == "rename_airline":
            name = " ".join(str(args.get("name") or "").split())
            if not (2 <= len(name) <= 20):
                return {"ok": False, "reason": "公司名称须为 2–20 个字符"}
            if any(ord(ch) < 32 for ch in name):
                return {"ok": False, "reason": "公司名称含非法字符"}
            if any(a is not p and a.name == name for a in self.airlines):
                return {"ok": False, "reason": "该名称已被其他公司使用"}
            old = p.name
            if name == old:
                return {"ok": True, "name": name}
            p.name = name
            self.log_event("公司改名", f"{old} → {name}")
            return {"ok": True, "name": name}

        return {"ok": False, "reason": f"未知指令 {action}"}

    def control(self, paused=None, speed=None):
        if paused is not None:
            self.paused = bool(paused)
        if speed is not None:
            self.speed = max(0, min(16, int(speed)))
            self.paused = self.speed == 0
        return {"paused": self.paused, "speed": self.speed}

    # ---------- 目标模式（FR-1101 / FR-1102 / FR-1103）----------

    def configure_mode(self, mode):
        """开局选择沙盒或目标模式；目标模式固定追踪四个目标。"""
        if mode not in ("sandbox", "goals"):
            raise ValueError("模式必须是 sandbox 或 goals")
        self.mode = mode
        self.mode_chosen = True
        self.goal_start_day = self.day
        self.goal_deadline_day = self.day + GOAL_DEADLINE_DAYS
        self.goal_state = blank_goal_state()
        self.settlement = None
        return self.mode

    def _current_goal_metrics(self):
        p = self.player
        empty = {"rank": None, "region_share": 0.0, "region": None,
                 "segments": 0, "avg_lf": 0.0, "month_ok": False}
        if p is None or not p.alive:
            return empty
        alive = [a for a in self.airlines if a.alive]
        ranked = sorted(alive, key=lambda a: -a.rank_score)
        rank = ranked.index(p) + 1 if p in ranked else None
        share, region, _ = region_market_share(self.world, alive, p)
        month_ok = bool(p.monthly) and month_quality_ok(p.monthly[-1])[0]
        return {"rank": rank, "region_share": share, "region": region,
                "segments": p.total_segments(),
                "avg_lf": weighted_load_factor(p), "month_ok": month_ok}

    def _update_goals(self):
        """每个游戏日结算后调用；逐日追踪四个目标并在期限/全达成时结算。"""
        if self.mode != "goals" or not self.mode_chosen or self.settlement:
            return
        p = self.player
        if p is None:
            return
        if not p.alive:
            self._settle_goals("bankrupt", "公司破产")
            return

        st = self.goal_state
        m = self._current_goal_metrics()
        within = self.day <= self.goal_deadline_day

        mt = st["market_top3"]
        if m["rank"] is not None:
            if mt["best_rank"] is None or m["rank"] < mt["best_rank"]:
                mt["best_rank"] = m["rank"]
            if within and not mt["achieved"] and m["rank"] <= 3:
                mt["achieved"] = True
                mt["day"] = self.day

        rl = st["region_leader"]
        if m["region"] is not None:
            if m["region_share"] > rl["best_share"]:
                rl["best_share"] = m["region_share"]
                rl["region"] = m["region"]
            if within and not rl["achieved"] and m["region_share"] >= 0.35:
                rl["achieved"] = True
                rl["day"] = self.day

        ne = st["network_expansion"]
        if m["segments"] > ne["best_segments"]:
            ne["best_segments"] = m["segments"]
        if m["avg_lf"] > ne["best_lf"]:
            ne["best_lf"] = m["avg_lf"]
        if (within and not ne["achieved"]
                and m["segments"] >= 100 and m["avg_lf"] >= 0.75):
            ne["achieved"] = True
            ne["day"] = self.day

        hq = st["high_quality"]
        if p.monthly:
            last = p.monthly[-1]
            if last.get("day") is not None and last["day"] != hq["last_month_day"]:
                ok, _, _ = month_quality_ok(last)
                hq["last_month_day"] = last["day"]
                hq["streak"] = hq["streak"] + 1 if ok else 0
                hq["best_streak"] = max(hq["best_streak"], hq["streak"])
                if within and not hq["achieved"] and hq["streak"] >= GOAL_MONTHS:
                    hq["achieved"] = True
                    hq["day"] = self.day

        if all(st[gid]["achieved"] for gid, _, _ in GOAL_DEFS):
            self._settle_goals("complete", "四个目标全部达成")
        elif self.day >= self.goal_deadline_day:
            self._settle_goals("deadline", "10 年目标期结束")

    def _settle_goals(self, kind, reason):
        if self.settlement:
            return
        achieved = [gid for gid, _, _ in GOAL_DEFS
                    if self.goal_state.get(gid, {}).get("achieved")]
        count = len(achieved)
        self.settlement = {
            "day": self.day,
            "kind": kind,
            "reason": reason,
            "rating": GOAL_RATINGS[count] if kind != "bankrupt" else None,
            "achieved_count": count,
            "achieved": achieved,
            "scored": kind != "bankrupt" and count > 0,
            "failed": kind == "bankrupt",
            "deadline_day": self.goal_deadline_day,
        }
        self.paused = True
        if kind == "bankrupt":
            self.log_event("目标失败", reason)
        else:
            self.log_event("目标结算",
                           f"{self.settlement['rating']} · {count}/4 · {reason}")

    def goals_snapshot(self):
        """给前端的只读目标状态；沙盒模式不暴露进度。"""
        if self.mode != "goals" or not self.mode_chosen:
            return {
                "mode": self.mode,
                "mode_chosen": self.mode_chosen,
                "setup_required": not self.mode_chosen,
                "start_day": self.goal_start_day,
                "deadline_day": None,
                "days_left": None,
                "years_left": None,
                "progress": [],
                "achieved_count": 0,
                "rating": None,
                "scored": False,
                "settled": False,
                "settlement": None,
            }

        m = self._current_goal_metrics()
        st = self.goal_state
        progress = []
        for gid, name, condition in GOAL_DEFS:
            s = st.get(gid) or {}
            if gid == "market_top3":
                detail = {"best_rank": s.get("best_rank"),
                          "current_rank": m["rank"]}
            elif gid == "region_leader":
                region = s.get("region")
                detail = {"best_share": round(float(s.get("best_share") or 0.0), 4),
                          "region": region,
                          "region_name": REGION_NAMES.get(region, region),
                          "current_share": round(m["region_share"], 4)}
            elif gid == "high_quality":
                detail = {"streak": s.get("streak", 0),
                          "best_streak": s.get("best_streak", 0),
                          "months_required": GOAL_MONTHS,
                          "current_month_ok": m["month_ok"]}
            else:
                detail = {"segments": m["segments"],
                          "avg_lf": round(m["avg_lf"], 4),
                          "best_segments": s.get("best_segments", 0),
                          "best_lf": round(float(s.get("best_lf") or 0.0), 4)}
            progress.append({
                "id": gid, "name": name, "condition": condition,
                "achieved": bool(s.get("achieved")),
                "day": s.get("day"), "detail": detail,
            })

        days_left = max(0, self.goal_deadline_day - self.day)
        settlement = self.settlement
        return {
            "mode": "goals",
            "mode_chosen": True,
            "setup_required": False,
            "start_day": self.goal_start_day,
            "deadline_day": self.goal_deadline_day,
            "days_left": days_left,
            "years_left": round(days_left / DAYS_PER_YEAR, 2),
            "progress": progress,
            "achieved_count": sum(1 for p in progress if p["achieved"]),
            "rating": settlement["rating"] if settlement else None,
            "scored": bool(settlement and settlement.get("scored")),
            "settled": settlement is not None,
            "settlement": settlement,
        }

    # ---------- 存档 / 读档 ----------

    def to_save(self):
        """序列化完整对局。只放必要状态，不保存可重算的缓存。"""
        def route_data(r):
            d = {
                "segments": list(r.segments),
                "daily_flights": r.daily_flights,
                "ac_type": r.ac_type,
                "price_index": r.price_index,
                "rep": r.rep,
                "lf_ewma": r.lf_ewma,
                "low_lf_months": r.low_lf_months,
                "slot_low_days": r.slot_low_days,
                "on_time": r.on_time,
                "cancel_rate": r.cancel_rate,
                "rep_target": r.rep_target,
                "price_base": r.price_base,
            }
            if hasattr(r, "rid"):
                d["rid"] = r.rid
            for key in ("last_pax", "last_revenue", "last_cost", "last_profit",
                        "last_margin", "last_distance_km"):
                if hasattr(r, key):
                    d[key] = getattr(r, key)
            return d

        def aircraft_data(a):
            return {
                "id": a.id, "type": a.type, "age": a.age, "lease": a.lease,
                "base": a.base, "hours_today": a.hours_today,
                "segments_today": a.segments_today,
                "deposit": getattr(a, "deposit", 0.0),
            }

        def airline_data(al):
            return {
                "name": al.name, "cash": al.cash, "debt": al.debt,
                "hubs": list(al.hubs), "rep": al.rep, "rank_score": al.rank_score,
                "alive": al.alive, "is_player": al.is_player,
                "history": al.history, "neg_days": al.neg_days,
                "dead_reason": al.dead_reason, "dead_day": al.dead_day,
                "contractions": al.contractions, "monthly": al.monthly,
                "ebitda_12m": getattr(al, "ebitda_12m", 0.0),
                "last_costs": getattr(al, "last_costs", None),
                "fleet": [aircraft_data(a) for a in al.fleet],
                "routes": [route_data(r) for r in al.routes],
            }

        w = self.world
        return {
            "format": SAVE_FORMAT,
            "version": SAVE_VERSION,
            "game": {
                "day": self.day,
                "seed": self.seed,
                "paused": self.paused,
                "speed": self.speed,
                "next_rid": self._next_rid,
                "rng_state": self.rng.getstate(),
                "params": self.params,
                "log": self.log,
                "snapshots": self.snapshots,
                "mode": self.mode,
                "mode_chosen": self.mode_chosen,
                "goal_start_day": self.goal_start_day,
                "goal_deadline_day": self.goal_deadline_day,
                "goal_state": self.goal_state,
                "settlement": self.settlement,
                "world": {
                    "slots_used": dict(w.slots_used),
                    "routes_at": dict(w.routes_at),
                    "hub_airports": sorted(w.hub_airports),
                    "secondhand_proceeds": w.secondhand_proceeds,
                    "slots_reclaimed": getattr(w, "slots_reclaimed", 0),
                },
                "airlines": [airline_data(al) for al in self.airlines],
            },
        }

    @classmethod
    def from_save(cls, data):
        """从 to_save() 的字典恢复完整对局。"""
        if not isinstance(data, dict) or data.get("format") != SAVE_FORMAT:
            raise ValueError("不是有效的航空公司存档")
        if int(data.get("version", 0)) > SAVE_VERSION:
            raise ValueError("存档版本高于当前程序，请升级后再读档")
        gd = data.get("game")
        if not isinstance(gd, dict):
            raise ValueError("存档缺少 game 数据")

        g = cls.__new__(cls)
        g.params = gd.get("params") or json.loads((CAL / "params.json").read_text(encoding="utf-8"))
        g.world = World(g.params)
        g.seed = int(gd.get("seed", 42))
        g.day = int(gd.get("day", 0))
        g.paused = bool(gd.get("paused", True))
        g.speed = int(gd.get("speed", 0))
        g._next_rid = int(gd.get("next_rid", 1))
        g.log = list(gd.get("log") or [])
        g.snapshots = list(gd.get("snapshots") or [])
        g.mode = gd.get("mode") or "sandbox"
        if g.mode not in ("sandbox", "goals"):
            g.mode = "sandbox"
        g.mode_chosen = bool(gd.get("mode_chosen", True))
        g.goal_start_day = int(gd.get("goal_start_day", 0))
        g.goal_deadline_day = int(gd.get("goal_deadline_day",
                                         g.goal_start_day + GOAL_DEADLINE_DAYS))
        g.goal_state = blank_goal_state()
        for gid, st in (gd.get("goal_state") or {}).items():
            if gid in g.goal_state and isinstance(st, dict):
                g.goal_state[gid].update(st)
        g.settlement = gd.get("settlement")
        g.airlines = []
        g.player = None

        g.rng = random.Random(g.seed)
        rng_state = gd.get("rng_state")
        if rng_state:
            try:
                g.rng.setstate((rng_state[0], tuple(rng_state[1]), rng_state[2]))
            except Exception:
                pass

        wd = gd.get("world") or {}
        w = g.world
        w.slots_used = defaultdict(int, wd.get("slots_used") or {})
        w.routes_at = defaultdict(int, wd.get("routes_at") or {})
        w.hub_airports = set(wd.get("hub_airports") or [])
        w.secondhand_proceeds = float(wd.get("secondhand_proceeds", 0.0))
        w.slots_reclaimed = int(wd.get("slots_reclaimed", 0))
        w._dist = {}
        w._demand_cache = {}

        max_ac_id = 0
        for ad in gd.get("airlines") or []:
            al = Airline(ad.get("name", "航空公司"), w,
                         float(ad.get("cash", 0.0)), None,
                         bool(ad.get("is_player", False)))
            al.debt = float(ad.get("debt", 0.0))
            al.hubs = list(ad.get("hubs") or [])
            al.rep = float(ad.get("rep", 50.0))
            al.rank_score = float(ad.get("rank_score", 0.0))
            al.alive = bool(ad.get("alive", True))
            al.history = list(ad.get("history") or [])[-HISTORY_DAYS:]
            al.neg_days = int(ad.get("neg_days", 0))
            al.dead_reason = ad.get("dead_reason")
            al.dead_day = ad.get("dead_day")
            al.contractions = int(ad.get("contractions", 0))
            al.monthly = list(ad.get("monthly") or [])[-MONTHLY_KEEP:]
            al.ebitda_12m = float(ad.get("ebitda_12m", 0.0))
            al.last_costs = ad.get("last_costs")

            for fd in ad.get("fleet") or []:
                if fd.get("type") not in w._aircraft_types:
                    raise ValueError(f"存档中的机型不存在：{fd.get('type')}")
                ac = Aircraft(fd["type"], age=float(fd.get("age", 0.0)),
                              lease=bool(fd.get("lease", False)),
                              base=fd.get("base"),
                              deposit=float(fd.get("deposit", 0.0) or 0.0))
                ac.id = int(fd.get("id", ac.id))
                max_ac_id = max(max_ac_id, ac.id)
                ac.hours_today = float(fd.get("hours_today", 0.0))
                ac.segments_today = int(fd.get("segments_today", 0))
                ac.airline = al
                al.fleet.append(ac)

            for rd in ad.get("routes") or []:
                segs = [str(s) for s in rd.get("segments", [])]
                if len(segs) < 2 or any(s not in w.airports for s in segs):
                    raise ValueError(f"存档中的航线机场不存在：{'＝'.join(segs)}")
                if rd.get("ac_type", "A320") not in w._aircraft_types:
                    raise ValueError(f"存档中的航线机型不存在：{rd.get('ac_type')}")
                r = Route(al, segs, int(rd.get("daily_flights", 1)),
                          rd.get("ac_type", "A320"), float(rd.get("price_index", 1.0)))
                for key in ("rep", "lf_ewma", "low_lf_months", "slot_low_days",
                            "on_time", "cancel_rate", "rep_target", "price_base",
                            "last_pax", "last_revenue", "last_cost", "last_profit",
                            "last_margin", "last_distance_km"):
                    if key in rd:
                        setattr(r, key, rd[key])
                if rd.get("rid") is not None:
                    r.rid = int(rd["rid"])
                al.routes.append(r)

            if al.is_player:
                if g.player is not None:
                    raise ValueError("存档包含多个玩家公司")
                g.player = al
            g.airlines.append(al)

        if g.player is None:
            raise ValueError("存档中没有玩家公司")
        max_rid = max((r.rid for al in g.airlines for r in al.routes
                       if hasattr(r, "rid")), default=0)
        g._next_rid = max(g._next_rid, max_rid + 1)
        Aircraft._next = max(Aircraft._next, max_ac_id + 1)

        # 老存档里的 AI 还叫 AI-01…AI-50：读档时补成名字池里的公司名，
        # 玩家自己改过的名字、「云翼航空」这类已有名字都保持原样。
        legacy = [al for al in g.airlines
                  if not al.is_player and LEGACY_AI_NAME.match(al.name or "")]
        if legacy:
            used = [al.name for al in g.airlines if al not in legacy and al.name]
            for al, name in zip(legacy, pick_ai_names(len(legacy), g.seed, taken=used)):
                al.name = name

        # FR-403：读档后按航线重算时刻，兼容旧存档中未计入
        # daily_flights / 经停中间机场的占用。
        w.slots_used.clear()
        for al in g.airlines:
            if not al.alive:
                continue
            for r in al.routes:
                touches = slot_touches(r.segments)
                for code, t in touches.items():
                    w.slots_used[code] += 2 * t * r.daily_flights
        return g

    # ---------- 快照（前端契约）----------

    def snapshot(self):
        w = self.world
        p = self.player
        out = {
            "tick": {"day": self.day, "paused": self.paused, "speed": self.speed,
                     "seed": self.seed},
            "airports": [
                {"iata": a["iata"], "city": a["city"], "lat": a["lat"], "lon": a["lon"],
                 "scale": a["scale"], "region": a["region"], "pax": a["pax"],
                 "slot_cap": a["slot_cap"], "slot_used": w.slots_used.get(a["iata"], 0)}
                for a in w.airports.values()
            ],
            "rivals": [],
            "rivals_total": 0,
            "log": self.log[-40:],
        }
        alive = [a for a in self.airlines if a.alive]
        ranked = sorted(alive, key=lambda x: -x.rank_score)
        # 侧栏「竞争对手」只列对手，不含本公司；rank 用全体存活公司名次，
        # 与 player.rank 同一口径，过滤玩家后名次会留空档，这是预期行为（FR-1002）。
        opponents = [(i + 1, a) for i, a in enumerate(ranked) if not a.is_player]
        out["rivals_total"] = len(opponents)
        for rank, a in opponents[:20]:
            h = a.history[-1] if a.history else {"pax": 0, "ebitda": 0}
            lf = (sum(r.lf_ewma for r in a.routes) / len(a.routes)) if a.routes else 0.0
            out["rivals"].append({
                "name": a.name, "hub": a.hubs[0] if a.hubs else None,
                "rank": rank,
                "routes": len(a.routes), "fleet": len(a.fleet),
                "pax": h["pax"], "ebitda": h["ebitda"], "lf": lf,
                "rep": a.rep, "market_cap": a.rank_score,
            })

        # 对手公开航线网络：只给航段/班次/机型/载客率，不给票价与财务（FR-1002）。
        out["opponent_routes"] = [
            {"airline": a.name, "hub": a.hubs[0] if a.hubs else None,
             "segments": list(r.segments), "daily_flights": r.daily_flights,
             "ac_type": r.ac_type, "lf": round(r.lf_ewma, 3),
             # 公开票价（R-632 / UI 信息边界）：只给价格指数与各 OD 票价，
             # 不暴露成本、收入与利润
             "price_index": round(r.price_index, 4),
             "prices": r.public_fares()}
            for a in alive if not a.is_player
            for r in a.routes
        ]
        if p:
            h = p.history[-1] if p.history else {}
            out["player"] = {
                "name": p.name, "alive": p.alive, "cash": p.cash, "debt": p.debt,
                "equity": p.equity, "reputation": p.rep, "market_cap": p.rank_score,
                "rank": (ranked.index(p) + 1) if p in ranked else None,
                "hubs": list(p.hubs),
                "fleet": [{"id": a.id, "type": a.type, "age": a.age,
                           "base": a.base, "lease": a.lease} for a in p.fleet],
                "routes": [
                    {"id": r.rid, "segments": list(r.segments),
                     "daily_flights": r.daily_flights, "ac_type": r.ac_type,
                     "price_index": r.price_index, "lf": r.lf_ewma,
                     # 与对手侧同一口径的 OD 票价，供「竞争者」卡片并排比价
                     "prices": r.public_fares(),
                     "rep": r.rep, "pax": getattr(r, "last_pax", 0.0),
                     "distance_km": round(getattr(r, "last_distance_km", r.total_km()), 0),
                     "revenue_M": round(getattr(r, "last_revenue", 0.0), 4),
                     "cost_M": round(getattr(r, "last_cost", 0.0), 4),
                     "profit_M": round(getattr(r, "last_profit", 0.0), 4),
                     "margin": (round(r.last_margin, 4)
                                if getattr(r, "last_margin", None) is not None else None)}
                    for r in p.routes
                ],
                "kpi": {"pax": h.get("pax", 0), "revenue": h.get("revenue", 0),
                        "cost": h.get("cost", 0), "ebitda": h.get("ebitda", 0)},
                # 成本分项与机队利用率：解释「航线都赚、公司却亏」
                "costs": ({k: round(v, 4) for k, v in p.last_costs.items()}
                          if getattr(p, "last_costs", None) else None),
                # 资产口径：总资产 = 现金 + 机队现值；净资产 = 总资产 − 负债
                "assets": {
                    "cash": round(p.cash, 2),
                    "fleet": round(p.fleet_value(), 2),
                    "total": round(p.cash + p.fleet_value(), 2),
                    "debt": round(p.debt, 2),
                    "equity": round(p.equity, 2),
                    "market_cap": round(p.rank_score, 2),
                },
                "capacity": {
                    "hours_used": round(p.total_hours(), 1),
                    "hours_cap": round(p.capacity_hours(), 1),
                    "segments_used": round(p.total_segments(), 1),
                    "segments_cap": p.capacity_segments(),
                    # 按机型分池：每架 16 h / 8 段，互不借用
                    "pools": capacity_pools(p),
                },
            }
        out["goals"] = self.goals_snapshot()
        return out



