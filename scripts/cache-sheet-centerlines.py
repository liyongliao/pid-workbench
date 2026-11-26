"""Backfill the current Mac revision without changing historical drawing files."""
import argparse
import concurrent.futures
import hashlib
import json
import sqlite3
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'cad-workbench'))
import ezdxf
from centerlines import PROCESS_LAYER, extract


def build(task):
    base, cache, record = task
    raw = (base/'output'/record['id']/'drawing.json').read_bytes()
    dest = cache / (hashlib.sha256(raw).hexdigest()+'.json')
    if dest.exists():
        return
    data = json.loads(raw)
    # Saved anchor pairs capture the original render scale, reflection and translation.
    anchors = [(i['xy'],i['position']) for i in data['items'] if 'position' in i and 'xy' in i]
    xy,uv = anchors[0]
    far,other = max(anchors,key=lambda a: (a[0][0]-xy[0])**2+(a[0][1]-xy[1])**2)
    dx,dy = far[0]-xy[0],far[1]-xy[1]
    if not dx and not dy:
        if not any(is_centerline(i) for i in data['items']):
            return
        raise ValueError('缺少坐标锚点 '+record['id'])
    scale = ((other[0]-uv[0])*dx-(other[1]-uv[1])*dy)/(dx*dx+dy*dy)
    def project(p):
        return (uv[0]+(p[0]-xy[0])*scale, uv[1]-(p[1]-xy[1])*scale)
    if any(max(abs(u-v) for u,v in zip(project(p),q))>.1 for p,q in anchors):
        raise ValueError('坐标校验失败 '+record['id'])
    doc = ezdxf.readfile(base / (record.get('workingDxf') or record['dxf']))
    paths = extract(doc,project,max(1.e-8,(data['extents'][2]-data['extents'][0])*1.e-5))
    temp = dest.with_suffix('.tmp')
    temp.write_text(json.dumps(paths,separators=(',',':')))
    temp.replace(dest)


def is_centerline(item):
    return PROCESS_LAYER.search(item['layer']) and item['entity'] in ('LINE','LWPOLYLINE','POLYLINE','ARC','SPLINE')


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('vault',type=Path)
    args=parser.parse_args()
    with sqlite3.connect(args.vault/'workbench.sqlite3') as db:
        generation=db.execute('SELECT generation FROM head').fetchone()[0]
    base=args.vault/'revisions'/generation/'library'
    cache=args.vault/'cache'/'cad-centerlines-v1'
    cache.mkdir(exist_ok=True,parents=True)
    records=json.loads((base/'data/manifest.json').read_bytes())
    with concurrent.futures.ProcessPoolExecutor(max_workers=4) as pool:
        list(pool.map(build,[(base,cache,r) for r in records]))
    print(len(records),'张图纸核对完成')
