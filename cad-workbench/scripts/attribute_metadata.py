"""Keep user attribute names, hidden data and lookup fields through index rebuilds."""
import json
from pathlib import Path
from references import codes

def decorate(data,base,record,doc,previous=None):
 path=Path(base)/'data/attribute-edits.json'
 saved=json.loads(path.read_text()).get('blocks',{}).get(record['id'],{}) if path.exists() else {}
 old={i['handle']:{a['key']:a for a in i['attributes']} for i in (previous or {}).get('items',[])}
 present={(t['handle'],t['text']) for t in data['texts']}
 for item in data['items']:
  labels={a['key']:a['label'] for a in saved.get(item['handle'],{}).get('attributes',[])}
  e=doc.entitydb.get(item['handle'])
  if e is None or e.dxftype()!='INSERT':continue
  attrs={a.dxf.tag.upper():a for a in e.attribs}
  for a in item['attributes']:
   prior=old.get(item['handle'],{}).get(a['key'],{});cad=attrs.get(a['key'])
   if a['key'] in labels:a['label']=labels[a['key']];a['customLabel']=True
   if 'sourceOriginal' in prior:a['sourceOriginal']=prior['sourceOriginal']
   if cad is not None:a['visible']=not bool(cad.dxf.flags&1)
   if record.get('workingDxf') and cad is not None:
    a['value']=cad.dxf.text;a['original']=cad.dxf.text
    if cad.dxf.flags&1 and codes(cad.dxf.text) and (item['handle'],cad.dxf.text) not in present:
     data['texts'].append({'handle':item['handle'],'text':cad.dxf.text,'zh':cad.dxf.text,'xy':[cad.dxf.insert.x,cad.dxf.insert.y]});present.add((item['handle'],cad.dxf.text))
  if record.get('workingDxf'):
   at={a['key']:a['value'] for a in item['attributes']}
   item['name']=at.get('EQ_DES') or at.get('VA_DESC') or at.get('LN_DESC') or at.get('IN_SERV') or item['name']
  if labels:item['attributeEdited']=True
 for eq in data['equipment']:
  item=next(i for i in data['items'] if i['handle']==eq['handle']);eq['search']=' '.join(a['value'] for a in item['attributes']);eq['name']=item['name']
 if record.get('workingDxf') and previous:
  ledgers={t['handle']:t for t in previous.get('translations',[])}
  for t in data.get('translations',[]):
   if t['handle'] in ledgers:t=dict(t,original=ledgers[t['handle']]['original'])
   ledgers[t['handle']]=t
  data['translations']=list(ledgers.values())

def search_extra(data):return ' '.join(a['label']+' '+a['value'] for i in data['items'] for a in i['attributes'])
