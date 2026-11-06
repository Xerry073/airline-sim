/* 地图交互：悬停浮层、点击吸附、开线向导 */
function tipHTML(m){
  if(m.kind==="city"){
    const pax=Math.round(m.pax||0);
    return `<div class="t1">${m.city} <span class="pill">${m.members.length} 座机场</span></div>
      <div class="sub">${m.members.join(" / ")}</div>
      <div class="row"><span>合计客流</span><b>${pax} 百万人次</b></div>
      <div class="row"><span>状态</span><b>${m.hub?"含玩家枢纽":"同城机场"}</b></div>
      <div class="hint">点击展开后选择具体机场</div>`;
  }
  const a=AP[m.iata]||{};
  const mine=(STATE&&STATE.player?STATE.player.routes:[]).filter(r=>r.segments.includes(m.iata)).length;
  return `<div class="t1"><code>${m.iata}</code> ${a.city||m.city}</div>
    <div class="sub">${a.region||""} · ${m.scale} 级</div>
    <div class="row"><span>年客流</span><b>${Math.round(a.pax||m.pax||0)} 百万人次</b></div>
    <div class="row"><span>我的航线</span><b>${mine} 条</b></div>
    <div class="row"><span>状态</span><b>${m.hub?"玩家枢纽":"普通机场"}</b></div>
    <div class="hint">${m.selected?"已选中 · 再点取消":"点击选择为航线端点"}</div>`;
}

function showAirportTip(m,e){
  if(!m) return;
  const t=$("#aptip");
  t.innerHTML=tipHTML(m);
  t.classList.add("show");
  positionTip(e);
}

function showRouteTip(r,e,kind,contested){
  if(!r) return;
  const t=$("#aptip");
  const rival=kind==="rival";
  const lf=Number.isFinite(r.lf)?(r.lf*100).toFixed(0):"—";
  const sub=rival
    ? `${escHTML(r.airline||"AI")} · ${r.ac_type||""}`
    : `${r.ac_type||""} · 我的航线 #${r.id}`;
  t.innerHTML=`<div class="t1"><code>${r.segments.join(" → ")}</code></div>
    <div class="sub">${sub}</div>
    <div class="row"><span>每日班次</span><b>${r.daily_flights}</b></div>
    <div class="row"><span>载客率</span><b>${lf}%</b></div>
    ${rival?`<div class="row"><span>竞争状态</span><b class="${contested?"pill":""}">${contested?"与你的市场重叠":"暂无重叠"}</b></div>`
           :`<div class="row"><span>价格指数</span><b>${Number(r.price_index||1).toFixed(2)}</b></div>`}
    <div class="hint">点击打开这条航线的详情</div>`;
  t.classList.add("show");
  positionTip(e);
}

function positionTip(e){
  const wrap=$("#mapwrap").getBoundingClientRect();
  const tip=$("#aptip");
  const w=tip.offsetWidth||210, h=tip.offsetHeight||90;
  let x=e.clientX-wrap.left+16, y=e.clientY-wrap.top+14;
  if(x+w>wrap.width-8) x=e.clientX-wrap.left-w-16;
  if(y+h>wrap.height-8) y=e.clientY-wrap.top-h-14;
  tip.style.left=Math.max(8,x)+"px";
  tip.style.top=Math.max(8,y)+"px";
}

function hideTip(){ $("#aptip").classList.remove("show"); }

function clientToView(e){
  const box=$("#map").getBoundingClientRect();
  const s=Math.min(box.width/VB.w,box.height/VB.h);
  const ox=(box.width-VB.w*s)/2, oy=(box.height-VB.h*s)/2;
  return {x:VB.x+(e.clientX-box.left-ox)/s, y:VB.y+(e.clientY-box.top-oy)/s};
}

function setHover(id){
  if(hoverId===id) return;
  if(hoverId&&MAPM.nodes[hoverId]) MAPM.nodes[hoverId].classList.remove("hover");
  hoverId=id;
  if(hoverId&&MAPM.nodes[hoverId]) MAPM.nodes[hoverId].classList.add("hover");
}

function updateHover(e){
  if(!STATE){ return; }
  const p=clientToView(e);
  const m=nearestMarker(MAPM.markers,p.x,p.y,view,15);
  if(m){
    setHover(m.id);
    showAirportTip(m,e);
    $("#map").style.cursor="pointer";
  }else{
    setHover(null);
    if(!routeHover){ hideTip(); $("#map").style.cursor="grab"; }
  }
}

function pick(iata){
  const a=AP[iata];
  if(!a) return;
  if(sel.length===0){
    sel=[iata];
    const group=(STATE.airports||[]).filter(x=>x.city===a.city);
    if(group.length>1) expandedCity=a.city;
  }else if(sel.length===1){
    if(sel[0]===iata){ sel=[]; }
    else if(AP[sel[0]]&&AP[sel[0]].city===a.city){
      toast("同城机场之间不构成航线",true);
      sel=[iata];
    }else{
      sel=[sel[0],iata];
      openWizard(sel[0],iata);
    }
  }else{
    sel=[iata];
    closeWizard();
  }
  renderMarkers(); drawLabels();
}

function clearSelection(){
  sel=[]; expandedCity=null; hoverId=null;
  closeWizard(); hideTip();
  renderMarkers(); drawLabels();
}

function closeWizard(){ $("#wiz").classList.remove("on"); }

async function openWizard(a,b){
  const w=$("#wiz");
  w.classList.add("on");
  w.innerHTML=`<h3><span>${a} → ${b}</span><span class="x" onclick="clearSelection()">✕</span></h3>
               <div class="hint">正在查询市场…</div>`;
  let m;
  try{ m=await fetch(`/api/market?from=${a}&to=${b}`).then(r=>r.json()); }
  catch(e){ w.innerHTML=`<h3><span>${a} → ${b}</span><span class="x" onclick="clearSelection()">✕</span></h3>
     <div class="hint" style="color:var(--bad)">市场查询失败</div>`; return; }
  if(!m.ok){
    w.innerHTML=`<h3><span>${a} → ${b}</span><span class="x" onclick="clearSelection()">✕</span></h3>
      <div class="hint" style="color:var(--bad)">${m.reason}</div>`;
    return;
  }

  const gap=Math.max(0,m.demand_air-m.supply_seats);
  w.innerHTML=`
    <h3><span>${a} → ${b}</span><span class="x" onclick="clearSelection()">✕</span></h3>
    <div class="kv"><span>航距</span><b>${m.distance_km} km</b></div>
    <div class="kv"><span>总出行需求</span><b>${m.demand_total.toLocaleString()}/日</b></div>
    <div class="kv"><span>航空需求</span><b>${m.demand_air.toLocaleString()}/日</b></div>
    <div class="kv"><span>现有运力</span><b>${m.supply_seats.toLocaleString()} 座</b></div>
    <div class="kv"><span>运力/需求</span><b class="${gap>0?'pos':'neg'}">${(m.load_ratio*100).toFixed(0)}%</b></div>
    <div class="kv"><span>参考票价</span><b>¥${m.p_ref_eco} / 商务 ¥${m.p_ref_biz}</b></div>
    <div class="kv"><span>竞争者</span><b>${m.competitors.length} 家</b></div>
    ${m.competitors.length?`<div class="hint">${m.competitors.map(c=>c.name).join("、")}</div>`:""}
    <div class="row">
      <span class="tag">班次</span><input id="wf" type="number" min="1" max="14" value="${m.suggest_flights}" style="width:56px">
      <select id="wa">${(META?META.aircraft:[]).map(t=>`<option value="${t.code}">${t.name}（${t.seats}座）</option>`).join("")}</select>
    </div>
    <div class="row">
      <button class="primary" id="wgo" style="flex:1">开通航线</button>
    </div>
    <div class="hint" id="west"></div>`;

  const estimate=()=>{
    const f=Math.max(1,Math.min(14,Number($("#wf").value)||1));
    const t=(META&&META.aircraft||[]).find(x=>x.code===$("#wa").value);
    const seats=t?t.seats:165;
    $("#west").textContent=`预计载客 ${Math.round(Math.min(gap,f*seats)).toLocaleString()} 人/日（按所选机型满座上限估算）`;
  };
  $("#wf").oninput=estimate;
  $("#wa").onchange=estimate;
  estimate();

  $("#wgo").onclick=async()=>{
    const res=await api("/api/command",{action:"open_route",
      args:{segments:[a,b], daily_flights:Number($("#wf").value), ac_type:$("#wa").value}});
    if(res.ok){
      toast("航线已开通"); closeWizard(); sel=[]; expandedCity=null;
      await refresh();
    }
  };
}

/* ============================================================
   运营操作面板（所有指令都有选择框入口）
   ============================================================ */
