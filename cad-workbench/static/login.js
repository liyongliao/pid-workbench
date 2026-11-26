const el=id=>document.getElementById(id);
const help={
 viewer:['输入普通用户的共享访问密码。','普通用户使用共享密码，请联系项目管理员获取。'],
 editor:['使用已获专业授权的账号登录。','请联系项目管理员，在「账号中心 → 编辑账号」查看登录账号或设置新密码。'],
 admin:['输入管理员账号和访问密码。','在运行工作台的 Mac 上，打开 PID 项目目录，双击「重置本机管理员密码.command」。窗口会提示管理员账号，并允许设置新密码。NAS 部署请由服务器管理员使用项目的密码重置脚本。']
};
let role='viewer';
function destination(){
 const next=new URLSearchParams(location.search).get('next')||'/';
 try{const url=new URL(next,location.origin);if(url.origin===location.origin&&!url.pathname.startsWith('/login'))return url.pathname+url.search+(location.hash||url.hash)}catch{}
 return '/';
}
function selectRole(next,focus=true){
 role=next;
 for(const button of document.querySelectorAll('[data-role]'))button.setAttribute('aria-pressed',String(button.dataset.role===next));
 const named=role!=='viewer';
 el('loginLabel').hidden=!named;el('username').required=named;
 el('formHelp').classList.add('sr-only');el('formHelp').textContent=help[role][0];el('recoverHelp').textContent=help[role][1];el('loginError').textContent='';
 el('password').value='';el('password').type='password';
 el('showPassword').textContent='显示';el('showPassword').setAttribute('aria-label','显示密码');el('showPassword').setAttribute('aria-pressed','false');
 if(focus)el(named?'username':'password').focus();
}
for(const b of document.querySelectorAll('[data-role]'))b.onclick=()=>selectRole(b.dataset.role);
el('showPassword').onclick=()=>{
 const show=el('password').type==='password';el('password').type=show?'text':'password';
 el('showPassword').textContent=show?'隐藏':'显示';el('showPassword').setAttribute('aria-label',show?'隐藏密码':'显示密码');el('showPassword').setAttribute('aria-pressed',String(show));
};
for(const id of ['loginForm','setupForm'])el(id).onsubmit=async e=>{
 e.preventDefault();
 const form=e.currentTarget,submit=e.submitter||form.querySelector('.primary');
 submit.disabled=true;el('loginError').textContent='';
 try{
  const setup=id==='setupForm',data=setup?Object.fromEntries(new FormData(form)):{role,login:el('username').value.trim(),password:el('password').value};
  if(setup&&(data.adminPassword!==data.adminConfirm||data.viewerPassword!==data.viewerConfirm))throw Error('两次输入的密码不一致');
  const r=await fetch('/api/auth/'+(setup?'setup':'login'),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
  if(!r.ok)throw Error((await r.json()).error||'登录失败');
  form.reset();location.replace(destination());
 }catch(error){el('loginError').textContent=error.message}finally{submit.disabled=false}
};
(async()=>{
 try{
  const session=await (await fetch('/api/auth/session')).json();
  if(session.authenticated){location.replace(destination());return}
  if(!session.configured){location.replace('/setup');return}
  if(session.configured){el('loginForm').hidden=false;selectRole('viewer',false)}
  else if(session.canSetup){el('formTitle').textContent='启用图纸工作台';el('formHelp').textContent='设置管理员账号与普通用户访问密码。';el('setupForm').hidden=false}
  else{el('formTitle').textContent='等待管理员启用';el('formHelp').textContent='请管理员在服务器本机打开工作台，完成首次密码设置。'}
 }catch{el('loginError').textContent='暂时无法连接服务，请刷新重试。'}
})();

fetch('/api/site').then(r=>r.json()).then(site=>{document.title='登录 · '+site.systemName;const brand=document.querySelector('.brand');brand.lastChild.textContent=site.systemName;el('projectName').textContent=site.projectName;el('projectDescription').textContent=site.description}).catch(()=>{});
