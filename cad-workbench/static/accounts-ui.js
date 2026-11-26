const el=id=>document.getElementById(id);
let session;
async function request(path,options){
 const response=await fetch(path,options);
 if(response.status===401&&path!=='/api/auth/passwords')location.replace('/login?next=/accounts.html');
 const result=await response.json();
 if(!response.ok)throw Error(result.error||'请求失败');
 return result;
}
function post(path,data,headers={}){
 return request(path,{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':session.csrf,...headers},body:JSON.stringify(data)});
}
function edit(user){
 const form=el('editorForm');form.reset();
 el('editorTitle').textContent=user?'编辑账号':'新增账号';
 form.elements.login.value=user?.login||'';form.elements.login.readOnly=!!user;
 form.elements.name.value=user?.name||'';form.elements.enabled.checked=user?!!user.enabled:true;
 form.elements.password.required=!user;form.elements.password.placeholder=user?'留空保留当前密码':'至少 8 个字符';
 for(const box of form.querySelectorAll('[name=team]'))box.checked=!!user?.teams.includes(box.value);
 form.querySelector('.error').textContent='';el('editorDialog').showModal();
}
async function list(){
 const rows=await request('/api/admin/accounts'),host=el('users');host.replaceChildren();
 for(const user of rows){
  const row=document.createElement('div'),text=document.createElement('div'),name=document.createElement('strong'),meta=document.createElement('p'),button=document.createElement('button');
  row.className='user-row';name.textContent=user.name+' · '+user.login;
  meta.textContent=(user.enabled?'已启用':'已停用')+' · '+(user.teams.join('、')||'未授权专业');
  button.className='ui-button';button.textContent='编辑';button.setAttribute('aria-label','编辑 '+user.login);button.onclick=()=>edit(user);
  text.append(name,meta);row.append(text,button);host.append(row);
 }
 if(!rows.length){const empty=document.createElement('p');empty.className='empty';empty.textContent='尚无专业编辑账号。';host.append(empty)}
}
function bindForm(id,save){
 const form=el(id);
 form.onsubmit=async event=>{
  event.preventDefault();const button=event.submitter||form.querySelector('.primary'),error=form.querySelector('.error');
  button.disabled=true;error.textContent='';
  try{await save(new FormData(form))}catch(e){error.textContent=e.message}finally{button.disabled=false}
 };
}
bindForm('editorForm',async data=>{
 const state=await request('/api/admin/state');
 await post('/api/admin/accounts',{login:data.get('login'),name:data.get('name'),password:data.get('password'),teams:data.getAll('team'),enabled:data.has('enabled')},{'X-Management-Token':state.token});
 el('editorDialog').close();el('notice').textContent='账号授权已保存。';
 try{await list()}catch(error){el('notice').textContent='已保存，列表刷新失败。请刷新页面。'}
});
bindForm('passwordForm',async data=>{
 const d=Object.fromEntries(data);
 if(!d.adminPassword&&!d.viewerPassword)throw Error('请填写至少一个新密码。');
 if(d.adminPassword!==d.adminConfirm||d.viewerPassword!==d.viewerConfirm)throw Error('两次输入的新密码不一致。');
 await post('/api/auth/passwords',{currentPassword:d.currentPassword,adminPassword:d.adminPassword,viewerPassword:d.viewerPassword});
 location.replace('/login?next=/accounts.html');
});
for(const b of document.querySelectorAll('[data-close]'))b.onclick=()=>b.closest('dialog').close();
for(const dialog of document.querySelectorAll('dialog'))dialog.onclose=()=>dialog.querySelector('form').reset();
el('add').onclick=()=>edit(null);
el('change').onclick=()=>{el('passwordForm').querySelector('.error').textContent='';el('passwordDialog').showModal()};
el('logout').onclick=async()=>{try{await post('/api/auth/logout',{});location.replace('/login')}catch(e){el('notice').textContent=e.message}};
try{
 session=await request('/api/auth/session');
 if(!session.authenticated)location.replace('/login?next=/accounts.html');
 else{
  const names={viewer:'普通用户',admin:'管理员',editor:'专业编辑'};
  el('identity').textContent=session.name||names[session.role];
  el('access').textContent=session.role==='viewer'?'可浏览、查询与下载图纸。':[names[session.role],session.login,session.role==='editor'&&session.teams.join('、')].filter(Boolean).join(' · ');
  el('logout').disabled=false;
  if(session.role==='admin'){const config=await request('/api/capabilities'),fieldset=el('editorForm').querySelector('fieldset');fieldset.replaceChildren(Object.assign(document.createElement('legend'),{textContent:'专业授权'}));for(const team of config.teams){const label=document.createElement('label'),box=document.createElement('input');box.type='checkbox';box.name='team';box.value=team.name;label.append(box,document.createTextNode(team.name+(team.enabled?'':'（已停用）')));fieldset.append(label)}el('editors').hidden=false;el('passwordCard').hidden=false;await list()}
 }
}catch(e){el('notice').textContent=e.message}
window.addEventListener('pageshow',event=>{if(event.persisted)location.reload()});
