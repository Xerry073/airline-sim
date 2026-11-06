/* 航线图层：玩家航线与 AI 航线（建节点、着色、动画） */
function createRouteNode(r){
  const el=document.createElementNS(NS,"g");
  el.setAttribute("class","rgroup");
  el.setAttribute("data-rid",String(r.id));
  const w=routeWidth(r.lf);
  const shifts=[-1000,0,1000];
  const paths=[], hits=[];
  for(const shift of shifts){
    const d=routePathD(r.segments,AP,shift);
    if(!d) continue;
    const glow=document.createElementNS(NS,"path");
    glow.setAttribute("class","rglow");
    glow.setAttribute("d",d);
    glow.setAttribute("stroke-width",w+4);
    el.appendChild(glow);
    const main=document.createElementNS(NS,"path");
    main.setAttribute("class","rmain");
    main.setAttribute("d",d);
    main.setAttribute("stroke-width",w);
    el.appendChild(main);
    const hit=document.createElementNS(NS,"path");
    hit.setAttribute("class","rhit");
    hit.setAttribute("d",d);
    hit.setAttribute("stroke-width",w+9);
    el.appendChild(hit);
    paths.push(glow,main); hits.push(hit);
  }
  const node={el,paths,hits,data:r,sig:(r.segments||[]).join(">"),w,contested:false,leaving:false};
  el.addEventListener("pointerenter",e=>{
    routeHover=node;
    showRouteTip(node.data,e,"player",node.contested);
    $("#map").style.cursor="pointer";
  });
  el.addEventListener("pointermove",e=>{ if(routeHover===node) positionTip(e); });
  el.addEventListener("pointerleave",()=>{
    if(routeHover===node){
      routeHover=null;
      hideTip();
      $("#map").style.cursor="grab";
    }
  });
  el.addEventListener("click",e=>{
    if(mapGestureMoved) return;
    const p=clientToView(e);
    if(nearestMarker(MAPM.markers,p.x,p.y,view,15)) return;
    e.stopPropagation();
    hideTip();
    openOp("route",node.data.id);
  });
  return node;
}

function animateRoute(node){
  node.paths.forEach(p=>{
    p.setAttribute("pathLength","1");
    p.style.strokeDasharray="1";
    p.style.strokeDashoffset="1";
  });
  requestAnimationFrame(()=>{
    node.paths.forEach(p=>{
      p.style.transition="stroke-dashoffset .46s ease-out";
      p.style.strokeDashoffset="0";
    });
  });
  setTimeout(()=>{
    node.paths.forEach(p=>{
      p.style.strokeDasharray="";
      p.style.strokeDashoffset="";
      p.style.transition="";
    });
  },620);
}

function applyPlayerStyle(node,r,aiMarkets){
  node.data=r;
  node.contested=routeIsContested(r.segments||[],aiMarkets,AP);
  node.el.classList.toggle("contested",node.contested);
  const w=routeWidth(r.lf);
  if(w!==node.w){
    node.w=w;
    node.paths.forEach((p,i)=>p.setAttribute("stroke-width",i%2===0?w+4:w));
    node.hits.forEach(p=>p.setAttribute("stroke-width",w+9));
  }
}

function syncRoutes(){
  const desired=new Map();
  const routes=(STATE&&STATE.player&&STATE.player.routes)||[];
  routes.forEach(r=>desired.set(Number(r.id),r));
  const aiMarkets=routeMarketSet((STATE&&STATE.opponent_routes)||[],AP);

  // 关线：保留 240ms 淡出
  for(const [id,node] of Array.from(ROUTE_NODES)){
    if(desired.has(id)) continue;
    ROUTE_NODES.delete(id);
    node.leaving=true;
    node.el.style.opacity="0";
    setTimeout(()=>node.el.remove(),280);
    if(routeHover===node){ routeHover=null; hideTip(); }
  }

  for(const [id,r] of desired){
    let node=ROUTE_NODES.get(id);
    if(!node){
      node=createRouteNode(r);
      applyPlayerStyle(node,r,aiMarkets);
      $("#routelayer").appendChild(node.el);
      ROUTE_NODES.set(id,node);
      if(!firstRouteSync) animateRoute(node);
      continue;
    }
    const sig=(r.segments||[]).join(">");
    if(sig!==node.sig){
      const fresh=createRouteNode(r);
      applyPlayerStyle(fresh,r,aiMarkets);
      node.el.replaceWith(fresh.el);
      ROUTE_NODES.set(id,fresh);
      if(!firstRouteSync) animateRoute(fresh);
      continue;
    }
    applyPlayerStyle(node,r,aiMarkets);
  }
  firstRouteSync=false;
}

/* 对手航线：低饱和灰；与我的市场重叠时变暗黄。线宽同样按客座率。 */
function rivalKey(r){
  return (r.airline||"AI")+"|"+(r.segments||[]).join(">");
}

function createRivalNode(r,contested){
  const el=document.createElementNS(NS,"g");
  el.setAttribute("class","rrgroup"+(contested?" contested":""));
  el.setAttribute("data-key",rivalKey(r));
  const w=routeWidth(r.lf);
  const shifts=[-1000,0,1000];
  const paths=[], hits=[];
  for(const shift of shifts){
    const d=routePathD(r.segments,AP,shift);
    if(!d) continue;
    const p=document.createElementNS(NS,"path");
    p.setAttribute("class","rrpath");
    p.setAttribute("d",d);
    p.setAttribute("stroke-width",w);
    el.appendChild(p);
    const hit=document.createElementNS(NS,"path");
    hit.setAttribute("class","rrhit");
    hit.setAttribute("d",d);
    hit.setAttribute("stroke-width",w+8);
    el.appendChild(hit);
    paths.push(p); hits.push(hit);
  }
  const node={el,paths,hits,data:r,sig:(r.segments||[]).join(">"),w,contested,leaving:false};
  el.addEventListener("pointerenter",e=>{
    routeHover=node;
    showRouteTip(node.data,e,"rival",node.contested);
    $("#map").style.cursor="pointer";
  });
  el.addEventListener("pointermove",e=>{ if(routeHover===node) positionTip(e); });
  el.addEventListener("pointerleave",()=>{
    if(routeHover===node){
      routeHover=null;
      hideTip();
      $("#map").style.cursor="grab";
    }
  });
  el.addEventListener("click",e=>{
    if(mapGestureMoved) return;
    const p=clientToView(e);
    if(nearestMarker(MAPM.markers,p.x,p.y,view,15)) return;
    e.stopPropagation();
    hideTip();
    openOp("public",node.data);
  });
  return node;
}

function syncRivalRoutes(){
  const layer=$("#rivalroutes");
  if(!SHOW_AI){
    if(routeHover&&[...RIVAL_NODES.values()].includes(routeHover)){ routeHover=null; hideTip(); }
    layer.innerHTML="";
    RIVAL_NODES.clear();
    return;
  }
  const routes=(STATE&&STATE.opponent_routes)||[];
  const playerMarkets=routeMarketSet((STATE&&STATE.player&&STATE.player.routes)||[],AP);
  const desired=new Map();
  routes.forEach(r=>desired.set(rivalKey(r),r));

  for(const [key,node] of Array.from(RIVAL_NODES)){
    if(desired.has(key)) continue;
    RIVAL_NODES.delete(key);
    node.el.remove();
    if(routeHover===node){ routeHover=null; hideTip(); }
  }

  for(const [key,r] of desired){
    const contested=routeIsContested(r.segments||[],playerMarkets,AP);
    let node=RIVAL_NODES.get(key);
    if(!node){
      node=createRivalNode(r,contested);
      layer.appendChild(node.el);
      RIVAL_NODES.set(key,node);
      continue;
    }
    if((r.segments||[]).join(">")!==node.sig){
      const fresh=createRivalNode(r,contested);
      node.el.replaceWith(fresh.el);
      RIVAL_NODES.set(key,fresh);
      if(routeHover===node){ routeHover=null; hideTip(); }
      continue;
    }
    node.data=r;
    node.contested=contested;
    node.el.classList.toggle("contested",contested);
    const w=routeWidth(r.lf);
    if(w!==node.w){
      node.w=w;
      node.paths.forEach(p=>p.setAttribute("stroke-width",w));
      node.hits.forEach(p=>p.setAttribute("stroke-width",w+8));
    }
  }
}

/* ============================================================
   浮层 / 点击 / 缩放 / 平移
   ============================================================ */
