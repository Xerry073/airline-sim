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

console.log("\n" + (failed ? "FAILED" : "OK") + "  " + passed + " passed, " + failed + " failed");
process.exit(failed ? 1 : 0);
