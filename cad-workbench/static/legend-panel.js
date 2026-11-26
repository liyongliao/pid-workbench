const LegendPanel=(()=>{
 const base='/project-legends/';
 const books={old:'旧 ASME 图例',new:'新项目图例 REV0',manual:'人工汉化 PDF'};
 const pageTitles={
  old:['编号、介质与管道等级','设备符号','仪表工艺连接'],
  new:['管线编号与材料等级','阀门、管件及设备','仪表符号与识别字母','仪表典型连接'],
  manual:['管线、设备及缩写','阀门、管件及设备','仪表与逻辑符号','仪表工艺连接']
 };
 const groups=[
  ['旧 ASME · 阀门型式','valves'],['旧 ASME · 端部连接','ends'],['旧 ASME · 特殊型式','special'],
  ['旧 ASME · 管道等级','classes'],['旧 ASME · 介质','service'],['旧 ASME · 系统','systems'],['旧 ASME · 绝热','insulation'],
  ['新项目 · 介质','newService'],['新项目 · 系统','newSystems'],['新项目 · 压力等级','ratings'],['新项目 · 材料','materials'],
  ['新项目 · 裕量','allowance'],['新项目 · 特殊要求','requirements'],['新项目 · 绝热与伴热','newInsulation'],
  ['人工汉化版 · 材料及明细','manualMaterials'],['人工汉化版 · 特殊要求','manualRequirements'],
  ['人工汉化版 · 压力等级','manualRatings'],['人工汉化版 · 介质','manualService'],['人工汉化版 · 系统','manualSystems'],
  ['设备符号','equipmentSymbols'],['仪表及连接','connections'],['阀门功能位号','functions'],['中英文阀门符号','symbols']
 ];
 let pending;
 function catalog(){
  if(!pending)pending=api(base+'catalog.json').catch(e=>{pending=null;throw e});
  return pending;
 }
 function pageLink(book,page,label){
  return '<a href="'+base+book+'.pdf#page='+page+'" target="_blank" rel="noopener">'+esc(label)+'</a>';
 }
 function symbol(type){
  if(!/^[1-7]$/.test(type||''))return '';
  return '<span class="legend-symbol legend-v'+type+'" title="人工汉化 PDF 第 2 页对应阀型示例" role="img" aria-label="阀型示例"></span>';
 }
 function result(data){
  const type=data.fields.find(f=>f.name==='阀门型式');
  return '<div class="legend-result"><div class="legend-summary"><strong>'+esc(data.title)+'</strong>'+symbol(type?.code)+'</div><dl>'+
   data.fields.map(f=>'<div><dt>'+esc(f.name)+'</dt><dd><b>'+esc(f.code)+'</b><span>'+esc(f.meaning)+'</span></dd></div>').join('')+
   '</dl>'+pageLink(data.source,data.page,books[data.source]+' · 第 '+data.page+' 张 ↗')+'</div>';
 }
 async function detail(host,choice){
  if(!host||!choice)return;
  host.innerHTML='<div class="legend-heading"><h3>图例释义</h3><button type="button" data-guide>查图例</button></div><div data-explanation aria-live="polite">正在读取图例…</div>';
  const body=host.querySelector('[data-explanation]');
  host.querySelector('button').onclick=()=>open(choice.tags.length===1?choice.tags[0]:'');
  try{
   const c=await catalog();
   if(!host.isConnected)return;
   if(choice.tags.length!==1){
    body.textContent=choice.tags.length?'此管段关联多个编号，请点击图上的具体管线标注：'+choice.tags.join('、'):'该图元没有关联到唯一编号，可点击附近的管线编号或查阅图例。';
    return;
   }
   const raw=choice.tags[0], decoded=PidLegend.decode(raw,c);
   body.innerHTML=decoded?result(decoded):'<p>'+esc(raw)+' 未匹配已核对的编号格式，可按图形或原页查阅。</p>';
  }catch{body.textContent='图例资料暂未载入，可通过“查图例”重试。'}
 }
 function glossary(c,q){
  const norm=q.toUpperCase();let matches=0;
  const html=groups.map(([name,key])=>{
   const entries=Object.entries(c[key]).filter(([code,label])=>!q||[code,label,name].some(v=>v.toUpperCase().includes(norm)));
   matches+=entries.length;
   if(!entries.length)return '';
   return '<details'+(q?' open':'')+'><summary>'+esc(name)+' <small>'+entries.length+'</small></summary><dl>'+
    entries.map(([code,label])=>'<div><dt>'+esc(code)+'</dt><dd>'+esc(label)+(key==='valves'?symbol(code):'')+'</dd></div>').join('')+'</dl></details>';
  }).join('');
  return matches?html:'<p>没有找到对应条目，可打开图例原页核对。</p>';
 }
 function sources(c){
  return Object.entries(pageTitles).map(([key,titles])=>'<section><h3>'+books[key]+'</h3><div class="legend-pages">'+titles.map((v,i)=>pageLink(key,i+1,(i+1)+' · '+v+' ↗')).join('')+'</div></section>').join('')+
   '<section><h3>汉化对照记录</h3>'+c.checks.map(([topic,notes])=>'<p><strong>'+esc(topic)+'</strong><br>'+esc(notes)+'</p>').join('')+'</section>';
 }
 async function open(initial=''){
  modal('P&ID 图例','<div id="legendGuide" class="legend-guide"><div class="legend-nav" aria-label="图例分类"><button data-mode="lookup" aria-pressed="true">编号与符号</button><button data-mode="source" aria-pressed="false">原页与校核</button></div><label><span class="legend-search-label">查编号、代码或中文名称</span><input type="search" placeholder="输入所选编号，或搜索“球阀”“消防水”"></label><div data-body aria-live="polite">正在读取图例…</div></div>');
  const guide=$('#legendGuide'),input=guide.querySelector('input'),body=guide.querySelector('[data-body]');
  input.value=initial;
  try{
   const c=await catalog();if(!guide.isConnected)return;
   let mode='lookup';
   function draw(){
    const q=input.value.trim(),decoded=q&&PidLegend.decode(q,c);
    body.innerHTML=mode==='source'?sources(c):decoded?result(decoded):glossary(c,q);
   }
   for(const b of guide.querySelectorAll('[data-mode]'))b.onclick=()=>{
    mode=b.dataset.mode;guide.querySelector('label').hidden=mode!=='lookup';
    guide.querySelectorAll('[data-mode]').forEach(btn=>btn.setAttribute('aria-pressed',String(btn===b)));draw();
   };
   input.oninput=draw;draw();if(!initial)input.focus();
  }catch{body.textContent='图例资料未载入。';const retry=document.createElement('button');retry.textContent='重新载入';retry.onclick=()=>open(initial);body.append(retry)}
 }
 return {open,detail};
})();
