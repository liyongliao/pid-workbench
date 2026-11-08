const auditView={q:'',offset:0,ticket:0};
function logValue(v){
 if(v===null||v===undefined)return '无记录 / 未设置';
 if('targets' in v){
  const code=id=>S.catalog.find(d=>d.id===id)?.code||id;
  return ['目标：'+((v.targets||[]).map(code).join('、')||'无'),'默认：'+(v.preferredTarget?code(v.preferredTarget):'无'),v.note?'备注：'+v.note:''].filter(Boolean).join('；');
 }
 return [v.label||'',v.value===''?'（空值）':v.value,'visible' in v?(v.visible?'图面显示':'图面隐藏'):'',v.visible&&'x' in v?'位置 '+v.x+' / '+v.y+'，字高 '+v.height:''].filter(x=>x!==undefined&&x!=='').join(' · ');
}
function renderChangeLog(){
 const el=$('#managementContent');if(!el)return;
 el.innerHTML='<div class="admin-card"><h3>修改日志</h3><p class="muted">暂存和正式发布分别记录；共享管理员账号按请求来源区分。历史记录没有来源地址时不作推断。</p><label class="admin-field">搜索图号、句柄、字段或操作<input id="auditQuery" placeholder="例如：块属性、图号或位号"></label><div id="auditRows" aria-live="polite"></div></div>';
 const input=$('#auditQuery');input.value=auditView.q;input.oninput=()=>{auditView.q=input.value.trim();auditView.offset=0;loadChangeLog()};loadChangeLog();
}
async function loadChangeLog(){
 const el=$('#auditRows'),ticket=++auditView.ticket;if(!el)return;
 try{const d=await api('/api/admin/change-log?'+new URLSearchParams({q:auditView.q,offset:auditView.offset}));if(!el.isConnected||ticket!==auditView.ticket)return;
 el.innerHTML=d.records.map(r=>`<article class="audit-event"><b>${esc(r.type)} · ${esc(r.code||'图纸库')}</b><small>${esc(r.time)} · ${esc(r.actor)}${r.handle?' · 句柄 '+esc(r.handle):''}</small>${r.description?'<p>'+esc(r.description)+'</p>':''}${r.changes.length?`<details><summary>查看变更（${r.changes.length}）</summary>${r.changes.map(c=>`<div class="audit-change"><strong>${esc(c.field)}</strong><span>修改前：${esc(logValue(c.before))}</span><span>修改后：${esc(logValue(c.after))}</span></div>`).join('')}</details>`:''}${r.drawing&&S.catalog.some(x=>x.id===r.drawing)?`<button data-open="${esc(r.drawing)}" data-handle="${esc(r.handle)}">查看位置 ↗</button>`:''}</article>`).join('')||'<p class="empty">没有符合条件的修改记录</p>';
 el.insertAdjacentHTML('beforeend',`<div class="audit-pages"><button id="auditPrev" ${auditView.offset===0?'disabled':''}>上一页</button><span>共 ${d.total} 条</span><button id="auditNext" ${auditView.offset+50>=d.total?'disabled':''}>下一页</button></div>`);
 $('#auditPrev').onclick=()=>{auditView.offset=Math.max(0,auditView.offset-50);loadChangeLog()};$('#auditNext').onclick=()=>{auditView.offset+=50;loadChangeLog()};
 }catch(e){if(el.isConnected&&ticket===auditView.ticket)el.textContent=e.message}
}
