import {cachedAsset} from './asset-cache.js';
import * as T from 'three';
import {industrialMaterial} from './industrial-surfaces.js';

function unpack(buffer,material){
 const headerSize=new DataView(buffer).getUint32(0,true);
 const descriptions=JSON.parse(new TextDecoder().decode(new Uint8Array(buffer,4,headerSize)));
 let offset=4+Math.ceil(headerSize/4)*4;
 const group=new T.Group();
 for(const {vertices,indices,mode,alpha,finishes,nodes} of descriptions){
  const g=new T.BufferGeometry(),n=vertices*3;
  g.setAttribute('position',new T.BufferAttribute(new Float32Array(buffer,offset,n),3));offset+=n*4;
  g.setAttribute('normal',new T.BufferAttribute(new Int8Array(buffer,offset,n),3,true));offset+=Math.ceil(n/4)*4;
  g.setAttribute('color',new T.BufferAttribute(new Uint8Array(buffer,offset,n),3,true));offset+=Math.ceil(n/4)*4;
  g.setIndex(new T.BufferAttribute(new Uint32Array(buffer,offset,indices),1));offset+=indices*4;
  if(mode===4){
   const kinds=new Uint8Array(vertices);
   let start=0;
   for(let i=0;i<(finishes?.length||0);i+=2){kinds.fill(finishes[i+1],start,finishes[i]);start=finishes[i]}
   g.setAttribute('finishKind',new T.BufferAttribute(kinds,1))
  }
  const m=material(mode,alpha),obj=mode===4?new T.Mesh(g,m):new T.LineSegments(g,m);
  obj.userData.sourceRuns=nodes;obj.castShadow=mode===4&&alpha>=.9;obj.receiveShadow=mode===4;group.add(obj);
 }
 if(offset!==buffer.byteLength)throw Error('模型分块数据长度不符');
 return group
}

export async function openPlatform(view,id,signal,addButton,progress,manifest=null){
 const url='/api/platforms/'+id+'/';
 if(!manifest){
  const response=await fetch(url+'index.json',{signal});
  if(!response.ok)throw Error('平台模型目录读取失败');
  manifest=await response.json()
 }
 const {version,tiles,skylight}=manifest;signal.throwIfAborted();
 if(version!==1||!tiles.length)throw Error('平台模型目录无效');
 const root=new T.Group(),materials=new Map(),detail=new Map(),overviews=new Map();
 const plane=new T.Plane(new T.Vector3(0,-1,0),0);
 const bounds=new T.Box3();
 for(const tile of tiles){tile.box=new T.Box3(new T.Vector3(...tile.min),new T.Vector3(...tile.max));bounds.union(tile.box)}
 const presets=globalThis.PidProject?.views?.[id] || {all:["全模型"]};
 let cut=null,timer=0,busy=false,changed=false,ready=false,disposed=false;
 const controller=new AbortController();let sky=null;
 // clear() also releases partial loads and removes all platform-only render state.
 function dispose(){
  if(disposed)return;disposed=true;controller.abort();clearTimeout(timer);signal.removeEventListener('abort',dispose);
  view.control.removeEventListener('change',schedule);view.scene.remove(root);
  root.traverse(o=>o.geometry?.dispose());root.clear();for(const m of materials.values())m.dispose();
  sky?.skyVolume.value.dispose();detail.clear();overviews.clear();view.renderer.localClippingEnabled=false;if(view.grid)view.grid.visible=true;
  view.camera.fov=36;view.camera.updateProjectionMatrix();view.invalidate()
 }
 view.platformDispose=dispose;signal.addEventListener('abort',dispose,{once:true});
 if(view.grid)view.grid.visible=false;view.scene.add(root);view.renderer.localClippingEnabled=true;
 if(skylight&&Math.max(...skylight.size)<=view.renderer.getContext().getParameter(WebGL2RenderingContext.MAX_3D_TEXTURE_SIZE)){
  try{
   const response=await cachedAsset(url+skylight.asset,{signal:controller.signal});
   if(!response.ok)throw Error('甲板采光数据读取失败');
   const data=await response.arrayBuffer();controller.signal.throwIfAborted();
   if(data.byteLength!==skylight.size.reduce((n,v)=>n*v,1))throw Error('甲板采光数据不完整');
   const texture=new T.Data3DTexture(new Uint8Array(data),...skylight.size);
   texture.format=T.RedFormat;texture.minFilter=texture.magFilter=T.LinearFilter;texture.unpackAlignment=1;texture.needsUpdate=true;
   sky={skyVolume:{value:texture},skyOrigin:{value:new T.Vector3(...skylight.origin)},skySpan:{value:new T.Vector3(...skylight.size).multiplyScalar(skylight.step)}}
  }catch(error){controller.signal.throwIfAborted();console.warn('使用基础天空光',error)}
 }
 function material(mode,alpha){
  const key=mode+'/'+alpha;
  if(!materials.has(key)){
   const options={vertexColors:true,transparent:alpha<1,opacity:alpha,depthWrite:alpha>=1,clippingPlanes:[view.presetPlane,view.plane].filter(Boolean)};
   materials.set(key,mode===4?industrialMaterial({...options,clipShadows:true,side:T.DoubleSide},null,sky):new T.LineBasicMaterial(options))
  }
  return materials.get(key)
 }
 async function get(entry){
  const res=await cachedAsset(url+entry.asset,{signal:controller.signal});
  if(!res.ok)throw Error('平台模型分块读取失败');
  const buffer=await res.arrayBuffer();controller.signal.throwIfAborted();
  if(buffer.byteLength!==entry.bytes)throw Error('平台模型分块不完整');
  const group=unpack(buffer,material);view.attachPlatformGroup?.(group);return group
 }
 function applyCut(height,normal){
  if(cut===height&&(height===null||plane.normal.y===normal))return;
  const attach=(cut===null)!==(height===null);
  cut=height;plane.normal.set(0,normal,0);plane.constant=height===null?0:-normal*height;
  view.presetPlane=height===null?null:plane;
  if(view.outlines)view.outlines.material.clippingPlanes=[view.presetPlane,view.plane].filter(Boolean);
  if(attach)for(const m of materials.values()){
   m.clippingPlanes=[view.presetPlane,view.plane].filter(Boolean);m.needsUpdate=true
  }
  view.light.dirty=true
 }
 function environment(name){
  view.light.set('platform',name);
  applyCut(name==='overview'?0:presets[name]?.[3]??null,name==='overview'?1:-1)
 }
 view.platformEnvironment=environment;
 // Sweep a preset cut out through the model bounds before bringing the next cut in.
 view.blendPlatformEnvironment=(from='all',to='all',t)=>{
  const name=t<.5?from:to;
  if(view.light.preset!==name)view.light.set('platform',name);
  const height=name==='overview'?0:presets[name]?.[3]??null;
  const visibility=from===to?1:1-T.MathUtils.smoothstep(t<.5?t:1-t,.10,.50);
  const normal=name==='overview'?1:-1;
  const outside=normal>0?bounds.min.y-1:bounds.max.y+1;
  applyCut(height===null||visibility===0?null:T.MathUtils.lerp(outside,height,visibility),normal)
 };
 function preset(name){
  environment(name);
  view.camera.up.set(0,1,0);
  const [,target,offset]=presets[name];
  const aspect=view.canvas.clientWidth/Math.max(1,view.canvas.clientHeight);
  view.camera.fov=42;view.camera.near=.025;view.camera.far=6000;view.camera.updateProjectionMatrix();
  if(name==='all'){
   bounds.getCenter(view.control.target);
   const fov=view.camera.fov*Math.PI/360,limitingAngle=Math.min(fov,Math.atan(Math.tan(fov)*Math.max(.1,aspect)));
   const distance=bounds.getSize(new T.Vector3()).length()*.53/Math.sin(limitingAngle);
   view.camera.position.set(.78,.54,1).normalize().multiplyScalar(distance).add(view.control.target)
  }else{
   // Keep the valve inspection camera inside the pipe bay, clear of its support columns.
   const fit=id==='k'&&name==='pipe'?1:Math.max(1,1.15/aspect);
   view.control.target.fromArray(target);view.camera.position.fromArray(offset).multiplyScalar(fit).add(view.control.target)
  }
  view.control.update();view.invalidate();schedule()
 }
 function schedule(){
  if(!ready||disposed||view.inactive||id!=='k')return;
  changed=true;if(!timer&&!busy)timer=setTimeout(refine,50)
 }
 async function refine(){
  timer=0;if(disposed||busy||view.inactive)return;
  busy=true;
  try{
   changed=false;
   view.camera.updateMatrixWorld();
   const frustum=new T.Frustum().setFromProjectionMatrix(new T.Matrix4().multiplyMatrices(view.camera.projectionMatrix,view.camera.matrixWorldInverse));
   const target=view.control.target;
   const score=t=>t.box.distanceToPoint(view.camera.position)+1.5*t.box.distanceToPoint(target);
   const focus=view.iso>=0?view.tree[view.iso][4]:null;
   const focusBox=focus?new T.Box3(new T.Vector3(...focus.slice(0,3)),new T.Vector3(...focus.slice(3))):null;
   const near=tiles.filter(t=>(!view.wireOnly||view.iso>=0)&&(!focusBox||t.box.intersectsBox(focusBox))&&t.full&&(cut===null||(plane.normal.y>0?t.max[1]>=cut:t.min[1]<cut))&&(view.full||t.box.distanceToPoint(view.camera.position)<Math.max(16,t.box.getSize(new T.Vector3()).length()*1.5))&&frustum.intersectsBox(t.box))
    .sort((a,b)=>score(a)-score(b));
   let bytes=0;const wanted=[];
   for(const tile of near){if(wanted.length>=4)break;if(bytes+tile.full.bytes>140*1048576)continue;wanted.push(tile);bytes+=tile.full.bytes}
   for(const [tile,part] of detail)if(!wanted.includes(tile)){
    view.detachPlatformGroup?.(part);root.remove(part);part.traverse(o=>o.geometry?.dispose());detail.delete(tile);overviews.get(tile).visible=true
   }
   for(const tile of wanted){
    if(changed||disposed)break;if(detail.has(tile))continue;
    const part=await get(tile.full);root.add(part);detail.set(tile,part);overviews.get(tile).visible=false;view.invalidate()
   }
  }catch(e){if(!disposed)console.warn('平台细节暂未载入',e)}
  finally{busy=false;view.light.dirty=true;if(changed)schedule();if(!disposed)view.invalidate()}
 }
 for(const [name,[title]] of Object.entries(presets))addButton(name,title,()=>preset(name));
 view.platformRefine=schedule;view.control.addEventListener('change',schedule);preset(presets.overview?'overview':'all');
 const center=view.control.target.clone();
 tiles.sort((a,b)=>a.box.distanceToPoint(center)-b.box.distanceToPoint(center));
 let next=0,count=0;
 async function load(){
  while(next<tiles.length){
   const tile=tiles[next++],part=await get(tile.low);root.add(part);overviews.set(tile,part);
   progress(++count,tiles.length);if(count%48===0||count===tiles.length)view.light.dirty=true;view.invalidate()
  }
 }
 await Promise.all([load(),load(),load()]);ready=true;schedule()
}
