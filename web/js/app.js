/* 应用入口：状态与渲染、指令解析、对手榜、事件绑定与启动 */
function setViewButtons(which){
  $$("#mapctl [data-view]").forEach(b=>b.classList.toggle("on",b.dataset.view===which));
}

function networkBounds(){
  if(!STATE) return null;
  const pts=[];
  const add=code=>{ if(AP[code]) pts.push(AP[code]); };
  ((STATE.player&&STATE.player.hubs)||[]).forEach(add);
  ((STATE.player&&STATE.player.routes)||[]).forEach(r=>(r.segments||[]).forEach(add));
  if(!pts.length) return null;
  let minLon=Infinity,maxLon=-Infinity,minLat=Infinity,maxLat=-Infinity;
  pts.forEach(a=>{
    minLon=Math.min(minLon,a.lon); maxLon=Math.max(maxLon,a.lon);
    minLat=Math.min(minLat,a.lat); maxLat=Math.max(maxLat,a.lat);
  });
  const padLon=Math.max(4,(maxLon-minLon)*0.22);
  const padLat=Math.max(4,(maxLat-minLat)*0.22);
  minLon-=padLon; maxLon+=padLon; minLat-=padLat; maxLat+=padLat;
  if(maxLon-minLon<10){ const c=(minLon+maxLon)/2; minLon=c-5; maxLon=c+5; }
  if(maxLat-minLat<10){ const c=(minLat+maxLat)/2; minLat=c-5; maxLat=c+5; }
  return {minLon,maxLon,minLat,maxLat};
}

function animateViewTo(target){
  if(viewAnim) cancelAnimationFrame(viewAnim);
  const start={...view}, t0=performance.now(), dur=380;
  const step=now=>{
    const t=Math.min(1,(now-t0)/dur);
    const e=1-Math.pow(1-t,3);
    view.k=start.k+(target.k-start.k)*e;
    view.x=start.x+(target.x-start.x)*e;
    view.y=start.y+(target.y-start.y)*e;
    applyView(); renderMarkers(); drawLabels();
    viewAnim=t<1?requestAnimationFrame(step):null;
  };
  viewAnim=requestAnimationFrame(step);
}

function bindMap(){
  const svg=$("#map");
  let drag=null, moved=false;

  svg.addEventListener("pointerdown",e=>{
    if(e.button!==0) return;
    mapGestureMoved=false;
    const routeTarget=e.target&&e.target.closest&&e.target.closest(".rgroup,.rrgroup");
    if(routeTarget){
      const p=clientToView(e);
      if(!nearestMarker(MAPM.markers,p.x,p.y,view,15)) return; // 点航线不启动拖拽，交给 click
    }
    if(viewAnim){ cancelAnimationFrame(viewAnim); viewAnim=null; }
    const box=svg.getBoundingClientRect();
    const s=Math.min(box.width/VB.w,box.height/VB.h);
    drag={x:e.clientX,y:e.clientY,vx:view.x,vy:view.y,s};
    moved=false;
    mapGestureMoved=false;
    svg.classList.add("dragging");
    try{ svg.setPointerCapture(e.pointerId); }catch(_){}
  });

  svg.addEventListener("pointermove",e=>{
    if(drag){
      const dx=e.clientX-drag.x, dy=e.clientY-drag.y;
      if(Math.hypot(dx,dy)>3){ moved=true; mapGestureMoved=true; }
      view.x=drag.vx+dx/drag.s;
      view.y=drag.vy+dy/drag.s;
      applyView(); drawLabels();
      setHover(null); if(!routeHover) hideTip();
      return;
    }
    updateHover(e);
  });

  const endDrag=e=>{
    if(!drag) return;
    const wasMoved=moved;
    drag=null; moved=false;
    svg.classList.remove("dragging");
    try{ svg.releasePointerCapture(e.pointerId); }catch(_){}
    if(!wasMoved) handleMapClick(e);
  };
  svg.addEventListener("pointerup",endDrag);
  svg.addEventListener("pointercancel",e=>{
    drag=null; moved=false; svg.classList.remove("dragging");
    try{ svg.releasePointerCapture(e.pointerId); }catch(_){}
  });

  /* 右键：选航线起点（地图上不弹浏览器菜单） */
  svg.addEventListener("contextmenu",e=>{
    e.preventDefault();
    if(!STATE) return;
    handleMapRightClick(e);
  });

  svg.addEventListener("wheel",e=>{
    e.preventDefault();
    if(viewAnim){ cancelAnimationFrame(viewAnim); viewAnim=null; }
    setViewButtons(null);
    const p=clientToView(e);
    const k0=view.k;
    const k=clamp(k0*Math.pow(1.0015,-e.deltaY),0.8,14);
    const wx=(p.x-view.x)/k0, wy=(p.y-view.y)/k0;
    view.k=k; view.x=p.x-wx*k; view.y=p.y-wy*k;
    applyView(); renderMarkers(); drawLabels();
  },{passive:false});

  svg.addEventListener("pointerleave",()=>{
    if(drag) return;
    setHover(null);
    if(!routeHover) hideTip();
  });

  $$("#mapctl [data-view]").forEach(b=>{
    b.onclick=()=>{
      setViewButtons(b.dataset.view);
      if(b.dataset.view==="region") animateViewTo(fitView(REGION,42));
      else if(b.dataset.view==="world") animateViewTo(fitView(WORLD,10,1.15));
      else{
        const bounds=networkBounds();
        animateViewTo(bounds?fitView(bounds,50,8):fitView(REGION,42));
      }
    };
  });

  const ai=$("#aitoggle");
  ai.onclick=()=>{
    SHOW_AI=!SHOW_AI;
    ai.classList.toggle("on",SHOW_AI);
    ai.textContent=SHOW_AI?"AI 航线：开":"AI 航线：关";
    if(SHOW_AI){
      if(!STATE)
        toast("尚未连接到后端，请稍后再试",true);
      else if(!Array.isArray(STATE.opponent_routes))
        toast("后端版本过旧，缺少 AI 航线数据，请重启后端",true);
      else if(!STATE.opponent_routes.length)
        toast("当前还没有 AI 航线；AI 通常会在开局第 1 天后逐步开线");
    }
    syncRivalRoutes();
  };
}

function handleMapClick(e){
  const p=clientToView(e);
  const m=nearestMarker(MAPM.markers,p.x,p.y,view,15);
  if(m){
    if(m.kind==="city"){
      expandedCity=expandedCity===m.city?null:m.city;
      if(expandedCity) toast(`${m.city}：右键机场设为起点，左键设为终点`);
      renderMarkers(); drawLabels();
    }else{
      pick(m.iata,e.altKey?"stop":"dest");
    }
    return;
  }
  if(sel.length||expandedCity||$("#wiz").classList.contains("on")) clearSelection();
}

function handleMapRightClick(e){
  const p=clientToView(e);
  const m=nearestMarker(MAPM.markers,p.x,p.y,view,15);
  if(!m) return;
  if(m.kind==="city"){
    expandedCity=m.city;
    toast(`${m.city}：选具体机场后右键设为起点`);
    renderMarkers(); drawLabels();
    return;
  }
  pick(m.iata,"origin");
}

/* ============================================================
   数据 / 侧栏 / 指令台
   ============================================================ */
async function api(path,body){
  const opt=body?{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)}:{};
  const r=await fetch(path,opt);
  const j=await r.json().catch(()=>({ok:false,reason:"响应解析失败"}));
  if(!r.ok && j.reason) toast(j.reason,true);
  return j;
}
function toast(msg,bad){
  const t=$("#toast"); t.textContent=msg;
  t.style.borderColor=bad?"var(--bad)":"var(--line)";
  t.classList.add("show"); clearTimeout(t._h);
  t._h=setTimeout(()=>t.classList.remove("show"),1700);
}
const money=v=>(v>=0?"":"-")+Math.abs(v).toLocaleString("zh-CN",{maximumFractionDigits:1});

function render(){
  const s=STATE; if(!s) return;
  if(s.goals&&s.goals.settlement){
    const st=s.goals.settlement;
    const key=`${st.day}:${st.kind}:${st.rating}`;
    if(SEEN_SETTLE!==key){
      SEEN_SETTLE=key;
      toast(st.failed?`目标失败：${st.reason}`:`目标结算：${st.rating}（${st.achieved_count}/4）`,st.failed);
      if(OP.mode!=="goals") setTimeout(()=>openOp("goals"),0);
    }
  }
  $("#clock").textContent=`第 ${s.tick.day} 天`;
  $$("[data-speed]").forEach(b=>
    b.classList.toggle("on", Number(b.dataset.speed)===(s.tick.paused?0:s.tick.speed)));

  const p=s.player;
  if(p){
    $("#pname").textContent=p.alive?p.name:p.name+"（已破产）";
    $("#rank").textContent=p.rank?`排名 #${p.rank}`:"未排名";
    const k=p.kpi||{}, eb=k.ebitda||0;
    const cap=p.capacity||{};
    const usage=fleetUsageSummary(cap);
    const usageCls=usage.over?'neg':(usage.worstPct>=85?'warn':'pos');
    $("#kpis").innerHTML=`
      <div class="kpi"><div class="l">现金 ¥M</div><div class="v">${money(p.cash)}</div></div>
      <div class="kpi" title="总资产 = 现金 + 机队现值；净资产 = 总资产 − 负债，与对手榜的市值同口径排名">
        <div class="l">总资产 ¥M</div><div class="v">${money((p.assets||{}).total ?? (p.cash + ((p.assets||{}).fleet||0)))}</div>
        <div class="sub">净资产 ${money((p.assets||{}).equity ?? p.equity)}</div></div>
      <div class="kpi"><div class="l">负债 ¥M</div><div class="v">${money(p.debt)}</div></div>
      <div class="kpi"><div class="l">日客流</div><div class="v">${Math.round(k.pax||0).toLocaleString()}</div></div>
      <div class="kpi"><div class="l">日 EBITDA</div><div class="v ${eb>=0?'pos':'neg'}">${money(eb)}</div></div>
      <div class="kpi"><div class="l">口碑</div><div class="v">${(p.reputation||0).toFixed(1)}</div></div>
      <div class="kpi"><div class="l">机队/航线</div><div class="v">${p.fleet.length}/${p.routes.length}</div></div>
      <div class="kpi" title="机队利用 = 每天被航线占用的飞机小时 ÷ 上限。每架飞机每天最多 16 h / 8 段，按机型和航段连通块分开算。">
        <div class="l">机队利用</div>
        <div class="v ${usageCls}">${usage.pct}%</div>
        <div class="sub">${usage.text}</div></div>`;
    $("#routecount").textContent=p.routes.length;
    const rhead=`<tr class="rhead"><th>航线</th><th>班次</th><th>机型</th><th>票价</th><th>客座</th><th></th></tr>`;
    $("#routes").innerHTML=rhead+(p.routes.map(r=>{
      const fare=routeFareEco(r);
      const lf=Math.round(Math.min(1,Number(r.lf)||0)*100);
      return `<tr class="rrow" onclick="openOp('route',${r.id})"
          title="${r.segments.join("→")} · 价格指数 ${Number(r.price_index).toFixed(2)} · 客座率 ${lf}% · 点击调整价格/班次/机型">
        <td class="seg">${r.segments.join("→")}</td>
        <td>${r.daily_flights}</td>
        <td class="ac">${escHTML(r.ac_type)}</td>
        <td>${fare!=null?"¥"+fare.toLocaleString("zh-CN"):"—"}</td>
        <td><div class="bar" title="客座率 ${lf}%"><i style="width:${lf}%"></i></div></td>
        <td><span class="x" onclick="event.stopPropagation();closeRouteConfirm(${r.id})">✕</span></td></tr>`;
    }).join("")||'<tr><td colspan="6" style="color:#78899c">点「开航线」或在地图上选两个机场</td></tr>');
  }
  renderRivals(s);

  if(s.log&&s.log.length){ const e=s.log[s.log.length-1];
    $("#log").textContent=`D${e.day} · ${e.title} ${e.detail||""}`; }
  if(OP.mode==="goals") renderGoalsOp();
}

// 侧栏「竞争对手」：只列对手（不含本公司），标题标注 TOP 20 / 共 N 家。
function renderRivals(s){
  const list=(s&&s.rivals)||[];
  const me=s&&s.player;
  const total=(s&&Number.isFinite(s.rivals_total))?s.rivals_total:list.length;
  const tag=$("#rivalcount");
  if(tag){
    tag.textContent=list.length<total?`TOP ${list.length}/${total}`:`${total} 家`;
    tag.title=`按市值排名，高亮的是你自己；对手显示前 ${list.length} 家`
      +(list.length<total?`（共 ${total} 家对手）`:"（全部对手）");
  }
  const rows=list.slice(0,20).map(a=>({
    rank:Number(a.rank)||1e9,
    html:`<tr><td class="rk">${a.rank||""}</td><td>${escHTML(a.name)}</td>
      <td>${escHTML(a.hub||"—")}</td><td>${a.routes}</td>
      <td>${money(a.market_cap)}</td></tr>`,
  }));
  if(me&&me.rank){
    rows.push({
      rank:Number(me.rank)||1e9,
      html:`<tr class="me"><td class="rk">${me.rank}</td><td>${escHTML(me.name)}（你）</td>
        <td>${escHTML((me.hubs||[])[0]||"—")}</td><td>${(me.routes||[]).length}</td>
        <td>${money(me.market_cap)}</td></tr>`,
    });
  }
  rows.sort((a,b)=>a.rank-b.rank);
  $("#rivals").innerHTML=rows.map(r=>r.html).join("")
    ||'<tr><td style="color:#78899c">暂无对手</td></tr>';
}
// ---- renderRivals 结束（tools/panel_check.js 抽取到此标记） ----

async function cmd(text){
  const t=(text||"").trim(); if(!t) return;
  const [op,...a]=t.split(/\s+/);
  const map={
    open:()=>({action:"open_route",args:{segments:a.slice(0,a.length-2),
      daily_flights:Number(a[a.length-2]||1),ac_type:a[a.length-1]||"A320"}}),
    close:()=>({action:"close_route",args:{route_id:Number(a[0])}}),
    price:()=>({action:"set_price",args:{route_id:Number(a[0]),price_index:Number(a[1])}}),
    flights:()=>({action:"set_flights",args:{route_id:Number(a[0]),daily_flights:Number(a[1])}}),
    ac:()=>({action:"set_aircraft",args:{route_id:Number(a[0]),ac_type:(a[1]||"").toUpperCase()}}),
    hub:()=>({action:"add_hub",args:{airport:a[0]}}),
    buy:()=>({action:"buy_aircraft",args:{ac_type:a[0]||"A320",base:a[1]}}),
    lease:()=>({action:"buy_aircraft",args:{ac_type:a[0]||"A320",base:a[1],lease:true}}),
    sell:()=>({action:"sell_aircraft",args:{aircraft_id:Number(a[0])}}),
    rebase:()=>({action:"rebase_aircraft",args:{aircraft_id:Number(a[0]),
      base:(a[1]||"").toUpperCase()}}),
    loan:()=>({action:"take_loan",args:{amount:Number(a[0])}}),
    rename:()=>({action:"rename_airline",args:{name:a.join(" ")}}),
  };
  if(!map[op]){ toast("未知指令 "+op,true); return; }
  const res=await api("/api/command",map[op]());
  if(res.ok){ toast("已执行"); refresh(); }
}

/* 航线主 OD（首→末）的经济舱票价；没有 prices 时返回 null（旧后端兼容） */
function routeFareEco(r){
  const segs=(r&&r.segments)||[];
  if(segs.length<2) return null;
  const list=(r&&r.prices)||[];
  const main=list.find(p=>p.from===segs[0]&&p.to===segs[segs.length-1])||list[0];
  const v=main&&Number(main.eco);
  return Number.isFinite(v)?v:null;
}

/* 机队利用汇总：按机型列利用率，并给出最紧张的一档（供 KPI 与测试使用） */
function fleetUsageSummary(cap){
  const pools=(cap&&cap.pools)||[];
  let used=0, total=0, over=false, worstPct=0, worstType="";
  const parts=[];
  for(const b of pools){
    used+=Number(b.hours_used)||0;
    total+=Number(b.hours_cap)||0;
    const pct=b.hours_cap?Math.round(100*(Number(b.hours_used)||0)/b.hours_cap):0;
    if(b.over||pct>=100) over=true;
    if(pct>worstPct){ worstPct=pct; worstType=b.type; }
    if((Number(b.hours_used)||0)>0||(Number(b.count)||0)>0) parts.push(`${b.type} ${pct}%`);
  }
  const pct=total?Math.round(100*used/total):0;
  return {pct, worstPct, worstType, over,
          text: parts.slice(0,3).join(" · ") || "—"};
}

/* ============================================================
   启动
   ============================================================ */
async function refresh(){
  try{
    STATE=await api("/api/state"); AP={};
    (STATE.airports||[]).forEach(a=>AP[a.iata]=a);
    render();
    renderMarkers();
    drawLabels();
    syncRoutes();
    syncRivalRoutes();
  }catch(e){ $("#log").textContent="后端未连接"; }
}

(async function boot(){
  META=await api("/api/meta").catch(()=>null);
  await loadGeo();
  drawGraticule();
  view=fitView(REGION,42);
  applyView();
  bindMap();
  await refresh();
  setInterval(refresh,1000);
  $("#run").onclick=()=>{ cmd($("#cmd").value); $("#cmd").value=""; };
  $("#cmd").addEventListener("keydown",e=>{
    if(e.key==="Enter"){ cmd($("#cmd").value); $("#cmd").value=""; }});
  $$("[data-speed]").forEach(b=>b.onclick=async()=>{
    const sp=Number(b.dataset.speed);
    const r=await api("/api/control",sp===0?{paused:true}:{paused:false,speed:sp});
    if(r&&r.reason) toast(r.reason,true);
    refresh();
  });

  $$("#actionbar [data-op]").forEach(b=>{
    b.onclick=()=>openOp(b.dataset.op);
  });
  $("#helpbtn").onclick=()=>openOp("help");
  $("#dashbtn").onclick=()=>openOp("dashboard");
  $("#goalbtn").onclick=()=>openOp("goals");
  $("#savebtn").onclick=()=>openOp("saves");
  $("#pname").title="点击修改公司名称";
  $("#pname").onclick=()=>openOp("company");
  $("#opclose").onclick=closeOp;
  $("#opmodal").addEventListener("click",e=>{
    if(e.target===$("#opmodal")) closeOp();
  });
  document.addEventListener("keydown",e=>{
    if(e.key==="Escape"&&OP.mode) closeOp();
  });
  $("#advbtn").onclick=()=>{
    const bar=$("#cmdbar");
    bar.classList.toggle("on");
    const on=bar.classList.contains("on");
    $("#advbtn").textContent=on?"收起指令":"高级指令";
    if(on) setTimeout(()=>$("#cmd").focus(),0);
  };

  if(STATE.goals&&STATE.goals.setup_required) openOp("goals");

  window.addEventListener("beforeunload",()=>{
    try{ navigator.sendBeacon("/api/autosave"); }catch(_){}
  });
})();
