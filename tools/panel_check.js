#!/usr/bin/env node
/*
 * 侧栏「竞争对手」面板口径校验（零依赖）
 * 从 web/js/app.js 原样抽取 renderRivals()，用轻量 DOM 桩验证
 * 「过滤玩家 / TOP 20 / 共 N 家 / 名次列」的口径与标题文案。
 *
 * 运行：node tools/panel_check.js
 */
const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const html = fs.readFileSync(path.join(root, "web", "js", "app.js"), "utf8");
const START = "function renderRivals";
const END = "// ---- renderRivals 结束";
const start = html.indexOf(START);
const end = start < 0 ? -1 : html.indexOf(END, start);
if (start < 0 || end < 0) {
  console.error("找不到 renderRivals 代码段");
  process.exit(1);
}
const block = html.slice(start, end);

function escHTML(s) {
  return String(s).replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}
const money = v => (v >= 0 ? "" : "-") + Math.abs(v).toLocaleString("zh-CN",
  { maximumFractionDigits: 1 });

function makeDom() {
  const nodes = new Map();
  const nodeFor = sel => {
    if (!nodes.has(sel)) nodes.set(sel, { textContent: "", title: "", innerHTML: "" });
    return nodes.get(sel);
  };
  return { nodeFor };
}

function render(state) {
  const dom = makeDom();
  const fn = new Function("$", "escHTML", "money",
    block + "\n; return renderRivals;");
  const renderRivals = fn(dom.nodeFor, escHTML, money);
  renderRivals(state);
  const tag = dom.nodeFor("#rivalcount");
  const html = dom.nodeFor("#rivals").innerHTML;
  const rows = (html.match(/class="rk"/g) || []).length;   // 只数真实对手行
  return { html, tag, rows };
}

let passed = 0, failed = 0;
function check(ok, msg, detail) {
  if (ok) { passed += 1; console.log("PASS  " + msg); }
  else { failed += 1; console.log("FAIL  " + msg + (detail ? "  " + detail : "")); }
}

function rivals(n, from = 2) {
  return Array.from({ length: n }, (_, i) => ({
    name: `AI-${String(i + 1).padStart(2, "0")}`, hub: "PEK",
    rank: from + i, routes: 4, fleet: 3, pax: 1000, ebitda: 10, lf: 0.8,
    rep: 50, market_cap: 10000 - i * 100,
  }));
}

// 1) 50 家对手只显示前 20：标题 TOP 20 / 50，行数 20
{
  const { tag, rows, html } = render({ rivals: rivals(20), rivals_total: 50 });
  check(tag.textContent === "TOP 20/50" && rows === 20
    && /共 50 家对手/.test(tag.title) && /class="rk">2</.test(html),
    "20 家/共 50：标签 TOP 20/50，渲染 20 行并带名次列",
    `${tag.textContent} / ${rows} 行 / ${tag.title}`);
}

// 2) 对手不足 20 家：标签直接给家数
{
  const { tag, rows } = render({ rivals: rivals(5), rivals_total: 5 });
  check(tag.textContent === "5 家" && rows === 5 && /全部对手/.test(tag.title),
    "5 家（全部）：标签 5 家，渲染 5 行",
    `${tag.textContent} / ${rows} 行`);
}

// 3) 没有对手：占位文案，不报错
{
  const { tag, rows, html } = render({ rivals: [], rivals_total: 0 });
  check(tag.textContent === "0 家" && rows === 0 && /暂无对手/.test(html),
    "无对手：标签 0 家 + 占位文案", `${tag.textContent} / ${html.slice(0, 40)}`);
}

// 4) 旧后端没有 rivals_total 字段时按列表长度兜底
{
  const { tag, rows } = render({ rivals: rivals(3) });
  check(tag.textContent === "3 家" && rows === 3, "缺 rivals_total 时按列表长度兜底",
    `${tag.textContent} / ${rows} 行`);
}

// 5) 名称做 HTML 转义，不注入标签
{
  const bad = rivals(2);
  bad[0].name = '<img src=x onerror="alert(1)">';
  const { html } = render({ rivals: bad, rivals_total: 2 });
  check(!/<img/.test(html) && /&lt;img/.test(html), "对手名称做了 HTML 转义");
}

/* ---------- AI 航线详情：公开票价口径 ---------- */
const panelsSrc = fs.readFileSync(path.join(root, "web", "js", "panels.js"), "utf8");
const PUB_START = "function renderPublicRouteOp";
const PUB_END = "/* ---------- 机队";
const pubStart = panelsSrc.indexOf(PUB_START);
const pubEnd = pubStart < 0 ? -1 : panelsSrc.indexOf(PUB_END, pubStart);
if (pubStart < 0 || pubEnd < 0) {
  console.error("找不到 renderPublicRouteOp 代码段");
  process.exit(1);
}
const pubBlock = panelsSrc.slice(pubStart, pubEnd);

function renderPublic(route) {
  const nodes = new Map();
  const nodeFor = sel => {
    if (!nodes.has(sel)) nodes.set(sel, { textContent: "", innerHTML: "" });
    return nodes.get(sel);
  };
  const fn = new Function("$", "escHTML", "STATE", "OP", "AP",
    "routeMarketSet", "routeIsContested",
    pubBlock + "\n; return renderPublicRouteOp;");
  fn(nodeFor, escHTML, { player: { routes: [] } }, { publicRoute: route }, {},
    () => new Set(), () => false)();
  return nodeFor("#opbody").innerHTML;
}

const aiRoute = {
  airline: "AI-25", hub: "SVO", segments: ["PEK", "SVO"], daily_flights: 1,
  ac_type: "A333", lf: 0.98, price_index: 0.97,
  prices: [{ from: "PEK", to: "SVO", eco: 3120, biz: 8112 }],
};

// 6) 详情面板公开价格指数与各 OD 票价
{
  const html = renderPublic(aiRoute);
  check(/价格指数/.test(html) && /0\.97/.test(html)
    && /经济 ¥3,120/.test(html) && /商务 ¥8,112/.test(html),
    "AI 航线详情展示价格指数与 OD 经济/商务票价",
    html.replace(/\s+/g, " ").slice(0, 160));
}

// 7) 文案改为「票价公开、成本与财务不公开」
{
  const html = renderPublic(aiRoute);
  check(/成本、收入与财务不公开/.test(html) && !/不含票价/.test(html),
    "AI 航线详情文案：票价公开、成本与财务不公开");
}

/* ---------- 我的航线：竞争者一览 ---------- */
const mapSrc = fs.readFileSync(path.join(root, "web", "js", "map.js"), "utf8");
const mkStart = mapSrc.indexOf("function routeMarketKeys");
const mkEnd = mapSrc.indexOf("function lodRank", mkStart);
if (mkStart < 0 || mkEnd < 0) {
  console.error("找不到 routeMarketKeys/routeMarketSet 代码段");
  process.exit(1);
}
const mkBlock = mapSrc.slice(mkStart, mkEnd);
const { routeMarketSet, routeIsContested } =
  new Function(mkBlock + "\n; return {routeMarketSet, routeIsContested};")();

const routeStart = panelsSrc.indexOf("function renderRouteOp");
const routeEnd = panelsSrc.indexOf("async function closeRouteConfirm", routeStart);
if (routeStart < 0 || routeEnd < 0) {
  console.error("找不到 renderRouteOp 代码段");
  process.exit(1);
}
const routeBlock = panelsSrc.slice(routeStart, routeEnd);

const APX = {
  PEK: { city: "北京" }, SHA: { city: "上海" }, PVG: { city: "上海" },
  CTU: { city: "成都" }, KMG: { city: "昆明" },
};

function renderMine(playerRoutes, opponentRoutes, fleet) {
  const nodes = new Map();
  const nodeFor = sel => {
    if (!nodes.has(sel)) nodes.set(sel, { textContent: "", innerHTML: "" });
    return nodes.get(sel);
  };
  const fn = new Function("$", "escHTML", "STATE", "OP", "AP",
    "routeMarketSet", "routeIsContested", "aircraftOf", "haversineKm",
    routeBlock + "\n; return renderRouteOp;");
  const STATE = {
    player: {
      routes: playerRoutes, fleet: fleet || [{ type: playerRoutes[0].ac_type }],
      costs: { staff: 0.42, hub_fixed: 0.08, depreciation: 0.06, lease: 0.14,
               interest: 0, idle: 0, fixed_total: 0.70, total: 1.26 },
      capacity: {
        hours_used: 22.3, hours_cap: 48, segments_used: 12, segments_cap: 24,
        pools: [{ type: "A320", base: "PEK", count: 2, hours_used: 26.2, hours_cap: 32,
                  segments_used: 10, segments_cap: 16, over: false }],
      },
    },
    opponent_routes: opponentRoutes,
  };
  const render = fn(nodeFor, escHTML, STATE, { routeId: playerRoutes[0].id }, APX,
    routeMarketSet, routeIsContested,
    code => ({ name: code + " 型", seats: 165, range: 6300 }), () => 1000);
  render();
  return nodeFor("#opbody").innerHTML;
}

const mine = {
  id: 1, segments: ["PEK", "SHA"], ac_type: "A320", daily_flights: 2,
  price_index: 1.2, lf: 0.9, pax: 300, distance_km: 1091,
  revenue_M: 1.2, cost_M: 0.9, profit_M: 0.3, margin: 0.25,
  prices: [{ from: "PEK", to: "SHA", eco: 1190, biz: 3094 }],
};

// 8) 竞争航线列出对手的班次 / 载客率 / 价格指数
{
  const html = renderMine([mine], [
    { airline: "AI-07", segments: ["PEK", "SHA"], daily_flights: 4, lf: 0.88, price_index: 0.92 },
    { airline: "AI-09", segments: ["SHA", "PEK"], daily_flights: 2, lf: 0.5, price_index: 1.45 },
    { airline: "AI-01", segments: ["PEK", "CTU"], daily_flights: 1, lf: 0.7, price_index: 0.6 },
  ]);
  check(/AI-07/.test(html) && /4 班 · LF 88% · 指数 0\.92/.test(html)
    && /AI-09/.test(html) && /比你低 23%/.test(html) && /比你高 21%/.test(html),
    "竞争航线显示对手班次/载客率/价格指数与价差", html.replace(/\s+/g, " ").slice(0, 200));
  check(!/AI-01/.test(html), "不相关市场的对手不出现在竞争列表");
}

// 9) 有 OD 票价时并排比价（按城市匹配，SHA 与 PVG 视为同一市场）
{
  const html = renderMine([mine], [
    { airline: "AI-07", segments: ["PEK", "SHA"], daily_flights: 4, lf: 0.88,
      price_index: 0.92, prices: [{ from: "PEK", to: "SHA", eco: 880, biz: 2288 }] },
    { airline: "AI-12", segments: ["PEK", "PVG"], daily_flights: 1, lf: 0.7,
      price_index: 1.0, prices: [{ from: "PEK", to: "PVG", eco: 900, biz: 2340 }] },
  ]);
  check(/我 ¥1,190 · 对手 ¥880/.test(html) && /低 26%/.test(html),
    "并排显示我的与对手的 OD 票价", html.replace(/\s+/g, " ").slice(0, 260));
  check(/我 ¥1,190 · 对手 ¥900/.test(html) && /低 24%/.test(html),
    "SHA/PVG 同城机场按城市匹配同一 OD");
}

// 10) 对手没有 OD 票价（旧后端）时退回价格指数比较
{
  const html = renderMine([mine], [
    { airline: "AI-07", segments: ["PEK", "SHA"], daily_flights: 4, lf: 0.88, price_index: 0.92 },
  ]);
  check(/价格指数比你低 23%/.test(html) && !/我 ¥/.test(html),
    "缺少 OD 票价时退回价格指数比较");
}

// 11) 没有竞争时给出占位，而不是空白
{
  const html = renderMine([mine], []);
  check(/没有 AI 在飞同一个市场/.test(html) && /暂无重叠/.test(html),
    "无竞争时给出占位文案与「暂无重叠」");
}

// 12) 换机型：下拉只列机队已有型号，当前机型必在列表中
{
  const html = renderMine([mine], [], [{ type: "A320" }, { type: "B789" }]);
  check(/id="acsel"/.test(html) && /id="acsave"/.test(html)
    && /value="A320"/.test(html) && /value="B789"/.test(html)
    && !/value="A333"/.test(html) && /更换机型/.test(html),
    "换机型下拉只列机队已有型号，且带更换按钮",
    html.replace(/\s+/g, " ").match(/<select id="acsel">[\s\S]*?<\/select>/)?.[0] || "");
}

// 13) 固定开销 vs 航线利润：解释「每条都赚、公司却亏」
{
  const html = renderMine([mine], []);
  check(/公司固定开销/.test(html) && /¥0\.70M\/日/.test(html)
    && /全部航线利润合计/.test(html) && /覆盖固定开销后/.test(html)
    && /机队日占机/.test(html) && /22\.3\/48 h（46%）/.test(html),
    "航线管理显示固定开销、航线利润合计与占机率",
    html.replace(/\s+/g, " ").slice(0, 260));
}

// 14) 运力池按「机型 + 基地」展示；调机入口接在后端 rebase_aircraft 上
{
  const html = renderMine([mine], []);
  check(/PEK 的 A320 运力 26\.2\/32 h/.test(html)
    && /action:"rebase_aircraft"/.test(panelsSrc) && /id="rb_go"/.test(panelsSrc),
    "航线面板显示该基地的机型运力池，机队面板提供调机入口");
}

// 15) 租赁机在机队面板里是「退租」而不是「出售」
{
  check(/a\.lease\?"退租":"出售"/.test(panelsSrc) && /退押金/.test(panelsSrc),
    "机队面板对租赁机显示退租与押金，而不是出售价");
}

console.log("\n" + (failed ? "FAILED" : "OK") + "  " + passed + " passed, " + failed + " failed");
process.exit(failed ? 1 : 0);
