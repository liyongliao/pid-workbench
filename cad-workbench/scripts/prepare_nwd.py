"""Build the editable web derivative from a project's indexed NWD geometry and source tree."""
import argparse
from collections import defaultdict
import gzip
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import struct
import sys
import tempfile
import zlib

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from platform_models import array, read_header


def saved_views(file):
    # Project NWDs use a lichunk container with a compressed section directory at the tail.
    with file.open('rb') as stream:
        stream.seek(max(0,file.stat().st_size-8192))
        tail = stream.read()
        header = tail.rfind(b'#LcUStream-', 0, tail.rfind(b'#LcUStream-'))
        start = tail.index(b'\x78\x9c', header)
        directory = zlib.decompress(tail[start:])
        key = b'LcOpSavedViewsElement'
        if key not in directory:
            return []
        end = directory.index(key) + len(key)
        location = None
        for shift in range(16):
            if directory[end+shift:end+shift+4] != struct.pack('<I', 1):
                continue
            for skip in (4, 8):
                offset, size = struct.unpack_from('<QQ', directory, end+shift+skip)
                if 0 < offset < file.stat().st_size and 0 < size <= file.stat().st_size-offset:
                    location = offset, size
                    break
            if location:
                break
        if not location:
            raise ValueError('无法定位保存视图段')
        stream.seek(location[0])
        raw = zlib.decompress(stream.read(location[1]))
    views = []
    for pos in range(0, len(raw)-150, 4):
        size, = struct.unpack_from('<I', raw, pos)
        if not 0 < size <= 2048:
            continue
        end = pos + 4 + (size+3)//4*4
        if raw[end:end+4] != bytes(4) or raw[end+20:end+24] != bytes(4):
            continue
        if raw[end+24:end+28] not in (b'\x77\x03\0\0', b'\x7f\x03\0\0'):
            continue
        try:
            name = raw[pos+4:pos+4+size].decode()
        except UnicodeDecodeError:
            continue
        if not name.isprintable():
            continue
        camera_start = (end+39)//8*8
        a = struct.unpack_from('<11d', raw, camera_start)
        if all(math.isfinite(v) and abs(v)<1e7 for v in a) and abs(math.hypot(*a[3:7])-1)<1e-6 and .01<a[8]<math.pi:
            views.append(dict(name=name.strip(), xyz=a[:3], rotation=a[3:7], fov=math.degrees(a[8])))
    return views


def write_mesh(folder, rows, overview=False):
    buffers = []
    metadata = []
    for mode, alpha in sorted({(r[0],r[4][3]) for r in rows},reverse=True):
        group = [r for r in rows if r[0] == mode and r[4][3] == alpha]
        if not group:
            continue
        xyz = np.concatenate([r[2] for r in group])
        low = xyz.min(axis=0)
        scale = np.maximum(xyz.max(axis=0)-low, .00001)
        packed = np.rint((xyz-low)/scale*65535).astype('<u2')
        starts = np.cumsum([0]+[len(r[2]) for r in group[:-1]])
        index = np.concatenate([r[3]+np.uint32(s) for r,s in zip(group,starts)]).astype('<u4')
        colors = np.concatenate([np.broadcast_to(r[4][:3], (len(r[2]),3)) for r in group]).astype('uint8')
        ends = np.cumsum([len(r[3]) for r in group], dtype='<u4')
        ranges = np.column_stack((ends,[r[1] for r in group])).astype('<u4')
        metadata.append([mode,len(xyz),len(index),len(group),low.tolist(),scale.tolist(),int(alpha)/255,overview,not overview])
        arrays = [packed if overview else xyz.astype('<f4',copy=False),colors,index,ranges]
        if overview:
            arrays.append(np.array([r[5] for r in group],dtype='<u4'))
        for a in arrays:
            buf = a.tobytes()
            buffers.extend([buf,bytes(-len(buf)%4)])
    header = json.dumps(metadata,separators=(',',':')).encode()
    raw = struct.pack('<I',len(header))+header+bytes(-len(header)%4)+b''.join(buffers)
    key = hashlib.sha256(raw).hexdigest()
    (folder/(key+'.gz')).write_bytes(gzip.compress(raw, compresslevel=2, mtime=0))
    return key


def prepare(model, hierarchy, nwd, parts=None, name=None, glb=None):
    parts = parts or model/'parts'
    files = [glb] if glb else sorted(parts.glob('*.glb'))
    if not files:
        raise ValueError('需要包含源节点编号的 GLB 几何分块')
    with nwd.open('rb') as stream:
        digest = hashlib.file_digest(stream,'sha256').hexdigest()
    info_file = model/'info.json'
    info = json.loads(info_file.read_bytes()) if info_file.is_file() else dict(digest=digest, source=nwd.name, name=name or nwd.stem)
    if info['digest']!=digest:
        raise ValueError('NWD 与已入库几何的版本不同')
    if glb:
        from import_geometry import normalize
        doc, offset = read_header(glb)
        h = normalize(doc, nwd)
    else:
        h = json.loads(hierarchy.read_bytes())
        if h['source']!=info['source'] or h['schema']!='offshore-native-hierarchy-v1':
            raise ValueError('源模型树不匹配')
    views = []
    if nwd.suffix.lower()=='.nwd':
        try:
            views = saved_views(nwd)
        except (ValueError, OSError, zlib.error, struct.error):
            pass
    parents = h['parent']
    n = len(parents)
    end = list(range(n))
    next_start = {}
    for i in range(n-1,0,-1):
        p = parents[i]
        if not 0<=p<i or (end[p]>p and end[i]+1!=next_start[p]):
            raise ValueError('模型树节点顺序不连续')
        end[p] = max(end[p],end[i])
        next_start[p] = i
    boxes = np.full((n,2,3),np.inf)
    boxes[:,1,:] = -np.inf
    dest = model/'editor'
    dest.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=dest) as tmp:
        tmp = Path(tmp)
        db = sqlite3.connect(tmp/'spool.sqlite')
        db.execute('CREATE TABLE pieces(cell TEXT, mode INT, node INT, xyz BLOB, ix BLOB, color BLOB, score REAL)')
        db.execute('PRAGMA synchronous=OFF')
        totals = defaultdict(int)
        for file in files:
            if not glb:
                doc,offset = read_header(file)
            with file.open('rb') as f:
                f.seek(offset)
                raw = f.read()
            batch = []
            batch_bytes = 0
            for obj in doc['nodes']:
                if 'mesh' not in obj:
                    continue
                node = obj['extras']['sourceNode']
                mat = np.array(obj['matrix'],dtype='f').reshape(4,4)
                for prim in doc['meshes'][obj['mesh']]['primitives']:
                    mode = prim.get('mode',4)
                    points = (array(doc,raw,prim['attributes']['POSITION'])@mat[:3,:3]+mat[3,:3]).astype('<f4',copy=False)
                    ix = array(doc,raw,prim['indices']).ravel().astype('<u4') if 'indices' in prim else np.arange(len(points),dtype='<u4')
                    if mode in (2,3) and len(ix)>=2:
                        if mode==2:
                            ix=np.append(ix,ix[0])
                        ix=np.column_stack((ix[:-1],ix[1:])).ravel()
                        mode=1
                    elif mode in (5,6) and len(ix)>=3:
                        if mode==5:
                            faces=np.column_stack((ix[:-2],ix[1:-1],ix[2:]))
                            faces[1::2]=faces[1::2][:,[1,0,2]]
                        else:
                            faces=np.column_stack((np.full(len(ix)-2,ix[0]),ix[1:-1],ix[2:]))
                        mode,ix=4,faces.ravel()
                    if mode not in (0,1,4) or not len(ix) or len(ix)%{4:3,1:2,0:1}[mode] or ix.max()>=len(points) or not np.isfinite(points).all():
                        raise ValueError('模型图元、索引或坐标无效；仅支持点、线条与表面')
                    if mode==4 and np.linalg.det(mat[:3,:3])<0:
                        ix = ix.reshape(-1,3)[:,[0,2,1]].reshape(-1)
                    lo,hi = points.min(axis=0),points.max(axis=0)
                    boxes[node,0] = np.minimum(boxes[node,0],lo)
                    boxes[node,1] = np.maximum(boxes[node,1],hi)
                    cell = ','.join(map(str,np.floor((lo+hi)/24).astype(int)))
                    rgb = doc['materials'][prim.get('material',0)]['pbrMetallicRoughness']['baseColorFactor']
                    color = np.rint(np.array(rgb)*255).astype('uint8').tobytes()
                    score = float(np.linalg.norm(hi-lo))/max(8,len(ix))**.3
                    batch.append((cell,mode,node,points.tobytes(),ix.tobytes(),color,score))
                    batch_bytes += points.nbytes+ix.nbytes
                    if batch_bytes >= 16*1024**2:
                        db.executemany('INSERT INTO pieces VALUES(?,?,?,?,?,?,?)',batch)
                        batch.clear()
                        batch_bytes=0
                    totals[cell] += len(ix)
            db.executemany('INSERT INTO pieces VALUES(?,?,?,?,?,?,?)',batch)
            db.commit()
        db.execute('CREATE INDEX by_cell ON pieces(cell,score DESC)')
        if not totals:
            raise ValueError('模型没有可显示的几何')
        # Preserve all full-detail geometry. The first frame has a bounded triangle budget.
        tiles = []
        membership = []
        overview = []
        total = sum(totals.values())
        for tile_id,(key,count) in enumerate(totals.items()):
            budget = max(90,int(count/total*1350000))
            used = 0
            a = np.full(3,np.inf)
            b = -a
            pages,rows = [],[]
            size = 0
            def finish_page():
                pages.append(write_mesh(tmp,rows))
                ids = sorted({r[1] for r in rows})
                membership.append(np.array([len(ids),*ids],dtype='<u4').tobytes())
            for mode,node,xyz,idx,color,_ in db.execute('SELECT mode,node,xyz,ix,color,score FROM pieces WHERE cell=? ORDER BY score DESC',(key,)):
                points = np.frombuffer(xyz,'<f4').reshape(-1,3)
                ix = np.frombuffer(idx,'<u4')
                row = (mode,node,points,ix,np.frombuffer(color,'u1'))
                if size>=270000:
                    finish_page()
                    rows,size = [],0
                rows.append(row)
                size+=len(ix)
                a=np.minimum(a,points.min(axis=0))
                b=np.maximum(b,points.max(axis=0))
                if used==0 or used+len(ix)<=budget:
                    overview.append((*row,tile_id))
                    used+=len(ix)
            if rows:
                finish_page()
            tiles.append(dict(min=a.tolist(),max=b.tolist(),pages=pages,count=count))
        db.close()
        for i in range(n-1,0,-1):
            p = parents[i]
            boxes[p,0] = np.minimum(boxes[p,0],boxes[i,0])
            boxes[p,1] = np.maximum(boxes[p,1],boxes[i,1])
        tree = [[p,end[i],h['name'][i] or h['className'][i] or info['source'],
                 h['className'][i],np.round(boxes[i].ravel(),3).tolist() if np.isfinite(boxes[i]).all() else None] for i,p in enumerate(parents)]
        tree_bytes=json.dumps(tree,ensure_ascii=False,separators=(',',':')).encode()
        tree_key=hashlib.sha256(tree_bytes).hexdigest()
        (tmp/(tree_key+'.gz')).write_bytes(gzip.compress(tree_bytes,compresslevel=3,mtime=0))
        members=b''.join(membership)
        members_key=hashlib.sha256(members).hexdigest()
        (tmp/(members_key+'.gz')).write_bytes(gzip.compress(members,compresslevel=3,mtime=0))
        manifest=dict(members=members_key,digest=info['digest'],name=name or info['name'],sourceFile=nwd.name,tree=tree_key,nodes=n,views=views,tiles=tiles,overview=write_mesh(tmp,overview,True))
        from review_edges import build as build_outlines
        manifest['outlines'] = build_outlines(tmp, manifest)
        for f in tmp.glob('*.gz'):
            f.replace(dest/f.name)
        index=tmp/'index.json'
        index.write_text(json.dumps(manifest,ensure_ascii=False,separators=(',',':')))
        index.replace(dest/index.name)
        print(info['name'],n,'节点',len(views),'预设',len(tiles),'空间分块',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for arg in ('model','hierarchy','nwd'):
        parser.add_argument(arg,type=Path)
    parser.add_argument('--parts',type=Path,help='带源节点编号的 GLB 分块目录，默认读取模型目录下的 parts')
    parser.add_argument('--name',help='在网页中显示的模型名称')
    args=parser.parse_args()
    import re
    if not re.fullmatch('[a-z0-9][a-z0-9_-]{0,63}',args.model.name):
        parser.error('模型目录名须为小写字母、数字、下划线或连字符')
    prepare(args.model,args.hierarchy,args.nwd,args.parts,args.name)
