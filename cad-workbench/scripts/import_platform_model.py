"""Install a full-fidelity chunked GLB export from a platform's NWD into a new local model library."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from platform_models import component,geometry,read_header,index_space,style_overview


def install(source,vault,model,nwd):
    parent=vault/'models';parent.mkdir(parents=True,exist_ok=True)
    dest=parent/model
    if dest.exists():raise ValueError('该平台模型已入库')
    meta=json.loads((source/'index.json').read_text())
    if meta.get('format')!='offshore-full-fidelity-chunks':raise ValueError('需要含源构件标识的 GLB 分块')
    with tempfile.TemporaryDirectory(dir=parent) as tmp:
        root=Path(tmp)/'model';parts=root/'parts';parts.mkdir(parents=True)
        db=sqlite3.connect(root/'objects.sqlite')
        db.executescript('CREATE TABLE objects(id INTEGER PRIMARY KEY, kind TEXT, name TEXT, tag TEXT, count INTEGER); CREATE TABLE fragments(part TEXT,node INTEGER,object INTEGER,tri INTEGER);')
        ids={}; counts={}; preview={}; rows=[]; total=0
        excluded_file=source.parent/f'platform-{model}-presentation.json'
        excluded={r['sourceId'] for r in json.loads(excluded_file.read_bytes()).get('exclusions',[])} if excluded_file.exists() else set()
        for f in sorted(source.glob('part-*.glb')):
            target=parts/f.name
            # Independent copy, using filesystem cloning when supported.
            if sys.platform!='darwin' or subprocess.run(['cp','-c',str(f),str(target)],stderr=subprocess.DEVNULL).returncode:
                shutil.copyfile(f,target)
            d,_=read_header(target)
            choices=[]
            for j,node in enumerate(d['nodes']):
                if 'mesh' not in node:continue
                sourceid=node['extras']['sourceId'];name=node['name']
                kind,label,tag=component(name,sourceid)
                key=(kind,label if kind!='构件' else sourceid)
                if key not in ids:
                    oid=len(ids)+1;ids[key]=oid;rows.append((oid,kind,label,tag));counts[oid]=0
                oid=ids[key];counts[oid]+=1; total+=1
                mesh=d['meshes'][node['mesh']]['primitives']
                tri=sum(d['accessors'][p['indices']]['count']//3 for p in mesh if p.get('mode',4)==4)
                choices.append((f.name,j,oid,tri))
                if not tri or sourceid in excluded or tri>12000:continue
                a=d['accessors'][mesh[0]['attributes']['POSITION']]
                m=node.get('matrix')
                if not m:continue
                scale=math.sqrt(sum(v*v for v in m[:3]))
                span=max((v-u)*scale for u,v in zip(a['min'],a['max']))
                if not .03<span<180:continue
                center=[(lo+hi)*.5 for lo,hi in zip(a['min'],a['max'])]
                xyz=[m[12+k]+sum(center[i]*m[i*4+k] for i in range(3)) for k in range(3)]
                cell=(kind,*(math.floor(n/2.8) for n in xyz))
                score=span/(max(tri,8)**.32)
                if cell not in preview or score>preview[cell][0]:preview[cell]=(score,f.name,j,oid,tri,kind)
            db.executemany('INSERT INTO fragments VALUES(?,?,?,?)',choices)
        db.executemany('INSERT INTO objects VALUES(?,?,?,?,?)',[(*r,counts[r[0]]) for r in rows])
        db.executescript('CREATE INDEX by_object ON fragments(object,part,node);CREATE INDEX by_tag ON objects(tag COLLATE NOCASE);CREATE INDEX by_part ON fragments(part,node);')
        db.commit();db.close()
        index_space(root)
        chosen=[];used={}
        budgets={'设备':180000,'构件':360000,'管线':180000,'阀门':90000,'仪表':40000}
        for score,part,node,oid,tri,kind in sorted(preview.values(),reverse=True):
            if used.get(kind,0)+tri<=budgets[kind]:
                chosen.append((part,node,oid));used[kind]=used.get(kind,0)+tri
        (root/'overview.bin').write_bytes(geometry(root,sorted(chosen)))
        visible={v[2] for v in chosen}
        (root/'overview.json').write_text(json.dumps({r[0]:r[1] for r in rows if r[0] in visible},ensure_ascii=False))
        style_overview(root)
        with nwd.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
        info=dict(id=model,platform={'l':'WHPL','k':'CEPK'}[model],name=model.upper()+' 平台',source=nwd.name,digest=digest,fragments=total,objects=len(ids),overview=len(chosen),bounds=meta['bounds'])
        deck=source.parent.parent.parent/'import-work'/f'platform-{model}.deck-view.json'
        if deck.is_file():
            view=json.loads(deck.read_bytes());info['view']=dict(min=view['min'],max=view['max'])
        (root/'info.json').write_text(json.dumps(info,ensure_ascii=False));os.rename(root,dest)
        print(info,flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('source',type=Path);parser.add_argument('vault',type=Path);parser.add_argument('model',choices=['k','l']);parser.add_argument('nwd',type=Path)
    a=parser.parse_args();install(a.source,a.vault,a.model,a.nwd)
