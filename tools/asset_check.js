#!/usr/bin/env node
/*
 * 前端资源引用校验（零依赖，不启子进程）
 *
 * index.html 是零构建的多文件前端：CSS 与 7 个 JS 靠 <script> 顺序共享一个全局作用域。
 * 这种结构最容易踩的两个坑，本脚本负责拦：
 *   1) 引用被移动/删除 → 资源不存在
 *   2) 两个文件都声明了同名 const/let/class → 加载时直接抛 SyntaxError
 *
 * 运行：node tools/asset_check.js
 */
const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const web = path.join(root, "web");
const html = fs.readFileSync(path.join(web, "index.html"), "utf8");

let passed = 0, failed = 0;
function check(ok, msg, detail) {
  if (ok) { passed++; console.log("PASS  " + msg); }
  else { failed++; console.log("FAIL  " + msg + (detail ? "  " + detail : "")); }
}

// ---------- 1. 收集引用 ----------
const scripts = [...html.matchAll(/<script[^>]+src="([^"]+)"/g)].map(m => m[1]);
const links = [...html.matchAll(/<link[^>]+href="([^"]+)"/g)].map(m => m[1]).filter(h => h.endsWith(".css"));

const missing = [];
for (const rel of [...scripts, ...links]) {
  const fp = path.join(web, rel);
  if (!fs.existsSync(fp) || fs.statSync(fp).size === 0) missing.push(rel);
}
check(scripts.length >= 1 && links.length === 1 && missing.length === 0,
  `index.html 引用的资源都存在（${scripts.length} 个脚本 + ${links.length} 个样式）`,
  missing.join(", "));

// ---------- 2. 加载顺序：入口必须最后 ----------
check(scripts.length > 0 && /(^|\/)app\.js$/.test(scripts[scripts.length - 1]),
  "入口 app.js 最后加载（启动绑定依赖前面所有文件）",
  scripts.join(" → "));

// ---------- 3. 每个脚本可编译 ----------
const bad = [];
for (const rel of scripts) {
  const code = fs.readFileSync(path.join(web, rel), "utf8");
  try {
    // new Function 与 node --check 对 classic script 的语法判定一致
    new Function(code);
  } catch (e) {
    bad.push(`${rel}: ${e.message}`);
  }
}
check(bad.length === 0, "所有脚本语法可解析", bad.join(" ; "));

// ---------- 4. 跨文件重名（const/let/class 重复会直接报错） ----------
const declared = new Map();   // name -> [file...]
const re = /^(?:const|let|class)\s+([A-Za-z_$][\w$]*)/;
for (const rel of scripts) {
  const code = fs.readFileSync(path.join(web, rel), "utf8");
  for (const line of code.split(/\r?\n/)) {
    const m = line.match(re);
    if (!m) continue;
    const name = m[1];
    if (!declared.has(name)) declared.set(name, []);
    declared.get(name).push(rel);
  }
}
const dup = [...declared.entries()].filter(([, files]) => files.length > 1);
check(dup.length === 0, "跨文件没有重复的 const/let/class 声明",
  dup.map(([n, f]) => `${n} @ ${f.join(",")}`).join(" ; "));

// ---------- 5. 顶层可执行语句只允许出现在最后加载的文件 ----------
const topLevel = [];
for (const rel of scripts.slice(0, -1)) {
  const code = fs.readFileSync(path.join(web, rel), "utf8");
  code.split(/\r?\n/).forEach((line, i) => {
    if (!/^\S/.test(line)) return;
    if (/^(function|async function|const |let |var |class |\/\*|\*|\/\/|}|\)|;|import |export )/.test(line)) return;
    topLevel.push(`${rel}:${i + 1}  ${line.trim().slice(0, 60)}`);
  });
}
check(topLevel.length === 0,
  "中间脚本没有顶层可执行语句（避免依赖尚未加载的全局）",
  topLevel.join(" ; "));

console.log("\n" + (failed ? "FAILED" : "OK") + "  " + passed + " passed, " + failed + " failed");
process.exit(failed ? 1 : 0);
