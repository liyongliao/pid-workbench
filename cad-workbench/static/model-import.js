export function setupImport({request,getJSON,notify,button,node,showDialog,dirty}){
 const trigger=document.getElementById('importModel'),key='pid.model.import';
 let pending='',timer,autoOpen=false;
 try{pending=localStorage.getItem(key)||''}catch{}
 function remember(id){pending=id;try{if(id)localStorage.setItem(key,id);else localStorage.removeItem(key)}catch{}}
 function monitor(){
  clearTimeout(timer);
  const id=pending;
  if(!id)return;
  getJSON('/api/admin/nwd-import?id='+encodeURIComponent(id)).then(job=>{
   if(id!==pending)return;
   if(job.status==='complete'){
    trigger.textContent='打开已导入的模型…';
    const open=()=>{
     if(dirty()&&!confirm('打开新模型将离开当前修改，继续？'))return;
     remember('');location.assign('/nwd.html?model='+encodeURIComponent(job.model))
    };
    if(autoOpen&&!dirty()&&!document.hidden&&!document.querySelector('dialog[open]')){open();return}
    const box=node('div');box.append(node('p',job.name+' 已可浏览、审查和发布。'),button('打开模型',open,'primary'),button('继续导入',choose));
    trigger.onclick=()=>showDialog('模型已入库',box);notify(job.name+' 已入库，可从「更多」打开');return
   }
   if(job.status==='failed'){remember('');trigger.textContent='导入模型…';trigger.onclick=choose;notify(job.message,true);return}
   if(autoOpen){notify(job.message,job.status!=='waiting');if(job.status==='waiting')autoOpen=false}
   trigger.textContent=job.status==='waiting'?'模型等待转换…':'查看导入进度…';
   trigger.onclick=()=>{const box=node('div');box.append(node('p',job.name),node('p',job.message),button('导入其他模型',choose));showDialog('模型导入',box)};
   timer=setTimeout(monitor,job.status==='waiting'?10000:1500)
  }).catch(e=>{if(id===pending){notify(e.message);timer=setTimeout(monitor,10000)}})
 }
 function choose(){
  const picker=node('input');picker.type='file';picker.accept='.nwd,.glb';
  const box=node('div');box.append(node('p','选择 NWD 源文件，导入完成后将打开审查。也支持静态 GLB，最大 2 GB。'),picker);
  showDialog('导入模型',box,async()=>{
   const file=picker.files[0];if(!file){notify('请选择模型文件');return}
   if(file.size>2*1024**3){notify('文件超过 2 GB');return}
   const token=(await getJSON('/api/admin/state')).token;
   trigger.disabled=true;notify('正在上传 '+file.name,true);
   try{
    const res=await request('/api/admin/nwd-import?name='+encodeURIComponent(file.name),{method:'POST',headers:{'Content-Type':'application/octet-stream','X-Management-Token':token},body:file});
    const job=await res.json();autoOpen=true;remember(job.id);notify(job.message);monitor()
   }finally{trigger.disabled=false}
  },'上传')
 }
 trigger.hidden=false;trigger.onclick=choose;monitor()
}
