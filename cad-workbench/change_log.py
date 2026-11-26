"""Present the same durable records that committed each drawing change."""
from management import read_json

FIELDS = ('label','value','visible','x','y','height')
def attributes(rows):
 return {a['key']:{k:a[k] for k in FIELDS if k in a} for a in rows}

def diff(before,after):
 return [{'field':k,'before':before.get(k),'after':after.get(k)} for k in dict.fromkeys([*before,*after]) if before.get(k)!=after.get(k)]

def link_value(ref):
 if ref is None:return None
 return {k:ref.get(k) for k in ('targets','preferredTarget','note')}

def entries(manager,query='',offset=0,limit=50):
 base=manager.base;events=[]
 def add(kind,r,changes=(),description=''):
  id=r.get('drawing');cat=manager.catmap.get(id,{})
  events.append({'type':kind,'drawing':id,'code':cat.get('code') or r.get('code',''),'title':cat.get('title') or r.get('title',''),'handle':r.get('handle',''),'time':r.get('time') or r.get('finishedAt') or r.get('createdAt',''),'actor':r.get('actor','管理员（历史记录）'),'changes':changes,'description':description})
 for file in (base/'data').glob('attribute-drafts*.json'):
  for r in read_json(file,{}).get('history',[]):
   add(r['type'],r,r['changes'])
 for r in read_json(base/'data/attribute-edits.json',{}).get('history',[]):
  changes=r.get('changes');note=''
  if changes is None:
   before=r.get('before');after=(r.get('after') or {}).get('attributes',[])
   if before is not None:changes=diff(attributes(before['attributes']),attributes(after))
   else:
    # Pre-upgrade jobs retained an actual copy of the previous drawing.
    doc=read_json(base/'data/attribute-revisions'/r['job']/'previous-output/drawing.json',{})
    block=next((i for i in doc.get('items',[]) if i['handle']==r['handle']),None)
    if block is None:changes=[];note='历史记录未保存可核对的旧值'
    else:
     slim=lambda rows:{a['key']:{k:a[k] for k in ('label','value') if k in a} for a in rows}
     changes=diff(slim(block.get('attributes',[])),slim(after))
  add('发布块属性',r,changes,note)
 for r in manager.overrides.get('history',[]):
  drawing,handle,code=r['key'].split('|',2)
  add('修改关联' if r.get('after') else '恢复自动关联',dict(r,drawing=drawing,handle=handle),[{'field':code,'before':r.get('from',link_value(r.get('before'))),'after':r.get('to',link_value(r.get('after')))}])
 for f in (base/'data/upload-jobs').glob('*.json'):
  r=read_json(f);add('导入图纸',r,description=r.get('filename','')+' · '+r.get('message',''))
 for f in (base/'data/attribute-batches').glob('*/job.json'):
  r=read_json(f)
  if r['status']=='failed':add('发布失败',r,description=r['message'])
 events.reverse()
 events.sort(key=lambda e:e['time'],reverse=True)
 if query:
  q=query.casefold();events=[e for e in events if q in ' '.join(str(e.get(k,'')) for k in ('code','title','handle','type','description','changes','actor')).casefold()]
 return {'total':len(events),'records':events[offset:] if limit is None else events[offset:offset+limit]}
