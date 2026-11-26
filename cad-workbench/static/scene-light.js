import * as T from 'three';
import {createOcean} from './ocean.js';
import {HDRLoader} from './appearance/HDRLoader.js';
import {prepareSurfaces} from './industrial-surfaces.js';

function studioReflection(pmrem){
 const room=new T.Scene();room.background=new T.Color(.17,.19,.22);
 const geometry=new T.PlaneGeometry();
 const lamps=[];
 function panel(x,y,z,w,h,r,g,b){
  const mat=new T.MeshBasicMaterial({color:new T.Color(r,g,b),side:T.DoubleSide});
  const plane=new T.Mesh(geometry,mat);plane.position.set(x,y,z);plane.scale.set(w,h,1);
  plane.lookAt(0,0,0);room.add(plane);lamps.push(mat)
 }
 panel(-5,4,3,4,8,3.2,3.05,2.8);panel(4,1,-4,2,7,2.3,2.8,3.1);
 panel(0,6,0,9,4,1.65,1.74,1.9);panel(3,-2,4,8,2,.055,.065,.075);
 const env=pmrem.fromScene(room,.04);geometry.dispose();for(const m of lamps)m.dispose();return env
}

export class SceneLight{
 constructor(view){
  this.view=view;this.mode='sheet';this.preset='';this.dirty=true;
  const {renderer,scene}=view;
  renderer.toneMapping=T.ACESFilmicToneMapping;renderer.toneMappingExposure=1.02;
  renderer.shadowMap.enabled=true;renderer.shadowMap.type=T.PCFShadowMap;renderer.shadowMap.autoUpdate=false;
  this.sun=new T.DirectionalLight(0xffead1,2.95);this.sun.castShadow=true;
  this.sun.shadow.mapSize.set(2048,2048);this.sun.shadow.bias=-.00015;this.sun.shadow.radius=1.6;
  this.hemi=new T.HemisphereLight(0xdaedff,0x6f716b,.55);
  scene.add(this.hemi,this.sun,this.sun.target);
  this.dir=new T.Vector3(-.48,.85,.54).normalize();
  this.pmrem=new T.PMREMGenerator(renderer);this.studio=studioReflection(this.pmrem);
  prepareSurfaces(renderer,()=>view.invalidate());
  this.floor=new T.Mesh(new T.PlaneGeometry(1600,1600),new T.MeshStandardMaterial({color:0xbfc7c6,roughness:.89,metalness:.03}));
  this.floor.rotation.x=-Math.PI/2;this.floor.position.y=-.18;this.floor.receiveShadow=true;scene.add(this.floor);
  this.set('sheet')
 }
 async loadCoast(){
  if(this.sky||this.loading)return;
  this.loading=true;
  try{
   const sky=await new HDRLoader().loadAsync('/appearance/coastal-day.hdr');
   sky.mapping=T.EquirectangularReflectionMapping;this.sky=sky;
   this.coast=this.pmrem.fromEquirectangular(sky);
   this.ocean?.setSky(sky,this.coast.texture);
   const {data,width,height}=sky.image;
   let peak=0,index=0;
   for(let i=0;i<width*height;i++){
    const value=T.DataUtils.fromHalfFloat(data[4*i+1]);
    if(value>peak){peak=value;index=i}
   }
   const az=((index%width+.5)/width-.5)*Math.PI*2,el=(.5-(Math.floor(index/width)+.5)/height)*Math.PI;
   this.coastDir=new T.Vector3(Math.cos(az)*Math.cos(el),Math.sin(el),Math.sin(az)*Math.cos(el));
   if(this.mode==='platform')this.set(this.mode,this.preset)
  }catch(err){console.warn('海面日光环境未载入',err)}
  finally{this.loading=false}
 }
 makeWater(){
  this.ocean=createOcean(()=>this.view.invalidate());
  this.water=this.ocean.group;this.view.scene.add(this.water);
  const catcher=new T.Mesh(new T.PlaneGeometry(500,500),new T.ShadowMaterial({opacity:.18,depthWrite:false}));
  catcher.receiveShadow=true;catcher.rotation.x=-Math.PI/2;catcher.position.set(120,.12,-105);this.water.add(catcher)

 }
 set(mode,preset=''){
  this.mode=mode;this.preset=preset;this.dirty=true;
  const {scene,renderer}=this.view,platform=mode==='platform';
  if(platform){this.loadCoast();if(!this.water)this.makeWater()}
  if(this.water)this.water.visible=platform&&preset!=='all';
  this.floor.visible=mode==='sheet';
  scene.environment=(platform&&this.coast?this.coast:this.studio).texture;
  scene.environmentIntensity=platform?.70:.96;
  scene.background=platform&&this.sky?this.sky:new T.Color(platform?0xc4d5df:0xd5dedf);
  scene.backgroundBlurriness=platform?.035:0;scene.backgroundIntensity=.90;
  scene.fog=platform&&preset!=='all'?new T.Fog(0xb7c4c9,250,3000):mode==='sheet'?new T.FogExp2(0xd5dedf,.0033):null;
  this.sun.color.set(platform?0xffe5c6:0xffebd6);this.sun.intensity=platform?2.75:2.45;
  this.hemi.intensity=platform?.29:.48;renderer.toneMappingExposure=platform?.93:1.0;
  this.view.invalidate()
 }
 prepare(){
  const view=this.view,c=view.control.target,shadow=this.sun.shadow;
  const distance=view.camera.position.distanceTo(c),radius=Math.max(5,Math.min(this.mode==='platform'?185:90,distance*.68));
  if(!this.dirty&&this.lastCenter?.distanceTo(c)<radius*.075&&Math.abs(this.lastRadius-radius)<radius*.13)return;
  this.lastCenter=c.clone();this.lastRadius=radius;this.dirty=false;
  this.sun.target.position.copy(c);
  this.sun.position.copy(c).addScaledVector(this.mode==='platform'&&this.coastDir?this.coastDir:this.dir,200);
  Object.assign(shadow.camera,{left:-radius,right:radius,top:radius,bottom:-radius,near:.2,far:420+radius});
  shadow.normalBias=radius*.0009;shadow.camera.updateProjectionMatrix();view.renderer.shadowMap.needsUpdate=true
 }
}
