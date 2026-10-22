"""Resolve CAD references from filenames, title-block numbers, and source notes."""
from pathlib import Path
import collections,json,re,hashlib
BASE=Path(__file__).resolve().parents[1]
PLATFORM=r'(?:CEPD|CEP[A-Z]?|PRP|WHP[A-Z]|WP[A-Z])'
NUMBER=r'(?:MD)?\d+[A-Z]?(?:\(\d+\))?(?:/(?:\d+[A-Z]?|[A-Z]))?'
CODE_RE=re.compile(r'(?<![A-Z0-9])(?:(?:MD(?:\([A-Z]+\))?|DD)-)?(?:DWG-|351-4-)?(?:PB-'+PLATFORM+r'-(?:(?:PR|IN|SA|GE)-)?'+NUMBER+'|'+PLATFORM+r'-(?:PR|IN|SA|GE)-'+NUMBER+r')(?![A-Z0-9])',re.I)
MAP={'CEP':'CEPD','WPA':'WHPA','WPB':'WHPB','WPE':'WHPE','WPF':'WHPF'}
def prepare(s):
 return re.sub(r'\s*-\s*','-',s.upper().replace('（','(').replace('）',')').replace('–','-').replace('—','-'))
def codes(s):return [m[0] for m in CODE_RE.finditer(prepare(s))]
def keys(code):
 s=prepare(code);s=re.sub(r'^(?:(?:MD(?:\([A-Z]+\))?|DD)-)?(?:DWG-|351-4-)?','',s)
 s=s.removeprefix('PB-');m=re.fullmatch('('+PLATFORM+r')-(?:(PR|IN|SA|GE)-)?(?:MD)?(\d+[A-Z]?)(?:\((\d+)\))?(?:/(\d+[A-Z]?|[A-Z]))?',s)
 if not m:return []
 platform,discipline,number,sheet,other=m.groups();stem=MAP.get(platform,platform)+'-'+(discipline or 'PR')+'-'
 result=[stem+number+('('+str(int(sheet))+')' if sheet else '')]
 if other:result.append(stem+(other if other[0].isdigit() else re.sub('[A-Z]$','',number)+other))
 return result

def zero_key(key):return re.sub(r'-(\d+)([A-Z]?)(\(\d+\))?$',lambda m:'-'+str(int(m[1]))+m[2]+(m[3] or ''),key)
def source_platform(r):
 parent=Path(r['source']).parent.name
 return next((p for p in ['CEPD','PRP','WHPA','WHPB','WHPE','WHPF'] if p in parent),r['platform'])
def rebuild():
 records=json.loads((BASE/'data/manifest.json').read_text(encoding='utf-8'));catalog=json.loads((BASE/'data/catalog.json').read_text(encoding='utf-8'));cats={r['id']:r for r in catalog};docs={};aliases=collections.defaultdict(set);evidence=[];canonical={};file_keys=collections.defaultdict(set)
 for r in records:
  r['platform']=source_platform(r);cats[r['id']]['platform']=r['platform'];d=json.loads((BASE/'output'/r['id']/'drawing.json').read_text(encoding='utf-8'));d['platform']=r['platform'];docs[r['id']]=d;canonical[r['id']]=keys(r['code'])[0]
  aliases[canonical[r['id']]].add(r['id']);file_keys[canonical[r['id']]].add(r['id'])
 def add(key,id,method,t):
  if key.split('-')[0]!=docs[id]['platform']:return
  aliases[key].add(id);evidence.append({'drawing':id,'alias':key,'method':method,'handle':t['handle'],'evidence':t['text']})
 for id,d in docs.items():
  x0,y0,x1,y1=d['extents'];w=x1-x0;h=y1-y0
  for t in d['texts']:
   found=codes(t['text']);tx,ty=t['xy']
   # A bare drawing number beside the current title-block number is an old drawing number.
   bare=bool(found) and prepare(t['text']).strip(' .')==found[0] and len(found)==1
   titleblock=bare and tx>x0+w*.72 and y0-h*.01<ty<y0+h*.13
   based=bool(re.search(r'BASED\s+ON|基于|依据',t['text'],re.I))
   if titleblock or based:
    for code in found:
     for key in keys(code):add(key,id,'标题栏图号' if titleblock else '原图编制依据',t)
   if based and not found:
    # Notes may wrap into the next CAD TEXT entity; only close continuation lines are read.
    for n in d['texts']:
     nx,ny=n['xy']
     if 0<ty-ny<13 and abs(nx-tx)<35 and not re.match(r'^\d+[.)]',n['text']):
      for code in codes(n['text']):
       for key in keys(code):add(key,id,'原图编制依据续行',n)
 # Numeric padding is accepted only when it identifies one unambiguous existing key.
 by_zero=collections.defaultdict(set)
 for key in aliases:by_zero[zero_key(key)].add(key)
 def lookup(key):
  if key in file_keys:return set(file_keys[key]),'源文件完整图号匹配'
  if key in aliases:return set(aliases[key]),'标题栏旧图号／编制依据'
  found=by_zero.get(zero_key(key),set())
  if len(found)==1:return set(aliases[next(iter(found))]),'图号前导零格式统一'
  # A series reference without a sheet suffix opens the first supplied sheet, with siblings retained.
  sheets={id for k,values in aliases.items() if re.fullmatch(re.escape(key)+r'(?:\(\d+\)|[A-Z])',k) for id in file_keys.get(k,values)}
  if sheets:return sheets,'分图系列（默认首页）'
  return set(),'目录未提供对应 DWG'
 def rank(id):
  r=cats[id];src=r['source'];revision=re.search(r'REV\s*(\d+)',src,re.I);sheet=re.search(r'\((\d+)\)$',canonical[id]);stage=0 if 'MD(DD)-' in src else 1 if 'MD-DWG-' in src else 2
  return (int(sheet[1]) if sheet else 0,stage,-int(revision[1]) if revision else 0,id)
 unresolved=[];counts=collections.Counter()
 for id,d in docs.items():
  refs=[];seen=set()
  for t in d['texts']:
   for code in codes(t['text']):
    signature=(t['handle'],code)
    if signature in seen:continue
    seen.add(signature);kk=keys(code);candidates=set();methods=[]
    for k in kk:
     got,method=lookup(k);candidates|=got;methods.append(method)
    is_self=id in candidates
    targets=sorted(candidates-{id},key=rank)
    # The current drawing's title number / old number is not a cross-drawing link.
    ref={'handle':t['handle'],'code':code,'key':kk[0],'context':t['zh'],'xy':t['xy'],'targets':targets,'preferredTarget':targets[0] if targets else None,'selfReference':is_self,'resolution':'本图图号' if is_self else '；'.join(dict.fromkeys(methods)),'alternatives':targets[1:]}
    refs.append(ref)
    if not is_self:
     if targets:counts['resolved']+=1
     else:counts['missing']+=1;unresolved.append(dict(ref,drawing=id))
  d['references']=refs;cats[id]['references']=refs
  (BASE/'output'/id/'drawing.json').write_text(json.dumps(d,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
 (BASE/'data/manifest.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
 (BASE/'data/catalog.json').write_text(json.dumps(catalog,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
 (BASE/'data/link-evidence.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')
 report={'sourceFiles':len(records),'unindexedFiles':[str(p.relative_to(BASE.parent)) for p in BASE.parent.rglob('*.dwg') if not p.is_relative_to(BASE) and str(p.relative_to(BASE.parent)) not in {r['source'] for r in records}],'resolvedOccurrences':counts['resolved'],'missingOccurrences':counts['missing'],'missingUnique':len({r['key'] for r in unresolved}),'unresolved':unresolved,'aliases':{k:sorted(v,key=rank) for k,v in sorted(aliases.items())},'evidenceCount':len(evidence)}
 (BASE/'data/reference-audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print({k:v for k,v in report.items() if k not in ('aliases','unresolved')})
if __name__=='__main__':rebuild()
