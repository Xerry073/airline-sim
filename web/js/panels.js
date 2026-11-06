/* 运营面板：开线 / 航线 / 机队 / 枢纽 / 贷款 / 改名 / 教程 / 数据看板 */
const HUB_FEE={XL:300,L:200,M:100,S:60,R:50};
let OP={mode:null,routeId:null,hubCode:null,acCode:null,publicRoute:null,seq:0};

function aircraftList(){ return (META&&META.aircraft)||[]; }
function aircraftOf(code){ return aircraftList().find(t=>t.code===code); }
function airportOptions(selected){
  return (STATE&&STATE.airports||[]).slice()
    .sort((a,b)=>(b.pax||0)-(a.pax||0))
    .map(a=>`<option value="${a.iata}"${a.iata===selected?" selected":""}>${a.iata} · ${a.city} · ${a.scale}</option>`)
    .join("");
}
function aircraftOptions(selected){
  return aircraftList().map(t=>
    `<option value="${t.code}"${t.code===selected?" selected":""}>${t.name} · ${t.seats}座 · ${Math.round(t.range)}km · ¥${t.price}M</option>`
  ).join("");
}
function acResale(a){
  const t=aircraftOf(a.type);
  if(!t) return 0;
  const mv=t.price*Math.max(.10,1-.065*a.age-.0015*a.age*a.age);
  return mv*.85;
}

const escHTML=s=>String(s).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));

function openOp(mode,arg){
  if(!STATE&&mode!=="help"){ toast("状态尚未加载",true); return; }
  OP={mode,routeId:null,hubCode:null,acCode:null,
      publicRoute:mode==="public"?arg:null,seq:OP.seq+1};
  if(mode==="route"){
    const routes=(STATE.player&&STATE.player.routes)||[];
    OP.routeId=arg!=null?Number(arg):(routes[0]?routes[0].id:null);
  }
  if(mode==="hub"){
    OP.hubCode=arg||"PEK";
    if(!AP[OP.hubCode]) OP.hubCode=(STATE.airports[0]||{}).iata||"PEK";
  }
  if(mode==="fleet"){
    const acs=aircraftList();
    const affordable=acs.find(t=>t.price<=(STATE.player?STATE.player.cash:0));
    OP.acCode=(affordable||acs[0]||{}).code||null;
  }
  $("#opmodal .dialog").classList.toggle("wide",mode==="dashboard"||mode==="saves"||mode==="goals");
  $("#opmodal").classList.add("on");
  $("#opmodal").setAttribute("aria-hidden","false");
  renderOp();
}
function closeOp(){
  OP.seq++;
  OP.mode=null;
  $("#opmodal").classList.remove("on");
  $("#opmodal").setAttribute("aria-hidden","true");
}
function renderOp(){
  if(!OP.mode) return;
  const titles={new:"开航线",route:"航线管理",fleet:"机队管理",hub:"枢纽设置",
    loan:"贷款",company:"公司名称",help:"教程 / 高级指令",dashboard:"航线数据看板",
    public:"航线详情",saves:"存档 / 读档",goals:"模式 / 目标"};
  $("#optitle").textContent=titles[OP.mode]||"运营操作";
  if(OP.mode==="new") renderNewRouteOp();
  else if(OP.mode==="route") renderRouteOp();
  else if(OP.mode==="fleet") renderFleetOp();
  else if(OP.mode==="hub") renderHubOp();
  else if(OP.mode==="loan") renderLoanOp();
  else if(OP.mode==="company") renderCompanyOp();
  else if(OP.mode==="help") renderHelpOp();
  else if(OP.mode==="dashboard") renderDashboardOp();
  else if(OP.mode==="public") renderPublicRouteOp();
  else if(OP.mode==="saves") renderSavesOp();
  else if(OP.mode==="goals") renderGoalsOp();
}

/* ---------- 开航线 ---------- */
function renderNewRouteOp(){
  const hubs=(STATE.player&&STATE.player.hubs)||[];
  const from=hubs[0]||"PEK";
  const to=(STATE.airports.find(a=>a.city!==(AP[from]||{}).city)||{}).iata||"SHA";
  const defaultAc=(aircraftList().find(t=>t.code==="A320")||aircraftList()[0]||{}).code||"";
  $("#opbody").innerHTML=`
    <div class="grid2">
      <div class="field"><label>起点机场</label><select id="of">${airportOptions(from)}</select></div>
      <div class="field"><label>终点机场</label><select id="ot">${airportOptions(to)}</select></div>
    </div>
    <div class="grid2">
      <div class="field"><label>经停点（可选）</label><select id="os"><option value="">不设经停（直飞）</option>${airportOptions("")}</select></div>
      <div class="field"><label>每日班次</label><input id="ofl" type="number" min="1" max="14" value="1"></div>
    </div>
    <div class="field"><label>机型</label><select id="oac">${aircraftOptions(defaultAc)}</select></div>
    <div class="marketbox" id="omkt">正在查询市场…</div>
    <div class="btnrow"><button class="primary" id="ogo">开通航线</button><span class="hintline" id="ohint"></span></div>`;

  let timer=null;
  const schedule=()=>{ clearTimeout(timer); timer=setTimeout(queryMarket,180); };
  async function queryMarket(){
    const seq=++OP.seq;
    const from=$("#of").value, to=$("#ot").value, stop=$("#os").value;
    const ac=aircraftOf($("#oac").value);
    const box=$("#omkt"), go=$("#ogo"), hint=$("#ohint");
    if(!box) return;
    hint.textContent="";
    if(!from||!to) return;
    const ca=AP[from], cb=AP[to];
    if(!ca||!cb) return;
    if(ca.city===cb.city){
      box.innerHTML='<span class="bad">同城机场之间不构成航线</span>';
      go.disabled=true; return;
    }
    if(stop){
      box.innerHTML='<span class="warn">经停航线</span>：市场预览只针对直飞；提交后由后端逐段校验航程、绕行与时刻。';
      go.disabled=false; return;
    }
    box.textContent="正在查询市场…";
    let m;
    try{ m=await fetch(`/api/market?from=${from}&to=${to}`).then(r=>r.json()); }
    catch(e){ if(seq===OP.seq) box.innerHTML='<span class="bad">市场查询失败</span>'; return; }
    if(seq!==OP.seq) return;
    if(!m.ok){ box.innerHTML=`<span class="bad">${m.reason}</span>`; go.disabled=true; return; }
    const over=ac && m.distance_km > ac.range*0.95;
    const lf=m.load_ratio==null?"—":(m.load_ratio*100).toFixed(0)+"%";
    const est=ac?Math.min(Math.max(0,m.demand_air-m.supply_seats),
                          Number($("#ofl").value||1)*ac.seats):0;
    box.innerHTML=`
      <div class="mgrid">
        <span>航距 <b>${m.distance_km} km</b></span>
        <span>航空需求 <b>${m.demand_air.toLocaleString()}/日</b></span>
        <span>现有运力 <b>${m.supply_seats.toLocaleString()} 座</b></span>
        <span>运力/需求 <b>${lf}</b></span>
        <span>参考票价 <b>¥${m.p_ref_eco}</b></span>
        <span>竞争者 <b>${m.competitors.length} 家</b></span>
      </div>
      <div class="hintline" style="margin-top:6px">预计载客 ${Math.round(est).toLocaleString()} 人/日（按所选机型满座上限估算）</div>
      ${over?`<div class="warn" style="margin-top:5px">超出机型航程（${Math.round(ac.range)} km），请换宽体机</div>`:""}`;
    go.disabled=!!over;
  }
  $("#of").onchange=schedule;
  $("#ot").onchange=schedule;
  $("#os").onchange=schedule;
  $("#oac").onchange=schedule;
  $("#ofl").oninput=schedule;
  $("#ogo").onclick=async()=>{
    const from=$("#of").value, to=$("#ot").value, stop=$("#os").value;
    if(from===to){ toast("起点和终点不能相同",true); return; }
    if(AP[from]&&AP[to]&&AP[from].city===AP[to].city){ toast("同城机场之间不构成航线",true); return; }
    const segments=stop?[from,stop,to]:[from,to];
    const btn=$("#ogo"); btn.disabled=true;
    const res=await api("/api/command",{action:"open_route",args:{
      segments, daily_flights:Number($("#ofl").value||1), ac_type:$("#oac").value}});
    btn.disabled=false;
    if(res.ok){ toast(`航线已开通 #${res.route_id}`); closeOp(); await refresh(); }
  };
  queryMarket();
}

/* ---------- 现航线：调价 / 班次 / 关闭 ---------- */
function renderRouteOp(){
  const routes=(STATE.player&&STATE.player.routes)||[];
  if(!routes.length){
    $("#opbody").innerHTML='<div class="empty">还没有航线。点左下角「开航线」，或在「高级指令」里用 open 开线。</div>';
    return;
  }
  if(!routes.some(r=>r.id===OP.routeId)) OP.routeId=routes[0].id;
  const r=routes.find(x=>x.id===OP.routeId);
  const opts=routes.map(x=>`<option value="${x.id}"${x.id===r.id?" selected":""}>#${x.id} ${x.segments.join("→")}</option>`).join("");
  const contested=routeIsContested(r.segments||[],
    routeMarketSet((STATE&&STATE.opponent_routes)||[],AP),AP);
  const fmtM=v=>{const n=Number(v)||0;return (n<0?"-":"")+`¥${Math.abs(n).toFixed(2)}M`;};
  const marginVal=r.margin==null?"—":(r.margin*100).toFixed(1)+"%";
  const marginCls=r.margin==null?"":r.margin>0?"pos":r.margin<0?"neg":"";
  $("#opbody").innerHTML=`
    <div class="field"><label>选择航线</label><select id="rsel">${opts}</select></div>
    <div class="marketbox">
      <div class="mgrid">
        <span>航段 <b>${r.segments.join(" → ")}</b></span>
        <span>机型 <b>${r.ac_type}</b></span>
        <span>每日班次 <b>${r.daily_flights}</b></span>
        <span>价格指数 <b>${r.price_index.toFixed(2)}</b></span>
        <span>载客率 <b>${(r.lf*100).toFixed(0)}%</b></span>
        <span>日客流 <b>${Math.round(r.pax||0).toLocaleString()}</b></span>
        <span>航距 <b>${Math.round(r.distance_km||0).toLocaleString()} km</b></span>
        <span>竞争 <b class="${contested?"warn":""}">${contested?"有 AI 共享市场":"暂无重叠"}</b></span>
        <span>日收入 <b>${fmtM(r.revenue_M)}</b></span>
        <span>日成本 <b>${fmtM(r.cost_M)}</b></span>
        <span>利润率 <b class="${marginCls}">${marginVal}</b></span>
        <span>日利润 <b>${fmtM(r.profit_M)}</b></span>
      </div>
      <div class="hintline" style="margin-top:6px">利润率为航线可归集口径，不含折旧租赁与总部固定费用。</div>
    </div>
    <div class="opcard">
      <h4>调价 <span>价格指数 0.50–1.50，1.00 = 参考票价</span></h4>
      <div class="range-row">
        <input id="prange" type="range" min="0.50" max="1.50" step="0.01" value="${r.price_index}">
        <input id="pnum" type="number" min="0.50" max="1.50" step="0.01" value="${r.price_index.toFixed(2)}">
      </div>
      <div class="btnrow"><button id="psave">应用新价格</button></div>
    </div>
    <div class="opcard">
      <h4>班次 <span>1–14 班/日，受机队运力限制</span></h4>
      <div class="range-row">
        <input id="flights_num" type="number" min="1" max="14" value="${r.daily_flights}" style="width:90px">
      </div>
      <div class="btnrow"><button id="fsave">应用班次</button></div>
    </div>
    <div class="btnrow"><button class="danger" id="rclose">关闭这条航线</button><span class="hintline">关闭后时刻释放，不可撤销</span></div>`;

  $("#rsel").onchange=()=>{ OP.routeId=Number($("#rsel").value); renderOp(); };
  $("#prange").oninput=()=>{ $("#pnum").value=Number($("#prange").value).toFixed(2); };
  $("#pnum").oninput=()=>{ const v=Number($("#pnum").value); if(Number.isFinite(v)) $("#prange").value=String(Math.max(.5,Math.min(1.5,v))); };
  $("#psave").onclick=async()=>{
    const idx=Number($("#pnum").value);
    if(!(idx>=.5&&idx<=1.5)){ toast("价格指数须在 0.50–1.50",true); return; }
    const res=await api("/api/command",{action:"set_price",args:{route_id:r.id,price_index:idx}});
    if(res.ok){ toast("价格指数已更新"); await refresh(); renderOp(); }
  };
  $("#fsave").onclick=async()=>{
    const n=Number($("#flights_num").value);
    if(!(n>=1&&n<=14)){ toast("班次须在 1–14 之间",true); return; }
    const res=await api("/api/command",{action:"set_flights",args:{route_id:r.id,daily_flights:n}});
    if(res.ok){ toast("班次已更新"); await refresh(); renderOp(); }
  };
  $("#rclose").onclick=async()=>{
    if(!confirm(`确认关闭 #${r.id} ${r.segments.join("→")}？`)) return;
    const res=await api("/api/command",{action:"close_route",args:{route_id:r.id}});
    if(res.ok){ toast("航线已关闭"); closeOp(); await refresh(); }
  };
}

async function closeRouteConfirm(id){
  const r=((STATE.player&&STATE.player.routes)||[]).find(x=>x.id===id);
  if(!r) return;
  if(!confirm(`确认关闭 #${r.id} ${r.segments.join("→")}？`)) return;
  const res=await api("/api/command",{action:"close_route",args:{route_id:r.id}});
  if(res.ok){ toast("航线已关闭"); await refresh(); }
}

function renderPublicRouteOp(){
  const r=OP.publicRoute;
  if(!r){ $("#opbody").innerHTML='<div class="empty">航线数据已失效</div>'; return; }
  const playerRoutes=(STATE.player&&STATE.player.routes)||[];
  const playerMarkets=routeMarketSet(playerRoutes,AP);
  const contested=routeIsContested(r.segments||[],playerMarkets,AP);
  const rivalMarkets=routeMarketSet([r],AP);
  const overlaps=playerRoutes.filter(pr=>routeIsContested(pr.segments||[],rivalMarkets,AP));
  const prices=Array.isArray(r.prices)?r.prices:[];
  const idx=Number(r.price_index);
  const fareRows=prices.map(p=>{
    const eco=Number(p.eco)||0, biz=Number(p.biz)||0;
    return `<div class="req"><span>${escHTML(p.from||"")} → ${escHTML(p.to||"")}</span>
        <b>经济 ¥${eco.toLocaleString("zh-CN")} · 商务 ¥${biz.toLocaleString("zh-CN")}</b></div>`;
  }).join("");
  $("#opbody").innerHTML=`
    <div class="marketbox">
      <div class="sectionline"><span>${escHTML((r.segments||[]).join(" → "))}</span>
        <span class="${contested?"pill":""}">${contested?"竞争航线":"暂无重叠"}</span></div>
      <div class="mgrid">
        <span>航空公司 <b>${escHTML(r.airline||"AI")}</b></span>
        <span>基地枢纽 <b>${escHTML(r.hub||"—")}</b></span>
        <span>机型 <b>${escHTML(r.ac_type||"—")}</b></span>
        <span>每日班次 <b>${r.daily_flights||"—"}</b></span>
        <span>载客率 <b>${Number.isFinite(r.lf)?(r.lf*100).toFixed(0)+"%":"—"}</b></span>
        <span>价格指数 <b>${Number.isFinite(idx)?idx.toFixed(2):"—"}</b></span>
      </div>
    </div>
    <div class="sectionline"><span>公开票价</span><span>参考价 × 价格指数</span></div>
    ${fareRows||'<div class="empty">这条航线暂未公开票价</div>'}
    <div class="sectionline"><span>与我的航线关系</span><span>${overlaps.length} 条重叠</span></div>
    ${overlaps.length
      ? overlaps.map(pr=>`<div class="req"><span>#${pr.id} ${escHTML((pr.segments||[]).join(" → "))}</span>
          <b class="warn">共享市场</b></div>`).join("")
      : '<div class="empty">这条 AI 航线目前与你的航线没有共享城市市场。</div>'}
    <div class="hintline" style="margin-top:10px">对手航线公开网络、班次、载客率与票价；成本、收入与财务不公开。</div>`;
}

/* ---------- 机队 ---------- */
function renderFleetOp(){
  const p=STATE.player, fleet=p.fleet||[], hubs=p.hubs||[];
  const acs=aircraftList();
  if(!acs.length){ $("#opbody").innerHTML='<div class="empty">机型库未加载</div>'; return; }
  if(!OP.acCode||!aircraftOf(OP.acCode)) OP.acCode=acs[0].code;
  const ac=aircraftOf(OP.acCode);
  const rows=fleet.map(a=>{
    const t=aircraftOf(a.type);
    return `<tr><td>${t?t.name:a.type}</td><td>${a.age.toFixed(1)}</td><td>${a.base||"—"}</td>
      <td>${a.lease?"租赁":"自有"}</td><td>¥${acResale(a).toFixed(0)}M</td>
      <td><button class="mini danger" data-sell="${a.id}">出售</button></td></tr>`;
  }).join("")||'<tr><td colspan="6" style="color:#78899c">暂无飞机</td></tr>';
  const baseOpts=hubs.map(h=>`<option value="${h}">${h}${AP[h]?" · "+AP[h].city:""}</option>`).join("")
    ||'<option value="">无枢纽</option>';
  $("#opbody").innerHTML=`
    <div class="sectionline"><span>现有机队</span><span>${fleet.length} 架</span></div>
    <div class="fleetlist"><table><thead><tr><th>机型</th><th>机龄</th><th>基地</th><th>方式</th><th>出售可得</th><th></th></tr></thead>
      <tbody>${rows}</tbody></table></div>
    <div class="opcard" style="margin-top:12px">
      <h4>购入 / 租赁 <span>自有飞机按目录价扣现金；租赁先付押金</span></h4>
      <div class="grid2">
        <div class="field" style="margin:0"><label>机型</label><select id="ac_type">${aircraftOptions(OP.acCode)}</select></div>
        <div class="field" style="margin:0"><label>基地机场</label><select id="ac_base">${baseOpts}</select></div>
      </div>
      <label class="checkrow"><input id="ac_lease" type="checkbox"> 租赁（押金约 3 个月租金）</label>
      <div class="hintline" id="acinfo"></div>
      <div class="btnrow"><button class="primary" id="ac_buy">购买</button><span class="hintline" id="achint"></span></div>
    </div>`;

  const updateBuy=()=>{
    const t=aircraftOf($("#ac_type").value);
    if(!t) return;
    OP.acCode=t.code;
    const lease=$("#ac_lease").checked;
    $("#acinfo").innerHTML=`${t.name} · ${t.seats}座 · ${Math.round(t.range)}km 航程 · 目录价 <b>¥${t.price}M</b> · 预计转售价约 ¥${(t.price*.85).toFixed(0)}M`;
    $("#ac_buy").textContent=lease?"租赁":"购买";
    $("#ac_buy").disabled=!hubs.length||(!lease&&STATE.player.cash<t.price);
    $("#achint").innerHTML=!hubs.length?"请先设置枢纽":
      (lease?"：租赁需支付押金，后端校验现金":(STATE.player.cash<t.price?"：现金不足":""));
  };
  $("#ac_type").onchange=updateBuy;
  $("#ac_lease").onchange=updateBuy;
  updateBuy();

  $("#opbody").querySelectorAll("[data-sell]").forEach(b=>{
    b.onclick=async()=>{
      const a=fleet.find(x=>String(x.id)===b.dataset.sell);
      if(!a||!confirm(`确认出售 ${a.type}（编号 ${a.id}）？预计回笼 ¥${acResale(a).toFixed(0)}M`)) return;
      const res=await api("/api/command",{action:"sell_aircraft",args:{aircraft_id:a.id}});
      if(res.ok){ toast(`已出售，回笼 ¥${Number(res.cash).toFixed(0)}M`); await refresh(); renderFleetOp(); }
    };
  });

  $("#ac_buy").onclick=async()=>{
    const lease=$("#ac_lease").checked;
    const base=$("#ac_base").value;
    if(!base){ toast("请先设置基地枢纽",true); return; }
    const btn=$("#ac_buy"); btn.disabled=true;
    const res=await api("/api/command",{action:"buy_aircraft",args:{
      ac_type:$("#ac_type").value, base, lease}});
    if(res.ok){ toast(lease?"飞机已租赁":"飞机已购入"); await refresh(); renderFleetOp(); }
    else btn.disabled=false;
  };
}

/* ---------- 枢纽 ---------- */
function renderHubOp(){
  const p=STATE.player, hubs=p.hubs||[];
  if(!OP.hubCode||!AP[OP.hubCode]) OP.hubCode=(STATE.airports[0]||{}).iata||"PEK";
  const code=OP.hubCode, a=AP[code];
  if(!a){ $("#opbody").innerHTML='<div class="empty">机场库未加载</div>'; return; }
  const routesAt=(p.routes||[]).filter(r=>r.segments.includes(code)).length;
  const based=(p.fleet||[]).filter(x=>x.base===code).length;
  const fee=HUB_FEE[a.scale]||0;
  const checks=[
    ["枢纽数量", `${hubs.length} / 3`, hubs.length<3],
    ["尚未设为枢纽", hubs.includes(code)?"已存在":"可以新增", !hubs.includes(code)],
    ["年客流 ≥ 10", `${a.pax} 百万人次`, a.pax>=10],
    ["本场航线 ≥ 2", `${routesAt} 条`, routesAt>=2],
    ["基地飞机 ≥ 3", `${based} 架`, based>=3]
  ];
  const ok=checks.every(x=>x[2]);
  $("#opbody").innerHTML=`
    <div class="field"><label>选择机场</label><select id="hubsel">${airportOptions(code)}</select></div>
    <div class="marketbox">
      <div class="sectionline"><span>当前枢纽</span><span>${hubs.join(" · ")||"—"}</span></div>
      ${checks.map(x=>`<div class="req"><span>${x[0]}</span><b class="${x[2]?"ok":"bad"}">${x[1]}</b></div>`).join("")}
      <div class="req"><span>开设费</span><b>¥${fee}M</b></div>
    </div>
    <div class="btnrow"><button class="primary" id="hubgo" ${ok?"":"disabled"}>设为新枢纽</button>
      <span class="hintline">${ok?"开设费从现金扣除":"上述红色条件未满足，暂不能开设"}</span></div>`;
  $("#hubsel").onchange=()=>{ OP.hubCode=$("#hubsel").value; renderHubOp(); };
  $("#hubgo").onclick=async()=>{
    const res=await api("/api/command",{action:"add_hub",args:{airport:code}});
    if(res.ok){ toast(`枢纽已开通，扣除 ¥${Number(res.fee).toFixed(0)}M`); closeOp(); await refresh(); }
  };
}

/* ---------- 贷款 ---------- */
function renderLoanOp(){
  const p=STATE.player;
  $("#opbody").innerHTML=`
    <div class="marketbox">
      <div class="mgrid">
        <span>现金 <b>¥${p.cash.toFixed(0)}M</b></span>
        <span>负债 <b>¥${p.debt.toFixed(0)}M</b></span>
        <span>权益 <b>¥${p.equity.toFixed(0)}M</b></span>
        <span>授信 <b>由资产/EBITDA 决定</b></span>
      </div>
    </div>
    <div class="field"><label>借款金额（¥M）</label><input id="ln_amt" type="number" min="1" step="50" value="100"></div>
    <div class="chips">
      <button data-amt="100">+100</button><button data-amt="300">+300</button>
      <button data-amt="500">+500</button><button data-amt="1000">+1000</button>
    </div>
    <div class="hintline">可贷额度由后端按机队价值、12 个月 EBITDA 与权益实时计算；超出额度会返回具体数字。</div>
    <div class="btnrow"><button class="primary" id="lngo">确认借款</button></div>`;
  $("#opbody").querySelectorAll("[data-amt]").forEach(b=>b.onclick=()=>{
    const cur=Number($("#ln_amt").value)||0;
    $("#ln_amt").value=String(cur+Number(b.dataset.amt));
  });
  $("#lngo").onclick=async()=>{
    const amt=Number($("#ln_amt").value);
    if(!(amt>0)){ toast("借款金额须大于 0",true); return; }
    const res=await api("/api/command",{action:"take_loan",args:{amount:amt}});
    if(res.ok){ toast(`已借款 ¥${amt}M`); await refresh(); renderLoanOp(); }
  };
}

/* ---------- 公司改名 ---------- */
function renderCompanyOp(){
  const p=STATE.player;
  $("#opbody").innerHTML=`
    <div class="marketbox">
      <div class="mgrid">
        <span>当前名称 <b>${escHTML(p.name)}</b></span>
        <span>当前排名 <b>${p.rank?"#"+p.rank:"未排名"}</b></span>
      </div>
    </div>
    <div class="field"><label>新的公司名称（2–20 个字符）</label>
      <input id="co_name" type="text" maxlength="20" value="${escHTML(p.name)}" autocomplete="off">
    </div>
    <div class="hintline">名称会同步到侧栏、排行榜、日志和地图开线向导；不能与其他公司重名。</div>
    <div class="btnrow">
      <button class="primary" id="co_save">保存名称</button>
      <span class="hintline" id="co_count"></span>
    </div>`;
  const input=$("#co_name"), count=$("#co_count"), save=$("#co_save");
  const refreshCount=()=>{
    const n=[...input.value].length;
    count.textContent=`${n} / 20`;
    save.disabled=n<2||n>20;
  };
  input.oninput=refreshCount;
  refreshCount();
  $("#co_save").onclick=async()=>{
    const name=input.value.trim();
    if([...name].length<2||[...name].length>20){ toast("公司名称须为 2–20 个字符",true); return; }
    save.disabled=true;
    const res=await api("/api/command",{action:"rename_airline",args:{name}});
    if(res.ok){ await refresh(); closeOp(); toast("公司名称已更新"); }
    else save.disabled=false;
  };
}

/* ---------- 教程 / 高级指令 ---------- */
function showCmd(cmd){
  closeOp();
  const bar=$("#cmdbar");
  bar.classList.add("on");
  $("#advbtn").textContent="收起指令";
  $("#cmd").value=cmd;
  setTimeout(()=>$("#cmd").focus(),0);
}
function renderHelpOp(){
  const row=(cmd,desc)=>`<tr>
    <td><code>${escHTML(cmd)}</code></td>
    <td class="desc">${desc}</td>
    <td><button class="mini fillbtn" data-cmd="${escHTML(cmd)}">填入</button></td></tr>`;
  $("#opbody").innerHTML=`
    <div class="marketbox">
      <div class="sectionline"><span>快速上手</span><span>日常操作不需要指令</span></div>
      <div class="steps">
        <div class="step"><b>1</b><div>点底部「开航线」，选起点/终点/班次/机型；也可以直接在地图上点两个机场。</div></div>
        <div class="step"><b>2</b><div>点侧栏航线行或底部「航线管理」，用滑杆调价、改班次；红叉关线。</div></div>
        <div class="step"><b>3</b><div>「机队」买/租/卖飞机，「设枢纽」看门槛，「贷款」补充现金，「改名」修改公司名称。</div></div>
        <div class="step"><b>4</b><div>「数据看板」按客座率、利润率、航距或机场顺序排序航线，点行可直接进入该航线管理。</div></div>
        <div class="step"><b>5</b><div>左上角「AI 航线」开关显示对手网络；灰=AI，暗黄=与你竞争；悬停看班次/客座率，点航线开详情。</div></div>
        <div class="step"><b>6</b><div>游戏会定时自动存档；「存档」里可手动保存、载入，或「保存并退出 / 保存并重启」。</div></div>
      </div>
    </div>
    <div class="sectionline"><span>自动存档 · 重启 · 退出</span><span>Windows 本地</span></div>
    <div class="marketbox">
      <div class="req"><span>启动游戏</span><b>桌面「航空模拟」或 start.cmd</b></div>
      <div class="req"><span>自动存档</span><b>后端定时 + 退出/重启前强制保存</b></div>
      <div class="req"><span>保存并重启</span><b>右上角「存档」→「保存并重启」</b></div>
      <div class="req"><span>保存并退出</span><b>桌面「退出航空模拟」或存档面板</b></div>
      <div class="req"><span>再次进入</span><b>下次启动默认自动恢复 autosave</b></div>
      <div class="req"><span>开新档</span><b>start.cmd -NoResume</b></div>
    </div>
    <div class="hintline" style="margin:5px 0 12px">只关浏览器不会停后端；直接关后端窗口也可退出，但建议用「保存并退出」。默认端口 8777，存档在项目 saves/ 目录。</div>
    <div class="sectionline"><span>指令怎么写</span><span>高级指令默认收起</span></div>
    <div class="hintline" style="margin-bottom:2px">点右下角「高级指令」展开输入框；点下表的「填入」可直接把示例带进去，再改参数。</div>
    <table class="cmdtbl"><tbody>
      ${row("open PEK SHA 1 A320","开直飞：起点 终点 每日班次 机型")}
      ${row("open PEK CTU LXA 1 A320","开经停：起点 经停 终点 每日班次 机型")}
      ${row("close 3","关闭 3 号航线；航线号见侧栏 / 航线管理")}
      ${row("price 3 1.15","把 3 号航线价格指数调到 1.15（0.50–1.50）")}
      ${row("flights 3 2","把 3 号航线加密到每日 2 班（1–14）")}
      ${row("hub PEK","把北京设为新枢纽；需满足 2 航线 + 3 架基地机 + 吞吐门槛")}
      ${row("buy A320 PEK","购买一架 A320，基地北京")}
      ${row("lease B789 PEK","租赁一架 787-9，基地北京；押金从现金扣除")}
      ${row("sell 12","出售 12 号飞机；飞机号见「机队」")}
      ${row("loan 500","借款 500 ¥M；额度由资产/EBITDA/权益决定")}
      ${row("rename 云翼航空","修改公司名称（2–20 个字符，不能重名）")}
    </tbody></table>
    <div class="hintline" style="margin-top:8px">机场代码看地图标签，航线号在侧栏航线表，飞机号在机队列表；所有输入仍由后端统一校验。</div>
    <div class="btnrow"><button class="primary" onclick="openOp('company')">修改公司名称</button></div>`;
  $("#opbody").querySelectorAll("[data-cmd]").forEach(b=>{
    b.onclick=()=>showCmd(b.dataset.cmd);
  });
}

/* ---------- 航线数据看板 ---------- */
function renderDashboardOp(){
  const routes=(STATE.player&&STATE.player.routes)||[];
  if(!routes.length){
    $("#opbody").innerHTML=`<div class="empty">还没有航线。点「开航线」创建第一条航线后，这里会显示客座率、距离和航线损益。</div>
      <div class="btnrow"><button class="primary" onclick="openOp('new')">去开航线</button></div>`;
    return;
  }
  const sorts={
    lf_desc:"客座率 · 高→低", lf_asc:"客座率 · 低→高",
    margin_desc:"利润率 · 高→低", margin_asc:"利润率 · 低→高",
    dist_desc:"航线距离 · 长→短", dist_asc:"航线距离 · 短→长",
    order_asc:"机场顺序 · A→Z", order_desc:"机场顺序 · Z→A"
  };
  if(!sorts[OP.dashSort]) OP.dashSort="lf_desc";
  const [key,dir]=OP.dashSort.split("_");
  const val=r=>({
    lf:r.lf||0,
    margin:r.margin==null?null:r.margin,
    dist:r.distance_km||0,
    order:(r.segments||[]).join("→")
  })[key];

  const sorted=[...routes].sort((a,b)=>{
    const va=val(a), vb=val(b);
    if(key==="order"){
      const c=String(va).localeCompare(String(vb),"zh-CN");
      return dir==="asc"?c:-c;
    }
    if(va==null&&vb==null) return a.id-b.id;
    if(va==null) return 1;
    if(vb==null) return -1;
    const c=va-vb;
    return (dir==="asc"?c:-c)||(a.id-b.id);
  });

  const sum=(arr,k)=>arr.reduce((s,r)=>s+(Number(r[k])||0),0);
  const totalPax=sum(routes,"pax");
  const avgLf=totalPax>0
    ?routes.reduce((s,r)=>s+(r.lf||0)*(r.pax||0),0)/totalPax
    :routes.reduce((s,r)=>s+(r.lf||0),0)/routes.length;
  const totalRev=sum(routes,"revenue_M");
  const totalCost=sum(routes,"cost_M");
  const totalProfit=totalRev-totalCost;
  const profitable=routes.filter(r=>r.margin!=null&&r.margin>0).length;
  const fmtM=v=>{const n=Number(v)||0;return (n<0?"-":"")+`¥${Math.abs(n).toFixed(2)}M`;};
  const marginCell=r=>{
    if(r.margin==null) return '<span style="color:#6f8499">—</span>';
    const p=(r.margin*100).toFixed(1)+"%";
    const cls=r.margin>0?"mpos":r.margin<0?"mneg":"";
    return `<span class="${cls}">${p}</span>`;
  };

  const opts=Object.entries(sorts).map(([k,label])=>
    `<option value="${k}"${k===OP.dashSort?" selected":""}>${label}</option>`).join("");

  $("#opbody").innerHTML=`
    <div class="dashbar">
      <div>
        <div class="sectionline" style="margin:0">最近结算日 · ${routes.length} 条航线</div>
        <div class="hintline">点任一行可进入该航线的调价 / 班次 / 关线面板</div>
      </div>
      <div class="ctl">
        <select id="dash_sort">${opts}</select>
        <button id="dash_refresh">刷新</button>
      </div>
    </div>
    <div class="dashstats">
      <div class="dashstat"><div class="l">航线数</div><div class="v">${routes.length}</div></div>
      <div class="dashstat"><div class="l">加权客座率</div><div class="v">${(avgLf*100).toFixed(1)}%</div></div>
      <div class="dashstat"><div class="l">可归集收入 / 日</div><div class="v">${fmtM(totalRev)}</div></div>
      <div class="dashstat"><div class="l">可归集利润 / 日</div><div class="v ${totalProfit>=0?"pos":"neg"}">${fmtM(totalProfit)}</div></div>
    </div>
    <div class="dashwrap">
      <table class="dashtable">
        <thead><tr>
          <th>航线</th><th>机型 / 班次</th><th>航距</th><th>客座率</th>
          <th>日客流</th><th>日收入</th><th>日成本</th><th>利润率</th>
        </tr></thead>
        <tbody>${sorted.map(r=>`
          <tr class="rrow" onclick="openOp('route',${r.id})" title="打开航线管理">
            <td><span class="routecell">${r.segments.join(" → ")}</span>
              <span class="sub">#${r.id} · 价格指数 ${Number(r.price_index).toFixed(2)}</span></td>
            <td>${r.ac_type}<span class="sub">${r.daily_flights} 班/日</span></td>
            <td>${Math.round(r.distance_km||0).toLocaleString()} km</td>
            <td>${((r.lf||0)*100).toFixed(0)}%</td>
            <td>${Math.round(r.pax||0).toLocaleString()}</td>
            <td>${fmtM(r.revenue_M||0)}</td>
            <td>${fmtM(r.cost_M||0)}</td>
            <td>${marginCell(r)}<span class="sub">${r.margin!=null?fmtM(r.profit_M||0):""}</span></td>
          </tr>`).join("")}</tbody>
      </table>
    </div>
    <div class="dashnote">
      ${profitable} / ${routes.length} 条航线可归集利润为正。利润率 =（航线收入 − 航线可归集成本）÷ 航线收入；
      成本含燃油、起降、导航、维护、地面、分销与航段人员，<b>不含</b>飞机折旧/租赁、总部固定人员、枢纽固定费与利息。
      因此这里不是公司总利润率。
    </div>`;

  $("#dash_sort").onchange=()=>{
    OP.dashSort=$("#dash_sort").value;
    renderDashboardOp();
  };
  $("#dash_refresh").onclick=async()=>{
    const btn=$("#dash_refresh"); if(btn) btn.disabled=true;
    await refresh();
    renderDashboardOp();
  };
}

/* ---------- 存档 / 读档 ---------- */
let SAVES_SEQ=0;
