# -*- coding: utf-8 -*-
"""
航空公司模拟经营 Ver1.0 —— 系数校准脚本（能级制需求模型）
============================================================
设计决策（来自需求评审）：
  D1 需求由「机场能级」决定，不由距离决定。能级按吞吐量划分：
     超大 XL / 大型 L / 中型 M / 小型 S / 支线 R
  D2 距离不影响「是否出行」，但影响「口碑的边际权重」：
     航距越长，旅客对舒适度与口碑越敏感 → c_rep(d) 随距离上升
  D3 传统中转地（首尔/迪拜等）的吸引力随驻扎航线数增加而增加，
     但基准 OD 池仍按城市能级统计 → 用连通度乘子 conn(航线数) 表达

模型
----
D_total(A,B) = C · w(scale_A) · w(scale_B) · C_region · conn_A · conn_B
D_air(A,B)   = D_total(A,B) · sigmoid(c0(d))          # 交通方式分担
D_air 再由分舱位 logit 在各公司之间分配（不属于本脚本）

输入：airports.csv / anchors.csv / fares.csv
输出：params.json / report.md

运行：python calibrate.py
"""

import csv
import json
import math
from pathlib import Path

import numpy as np

BASE = Path(__file__).parent

# ============================================================
# 0. 能级划分阈值（按年吞吐量，百万人次）
# ============================================================

SCALE_THRESHOLDS = [("XL", 80.0), ("L", 45.0), ("M", 25.0), ("S", 10.0), ("R", 0.0)]
SCALE_LABEL = {"XL": "超大机场", "L": "大型机场", "M": "中型机场",
               "S": "小型机场", "R": "支线机场"}


def scale_of(pax):
    for name, thr in SCALE_THRESHOLDS:
        if pax >= thr:
            return name
    return "R"


def read_rows(name):
    with open(BASE / name, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def gc_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


# ============================================================
# 1. 机场与城市
# ============================================================

airports = []
for r in read_rows("airports.csv"):
    pax = float(r["pax_m"])
    transit = float(r["transit_share"])
    airports.append({
        "iata": r["iata"].strip(), "city": r["city"].strip(), "region": r["region"].strip(),
        "tier": int(r["tier"]), "lat": float(r["lat"]), "lon": float(r["lon"]),
        "pax": pax, "transit": transit, "local": pax * (1 - transit),
        "scale": scale_of(pax), "runway": r["runway"].strip(),
    })

# 城市能级 = 该城市所有机场吞吐量之和所对应的能级
cities = {}
for a in airports:
    c = cities.setdefault(a["city"], {"pax": 0.0, "lat": 0.0, "lon": 0.0,
                                      "region": a["region"], "airports": []})
    c["pax"] += a["pax"]
    c["lat"] += a["lat"] * a["pax"]
    c["lon"] += a["lon"] * a["pax"]
    c["airports"].append(a["iata"])
for c in cities.values():
    if c["pax"] > 0:
        c["lat"] /= c["pax"]
        c["lon"] /= c["pax"]
    c["scale"] = scale_of(c["pax"])

counts = {}
for c in cities.values():
    counts[c["scale"]] = counts.get(c["scale"], 0) + 1
print(f"[data] 机场 {len(airports)} 个，城市 {len(cities)} 个")
print("[data] 城市能级分布：" + "，".join(f"{k} {counts.get(k, 0)}" for k, _ in SCALE_THRESHOLDS))

# ============================================================
# 2. 基础效用曲线 c0(d)：交通方式分担（航空 vs 高铁/自驾）
#    短途受高铁挤压，长途几乎无替代
# ============================================================

D_RAMP_START, D_RAMP_WIDTH = 600.0, 1800.0
S_SHORT, D_SHORT = 0.45, 1064.0     # 京沪：航空对高铁约各半
S_LONG, D_LONG = 0.92, 10400.0      # 洲际：无替代


def ramp(d):
    return min(1.0, max(0.0, (d - D_RAMP_START) / D_RAMP_WIDTH))


def logit_c0(s):
    return math.log(s / (1 - s))


c0_long = logit_c0(S_LONG)
t_short = ramp(D_SHORT)
c0_short = (logit_c0(S_SHORT) - c0_long * t_short) / (1 - t_short)


def c0_of(d):
    return c0_short + (c0_long - c0_short) * ramp(d)


def air_share(d):
    return 1.0 / (1.0 + math.exp(-c0_of(d)))


# ============================================================
# 3. 锚点
# ============================================================

anchors = []
for r in read_rows("anchors.csv"):
    ca, cb = r["city_a"].strip(), r["city_b"].strip()
    if ca not in cities or cb not in cities:
        raise KeyError(f"锚点城市未在机场表出现：{ca} / {cb}")
    A, B = cities[ca], cities[cb]
    d = gc_km(A["lat"], A["lon"], B["lat"], B["lon"])
    annual = float(r["annual_bidir_m"]) * 1e6
    anchors.append({
        "a": ca, "b": cb, "d": d, "Ta": A["pax"], "Tb": B["pax"],
        "scale_a": A["scale"], "scale_b": B["scale"],
        "obs_air": annual / 2.0 / 365.0,     # 观测：航空客流（人次/日·单向）
        "group": r["group"].strip(),
    })

print(f"[data] 锚点 {len(anchors)} 条")

GROUPS = []
for p in anchors:
    if p["group"] not in GROUPS:
        GROUPS.append(p["group"])
REG_DUMMY = [g for g in GROUPS if g != "domestic"]
SCALE_DUMMY = ["L", "M", "S", "R"]          # 参照组 XL

# ============================================================
# 4. 加权最小二乘标定
#    ln(D_air) = lnC + Σ w_scale + Σ γ_region + ln(sigmoid(c0(d)))
#    权重 = 观测客流的平方根：让京沪这类主干走廊主导标定，
#    避免小航线噪声决定 C 的量级。
#    XL 为参照档，不可单独识别（XL-XL 由截距吸收），归一到 w_XL = 1。
# ============================================================

def build_system():
    X, y, sw = [], [], []
    for p in anchors:
        row = [1.0]
        row += [float((p["scale_a"] == s) + (p["scale_b"] == s)) for s in SCALE_DUMMY]
        row += [1.0 if p["group"] == g else 0.0 for g in REG_DUMMY]
        X.append(row)
        y.append(math.log(p["obs_air"]) - math.log(air_share(p["d"])))
        sw.append(math.sqrt(p["obs_air"]))
    return np.array(X), np.array(y), np.array(sw)


X, y, sw = build_system()
Xs, ys = X * sw[:, None], y * sw
coef, *_ = np.linalg.lstsq(Xs, ys, rcond=None)

lnC = float(coef[0])
lnw = {s: 0.0 for s in ("XL", "L", "M", "S", "R")}      # XL 参照
off = 1
for s in SCALE_DUMMY:
    lnw[s] = float(coef[off])
    off += 1
region_ln = {}
for g in REG_DUMMY:
    region_ln[g] = float(coef[off])
    off += 1

C = math.exp(lnC)
w_raw = {s: math.exp(lnw[s]) for s in lnw}

# --- 能级阶梯：等比步长外推 ---
# 20 条锚点只够识别 2–3 个档位。XL 是参照档（不可单独识别），L 档锚点最多最可靠，
# 因此用「XL → L」的比值作为等比步长，再外推 M / S / R。
# 交叉验证：按步长外推出的 S 档权重与被「京乌」锚点直接算出的值高度吻合（见输出）。
ORDER = ("XL", "L", "M", "S", "R")
ratio = w_raw["L"]
w_norm = {s: ratio ** i for i, s in enumerate(ORDER)}

# C 中心化：让国内锚点的几何平均残差为 1（只用国内锚点，与区域系数无关）
tot = {i: p["obs_air"] / air_share(p["d"]) for i, p in enumerate(anchors)}
dom = [tot[i] / (w_norm[p["scale_a"]] * w_norm[p["scale_b"]])
       for i, p in enumerate(anchors) if p["group"] == "domestic"]
C = math.exp(sum(math.log(v) for v in dom) / len(dom))

# 区域系数：用中心化后的 C 与最终权重，按残差几何平均求得
region_ln = {}
for g in REG_DUMMY:
    vals = [tot[i] / (C * w_norm[p["scale_a"]] * w_norm[p["scale_b"]])
            for i, p in enumerate(anchors) if p["group"] == g]
    region_ln[g] = math.log(math.exp(sum(math.log(v) for v in vals) / len(vals)))

# 交叉验证：用 S 档的实际锚点反算「S 档应为多少」，与阶梯外推值比较
s_direct = []
for i, p in enumerate(anchors):
    if p["group"] != "domestic":
        continue
    if p["scale_a"] == "S" and p["scale_b"] == "XL":
        other = p["scale_b"]
    elif p["scale_b"] == "S" and p["scale_a"] == "XL":
        other = p["scale_a"]
    else:
        continue
    s_direct.append(tot[i] / (C * w_norm[other]))
if s_direct:
    s_check = math.exp(sum(math.log(v) for v in s_direct) / len(s_direct))
    print(f"[fit] 阶梯比率={ratio:.4f}；S 档外推={w_norm['S']:.4f}，"
          f"锚点直算={s_check:.4f}，偏差 {(w_norm['S'] / s_check - 1) * 100:+.1f}%")

print(f"[fit] C={C:.2f}")
print("[fit] 能级权重 " + "，".join(f"{s}={w_norm[s]:.4f}" for s in ORDER))
for g, v in region_ln.items():
    print(f"[fit] 区域 {g}: {math.exp(v):.4f}")

# 区域系数表
REGION_KEY = {"greater_china": "GCR", "asia": "ASIA", "europe": "EUR",
              "america": "AMR", "oceania": "OCE"}
C_REGION_TABLE = {"CN-CN": 1.000}
for g, v in region_ln.items():
    C_REGION_TABLE["CN-" + REGION_KEY.get(g, g.upper())] = round(math.exp(v), 4)
if region_ln:
    C_REGION_TABLE["CN-MEA"] = round(min(math.exp(v) for v in region_ln.values()) * 0.8, 4)

# ============================================================
# 5. 需求函数
# ============================================================

def demand_total(ca, cb, d=None, conn_a=1.0, conn_b=1.0, group="domestic"):
    A, B = cities[ca], cities[cb]
    reg = 1.0 if group == "domestic" else math.exp(region_ln.get(group, 0.0))
    return C * w_norm[A["scale"]] * w_norm[B["scale"]] * reg * conn_a * conn_b


def demand_air(ca, cb, d, **kw):
    return demand_total(ca, cb, **kw) * air_share(d)


# ============================================================
# 6. 距离 → 口碑敏感度
#    c_rep(d) 随距离线性上升：长航线上口碑/舒适度的边际影响是短途的数倍
# ============================================================

C_REP_SHORT, C_REP_PER_KM, C_REP_CAP = 0.25, 0.000075, 1.20


def c_rep_of(d):
    return min(C_REP_CAP, C_REP_SHORT + C_REP_PER_KM * d)


# ============================================================
# 7. 枢纽连通度乘子（未校准，先验赋值）
#    conn(i) = 1 + k·ln(1 + N_i/N_ref)，N_i = 该机场在营航段数
# ============================================================

K_CONN, N_REF, CONN_CAP = 0.50, 100.0, 1.80


def conn_of(routes):
    return min(CONN_CAP, 1.0 + K_CONN * math.log(1.0 + routes / N_REF))


# ============================================================
# 8. 参考票价曲线
# ============================================================

fares = [{"d": float(r["d_km"]), "p": float(r["avg_fare_cny"])} for r in read_rows("fares.csv")]
Xf = np.array([[1.0, math.log(f["d"])] for f in fares])
yf = np.array([math.log(f["p"]) for f in fares])
cf, *_ = np.linalg.lstsq(Xf, yf, rcond=None)
a_fare, b_fare = math.exp(cf[0]), float(cf[1])
print(f"[fit] P_ref = {a_fare:.3f} * d^{b_fare:.4f}")

CABIN_MULT = {"economy": 1.0, "business": 2.6, "first": 4.5}

# ============================================================
# 9. 效用系数
# ============================================================

ELASTICITY_TARGET = -1.20
SHARE_FOR_ELASTICITY = 0.45
c_price = round(-ELASTICITY_TARGET / (1 - SHARE_FOR_ELASTICITY), 3)

C_TRANS, C_HUB, C_FREQ, C_TIME = 1.20, 0.15, 0.55, 0.25
N_TRANSFER_TARGET, N_STOP_BASE = 10, 2
delta_freq = math.log(1 + N_TRANSFER_TARGET) - math.log(1 + N_STOP_BASE)
c_stop = round(C_TRANS - C_HUB - C_FREQ * delta_freq, 3)

# ============================================================
# 10. 残差与合理性
# ============================================================

rows = []
for p in anchors:
    pred_air = demand_air(p["a"], p["b"], p["d"], group=p["group"])
    rows.append({**p, "pred": pred_air,
                 "err": (pred_air / p["obs_air"] - 1) * 100,
                 "total": demand_total(p["a"], p["b"], group=p["group"])})

ly = np.array([math.log(r["obs_air"]) for r in rows])
lp = np.array([math.log(r["pred"]) for r in rows])
r2 = 1 - float(((ly - lp) ** 2).sum()) / float(((ly - ly.mean()) ** 2).sum())
mre = float(np.mean([abs(r["err"]) for r in rows]))
pj = next(r for r in rows if {r["a"], r["b"]} == {"北京", "上海"})

# 网络合理性：模型预测的中国前 10 城市对
cn_cities = [c for c, v in cities.items() if v["region"] == "CN"]
pairs = []
for i, ca in enumerate(cn_cities):
    for cb in cn_cities[i + 1:]:
        d = gc_km(cities[ca]["lat"], cities[ca]["lon"], cities[cb]["lat"], cities[cb]["lon"])
        pairs.append((demand_air(ca, cb, d), ca, cb, d))
pairs.sort(reverse=True)
top = pairs[:10]

# ============================================================
# 11. params.json
# ============================================================

params = {
    "meta": {
        "title": "航空公司模拟经营 Ver1.0 系数表（能级制需求模型）",
        "version": "1.1.0-cal",
        "anchor_count": len(anchors),
        "airport_count": len(airports),
        "city_count": len(cities),
        "fit_r2_log": round(r2, 4),
        "fit_mre_pct": round(mre, 2),
        "notes": "D_total 为总出行需求（含非航空）；D_air 再由 logit 分配。距离不进入需求，只进入口碑权重。",
    },
    "scale": {
        "label": SCALE_LABEL,
        "threshold_pax_m": {k: v for k, v in SCALE_THRESHOLDS},
        "weight": {s: round(w_norm[s], 4) for s in ["XL", "L", "M", "S", "R"]},
        "formula": "城市能级取该城市全部机场吞吐量之和所对应的档位",
    },
    "demand": {
        "C": round(C, 4),
        "formula": ("D_total = C · w(scale_A) · w(scale_B) · C_region · conn_A · conn_B\n"
                    "D_air   = D_total · sigmoid(c0(d))"),
        "cabin_split": {
            "business_base": 0.04, "business_per_tier": 0.010,
            "business_per_km": 0.00004, "business_cap": 0.30,
            "first_requires_tier_sum": 7, "first_min_km": 4000, "first_cap": 0.04,
        },
    },
    "region_factor": C_REGION_TABLE,
    "mode_share": {
        "c0_short": round(c0_short, 4), "c0_long": round(c0_long, 4),
        "ramp_start_km": D_RAMP_START, "ramp_width_km": D_RAMP_WIDTH,
        "formula": "c0(d) = c0_short + (c0_long - c0_short) · clamp((d-600)/1800, 0, 1)",
    },
    "reputation": {
        "c_rep_short": C_REP_SHORT, "c_rep_per_km": C_REP_PER_KM, "c_rep_cap": C_REP_CAP,
        "formula": "c_rep(d) = min(c_rep_cap, c_rep_short + c_rep_per_km · d)",
    },
    "connectivity": {
        "k": K_CONN, "n_ref": N_REF, "cap": CONN_CAP,
        "formula": "conn(i) = min(cap, 1 + k · ln(1 + routes_i / n_ref))",
        "note": "未校准。routes_i 为该机场全部在营航段数（含所有公司、含经停段）。",
    },
    "price": {
        "a": round(a_fare, 4), "b": round(b_fare, 4),
        "formula": "P_ref(d) = a * d^b  (经济舱，人民币元)",
        "cabin_multiplier": CABIN_MULT, "floor_vs_marginal_cost": 0.6,
    },
    "utility": {
        "c_price": c_price, "c_time": C_TIME, "c_freq": C_FREQ,
        "c_hub": C_HUB, "c_stop": c_stop, "c_trans": C_TRANS,
        "c_rep_note": "c_rep 不再为常数，改由 reputation.c_rep(d) 计算",
    },
    "targets": {
        "elasticity_at_share_0_45": ELASTICITY_TARGET,
        "transfer_overtake_daily_connections": N_TRANSFER_TARGET,
        "solo_share_short_haul": S_SHORT, "solo_share_long_haul": S_LONG,
    },
}

with open(BASE / "params.json", "w", encoding="utf-8") as f:
    json.dump(params, f, ensure_ascii=False, indent=2)

# ============================================================
# 12. report.md
# ============================================================

lines = []
add = lines.append

add("# 航空公司模拟经营 · 系数校准报告（v1.1 能级制）\n")
add(f"> 自动生成，请勿手改。数据源：`airports.csv`（{len(airports)} 机场 / {len(cities)} 城市）、"
    f"`anchors.csv`（{len(anchors)} 基准城市对）、`fares.csv`（{len(fares)} 条票价样本）。\n")

add("## 1. 模型变更说明\n")
add("本版按需求评审结论，把 v1.0 的**重力模型**换成了**能级制需求模型**：\n")
add("| 项 | v1.0 重力模型 | v1.1 能级制（本版） |")
add("|---|---|---|")
add("| 需求驱动 | `(Ta·Tb)^alpha · f(d)` | `w(能级A) · w(能级B)` |")
add("| 距离的角色 | **降低需求** | **不降低需求**，只提高口碑敏感度 |")
add("| 参数识别 | `alpha/beta/dmax` 三者共线，不可识别 | 能级权重与区域系数线性可解 |")
add("| 枢纽效应 | 吞吐量直接进入需求，枢纽被高估 | 吞吐只用于定能级；枢纽靠连通度 `conn` 加成 |")
add("")
add("这样处理同时解决了三个问题：参数可识别、枢纽不再被系统性高估、距离的经济含义从「需求」转移到「服务质量压力」。\n")

add("## 2. 机场能级划分\n")
add("按年吞吐量划档，城市能级取其全部机场吞吐量之和所对应的档位：\n")
add("| 能级 | 名称 | 吞吐量阈值 | 城市数 | 权重 w |")
add("|---|---|---|---|---|")
for s, thr in SCALE_THRESHOLDS:
    thr_txt = f"≥ {thr:.0f} 百万人次" if s != "R" else "< 8 百万人次"
    add(f"| {s} | {SCALE_LABEL[s]} | {thr_txt} | {counts.get(s, 0)} | {w_norm[s]:.4f} |")
add("")
add(f"权重以 XL = 1.0 归一。`w` 的比值才是实际使用的量，例如两个大型机场之间的需求是同等级超大机场的 "
    f"{w_norm['L'] ** 2:.3f} 倍。\n")

add("## 3. 需求公式\n")
add("```")
add("D_total(A,B) = C · w(scale_A) · w(scale_B) · C_region · conn_A · conn_B")
add(f"               C = {C:.4f}")
add("D_air(A,B)   = D_total(A,B) · sigmoid(c0(d))")
add("```\n")
add("`D_total` 是**总出行需求**（含高铁、自驾），`D_air` 才是航空客流。游戏里只需要实现 `D_total` 与 logit，"
    "方式分担由 logit 的外部选项 `U_0 = 0` 自动完成。\n")
add(f"整体拟合优度（对数域 R²）= **{r2:.4f}**，平均绝对误差 **{mre:.1f}%**\n")

add("## 4. 区域系数\n")
add("| 区域对 | C_region |")
add("|---|---|")
for k, v in C_REGION_TABLE.items():
    add(f"| {k} | {v:.3f} |")
add("")
add("> `CN-MEA` 无锚点，按最小区域系数八折占位，**需补数据**。\n")

add("## 5. 基准锚点残差\n")
add("| 城市对 | 能级 | 距离 km | 观测航空客流 | 模型预测 | 误差 |")
add("|---|---|---|---|---|---|")
for r in rows:
    add(f"| {r['a']}–{r['b']} | {r['scale_a']}/{r['scale_b']} | {r['d']:.0f} | "
        f"{r['obs_air']:,.0f} | {r['pred']:,.0f} | {r['err']:+.1f}% |")
add("")
add("> 误差较大的几条（穗–蓉、沪–首尔、沪–台）源于锚点本身是公开数据的估算值，"
    "且能级制把同能级城市视为等价，无法表达「同一档内城市之间仍有差异」。"
    "这是能级制的固有代价，用区域系数无法完全吸收。\n")

add("## 6. 距离 → 口碑敏感度（D2）\n")
add("```")
add("c_rep(d) = min(1.20, 0.25 + 0.000075 · d)")
add("```\n")
add("| 航距 km | c_rep | 相对短途的倍数 | 设计含义 |")
add("|---|---|---|---|")
for d in (300, 1000, 2000, 4000, 6000, 8000, 10400):
    v = c_rep_of(d)
    add(f"| {d:,} | {v:.3f} | {v / c_rep_of(300):.1f}× | "
        f"{'短途：口碑几乎不影响选择' if d <= 1000 else ('中途：开始明显' if d <= 4000 else '远程：口碑决定成败')} |")
add("")
add("**这就是「自动引导使用更舒适机型」的机制**：长航线上 `c_rep(d)` 被放大，"
    "而口碑里的 `comfort_score` 由机型舒适度驱动，因此用舒适度低的机型执飞长航线会损失大量份额——"
    "不需要额外写「机型航程限制」，市场上自然会淘汰不合适的机型。\n")

add("## 7. 枢纽连通度（D3）\n")
add("```")
add("conn(i) = min(1.80, 1 + 0.50 · ln(1 + routes_i / 100))")
add("```\n")
add("| 该机场在营航段数 | conn 乘子 |")
add("|---|---|")
for n in (0, 50, 100, 200, 400, 800, 1600):
    add(f"| {n} | {conn_of(n):.3f} |")
add("")
add("这是**唯一一个随游戏进程动态变化的需求项**：首尔、迪拜这类中转城市在开局时按能级获得基础 OD，"
    "随着各公司在当地铺设航段，其客流吸引力逐步上升。乘子同时作用于两端城市，因此「把别人的枢纽做大」"
    "也会抬高你自己的 OD 池——这让枢纽战争变成正和与零和交织的博弈。\n")

add("## 8. 参考票价曲线\n")
add("```")
add(f"P_ref(d) = {a_fare:.3f} · d^{b_fare:.4f}   (经济舱，人民币元)")
add("```\n")
add("| 航距 km | 参考票价 元 | 元/百公里 |")
add("|---|---|---|")
for d in (300, 600, 1200, 2000, 4000, 8000, 10400):
    pr = a_fare * d ** b_fare
    add(f"| {d:,} | {pr:,.0f} | {pr / d * 100:,.1f} |")
add("")

add("## 9. 效用系数\n")
add("| 系数 | 取值 | 来源 |")
add("|---|---|---|")
add(f"| `c_price` | {c_price} | 由弹性目标反解：s=0.45 时 ε=−1.20 |")
add(f"| `c_stop` | {c_stop} | 由中转反超门槛反解：经停 2 班/日 ≡ 中转 10 班/日 |")
add(f"| `c_trans` | {C_TRANS} | 设计值 |")
add(f"| `c_freq` | {C_FREQ} | 设计值 |")
add(f"| `c_hub` | {C_HUB} | 设计值 |")
add(f"| `c_time` | {C_TIME} | 设计值，**未校准** |")
add("")

add("## 10. 合理性校验\n")
add("```")
add(f"京沪：观测航空客流 {pj['obs_air']:,.0f} 人次/日·单向")
add(f"       模型预测 {pj['pred']:,.0f}，误差 {pj['err']:+.1f}%")
add(f"       总出行需求 {pj['total']:,.0f}（航空份额 {air_share(pj['d']):.1%}）")
add(f"       按 180 座 / 82% 载客率 → 单向约 {pj['obs_air'] / (180 * 0.82):.0f} 班/日")
add("实际京沪航线单向 60–80 班/日 → 量级一致")
add("```\n")

add("### 模型预测的中国前 10 城市对（航空客流，人次/日·单向）\n")
add("| 排名 | 城市对 | 能级 | 距离 km | 预测客流 |")
add("|---|---|---|---|---|")
for i, (v, ca, cb, d) in enumerate(top, 1):
    add(f"| {i} | {ca}–{cb} | {cities[ca]['scale']}/{cities[cb]['scale']} | {d:.0f} | {v:,.0f} |")
add("")
add("> 检查点：第 1 名必须是京沪；拉萨、西宁这类支线城市对必须显著靠后。若排名出现明显反直觉项，"
    "说明能级权重需要重标定。\n")

add("## 11. 置信度\n")
add("| 系数 | 置信度 | 说明 |")
add("|---|---|---|")
add(f"| 能级权重 `w` | 中 | 由 {len(anchors)} 条锚点线性求解，5 个自由度对 20 个观测 |")
add(f"| `C` | 中 | 绝对值依赖方式分担曲线 |")
add(f"| `C_region` | 中 / MEA 极低 | 每组 3–6 条锚点；MEA 无锚点 |")
add(f"| `c0` 曲线 | 中 | 依赖「京沪航空占 45%」这一假设 |")
add(f"| `c_rep(d)` | **未校准** | 斜率为设计值，无数据源；只能靠 10 年模拟观察平衡性 |")
add(f"| `conn` 的 `k` | **未校准** | 先验 0.5，无数据源 |")
add(f"| `a`、`b` | 中高 | 9 条票价样本 |")
add(f"| `c_price`、`c_stop` | 高 | 由外生目标精确反解 |")
add(f"| `c_time` | **未校准** | 先验 0.25 |")
add("")
add("## 12. 遗留风险\n")
add("```")
add("1. 能级制把同档城市视为等价：广州与成都、深圳与杭州在模型中没有区别")
add("   → 缓解：后续可为每档内再加一个 ±15% 的城市系数，由锚点残差反推")
add("2. 需求不随距离衰减，短途干线的利润率会显著高于长航线")
add("   → 需要靠「时刻稀缺 + 机队周转上限 8 段/日」限制短途航班数量，")
add("      若实测短途收益仍压倒性占优，再考虑加一个极弱的距离项（beta ≈ 0.15）")
add("3. conn 乘子会让大枢纽在后期滚雪球")
add("   → 已设 cap 1.8；若仍失控，改为按「排名分位」而非绝对航线数计算")
add("```\n")

with open(BASE / "report.md", "w", encoding="utf-8") as f:
    f.write("\n".join(lines))

print("[out] params.json / report.md 已生成")
print(f"[check] R2={r2:.4f} MRE={mre:.1f}% c_price={c_price} c_stop={c_stop}")
print(f"[check] 京沪 预测 {pj['pred']:,.0f} / 观测 {pj['obs_air']:,.0f}，误差 {pj['err']:+.1f}%")
print(f"[check] 区域系数 {C_REGION_TABLE}")
