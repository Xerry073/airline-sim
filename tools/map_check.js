#!/usr/bin/env node
/*
 * 地图几何校验（零依赖）
 * 从 web/js/map.js 原样抽取 MAP_MATH 段执行，验证：
 *   - 投影 / 大圆 / 日界线
 *   - 中国+东亚默认视野
 *   - 分级显示、同城合并、标签零重叠
 *   - 重叠机场的最近点点击吸附
 *
 * 运行：node tools/map_check.js
 */
const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const html = fs.readFileSync(path.join(root, "web", "js", "map.js"), "utf8");
const match = html.match(
  /\/\* ===== MAP_MATH_START ===== \*\/([\s\S]*?)\/\* ===== MAP_MATH_END ===== \*\//
);
if (!match) throw new Error("找不到 MAP_MATH 段");

const M = new Function(
  match[1] +
  "\nreturn {VB,RADIUS,SCALE_RANK,MERGE_K,clamp,scaleRank,proj,haversineKm,gcPoints," +
  "routePathD,routeWidth,routeMarketKeys,routeMarketSet,routeIsContested," +
  "lodRank,buildMarkers,markerLabel,layoutLabels,nearestMarker,fitView};"
)();

let passed = 0, failed = 0;
function check(ok, msg, detail) {
  if (ok) { passed++; console.log("PASS  " + msg); }
  else { failed++; console.log("FAIL  " + msg + (detail ? "  " + detail : "")); }
}
function near(a, b, eps) { return Math.abs(a - b) <= eps; }
function scaleOf(pax) {
  return pax >= 80 ? "XL" : pax >= 45 ? "L" : pax >= 25 ? "M" : pax >= 10 ? "S" : "R";
}

const airports = fs.readFileSync(path.join(root, "calibration", "airports.csv"), "utf8")
  .trim().split(/\r?\n/).slice(1).map(line => {
    const [iata, city, country, region, tier, lat, lon, pax] = line.split(",");
    const p = Number(pax);
    return { iata, city, region, lat: Number(lat), lon: Number(lon), pax: p, scale: scaleOf(p) };
  });
const AP = Object.fromEntries(airports.map(a => [a.iata, a]));

function centerView(lon, lat, k) {
  const [x, y] = M.proj(lon, lat);
  return { k, x: M.VB.x + M.VB.w / 2 - x * k, y: M.VB.y + M.VB.h / 2 - y * k };
}
function textWidth(t) {
  return [...t].reduce((s, ch) => s + (ch.charCodeAt(0) > 255 ? 11 : 6.4), 0);
}
function overlaps(a, b) {
  return a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
}
function markerScreen(m, view) {
  return { x: m.x * view.k + view.x, y: m.y * view.k + view.y };
}

check(airports.length === 63, "机场库 63 条", "实际 " + airports.length);

/* 投影与视野 */
const pek = M.proj(AP.PEK.lon, AP.PEK.lat);
check(pek[0] > 820 && pek[0] < 826 && pek[1] > 370 && pek[1] < 385,
  "PEK Web Mercator 投影落在预期区域", pek.map(v => v.toFixed(1)).join(","));

const regionView = M.fitView({ minLon: 72, maxLon: 147, minLat: 14, maxLat: 50 }, 42);
check(regionView.k > 4.2 && regionView.k < 4.6,
  "默认中国/东亚视野 k≈4.4", "k=" + regionView.k.toFixed(2));

const outside = airports.filter(a => {
  const [x, y] = M.proj(a.lon, a.lat);
  const sx = x * regionView.k + regionView.x;
  const sy = y * regionView.k + regionView.y;
  return a.region === "CN" && (sx < 0 || sx > 1000 || sy < 24 || sy > 736);
});
check(outside.length === 0, "默认视野覆盖全部中国机场",
  outside.map(a => a.iata).join(","));

const defaultMarkers = M.buildMarkers(airports, {
  k: regionView.k, view: regionView, hubs: ["PEK"], sel: []
});
const defaultLabels = M.layoutLabels(defaultMarkers, textWidth, regionView, M.VB);
const inView = defaultMarkers.filter(m => {
  const sx = m.x * regionView.k + regionView.x;
  const sy = m.y * regionView.k + regionView.y;
  return sx >= 0 && sx <= 1000 && sy >= 24 && sy <= 736;
});
const missing = inView.filter(m => !defaultLabels.some(l => l.m.id === m.id));
check(missing.length === 0,
  "默认视野内标记全部有标签",
  "inView=" + inView.length + " labels=" + defaultLabels.length +
  " missing=" + missing.map(m => m.iata || m.city).join(","));

/* 分级 */
const low = M.buildMarkers(airports, { k: 1, view: centerView(110, 30, 1), hubs: ["PEK"], sel: [] });
const badLow = low.filter(m => m.kind === "airport" && !m.hub && M.scaleRank(m.scale) < 4);
check(badLow.length === 0, "k=1 只显示 L 及以上机场（+枢纽）",
  badLow.map(m => m.iata).join(","));

const high = M.buildMarkers(airports, { k: 8, view: centerView(110, 30, 8), hubs: ["PEK"], sel: [] });
check(high.length === 63, "k=8 全部 63 个机场可见", "实际 " + high.length);

/* 同城合并 / 展开 */
const mid = M.buildMarkers(airports, {
  k: 4.1, view: centerView(120, 30, 4.1), hubs: ["PEK"], sel: []
});
const shCity = mid.filter(m => m.kind === "city" && m.city === "上海");
check(shCity.length === 1 && shCity[0].members.length === 2,
  "上海同城机场在 k<6 合并为一个城市标记",
  JSON.stringify(shCity.map(m => m.members)));

const highGroup = M.buildMarkers(airports, {
  k: 8, view: centerView(121.5, 31.2, 8), hubs: ["PEK"], sel: []
});
const sh = highGroup.filter(m => m.iata === "SHA" || m.iata === "PVG");
const shGap = sh.length === 2 ? Math.hypot(sh[0].x - sh[1].x, sh[0].y - sh[1].y) * 8 : 0;
check(sh.length === 2 && shGap >= 30,
  "k=8 时 SHA/PVG 展开为两个可点标记",
  "gap=" + shGap.toFixed(1));

/* 标签避让：所有缩放级别 0 重叠 */
for (const k of [1, 2, 3, 4.1, 6, 8, 14]) {
  const view = centerView(110, 30, k);
  const markers = M.buildMarkers(airports, {
    k, view, hubs: ["PEK"], sel: k >= 8 ? ["PEK"] : []
  });
  const labels = M.layoutLabels(markers, textWidth, view, M.VB);
  let collisions = 0;
  for (let i = 0; i < labels.length; i++) {
    for (let j = i + 1; j < labels.length; j++) {
      if (overlaps(labels[i], labels[j])) collisions++;
    }
  }
  check(collisions === 0 && labels.length > 0,
    `k=${k} 标签零重叠`, `labels=${labels.length}, collisions=${collisions}`);
}

/* PEK 枢纽在低缩放必须有标签 */
const worldLabels = M.layoutLabels(
  M.buildMarkers(airports, { k: 1, view: centerView(110, 30, 1), hubs: ["PEK"], sel: [] }),
  textWidth, centerView(110, 30, 1), M.VB
);
check(worldLabels.some(l => l.m.iata === "PEK"), "k=1 北京枢纽标签仍保留");

/* 最近点吸附：CAN/SZX 在 k=8 相距约 22px，偏 3px 点击仍应命中各自 */
const clickView = centerView(120, 30, 8);
const clickMarkers = M.buildMarkers(airports, { k: 8, view: clickView, hubs: [], sel: [] });
for (const code of ["CAN", "SZX"]) {
  const m = clickMarkers.find(x => x.iata === code);
  const s = markerScreen(m, clickView);
  const hit = M.nearestMarker(clickMarkers, s.x + 3, s.y + 3, clickView, 15);
  check(hit && hit.iata === code, `点击吸附命中 ${code}`, hit && hit.iata);
}

/* 大圆 / 日界线 */
const pekSha = M.gcPoints(AP.PEK, AP.SHA);
const pekShaKm = pekSha.slice(1).reduce((sum, p, i) => sum + M.haversineKm(pekSha[i], p), 0);
check(pekShaKm >= 1050 && pekShaKm <= 1100, "PEK-SHA 大圆距离落在 1050–1100 km",
  pekShaKm.toFixed(1));

const pekLax = M.gcPoints(AP.PEK, AP.LAX);
const last = pekLax[pekLax.length - 1];
check(last.lon > 180, "PEK-LAX 经度连续展开并跨过 +180°", "lastLon=" + last.lon.toFixed(2));
check(near(last.lat, AP.LAX.lat, 0.01), "PEK-LAX 大圆终点落在 LAX 纬度",
  last.lat.toFixed(2));
const pekLaxKm = pekLax.slice(1).reduce((sum, p, i) => sum + M.haversineKm(pekLax[i], p), 0);
check(near(pekLaxKm, M.haversineKm(AP.PEK, AP.LAX), 5), "大圆采样保持球面距离",
  pekLaxKm.toFixed(1));

const d0 = M.routePathD(["PEK", "LAX"], AP, 0);
const dLeft = M.routePathD(["PEK", "LAX"], AP, -1000);
check(/M\d{3,4}[.,]/.test(d0) && /M-?\d+/.test(dLeft),
  "跨日界线航线生成主路径与左侧副本", d0.slice(0, 28) + " ...");

/* 航线宽度：按客座率 */
const widths = [0.2, 0.5, 0.8, 1.0].map(M.routeWidth);
check(widths.every((w, i) => i === 0 || w >= widths[i - 1]) && widths[3] <= 3.4,
  "航线宽度随客座率单调且封顶 3.4", widths.join(" / "));

/* 市场竞争：城市级、方向不敏感、经停看航段 */
const aiRoutes = [{ segments: ["PEK", "SHA"] }, { segments: ["PEK", "CTU", "LXA"] }];
const aiMarkets = M.routeMarketSet(aiRoutes, AP);
check(M.routeIsContested(["SHA", "PEK"], aiMarkets, AP),
  "反向京沪航线判定为竞争");
check(M.routeIsContested(["CTU", "PEK"], aiMarkets, AP),
  "经停航段与直飞共享市场判定为竞争");
check(!M.routeIsContested(["PEK", "CAN"], aiMarkets, AP),
  "无交集航线不判定为竞争");

console.log("\n" + (failed ? "FAILED" : "OK") + "  " + passed + " passed, " + failed + " failed");
process.exit(failed ? 1 : 0);
