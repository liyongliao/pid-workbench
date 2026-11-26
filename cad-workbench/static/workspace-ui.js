function openInspector(){
 const popup=document.getElementById('inspector');
 if(!popup.matches(':popover-open'))popup.showPopover();
 restoreFloatingPosition();
}
function closeDirectory(){
 document.body.classList.remove('directory-open');
 document.getElementById('directoryToggle')?.setAttribute('aria-expanded','false');
}
const directoryButton=document.getElementById('directoryToggle');
directoryButton?.addEventListener('click',()=>{
 const open=document.body.classList.toggle('directory-open');
 directoryButton.setAttribute('aria-expanded',String(open));
 if(open)document.getElementById('search').focus();
});
function closeMenus(except){
 for(const menu of document.querySelectorAll('.action-menu[open]')){
  if(menu!==except)menu.open=false;
 }
}
document.addEventListener('click',event=>{
 const menu=event.target.closest('.action-menu');
 closeMenus(event.target.closest('summary')?menu:null);
 if(!event.target.closest('#projectDirectory,#directoryToggle'))closeDirectory();
});
document.addEventListener('keydown',event=>{
 if(event.key!=='Escape')return;
 const menu=document.querySelector('.action-menu[open]');
 if(menu){closeMenus();menu.querySelector('summary').focus()}
 closeDirectory();
});

const inspector=document.getElementById('inspector');
const positionKey='pid.inspector.position.v1';
let floatingPosition=null;
try{
 const saved=JSON.parse(localStorage.getItem(positionKey));
 if(Number.isFinite(saved?.x)&&Number.isFinite(saved?.y))floatingPosition=saved;
}catch{}
function restoreFloatingPosition(){
 if(!inspector?.matches(':popover-open')||!floatingPosition)return;
 const {width,height}=inspector.getBoundingClientRect();
 const x=Math.min(Math.max(4,floatingPosition.x),Math.max(4,innerWidth-width-4));
 const y=Math.min(Math.max(4,floatingPosition.y),Math.max(4,innerHeight-height-4));
 Object.assign(inspector.style,{inset:'auto',top:y+'px',left:x+'px'});
}
if(inspector){
 const grip=inspector.querySelector('.inspector-header');
 function save(){try{localStorage.setItem(positionKey,JSON.stringify(floatingPosition))}catch{}}
 grip.onpointerdown=e=>{
  if(e.button!==0||e.target.closest('button'))return;
  const rect=inspector.getBoundingClientRect(),dx=e.clientX-rect.left,dy=e.clientY-rect.top;
  grip.setPointerCapture(e.pointerId);
  grip.onpointermove=move=>{floatingPosition={x:move.clientX-dx,y:move.clientY-dy};restoreFloatingPosition()};
  grip.onlostpointercapture=()=>{grip.onpointermove=null;save()}
 };
 grip.onkeydown=e=>{
  if(e.target!==grip||!e.key.startsWith('Arrow'))return;
  e.preventDefault();const r=inspector.getBoundingClientRect();
  floatingPosition={x:r.left+({ArrowLeft:-12,ArrowRight:12}[e.key]||0),y:r.top+({ArrowUp:-12,ArrowDown:12}[e.key]||0)};
  restoreFloatingPosition();save()
 };
 inspector.addEventListener('beforetoggle',event=>{
  if(event.newState!=='closed')return;
  const {left,top,width}=inspector.getBoundingClientRect();
  if(width){floatingPosition={x:left,y:top};save()}
 });
 inspector.addEventListener('toggle',restoreFloatingPosition);
 new ResizeObserver(restoreFloatingPosition).observe(inspector);
 window.addEventListener('resize',restoreFloatingPosition)
}
