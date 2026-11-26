import {paintSafetyNodes} from './safety-paint.js';
import * as T from 'three';
import {ReviewOutlines} from './review-outlines.js';
import {SceneLight} from './scene-light.js';
import {OrbitControls} from './OrbitControls.js';

const v=(a)=>new T.Vector3(...a);
const box=(a,b)=>new T.Box3(v(a),v(b));
const unpackBox=a=>a&&box(a.slice(0,3),a.slice(3));
const worldUp=new T.Vector3(0,1,0);
const forward=new T.Vector3(0,0,-1);
const navToWorld=p=>new T.Vector3(p.x,p.z,-p.y);
const toBytes=hex=>new T.Color(hex).toArray().map(x=>Math.round(x*255));
const twinHighlight=toBytes('#eb792c'),reviewHighlight=toBytes('#58c769');

export class NwdRenderer {
 constructor(canvas,tree,index,asset,onPick,onProgress,onFrame,native=false,presentation=native){
  Object.assign(this,{native,presentation,canvas,tree,index,asset,onPick,onProgress,onFrame});
  this.gl=new T.WebGLRenderer({canvas,antialias:true,alpha:true,preserveDrawingBuffer:true});
  this.gl.setPixelRatio(Math.min(presentation?2:1.65,devicePixelRatio));this.gl.localClippingEnabled=true;
  this.scene=new T.Scene();this.camera=new T.PerspectiveCamera(42,1,.025,4000);
  this.control=new OrbitControls(this.camera,canvas);this.control.minDistance=.06;this.control.zoomToCursor=!native;
  this.control.addEventListener('change',()=>{this.draw();this.queueDetail()});
  this.renderer=this.gl;
  if(native){this.light=new SceneLight(this)}
  else{
  this.scene.add(new T.HemisphereLight(0xffffff,0xb2b9bd,2.0));
  const sun=new T.DirectionalLight(0xfffcf1,2.0);sun.position.set(30,65,38);this.scene.add(sun);
  }
  const solid={vertexColors:true,flatShading:true,side:T.DoubleSide};
  this.paint=presentation?new T.MeshStandardMaterial({...solid,roughness:.86,metalness:0}):
   new T.MeshPhongMaterial({...solid,shininess:12,specular:0x1d2328,polygonOffset:true,polygonOffsetFactor:1,polygonOffsetUnits:1});
  this.pointMaterial=new T.PointsMaterial({vertexColors:true,size:3,sizeAttenuation:false});
  this.pen=new T.LineBasicMaterial({vertexColors:true});
  this.ghostPaint=new T.MeshBasicMaterial({color:0x677d8c,transparent:true,opacity:.10,wireframe:true,depthWrite:false});
  this.ghostPen=new T.LineBasicMaterial({color:0x677d8c,transparent:true,opacity:.12,depthWrite:false});
  this.materials=[this.paint,this.pen,this.pointMaterial,this.ghostPaint,this.ghostPen];this.groups=new Set();this.detailTiles=new Set();this.transparent=new Map();this.selected=-1;this.iso=-1;
  this.mask=new Uint8Array(tree.length);this.rootBox=unpackBox(tree[0][4]);
  this.boundsSphere=this.rootBox.getBoundingSphere(new T.Sphere());this.viewDirection=new T.Vector3();
  this.context=!presentation;
  this.tiles=index.tiles.map((t,id)=>({...t,id,box:box(t.min,t.max),groups:[],loaded:new Set(),preview:new Set(),covered:new Set()}));
  if(index.outlines?.length)this.outlines=new ReviewOutlines(this,index.outlines);
  this.jobs=new Map();this.detailFocus=new T.Vector2();
  canvas.addEventListener('wheel',event=>{
   const rect=canvas.getBoundingClientRect();
   this.detailFocus.set((event.clientX-rect.left)*2/rect.width-1,1-(event.clientY-rect.top)*2/rect.height)
  },{passive:true});
  canvas.addEventListener('pointerdown',()=>this.detailFocus.set(0,0));
  this.ray=new T.Raycaster();this.ray.params.Points.threshold=.05;this.ray.params.Line.threshold=.05;
  this.resize=new ResizeObserver(()=>{this.draw();this.queueDetail()});this.resize.observe(canvas);
  let down=null;
  canvas.addEventListener('pointerdown',e=>{if(e.button===0){down=[e.clientX,e.clientY];canvas.focus()}});
  canvas.addEventListener('pointerup',e=>{
   if(!this.control.enabled||e.button!==0||!down||Math.hypot(e.clientX-down[0],e.clientY-down[1])>4)return;
   down=null;if(!['orbit','measure','mark'].includes(this.mode))return;const rect=canvas.getBoundingClientRect();
   this.ray.setFromCamera(new T.Vector2(2*(e.clientX-rect.left)/rect.width-1,1-2*(e.clientY-rect.top)/rect.height),this.camera);
   const hits=this.ray.intersectObjects([...this.groups].filter(g=>g.visible).flatMap(g=>g.children.filter(o=>o.visible&&!o.userData.ghostOnly)),false);
   for(const hit of hits){
    if([this.plane,this.presetPlane].some(p=>p&&p.distanceToPoint(hit.point)<0))continue;
    const at=hit.object.isMesh?hit.faceIndex*3:hit.object.isPoints?hit.object.geometry.index.array.indexOf(hit.index):hit.index;
    const ends=hit.object.userData.hit;let lo=0,hi=ends.length/2;
    while(lo<hi){const mid=(lo+hi)>>1;if(ends[mid*2]<=at)lo=mid+1;else hi=mid}
    if(lo*2<ends.length){onPick(ends[lo*2+1],hit.point.toArray());return}
   }
   const outline=this.outlines?.pick(this.ray,this.camera);
   if(outline){onPick(outline.id,outline.point);return}
   if(this.mode==='orbit'&&this.selected>=0)onPick(-1,null)
  });
  canvas.addEventListener('keydown',e=>{
   if(this.mode!=='walk'||!['w','a','s','d','q','e','ArrowUp','ArrowDown','ArrowRight','ArrowLeft'].includes(e.key))return;
   e.preventDefault();const dir=this.camera.getWorldDirection(new T.Vector3()),right=dir.clone().cross(worldUp).normalize();
   const step=e.shiftKey?2:.45;
   const move=['w','ArrowUp'].includes(e.key)?dir:['s','ArrowDown'].includes(e.key)?dir.negate():['a','ArrowLeft'].includes(e.key)?right.negate():['d','ArrowRight'].includes(e.key)?right:worldUp.clone().multiplyScalar(e.key==='e'?1:-1);
   this.camera.position.addScaledVector(move,step);this.control.target.addScaledVector(move,step);this.control.update();this.draw()
  });
  canvas.addEventListener('pointermove',e=>{
   if(this.mode!=='walk'||!(e.buttons&1))return;
   const rotation=new T.Euler().setFromQuaternion(this.camera.quaternion,'YXZ');
   rotation.y-=e.movementX*.004;rotation.x=T.MathUtils.clamp(rotation.x-e.movementY*.004,-1.53,1.53);
   this.control.target.copy(forward).applyEuler(rotation).multiplyScalar(3).add(this.camera.position);this.control.update();this.draw()
  });
 }
 draw(){
  if(this.frame||this.inactive)return;
  this.frame=requestAnimationFrame(()=>{
   this.frame=0;const {clientWidth:w,clientHeight:h}=this.canvas;if(!w||!h)return;
   if(w!==this.width||h!==this.height){this.width=w;this.height=h;this.gl.setSize(w,h,false);this.camera.aspect=w/h;this.camera.updateProjectionMatrix()}
   // A fixed near plane of .025 loses centimetres of depth precision on distant decks.
   const sphere=this.boundsSphere,dir=this.camera.getWorldDirection(this.viewDirection);
   const depth=(sphere.center.x-this.camera.position.x)*dir.x+(sphere.center.y-this.camera.position.y)*dir.y+(sphere.center.z-this.camera.position.z)*dir.z;
   let front=Infinity;
   for(const {box:{min,max}} of this.tiles){
    const x=dir.x>=0?min.x:max.x,y=dir.y>=0?min.y:max.y,z=dir.z>=0?min.z:max.z;
    front=Math.min(front,(x-this.camera.position.x)*dir.x+(y-this.camera.position.y)*dir.y+(z-this.camera.position.z)*dir.z)
   }
   // Leave near-field room for water as well as the engineering geometry.
   const near=this.explode ? .025 : T.MathUtils.clamp(front*.35,.025,8),far=Math.max(this.native?6000:100,depth+sphere.radius+30,near+1);
   if(near!==this.camera.near||far!==this.camera.far){this.camera.near=near;this.camera.far=far;this.camera.updateProjectionMatrix()}
   this.light?.prepare();this.gl.render(this.scene,this.camera);this.onFrame(this.camera);
  })
 }
 cameraState(){return {eye:this.camera.position.toArray(),target:this.control.target.toArray(),up:this.camera.up.toArray(),fov:this.camera.fov}}
 setCamera(c){
  this.camera.position.fromArray(c.eye);this.camera.up.fromArray(c.up).normalize();this.control.target.fromArray(c.target);
  this.camera.fov=c.fov;this.camera.updateProjectionMatrix();this.control.update();this.draw();this.queueDetail()
 }
 preset(p){
  const q=new T.Quaternion(...p.rotation),pos=navToWorld(v(p.xyz));
  const dir=navToWorld(forward.clone().applyQuaternion(q)),up=navToWorld(new T.Vector3(0,1,0).applyQuaternion(q));
  this.setCamera({eye:pos.toArray(),target:pos.clone().addScaledVector(dir,5).toArray(),up:up.toArray(),fov:p.fov})
 }
 home(bounds){
  const b=bounds?unpackBox([...bounds.min,...bounds.max]):this.rootBox;
  this.fitBox(b,new T.Vector3(.9,.58,1.1))
 }
 fitBox(b,dir){
  if(!b)return;const c=b.getCenter(new T.Vector3());
  const d=dir||this.camera.position.clone().sub(this.control.target);
  if(d.lengthSq()<.001)d.set(1,.6,1);
  d.normalize();
  const right=new T.Vector3().crossVectors(worldUp,d);
  if(right.lengthSq()<1e-8)right.set(1,0,0);else right.normalize();
  const up=new T.Vector3().crossVectors(d,right);
  const aspect=Math.max(.1,this.canvas.clientWidth/Math.max(1,this.canvas.clientHeight));
  const tan=Math.tan(42*Math.PI/360),half=b.getSize(new T.Vector3()).multiplyScalar(.5);
  const corner=new T.Vector3();let distance=.3;
  for(const x of [-half.x,half.x])for(const y of [-half.y,half.y])for(const z of [-half.z,half.z]){
   corner.set(x,y,z);
   const span=Math.max(Math.abs(corner.dot(right))/aspect,Math.abs(corner.dot(up)));
   distance=Math.max(distance,corner.dot(d)+1.1*span/tan)
  }
  this.setCamera({eye:c.clone().addScaledVector(d,distance).toArray(),target:c.toArray(),up:up.toArray(),fov:42})
 }
 fit(id){this.fitBox(id>=0?unpackBox(this.tree[id][4]):this.rootBox)}
 face(key){
  const dir={front:[0,0,1],back:[0,0,-1],left:[-1,0,0],right:[1,0,0],top:[0,1,.00001],bottom:[0,-1,.00001]}[key];
  const c=this.control.target.clone(),dist=c.distanceTo(this.camera.position);
  this.setCamera({eye:c.clone().addScaledVector(v(dir),dist).toArray(),target:c.toArray(),up:[0,1,0],fov:this.camera.fov})
 }
 modeTo(mode){this.mode=mode;this.control.enableRotate=mode!=='walk';this.control.mouseButtons.LEFT=mode==='pan'?T.MOUSE.PAN:mode==='zoom'?T.MOUSE.DOLLY:T.MOUSE.ROTATE;this.canvas.focus()}
 section(c){
  const key=c?c.axis+'/'+c.value:'';
  if(this.lastSection===key&&this.lastPresetPlane===this.presetPlane)return;
  this.lastSection=key;this.lastPresetPlane=this.presetPlane;
  this.plane=c?new T.Plane(new T.Vector3(-(c.axis==='x'),-(c.axis==='y'),-(c.axis==='z')),c.value):null;
  if(this.outlines)this.outlines.material.clippingPlanes=[this.presetPlane,this.plane].filter(Boolean);
  const materials=new Set(this.materials);
  if(this.native)for(const group of this.groups)for(const o of group.children)materials.add(o.material);
  for(const m of materials){m.clippingPlanes=[this.presetPlane,this.plane].filter(Boolean);m.needsUpdate=true}
  if(this.light)this.light.dirty=true;this.draw()
 }
 attachMembers(buffer){
  const ids=new Uint32Array(buffer);let off=0;
  for(const t of this.tiles){t.members=t.pages.map(()=>{const n=ids[off++],part=ids.subarray(off,off+n);off+=n;return part})}
  if(off!==ids.length)throw Error('图层分块索引无效')
 }
 includesNode(ids,id){
  if(id<0||!ids)return true;
  let lo=0,hi=ids.length;
  while(lo<hi){const mid=(lo+hi)>>1;if(ids[mid]<id)lo=mid+1;else hi=mid}
  return lo<ids.length&&ids[lo]<=this.tree[id][1]
 }
 filter(hidden,removed,iso,selected){
  if(!this.native&&iso!==this.iso){
   for(const job of this.jobs?.values()||[])job.controller.abort();
   for(const tile of this.tiles||[])this.clearTile(tile)
   this.detailTiles.clear()
  }
  this.explicitMask=hidden.length>0||removed.length>0;this.hasMask=iso>=0||this.explicitMask;this.iso=iso;this.selected=selected;if(this.light)this.light.dirty=true;const ranges=this.tree,mask=this.mask;mask.fill(0);
  if(iso>=0){mask.fill(1,0,iso);mask.fill(1,ranges[iso][1]+1)}
  for(const list of [hidden,removed])for(const id of list)mask.fill(2,id,ranges[id][1]+1);
  if(this.presentation&&this.outlines)this.lineFilterKey=[hidden.join(','),removed.join(','),this.context?-1:iso].join('/');
  this.outlines?.update();
  for(const group of this.groups)this.updateGroup(group);
  this.queueDetail();this.draw()
 }
 invalidate(){this.draw()}
 attachPlatformGroup(group){
  for(const object of group.children){
   const geo=object.geometry,runs=object.userData.sourceRuns;
   if(!runs?.length||runs.at(-2)!==geo.index.count)throw Error('平台分块缺少源构件映射，请重新导入。');
   if(object.isMesh)paintSafetyNodes(this.tree,runs,geo.index.array,geo.attributes.color.array);
   object.userData={runs,hit:runs,original:geo.index.array,base:geo.attributes.color.array,color:geo.attributes.color.array,lastSelected:-1};
   geo.computeBoundingSphere()
  }
  this.groups.add(group);this.updateGroup(group);
  if(this.explode)this.explodeGroup(group,this.explode)
 }
 detachPlatformGroup(group){this.groups.delete(group)}
 updateGroup(group){
  for(const mesh of [...group.children]){
   if(mesh.userData.ghostOnly)continue;
   const g=mesh.geometry,data=mesh.userData;
   const {runs}=data;
   if(this.presentation&&this.outlines&&!this.explode){
    // Most native meshes lie wholly outside a small isolated component. Keep
    // their original GPU buffers intact; the context comes from CAD outlines.
    const solidOff=(this.wireOnly&&this.iso<0)||(this.iso>=0&&!runs.some((id,i)=>i%2===1&&!this.mask[id]));
    if(solidOff){mesh.visible=false;data.hit=[];data.outlineOnly=true;if(data.ghost)data.ghost.visible=false;continue}
    if(data.outlineOnly){mesh.visible=true;data.outlineOnly=false}
   }else if(data.outlineOnly){mesh.visible=true;data.outlineOnly=false}
   if(!this.native&&data.originalMaterial?.transparent)mesh.material=this.iso>=0?(mesh.isMesh?this.paint:mesh.isPoints?this.pointMaterial:this.pen):data.originalMaterial;
   if(data.lastSelected!==this.selected){
    if(data.lastSelected>=0&&data.color!==data.base)data.color.set(data.base);
    const endNode=this.selected>=0?this.tree[this.selected][1]:-1;
    let matched=false,from=0;
    for(let i=0;i<runs.length&&this.selected>=0;i+=2){
     const end=runs[i],id=runs[i+1];
     if(id>=this.selected&&id<=endNode){
      if(data.color===data.base)data.base=data.color.slice();
      for(let k=from;k<end;k++)data.color.set(this.presentation?twinHighlight:reviewHighlight,data.original[k]*3);
      matched=true
     }
     from=end
    }
    if(matched||data.lastSelected>=0)g.attributes.color.needsUpdate=true;
    data.lastSelected=matched?this.selected:-1
   }
   const needsFilter=this.hasMask&&(!this.native||runs.some((id,i)=>i%2===1&&this.mask[id]));
   if(this.native&&!needsFilter&&!data.filtered){data.hit=runs;continue}
   if(this.native&&data.original===g.index.array)data.original=g.index.array.slice();
   const original=data.original;data.filtered=needsFilter;
   let offset=0,write=0,ghostCount=0;const hits=[];
   const ghostOn=!mesh.isPoints&&(!this.outlines||this.explode)&&this.iso>=0&&this.context&&(this.native||!!data.tileIds);
   if(ghostOn&&!data.ghost){
    const geom=new T.BufferGeometry();geom.setAttribute('position',g.attributes.position);geom.setIndex(new T.BufferAttribute(new Uint32Array(original.length),1));
    const ghost=mesh.isMesh?new T.Mesh(geom,this.ghostPaint):new T.LineSegments(geom,this.ghostPen);
    ghost.userData.ghostOnly=true;ghost.raycast=()=>{};data.ghost=ghost;group.add(ghost)
   }
   for(let i=0;i<runs.length;i+=2){
    const end=runs[i],id=runs[i+1];
    const tileId=data.tileIds?.[i/2],tile=this.tiles?.[tileId];
    if(!this.mask[id]&&(this.detailTiles.has(tileId)||tile?.covered?.has(id))){offset=end;continue}
    if(data.detailTile?.preview.has(id)&&!data.detailTile.covered.has(id)&&!this.detailTiles.has(data.detailTile.id)){offset=end;continue}
    if(!this.mask[id]){
     g.index.array.set(original.subarray(offset,end),write);write+=end-offset;hits.push(write,id)
    }else if(ghostOn&&this.mask[id]===1){data.ghost.geometry.index.array.set(original.subarray(offset,end),ghostCount);ghostCount+=end-offset}
    offset=end
   }
   if(data.ghost){data.ghost.visible=ghostCount>0;data.ghost.geometry.setDrawRange(0,ghostCount);data.ghost.geometry.index.needsUpdate=true}
   g.setDrawRange(0,write);g.index.needsUpdate=true;data.hit=hits;mesh.visible=write>0
  }
 }
 unpack(buffer,detailTile=null){
  const len=new DataView(buffer).getUint32(0,true),spec=JSON.parse(new TextDecoder().decode(new Uint8Array(buffer,4,len)));
  let at=4+Math.ceil(len/4)*4;const group=new T.Group();
  function take(type,n){const arr=new type(buffer,at,n);at+=Math.ceil(arr.byteLength/4)*4;return arr}
  for(const [mode,n,ni,nr,origin,scale,alpha=1,hasTiles=false,full=false] of spec){
   let xyz=take(full?Float32Array:Uint16Array,n*3),rgb=take(Uint8Array,n*3),indices=take(Uint32Array,ni),runs=take(Uint32Array,nr*2);
   const tileIds=hasTiles?take(Uint32Array,nr):null;
   if(full&&!this.native&&this.iso>=0){
    const last=this.tree[this.iso][1],spans=[],kept=[];let start=0,count=0;
    for(let i=0;i<runs.length;i+=2){
     const end=runs[i],id=runs[i+1];
     if(id>=this.iso&&id<=last){spans.push([start,end]);count+=end-start;kept.push(count,id)}
     start=end
    }
    if(!count)continue;
    if(count<ni){
     const remap=new Uint32Array(n),next=new Uint32Array(count),vertices=[];let offset=0;
     for(const [from,to] of spans)for(let j=from;j<to;j++){
      const old=indices[j];if(!remap[old])remap[old]=vertices.push(old);
      next[offset++]=remap[old]-1
     }
     const pos=new Float32Array(vertices.length*3),colors=new Uint8Array(vertices.length*3);
     vertices.forEach((old,i)=>{for(let k=0;k<3;k++){pos[i*3+k]=xyz[old*3+k];colors[i*3+k]=rgb[old*3+k]}});
     xyz=pos;rgb=colors;indices=next;runs=Uint32Array.from(kept)
    }
   }
   if(tileIds&&this.tiles)for(let i=0;i<nr;i++)this.tiles[tileIds[i]]?.preview?.add(runs[i*2+1]);
   const g=new T.BufferGeometry(),pos=full?xyz:new Float32Array(n*3);
   if(!full)for(let i=0;i<pos.length;i+=3)for(let j=0;j<3;j++)pos[i+j]=origin[j]+xyz[i+j]*scale[j]/65535;
   const color=rgb.slice();
   if(mode===4)paintSafetyNodes(this.tree,runs,indices,color);
   g.setAttribute('position',new T.BufferAttribute(pos,3));g.setAttribute('color',new T.BufferAttribute(color,3,true));
   g.setIndex(new T.BufferAttribute(indices.slice(),1));g.computeBoundingSphere();
   let material=mode===4?this.paint:mode===0?this.pointMaterial:this.pen;
   if(alpha<1){
    const key=mode+'/'+alpha;if(!this.transparent.has(key)){
     const m=material.clone();m.transparent=true;m.opacity=alpha;m.depthWrite=false;
     this.transparent.set(key,m);this.materials.push(m)
    }material=this.transparent.get(key)
   }
   const mesh=mode===4?new T.Mesh(g,material):mode===0?new T.Points(g,material):new T.LineSegments(g,material);
   mesh.userData={original:indices,runs,tileIds,base:color,color,lastSelected:-1,originalMaterial:material,detailTile};group.add(mesh)
  }
  if(at!==buffer.byteLength)throw Error('几何分块数据不完整');
  this.groups.add(group);this.scene.add(group);this.updateGroup(group);if(this.explode)this.explodeGroup(group,this.explode);this.draw();return group
 }
 explodeGroup(group,value){
  const center=this.rootBox.getCenter(new T.Vector3());
  for(const m of group.children){
   if(m.userData.ghostOnly)continue;
   const attr=m.geometry.attributes.position,d=m.userData;
   if(!d.rest)d.rest=attr.array.slice();
   attr.array.set(d.rest);
   if(value){let start=0;for(let i=0;i<d.runs.length;i+=2){
    let id=d.runs[i+1];while(this.tree[id][0]>0&&this.tree[this.tree[id][0]][0]>0)id=this.tree[id][0];
    const b=this.tree[id][4];if(b){
     const delta=[0,1,2].map(j=>((b[j]+b[j+3])*.5-center.getComponent(j))*value);
     for(let k=start;k<d.runs[i];k++){const vertex=d.original[k]*3;for(let j=0;j<3;j++)attr.array[vertex+j]=d.rest[vertex+j]+delta[j]}
    }start=d.runs[i]
   }}
   attr.needsUpdate=true;m.geometry.computeBoundingSphere();if(!value)delete d.rest
  }
 }
 separate(value){if(value===(this.explode||0))return;this.explode=value;this.outlines?.update();if(this.light)this.light.dirty=true;for(const group of this.groups)this.explodeGroup(group,value);if(this.outlines){for(const group of this.groups)this.updateGroup(group);this.queueDetail()}this.draw()}
 release(g){this.groups.delete(g);this.scene.remove(g);for(const m of g.children)m.geometry.dispose()}
 clearTile(tile){
  for(const group of tile.groups)this.release(group);
  const partial=!!tile.covered?.size;tile.groups=[];tile.loaded?.clear();tile.covered?.clear();tile.remaining=null;
  return this.detailTiles.delete(tile.id)||partial
 }
 queueDetail(delay=45){
  if(this.inactive||!this.ready)return;
  if(this.native){
   this.platformRefine?.();
   if(this.outlines?.group.visible&&!this.outlineFrame)this.outlineFrame=requestAnimationFrame(()=>{
    this.outlineFrame=0;if(!this.outlines.group.visible||this.inactive)return;
    this.camera.updateMatrixWorld();this.outlines.schedule(new T.Frustum().setFromProjectionMatrix(new T.Matrix4().multiplyMatrices(this.camera.projectionMatrix,this.camera.matrixWorldInverse)))
   });
   return
  }
  if(this.timer)return;
  this.timer=setTimeout(()=>{this.timer=0;this.refine()},delay)
 }
 refine(){
  if(!this.ready||this.inactive)return;
  this.camera.updateMatrixWorld();
  const frustum=new T.Frustum().setFromProjectionMatrix(new T.Matrix4().multiplyMatrices(this.camera.projectionMatrix,this.camera.matrixWorldInverse));
  const focusRay=new T.Raycaster();focusRay.setFromCamera(this.detailFocus,this.camera);
  const sphere=new T.Sphere(),isolate=this.iso>=0?unpackBox(this.tree[this.iso][4]):null;
  const near=[];
  for(const tile of this.tiles){
   if(!frustum.intersectsBox(tile.box)||(isolate&&!tile.box.intersectsBox(isolate)))continue;
   const distance=tile.box.distanceToPoint(this.camera.position);tile.box.getBoundingSphere(sphere);
   if(!this.full&&!isolate&&sphere.radius*this.height/(Math.tan(this.camera.fov*Math.PI/360)*Math.max(.01,distance))<100)continue;
   const lateral=Math.max(0,focusRay.ray.distanceToPoint(sphere.center)-sphere.radius*.5);
   near.push({tile,score:distance+3*lateral})
  }
  near.sort((a,b)=>a.score-b.score);
  let budget=this.full?18000000:6500000;
  const wanted=new Set(),waiting=[];
  for(const {tile} of near){
   if(budget<=0)break;
   const pages=[];
   for(let i=0;i<tile.pages.length;i++)if(this.includesNode(tile.members?.[i],this.iso))pages.push(i);
   if(!pages.length)continue;
   budget-=tile.count*pages.length/tile.pages.length;wanted.add(tile);
   if(!tile.remaining){
    tile.remaining=new Map();
    if(tile.members)for(const i of pages)for(const id of tile.members[i])if(tile.preview.has(id))tile.remaining.set(id,1+(tile.remaining.get(id)||0))
   }
   for(const page of pages){
    const key=tile.id+'/'+page;
    if(!tile.loaded.has(page)&&!this.jobs.has(key)&&!(tile.retry>Date.now()))waiting.push({tile,page,key,total:pages.length})
   }
  }
  let refresh=false;
  for(const job of this.jobs.values())if(!wanted.has(job.tile))job.controller.abort();
  for(const t of this.tiles)if(!wanted.has(t)&&t.remaining)refresh=this.clearTile(t)||refresh;
  if(refresh)this.updateGroup(this.overview);
  for(const job of waiting){
   if(this.jobs.size>=3)break;
   job.controller=new AbortController();this.jobs.set(job.key,job);this.loadPage(job)
  }
  this.outlines?.schedule(frustum);
  this.onProgress(this.jobs.size?'正在细化当前视野':this.full?'可见区域原始精度':'自适应精度')
 }
 async loadPage(job){
  const {tile,page,key,controller,total}=job;
  try{
   const raw=await this.asset(tile.pages[page],controller.signal);
   if(controller.signal.aborted||this.inactive)return;
   const group=this.unpack(raw,tile);tile.groups.push(group);tile.loaded.add(page);
   let refresh=false;
   for(const id of tile.members?.[page]||[]){
    const left=tile.remaining.get(id);
    if(left===1){tile.remaining.delete(id);tile.covered.add(id);refresh=true}
    else if(left>1)tile.remaining.set(id,left-1)
   }
   if(tile.loaded.size===total){this.detailTiles.add(tile.id);refresh=true}
   if(refresh){
    this.updateGroup(this.overview);for(const g of tile.groups)this.updateGroup(g)
   }
   this.draw()
  }catch(error){
   if(!controller.signal.aborted){tile.retry=Date.now()+2000;this.onProgress('细节读取失败，移动视角可重试');console.warn(error)}
  }finally{this.jobs.delete(key);this.queueDetail(8)}
 }
 project(point){return v(point).project(this.camera)}
 measure(a,b){
  this.clearMeasurement();
  const g=new T.BufferGeometry().setFromPoints([v(a),v(b)]);this.line=new T.Line(g,new T.LineBasicMaterial({color:0xe07223,depthTest:false}));this.line.renderOrder=9;this.scene.add(this.line);this.draw();return v(a).distanceTo(v(b))
 }
 clearMeasurement(){if(this.line){this.scene.remove(this.line);this.line.geometry.dispose();this.line.material.dispose();this.line=null}this.draw()}
}
