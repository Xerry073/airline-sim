#!/usr/bin/env node
/*
 * 目标模式前端逻辑校验（零依赖）
 * 从 web/js/goals.js 原样抽取「模式 / 目标」渲染与开新局代码，
 * 用轻量 DOM 桩验证沙盒/目标/结算面板与 /api/new_game 调用。
 *
 * 运行：node tools/goal_check.js
 */
const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const src = fs.readFileSync(path.join(root, "web", "js", "goals.js"), "utf8");
const start = src.indexOf("async function startNewGame");
if (start < 0) {
  console.error("找不到「模式 / 目标」代码段");
  process.exit(1);
}
const block = src.slice(start);

function escHTML(s) {
  return String(s).replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

function makeDom() {
  const nodes = new Map();
  const nodeFor = sel => {
    if (!nodes.has(sel)) nodes.set(sel, { innerHTML: "", onclick: null });
    return nodes.get(sel);
  };
  return { nodeFor, op: nodeFor("#opbody") };
}

function make(state, opts = {}) {
  const dom = makeDom();
  const calls = { api: [], toast: [], open: [], refresh: 0, close: 0 };
  const toast = (msg, bad) => calls.toast.push({ msg, bad: !!bad });
  const api = async (p, body) => {
    calls.api.push([p, body]);
    return { ok: opts.apiOk !== false };
  };
  const refresh = async () => { calls.refresh += 1; };
  const closeOp = () => { calls.close += 1; };
  const confirm = () => opts.confirm !== false;
  const openOp = mode => calls.open.push(mode);
  const fn = new Function(
    "STATE", "$", "escHTML", "toast", "api", "refresh", "closeOp",
    "confirm", "openOp", "sel", "expandedCity", "closeWizard", "SEEN_SETTLE",
    block + "\n; return {renderGoalsOp,startNewGame};"
  );
  const apiObj = fn(state, dom.nodeFor, escHTML, toast, api, refresh, closeOp,
    confirm, openOp, [], null, () => {}, null);
  return { apiObj, dom, calls };
}

let passed = 0, failed = 0;
function check(ok, msg, detail) {
  if (ok) { passed += 1; console.log("PASS  " + msg); }
  else { failed += 1; console.log("FAIL  " + msg + (detail ? "  " + detail : "")); }
}
const sleep = ms => new Promise(r => setTimeout(r, ms));

function baseProgress() {
  return [
    { id: "market_top3", name: "市值进前三", condition: "10 游戏年内市值排名 ≤ 3",
      achieved: false, day: null,
      detail: { current_rank: 4, best_rank: 4 } },
    { id: "region_leader", name: "区域霸主", condition: "某区域内市场份额 ≥ 35%",
      achieved: false, day: null,
      detail: { current_share: 0.12, best_share: 0.12, region: "CN", region_name: "中国" } },
    { id: "high_quality", name: "高质高效",
      condition: "连续 24 个月 EBITDA 率 ≥ 15% 且准点率 ≥ 85%",
      achieved: false, day: null,
      detail: { streak: 0, best_streak: 0, months_required: 24 } },
    { id: "network_expansion", name: "网络扩张",
      condition: "航段数 ≥ 100 且平均载客率 ≥ 75%",
      achieved: false, day: null,
      detail: { segments: 2, avg_lf: 0.8, best_segments: 2, best_lf: 0.8 } },
  ];
}

function stateForGoals(overrides = {}) {
  return {
    tick: { day: 100, paused: false, speed: 4 },
    player: { routes: [], fleet: [{ id: 1 }] },
    goals: Object.assign({
      mode: "goals", mode_chosen: true, setup_required: false,
      progress: baseProgress(), achieved_count: 0, settled: false,
      deadline_day: 3600, days_left: 3500, years_left: 9.72,
      settlement: null, rating: null, scored: false,
    }, overrides),
  };
}

function stateForSetup() {
  return {
    tick: { day: 0, paused: true, speed: 4 },
    player: { routes: [], fleet: [{ id: 1 }] },
    goals: {
      mode: "sandbox", mode_chosen: false, setup_required: true,
      progress: [], achieved_count: 0, settled: false,
      deadline_day: null, days_left: null, years_left: null,
      settlement: null, rating: null, scored: false,
    },
  };
}

(async () => {
  {
    const { apiObj, dom } = make(stateForSetup());
    apiObj.renderGoalsOp();
    const h = dom.op.innerHTML;
    check(/开局模式/.test(h) && /开始沙盒模式/.test(h) && /开始目标模式/.test(h),
      "setup 面板：沙盒 / 目标两个开局按钮");
  }
  {
    const { apiObj, dom } = make(stateForGoals({
      mode: "sandbox", setup_required: false, progress: [],
      deadline_day: null, days_left: null, years_left: null,
    }));
    apiObj.renderGoalsOp();
    const h = dom.op.innerHTML;
    check(/当前：沙盒模式/.test(h) && /换成目标模式/.test(h)
      && /id="restart_sandbox"/.test(h) && /开新对局/.test(h),
      "沙盒面板：说明当前模式，提供重开沙盒与切换目标模式");
  }
  {
    const { apiObj, dom } = make(stateForGoals());
    apiObj.renderGoalsOp();
    const h = dom.op.innerHTML;
    check(/目标模式/.test(h) && /市值进前三/.test(h) && /区域霸主/.test(h)
      && /高质高效/.test(h) && /网络扩张/.test(h) && /剩余天数/.test(h),
      "目标面板：四目标 + 期限 + 剩余天数");
  }
  {
    const progress = baseProgress().map((p, i) => ({
      ...p, achieved: i < 3, day: i < 3 ? 100 + i * 10 : null,
    }));
    const { apiObj, dom } = make(stateForGoals({
      progress, achieved_count: 3, settled: true, days_left: 0, years_left: 0,
      settlement: { day: 3600, kind: "deadline", rating: "B", achieved_count: 3,
        scored: true, failed: false, reason: "10 年目标期结束" },
      rating: "B", scored: true,
    }));
    apiObj.renderGoalsOp();
    const h = dom.op.innerHTML;
    check(/结算结果/.test(h) && /评级 <b>B<\/b>/.test(h) && /3 \/ 4/.test(h),
      "结算面板：B 评级 / 3 个达成");
  }
  {
    const { apiObj, dom } = make(stateForGoals({
      settled: true, achieved_count: 0, days_left: 0, years_left: 0,
      settlement: { day: 3600, kind: "deadline", rating: "E", achieved_count: 0,
        scored: false, failed: false, reason: "10 年目标期结束" },
      rating: "E", scored: false,
    }));
    apiObj.renderGoalsOp();
    const h = dom.op.innerHTML;
    check(/E（未达成）/.test(h) && /否（未达成）/.test(h),
      "0/4 结算：E 且不计分");
  }
  {
    const { apiObj, dom } = make(stateForGoals({
      settled: true, days_left: 0,
      settlement: { day: 3500, kind: "bankrupt", rating: null, achieved_count: 0,
        scored: false, failed: true, reason: "公司破产" },
    }));
    apiObj.renderGoalsOp();
    const h = dom.op.innerHTML;
    check(/评级 <b>失败<\/b>/.test(h) && /公司破产/.test(h), "破产结算：失败 / 不计分");
  }
  {
    const { apiObj, calls } = make(stateForSetup(), { confirm: true });
    await apiObj.startNewGame("goals");
    await sleep(220);
    check(calls.api.length === 1 && calls.api[0][0] === "/api/new_game"
      && calls.api[0][1].mode === "goals" && calls.refresh === 1
      && calls.close === 1 && calls.open.includes("goals"),
      "开局按钮：POST /api/new_game {mode:goals} 并刷新/打开目标面板",
      JSON.stringify(calls));
  }
  {
    const { apiObj, calls } = make({
      tick: { day: 12, paused: false, speed: 4 },
      player: { routes: [{ id: 1 }], fleet: [{ id: 1 }] },
      goals: stateForGoals().goals,
    }, { confirm: false });
    await apiObj.startNewGame("goals");
    check(calls.api.length === 0, "有进度且取消确认时不重置对局");
  }

  console.log("\n" + (failed ? "FAILED" : "OK") + "  " + passed + " passed, " + failed + " failed");
  process.exit(failed ? 1 : 0);
})();
