# 航空公司模拟经营 Ver 1.0

单机航空经营模拟：你经营一家航空公司，和最多 50 家 AI 在同一张真实航线网络上抢客源。

- **浏览器里玩**：界面跑在 `http://127.0.0.1:8777/`，后端在本机跑权威模拟
- **不需要联网**：底图、机场库、机型库全部内置
- **不需要装任何第三方库**：后端纯 Python 标准库，前端零构建
- **单机存档**：进度存在 `saves/`，随时保存、退出、下次接着玩

---

## 30 秒上手

1. 确认有 **Python 3.9+**：命令行执行 `python --version`
2. **双击 `start.cmd`**（会等后端就绪再自动开浏览器）
3. 浏览器打开 <http://127.0.0.1:8777/> 后，先选玩法：

   | 选择 | 适合 |
   |---|---|
   | **沙盒** | 无终点，随便折腾，随时存档退出 |
   | **目标** | 10 游戏年内完成 4 个目标，按达成数评 A–E |

4. 退出：双击 **`quit.cmd`**，或页面右上角「存档 → 保存并退出」

> 只关浏览器标签**不会**退出游戏，后端时钟还在推进。要真正结束请用 `quit.cmd`。

macOS / Linux 没有 `.cmd` 启动器，直接在项目目录执行 `python server/supervisor.py` 即可。

---

## 文档

| 文档 | 给谁 | 内容 |
|---|---|---|
| **[README-玩家.md](README-玩家.md)** | 玩家 | 怎么玩、界面入口、破产线、常见问题 |
| **[README-开发者.md](README-开发者.md)** | 开发者 | 架构、模块边界、API 契约、测试、调参、打包 |
| **[CONTRIBUTING.md](CONTRIBUTING.md)** | 贡献者 | 分支与提交规范、目录边界、PR 检查清单 |
| [CHANGELOG.md](CHANGELOG.md) | — | 按轮次记录代码与文档变更 |
| [sim/README.md](sim/README.md) | 开发者 | 内核机制、口碑/定价演化、基准场景数据 |
| [docs/](docs/) | 产品 | 需求文档（48 条 FR）、规则边界（R/D 编号） |

---

## 仓库结构

```
server/           后端（标准库 http.server，零依赖）
  app.py            命令行参数与启动
  api.py            HTTP 路由、静态文件
  session.py        一局游戏：时钟、指令、存档
  meta.py           /api/meta 元数据
  paths.py          路径与内核 import
  supervisor.py     监督进程，负责页面内「保存并重启」

sim/              模拟内核（纯 Python，无 IO）
  simulate.py       兼容门面（re-export）
  config.py         系数、目标常量、区域名
  util.py           工具函数
  model.py          World / Aircraft / Route / Airline
  products.py       行程产品构建
  market.py         需求分配（logit + 段容量）
  settle.py         日结算
  ai.py             AI 决策
  goals.py          目标模式判定
  game.py           Game：推进、指令、快照、存档
  report.py         批量模拟与报告
  selftest.py       56 条验收自测

web/              前端（零构建，纯静态）
  index.html        页面结构 + 脚本加载顺序
  css/app.css       样式
  js/map.js         地图与几何
  js/routes.js      航线图层
  js/interaction.js 悬停、点击、开线向导
  js/panels.js      运营面板
  js/saves.js       存档面板
  js/goals.js       目标模式
  js/app.js         入口与启动绑定
  data/world.geo.json  内置陆地轮廓

calibration/      系数表与机场数据（params.json、airports.csv、calibrate.py）
tools/            测试脚本（asset/map/goal/panel/route_gui_check.js）与打包脚本
docs/             需求文档、规则边界
saves/            存档（运行时生成，不入库）
```

---

## 开发

```bash
python server/supervisor.py --port 8777 --ai 10 --day-seconds 0.5 --speed 4
```

提交前跑：

```bash
python sim/selftest.py
node tools/asset_check.js
node tools/map_check.js
node tools/goal_check.js
node tools/panel_check.js
node tools/route_gui_check.js
```

CI 在 `.github/workflows/ci.yml`，规则细节见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 打包发布

```powershell
powershell -ExecutionPolicy Bypass -File tools/package.ps1 -Version 1.0
```

产出 `release/airline-sim-v1.0/` 与同名 zip；zip 建议作为 GitHub Release 附件上传。

---

## 运行环境

| 项 | 要求 |
|---|---|
| 操作系统 | Windows 10 / 11（启动脚本是 `.cmd` + `.ps1`）；核心纯 Python，其他平台可直接跑 |
| Python | 3.9 及以上，**只用标准库** |
| 浏览器 | Chrome / Edge / Firefox 等现代浏览器 |
| 网络 | 不需要 |
| Node.js | 仅跑前端测试时需要，玩游戏不需要 |

## 边界

- 单机 Demo：后端只监听 `127.0.0.1`，不做鉴权/限流/字段级校验，详见开发者文档「Demo 边界」
- 时间：1 游戏日 = 60 秒 ÷ 倍速（默认 4 倍速 ≈ 15 秒一天）
- 存档：JSON 明文，单档约 0.4 MB（50 AI、30 天量级）
