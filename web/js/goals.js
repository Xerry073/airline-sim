/* 目标模式：模式选择、四目标进度、A–E 结算 */
async function startNewGame(mode,skipConfirm){
  if(mode!=="sandbox"&&mode!=="goals") return;
  const routes=((STATE.player&&STATE.player.routes)||[]).length;
  const fleet=((STATE.player&&STATE.player.fleet)||[]).length;
  const progressed=STATE.tick.day>0||routes>0||fleet>1;
  if(progressed&&!skipConfirm&&!confirm("开始新对局会把当前进度重置为第 0 天，确定继续？")) return;
  const res=await api("/api/new_game",{mode});
  if(!res.ok) return;
  SEEN_SETTLE=null;
  sel=[]; stopover=null; expandedCity=null; closeWizard();
  closeOp();
  await refresh();
  toast(mode==="goals"?"目标模式已开始：10 年内追踪四个目标":"沙盒模式已开始");
  if(mode==="goals") setTimeout(()=>openOp("goals"),150);
}

function renderGoalsOp(){
  const g=STATE.goals;
  if(!g){
    $("#opbody").innerHTML='<div class="empty">后端版本过旧，缺少模式/目标数据，请重启后端。</div>';
    return;
  }
  if(g.setup_required){
    const progressed=STATE.tick.day>0
      ||((STATE.player&&STATE.player.routes)||[]).length>0;
    $("#opbody").innerHTML=`
      <div class="marketbox">
        <div class="sectionline"><span>开局模式</span><span>第 ${STATE.tick.day} 天</span></div>
        <div class="hintline">${progressed?"开始新对局会重置当前进度。":"选择模式后开始；目标模式会从第 0 天起追踪四个目标。"}</div>
      </div>
      <div class="goalgrid">
        <div class="modecard sel">
          <div class="goalname">沙盒模式</div>
          <div class="goalcond">无终点，随时存档退出；不追踪目标，不做 A–E 结算。</div>
        </div>
        <div class="modecard">
          <div class="goalname">目标模式</div>
          <div class="goalcond">10 游戏年内同时追踪四个目标；到期或全部达成时暂停并结算 A–E；未达成不计分。</div>
        </div>
      </div>
      <div class="btnrow">
        <button class="primary" id="start_sandbox">开始沙盒模式</button>
        <button id="start_goals">开始目标模式</button>
      </div>`;
    $("#start_sandbox").onclick=()=>startNewGame("sandbox");
    $("#start_goals").onclick=()=>startNewGame("goals");
    return;
  }

  if(g.mode==="sandbox"){
    $("#opbody").innerHTML=`
      <div class="marketbox">
        <div class="sectionline"><span>当前：沙盒模式</span><span>无终点</span></div>
        <div class="hintline">沙盒模式不追踪 FR-1102 的四个目标，也没有 A–E 结算；可随时存档退出。</div>
      </div>
      <div class="opcard">
        <h4>开始目标模式 <span>会重置为第 0 天</span></h4>
        <div class="savehint">目标模式固定同时追踪四个目标：市值进前三、区域霸主、高质高效、网络扩张。</div>
        <div class="btnrow"><button class="primary" id="switch_goals">选择目标模式</button></div>
      </div>`;
    $("#switch_goals").onclick=()=>startNewGame("goals");
    return;
  }

  const s=g.settlement;
  const settled=g.settled;
  const rating=settled?(s.failed?"失败":(s.scored?s.rating:`${s.rating}（未达成）`)):"—";
  const achieved=g.achieved_count||0;
  const cards=(g.progress||[]).map(p=>{
    const d=p.detail||{};
    let line="";
    if(p.id==="market_top3"){
      line=`当前排名 #${d.current_rank||"—"} · 最佳 #${d.best_rank||"—"}`;
    }else if(p.id==="region_leader"){
      line=`最佳 ${d.region_name||"—"} ${(Number(d.best_share||0)*100).toFixed(1)}% · 当前 ${(Number(d.current_share||0)*100).toFixed(1)}%`;
    }else if(p.id==="high_quality"){
      line=`连续 ${d.streak||0}/${d.months_required||24} 个月 · 最佳 ${d.best_streak||0}`;
    }else{
      line=`当前 ${d.segments||0} 段 · 客座率 ${(Number(d.avg_lf||0)*100).toFixed(1)}% · 最佳 ${d.best_segments||0} 段`;
    }
    return `<div class="goalcard ${p.achieved?"done":""}">
      <div class="goalhead"><span class="goalname">${escHTML(p.name)}</span>
        <span class="goalstatus ${p.achieved?"done":""}">${p.achieved?"已达成":"进行中"}</span></div>
      <div class="goalcond">${escHTML(p.condition)}</div>
      <div class="goaldetail">${line}${p.achieved&&p.day?` · 第 ${p.day} 天达成`:""}</div>
    </div>`;
  }).join("");
  const settleBox=settled?`
    <div class="marketbox">
      <div class="sectionline"><span>结算结果</span><span>第 ${s.day} 天</span></div>
      <div class="mgrid">
        <span>评级 <b>${rating}</b></span>
        <span>达成 <b>${achieved} / 4</b></span>
        <span>计分 <b>${s.scored?"是":"否（未达成）"}</b></span>
        <span>原因 <b>${escHTML(s.reason||"")}</b></span>
      </div>
      <div class="hintline">${s.failed?"公司破产，目标模式失败。":"目标模式已结算；可重新开局或切换模式。"}</div>
    </div>`:"";
  $("#opbody").innerHTML=`
    <div class="marketbox">
      <div class="sectionline"><span>目标模式 · 10 游戏年</span><span>第 ${STATE.tick.day} 天 / 期限第 ${g.deadline_day} 天</span></div>
      <div class="dashstats" style="margin-bottom:0">
        <div class="dashstat"><div class="l">已达成</div><div class="v">${achieved} / 4</div></div>
        <div class="dashstat"><div class="l">评级</div><div class="v">${settled?rating:"—"}</div></div>
        <div class="dashstat"><div class="l">剩余</div><div class="v">${g.years_left} 年</div></div>
        <div class="dashstat"><div class="l">剩余天数</div><div class="v">${g.days_left}</div></div>
      </div>
      <div class="hintline">四个目标同时追踪；到期或四个全部达成时暂停并结算。区域份额按航线客流在航段端点所在区域均摊。</div>
    </div>
    ${settleBox}
    <div class="goalgrid" style="margin-top:8px">${cards}</div>
    <div class="btnrow" style="margin-top:10px">
      <button id="restart_goals">重新开始目标模式</button>
      <button class="danger" id="switch_sandbox">切换到沙盒模式</button>
      <span class="hintline">重新开局会重置当前进度</span>
    </div>`;
  $("#restart_goals").onclick=()=>startNewGame("goals");
  $("#switch_sandbox").onclick=()=>startNewGame("sandbox");
}

