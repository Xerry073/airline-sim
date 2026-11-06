# 变更记录

按轮次记录实际代码与文档变更。需求文档的 FR 编号、验收条款和 `calibration/` 标定参数不在本文件改动范围内。

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
