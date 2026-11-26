class ProductHeader extends HTMLElement {
 async connectedCallback(){
  const active=this.getAttribute('section');
  try{
   const [config,session]=await Promise.all([fetch('/api/capabilities').then(r=>r.json()),fetch('/api/auth/session').then(r=>r.json())]);
   if(!config.enabled)return;
   const tabs=[['drawings','图纸工作区','/',true],['twin','数字孪生','/twin.html',config.enabled.models],['equipment','设备','/?tab=equipment',config.enabled.equipment],['logic','因果逻辑','/?tab=logic',config.enabled.logic]];
   this.innerHTML='<div class="product-header" role="banner"><a class="product-brand" href="/"><span class="brand-mark" aria-hidden="true"><i></i><i></i><i></i><i></i></span><strong></strong></a><span class="project"></span><div class="product-links" role="navigation" aria-label="工作区">'+tabs.filter(t=>t[3]).map(([id,title,url])=>'<a href="'+url+'"'+(id===active?' aria-current="page"':'')+'>'+title+'</a>').join('')+'</div>'+(session.role==='admin'?'<a class="product-account" href="/settings.html"'+(active==='settings'?' aria-current="page"':'')+'>系统设置</a>':'')+'<a class="product-account" href="/accounts.html"'+(active==='accounts'?' aria-current="page"':'')+'>账号中心</a></div>';
   this.querySelector('strong').textContent=config.systemName;this.querySelector('.project').textContent=config.projectName;document.title=(active==='accounts'?'账号中心':active==='settings'?'系统设置':'模型浏览')+' · '+config.systemName;
  }catch{this.innerHTML='<a href="/">返回工作台</a>'}
 }
}
customElements.define('product-header',ProductHeader);
