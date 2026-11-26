// Sheet coordinates are normalized uniformly. Heights and fitting sizes are illustrative.
const PidScene = (() => {
 const pipeLayer = /PROCESS|^AS_PIPE|^PIP(?:E|_|ING)|MAJORP|MINORP|^(?:MAJOR|MINOR)[ -]LINE|^0[12]-(?:MAJOR|MINOR)|主流程|次流程|工艺管|^LDL[123]A$|^SECONDARY$/i;
 const equipmentLayer = /^(EQP(?:_MAJ)?|EQUIP(?:MENT)?|EQU|AS_EQU|ZND-设备|05-equipment)$/i;
 function identify(i) {
  const b=(i.block||'').toUpperCase(), tag=i.tag||'', name=i.name||'';
  const a=Object.fromEntries((i.attributes||[]).map(p=>[p.key,String(p.value||'').trim()]));
  const pressure=/^(?:.*-)?(?:PI|PG)-?\d+[A-Z]?(?:\/[A-Z])?$/i.test(tag);
  const taggedGauge=pressure&&/^(?:INSERT|TEXT|MTEXT)$/.test(i.entity)&&!a.EQ_TAG&&!a.LN_TAG&&!a.VA_TAG;
  if(taggedGauge||(i.entity==='INSERT'&&/^(?:PI|PG)$/i.test(a.IN_TAG||a.FNC||''))){
   const label=tag||[a.IN_TAG||a.FNC,a.IN_NUM||a.LOOP].filter(Boolean).join('-');
   return ['仪表',label,'gauge']
  }
  const line=a.LN_TAG||a['LINE-TAG']||a.LINE_NO;
  if(line)return ['管线标注',line,'label'];
  if(/^(LINE|LWPOLYLINE|POLYLINE|ARC|SPLINE)$/.test(i.entity)&&pipeLayer.test(i.layer))return ['管线',tag||i.layer+' · '+i.handle,'pipe'];
  const symbol=i.entity==='INSERT';
  if(symbol&&b==='ANGLEF')return ['阀门',tag||'角阀 '+i.handle,'angle'];
  if(symbol&&/^(?:NOZZLE|NOZ[0-9]?-C)$/.test(b))return ['管口',tag||'管口 '+i.handle,'nozzle'];
  if(symbol&&/^(REDUC|CONR-C|ECCRED)/.test(b))return ['管件',tag||'异径管 '+i.handle,'reducer'];
  if(/撬装/.test(name))return tag?['设备',tag,'skid']:null;
  if(symbol&&(!/^(TAG[_-]|IB\d)/.test(b)&&(/阀/.test(name)||/^(V\d{3}|BALL|ABAV|VALVE|VPLUG|GATE|CHECK)/.test(b)||a.VTAG||a.VA_TAG))){
   const safety=/(?:^|[-_])(SDV|BDV|PSV)[-_ ]*\d/i.exec(tag||a.VA_TAG||a.VTAG||'');
   const family=safety?safety[1].toLowerCase():/^VPLUG/.test(b)?'plug':/止回|CHECK/.test(name+b)?'check':/控制阀|调节阀|关断阀|^SDV|^PCV|^FCV/.test(name+tag)?'actuated':/BALL|球阀/.test(b+name)?'ball':/闸阀|GATE/.test(name+b)?'gate':'valve';
   return ['阀门',tag||a.VTAG||a.VA_TAG||'阀门 '+i.handle,family]
  }
  if(symbol&&/^(?:FLANGE|FLG-C|BFLG-C)$/i.test(b))return ['管件',tag||'法兰 '+i.handle,'flange'];
  if(symbol&&/^(?:VEV-C|FIL-C)$/.test(b))return ['设备',tag||(/FIL/.test(b)?'过滤器 ':'立式容器 ')+i.handle,/FIL/.test(b)?'filter':'tank'];
  if(!tag)return null;
  if(/泵|压缩机/.test(name))return ['设备',tag,/泵/.test(name)?'pump':'compressor'];
  if(/储罐|洗涤罐|缓冲罐|过滤器|分离器|容器|换热器|冷却器/.test(name))return ['设备',tag,/储罐/.test(name)?'tank':/过滤器/.test(name)?'filter':/冷却|换热/.test(name)?'exchanger':'vessel'];
  if(/变送|测量|温度|压力|指示|液位|开关|仪表|报警|控制器/.test(name)||a.IN_NUM||a.LOOP)
   return ['仪表',tag,/^P[IG]-/i.test(tag)?'gauge':/报警|控制器/.test(name)?'control':/开关/.test(name)?'switch':/^(?:TW|TE)-/i.test(tag)?'probe':/T-|变送/.test(tag+' '+name)?'transmitter':'indicator'];

  return null
 }
 function box(nodes) {
  if(!nodes.length)return null;
  const b=nodes.map(p=>p.getBBox()), x=Math.min(...b.map(v=>v.x)),y=Math.min(...b.map(v=>v.y));
  return [x,y,Math.max(...b.map(v=>v.x+v.width))-x,Math.max(...b.map(v=>v.y+v.height))-y]
 }
 function strokes(path,convert) {
  const d=path.getAttribute('d')||'';
  if(!d)return [];
  if(!/[achqstv]/i.test(d)){
   // Preserve CAD vertices and pen lifts, including dashed multi-subpath entities.
   const words=d.match(/[a-z]|[-+]?(?:\d*\.\d+|\d+\.?\d*)(?:e[-+]?\d+)?/ig)||[];
   let x=0,y=0,command='',run=[],runs=[];
   for(let j=0;j<words.length;){
    if(/^[a-z]$/i.test(words[j]))command=words[j++];
    if(command.toLowerCase()==='z'){if(run.length)run.push(run[0]);command='';continue}
    if(!/^[ml]$/i.test(command)||j+1>=words.length)break;
    const relative=command===command.toLowerCase(),move=command.toLowerCase()==='m';
    x=(relative?x:0)+Number(words[j++]);y=(relative?y:0)+Number(words[j++]);
    if(move){run=[];runs.push(run);command=relative?'l':'L'}
    run.push(convert(x,y))
   }
   return runs.filter(r=>r.length>1)
  }
  const length=path.getTotalLength(), count=Math.min(80,Math.max(4,Math.ceil(length*convert.scale/.24)));
  if(!length)return [];
  return [Array.from({length:count+1},(_,j)=>{const p=path.getPointAtLength(length*j/count);return convert(p.x,p.y)})]
 }
 function cadRuns(nodes,convert,entity) {
  const runs=nodes.flatMap(p=>strokes(p,convert));
  if(entity!=='LINE'||runs.length<2)return runs;
  // SVG dash segments belong to one straight CAD entity, including on equipment outlines.
  const flat=runs.flat(),a=flat[0],b=flat.at(-1),dx=b[0]-a[0],dz=b[2]-a[2],len=Math.hypot(dx,dz);
  return len&&flat.every(p=>Math.abs((p[0]-a[0])*dz-(p[2]-a[2])*dx)<len*.005)?[[a,b]]:runs
 }
 function anglePorts(nodes,xy){
  const lines=nodes.flatMap(n=>strokes(n,xy)).filter(a=>a.length===2);
  const nodesByKey=new Map(),key=p=>p[0].toFixed(3)+','+p[2].toFixed(3);
  for(const pair of lines)for(const p of pair){
   const k=key(p),entry=nodesByKey.get(k)||{point:p,count:0};entry.count++;nodesByKey.set(k,entry)
  }
  const centers=[...nodesByKey.values()].filter(n=>n.count>=4);
  if(centers.length!==1)return;
  const center=centers[0].point,ports=[];
  for(const [a,b] of lines){
   const point=[(a[0]+b[0])/2,1,(a[2]+b[2])/2],x=point[0]-center[0],z=point[2]-center[2];
   const length=Math.hypot(x,z),bar=Math.hypot(b[0]-a[0],b[2]-a[2]);
   if(length<.01||bar<.01||Math.abs(x*(b[0]-a[0])+z*(b[2]-a[2]))>bar*length*.025)continue;
   const dx=x/length,dz=z/length,port={point,dx,dz,length};
   const i=ports.findIndex(p=>p.dx*dx+p.dz*dz>.99);
   if(i<0)ports.push(port);else if(length>ports[i].length)ports[i]=port
  }
  if(ports.length===2&&Math.abs(ports[0].dx*ports[1].dx+ports[0].dz*ports[1].dz)<.025)return {center,ports}
 }
 function nearest(e,segments) {
  return segments.map(s=>{
   const dx=s.b[0]-s.a[0],dz=s.b[2]-s.a[2],len=dx*dx+dz*dz;
   const t=len?Math.max(0,Math.min(1,((e.x-s.a[0])*dx+(e.z-s.a[2])*dz)/len)):0;
   const x=s.a[0]+dx*t,z=s.a[2]+dz*t;
   return {s,x,z,d:Math.hypot(e.x-x,e.z-z),angle:Math.atan2(dz,dx)}
  }).sort((a,b)=>a.d-b.d)
 }
 // Recover exploded bubbles only when the function and loop number are both
 // inside the same CAD symbol. Separate text in a title or a note has no mount.
 function pressureBubbles(data,paths,xy,objects){
  const numbers=[],functions=[],rings=[],dividers=[];
  for(const i of data.items){
   const text=(i.texts||[]).join('').trim();
   const isText=/^(?:TEXT|MTEXT)$/.test(i.entity);
   const functionText=isText&&/^(?:PI|PG)(?:-?\d+[A-Z]?)?$/i.test(text);
   const numeric=isText&&/^\d{2,6}[A-Z]?(?:\/[A-Z])?$/.test(text);
   const ring=i.entity==='CIRCLE'||i.entity==='INSERT'&&/^(?:SDC-C|IB01S|IB06S|TAG_IN[12]|BUB_TB)$/i.test(i.block);
   const divider=i.entity==='LINE'&&/^(?:0|SYM|AS_INST|INSTR|04-INST|ZND-仪表符号)$/i.test(i.layer);
   if(!functionText&&!numeric&&!ring&&!divider)continue;
   const nodes=(paths.get(i.handle)||[]).filter(p=>p.tagName.toLowerCase()==='path');
   if(divider){
    const b=box(nodes);if(b&&b[3]*xy.scale<.018&&b[2]*xy.scale<4)
     dividers.push({x:xy(b[0]+b[2]/2,b[1])[0],z:xy(b[0],b[1])[2],w:b[2]*xy.scale});
    continue
   }
   const ink=nodes.filter(p=>p.style.fill==='none'),b=box(ring&&ink.length?ink:nodes)||i.bounds;
   if(!b)continue;
   const [x,,z]=xy(b[0]+b[2]/2,b[1]+b[3]/2),w=b[2]*xy.scale,h=b[3]*xy.scale;
   if(ring&&w>.22&&w<4.2&&Math.abs(w-h)<w*.18)rings.push({i,x,z,r:(w+h)/4});
   if(functionText||numeric)(numeric?numbers:functions).push({i,x,z,text})
  }
  const contains=(r,p)=>Math.hypot(p.x-r.x,p.z-r.z)<r.r*.92;
  for(const r of rings){
   const panel=/^(?:SDC-C|IB06S|TAG_IN2)$/i.test(r.i.block||'')||
    dividers.some(d=>Math.abs(d.x-r.x)<.04&&Math.abs(d.z-r.z)<.04&&Math.abs(d.w-2*r.r)<.07);
   const existing=objects.get(r.i.handle);
   if(existing?.family==='gauge'){
    existing.panel=panel;
    const loops=numbers.filter(n=>contains(r,n));
    if(!/\d/.test(existing.label)&&loops.length===1){
     existing.label+='-'+loops[0].text;existing.outline=[loops[0].i.handle]
    }
    continue
   }
   if(r.i.block==='BUB_TB'||r.i.entity==='CIRCLE'){
    const matches=[...objects.values()].filter(o=>o.family==='gauge'&&o.symbol&&
     Math.hypot(o.x-r.x,o.z-r.z)<.035&&Math.abs(o.width-2*r.r)<.08);
    if(matches.length===1){
     const g=matches[0];(g.outline??=[]).push(r.i.handle);continue
    }
   }
   const texts=functions.filter(t=>contains(r,t));
   if(texts.length!==1)continue;
   const t=texts[0],found=numbers.filter(n=>contains(r,n));
   if(!/\d/.test(t.text)&&found.length!==1)continue;
   const label=/\d/.test(t.text)?t.text:t.text+'-'+found[0].text;
   const old=objects.get(t.i.handle);
   if(old?.symbol||[...objects.values()].some(o=>o.family==='gauge'&&o.handle!==t.i.handle&&Math.hypot(o.x-r.x,o.z-r.z)<r.r*.18))continue;
   objects.set(t.i.handle,{handle:t.i.handle,kind:'仪表',family:'gauge',label,layer:t.i.layer,description:'压力指示仪',
    x:r.x,z:r.z,width:2*r.r,depth:2*r.r,angle:0,linked:[],paths:[],symbol:true,panel,
    outline:[r.i.handle,...found.map(n=>n.i.handle)]})
  }
 }
 const impulseLayer=/^(?:0|SYM|L[DP]L7A|PRIML|AS_INST|INSTR(?:UMENT)?|04-INST|ZND-仪表符号|SYMBOL_LDL2A|INSTRUMENT-SYMBLE)$/i;
 function mountPressureGauges(objects,segments,leaders,airTubes){
  const potentialHosts=segments.concat(airTubes.flatMap(e=>e.paths.flatMap(run=>run.slice(1).map((b,i)=>({a:run[i],b,e})))));
  const distance=(a,b)=>Math.hypot(a[0]-b[0],a[2]-b[2]);
  const edges=[];
  for(const run of leaders){
   if(objects.get(run.handle)?.family==='pipe')continue;
   edges.push(run)
  }
  const terminals=[];
  for(const o of [...objects.values(),...airTubes]){
   if(o.family==='pipe'){
    for(const path of o.paths)for(const [p,q] of [[path[0],path[1]],[path.at(-1),path.at(-2)]])
     terminals.push({point:p,next:q,other:o.handle});
   }else if(o.kind==='阀门'&&o.connected&&o.sockets?.length===1&&o.family!=='plug'){
    const dx=Math.cos(o.angle),dz=Math.sin(o.angle),half=o.span/2;
    const face=[o.x+half*dx,1,o.z+half*dz];
    const symbolHalf=(Math.abs(dx)*o.width+Math.abs(dz)*o.depth)/2;
    terminals.push({point:[o.x+symbolHalf*dx,1,o.z+symbolHalf*dz],next:[o.x,1,o.z],mount:face,other:o.handle})
   }
  }
  function hostAt(p,from){
   const matches=[];
   for(const {a,b,e} of potentialHosts){
    const dx=b[0]-a[0],dz=b[2]-a[2],len=Math.hypot(dx,dz);if(!len)continue;
    const t=Math.max(0,Math.min(1,((p[0]-a[0])*dx+(p[2]-a[2])*dz)/(len*len)));
    const point=[a[0]+t*dx,1,a[2]+t*dz];
    if(distance(p,point)>.042)continue;
    if(t>.002&&t<.998&&Math.abs((p[0]-from[0])*dz-(p[2]-from[2])*dx)<distance(p,from)*len*.55)continue;
    if(e.cuts?.some(c=>c.a===a&&c.b===b&&distance(c.from,point)+distance(c.to,point)<=distance(c.from,c.to)+.001))continue;
    if(!matches.some(m=>m.other===e.handle))matches.push({other:e.handle,point})
   }
   for(const end of terminals)if(end.mount&&distance(end.point,p)<.13)matches.push({other:end.other,point:end.mount});
   if(matches.length===1)return matches[0];
   if(matches.length>1){
    const atEnd=matches.map(m=>terminals.find(t=>t.other===m.other&&!t.mount&&distance(t.point,p)<.012));
    if(atEnd.every(Boolean)&&matches.every(m=>distance(m.point,matches[0].point)<.012&&
     (objects.get(m.other)?.elevation||1)===(objects.get(matches[0].other)?.elevation||1))){
     const axis=t=>Math.atan2(t.point[2]-t.next[2],t.point[0]-t.next[0]);
     if(atEnd.length===2&&Math.cos(axis(atEnd[0])-axis(atEnd[1]))<-.995)return matches[0]
    }
    return {ambiguous:true}
   }
  }
  for(const g of objects.values()){
   if(g.family!=='gauge')continue;
   if(g.panel){delete g.tap;g.blockSource='盘面压力指示 · 见图纸';continue}
   if(g.tap)continue;
   if(!g.symbol){g.blockSource='压力标注 · 取压点待核';continue}
   const center=[g.x,1,g.z],r=(g.width+g.depth)/4;
   const enters=(p,q)=>{
    const d=distance(p,center),span=distance(p,q);
    return span>.007&&Math.abs(d-r)<Math.min(.19,Math.max(.06,r*.16))&&
     (center[0]-p[0])*(p[0]-q[0])+(center[2]-p[2])*(p[2]-q[2])>.76*d*span
   };
   const direct=terminals.filter(t=>enters(t.point,t.next));
   const starts=[];
   for(const edge of edges)for(const direction of [edge.points,edge.reverse]){
    if(enters(direction[0],direction[1]))starts.push({edge,direction})
   }
   if(direct.length===1&&!starts.length){
    const t=direct[0];g.tap={point:t.mount||t.point,other:t.other};continue
   }
   if(direct.length||starts.length!==1)continue;
   let {edge,direction}=starts[0];const used=new Set();
   while(!used.has(edge.handle)){
    used.add(edge.handle);
    const p=direction.at(-1),q=direction.at(-2),host=hostAt(p,q);
    if(host?.ambiguous)break;
    if(host){g.tap={...host,evidence:[...used]};break}
    const next=[];
    for(const e of edges)if(!used.has(e.handle))for(const path of [e.points,e.reverse])
     if(distance(path[0],p)<.036)next.push({edge:e,direction:path});
    if(next.length!==1)break;
    ({edge,direction}=next[0])
   }
  }
  // Pneumatic tubing is a physical pressure source. Keep it separate from
  // process connectivity so an air signal cannot become a process valve port.
  const selected=new Set([...objects.values()].filter(g=>g.tap).map(g=>g.tap.other));
  const queue=airTubes.filter(t=>selected.has(t.handle));
  const ends=t=>t.paths.flatMap(p=>[p[0],p.at(-1)]);
  while(queue.length){
   const tube=queue.pop();if(objects.has(tube.handle))continue;
   objects.set(tube.handle,tube);
   for(const next of airTubes)if(!objects.has(next.handle)&&ends(tube).some(a=>ends(next).some(b=>distance(a,b)<.025)))queue.push(next)
  }
 }
 // Match off-sheet symbols only with an explicit direction note, a local
 // line-number label and an open end on that same identified run.
 function connectReferences(data,objects,pipes,junctions,xy){
  if(!data.references?.length)return;
  const items=new Map(data.items.map(i=>[i.handle,i]));
  const at=id=>{const p=items.get(id)?.position;return p&&xy(...p)};
  const notes=[];
  for(const t of data.texts||[]){
   const p=at(t.handle),from=/^FROM\s+/i.test(t.text),to=/^(?:TO\s+)|\sTO\s|\bOVERBOARD$/i.test(t.text);
   if(p&&(from||to)&&!/^TO (?:PREVENT|BE|ALLOW|AVOID)\b/i.test(t.text))notes.push({p,from,text:(t.zh||t.text).replace(/^(?:来自|去往|FROM|TO)\s*/i,'')})
  }
  const labels=[...objects.values()].filter(o=>o.family==='label'&&o.linked.length);
  const ends=[];
  for(const pipe of pipes)for(const run of pipe.paths)for(const [end,next] of [[run[0],run[1]],[run.at(-1),run.at(-2)]]){
   if(next&&junctions.get(Math.round(end[0]*50)+','+Math.round(end[2]*50))?.size===1)ends.push({pipe,end,next})
  }
  function closest(rows,score,max,gap){
   const sorted=rows.map(row=>({row,d:score(row)})).filter(x=>x.d<=max).sort((a,b)=>a.d-b.d);
   return sorted.length&&(!sorted[1]||sorted[1].d-sorted[0].d>gap)?sorted[0].row:null
  }
  for(const ref of data.references){
   const p=at(ref.handle);if(!p||ref.selfReference)continue;
   const score=(x,z)=>Math.hypot(x-p[0],(z-p[2])*4);
   const note=closest(notes,n=>score(n.p[0],n.p[2]),11,.45);
   const tag=closest(labels,l=>score(l.x,l.z),12,.5);
   if(!note||!tag)continue;
   const candidate=closest(ends.filter(e=>tag.linked.includes(e.pipe.handle)),e=>score(e.end[0],e.end[2]),12,.65);
   if(!candidate||candidate.used)continue;
   candidate.used=true;
   (candidate.pipe.offSheet??=[]).push({end:candidate.end,next:candidate.next,from:note.from,text:note.text,ref:ref.code})
  }
 }
 function assemble(data,paths,frame,recipe=null) {
  const [left,top,w,h]=frame, scale=100/w;
  const xy=(x,y)=>[(x-left-w/2)*scale,1,(y-top-h/2)*scale];xy.scale=scale;
  const objects=new Map(),segments=[],outlines=[],unmarked=[],leaders=[],airTubes=[],specs=new Map();
  const norm=s=>s.trim().toUpperCase().replace(/\s+/g,'');
  for(const i of data.items){
   if(!i.tag||i.entity!=='INSERT')continue;
   const type=identify(i);
   if(type?.[0]==='设备')specs.set(norm(i.tag),{type,name:i.name,attrs:i.attributes})
  }
  for(const i of data.items){
   const nodes=(paths.get(i.handle)||[]).filter(p=>p.tagName.toLowerCase()==='path');
   const text=/^(TEXT|MTEXT)$/.test(i.entity)?(i.texts||[]).find(t=>specs.has(norm(t))):null;
   const spec=text?specs.get(norm(text)):null;
   const type=spec?.type||identify(i);
   const unmarkedLine=/^(?:0|SYM|L[DP]L7A)$/i.test(i.layer)&&i.entity==='LINE';
   const leader=impulseLayer.test(i.layer)&&/^(LINE|LWPOLYLINE|POLYLINE)$/.test(i.entity);
   const airTube=i.entity==='LINE'&&/^PNEUMATIC_LDL7A$/i.test(i.layer);
   if(!type&&!airTube&&!unmarkedLine&&!leader&&!equipmentLayer.test(i.layer))continue;
   const ink=nodes.filter(p=>p.style.fill==='none');
   const b=box(ink.length?ink:nodes)||i.bounds;if(!b)continue;
   const cx=b[0]+b[2]/2,cy=b[1]+b[3]/2;
   if(cx<left||cx>left+w||cy<top||cy>top+h)continue;
   const [x,,z]=xy(cx,cy);
   const centerline=data.centerlines?.[i.handle];
   const runs=nodes=>centerline?[centerline.map(p=>xy(...p))]:cadRuns(nodes,xy,i.entity);
   if(airTube){
    const paths=runs(ink);
    if(paths.length===1&&paths[0].length>=2)airTubes.push({handle:i.handle,kind:'管线',family:'pipe',label:'仪表气管',layer:i.layer,
     description:'仪表气管',x,z,paths,linked:[]});
    continue
   }
   if(!type){
    if(unmarkedLine||leader){
     const [run,...rest]=runs(ink);
     if(leader&&run&&!rest.length&&run.length>=2&&run[0]!==run.at(-1))
      leaders.push({handle:i.handle,points:run,reverse:[...run].reverse()});
     if(unmarkedLine&&run&&!rest.length&&run.length===2&&Math.hypot(run[0][0]-run[1][0],run[0][2]-run[1][2])<8)
      unmarked.push({a:run[0],b:run[1],handle:i.handle,layer:i.layer});
     continue
    }
    if(i.entity!=='INSERT'&&ink.length)for(const pts of cadRuns(ink,xy,i.entity))outlines.push({pts,handle:i.handle});
    continue
   }
   const [kind,label,family]=type;
   const e={handle:i.handle,kind,label,family,description:spec?.name||i.name,layer:i.layer,schedule:i.entity==='INSERT'&&!!i.attributes.find(a=>a.key==='EQ_TAG'),x,z,width:b[2]*scale,depth:b[3]*scale,paths:[],angle:0,linked:[]};
   if(family==='gauge'){
    e.symbol=i.entity==='INSERT';e.panel=/^(?:SDC-C|IB06S|TAG_IN2)$/i.test(i.block||'')
   }
   if(family==='angle'){
    const corner=anglePorts(ink,xy);if(!corner)continue;
    e.x=corner.center[0];e.z=corner.center[2];e.ports=corner.ports
   }
   if(family==='pipe'){
    e.paths=runs(nodes);if(!e.paths.length)continue;
    for(const pts of e.paths)for(let j=1;j<pts.length;j++)segments.push({a:pts[j-1],b:pts[j],e})
   }
   objects.set(i.handle,e)
  }
  pressureBubbles(data,paths,xy,objects);
  placeEquipment(objects,outlines);
  const pipes=[...objects.values()].filter(e=>e.family==='pipe');
  recoverEditedBranches(objects,pipes,segments,unmarked);
  const node=p=>Math.round(p[0]*50)+','+Math.round(p[2]*50);
  const junctions=new Map();
  for(const pipe of pipes)for(const run of pipe.paths)for(const p of [run[0],run.at(-1)]){
   const k=node(p);if(!junctions.has(k))junctions.set(k,new Set());junctions.get(k).add(pipe)
  }
  for(const e of objects.values()){
   if(e.family!=='label')continue;
   const near=nearest(e,segments),first=near[0],alt=near.find(v=>v.s.e!==first?.s.e);
   if(!first||first.d>2||alt&&alt.d-first.d<.18)continue;
   e.linked=[first.s.e.handle];first.s.e.lineTags??=[];first.s.e.lineTags.push(e.label)
  }
  // A run continues only through two-ended joints. A tee, a crossing or conflicting line numbers ends propagation.
  const adjacency=new Map(pipes.map(p=>[p,new Set()]));
  for(const pair of junctions.values())if(pair.size===2){const [a,b]=pair;adjacency.get(a).add(b);adjacency.get(b).add(a)}
  const visited=new Set();
  for(const p of pipes){
   if(visited.has(p))continue;
   const run=[],todo=[p],tags=new Set();
   while(todo.length){
    const q=todo.pop();if(visited.has(q))continue;visited.add(q);run.push(q);
    for(const tag of q.lineTags||[])tags.add(tag);
    todo.push(...adjacency.get(q))
   }
   if(tags.size===1){const ids=run.map(t=>t.handle);for(const q of run){q.run=ids;q.lineTags=[...tags];q.label=q.lineTags[0]}}
  }
  for(const e of objects.values())if(e.family==='label'&&e.linked.length)e.linked=objects.get(e.linked[0]).run||e.linked;
  connectReferences(data,objects,pipes,junctions,xy);
  connectSheet(objects,pipes,segments);
  mountPressureGauges(objects,segments,leaders,airTubes);
  // Overlay suggestions only after native pipe runs, valve sockets, instruments and equipment have been resolved.
  if(recipe)enhance(objects,data,recipe,xy,frame,segments);
  return objects
 }
 function enhance(objects,data,recipe,xy,frame,segments){
  const [left,top,w,h]=frame;
  const fittings=new Set(['cap','plug','reducer','flange','coupling','dampener','flowelement']);
  const matchedPumps=new Set(),captions=new Map();
  for(const i of data.items){
   const obj=objects.get(i.handle);
   if(obj?.family==='pump'&&!obj.schedule&&i.bounds){
    const [x,y,w,h]=i.bounds;captions.set(obj,xy(x+w/2,y+h/2))
   }
  }
  for(const item of data.items){
   const proposal=recipe.parts?.[item.handle];
   if(!proposal||item.entity!=='INSERT'||!item.bounds||objects.has(item.handle))continue;
   const block=(item.block||'').toUpperCase();
   if(/^(TAG[_-]|BUB|BOX[_-]|ARROW|PARROW|FLAG|PLC-|\*|A\$)/.test(block))continue;
   const [kind,,geometry]=proposal;
   let family=block==='CAP'?'cap':proposal[1];
   if(['pipe','angle','nozzle','gauge'].includes(family))continue;
   const [bx,by,bw,bh]=item.bounds,cx=bx+bw/2,cy=by+bh/2;
   if(cx<left||cx>left+w||cy<top||cy>top+h)continue;
   const [x,,z]=xy(cx,cy);
   const obj={handle:item.handle,kind,label:item.tag||block,family,description:item.name,layer:item.layer,
    width:bw*xy.scale,depth:bh*xy.scale,x,z,angle:0,paths:[],linked:[],enhanced:true,geometry};
   if(family==='meteringpump'||family==='pump'){
    const nearPumps=[...captions].filter(([o])=>!o.annotation&&!matchedPumps.has(o.handle))
     .map(([o,p])=>({o,d:Math.hypot(p[0]-x,p[2]-z)})).sort((a,b)=>a.d-b.d);
    if(nearPumps[0]?.d<Math.max(3,obj.width*1.8)&&(!nearPumps[1]||nearPumps[1].d-nearPumps[0].d>.3)){
     if(family==='meteringpump'){
      const pump=nearPumps[0].o;
      Object.assign(pump,{family,enhanced:true,x,z,span:Math.max(obj.width,obj.depth),angle:obj.depth>obj.width?Math.PI/2:0});
      (pump.outline??=[]).push(item.handle);matchedPumps.add(pump.handle)
     }
     continue
    }
   }
   if(fittings.has(family)||kind==='阀门'){
    const snap=nearest(obj,segments),first=snap[0];
    const radius=Math.min(1.1,Math.max(.23,Math.max(obj.width,obj.depth)*.55));
    if(!first||first.d>radius)continue;
    // Coincident collinear ends describe one axis. Other close axes are ambiguous.
    if(snap.some(p=>p.d<first.d+.08&&Math.abs(Math.sin(p.angle-first.angle))>.18))continue;
    obj.x=first.x;obj.z=first.z;obj.angle=first.angle;obj.elevation=first.s.e.elevation||1;
    if(family==='cap'&&Math.hypot(obj.x-first.s.a[0],obj.z-first.s.a[2])<Math.hypot(obj.x-first.s.b[0],obj.z-first.s.b[2]))obj.angle+=Math.PI;
    obj.connected=true;obj.span=Math.min(1.05,Math.max(.18,Math.max(obj.width,obj.depth)));
   }
   objects.set(item.handle,obj)
  }
  // An A/B schedule row refers to both physical pumps. Highlight both when the exact two tags were located.
  const byTag=new Map([...matchedPumps].map(h=>[objects.get(h).label,h]));
  for(const o of objects.values()){
   if(!o.schedule||o.family!=='pump')continue;
   const m=/^(.*)([A-Z])\/([A-Z])$/.exec(o.label);
   if(m&&byTag.has(m[1]+m[2])&&byTag.has(m[1]+m[3])){
    o.annotation=true;o.linked=[byTag.get(m[1]+m[2]),byTag.get(m[1]+m[3])]
   }
  }
 }
 function placeEquipment(objects,outlines){
  // Reassemble outlines from CAD stroke endpoints; use their extents only for nearby tagged equipment.
  const parents=outlines.map((_,i)=>i),ends=[];
  const root=i=>{while(i!==parents[i]){parents[i]=parents[parents[i]];i=parents[i]}return i};
  for(const [i,{pts}] of outlines.entries())for(const p of [pts[0],pts.at(-1)]){
   for(const end of ends)if(Math.hypot(p[0]-end.p[0],p[2]-end.p[2])<=.45)parents[root(i)]=root(end.i);
   ends.push({i,p})
  }
  const groups=new Map();outlines.forEach((l,i)=>{const k=root(i);if(!groups.has(k))groups.set(k,[]);groups.get(k).push(l)});
  const bodies=[];
  for(const lines of groups.values()){
   const pts=lines.flatMap(l=>l.pts),xs=pts.map(p=>p[0]),zs=pts.map(p=>p[2]);
   const x0=Math.min(...xs),x1=Math.max(...xs),z0=Math.min(...zs),z1=Math.max(...zs);
   if(x1-x0>=1.6&&z1-z0>=1.2&&Math.max(x1-x0,z1-z0)<42)bodies.push({x:(x0+x1)/2,z:(z0+z1)/2,w:x1-x0,h:z1-z0,lines})
  }
  const used=new Set(),byTag=new Map();
  const candidates=[];
  for(const e of objects.values()){
   if(e.kind!=='设备')continue;
   if(!byTag.has(e.label))byTag.set(e.label,[]);byTag.get(e.label).push(e);
   if(e.schedule||e.family==='skid')continue;
   for(const b of bodies){const d=Math.hypot(Math.max(0,Math.abs(e.x-b.x)-b.w/2),Math.max(0,Math.abs(e.z-b.z)-b.h/2));
    if(d<3.2)candidates.push({e,b,d:d+.01*Math.hypot(e.x-b.x,e.z-b.z)})
   }
  }
  for(const {e,b} of candidates.sort((a,b)=>a.d-b.d)){
   if(e.body||used.has(b))continue;
   e.body=b;e.x=b.x;e.z=b.z;e.span=Math.max(b.w,b.h);e.angle=b.h>b.w?Math.PI/2:0;used.add(b)
  }
  for(const e of objects.values())if(e.body)e.outline=[...new Set(e.body.lines.map(l=>l.handle))];
  for(const group of byTag.values()){
   const winner=group.find(e=>e.body)||group.find(e=>!e.schedule)||group[0];
   for(const e of group)if(e!==winner&&!e.body){e.linked=[winner.handle];e.annotation=true}
  }
 }
 function recoverEditedBranches(objects,pipes,segments,unmarked){
  const known=segments.slice(),used=new Set();
  const valves=[...objects.values()].filter(e=>e.kind==='阀门'&&!e.ports);
  const gauges=[...objects.values()].filter(e=>e.kind==='仪表'&&!e.panel&&(e.family==='gauge'&&e.symbol||/^(?:PT|PIT)-/i.test(e.label)));
  const dist=(a,b)=>Math.hypot(a[0]-b[0],a[2]-b[2]);
  function gaugeAt(p,from){
   const dx=p[0]-from[0],dz=p[2]-from[2],len=Math.hypot(dx,dz);
   const matches=gauges.filter(g=>{
    const x=g.x-p[0],z=g.z-p[2],r=(g.width+g.depth)/4,d=Math.hypot(x,z);
    return r>.1&&Math.abs(g.width-g.depth)<r*.25&&Math.abs(r-d)<.07&&x*dx+z*dz>d*len*.96
   });
   return matches.length===1?matches[0]:null
  }
  function toPipe(p){
   return known.some(({a,b})=>{
    const dx=b[0]-a[0],dz=b[2]-a[2],len=dx*dx+dz*dz;
    if(!len)return false;
    const f=Math.max(0,Math.min(1,((p[0]-a[0])*dx+(p[2]-a[2])*dz)/len));
    return dist(p,[a[0]+dx*f,1,a[2]+dz*f])<.035
   })
  }
  // Layer 0 contains annotations too. Recover only a short, unique chain returning to process geometry.
  function trace(ref,seen){
   const next=ref.base.a===ref.point?ref.base.b:ref.base.a;
   if(toPipe(next))return {lines:[ref.base]};
   const gauge=ref.base.layer!=='0'&&gaugeAt(next,ref.point);
   if(gauge)return {lines:[ref.base],gauge,point:next};
   if(seen.size===2)return null;
   const continuation=[];
   for(const base of unmarked){
    if(seen.has(base)||base===ref.base||base.layer!==ref.base.layer)continue;
    for(const point of [base.a,base.b])if(dist(point,next)<.025)continuation.push({base,point})
   }
   if(continuation.length!==1)return null;
   const rest=trace(continuation[0],new Set([...seen,ref.base]));
   return rest&&{...rest,lines:[ref.base,...rest.lines]}
  }
  for(const valve of valves){
   const center=[valve.x,1,valve.z];
   const symbol=!pipeLayer.test(valve.layer);
   const close=known.flatMap(s=>[[s.a,s.b],[s.b,s.a]]).filter(([p])=>dist(p,center)<.9);
   if(close.length&&!symbol)continue;
   const sides=[];
   for(const base of unmarked)for(const point of [base.a,base.b]){
    if((symbol?base.layer==='0':base.layer!=='0')||dist(point,center)>1.4)continue;
    const other=point===base.a?base.b:base.a,len=dist(point,other);
    if(len<.03)continue;
    const dx=(point[0]-other[0])/len,dz=(point[2]-other[2])/len;
    const x=valve.x-point[0],z=valve.z-point[2],along=x*dx+z*dz;
    if(along<-.06||Math.abs(x*dz-z*dx)>.10)continue;
    if(symbol&&along>(Math.abs(dx)*valve.width+Math.abs(dz)*valve.depth)/2+.18)continue;
    const route=trace({base,point},new Set());
    if(route)sides.push({dx,dz,point,route})
   }
   if(symbol&&sides.length===1&&sides[0].route.gauge){
    const side=sides[0],hits=close.filter(([p,q])=>{
     const dx=p[0]-q[0],dz=p[2]-q[2],len=dist(p,q),x=valve.x-p[0],z=valve.z-p[2];
     return len>.01&&(dx*side.dx+dz*side.dz)<-.98*len&&x*dx+z*dz>=0&&Math.abs(x*dz-z*dx)<.05*len
    });
    if(hits.length===1)sides.push({point:hits[0][0],dx:-side.dx,dz:-side.dz,route:{lines:[]}})
   }
   if(sides.length!==2)continue;
   const [a,b]=sides;
   if(a.dx*b.dx+a.dz*b.dz>-.98||dist(a.point,b.point)>2.1||a.route.lines.some(l=>b.route.lines.includes(l))||a.route.gauge&&b.route.gauge)continue;
   const tap=a.route.gauge?a.route:b.route.gauge?b.route:null;
   if(symbol&&!tap)continue;
   if(tap)tap.gauge.tap={point:tap.point,other:tap.lines.at(-1).handle};
   for(const base of [...a.route.lines,...b.route.lines]){
    if(used.has(base))continue;used.add(base);
    const e={handle:base.handle,kind:'管线',label:'CAD 管段 · '+base.handle,family:'pipe',description:tap?'仪表取压支管':'与工艺管段相接的 CAD 线',layer:base.layer,x:(base.a[0]+base.b[0])/2,z:(base.a[2]+base.b[2])/2,paths:[[base.a,base.b]],linked:[]};
    objects.set(e.handle,e);pipes.push(e);segments.push({a:base.a,b:base.b,e})
   }
   valve.restoredBranch=true
  }
 }
 function connectSheet(objects,pipes,segments){
  const ends=[];
  function endpoint(e,point,dx,dz){
   const length=Math.hypot(dx,dz);
   if(length>1e-6)ends.push({e,point,length,dx:dx/length,dz:dz/length})
  }
  for(const e of pipes)for(const run of e.paths){
   const first=run[0],last=run.at(-1);
   const next=run.find(p=>Math.hypot(p[0]-first[0],p[2]-first[2])>1e-6);
   const prev=run.findLast(p=>Math.hypot(p[0]-last[0],p[2]-last[2])>1e-6);
   if(next&&prev){endpoint(e,first,first[0]-next[0],first[2]-next[2]);endpoint(e,last,last[0]-prev[0],last[2]-prev[2])}
  }
  const vessels=[...objects.values()].filter(o=>o.body&&/^(vessel|exchanger|filter|tank)$/.test(o.family));
  for(const e of vessels)e.upright=e.family==='filter'||e.family==='tank'||e.family==='vessel'&&e.body.h>e.body.w*1.3;
  for(const e of objects.values()){
   if(e.family!=='nozzle')continue;
   const candidates=vessels.map(v=>{
    const dx=e.x-v.x,dz=e.z-v.z;
    const x=Math.abs(dx)-v.body.w/2,z=Math.abs(dz)-v.body.h/2;
    return {v,dx,dz,edge:x>z?'x':'z',distance:Math.abs(Math.max(x,z))}
   }).filter(c=>c.distance<=.85).sort((a,b)=>a.distance-b.distance);
   const c=candidates[0];if(!c||candidates[1]&&candidates[1].distance-c.distance<.14)continue;
   const vessel=c.v,dx=c.edge==='x'?Math.sign(c.dx):0,dz=c.edge==='z'?Math.sign(c.dz):0;
   e.vessel=vessel.handle;e.portSide=dz<0?'top':dz>0?'bottom':'side';
   // A short horizontal flange stroke faces up/down on the drawing; a vertical one faces sideways.
   if(dx&&e.depth<e.width*.75||dz&&e.width<e.depth*.75){delete e.vessel;continue}
   e.portElevation=e.portSide==='top'?vesselLayout(vessel).top+.42:1;
   endpoint(e,[e.x,1,e.z],dx,dz)
  }
  const links=new Map([...objects.values()].map(o=>[o,new Set()]));
  const link=(a,b)=>{links.get(a).add(b);links.get(b).add(a);a.connected=b.connected=true};
  const near=(a,b)=>Math.hypot(a[0]-b[0],a[2]-b[2]);
  for(const e of objects.values()){
   if(e.family==='angle'||e.kind!=='阀门'&&e.kind!=='管件')continue;
   const center=[e.x,1,e.z],size=Math.max(e.width,e.depth);
   const radius=Math.max(e.restoredBranch?1.4:e.family==='plug'?.75:.38,Math.min(1.45,size*.83+.37));
   const local=ends.filter(p=>!p.used&&near(p.point,center)<radius);
   let best;
   for(const [i,a] of local.entries())for(const b of local.slice(i+1)){
    if(a.e===b.e||e.family==='plug')continue;
    const len=near(a.point,b.point);if(len<.11||len>2.1)continue;
    const dx=(b.point[0]-a.point[0])/len,dz=(b.point[2]-a.point[2])/len;
    if(a.dx*dx+a.dz*dz<.94||b.dx*dx+b.dz*dz>-.94)continue;
    const x=e.x-a.point[0],z=e.z-a.point[2],along=x*dx+z*dz,offset=Math.abs(x*dz-z*dx);
    if(along<-.04||along>len+.04||offset>Math.min(.27,.12+size*.24))continue;
    const score=offset*3+Math.abs(along-len/2)+len*.18;
    if(!best||score<best.score)best={a,b,len,dx,dz,score}
   }
   if(best){
    const {a,b,len,dx,dz}=best;e.angle=Math.atan2(dz,dx);e.span=len;
    e.x=(a.point[0]+b.point[0])/2;e.z=(a.point[2]+b.point[2])/2;
    e.sockets=[a,b].map(p=>({point:p.point,other:p.e.handle}));
    for(const p of [a,b]){p.used=true;link(e,p.e)}
    continue
   }
   // If only one terminal is visible, seat that side and leave the other side open.
   const single=local.map(p=>{
    const x=e.x-p.point[0],z=e.z-p.point[2];
    return {p,along:x*p.dx+z*p.dz,offset:Math.abs(x*p.dz-z*p.dx)}
   }).filter(c=>c.along>.045&&c.along<(e.family==='plug'?.72:Math.min(.95,size*.72+.26))&&c.offset<.13).sort((a,b)=>a.offset+a.along*.2-b.offset-b.along*.2);
   if(single.length===1){
    const {p,along}=single[0];p.used=true;link(e,p.e);
    const half=e.family==='plug'?.09:Math.min(along,Math.max(.12,size*.38));
    e.span=half*2;e.angle=Math.atan2(p.dz,p.dx);
    e.x=p.point[0]+along*p.dx;e.z=p.point[2]+along*p.dz;
    const face=[e.x-half*p.dx,1,e.z-half*p.dz];
    e.sockets=[{point:p.point,face,other:p.e.handle}];
    continue
   }
   // Some CAD symbols overlay an unbroken pipe centerline. Reserve a socket gap on that same entity.
   if(e.family==='plug')continue;
   const overlaps=nearest(e,segments).filter(({s,x,z,d,angle})=>{
    if(d>.105)return false;
    const half=Math.max(.12,Math.min(.51,(Math.abs(Math.cos(angle))*e.width+Math.abs(Math.sin(angle))*e.depth)*.49));
    const point=[x,1,z];
    return near(s.a,point)>half+.035&&near(s.b,point)>half+.035
   });
   if(overlaps.length===1){
    const {s,x,z,angle}=overlaps[0],dx=Math.cos(angle),dz=Math.sin(angle);
    const half=Math.max(.12,Math.min(.51,(Math.abs(dx)*e.width+Math.abs(dz)*e.depth)*.49));
    s.e.cuts??=[];s.e.cuts.push({a:s.a,b:s.b,from:[x-half*dx,1,z-half*dz],to:[x+half*dx,1,z+half*dz]});
    e.x=x;e.z=z;e.angle=angle;e.span=half*2;e.hostPipe=s.e.handle;
    link(e,s.e)
   }
  }
  // A valve can bolt directly to another valve. Match opposing outer faces
  // of the two drawn symbols only when that pairing is unique in both directions.
  const faces=[];
  for(const e of objects.values()){
   if(e.ports){
    for(const port of e.ports){
     const matches=ends.filter(n=>!n.used&&n.e.family==='pipe'&&near(n.point,port.point)<.12&&n.dx*port.dx+n.dz*port.dz<-.97);
     if(matches.length===1){const n=matches[0];n.used=true;port.mate=n.e.handle;port.target=n.point;link(e,n.e)}
     else if(!matches.length)faces.push({e,...port,port})
    }
   }else if(e.kind==='阀门'&&e.family!=='plug'&&e.sockets?.length===1){
    const dx=Math.cos(e.angle),dz=Math.sin(e.angle),half=(Math.abs(dx)*e.width+Math.abs(dz)*e.depth)/2;
    faces.push({e,dx,dz,point:[e.x+dx*half,1,e.z+dz*half]})
   }
  }
  const counterparts=f=>faces.filter(p=>p.e!==f.e&&near(p.point,f.point)<.12&&p.dx*f.dx+p.dz*f.dz<-.985&&
   Math.abs((p.point[0]-f.point[0])*f.dz-(p.point[2]-f.point[2])*f.dx)<.035);
  for(const a of faces){
   const pair=counterparts(a);if(a.done||pair.length!==1)continue;
   const b=pair[0];if(b.done||counterparts(b).length!==1)continue;
   const mid=[(a.point[0]+b.point[0])/2,1,(a.point[2]+b.point[2])/2];
   for(const [face,other] of [[a,b],[b,a]]){
    face.done=true;
    if(face.port){face.port.mate=other.e.handle;face.port.target=mid;continue}
    const e=face.e,first=e.sockets[0].face||e.sockets[0].point;
    e.x=(mid[0]+first[0])/2;e.z=(mid[2]+first[2])/2;e.span=near(first,mid);e.sockets.push({point:mid,other:other.e.handle})
   }
   link(a.e,b.e)
  }
  const join=(a,b,point,through)=>{
   a.e.connected=b.e.connected=true;
   a.e.joins??=[];const joint={start:a.point,end:b.point,point,other:b.e.handle};
   // Carry the two actual pipe tangents through to the elbow builder.
   if(through&&a.e.family==='pipe'&&b.e.family==='pipe'&&Math.abs(a.dx*b.dx+a.dz*b.dz)<.012)
    joint.turn={a:[a.dx,a.dz],b:[b.dx,b.dz],clearance:Math.min(a.length,b.length)*.43};
   a.e.joins.push(joint);
   if(through)link(a.e,b.e)
  };
  const open=ends.filter(p=>!p.used);
  for(const a of open){
   if(a.used)continue;
   const group=open.filter(b=>!b.used&&b.e!==a.e&&near(a.point,b.point)<.022);
   if(group.length){
    a.used=true;
    for(const b of group){b.used=true;join(a,b,a.point,group.length===1)}
   }
  }
  // Repair short pen gaps between facing ends; never bridge interior crossings.
  for(const a of open){
   if(a.used)continue;
   const candidates=[];
   for(const b of open){
    if(b.used||b.e===a.e||near(a.point,b.point)>.32)continue;
    const x=b.point[0]-a.point[0],z=b.point[2]-a.point[2],alignment=a.dx*b.dx+a.dz*b.dz;
    if(alignment<-.95&&Math.abs(x*a.dz-z*a.dx)<.05&&x*a.dx+z*a.dz>-.015){
     candidates.push({b,point:a.point});continue
    }
    const determinant=a.dx*b.dz-a.dz*b.dx;
    if(Math.abs(determinant)<.85)continue;
    const t=(x*b.dz-z*b.dx)/determinant,u=(x*a.dz-z*a.dx)/determinant;
    if(t>=-.022&&u>=-.022&&t<=.27&&u<=.27)candidates.push({b,point:[a.point[0]+a.dx*t,1,a.point[2]+a.dz*t]})
   }
   if(candidates.length===1){
    const {b,point}=candidates[0];a.used=b.used=true;join(a,b,point,true)
   }
  }
  for(const a of open){
   if(a.used||a.e.family==='nozzle')continue;
   const nearby=nearest({x:a.point[0],z:a.point[2]},segments.filter(s=>s.e!==a.e));
   const tee=nearby.filter(c=>c.d<.025&&near(c.s.a,a.point)>.025&&near(c.s.b,a.point)>.025&&Math.abs(Math.cos(c.angle)*a.dx+Math.sin(c.angle)*a.dz)<.2);
   if(tee.length===1){const t=tee[0],point=[t.x,1,t.z];join(a,{e:t.s.e,point},point,false)}
  }
  for(const nozzle of objects.values()){
   if(nozzle.portSide!=='top'||!links.get(nozzle).size)continue;
   const seen=new Set(),queue=[nozzle];
   let line=null;
   while(queue.length){
    const e=queue.pop();if(seen.has(e)||e.family==='nozzle'&&e!==nozzle)continue;
    seen.add(e);
    const tag=e.lineTags?.[0];if(tag&&line&&tag!==line)continue;
    line??=tag;e.elevation=Math.max(nozzle.portElevation,e.elevation||0);
    if(links.get(e).size<=2)queue.push(...links.get(e))
   }
  }
  for(const e of objects.values())if(e.hostPipe)e.elevation=objects.get(e.hostPipe).elevation;
 }
 function vesselLayout(e){
  const length=Math.min(28,Math.max(1.4,e.span||5.5));
  const upright=e.upright??(e.family==='tank'||e.family==='filter');
  const height=upright?(e.body?length*.72:length):length*.41;
  const width=upright&&e.body?Math.min(e.body.w,e.body.h):length*.41;
  return {upright,length,height,width,center:height/2+.44,top:height+.44}
 }
 return {assemble,vesselLayout}
})();
