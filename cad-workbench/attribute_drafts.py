"""Persistent attribute drafts and explicit, atomic multi-drawing CAD publication."""
from pathlib import Path
import copy,os,shutil,subprocess,sys,threading,uuid
from management import read_json,write_json,stamp
BASE=Path(__file__).resolve().parent

def drafts(base):return read_json(base/'data/attribute-drafts.json',{'counter':0,'blocks':{}})
def key(drawing,handle):return drawing+'|'+handle

def overlay_info(manager,info):
 pending=drafts(manager.base)['blocks'].get(key(info['drawing'],info['handle']))
 info['draftRevision']=pending['revision'] if pending else 0;info['hasDraft']=bool(pending)
 if pending:
  current={a['key']:a for a in info['attributes']}
  info['attributes']=[dict(current.get(a['key'],{'sourceOriginal':None,'readonly':False}),**a) for a in pending['attributes']]
 return info

def jobs(base):return sorted([read_json(p) for p in (base/'data/attribute-batches').glob('*/job.json')],key=lambda j:j['createdAt'],reverse=True)
def active(base):return any(j['status'] not in ('complete','failed') for j in jobs(base))
def summary(manager):
 rows=list(drafts(manager.base)['blocks'].values())
 return {'counter':drafts(manager.base)['counter'],'blocks':[dict(drawing=r['drawing'],handle=r['handle'],code=manager.catmap.get(r['drawing'],{}).get('code',r['drawing']),revision=r['revision'],updatedAt=r['updatedAt'],attributes=r['attributes']) for r in rows],'drawingCount':len({r['drawing'] for r in rows}),'blockCount':len(rows),'jobs':jobs(manager.base)[:20]}

def save(manager,data):
 from attribute_editor import normalize
 with manager.lock:
  if active(manager.base):raise ValueError('正在统一保存，完成后可继续编辑；已有草稿已保留')
  info,rows=normalize(manager,data);store=drafts(manager.base);store['counter']+=1
  record={'drawing':info['drawing'],'handle':info['handle'],'baseRevision':info['revision'],'revision':store['counter'],'attributes':rows,'updatedAt':stamp()}
  store['blocks'][key(info['drawing'],info['handle'])]=record;write_json(manager.base/'data/attribute-drafts.json',store)
  return {'status':'draft','message':'修改已暂存；点击“统一保存”后生成 CAD 图纸','draftRevision':record['revision'],'summary':summary(manager)}

def discard(manager,data):
 with manager.lock:
  if active(manager.base):raise ValueError('统一保存期间不能撤销草稿')
  store=drafts(manager.base);k=key(str(data.get('drawing','')),str(data.get('handle','')));record=store['blocks'].get(k)
  if not record or record['revision']!=data.get('draftRevision'):raise ValueError('草稿已变更，请刷新后重试')
  del store['blocks'][k];store['counter']+=1;write_json(manager.base/'data/attribute-drafts.json',store);return summary(manager)

def submit(manager,data):
 from attribute_editor import state
 from cad_runtime import converter_status
 with manager.lock:
  pending=drafts(manager.base)
  if not pending['blocks']:raise ValueError('没有待保存的修改')
  if data.get('counter')!=pending['counter']:raise ValueError('草稿列表已变化，请刷新待保存清单后重试')
  runtime=converter_status()
  if not runtime['available']:raise ValueError(runtime['message']+' 草稿已保留。')
  st=state(manager.base)
  for r in pending['blocks'].values():
   if st['revisions'].get(r['drawing'],0)!=r['baseRevision']:raise ValueError('图纸版本已变化，请重新核对草稿：'+r['drawing'])
  if not manager.import_lock.acquire(blocking=False):raise ValueError('已有 CAD 图纸正在处理，请稍后统一保存')
  try:
   bid='b'+uuid.uuid4().hex[:12];folder=manager.base/'data/attribute-batches'/bid;grouped={}
   for r in pending['blocks'].values():grouped.setdefault(r['drawing'],[]).append(r)
   children=[]
   for drawing,blocks in grouped.items():
    jid=bid+'-'+drawing;r=manager.catmap[drawing]
    child={'id':jid,'batch':bid,'kind':'attributes','drawing':drawing,'code':r['code'],'title':r['title'],'handle':blocks[0]['handle'],'blocks':blocks,'revision':blocks[0]['baseRevision'],'createdAt':stamp(),'status':'queued','message':'等待统一保存'}
    write_json(manager.base/'data/attribute-jobs'/f'{jid}.json',child);children.append(jid)
   job={'id':bid,'children':children,'status':'queued','createdAt':stamp(),'drawings':len(grouped),'blocks':len(pending['blocks']),'counter':pending['counter'],'message':'准备合并修改并统一生成 DWG'}
   write_json(folder/'job.json',job);threading.Thread(target=run,args=(manager,bid),daemon=True).start();return job
  except:manager.import_lock.release();raise

def restore(base,folder):
 snapshot=read_json(folder/'previous-indexes.json',{})
 for jid in read_json(folder/'job.json')['children']:
  child=read_json(base/'data/attribute-jobs'/f'{jid}.json');revision=base/'data/attribute-revisions'/jid;backup=revision/'previous-output';live=base/'output'/child['drawing']
  if backup.exists():
   if live.exists():shutil.rmtree(live)
   os.replace(backup,live)
 for p in (folder/'previous-metadata').glob('*.json'):shutil.copy2(p,base/'output'/p.stem/'drawing.json')
 for name,content in snapshot.items():write_json(base/'data'/name,content)

def recover(base):
 for job in jobs(base):
  if job['status']=='complete':
   for jid in job['children']:
    p=base/'data/attribute-jobs'/f'{jid}.json';child=read_json(p)
    if child and child['status']!='complete':child.update(status='complete',message=job['message'],finishedAt=job.get('finishedAt',stamp()));write_json(p,child)
   continue
  if job['status']=='failed':continue
  folder=base/'data/attribute-batches'/job['id']
  if job['status']=='publishing':restore(base,folder)
  job.update(status='failed',message='服务重启中断统一保存；正式图纸已保留，草稿可重新保存');write_json(folder/'job.json',job)
  for jid in job['children']:
   p=base/'data/attribute-jobs'/f'{jid}.json';child=read_json(p);child.update(status='failed',message=job['message']);write_json(p,child)

def run(manager,bid):
 from attribute_editor import state
 base=manager.base;folder=base/'data/attribute-batches'/bid;path=folder/'job.json'
 try:
  with (folder/'build.log').open('w') as log:
   p=subprocess.run([sys.executable,str(BASE/'scripts/publish_attributes.py'),str(base),bid],stdout=log,stderr=log,timeout=1800)
  if p.returncode:raise RuntimeError(read_json(folder/'failure.json',{}).get('error','生成或校验失败，正式图纸未替换，草稿已保留'))
  job=read_json(path)
  with manager.lock:
   snapshot={name:read_json(base/'data'/name,{} if name in ('attribute-edits.json','attribute-drafts.json') else []) for name in ('manifest.json','catalog.json','attribute-edits.json','attribute-drafts.json')}
   write_json(folder/'previous-indexes.json',snapshot)
   for r in manager.catalog:
    dst=folder/'previous-metadata'/f"{r['id']}.json";dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(base/'output'/r['id']/'drawing.json',dst)
   job.update(status='publishing',message='全部校验通过，正在统一发布');write_json(path,job)
   try:
    manifests=copy.deepcopy(snapshot['manifest.json']);catalogs=copy.deepcopy(snapshot['catalog.json']);st=state(base);pending=drafts(base)
    for jid in job['children']:
     child=read_json(base/'data/attribute-jobs'/f'{jid}.json');id=child['drawing'];revision=base/'data/attribute-revisions'/jid
     os.replace(base/'output'/id,revision/'previous-output');os.replace(revision/'stage/output'/id,base/'output'/id)
     r=next(r for r in manifests if r['id']==id);r['workingDxf']=str((revision/'working.dxf').relative_to(base));r['workingRoundtrip']=str((revision/'roundtrip/中文图纸.dxf').relative_to(base))
     new=read_json(revision/'result.json')['catalog'];catalogs=[new if r['id']==id else r for r in catalogs];st['revisions'][id]=child['revision']+1
     for block in child['blocks']:
      handle=block['handle'];before=st['blocks'].get(id,{}).get(handle);after={'attributes':block['attributes'],'updatedAt':stamp(),'job':jid}
      st['blocks'].setdefault(id,{})[handle]=after;st['history'].append({'job':jid,'batch':bid,'drawing':id,'handle':handle,'before':before,'after':after,'time':stamp()})
      k=key(id,handle)
      if pending['blocks'].get(k,{}).get('revision')==block['revision']:pending['blocks'].pop(k)
    for name,content in [('manifest.json',manifests),('catalog.json',catalogs),('attribute-edits.json',st),('attribute-drafts.json',pending)]:write_json(base/'data'/name,content)
    import references
    previous=references.BASE;references.BASE=base
    try:references.rebuild()
    finally:references.BASE=previous
    manager.reload();job.update(status='complete',message=f"已统一保存 {job['drawings']} 张图纸、{job['blocks']} 个块的修改",finishedAt=stamp());write_json(path,job)
   except:restore(base,folder);manager.reload();raise
  for jid in job['children']:
   p=base/'data/attribute-jobs'/f'{jid}.json';child=read_json(p);child.update(status='complete',message=job['message'],finishedAt=stamp());write_json(p,child)
 except Exception as ex:
  job=read_json(path);job.update(status='failed',message=str(ex),finishedAt=stamp());write_json(path,job)
  for jid in job['children']:
   p=base/'data/attribute-jobs'/f'{jid}.json';child=read_json(p);child.update(status='failed',message=job['message']);write_json(p,child)
 finally:manager.import_lock.release()

def worker(base,bid):
 from attribute_editor import worker as prepare,verify_prepared
 from cad_runtime import convert
 folder=base/'data/attribute-batches'/bid;path=folder/'job.json';job=read_json(path)
 def progress(message):
  if read_json(path)['status']=='failed':raise RuntimeError('统一保存已中断')
  job.update(status='processing',message=message);write_json(path,job)
 inputs=folder/'inputs';dwgs=folder/'dwgs';rt=folder/'roundtrip';inputs.mkdir(exist_ok=True)
 for n,jid in enumerate(job['children'],1):
  progress(f"正在合并第 {n}/{job['drawings']} 张图纸的修改")
  prepare(base,jid,prepare_only=True);child=read_json(base/'data/attribute-jobs'/f'{jid}.json');revision=base/'data/attribute-revisions'/jid
  shutil.copy2(revision/'working.dxf',inputs/(child['drawing']+'.dxf'))
 progress('正在批量生成 DWG');convert(inputs,dwgs,'DWG','*.dxf')
 progress('正在批量回读校验 DWG');convert(dwgs,rt,'DXF','*.dwg')
 for jid in job['children']:
  child=read_json(base/'data/attribute-jobs'/f'{jid}.json');id=child['drawing'];revision=base/'data/attribute-revisions'/jid
  verify_prepared(base,jid,rt/(id+'.dxf'));(revision/'roundtrip').mkdir(exist_ok=True)
  shutil.copy2(rt/(id+'.dxf'),revision/'roundtrip/中文图纸.dxf');shutil.copy2(dwgs/(id+'.dwg'),revision/'stage/output'/id/'中文图纸.dwg')
 write_json(folder/'verification.json',{'passed':True,'drawings':job['drawings'],'blocks':job['blocks'],'converterInvocations':2,'conversionBatches':1,'roundtripBatches':1});progress('全部图纸校验通过')
