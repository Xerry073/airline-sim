# -*- coding: utf-8 -*-
"""航空公司模拟经营 —— 本地后端服务（入口）

架构：前后端分离，后端在本机跑权威模拟，浏览器通过 HTTP API 取状态、下指令。

为什么用标准库 http.server：
  - 目标运行环境没有安装 FastAPI/uvicorn，pip 也不可用
  - 单机本地单用户，线程数极少，ThreadingHTTPServer 完全够用
  - 零依赖意味着分发时不需要用户装任何东西
  - 接口契约与框架无关，日后换 FastAPI 只需替换 api.py 里的 Handler

文件分工：
  paths.py    项目路径、存档目录、内核 import
  session.py  一局游戏：时钟推进、玩家指令、存档读写
  meta.py     /api/meta 的静态元数据
  api.py      HTTP 路由与静态文件
  app.py      命令行参数与启动（本文件）

接口一览
--------
GET  /api/health   /api/meta   /api/state   /api/market   /api/saves
POST /api/new_game /api/save   /api/load    /api/delete_save
POST /api/autosave /api/quit   /api/restart /api/command   /api/control
GET  /             静态前端（web/ 目录）

运行：python server/app.py --port 8777 --ai 50 --speed 4
"""

import argparse
import sys
from http.server import ThreadingHTTPServer

from api import Handler
from paths import S
from session import Session

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8777)
    ap.add_argument("--ai", type=int, default=50)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--cash", type=float, default=3000.0)
    ap.add_argument("--speed", type=int, default=4, help="初始倍速 0/1/4/16")
    ap.add_argument("--hub", default="PEK", help="玩家初始枢纽")
    ap.add_argument("--cost-mult", type=float, default=1.0)
    ap.add_argument("--day-seconds", type=float, default=60.0,
                    help="1 游戏日对应的真实秒数（开发时可用 0.5 加速验证）")
    ap.add_argument("--no-resume", action="store_true",
                    help="启动时不自动恢复 autosave，开新档")
    ap.add_argument("--autosave-seconds", type=int, default=60,
                    help="自动存档间隔（真实秒，0=关闭定时自动存档）")
    ap.add_argument("--mode", choices=("sandbox", "goals"), default=None,
                    help="新对局模式；省略时由页面开局选择")
    ap.add_argument("--supervised", action="store_true", help=argparse.SUPPRESS)
    args = ap.parse_args()

    if args.cost_mult != 1.0:
        for k in ("fuel_price_per_kg", "landing_base_M", "nav_rate_M_per_km",
                  "staff_base_M_day", "staff_per_aircraft_M_day", "staff_per_segment_M_day",
                  "ground_per_pax_M", "idle_cost_M_day"):
            S.ECON[k] *= args.cost_mult
        for k in S.ECON["hub_fixed_by_scale"]:
            S.ECON["hub_fixed_by_scale"][k] *= args.cost_mult
        S.ECON["distribution_pct"] = min(0.30, S.ECON["distribution_pct"] * args.cost_mult)

    Handler.session = Session(
        args.ai, args.seed, args.cash, args.speed, args.hub.upper(),
        day_seconds=args.day_seconds, resume=not args.no_resume,
        autosave_seconds=args.autosave_seconds, mode=args.mode)
    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    mode_text = "由页面选择" if not Handler.session.game.mode_chosen else Handler.session.game.mode
    print(f"航空模拟后端已启动 → http://127.0.0.1:{args.port}/")
    print(f"  对手 {args.ai} 家 · 种子 {args.seed} · 初始倍速 {args.speed}x · 模式 {mode_text}")
    print(f"  自动存档：{args.autosave_seconds}s · 启动恢复：{'关' if args.no_resume else '开'}")
    print("  Ctrl+C 停止；页面内「存档」可保存并退出/重启")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n正在停止…")
    finally:
        Handler.session.stop()
        srv.server_close()
        if Handler.session.restart_requested:
            print("正在重启后端…")
            sys.stdout.flush()
            raise SystemExit(42)


if __name__ == "__main__":
    main()
