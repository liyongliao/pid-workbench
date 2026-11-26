// Apply the server's capability decisions consistently across the workbench.
async function initializeSite(){
 const caps=await api('/api/capabilities');S.capabilities=caps;
 document.title=caps.systemName;document.querySelector('.brand b').textContent=caps.systemName;document.querySelector('.app-header .project').textContent=caps.projectName;document.querySelector('.brand').title=caps.systemName;
 document.getElementById('pidLegend').hidden=!caps.hasLegends;
 const filter=document.getElementById('teamFilter'),selected=filter.value;
 filter.replaceChildren(new Option('全部专业',''),...caps.teams.map(t=>new Option(t.name+(t.enabled?'':'（已停用）'),t.name)));filter.value=selected;
 teamNames.splice(0,teamNames.length,...caps.teams.filter(t=>t.enabled).map(t=>t.name));
 for(const key of ['equipment','logic'])document.querySelector(`[data-tab="${key}"]`).hidden=!caps.enabled[key];
 document.querySelector('.app-header a[href="/twin.html"]').hidden=!caps.enabled.models;
 const drawingTools=['missingList','reviewAudit','releases','coverage','fileCoverage','printResults'];
 for(const id of drawingTools){const button=document.getElementById(id);if(button)button.hidden=!caps.enabled.drawings||(id==='releases'&&S.role==='viewer')}
 document.getElementById('systemSettings').hidden=S.role!=='admin';
 document.getElementById('systemSettings').onclick=()=>location.assign('/settings.html');
 const available=caps.enabled.drawings;
 for(const button of document.querySelectorAll('.drawing-actions button'))button.disabled=!available;
 document.querySelector('[data-tab="drawings"]').textContent='图纸工作区';
 if(!available&&S.drawing){S.drawing=null;S.selected=null;document.getElementById('scene').replaceChildren();setTab('drawings')}
 if(['equipment','logic'].includes(S.tab)&&!caps.enabled[S.tab])setTab('drawings');
 Linked.configure(caps);
 if(caps.setupRequired&&S.role==='admin'){location.replace('/setup');throw Error('正在打开初始化向导…')}
 return caps;
}
