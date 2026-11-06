# 开发者手册 · 航空公司模拟经营 Ver 1.0

面向要改代码、调数值、跑测试、重新打包的人。玩家向内容见 [README-玩家.md](README-玩家.md)，
协作规范见 [CONTRIBUTING.md](CONTRIBUTING.md)。

---

## 1. 一句话架构

前后端分离，后端在本机跑权威模拟，浏览器通过 HTTP/JSON 取状态、下指令。
**零第三方依赖**：后端只用 Python 标准库，前端是纯静态多文件、无构建步骤。

```
浏览器（web/index.html + css + 7 个 js）
   │  GET /api/state  每秒轮询
   │  POST /api/command|control|save|load|new_game ...
   ▼
后端（server/：api.py 路由 → session.py 会话 → sim/ 内核）
   │
   ▼
模拟内核（sim/ 10 个分层模块，simulate.py 只是兼容门面）
   │
   ▼
系数与数据（calibration/params.json、airports.csv；sim/aircraft.csv）
```

关键点：

- **时钟在后端**。浏览器只读 `/api/state.tick`，不自己推进时间。
- **`Game.apply()` 是玩家唯一写入口**。前后端所有指令最终落到这一个函数。
- **快照是裁剪视图**。`Game.snapshot()` 返回新字典；对手只暴露公开信息（FR-1002）。
- **存档是显式 JSON**。`to_save()/from_save()` 手写字段映射，不用 pickle。

---

## 2. 目录与模块边界

| 路径 | 说明 |
|---|---|
| `server/app.py` | 入口：命令行参数、成本系数覆盖、启动 HTTP 服务 |
| `server/api.py` | `Handler`：路由分发、JSON 读写、静态文件 |
| `server/session.py` | `Session`：游戏时钟线程、玩家指令、存档读写、市场查询 |
| `server/meta.py` | `/api/meta` 响应体 |
| `server/paths.py` | 项目路径、存档目录、把 `sim/` 放进 `sys.path` 并暴露 `S` |
| `server/supervisor.py` | 监督进程：`app.py` 以退出码 42 退出时用原参数重启 |
| `sim/simulate.py` | **兼容门面**：re-export 下面所有模块，保持旧 import 与 CLI 用法 |
| `sim/config.py` | 路径、ECON/COST 系数、目标常量、区域名 |
| `sim/util.py` | CSV 读取、大圆距离、clamp、sigmoid、`slot_touches` |
| `sim/model.py` | `World` / `Aircraft` / `Route` / `Airline` |
| `sim/products.py` | 航线 → 行程产品（直飞/经停/中转、候选上限、去重） |
| `sim/market.py` | 能级池 → 分舱 → logit → 段容量 yield 截断 |
| `sim/settle.py` | 日结算：收入、九项成本、利息、破产、市值 |
| `sim/ai.py` | AI 决策：定价枚举、开线/关线、枢纽扩张、经停延伸 |
| `sim/goals.py` | 四目标判定、区域份额、月报质量、A–E 评级 |
| `sim/game.py` | `Game`：逐日推进、玩家指令、快照、存档序列化 |
| `sim/report.py` | `run` / `summarize` / `write_report` / CLI |
| `sim/selftest.py` | 52 条验收自测 |
| `web/index.html` | 页面结构 + 脚本加载顺序 |
| `web/css/app.css` | 全部样式 |
| `web/js/*.js` | 按加载顺序：map → routes → interaction → panels → saves → goals → app |
| `web/data/world.geo.json` | 陆地轮廓底图（127 要素、无国界、无属性） |
| `calibration/*` | 系数表、机场、锚点、票价样本、标定脚本与报告 |
| `tools/*_check.js` | 前端/地图校验（零依赖、不启子进程） |
| `tools/package.ps1` | 发布打包（复制 + 排除 + 自检 + zip） |

### sim/ 的依赖方向（硬约束）

```
config → util → model → products → market → settle → ai → goals → game → report
```

- 只允许「左边被右边 import」，不允许反向
- `simulate.py` 只做 `from x import *`，**不要往里加逻辑**
- 模块之间是**直接 `from x import f`**，因此测试里 monkeypatch 要打在「使用处」所在模块：
  `market.allocate` 用的是 `market.build_products`，patch `simulate.build_products` **不会生效**

### web/ 的加载顺序（硬约束）

7 个脚本是 classic script，按 `<script>` 顺序执行，共享同一个全局词法作用域：

- 后面的文件可以用前面文件里的 `const` / `function`，反之不行
- 顶层可执行语句只允许出现在最后加载的 `js/app.js`（启动绑定）
- 两个文件声明同名 `const` / `let` / `class` 会直接抛 `SyntaxError` —— `tools/asset_check.js` 会拦住

---

## 3. 环境与启动

| 用途 | 需要 |
|---|---|
| 玩 / 跑后端 | Python 3.9+，**无第三方包** |
| 跑前端测试 | Node.js 18+（脚本零依赖） |
| 重新标定 | Python + numpy（只有 `calibration/calibrate.py` 用） |

```bash
# 完整启动（启动器找 Python → supervisor → app.py → 开浏览器）
start.cmd
start.cmd -Port 8777 -Ai 50 -Speed 4 -NoResume

# 只用 supervisor（开发常用，终端能看日志，Ctrl+C 退出）
python server/supervisor.py --port 8777 --ai 50 --speed 4

# 直接跑 app.py（最快，但页面「保存并重启」不会自动拉起新进程）
python server/app.py --port 8777 --ai 50
```

### 命令行参数（`server/app.py`）

| 参数 | 默认 | 说明 |
|---|---|---|
| `--port` | `8777` | 监听端口（只绑 `127.0.0.1`） |
| `--ai` | `50` | AI 航司数量 |
| `--seed` | `42` | 随机种子（入档，可重放） |
| `--cash` | `3000` | 每家起始资金（¥M） |
| `--speed` | `4` | 初始倍速，`0/1/4/16`（0 = 暂停开局） |
| `--hub` | `PEK` | 玩家初始枢纽 |
| `--cost-mult` | `1.0` | 全部成本系数（难度旋钮） |
| `--day-seconds` | `60` | 1 游戏日的真实秒数（再除以倍速） |
| `--autosave-seconds` | `60` | 自动存档间隔（真实秒，0 = 关闭） |
| `--no-resume` | 关 | 启动时不恢复 `saves/autosave.json` |
| `--mode` | 无 | `sandbox`/`goals`；省略则由页面开局选择 |

`--cost-mult`：`1.0` 是标定基准（几乎不破产），`1.2` 附近才是可玩难度，`2.5` 是压力测试。

---

## 4. 一次操作走哪

```
用户点「开通航线」
  → web/js/panels.js: api("/api/command", {action:"open_route", args:{...}})
  → server/api.py do_POST → Session.apply（持 RLock）
  → Game.apply("open_route", args)   ← 唯一写入口，做全部校验
  → 返回 {ok:true} 或 {ok:false, reason:"..."}
  → 前端：成功 toast + 立刻 refresh()；失败把 reason 弹出来
  → 下一次 /api/state 轮询把新状态渲染到地图与面板
```

- 前端**不预测**结果，只信后端的 `ok/reason`
- 失败必须带中文 `reason`（FR-1005 验收）
- 时钟：`Session._loop()` 每 50 ms 检查一次，到点 `advance_day()`；到间隔写 autosave

---

## 5. API 契约

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/health` | `{ok, day}`，启动器与页面用它判断后端是否就绪 |
| GET | `/api/meta` | 机场库、机型库、规则参数、目标定义 |
| GET | `/api/state` | 世界快照（前端每秒轮询） |
| GET | `/api/market?from=PEK&to=SHA` | 两机场之间的市场情报（开线向导用） |
| GET | `/api/saves` | 本地存档列表 |
| POST | `/api/new_game` | `{"mode":"sandbox"\|"goals"}` 重建第 0 天 |
| POST | `/api/save` | `{"name":"..."}` 保存并命名 |
| POST | `/api/load` | `{"id":"save_..."}` 载入 |
| POST | `/api/delete_save` | `{"id":"save_..."}` 删除 |
| POST | `/api/autosave` | 立即写 `saves/autosave.json` |
| POST | `/api/quit` | 自动存档并停后端 |
| POST | `/api/restart` | 自动存档并请 supervisor 重启 |
| POST | `/api/command` | `{"action":"open_route","args":{...}}` |
| POST | `/api/control` | `{"paused":false,"speed":4}` |
| GET | `/` | 静态前端（`web/` 整目录，含 `/data/world.geo.json`） |

### 指令集（`Game.apply`）

| action | args | 校验要点 |
|---|---|---|
| `open_route` | `segments:["PEK","SHA"]`、`daily_flights`、`ac_type` | 航段 1–2、距离、航程、时刻、机队运力；2 段走九项经停校验 |
| `close_route` | `route_id` | 存在性；关线立即释放时刻 |
| `set_price` | `route_id`、`price_index` | 0.50–1.50 |
| `set_flights` | `route_id`、`daily_flights` | 1–14 且机队运力足够 |
| `add_hub` | `airport` | 三档门槛 + 开设费 |
| `buy_aircraft` | `ac_type`、`base`、`lease` | 现金或租赁额度 |
| `sell_aircraft` | `aircraft_id` | 存在性 |
| `take_loan` | `amount` | 授信额度 |
| `rename_airline` | `name` | 2–20 字符、不可重名 |

全部返回 `{"ok": bool, "reason": "失败原因"}`。

### 快照关键字段（`GET /api/state`）

```text
tick            {day, paused, speed, seed}
airports[]      {iata, city, lat, lon, scale, region, pax, slot_cap, slot_used}
player          {name, alive, cash, debt, equity, reputation, market_cap, rank,
                 hubs[], fleet[], routes[], kpi{pax,revenue,cost,ebitda}}
player.routes[] {id, segments, daily_flights, ac_type, price_index, lf, rep, pax,
                 distance_km, revenue_M, cost_M, profit_M, margin,
                 prices[]{from, to, eco, biz}}
rivals[]        对手榜：市值前 20、**不含本公司**
                 {name, hub, rank, routes, fleet, pax, ebitda, lf, rep, market_cap}
rivals_total    存活对手总家数（50 AI 时约 49）
opponent_routes[] 对手公开航线 {airline, hub, segments, daily_flights, ac_type, lf,
                 price_index, prices[]{from, to, eco, biz}}
goals           {mode, mode_chosen, setup_required, deadline_day, days_left,
                 years_left, progress[], achieved_count, rating, scored,
                 settled, settlement}
log[]           最近 40 条事件
```

- `rivals[].rank` 是**全体存活公司**名次（与 `player.rank` 同口径），过滤自己后会留空档
- `player.routes[].margin` 是**航线可归集口径**：不含折旧租赁、总部固定费与利息
- 对手航线的**票价公开**：`price_index` + 每个 OD 的 `eco`/`biz`，算法与玩家侧一致
  （`p_ref(OD 两端直线距离, 舱位) × 价格指数`，R-632）；成本、收入与利润仍然不可见（FR-1002）

---

## 6. 测试

```bash
python sim/selftest.py          # 52 条内核验收（FR 编号对齐需求文档）
node tools/asset_check.js       #  5 条：前端资源引用、加载顺序、语法、重名、顶层语句
node tools/map_check.js         # 31 条：地图几何、分级、标签避让、大圆、日界线、开线焦点
node tools/goal_check.js        #  8 条：目标/模式面板与 /api/new_game 开局
node tools/panel_check.js       # 13 条：对手榜口径、AI 票价、我的航线竞争对照
node tools/route_gui_check.js   # 10 条：开线手势（右键起点 / 左键终点 / Alt+左键经停）
python -m compileall -q server sim calibration
```

当前记录：`52/52`、`5/5`、`31/31`、`8/8`、`13/13`、`10/10`，`compileall` 退出码 0。

### 前端测试怎么工作

`tools/*_check.js` 不做浏览器自动化，而是**从源文件抽取函数**再用 `new Function` 注入 DOM 桩执行：

| 脚本 | 抽取来源 | 抽取方式 |
|---|---|---|
| `asset_check.js` | `web/index.html` + 全部 `js/` | 解析引用，整体编译 |
| `map_check.js` | `web/js/map.js` | 正则截取 `MAP_MATH_START/END` 之间 |
| `goal_check.js` | `web/js/goals.js` | 从 `async function startNewGame` 到文件末尾 |
| `panel_check.js` | `web/js/app.js` | 从 `function renderRivals` 到标记注释 |
| `route_gui_check.js` | `web/js/interaction.js` | 截取 `ROUTE_PICK_START/END` 之间，桩掉 DOM 与向导 |

所以**改函数名或删标记注释会让脚本报「找不到代码段」**——这是故意的，提示你同步更新测试。
它们验证逻辑与输出字符串，不验证像素级外观。

---

## 7. 内核要点

### 一个游戏日

```
机龄 +1/360 天
  → AI 决策（每 7 日）：关低载客率航线 / 调价 / 加班次 / 开新线
  → update_route_stats()：准点率、取消率、口碑目标值（含惯性）
  → build_products()：航线 → 行程产品；机队周转超限的航线当天不执行
  → cabin_demand()：能级池 → 方式分担 → 三舱拆分
  → logit 分配：价格 / 时间 / 班次 / 口碑 / HUB / 经停 / 换机
  → 段容量 yield 截断：跨段旅客挤占短途客
  → settle_day()：收入 − 9 项成本
  → LF / 客流加权口碑 / 破产 / 市值
```

细节（口碑公式、AI 定价三轮迭代、破产与收缩表、基准场景）见 `sim/README.md`，改数值前先读。

### 目标模式

- `Game.configure_mode("goals")`：`goal_deadline_day = 3600`（10 × 360）
- 逐日 `_update_goals()` 更新；四项同时追踪、互不冲突（FR-1102 验收条款）
- 全达成 → `complete`（A）；到期 → `deadline`（按达成数 A–E）；破产 → `bankrupt`（失败不计分）
- 结算只发生一次，之后 `paused=true`，`Session.apply/control` 拒绝继续

### 参数入口

| 想改 | 改哪 |
|---|---|
| 成本、票价、效用、需求系数 | `calibration/params.json` → 重启生效 |
| 机场、能级、区域、时刻容量 | `calibration/airports.csv` |
| 机型（座位/航程/成本/舒适度） | `sim/aircraft.csv` |
| AI 行为常量（决策周期、目标载客率） | `sim/ai.py` 顶部 |
| 目标期限与评级 | `sim/config.py`（`GOAL_YEARS` / `GOAL_RATINGS`） |

重新标定：`python calibration/calibrate.py`（需要 numpy）。

---

## 8. 存档格式

`saves/*.json`，顶层两段：

```json
{
  "meta": {"version": 1, "saved_at": "...", "day": 32, "name": "..."},
  "game": {
    "day": 32, "seed": 42, "speed": 4, "paused": false,
    "mode": "goals", "mode_chosen": true,
    "goal_start_day": 0, "goal_deadline_day": 3600,
    "goal_state": {...}, "settlement": null,
    "player": {...}, "airlines": [...], "routes": [...],
    "world": {"slots_used": {...}}, "log": [...], "rng_state": "..."
  }
}
```

- 写入走「临时文件 + 原子替换」
- `from_save()` 手工校验并重建对象；旧存档缺 `mode/goal_*` 时默认沙盒，仍可读
- 随机数状态入档：同一天重放结果一致（FR-1202）
- 单档约 0.4 MB（50 AI、30 天量级），上限 5 MB 有余量

---

## 9. 关键设计决策

1. **后端用标准库 `http.server`，不引框架**：零依赖分发；接口契约与框架无关，换 FastAPI 只改 `api.py`。
2. **时钟在后端，前端只读**：暂停/加速对所有人一致。
3. **前后端只通过 JSON 快照通信**：快照是裁剪视图，对手不给成本、收入与财务（票价按公开口径可见）。
4. **玩家不是 AI 的特例，而是被排除在 AI 决策之外**：`advance_day()` 里 `if al.is_player: continue`。
5. **存档用显式 JSON，不用 pickle**：可读、可排查、不执行任意反序列化。
6. **自动存档 + supervisor 负责安全重启**：浏览器无需进程权限，重启不丢对局。
7. **前端零构建、多文件**：`<script>` 顺序即依赖顺序；不引打包器，分发即源码。

---

## 10. Demo 边界与安全

这是**本地单机 Demo**，不是生产服务：

- 只由本机同版本前端访问后端；输入来自可信玩家
- 不做鉴权、限流、CSRF、跨进程存档锁、字段级 schema 校验
- `/api/command` 收到非数字的 `daily_flights`/`price_index`/`amount` 时，可能直接结束请求
- 多个端口同时读写同一个 `saves/` 没有加锁，测试请用副本或独立目录
- 后端只绑 `127.0.0.1`，静态文件服务有目录穿越防护（`Path.relative_to` 校验）

产品化优先级：参数类型校验与统一错误响应 → 鉴权/限流 → 存档并发与原子写 → 反向代理。

---

## 11. 已知问题与未做

| 项 | 状态 |
|---|---|
| 目标模式「逐目标勾选」 | 未做。当前固定四目标，满足 FR-1102「可同时追踪」 |
| 区域份额口径 | 近似值：跨区航线按航段端点数量均摊客流 |
| 公司级财务面板 | 未做，只有航线级可归集损益 |
| 二手飞机市场、时刻回收可视化 | 未做 |
| 结算历史/回放、音效 | 未做 |
| 浏览器视觉验收 | 自动化只覆盖 DOM 与资源引用，像素级外观需人工过一遍 |
| 快照体积随天数增长 | 50 AI 第 60 天约 54.7 KB、第 90 天约 56.2 KB |
| 重建快照/存档的字段变更 | 需要手动同步 `to_save`/`from_save` 与本文档 |

---

## 12. 打包发布

```powershell
powershell -ExecutionPolicy Bypass -File tools/package.ps1 -Version 1.0
```

脚本会：复制运行所需文件到 `release/airline-sim-v<版本>/` → 排除 `saves/*.json`、
`__pycache__`、`release/`、`.git` → 校验没有残留交接文档 → 跑全部测试 → 打 zip。

发布 zip 建议作为 **GitHub Release** 附件（tag `v1.0`），不要提交进 git。

> `.ps1` 必须 UTF-8 **带 BOM**；`.cmd` 内不写中文。

---

## 13. 文档索引

| 文档 | 内容 |
|---|---|
| `docs/航空公司模拟经营-需求文档-v1.0.md` | 48 条 FR 与验收标准（数据源） |
| `docs/航空公司模拟经营-规则边界.md` | 规则推导、决策记录（D/R 编号）、漏洞登记簿 |
| `CONTRIBUTING.md` | 分支、提交规范、目录边界、PR 清单 |
| `CHANGELOG.md` | 每轮代码/文档变更与验证结果 |
| `sim/README.md` | 内核机制、口碑与定价演化、基准场景 |
| `calibration/report.md` | 标定报告（拟合指标、参数来源） |
