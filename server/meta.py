# -*- coding: utf-8 -*-
"""/api/meta 的响应体：机场库、机型库、规则参数、目标定义。"""

from paths import S

def build_meta(game):
    w = game.world
    return {
        "airports": [
            {"iata": a["iata"], "city": a["city"], "region": a["region"],
             "scale": a["scale"], "lat": a["lat"], "lon": a["lon"],
             "pax": a["pax"], "runway": a["runway"], "slot_cap": a["slot_cap"]}
            for a in w.airports.values()
        ],
        "aircraft": list(w._aircraft_types.values()),
        "params": {
            "region_factor": game.params["region_factor"],
            "price": game.params["price"],
            "scale_weight": game.params["scale"]["weight"],
        },
        "stop_rules": S.STOP,
        "flight_rules": {k: v for k, v in S.FLIGHT.items() if k != "turnaround_min"},
        "cabins": {"经济": 1.0, "商务": 2.6, "头等": 4.5},
        "goals": [{"id": gid, "name": name, "condition": cond}
                  for gid, name, cond in S.GOAL_DEFS],
        "goal_years": S.GOAL_YEARS,
        "days_per_year": S.DAYS_PER_YEAR,
        "goal_deadline_days": S.GOAL_DEADLINE_DAYS,
        "modes": [
            {"id": "sandbox", "name": "沙盒模式", "desc": "无终点，随时存档退出"},
            {"id": "goals", "name": "目标模式",
             "desc": f"{S.GOAL_YEARS} 游戏年内同时追踪四个目标，到期结算 A–E"},
        ],
    }

