"""Verify real CAD round trips, source integrity, and fixed engineering identifiers."""
from pathlib import Path
import sys,json,hashlib,collections,math,concurrent.futures
import ezdxf
BASE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE/'scripts'))
from refresh import PROTECTED,protected_value
FIELDS=('start','end','center','radius','insert','align_point','extrusion','rotation','xscale','yscale','zscale','elevation','start_angle','end_angle','location','major_axis','ratio','start_param','end_param','closed','flags','degree')
def comparable(v):
 if isinstance(v,(str,int,bool)) or v is None:return v
 try:return tuple(comparable(x) for x in v)
 except TypeError:return round(float(v),6)
def entities(doc):
 out={}
 for block in doc.blocks:
  # Named blocks and model space; paper space contains ODA-managed viewport bookkeeping.
  if block.name.upper().startswith('*PAPER_SPACE'):continue
  for e in block:
   vals={k:comparable(e.dxf.get(k,e.dxf.dxf_default_value(k))) for k in FIELDS if e.dxf.is_supported(k)}
   # REGION flags record modeler history state, not geometric coordinates.
   if e.dxftype()=='REGION':vals.pop('flags',None)
   if e.dxftype()=='LWPOLYLINE':vals['vertices']=comparable(list(e.get_points()))
   if e.dxftype()=='INSERT':vals['block']=doc.blocks[e.dxf.name].block_record_handle
   out[e.dxf.handle]=(e.dxftype(),vals)
 return out

def work(r):
 errors=[];source=BASE.parent/r['source'];a=ezdxf.readfile(BASE/r.get('workingDxf',r['dxf']));b=ezdxf.readfile(BASE/'output'/r['id']/'中文图纸.dxf');c=ezdxf.readfile(BASE/r.get('workingRoundtrip',f"data/roundtrip-check/{r['id']}/中文图纸.dxf"))
 if hashlib.sha256(source.read_bytes()).hexdigest()!=r['sha256']:errors.append('原始DWG哈希改变')
 ma,mb,mc=[entities(d) for d in (a,b,c)]
 for label,other in [('中文DXF',mb),('中文DWG回读',mc)]:
  if collections.Counter(x[0] for x in ma.values())!=collections.Counter(x[0] for x in other.values()):errors.append(label+'图元数量或类型改变')
  diff=[h for h,x in ma.items() if other.get(h)!=x]
  if diff:errors.append(label+'几何差异:'+','.join(diff[:12]))
 protected=0
 for e in a.entitydb.values():
  if e.dxftype() in ('ATTRIB','ATTDEF') and protected_value(e.dxf.tag,e.dxf.text):
   protected+=1
   for label,doc in [('DXF',b),('DWG',c)]:
    v=doc.entitydb.get(e.dxf.handle)
    if v is None or v.dxf.text!=e.dxf.text:errors.append(label+'位号属性改变:'+e.dxf.handle)
 ledger=json.loads((BASE/'output'/r['id']/'drawing.json').read_text())['translations']
 zh=0
 for t in ledger:
  e=c.entitydb.get(t['handle'])
  if e is not None:
   text=e.text if e.dxftype()=='MTEXT' else e.dxf.text
   if any('\u4e00'<=v<='\u9fff' for v in t['chinese']):
    if not any('\u4e00'<=v<='\u9fff' for v in text):errors.append('中文未写入DWG:'+t['handle'])
    else:zh+=1
 return dict(id=r['id'],code=r['code'],geometryCount=len(ma),protectedAttributes=protected,chineseEntities=zh,errors=errors)
if __name__=='__main__':
 records=json.loads((BASE/'data/manifest.json').read_text());results=[]
 with concurrent.futures.ProcessPoolExecutor(max_workers=3) as pool:
  for n,r in enumerate(pool.map(work,records),1):
   results.append(r)
   if r['errors']:print(r['id'],r['errors'][:5],flush=True)
   elif n%25==0:print(n,'verified',flush=True)
 report={'drawings':len(results),'passed':sum(not r['errors'] for r in results),'protectedAttributes':sum(r['protectedAttributes'] for r in results),'chineseEntities':sum(r['chineseEntities'] for r in results),'results':results}
 (BASE/'data/verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print({k:v for k,v in report.items() if k!='results'},flush=True)
 sys.exit(0 if report['passed']==report['drawings'] else 1)
