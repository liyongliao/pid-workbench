"""Read indexed Navisworks exports. Geometry and component names stay on the data volume."""
import contextlib
import json
import re
import sqlite3
import struct
from functools import lru_cache
from pathlib import Path
import numpy as np


def component(name, fragment):
    """Group only by explicit source hierarchy. Numbered valves are local to a branch."""
    branch = re.search(r'\bBRANCH\s+/([^ ]+)', name, re.I)
    equip = re.search(r'\bEQUIPMENT\s+/([^ /]+)', name, re.I)
    if branch:
        line = re.sub(r'/B\d+[A-Z]?(?:/.*)?$', '', branch[1], flags=re.I)
        leaf = re.match(r'^(VALVE|INSTRUMENT)\s+\d+\b',name,re.I)
        if leaf:
            kind = '阀门' if leaf[1].upper()=='VALVE' else '仪表'
            return kind, name, ''
        return '管线',line,line
    if equip:
        return '设备',equip[1],equip[1]
    return '构件',name or fragment,''


def read_header(path):
    with path.open('rb') as stream:
        head=stream.read(20)
        if head[:4]!=b'glTF' or head[16:20]!=b'JSON':
            raise ValueError('无效 GLB')
        length=struct.unpack_from('<I',head,12)[0]
        return json.loads(stream.read(length)),28+length


def array(doc, raw, idx):
    a=doc['accessors'][idx]
    v=doc['bufferViews'][a['bufferView']]
    dtype={5123:'<u2',5125:'<u4',5126:'<f4',5121:'u1'}[a['componentType']]
    width={'SCALAR':1,'VEC3':3}[a['type']]
    start=v.get('byteOffset',0)+a.get('byteOffset',0)
    step=np.dtype(dtype).itemsize
    return np.ndarray((a['count'],width),dtype,raw,start,(v.get('byteStride',width*step),step))


def geometry(root, rows):
    """Compact indexed world-space triangles with exact component ranges for picking."""
    vertices=[]; indices=[]; ranges=[]; lines=[]; line_ranges=[]; nv=ni=nl=0
    file=None
    for part,node_id,oid in rows:
        if part!=file:
            path=root/'parts'/part
            doc,offset=read_header(path)
            with path.open('rb') as stream:
                stream.seek(offset); raw=stream.read()
            file=part
        node=doc['nodes'][node_id]
        matrix=np.asarray(node.get('matrix',np.eye(4).ravel()),dtype=np.float32).reshape(4,4)
        for prim in doc['meshes'][node['mesh']]['primitives']:
            mode=prim.get('mode',4)
            if mode not in (1,4):continue
            xyz=array(doc,raw,prim['attributes']['POSITION'])
            world=xyz @ matrix[:3,:3]+matrix[3,:3]
            idx=array(doc,raw,prim['indices']).ravel().astype('<u4') if 'indices' in prim else np.arange(len(xyz),dtype='<u4')
            if mode==1:
                lines.append(world[idx].astype('<f4'));nl+=len(idx);line_ranges.append([nl,oid]);continue
            vertices.append(world.astype('<f4'));indices.append(idx+nv)
            nv+=len(xyz);ni+=len(idx);ranges.append([ni,oid])
    header=json.dumps(dict(vertices=nv,indices=ni,ranges=ranges,lines=nl,lineRanges=line_ranges),separators=(',',':')).encode()
    header+=b' '*(-len(header)%4)
    return struct.pack('<I',len(header))+header+b''.join(v.tobytes() for v in vertices)+b''.join(i.tobytes() for i in indices)+b''.join(v.tobytes() for v in lines)


def platform_dir(vault,model):
    if model not in ('k','l'):raise ValueError('未知模型平台')
    root=vault.root/'models'/model
    if not (root/'info.json').is_file():raise ValueError('平台模型尚未入库')
    return root


def catalog(vault):
    return [dict(json.loads(f.read_bytes()),reviewReady=(f.parent/'editor/index.json').is_file())
            for f in sorted((vault.root/'models').glob('[kl]/info.json'))]


def connect(root):
    db=sqlite3.connect((root/'objects.sqlite').resolve().as_uri()+'?mode=ro',uri=True)
    db.row_factory=sqlite3.Row
    return contextlib.closing(db)


def describe(root,oid):
    with connect(root) as db:
        row=db.execute('SELECT * FROM objects WHERE id=?',(oid,)).fetchone()
        if not row:raise ValueError('模型对象不存在')
        return dict(row)


def lookup(root,term,kind,offset):
    with connect(root) as db:
        clause="WHERE (?='' OR kind=?) AND instr(upper(name),upper(?))>0"
        rows=db.execute("SELECT * FROM objects "+clause+" ORDER BY (kind='构件'),id LIMIT 51 OFFSET ?",(kind,kind,term,offset)).fetchall()
        return {'rows':[dict(r) for r in rows[:50]],'more':len(rows)>50}


def detail(root,oid,page):
    # Limit each response by source triangle count and return all parts over successive pages.
    with connect(root) as db:
        rows=db.execute('SELECT part,node,object,tri FROM fragments WHERE object=? ORDER BY part,node LIMIT 512 OFFSET ?', (oid,page)).fetchall()
    if not rows:raise ValueError('构件几何不存在')
    count=0; limit=0
    for row in rows:
        if count and limit+row[3]>170000:break
        count+=1;limit+=row[3]
    return geometry(root,[tuple(r)[:3] for r in rows[:count]]),count

@lru_cache(maxsize=64)
def cad_tags(file,revision):
    document=json.loads(file.read_bytes())
    result={}
    for item in document['items']:
        attrs={a['key'].upper():str(a.get('value','')).strip().upper() for a in item.get('attributes',[])}
        value=next((attrs[k] for k in ('LN_TAG','LINE-TAG','LINE_NO','EQNO','TAG') if attrs.get(k)),str(item.get('tag','')).strip().upper())
        if value:result[item['handle']]=value
    return result


def matches(vault,manager,root,drawing):
    info=json.loads((root/'info.json').read_bytes())
    cat=manager.catmap.get(drawing)
    if not cat or cat['platform'].upper()!=info['platform']:return {}
    tags=cad_tags(manager.base/'output'/drawing/'drawing.json',cat.get('revision',0))
    mapping={}
    with connect(root) as db:
        for tag in set(tags.values()):
            rows=db.execute('SELECT id FROM objects WHERE tag=? COLLATE NOCASE LIMIT 2',(tag,)).fetchall()
            if len(rows)==1:mapping[tag]=rows[0][0]
    result={h:mapping[t] for h,t in tags.items() if t in mapping}
    with contextlib.closing(vault.connect()) as db:
        for row in db.execute('SELECT handle,object FROM model_links WHERE drawing=? AND model=? AND digest=?',(drawing,info['id'],info['digest'])):
            result[row[0]]=row[1]
    return result


def bind(vault,manager,data,actor):
    root=platform_dir(vault,data.get('model'));info=json.loads((root/'info.json').read_bytes())
    drawing=data['drawing'];handle=data.get('handle')
    if info['platform']!=manager.catmap[drawing]['platform'] or info['digest']!=data.get('digest'):
        raise ValueError('平台或模型版本不一致，请重新选择')
    if not any(i['handle']==handle for i in manager.drawing(drawing)['items']):raise ValueError('图元不存在')
    oid=data.get('object')
    if oid is not None:
        oid=int(oid);describe(root,oid)
    with vault.transaction() as db:
        key=(drawing,handle,info['id'],info['digest'])
        old=db.execute('SELECT object FROM model_links WHERE drawing=? AND handle=? AND model=? AND digest=?',key).fetchone()
        if data.get('prior')!=(old[0] if old else None):raise ValueError('关联已变更，请刷新后核对')
        if oid is None:
            db.execute('DELETE FROM model_links WHERE drawing=? AND handle=? AND model=? AND digest=?',key)
        else:
            db.execute('INSERT OR REPLACE INTO model_links VALUES(?,?,?,?,?)',(*key,oid))
        from vault import now
        vault.audit_event(db,dict(type='恢复自动模型关联' if oid is None else '关联三维构件',time=now(),drawing=drawing,code=manager.catmap[drawing]['code'],handle=handle,actor=actor,title=manager.catmap[drawing]['title'],description=info['name'],changes=[dict(field='模型对象',before=old[0] if old else None,after=oid)]))
    return {'saved':True}


def serve(handler,vault,manager,path,params):
    q=lambda k,default='':params.get(k,[default])[0]
    if path=='/api/models':return handler.send(catalog(vault))
    if path=='/api/models/blocks':
        folder=vault.root/'models'/'blocks'
        asset=q('asset')
        if asset and not re.fullmatch(r'[0-9a-f]{64}',asset):
            raise ValueError('构件版本无效')
        file=folder/(asset+'.bin' if asset else 'catalog.json')
        if not file.is_file():
            return handler.send({'error':'构件不存在'},404) if asset else handler.send({})
        return handler.cached(('pid-block',asset or file.stat().st_mtime_ns),file.read_bytes,
                              'application/octet-stream' if asset else 'application/json')
    root=platform_dir(vault,q('model'));info=json.loads((root/'info.json').read_bytes())
    if path.endswith('/overview') or path.endswith('/palette'):
        f=root/('overview.bin' if path.endswith('/overview') else 'overview.json')
        packed=f.with_suffix('.bin.gz')
        if f.suffix=='.bin' and packed.is_file() and re.search(r'(?:^|,)\s*gzip\s*(?:,|$)',handler.headers.get('Accept-Encoding',''),re.I):
            etag=f'W/"{info["digest"]}-{f.stat().st_mtime_ns}"'
            headers={'ETag':etag,'Cache-Control':'private, no-cache, must-revalidate','Vary':'Cookie, Accept-Encoding','Content-Encoding':'gzip'}
            if etag in [v.strip() for v in handler.headers.get('If-None-Match','').split(',')]:
                handler.send_response(304)
                for k,v in headers.items():handler.send_header(k,v)
                return handler.end_headers()
            return handler.send(packed.read_bytes(),ctype='application/octet-stream',headers=headers)
        return handler.cached((info['digest'],f.stat().st_mtime_ns,f.name),f.read_bytes,'application/octet-stream' if f.suffix=='.bin' else 'application/json')
    if path.endswith('/objects'):return handler.send(lookup(root,q('q')[:160],q('kind'),max(0,int(q('offset',0)))))
    if path.endswith('/links'):
        drawing=q('drawing')
        with contextlib.closing(vault.connect()) as db:
            manual=dict(db.execute('SELECT handle,object FROM model_links WHERE drawing=? AND model=? AND digest=?',(drawing,info['id'],info['digest'])).fetchall())
        return handler.send(dict(links=matches(vault,manager,root,drawing),manual=manual))
    if path.endswith('/nearby'):
        point=[float(v) for v in q('point').split(',')]
        start=max(0,int(q('start',0)))
        def read_region():
            n,more,mesh,kinds=nearby(root,point,start)
            meta=json.dumps(dict(next=start+n,more=more,kinds=kinds)).encode()
            meta+=b' '*(-len(meta)%4)
            return struct.pack('<I',len(meta))+meta+mesh
        return handler.cached((info['digest'],*point,start,'region2'),read_region,'application/octet-stream')
    oid=int(q('object',0))
    if path.endswith('/object'):
        obj=describe(root,oid);refs=[]
        with connect(root) as db:
            first=db.execute('SELECT part,node FROM fragments WHERE object=? ORDER BY part,node LIMIT 1',(oid,)).fetchone()
        if first:
            doc,_=read_header(root/'parts'/first[0])
            node=doc['nodes'][first[1]];obj['sourceId']=node.get('extras',{}).get('sourceId','');obj['sourceName']=node.get('name','')
        for cat in manager.catalog:
            if cat['platform']!=info['platform']:continue
            for handle,target in matches(vault,manager,root,cat['id']).items():
                if oid==target:refs.append(dict(drawing=cat['id'],handle=handle,code=cat['code'],title=cat['title']))
        return handler.send(dict(obj,drawings=refs))
    if path.endswith('/detail'):
        start=max(0,int(q('start',0)))
        # Prefix the binary payload with the next fragment offset for paging.
        def read():
            payload,n=detail(root,oid,start)
            return struct.pack('<I',start+n)+payload
        return handler.cached((info['digest'],oid,start,'geometry2'),read,'application/octet-stream')
    return handler.send({'error':'未知模型请求'},404)


def index_space(root):
    """Build a spatial index over the same transformed source geometry used for picking."""
    db=sqlite3.connect(root/'objects.sqlite')
    try:
        db.execute('CREATE VIRTUAL TABLE IF NOT EXISTS space USING rtree(id,x0,x1,y0,y1,z0,z1)')
        if db.execute('SELECT count(*) FROM space').fetchone()[0]:return
        with db:
            for file in sorted((root/'parts').glob('*.glb')):
                doc,_=read_header(file)
                local=[]
                for mesh in doc['meshes']:
                    boxes=[doc['accessors'][p['attributes']['POSITION']] for p in mesh['primitives']]
                    local.append([np.min([a['min'] for a in boxes],axis=0),np.max([a['max'] for a in boxes],axis=0)])
                records=db.execute('SELECT rowid,node FROM fragments WHERE part=? ORDER BY node',(file.name,)).fetchall()
                if not records:continue
                nodes=[doc['nodes'][i] for _,i in records]
                bounds=np.array([local[n['mesh']] for n in nodes])
                mat=np.array([n.get('matrix',np.eye(4).ravel()) for n in nodes]).reshape(-1,4,4)
                center=np.einsum('ni,nij->nj',bounds.mean(axis=1),mat[:,:3,:3])+mat[:,3,:3]
                radius=np.einsum('ni,nij->nj',(bounds[:,1]-bounds[:,0])*.5,abs(mat[:,:3,:3]))
                values=np.stack((center-radius,center+radius),axis=2).reshape(-1,6).tolist()
                db.executemany('INSERT INTO space VALUES(?,?,?,?,?,?,?)',[(r[0],*coords) for r,coords in zip(records,values)])
    finally:
        db.close()


def nearby(root,point,start):
    if len(point)!=3 or not all(np.isfinite(point)) or any(abs(n)>1e7 for n in point):raise ValueError('空间位置无效')
    x,y,z=point;radius=1.8
    with connect(root) as db:
        rows=db.execute('''SELECT f.part,f.node,f.object,f.tri,o.kind
            FROM space s JOIN fragments f ON s.id=f.rowid JOIN objects o ON o.id=f.object
            WHERE s.x1>=? AND s.x0<=? AND s.y1>=? AND s.y0<=? AND s.z1>=? AND s.z0<=?
            ORDER BY f.part,f.node LIMIT 257 OFFSET ?''',(x-radius,x+radius,y-radius,y+radius,z-radius,z+radius,start)).fetchall()
    n=0;total=0
    for row in rows[:256]:
        if n and total+row[3]>110000:break
        n+=1;total+=row[3]
    return n,n<len(rows),geometry(root,[(r[0],r[1],r[2]) for r in rows[:n]]),{r[2]:r[4] for r in rows[:n]}


def preview_material(kind,name,rgba):
    """Muted source finishes on structure, consistent engineering colours on process objects."""
    import colorsys
    if kind=='构件':
        h,s,v=colorsys.rgb_to_hsv(*rgba[:3])
        if s>.42 and v>.12:
            rgb=colorsys.hsv_to_rgb(h,min(s*.7,.68),max(.46,min(.84,.30+v*.53)))
            return '#'+''.join(f'{round(n*255):02x}' for n in rgb)
        return '#879ba8'
    if kind=='管线':
        system=re.search(r'-(FW|CO2|CI|DO|N2|WS|GC|AV|IA|FG)-',name.upper())
        return {'FW':'#b26c53','CO2':'#378b82','CI':'#588bb5','DO':'#b99656','N2':'#7683a8','WS':'#489893','IA':'#6598ad','FG':'#b79a53'}.get(system[1] if system else '', '#318e8b')
    return {'阀门':'#347eaf','仪表':'#b19055','设备':'#b0bdc3'}[kind]


def style_overview(root):
    import gzip
    file=root/'overview.json';palette=json.loads(file.read_bytes())
    with connect(root) as db:
        # Each object keeps its source fragment identity. Only the display colour changes.
        entries=[]
        for oid in palette:
            row=db.execute('SELECT f.part,f.node,o.kind,o.name FROM fragments f JOIN objects o ON o.id=f.object WHERE f.object=? LIMIT 1',(int(oid),)).fetchone()
            entries.append((row[0],row[1],oid,row[2],row[3]))
    previous=None
    for part,node,oid,kind,name in sorted(entries):
        if previous!=part:
            doc,_=read_header(root/'parts'/part);previous=part
        mesh=doc['nodes'][node]['mesh'];primitive=doc['meshes'][mesh]['primitives'][0]
        material=doc['materials'][primitive.get('material',0)]
        rgba=material.get('pbrMetallicRoughness',{}).get('baseColorFactor',[.6,.6,.6,1])
        palette[oid]=[kind,preview_material(kind,name,rgba)]
    file.write_text(json.dumps(palette,ensure_ascii=False,separators=(',',':')))
    asset=root/'overview.bin';asset.with_suffix('.bin.gz').write_bytes(gzip.compress(asset.read_bytes(),compresslevel=5,mtime=0))
