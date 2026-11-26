// Prepare the authored offshore-arena scenes once. The viewer only needs the vault.
import fs from 'node:fs';
import {bakeSkylight} from './platform-skylight.mjs';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';
import {gzipSync} from 'node:zlib';

const [source, vault] = process.argv.slice(2);
if (!source || !vault) throw Error('用法：node import-platform-scenes.mjs offshore-arena目录 工作台资料盘');
const models = path.join(source, 'public/models');
const output = path.join(vault, 'models/native');
const read = name => JSON.parse(fs.readFileSync(path.join(models, name)));
const load = name => import(pathToFileURL(path.resolve(source, name)));
const T = await load('node_modules/three/build/three.module.js');
const {GLTFLoader} = await load('node_modules/three/examples/jsm/loaders/GLTFLoader.js');
const {applyPresentation} = await load('public/twin/presentation.js');
const {applyModelPlayFilter} = await load('public/model-play-filter.js');
const {createEquipmentMaterialStyler} = await load('public/model-equipment-materials.js');
const {lFinishColor} = await load('public/twin/l-finish-catalog.js');
// Finish IDs are stored in runs in the tile header, leaving legacy geometry readable.
const finishCode={paint:0,deck:1,fire:2,process:3,steel:3,grating:4,vessel:5,cabinet:7,luminaire:16,
  rubber:18,glass:19,rotor:3,navy:8,rescue:14,lifebuoy:14};
function surfaceRuns(values){
  const runs=[];
  for(let start=0;start<values.length;){
    const value=values[start];let end=start+1;
    while(end<values.length&&values[end]===value)end++;
    runs.push(end,value);start=end;
  }
  return runs;
}
const {decodeSpatialTile} = await load('public/twin/k-stream.js');
const arrayBuffer = b => b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength);
const raw = a => Buffer.from(a.buffer,a.byteOffset,a.byteLength);
const digest = b => createHash('sha256').update(b).digest('hex');

function writeTile(directory, groups) {
  const chunks=[], descriptions=[];
  let triangles=0;
  for(const {positions,normals,colors,indices,mode,alpha,surfaces,nodes} of groups){
    if(!indices.length) continue;
    const vertices=positions.length/3;
    if(!nodes.length||nodes.at(-2)!==indices.length)throw Error('模型源节点索引长度不符');
    descriptions.push({nodes,vertices, indices:indices.length, mode, alpha,finishes:mode===4?surfaceRuns(surfaces):undefined});
    chunks.push(raw(positions),raw(normals),Buffer.alloc((-normals.byteLength)&3),
      raw(colors),Buffer.alloc((-colors.byteLength)&3),raw(indices));
    if(mode===4) triangles+=indices.length/3;
  }
  const header=Buffer.from(JSON.stringify(descriptions)),length=Buffer.alloc(4);
  length.writeUInt32LE(header.length);
  const buffer=Buffer.concat([length,header,Buffer.alloc((-header.length)&3),...chunks]);
  const hash=digest(buffer), filename=hash+'.bin.gz';
  if(!fs.existsSync(path.join(directory,filename))){
    fs.writeFileSync(path.join(directory,filename+'.tmp'),gzipSync(buffer,{level:2}));
    fs.renameSync(path.join(directory,filename+'.tmp'),path.join(directory,filename));
  }
  return {asset:hash,bytes:buffer.length,triangles};
}
function publish(directory,tiles) {
  const reviewPath=path.join(vault,'models',path.basename(directory),'editor/index.json');
  const review=fs.existsSync(reviewPath)?JSON.parse(fs.readFileSync(reviewPath)):null;
  fs.writeFileSync(path.join(directory,'index.tmp'),JSON.stringify({version:1,sourceTree:review?.tree,tiles,skylight:bakeSkylight(directory,tiles)}));
  fs.renameSync(path.join(directory,'index.tmp'),path.join(directory,'index.json'));
}
async function platformL(){
  const directory=path.join(output,'l');fs.mkdirSync(directory,{recursive:true});
  const loader=new GLTFLoader();
  const manifest=read('platform-l-full/index.json'), filter=read('platform-l-play-config.json');
  const presentation=read('platform-l-presentation.json'),styler=createEquipmentMaterialStyler(read('l-equipment-style.json'));
  const finishes=new Map(read('platform-l-surfaces.json').entries.map(e=>[e.sourceId,e]));
  const tiles=[],p=new T.Vector3(),normalMatrix=new T.Matrix3();
  for(const entry of manifest.chunks){
    const input=fs.readFileSync(path.join(models,'platform-l-full',entry.url));
    if(digest(input)!==entry.sha256) throw Error('L 分块校验失败 '+entry.url);
    const {scene}=await loader.parseAsync(arrayBuffer(input),'');
    applyModelPlayFilter(scene,filter);applyPresentation(scene,presentation);styler.apply(scene);scene.updateMatrixWorld(true);
    const plans=new Map(), bounds=new T.Box3();
    scene.traverseVisible(o=>{
      if(!o.geometry)return;
      if(o.isInstancedMesh||Array.isArray(o.material))throw Error('未支持的几何形式 '+o.name);
      const mode=o.isMesh?4:o.isLineSegments?1:null;
      if(mode===null)throw Error('未支持的绘图模式 '+o.type);
      const g=o.geometry,m=o.material,alpha=m.transparent?m.opacity:1,key=mode+'/'+alpha;
      if(!plans.has(key))plans.set(key,{mode,alpha,list:[],nv:0,ni:0});
      const plan=plans.get(key),nv=g.attributes.position.count,ni=g.index?.count??nv;
      const finish=finishes.get(o.userData.sourceId);
      if(finish&&finish.sourceNode!==o.userData.sourceNode)throw Error('表面版本不匹配');
      const color=m.color.clone();
      if(!m.userData.equipmentProfile&&mode===4)color.set(lFinishColor(finish?.finish||m.userData.surfaceFamily||'paint',color.getHSL({},T.SRGBColorSpace)));
      const surface=finishCode[m.userData.equipmentProfile]??finishCode[finish?.finish]??finishCode[m.userData.surfaceFamily]??0;
      plan.list.push({o,color,ni,nv,surface});plan.nv+=nv;plan.ni+=ni;
    });
    const groups=[];
    for(const {mode,alpha,list,nv,ni} of plans.values()){
      const positions=new Float32Array(nv*3),normals=new Int8Array(nv*3),colors=new Uint8Array(nv*3),indices=new Uint32Array(ni);
      let vertex=0,idx=0;
      const surfaces=new Uint8Array(nv),nodes=[];
      for(const {o,color,ni,nv,surface} of list){
        surfaces.fill(surface,vertex,vertex+nv);
        const g=o.geometry;
        if(mode===4&&!g.attributes.normal)g.computeVertexNormals();
        normalMatrix.getNormalMatrix(o.matrixWorld);
        for(let i=0;i<nv;i++){
          const offset=3*(vertex+i);
          p.fromBufferAttribute(g.attributes.position,i).applyMatrix4(o.matrixWorld).toArray(positions,offset);bounds.expandByPoint(p);
          if(g.attributes.normal){p.fromBufferAttribute(g.attributes.normal,i).applyNormalMatrix(normalMatrix).multiplyScalar(127);for(let k=0;k<3;k++)normals[offset+k]=Math.round(p.getComponent(k));}
          const c=g.attributes.color;
          colors[offset]=Math.round(255*color.r*(c?c.getX(i):1));colors[offset+1]=Math.round(255*color.g*(c?c.getY(i):1));colors[offset+2]=Math.round(255*color.b*(c?c.getZ(i):1));
        }
        const mirror=mode===4&&o.matrixWorld.determinant()<0;
        for(let i=0;i<ni;i++){
          const j=mirror&&i%3!==0?i+(i%3===1?1:-1):i;
          indices[idx++]=vertex+(g.index?g.index.getX(j):j);
        }
        const node=o.userData.sourceNode;
        if(!Number.isSafeInteger(node)||node<0)throw Error('L 构件缺少源编号');
        nodes.push(idx,node);vertex+=nv;
      }
      groups.push({mode,alpha,positions,normals,colors,indices,surfaces,nodes});
    }
    const low=writeTile(directory,groups);if(!bounds.isEmpty())tiles.push({low,min:bounds.min.toArray(),max:bounds.max.toArray()});
  }
  styler.dispose();publish(directory,tiles);console.log('L:',tiles.length,'分块');
}
async function platformK(){
  const directory=path.join(output,'k');fs.mkdirSync(directory,{recursive:true});
  const excluded=new Set(read('platform-k-presentation.json').entries.map(e=>e.sourceNode));
  const finishes=new Map(read('platform-k-surfaces.json').entries.map(([id,node,kind,system])=>['nw-f'+id,{node,kind,system}]));
  const manifest=read('platform-k-stream/index.json'),tiles=[];
  const materials=new Map();
  function material(group){if(!materials.has(group.alpha))materials.set(group.alpha,new T.MeshBasicMaterial({opacity:group.alpha}));return materials.get(group.alpha)}
  for(const entry of manifest.tiles){
    const tile={min:entry.min,max:entry.max};
    for(const level of ['low','full']){
      const item=entry[level],b=fs.readFileSync(path.join(models,'platform-k-stream',item.url));
      if(b.length!==item.bytes)throw Error('K 分块校验失败 '+item.url);
      const decoded=decodeSpatialTile(arrayBuffer(b),material,excluded,finishes);
      const groups=decoded.root.children.map(o=>{
        const g=o.geometry,{start,count}=g.drawRange;
        const index=g.index.array.subarray(start,start+count);
        // Repack only referenced vertices for this render state.
        const remap=new Map(),indices=Uint32Array.from(index,v=>{
          if(!remap.has(v))remap.set(v,remap.size);return remap.get(v);
        });
        const select=a=>{const out=new a.constructor(remap.size*3);for(const [src,dest] of remap)out.set(a.subarray(src*3,src*3+3),dest*3);return out};
        const nodes=[];
        for(const part of o.userData.parts){
          if(part.start>=start&&part.start<start+count)nodes.push(part.start+part.count-start,part.node);
        }
        return {nodes,mode:o.isMesh?4:1,alpha:o.material.opacity,positions:select(g.attributes.position.array),
          normals:select(g.attributes.normal.array),colors:select(g.attributes.color.array),indices,
          surfaces:Uint8Array.from(remap.keys(),v=>g.attributes.surfaceKind.getX(v))};
      });
      tile[level]=writeTile(directory,groups);decoded.dispose();
    }
    tiles.push(tile);
  }
  publish(directory,tiles);console.log('K:',tiles.length,'分块');
}
await platformL();await platformK();
