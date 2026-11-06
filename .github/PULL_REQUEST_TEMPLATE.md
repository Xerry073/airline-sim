## 改了什么

<!-- 一句话说明这个 PR 做了什么 -->

## 为什么

<!-- 关联 issue / 需求编号（FR-xxx）/ 动机 -->

## 怎么验证的

- [ ] `python sim/selftest.py` → __ / 49
- [ ] `node tools/asset_check.js` → __ / __
- [ ] `node tools/map_check.js` → __ / 28
- [ ] `node tools/goal_check.js` → __ / 8
- [ ] `node tools/panel_check.js` → __ / 5
- [ ] 手工/浏览器验证了（说明步骤）：

## 检查清单

- [ ] 没有引入第三方运行时依赖
- [ ] 没有把 `saves/`、`release/`、`__pycache__` 带进 diff
- [ ] 行为变更已补测试，或已说明为什么不需要
- [ ] 改了存档 / API / 快照字段时，同步更新了 `README-开发者.md`
