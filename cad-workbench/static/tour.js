import {Vector3,Spherical,MathUtils} from 'three';

const el=id=>document.getElementById(id);
const vec=a=>new Vector3().fromArray(a);
const point=a=>Array.isArray(a)&&a.length===3&&a.every(Number.isFinite);
function validCamera(c){return c&&point(c.eye)&&point(c.target)&&point(c.up)&&Number.isFinite(c.fov)&&vec(c.eye).distanceTo(vec(c.target))>.0001}
// A cyclic Hermite curve in orbit coordinates. Shared time-based tangents keep
// speed continuous at the joins, including the last shot returning to the intro.
function orbitRoute(stops){
 const first=stops[0],intro=structuredClone(first.camera);
 const opening=new Spherical().setFromVector3(vec(intro.eye).sub(vec(intro.target)));
 opening.radius*=1.12;opening.theta-=.045;
 intro.eye=vec(intro.target).add(new Vector3().setFromSpherical(opening)).toArray();
 const shots=[{...first,camera:intro,seconds:6},...stops];
 const keys=shots.map(({camera:c})=>{
  const orbit=new Spherical().setFromVector3(vec(c.eye).sub(vec(c.target)));
  return [...c.target,Math.log(orbit.radius),orbit.phi,orbit.theta,c.fov,...c.up]
 });
 const legs=keys.map((key,i)=>{
  const next=keys[(i+1)%keys.length],duration=shots[i].seconds;
  const delta=key.map((value,j)=>next[j]-value);
  delta[5]=MathUtils.euclideanModulo(delta[5]+Math.PI,2*Math.PI)-Math.PI;
  return {key,delta,duration,speed:delta.map(d=>d/duration)}
 });
 const tangent=legs.map((leg,i)=>{
  const previous=legs[(i+legs.length-1)%legs.length];
  return leg.speed.map((out,j)=>{
   const incoming=previous.speed[j];
   return incoming*out>0?2/(1/incoming+1/out):0
  })
 });
 function sample(i,t){
  const {key,delta,duration}=legs[i],next=(i+1)%legs.length;
  const u=1-t,h=t*t*(3-2*t);
  const values=key.map((v,j)=>v+h*delta[j]+duration*t*u*(u*tangent[i][j]-t*tangent[next][j]));
  const [x,y,z,logRadius,phi,theta,fov,ux,uy,uz]=values;
  const target=new Vector3(x,y,z),up=new Vector3(ux,uy,uz);
  if(up.lengthSq()<1e-6)up.set(0,1,0);
  const offset=new Vector3().setFromSpherical(new Spherical(Math.exp(logRadius),phi,theta));
  return {eye:target.clone().add(offset).toArray(),target:target.toArray(),fov,up:up.normalize().toArray()}
 }
 return {shots,sample}
}
export function createTour(view,presets,sourceViews,model,scope,notify,name){
 const key='pid.tour.v1.'+model+'.'+scope,film=el('film');
 const platformName=name||model.toUpperCase()+' 平台';
 const introduction=!['k','l'].includes(model)?platformName+' · 模型全景与构件展示。':'这里是东方 1-1 气田 '+platformName+'。跟随镜头，从水上全景走进甲板、设备与管线。';
 let list,title=platformName+' · 数字孪生',subtitle=introduction;
 const appearance=()=>view.light?.preset||'all';
 const capture=()=>({camera:view.cameraState(),environment:appearance()});
 function show(shot){view.platformEnvironment?.(shot.environment||'all');view.setCamera(shot.camera)}
 const before=capture();
 try{
  const saved=JSON.parse(localStorage.getItem(key));
  if(saved&&typeof saved.title==='string'&&typeof saved.subtitle==='string'&&Array.isArray(saved.stops)&&saved.stops.length<=100&&saved.stops.every(s=>validCamera(s.camera)&&typeof s.name==='string'&&typeof s.description==='string'&&s.seconds>=1&&s.seconds<=180)){
   list=saved.stops;title=saved.title;subtitle=saved.subtitle==='东方 1-1 气田'?introduction:saved.subtitle
  }
 }catch{}
 if(!list){
  list=[];
  const descriptions={
   overview:'从海面看平台的整体布局。',top:'从上方俯瞰各层甲板。',
   deck:'沿甲板观察设备的布置。',lower:'剖开上方甲板，查看下层空间。',
   equipment:'拉近视角，观察设备本体与周边管线。',pipe:'沿管线近看阀件和连接位置。'
  };
  for(const [id,preset] of presets){
   if(id==='all')continue;
   preset.apply();list.push({...capture(),name:preset.title,description:descriptions[id]||platformName,seconds:15})
  }
  if(!list.length){
   list.push({...before,name:['k','l'].includes(model)?'平台全景':'模型全景',description:'',seconds:8});
   for(const p of sourceViews.slice(0,5)){view.preset(p);list.push({...capture(),name:p.name,description:'',seconds:8})}
  }
  show(before)
 }
 function save(){
  film.dispatchEvent(new Event('routechange'));
  try{localStorage.setItem(key,JSON.stringify({title,subtitle,stops:list}))}
  catch{notify('本机无法保存路线，本次打开期间仍可播放。')}
 }
 function button(text,fn,cls=''){const b=document.createElement('button');b.type='button';b.textContent=text;b.onclick=fn;b.className=cls;return b}
 function field(label,value,fn,number=false){
  const wrap=document.createElement('label'),input=document.createElement('input');wrap.textContent=label;
  input.type=number?'number':'text';if(number){input.min=1;input.max=180}else input.maxLength=180;
  input.value=value;input.addEventListener(number?'change':'input',()=>{
   const next=number?MathUtils.clamp(Math.round(Number(input.value)||1),1,180):input.value;
   if(number)input.value=next;fn(next);save()
  });wrap.append(input);return wrap
 }
 function edit(parent){
  const head=document.createElement('div');head.className='tour-editor';
  const startButton=button('开始宣传巡航',start,'tour-start');startButton.disabled=!list.length;
  head.append(startButton,field('片头标题',title,v=>title=v),field('片头副标题',subtitle,v=>subtitle=v),button('＋ 添加当前视角',()=>{
   if(list.length>=100){notify('每条路线最多可保存 100 个镜头');return}
   list.push({...capture(),name:'镜头 '+(list.length+1),description:'',seconds:8});save();refresh()
  },'ui-button'));
  const help=document.createElement('small');help.textContent='路线自动保存在此浏览器，按账号与平台分别保存。';head.append(help);parent.append(head);
  function refresh(){parent.replaceChildren();edit(parent)}
  list.forEach((shot,i)=>{
   const row=document.createElement('div');row.className='tour-stop';
   const desc=field('字幕',shot.description,v=>shot.description=v);desc.className='wide-field';
   row.append(field('镜头 '+(i+1),shot.name,v=>shot.name=v),field('秒',shot.seconds,v=>shot.seconds=v,true),desc);
   const actions=document.createElement('div');actions.className='tour-actions';
   const move=by=>{[list[i],list[i+by]]=[list[i+by],list[i]];save();refresh()};
   const up=button('上移',()=>move(-1)),down=button('下移',()=>move(1));up.disabled=i===0;down.disabled=i===list.length-1;
   actions.append(button('预览',()=>show(shot)),button('覆盖视角',()=>{Object.assign(shot,capture());save();notify('镜头视角已更新')}),up,down,button('移除',()=>{list.splice(i,1);save();refresh()}));
   row.append(actions);parent.append(row)
  })
 }
 let playing=false,paused=false,step=0,elapsed=0,last=0,frame=0,restore,route,originFocus,enteredFullscreen=false;
 const caption=film.querySelector('.film-caption'),heading=caption.querySelector('h2'),body=caption.querySelector('p');
 function enterShot(){
  const shot=route.shots[step];
  heading.textContent=step===0?title:shot.name;body.textContent=step===0?subtitle:shot.description;
  el('filmCount').textContent=step===0?'片头':step+' / '+list.length;
 }
 function renderTime(){
  const {shots}=route,shot=shots[step],next=shots[(step+1)%shots.length];
  const duration=shot.seconds,t=elapsed/duration;
  view.setCamera(route.sample(step,t));
  if(view.blendPlatformEnvironment)view.blendPlatformEnvironment(shot.environment,next.environment,t);
  const fade=Math.min(step===0?1.65:.9,duration*.28);
  const tail=1-MathUtils.smoothstep(elapsed,duration-fade*.7,duration);
  caption.style.opacity=MathUtils.smoothstep(elapsed,0,fade)*tail;
  body.style.opacity=MathUtils.smoothstep(elapsed,fade*.38,fade*1.18);
 }
 function tick(now){
  if(!playing||paused)return;
  elapsed+=Math.max(0,now-last)/1000;last=now;
  while(elapsed>=route.shots[step].seconds){
   elapsed-=route.shots[step].seconds;step=(step+1)%route.shots.length;enterShot()
  }
  renderTime();frame=requestAnimationFrame(tick)
 }
 function start(){
  if(!list.length){notify('请先在巡航路线中添加视角');return}
  if(playing)return;
  route=orbitRoute(list);originFocus=document.activeElement;restore=capture();playing=true;paused=false;step=0;elapsed=0;
  view.control.enabled=false;document.body.classList.add('presenting');film.hidden=false;
  view.platformEnvironment?.(list[0].environment||'all');
  enterShot();renderTime();el('pauseFilm').textContent='暂停';el('pauseFilm').focus();
  last=performance.now();frame=requestAnimationFrame(tick)
 }
 function pause(){
  if(!playing)return;paused=!paused;el('pauseFilm').textContent=paused?'继续':'暂停';
  cancelAnimationFrame(frame);if(!paused){last=performance.now();frame=requestAnimationFrame(tick)}
 }
 function stop(){
  if(!playing)return;playing=false;cancelAnimationFrame(frame);film.hidden=true;document.body.classList.remove('presenting');
  view.control.enabled=true;show(restore);originFocus?.focus({preventScroll:true});
  if(enteredFullscreen&&document.fullscreenElement)document.exitFullscreen().catch(()=>{});enteredFullscreen=false
 }
 el('exitFilm').onclick=stop;el('pauseFilm').onclick=pause;
 el('fullFilm').onclick=async()=>{
  try{if(document.fullscreenElement){await document.exitFullscreen();enteredFullscreen=false}
   else{await document.documentElement.requestFullscreen();enteredFullscreen=true}}
  catch{notify('此浏览器未允许全屏')}
 };
 document.addEventListener('fullscreenchange',()=>el('fullFilm').textContent=document.fullscreenElement?'退出全屏':'全屏');
 document.addEventListener('keydown',e=>{
  if(!playing)return;
  if(e.key==='Escape'){e.preventDefault();e.stopImmediatePropagation();stop()}
  if(e.code==='Space'&&e.target.tagName!=='BUTTON'){e.preventDefault();pause()}
 },true);
 document.addEventListener('visibilitychange',()=>{if(document.hidden&&playing&&!paused)pause()});
 return {edit,start,get stops(){return list.map(s=>s.name)},preview(i){if(list[i])show(list[i])},get playing(){return playing}}
}
