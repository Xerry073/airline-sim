/* 地图交互：悬停浮层、点击吸附、开线向导 */
function tipHTML(m){
  if(m.kind==="city"){
    const pax=Math.round(m.pax||0);
    return `<div class="t1">${m.city} <span class="pill">${m.members.length} 座机场</span></div>
      <div class="sub">${m.members.join(" / ")}</div>
      <div class="row"><span>合计客流</span><b>${pax} 百万人次</b></div>
      <div class="row"><span>状态</span><b>${m.hub?"含玩家枢纽":"同城机场"}</b></div>
      <div class="hint">右键展开后选具体机场为起点</div>`;
  }
  const a=AP[m.iata]||{};
  const mine=(STATE&&STATE.player?STATE.player.routes:[]).filter(r=>r.segments.includes(m.iata)).length;
  return `<div class="t1"><code>${m.iata}</code> ${a.city||m.city}</div>
    <div class="sub">${a.region||""} · ${m.scale} 级</div>
    <div class="row"><span>年客流</span><b>${Math.round(a.pax||m.pax||0)} 百万人次</b></div>
    <div class="row"><span>我的航线</span><b>${mine} 条</b></div>
    <div class="row"><span>状态</span><b>${m.hub?"玩家枢纽":"普通机场"}</b></div>
    <div class="hint">${m.stop?"经停点 · Alt+左键取消"
      :(m.selIndex===0?"起点 · 左键点终点 · Alt+左键加经停"
      :(m.selIndex===1?"终点 · 右键可重选起点"
      :"右键=起点 · 左键=终点 · Alt+左键=经停"))}</div>`;
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

/* 开线选择：右键=起点，左键=终点，Alt+左键=经停点 */
/* ===== ROUTE_PICK_START（tools/route_gui_check.js 原样抽取） ===== */
function pick(iata,mode){
  if(!AP[iata]) return;
  if(mode==="origin") return pickOrigin(iata);
  if(mode==="stop") return pickStopover(iata);
  return pickDestination(iata);
}

function pickOrigin(iata){
  const a=AP[iata];
  if($("#wiz").classList.contains("on")) closeWizard();
  sel=[iata]; stopover=null;
  if((STATE.airports||[]).filter(x=>x.city===a.city).length>1) expandedCity=a.city;
  toast(`${iata} 已设为起点 · 左键点终点 · Alt+左键加经停`);
  renderMarkers(); drawLabels();
}

function pickStopover(iata){
  if(!sel.length){ toast("先用右键点击机场选择起点",true); return; }
  const origin=sel[0], a=AP[iata];
  if(iata===origin){ toast("经停点不能与起点相同",true); return; }
  if(AP[origin]&&AP[origin].city===a.city){ toast("同城机场不能互相经停",true); return; }
  stopover = stopover===iata ? null : iata;
  if(!stopover){ toast("已取消经停点"); renderMarkers(); drawLabels(); return; }
  toast(`经停点 ${stopover} · 再 Alt+左键一次取消`);
  if(sel.length===2) openWizard(routeSegments(sel[0],stopover,sel[1]));
  else { renderMarkers(); drawLabels(); }
}

function pickDestination(iata){
  if(!sel.length){ toast("右键点击机场选择航线起点",true); return; }
  const origin=sel[0], a=AP[iata];
  if(iata===origin){ toast("起点与终点不能相同",true); return; }
  if(AP[origin]&&AP[origin].city===a.city){ toast("同城机场之间不构成航线",true); return; }
  if(stopover===iata) stopover=null;
  sel=[origin,iata];
  openWizard(routeSegments(origin,stopover,iata));
  renderMarkers(); drawLabels();
}

function routeSegments(origin,stop,dest){
  return stop ? [origin,stop,dest] : [origin,dest];
}

function clearSelection(){
  sel=[]; stopover=null; expandedCity=null; hoverId=null;
  closeWizard(); hideTip();
  renderMarkers(); drawLabels();
}

function closeWizard(){ $("#wiz").classList.remove("on"); }
/* ===== ROUTE_PICK_END ===== */

async function openWizard(segs){
  const w=$("#wiz");
  const stop=segs.length>2?segs[1]:null;
  const head=`<h3><span>${segs.join(" → ")}</span><span class="x" onclick="clearSelection()">✕</span></h3>`;
  w.classList.add("on");
  w.innerHTML=head+`<div class="hint">正在查询市场…</div>`;

  let market=null;
  if(!stop){
    try{ market=await fetch(`/api/market?from=${segs[0]}&to=${segs[1]}`).then(r=>r.json()); }
    catch(e){ w.innerHTML=head+`<div class="hint" style="color:var(--bad)">市场查询失败</div>`; return; }
    if(!market.ok){ w.innerHTML=head+`<div class="hint" style="color:var(--bad)">${market.reason}</div>`; return; }
  }

  let body, gap=0, suggest=1;
  if(stop){
    const legs=[];
    for(let i=0;i<segs.length-1;i++){
      const from=segs[i], to=segs[i+1];
      legs.push({from,to,km:Math.round(haversineKm(AP[from],AP[to]))});
    }
    const total=legs.reduce((s,x)=>s+x.km,0);
    const direct=Math.round(haversineKm(AP[segs[0]],AP[segs[segs.length-1]]));
    body=`<div class="kv"><span>航段</span><b>${legs.length} 段 · 1 个经停</b></div>
      ${legs.map(l=>`<div class="kv"><span>${l.from} → ${l.to}</span><b>${l.km} km</b></div>`).join("")}
      <div class="kv"><span>总航程</span><b>${total} km</b></div>
      <div class="kv"><span>直飞距离</span><b>${direct} km</b></div>
      <div class="kv"><span>绕行系数</span><b>${direct?(total/direct).toFixed(2):"—"}</b></div>
      <div class="hint">经停航线没有直飞市场数据：开通时后端会逐段校验航程、绕行与时刻。</div>`;
  }else{
    gap=Math.max(0,market.demand_air-market.supply_seats);
    suggest=market.suggest_flights||1;
    body=`<div class="kv"><span>航距</span><b>${market.distance_km} km</b></div>
      <div class="kv"><span>总出行需求</span><b>${market.demand_total.toLocaleString()}/日</b></div>
      <div class="kv"><span>航空需求</span><b>${market.demand_air.toLocaleString()}/日</b></div>
      <div class="kv"><span>现有运力</span><b>${market.supply_seats.toLocaleString()} 座</b></div>
      <div class="kv"><span>运力/需求</span><b class="${gap>0?'pos':'neg'}">${(market.load_ratio*100).toFixed(0)}%</b></div>
      <div class="kv"><span>参考票价</span><b>¥${market.p_ref_eco} / 商务 ¥${market.p_ref_biz}</b></div>
      <div class="kv"><span>竞争者</span><b>${market.competitors.length} 家</b></div>
      ${market.competitors.length?`<div class="hint">${market.competitors.map(c=>c.name).join("、")}</div>`:""}`;
  }

  w.innerHTML=head+body+`
    <div class="row">
      <span class="tag">班次</span><input id="wf" type="number" min="1" max="14" value="${suggest}" style="width:56px">
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
    const cap=stop?f*seats:Math.min(gap,f*seats);
    $("#west").textContent=`预计载客 ${Math.round(cap).toLocaleString()} 人/日（按所选机型满座上限估算）`;
  };
  $("#wf").oninput=estimate;
  $("#wa").onchange=estimate;
  estimate();

  $("#wgo").onclick=async()=>{
    const btn=$("#wgo"); btn.disabled=true;
    const res=await api("/api/command",{action:"open_route",args:{
      segments:segs.slice(), daily_flights:Number($("#wf").value), ac_type:$("#wa").value}});
    btn.disabled=false;
    if(res.ok){
      toast(`航线已开通${res.route_id?" #"+res.route_id:""}`);
      closeWizard(); sel=[]; stopover=null; expandedCity=null;
      await refresh();
    }else{
      $("#west").textContent=res.reason||"开通失败";
    }
  };
}

/* ============================================================
   运营操作面板（所有指令都有选择框入口）
   ============================================================ */
