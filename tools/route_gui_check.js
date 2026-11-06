#!/usr/bin/env node
/*
 * 地图开线手势校验（零依赖）
 * 从 web/js/interaction.js 原样抽取 ROUTE_PICK 段，用轻量桩验证
 * 「右键=起点 / 左键=终点 / Alt+左键=经停点」的选择状态机：
 * 航段顺序、非法端点、经停点开关、重选起点后的清理。
 *
 * 运行：node tools/route_gui_check.js
 */
const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const src = fs.readFileSync(path.join(root, "web", "js", "interaction.js"), "utf8");
const START = "/* ===== ROUTE_PICK_START";
const END = "/* ===== ROUTE_PICK_END ===== */";
const start = src.indexOf(START);
const end = start < 0 ? -1 : src.indexOf(END, start);
if (start < 0 || end < 0) {
  console.error("找不到 ROUTE_PICK 代码段（标记被删了？）");
  process.exit(1);
}
const block = src.slice(start, end);

const AP = {
  PEK: { iata: "PEK", city: "北京" },
  SHA: { iata: "SHA", city: "上海" },
  PVG: { iata: "PVG", city: "上海" },
  CTU: { iata: "CTU", city: "成都" },
  LXA: { iata: "LXA", city: "拉萨" },
};
const STATE = { airports: Object.values(AP) };

/* 用 new Function 构造与浏览器同名的自由变量环境 */
function makeHarness() {
  const opened = [];
  const toasts = [];
  let wizOpen = false;
  const fn = new Function(
    "AP", "STATE", "toast", "$", "renderMarkers", "drawLabels", "openWizard", "hideTip",
    "let sel=[], stopover=null, expandedCity=null, hoverId=null;\n"
    + block
    + "\nreturn {pick, clearSelection, sel:()=>sel.slice(), stopover:()=>stopover};"
  );
  const api = fn(
    AP, STATE,
    (msg, bad) => toasts.push({ msg, bad: !!bad }),
    () => ({ classList: { contains: () => wizOpen, remove: () => { wizOpen = false; } } }),
    () => {}, () => {},
    segs => { opened.push(segs); },
    () => {}
  );
  return { api, opened, toasts, isWizOpen: () => wizOpen, openWiz: () => { wizOpen = true; } };
}

let passed = 0, failed = 0;
function check(ok, msg, detail) {
  if (ok) { passed += 1; console.log("PASS  " + msg); }
  else { failed += 1; console.log("FAIL  " + msg + (detail ? "  " + detail : "")); }
}

// 1) 没有起点时左键点机场：不开向导，提示先用右键
{
  const h = makeHarness();
  h.api.pick("SHA", "dest");
  check(h.opened.length === 0 && h.api.sel().length === 0 && /右键/.test(h.toasts[0].msg),
    "未选起点时左键不建航线，提示用右键选起点", JSON.stringify(h.toasts));
}

// 2) 右键设起点：只记起点，不开向导
{
  const h = makeHarness();
  h.api.pick("PEK", "origin");
  check(JSON.stringify(h.api.sel()) === '["PEK"]' && h.opened.length === 0
    && /起点/.test(h.toasts[0].msg), "右键设起点：sel=[PEK] 且不弹向导");
}

// 3) 直飞：右键起点 + 左键终点 → 两段
{
  const h = makeHarness();
  h.api.pick("PEK", "origin");
  h.api.pick("SHA", "dest");
  check(JSON.stringify(h.opened) === '[["PEK","SHA"]]', "直飞：向导收到 [起点,终点]", JSON.stringify(h.opened));
}

// 4) 经停：右键起点 + Alt 经停 + 左键终点 → 顺序为 起点→经停→终点
{
  const h = makeHarness();
  h.api.pick("PEK", "origin");
  h.api.pick("CTU", "stop");
  h.api.pick("LXA", "dest");
  check(JSON.stringify(h.opened) === '[["PEK","CTU","LXA"]]',
    "经停：向导收到 [起点,经停,终点]", JSON.stringify(h.opened));
}

// 5) Alt 再点同一机场取消经停
{
  const h = makeHarness();
  h.api.pick("PEK", "origin");
  h.api.pick("CTU", "stop");
  h.api.pick("CTU", "stop");
  h.api.pick("SHA", "dest");
  check(h.api.stopover() === null && JSON.stringify(h.opened) === '[["PEK","SHA"]]',
    "再次 Alt+左键取消经停点", JSON.stringify(h.opened));
}

// 6) 同城机场作为终点被拒，起点保留
{
  const h = makeHarness();
  h.api.pick("SHA", "origin");
  h.api.pick("PVG", "dest");
  check(h.opened.length === 0 && JSON.stringify(h.api.sel()) === '["SHA"]'
    && /同城/.test(h.toasts[h.toasts.length - 1].msg), "同城机场作终点被拒且起点不变", JSON.stringify(h.toasts));
}

// 7) 经停点不能等于起点，也不能与起点同城
{
  const a = makeHarness();
  a.api.pick("PEK", "origin");
  a.api.pick("PEK", "stop");
  const b = makeHarness();
  b.api.pick("SHA", "origin");
  b.api.pick("PVG", "stop");
  const last = h => h.toasts[h.toasts.length - 1].msg;
  check(a.api.stopover() === null && /经停点不能与起点相同/.test(last(a))
    && b.api.stopover() === null && /同城机场不能互相经停/.test(last(b)),
    "经停点的两种非法情形都被拒绝", JSON.stringify([last(a), last(b)]));
}

// 8) 重选起点会清掉旧经停点
{
  const h = makeHarness();
  h.api.pick("PEK", "origin");
  h.api.pick("CTU", "stop");
  h.api.pick("LXA", "origin");
  check(h.api.stopover() === null && JSON.stringify(h.api.sel()) === '["LXA"]',
    "重选起点清空经停点", JSON.stringify({ sel: h.api.sel(), stop: h.api.stopover() }));
}

// 9) 向导开着时左键换终点：沿用起点，重新开向导
{
  const h = makeHarness();
  h.api.pick("PEK", "origin");
  h.api.pick("SHA", "dest");
  h.api.pick("CTU", "dest");
  check(h.opened.length === 2 && JSON.stringify(h.opened[1]) === '["PEK","CTU"]',
    "换终点时沿用起点并重开向导", JSON.stringify(h.opened));
}

// 10) 向导开着时右键改起点，先关向导
{
  const h = makeHarness();
  h.api.pick("PEK", "origin");
  h.api.pick("SHA", "dest");
  h.openWiz();
  h.api.pick("CTU", "origin");
  check(!h.isWizOpen() && JSON.stringify(h.api.sel()) === '["CTU"]',
    "右键改起点会关闭已打开的向导");
}

console.log("\n" + (failed ? "FAILED" : "OK") + "  " + passed + " passed, " + failed + " failed");
process.exit(failed ? 1 : 0);
