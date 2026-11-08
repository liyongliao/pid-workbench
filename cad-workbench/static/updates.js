// Only a small revision token is polled. Drawing bodies use authenticated HTTP revalidation.
const libraryUpdates={version:null,busy:null};
async function refreshLibrary(force=false){
 if(libraryUpdates.busy){await libraryUpdates.busy;if(force)return refreshLibrary(true);return}
 libraryUpdates.busy=(async()=>{
  const {version}=await api('/api/library-version');
  if(!force&&version===libraryUpdates.version)return;
  const catalog=await api('/api/catalog');S.catalog=catalog;renderPlatforms();
  if(S.query)await search();else updateList();
  const current=S.drawing?.id,sequence=S.loadVersion;
  if(current){
   const updated=await api('/api/drawing/'+current);
   if(current===S.drawing?.id&&sequence===S.loadVersion){
    const handle=S.selected?.handle;S.drawing=updated;S.selected=null;
    await loadSvg(sequence,true);
    if(current===S.drawing?.id&&sequence===S.loadVersion){
     if(handle&&updated.items.some(i=>i.handle===handle))await selectItem(handle);else renderDrawingInfo();
     if(S.tab==='drawings')$('#drawingTitle').textContent=updated.title;
    }
   }
  }
  if(S.tab==='equipment'&&!S.query)renderEquipment();
  if(S.tab==='management'&&M.tab==='attributes')await renderAttributeManager();
  libraryUpdates.version=version;
 })();try{await libraryUpdates.busy}finally{libraryUpdates.busy=null}
}
function listenForUpdates(){
 const check=()=>{if(!document.hidden&&!$('#dialog').open&&S.auth)refreshLibrary().catch(()=>{})};
 window.addEventListener('focus',check);document.addEventListener('visibilitychange',check);
 window.addEventListener('storage',e=>{if(e.key==='pid-published')check()});setInterval(check,30000);
}
async function afterPublication(){await refreshLibrary(true);try{localStorage.setItem('pid-published',String(Date.now()))}catch{}}
