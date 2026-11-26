import {Box3,BufferAttribute,BufferGeometry,Group,LineBasicMaterial,LineSegments,Sphere,Vector3} from 'three';

// Positions come from full-detail CAD pages. Each run belongs to one source node.
export class ReviewOutlines{
 constructor(view,tiles){
  this.view=view;this.group=new Group();view.scene.add(this.group);
  this.material=new LineBasicMaterial({color:0x34414a,transparent:true,opacity:.37,depthWrite:false});
  this.tiles=tiles.map(tile=>({...tile,box:new Box3(new Vector3(...tile.min),new Vector3(...tile.max))}));
  this.active=0;this.group.visible=!view.presentation
 }
 schedule(frustum){
  if(this.view.inactive||!this.group.visible)return;
  const eye=this.view.camera.position;
  const visible=this.tiles.filter(t=>frustum.intersectsBox(t.box)).sort((a,b)=>a.box.distanceToPoint(eye)-b.box.distanceToPoint(eye));
  if(this.view.presentation){
   let lines=0;
   const wanted=new Set(visible.filter(tile=>{
    if(lines+tile.lines>220000)return false;
    lines+=tile.lines;return true
   }));
   let changed=false;
   for(const tile of this.tiles){
    if(wanted.has(tile)===!!tile.wanted)continue;
    tile.wanted=wanted.has(tile);
    if(tile.line){changed=true;if(tile.wanted)this.filterTile(tile);else tile.line.visible=false}
   }
   // Bound the retained geometry as the camera visits different parts of a platform.
   const cached=this.tiles.filter(t=>t.line&&!t.wanted).sort((a,b)=>b.box.distanceToPoint(eye)-a.box.distanceToPoint(eye));
   let stored=cached.reduce((sum,t)=>sum+t.lines,0);
   for(const tile of cached){
    if(stored<=440000)break;
    this.group.remove(tile.line);tile.line.geometry.dispose();stored-=tile.lines;
    tile.line=null;tile.runs=null;tile.hit=null;tile.indices=null;tile.filterKey=undefined
   }
   if(changed)this.view.draw();
  }
  this.pending=visible.filter(t=>(!this.view.presentation||t.wanted)&&!t.line&&!t.loading&&(!t.retry||Date.now()>t.retry));
  this.pump()
 }
 pump(){
  while(this.active<2&&this.pending?.length&&!this.view.inactive&&this.group.visible){
   const tile=this.pending.shift();tile.loading=true;this.active++;
   this.view.asset(tile.asset).then(raw=>{
    const vertices=tile.lines*2,coords=vertices*3;
    if(raw.byteLength<coords*2||(raw.byteLength-coords*2)%8)throw Error('审查线稿数据无效');
    const src=new Uint16Array(raw,0,coords),position=new Float32Array(coords);
    for(let axis=0;axis<3;axis++){
     const step=(tile.max[axis]-tile.min[axis])/65535;
     for(let i=axis;i<coords;i+=3)position[i]=tile.min[axis]+src[i]*step
    }
    tile.runs=new Uint32Array(raw,coords*2);
    if(tile.runs.at(-2)!==vertices)throw Error('审查线稿构件映射无效');
    const geom=new BufferGeometry();geom.setAttribute('position',new BufferAttribute(position,3));
    geom.boundingSphere=tile.box.getBoundingSphere(new Sphere());
    tile.line=new LineSegments(geom,this.material);tile.line.renderOrder=1;
    tile.line.userData.outlineTile=tile;this.group.add(tile.line);this.filterTile(tile);this.view.draw()
   }).catch(error=>{tile.retry=Date.now()+5000;console.warn('审查线稿加载失败',error)})
   .finally(()=>{tile.loading=false;this.active--;this.pump()})
  }
 }
 filterTile(tile){
  const {mask,iso,context,hasMask}=this.view,geom=tile.line.geometry;
  if(this.view.presentation&&!tile.wanted){tile.line.visible=false;return}
  const key=this.view.lineFilterKey;
  if(key!==undefined&&tile.filterKey===key){tile.line.visible=geom.drawRange.count>0;return}
  tile.filterKey=key;
  if(!hasMask||(context&&iso>=0&&!this.view.explicitMask)){
   geom.setIndex(null);geom.setDrawRange(0,Infinity);tile.hit=tile.runs;tile.line.visible=true;return
  }
  tile.indices??=new BufferAttribute(new Uint32Array(tile.lines*2),1);
  const indices=tile.indices.array,hits=[];let write=0,start=0;
  for(let i=0;i<tile.runs.length;i+=2){
   const end=tile.runs[i],id=tile.runs[i+1];
   if(mask[id]===0||(iso>=0&&context&&mask[id]===1)){
    for(let j=start;j<end;j++)indices[write++]=j;
    hits.push(write,id)
   }
   start=end
  }
  geom.setIndex(tile.indices);tile.indices.needsUpdate=true;
  geom.setDrawRange(0,write);tile.hit=hits;tile.line.visible=write>0
 }
 update(){
  this.group.visible=!this.view.explode&&(!this.view.presentation||this.view.wireOnly||(this.view.context&&this.view.iso>=0));
  if(!this.group.visible){this.pending=[];return}
  this.material.opacity=this.view.iso>=0?.23:.39;
  this.material.clippingPlanes=[this.view.presetPlane,this.view.plane].filter(Boolean);
  for(const tile of this.tiles)if(tile.line)this.filterTile(tile)
 }
 pick(ray,camera){
  if(!this.group.visible)return null;
  const threshold=ray.params.Line.threshold,oldFar=ray.far;
  let nearest=null;
  try{
   for(const tile of this.tiles){
    if(!tile.line?.visible||!ray.ray.intersectsBox(tile.box))continue;
    const distance=tile.box.distanceToPoint(camera.position);
    ray.params.Line.threshold=Math.min(.15,Math.max(.013,distance*Math.tan(camera.fov*Math.PI/360)*3/Math.max(1,this.view.height)));
    for(const hit of ray.intersectObject(tile.line,false)){
     if([this.view.presetPlane,this.view.plane].some(p=>p&&p.distanceToPoint(hit.point)<0))continue;
     if(nearest&&hit.distance>=nearest.distance)break;
     let lo=0,hi=tile.hit.length/2;
     while(lo<hi){const mid=(lo+hi)>>1;if(tile.hit[mid*2]<=hit.index)lo=mid+1;else hi=mid}
     if(lo<tile.hit.length/2){nearest={id:tile.hit[lo*2+1],point:hit.point.toArray(),distance:hit.distance};ray.far=hit.distance}
     break
    }
   }
  }finally{ray.params.Line.threshold=threshold;ray.far=oldFar}
  return nearest
 }
}
