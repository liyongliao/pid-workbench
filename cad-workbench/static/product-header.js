class ProductHeader extends HTMLElement {
 connectedCallback(){
  const active=this.getAttribute('section');
  const tabs=[['drawings','联动工作区','/'],['twin','数字孪生','/twin.html'],['equipment','设备','/?tab=equipment'],['logic','因果逻辑','/?tab=logic']];
  this.innerHTML='<div class="product-header" role="banner"><a class="product-brand" href="/"><span class="brand-mark" aria-hidden="true"><i></i><i></i><i></i><i></i></span><strong>图纸工作台</strong></a><span class="project">工程图纸与模型</span><div class="product-links" role="navigation" aria-label="工作区">'+tabs.map(([id,title,url])=>'<a href="'+url+'"'+(id===active?' aria-current="page"':'')+'>'+title+'</a>').join('')+'</div><a class="product-account" href="/accounts.html">账号中心</a></div>';
 }
}
customElements.define('product-header',ProductHeader);
