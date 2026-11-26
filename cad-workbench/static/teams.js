const teamNames=['工艺','动力','机械','电气'];
document.getElementById('teamFilter').onchange=event=>{
 S.team=event.target.value;
 document.querySelector('[data-tab="logic"]').hidden=!S.capabilities?.enabled.logic||!!S.team&&S.team!=='工艺';
 if((S.tab==='drawings'&&S.team&&S.drawing?.team!==S.team)||(S.tab==='logic'&&S.team&&S.team!=='工艺')){
  setTab('equipment');return search();
 }
 if(S.query) search();
 else {updateList();if(S.tab==='equipment')renderEquipment();}
};
async function releaseManager(){
 const releases=await api('/api/admin/releases'),health=await api('/api/health');
 $('#dialog').close();
 modal('图纸修订',releases.map(r=>{
  const names=r.drawings.map(id=>S.catalog.find(d=>d.id===id)?.code||id).join('、');
  return `<article class="admin-card"><b>${esc(names)}</b><p>${esc(r.created)} · ${esc(r.actor)}</p>${r.kind==='upload'?'首次入库':`<button data-restore="${esc(r.id)}">恢复这批图纸到修改前</button>`}</article>`;
 }).join('')||'<p>暂无已发布的新修订。</p>');
 for(const b of $$('[data-restore]'))b.onclick=async()=>{
  if(!confirm('确认将所列图纸恢复到这次修改前，并生成新修订？'))return;
  try{await managementState();const job=await adminPost('/api/admin/rollback',{release:b.dataset.restore,generation:health.generation});$('#dialog').close();toast('恢复任务已提交');watchRestore(job.id);}catch(e){toast(e.message);}
 };
}

async function watchRestore(id){
 try{
  const job=await api('/api/admin/job?id='+encodeURIComponent(id));
  if(job.status==='complete'){await afterPublication();toast('图纸修订已恢复');}
  else if(job.status==='failed')toast(job.message);
  else setTimeout(()=>watchRestore(id),1200);
 }catch(e){toast(e.message);}
}
