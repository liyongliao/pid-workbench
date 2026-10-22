"""Overlay translated text fields on the original DXF records.
All non-text entity records and extension payloads remain byte-for-byte intact.
This avoids writer normalization and preserves unsupported CAD objects.
"""
from pathlib import Path
import json,collections
BASE=Path(__file__).resolve().parents[1]
TEXT_TYPES={'TEXT','MTEXT','ATTRIB','ATTDEF'}
def records(path):
 lines=path.read_text(encoding='utf-8-sig').splitlines(keepends=True)
 result=[];current=[]
 for i in range(0,len(lines),2):
  pair=(int(lines[i].strip()),lines[i+1].rstrip('\r\n'),lines[i]+lines[i+1])
  if pair[0]==0 and current:result.append(current);current=[]
  current.append(pair)
 if current:result.append(current)
 return result
def value(record,code):return next((v for c,v,_ in record if c==code),'')
def apply(source,localized):
 original=records(source);translated=records(localized)
 changed={value(r,5):r for r in translated if value(r,0) in TEXT_TYPES}
 style=next(r for r in translated if value(r,0)=='STYLE' and value(r,2)=='中文标注')
 result=[];inside_style=False;count=0
 needs_style=not any(value(r,0)=='STYLE' and value(r,2)=='中文标注' for r in original)
 for record in original:
  typ=value(record,0)
  if needs_style and typ=='TABLE' and value(record,2)=='STYLE':
   inside_style=True
   record=[(c,str(int(v)+1),f'{c:3d}\n{int(v)+1}\n') if c==70 else (c,v,raw) for c,v,raw in record]
  if typ=='ENDTAB' and inside_style:
   result.extend(raw for _,_,raw in style);inside_style=False
  if typ in TEXT_TYPES and value(record,5) in changed:
   trans=changed[value(record,5)];codes={1,3,7} | ({41} if typ!='MTEXT' else set())
   replacements=collections.defaultdict(list)
   for c,v,raw in trans:
    if c in codes:replacements[c].append((c,v,raw))
   emitted=set();patched=[]
   for c,v,raw in record:
    if c in codes:
     if c in (1,3):
      if 1 not in emitted:
       patched.extend(replacements[3]+replacements[1]);emitted.update({1,3})
     elif c not in emitted:patched.extend(replacements[c]);emitted.add(c)
    else:patched.append((c,v,raw))
   # Add missing width or style codes inside the entity before its XDATA.
   pending=[pair for c in codes-emitted for pair in replacements[c]]
   index=next((i for i,(c,v,raw) in enumerate(patched) if c>=1000),len(patched))
   patched[index:index]=pending;record=patched;count+=1
  result.extend(raw for _,_,raw in record)
 localized.write_text(''.join(result),encoding='utf-8')
 return count
if __name__=='__main__':
 manifest=json.loads((BASE/'data/manifest.json').read_text());total=0
 for r in manifest:total+=apply(BASE/r.get('workingDxf',r['dxf']),BASE/'output'/r['id']/'中文图纸.dxf')
 print('Preserved original geometry in',len(manifest),'drawings;',total,'text records overlaid')
