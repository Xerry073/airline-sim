/* 地图：投影、大圆采样、机场点、标签避让、缩放视图、底图加载 */
/* ============================================================
   基础状态
   ============================================================ */
const $ = s => document.querySelector(s);
const $$ = s => Array.from(document.querySelectorAll(s));
const NS = "http://www.w3.org/2000/svg";
let STATE=null, META=null, AP={}, GEO=null;

let view={k:1,x:0,y:0};
let sel=[];                 // 已选机场（最多 2 个）
let hoverId=null;           // 当前悬停的机场/城市标记 id
let expandedCity=null;      // 被点开的同城机场组
let routeHover=null;        // 当前悬停的航线节点
let viewAnim=null;

const MAPM={markers:[],nodes:{}};
const ROUTE_NODES=new Map();
const RIVAL_NODES=new Map();
let firstRouteSync=true;
let SHOW_AI=false;
let SEEN_SETTLE=null;
let mapGestureMoved=false;

const REGION={minLon:72,maxLon:147,minLat:14,maxLat:50};
const WORLD={minLon:-180,maxLon:180,minLat:-58,maxLat:82};

/* ============================================================
   地图纯几何（可被 tools/map_check.js 原样抽取测试）
   ============================================================ */
/* ===== MAP_MATH_START ===== */
const VB={x:0,y:24,w:1000,h:712};
const RADIUS={XL:6,L:5,M:4,S:3,R:2.4};
const SCALE_RANK={XL:5,L:4,M:3,S:2,R:1};
const MERGE_K=6;

const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
const scaleRank=s=>SCALE_RANK[s]||1;

function proj(lon,lat){
  const x=(lon+180)/360;
  const s=Math.sin(clamp(lat,-85,85)*Math.PI/180);
  const y=0.5-Math.log((1+s)/(1-s))/(4*Math.PI);
  return [x*1000, y*1000];
}

function haversineKm(a,b){
  const rad=Math.PI/180;
  const dLat=(b.lat-a.lat)*rad, dLon=(b.lon-a.lon)*rad;
  const h=Math.sin(dLat/2)**2+Math.cos(a.lat*rad)*Math.cos(b.lat*rad)*Math.sin(dLon/2)**2;
  return 6371.0088*2*Math.asin(Math.sqrt(h));
}

/* 大圆插值。经度会连续展开（可能 >180 或 < -180），方便 Mercator 下跨日界线绘制。 */
function gcPoints(a,b){
  const rad=Math.PI/180;
  const lat1=a.lat*rad, lon1=a.lon*rad, lat2=b.lat*rad, lon2=b.lon*rad;
  const dLat=lat2-lat1, dLon=lon2-lon1;
  let d=2*Math.asin(Math.sqrt(
    Math.sin(dLat/2)**2+Math.cos(lat1)*Math.cos(lat2)*Math.sin(dLon/2)**2));
  if(!(d>1e-9)) return [{lon:a.lon,lat:a.lat},{lon:b.lon,lat:b.lat}];
  const n=Math.max(12,Math.min(96,Math.ceil(d*45)));
  const pts=[];
  let prevLon=a.lon;
  for(let i=0;i<=n;i++){
    const t=i/n;
    const A=Math.sin((1-t)*d)/Math.sin(d), B=Math.sin(t*d)/Math.sin(d);
    const x=A*Math.cos(lat1)*Math.cos(lon1)+B*Math.cos(lat2)*Math.cos(lon2);
    const y=A*Math.cos(lat1)*Math.sin(lon1)+B*Math.cos(lat2)*Math.sin(lon2);
    const z=A*Math.sin(lat1)+B*Math.sin(lat2);
    const lat=Math.atan2(z,Math.hypot(x,y))/rad;
    let lon=Math.atan2(y,x)/rad;
    while(lon-prevLon>180) lon-=360;
    while(lon-prevLon<-180) lon+=360;
    pts.push({lon,lat});
    prevLon=lon;
  }
  return pts;
}

function routePathD(segments,ap,shiftX){
  shiftX=shiftX||0;
  let d="";
  for(let i=0;i<segments.length-1;i++){
    const a=ap[segments[i]], b=ap[segments[i+1]];
    if(!a||!b) continue;
    const pts=gcPoints(a,b);
    pts.forEach((p,j)=>{
      const [x,y]=proj(p.lon,p.lat);
      d+=(j?"L":"M")+(x+shiftX).toFixed(1)+","+y.toFixed(1);
    });
  }
  return d;
}

function routeWidth(lf){
  return clamp(1.0+clamp(Number(lf)||0,0,1)*2.4,1.0,3.4);
}

/* 航线市场竞争：同时比较完整 OD 与每一个航段；城市级，方向不敏感。 */
function routeMarketKeys(segments,ap){
  const keys=new Set();
  const city=code=>(ap[code]&&ap[code].city)||code;
  if(segments && segments.length>=2){
    const a=city(segments[0]), b=city(segments[segments.length-1]);
    keys.add([a,b].sort().join("|"));
  }
  for(let i=0;segments && i<segments.length-1;i++){
    const a=city(segments[i]), b=city(segments[i+1]);
    keys.add([a,b].sort().join("|"));
  }
  return keys;
}
function routeMarketSet(routes,ap){
  const set=new Set();
  (routes||[]).forEach(r=>{
    routeMarketKeys(r.segments||[],ap).forEach(k=>set.add(k));
  });
  return set;
}
function routeIsContested(segments,otherSet,ap){
  for(const k of routeMarketKeys(segments||[],ap)) if(otherSet.has(k)) return true;
  return false;
}

/* 当前缩放最低显示能级：k<2 只显示 L 及以上；k<3 显示 M 及以上；再放大全显示。 */
function lodRank(k){
  if(k<2) return 4;
  if(k<3) return 3;
  return 1;
}

function buildMarkers(airports,opt){
  const k=opt.k, hubs=opt.hubs||[], selected=opt.sel||[];
  const expanded=opt.expandedCity||null;
  const minRank=lodRank(k);
  const byCity=new Map();
  airports.forEach(a=>{
    if(!byCity.has(a.city)) byCity.set(a.city,[]);
    byCity.get(a.city).push(a);
  });

  const markers=[];
  for(const [city,group] of byCity){
    group.sort((a,b)=>(b.pax||0)-(a.pax||0));
    const hub=group.some(a=>hubs.includes(a.iata));
    const selGroup=group.some(a=>selected.includes(a.iata));
    const maxRank=Math.max(...group.map(a=>scaleRank(a.scale)));
    if(maxRank<minRank && !hub && !selGroup) continue;

    const truePts=group.map(a=>proj(a.lon,a.lat));
    const baseX=truePts.reduce((s,p)=>s+p[0],0)/truePts.length;
    const baseY=truePts.reduce((s,p)=>s+p[1],0)/truePts.length;
    const maxScale=group.reduce((s,a)=>scaleRank(a.scale)>scaleRank(s)?a.scale:s,"R");
    const expandedNow=expanded===city;
    const merged=group.length>1 && k<MERGE_K && !expandedNow && !selGroup;

    if(merged){
      markers.push({
        id:"city:"+city, kind:"city", city, iata:null,
        members:group.map(a=>a.iata), x:baseX, y:baseY, trueX:baseX, trueY:baseY,
        scale:maxScale, pax:group.reduce((s,a)=>s+(a.pax||0),0),
        hub, selected:false, selIndex:-1, leader:false
      });
      continue;
    }

    group.forEach((a,i)=>{
      const trueX=truePts[i][0], trueY=truePts[i][1];
      let x=trueX, y=trueY;
      if(group.length>1){
        const ang=group.length===2 ? (i===0?Math.PI:0)
                                  : (-Math.PI/2+i*2*Math.PI/group.length);
        const rad=18; // 屏幕/viewBox 恒定，避免同城两点永远叠在一起
        x=baseX+Math.cos(ang)*rad/k;
        y=baseY+Math.sin(ang)*rad/k;
      }
      if(scaleRank(a.scale)<minRank && !hubs.includes(a.iata)
         && !selected.includes(a.iata) && !expandedNow) return;
      markers.push({
        id:a.iata, kind:"airport", city, iata:a.iata,
        members:[a.iata], x, y, trueX, trueY,
        scale:a.scale, pax:a.pax||0, hub:hubs.includes(a.iata),
        selected:selected.includes(a.iata), selIndex:selected.indexOf(a.iata),
        leader:group.length>1
      });
    });
  }
  return markers;
}

function markerLabel(m){
  const base=m.kind==="city" ? `${m.city} ×${m.members.length}` : m.iata;
  if(m.selIndex===0) return "① "+base;
  if(m.selIndex===1) return "② "+base;
  return base;
}

/* 屏幕空间贪心避让：优先级为选中 > 枢纽 > 能级/客流。返回不重叠的标签框。 */
function layoutLabels(markers,measure,view,vb){
  vb=vb||VB;
  const items=[];
  markers.forEach(m=>{
    const sx=m.x*view.k+view.x, sy=m.y*view.k+view.y;
    if(sx<vb.x-70||sx>vb.x+vb.w+70||sy<vb.y-70||sy>vb.y+vb.h+70) return;
    const r=RADIUS[m.scale]||3;
    const text=markerLabel(m);
    const w=measure(text)+8, h=15;
    const priority=(m.selIndex>=0?1e7-m.selIndex:0)
                  +(m.hub?1e6:0)+(scaleRank(m.scale)||1)*1e4+(m.pax||0)/100;
    items.push({m,sx,sy,r,w,h,text,priority});
  });
  items.sort((a,b)=>b.priority-a.priority);

  const dots=[];
  markers.forEach(m=>{
    const sx=m.x*view.k+view.x, sy=m.y*view.k+view.y;
    if(sx<vb.x-20||sx>vb.x+vb.w+20||sy<vb.y-20||sy>vb.y+vb.h+20) return;
    const r=RADIUS[m.scale]||3;
    dots.push({id:m.id,x:sx-r,y:sy-r,w:r*2,h:r*2});
  });

  const overlap=(a,b)=>a.x<b.x+b.w && b.x<a.x+a.w && a.y<b.y+b.h && b.y<a.y+a.h;
  const inBounds=b=>b.x>=vb.x+4 && b.y>=vb.y+4 &&
                    b.x+b.w<=vb.x+vb.w-4 && b.y+b.h<=vb.y+vb.h-4;
  const boxes=[];
  for(const it of items){
    const {sx,sy,r,w,h}=it;
    const cands=[
      [sx+r+4, sy-h/2], [sx-r-4-w, sy-h/2],
      [sx-w/2, sy-r-7-h], [sx-w/2, sy+r+7],
      [sx+r+3, sy-r-2-h], [sx-r-3-w, sy-r-2-h],
      [sx+r+3, sy+r+2], [sx-r-3-w, sy+r+2]
    ];
    let box=null;
    for(const [x,y] of cands){
      const b={x,y,w,h};
      if(!inBounds(b)) continue;
      if(boxes.some(o=>overlap(b,o))) continue;
      if(dots.some(d=>d.id!==it.m.id && overlap(b,d))) continue;
      box=b; break;
    }
    if(!box){
      // 候选位都被占时，沿环向外找空位；仍找不到就不标这个点，避免糊成一团。
      const maxRad=it.priority>=1e6?120:68;
      outer:
      for(let rad=Math.max(18,r+10);rad<=maxRad;rad+=7){
        for(let ai=0;ai<16;ai++){
          const ang=ai/16*Math.PI*2;
          const cx=sx+Math.cos(ang)*rad, cy=sy+Math.sin(ang)*rad;
          const b={x:cx-w/2,y:cy-h/2,w,h};
          if(!inBounds(b)) continue;
          if(boxes.some(o=>overlap(b,o))) continue;
          if(dots.some(d=>d.id!==it.m.id && overlap(b,d))) continue;
          if(b.x<=sx && sx<=b.x+b.w && b.y<=sy && sy<=b.y+b.h) continue;
          box=b; break outer;
        }
      }
    }
    if(box) boxes.push({...it,...box});
  }
  return boxes;
}

function nearestMarker(markers,px,py,view,radius){
  radius=radius||15;
  let best=null, bd=radius*radius;
  for(const m of markers){
    const sx=m.x*view.k+view.x, sy=m.y*view.k+view.y;
    const d=(px-sx)**2+(py-sy)**2;
    if(d<bd){ bd=d; best=m; }
  }
  return best;
}

function fitView(bounds,padding,maxK){
  padding=padding==null?40:padding;
  maxK=maxK==null?12:maxK;
  const [x0,yTop]=proj(bounds.minLon,bounds.maxLat);
  const [x1,yBottom]=proj(bounds.maxLon,bounds.minLat);
  const spanX=Math.max(1,x1-x0), spanY=Math.max(1,yBottom-yTop);
  const k=clamp(Math.min((VB.w-2*padding)/spanX,(VB.h-2*padding)/spanY),0.8,maxK);
  const cx=(x0+x1)/2, cy=(yTop+yBottom)/2;
  return {k, x:VB.x+VB.w/2-cx*k, y:VB.y+VB.h/2-cy*k};
}
/* ===== MAP_MATH_END ===== */

/* ============================================================
   地图渲染
   ============================================================ */
function applyView(){
  $("#world").setAttribute("transform",`translate(${view.x},${view.y}) scale(${view.k})`);
}

function drawGraticule(){
  const g=$("#graticule"); g.innerHTML="";
  let d="";
  for(let lon=-180;lon<=180;lon+=30){
    const [x1,y1]=proj(lon,85),[x2,y2]=proj(lon,-85);
    d+=`M${x1},${y1}L${x2},${y2}`;
  }
  for(let lat=-60;lat<=75;lat+=15){
    const [x1,y1]=proj(-180,lat),[x2]=proj(180,lat);
    d+=`M${x1},${y1}L${x2},${y1}`;
  }
  g.innerHTML=`<path d="${d}" fill="none" stroke="var(--grid)" stroke-width="0.7"/>`;
}

async function loadGeo(){
  // 可选底图：把 Natural Earth 的 geojson 放到 web/data/world.geo.json 即自动生效
  try{
    const r=await fetch("/data/world.geo.json");
    if(!r.ok) throw 0;
    GEO=await r.json();
    const g=$("#land"); let d="";
    const ring=coords=>{
      coords.forEach(([lon,lat],j)=>{
        const [x,y]=proj(lon,lat);
        d+=(j?"L":"M")+x.toFixed(1)+","+y.toFixed(1);
      });
      d+="Z";
    };
    const walk=geo=>{
      geo.forEach(f=>{
        const gg=f.geometry||f; if(!gg||!gg.coordinates) return;
        // 记录本要素最高纬度：南极在 Mercator 下会被拉成底部大色带，直接跳过
        let maxLat=-90;
        const scan=c=>{ if(typeof c[0]==="number"){ if(c[1]>maxLat) maxLat=c[1]; } else c.forEach(scan); };
        scan(gg.coordinates);
        if(maxLat<-55) return;
        if(gg.type==="Polygon") gg.coordinates.forEach(ring);
        else if(gg.type==="MultiPolygon") gg.coordinates.forEach(p=>p.forEach(ring));
      });
    };
    walk(GEO.features||[GEO]);
    g.innerHTML=`<path d="${d}" fill="#16212c" stroke="#22303f" stroke-width="0.6"/>`;
  }catch(e){
    $("#mapnote").textContent="点击机场开线 · 滚轮缩放 · 拖拽平移 · 底图未加载";
  }
}

function renderMarkers(){
  const g=$("#aps"), lg=$("#leaders");
  g.innerHTML=""; lg.innerHTML="";
  MAPM.nodes={};
  if(!STATE){ MAPM.markers=[]; return; }

  const hubs=(STATE.player&&STATE.player.hubs)||[];
  const markers=buildMarkers(STATE.airports||[],{
    k:view.k, view, hubs, sel, expandedCity
  });
  MAPM.markers=markers;

  const frag=document.createDocumentFragment();
  for(const m of markers){
    if(m.kind==="airport" && m.leader){
      const line=document.createElementNS(NS,"line");
      line.setAttribute("x1",m.trueX); line.setAttribute("y1",m.trueY);
      line.setAttribute("x2",m.x); line.setAttribute("y2",m.y);
      line.setAttribute("class","leader"+(m.hub?" hub":""));
      lg.appendChild(line);
    }

    const el=document.createElementNS(NS,"g");
    el.setAttribute("class","ap"+(m.selected?" sel":"")+(hoverId===m.id?" hover":""));
    el.setAttribute("data-id",m.id);

    const rad=(RADIUS[m.scale]||3)/view.k;
    const halo=document.createElementNS(NS,"circle");
    halo.setAttribute("class","halo");
    halo.setAttribute("cx",m.x); halo.setAttribute("cy",m.y);
    halo.setAttribute("r",rad+5/view.k);
    halo.setAttribute("stroke-width",1.4/view.k);
    el.appendChild(halo);

    if(m.kind==="city"){
      const ring=document.createElementNS(NS,"circle");
      ring.setAttribute("class","cityring");
      ring.setAttribute("cx",m.x); ring.setAttribute("cy",m.y);
      ring.setAttribute("r",rad+3.4/view.k);
      ring.setAttribute("stroke-width",1/view.k);
      el.appendChild(ring);
    }else if(m.hub){
      const ring=document.createElementNS(NS,"circle");
      ring.setAttribute("class","hubring");
      ring.setAttribute("cx",m.x); ring.setAttribute("cy",m.y);
      ring.setAttribute("r",rad+2.6/view.k);
      ring.setAttribute("stroke-width",1.1/view.k);
      el.appendChild(ring);
    }

    const dot=document.createElementNS(NS,"circle");
    dot.setAttribute("class","dot");
    dot.setAttribute("cx",m.x); dot.setAttribute("cy",m.y);
    dot.setAttribute("r",rad);
    dot.setAttribute("fill",m.selected?"#ffc93c":(m.hub?"#ff8a3d":(m.kind==="city"?"#c8d6e4":SCALE_COLOR[m.scale]||"#6b7684")));
    dot.setAttribute("stroke",(m.selected||m.hub)?"#fff":"#0a0f14");
    dot.setAttribute("stroke-width",(m.selected||m.hub?1.1:0.65)/view.k);
    el.appendChild(dot);

    frag.appendChild(el);
    MAPM.nodes[m.id]=el;
  }
  g.appendChild(frag);
  if(hoverId && !MAPM.nodes[hoverId]){ hoverId=null; hideTip(); }
}

let _measureCtx=null;
function measureLabel(text){
  if(!_measureCtx){
    try{ _measureCtx=document.createElement("canvas").getContext("2d"); }catch(e){}
  }
  if(!_measureCtx) return text.length*6.6;
  _measureCtx.font='600 11px -apple-system,"Segoe UI","Microsoft YaHei",sans-serif';
  return _measureCtx.measureText(text).width;
}

function drawLabels(){
  const g=$("#labels"); g.innerHTML="";
  if(!STATE) return;
  const labels=layoutLabels(MAPM.markers,measureLabel,view,VB);
  const frag=document.createDocumentFragment();
  for(const l of labels){
    // 标签被挤远时补一条细引线，避免读者不知道它属于哪个点
    const cx=l.x+l.w/2, cy=l.y+l.h/2;
    if(Math.hypot(cx-l.sx,cy-l.sy)>18){
      const tx=clamp(l.sx,l.x,l.x+l.w), ty=clamp(l.sy,l.y,l.y+l.h);
      const line=document.createElementNS(NS,"line");
      line.setAttribute("x1",l.sx); line.setAttribute("y1",l.sy);
      line.setAttribute("x2",tx); line.setAttribute("y2",ty);
      line.setAttribute("class","labline");
      frag.appendChild(line);
    }
    const t=document.createElementNS(NS,"text");
    t.setAttribute("x",l.x+4); t.setAttribute("y",l.y+11);
    let cls="lab";
    if(l.m.kind==="city") cls+=" lab-city";
    else if(l.m.selIndex>=0) cls+=" lab-sel";
    else if(l.m.hub) cls+=" lab-hub";
    else if(scaleRank(l.m.scale)<=2) cls+=" lab-minor";
    t.setAttribute("class",cls);
    t.textContent=l.text;
    frag.appendChild(t);
  }
  g.appendChild(frag);
}

const SCALE_COLOR={XL:"#3da9fc",L:"#54c6a0",M:"#c2b45a",S:"#8b7fd4",R:"#6b7684"};

/* ============================================================
   航线：大圆 + 日界线复制 + 按 route id 的进入/退出动画
   ============================================================ */
