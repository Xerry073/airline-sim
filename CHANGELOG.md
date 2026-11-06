# 变更记录

按轮次记录实际代码与文档变更。需求文档的 FR 编号、验收条款和 `calibration/` 标定参数不在本文件改动范围内。

---

## 2026-11-07 · 修正轮：租赁机只能退租；卖机/退租不得吃穿运力

反馈：租赁来的 E190 竟然有「出售」按钮，而且运力已经 47.8/32 h 还允许减飞机，等于放任超载。

### 变更

- **租赁与自有区分**（`sim/model.py`、`sim/game.py`、`web/js/panels.js`）
  - 自有飞机 → 「出售」，按市价 85% 回笼现金（原逻辑不变）
  - 租赁飞机 → 「退租」，只退还押金（3 个月租金口径，与买入时一致），**不产生二手收入**
  - `sell_aircraft` 返回值新增 `kind: "sell" | "return"`，日志分别记「出售飞机」「飞机退租」
  - 机队表头「出售可得」改为「出手/退租」，租赁行显示「退押金」
- **运力护栏**：卖机/退租前先试算 (机型, 基地) 池，若会让在飞航线吃穿运力则直接拒绝
  - 报错写明池子占用与建议：「PEK 的 A320 运力会被吃穿：已占 26.2/32 h…先给这个基地的航线减班或关线」
  - 与开线、改班次、换机型、调机共用同一套「允许补救、禁止恶化」判据
- **文档**：玩家手册补「出售/退租」一行；README-开发者指令表补 `sell_aircraft` 的新语义

### 测试

- `sim/selftest.py` 64 → **66**：卖机会吃穿运力时被拒；租赁机退租只退押金且不留在机队
- `tools/panel_check.js` 16 → **17**：机队面板对租赁机显示退租/押金

```text
python sim/selftest.py        -> 66 / 66
node tools/asset_check.js     ->  5 /  5
node tools/map_check.js       -> 31 / 31
node tools/goal_check.js      ->  8 /  8
node tools/panel_check.js     -> 17 / 17
node tools/route_gui_check.js -> 10 / 10
```

---

## 2026-11-07 · 修正轮：运力按「机型 + 基地」分池，禁止飞机瞬移

反馈：租赁的 E190 空闲，却开不了新航线——因为运力是按全机队小时池算的，
A320 航线把 E190 的时间也吃掉了；而且同一架飞机一天可以在两个无关机场之间「瞬移」。

### 根因

`capacity_hours()` 用 `16 h × 机队总数` 做分母，`route_hours()` 按航线的机型算分子，
两者之间没有「哪架飞机在哪个机场」的对应关系。于是：

- 2 架 A320 能飞 47.8 h（上限本该 32 h），多出来的时间是 E190 的
- 8 条航线里有 3 条从 SHA/XIY/DEL 起飞，而这些机场根本没有基地飞机

### 变更

- **运力池改为 (机型, 基地)**（`sim/model.py`）
  - `base_capacity(type, base)`、`usage_by_base()`、`excess_by_base()`、`fits_route()`
  - 一架飞机一天只能从一个机场起飞；航线都是往返，所以出发机场就是它的基地
  - 校验统一走「允许补救、禁止恶化」：超载的旧存档仍可减班/关线/换机型，但不能更糟
- **`open_route` 增加两道校验**（`sim/game.py`）
  - 机队里必须有该机型（原来没查，理论上可以拿没买过的机型开线）
  - 该 (机型, 出发机场) 池要装得下；报错会写清哪个池、已占多少、需要多少
- **新增 `rebase_aircraft` 调机**（`sim/game.py`、`web/js/panels.js`）
  - 把飞机挪到任意机场，费用按距离与 MTOW 计（PEK→SHA 约 0.3 ¥M）
  - 调机后原基地运力不得被吃穿（在飞的航线要先减班/关线）
  - 机队面板新增「调机」卡片；指令 `rebase 12 SHA`
- **买机基地不再限于枢纽**（`web/js/panels.js`）：基地下拉改成全部机场，
  否则 SHA/XIY 这类出发地永远没法配飞机
- **修跑道等级判定方向**（`sim/util.py`、`sim/ai.py`、`sim/game.py`）
  - 原来 `支线: ("R",)`，等于 E190/ATR72 只能落 R 级机场——而全图只有 S/W，
    结果换机型到 E190 永远报「跑道等级不满足」
  - 改为「机型等级 ≤ 机场等级」：支线 ≤ S ≤ W，宽体只能落 W；直飞开线也补上这项校验
- **AI 适配**（`sim/ai.py`）
  - 开线前按 (机型, 机场) 检查运力；不够就买同型机，最多补 2 架
  - 优先从「已有基地飞机」的城市机场出发；跑道不允许时降级到窄体

### 测试

- `sim/selftest.py` 58 → **64**：机型封顶、空闲机型可开线、未拥有机型、跑道方向、
  异地无基地不能开线、调机后可以
- `tools/panel_check.js` 15 → **16**：航线面板显示该基地运力池、机队面板有调机入口

### 基准（50 AI × 720 日）

| 指标 | 改前 | 改后 |
|---|---|---|
| 存活 | 49 / 50 | 49 / 50 |
| 航线条数 / 机队 | 769 / 513 | 488 / 439 |
| 全网载客率 | 87.4% | 87.8% |
| 行业 EBITDA 率 | 14.5% | 14.0% |
| 经停航线占比 | 4% | 19% |

行业规模变小是预期的：每条航线都要有一座「停着飞机」的机场，扩张变慢、网络更集中在基地。

> 旧存档里已经超载的 (机型, 基地) 池会显示为红色「超载」，新开线会被拦下；
> 处理办法：关线/减班腾出运力，或调机/买机补上——这正是这次要复现的现实约束。

---

## 2026-11-06 · 参数轮：下调成本系数，让小规模航司能盈利

背景：玩家 3 架飞机、8 条航线、机队占机 99.6%、平均载客率 89.8%，可归集利润合计
0.32 ¥M/日，但公司 EBITDA 仍是 −0.37/日。固定开销 0.775（人工 0.499 / 枢纽 0.080 /
折旧 0.060 / 租赁 0.136）把小航司一刀砍死；AI 因为规模大（7 机、9 线）反而普遍盈利。

### 变更（`sim/config.py` 的 `ECON`）

| 系数 | 原值 | 新值 | 说明 |
|---|---|---|---|
| `staff_base_M_day` | 0.15 | **0.08** | 总部基础人工 |
| `staff_per_aircraft_M_day` | 0.05 | **0.030** | 每架飞机的人工 |
| `staff_per_segment_M_day` | 0.010 | **0.006** | 每航段的人工 |
| `hub_fixed_by_scale` | XL .08 / L .06 / M .04 / S .02 / R .01 | **XL .05 / L .04 / M .025 / S .012 / R .006** | 枢纽固定费整体降约 38% |
| `idle_cost_M_day` | 0.02 | **0.01** | 闲置成本 |
| `depreciation_years` | 20 | **28** | 折旧年限（按你最初的想法也降了折旧） |
| `residual` | 0.10 | **0.15** | 残值率 |
| `lease_rate_month` | 0.0055 | **0.0038** | 租赁率 |
| `nav_rate_M_per_km` | 1.0e-5 | **0.8e-5** | 航路导航费 |
| `landing_base_M` | 0.008 | **0.0068** | 起降费基准 |
| `maint_load_factor` | 1.40 | **1.25** | 维护成本系数 |
| 燃油 / 分销 / 地服 | — | **不变** | 保持标定值 |

### 实测（同一份玩家存档，3 机 8 线）

| 场景 | 改前 EBITDA | 改后 EBITDA |
|---|---|---|
| 按当前方式经营（1–2 班、指数 ~0.97） | −0.371 | **+0.007** |
| 加密班次 + 价格指数 1.15 | +0.115 | **+0.484** |

固定开销从 0.775 降到 0.474；航线利润合计从 0.145 升到 0.321（起降/导航/维护下调叠加）。

### 基准场景（50 AI × 720 日 × 3000 ¥M，`python sim/simulate.py --days 720 --ai 50`）

| 指标 | 改前 | 改后 |
|---|---|---|
| 存活 | 50 / 50 | 49 / 50 |
| 航线条数 / 机队 | 663 / 482 | 769 / 513 |
| 全网载客率 | 93.3% | 87.4% |
| 行业 EBITDA 率 | 14.3% | 14.5% |
| 日收入 / EBITDA | 407.7 / 58.3 | 374.0 / 54.1 |

`--cost-mult` 难度实测（360 日）：1.0 → 0/50 破产，1.2 → 0/50，1.35 → 1/50。默认难度因此从
「小航司必亏」变成「玩家能活、但要靠经营赶超 AI」。

### 测试

```text
python sim/selftest.py        -> 58 / 58
node tools/asset_check.js     ->  5 /  5
node tools/map_check.js       -> 31 / 31
node tools/goal_check.js      ->  8 /  8
node tools/panel_check.js     -> 15 / 15
node tools/route_gui_check.js -> 10 / 10
```

> 只动成本侧，票价与需求标定（`calibration/params.json`、`p_ref`）未改。

---

## 2026-11-06 · 可解释性轮：把「航线都赚、公司却亏」摆在面上

背景：玩家开了 4 条航线、每条利润率都是正的，公司 EBITDA 却是 −0.48。查下来折旧只占成本
4.7%，真正的原因是**机队只用了 46%**（22.3/48 小时）+ 价格指数偏低（0.96–1.05，同市场 AI 约 1.2）。
按「不改数值、只把账说清楚」的决定，这一轮只做可见性。

### 变更

- **快照新增成本分项与利用率**（`sim/settle.py`、`sim/game.py`）
  - `settle_day()` 把当日 12 项成本拆解存到 `al.last_costs`，随存档往返
  - `player.costs{fuel…total, fixed_total}`、`player.capacity{hours_used,hours_cap,segments_used,segments_cap}`
  - `fixed_total` 只含人工 + 枢纽固定 + 折旧 + 租赁 + 利息 + 闲置，即可归集成本之外的部分
- **侧栏 KPI 增加「日占机」**（`web/js/app.js`、`web/css/app.css`）
  - 显示 `22.3/48h`，≥75% 绿、<50% 黄；标题说明固定开销按机队发生
- **航线管理增加「公司固定开销」卡片**（`web/js/panels.js`）
  - 人工 / 枢纽 / 折旧 / 租赁 四项明细，合计 `fixed_total`
  - 「全部航线利润合计」「覆盖固定开销后」两行直接给出差额（正绿负红）
  - 附机队占机率与一段说明：航线利润只扣可归集成本，固定开销摊不薄就是亏
- **文档**：玩家手册新增「为什么每条航线都赚钱，公司还是亏」；KPI 与快照契约同步
- **测试**
  - `sim/selftest.py` 56 → **58**：成本分项齐全且 `fixed_total` 自洽；利用率字段在合理区间
  - `tools/panel_check.js` 14 → **15**：固定开销卡片、利润合计、占机率文案

### 测试

```text
python sim/selftest.py        -> 58 / 58
node tools/asset_check.js     ->  5 /  5
node tools/map_check.js       -> 31 / 31
node tools/goal_check.js      ->  8 /  8
node tools/panel_check.js     -> 15 / 15
node tools/route_gui_check.js -> 10 / 10
```

### 说明

数值（`ECON`）一个都没改：折旧年限、残值、人工、租赁率维持原样。这一轮只是把
「固定开销 vs 航线利润」和「机队利用率」变成可读的数字。

---

## 2026-11-06 · 运营轮：航线可以换机型

目的：原来一条航线开通时机型就定死了，想从小飞机换大飞机只能关线重开（还要吃时刻与
口碑的损失）。现实中航司按季节换机型是常规操作。

### 变更

- **新增指令 `set_aircraft`**（`sim/game.py`）
  - `{route_id, ac_type}` → 换机型；机队里没有该机型时拒绝（只能在自己运营的型号间调机）
  - 校验：机型存在；2 段航线直接走单段航程 + 跑道等级校验，经停航线走完整
    `validate_stopover()`（航程/跑道/绕行/16h）；换更慢的机型后再验一次机队日占机
  - 换成同一机型是空操作（`changed: false`），不写日志
  - 成功写一条「更换机型」事件日志
- **航线管理面板**（`web/js/panels.js`）
  - 新增「机型」卡片：下拉只列**机队已有型号 + 当前机型**，每个选项带座位与航程
  - 选中后实时显示「最长航段 X km · 该机型航程 Y km」，超出时标红提示
  - 「更换机型」按钮调用 `set_aircraft`，失败原因由 `api()` 弹出
- **高级指令**：`ac 3 B789`（`web/js/app.js`），教程面板同步加一行
- **测试**
  - `sim/selftest.py` 52 → **56**：换机型成功、同机型空操作、机队没有该机型被拒、机型不存在被拒
  - `tools/panel_check.js` 13 → **14**：下拉只列机队型号、带更换按钮

### 测试

```text
python sim/selftest.py        -> 56 / 56
node tools/asset_check.js     ->  5 /  5
node tools/map_check.js       -> 31 / 31
node tools/goal_check.js      ->  8 /  8
node tools/panel_check.js     -> 14 / 14
node tools/route_gui_check.js -> 10 / 10
```

> 换机型不买卖飞机：机队规模与现金都不变，改变的只是这条航线由哪种机型执飞。

---

## 2026-11-06 · 交互轮：选中起点后聚焦该机场已连通的航线

目的：右键选完起点，玩家最想知道的是「这个机场已经连通了哪里、还有哪些方向空着」。
原来所有航线一律同亮度，AI 航线还会跟自己的航线互相盖住。

### 变更

- **`applyRouteFocus()`**（`web/js/routes.js`）
  - 只要 `sel`（起点/终点）或经停点非空，就按「航线是否经过这些机场」给每个航线节点打
    `.focus` / `.dim`
  - 玩家航线：命中的保持原色并提亮（蓝=我的、黄=竞争），未命中的压到 12% 透明度
  - AI 航线：开关打开时同样处理（灰=普通、暗黄=竞争），未命中的压到 12%
  - 在 `syncRoutes()` / `syncRivalRoutes()` 末尾以及每个选择动作后调用，刷新与切换开关都不会丢焦点
- **纯函数 `routeTouches(segments, codes)`**（`web/js/map.js`，放进 `MAP_MATH` 段便于抽取测试）
- **选中起点的提示带条数**：`PEK 已设为起点 · 我的 2 条 · AI 5 条`；
  AI 航线开关没开时提示 `AI 5 条（开关未开）`，不至于让人以为这个机场没人飞
- **样式**（`web/css/app.css`）：`.focus` 提亮、`.dim` 压暗，过渡 0.2s

### 测试

- `tools/map_check.js` 28 → **31**：`routeTouches` 的方向不敏感、经停点命中、无关机场不命中

```text
python sim/selftest.py        -> 52 / 52
node tools/asset_check.js     ->  5 /  5
node tools/map_check.js       -> 31 / 31
node tools/goal_check.js      ->  8 /  8
node tools/panel_check.js     -> 13 / 13
node tools/route_gui_check.js -> 10 / 10
```

> 焦点只是视觉强调，不改任何数值与判定；AI 航线是否出现仍由左上角「AI 航线」开关决定。

---

## 2026-11-06 · 信息轮：玩家航线也输出 OD 票价，与对手并排比价

目的：上一轮只显示了对手的价格指数，玩家还得自己换算才比得出「我贵多少」。现在两侧
用同一口径输出 OD 票价，面板直接并排。

### 变更

- **快照**（`sim/game.py`）
  - `player.routes[]` 增加 `prices[]{from, to, eco, biz}`，与 `opponent_routes[].prices` 同一实现
    （`Route.public_fares()`，`p_ref(两端直线距离, 舱位) × price_index`，R-632）
  - 没有新增计算路径，也没有引入成本/收入字段
- **航线管理 · 竞争者卡片**（`web/js/panels.js`）
  - 每个对手航线下面并排列出**重叠 OD** 的票价：`PEK → SHA：我 ¥1,190 · 对手 ¥880 低 26%`
  - OD 匹配按**城市**、方向不敏感：`SHA` 与 `PVG` 视为同一个市场
  - 价差 |差| ≥ 1% 才标色（对手更便宜 = 红，更贵 = 绿）
  - 对手或自己没有 `prices` 时（旧后端 / 无重叠 OD）自动退回价格指数比较，不出现空白
- **测试**
  - `sim/selftest.py` 52 条：新增「玩家航线带 OD 票价，口径与对手一致」
  - `tools/panel_check.js` 13 条：新增并排票价、SHA/PVG 同城匹配、缺 `prices` 时退回指数比较

### 测试

```text
python sim/selftest.py        -> 52 / 52
node tools/asset_check.js     ->  5 /  5
node tools/map_check.js       -> 28 / 28
node tools/goal_check.js      ->  8 /  8
node tools/panel_check.js     -> 13 / 13
node tools/route_gui_check.js -> 10 / 10
```

---

## 2026-11-06 · 信息轮：我的航线面板显示竞争者公开数据

目的：调价/改班次时，玩家要能在同一个地方看到「对手在这条市场上开几班、卖多贵、坐得多满」，
否则只能凭载客率猜。

### 变更

- **航线管理面板新增「竞争者」卡片**（`web/js/panels.js`）
  - 按「共享同一城市市场」筛出对手航线，按班次降序取前 10 条
  - 每条显示：航空公司、航段、每日班次、载客率、价格指数
  - 价格差 ≥1% 时追加一行「价格指数比你低/高 N%（你的 X.XX）」
  - 左上指标里的「竞争」改为带条数：`有 AI 共享市场（N 条）`
  - 超过 10 条时提示「另有 N 条未显示」，并注明对手只有公开口径数据
- **测试**（`tools/panel_check.js`，7 → 10 条）
  - 抽取 `renderRouteOp()`，用桩注入 `routeMarketSet`/`routeIsContested`（与 `map.js` 同源）
  - 覆盖：竞争者列表内容与价差方向、不相关市场不出现、无竞争时的占位

### 说明

- 竞争者数据完全来自已有的公开快照（`opponent_routes[].lf / daily_flights / price_index`），
  没有新增后端字段，也没有放开财务数据
- 修的是「玩家看得见竞争却看不见对手怎么定价」，属于信息展示，不改模拟内核

### 测试

```text
python sim/selftest.py        -> 51 / 51
node tools/asset_check.js     ->  5 /  5
node tools/map_check.js       -> 28 / 28
node tools/goal_check.js      ->  8 /  8
node tools/panel_check.js     -> 10 / 10
node tools/route_gui_check.js -> 10 / 10
```

---

## 2026-11-06 · 信息轮：公开 AI 航线的票价

目的：对手航线原来只公开「航段 / 班次 / 载客率」，玩家无法判断对手是低价抢量还是高价收割；
现在把票价纳入公开信息，同时继续隐藏成本与财务。

### 变更

- **快照新增公开票价**（`sim/game.py`、`sim/model.py`）
  - `opponent_routes[]` 增加 `price_index`（4 位小数）与 `prices[]`
  - `prices[]` 覆盖该航线服务的每个 OD：`{from, to, eco, biz}`
  - 票价算法与玩家侧一致：`p_ref(OD 两端直线距离, 舱位) × 价格指数`（R-632），
    经停航线按每个 OD 单独计算，不是整条航线的平均价
  - 成本、收入、利润**仍然不进入快照**；`Route.public_fares()` 只读票价
- **前端**（`web/js/panels.js`、`web/js/interaction.js`）
  - 「航线详情」面板新增「价格指数」格与「公开票价」列表（经济 / 商务），多 OD 逐条列出
  - 悬停提示增加价格指数；底部说明改为「公开网络、班次、载客率与票价；成本、收入与财务不公开」
- **规则与需求文档口径同步**（这是本次唯一的规则变更）
  - `docs/…需求文档…` FR-1002：可见项由「票价区间、不显示精确票价」改为「价格指数与各 OD 参考票价」
  - `docs/…规则边界…` §10 UI 信息边界同步修改

### 测试

- `sim/selftest.py`：UI-03 由「不泄露票价」改为三条——公开价格指数与 OD 票价、
  票价 = 参考价 × 价格指数、仍不泄露成本/收入/利润；总数 49 → **51**
- `tools/panel_check.js`：新增 2 条抽 `renderPublicRouteOp()` 验证票价渲染与文案，总数 5 → **7**

```text
python sim/selftest.py        -> 51 / 51
node tools/asset_check.js     ->  5 /  5
node tools/map_check.js       -> 28 / 28
node tools/goal_check.js      ->  8 /  8
node tools/panel_check.js     ->  7 /  7
node tools/route_gui_check.js -> 10 / 10
```

### 取舍

公开精确票价会削弱信息不对称：玩家能直接看出对手在打价格战还是收溢价，AI 调价的可预测性上升。
按 FR-1002 的「可见区间」原口径，另一种做法是只给区间（如 0.9–1.0），但那样既不给具体价、
也不告诉玩家自己贵在哪里。这里选择了「透明票价 + 隐藏财务」，若后续要收紧，改
`Game.snapshot()` 里 `prices` 的聚合粒度即可，前端字段可原位替换。

---

## 2026-11-06 · 交互轮：地图开线改为右键起点 / 左键终点 / Alt+左键经停

目的：把「点两下机场」的隐式选择换成分工明确的三个手势，并让经停航线能在图上一次选齐。

### 变更

- **地图开线手势**（`web/js/{map,interaction,app}.js`、`web/css/app.css`）
  - 右键点机场 = 设起点（仅在地图上拦截浏览器右键菜单）
  - 左键点机场 = 设终点，选定即打开开线向导
  - `Alt + 左键` = 加/取消经停点，再按一次取消；向导标题显示 `起点 → 经停 → 终点`
  - 标记：起点 `① 北京`、终点 `② 上海`（黄），经停点 `经 成都`（紫 + 虚线光环）
  - 左键换终点时沿用起点重开向导；右键改起点会先关掉已打开的向导
  - 非法组合拒绝并说明原因：同城机场、起点=终点、经停点=起点、经停点与起点同城
- **经停向导**：显示每段航距、总航程、直飞距离与绕行系数；开通失败时把后端原因回显在向导里
  （原来只弹一条 toast，向导内不显示）
- **新增测试** `tools/route_gui_check.js`（10 条）：从 `interaction.js` 抽取 `ROUTE_PICK_START/END`
  之间的选择状态机，用桩验证航段顺序与四类非法选择
- `.github/workflows/ci.yml`、`tools/package.ps1` 同步纳入第 6 套前端检查

### 修复

- `web/js/panels.js` 底部「开航线」面板的经停点顺序错误：原来提交 `[起点, 终点, 经停]`，
  等于把终点当经停点、把经停点当终点；改为 `[起点, 经停, 终点]`，与 `open` 指令和
  内核 `validate_stopover()` 的口径一致

### 文档

- `README-玩家.md`：地图手势表、经停航线开法、地图条目提到新手势
- `README.md`、`README-开发者.md`、`CONTRIBUTING.md`：测试清单加入第 6 套并说明抽取方式

### 测试

```text
python sim/selftest.py        -> 49 / 49
node tools/asset_check.js     ->  5 /  5
node tools/map_check.js       -> 28 / 28
node tools/goal_check.js      ->  8 /  8
node tools/panel_check.js     ->  5 /  5
node tools/route_gui_check.js -> 10 / 10
python -m compileall -q server sim calibration -> exit 0
```

> 未做浏览器内实点验证：`route_gui_check` 只验证选择状态机，不验证指针事件绑定与像素表现。
> 合并前建议用 `start.cmd` 实际点一遍右键起点 → 左键终点 → Alt+左键经停。

---

## 2026-11-06 · 协作轮：前后端拆分 + CI + 协作规范

目的：把两个巨型单文件拆成可并行修改的模块，并让"提 PR 必须先跑什么"有机器可验的定义。

### 后端拆分

`sim/simulate.py` 2368 行 → 10 个分层模块 + 兼容门面（行为零变化）：

```
config → util → model → products → market → settle → ai → goals → game → report
```

- 门面 `sim/simulate.py` 只做 re-export，`import simulate as S` 与 `python simulate.py --days 720` 用法不变
- `slot_touches` 从 AI 段下沉到 `util`（它被 `Airline` 使用，是唯一的向前引用）
- 分层靠 AST 分析生成 import，module 之间只允许单向依赖

`server/app.py` 548 行 → 5 个模块：
`paths.py`（路径与内核 import）· `session.py`（时钟/指令/存档）· `meta.py`（/api/meta）·
`api.py`（路由与静态文件）· `app.py`（CLI 与启动）。

### 前端拆分

`web/index.html` 108 KB 单文件 → `index.html`(4 KB) + `css/app.css` + 7 个 JS：

```
map → routes → interaction → panels → saves → goals → app
```

- 仍是零构建 classic script，按 `<script>` 顺序共享全局作用域
- 入口与启动绑定只保留在最后加载的 `js/app.js`
- 三个测试脚本改为从对应 JS 文件抽取（标记 `MAP_MATH_START/END`、`startNewGame`、`renderRivals`）

### 新增

- `tools/asset_check.js`（5 条）：资源是否存在、入口是否最后、脚本可否编译、跨文件 const/let 重名、中间脚本顶层语句
- `tools/package.ps1`：一键打包（复制 → 排除 → 自检 → 跑测试 → zip），替代手写步骤
- `.github/workflows/ci.yml`：push/PR 跑全部 5 套检查
- `CONTRIBUTING.md`：分支与提交规范、目录边界、PR 清单
- `.editorconfig`、`.github/PULL_REQUEST_TEMPLATE.md`
- 仓库文档重排：`README.md`（入口）、`README-玩家.md`、`README-开发者.md`；需求与规则文档移入 `docs/`

### 移除

- 三份交接文档（`交接-下一轮.md` / `交接-下一对话*.md`）：内部交接记录不再入库、不再打包

### 测试

```text
python sim/selftest.py      -> 49 / 49
node tools/asset_check.js   ->  5 /  5
node tools/map_check.js     -> 28 / 28
node tools/goal_check.js    ->  8 /  8
node tools/panel_check.js   ->  5 /  5
python -m compileall -q server sim calibration -> exit 0
```

HTTP 冒烟（项目副本 + 8793）：`/`、`/css/app.css`、`/js/*.js`、`/data/world.geo.json`
全部 200；`/api/state`、`/api/meta` 正常；`POST /api/quit` 后端口释放。

### 兼容与边界

- 存档格式、API、快照字段、游戏数值均未改变
- 前端改为多文件后，**更新时必须 `Ctrl+F5` 强刷**（旧页面会继续用缓存的内联脚本）
- 模块之间直接 `from x import f`，测试里 monkeypatch 要打在「使用处」所在模块
  （`market.allocate` 用 `market.build_products`，patch 门面无效）——`sim/selftest.py` 已按此修正

---

## 2026-11-06 · 打包轮：发布包 + 玩家/开发者文档

### 变更

- **启动器去依赖**（`start.ps1`）
  - 探测条件由 `import sys,numpy` 改为 `import sys`：本游戏只用标准库，原先的 numpy 探测会让
    没装 numpy 的机器误判为「没有可用 Python」。
  - 删除写死的本机运行时路径，补充 `py` 启动器与 Python 3.9/3.10 常规安装位。
  - 报错文案改为「装 Python 3.9+，不需要第三方包」。
  - 保持 UTF-8 BOM 与 `.cmd` 纯 ASCII 约定。
- **发布包** `release/airline-sim-v1.0/`
  - 只含运行所需文件，排除 `__pycache__`、`saves/*.json`；`saves/` 以空目录 + `.gitkeep` 交付。
  - 文档分层：根目录入口 `README.md` + `README-玩家.md` + `README-开发者.md`，
    需求/规则/交接记录移入 `docs/`。
- **文档**
  - `README-玩家.md`：启动退出、模式选择、界面入口、开线流程、破产线、常见问题。
  - `README-开发者.md`：架构、目录、CLI 参数、API 契约、快照字段、测试、内核要点、存档格式、
    设计决策、Demo 边界、已知问题、**重新打包发布流程**。

### 验证

在发布目录内（路径全为相对路径）执行：

```text
python sim/selftest.py        -> 49 / 49
node tools/map_check.js       -> 28 / 28
node tools/goal_check.js      ->  8 /  8
node tools/panel_check.js     ->  5 /  5
python -m py_compile ...      -> exit 0
```

并用发布目录的 `start.ps1` 在独立端口做一次真实启动、`/api/state` 读取、`POST /api/quit` 退出，
确认端口释放、`saves/` 只留下本次自动存档（打包前已清空）。

### 影响与边界

- 存档格式、API、游戏数值均未改变，与上一轮存档双向兼容。
- 发布包不含 `saves/` 里的任何历史存档，也不含桌面快捷方式（`.lnk` 指向绝对路径，换机即失效）。

---

## 2026-11-06 · 修正轮：侧栏「竞争对手」面板口径

### 变更

- **后端** `Game.snapshot()`（`sim/simulate.py`）
  - `rivals[]` 只含存活且非本公司的对手，按 `rank_score` 降序取前 20。
  - 每条新增 `rank`：全体存活公司名次，与 `player.rank` 同口径（过滤自己后名次会留空档）。
  - 新增 `rivals_total`：全部存活对手家数（玩家已排除）。
- **前端** `web/index.html`
  - 抽出 `renderRivals(s)`，`render()` 改为调用它。
  - 标签：对手超过 20 家时显示 `TOP 20/N`，否则显示 `N 家`；悬停说明「按市值排名，不含本公司」。
  - 表格渲染前 20 行（原为 14 行），新增名次列 `td.rk`；空榜显示「暂无对手」。
  - 名称继续走 `escHTML`，避免注入。
- **测试**
  - `sim/selftest.py` 新增 3 条 FR-1002 用例（不含本公司 / 上限 20 与 `rivals_total` / 名次口径），46 → 49。
  - 新增 `tools/panel_check.js`：5 条前端面板口径校验（20/50、全部 5 家、空榜、缺 `rivals_total` 兜底、名称转义）。

### 验证

```text
python sim/selftest.py        -> 49 / 49
node tools/map_check.js       -> 28 / 28
node tools/goal_check.js      ->  8 / 8
node tools/panel_check.js     ->  5 /  5
python -m py_compile ...      -> exit 0
内联 JS node --check          -> exit 0
```

API 冒烟（项目副本 + 独立端口 8791 + 12 AI，不触碰真实 `saves/`）：
`/api/state` 返回 `rivals_total=12`、`rivals` 12 条、名次 1–12 连续、玩家不在榜内，
`GET /` 已包含 `renderRivals`。测试后 `/api/quit` 正常停服，端口无残留，`saves/` 未被改写。

### 影响与边界

- 存档格式未变；`rivals`/`rivals_total` 是快照派生字段，读档后按当前状态重算。
- 若有脚本按「`rivals` 第一条就是本公司」取数，需要改用 `player.rank` / `player.market_cap`。
- 排行榜仍是「市值（`rank_score`）前 20」的截断视图，不是全量榜单；`rivals_total` 只给家数，不给完整名单。

---

## 2026-11-06 · 实现轮：FR-403 修复 + 目标模式 FR-1101~FR-1103

### 新增

- **目标模式（FR-1101 / FR-1102 / FR-1103）**
  - `Game` 新增 `mode = sandbox | goals`、`mode_chosen`、`goal_start_day`、`goal_deadline_day`、`goal_state`、`settlement`。
  - 目标模式期限 3600 游戏日（10 × 360），逐日追踪四个目标：
    - 市值进前三：存活公司 `rank_score` 日排名曾 ≤ 3。
    - 区域霸主：航线最近结算日客流按航段端点区域均摊，任一区域份额曾 ≥ 35%。
    - 高质高效：月报 EBITDA 率 ≥ 15% 且客流加权准点率 ≥ 85%，连续 24 个月。
    - 网络扩张：日航段数 ≥ 100 且客流加权平均客座率 ≥ 75%，同日满足。
  - 评级：4/3/2/1/0 个目标达成 → A/B/C/D/E；0 个标记未达成、不计分；破产为失败。
  - 四个目标全部达成时提前结算，否则到期结算；结算后暂停并禁止继续经营。
  - 月报新增 `on_time` 与 `ebitda_rate`，供高质高效判定。
- **API**
  - `POST /api/new_game {"mode":"sandbox"|"goals"}`：按模式重建第 0 天对局。
  - `/api/meta` 增加 `goals`、`goal_years`、`days_per_year`、`goal_deadline_days`、`modes`。
  - `/api/state` 增加 `goals`：模式、期限、剩余天数、四目标进度、达成数、评级、结算结果。
  - CLI 新增 `--mode sandbox|goals`；省略时由页面选择。
- **前端**
  - 顶栏「目标 / 模式」按钮。
  - 新局模式选择面板：沙盒 / 目标。
  - 目标面板：10 年期限、四目标进度、A–E 结算、破产失败。
  - 结算自动暂停、弹出目标面板；结算后速度按钮与指令均会被拒绝。
- **测试/工具**
  - 新增 `tools/goal_check.js`：8 条前端逻辑校验（开局面板、沙盒/目标面板、A–E、0 分、破产、`/api/new_game` 调用）。
  - `sim/selftest.py` 新增 FR-1101~FR-1103 用例，最终 46 条。

### 修复

- **FR-403 时刻校验/记账/释放**
  - 新增 `slot_touches()`：按“每个航段的两端”统计机场触及次数，经停中间机场计 2 段。
  - `open_route` 按 `2 × 触及航段数 × daily_flights` 校验与记账，不再写死 `+2`。
  - `close_route` 立即释放对应时刻，不再等次日重算。
  - 每日全局重算同步改为按航段端点计数。
  - 玩家开线校验复用 `usable_slots()`，外站 HUB 只允许用 70%（FR-502）。
  - `from_save` 读档后按航线重算 `slots_used`，兼容旧存档。
- **AI 航线开关 Day 0 提示**
  - 区分三种情况：未连接后端 / 旧后端缺字段 / 新后端但第 0 天尚无 AI 航线。
  - 第 0 天不再提示“请重启后端”，改为“AI 通常会在开局第 1 天后逐步开线”。

### 文档

- `README.md`：新增目标模式说明、`/api/new_game`、`--mode`、Demo 边界与防御性编程、更新测试计数。
- `sim/README.md`：补目标模式与逐日追踪说明，测试计数更新为 46。
- `交接-下一对话-测试.md`：补目标模式事实、更新启动命令与测试计数（46/28/8）。
- `航空公司模拟经营-规则边界.md`：变更记录追加 v0.8 条目。
- `交接-下一轮.md`：新增当前状态、任务整理、已知问题与接手步骤，作为最新交接文档。

### 验证

```text
python sim/selftest.py        -> 46 / 46
node tools/map_check.js       -> 28 / 28
node tools/goal_check.js      -> 8 / 8
python -m py_compile ...      -> exit 0
内联 JS node --check          -> exit 0
```

API 实测覆盖：新局模式选择、`/api/new_game`、四目标进度、存档/读档、到期结算、结算后拒绝继续操作。
50 AI / 120 天回归：沙盒与目标模式的存活数、航线数、玩家现金一致（51 / 387 / 2479.2）。

### 已知边界

- 目标模式固定同时追踪四个目标；“可选”体现为沙盒/目标模式的开局选择，未做逐目标勾选。
- 区域份额按航线客流在航段端点区域均摊，是可解释近似，不是审计口径。
- `/api/command` 非法数字/类型仍按 Demo 边界处理，不保证返回 400 JSON；详见 README「Demo 边界与防御性编程」。
- 真实 `saves/` 未在测试中改写；测试使用临时副本。
