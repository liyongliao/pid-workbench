"""Edit real ATTRIB records on a derived CAD revision, retaining source DWGs."""
from pathlib import Path
import collections,copy,hashlib,json,math,os,re,shutil,subprocess,sys,threading,uuid
BASE=Path(__file__).resolve().parent
sys.path.insert(0,str(BASE/'scripts'))
from management import read_json,write_json,stamp
import ezdxf
from translate import translate
from build import ATTR
from preserve_cad import records,value

def state(base):return dict({'revisions':{},'blocks':{},'history':[]},**read_json(base/'data/attribute-edits.json',{}))
def working(base,r):return base/r['workingDxf'] if r.get('workingDxf') else base/'output'/r['id']/'中文图纸.dxf'
def block_info(manager,id,handle,include_draft=True):
 if id not in manager.manifest:raise ValueError('图纸不存在')
 r=manager.manifest[id];doc=ezdxf.readfile(working(manager.base,r));e=doc.entitydb.get(handle)
 if e is None or e.dxftype()!='INSERT' or e.dxf.owner!=doc.modelspace().block_record_handle:raise ValueError('请选择图纸中的块对象后编辑属性')
 if doc.blocks[e.dxf.name].block.dxf.flags&12:raise ValueError('外部参照块请在其源图中修改属性')
 source=ezdxf.readfile(manager.base/r['dxf']);original=source.entitydb.get(handle)
 old={a.dxf.tag.upper():a.dxf.text for a in original.attribs} if original is not None and original.dxftype()=='INSERT' else {}
 st=state(manager.base);saved=st['blocks'].get(id,{}).get(handle,{});labels={a['key']:a['label'] for a in saved.get('attributes',[])}
 prompts={a.dxf.tag.upper():a.dxf.get('prompt','') for a in doc.blocks[e.dxf.name] if a.dxftype()=='ATTDEF'}
 known=next((i for i in manager.drawing(id)['items'] if i['handle']==handle),{});known_labels={a['key']:a['label'] for a in known.get('attributes',[])}
 attributes=[]
 for a in e.attribs:
  key=a.dxf.tag.upper();label=labels.get(key) or known_labels.get(key) or ATTR.get(key) or translate(prompts.get(key,'')) or '扩展属性（'+key+'）'
  if key not in labels and not re.search(r'[\u4e00-\u9fff]',label):label='扩展属性（'+key+'）'
  attributes.append({'key':key,'label':label,'value':a.dxf.text,'sourceOriginal':old.get(key),'visible':not bool(a.dxf.flags&1),'new':False,'x':a.dxf.insert.x,'y':a.dxf.insert.y,'height':a.dxf.height,'readonly':bool(a.has_embedded_mtext_entity),'attributeHandle':a.dxf.handle})
 h=next((a.dxf.height for a in e.attribs if a.dxf.height>0),2.5)
 p=e.ocs().to_wcs(e.dxf.insert);suggest={'x':round(p.x,3),'y':round(min((a.dxf.insert.y for a in e.attribs),default=p.y)-2*h,3),'height':round(h,3)}
 info={'drawing':id,'code':r['code'],'title':manager.catmap[id]['title'],'handle':handle,'block':e.dxf.name,'revision':st['revisions'].get(id,0),'attributes':attributes,'placement':suggest,'token':manager.token}
 if include_draft:
  from attribute_drafts import overlay_info
  info=overlay_info(manager,info)
 return info

def normalize(manager,data):
 info=block_info(manager,data.get('drawing'),str(data.get('handle','')))
 if data.get('revision')!=info['revision']:raise ValueError('此图纸属性已更新，请重新打开编辑器后保存')
 if data.get('draftRevision',0)!=info.get('draftRevision',0):raise ValueError('此块草稿已更新，请重新打开后编辑')
 rows=data.get('attributes')
 if not isinstance(rows,list) or len(rows)>256:raise ValueError('属性列表无效或超过 256 项')
 current={a['key']:a for a in info['attributes']};result=[];seen=set()
 for row in rows:
  if not isinstance(row,dict):raise ValueError('属性行格式无效')
  key=str(row.get('key','')).strip().upper()
  if key not in current and not re.fullmatch(r'[A-Z_\u4e00-\u9fff][A-Z0-9_\-\u4e00-\u9fff]{0,63}',key):raise ValueError('属性标识应为中英文字母、数字、下划线或短横线，且不能以数字开头')
  if key in seen:raise ValueError('属性标识重复：'+key)
  seen.add(key);label=str(row.get('label','')).strip();text=row.get('value','')
  if not label or len(label)>80:raise ValueError('请填写 1—80 字的属性中文名称')
  if not isinstance(text,str) or len(text)>2048 or any(ord(c)<32 for c in text):raise ValueError('属性值最多 2048 字，不能包含换行或控制字符')
  if not isinstance(row.get('visible'),bool):raise ValueError('请明确是否在图面显示此属性')
  existing=current.get(key)
  if existing and existing['readonly'] and (text!=existing['value'] or row['visible']!=existing['visible']):raise ValueError(key+' 为多行 CAD 属性，请在 CAD 中修改其内容')
  item={'key':key,'label':label,'value':text,'visible':row['visible'],'new':existing is None}
  if existing and not existing.get('new'):
   item.update(x=existing['x'],y=existing['y'],height=existing['height'])
  else:
   item['new']=True
   for k in ('x','y','height'):
    v=row.get(k,info['placement'][k])
    if not isinstance(v,(int,float)) or not math.isfinite(v) or abs(v)>1e10 or (k=='height' and not 0<v<=10000):raise ValueError('新增属性的位置或字高无效')
    item[k]=v
  result.append(item)
 if {k for k,a in current.items() if not a.get('new')}-seen:raise ValueError('已有属性不能省略；如需清空，请将其值留空')
 if all(a['key'] in current and all(a[k]==current[a['key']][k] for k in ('label','value','visible','x','y','height')) for a in result) and len(result)==len(current):raise ValueError('属性没有变化，无需保存')
 return info,result

def submit(manager,data):
 with manager.lock:
  info,rows=normalize(manager,data)
  if not manager.import_lock.acquire(blocking=False):raise ValueError('有 CAD 图纸正在处理，请完成后再保存属性')
  job={'id':'a'+uuid.uuid4().hex[:12],'kind':'attributes','drawing':info['drawing'],'handle':info['handle'],'code':info['code'],'title':info['title'],'revision':info['revision'],'attributes':rows,'createdAt':stamp(),'status':'queued','message':'准备更新块属性'}
  try:
   write_json(manager.base/'data/attribute-jobs'/f"{job['id']}.json",job)
   threading.Thread(target=run_job,args=(manager,job['id']),daemon=True).start();return {k:v for k,v in job.items() if k!='attributes'}
  except:manager.import_lock.release();raise

def run_job(manager,jid):
 base=manager.base;path=base/'data/attribute-jobs'/f'{jid}.json';folder=base/'data/attribute-revisions'/jid;folder.mkdir(parents=True,exist_ok=True)
 try:
  with (folder/'build.log').open('w') as log:
   process=subprocess.run([sys.executable,str(BASE/'scripts/edit_attributes.py'),str(base),jid],stdout=log,stderr=log,timeout=600)
  if process.returncode:raise RuntimeError('块属性写入或 CAD 校验失败，本次未修改正式图纸。请查看属性修改记录中的失败原因。')
  job=read_json(path);bundle=read_json(folder/'result.json');id=job['drawing'];live=base/'output'/id;backup=folder/'previous-output';stage=folder/'stage/output'/id
  with manager.lock:
   snapshots={name:read_json(base/'data'/name,{} if name=='attribute-edits.json' else []) for name in ('manifest.json','catalog.json','attribute-edits.json')}
   write_json(folder/'previous-indexes.json',snapshots);job.update(status='publishing',message='校验通过，正在同步图纸与索引');write_json(path,job)
   try:
    os.replace(live,backup);os.replace(stage,live)
    manifests=copy.deepcopy(snapshots['manifest.json']);r=next(r for r in manifests if r['id']==id);r['workingDxf']=str((folder/'working.dxf').relative_to(base));r['workingRoundtrip']=str((folder/'roundtrip/中文图纸.dxf').relative_to(base));write_json(base/'data/manifest.json',manifests)
    catalogs=snapshots['catalog.json'];catalogs=[bundle['catalog'] if r['id']==id else r for r in catalogs];write_json(base/'data/catalog.json',catalogs)
    st=state(base);before=st['blocks'].get(id,{}).get(job['handle']);st['revisions'][id]=job['revision']+1;st['blocks'].setdefault(id,{})[job['handle']]={'attributes':job['attributes'],'updatedAt':stamp(),'job':jid};st['history'].append({'job':jid,'drawing':id,'handle':job['handle'],'before':before,'after':st['blocks'][id][job['handle']],'time':stamp()});write_json(base/'data/attribute-edits.json',st)
    import references
    old=references.BASE;references.BASE=base
    try:references.rebuild()
    finally:references.BASE=old
    manager.reload()
   except:
    if backup.exists():
     if live.exists():os.replace(live,folder/'failed-output')
     os.replace(backup,live)
    for name,content in snapshots.items():write_json(base/'data'/name,content)
    manager.reload();raise
  job.update(status='complete',message='块属性已保存，中文 CAD、图纸和设备索引已同步',finishedAt=stamp());write_json(path,job)
 except Exception as ex:
  job=read_json(path);details=read_json(folder/'failure.json',{});job.update(status='failed',message=details.get('error',str(ex)),finishedAt=stamp());write_json(path,job)
 finally:manager.import_lock.release()

def patch_dxf(source,target,handle,rows):
 """Replace only changed ATTRIB records; append new compound records, keep others exact."""
 d=ezdxf.readfile(source);e=d.entitydb[handle];before={a.dxf.tag.upper():a for a in e.attribs};changed=set();added=[]
 if '中文标注' not in d.styles:raise ValueError('中文样式不存在，请先完成图纸汉化')
 from cad_runtime import drawing_font
 d.styles.get('中文标注').dxf.font=Path(drawing_font()).name
 original=records(source);original_handles={value(rec,5) for rec in original}
 old_seq=e.seqend.dxf.handle if e.seqend and e.seqend.dxf.handle in original_handles else None
 for row in rows:
  a=before.get(row['key'])
  if a is not None:
   flags=(a.dxf.flags&~1)|(0 if row['visible'] else 1)
   if a.dxf.text==row['value'] and flags==a.dxf.flags:continue
   a.dxf.text=row['value'];a.dxf.flags=flags;a.dxf.style='中文标注';changed.add(a.dxf.handle)
  else:
   a=e.add_attrib(row['key'],row['value'],insert=(row['x'],row['y'],0),dxfattribs={'layer':e.dxf.layer,'height':row['height'],'flags':0 if row['visible'] else 1,'style':'中文标注'});added.append(a.dxf.handle)
 generated=target.with_name('generated.dxf');d.saveas(generated)
 made=records(generated);lookup={value(r,5):r for r in made if value(r,5)};result=[];inserted=False
 for rec in original:
  h=value(rec,5);typ=value(rec,0)
  if typ=='STYLE' and value(rec,2)=='中文标注':
   rec=[(c,Path(drawing_font()).name,f'  3\n{Path(drawing_font()).name}\n') if c==3 else (c,v,raw) for c,v,raw in rec]
  if h in changed:
   # Preserve position, width and all extension payloads; only text, visibility and style change.
   replacement={c:(c,v,raw) for c,v,raw in lookup[h] if c in (1,7,70)};emitted=set();patched=[]
   for c,v,raw in rec:
    if c in replacement:patched.append(replacement[c]);emitted.add(c)
    else:patched.append((c,v,raw))
   missing=[replacement[c] for c in replacement.keys()-emitted];idx=next((i for i,(c,_,_) in enumerate(patched) if c>=1000),len(patched));patched[idx:idx]=missing;rec=patched
  if added and h==handle and typ=='INSERT':
   # Group 66 belongs to AcDbBlockReference, not the superclass.
   if any(c==66 for c,_,_ in rec):rec=[(66,'1',' 66\n1\n') if c==66 else (c,v,raw) for c,v,raw in rec]
   else:
    idx=next((i+1 for i,(c,v,_) in enumerate(rec) if c==100 and v=='AcDbBlockReference'),len(rec));rec=rec[:idx]+[(66,'1',' 66\n1\n')]+rec[idx:]
  if added and old_seq and h==old_seq:
   for ah in added:result.extend(raw for _,_,raw in lookup[ah])
   inserted=True
  result.extend(raw for _,_,raw in rec)
  if added and not old_seq and h==handle:
   for ah in added+[e.seqend.dxf.handle]:result.extend(raw for _,_,raw in lookup[ah])
   inserted=True
 if added and not inserted:raise RuntimeError('无法定位属性序列，未写入文件')
 # Preserve the raw header except the handle allocator seed for newly appended entities.
 text=''.join(result)
 seed=format(max(int(h,16) for h in d.entitydb if h)+1,'X')
 text=re.sub(r'(\$HANDSEED\s*\n\s*5\s*\n)[0-9A-Fa-f]+',lambda m:m[1]+seed,text,count=1)
 target.write_text(text,encoding='utf-8');generated.unlink();return {'changed':sorted(changed),'added':added,'insert':handle,'newSequence':None if old_seq else (e.seqend.dxf.handle if e.seqend else None)}

def worker(base,jid,prepare_only=False):
 folder=base/'data/attribute-revisions'/jid;folder.mkdir(parents=True,exist_ok=True);jobpath=base/'data/attribute-jobs'/f'{jid}.json';job=read_json(jobpath);id=job['drawing'];r=next(r for r in read_json(base/'data/manifest.json') if r['id']==id)
 def progress(msg):
  if read_json(jobpath)['status']=='failed':raise RuntimeError('属性处理已中断')
  job.update(status='processing',message=msg);write_json(jobpath,job)
 progress('正在写入当前块的 CAD 属性')
 source=working(base,r);blocks=job.get('blocks') or [{'handle':job['handle'],'attributes':job['attributes']}]
 changed={'changed':[],'added':[],'blocks':[]};current_path=source
 for n,block in enumerate(blocks):
  target=folder/f'patch-{n}.dxf';part=patch_dxf(current_path,target,block['handle'],block['attributes']);current_path=target
  changed['changed'].extend(part['changed']);changed['added'].extend(part['added']);changed['blocks'].append(part)
 shutil.copy2(current_path,folder/'working.dxf');write_json(folder/'changed-records.json',changed)
 edits={b['handle']:b['attributes'] for b in blocks}
 original_data=read_json(base/'output'/id/'drawing.json');stage=folder/'stage';out=stage/'output'/id;out.mkdir(parents=True);stage_source=stage/'working.dxf';shutil.copy2(folder/'working.dxf',stage_source)
 progress('正在更新图纸、设备位号和检索字段')
 import build
 build.BASE=stage;build.ROOT=base.parent;build.translate=lambda x:x
 rr=dict(r,dxf='working.dxf',fixedExtents=original_data['extents']);rr.pop('workingDxf',None)
 c=build.build(rr)
 if c['status']!='ready':raise RuntimeError(c.get('error','无法生成图纸'))
 # The display build is not used as the CAD writer. Keep exact patched CAD records.
 shutil.copy2(folder/'working.dxf',out/'中文图纸.dxf');shutil.copy2(base/'output'/id/'original.svg',out/'original.svg')
 d=read_json(out/'drawing.json');d['title']=original_data['title'];d['extents']=original_data['extents'];d['attributeRevision']=job['revision']+1
 current=ezdxf.readfile(folder/'working.dxf');orig=ezdxf.readfile(base/r['dxf']);saved=state(base)['blocks'].get(id,{})
 oldlabels={i['handle']:{a['key']:a['label'] for a in i['attributes']} for i in original_data['items']}
 for it in d['items']:
  e=current.entitydb.get(it['handle'])
  if e is None or e.dxftype()!='INSERT':continue
  labels={a['key']:a['label'] for a in saved.get(it['handle'],{}).get('attributes',[])}
  if it['handle'] in edits:labels.update({a['key']:a['label'] for a in edits[it['handle']]})
  oe=orig.entitydb.get(it['handle']);initial={a.dxf.tag.upper():a.dxf.text for a in oe.attribs} if oe is not None and oe.dxftype()=='INSERT' else {}
  it['attributes']=[{'key':a.dxf.tag.upper(),'label':labels.get(a.dxf.tag.upper()) or oldlabels.get(it['handle'],{}).get(a.dxf.tag.upper()) or ATTR.get(a.dxf.tag.upper()) or a.dxf.tag,'original':a.dxf.text,'sourceOriginal':initial.get(a.dxf.tag.upper()),'value':a.dxf.text,'customLabel':a.dxf.tag.upper() in labels,'visible':not bool(a.dxf.flags&1)} for a in e.attribs]
  if it['handle'] in edits:it['attributeEdited']=True
  # Invisible DWG-reference attributes still participate in links and search.
  existing_text={(t['handle'],t['text']) for t in d['texts']}
  from references import codes
  for a in e.attribs:
   if a.dxf.flags&1 and codes(a.dxf.text) and (it['handle'],a.dxf.text) not in existing_text:d['texts'].append({'handle':it['handle'],'text':a.dxf.text,'zh':a.dxf.text,'xy':[a.dxf.insert.x,a.dxf.insert.y]})
 ledger=[t for t in original_data['translations'] if t['handle'] not in set(changed['changed'])]
 for handle,rows in edits.items():
  for row in rows:
   a=current.entitydb[handle].get_attrib(row['key']);original=orig.entitydb.get(a.dxf.handle)
   if a.dxf.handle in changed['changed']+changed['added']:ledger.append({'handle':a.dxf.handle,'entity':'ATTRIB','original':original.dxf.text if original is not None else '', 'chinese':row['value'],'review':False,'userEdited':True})
 d['translations']=ledger;c['title']=d['title'];c['translated']=len(ledger);c['reviewCount']=sum(t['review'] for t in ledger)
 from pypinyin import lazy_pinyin
 c['search']=' '.join([r['filename'],d['title'],''.join(lazy_pinyin(d['title']))]+[t['zh'] for t in d['texts']]+[a['value']+' '+a['label'] for i in d['items'] for a in i['attributes']])
 for eq in d['equipment']:
  it=next(i for i in d['items'] if i['handle']==eq['handle']);eq['search']=' '.join(a['value'] for a in it['attributes'])
 c['equipment']=d['equipment'];write_json(out/'drawing.json',d)
 write_json(folder/'result.json',{'catalog':c})
 if prepare_only:return
 progress('正在生成 DWG 并回读校验属性')
 from cad_runtime import convert
 rt=folder/'roundtrip'
 convert(out,out,'DWG','*.dxf');convert(out,rt,'DXF','*.dwg')
 verify_prepared(base,jid,rt/'中文图纸.dxf');progress('属性与图元校验通过，准备发布')

def verify_prepared(base,jid,roundtrip):
 folder=base/'data/attribute-revisions'/jid;job=read_json(base/'data/attribute-jobs'/f'{jid}.json');r=next(r for r in read_json(base/'data/manifest.json') if r['id']==job['drawing'])
 changed=read_json(folder/'changed-records.json');current=ezdxf.readfile(folder/'working.dxf');reread=ezdxf.readfile(roundtrip);before=ezdxf.readfile(working(base,r))
 blocks=job.get('blocks') or [{'handle':job['handle'],'attributes':job['attributes']}]
 sys.path.insert(0,str(BASE/'tests'));from verify_cad import entities
 assert entities(before)==entities(current)==entities(reread),'几何图元发生了非预期改变'
 for block in blocks:
  for row in block['attributes']:
   a=reread.entitydb[block['handle']].get_attrib(row['key']);assert a is not None and a.dxf.text==row['value'],'DWG 属性回读值不一致：'+row['key'];assert bool(a.dxf.flags&1)==(not row['visible']),'属性可见性回读不一致'
 for e in before.entitydb.values():
  if e.dxftype()=='ATTRIB' and e.dxf.handle not in changed['changed']:
   a=reread.entitydb.get(e.dxf.handle);assert a is not None and a.dxf.text==e.dxf.text,'其他块属性被修改'
 from vault import original,sha
 if sha(original(base,r))!=r['sha256']:raise ValueError('原始 DWG 已变化')
 write_json(folder/'verification.json',{'passed':True,'geometryUnchanged':True,'otherAttributesUnchanged':True,'originalDWGHashUnchanged':True,'attributeCount':sum(len(b['attributes']) for b in blocks),'changed':changed})
