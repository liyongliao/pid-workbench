import * as T from 'three';
import {safetyRed} from './safety-paint.js';

const up=new T.Vector3(0,1,0), identity=new T.Quaternion();
const vector=a=>new T.Vector3(...a);
export const steel=0xadb8bb, shell=0xdadbd1, pipe=0x8caaab, frame=0x414f59;
export const bolts=0x66717a, bonnet=0x30696a, actuator=0xae5935, instrument=0x366f84;


export function sheetFittings(root,drawing,blocks){
 const pieces=new Map(),byId=new Map(),batch=new Map(),tags=new Map(),labels=[];
 const handlesBySource=new Set();
 for(const item of drawing.items){
  handlesBySource.add(item.handle);
  if(!item.tag)continue;
  if(!tags.has(item.tag))tags.set(item.tag,[]);
  tags.get(item.tag).push(item.handle)
 }
 const handles=new Map();
 for(const [tag,ids] of tags){
  // Prefer the in-sheet equipment label over its repeated equipment schedule entry.
  const id=ids.includes('6F42')?'6F42':ids.includes('709B')?'709B':ids.includes('6DBD')?'6DBD':ids.includes('6C67')?'6C67':ids[0];
  handles.set(tag,id);
  for(const alias of ids)byId.set(alias,{linked:[id]})
 }
 const cyl=new T.CylinderGeometry(1,1,1,32),hex=new T.CylinderGeometry(1,1,1,6);
 const cube=new T.BoxGeometry(),ball=new T.SphereGeometry(1,32,20);
 const torus=new T.TorusGeometry(1,.095,8,40);
 function place(tag,g,at,size,color,rot=identity){
  const matrix=new T.Matrix4().compose(vector(at),rot,vector(size)),id=handles.get(tag)??(handlesBySource.has(tag)?tag:undefined);
  if(id&&(!byId.has(id)||id===tag))byId.set(id,{linked:[id]});
  const part={id,g,matrix,color};
  if(!batch.has(g))batch.set(g,[]);
  batch.get(g).push(part);
  if(id){if(!pieces.has(id))pieces.set(id,[]);pieces.get(id).push(part)}
 }
 function rod(tag,a,b,r,color=pipe,g=cyl){
  const v=vector(b).sub(vector(a)),length=v.length();
  place(tag,g,vector(a).addScaledVector(v,.5).toArray(),[r,length,r],color,new T.Quaternion().setFromUnitVectors(up,v.normalize()))
 }
 function box(tag,x,y,z,w,h,d,c){place(tag,cube,[x,y,z],[w,h,d],c)}
 function oval(tag,at,size,c){place(tag,ball,at,size,c)}
 function line(tag,pts,r,c=pipe){
  const points=pts.map(vector).filter((v,i,a)=>!i||!v.equals(a[i-1])),path=new T.CurvePath();
  let start=points[0];
  for(let i=1;i<points.length-1;i++){
   const p=points[i],before=points[i-1],after=points[i+1];
   const bend=Math.min(r*2.4,p.distanceTo(before)*.35,p.distanceTo(after)*.35);
   const entry=p.clone().addScaledVector(before.clone().sub(p).normalize(),bend);
   const exit=p.clone().addScaledVector(after.clone().sub(p).normalize(),bend);
   path.add(new T.LineCurve3(start,entry));path.add(new T.QuadraticBezierCurve3(entry,p,exit));start=exit
  }
  path.add(new T.LineCurve3(start,points.at(-1)));
  // Generate each straight / elbow separately so long straight spools do not
  // consume the subdivisions needed by the short bends.
  for(const curve of path.curves){
   if(curve.isLineCurve3)rod(tag,curve.v1.toArray(),curve.v2.toArray(),r,c);
   else place(tag,new T.TubeGeometry(curve,10,r,20,false),[0,0,0],[1,1,1],c)
  }
 }
 function flange(tag,at,axis,r,count=8){
  const p=vector(at),normal=vector(axis),side=new T.Vector3().crossVectors(normal,Math.abs(normal.y)>.8?new T.Vector3(0,0,1):up).normalize();
  const other=new T.Vector3().crossVectors(normal,side),wide=r*1.58+.008;
  const end=(center,t)=>center.clone().addScaledVector(normal,t).toArray();
  rod(tag,end(p,-.015),end(p,.015),wide,steel);
  for(let i=0;i<count;i++){
   const a=2*Math.PI*i/count,center=p.clone().addScaledVector(side,wide*.81*Math.cos(a)).addScaledVector(other,wide*.81*Math.sin(a));
   rod(tag,end(center,-.022),end(center,.024),Math.max(.005,r*.092),bolts,hex)
  }
 }
 function station(tag,x,y,z,r,type){
  if(type==='shutdown'){
   const family=tag.startsWith('BDV')?'bdv':'sdv', template=blocks.get(family);
   // SDV template is the 8-inch L assembly. Smaller-bore actuators retain a
   // substantial envelope; derived sizes are layout estimates, not catalog sizes.
   const scale=family==='bdv'?.86:r>=.09?1:.54;
   if(template){place(tag,template.g,[x,y,z],[scale,scale,scale],safetyRed);return}
   const span=(family==='bdv'?.23:.37)*scale,stem=(family==='bdv'?.35:.88)*scale;
   oval(tag,[x,y,z],[span,r*1.9,r*1.9],safetyRed);
   for(const sign of [-1,1])flange(tag,[x+sign*span,y,z],[1,0,0],r);
   rod(tag,[x,y,z],[x,y+stem,z],.09*scale,safetyRed);
   const h=y+stem;box(tag,x,h,z,.37*scale,.31*scale,.29*scale,safetyRed);
   rod(tag,[x-.84*scale,h,z],[x+1.10*scale,h,z],.115*scale,safetyRed);
   place(tag,torus,[x-.88*scale,h,z],[.25*scale,.25*scale,.25*scale],safetyRed,new T.Quaternion().setFromAxisAngle(up,Math.PI/2));
   return
  }
  const span=r*2.4;
  flange(tag,[x-span,y,z],[1,0,0],r);flange(tag,[x+span,y,z],[1,0,0],r);
  oval(tag,[x,y,z],[span,r*1.42,r*1.4],type==='meter'?steel:bonnet);
  rod(tag,[x,y+r,z],[x,y+r+.13,z],r*.38,steel);
  if(type==='meter')return;
  const h=y+r+.16;
  rod(tag,[x,h-.035,z],[x,h+.055,z],r*.74,bonnet);
  oval(tag,[x,h+.077,z],[r+.07,.058,r+.07],actuator)
 }
 function handValve(tag,x,y,z,r){
  const w=r*1.7,h=y+r+.098;
  flange(tag,[x-w,y,z],[1,0,0],r,4);flange(tag,[x+w,y,z],[1,0,0],r,4);
  oval(tag,[x,y,z],[w,r*1.2,r*1.28],bonnet);
  rod(tag,[x,y+r,z],[x,h,z],.011,steel);
  const wheel=r+.038;
  place(tag,torus,[x,h,z],[wheel,wheel,wheel],actuator,new T.Quaternion().setFromAxisAngle(new T.Vector3(1,0,0),Math.PI/2));
  for(let k=0;k<3;k++){
   const a=k*2*Math.PI/3;rod(tag,[x,h,z],[x+wheel*Math.cos(a),h,z+wheel*Math.sin(a)],.004,actuator)
  }
 }
 function transmitter(tag,x,y,z,base){
  rod(tag,base,[x,y-.044,z],.011,steel);
  box(tag,x,y,z,.089,.095,.073,instrument);
  rod(tag,[x,y,z+.032],[x,y,z+.047],.033,steel);
  rod(tag,[x,y,z+.047],[x,y,z+.05],.027,frame)
 }
 function label(tag,pos,caption=tag){const id=handles.get(tag)??(handlesBySource.has(tag)?tag:null);if(id)labels.push({id,tag:caption,anchor:vector(pos)})}


 // Relief template datum is the bottom inlet. Its outlet faces local +X.
 function relief(tag,x,y,z,scale=1){
  const g=blocks.get('psv')?.g,rot=new T.Quaternion().setFromAxisAngle(up,Math.PI/2);
  if(g)place(tag,g,[x,y,z],[scale,scale,scale],safetyRed,rot);
  else{
   rod(tag,[x,y,z],[x,y+.49*scale,z],.061*scale,safetyRed);
   rod(tag,[x,y+.125*scale,z],[x,y+.125*scale,z-.1625*scale],.048*scale,safetyRed);
   flange(tag,[x,y+.125*scale,z-.1625*scale],[0,0,1],.062*scale)
  }
  return [x,y+.125*scale,z-.1625*scale]
 }
 function connection(tag,path,r,incoming,description,sheet){
  line(tag,path,r);
  const tip=vector(path.at(-1)),direction=tip.clone().sub(vector(path.at(-2))).normalize();
  const arrowAt=tip.clone().addScaledVector(direction,.14);
  rod(tag,tip.toArray(),tip.clone().addScaledVector(direction,.004).toArray(),r*.84,frame);
  if(incoming)direction.negate();
  place(tag,arrow,arrowAt.toArray(),[r+.048,.235,r+.048],0x216f77,new T.Quaternion().setFromUnitVectors(up,direction));
  const id=handles.get(tag);
  if(id)labels.push({id,tag:(incoming?'来自':'去往')+description,ref:sheet,anchor:tip,connection:true})
 }
 const arrow=new T.ConeGeometry(1,1,24);
 function finish(){
  const mat=new T.MeshStandardMaterial({roughness:.46,metalness:.38});
  for(const [g,parts] of batch){
   const mesh=new T.InstancedMesh(g,mat,parts.length);
   mesh.userData.ids=parts.map(p=>p.id);mesh.castShadow=mesh.receiveShadow=true;
   parts.forEach((p,i)=>{mesh.setMatrixAt(i,p.matrix);mesh.setColorAt(i,new T.Color(p.color))});
   root.add(mesh)
  }
  for(const [id,entry] of byId)if(!pieces.has(entry.linked[0]))byId.delete(id);
  return {pieces,byId,labels,direction:[.48,.49,1]}
 }
 return {rod,box,oval,place,line,flange,station,handValve,transmitter,label,relief,connection,finish}
}
