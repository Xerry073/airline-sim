# -*- coding: utf-8 -*-
"""基础工具：CSV 读取、大圆距离、限幅、sigmoid、时刻触及计数。

由 sim/simulate.py 拆分而来；只允许依赖更靠前的分层，不要反向 import。
"""

import csv
import math


# ============================================================
# 基础工具
# ============================================================

def read_csv(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def gc_km(a, b):
    R = 6371.0
    lat1, lon1 = math.radians(a["lat"]), math.radians(a["lon"])
    lat2, lon2 = math.radians(b["lat"]), math.radians(b["lon"])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def clamp(x, lo, hi):
    return max(lo, min(hi, x))


def sigmoid(x):
    return 1.0 / (1.0 + math.exp(-x))





def slot_touches(segments):
    """FR-403：每个机场被航线触及的航段数（每个航段的两端各算一次）。"""
    counts = {}
    for i in range(len(segments) - 1):
        for code in (segments[i], segments[i + 1]):
            counts[code] = counts.get(code, 0) + 1
    return counts

