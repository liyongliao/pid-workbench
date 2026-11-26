const SheetAI = (() => {
 const base='/api/admin/sheet-ai', names={queued:'排队中',running:'生成中',review:'待审核',published:'已上线',rejected:'已退回',archived:'历史版本',superseded:'旧草稿',baseline:'沿用原自动模型',failed:'生成失败',deferred:'暂缓建模'};
 let timer, sequence=0;
 const here=()=>S.tab==='management'&&M.tab==='sheetAi'&&S.editing;
 const post=(action,data)=>adminPost(base+'/'+action,data);
 async function open(){
  const request=++sequence;clearTimeout(timer);
  const host=$('#managementContent');
  try{
   const state=await api(base);
   if(request!==sequence||!here()||!host.isConnected)return;
   const allowed=S.catalog.filter(d=>S.role==='admin'||S.auth.teams.includes(d.team));
   host.innerHTML=`<section class="admin-card ai-batch"><h3>逐张交给 Agent 建模</h3>
    <p>选择图纸后，把任务复制到 PID 项目中的 Agent 会话。模型经对照原图审核后上线。</p>
    <label>筛选图纸<input id="aiFilter" type="search" placeholder="图号、平台或名称"></label>
    <label>图纸<select id="agentDrawing"></select></label>
    <label>建模任务<textarea id="agentBrief" rows="5" readonly></textarea></label>
    <button class="solid-button" id="copyAgentBrief" disabled>复制本图建模任务</button></section>
    <section class="admin-card"><h3>生成与审核记录</h3><div id="aiRecords" aria-live="polite"></div></section>`;
   const picker=$('#agentDrawing'),brief=$('#agentBrief'),copy=$('#copyAgentBrief');
   let revisionRequest=0;
   async function showBrief(){
    const ticket=++revisionRequest,id=picker.value;
    copy.disabled=true;brief.value='';
    if(!id)return;
    try{
     const drawing=await api('/api/drawing/'+encodeURIComponent(id));
     if(ticket!==revisionRequest||!host.isConnected||request!==sequence)return;
     if(!drawing.drawingDigest)throw Error('图纸缺少版本校验信息');
     const rejected=state.jobs.find(r=>r.drawing===id&&r.digest===drawing.drawingDigest&&['rejected','published'].includes(r.state));
     brief.value=[
      '在 PID 项目中，逐张为 '+drawing.code+'《'+drawing.title+'》建模装配。',
      '图纸 ID '+id+'，源图校验值 SHA-256 '+drawing.drawingDigest+'。',
      '先查看对应版本的 CAD 原图、设备表和已有三维资料，按位号核对设备、管口及管线去向。',
      '以项目已审核的装配为对照，按图建立设备外形、支撑、阀组和配管。标明推定尺寸、布置和原图疑点。',
      '实际渲染并检查图纸与模型的构件联动，提交待审核草稿，由人工决定上线。',
      rejected?.state==='rejected'&&rejected.message?'上次退回意见：'+rejected.message:''
     ].filter(Boolean).join('\n');
     copy.disabled=false
    }catch(error){if(ticket===revisionRequest&&host.isConnected)brief.value=error.message}
   }
   function filter(){
    const q=$('#aiFilter').value.trim().toLowerCase(),last=picker.value||S.drawing?.id;
    const options=allowed.filter(d=>[d.code,d.platform,d.title].join(' ').toLowerCase().includes(q));
    picker.replaceChildren(...options.map(d=>new Option(d.code+' · '+d.title,d.id)));
    if(options.some(d=>d.id===last))picker.value=last;
    if(!options.length)picker.append(new Option('没有匹配的图纸',''));
    showBrief()
   }
   picker.onchange=showBrief;$('#aiFilter').oninput=filter;filter();
   copy.onclick=async()=>{
    try{await navigator.clipboard.writeText(brief.value);toast('已复制本图建模任务')}
    catch{brief.focus();brief.select();toast(document.execCommand('copy')?'已复制本图建模任务':'任务文本已选中，可手动复制')}
   };
   const catalog=new Map(allowed.map(d=>[d.id,d]));
   function records(rows){
    $('#aiRecords').innerHTML=rows.map(r=>{
     const d=catalog.get(r.drawing);
     return `<article class="occurrence"><div><b>${esc(d?.code||r.drawing)} · ${esc(names[r.state])}</b>
      <p>${esc(d?.title||'')} · #${r.id} · ${esc(r.model)} · 提交 ${esc(r.actor)}</p>
      <small>${esc(r.message||'')}${r.reviewer?' · 审核 '+esc(r.reviewer):''}</small></div>
      ${r.state==='review'?`<div><button data-preview="${r.id}">对照原图审核</button><button data-reject="${r.id}">退回</button></div>`:''}</article>`
    }).join('')||'<p>尚无生成记录。</p>';
   }
   async function refresh(){
    clearTimeout(timer);
    if(!host.isConnected||!here()||request!==sequence)return;
    try{const fresh=await api(base);if(host.isConnected&&here()&&request===sequence){state.jobs=fresh.jobs;records(fresh.jobs)}}
    catch(error){if(host.isConnected)toast(error.message)}
    if(host.isConnected&&here()&&request===sequence)timer=setTimeout(refresh,5000)
   }
   $('#aiRecords').onclick=async e=>{
    const b=e.target.closest('button');if(!b)return;b.disabled=true;
    try{
     if(b.dataset.reject){if(await decide(+b.dataset.reject,'reject'))await refresh();return}
     const draft=await api(base+'?preview='+encodeURIComponent(b.dataset.preview));
     if(!here())return;
     await loadDrawing(draft.drawing);Linked.previewModel(draft)
    }catch(err){toast(err.message)}finally{b.disabled=false}
   };
   records(state.jobs);timer=setTimeout(refresh,5000)
  }catch(err){if(request===sequence&&host.isConnected)host.textContent=err.message}
 }
 async function decide(id,decision){
  let note='';
  if(decision==='reject'){
   note=prompt('退回原因（选填，同版重新生成时保留意见）','');if(note===null)return false
  }
  await post('review',{id,decision,note});toast(decision==='approve'?'审核通过，模型已上线':'草稿已退回');return true
 }
 async function finish(decision){
  const draft=Linked.draft();if(!draft)return;
  try{if(await decide(draft.id,decision)&&Linked.draft()===draft)await loadDrawing(draft.drawing,null,false)}
  catch(err){toast(err.message)}
 }
 $('#sheetApprove').onclick=()=>finish('approve');
 $('#sheetReject').onclick=()=>finish('reject');
 $('#sheetBack').onclick=async()=>{const draft=Linked.draft();if(draft)await loadDrawing(draft.drawing,null,false);M.tab='sheetAi';setTab('management')};
 return {open}
})();
