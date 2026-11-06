# -*- coding: utf-8 -*-
"""全局配置：路径、成本与经济系数、目标常量、区域名。

由 sim/simulate.py 拆分而来；只允许依赖更靠前的分层，不要反向 import。
"""

from pathlib import Path


ROOT = Path(__file__).resolve().parent
CAL = ROOT.parent / "calibration"

# ============================================================
# 成本与经济系数（★ 后续 hotfix 的主要入口）
# ============================================================

SAVE_FORMAT = "airline-sim-save"
SAVE_VERSION = 1

ECON = {
    # 2026-11 参数轮：小规模航司原来无法盈利（3 机 8 线、满负荷仍 −0.37/日）。
    # 固定开销下调约 45%、折旧/租赁下调约 30%、导航/起降/维护下调 20–25%，
    # 使「按机队规模摊固定开销」不再一刀砍死小航司；燃油与分销保持标定值。
    "fuel_price_per_kg": 5.0,        # 人民币元/kg
    "landing_base_M": 0.0068,        # ¥M / 次，按 MTOW/70 缩放
    "nav_rate_M_per_km": 0.8e-5,     # ¥M / km，按 MTOW/70 缩放
    "staff_base_M_day": 0.08,
    "staff_per_aircraft_M_day": 0.030,
    "staff_per_segment_M_day": 0.006,
    "hub_fixed_by_scale": {"XL": 0.05, "L": 0.04, "M": 0.025, "S": 0.012, "R": 0.006},
    "distribution_pct": 0.10,        # 销售与分销费用，按收入比例
    "ground_per_pax_M": 0.00012,     # 地面服务 / 值机 / 安检 / 餐食，¥M / 人次
    "maint_load_factor": 1.25,       # 维护成本修正：真实航司维修负担高于按小时线性估算
    "depreciation_years": 28,
    "residual": 0.15,
    "lease_rate_month": 0.0038,
    "max_debt_to_equity": 2.0,
    "loan_rate_base": 0.06,
    "loan_rate_max": 0.12,
    "idle_cost_M_day": 0.01,         # 闲置停机与人员（R-702）
}

FLIGHT = {
    "max_hours_per_day": 16.0,
    "max_segments_per_day": 8,
    "turnaround_min": {"支线": 30, "窄体": 45, "宽体": 90},
    "stopover_extra_min": 15,
    "peak_coverage": 0.75,
}

# AI 定价的目标载客率：价格控制器以它为锚上下调整
PRICE_TARGET_LF = 0.82

STOP = {
    "min_total_km": 2000.0,     # R-534
    "min_segment_km": 300.0,    # R-535
    "max_detour": 1.40,         # R-536
    "max_range_factor": 1.30,   # R-537
    "max_stops": 2,             # R-531（规则上限，供玩家使用）
    # v1.0 决策：AI 只生成「1 个经停点（2 段）」的经停航线。
    # 3 段（2 个经停点）虽然规则允许，但候选组合会从 3 个/端点膨胀到 9 个/端点，
    # 且 R-537 允许 A320 拼出 8,190 km 的航线，经济上可疑 —— 先锁死，留给玩家。
    "ai_max_segments": 2,
}

KNOWN_GAPS = [
    "时刻 use-it-or-lose-it 未实现（R-513）",
    "二手飞机市场只做了破产清算投放，没有交易界面（§7.2）",
    "中转仅支持本公司 HUB、最多 1 次换机",
    "取消航班为确定性比率，无逐日随机与玩家主动取消",
    "经停只能由 AI 从直飞航线延伸生成，玩家无操作入口；3 段航线不会自动生成",
    "AI 不调整座位配置、不更换机型",
]

# ============================================================
# 目标模式（FR-1101 / FR-1102 / FR-1103）
# ============================================================

DAYS_PER_YEAR = 360
GOAL_YEARS = 10
GOAL_DEADLINE_DAYS = DAYS_PER_YEAR * GOAL_YEARS
GOAL_MONTHS = 24

GOAL_DEFS = [
    ("market_top3", "市值进前三", "10 游戏年内市值排名 ≤ 3"),
    ("region_leader", "区域霸主", "某区域内市场份额 ≥ 35%"),
    ("high_quality", "高质高效", "连续 24 个月 EBITDA 率 ≥ 15% 且准点率 ≥ 85%"),
    ("network_expansion", "网络扩张", "航段数 ≥ 100 且平均载客率 ≥ 75%"),
]
GOAL_RATINGS = {4: "A", 3: "B", 2: "C", 1: "D", 0: "E"}
REGION_NAMES = {
    "CN": "中国",
    "GCR": "港澳台",
    "ASIA": "亚洲其他",
    "EUR": "欧洲",
    "AMR": "美洲",
    "MEA": "中东非洲",
    "OCE": "大洋洲",
}


