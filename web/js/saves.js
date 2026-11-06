/* 存档面板：保存、载入、删除、退出与重启 */
function renderSavesOp(){
  const token=++SAVES_SEQ;
  const p=STATE.player;
  const defaultName=`${p.name} · 第 ${STATE.tick.day} 天`;
  $("#opbody").innerHTML=`
    <div class="opcard">
      <h4>保存当前对局 <span>第 ${STATE.tick.day} 天 · ${escHTML(p.name)}</span></h4>
      <div class="savenew">
        <input id="save_name" type="text" maxlength="40" value="${escHTML(defaultName)}" autocomplete="off">
        <button class="primary" id="save_go">保存</button>
      </div>
      <div class="savehint">完整保存玩家、AI、航线、机队、现金与随机数状态到本地 <code>saves/</code> 目录。</div>
    </div>
    <div class="opcard">
      <h4>自动存档 / 运行控制 <span>后端定时 + 退出/重启前强制保存</span></h4>
      <div class="savehint">下次启动默认自动恢复 autosave；退出或重启会再保存一次。</div>
      <div class="btnrow">
        <button class="danger" id="quit_go">保存并退出</button>
        <button id="restart_go">保存并重启</button>
        <span class="hintline">重启时页面会等待后端恢复</span>
      </div>
    </div>
    <div class="sectionline"><span>已有存档</span><span id="save_count">…</span></div>
    <div class="savelist" id="savelist"><div class="empty">正在读取存档…</div></div>`;

  $("#save_go").onclick=async()=>{
    const name=$("#save_name").value.trim();
    const btn=$("#save_go"); btn.disabled=true;
    const res=await api("/api/save",{name});
    if(res.ok){ toast("存档已保存"); await renderSavesOp(); }
    else btn.disabled=false;
  };

  $("#quit_go").onclick=async()=>{
    if(!confirm("自动保存并退出？后端会停止，可以关闭浏览器；下次双击 start.cmd 会自动恢复。")) return;
    const btn=$("#quit_go"); btn.disabled=true;
    const sleep=ms=>new Promise(r=>setTimeout(r,ms));
    // 这里不要依赖 JSON 回包：后端会在回包后主动停服，网络层可能先断开。
    try{
      await fetch("/api/quit",{method:"POST",headers:{"Content-Type":"application/json"},
        body:"{}",cache:"no-store"});
    }catch(e){}
    await sleep(700);
    let down=false;
    for(let i=0;i<20;i++){
      try{
        const r=await fetch("/api/health",{cache:"no-store"});
        if(!r.ok){ down=true; break; }
      }catch(e){ down=true; break; }
      await sleep(400);
    }
    if(!down){
      btn.disabled=false;
      toast("后端仍在运行，请稍后重试或关闭后端窗口",true);
      return;
    }
    $("#optitle").textContent="已安全退出";
    $("#opbody").innerHTML=`
      <div class="marketbox">
        <div class="sectionline"><span>已保存并退出</span><span>Autosave OK</span></div>
        <div class="savehint">后端已经停止，现在可以关闭浏览器。下次双击桌面「航空模拟」会自动恢复这次自动存档。</div>
      </div>`;
  };

  $("#restart_go").onclick=async()=>{
    if(!confirm("自动保存并重启后端？页面会自动等待后端恢复（约数秒）。")) return;
    const btn=$("#restart_go"); btn.disabled=true;
    const sleep=ms=>new Promise(r=>setTimeout(r,ms));
    try{
      await fetch("/api/restart",{method:"POST",headers:{"Content-Type":"application/json"},
        body:"{}",cache:"no-store"});
    }catch(e){ /* 回包可能被停服截断，继续看健康状态 */ }
    $("#optitle").textContent="正在重启后端";
    $("#opbody").innerHTML=`
      <div class="marketbox">
        <div class="sectionline"><span>保存并重启</span><span>请稍候</span></div>
        <div class="savehint">后端正在停止并重新拉起，完成后页面会自动刷新并恢复自动存档。</div>
      </div>`;
    await sleep(800);
    let sawDown=false;
    for(let i=0;i<24;i++){
      try{
        const r=await fetch("/api/health",{cache:"no-store"});
        if(!r.ok){ sawDown=true; break; }
      }catch(e){ sawDown=true; break; }
      await sleep(250);
    }
    if(!sawDown){
      btn.disabled=false;
      $("#opbody").innerHTML='<div class="empty">没有检测到后端停止，重启请求可能失败。请查看后端窗口。</div>';
      return;
    }
    for(let i=0;i<60;i++){
      try{
        const r=await fetch("/api/health",{cache:"no-store"});
        if(r.ok){ location.reload(); return; }
      }catch(e){}
      await sleep(500);
    }
    $("#opbody").innerHTML='<div class="empty">重启超时。请查看后端窗口，或手动重新运行 start.cmd。</div>';
  };

  api("/api/saves").then(data=>{
    if(token!==SAVES_SEQ||OP.mode!=="saves") return;
    const saves=(data&&data.saves)||[];
    $("#save_count").textContent=saves.length;
    const list=$("#savelist");
    if(!saves.length){
      list.innerHTML='<div class="empty">还没有存档。填好名称后点「保存」。</div>';
      return;
    }
    list.innerHTML=saves.map(s=>`
      <div class="saveitem">
        <div class="sname"><b>${escHTML(s.name||"未命名存档")}${s.auto?' <span class="tag">自动</span>':""}</b>
          <div class="ssub">第 ${s.day} 天 · ${escHTML(s.player||"—")} · ${escHTML((s.saved_at||"").replace("T"," ").slice(0,16))}</div>
        </div>
        <div class="sstat">现金 ¥${Number(s.cash||0).toFixed(0)}M<br>${s.routes} 航线 · ${s.fleet} 机 · ${s.ai} AI</div>
        <div class="sact">
          <button data-load="${escHTML(s.id)}">载入</button>
          <button class="danger" data-del="${escHTML(s.id)}">删除</button>
        </div>
      </div>`).join("");
    list.querySelectorAll("[data-load]").forEach(b=>{
      b.onclick=async()=>{
        const s=saves.find(x=>x.id===b.dataset.load);
        if(!s) return;
        if(!confirm(`载入「${s.name}」？当前未保存的进度会丢失。`)) return;
        const res=await api("/api/load",{id:s.id});
        if(res.ok){
          SEEN_SETTLE=null;
          closeOp(); sel=[]; expandedCity=null; closeWizard();
          await refresh(); toast(`已载入第 ${res.save.day} 天存档`);
        }
      };
    });
    list.querySelectorAll("[data-del]").forEach(b=>{
      b.onclick=async()=>{
        const s=saves.find(x=>x.id===b.dataset.del);
        if(!s||!confirm(`删除存档「${s.name}」？`)) return;
        const res=await api("/api/delete_save",{id:s.id});
        if(res.ok){ toast("存档已删除"); renderSavesOp(); }
      };
    });
  }).catch(()=>{
    if(token===SAVES_SEQ&&OP.mode==="saves")
      $("#savelist").innerHTML='<div class="empty">读取存档列表失败，请检查后端。</div>';
  });
}

/* ---------- 模式 / 目标（FR-1101 / FR-1102 / FR-1103） ---------- */
