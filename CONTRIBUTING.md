# 参与开发

单机航空经营模拟，零第三方依赖。本文写给要改代码 / 调数值 / 提 PR 的人；
玩家向说明见 [README-玩家.md](README-玩家.md)，架构细节见 [README-开发者.md](README-开发者.md)。

## 1. 环境

| 用途 | 需要 |
|---|---|
| 跑游戏 | Python 3.9+，**只用标准库** |
| 跑测试脚本 | Node.js 18+（脚本零依赖，不需要 npm install） |
| 重新标定系数 | Python + numpy（只有 `calibration/calibrate.py` 用） |

不引入第三方运行时依赖是项目底线：分发时用户只要装 Python 就能跑。

## 2. 跑起来

```bash
python server/supervisor.py --port 8777 --ai 10 --day-seconds 0.5 --speed 4
# 浏览器打开 http://127.0.0.1:8777/
```

开发时用 `--day-seconds 0.5 --ai 5` 能几秒看到世界变化。
**不要用 8777 跑测试**，会覆盖正在玩的人 `saves/autosave.json`；换端口或用项目副本。

## 3. 提交前必须跑完

```bash
python -m compileall -q server sim calibration   # 语法
python sim/selftest.py                            # 66 条内核验收
node tools/asset_check.js                         # 前端资源引用与语法
node tools/map_check.js                           # 31 条地图几何
node tools/goal_check.js                          #  8 条目标模式
node tools/panel_check.js                         # 20 条对手榜、AI 票价、竞争对照、换机型、固定开销、调机
node tools/route_gui_check.js                     # 10 条开线手势
```

CI（`.github/workflows/ci.yml`）会跑同样一套。本地全绿再推，PR 才可能过。
**测试数量只增不减**：改内核行为要在 `sim/selftest.py` 里补一条能复现的用例。

## 4. 目录边界（改之前先看这个）

```
server/   HTTP 与一局游戏的会话          sim/     模拟内核（纯 Python，无 IO）
web/      前端（零构建，纯静态）          tools/   测试与运维脚本
calibration/  系数与机场数据              docs/    需求、规则边界
```

### sim/ 只允许"向下依赖"

```
config → util → model → products → market → settle → ai → goals → game → report
```

- 左边的模块不能 import 右边的；`sim/simulate.py` 只是兼容门面，**不要往里加逻辑**
- 新逻辑放进对应层；跨层调用请先想清楚是不是该换层
- 注意：模块之间是直接 `from x import f`，所以**测试里 monkeypatch 要打在"使用处"所在模块**
  （例：`market.allocate` 用的是 `market.build_products`，patch `simulate.build_products` 无效）

### web/ 只允许"按加载顺序依赖"

```
index.html → css/app.css + js/{map,routes,interaction,panels,saves,goals,app}.js
```

- 7 个脚本按 `<script>` 顺序加载，共享同一个全局作用域；**后面的可以用前面的，反之不行**
- 入口与启动绑定在最后加载的 `js/app.js`；不要在中途的脚本里写顶层可执行语句
- 不要引入构建步骤或 npm 依赖：`node tools/*_check.js` 直接从源文件抽取函数执行

### 数据与数值

- 系数只改 `calibration/params.json`，不要写死在 Python 里
- 机场/机型改 `calibration/airports.csv`、`sim/aircraft.csv`
- 改完跑 `python calibration/calibrate.py` 看拟合有没有崩，并在 PR 里贴关键指标

## 5. 分支与提交

- `main` 保持可运行、测试全绿；**不直接推 main**，用 `feat/*`、`fix/*`、`refactor/*`、`docs/*` 分支 + PR
- 提交信息用 Conventional Commits：

  ```
  feat(goals): 目标模式增加破产提前结算
  fix(web): 对手榜标签在不足 20 家时显示错误
  refactor(sim): 把需求分配从市场层拆出
  docs(readme): 补充开线向导说明
  test(sim): 补 FR-403 时刻回收用例
  ```

- 一个 PR 只做一件事；重构与行为变更**不要混在同一个 PR**

## 6. 不要提交的东西

`saves/*.json`（个人存档）、`release/`（发布产物）、`__pycache__/`、`*.pyc`、`check.js`。
这些已在 `.gitignore` 里；`release/` 的 zip 走 GitHub Releases 上传。

## 7. 换行与编码

- 仓库内统一 LF；`.cmd` / `.bat` / `.ps1` 由 `.gitattributes` 强制 CRLF
- **`.ps1` 必须保存为 UTF-8 with BOM**，否则 Windows PowerShell 5.1 会把中文读成乱码
- `.cmd` 里不写中文（编码不可控），中文提示都放在 `.ps1` 里

## 8. PR 检查清单

- [ ] 本地 6 条命令全绿（见 §3）
- [ ] 新增/修改的行为有对应测试，或说明了为什么不需要
- [ ] 没有引入第三方运行时依赖
- [ ] 没有 `saves/`、`release/`、`__pycache__` 混进 diff
- [ ] 改了数据结构（存档、API、快照）时：同步更新 `README-开发者.md` 并在 PR 里写迁移说明
- [ ] 改动涉及数值时：贴出标定/回归结果

## 9. 文档在哪

| 文档 | 内容 |
|---|---|
| `README.md` | 项目入口 |
| `README-玩家.md` | 玩家手册 |
| `README-开发者.md` | 架构、API、测试、打包 |
| `sim/README.md` | 内核机制与基准场景 |
| `CHANGELOG.md` | 每轮变更记录 |
| `docs/` | 需求文档（FR 编号）、规则边界（R/D 编号） |
