"""Local CAD management: persistent overrides, source upload jobs, and missing-reference reports."""
from pathlib import Path
import copy,collections,datetime,hashlib,html,json,math,os,re,secrets,subprocess,sys,threading,uuid
BASE=Path(__file__).resolve().parent
sys.path.insert(0,str(BASE/'scripts'))
from references import keys,codes

def write_json(path,data):
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
 tmp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp');tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8');os.replace(tmp,path)
def read_json(path,default=None):
 return json.loads(Path(path).read_text(encoding='utf-8')) if Path(path).exists() else copy.deepcopy(default)
def stamp():return datetime.datetime.now().astimezone().isoformat(timespec='seconds')
def signature(drawing,handle,code):return drawing+'|'+handle+'|'+code

class Manager:
 def __init__(self,base=BASE,recovery=True):
  from workspace import initialize
  initialize(base)
  self.base=Path(base);self.lock=threading.RLock();self.import_lock=threading.Lock();self.token=secrets.token_urlsafe(32)
  self.override_path=self.base/'data/manual-links.json'
  if recovery:
   from attribute_drafts import recover
   recover(self.base)
   for p in (self.base/'data/upload-jobs').glob('*.json'):
    j=read_json(p)
    if j.get('status') not in ('complete','failed'):
     j.update(status='failed',message='服务重启中断了导入，请重新上传。原文件已保留。');write_json(p,j)
   for p in (self.base/'data/attribute-jobs').glob('*.json'):
    j=read_json(p)
    if j.get('status') not in ('complete','failed'):
     folder=self.base/'data/attribute-revisions'/j['id'];backup=folder/'previous-output';live=self.base/'output'/j['drawing']
     if j.get('status')=='publishing' and backup.exists():
      if live.exists():os.replace(live,folder/'interrupted-output')
      os.replace(backup,live)
      for name,content in read_json(folder/'previous-indexes.json',{}).items():write_json(self.base/'data'/name,content)
     j.update(status='failed',message='服务重启中断了属性保存，请重新提交；上次正式图纸已保留。');write_json(p,j)
  self.reload()
 def reload(self,pending_links=None):
  self.validators=read_json(self.base/'data/validators.json',{})
  self.manifest={r['id']:r for r in read_json(self.base/'data/manifest.json',[])}
  self.base_catalog=read_json(self.base/'data/catalog.json',[])
  self.overrides=pending_links if pending_links is not None else self.vault.overrides() if getattr(self,'vault',None) else read_json(self.override_path,{'revision':0,'links':{},'history':[]})
  self.catalog=copy.deepcopy(self.base_catalog);self.catmap={r['id']:r for r in self.catalog}
  revisions=read_json(self.base/'data/attribute-edits.json',{}).get('revisions',{})
  for d in self.catalog:
   d['revision']=revisions.get(d['id'],0)
   d['team']=self.manifest[d['id']].get('team','工艺')
   for ref in d.get('references',[]):
    if len(ref['targets'])>1:ref['preferredTarget']=None
  for sid,patch in self.overrides['links'].items():
   d=self.catmap.get(patch['drawing'])
   if not d:continue
   ref=next((r for r in d['references'] if r['handle']==patch['handle'] and r['code']==patch['code']),None)
   if ref is None:
    ref={k:patch[k] for k in ('handle','code','key','xy','context')};d['references'].append(ref)
   valid=[t for t in patch['targets'] if t in self.catmap and t!=d['id']]
   ref.update(targets=valid,preferredTarget=patch['preferredTarget'] if patch['preferredTarget'] in valid else (valid[0] if len(valid)==1 else None),alternatives=[t for t in valid if t!=patch['preferredTarget']],selfReference=False,resolution='手动关联' if valid else '手动标记为未关联',manual=True,note=patch.get('note',''))
  # Calculated once per committed library refresh, never per reader.
  def digest(value):return hashlib.sha256(json.dumps(value,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
  self.ref_versions={r['id']:digest(r['references']) for r in self.catalog}
  self.library_version=digest([self.catalog,self.overrides['revision'],[(r['id'],r.get('workingDxf')) for r in self.manifest.values()]])
  from search_index import SearchIndex
  self.search_index=SearchIndex(self.catalog)
  self.report=self.missing_report()
  self.export_report()
 def drawing(self,id):return read_json(self.base/'output'/id/'drawing.json')
 def missing_report(self):
  groups={}
  for d in self.catalog:
   missing=[r for r in d['references'] if not r.get('targets') and not r.get('selfReference')]
   if not missing:continue
   doc=self.drawing(d['id']);items={i['handle']:i for i in doc['items']};x0,y0,x1,y1=doc['extents'];w=x1-x0;h=y1-y0
   for r in missing:
    x,y=r.get('xy',items.get(r['handle'],{}).get('xy',[x0,y0]));nx=max(0,min(.9999,(x-x0)/w));ny=max(0,min(.9999,(y1-y)/h))
    zone=['上部','中部','下部'][min(2,int(ny*3))]+' · '+['左侧','中间','右侧'][min(2,int(nx*3))]
    grid=chr(65+int(ny*6))+str(1+int(nx*8))
    near=sorted((t for t in doc['texts'] if t['handle']!=r['handle'] and t.get('zh')),key=lambda t:(t['xy'][0]-x)**2+(t['xy'][1]-y)**2)[:3]
    k=r['key'];g=groups.setdefault(k,{'key':k,'platform':k.split('-')[0],'codes':[],'occurrences':[]})
    if r['code'] not in g['codes']:g['codes'].append(r['code'])
    raw=next((t['text'] for t in doc['texts'] if t['handle']==r['handle'] and r['code'] in codes(t['text'])),r['context'])
    fields=[a['key'] for a in items.get(r['handle'],{}).get('attributes',[]) if r['code'] in codes(a.get('original',''))]
    origin='块属性 '+','.join(fields) if fields else 'CAD 文字标注'
    g['occurrences'].append({'drawing':d['id'],'sourceCode':d['code'],'sourceTitle':d['title'],'sourcePlatform':d['platform'],'sourceFile':d['source'],'handle':r['handle'],'code':r['code'],'context':raw,'referenceType':origin,'xy':[round(x,3),round(y,3)],'zone':zone,'grid':grid,'nearby':' / '.join(t['zh'] for t in near)[:250],'locatable':r['handle'] in items,'url':'http://127.0.0.1:8765/?loc='+r['handle']+'#'+d['id']})
  gs=sorted(groups.values(),key=lambda g:(g['platform'],g['key']));platforms=[]
  for p in sorted({g['platform'] for g in gs}):
   pg=[g for g in gs if g['platform']==p];platforms.append({'platform':p,'drawings':len(pg),'occurrences':sum(len(g['occurrences']) for g in pg)})
  return {'generatedAt':stamp(),'missingUnique':len(gs),'missingOccurrences':sum(len(g['occurrences']) for g in gs),'platforms':platforms,'groups':gs,'positionNote':'位置按原 CAD 坐标及图幅计算。A–F 行从上至下、1–8 列从左至右，为本清单的辅助定位网格，不是原图分区。'}
 def export_report(self):
  out=self.base/'reports';out.mkdir(exist_ok=True);r=self.report;e=html.escape
  text=['缺失关联 DWG 补图清单',f"{r['missingUnique']} 个图号，{r['missingOccurrences']} 处引用",r['positionNote'],'']
  parts=[f'<h1>缺失关联 DWG 补图清单</h1><p>{r["missingUnique"]} 个图号 · {r["missingOccurrences"]} 处引用</p><p>{e(r["positionNote"])}</p>']
  for p in r['platforms']:
   text.append(f"\n{p['platform']} 平台：{p['drawings']} 个图号，{p['occurrences']} 处引用")
   parts.append(f'<h2>{e(p["platform"])} 平台 <small>{p["drawings"]} 个图号 / {p["occurrences"]} 处引用</small></h2>')
   for g in (g for g in r['groups'] if g['platform']==p['platform']):
    text.append('\n待补图号：'+g['key']+'；原图写法：'+'、'.join(g['codes']))
    parts.append(f'<h3>{e(g["key"])}</h3><p>原图写法：{e("、".join(g["codes"]))}</p><table><thead><tr><th>引用图纸</th><th>引用位置</th><th>原文与邻近标注</th></tr></thead><tbody>')
    for o in g['occurrences']:
     loc=f"{o['zone']}；网格 {o['grid']}；句柄 {o['handle']}；{o['referenceType']}；X={o['xy'][0]}，Y={o['xy'][1]}"
     text.extend([f"  来源：{o['sourcePlatform']} / {o['sourceCode']} / {o['sourceTitle']}",f"  位置：{loc}",f"  引用：{o['context']}",f"  邻近：{o['nearby']}",f"  源文件：{o['sourceFile']}",f"  定位：{o['url']}"])
     parts.append(f'<tr><td><b>{e(o["sourceCode"])}</b><br>{e(o["sourceTitle"])}<details><summary>原始文件</summary>{e(o["sourceFile"])}</details></td><td>{e(loc)}<br><a href="{e(o["url"])}">定位到图纸</a></td><td>{e(o["context"])}<br><small>邻近：{e(o["nearby"])}</small></td></tr>')
    parts.append('</tbody></table>')
  report='<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>缺失关联 DWG 补图清单</title><style>body{font:14px/1.7 system-ui;margin:40px auto;max-width:1200px;padding:0 24px;color:#253039}h1{font-size:26px}h2{margin-top:40px;border-bottom:2px solid #d85a31}h3{margin-bottom:4px}small{font-size:12px;color:#6b7378}table{width:100%;border-collapse:collapse;table-layout:fixed}th,td{padding:12px;text-align:left;border:1px solid #ddd;vertical-align:top;overflow-wrap:anywhere}th{background:#f4f2ee}a{color:#b5431e}details{font-size:11px}@media print{body{margin:0;font-size:10pt}tr{break-inside:avoid}h2,h3{break-after:avoid}}</style>'+''.join(parts)+'</html>'
  (out/'缺失关联图号清单.html').write_text(report,encoding='utf-8');(out/'缺失关联图号清单.txt').write_text('\n'.join(text),encoding='utf-8');(self.base/'未提供的关联DWG清单.txt').write_text('\n'.join(text),encoding='utf-8');write_json(out/'missing-references.json',r)
 def state(self):
  attribute_jobs=[{k:v for k,v in read_json(p).items() if k not in ('attributes','blocks')} for p in (self.base/'data/attribute-jobs').glob('*.json')]
  from attribute_drafts import summary
  from cad_runtime import converter_status
  from diagnostics import snapshot
  return {'system':snapshot(self),'drafts':summary(self),'cadRuntime':converter_status(),'token':self.token,'revision':self.overrides['revision'],'missing':self.report,'manualLinks':list(self.overrides['links'].values()),'attributeJobs':sorted(attribute_jobs,key=lambda j:j['createdAt'],reverse=True)[:30],'uploads':sorted([read_json(p) for p in (self.base/'data/upload-jobs').glob('*.json')],key=lambda j:j['createdAt'],reverse=True)[:20]}
 def edit_link(self,data):
  with self.lock:
   if data.get('revision')!=self.overrides['revision']:raise ValueError('关联已被其他窗口修改，请重新打开编辑器后保存。')
   id=data.get('drawing');handle=str(data.get('handle',''));code=str(data.get('code','')).strip()
   if id not in self.catmap:raise ValueError('来源图纸不存在')
   doc=self.drawing(id);item=next((i for i in doc['items'] if i['handle']==handle),None)
   if not item:raise ValueError('来源图元不存在，请先在图纸中选择位置')
   kk=keys(code)
   if not kk and code and len(code)<=120 and code.isprintable():kk=[code]
   if not kk:raise ValueError('请填写完整关联图号，例如 CEPD-PR-1510')
   targets=data.get('targets',[])
   if not isinstance(targets,list) or len(targets)!=len(set(targets)) or any(t not in self.catmap or t==id for t in targets):raise ValueError('关联目标必须为目录中的其他图纸，且不能重复')
   preferred=data.get('preferredTarget') or (targets[0] if len(targets)==1 else None)
   if preferred is not None and preferred not in targets:raise ValueError('默认跳转图纸必须包含在关联目标中')
   ref=next((r for r in self.catmap[id]['references'] if r['handle']==handle and r['code']==code),None)
   xy=ref['xy'] if ref else data.get('xy',item['xy'])
   if not isinstance(xy,list) or len(xy)!=2 or not all(isinstance(v,(int,float)) and math.isfinite(v) for v in xy):raise ValueError('关联位置坐标无效')
   key=signature(id,handle,code);before=self.overrides['links'].get(key)
   if data.get('action')=='restore':self.overrides['links'].pop(key,None)
   else:self.overrides['links'][key]={'drawing':id,'handle':handle,'code':code,'key':kk[0],'context':ref['context'] if ref else code,'xy':xy,'targets':targets,'preferredTarget':preferred,'note':str(data.get('note',''))[:1000],'updatedAt':stamp()}
   from change_log import link_value
   auto=next((r for d in self.base_catalog if d['id']==id for r in d['references'] if r['handle']==handle and r['code']==code),None)
   self.overrides['revision']+=1;self.overrides['history'].append({'time':stamp(),'key':key,'actor':data.get('_actor','管理员'),'from':link_value(ref),'to':link_value(self.overrides['links'].get(key) or auto),'before':before,'after':self.overrides['links'].get(key)})
   if getattr(self,'vault',None):
    with self.vault.transaction() as db:
     self.vault.index_links(db,self.base_catalog,self.overrides)
     self.vault.sync_audit(db,self)
    # The active SQLite transaction is owned by the HTTP request.
    pending=self.overrides
    self.reload(pending)
   else:
    write_json(self.override_path,self.overrides);self.reload()
   return {'revision':self.overrides['revision'],'missingUnique':self.report['missingUnique']}
 def upload(self,stream,length,meta):
  filename=str(meta.get('filename',''))
  if Path(filename).name!=filename or '/' in filename or '\\' in filename or not filename.lower().endswith('.dwg') or len(filename.encode('utf-8'))>240 or any(ord(c)<32 for c in filename):raise ValueError('请上传 .dwg 文件，文件名不能包含路径或控制字符，且不能过长')
  code=str(meta.get('code','')).strip().upper();kk=keys(code);title=str(meta.get('title','')).strip();platform=str(meta.get('platform','')).strip().upper()
  from vault import TEAMS
  team=meta.get('team','工艺')
  if team not in TEAMS:raise ValueError('请选择所属专业')
  from disciplines import check_number
  check_number(team,code)
  if team!='工艺' and code and all(ch.isprintable() for ch in code):kk=[code]
  if not kk or len(code)>120:raise ValueError('请填写有效的完整图号')
  if not platform or len(platform)>80 or (team=='工艺' and platform!=kk[0].split('-')[0]):raise ValueError('所属平台应与图号一致')
  if not title or len(title)>140:raise ValueError('请填写图纸中文名称（最多 140 字）')
  if length<6 or length>64*1024*1024:raise ValueError('单张 DWG 文件大小应在 6 字节至 64 MB 之间')
  from cad_runtime import converter_status,drawing_font
  status=converter_status()
  if not getattr(self,'vault',None) and not status['available']:raise ValueError(status['message'])
  if not getattr(self,'vault',None):drawing_font()
  if not self.import_lock.acquire(blocking=False):raise ValueError('已有图纸正在导入，请等待完成后再上传')
  id='u'+uuid.uuid4().hex[:12];folder=self.base/'uploads'/id;folder.mkdir(parents=True);path=folder/filename
  try:
   digest=hashlib.sha256();remaining=length
   with path.open('wb') as f:
    while remaining:
     chunk=stream.read(min(1024*1024,remaining))
     if not chunk:raise ValueError('上传未完成，请重试')
     f.write(chunk);digest.update(chunk);remaining-=len(chunk)
   with path.open('rb') as f:header=f.read(6)
   if not re.fullmatch(rb'AC10[0-9]{2}',header):raise ValueError('文件不是有效的 DWG，不能仅修改扩展名后上传')
   existing=next((r for r in self.manifest.values() if r['sha256']==digest.hexdigest() and r.get('team','工艺')==team),None)
   if existing:raise ValueError('此 DWG 已在目录中：'+existing['code']+'。请直接编辑关联。')
   job={'id':id,'actor':meta.get('_actor','管理员'),'filename':filename,'team':team,'code':code,'title':title,'platform':platform,'sha256':digest.hexdigest(),'source':str(path.relative_to(self.base.parent)),'createdAt':stamp(),'status':'queued','message':'已接收，准备转换 CAD'}
   if getattr(self,'vault',None):
    from vault import archive
    archive(self.vault.root,path,job['sha256']);job['archived']=True;path.unlink()
   write_json(self.base/'data/upload-jobs'/f'{id}.json',job)
   if getattr(self,'vault',None):
    self.vault.enqueue('upload',dict(job,drawing=id),[id]);self.import_lock.release()
   else:threading.Thread(target=self.run_import,args=(id,),daemon=True).start()
   return job
  except:
   path.unlink(missing_ok=True);folder.rmdir();self.import_lock.release();raise
 def run_import(self,id):
  jobpath=self.base/'data/upload-jobs'/f'{id}.json'
  try:
   with (self.base/'uploads'/id/'import.log').open('w') as log:
    p=subprocess.run([sys.executable,str(BASE/'scripts/import_drawing.py'),str(self.base),id],stdout=log,stderr=log,timeout=600,env=dict(os.environ,PID_DATA_ROOT=str(self.base)))
   if p.returncode:raise RuntimeError('CAD 转换或校验失败，请检查文件是否可在 CAD 中打开。详情已保存在该次上传的 import.log。')
   bundle=read_json(self.base/'uploads'/id/'result.json')
   with self.lock:
    old_manifest=read_json(self.base/'data/manifest.json');old_catalog=read_json(self.base/'data/catalog.json');old_titles=read_json(self.base/'data/titles.json',{})
    try:
     write_json(self.base/'data/manifest.json',old_manifest+[bundle['manifest']]);write_json(self.base/'data/catalog.json',old_catalog+[bundle['catalog']]);write_json(self.base/'data/titles.json',dict(old_titles,**{id:bundle['catalog']['title']}))
     # Publication uses the same source-based resolver as the original 228 drawings.
     import references
     oldbase=references.BASE;references.BASE=self.base
     try:references.rebuild()
     finally:references.BASE=oldbase
     self.reload()
    except:
     write_json(self.base/'data/manifest.json',old_manifest);write_json(self.base/'data/catalog.json',old_catalog);write_json(self.base/'data/titles.json',old_titles);self.reload();raise
   job=read_json(jobpath);job.update(status='complete',message='导入完成，已建立图形、设备与关联索引',drawing=id,finishedAt=stamp());write_json(jobpath,job)
  except Exception as ex:
   job=read_json(jobpath);job.update(status='failed',message=str(ex),finishedAt=stamp());write_json(jobpath,job)
  finally:self.import_lock.release()
