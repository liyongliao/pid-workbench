import {cachedAsset,initAssetCache} from './asset-cache.js';
import {NwdRenderer} from './nwd-render.js';
import {openPlatform} from './platform-scene.js';
import {createTour} from './tour.js';
import {Matrix4} from 'three';

const $=id=>document.getElementById(id);
const params=new URLSearchParams(location.search),model=params.get('model')||'l',rev=params.get('rev')||'latest',embed=params.get('embed')==='1';
let twinMode=location.pathname==='/twin.html'||params.get('workspace')==='twin',tour,environment='overview';
const title={tour:'巡航路线',views:'视图',tree:'模型浏览器',props:'构件特性',settings:'显示设置',notes:'批注'};
let tree,children,index,info,viewer,scene,revision,admin=false,managementToken,panel='views',selected=-1,isolate=-1,mode='orbit',activeView='',dirty=false,publishing=false,baseline='';
let floating=false,query='',treeQuery='',point=null,measureStart=null,measurement=null,noticeTimer,limit=80,edits=[],redos=[];
let lastTreeClick=null,remoteRemoved=[],remoteRevision=0;
const removedNodes=()=>remoteRemoved.length?[...new Set([...scene.removed,...remoteRemoved])]:scene.removed;
let reviewAuthor='',reviewLogin='',namedEditor=false,savingEntry=false;
const canContribute=()=>namedEditor&&!embed&&!twinMode&&rev==='latest';
const entryIdentity=()=>({author:reviewAuthor,id:Array.from(crypto.getRandomValues(new Uint8Array(16)),v=>v.toString(16).padStart(2,'0')).join('')});
const authorOf=entry=>entry.author||'历史记录 · 作者未记录';
const editable=()=>admin&&!twinMode;
const publicationKey='pid.model.published.'+model;
const expanded=new Set([0,1]),limits=new Map();
const labels=$('labels'),stage=$('stage');
if(embed)document.body.classList.add('embed');
document.body.classList.toggle('overview-mode',twinMode&&!embed);
$('overviewLink').href='/twin.html?model='+encodeURIComponent(model);
function node(tag,text,cls){const el=document.createElement(tag);if(text!=null)el.textContent=text;if(cls)el.className=cls;return el}
function button(label,fn,cls,tip){const b=node('button',label,cls);b.type='button';if(tip)b.title=tip;b.onclick=fn;return b}
function notify(message,stay=false){clearTimeout(noticeTimer);$('status').textContent=message;$('status').hidden=false;if(!stay)noticeTimer=setTimeout(()=>$('status').hidden=true,3200)}
async function request(url,options){
 const r=await (url.includes('/api/nwd/asset?')?cachedAsset(url,options):fetch(url,options));
 if(r.status===401){location.replace('/login?next='+encodeURIComponent(location.pathname+location.search));throw Error('请先登录')}
 if(!r.ok){const e=await r.json().catch(()=>({}));throw Error(e.error||'读取失败（'+r.status+'）')}return r
}
const endpoint=path=>'/api/nwd/'+path+'?model='+encodeURIComponent(model);
const getJSON=async url=>(await request(url)).json();
const asset=async (id,signal)=>(await request(endpoint('asset')+'&id='+id,{signal})).arrayBuffer();
function revisionLabel(){const b=$('publish');$('revision').textContent=(revision?'已发布 v'+revision:'源模型')+(dirty?(admin?' · 有未发布修改':' · 临时显示'):'');b.hidden=embed||twinMode;b.disabled=!editable()||!viewer||publishing;
 b.textContent=publishing?'发布中…':'保存并发布';b.title=rev!=='latest'?'历史版本只读':admin?'保存审查修改，更新数字孪生':'管理员可保存并发布模型'}
// These two supplier assemblies contain complete alternatives for one physical crane each.
let craneAssemblies=[],showCranePoses=false,suppressedPoses=[];
function findCraneAssemblies(){
 const groups=[];
 for(const [tag,suffix] of globalThis.PidProject?.cranes?.[model] || []){
  const root=tree.findIndex(n=>n[2]==='/('+tag+')');if(root<0)continue;
  const nodes=children.get(root)||[],preferred=nodes.find(id=>tree[id][2]==='/'+tag+suffix);
  if(preferred===undefined)continue;
  const poses=nodes.filter(id=>id===preferred||tree[id][2].startsWith('/EAB-'+tag.slice(0,-1))||
   (tree[id][2].startsWith('EQUIPMENT ')&&tree[id][2].endsWith(' of ZONE /('+tag+')')));
  if(poses.length>1)groups.push({preferred,poses})
 }
 return groups
}
function displayHidden(){
 suppressedPoses=[];
 if(!showCranePoses)for(const {preferred,poses} of craneAssemblies){
  const chosen=poses.find(id=>below(selected,id))??preferred;
  suppressedPoses.push(...poses.filter(id=>id!==chosen))
 }
 return [...scene.hidden,...suppressedPoses]
}
function nodeName(id){return scene.names?.[id]||tree[id][2]}
function filterScene(){
 if(selected>=0&&ancestor(selected,removedNodes())>=0){selected=-1;point=null}
 if(isolate>=0&&ancestor(isolate,removedNodes())>=0)isolate=-1;
 const focus=isolate>=0?isolate:!twinMode&&!embed?selected:-1;
 viewer.filter(displayHidden(),removedNodes(),focus,selected);
 $('selection').hidden=selected<0;
 if(selected>=0)$('selectionName').textContent=nodeName(selected);
 $('deleteSelection').hidden=!editable();
 $('selectionContext').hidden=focus<0;
 $('selectionContext').setAttribute('aria-pressed',String(viewer.context))
}
function update(){filterScene();viewer.section(scene.section);drawLabels();revisionLabel();componentCard()}
function markDirty(){dirty=JSON.stringify(scene)!==baseline;revisionLabel()}
function change(fn){edits.push(structuredClone(scene));if(edits.length>40)edits.shift();redos=[];fn();markDirty();update();renderPanel()}
function undo(again=false){const from=again?redos:edits,to=again?edits:redos;if(!from.length)return;to.push(structuredClone(scene));scene=from.pop();markDirty();update();renderPanel()}
function ancestor(id,list){for(let i=id;i>=0;i=tree[i][0])if(list.includes(i))return i;return -1}
function below(id,parent){return parent>=0&&id>=parent&&id<=tree[parent][1]}
function fitIsolation(id){
 const plane=viewer.presetPlane,bounds=tree[id]?.[4];
 if(twinMode&&plane&&bounds&&plane.normal.y*(plane.normal.y>0?bounds[4]:bounds[1])+plane.constant<0){
  environment='all';viewer.platformEnvironment(environment);$('preset').value=environment
 }
 viewer.fit(id)
}
function select(id,p=null){
 const follow=isolate>=0&&id!==isolate;
 if(follow)isolate=id;
 selected=id;point=p;
 filterScene();if(follow&&id>=0)fitIsolation(id);renderPanel();componentCard()
}
function componentCard(){
 const card=$('componentCard');card.hidden=!(twinMode&&!embed&&selected>=0);
 if(card.hidden)return;
 const host=$('componentBody'),item=tree[selected];
 host.replaceChildren(node('strong',nodeName(selected)),node('p',item[0]>=0?nodeName(item[0]):info.name));
 const status=ancestor(selected,[...scene.hidden,...scene.removed,...suppressedPoses])>=0?'隐藏':'可见';
 host.append(node('small',info.name+' · '+(item[3]||'构件')+' · '+status),button('定位到构件',()=>viewer.fit(selected),'wide'))
}
function outsidePath(id,root=0){
 const siblings=[];
 for(let child=id;child!==root;child=tree[child][0]){
  for(const other of children.get(tree[child][0]))if(other!==child)siblings.push(other)
 }
 return siblings
}
function effectiveHidden(){
 return [...new Set([...scene.hidden,...(isolate>=0?outsidePath(isolate):[])])]
}
function toggleHidden(id){
 const a=ancestor(id,scene.hidden);
 change(()=>{
  // Revealing a child of a hidden group keeps the other branches hidden.
  scene.hidden=scene.hidden.filter(n=>n!==a&&!below(n,id));
  if(a<0)scene.hidden.push(id);
  else if(a!==id)scene.hidden.push(...outsidePath(id,a))
 })
}
function removeNode(id){
 if(!editable()||id<0||ancestor(id,removedNodes())>=0)return;
 const message=node('p','删除「'+nodeName(id)+'」'+(children.has(id)?'及其下属构件':'')+'？保存并发布后，审查和数字孪生都将移除该构件。');
 showDialog('删除构件',message,()=>{
  if(!editable()||ancestor(id,removedNodes())>=0)return;
  change(()=>{scene.removed=scene.removed.filter(n=>!below(n,id));scene.removed.push(id)});
  notify('已删除构件，可撤销。保存并发布后同步到数字孪生。')
 },'删除构件')
}
function field(label,el){const l=node('label',null,'field');l.append(node('span',label),el);return l}
function showDialog(heading,content,onOK,label='确定'){
 const d=$('dialog');$('dialogTitle').textContent=heading;$('dialogBody').replaceChildren(content);$('confirm').textContent=label;$('confirm').hidden=!onOK;
 d.onclose=()=>{if(d.returnValue==='ok'&&onOK)Promise.resolve().then(onOK).catch(e=>notify(e.message,true))};d.returnValue='';if(!d.open)d.showModal()
}
function inputDialog(heading,action,max=120){
 const input=node('input');input.maxLength=max;input.placeholder='输入'+heading;showDialog(heading,input,()=>{if(input.value.trim())return action(input.value.trim())});input.focus()
}
function applyCamera(saved){
 environment=saved.environment||'all';
 viewer.platformEnvironment?.(environment);
 viewer.setCamera(saved.camera);
 if(viewer.native)$('preset').value=saved.environment||'all'
}
async function changeEntry(kind,action,entry){
 if(canContribute()){
  if(savingEntry)throw Error('正在保存上一条记录，请稍后再试');
  savingEntry=true;
  try{
   if(!managementToken)managementToken=(await getJSON('/api/admin/state')).token;
   const response=await request('/api/admin/nwd-entry',{method:'POST',headers:{'Content-Type':'application/json','X-Management-Token':managementToken},
    body:JSON.stringify({model,base:revision,digest:index.digest,kind,action,id:entry.id,entry})});
   const saved=await response.json(),base=JSON.parse(baseline);
   scene[kind]=saved.entries;base[kind]=saved.entries;baseline=JSON.stringify(base);revision=saved.revision;
   try{localStorage.setItem(publicationKey,JSON.stringify([index.digest,revision]))}catch{}
   markDirty();update();renderPanel();notify(action==='add'?'已保存':'已删除')
  }finally{savingEntry=false}
 }else change(()=>{
  if(action==='add')scene[kind].push(entry);
  else{const i=scene[kind].findIndex(v=>v===entry||(entry.id&&v.id===entry.id));if(i>=0)scene[kind].splice(i,1)}
 })
}
function addView(){inputDialog('视图名称',async name=>{
 const entry={...entryIdentity(),name,camera:viewer.cameraState(),environment:viewer.light?.preset||environment,
  hidden:!twinMode&&selected>=0?[...scene.hidden]:effectiveHidden(),section:structuredClone(scene.section||null),
  ...(!twinMode&&selected>=0?{focus:selected,context:viewer.context}:{})};
 await changeEntry('views','add',entry);activeView='custom-'+scene.views.findIndex(v=>v.id===entry.id);renderPanel()
})}
function copy(text){
 if(navigator.clipboard?.writeText)return navigator.clipboard.writeText(text).then(()=>notify('已复制')).catch(()=>fallback());
 function fallback(){const el=node('textarea');el.value=text;$('dialogBody').append(el);el.select();const ok=document.execCommand('copy');if(ok){el.remove();notify('已复制')}else notify('请选中文字复制')}
 fallback()
}
function share(){
 const div=node('div');
 for(const [name,fixed] of [['始终查看最新版',false],['固定当前版本',true]]){
  if(fixed&&!revision)continue;
  const url=new URL(twinMode?'/twin.html':'/nwd.html',location.origin);url.searchParams.set('model',model);if(fixed)url.searchParams.set('rev',revision);
  if(!twinMode){
   url.searchParams.set('tree',index.tree);
   if(selected>=0){url.searchParams.set('node',selected);url.searchParams.set('context',viewer.context?'1':'0')}
   const c=viewer.cameraState();
   url.hash=new URLSearchParams({camera:[...c.eye,...c.target,...c.up,c.fov].map(n=>Number(n.toFixed(6))).join(',')}).toString()
  }
  div.append(node('p',name,'bucket'));const link=node('input');link.value=url.href;link.readOnly=true;div.append(link,button('复制链接',()=>copy(link.value),'wide'));
  url.searchParams.set('embed','1');const iframe=document.createElement('iframe');iframe.src=url.href;iframe.title=info.name+'模型';iframe.width='100%';iframe.height='560';iframe.loading='lazy';iframe.allowFullscreen=true;div.append(button('复制网页嵌入代码',()=>copy(iframe.outerHTML),'wide'))
 }
 if(dirty)div.prepend(node('p','当前修改在发布后生效。','help'));showDialog('分享模型',div)
}
const iconPaths={
 home:'M3 10 12 3l9 7M6 9v11h5v-6h3v6h4V9',
 fit:'M3 9V4h5m8 0h5v5m0 6v5h-5m-8 0H3v-5M8 12h8m-4-4v8',
 pan:'M8 13V6a1.5 1.5 0 0 1 3 0v5-7a1.5 1.5 0 0 1 3 0v7-5a1.5 1.5 0 0 1 3 0v6-3a1.5 1.5 0 0 1 3 0v5c0 5-2 7-6 7h-1c-2 0-3-1-5-3l-4-5q-1-3 2-2l2 2',
 zoom:'M16 16l5 5M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0',
 orbit:'M20 9a9 9 0 0 0-16-2m0-4v4h4M4 15a9 9 0 0 0 16 2m0 4v-4h-4M9 11l3-2 3 2v3l-3 2-3-2z',
 walk:'M15 4a1.5 1.5 0 1 0-3 0 1.5 1.5 0 0 0 3 0M7 12l3-4 3-1 3 5h3M12 9l-2 6 4 3 1 4M10 15l-2 4-3 2',
 measure:'M3 15 16 2l6 6L9 21zM13 5l3 3m-6 0 2 2m-5 1 3 3',
 cut:'M4 8l8-5 8 5v9l-8 5-8-5zM4 8l8 5 8-5m-8 5v9M2 15l20-7',
 explode:'M3 7l9-5 9 5-9 5zM3 12l9 5 9-5M3 17l9 5 9-5',
 mark:'M4 20l1-5L16 4l4 4L9 19zM14 6l4 4',
 views:'M3 5h18v14H3zM3 9h18',tree:'M9 3h6v5H9zM4 16h6v5H4zm10 0h6v5h-6zM12 8v4m-5 4v-4h10v4',
 props:'M5 3h14v18H5zM9 8h6m-6 4h6m-6 4h4',settings:'M3 7h9m4 0h5M3 17h3m4 0h11M12 4v6h4V4zM6 14v6h4v-6z',
 notes:'M3 4h18v12H9l-5 4v-4H3zM7 8h10m-10 4h7',snapshot:'M3 7h4l2-3h6l2 3h4v13H3zM16 13a4 4 0 1 1-8 0 4 4 0 1 1 8 0',
 share:'M8 9H4v12h16V9h-4M12 15V2m-4 4 4-4 4 4'
};
function toolIcon(name){
 const svg=document.createElementNS('http://www.w3.org/2000/svg','svg'),path=document.createElementNS(svg.namespaceURI,'path');
 svg.setAttribute('viewBox','0 0 24 24');svg.setAttribute('class','tool-icon');svg.setAttribute('aria-hidden','true');
 path.setAttribute('d',iconPaths[name]);svg.append(path);return svg
}
function tools(){
 const items=[['home','⌂','主页',()=>{viewer.separate(0);isolate=-1;select(-1);scene.camera?applyCamera(scene):viewer.native?($('preset').value='overview',$('preset').onchange()):viewer.home(info.view);activeView='';renderPanel()}],['fit','⊡','拟合',()=>viewer.fit(selected>=0?selected:isolate)],['pan','✥','平移'],['zoom','⊕','缩放'],['orbit','⟳','环绕'],['walk','♙','漫游'],['measure','↔','测量'],['cut','◩','剖切',()=>{setPanel('settings');$('sectionAxis')?.focus()}],['explode','◇','分解',()=>{setPanel('settings');$('explode')?.focus()}],['mark','✎','标记']];
 for(const [id,icon,label,action] of items){
  if(embed&&['cut','explode','mark'].includes(id))continue;
  const b=button('',action||(()=>setMode(id)));b.dataset.tool=id;b.hidden=twinMode&&id==='mark';b.title=label;b.append(toolIcon(id),node('span',label));$('tools').append(b)
 }
 for(const b of document.querySelectorAll('#panels [data-panel],#reviewActions>button[data-panel="notes"]')){
  const key=b.dataset.panel;b.replaceChildren(toolIcon(key),node('span',title[key]))
 }
 for(const [id,label] of [['snapshot','快照'],['share','分享']])$(id).replaceChildren(toolIcon(id),node('span',label));
 setMode('orbit')
}
function setMode(next){
 mode=next;measureStart=null;viewer.modeTo(next);
 for(const b of $('tools').children)b.setAttribute('aria-pressed',String(b.dataset.tool===next));
 if(next==='measure')notify('依次点击模型表面两点，测量直线距离');
 if(next==='walk')notify('按住左键环顾，W A S D 移动，Q / E 升降');
 if(next==='mark')notify('点击模型表面放置批注')
}
function pick(id,p){
 if(id<0){if(mode==='orbit')select(-1);return}
 if(mode==='measure'){
  if(viewer.explode){notify('请先将分解距离调为零，再测量原始位置');return}
  if(!measureStart){viewer.clearMeasurement();measurement=null;measureStart=p;notify('请选择第二个测量点',true)}
  else{const d=viewer.measure(measureStart,p);measurement={point:p.map((x,i)=>(x+measureStart[i])/2),text:d.toFixed(3)+' 模型单位'};measureStart=null;notify('两点直线距离 '+measurement.text);drawLabels()}return
 }
 if(mode==='mark'){if(viewer.explode){notify('请先复原分解，再添加批注');return}inputDialog('批注内容',text=>changeEntry('notes','add',{...entryIdentity(),point:p,text}),300);return}
 if(panel==='tree'||floating){
  for(let i=tree[id][0];i>=0;i=tree[i][0])expanded.add(i)
 }
 select(id,p);
 if(panel==='tree'||floating)document.querySelector('.row.selected')?.scrollIntoView({block:'nearest'})
}
function drawLabels(){labels.replaceChildren();for(const entry of [...scene.notes,...(measurement?[measurement]:[])]){const l=node('span',entry===measurement?entry.text:entry.text+' · '+authorOf(entry));l._point=entry.point;labels.append(l)}viewer.draw()}
const cubeMatrix=new Matrix4();
function frame(camera){
 cubeMatrix.makeRotationFromQuaternion(camera.quaternion).transpose();
 const m=cubeMatrix.elements.slice();for(const i of [1,4,6,9])m[i]*=-1;$('cube').style.transform='matrix3d('+m.join(',')+')';
 for(const label of labels.children){const p=viewer.project(label._point);label.hidden=Math.abs(p.z)>1||Math.abs(p.x)>1||Math.abs(p.y)>1;if(!label.hidden){label.style.left=(p.x+1)*50+'%';label.style.top=(1-p.y)*50+'%'}}
}
function setPanel(name){
 panel=name;if(twinMode||embed||innerWidth<850)floating=false;$('treeWindow').hidden=!floating;$('side').hidden=!name;renderPanel();
 for(const b of document.querySelectorAll('[data-panel]'))b.setAttribute('aria-pressed',String(b.dataset.panel===name||(floating&&b.dataset.panel==='tree')))
}
function searchInput(value,placeholder,oninput){
 const input=node('input');input.type='search';input.value=value;input.placeholder=placeholder;input.setAttribute('aria-label',placeholder);
 input.oninput=()=>oninput(input.value);return input
}
function renderPanel(){
 if(!viewer)return;
 if(floating){const host=$('floatingTree'),pos=host.scrollTop;host.replaceChildren();treePanel(host);host.scrollTop=pos}
 if(!panel)return;
 const container=$('panel'),scroll=container.scrollTop;container.replaceChildren();$('side').querySelector('h2').textContent=title[panel];
 if(panel==='tour')tour?.edit(container);
 if(panel==='views')viewsPanel(container);
 if(panel==='tree')treePanel(container);
 if(panel==='props')propsPanel(container);
 if(panel==='settings')settingsPanel(container);
 if(panel==='notes')notesPanel(container);
 container.scrollTop=scroll
}
function viewsPanel(parent){
 const list=node('div');parent.append(searchInput(query,'搜索预设视图',s=>{query=s;fill()}));
 if(!twinMode){
  const home=button(info.name+' · 全景',()=>document.querySelector('#tools [data-tool=home]')?.click(),'view');
  home.classList.toggle('on',!activeView);parent.append(home)
 }
 if(editable()||canContribute())parent.append(button('＋ 保存当前视角',addView,'wide'));
 parent.append(list);
 function fill(){
  list.replaceChildren();
  for(const [group,items] of [['项目视图',scene.views],['NWD 预设视图',index.views]]){
   const custom=items===scene.views;if(!items.length)continue;
   const rows=items.map((p,i)=>[p,i]).filter(([p,i])=>(custom||!scene.removedViews?.includes(i))&&p.name.toLowerCase().includes(query.trim().toLowerCase()));
   list.append(node('div',group+' · '+rows.length,'bucket'));
   for(const [p,i] of rows){const key=(custom?'custom-':'source-')+i;
    const b=button(p.name,()=>{
     selected=-1;point=null;isolate=-1;
     if(custom){
      applyCamera(p);
      if(p.hidden){scene.hidden=[...p.hidden];scene.section=p.section;markDirty()}
      if(!twinMode&&Number.isInteger(p.focus)){selected=p.focus;if(embed)isolate=p.focus;viewer.context=p.context!==false}
     }else{viewer.platformEnvironment?.('all');viewer.preset(p)}
     activeView=key;update();renderPanel();if(innerWidth<760)setPanel(null)
    },'view',p.name);
    b.classList.toggle('on',key===activeView);
    const row=node('div',null,'review-entry'),details=node('div',null,'review-entry-main');
    details.append(b);if(custom)details.append(node('small',authorOf(p)));
    row.append(details);
    if(editable()||(custom&&canContribute()&&p.authorLogin===reviewLogin))row.append(button('删除',()=>showDialog('删除视角',node('p','从项目视图中删除「'+p.name+'」？'),()=>{
     activeView='';
     if(custom)return changeEntry('views','delete',p);
     change(()=>{if(!scene.removedViews?.includes(i))(scene.removedViews??=[]).push(i)})
    },'删除视角'),'entry-delete','删除视角 '+p.name));
    list.append(row)
   }
  }
 }fill()
}
function treePanel(parent){
 const bar=node('div',null,'treeActions'),list=node('div');
 parent.append(searchInput(treeQuery,'搜索名称或源节点编号',s=>{treeQuery=s;limit=80;fill()}),bar,list);
 if(editable()){
  const del=button('删除构件',()=>removeNode(selected),'delete-node',selected<0?'先选择一个构件':'删除所选构件及其子节点');
  del.disabled=selected<0;bar.append(del)
 }
 if(selected>=0&&!twinMode)bar.append(button('清除选择',()=>select(-1)));
 if(selected>=0){bar.append(button('拟合',()=>viewer.fit(selected)),button(isolate===selected?'退出隔离':'隔离',()=>{isolate=isolate===selected?-1:selected;update();if(isolate>=0)fitIsolation(isolate);renderPanel()}));

 }
 if(isolate>=0||(!twinMode&&selected>=0)){const ctx=button(viewer.context?'隐藏周围线稿':'显示周围线稿',()=>{viewer.context=!viewer.context;update();renderPanel()});bar.append(ctx)}
 if(isolate>=0&&isolate!==selected)bar.append(button('退出隔离',()=>{isolate=-1;update();renderPanel()}));
 if(scene.hidden.length)bar.append(button('全部显示',()=>change(()=>{scene.hidden=[]})));
 if(editable()&&edits.length)bar.append(button('撤销',()=>undo()));if(editable()&&redos.length)bar.append(button('重做',()=>undo(true)));
 function row(id,depth,flat=false){
  if(ancestor(id,removedNodes())>=0)return;
  const item=tree[id],group=children.has(id),r=node('div',null,'row');
  const focus=viewer.iso,other=focus>=0&&!below(id,focus)&&!below(focus,id);
  r.classList.toggle('context-row',other);r.classList.toggle('muted',ancestor(id,scene.hidden)>=0);r.classList.toggle('selected',id===selected);
  r.style.paddingLeft=Math.min(depth*12,105)+'px';
  const b=button(group?(expanded.has(id)?'▾':'▸'):'·',()=>{if(expanded.has(id))expanded.delete(id);else expanded.add(id);if(flat){treeQuery='';for(let p=item[0];p>=0;p=tree[p][0])expanded.add(p);renderPanel()}else fill()},'toggle',group?'展开 / 收起':'叶节点');b.disabled=!group;
  const label=button(nodeName(id),e=>{
   const now=performance.now(),double=e.detail>0&&lastTreeClick?.id===id&&now-lastTreeClick.time<400;
   lastTreeClick=double?null:{id,time:now};
   if(selected!==id)select(id);
   if(double)viewer.fit(id)
  },'name',nodeName(id));
  label.dataset.node=id;
  label.onkeydown=e=>{
   if(e.key.toLowerCase()==='f'){e.stopPropagation();viewer.fit(id);return}
   if(!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(e.key))return;
   e.preventDefault();const visible=[...list.querySelectorAll('[data-node]')],at=visible.indexOf(label);
   if(e.key==='ArrowDown'||e.key==='ArrowUp'){visible[at+(e.key==='ArrowDown'?1:-1)]?.focus();return}
   if(group&&!flat&&(e.key==='ArrowRight')!==expanded.has(id)){
    if(expanded.has(id))expanded.delete(id);else expanded.add(id);fill();list.querySelector('[data-node="'+id+'"]')?.focus()
   }else if(e.key==='ArrowLeft')list.querySelector('[data-node="'+item[0]+'"]')?.focus();
   else if(group)visible[at+1]?.focus()
  };const alternate=ancestor(id,suppressedPoses)>=0,hidden=ancestor(id,scene.hidden)>=0,mixed=!hidden&&scene.hidden.some(n=>below(n,id));
  const eye=button('',()=>alternate&&!hidden?select(id):toggleHidden(id),'visibility',hidden?'显示图层':alternate?'查看此吊臂姿态':'隐藏图层');
  eye.setAttribute('aria-label',(hidden?'显示 ':alternate?'查看此姿态 ':'隐藏 ')+nodeName(id));r.classList.toggle('muted',hidden||alternate);eye.dataset.state=hidden||alternate?'hidden':mixed?'mixed':'visible';
  r.append(b,label,eye);list.append(r);
  if(!flat&&group&&expanded.has(id)){
   const ids=children.get(id),n=limits.get(id)||60;
   const visible=ids.slice(0,n);const picked=selected>=0&&ids.find(child=>below(selected,child));
   if(picked&&!visible.includes(picked))visible.push(picked);for(const child of visible)row(child,depth+1);
   if(n<ids.length)list.append(button('展开更多子节点（'+(ids.length-n)+'）',()=>{limits.set(id,n+100);fill()},'wide'))
  }
 }
 function fill(){
  list.replaceChildren();const term=treeQuery.trim().toLowerCase();
  if(term){let count=0;for(let i=0;i<tree.length;i++){if(!nodeName(i).toLowerCase().includes(term)&&!tree[i][2].toLowerCase().includes(term)&&String(i)!==term)continue;if(ancestor(i,removedNodes())>=0)continue;if(++count<=limit)row(i,0,true)}
   list.prepend(node('div',count+' 个匹配节点','searchCount'));if(count>limit)list.append(button('加载更多',()=>{limit+=80;fill()},'wide'))
  }else row(0,0);
  if(editable()&&scene.removed.length){list.append(node('div','已删除 · '+scene.removed.length,'bucket'));for(const id of scene.removed)list.append(button('恢复　'+nodeName(id),()=>change(()=>{scene.removed=scene.removed.filter(n=>n!==id)}),'wide'))}
 }fill()
}
function propsPanel(p){
 if(selected<0){p.append(node('p','点击模型表面或在模型浏览器中选择一个构件。','empty'));return}
 const id=selected,r=tree[id],dl=node('dl'),keys=[];for(let i=id;i>=0;i=tree[i][0])keys.unshift(nodeName(i));
 const fields=[['名称',nodeName(id)],['源节点',id],['类型',r[3]||'模型'],['所属层级',keys.join(' / ')],['下级节点',r[1]-id]];
 if(r[4])fields.push(['包围盒尺寸（模型单位）',[0,1,2].map(k=>(r[4][k+3]-r[4][k]).toFixed(3)).join(' × ')]);
 if(point)fields.push(['点选坐标（模型单位）',point.map(x=>x.toFixed(3)).join(', ')]);
 for(const [k,s] of fields)dl.append(node('dt',k),node('dd',s));p.append(dl,button('拟合到构件',()=>viewer.fit(id),'wide'))
 if(editable())p.append(button('修改名称',()=>{
  const input=node('input');input.maxLength=120;input.value=nodeName(id);
  showDialog('修改构件名称',input,()=>{
   const name=input.value.trim();if(!name)throw Error('请输入构件名称');
   change(()=>{scene.names??={};if(name===r[2])delete scene.names[id];else scene.names[id]=name})
  },'保存');input.select()
 },'wide'))
}
function settingsPanel(p){
 if(craneAssemblies.length){
  const all=node('input');all.type='checkbox';all.checked=showCranePoses;
  all.onchange=()=>{showCranePoses=all.checked;filterScene();renderPanel()};
  p.append(field('叠加显示吊臂全部工况',all))
 }
 const axis=node('select');axis.id='sectionAxis';for(const [v,s] of [['','关闭'],['x','X · 左右'],['y','Y · 高度'],['z','Z · 前后']])axis.add(new Option(s,v));
 axis.value=scene.section?.axis||'';p.append(field('剖切方向',axis));
 axis.onchange=()=>change(()=>{const a=axis.value,k='xyz'.indexOf(a),b=tree[0][4];scene.section=a?{axis:a,value:(b[k]+b[k+3])/2}:null});
 if(scene.section){const r=node('input'),k='xyz'.indexOf(scene.section.axis),b=tree[0][4];r.type='range';r.min=b[k];r.max=b[k+3];r.step='.05';r.value=scene.section.value;
  const output=node('small',Number(r.value).toFixed(2)+' 模型单位');r.oninput=()=>{scene.section.value=Number(r.value);output.textContent=Number(r.value).toFixed(2)+' 模型单位';viewer.section(scene.section);markDirty()};p.append(field('剖切位置',r),output)
 }
 const dist=node('input');dist.id='explode';dist.type='range';dist.min=0;dist.max=2;dist.step='.05';dist.value=viewer.explode||0;dist.onchange=()=>viewer.separate(Number(dist.value));p.append(field('按源图层分解',dist));
 const detail=node('select');detail.add(new Option('自动按距离加载','auto'));detail.add(new Option('当前可见区域原始精度','full'));detail.value=viewer.full?'full':'auto';detail.onchange=()=>{viewer.full=detail.value==='full';viewer.queueDetail()};p.append(field('模型精度',detail));
 const line=node('input');line.type='checkbox';line.checked=!!(viewer.wireOnly||viewer.paint.wireframe);line.onchange=()=>{
  if(viewer.presentation&&viewer.outlines&&!viewer.explode){viewer.wireOnly=line.checked;filterScene();return}
  viewer.paint.wireframe=line.checked;for(const g of viewer.groups)for(const o of g.children)if(o.isMesh&&!o.userData.ghostOnly)o.material.wireframe=line.checked;viewer.draw()};p.append(field('线框显示',line));
 p.append(button('全屏浏览',()=>{if(document.fullscreenElement)document.exitFullscreen();else document.documentElement.requestFullscreen().catch(e=>notify(e.message))},'wide'))
}
function notesPanel(p){
 if(!twinMode)p.append(button('＋ 在模型上标记',()=>{setMode('mark');if(innerWidth<760)setPanel(null)},'wide'));
 if(!scene.notes.length)p.append(node('p','尚无批注。','empty'));
 const persisted=new Set((JSON.parse(baseline).notes||[]).map(n=>n.id));
 scene.notes.forEach(m=>{
  const row=node('div',null,'review-entry'),details=node('div',null,'review-entry-main');
  details.append(button(m.text,()=>viewer.fitBox({getCenter:t=>t.fromArray(m.point),getSize:t=>t.set(3,3,3)}),'name'),node('small',authorOf(m)));
  row.append(details);
  if(editable()||(canContribute()&&m.authorLogin===reviewLogin)||(!twinMode&&m.id&&!persisted.has(m.id)))row.append(button('删除',()=>showDialog('删除批注',node('p',m.text+' · '+authorOf(m)),()=>changeEntry('notes','delete',m),'删除批注'),'entry-delete','删除批注 '+m.text));
  p.append(row)
 })
}
async function publish(){
 if(publishing||!editable())return;
 if(viewer.explode){notify('请先将分解距离调为零，再发布模型');return}
 publishing=true;revisionLabel();
 const before=JSON.stringify(scene),previousIsolation=isolate;
 const snapshot=structuredClone({...scene,removedViews:scene.removedViews||[],hidden:effectiveHidden(),camera:viewer.cameraState(),environment:viewer.light?.preset||environment});
 try{
  if(!managementToken)managementToken=(await getJSON('/api/admin/state')).token;
  const r=await request('/api/admin/nwd-scene',{method:'POST',headers:{'Content-Type':'application/json','X-Management-Token':managementToken},body:JSON.stringify({model,digest:index.digest,base:revision,scene:snapshot})});
  revision=(await r.json()).revision;remoteRemoved=[];remoteRevision=0;try{localStorage.setItem(publicationKey,JSON.stringify([index.digest,revision]))}catch{}
  baseline=JSON.stringify(snapshot);
  if(JSON.stringify(scene)===before&&isolate===previousIsolation){scene=snapshot;isolate=-1}
  markDirty();update();renderPanel();notify('已发布 v'+revision+' · 项目网页可查看')
 }catch(e){notify(e.message,true)}finally{publishing=false;revisionLabel()}
}
async function init(){
 const [session,catalog]=await Promise.all([getJSON('/api/auth/session'),getJSON('/api/nwd/models')]);
 reviewLogin=session.login||'';namedEditor=session.role==='editor'&&!!reviewLogin;
 reviewAuthor=session.name||session.login||({viewer:'普通用户',editor:'专业编辑',admin:'管理员'}[session.role]);
 admin=!embed&&rev==='latest'&&session.role==='admin';
 if(admin){
  const {setupImport}=await import('./model-import.js');
  setupImport({request,getJSON,notify,button,node,showDialog,dirty:()=>dirty&&admin})
 }
 const models=catalog;info=models.find(m=>m.id===model);
 if(!info&&models.length&&!params.has('model')){const url=new URL(location.href);url.searchParams.set('model',models[0].id);location.replace(url);return}
 if(!info){notify(models.length?'找不到指定的模型':admin?'模型库为空，可从「更多 → 导入模型」开始':'暂无已入库模型',true);return}
 for(const m of models)$('model').add(new Option(m.name,m.id));$('model').value=model;
 $('model').onchange=()=>{if(dirty&&!confirm('离开将丢弃未发布修改，继续切换？')){$('model').value=model;return}dirty=false;location.assign((twinMode?'/twin.html':'/nwd.html')+'?model='+encodeURIComponent($('model').value))};
 if(!['k','l'].includes(model))document.querySelector('.platform-id small').textContent='工程模型数字孪生';
 $('source').textContent=info.source;document.title=info.name+' · NWD 模型审查';
 await initAssetCache(session);
 const [meta,published]=await Promise.all([getJSON(endpoint('index')),getJSON(endpoint('scene')+'&rev='+encodeURIComponent(rev))]);index=meta;revision=published.revision;
 scene={hidden:[],removed:[],views:[],notes:[],...published.scene};baseline=JSON.stringify(scene);
 const native=!['k','l'].includes(model)?null:await fetch('/api/platforms/'+encodeURIComponent(model)+'/index.json').then(r=>r.ok?r.json():null).catch(()=>null);
 const authored=native?.sourceTree===index.tree;
 tree=await getJSON(endpoint('asset')+'&id='+index.tree);children=new Map();
 for(let i=1;i<tree.length;i++){const p=tree[i][0];if(!children.has(p))children.set(p,[]);children.get(p).push(i)}
 craneAssemblies=findCraneAssemblies();
 const presets=new Map(),renderers=new Map();let switching=false,reviewDraft=null;environment=scene.environment||'overview';
 async function rendererFor(twin){
  if(renderers.has(twin))return renderers.get(twin);
  const high=twin&&authored,canvas=$(twin?'canvas':'reviewCanvas');
  const view=new NwdRenderer(canvas,tree,index,asset,pick,msg=>{if(view===viewer)$('progress').textContent=msg},c=>{if(view===viewer)frame(c)},high,twin);
  view.filter(displayHidden(),removedNodes(),-1,-1);
  if(high){
   await openPlatform(view,model,new AbortController().signal,(name,title,apply)=>{
    presets.set(name,{title,apply});$('preset').add(new Option(title,name))
   },(done,total)=>{$('status').textContent='载入平台模型 '+done+' / '+total},native)
  }else{
   const [overview,members]=await Promise.all([asset(index.overview),index.members?asset(index.members):null]);
   if(members)view.attachMembers(members);
   view.overview=view.unpack(overview);view.home(info.view)
  }
  renderers.set(twin,view);return view
 }
 function dock(){
  const visible=twinMode&&tour&&!embed;$('tourDock').hidden=!visible;
  if(!visible)return;
  $('stops').replaceChildren(...tour.stops.map((name,i)=>button(name,()=>tour.preview(i),'stop',name)))
 }
 function showChrome(twin){
  const review=!twin&&!embed;document.body.classList.toggle('review-mode',review);
  if(review){
   document.body.insertBefore($('tools'),document.querySelector('body>footer'));
   for(const id of ['snapshot','share'])$('reviewActions').insertBefore($(id),$('reviewActions').querySelector('details'))
  }else{
   stage.append($('tools'));for(const id of ['snapshot','share'])$('reviewMenu').append($(id))
  }
  document.body.classList.toggle('overview-mode',twin&&!embed);
  $('platformName').textContent=info.name;$('nativeViews').hidden=!viewer.native||embed;
  $('canvas').hidden=!twin;$('reviewCanvas').hidden=twin;
  for(const [id,active] of [['overviewLink',twin],['reviewLink',!twin]]){
   if(active)$(id).setAttribute('aria-current','page');else $(id).removeAttribute('aria-current')
  }
  document.title=info.name+' · '+(twin?'数字孪生':'NWD 模型审查')
 }
 async function workspace(twin){
  if(savingEntry){notify('正在保存审查记录，请稍后切换');return false}
  if(switching)return false;switching=true;
  const old=viewer;
  try{
   $('status').hidden=false;$('status').textContent=twin?'正在载入平台模型…':'正在载入审查模型…';
   if(old?.native)environment=old.light.preset;
   const targetCanvas=$(twin?'canvas':'reviewCanvas');
   if(targetCanvas.hidden){targetCanvas.classList.add('staging');targetCanvas.hidden=false}
   const next=await rendererFor(twin);
   if(old&&!twinMode&&twin){
    reviewDraft={scene,dirty,baseline,revision,edits,redos};
    scene=structuredClone(scene);dirty=false;baseline=JSON.stringify(scene);edits=[];redos=[];isolate=-1
   }else if(old&&twinMode&&!twin){
    if(reviewDraft&&(reviewDraft.dirty||reviewDraft.revision===revision)){
     const newer=reviewDraft.revision<revision;
     if(newer){remoteRemoved=scene.removed;remoteRevision=revision}
     ({scene,dirty,baseline,revision,edits,redos}=reviewDraft)
    }else{scene=JSON.parse(baseline);dirty=false;edits=[];redos=[]}
    reviewDraft=null;isolate=-1
   }
   const pose=old?.cameraState()||scene.camera;
   if(old&&old!==next){old.separate(0);old.inactive=true;old.ready=false;old.clearMeasurement();measurement=null;measureStart=null}
   viewer=next;viewer.inactive=false;twinMode=twin;next.canvas.classList.remove('staging');showChrome(twin);
   if(pose){viewer.platformEnvironment?.(environment);viewer.setCamera(pose);$('preset').value=environment}
   // openPlatform has already selected its initial preset; do not reset after loading.
   if(twin&&!tour){tour=createTour(viewer,presets,index.views.filter((_,i)=>!scene.removedViews?.includes(i)),model,[index.digest,session.login||session.role].join('.'),notify,info.name)}
   viewer.ready=true;update();viewer.queueDetail();setMode('orbit');dock();
   floating=!twin&&!embed&&innerWidth>=1120;
   setPanel(innerWidth<850||embed?null:twin?'tree':'views');
   const mark=$('tools').querySelector('[data-tool=mark]');if(mark)mark.hidden=twin;
   if(!embed)history.replaceState(null,'',twin?$('overviewLink').href:$('reviewLink').href);
   $('status').hidden=true;$('present').disabled=false;return true
  }catch(error){const canvas=$(twin?'canvas':'reviewCanvas');canvas.classList.remove('staging');if(old)showChrome(twinMode);notify(error.message,true);console.error(error);return false}finally{switching=false}
 }
 for(const [id,twin] of [['overviewLink',true],['reviewLink',false]]){
  const url=new URL(location.href);url.pathname=twin?'/twin.html':'/nwd.html';url.searchParams.delete('workspace');url.searchParams.set('model',model);$(id).href=url;
  $(id).onclick=e=>{if(e.ctrlKey||e.metaKey||e.shiftKey||e.altKey)return;e.preventDefault();if(twin!==twinMode)workspace(twin)}
 }
 $('preset').onchange=()=>presets.get($('preset').value)?.apply();
 $('present').onclick=$('dockPlay').onclick=async()=>{if(twinMode||await workspace(true))tour?.start()};
 $('selectionContext').onclick=()=>{viewer.context=!viewer.context;filterScene();renderPanel()};
 $('deleteSelection').onclick=()=>removeNode(selected);
 $('clearSelection').onclick=()=>{isolate=-1;select(-1)};
 $('closeCard').onclick=()=>{$('componentCard').hidden=true};
 $('film').addEventListener('routechange',dock);
 if(!await workspace(twinMode))return;
 tools();
 if(!twinMode&&params.get('tree')===index.tree){
  const entry=params.get('node'),id=entry===null?-1:Number(entry);
  if(Number.isInteger(id)&&id>=0&&id<tree.length&&ancestor(id,[...scene.hidden,...scene.removed])<0){
   for(let parent=tree[id][0];parent>=0;parent=tree[parent][0])expanded.add(parent);
   viewer.context=params.get('context')!=='0';if(embed)isolate=id;select(id);viewer.fit(id);
   document.querySelector('.row.selected')?.scrollIntoView({block:'nearest'})
  }
  const raw=new URLSearchParams(location.hash.slice(1)).get('camera');
  if(raw){
   const n=raw.split(',').map(Number);
   if(n.length===10&&n.every(v=>Number.isFinite(v)&&Math.abs(v)<1e8)&&Math.hypot(n[0]-n[3],n[1]-n[4],n[2]-n[5])>.001&&Math.hypot(...n.slice(6,9))>.01&&n[9]>=1&&n[9]<=175){
    viewer.setCamera({eye:n.slice(0,3),target:n.slice(3,6),up:n.slice(6,9),fov:n[9]})
   }
  }
 }
 let checking=false;
 async function refreshScene(){
  if(rev!=='latest'||document.hidden||!viewer.ready||checking||switching)return;
  checking=true;
  try{
   const fresh=await getJSON(endpoint('scene')+'&rev=latest');
   if(fresh.revision<=revision||switching)return;
   if(publishing||savingEntry)return;
   if(dirty&&editable()){
    if(remoteRevision!==fresh.revision){remoteRemoved=fresh.scene.removed||[];remoteRevision=fresh.revision;update();renderPanel()}
    $('revision').textContent='已发布 v'+fresh.revision+' · 请核对当前草稿';return
   }
   remoteRemoved=[];remoteRevision=0;dirty=false;
   scene={hidden:[],removed:[],views:[],notes:[],...fresh.scene};baseline=JSON.stringify(scene);revision=fresh.revision;isolate=-1;edits=[];redos=[];
   environment=scene.environment||'overview';
   // Publishing metadata must not move a visitor's active camera.
   update();renderPanel()
  }catch{ /* A temporarily offline viewer keeps its current version. */ }finally{checking=false}
 }
 window.addEventListener('storage',e=>{if(e.key===publicationKey)refreshScene()});
 document.addEventListener('visibilitychange',refreshScene);window.addEventListener('focus',refreshScene);
 setInterval(refreshScene,10000);
 for(const b of document.querySelectorAll('[data-panel]'))b.onclick=async()=>{
  if(b.dataset.panel==='tour'&&!twinMode&&!await workspace(true))return;
  if(!twinMode&&!embed&&b.dataset.panel==='tree'&&innerWidth>=850){floating=!floating;setPanel(panel==='tree'?null:panel)}
  else setPanel(b.dataset.panel===panel?null:b.dataset.panel)
 };
 $('close').onclick=()=>setPanel(null);$('closeTree').onclick=()=>{floating=false;setPanel(panel)};
 const win=$('treeWindow'),grip=$('treeGrip');
 function clampTree(x=win.offsetLeft,y=win.offsetTop){
  if(win.hidden)return;
  win.style.left=Math.max(0,Math.min(stage.clientWidth-win.offsetWidth,x))+'px';
  win.style.top=Math.max(0,Math.min(stage.clientHeight-win.offsetHeight,y))+'px'
 }
 new ResizeObserver(()=>clampTree()).observe(stage);
 matchMedia('(max-width:849px)').addEventListener('change',event=>{
  if(event.matches&&!twinMode){floating=false;setPanel(null)}
 });
 $('reviewCanvas').ondblclick=()=>{if(mode==='orbit'&&selected>=0)viewer.fit(selected)};
 grip.onpointerdown=e=>{
  if(e.target.closest('button'))return;
  const x=e.clientX-win.offsetLeft,y=e.clientY-win.offsetTop;grip.setPointerCapture(e.pointerId);
  grip.onpointermove=move=>clampTree(move.clientX-x,move.clientY-y);
  grip.onlostpointercapture=()=>grip.onpointermove=null
 };
 for(const b of $('cube').children)b.onclick=()=>viewer.face(b.dataset.face);
 $('share').onclick=share;$('publish').onclick=publish;$('print').onclick=()=>window.print();
 $('snapshot').onclick=()=>{const link=node('a');link.download=info.name+'-快照.png';const out=document.createElement('canvas');out.width=viewer.canvas.width;out.height=viewer.canvas.height;const ctx=out.getContext('2d');ctx.fillStyle='#e2eaf0';ctx.fillRect(0,0,out.width,out.height);ctx.drawImage(viewer.canvas,0,0);
 for(const l of labels.children){if(l.hidden)continue;const p=viewer.project(l._point);ctx.font='16px sans-serif';ctx.fillStyle='#17384c';ctx.fillText(l.textContent,(p.x+1)*out.width/2,(1-p.y)*out.height/2)}
 link.href=out.toDataURL();link.click()};
 document.addEventListener('keydown',e=>{if(tour?.playing||$('dialog').open||/INPUT|TEXTAREA|SELECT/.test(e.target.tagName))return;if(e.key==='Escape'){if(selected>=0||isolate>=0){isolate=-1;select(-1)}else if(mode!=='orbit')setMode('orbit');else if(floating){floating=false;setPanel(panel)}else setPanel(null);return}if(e.key.toLowerCase()==='f')viewer.fit(selected);if(editable()&&(e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='z'){e.preventDefault();undo(e.shiftKey)}});
 window.addEventListener('beforeunload',e=>{if((dirty&&editable())||reviewDraft?.dirty){e.preventDefault();e.returnValue=''}})
}
init().catch(e=>{notify(e.message,true);console.error(e)});
