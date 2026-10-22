"""Build and verify one uploaded DWG before publishing it in the live catalog."""
from pathlib import Path
import sys,json,subprocess,collections,hashlib
base=Path(sys.argv[1]).resolve();id=sys.argv[2];sys.path.insert(0,str(Path(__file__).resolve().parents[1]));sys.path.insert(0,str(Path(__file__).parent))
from management import read_json,write_json
jobpath=base/'data/upload-jobs'/f'{id}.json';job=read_json(jobpath)
def progress(message):
 if read_json(jobpath).get('status')=='failed':raise RuntimeError('导入已中断，请重新上传')
 job.update(status='processing',message=message);write_json(jobpath,job)
from cad_runtime import convert
progress('正在读取 DWG 原始图元')
source=base.parent/job['source'];dxfdir=base/'data/source-dxf/uploads'/id
convert(source.parent,dxfdir,'DXF','*.dwg')
dxf=next(iter(dxfdir.glob('*.dxf')),None)
if not dxf:raise RuntimeError('DWG 未生成可读取的 DXF')
import ezdxf
source_doc=ezdxf.readfile(dxf)
if not len(source_doc.modelspace()):raise ValueError('DWG 模型空间为空，当前查看器需要模型空间图纸')
r={'id':id,'filename':job['filename'],'code':job['code'],'platform':job['platform'],'source':job['source'],'dxf':str(dxf.relative_to(base)),'sha256':job['sha256'],'entityCounts':dict(collections.Counter(e.dxftype() for e in source_doc.modelspace()))}
progress('正在生成矢量图纸与设备索引')
import build,refresh,preserve_cad
build.BASE=base;build.ROOT=base.parent;refresh.BASE=base;refresh.ROOT=base.parent
c=build.build(r)
if c['status']!='ready':raise RuntimeError(c.get('error','图纸解析失败'))
progress('正在应用中文术语并生成中文 DWG')
c=refresh.work(r);c['title']=job['title'];c['search']+=' '+job['title']
from pypinyin import lazy_pinyin
c['search']+=' '+''.join(lazy_pinyin(job['title']))
folder=base/'output'/id;d=read_json(folder/'drawing.json');d['title']=job['title'];write_json(folder/'drawing.json',d)
preserve_cad.apply(dxf,folder/'中文图纸.dxf')
convert(folder,folder,'DWG','*.dxf')
progress('正在回读 DWG 并校验图元、位号与文字')
roundtrip=base/'data/roundtrip-check'/id
convert(folder,roundtrip,'DXF','*.dwg')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tests'))
import verify_cad
verify_cad.BASE=base;check=verify_cad.work(r)
if check['errors']:raise RuntimeError('CAD 完整性校验失败：'+'；'.join(check['errors']))
assert hashlib.sha256(source.read_bytes()).hexdigest()==r['sha256']
write_json(base/'uploads'/id/'verification.json',check)
write_json(base/'uploads'/id/'result.json',{'manifest':r,'catalog':c})
progress('CAD 校验通过，正在更新目录与跨图关联')
