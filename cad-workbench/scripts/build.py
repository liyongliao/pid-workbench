import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from cad_runtime import drawing_font
from centerlines import extract as extract_centerlines
"""DWG-derived CAD build. Never reads a source PDF and never invokes OCR."""
from pathlib import Path
import json,re,math,time,hashlib,logging,sys,copy,concurrent.futures,collections,traceback
import ezdxf
from ezdxf import bbox,disassemble
from ezdxf.addons.drawing import Frontend,RenderContext,svg,layout,config
from ezdxf.math import BoundingBox2d
from pypinyin import lazy_pinyin
from translate import clean,translate,residual
BASE=Path(__file__).resolve().parents[1]; ROOT=BASE.parent
logging.getLogger('ezdxf').setLevel(logging.ERROR)
INSTRUMENTS={'LT':'液位变送器','LI':'液位指示仪','LIC':'液位指示控制器','LC':'液位控制器','LG':'液位计','LV':'液位控制阀','LY':'液位转换器','LSHH':'高高液位开关','LSLL':'低低液位开关','LAH':'高液位报警','LAL':'低液位报警','PT':'压力变送器','PI':'压力指示仪','PIC':'压力指示控制器','PCV':'压力控制阀','PV':'压力控制阀','PIT':'压力指示变送器','PDI':'差压指示仪','PDIT':'差压指示变送器','PDT':'差压变送器','PDIC':'差压指示控制器','PSV':'压力安全阀','PSHH':'高高压力开关','PSLL':'低低压力开关','TT':'温度变送器','TI':'温度指示仪','TIT':'温度指示变送器','TIC':'温度指示控制器','TE':'温度元件','TW':'温度套管','TV':'温度控制阀','FT':'流量变送器','FI':'流量指示仪','FIC':'流量指示控制器','FE':'流量检测元件','FV':'流量控制阀','FCV':'流量控制阀','SDV':'关断阀','BDV':'泄压阀','SOV':'电磁阀','XV':'开关阀','MOV':'电动阀','ZSO':'开位限位开关','ZSC':'关位限位开关','ZIO':'开位指示','ZIC':'关位指示','RO':'限流孔板','HS':'手动开关','HIC':'手动指示控制器','ESD':'紧急关断','SSV':'地面安全阀','SCSSV':'地面控制井下安全阀','V':'容器','P':'泵','X':'撬装设备','E':'换热设备','C':'压缩机','T':'储罐','F':'过滤器'}
ATTR={'IN_TAG':'仪表功能','IN_NUM':'仪表编号','IN_SERV':'用途','IN_SPEC':'规格','IN_MANU':'制造商','IN_MODL':'型号','IN_DRAW':'参考图纸','IN_NOTE':'说明','IN_TRIPPT':'跳停设定','IN_INTLCK':'联锁','FNC':'仪表功能','LOOP':'回路编号','FUNC':'功能','EQ_TAG':'设备位号','EQ_DES':'设备描述','EQ_DUT':'设计负荷','EQ_DEZ':'设计条件','EQ_OPR':'操作条件','EQ_MAWP':'最大允许工作压力','EQ_SIZ':'尺寸','EQ_AREA':'面积','EQ_TYP':'类型','EQ_WT':'重量','EQ_MAN':'制造商','EQ_MOD':'型号','EQ_MATL':'材质','EQ_COM':'备注','VA_TAG':'阀门编号','VA_DESC':'阀门描述','VA_MANU':'制造商','VA_MODL':'型号','VA_POST':'阀位状态','VA_USE':'用途','LN_TAG':'管线编号','LN_FROM':'流程来源','LN_TO':'流程去向','LN_DESC':'管线描述','LN_SERV':'介质／用途','LN_OTEMP':'操作温度','LN_OPRES':'操作压力','LN_DTEMP':'设计温度','LN_DPRES':'设计压力','LN_MATER':'材料','LN_TYPE':'类型','LN_TEST':'试验','LN_INSUL':'保温','LN_REM':'备注','PSV_TAG':'安全阀功能','PSV_NUM':'安全阀编号','PSV_SIZ':'安全阀尺寸','PSV_SET':'整定压力','PSV_RELIEF':'泄放条件','PSV_DES':'安全阀描述','DWG_NO':'关联图号','DWGNO':'关联图号','VTAG':'阀门位号','VSIZE':'阀门尺寸','VSTATUS':'阀门状态','TAG':'位号','NOZ_TAG':'管口位号','NOZ_NO':'管口编号','NOZ_EQP':'所属设备','NOZ_TYPE':'管口类型','PACKAGENO':'撬装编号','SPEC_1':'连接规格一','SPEC_2':'连接规格二','PANEL':'控制盘','BOARD_NO':'盘号','FUNCTION':'功能'}
REF_RE=re.compile(r'(?:MD\(DD\)-DWG-|MD-DWG-|DWG-|351-4-)?(?:CEPD|WHP[A-Z]|PRP)-(?:PR|IN|SA)-?\d+[A-Z]?(?:\(\d+\))?|(?:351-4-)?PB-(?:CEP|WP[A-Z])-\d+[A-Z]?|(?:CEP|WP[A-Z])-PR-\d+[A-Z]?',re.I)
TAG_RE=re.compile(r'(?<![\w-])(?:(?:CEP|CEPD|PRP|WHP[A-Z]|WP[A-Z])-)?(?:'+ '|'.join(sorted(INSTRUMENTS,key=len,reverse=True))+r')-?\d{3,6}[A-Z]?(?:/[A-Z])?(?![\w-])',re.I)
def tagname(tag):
 m=re.search(r'(?:^|-)([A-Z]+)-?\d',tag);return INSTRUMENTS.get(m[1],'设备／仪表') if m else '设备／仪表'
def normtag(s):
 s=clean(s).upper().replace(' ','');m=TAG_RE.fullmatch(s)
 if not m:return s
 return re.sub(r'([A-Z])-?(\d)',r'\1-\2',s, count=1)
def normref(s):
 s=s.upper().replace(' ','');s=re.sub(r'^(MD\(DD\)-DWG-|MD-DWG-|DWG-|351-4-)','',s);return s
class TaggedRender(svg.SVGRenderBackend):
 def add_strokes(self,d,p):
  super().add_strokes(d,p)
  if d:self.entities[-1].set('data-handle',p.handle);self.entities[-1].set('data-layer',p.layer)
 def add_filling(self,d,p):
  super().add_filling(d,p)
  if d:self.entities[-1].set('data-handle',p.handle);self.entities[-1].set('data-layer',p.layer)
class TaggedSVG(svg.SVGBackend):
 @staticmethod
 def make_backend(page,settings):return TaggedRender(page,settings)
def render(d,folder,variant,ext):
 c=config.Configuration(background_policy=config.BackgroundPolicy.WHITE,color_policy=config.ColorPolicy.BLACK,lineweight_scaling=1.0,min_lineweight=0.12)
 bk=TaggedSVG();Frontend(RenderContext(d),bk,config=c).draw_layout(d.modelspace(),finalize=True)
 w,h=ext[2]-ext[0],ext[3]-ext[1]
 root=bk.get_xml_root_element(layout.Page(841,841*h/w),render_box=BoundingBox2d([(ext[0],ext[1]),(ext[2],ext[3])]))
 import xml.etree.ElementTree as ET
 # Inline styles also support CAD-to-PDF rendering engines without CSS class support.
 styles={}
 for el in root.iter('style'):
  styles.update(dict(re.findall(r'\.([A-Z]\d+) \{([^}]+)\}',el.text or '')))
 for el in root.iter('path'):
  cl=el.attrib.pop('class',None)
  if cl in styles:el.set('style',styles[cl])
 text=ET.tostring(root,encoding='unicode');(folder/f'{variant}.svg').write_text(text,encoding='utf-8')
 return bk.transformation_matrix,root.get('viewBox')
def title(r):
 s=Path(r['filename']).stem
 s=re.sub(r'^\S+\s*','',s);s=re.sub(r'\s*REV\s*\d+\s*$','',s,flags=re.I)
 s=re.sub(r'^(PROCESS |UTILITY )?PIPING & INSTRUMENT(?:ATION)? DIAGRAM\s*','',s,flags=re.I)
 return translate(s).strip() or r['code']
def get_text(e):return clean(e.plain_text() if e.dxftype()=='MTEXT' else e.dxf.text)
def point(e):
 try:
  if e.dxftype() in ['TEXT','ATTRIB','ATTDEF']:
   align,p1,p2=e.get_placement();return p1
  return e.dxf.insert
 except:return (0,0,0)
def read_source(path):
 d=ezdxf.readfile(path)
 try:return d,d.audit()
 except AttributeError as ex:
  # ezdxf audit may remove a layout object that it later dereferences. Reload the
  # untouched conversion; validate geometry separately instead of saving partial repairs.
  from types import SimpleNamespace
  return ezdxf.readfile(path),SimpleNamespace(errors=[],fixes=[],unavailable=str(ex))
def build(r):
 folder=BASE/'output'/r['id'];folder.mkdir(parents=True,exist_ok=True)
 previous=json.loads((folder/'drawing.json').read_text(encoding='utf-8')) if r.get('workingDxf') and (folder/'drawing.json').exists() else None
 try:
  d,audit=read_source(BASE/r.get('workingDxf',r['dxf']))
  texts=[];items=[];equip=[];refs=[];ledger=[]
  # Keep every text-bearing symbol and every modelspace graphical entity clickable.
  for e in d.modelspace():
   et=e.dxftype();handle=e.dxf.handle
   item={'handle':handle,'entity':et,'layer':e.dxf.get('layer','0'),'tag':'','name':'CAD图元','attributes':[],'texts':[]}
   if et=='INSERT':
    item['block']=e.dxf.name; at={a.dxf.tag.upper():clean(a.dxf.text) for a in e.attribs}
    for k,v in at.items():item['attributes'].append({'key':k,'label':ATTR.get(k,'属性 '+k),'original':v,'value':v if r.get('workingDxf') else translate(v)})
    for a,b in [('IN_TAG','IN_NUM'),('FNC','LOOP'),('PSV_TAG','PSV_NUM')]:
     if a in at and b in at and re.fullmatch(r'[A-Z]{1,6}',at[a]) and re.fullmatch(r'\d+[A-Z]?(?:/[A-Z])?',at[b]):item['tag']=at[a]+'-'+at[b];break
    if not item['tag']:
     for k in ['EQ_TAG','VA_TAG','VTAG','LN_TAG','TAG','NOZ_TAG']:
      if at.get(k):item['tag']=normtag(at[k]);break
    item['name']=translate(at.get('EQ_DES') or at.get('VA_DESC') or at.get('LN_DESC') or at.get('IN_SERV') or '') or (tagname(item['tag']) if item['tag'] else 'CAD属性块')
   try:
    for x in disassemble.recursive_decompose([e]):
     if x.dxftype() not in ['TEXT','MTEXT','ATTRIB']:continue
     if x.dxftype()=='ATTRIB' and x.dxf.flags&1:continue
     t=get_text(x)
     if not t:continue
     p=point(x);rec={'handle':handle,'text':t,'zh':translate(t),'xy':[p[0],p[1]]};texts.append(rec);item['texts'].append(t)
     for m in REF_RE.finditer(t):refs.append({'handle':handle,'code':m[0],'key':normref(m[0]),'context':translate(t),'xy':rec['xy']})
     if not item['tag']:
      m=TAG_RE.search(t)
      if m:item['tag']=normtag(m[0]);item['name']=tagname(item['tag'])
   except Exception as ex:item['readWarning']=str(ex)
   try:
    p=point(e);item['xy']=[p[0],p[1]]
    if item['tag'] or et=='INSERT':
     box=bbox.extents([e],fast=True)
     if box.has_data:item['box']=[box.extmin.x,box.extmin.y,box.extmax.x,box.extmax.y];item['xy']=[box.center.x,box.center.y]
   except:pass
   if item['tag']:equip.append({'handle':handle,'tag':item['tag'],'name':item['name'],'xy':item['xy']})
   items.append(item)
  ext0=d.header.get('$EXTMIN');ext1=d.header.get('$EXTMAX');ext=[ext0[0],ext0[1],ext1[0],ext1[1]]
  if not all(math.isfinite(x) and abs(x)<1e9 for x in ext) or ext[2]<=ext[0] or ext[3]<=ext[1]:
   box=bbox.extents(d.modelspace(),fast=True);ext=[box.extmin.x,box.extmin.y,box.extmax.x,box.extmax.y]
  if r.get('fixedExtents'):ext=r['fixedExtents']
  # Font substitution is for display only. CAD copies get a dedicated Chinese text style.
  originalfonts={s.dxf.name:(s.dxf.font,s.dxf.get('bigfont','')) for s in d.styles}
  for s in d.styles:s.dxf.font=drawing_font();s.dxf.bigfont=''
  matrix,viewbox=render(d,folder,'working-original' if r.get('workingDxf') and (folder/'original.svg').exists() else 'original',ext)
  # Translate text, including nested block definitions and attribute values. Identifiers remain intact.
  for e in list(d.entitydb.values()):
   if e.dxftype() not in ['TEXT','MTEXT','ATTRIB','ATTDEF']:continue
   raw=e.text if e.dxftype()=='MTEXT' else e.dxf.text
   if r.get('workingDxf') and e.dxftype()=='ATTRIB':continue
   original=get_text(e);zh=translate(original)
   if zh==original:continue
   # Attributes holding identifiers are never translated.
   if e.dxftype() in ['ATTRIB','ATTDEF'] and e.dxf.tag.upper() in {'IN_TAG','IN_NUM','FNC','LOOP','PSV_TAG','PSV_NUM','EQ_TAG','VA_TAG','VTAG','LN_TAG','TAG','NOZ_TAG','DWG_NO','DWGNO'}:continue
   ledger.append({'handle':e.dxf.handle,'entity':e.dxftype(),'original':original,'chinese':zh,'review':bool(residual(original))})
   if e.dxftype()=='MTEXT':e.text=zh;e.dxf.style='中文标注'
   else:
    e.dxf.text=zh;e.dxf.style='中文标注'
    # Preserve the annotation envelope. CJK glyphs are wider than Latin glyphs.
    oldw=sum(1 if ord(c)>127 else .56 for c in original);neww=sum(1 if ord(c)>127 else .56 for c in zh)
    e.dxf.width=min(1.0,e.dxf.get('width',1.0)*oldw/max(neww,1))
  if '中文标注' not in d.styles:d.styles.new('中文标注',dxfattribs={'font':drawing_font()})
  matrix,viewbox=render(d,folder,'chinese',ext)
  for it in items:
   p=matrix.transform((*it['xy'],0));it['position']=[p.x,p.y]
   if 'box' in it:
    x0,y0,x1,y1=it['box'];p0=matrix.transform((x0,y0,0));p1=matrix.transform((x1,y1,0));it['bounds']=[min(p0.x,p1.x),min(p0.y,p1.y),abs(p1.x-p0.x),abs(p1.y-p0.y)]
  for ref in refs:
   p=matrix.transform((*ref['xy'],0));ref['position']=[p.x,p.y]
  for st in d.styles:
   if st.dxf.name in originalfonts:st.dxf.font,st.dxf.bigfont=originalfonts[st.dxf.name]
  d.styles.get('中文标注').dxf.font=Path(drawing_font()).name
  d.saveas(folder/'中文图纸.dxf')
  centerlines=extract_centerlines(d,lambda p:tuple(matrix.transform(p))[:2],max(1.e-8,(ext[2]-ext[0])*1.e-5))
  payload={'centerlines':centerlines,'id':r['id'],'title':title(r),'code':r['code'],'platform':r['platform'],'source':r['source'],'extents':ext,'viewBox':[float(x) for x in viewbox.split()],'items':items,'equipment':equip,'references':refs,'texts':texts,'translations':ledger,'entityCounts':r['entityCounts'],'audit':{'errors':len(audit.errors),'fixes':len(audit.fixes),'unavailable':getattr(audit,'unavailable',None)},'xref':[b.name for b in d.blocks if b.block.dxf.flags&4]}
  from attribute_metadata import decorate,search_extra
  decorate(payload,BASE,r,d,previous);ledger=payload['translations'];equip=payload['equipment']
  (folder/'drawing.json').write_text(json.dumps(payload,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
  return {'id':r['id'],'code':r['code'],'title':payload['title'],'platform':r['platform'],'source':r['source'],'equipment':equip,'references':refs,'textCount':len(texts),'translated':len(ledger),'reviewCount':sum(x['review'] for x in ledger),'entityCount':len(items),'search':' '.join([r['filename'],payload['title'],''.join(lazy_pinyin(payload['title']))]+[x['zh'] for x in texts]+[e['tag'] for e in equip]+[search_extra(payload)]),'status':'ready'}
 except Exception as ex:
  traceback.print_exc();return {'id':r['id'],'code':r['code'],'title':title(r),'platform':r['platform'],'status':'error','error':str(ex)}
def main():
 records=json.loads((BASE/'data/manifest.json').read_text(encoding='utf-8')); selected=set(sys.argv[1:]);rs=[r for r in records if not selected or r['id'] in selected]
 results=[]
 with concurrent.futures.ProcessPoolExecutor(max_workers=3) as pool:
  for n,result in enumerate(pool.map(build,rs)):
   results.append(result);print(f"{n+1}/{len(rs)} {result['id']} {result['status']}",flush=True)
 old=json.loads((BASE/'data/catalog.json').read_text(encoding='utf-8')) if selected and (BASE/'data/catalog.json').exists() else []
 allres={r['id']:r for r in old};allres.update({r['id']:r for r in results})
 aliases=collections.defaultdict(list)
 for r in records:
  aliases[normref(r['code'])].append(r['id'])
 for r in allres.values():
  for ref in r.get('references',[]):ref['targets']=[x for x in aliases.get(ref['key'],[]) if x!=r['id']]
 (BASE/'data/catalog.json').write_text(json.dumps(list(allres.values()),ensure_ascii=False,separators=(',',':')),encoding='utf-8')
 (BASE/'data/glossary.json').write_text(json.dumps({'instruments':INSTRUMENTS,'attributes':ATTR},ensure_ascii=False),encoding='utf-8')
if __name__=='__main__':main()
