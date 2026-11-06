# -*- coding: utf-8 -*-
"""批量模拟与报告：run / summarize / write_report / CLI。

由 sim/simulate.py 拆分而来；只允许依赖更靠前的分层，不要反向 import。
"""

import argparse
from collections import defaultdict
from config import ECON, KNOWN_GAPS, ROOT
from game import Game
from goals import evaluate_goals
from products import cabin_split_for


def run(days, n_ai, seed=42, verbose=True, start_cash=1500.0):
    """批量模拟入口（保留旧签名，供报告与回归使用）"""
    g = Game(n_ai=n_ai, seed=seed, start_cash=start_cash, with_player=False)
    for _ in range(days):
        g.advance_day()
        if verbose and g.day % 90 == 0 and g.snapshots:
            s = g.snapshots[-1]
            print(f"[day {s['day']:4d}] 存活 {s['alive']:2d}  航线 {s['routes']:3d}  "
                  f"机队 {s['fleet']:3d}  客流 {s['pax']:8.0f}  "
                  f"收入 {s['rev']:8.1f} ¥M  现金 {s['cash']:9.1f} ¥M")
    return g.world, g.airlines, g.snapshots


def summarize(world, airlines):
    alive = [a for a in airlines if a.alive]
    rows = []
    for a in alive:
        h = a.history[-1]
        rows.append({
            "name": a.name, "hub": a.hubs[0] if a.hubs else "-",
            "routes": len(a.routes), "fleet": len(a.fleet),
            "pax": h["pax"], "rev": h["revenue"], "cost": h["cost"],
            "ebitda": h["ebitda"], "cash": a.cash, "debt": a.debt,
            "cap": a.rank_score,
            "lf": (sum(r.lf_ewma for r in a.routes) / len(a.routes)) if a.routes else 0.0,
            "rep": a.rep,
            "avg_age": a.avg_age(),
            "op_hours": a.total_hours(), "cap_hours": a.capacity_hours(),
        })
    rows.sort(key=lambda x: -x["cap"])

    # 网络层面：按 OD 统计在营单程座位
    seats = defaultdict(float)
    route_cap = 0.0
    route_pax_est = 0.0
    for a in alive:
        for r in a.routes:
            t = world.ac(r.ac_type)
            split = cabin_split_for(t)
            n = r.n_segments
            cap_seg = r.daily_flights * t["seats"] * sum(split.values())
            route_cap += cap_seg * n
            route_pax_est += cap_seg * n * r.lf_ewma
            for i in range(n):
                for j in range(i, n):
                    ca = world.airports[r.segments[i]]["city"]
                    cb = world.airports[r.segments[j + 1]]["city"]
                    key = (ca, cb) if ca < cb else (cb, ca)
                    seats[key] += cap_seg
    tot_seats = route_cap
    tot_pax = sum(r["pax"] for r in rows)
    return rows, seats, tot_seats, tot_pax, route_pax_est


def write_report(world, airlines, snaps, path):
    rows, seats, tot_seats, tot_pax, route_pax_est = summarize(world, airlines)
    L = []
    A = L.append
    A("# 模拟内核运行报告（v0.1 跑通版）\n")
    A(f"> 自动生成。模拟 {snaps[-1]['day']} 游戏日，{len(airlines)} 家 AI 航空公司。\n")
    A("## 1. 总体结果\n")
    A("| 指标 | 数值 |")
    A("|---|---|")
    A(f"| 存活公司 | {len(rows)} / {len(airlines)} |")
    A(f"| 总航线条数 | {sum(r['routes'] for r in rows)} |")
    A(f"| 总机队 | {sum(r['fleet'] for r in rows)} 架 |")
    stop_n = sum(1 for a in [x for x in airlines if x.alive] for r in a.routes if r.n_segments >= 2)
    stop3 = sum(1 for a in [x for x in airlines if x.alive] for r in a.routes if r.n_segments >= 3)
    A(f"| 经停航线 | {stop_n} 条（2 段 {stop_n - stop3} / 3 段 {stop3}），"
      f"占全部航线的 {stop_n / max(1, sum(r['routes'] for r in rows)):.0%} |")
    A(f"| 日客流 | {tot_pax:,.0f} 人次/日（单向，含中转运送） |")
    A(f"| 日单向座位供给 | {tot_seats:,.0f} 座 |")
    A(f"| 全网平均载客率 | {route_pax_est / tot_seats:.1%} |" if tot_seats else "| 平均载客率 | - |")
    A(f"| 日收入 | {sum(r['rev'] for r in rows):,.1f} ¥M |")
    A(f"| 日成本 | {sum(r['cost'] for r in rows):,.1f} ¥M |")
    A(f"| 日 EBITDA | {sum(r['ebitda'] for r in rows):,.2f} ¥M |")
    A(f"| 现金合计 | {sum(r['cash'] for r in rows):,.1f} ¥M |")
    A("")
    A("## 2. 公司排行\n")
    A("| # | 公司 | HUB | 航线 | 机队 | 日客流 | 日收入 | 日EBITDA | 载客率 | 口碑 | 机龄 | 占机/容量 h | 市值 |")
    A("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for i, r in enumerate(rows[:12], 1):
        A(f"| {i} | {r['name']} | {r['hub']} | {r['routes']} | {r['fleet']} | {r['pax']:,.0f} | "
          f"{r['rev']:,.1f} | {r['ebitda']:,.2f} | {r['lf']:.0%} | {r['rep']:.1f} | "
          f"{r['avg_age']:.1f} | {r['op_hours']:.0f}/{r['cap_hours']:.0f} | {r['cap']:,.0f} |")
    A("")
    A("## 3. 需求最大的 15 个城市对（按在营座位）\n")
    A("| # | 城市对 | 在营单向座位/日 | 需求池（单向人次/日） | 座位/需求 |")
    A("|---|---|---|---|---|")
    for i, (k, v) in enumerate(sorted(seats.items(), key=lambda x: -x[1])[:15], 1):
        _, air = world.demand_air(*k)
        A(f"| {i} | {k[0]}–{k[1]} | {v:,.0f} | {air:,.0f} | {v / air:.2f} |" if air > 0 else "")
    A("")
    A("## 4. 票价与载客率分布\n")
    ratios, lfs = [], []
    for a in [x for x in airlines if x.alive]:
        for r in a.routes:
            if r.total_km() <= 0:
                continue
            ratios.append(r.price_index)
            lfs.append(r.lf_ewma)
    if ratios:
        ratios.sort()
        A("| 指标 | 数值 |")
        A("|---|---|")
        A(f"| 航线数 | {len(ratios)} |")
        A(f"| 票价 / 参考价 中位数 | {ratios[len(ratios) // 2]:.2f} |")
        A(f"| 票价 / 参考价 区间 | {ratios[0]:.2f} – {ratios[-1]:.2f} |")
        A(f"| 载客率 中位数 | {sorted(lfs)[len(lfs) // 2]:.1%} |")
        A(f"| 售罄航线（LF ≥ 95%）占比 | {sum(1 for x in lfs if x >= 0.95) / len(lfs):.0%} |")
        A(f"| 空座较多（LF < 60%）占比 | {sum(1 for x in lfs if x < 0.60) / len(lfs):.0%} |")
        A("")
    A("## 5. 时间序列快照\n")
    A("| 日 | 存活 | 航线 | 机队 | 日客流 | 日收入 ¥M | 现金 ¥M |")
    A("|---|---|---|---|---|---|---|")
    for s in snaps:
        if s["day"] % 90 == 0 or s["day"] == 1:
            A(f"| {s['day']} | {s['alive']} | {s['routes']} | {s['fleet']} | "
              f"{s['pax']:,.0f} | {s['rev']:,.1f} | {s['cash']:,.0f} |")
    A("")
    A("## 6. 破产与收缩\n")
    dead = [a for a in airlines if not a.alive]
    A(f"- 破产公司：**{len(dead)} / {len(airlines)}**")
    A(f"- 累计收缩次数（关线 + 卖机）：{sum(a.contractions for a in airlines)}")
    A(f"- 清算资产流入二手市场：{world.secondhand_proceeds:,.1f} ¥M")
    if dead:
        A("")
        A("| 公司 | 破产日 | 原因 | 累计收缩 |")
        A("|---|---|---|---|")
        for a in sorted(dead, key=lambda x: x.dead_day or 0):
            A(f"| {a.name} | {a.dead_day} | {a.dead_reason} | {a.contractions} |")
    A("")
    A("## 7. 月报表（最近 6 个月，市值第一的公司）\n")
    if rows:
        top_al = next(a for a in airlines if a.name == rows[0]["name"])
        if top_al.monthly:
            A("| 月份末 | 客流 | 收入 ¥M | 成本 ¥M | EBITDA ¥M | EBITDA率 | 机队 | 航线 |")
            A("|---|---|---|---|---|---|---|---|")
            for m in top_al.monthly[-6:]:
                rate = m["ebitda"] / m["revenue"] if m["revenue"] > 0 else 0.0
                A(f"| D{m['day']} | {m['pax']:,.0f} | {m['revenue']:,.1f} | {m['cost']:,.1f} | "
                  f"{m['ebitda']:,.2f} | {rate:.1%} | {m['fleet']} | {m['routes']} |")
            A("")
    A("## 8. 目标与评级\n")
    goals, rating = evaluate_goals(world, airlines, snaps[-1]["day"])
    A(f"- 综合评级：**{rating}**")
    A(f"- 时刻回收（FR-404）：{getattr(world, 'slots_reclaimed', 0)} 次")
    A(f"- HUB 机场数：{len(world.hub_airports)}")
    A("")
    if goals:
        A("| 目标 | 达成 |")
        A("|---|---|")
        for name, ok in goals:
            A(f"| {name} | {'✅' if ok else '—'} |")
        A("")
    A("## 9. 未实现（已知缺口）\n")
    for g in KNOWN_GAPS:
        A(f"- {g}")
    A("")
    A("> 参数集中在 `simulate.py` 顶部的 `ECON` / `FLIGHT` / `STOP` 三个字典，hotfix 直接改这里。\n")
    path.write_text("\n".join(L), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=360)
    ap.add_argument("--ai", type=int, default=12)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--cash", type=float, default=1500.0, help="每家起始资金 ¥M")
    ap.add_argument("--cost-mult", type=float, default=1.0,
                    help="成本压力系数（1.0 为标定基准；>1.2 用于加压测试与验证破产路径）")
    args = ap.parse_args()
    if args.cost_mult != 1.0:
        for k in ("fuel_price_per_kg", "landing_base_M", "nav_rate_M_per_km",
                  "staff_base_M_day", "staff_per_aircraft_M_day", "staff_per_segment_M_day",
                  "ground_per_pax_M", "idle_cost_M_day"):
            ECON[k] *= args.cost_mult
        for k in ECON["hub_fixed_by_scale"]:
            ECON["hub_fixed_by_scale"][k] *= args.cost_mult
        ECON["distribution_pct"] = min(0.30, ECON["distribution_pct"] * args.cost_mult)
        print(f"[difficulty] 成本系数 ×{args.cost_mult}")
    world, airlines, snaps = run(args.days, args.ai, args.seed, start_cash=args.cash)
    write_report(world, airlines, snaps, ROOT / "run_report.md")
    print("\n=== 期末 ===")
    print(f"存活 {sum(1 for a in airlines if a.alive)} / {len(airlines)}")
    for a in sorted([x for x in airlines if x.alive], key=lambda x: -x.rank_score)[:5]:
        h = a.history[-1]
        print(f"{a.name:8s} HUB {a.hubs[0] if a.hubs else '-':4s} 市值 {a.rank_score:9.1f}  "
              f"现金 {a.cash:8.1f}  航线 {len(a.routes):2d}  机队 {len(a.fleet):2d}  "
              f"日客流 {h['pax']:6.0f}  日EBITDA {h['ebitda']:6.2f}")
    print("\n报告已写入 sim/run_report.md")
    print("已知缺口：")
    for g in KNOWN_GAPS:
        print(" -", g)


if __name__ == "__main__":
    main()

