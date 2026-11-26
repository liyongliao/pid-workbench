import {safetyRed} from './safety-paint.js';
import * as T from 'three';
import {sheetMaterial} from './industrial-surfaces.js';

const library=new Map(),primitive=new Map();
const paint={steel:0xb6bec0,case:0x769394,pipe:0x537e83,smallPipe:0x849ca0,motor:0x507475,iron:0x535e62,
 wheel:0xae5039,instrument:0x697d91,dial:0xf0eee5,brass:0xc39556,base:0x536064};
const axis=new T.Vector3(0,1,0), rotation=new T.Quaternion(), pos=new T.Vector3(), scale=new T.Vector3();
const finishByPaint=new Map([
 [paint.steel,5],[paint.smallPipe,3],[paint.iron,21],[paint.brass,20],[paint.wheel,12],
 [paint.instrument,7],[paint.dial,19],[paint.motor,8],[paint.base,21]
]);

function geometry(key,build) {
 if(!primitive.has(key)){const g=build();g.userData.shared=true;primitive.set(key,g)}
 return primitive.get(key)
}
const cyl=()=>geometry('cylinder',()=>new T.CylinderGeometry(1,1,1,24));
const sphere=()=>geometry('sphere',()=>new T.SphereGeometry(1,24,16));
const box=()=>geometry('box',()=>new T.BoxGeometry());
const elbow=()=>geometry('long-radius-elbow',()=>new T.TorusGeometry(2,1,16,16,Math.PI/2));
const ring=()=>geometry('wheel',()=>new T.TorusGeometry(.88,.12,10,32));
const cone=()=>geometry('taper',()=>new T.CylinderGeometry(.42,1,1,24));
let catalog;
export async function loadBlocks(families){
 if(!catalog)catalog=fetch('/api/models/blocks').then(r=>{if(!r.ok)throw Error();return r.json()}).catch(()=>{catalog=null;return {}});
 const available=await catalog;
 await Promise.all([...families].filter(k=>available[k]).map(async k=>{
  if(!library.has(k)){
   const entry=available[k];
   library.set(k,fetch('/api/models/blocks?asset='+encodeURIComponent(entry.asset)).then(async r=>{
    if(!r.ok)throw Error();
    const buf=await r.arrayBuffer(),v=new DataView(buf),n=v.getUint32(0,true),m=v.getUint32(4,true);
    const colorsOffset=8+12*n+4*m,withNormals=buf.byteLength===8+n*27+m*4;
    if((!withNormals&&buf.byteLength!==8+n*15+m*4)||!n||!m)throw Error();
    const g=new T.BufferGeometry();g.setAttribute('position',new T.BufferAttribute(new Float32Array(buf,8,n*3),3));
    g.setIndex(new T.BufferAttribute(new Uint32Array(buf,8+12*n,m),1));
    g.setAttribute('color',new T.BufferAttribute(new Uint8Array(buf,colorsOffset+(withNormals?12*n:0),n*3),3,true));
    if(withNormals)g.setAttribute('normal',new T.BufferAttribute(new Float32Array(buf,colorsOffset,n*3),3));
    else g.computeVertexNormals();
    g.userData.shared=true;g.userData.finish=k==='gauge'?7:k==='pump'?8:k==='ball'||k==='flange'||k==='check'?3:0;
    return {g,entry}
   }).catch(()=>{library.delete(k);return null}))
  }
  return library.get(k)
 }));
 const blocks=new Map();for(const k of families){const item=await library.get(k);if(item)blocks.set(k,item)}return blocks
}

// All instances of a repeated solid share geometry and a draw call. Selection retains the original CAD handle.
export function buildSheet(root,objects,blocks){
 const labels=[];
 const batches=new Map(),pieces=new Map(),byId=new Map(objects.map(o=>[o.handle,o]));
 let owner,placement=new T.Matrix4();
 function put(g,local,color){
  if(!batches.has(g))batches.set(g,new Map());
  const mat=sheetMaterial(g.userData.finish??finishByPaint.get(color)??0,g.hasAttribute('color'));
  const families=batches.get(g);
  if(!families.has(mat))families.set(mat,[]);
  const matrix=new T.Matrix4().multiplyMatrices(placement,local);
  const rec={id:owner.handle,matrix,color:new T.Color(color),g};families.get(mat).push(rec);
  if(!pieces.has(rec.id))pieces.set(rec.id,[]);pieces.get(rec.id).push(rec)
 }
 function part(g,x,y,z,sx,sy,sz,color,rx=0,ry=0,rz=0){
  rotation.setFromEuler(new T.Euler(rx,ry,rz));
  put(g,new T.Matrix4().compose(pos.set(x,y,z),rotation,scale.set(sx,sy,sz)),color)
 }
 function rod(a,b,r,color,g=cyl()){
  const p=new T.Vector3(...a),q=new T.Vector3(...b),d=q.clone().sub(p),len=d.length();if(len<.0001)return;
  put(g,new T.Matrix4().compose(p.lerp(q,.5),rotation.setFromUnitVectors(axis,d.normalize()),scale.set(r,len,r)),color)
 }
 function flange(x,y,z,r){
  if(blocks.has('flange'))part(blocks.get('flange').g,x,y,z,2*r,2*r,2*r,0xffffff);
  else{rod([x-.06,y,z],[x+.06,y,z],r,paint.steel);
   for(let j=0;j<6;j++){const a=j*Math.PI/3,yy=y+.76*r*Math.sin(a),zz=z+.76*r*Math.cos(a);rod([x-.08,yy,zz],[x+.08,yy,zz],r*.095,paint.iron)}}
 }
 function valve(f){
  if(f==='check'){part(sphere(),0,0,0,.42,.28,.26,paint.case);rod([-.5,0,0],[.5,0,0],.18,paint.case)}
  else{
   for(const k of [-1,1])rod([k*.5,0,0],[k*.03,0,0],.27,paint.case,cone());
   part(sphere(),0,.03,0,.27,.26,.25,paint.case);
   rod([0,.12,0],[0,.61,0],.085,paint.iron);
   if(f==='actuated'){rod([0,.48,0],[0,.65,0],.3,paint.instrument);part(sphere(),0,.64,0,.31,.13,.31,paint.instrument)}
   else{part(ring(),0,.62,0,.31,.31,.31,paint.wheel,Math.PI/2);
    for(let j=0;j<3;j++){let a=j*Math.PI*2/3;rod([0,.62,0],[.28*Math.cos(a),.62,.28*Math.sin(a)],.027,paint.wheel)}}
  }
  const off=blocks.has('flange')?.376:.42;
  flange(-off,0,0,.29);flange(off,0,0,.29)
 }
 function instrument(f){
  if(f==='control'||f==='switch'||f==='indicator'){
   part(box(),0,.41,0,.42,.52,.24,paint.instrument);
   part(box(),0,.44,.13,.31,.29,.025,paint.dial);
   if(f==='switch')rod([0,0,0],[0,.22,0],.056,paint.iron);
   return
  }
  if(f==='probe'){rod([0,-.12,0],[0,.5,0],.055,paint.steel);rod([0,.28,0],[0,.36,0],.15,paint.brass);return}
  rod([0,0,0],[0,.45,0],.07,paint.brass);
  if(f==='transmitter'){part(box(),0,.63,0,.48,.42,.29,paint.instrument);part(sphere(),0,.64,.155,.15,.15,.04,paint.dial)}
  else{rod([0,.65,-.13],[0,.65,.13],.29,paint.iron);rod([0,.65,.13],[0,.65,.145],.25,paint.dial);
   rod([0,.65,.15],[.14,.76,.15],.019,paint.wheel)}
 }
 function pump(f){
  part(box(),0,-.24,0,1.24,.09,.55,paint.base);
  for(const x of [-.35,.28])part(box(),x,-.13,0,.18,.2,.3,paint.iron);
  rod([-.05,.06,0],[.51,.06,0],.2,paint.motor);
  for(let j=0;j<10;j++){const a=j*Math.PI/5,y=.06+.18*Math.cos(a),z=.18*Math.sin(a);rod([.01,y,z],[.45,y,z],.031,paint.motor)}
  part(box(),.24,.27,0,.19,.09,.14,paint.iron);
  part(sphere(),-.33,.05,0,.23,.24,.19,paint.case);
  rod([-.33,.17,0],[-.33,.37,0],.09,paint.case);rod([-.60,.05,0],[-.37,.05,0],.09,paint.case);flange(-.57,.05,0,.15);
  if(f==='compressor')for(const x of [-.36,-.17])rod([x,.14,0],[x,.37,.08],.085,paint.steel)
 }
 function vessel(f,layout){
  if(layout.upright){
   const r=layout.width/2,head=Math.min(r*.46,layout.height*.18),side=layout.height/2-head;
   rod([0,-side,0],[0,side,0],r,paint.steel);
   for(const y of [-side,side])part(sphere(),0,y,0,r,head,r,paint.steel);
   for(const x of [-r*.6,r*.6])for(const z of [-r*.6,r*.6])
    rod([x,-layout.center+.04,z],[x,-side,z],r*.105,paint.iron);
   for(const yy of [-side,side]){
    rod([0,yy-r*.014,0],[0,yy+r*.014,0],r*1.008,paint.iron)
   }
   // Foot plates are attached to the same support axes as the shell.
   for(const x of [-r*.6,r*.6])for(const z of [-r*.6,r*.6])
    part(box(),x,-layout.center+.045,z,r*.37,.09,r*.37,paint.base);
   if(f==='filter')rod([0,side-.14,0],[0,side,0],r*1.05,paint.iron);
   return
  }
  const r=layout.width/2,len=layout.length;
  rod([-len*.4,0,0],[len*.4,0,0],r,paint.steel);
  for(const k of [-1,1]){
   part(sphere(),k*len*.4,0,0,len*.10,r,r,paint.steel);
   part(box(),k*len*.29,-r-.19,0,len*.055,.5,r*1.4,paint.iron);
   part(box(),k*len*.29,-layout.center+.035,0,len*.12,.07,r*1.8,paint.base);
  }
  if(f==='exchanger')for(const x of [-.38,-.32,.32,.38])flange(x*len,0,0,r*1.06)
 }
 const clamp=(x,min,max)=>Math.max(min,Math.min(max,x));
 const elevation=e=>e?.elevation||1;
 const pointAt=(p,y)=>[p[0],y,p[2]];
 const pipeRadius=e=>/^(?:仪表取压支管|仪表气管)$/.test(e.description)?.055:/MINOR|SECONDARY|次流程/i.test(e.layer||e.label)?.09:.14;
 function route(points,r,color){
  const clean=points.map(p=>new T.Vector3(...p)).filter((p,j,all)=>!j||p.distanceToSquared(all[j-1])>1e-8);
  if(clean.length<2)return;
  let start=clean[0];
  for(let j=1;j<clean.length-1;j++){
   const corner=clean[j],next=clean[j+1],incoming=corner.clone().sub(start),out=next.clone().sub(corner);
   const before=incoming.length(),after=out.length();
   incoming.normalize();out.normalize();
   if(Math.abs(incoming.dot(out))<.012&&before>=2*r-.0001&&after>=2*r-.0001){
    const tangent=corner.clone().addScaledVector(incoming,-2*r),exit=corner.clone().addScaledVector(out,2*r);
    rod(start.toArray(),tangent.toArray(),r,color);
    const x=out.clone().negate(),z=new T.Vector3().crossVectors(x,incoming);
    const matrix=new T.Matrix4().makeBasis(x,incoming,z).scale(new T.Vector3(r,r,r));
    matrix.setPosition(tangent.clone().addScaledVector(out,2*r));put(elbow(),matrix,color);
    start=exit
   }else{
    rod(start.toArray(),corner.toArray(),r,color);
    if(Math.abs(incoming.dot(out))<.998)part(sphere(),...corner.toArray(),r,r,r,color);
    start=corner
   }
  }
  rod(start.toArray(),clean.at(-1).toArray(),r,color)
 }
 // Trim both CAD entities to their common tangent points. The bend belongs to
 // the first handle; the second remains independently selectable beyond its weld.
 const trims=new Map(),turns=new Map();
 for(const e of objects)for(const j of e.joins||[]){
  const other=byId.get(j.other),r=pipeRadius(e);
  if(!j.turn||elevation(e)!==elevation(other)||pipeRadius(other)!==r||j.turn.clearance<2*r||e.cuts?.length||other.cuts?.length)continue;
  const at=(d)=>[j.point[0]-2*r*d[0],elevation(e),j.point[2]-2*r*d[1]];
  const a=at(j.turn.a),b=at(j.turn.b);
  trims.set(j.start,a);trims.set(j.end,b);turns.set(j,[a,pointAt(j.point,elevation(e)),b])
 }
 function nozzle(e){
  const v=byId.get(e.vessel);if(!v||!e.connected)return;
  const layout=PidScene.vesselLayout(v),r=layout.width/2,level=elevation(e);
  const outlet=[e.x,level,e.z];
  if(e.portSide==='top'){
   const along=clamp((e.x-v.x)*Math.cos(v.angle)+(e.z-v.z)*Math.sin(v.angle),-layout.length*.36,layout.length*.36);
   const x=layout.upright?v.x+clamp(e.x-v.x,-r*.65,r*.65):v.x+along*Math.cos(v.angle);
   const z=layout.upright?v.z:v.z+along*Math.sin(v.angle);
   // Follow the dished head at an offset nozzle, keeping the neck inside the shell.
   const y=layout.top-(layout.upright?Math.min(r*.46,layout.height*.18)*(1-Math.sqrt(1-((x-v.x)/r)**2)):0);
   rod([x,y-.15,z],[x,y+.16,z],.20,paint.steel);
   rod([x,y+.14,z],[x,y+.23,z],.27,paint.iron);
   route([[x,y+.18,z],[x,level,z],outlet],.14,paint.pipe);
   return
  }
  if(e.portSide==='bottom'){
   const bottom=layout.center-layout.height/2;
   route([[v.x,bottom+.04,v.z],[v.x,bottom-.15,v.z],[e.x,bottom-.15,e.z],outlet],.14,paint.pipe);
   return
  }
  const along=clamp((e.z-v.z)/(v.body.h/2),-.78,.78);
  const y=layout.upright?layout.center-along*layout.height/2:layout.center;
  const side=e.x<v.x?-1:1;
  const x=layout.upright?v.x+side*r:v.x+clamp(e.x-v.x,-layout.length*.38,layout.length*.38);
  const z=layout.upright?v.z:v.z+(e.z<v.z?-r:r);
  const stub=layout.upright?x+side*.34:x;
  const zStub=layout.upright?z:z+(e.z<v.z?-.34:.34);
  route([[x,y,z],[stub,y,zStub],[stub,level,zStub],outlet],.14,paint.pipe)
 }
 for(const e of objects){
  owner=e;
  if(e.family==='label'||e.annotation)continue;
  const f=e.family,height=elevation(e);
  placement.identity();
  // The same elevation applies to pipe ends, inline sockets, and top-nozzle risers.
  if(e.joins)for(const j of e.joins){
   const other=elevation(byId.get(j.other));
   route(turns.get(j)||[pointAt(j.start,height),pointAt(j.point,height),pointAt(j.point,other),pointAt(j.end,other)],pipeRadius(e),paint.pipe)
  }
  if(f==='pipe'){
   e.blockSource=height>1?'CAD 管段 · 罐顶接出':'CAD 管段';
   const r=pipeRadius(e);
   const color=r<.1?paint.smallPipe:paint.pipe;
   for(const pts of e.paths){
    let section=[pts[0]];
    for(let j=1;j<pts.length;j++){
     const start=pts[j-1],end=pts[j];
     const cuts=e.cuts?.filter(c=>c.a===start&&c.b===end).sort((a,b)=>Math.hypot(a.from[0]-start[0],a.from[2]-start[2])-Math.hypot(b.from[0]-start[0],b.from[2]-start[2]))||[];
     for(const cut of cuts){
      section.push(cut.from);route(section.map(p=>pointAt(trims.get(p)||p,height)),r,color);section=[cut.to]
     }
     section.push(end)
    }
    route(section.map(p=>pointAt(trims.get(p)||p,height)),r,color)
   }
   for(const link of e.offSheet||[]){
    const start=pointAt(link.end,height),dir=new T.Vector3().fromArray(link.end).sub(new T.Vector3().fromArray(link.next)).setY(0).normalize();
    const tip=new T.Vector3(...start).addScaledVector(dir,2.4);
    route([start,tip.toArray()],r,color);
    const along=link.from?dir.clone().negate():dir;
    put(geometry('flow-arrow',()=>new T.ConeGeometry(1,1,20)),new T.Matrix4().compose(tip.clone().addScaledVector(dir,-.23),new T.Quaternion().setFromUnitVectors(axis,along),new T.Vector3(r*1.7,.46,r*1.7)),paint.pipe);
    labels.push({id:e.handle,tag:(link.from?'来自':'去往')+link.text,ref:link.ref,anchor:tip,connection:true})
   }
   continue
  }
  if(f==='angle'){
   if(!e.connected){e.blockSource='待核对角阀接口';continue}
   const reach=Math.min(...e.ports.map(p=>p.length)),r=clamp(reach*.33,.045,.22);
   for(const p of e.ports){
    const face=pointAt(p.target||p.point,height),neck=[face[0]-p.dx*.08,height,face[2]-p.dz*.08];
    rod([e.x,height,e.z],face,r,paint.case);rod(neck,face,r*1.65,paint.steel);
    if(p.mate)route([face,pointAt(face,elevation(byId.get(p.mate)))],r,paint.pipe)
   }
   part(sphere(),e.x,height,e.z,r*1.5,r*1.45,r*1.5,paint.case);
   rod([e.x,height,e.z],[e.x,height+r*3.1,e.z],r*.38,paint.iron);
   part(ring(),e.x,height+r*3.1,e.z,r*1.65,r*1.65,r*1.65,paint.wheel,Math.PI/2);
   e.blockSource='CAD 双接口角阀';continue
  }
  if(f==='gauge'){
   if(!e.tap){e.blockSource=e.panel?'盘面压力指示 · 见图纸':'取压点待核 · 见图纸';continue}
   const host=byId.get(e.tap.other);
   const [tx,,tz]=e.tap.point,h=elevation(host);
   const size=clamp(Math.min(e.width,e.depth)*.95,.62,1.55);
   const barrel=host.family==='pipe'?pipeRadius(host):.13;
   let x=tx,z=tz;
   const tube=Math.min(barrel,.06*size);
   const seat=h+Math.max(barrel+.19*size,3*tube);
   const ends=host.paths.flatMap(run=>[[run[0],run[1]],[run.at(-1),run.at(-2)]]);
   const end=ends.find(([p])=>Math.hypot(p[0]-tx,p[2]-tz)<.008);
   if(end){
    const [p,q]=end,dx=p[0]-q[0],dz=p[2]-q[2],length=Math.hypot(dx,dz);
    if(length>.001){x+=dx/length*2*tube;z+=dz/length*2*tube}
   }
   route([[tx,h,tz],[x,h,z],[x,seat,z]],tube,paint.smallPipe);
   if(!end)rod([x,h+barrel*.6,z],[x,h+barrel+.06*size,z],.092*size,paint.iron);
   rod([x,seat-.075*size,z],[x,seat+.018*size,z],.085*size,paint.brass);
   const asset=blocks.get('gauge');
   placement.makeTranslation(x,seat,z);
   const calibration=asset && globalThis.PidProject?.gauges?.[asset.entry.asset];
   if(calibration)placement.multiply(new T.Matrix4().makeRotationY(calibration.yaw));
   placement.scale(new T.Vector3(size,size,size));
   if(calibration)placement.multiply(new T.Matrix4().makeTranslation(...calibration.offset));
   if(asset)put(asset.g,new T.Matrix4(),0xffffff);else instrument('gauge');
   const location=host.lineTags?.[0]||(host.family==='pipe'?(host.description==='仪表气管'?'仪表气管':'管段'):host.label);
   e.blockSource='取压接口 · '+location+'（'+host.handle+'）';
   e.labelHeight=seat+size;continue
  }
  if(e.tap){
   const tip=pointAt(e.tap.point,elevation(byId.get(e.tap.other)));
   route([tip,[e.x,tip[1],e.z],[e.x,height,e.z]],.055,paint.smallPipe)
  }
  if(f==='nozzle'){nozzle(e);continue}
  if(/^(exchanger|vessel|tank|filter)$/.test(f)){
   const layout=PidScene.vesselLayout(e);
   e.labelHeight=layout.top;
   placement.compose(new T.Vector3(e.x,layout.center,e.z),new T.Quaternion().setFromAxisAngle(axis,layout.upright?0:-e.angle),new T.Vector3(1,1,1));
   vessel(f,layout);e.blockSource='参数化构件';continue
  }
  const equipment=e.kind==='设备';
  const inline=e.kind==='阀门'||e.kind==='管件';
  if(inline&&!e.connected){e.blockSource='待核对管段接口';continue}
  for(const socket of e.sockets||[]){
   const other=elevation(byId.get(socket.other));
   const face=socket.face||socket.point;
   route([pointAt(socket.point,other),pointAt(face,other),pointAt(face,height)],.14,paint.pipe)
  }
  const size=equipment?clamp(e.span||3.3,1.4,28):inline?clamp(e.span||Math.max(e.width,e.depth),.26,1.25):clamp(Math.min(e.width,e.depth)*.95,.62,1.55);
  const asset=blocks.get(f);
  if(e.kind==='阀门'&&f!=='plug'&&e.span){
   const axisX=Math.cos(e.angle),axisZ=Math.sin(e.angle);
   const mates=new Map();
   if(e.hostPipe){mates.set(-1,byId.get(e.hostPipe));mates.set(1,byId.get(e.hostPipe))}
   for(const s of e.sockets||[]){
    const face=s.face||s.point;
    mates.set((face[0]-e.x)*axisX+(face[2]-e.z)*axisZ>0?1:-1,byId.get(s.other))
   }
   for(const [side,pipe] of mates){
    if(pipe.kind==='阀门')continue;
    const radius=pipeRadius(pipe),outer=Math.max(radius*1.55,size*(f==='check'?.28:.30));
    const p=d=>[e.x+side*axisX*(e.span/2+d),height,e.z+side*axisZ*(e.span/2+d)];
    const thickness=Math.min(.08,e.span*.09);
    rod(p(0),p(thickness),outer,paint.steel);
    rod(p(thickness),p(thickness*2.4),radius*1.15,paint.case);
    for(let n=0;n<8;n++){
     const a=(n+.5)*Math.PI/4,dy=outer*.78*Math.sin(a),cross=outer*.78*Math.cos(a);
     const bolt=d=>{const q=p(d);return [q[0]-axisZ*cross,q[1]+dy,q[2]+axisX*cross]};
     rod(bolt(-thickness*.35),bolt(thickness*1.25),Math.max(.012,outer*.075),paint.iron)
    }
   }
  }
  // Calibrated flange faces of the reused solids in template coordinates.
  const faceSpan=f==='sdv'&&asset?.entry.units==='m'?.74:f==='bdv'&&asset?.entry.units==='m'?.46:f==='ball'&&asset?.entry?.platform==='K 平台'?.9932:f==='flange'?(asset?.entry?.platform==='K 平台'?.4286:.16):1;
  const axial=inline&&e.span?e.span/faceSpan:size;
  const socketY=f==='ball'&&asset?.entry?.platform==='K 平台'?.1293:0;
  const y=equipment?(f==='skid'?.22:Math.max(1,size*.30)):height-socketY*size;
  e.labelHeight=y+size*.55;
  placement.compose(new T.Vector3(e.x,y,e.z),new T.Quaternion().setFromAxisAngle(axis,-e.angle),new T.Vector3(axial,size,size));
  e.blockSource=asset?asset.entry.platform+'构件 · '+({ball:'球阀',gauge:'压力表',check:'止回阀',flange:'法兰',pump:'泵',gate:'闸阀',sdv:'关断阀',bdv:'泄压阀',psv:'安全阀'}[f]):'参数化构件';
  if(e.kind==='阀门'&&f!=='plug'&&e.sockets?.length===1)e.blockSource+=' · 另一端待核';
  if(f==='assembly'&&e.geometry){
   const bottom=Math.min(...e.geometry.map(([,x,y,z,w,h])=>y-h/2));
   const top=Math.max(...e.geometry.map(([,x,y,z,w,h])=>y+h/2));
   placement.compose(new T.Vector3(e.x,.1-bottom*size,e.z),new T.Quaternion().setFromAxisAngle(axis,-e.angle),new T.Vector3(size,size,size));
   for(const [shape,x,y,z,w,h,d] of e.geometry){
    if(shape==='box')part(box(),x,y,z,w,h,d,paint.case);
    else if(shape==='ellipsoid')part(sphere(),x,y,z,w/2,h/2,d/2,paint.steel);
    else if(shape==='cylinderX')part(cyl(),x,y,z,h/2,w,d/2,paint.steel,0,0,Math.PI/2);
    else part(cyl(),x,y,z,w/2,h,d/2,paint.steel)
   }
   e.labelHeight=.1+(top-bottom)*size;e.blockSource='AI 组合几何 · 示意比例';continue
  }
  if(f==='meteringpump'){
   const base=blocks.get('pump');
   if(base)put(base.g,new T.Matrix4(),0xffffff);else pump('pump');
   part(box(),-.37,.12,.23,.25,.32,.1,paint.case);
   for(const yy of [-.04,.31])rod([-.37,yy,.23],[-.37,yy+.09,.23],.075,paint.brass);
   for(const xx of [-.46,-.28])for(const yy of [.02,.23])
    rod([xx,yy,.27],[xx,yy,.30],.022,paint.iron);
   e.blockSource='加药泵 · 泵头与驱动示意';continue
  }
  if(['cap','coupling','dampener','flowelement'].includes(f)){
   rod([-.45,0,0],[.45,0,0],f==='cap'?.28:.22,paint.steel);
   if(f==='cap'){
    part(sphere(),.36,0,0,.16,.28,.28,paint.case);
    rod([-.44,0,0],[-.34,0,0],.31,paint.iron)
   }else if(f==='dampener'){
    rod([0,.09,0],[0,.32,0],.12,paint.brass);
    rod([0,.31,0],[0,.77,0],.25,paint.steel);
    for(const y of [.32,.77])part(sphere(),0,y,0,.25,.16,.25,paint.steel);
   }else{
    for(const x of [-.32,.32])rod([x-.06,0,0],[x+.06,0,0],.30,paint.iron);
    if(f==='flowelement')rod([0,.16,0],[0,.4,0],.065,paint.brass)
   }
   e.blockSource='CAD 图块 · '+({cap:'端帽',coupling:'接头',dampener:'脉动阻尼器',flowelement:'流量元件'}[f]);continue
  }
  if(asset){put(asset.g,new T.Matrix4(),['sdv','bdv','psv'].includes(f)?safetyRed:0xffffff);continue}
  if(f==='plug'){rod([-.5,0,0],[.30,0,0],.32,paint.steel);rod([.24,0,0],[.5,0,0],.43,paint.iron)}
  else if(f==='reducer')rod([-.5,0,0],[.5,0,0],.24,paint.steel,cone());
  else if(e.kind==='阀门')valve(f);
  else if(f==='flange')flange(0,0,0,.5);
  else if(e.kind==='仪表')instrument(f);
  else if(f==='pump'||f==='compressor')pump(f);
  else if(f==='skid'){for(const z of [-.28,.28])part(box(),0,0,z,1,.058,.05,paint.base);
   for(const x of [-.47,0,.47])part(box(),x,0,0,.055,.052,.53,paint.base)}
 }
 for(const [g,families] of batches)for(const [material,recs] of families){
  const mesh=new T.InstancedMesh(g,material,recs.length);mesh.castShadow=true;mesh.receiveShadow=true;
  mesh.userData.ids=recs.map(r=>r.id);
  recs.forEach((r,j)=>{mesh.setMatrixAt(j,r.matrix);mesh.setColorAt(j,r.color)});
  mesh.computeBoundingBox();mesh.computeBoundingSphere();root.add(mesh)
 }
 return {pieces,byId,labels}
}
