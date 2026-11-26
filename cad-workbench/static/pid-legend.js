// Decode each field against the matching project's legend, preserving the CAD value.
const PidLegend = (() => {
 const sizeToken = '(?:\\d+(?: \\d+\\/\\d+|\\/\\d+)?"|(?:DN)?\\d+)';
 const valve = new RegExp('^('+sizeToken+')?\\s*([A-Z]\\d+[A-Z]?)\\s*-\\s*(\\d+)([A-Z])([A-NP-Z]*)(?:O([A-Z]))?$');
 const pipe = new RegExp('^('+sizeToken+')\\s*(?:-\\s*|\\s+)([A-Z][A-Z0-9]*)-(\\d+)-(\\d+)-([A-Z]\\d+)(?:-([A-Z0-9]+))?$');
 const modern = new RegExp('^('+sizeToken+')\\s*-\\s*([A-Z][A-Z0-9]*)-(\\d{2})\\s*(\\d{3})-([A-K]\\d[A-Z][A-Z]\\d[A-Z]|[A-KMOP]\\d[A-Z][A-Z])(?:-([A-Z0-9]+))?$');
 const sizeText = size => size.endsWith('"') ? '公称管径 '+size.slice(0,-1)+' 英寸' : '公称直径 DN'+size.replace(/^DN/,'');
 const unknown = '图例未列此代码，请核对原图';
 function decode(raw, c) {
  const value=String(raw||'').trim().toUpperCase().replace(/[″＂”]/g,'"').replace(/[‐‑–－]/g,'-').replace(/\s*-\s*/g,'-').replace(/\s+/g,' ');
  const fields=[];
  const add=(name,code,meaning)=>fields.push({name,code,meaning:meaning||unknown});
  let m=valve.exec(value);
  if(m){
   const [,size,grade,type,end,special,opposite]=m;
   if(size)add('公称尺寸',size,sizeText(size));
   add('管道等级',grade,c.classes[grade]);add('阀门型式',type,c.valves[type]);add('端部连接',end,c.ends[end]);
   for(const code of special)add('特殊型式',code,c.special[code]);
   if(opposite)add('另一端连接','O'+opposite,c.ends[opposite]);
   return {title:c.valves[type]||'阀门编号',source:'old',page:1,fields};
  }
  m=pipe.exec(value);
  if(m){
   const [,size,service,system,sequence,grade,insulation]=m;
   add('公称尺寸',size,sizeText(size));add('介质',service,c.service[service]);add('系统号',system,c.systems[system]);
   add('管线顺序号',sequence,'系统内的管线顺序号');add('管道等级',grade,c.classes[grade]);
   if(insulation)add('绝热代号',insulation,c.insulation[insulation]);
   return {title:'管线编号',source:'old',page:1,fields};
  }
  m=modern.exec(value);
  if(m){
   const [,size,service,system,sequence,grade,insulation]=m;
   const manual=grade.length===4;
   add('公称尺寸',size,sizeText(size));add('介质',service,(manual?c.manualService:c.newService)[service]);
   add('系统号',system,(manual?c.manualSystems:c.newSystems)[system]);add('管线顺序号',sequence,'系统内的管线顺序号');
   add('压力等级',grade[0],(manual?c.manualRatings:c.ratings)[grade[0]]);
   if(manual){
    add('材料及明细',grade.slice(1,3),c.manualMaterials[grade.slice(1,3)]);
    add('特殊要求',grade[3],c.manualRequirements[grade[3]]);
   }else{
    add('等级细分',grade[1],grade[1]==='0'?'完整压力等级':'细分等级 '+grade[1]);
    add('材料',grade.slice(2,4),c.materials[grade.slice(2,4)]);add('腐蚀／冲蚀／机械裕量',grade[4],c.allowance[grade[4]]);
    add('特殊要求',grade[5],c.requirements[grade[5]]);
   }
   if(insulation){
    const match=/^([HTSPC]+)(\d{2})?$/.exec(insulation);
    if(match){for(const ch of match[1])add('绝热／伴热',ch,c.newInsulation[ch]);if(match[2])add('维持温度',match[2],Number(match[2])+' ℃')}
    else add('绝热代号',insulation);
   }
   return {title:'管线编号',source:manual?'manual':'new',page:1,fields};
  }
  m=/^(?:([A-Z][A-Z0-9]*)-)?(SDV|BDV|PSV)[- ]?(\d+[A-Z]?)$/.exec(value);
  if(m){
   if(m[1])add('位号前缀',m[1],'原图标注的区域或平台前缀');
   add('功能代号',m[2],c.functions[m[2]]);add('编号',m[3],'原图功能位号编号');
   return {title:c.functions[m[2]],source:'new',page:3,fields};
  }
  return null;
 }
 function selection(item,object){
  const attrs=Object.fromEntries((item.attributes||[]).map(a=>[a.key,String(a.value||'').trim()]));
  const line=attrs.LN_TAG||attrs['LINE-TAG']||attrs.LINE_NO, valve=attrs.VA_TAG||attrs.VTAG;
  if(line||valve)return {tags:[line||valve],kind:line?'管线':'阀门'};
  if(object?.kind==='管线')return {tags:[...new Set(object.lineTags||[])],kind:'管线'};
  if(object?.kind==='阀门'||object?.kind==='管线标注')return {tags:item.tag?[item.tag]:[],kind:object.kind};
  return null;
 }
 return {decode,selection};
})();
if(typeof module!=='undefined'&&module.exports)module.exports=PidLegend;
