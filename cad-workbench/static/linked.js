// Both viewports resolve selections by drawing ID and CAD handle, or by a versioned model object.
const Linked=(()=>{
 const el=id=>document.getElementById(id);
 let capabilities=null,ViewClass=null,modelEnabled=false;
 let render,draw,source='sheet',models=[],objects=new Map(),outlines=new Map(),paths=new Map(),selectedSheet=null;
 let links={},manual={},currentModel=null,pending=null,sequence=0,detailSeq=0,searchSeq=0,mode='split';
 let authored=false,assembly=null,preview=null,compare=false,reviewCamera=null;
 let regionRequest,area=null,areaMode=false;
 let drawingMarkers=[],loadAbort,detailAbort;
 const loaded=new Map();
 function html(value){return String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
 function info(){return models.find(m=>m.id===source)}
 function route(endpoint,params={}){return '/api/models/'+endpoint+'?'+new URLSearchParams({model:source,...params})}
 function notice(msg){el('modelEmpty').textContent=msg;el('modelEmpty').hidden=!msg}
 function mount(View){
  ViewClass=View;if(!modelAllowed())return;
  if(render)return;
  try{render=new View(el('modelSurface'),id=>source==='sheet'?selectItem(id,true):choose(Number(id),true),()=>{});if(draw)showSource()}
  catch{notice('当前浏览器无法启用 WebGL 三维显示。可通过本图对象和模型搜索查询属性。')}
 }
 function bind(data,svg){
  const changed=draw!==data;draw=data;paths=new Map();
  for(const p of svg.querySelectorAll('[data-handle]')){
   if(!paths.has(p.dataset.handle))paths.set(p.dataset.handle,[]);
   paths.get(p.dataset.handle).push(p)
  }
  if(changed){
   const tag=globalThis.PidProject?.vessels?.[data.code];
   const recipe=preview?.recipe||data.sheetModel;
   assembly=!compare&&recipe?.version===3?recipe.assembly:null;
   authored=!!globalThis.PidProject?.loadAssembly && (!!assembly || !!tag && data.items.some(i=>i.tag===tag));
   const basis=el('modelBasis');
   basis.querySelector('section')?.remove();
   const lines=globalThis.PidProject?.notes?.[data.code];
   if(lines?.length){
    const section=document.createElement('section');
    lines.forEach((line,i)=>{const part=document.createElement(i?'p':'b');part.textContent=line;section.append(part)});
    basis.append(section)
   }
   el('modelSource').querySelector('[value=sheet]').textContent=preview?'待审核模型':recipe?'已发布模型':authored?'手工精细模型':'按本图生成';
   objects=PidScene.assemble(data,paths,S.sheetFrame||data.viewBox,compare||authored?null:recipe);outlines=new Map();
   for(const o of objects.values())for(const h of o.outline||[])outlines.set(h,o.handle)
  }
  const hit=document.createDocumentFragment();
  for(const o of objects.values()){
   if(o.kind!=='管线')continue;
   for(const path of paths.get(o.handle)||[]){
    if(path.tagName.toLowerCase()!=='path')continue;
    const target=document.createElementNS('http://www.w3.org/2000/svg','path');
    target.setAttribute('d',path.getAttribute('d'));target.dataset.handle=o.handle;
    target.setAttribute('fill','none');target.setAttribute('stroke','transparent');target.setAttribute('stroke-width','6');
    target.setAttribute('vector-effect','non-scaling-stroke');target.setAttribute('pointer-events','stroke');hit.append(target)
   }
  }
  el('hitAreas').prepend(hit);
  configure(capabilities);
  list();if(changed){pending=null;selectedSheet=null;currentModel=null;el('modelTag').hidden=true;links={};manual={};
   source=sheetAllowed()?'sheet':models.find(m=>m.platform===draw.platform)?.id||'';
   showSource()
  }else if(source==='sheet'&&render){select(S.selected)}
 }
 function list(){
  const host=el('objectGroups');if(el('objectTree').hidden)return;
  const q=el('objectQuery').value.trim().toUpperCase();
  const groups=new Map();
  for(const o of objects.values()){
   if(o.annotation)continue;
   if(q&&![o.label,o.handle,o.description].some(s=>String(s).toUpperCase().includes(q)))continue;
   if(!groups.has(o.kind))groups.set(o.kind,[]);groups.get(o.kind).push(o)
  }
  const fragment=document.createDocumentFragment();
  for(const [kind,items] of groups){const details=document.createElement('details');details.open=true;
   const title=document.createElement('summary');title.textContent=kind+' · '+items.length;details.append(title);
   for(const o of items){const b=document.createElement('button');b.className='object-row';b.dataset.cad=o.handle;b.title=o.description+' · '+o.handle;b.textContent=o.label;b.classList.toggle('active',o.handle===selectedSheet);details.append(b)}fragment.append(details)
  }
  if(!groups.size)fragment.append('未找到匹配对象');host.replaceChildren(fragment)
 }
 function tree(on){
  el('libraryTree').hidden=on;el('objectTree').hidden=!on;el('treeDrawings').setAttribute('aria-pressed',!on);el('treeObjects').setAttribute('aria-pressed',on);if(on)list()
 }
 el('treeObjects').onclick=()=>{if(draw){setTab('drawings');tree(true)}};
 el('treeDrawings').onclick=()=>tree(false);
 el('objectQuery').oninput=list;
 el('objectGroups').onclick=e=>{const b=e.target.closest('[data-cad]');if(b)selectItem(b.dataset.cad,true)};
 function layout(newMode){
  if(newMode!=='drawing'&&!modelAllowed())newMode='drawing';
  mode=newMode;el('linkedViews').dataset.layout=mode;
  document.querySelectorAll('button[data-layout]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.layout===mode)));
  requestAnimationFrame(()=>{resizeView();render?.invalidate()})
 }
 document.querySelectorAll('button[data-layout]').forEach(b=>b.onclick=()=>layout(b.dataset.layout));
 el('modelReset').onclick=()=>{endRegion();if(render){render.disposeChildren(render.region);render.reset()}label('')};
 el('modelFocus').onclick=()=>render?.focus();
 function label(text){el('modelTag').textContent=text;el('modelTag').hidden=!text}
 function selCAD(item){
  for(const p of drawingMarkers)p.classList.remove('linked-highlight');
  drawingMarkers=item?[...(paths.get(item.handle)||[])]:[];
  for(const p of drawingMarkers)p.classList.add('linked-highlight');
  selectedSheet=item?.handle||null;
  for(const b of el('objectGroups').querySelectorAll('.active'))b.classList.remove('active');
  if(item)el('objectGroups').querySelector('[data-cad="'+CSS.escape(item.handle)+'"]')?.classList.add('active')
 }
 let fromModel=false;
 function select(item){
  selCAD(item);
  if(!draw)return;
  if(!source||source==='sheet'){
   const o=objects.get(item?.handle),shown=render?.highlight(item?.handle);
   el('modelFocus').disabled=!shown;
   if(authored){label(item?((item.tag||o?.label||item.name)+' · '+(shown?'对应装配构件':'仅图纸标注')):'');return}
   for(const h of new Set([...(o?.run||[]),...(o?.linked||[])].flatMap(h=>[h,...(objects.get(h)?.outline||[])]).concat(o?.outline||[],o?.tap?[o.tap.other,...(o.tap.evidence||[])]:[])))for(const p of paths.get(h)||[]){p.classList.add('linked-highlight');drawingMarkers.push(p)}
   const names=o?.lineTags?.join(' / ');
   label(o?[names||o.label,o.blockSource||(shown?'对应本图构件':'暂无唯一对应管段')].join(' · '):item?'此图元仅在图纸中显示':'');return
  }
  if(fromModel)return;
  if(item&&links[item.handle]){if(currentModel!==links[item.handle])choose(links[item.handle],false);else bindButton(item);return}
  currentModel=null;++detailSeq;detailAbort?.abort();render?.clearDetail();el('modelFocus').disabled=true;
  label(item?(draw.platform===info()?.platform?'此图元尚未关联模型':draw.platform+' 图纸 · '+info()?.name+' 独立浏览'):'');
  if(item&&S.editing&&draw.platform===info()?.platform)bindButton(item)
 }
 function bindButton(item){
  if(!S.editing||draw.platform!==info()?.platform)return;
  const host=el('inspectorBody');if(host.querySelector('[data-bind-model]'))return;
  const b=document.createElement('button');b.className='solid-button';b.dataset.bindModel='';b.textContent='选择模型构件并关联';
  b.onclick=()=>{pending={id:draw.id,handle:item.handle,model:source};label('请在模型或模型搜索中选择要关联的构件')};host.prepend(b);
  if(manual[item.handle]!=null){
   const reset=document.createElement('button');reset.textContent='恢复自动模型关联';reset.onclick=async()=>{
    if(!confirm('移除此图元的手动模型关联并恢复自动匹配？'))return;
    try{await managementState();await adminPost('/api/admin/model-link',{drawing:draw.id,handle:item.handle,model:source,digest:info().digest,object:null,prior:manual[item.handle]});await showSource();await selectItem(item.handle);toast('已恢复自动模型关联')}catch(e){toast(e.message)}
   };b.after(reset)
  }
 }
 async function loadRegion(){
  if(!area||!render)return;
  const target=area;regionRequest?.abort();regionRequest=new AbortController();
  try{
   const response=await fetch(route('nearby',{point:target.point.join(','),start:target.next}),{signal:regionRequest.signal});
   if(!response.ok)throw Error('局部几何加载失败');
   const buf=await response.arrayBuffer();if(area!==target)return;
   const n=new DataView(buf).getUint32(0,true),data=JSON.parse(new TextDecoder().decode(new Uint8Array(buf,4,n)));
   render.mesh(buf,4+n,data.kinds,null,render.region);target.next=data.next;el('modelMore').hidden=!data.more;
   label('局部精查 · 已载入 '+data.next+' 个源片段')
  }catch(e){if(e.name!=='AbortError')label(e.message)}
 }
 function endRegion(){
  regionRequest?.abort();area=null;areaMode=false;if(render)render.regionPick=null;
  el('modelInspect').setAttribute('aria-pressed','false');el('modelMore').hidden=true
 }
 el('modelMore').onclick=loadRegion;
 el('modelInspect').onclick=()=>{
  endRegion();if(!render)return;areaMode=true;el('modelInspect').setAttribute('aria-pressed','true');label('点击模型表面，查看该位置附近的原始构件');
  render.regionPick=point=>{endRegion();area={point:point.map(v=>Number(v.toFixed(3))),next:0};render.regionView(point);loadRegion()}
 };
 el('processOnly').onclick=()=>{
  const b=el('processOnly'),on=b.getAttribute('aria-pressed')!=='true';b.setAttribute('aria-pressed',on);render?.processOnly(on)
 };
 el('sheetView').onchange=e=>render?.reset(Number(e.target.value));
 function loading(){el('sheetView').hidden=true;compare=false;reviewCamera=null;preview=null;el('sheetReview').hidden=true;el('modelBasis').hidden=true;el('modelBasis').open=false;endRegion();++sequence;++detailSeq;loadAbort?.abort();detailAbort?.abort();draw=null;links={};paths.clear();objects.clear();outlines.clear();selectedSheet=null;pending=null;currentModel=null;render?.clear();label('');notice('正在载入当前图纸…')}
 async function showSource(){
  endRegion();el('processOnly').setAttribute('aria-pressed','false');const seq=++sequence;++detailSeq;++searchSeq;loadAbort?.abort();detailAbort?.abort();loadAbort=new AbortController();
  const signal=loadAbort.signal;
  if(!source)source='sheet';el('modelSource').value=source;
  el('sheetView').hidden=true;
  const physical=source!=='sheet';el('sheetReview').hidden=physical||!preview;el('sheetApprove').disabled=true;el('sheetChanges').hidden=true;el('modelInspect').hidden=!physical;el('processOnly').hidden=!physical;document.querySelector('.model-searchbox').hidden=!physical;
  el('modelResults').hidden=true;el('modelQuery').value='';el('modelKind').value='';pending=null;
  el('modelFocus').disabled=true;label('');render?.clear();currentModel=null;links={};manual={};
  el('modelBasis').hidden=physical||!draw||!authored;el('modelBasis').open=false;
  if(!draw||!modelAllowed()||source==='sheet'&&!sheetAllowed())return;
  const state=document.querySelector('.link-state');
  const shared=!physical||info()?.platform===draw.platform;
  state.classList.toggle('independent',!shared);
  state.lastChild.textContent=physical?(shared?' 同平台联动':' 跨平台浏览'):authored?' 精细模型联动':' 本图示意联动';
  if(!physical){
   el('modelSourceNote').textContent=compare?'对照 · 原自动模型':assembly?'原图参数化装配 · 布置与标高推定':preview?'待人工审核 · 尺寸与标高为示意':draw.sheetModel?'AI 已审核上线 · 尺寸与标高为示意':authored?'按原图建模 · 撬内布置推定':'按本图生成 · 高度与尺寸为示意';
   notice('正在组装本图构件…');
   try{
    const visible=authored?await render?.authoredSheet(draw,assembly):await render?.schematic([...objects.values()]);if(seq!==sequence)return;
    if(visible&&render?.sheet?.views){
     const menu=el('sheetView');
     menu.replaceChildren(...render.sheet.views.map((v,i)=>new Option(v.title,String(i))));menu.hidden=false
    }
    if(preview&&visible){
     if(reviewCamera){
      render.camera.position.copy(reviewCamera.position);render.control.target.copy(reviewCamera.target);render.control.update();render.invalidate();reviewCamera=null
     }
     const changes=assembly?draw.items.filter(i=>render.sheet.pieces.has(i.handle)).map(i=>({handle:i.handle,label:i.tag||i.texts?.[0]||i.block||i.name})):[...objects.values()].filter(o=>o.enhanced&&render.sheet?.pieces.get(o.handle)?.length);
     const visibleParts=changes.length,menu=el('sheetChanges');menu.hidden=!visibleParts;
     menu.replaceChildren(new Option('定位图纸构件…',''),...changes.map(o=>new Option(o.label+' · '+o.handle,o.handle)));
     el('sheetApprove').disabled=compare||!visibleParts;
     el('sheetReviewInfo').textContent=compare?'原自动模型':assembly?'装配草稿 #'+preview.id+' · '+visibleParts+' 个可定位图元':authored?'本图已有手工精细模型':'草稿 #'+preview.id+' · '+visibleParts+' 个可见增强构件';
    }
    notice(!render?'浏览器未启用 WebGL':visible?'':(/目录|位号表/.test(draw.title)||draw.texts.some(t=>/FLOWLINE AND INSTRUMENT SCHEDULE/i.test(t.text))?'本页为目录或明细表，可在左侧浏览原图':'本页未识别到可生成三维的管段或构件'));select(S.selected)
   }catch{if(seq===sequence)notice('三维图未能生成，可继续浏览原图')}
   return
  }
  const m=info();if(!m)return;
  el('modelSourceNote').textContent=m.name+'工程模型 · '+(draw.platform===m.platform?'分级概览':draw.platform+' 图纸未配对');
  notice('载入'+m.name+'工程概览…');
  try{
   const get=async(path,json)=>{const r=await fetch(path,{signal});if(!r.ok)throw Error('模型资源读取失败');return json?r.json():r.arrayBuffer()};
   const url=ep=>route(ep,{v:m.digest});
   const [data,mapping]=await Promise.all([
    loaded.has(m.id)?loaded.get(m.id):Promise.all([get(url('overview'),false),get(url('palette'),true)]),
    get(route('links',{drawing:draw.id}),true)]);
   if(seq!==sequence)return;loaded.set(m.id,data);links=mapping.links;manual=mapping.manual;
   render?.overview(...data,m);notice(render?'':'浏览器未启用 WebGL，可搜索模型构件');
   select(S.selected)
  }catch(err){if(seq===sequence)notice('模型加载失败，可重新选择模型重试')}
 }
 el('modelSource').onchange=()=>{source=el('modelSource').value;showSource()};
 async function inventory(){
  const menu=el('modelSource');
  try{
   models=await api('/api/models');
   menu.querySelectorAll('optgroup').forEach(g=>g.remove());
   const group=document.createElement('optgroup');group.label='工程构件索引';
   for(const m of models)group.append(new Option(m.name+'构件索引',m.id));
   if(models.length)menu.append(group);
   configure(capabilities);if(draw&&!sheetAllowed()){source=models.find(m=>m.platform===draw.platform)?.id||'';showSource()}
  }catch{menu.title="工程构件索引暂不可用"}
 }
 async function choose(id,picked){
  if(!info())return;
  const seq=++detailSeq;detailAbort?.abort();detailAbort=new AbortController();
  const signal=detailAbort.signal;
  try{
   const obj=await api(route('object',{object:id}));if(seq!==detailSeq)return;
   currentModel=id;render?.clearDetail();el('modelFocus').disabled=true;
   label(obj.name+' · '+obj.kind);el('modelResults').hidden=true;
   if(picked&&pending){
    const p=pending;pending=null;
    if(p.id===draw.id&&p.model===source&&confirm('将图元 '+p.handle+' 关联到 '+info().name+' 的 '+obj.name+'？')){
     await managementState();
     await adminPost('/api/admin/model-link',{drawing:draw.id,handle:p.handle,model:source,digest:info().digest,object:id,prior:manual[p.handle]??null});
     if(seq!==detailSeq)return;links[p.handle]=id;manual[p.handle]=id;obj.drawings.push({drawing:draw.id,handle:p.handle,code:draw.code,title:draw.title});toast('模型关联已保存')
    }
   }
   if(picked){
    const same=obj.drawings.filter(r=>r.drawing===draw.id);
    if(same.length===1){fromModel=true;try{selectItem(same[0].handle,true)}finally{fromModel=false}}
    else if(obj.drawings.length===1){const r=obj.drawings[0];await loadDrawing(r.drawing,r.handle);return}
    else{resetBlockPanel();fromModel=true;try{S.selected=null;renderSelection()}finally{fromModel=false}
     openInspector();el('inspectorHeading').textContent='模型构件';el('inspectorBody').innerHTML='<div class="model-kind">'+html(info().name)+' / '+html(obj.kind)+'</div><div class="model-name">'+html(obj.name)+'</div><dl class="detail-table">'+row('原始模型',info().source)+row('源片段',String(obj.count))+row('首个源片段 ID',obj.sourceId)+row('构件索引',source.toUpperCase()+' · '+obj.id)+'</dl><div class="section-title">关联图元</div>'+(obj.drawings.length?obj.drawings.map(r=>'<button class="link-card" data-open="'+html(r.drawing)+'" data-handle="'+html(r.handle)+'">'+html(r.code)+' · '+html(r.handle)+'</button>').join(''):'<p class="muted">当前图库尚无已核对的对应图元。</p>');
     el('locate').disabled=true;el('editBlockAttributes').hidden=true;el('editSelectedLink').hidden=true
    }
   }else if(S.selected)bindButton(S.selected);
   let start=0;
   while(start<obj.count){
    const r=await fetch(route('detail',{object:id,start,v:info().digest}),{signal});
    if(!r.ok)throw Error('构件几何读取失败');
    const buffer=await r.arrayBuffer();if(seq!==detailSeq)return;
    const end=new DataView(buffer).getUint32(0,true);if(end<=start)throw Error('构件分页异常');
    render?.mesh(buffer,4,{},id);start=end
   }
   if(seq===detailSeq){el('modelFocus').disabled=false;if(picked==='search'||!picked)render?.focus()}
  }catch(e){if(seq===detailSeq)label(e.message)}
 }
 async function searchModel(offset=0){
  const seq=++searchSeq;const host=el('modelResults');host.hidden=false;
  try{const d=await api(route('objects',{q:el('modelQuery').value.trim(),kind:el('modelKind').value,offset}));if(seq!==searchSeq)return;
   host.innerHTML=d.rows.map(o=>'<button data-model-object="'+o.id+'"><small>'+html(o.kind)+'</small><span>'+html(o.name)+'</span></button>').join('')||'<p>无匹配构件</p>';
   if(offset||d.more)host.insertAdjacentHTML('beforeend','<div class="model-paging">'+(offset?'<button data-offset="'+(offset-50)+'">上一页</button>':'')+(d.more?'<button data-offset="'+(offset+50)+'">下一页</button>':'')+'</div>')
  }catch(e){if(seq===searchSeq)host.textContent=e.message}
 }
 let timer;el('modelQuery').onfocus=()=>searchModel();el('modelQuery').oninput=()=>{++searchSeq;clearTimeout(timer);timer=setTimeout(()=>searchModel(),150)};
 el('modelKind').onchange=()=>searchModel();el('modelResults').onclick=e=>{const b=e.target.closest('button');if(b?.dataset.modelObject)choose(+b.dataset.modelObject,'search');else if(b?.dataset.offset)searchModel(+b.dataset.offset)};
 document.addEventListener('pointerdown',e=>{if(!e.target.closest('.model-searchbox,#modelResults'))el('modelResults').hidden=true});
 el('modelQuery').onkeydown=e=>{if(e.key==='Escape')el('modelResults').hidden=true};
 document.addEventListener('DOMContentLoaded',inventory);
 el('sheetChanges').onchange=async e=>{
  const h=e.target.value;if(h&&preview&&!compare){await selectItem(h);if(selectedSheet===h)render?.focus()}
 };
 el('sheetCompare').onclick=()=>{
  if(!preview||!draw||!render)return;
  reviewCamera=preview.recipe?.assembly?null:{position:render.camera.position.clone(),target:render.control.target.clone()};
  compare=!compare;el('sheetCompare').textContent=compare?'返回增强模型':'查看原自动模型';
  const data=draw;draw=null;renderHitAreas();bind(data,el('scene').querySelector('svg'))
 };
 function previewModel(draft){
  if(!draw||draw.id!==draft.drawing||draw.drawingDigest!==draft.digest)throw Error('图纸版本已变化，请重新打开草稿');
  preview=draft;compare=false;el('sheetCompare').textContent='查看原自动模型';const data=draw;draw=null;el('sheetReviewInfo').textContent='正在组装草稿…';
  renderHitAreas();bind(data,el('scene').querySelector('svg'));layout('split')
 }
 function sheetAllowed(){return !!capabilities&&(capabilities.enabled.schematic||capabilities.enabled.drawings&&capabilities.modelPolicy!=='off'&&(!!draw?.sheetModel||authored))}
 function modelAllowed(){return !!capabilities&&capabilities.enabled.drawings&&(sheetAllowed()||capabilities.linkedModels&&models.some(m=>m.platform===draw?.platform))}
 function configure(next){
  if(!next)return;
  const load=next.linkedModels&&!capabilities?.linkedModels;capabilities=next;
  const on=modelAllowed(),wasEnabled=modelEnabled;modelEnabled=on;el('modelPane').hidden=!on;document.querySelector('.view-toolbar').hidden=!on;
  el('modelSource').querySelector('[value=sheet]').hidden=!sheetAllowed();
  if(!on)layout('drawing');else if(!wasEnabled&&mode==='drawing')layout('split');
  if(on&&ViewClass&&!render)mount(ViewClass);
  if(load)inventory();
 }
 return {configure,mount,bind,select,loading,previewModel,draft:()=>preview,directory:()=>tree(false),object:h=>objects.get(h),owner:h=>source==='sheet'&&!(authored&&render?.sheet?.byId.has(h))?(outlines.get(h)||h):h}
})();
