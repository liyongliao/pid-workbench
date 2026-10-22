import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from cad_runtime import drawing_font
"""Reapply reviewed translations from original CAD, retaining the original vector asset."""
from build import *
from translate import translate,clean,residual
import xml.etree.ElementTree as ET
PROTECTED={'IN_TAG','IN_NUM','FNC','LOOP','PSV_TAG','PSV_NUM','EQ_TAG','VA_TAG','VTAG','LN_TAG','TAG','NOZ_TAG','DWG_NO','DWGNO'}
def protected_value(key,value):
 if key.upper() not in PROTECTED:return False
 return translate(value)==value or bool(re.fullmatch(r'[A-Z0-9.()/_-]+',value) and re.search(r'\d',value))
def work(r):
 folder=BASE/'output'/r['id'];p=folder/'drawing.json'
 if not p.exists():return None
 d,audit=read_source(BASE/r.get('workingDxf',r['dxf']));data=json.loads(p.read_text());ledger=[]
 overrides=json.loads((BASE/'data/text-overrides.json').read_text()).get(r['id'],{}) if (BASE/'data/text-overrides.json').exists() else {}
 origfonts={s.dxf.name:(s.dxf.font,s.dxf.get('bigfont','')) for s in d.styles}
 if '中文标注' not in d.styles:d.styles.new('中文标注')
 for s in d.styles:s.dxf.font=drawing_font();s.dxf.bigfont=''
 for e in list(d.entitydb.values()):
  if e.dxftype() not in ['TEXT','MTEXT','ATTRIB','ATTDEF']:continue
  original=get_text(e);override=overrides.get(e.dxf.handle,{});zh=override.get('chinese',translate(original))
  if r.get('workingDxf') and e.dxftype()=='ATTRIB':zh=original
  if zh==original:continue
  if e.dxftype() in ['ATTRIB','ATTDEF'] and protected_value(e.dxf.tag,original):continue
  ledger.append({'handle':e.dxf.handle,'entity':e.dxftype(),'original':original,'chinese':zh,'review':override.get('review',bool(re.search(r'(?<!等)待核|含义待',zh)))})
  if e.dxftype()=='MTEXT':
   # Preserve explicit paragraph boundaries when present, allowing CAD's native wrapping.
   raw=e.text
   if '\\P' in raw:
    pieces=raw.split('\\P');part_zh=[]
    for part in pieces:
     from ezdxf.tools.text import plain_mtext
     part_zh.append(translate(plain_mtext(part)))
    if all(not residual(part) for part in part_zh):zh='\\P'.join(part_zh)
   e.text=zh
  else:
   e.dxf.text=zh;oldw=sum(1 if ord(c)>127 else .56 for c in original);neww=sum(1 if ord(c)>127 else .56 for c in zh)
   e.dxf.width=min(1.0,e.dxf.get('width',1.0)*oldw/max(neww,1))
  e.dxf.style='中文标注'
 render(d,folder,'chinese',data['extents'])
 for s in d.styles:
  if s.dxf.name in origfonts:s.dxf.font,s.dxf.bigfont=origfonts[s.dxf.name]
 d.styles.get('中文标注').dxf.font=Path(drawing_font()).name;d.saveas(folder/'中文图纸.dxf')
 previous=json.loads(p.read_text());data['translations']=ledger;data['title']=title(r);data['title']=re.sub(r'列\s*[\x27\"]?([A-C])[\x27\"]?',r'\1列',data['title']).replace('[原版]','').strip()
 for t in data['texts']:t['zh']=overrides.get(t['handle'],{}).get('chinese',translate(t['text']))
 for it in data['items']:
  for a in it['attributes']:a['value']=a['original'] if protected_value(a['key'],a['original']) else translate(a['original'])
  at={a['key']:a['value'] for a in it['attributes']}
  it['name']=at.get('EQ_DES') or at.get('VA_DESC') or at.get('LN_DESC') or at.get('IN_SERV') or (tagname(it['tag']) if it['tag'] else ('CAD属性块' if it['entity']=='INSERT' else 'CAD图元'))
 for e in data['equipment']:
  it=next(x for x in data['items'] if x['handle']==e['handle']);e['name']=it['name']
 for ref in data['references']:ref['context']=next((t['zh'] for t in data['texts'] if t['handle']==ref['handle']),ref['context'])
 from attribute_metadata import decorate,search_extra
 decorate(data,BASE,r,d,previous);ledger=data['translations']
 p.write_text(json.dumps(data,ensure_ascii=False,separators=(',',':')))
 return {'id':r['id'],'code':r['code'],'title':data['title'],'platform':r['platform'],'source':r['source'],'equipment':data['equipment'],'references':data['references'],'textCount':len(data['texts']),'translated':len(ledger),'reviewCount':sum(x['review'] for x in ledger),'entityCount':len(data['items']),'search':' '.join([r['filename'],data['title'],''.join(lazy_pinyin(data['title']))]+[x['zh'] for x in data['texts']]+[e['tag'] for e in data['equipment']]+[search_extra(data)]),'status':'ready'}
def link_catalog(results,records):
 (BASE/'data/catalog.json').write_text(json.dumps(sorted(results,key=lambda r:r['id']),ensure_ascii=False,separators=(',',':')))
 from references import rebuild
 rebuild()
if __name__=='__main__':
 records=json.loads((BASE/'data/manifest.json').read_text());selected=set(sys.argv[1:]);rs=[r for r in records if not selected or r['id'] in selected];results=[]
 with concurrent.futures.ProcessPoolExecutor(max_workers=3) as pool:
  for n,r in enumerate(pool.map(work,rs)):
   if r:results.append(r)
   print(n+1,len(rs),r['id'] if r else 'error',flush=True)
 if selected:
  previous={r['id']:r for r in json.loads((BASE/'data/catalog.json').read_text())};previous.update({r['id']:r for r in results});results=list(previous.values())
 link_catalog(results,records)
