# -*- coding: utf-8 -*-
"""
需求文档 v1.0 —— 验收自测
==========================
对应《需求文档》各 FR 的「验收」条款，直接调用模拟内核的模块级接口。
这些用例覆盖的是「跑批里不容易触发」的路径：HUB 升级、时刻回收、
座位门槛、候选产品上限、绕行定价。

运行：python selftest.py
"""

import json
import math

import simulate as S
import market as MKT   # monkeypatch 要打在“使用处所在模块”，打在门面上不会生效

CAL = S.CAL
PASS, FAIL = [], []


def check(fr, desc, cond, detail=""):
    (PASS if cond else FAIL).append((fr, desc, detail))
    print(f"{'PASS' if cond else 'FAIL'}  [{fr}] {desc}" + (f"  → {detail}" if detail and not cond else ""))


def main():
    params = json.loads((CAL / "params.json").read_text(encoding="utf-8"))
    world = S.World(params)

    # ---------- FR-102 能级边界 ----------
    cases = [(79.9, "L"), (80.0, "XL"), (45.0, "L"), (44.9, "M"),
             (25.0, "M"), (24.9, "S"), (10.0, "S"), (9.9, "R")]
    bad = [f"{p}→{S.World._scale_of(p)}(期望{s})" for p, s in cases if S.World._scale_of(p) != s]
    check("FR-102", "能级边界划分", not bad, "；".join(bad))

    # ---------- FR-103 城市聚合 ----------
    check("FR-103", "上海(虹桥45.6+浦东76.2)能级为 XL",
          world.cities["上海"]["scale"] == "XL", world.cities["上海"]["scale"])

    # ---------- FR-106 距离 ----------
    d_sh = world.dist("北京", "上海")
    check("FR-106", f"北京–上海距离在 1050–1100 km（实测 {d_sh:.0f}）", 1050 <= d_sh <= 1100)
    d_ny = world.dist("北京", "纽约")
    check("FR-106", f"北京–纽约距离在 10900–11000 km（实测 {d_ny:.0f}）", 10900 <= d_ny <= 11000)

    # ---------- FR-201 / FR-202 需求池 ----------
    total, air = world.demand_air("北京", "上海")
    check("FR-201", f"京沪总出行需求 ≈ 21,455（实测 {total:,.0f}）", abs(total - 21455) < 50)
    check("FR-202", f"京沪航空分担率 ≈ 46%（实测 {air / total:.1%}）", 0.44 <= air / total <= 0.48)

    # 距离不进入需求：同能级的两组城市对需求应相等（只看能级与区域）
    t1, _ = world.demand_air("上海", "广州")
    t2, _ = world.demand_air("上海", "深圳")
    check("FR-201", "同为 XL-L 的两组国内城市对需求相同",
          abs(t1 - t2) < 1.0, f"{t1:.1f} vs {t2:.1f}")

    # ---------- FR-306 绕行不提价 ----------
    al = S.Airline("TEST-1", world, 5000.0, "PEK")
    # 直飞 PEK→CAN
    r_direct = S.Route(al, ["PEK", "CAN"], 1, "A320", 0.97)
    # 绕行 PEK→CTU→CAN（多飞很远）
    r_stop = S.Route(al, ["PEK", "CTU", "CAN"], 1, "A320", 0.97)
    al.routes = [r_direct, r_stop]
    al.fleet = [S.Aircraft("A320", base="PEK") for _ in range(3)]
    for a in al.fleet:
        a.airline = al
    prods = S.build_products(world, [al])
    pk = ("北京", "广州")
    prices = sorted(it["price"] for it in prods[pk]["eco"])
    check("FR-306", f"直飞与绕行经停的京广票价相同（{prices[0]:.1f} / {prices[1]:.1f}）",
          len(prices) == 2 and abs(prices[0] - prices[1]) < 0.5)

    # ---------- FR-308 候选产品上限 ----------
    al2 = S.Airline("TEST-2", world, 5000.0, "PEK")
    al2.routes = [
        S.Route(al2, ["PEK", "CAN"], 1, "A320", 0.97),
        S.Route(al2, ["PEK", "CTU"], 1, "A320", 0.97),
        S.Route(al2, ["PEK", "XIY"], 1, "A320", 0.97),
        S.Route(al2, ["PEK", "NKG"], 1, "A320", 0.97),
    ]
    al2.fleet = [S.Aircraft("A320", base="PEK") for _ in range(4)]
    for a in al2.fleet:
        a.airline = al2
    p2 = S.build_products(world, [al2])
    over = {k: len(v["eco"]) for k, v in p2.items() if v["eco"] and len(v["eco"]) > 3}
    check("FR-308", "每 OD 每公司候选产品不超过 3 个", not over, str(over))

    # ---------- FR-501 HUB 门槛 ----------
    al3 = S.Airline("TEST-3", world, 5000.0, "PEK")
    al3.fleet = [S.Aircraft("A320", base="CAN") for _ in range(3)]
    for a in al3.fleet:
        a.airline = al3
    al3.routes = [S.Route(al3, ["CAN", "PEK"], 1, "A320", 0.97),
                  S.Route(al3, ["CAN", "SHA"], 1, "A320", 0.97)]
    ok1, why1 = al3.can_add_hub("CAN")
    check("FR-501", "满足 2 航线 + 3 架基地机 + 吞吐门槛时可新增 HUB", ok1, str(why1))

    al3.fleet = al3.fleet[:2]
    ok2, why2 = al3.can_add_hub("CAN")
    check("FR-501", "基地飞机不足 3 架时拒绝新增 HUB", not ok2, why2)

    al3.fleet = [S.Aircraft("A320", base="CAN") for _ in range(3)]
    for a in al3.fleet:
        a.airline = al3
    al3.routes = [S.Route(al3, ["CAN", "PEK"], 1, "A320", 0.97)]
    ok3, why3 = al3.can_add_hub("CAN")
    check("FR-501", "航线不足 2 条时拒绝新增 HUB", not ok3, why3)

    al3.routes.append(S.Route(al3, ["CAN", "SHA"], 1, "A320", 0.97))
    cash_before = al3.cash
    fee = al3.HUB_FEE[world.airports["CAN"]["scale"]]
    al3.add_hub("CAN", fee)
    check("FR-501", f"新增 HUB 扣除开设费 {fee:.0f} ¥M，现金减少一致",
          abs((cash_before - al3.cash) - fee) < 1e-6 and "CAN" in al3.hubs)
    check("FR-501", "新增 HUB 后进入全图 HUB 集合（用于时刻保留）",
          "CAN" in world.hub_airports)

    # ---------- FR-404 时刻回收 ----------
    r = S.Route(al, ["PEK", "SHA"], 3, "A320", 0.97)
    r.slot_low_days = 60
    al.routes = [r]
    n = S.reclaim_stale_slots(world, [al])
    check("FR-404", f"连续 60 日低使用率后削减 1 个班次（{n} 次，现 {r.daily_flights} 班）",
          n == 1 and r.daily_flights == 2)

    r2 = S.Route(al, ["PEK", "SHA"], 1, "A320", 0.97)
    r2.slot_low_days = 60
    al.routes = [r2]
    n2 = S.reclaim_stale_slots(world, [al])
    check("FR-404", "只有 1 班时不回收（避免把航线砍死）", n2 == 0 and r2.daily_flights == 1)

    # ---------- FR-403 时刻占用 ----------
    g_slot = S.Game(n_ai=0, with_player=True, seed=31)
    w_slot = g_slot.world
    open2 = g_slot.apply("open_route", {"segments": ["PEK", "SHA"],
                                        "daily_flights": 2, "ac_type": "A320"})
    check("FR-403", "开 2 班直飞后两端各占 4 个时刻",
          open2.get("ok") and w_slot.slots_used["PEK"] == 4
          and w_slot.slots_used["SHA"] == 4, str(dict(w_slot.slots_used)))

    if open2.get("ok"):
        g_slot.apply("close_route", {"route_id": open2["route_id"]})
    check("FR-403", "关线后时刻立即释放（不必等到次日重算）",
          w_slot.slots_used["PEK"] == 0 and w_slot.slots_used["SHA"] == 0,
          str(dict(w_slot.slots_used)))

    g_stop = S.Game(n_ai=0, with_player=True, seed=32)
    w_stop = g_stop.world
    open3 = g_stop.apply("open_route", {"segments": ["PEK", "PVG", "CAN"],
                                        "daily_flights": 1, "ac_type": "A320"})
    check("FR-403", "2 段航线中间机场占 4 个时刻（两端各 2 个）",
          open3.get("ok") and w_stop.slots_used["PEK"] == 2
          and w_stop.slots_used["PVG"] == 4 and w_stop.slots_used["CAN"] == 2,
          str(dict(w_stop.slots_used)))

    if open3.get("ok"):
        g_stop.advance_day()
        check("FR-403", "次日全局重算后中间机场仍占 4 个时刻",
              w_stop.slots_used["PVG"] == 4, str(dict(w_stop.slots_used)))
        g_stop.apply("close_route", {"route_id": open3["route_id"]})
        check("FR-403", "关经停航线后三个机场的时刻全部释放",
              w_stop.slots_used["PEK"] == 0 and w_stop.slots_used["PVG"] == 0
              and w_stop.slots_used["CAN"] == 0, str(dict(w_stop.slots_used)))

    g_over = S.Game(n_ai=0, with_player=True, seed=33)
    w_over = g_over.world
    w_over.slots_used["PEK"] = w_over.airports["PEK"]["slot_cap"] - 2
    over = g_over.apply("open_route", {"segments": ["PEK", "SHA"],
                                       "daily_flights": 2, "ac_type": "A320"})
    check("FR-403", "仅剩 2 个时刻时，开 2 班（需 4 个）被拒绝",
          not over.get("ok") and "时刻" in str(over.get("reason")), str(over))

    g_old = S.Game(n_ai=0, with_player=True, seed=35)
    g_old.apply("open_route", {"segments": ["PEK", "PVG", "CAN"],
                               "daily_flights": 1, "ac_type": "A320"})
    legacy = json.loads(json.dumps(g_old.to_save(), ensure_ascii=False))
    legacy["game"]["world"]["slots_used"] = {}
    loaded = S.Game.from_save(legacy)
    check("FR-403", "读档后按航线重算时刻（兼容旧存档）",
          loaded.world.slots_used["PEK"] == 2
          and loaded.world.slots_used["PVG"] == 4
          and loaded.world.slots_used["CAN"] == 2,
          str(dict(loaded.world.slots_used)))

    # FR-502-1：非 HUB 公司在外站 HUB 只能用 70% 时刻
    g_res = S.Game(n_ai=0, with_player=True, seed=34)
    w_res = g_res.world
    w_res.hub_airports.add("PVG")
    w_res.slots_used["PVG"] = int(w_res.airports["PVG"]["slot_cap"] * 0.70)
    res = g_res.apply("open_route", {"segments": ["PEK", "PVG"],
                                     "daily_flights": 1, "ac_type": "A320"})
    check("FR-502", "非 HUB 公司在外站 HUB 只能用 70% 时刻",
          not res.get("ok") and "PVG" in str(res.get("reason")), str(res))

    # ---------- FR-1101 / FR-1102 / FR-1103 目标模式 ----------
    g_sand = S.Game(n_ai=0, with_player=True, seed=41)
    sand = g_sand.goals_snapshot()
    check("FR-1101", "默认沙盒模式，无目标期限与进度",
          sand["mode"] == "sandbox" and not sand["progress"]
          and not sand["settled"] and sand["deadline_day"] is None,
          str(sand))

    g_mode = S.Game(n_ai=0, with_player=True, seed=42)
    g_mode.configure_mode("goals")
    mode = g_mode.goals_snapshot()
    check("FR-1102", "目标模式开局选择后 10 年期限与四目标就绪",
          mode["mode"] == "goals" and mode["deadline_day"] == S.GOAL_DEADLINE_DAYS
          and len(mode["progress"]) == 4 and mode["achieved_count"] == 0,
          str(mode["deadline_day"]))

    g_mode.apply("open_route", {"segments": ["PEK", "SHA"],
                                "daily_flights": 1, "ac_type": "A320"})
    g_mode.advance_day()
    progress = {p["id"]: p for p in g_mode.goals_snapshot()["progress"]}
    check("FR-1102", "市值进前三与区域霸主在满足条件当日被追踪",
          progress["market_top3"]["achieved"]
          and progress["region_leader"]["achieved"],
          str({k: v["achieved"] for k, v in progress.items()}))

    g_net = S.Game(n_ai=0, with_player=True, seed=43)
    g_net.configure_mode("goals")
    p_net = g_net.player
    p_net.routes = []
    for _ in range(50):
        r_net = S.Route(p_net, ["PEK", "SHA"], 1, "A320", 0.97)
        r_net.lf_ewma = 0.80
        r_net.last_pax = 100.0
        p_net.routes.append(r_net)
    g_net._update_goals()
    net = {p["id"]: p for p in g_net.goals_snapshot()["progress"]}["network_expansion"]
    check("FR-1102", "网络扩张要求 100 段且平均客座率 ≥75%",
          net["achieved"] and net["detail"]["segments"] == 100
          and abs(net["detail"]["avg_lf"] - 0.80) < 1e-6, str(net["detail"]))

    g_q = S.Game(n_ai=0, with_player=True, seed=44)
    g_q.configure_mode("goals")
    for i in range(1, S.GOAL_MONTHS + 1):
        g_q.player.monthly.append({
            "day": i * 30, "pax": 1000.0, "revenue": 100.0, "cost": 80.0,
            "ebitda": 20.0, "on_time": 0.90, "ebitda_rate": 0.20,
            "cash": 1000.0, "debt": 0.0, "fleet": 1, "routes": 1,
        })
        g_q.day = i * 30
        g_q._update_goals()
    hq = {p["id"]: p for p in g_q.goals_snapshot()["progress"]}["high_quality"]
    check("FR-1102", "高质高效要求连续 24 个月 EBITDA 率与准点率同时达标",
          hq["achieved"] and hq["detail"]["streak"] == S.GOAL_MONTHS,
          str(hq["detail"]))

    g_month = S.Game(n_ai=0, with_player=True, seed=45)
    g_month.configure_mode("goals")
    g_month.apply("open_route", {"segments": ["PEK", "SHA"],
                                 "daily_flights": 1, "ac_type": "A320"})
    for _ in range(30):
        g_month.advance_day()
    last_month = g_month.player.monthly[-1] if g_month.player.monthly else {}
    check("FR-1102", "月报包含准点率与 EBITDA 率（供高质高效判定）",
          "on_time" in last_month and last_month["on_time"] >= 0.85
          and "ebitda_rate" in last_month, str(last_month))

    g_rate = S.Game(n_ai=1, with_player=True, seed=46)
    g_rate.configure_mode("goals")
    g_rate.day = S.GOAL_DEADLINE_DAYS
    g_rate.player.rank_score = 0.0
    g_rate.airlines[1].rank_score = 1000.0
    for gid in ("market_top3", "region_leader", "high_quality"):
        g_rate.goal_state[gid]["achieved"] = True
    g_rate._update_goals()
    settle = g_rate.settlement or {}
    check("FR-1103", "到期按达成个数结算：3/4 → B，并暂停对局",
          settle.get("rating") == "B" and settle.get("achieved_count") == 3
          and g_rate.paused and settle.get("scored"), str(settle))

    g_zero = S.Game(n_ai=3, with_player=True, seed=47)
    g_zero.configure_mode("goals")
    g_zero.day = S.GOAL_DEADLINE_DAYS
    g_zero.player.rank_score = 0.0
    for rival in g_zero.airlines[1:]:
        rival.rank_score = 1000.0
    g_zero._update_goals()
    zero = g_zero.settlement or {}
    check("FR-1103", "0/4 到期为 E 且不计分（未达成不打分）",
          zero.get("rating") == "E" and zero.get("achieved_count") == 0
          and not zero.get("scored"), str(zero))

    g_all = S.Game(n_ai=0, with_player=True, seed=48)
    g_all.configure_mode("goals")
    for gid, _, _ in S.GOAL_DEFS:
        g_all.goal_state[gid]["achieved"] = True
    g_all._update_goals()
    all_done = g_all.settlement or {}
    check("FR-1103", "四个目标全部达成时提前结算 A",
          all_done.get("kind") == "complete" and all_done.get("rating") == "A"
          and all_done.get("scored") and g_all.paused, str(all_done))

    g_bank = S.Game(n_ai=0, with_player=True, seed=49)
    g_bank.configure_mode("goals")
    g_bank.player.alive = False
    g_bank._update_goals()
    bank = g_bank.settlement or {}
    check("FR-1103", "破产结束目标模式且不计分",
          bank.get("kind") == "bankrupt" and bank.get("failed")
          and not bank.get("scored"), str(bank))

    payload = json.loads(json.dumps(g_rate.to_save(), ensure_ascii=False))
    restored = S.Game.from_save(payload)
    check("FR-1103", "目标模式/期限/进度/结算随存档往返",
          restored.mode == "goals"
          and restored.goal_deadline_day == S.GOAL_DEADLINE_DAYS
          and restored.goal_state["market_top3"]["achieved"]
          and restored.settlement.get("rating") == "B",
          str(restored.settlement))

    # ---------- FR-307 座位门槛 ----------
    # 构造「5 座、极低票价（高效用）」的占位产品，验证它不会稀释分母、压制对手份额
    def synth(seats_tiny):
        big_al = S.Airline("BIG", world, 5000.0, "SHA")
        tiny_al = S.Airline("TINY", world, 5000.0, "PEK")

        def prod(al, seats, price):
            return {"airline": al, "route": None, "type": "direct", "seats": seats,
                    "price": price, "time_h": 2.0, "freq": 1.1, "hub": 0.0,
                    "stops": 0, "transfers": 0, "i": 0, "j": 0, "km": 1900.0,
                    "cabin": "eco", "rep": 50.0, "legs": []}

        items = [prod(big_al, 200.0, 1500.0)]
        if seats_tiny is not None:
            items.append(prod(tiny_al, seats_tiny, 100.0))   # 极低价，若不设门槛会抢走大量份额
        return {("北京", "广州"): {"eco": items}}, big_al, tiny_al

    orig_bp = MKT.build_products
    try:
        MKT.build_products = lambda w, a: synth(None)[0]
        alloc_without, _ = S.allocate(world, [S.Airline("X", world, 1.0, "PEK")], params)
        pax_without = alloc_without[("BIG", "eco")]["pax"]

        MKT.build_products = lambda w, a: synth(5.0)[0]
        alloc_with, _ = S.allocate(world, [S.Airline("X", world, 1.0, "PEK")], params)
        pax_with = alloc_with[("BIG", "eco")]["pax"]
        tiny_pax = alloc_with[("TINY", "eco")]["pax"]
    finally:
        MKT.build_products = orig_bp

    check("FR-307", "5 座占位产品不改变对手份额（不进入分母）",
          abs(pax_with - pax_without) < 1e-6, f"无占位 {pax_without:.1f} vs 有占位 {pax_with:.1f}")
    check("FR-307", "被排除的占位产品承运客流为 0", tiny_pax < 1e-9, f"{tiny_pax:.3f}")

    # 对照：座位足够时它应当正常参与竞争
    try:
        MKT.build_products = lambda w, a: synth(60.0)[0]
        alloc_ok, _ = S.allocate(world, [S.Airline("Y", world, 1.0, "PEK")], params)
        pax_ok = alloc_ok[("BIG", "eco")]["pax"]
    finally:
        MKT.build_products = orig_bp
    check("FR-307", "座位 ≥ 30 时该产品正常参与，对手份额下降",
          pax_ok < pax_without - 1e-6, f"对手 {pax_without:.1f} → {pax_ok:.1f}")

    # ---------- 公司名称（UI 编辑入口） ----------
    g = S.Game(n_ai=0, with_player=True, seed=7)
    r = g.apply("rename_airline", {"name": "云翼航空"})
    check("UI-01", "玩家可以修改公司名称",
          r.get("ok") and g.player.name == "云翼航空"
          and g.snapshot()["player"]["name"] == "云翼航空",
          str(r))
    r_bad = g.apply("rename_airline", {"name": " "})
    check("UI-01", "空公司名称被拒绝", not r_bad.get("ok"), str(r_bad))

    # ---------- 航线数据看板 ----------
    g2 = S.Game(n_ai=0, with_player=True, seed=8)
    opened = g2.apply("open_route", {"segments": ["PEK", "SHA"],
                                     "daily_flights": 1, "ac_type": "A320"})
    g2.advance_day()
    route = g2.snapshot()["player"]["routes"][0] if opened.get("ok") else {}
    check("UI-02", "航线看板返回客流、距离、收入、成本与利润率",
          route.get("pax", 0) > 0 and route.get("distance_km", 0) > 1000
          and route.get("revenue_M", 0) > 0 and route.get("cost_M", 0) > 0
          and route.get("margin") is not None, str(route))
    check("UI-02", "航线利润率与收入/成本一致",
          route and abs(route["margin"] - route["profit_M"] / route["revenue_M"]) < 0.002,
          str(route.get("margin")))
    check("UI-02", "玩家航线带 OD 票价，口径与对手一致（R-632）",
          route.get("prices") and any(
              abs(p["eco"] - round(g2.world.p_ref(
                      g2.world.dist(g2.world.airports[p["from"]]["city"],
                                    g2.world.airports[p["to"]]["city"]), "eco")
                  * route["price_index"])) <= max(2, p["eco"] * 0.001)
              and p["biz"] > p["eco"] for p in route["prices"]),
          str(route.get("prices")))

    # ---------- 换机型（航线管理） ----------
    g6 = S.Game(n_ai=0, with_player=True, seed=12)
    g6.apply("open_route", {"segments": ["PEK", "SHA"], "daily_flights": 1,
                            "ac_type": "A320"})
    g6.apply("buy_aircraft", {"ac_type": "A333", "base": "PEK", "lease": True})
    rid6 = g6.player.routes[0].rid
    r_ok = g6.apply("set_aircraft", {"route_id": rid6, "ac_type": "A333"})
    check("UI-05", "航线可以在机队已有型号之间换机型",
          r_ok.get("ok") and g6.player.routes[0].ac_type == "A333"
          and g6.snapshot()["player"]["routes"][0]["ac_type"] == "A333", str(r_ok))
    r_same = g6.apply("set_aircraft", {"route_id": rid6, "ac_type": "A333"})
    check("UI-05", "换成同一机型是空操作",
          r_same.get("ok") and not r_same.get("changed"), str(r_same))
    r_missing = g6.apply("set_aircraft", {"route_id": rid6, "ac_type": "B789"})
    check("UI-05", "机队没有的机型被拒绝",
          not r_missing.get("ok") and "机队没有" in str(r_missing.get("reason")),
          str(r_missing))
    r_unknown = g6.apply("set_aircraft", {"route_id": rid6, "ac_type": "XXXX"})
    check("UI-05", "不存在的机型被拒绝", not r_unknown.get("ok"), str(r_unknown))

    # ---------- 成本分项与利用率（解释「航线都赚、公司却亏」） ----------
    g7 = S.Game(n_ai=0, with_player=True, seed=13)
    g7.apply("open_route", {"segments": ["PEK", "SHA"], "daily_flights": 1,
                            "ac_type": "A320"})
    g7.advance_day()
    pl7 = g7.snapshot()["player"]
    c7 = pl7.get("costs") or {}
    need = {"fuel", "landing", "nav", "maint", "depreciation", "lease", "staff",
            "distribution", "ground", "hub_fixed", "interest", "idle",
            "fixed_total", "total"}
    check("UI-06", "快照给出成本分项与固定开销合计",
          need <= set(c7) and abs(
              c7["fixed_total"] - (c7["staff"] + c7["hub_fixed"] + c7["depreciation"]
                                   + c7["lease"] + c7["interest"] + c7["idle"])) <= 0.002,
          str({k: c7.get(k) for k in ("staff", "hub_fixed", "depreciation", "lease", "fixed_total")}))
    cap7 = pl7.get("capacity") or {}
    check("UI-06", "快照给出机队利用率（占机小时与航段）",
          cap7.get("hours_cap", 0) > 0 and 0 < cap7.get("hours_used", 0) <= cap7["hours_cap"]
          and cap7.get("segments_cap", 0) > 0, str(cap7))

    # ---------- 运力按机型分池（E190 空闲不能被 A320 借用） ----------
    g8 = S.Game(n_ai=0, with_player=True, seed=14)
    for segs in (["PEK", "SHA"], ["PEK", "CAN"], ["PEK", "CTU"]):
        g8.apply("open_route", {"segments": segs, "daily_flights": 1, "ac_type": "A320"})
    r_full = g8.apply("open_route", {"segments": ["PEK", "XIY"],
                                     "daily_flights": 1, "ac_type": "A320"})
    check("UI-07", "A320 运力按机型封顶，超出时报该机型运力不足",
          not r_full.get("ok") and "A320 运力不足" in str(r_full.get("reason")),
          str(r_full))
    g8.apply("buy_aircraft", {"ac_type": "E190", "base": "PEK", "lease": True})
    r_e = g8.apply("open_route", {"segments": ["PEK", "DLC"],
                                  "daily_flights": 1, "ac_type": "E190"})
    check("UI-07", "空闲的 E190 可以单独开线（A320 满员也能开）",
          r_e.get("ok"), str(r_e))
    r_unknown = g8.apply("open_route", {"segments": ["PEK", "SHA"],
                                        "daily_flights": 1, "ac_type": "B789"})
    check("UI-07", "机队没有的机型不能开线",
          not r_unknown.get("ok") and "机队没有 B789" in str(r_unknown.get("reason")),
          str(r_unknown))
    g8.apply("buy_aircraft", {"ac_type": "A333", "base": "PEK", "lease": True})
    r_runway = g8.apply("open_route", {"segments": ["PEK", "LXA"],
                                       "daily_flights": 1, "ac_type": "A333"})
    check("UI-07", "跑道等级按「机型 ≤ 机场」判定：宽体不能落 S 级机场",
          not r_runway.get("ok") and "跑道等级" in str(r_runway.get("reason")),
          str(r_runway))

    # 机场 × 机型双维度：飞机在哪个机场，就只能从那里起飞（否则等于瞬移）
    r_far = g8.apply("open_route", {"segments": ["SHA", "PEK"],
                                    "daily_flights": 1, "ac_type": "E190"})
    check("UI-07", "基地不在 SHA 时不能在 SHA 开线",
          not r_far.get("ok") and "SHA 的 E190" in str(r_far.get("reason")), str(r_far))
    # 先租一架闲置的 E190（前面那架已经在飞 PEK 航线，不能调走）
    fresh = g8.apply("buy_aircraft", {"ac_type": "E190", "base": "PEK", "lease": True})
    e_id = fresh.get("aircraft_id")
    r_rb = g8.apply("rebase_aircraft", {"aircraft_id": e_id, "base": "SHA"})
    r_after = g8.apply("open_route", {"segments": ["SHA", "PEK"],
                                      "daily_flights": 1, "ac_type": "E190"})
    check("UI-07", "调机到 SHA 后可以在 SHA 开线",
          r_rb.get("ok") and r_after.get("ok"), str(r_rb) + " / " + str(r_after))

    # ---------- AI 公开航线网络 ----------
    g3 = S.Game(n_ai=3, with_player=True, seed=11)
    for _ in range(10):
        g3.advance_day()
    snap3 = g3.snapshot()
    opp = snap3.get("opponent_routes", [])
    check("UI-03", "AI 航线以公开字段进入快照",
          len(opp) > 0 and all(
              {"airline", "segments", "daily_flights", "ac_type", "lf"} <= set(r)
              for r in opp), f"{len(opp)} 条")
    check("UI-03", "AI 航线公开价格指数与各 OD 票价",
          all("price_index" in r and r["prices"] for r in opp),
          f"{sum(len(r.get('prices') or []) for r in opp)} 个 OD")
    check("UI-03", "公开票价 = 参考价 × 价格指数（R-632）",
          all(abs(p["eco"] - round(g3.world.p_ref(
                  g3.world.dist(g3.world.airports[p["from"]]["city"],
                                g3.world.airports[p["to"]]["city"]), "eco") * r["price_index"]))
              <= max(2, p["eco"] * 0.001)
              and p["biz"] > p["eco"]
              for r in opp for p in r["prices"]))
    check("UI-03", "AI 航线快照仍不泄露成本、收入与利润",
          all(not ({"cost", "cost_M", "revenue", "revenue_M", "profit", "profit_M",
                    "margin"} & set(r)) for r in opp))

    # ---------- 侧栏「竞争对手」口径（FR-1002） ----------
    g5 = S.Game(n_ai=30, with_player=True, seed=31)
    g5.player.rank_score = 1e9        # 把玩家顶到第 1 名，验证不会把自己当对手
    snap5 = g5.snapshot()
    rivals5 = snap5["rivals"]
    check("FR-1002", "对手榜不含本公司",
          g5.player.name not in [r["name"] for r in rivals5],
          str([r["name"] for r in rivals5][:3]))
    check("FR-1002", "对手榜最多 20 家并给出全量对手家数",
          len(rivals5) == 20 and snap5.get("rivals_total") == 30,
          f"{len(rivals5)} / {snap5.get('rivals_total')}")
    check("FR-1002", "对手名次沿用全体存活排名，与玩家名次同口径",
          snap5["player"]["rank"] == 1
          and [r["rank"] for r in rivals5] == list(range(2, 22)),
          str([r.get("rank") for r in rivals5][:3]))

    # ---------- 卖机 / 退租的运力约束 ----------
    g9 = S.Game(n_ai=0, with_player=True, seed=15)
    g9.apply("open_route", {"segments": ["PEK", "SHA"], "daily_flights": 2,
                            "ac_type": "A320"})
    only_id = g9.player.fleet[0].id
    r_sell = g9.apply("sell_aircraft", {"aircraft_id": only_id})
    check("UI-08", "有航线在飞时不能卖掉唯一一架该基地的飞机",
          not r_sell.get("ok") and "运力会被吃穿" in str(r_sell.get("reason")),
          str(r_sell))

    g10 = S.Game(n_ai=0, with_player=True, seed=16)
    lease = g10.apply("buy_aircraft", {"ac_type": "E190", "base": "PEK", "lease": True})
    lid = lease.get("aircraft_id")
    cash_before = g10.player.cash
    deposit = g10.player.lease_deposit("E190")
    r_ret = g10.apply("sell_aircraft", {"aircraft_id": lid})
    check("UI-08", "租赁机是退租而不是出售：只退押金，不产生二手收入",
          r_ret.get("ok") and r_ret.get("kind") == "return"
          and abs((g10.player.cash - cash_before) - deposit) < 1e-6
          and not any(a.id == lid for a in g10.player.fleet),
          f"{r_ret} / 押金 {deposit:.2f} / 现金变化 {g10.player.cash - cash_before:.2f}")

    # ---------- 存档 / 读档 ----------
    g4 = S.Game(n_ai=2, with_player=True, seed=21)
    g4.apply("open_route", {"segments": ["PEK", "SHA"],
                            "daily_flights": 2, "ac_type": "A320"})
    for _ in range(7):
        g4.advance_day()
    before = g4.snapshot()
    loaded = S.Game.from_save(json.loads(json.dumps(g4.to_save(), ensure_ascii=False)))
    after = loaded.snapshot()
    p_before, p_after = before["player"]["routes"][0], after["player"]["routes"][0]
    check("UI-04", "存档读档保留日期、公司、航线与现金流",
          loaded.day == g4.day
          and loaded.player.name == g4.player.name
          and abs(loaded.player.cash - g4.player.cash) < 1e-9
          and p_after["segments"] == p_before["segments"]
          and abs(p_after["margin"] - p_before["margin"]) < 1e-9)
    g4.advance_day()
    loaded.advance_day()
    check("UI-04", "读档后继续推进与未中断对局一致",
          loaded.day == g4.day
          and abs(loaded.player.cash - g4.player.cash) < 1e-9
          and len(loaded.airlines) == len(g4.airlines))

    # ---------- 汇总 ----------
    print("\n" + "=" * 60)
    print(f"通过 {len(PASS)} / {len(PASS) + len(FAIL)}")
    if FAIL:
        print("失败项：")
        for fr, desc, detail in FAIL:
            print(f"  [{fr}] {desc}  {detail}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
