import * as T from 'three';
import {SceneLight} from './scene-light.js';
import {openPlatform} from './platform-scene.js';
import {buildSheet,loadBlocks} from './pid-blocks.js';
import {OrbitControls} from './OrbitControls.js';

const axisUp=new T.Vector3(0,1,0);
const colors={'设备':0xb1c9d1,'仪表':0x4d8ab0,'管线':0x268b90,'管线标注':0x4aa9aa,'阀门':0x467398,'构件':0x8298a8,'CAD 线元':0x778695};
// Preserve the selected object's material across the face. Amber concentrates at
// the silhouette while exposed bolts and lettering retain their own highlights.
const selectionPaint=new T.ShaderMaterial({
 transparent:true,depthWrite:false,side:T.DoubleSide,polygonOffset:true,polygonOffsetFactor:-2,
 vertexShader:`varying vec3 N,V;void main(){
  vec4 p=modelViewMatrix*vec4(position,1.);V=-p.xyz;N=normalMatrix*normal;
  gl_Position=projectionMatrix*p;
 }`,
 fragmentShader:`varying vec3 N,V;void main(){
  float edge=1.-abs(dot(normalize(N),normalize(V)));
  gl_FragColor=vec4(1.,.29,.012,.075+.80*pow(edge,2.6));
  #include <colorspace_fragment>
 }`
});
selectionPaint.userData.shared=true;
const activeColor=new T.Color(0xff822b);
const steel=new T.MeshStandardMaterial({metalness:.34,roughness:.45,side:T.DoubleSide,vertexColors:true});

export class ModelView{
 constructor(canvas,pick,changed){
  this.renderer=new T.WebGLRenderer({canvas,antialias:true,alpha:true,powerPreference:'high-performance'});
  this.renderer.setPixelRatio(Math.min(2,window.devicePixelRatio||1));
  this.canvas=canvas;this.pick=pick;
  this.labelLayer=document.createElement('div');this.labelLayer.className='model-labels';canvas.after(this.labelLayer);this.onChange=changed;this.scene=new T.Scene();
  this.camera=new T.PerspectiveCamera(36,1,.02,5000);
  this.control=new OrbitControls(this.camera,canvas);this.control.enableDamping=false;
  this.control.addEventListener('change',()=>this.invalidate());
  this.light=new SceneLight(this);
  this.root=new T.Group();this.overlay=new T.Group();this.region=new T.Group();this.scene.add(this.root,this.region,this.overlay);
  this.grid=new T.GridHelper(220,44,0xb5b4ad,0xd1cfc9);this.grid.material.transparent=true;this.grid.material.opacity=.15;this.scene.add(this.grid);
  this.bounds=new T.Box3();this.ray=new T.Raycaster();this.selected=null;
  this.observer=new ResizeObserver(()=>this.invalidate());this.observer.observe(canvas);
  let down=null;
  canvas.addEventListener('pointerdown',e=>{down=e.button===0?[e.clientX,e.clientY]:null});
  canvas.addEventListener('pointerup',e=>{
   if(this.platformDispose||!down||Math.hypot(e.clientX-down[0],e.clientY-down[1])>4)return;
   down=null;const r=canvas.getBoundingClientRect();
   this.ray.setFromCamera(new T.Vector2(2*(e.clientX-r.left)/r.width-1,1-2*(e.clientY-r.top)/r.height),this.camera);
   const hits=this.ray.intersectObjects([...this.overlay.children,...this.region.children,...this.root.children],true);
   for(const hit of hits){
    if(this.regionPick){this.regionPick(hit.point.toArray());break}
    const obj=hit.object;if(obj.isInstancedMesh&&obj.userData.ids){this.pick(obj.userData.ids[hit.instanceId]);break}
    if(obj.userData.id!=null){this.pick(obj.userData.id);break}
    if(obj.userData.ranges){const face=obj.isLineSegments?hit.index:hit.faceIndex*3,ranges=obj.userData.ranges;let lo=0,hi=ranges.length;
     while(lo<hi){const m=(lo+hi)>>1;if(ranges[m][0]<=face)lo=m+1;else hi=m}
     if(lo<ranges.length)this.pick(ranges[lo][1]);break}
   }
  });
  canvas.addEventListener('dblclick',()=>this.focus());
 }
 invalidate(){
  if(this.frame)return;
  this.frame=requestAnimationFrame(()=>{
   this.frame=0;const w=this.canvas.clientWidth,h=this.canvas.clientHeight;if(!w||!h)return;
   if(this.width!==w||this.height!==h){this.renderer.setSize(w,h,false);this.width=w;this.height=h}
   this.camera.aspect=w/h;this.camera.updateProjectionMatrix();this.light.prepare();
   this.renderer.render(this.scene,this.camera);this.positionLabels(w,h);this.onChange();
  });
 }
 positionLabels(w,h){
  const placed=[];
  for(const label of this.labelLayer.querySelectorAll('button')){
   const p=label.anchor.clone().project(this.camera),x=(p.x*.5+.5)*w,y=(.5-p.y*.5)*h;
   label.hidden=Math.abs(p.z)>1||x<0||x>w||y<0||y>h;
   if(label.leader)label.leader.style.display='none';
   if(label.hidden)continue;
   const half=Math.min(label.offsetWidth*.5,w*.5),cx=Math.max(half,Math.min(w-half,x)),lh=label.offsetHeight;
   const levels=label.leader?[0,-1,1,-2,2,-3,3,-4,4]:[0];
   let cy=null;
   for(const level of levels){
    const bottom=Math.max(lh+3,Math.min(h-29,y+level*(lh+3)));
    if(!placed.some(b=>Math.abs(b.x-cx)<b.half+half+3&&bottom>b.top-2&&bottom-lh<b.bottom+2)){cy=bottom;break}
   }
   label.hidden=cy===null;if(label.hidden)continue;
   label.style.left=cx+'px';label.style.top=cy+'px';
   placed.push({x:cx,half,top:cy-lh,bottom:cy});
   if(label.leader){
    for(const [attr,value] of Object.entries({x1:x,y1:y,x2:cx,y2:y>=cy?cy:cy-lh}))label.leader.setAttribute(attr,value);
    label.leader.style.display=''
   }
  }
 }
 disposeChildren(group){
  for(const child of [...group.children]){
   child.traverse(o=>{if(o.geometry&&!o.userData.borrowedGeometry&&!o.geometry.userData.shared)o.geometry.dispose();if(o.material&&o.material!==steel&&!o.material.userData.shared)o.material.dispose();if(o.isInstancedMesh)o.dispose()});
   group.remove(child);
  }
 }
 platform(id,signal,addButton,progress){return openPlatform(this,id,signal,addButton,progress)}
 clear(){this.platformDispose?.();this.platformDispose=null;this.light.set('sheet');this.labelLayer.replaceChildren();this.sheetVersion=(this.sheetVersion||0)+1;this.sheet=null;this.disposeChildren(this.root);this.disposeChildren(this.region);this.disposeChildren(this.overlay);this.selected=null;this.bounds.makeEmpty();this.invalidate()}
 cameraAt(box,angle=1){
  if(box.isEmpty())return;
  const center=box.getCenter(new T.Vector3()),size=box.getSize(new T.Vector3());
  const distance=Math.max(size.length()*.77,Math.max(...size.toArray())/(1.25*Math.max(.38,this.canvas.clientWidth/Math.max(this.canvas.clientHeight,1))),.7);
  const dir=angle===1?new T.Vector3(1,.66,1.28).normalize():this.camera.position.clone().sub(this.control.target).normalize();
  this.camera.position.copy(center).addScaledVector(dir,distance*1.85);this.control.target.copy(center);
  this.camera.near=Math.max(.006,distance/9000);this.camera.far=Math.max(1800,distance*40);this.camera.updateProjectionMatrix();this.control.update();this.invalidate()
 }
 reset(viewIndex=this.sheet?.viewIndex??0){
  if(!this.sheet||this.bounds.isEmpty()){this.cameraAt(this.bounds);return}
  this.sheet.viewIndex=viewIndex;
  const view=this.sheet.views?.[viewIndex];
  const bounds=view?.min?new T.Box3(new T.Vector3(...view.min),new T.Vector3(...view.max)):this.bounds;
  const center=bounds.getCenter(new T.Vector3()),dir=new T.Vector3(...(this.sheet.direction||[.78,.98,1.05])).normalize();
  const right=new T.Vector3().crossVectors(axisUp,dir).normalize(),up=new T.Vector3().crossVectors(dir,right);
  const aspect=Math.max(.15,this.canvas.clientWidth/Math.max(this.canvas.clientHeight,1)),tan=Math.tan(this.camera.fov*Math.PI/360);
  let distance=2;
  for(const x of [bounds.min.x,bounds.max.x])for(const y of [bounds.min.y,bounds.max.y])for(const z of [bounds.min.z,bounds.max.z]){
   const corner=new T.Vector3(x,y,z).sub(center);
   distance=Math.max(distance,corner.dot(dir)+1.08*Math.max(Math.abs(corner.dot(right))/(aspect*tan),Math.abs(corner.dot(up))/tan))
  }
  this.camera.position.copy(center).addScaledVector(dir,distance);this.control.target.copy(center);this.control.update();this.invalidate()
 }
 focus(){if(this.overlay.children.length){this.cameraAt(new T.Box3().setFromObject(this.overlay),0);return}if(this.selected!=null){const box=new T.Box3();this.root.traverse(o=>{if(o.userData.id===this.selected)box.expandByObject(o)});this.cameraAt(box,0)}}
 mesh(buffer,offset,palette,detailId=null,group=this.root){
  const len=new DataView(buffer).getUint32(offset,true),start=offset+4+len;
  const h=JSON.parse(new TextDecoder().decode(new Uint8Array(buffer,offset+4,len)));
  const pos=new Float32Array(buffer,start,h.vertices*3),idx=new Uint32Array(buffer,start+pos.byteLength,h.indices);
  const geom=new T.BufferGeometry();geom.setAttribute('position',new T.BufferAttribute(pos,3));geom.setIndex(new T.BufferAttribute(idx,1));geom.computeVertexNormals();
  const rgb=new Uint8Array(h.vertices*3);let prev=0;
  for(const [end,id] of h.ranges){const col=detailId!==null?activeColor:new T.Color(Array.isArray(palette[id])?palette[id][1]:(colors[palette[id]]||colors['构件']));
   const r=Math.round(col.r*255),g=Math.round(col.g*255),b=Math.round(col.b*255);
   for(let j=prev;j<end;j++){const k=3*idx[j];rgb[k]=r;rgb[k+1]=g;rgb[k+2]=b}prev=end}
  geom.setAttribute('color',new T.BufferAttribute(rgb,3,true));
  const obj=new T.Mesh(geom,steel);obj.castShadow=detailId===null;obj.receiveShadow=true;obj.userData.ranges=h.ranges;
  if(detailId!==null){obj.userData.id=detailId;obj.renderOrder=3;this.overlay.add(obj)}else group.add(obj);
  if(h.lines){
   const g=new T.BufferGeometry();
   g.setAttribute('position',new T.BufferAttribute(new Float32Array(buffer,start+pos.byteLength+idx.byteLength,h.lines*3),3));
   const line=new T.LineSegments(g,new T.LineBasicMaterial({color:detailId!==null?0xff8429:0x657f8a}));
   line.userData.ranges=h.lineRanges;if(detailId!==null)line.userData.id=detailId;
   (detailId!==null?this.overlay:group).add(line)
  }
  this.invalidate();return obj
 }
 overview(buffer,palette,info){
  this.clear();this.light.set('index');this.overviewMesh=this.mesh(buffer,0,palette);this.normalIndex=this.overviewMesh.geometry.index;this.normalRanges=this.overviewMesh.userData.ranges;this.palette=palette;
  const box=info.view||info.bounds;
  this.bounds.set(new T.Vector3(...box.min),new T.Vector3(...box.max));
  const center=this.bounds.getCenter(new T.Vector3());this.grid.position.set(center.x,this.bounds.min.y-.3,center.z);
  this.reset()
 }
 processOnly(on){
  const obj=this.overviewMesh;if(!obj||!this.root.children.includes(obj))return;
  if(on){
   const indices=this.normalIndex.array,ranges=[],parts=[];let start=0,total=0;
   for(const [end,id] of this.normalRanges){
    const kind=Array.isArray(this.palette[id])?this.palette[id][0]:this.palette[id];
    if(kind!=='构件'){parts.push(indices.subarray(start,end));total+=end-start;ranges.push([total,id])}
    start=end
   }
   const items=new Uint32Array(total);let at=0;for(const part of parts){items.set(part,at);at+=part.length}
   obj.geometry.setIndex(new T.BufferAttribute(items,1));obj.userData.ranges=ranges;
  }else{obj.geometry.setIndex(this.normalIndex);obj.userData.ranges=this.normalRanges}
  this.invalidate()
 }
 regionView(point){
  this.disposeChildren(this.region);const c=new T.Vector3(...point);
  const box=new T.Box3(c.clone().addScalar(-2.2),c.clone().addScalar(2.2));this.cameraAt(box,0);
 }
 clearDetail(){this.disposeChildren(this.overlay);this.selected=null;this.invalidate()}
 highlight(id){
  if(!this.sheet)return;
  this.selected=id;this.disposeChildren(this.overlay);
  const object=this.sheet.byId.get(id);
  const ids=object?.linked.length?object.linked:object?.run||[id];
  for(const key of ids)for(const part of this.sheet.pieces.get(key)||[]){
   const mesh=new T.Mesh(part.g,selectionPaint);mesh.matrixAutoUpdate=false;mesh.matrix.copy(part.matrix);
   mesh.userData.id=key;mesh.userData.borrowedGeometry=true;this.overlay.add(mesh)
  }
  this.invalidate();return this.overlay.children.length>0
 }
 addSheetLabels(){
  if(!this.sheet.labels?.length)return;
  const ns='http://www.w3.org/2000/svg',leaders=document.createElementNS(ns,'svg');leaders.setAttribute('aria-hidden','true');this.labelLayer.append(leaders);
  for(const {id,tag,anchor,ref,connection} of [...this.sheet.labels].sort((a,b)=>Number(!!b.connection)-Number(!!a.connection))){
   const label=document.createElement('button');label.type='button';label.textContent=tag;
   if(connection){
    label.className='pipe-end';const sheet=document.createElement('small');sheet.textContent=ref;label.append(sheet);
    label.leader=document.createElementNS(ns,'line');leaders.append(label.leader)
   }
   label.anchor=anchor;label.onclick=()=>this.pick(id);this.labelLayer.append(label)
  }
 }
 async authoredSheet(drawing,assembly=null){
  this.clear();const version=this.sheetVersion;
  const {build:builder,families}=globalThis.PidProject.loadAssembly(drawing,assembly);
  const [build,blocks]=await Promise.all([builder,loadBlocks(families)]);
  if(this.sheetVersion!==version)return;
  this.sheet=build(this.root,drawing,blocks,assembly);
  this.addSheetLabels();
  this.bounds.setFromObject(this.root);this.grid.position.set(0,-.14,0);
  this.light.dirty=true;this.reset();return !this.bounds.isEmpty()
 }
 async schematic(objects){
  this.clear();const version=this.sheetVersion;
  const families=new Set(objects.map(e=>e.family));
  if(objects.some(e=>e.kind==='阀门'||e.kind==='设备'))families.add('flange');
  if(families.has('meteringpump'))families.add('pump');
  const blocks=await loadBlocks(families);if(this.sheetVersion!==version)return;
  this.sheet=buildSheet(this.root,objects,blocks);this.light.dirty=true;this.addSheetLabels();
  for(const e of objects.filter(o=>o.kind==='设备'&&!o.annotation&&o.family!=='skid').sort((a,b)=>(b.span||0)-(a.span||0)).slice(0,10)){
   const label=document.createElement('button');label.type='button';label.textContent=e.label;label.title=e.description;
   label.anchor=new T.Vector3(e.x,e.labelHeight,e.z);label.onclick=()=>this.pick(e.handle);this.labelLayer.append(label)
  }
  this.bounds.setFromObject(this.root);this.grid.position.set(0,-.14,0);
  this.reset();return !this.bounds.isEmpty()
 }
}
