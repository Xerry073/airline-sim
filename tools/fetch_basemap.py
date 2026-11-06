# -*- coding: utf-8 -*-
"""
底图获取与处理
==============
下载 Natural Earth 的「陆地轮廓」（只有陆地，不含任何国界线），
裁剪属性、降低坐标精度后写入 web/data/world.geo.json。

为什么要这个脚本：
  - 本机 Schannel（curl / .NET / PowerShell 都走它）被拦，只能用 Python 的 OpenSSL
  - 顺便做体积压缩与合规校验（确认文件里没有国界要素）

用法：
  python tools/fetch_basemap.py            # 下载并安装
  python tools/fetch_basemap.py --check    # 只校验已有的 world.geo.json
"""

import argparse
import json
import ssl
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "web" / "data" / "world.geo.json"

# Natural Earth 110m 陆地轮廓（公有领域，只有陆地块，无国界）
SOURCES = [
    "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_110m_land.geojson",
    "https://cdn.jsdelivr.net/gh/nvkelso/natural-earth-vector@master/geojson/ne_110m_land.geojson",
]

KEEP_TYPES = {"Polygon", "MultiPolygon"}


def fetch(url, timeout=40):
    ctx = ssl.create_default_context()
    req = urllib.request.Request(url, headers={"User-Agent": "airline-sim/1.0"})
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        return r.read()


def round_coords(obj, nd=2):
    """坐标降精度：2 位小数 ≈ 1 km，在 1000px 世界图上不到 0.03 px"""
    if isinstance(obj, (int, float)):
        return round(obj, nd)
    if isinstance(obj, list):
        return [round_coords(x, nd) for x in obj]
    return obj


def normalize(raw):
    doc = json.loads(raw)
    feats = doc.get("features") or ([doc] if doc.get("geometry") else [])
    if not feats:
        raise ValueError("不是 GeoJSON FeatureCollection")

    out, dropped = [], 0
    for f in feats:
        g = f.get("geometry") or f
        t = g.get("type")
        if t not in KEEP_TYPES:
            dropped += 1
            continue
        out.append({
            "type": "Feature",
            "properties": {},                      # 裁掉属性：彻底去掉任何地名/国名
            "geometry": {"type": t, "coordinates": round_coords(g["coordinates"])},
        })
    return {"type": "FeatureCollection", "features": out}, len(feats), dropped


def bbox(doc):
    xs, ys = [], []
    def walk(c):
        if isinstance(c[0], (int, float)):
            xs.append(c[0]); ys.append(c[1])
        else:
            for x in c:
                walk(x)
    for f in doc["features"]:
        walk(f["geometry"]["coordinates"])
    return min(xs), min(ys), max(xs), max(ys)


def validate(doc):
    """校验：只有陆地、范围覆盖全球、坐标合法"""
    problems = []
    types = {f["geometry"]["type"] for f in doc["features"]}
    if not types <= KEEP_TYPES:
        problems.append(f"出现非面要素：{types - KEEP_TYPES}")
    if any(f.get("properties") for f in doc["features"]):
        problems.append("存在属性字段（可能不是 land 数据）")
    x0, y0, x1, y1 = bbox(doc)
    if not (-180.5 <= x0 <= -170 and 170 <= x1 <= 180.5):
        problems.append(f"经度范围异常：{x0:.1f} ~ {x1:.1f}")
    if not (-90.5 <= y0 <= -80 and 80 <= y1 <= 90.5):
        problems.append(f"纬度范围异常：{y0:.1f} ~ {y1:.1f}")
    return problems, (x0, y0, x1, y1)


def install(raw):
    doc, total, dropped = normalize(raw)
    problems, bb = validate(doc)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, separators=(",", ":"), ensure_ascii=False),
                   encoding="utf-8")
    size = OUT.stat().st_size
    print(f"[ok] 要素 {len(doc['features'])}（原始 {total}，丢弃非面要素 {dropped}）")
    print(f"[ok] 包围盒 lon {bb[0]:.1f}~{bb[2]:.1f}  lat {bb[1]:.1f}~{bb[3]:.1f}")
    print(f"[ok] 已写入 {OUT.relative_to(ROOT)}  {size/1024:.0f} KB")
    if problems:
        print("[warn] 校验发现问题：")
        for p in problems:
            print("   -", p)
        return 1
    print("[ok] 校验通过：纯陆地轮廓，无国界、无属性")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="只校验已有文件")
    args = ap.parse_args()

    if args.check:
        if not OUT.exists():
            print(f"[x] 不存在：{OUT}")
            return 1
        doc = json.loads(OUT.read_text(encoding="utf-8"))
        problems, bb = validate(doc)
        print(f"要素 {len(doc['features'])}  {OUT.stat().st_size/1024:.0f} KB  "
              f"bbox {bb[0]:.1f}~{bb[2]:.1f} / {bb[1]:.1f}~{bb[3]:.1f}")
        print("校验通过" if not problems else "问题：" + "；".join(problems))
        return 0 if not problems else 1

    last = None
    for url in SOURCES:
        try:
            print(f"[..] 下载 {url}")
            raw = fetch(url)
            print(f"[ok] {len(raw):,} 字节")
            return install(raw)
        except Exception as e:
            last = e
            print(f"[x] 失败：{type(e).__name__}: {str(e)[:120]}")
    print("[x] 所有源都失败。可在有网络的机器上下载 ne_110m_land.geojson，"
          "改名为 world.geo.json 放进 web/data/。")
    print("    参考：", last)
    return 1


if __name__ == "__main__":
    sys.exit(main())
