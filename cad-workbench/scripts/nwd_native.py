"""Offline reader for supported lichunk-008 engineering models.

Decode only recognized layouts. Compare record boundaries, topology and source
node references before a model can enter the catalog. Container and strip layout
reference: https://ioextend.github.io/NwcIO/format-notes.html
"""
import json
import math
from pathlib import Path
import struct
import zlib

import numpy as np


class UnsupportedNwd(ValueError):
    pass


def check(ok, message):
    if not ok:
        raise UnsupportedNwd(message)


class Reader:
    def __init__(self, data):
        self.data = memoryview(data)
        self.pos = 0

    def take(self, size):
        end = self.pos + size
        check(size >= 0 and end <= len(self.data), 'NWD 记录长度越界')
        value = self.data[self.pos:end]
        self.pos = end
        return value

    def ints(self, count):
        return np.frombuffer(self.take(count*4), '<i4')

    def i(self):
        return struct.unpack('<i', self.take(4))[0]

    def count(self, limit=4000000):
        value = self.i()
        check(0 <= value <= limit, 'NWD 数组超出支持范围')
        return value

    def align(self, width):
        check(not any(self.take(-self.pos % width)), 'NWD 记录对齐方式未知')

    def string(self):
        n = self.i()
        if n == -1:
            return ''
        text = bytes(self.take(n)).decode('utf-8')
        self.align(4)
        return text

    def floats(self, n, double=False):
        if double:
            self.align(8)
        a = np.frombuffer(self.take(n*(8 if double else 4)), '<f8' if double else '<f4')
        check(np.isfinite(a).all(), 'NWD 坐标或材质包含无效数值')
        return a

    def finish(self):
        self.align(8)
        check(self.pos == len(self.data), 'NWD 记录尾部未识别')


def inflate(data, limit):
    z = zlib.decompressobj()
    result = z.decompress(data, limit+1)
    check(z.eof and not z.unused_data and len(result)<=limit, 'NWD 压缩段无效或超过内置读取容量')
    return result


def directory(f):
    header=f.readline(128)
    check(header.startswith(b'#LcUStream-') and header.rstrip().endswith(b'lichunk-008'), '内置读取器尚不支持此 NWD 版本')
    end=f.seek(0,2)
    f.seek(max(0,end-1024*1024))
    tail=f.read()
    # Section 1 contains a named directory followed by the final header.
    at=tail.rfind(b'#LcUStream-',0,tail.rfind(header))
    check(at>=0, '找不到 NWD 段目录')
    line=tail.find(b'\n',at,at+128)
    check(line>at and b'lizlib' in tail[at:line],'NWD 目录编码未知')
    pos=line+1
    while pos<len(tail) and tail[pos]==0:
        pos+=1
    encoded=tail[pos:tail.rfind(header)]
    z=zlib.decompressobj()
    payload=z.decompress(encoded,1024*1024)
    check(z.eof, 'NWD 目录压缩格式未知')
    r=Reader(payload)
    check(r.i()==-1, 'NWD 目录标识未知')
    entries={}
    for _ in range(r.count(65536)):
        name=r.string().rsplit('\\',1)[-1]
        flags=r.i()
        r.align(8)
        offset,length=struct.unpack('<qq',r.take(16))
        prefix,toc=r.ints(2)
        check(0<=offset<=end and 0<=length<=end-offset, 'NWD 段位置无效')
        entries[name]=(offset,length,flags,int(prefix),int(toc))
    return entries


def segment(f, entry):
    offset,length,flags,prefix,toc=entry
    check(flags==1 and not prefix and not toc and length<=256*1024**2,'不支持的 NWD 数据段')
    f.seek(offset)
    return inflate(f.read(length),256*1024**2)


def geometry_records(f, entry):
    start,length,flags,prefix,toc=entry
    check(flags==1 and prefix==4 and 0<toc<length-4,'不支持的 NWD 几何目录')
    f.seek(start+length-toc)
    r=Reader(inflate(f.read(toc),32*1024**2))
    count,chunks=r.count(),r.count(65536)
    sizes=r.ints(chunks)
    lengths=r.ints(count)
    check(np.all(sizes>0) and np.all(lengths>=0) and sum(map(int,sizes))==length-toc-4,'NWD 几何目录大小不一致')
    check(lengths.sum()<=384*1024**2,'模型超过内置解码容量')
    f.seek(start)
    check(struct.unpack('<I',f.read(4))[0]==65536,'NWD 几何分块大小未知')
    block=bytearray()
    for sz in sizes:
        block.extend(inflate(f.read(int(sz)),65536))
    check(len(block)==lengths.sum(),'NWD 几何分块缺失')
    buf=memoryview(block)
    offsets=np.cumsum(lengths,dtype=np.int64)
    return [buf[int(stop-size):int(stop)] for stop,size in zip(offsets,lengths)]


class Objects(Reader):
    def __init__(self,data,first):
        super().__init__(data)
        self.objects={}
        self.next_id=first

    def pointer(self, allowed):
        number=self.i()
        if number==0:
            return None
        if number==1:
            key=self.i()
            check(key in self.objects,'无效的 NWD 对象引用')
            kind,value=self.objects[key]
            check(kind in allowed,'NWD 对象引用类型不匹配')
            return value
        check(number==self.next_id,'NWD 对象编号不连续')
        self.next_id+=1
        kind=self.i()
        check(kind in allowed,f'尚未支持的 NWD 对象类型 {kind}')
        value=self.body(kind)
        self.objects[number]=(kind,value)
        return value


class Fragments(Objects):
    def body(self,kind):
        if kind==13:
            self.floats(1,True)
            primitives,_,_,node=map(int,self.ints(4))
            pose=self.pointer((14,15,16))
            color=self.pointer((55,))
            geo=self.pointer((93,))
            return node,primitives,pose,color,geo
        if kind in (14,15,16):
            t=self.floats(3,True)
            mat=np.eye(4)
            if kind!=14:
                x,y,z,w=self.floats(4,True)
                check(abs(x*x+y*y+z*z+w*w-1)<1e-4,'NWD 旋转参数无效')
                mat[:3,:3]=[[1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w)],
                             [2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)],
                             [2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)]]
            if kind==16:
                mat[:3,:3]*=self.floats(1,True)[0]
            mat[:3,3]=t
            return mat
        if kind==55:
            flags=self.i()
            rgba=self.pointer((54,))
            if flags&32:
                check(self.i()==0,'该材质使用外部资源')
            return rgba
        if kind==54:
            a=self.floats(14)
            return tuple(np.clip([*a[3:6],1-a[13]],0,1).tolist())
        box=self.floats(6)
        center=self.floats(3,True)
        self.floats(1)
        _,record=self.ints(2)
        return int(record),box,center

    def read(self):
        n=self.count()
        if struct.unpack_from('<i',self.data,self.pos)[0]==0:
            self.i()
        result=[self.pointer((13,)) for _ in range(n)]
        self.finish()
        return result


class Hierarchy(Objects):
    def body(self,kind):
        if kind in (22,32,53):
            if kind==32:self.string()
            name=self.string()
            identity=self.pointer((52,))
            self.ints(2)
            for _ in range(self.count()):
                self.pointer((31,39,40,41,52,86))
            children=[self.pointer((22,32,53)) for _ in range(self.count())] if kind!=22 else []
            if kind==32:
                check(self.i()==2,'NWD 分区尾部版本未知')
                self.i();self.floats(3,True);self.i();self.string();self.ints(3)
                self.floats(6,True);self.i();self.string();self.i();self.string()
                self.floats(7,True);self.ints(2)
            return name or (identity or ('',''))[0], (identity or ('',''))[0], children
        if kind==52:
            return self.string(),self.string()
        if kind==31:
            self.string()
            self.pointer((52,))
            self.i()
            self.floats(14,True)
        elif kind in (39,40,41):
            self.string();self.pointer((52,));self.i()
            self.floats({39:12,40:3,41:7}[kind],True)
        elif kind==86:
            self.string()
            self.pointer((52,))
            self.i()
            for _ in range(self.count()):
                self.pointer((52,))
                typ=self.i()
                if typ in (1,5,6,7,10,11):
                    self.floats(1,True)
                elif typ in (2,3):
                    self.i()
                elif typ in (4,9):
                    self.string()
                elif typ==8:
                    self.pointer((52,))
                else:
                    check(typ==0,'不支持的 NWD 属性类型')

    def read(self,source):
        self.ints(self.count())
        check(self.i()==100,'NWD 层级根节点无效')
        roots=[self.pointer((22,32,53)) for _ in range(self.count())]
        # Inventor assemblies can append complete top-level instances before the terminator.
        while len(self.data)-self.pos>8:
            roots.append(self.pointer((22,32,53)))
        check(self.i()==1,'NWD 层级尾部无效')
        self.finish()
        names,classes,parents=[source.stem],['模型'],[-1]
        stack=[(0,n) for n in reversed(roots)]
        while stack:
            parent,(name,cls,kids)=stack.pop()
            idx=len(names)
            check(idx<4000000,'NWD 模型层级过大')
            names.append(name);classes.append(cls);parents.append(parent)
            stack.extend((idx,c) for c in reversed(kids))
        return dict(schema='offshore-native-hierarchy-v1',source=source.name,parent=parents,name=names,className=classes)


def tokens(r,count,fresh,normals=False):
    check(0<=count<=4000000 and 0<=fresh<=count,'NWD 顶点映射数量无效')
    out=[]
    cursor=0
    while len(out)<count:
        b=r.take(1)[0]
        if b<64:
            out.extend(range(cursor,cursor+b+1))
            cursor+=b+1
        elif 128<=b<192:
            check(bool(out),'NWD 顶点映射引用无效')
            out.extend([out[-1]]*(b-127))
        elif normals and 208<=b<=213:
            out.append(-1)
        elif b==240:
            literal=int.from_bytes(r.take(2),'big')
            check(literal<cursor,'无效的 NWD 顶点引用')
            out.append(literal)
        else:
            if 64<=b<128:
                back=b-64
            elif 224<=b<=239:
                back=((b&15)<<8)|r.take(1)[0]
            else:
                raise UnsupportedNwd('尚未支持的 NWD 顶点编码')
            check(0<back<=len(out),'NWD 顶点映射距离无效')
            out.append(out[-back])
    check(len(out)==count and cursor==fresh,'NWD 顶点映射长度不符')
    r.align(4)
    return np.asarray(out,dtype='<u4' if not normals else '<i4')


def analytic(r,kind,triangles):
    flags=r.i()
    center=r.floats(3)
    end=r.floats(3) if kind==105 else None
    u,v=r.floats(3),r.floats(3)
    radius=r.floats(1)[0]
    if kind==104:
        check(r.floats(1)[0]==0,'圆盘记录尾部未知')
    r.finish()
    if radius==0:
        return None
    check(radius>0 and flags==(3 if kind==104 else 0x30003),'不支持的 NWD 圆面记录')
    check(abs(np.dot(u,v))<1e-4 and abs(np.dot(u,u)-1)<1e-4 and abs(np.dot(v,v)-1)<1e-4,'NWD 圆面基向量无效')
    bits=triangles if kind==104 else triangles//2
    check(3<=bits<=65536,'圆面离散精度未知')
    theta=np.arange(bits)*math.tau/bits
    ring=radius*(np.cos(theta)[:,None]*u+np.sin(theta)[:,None]*v)
    idx=np.arange(bits,dtype='<u4')
    nxt=(idx+1)%bits
    if kind==104:
        points=np.vstack((center+ring,center))
        faces=np.column_stack((np.full(bits,bits),idx,nxt))
    else:
        points=np.vstack((center+ring,end+ring))
        faces=np.vstack((np.column_stack((idx,nxt,idx+bits)),np.column_stack((nxt,nxt+bits,idx+bits))))
        if np.dot(np.cross(u,v),end-center)<0:
            faces=faces[:,[0,2,1]]
    return 4,points.astype('<f4'),faces.astype('<u4').ravel()


def geometry(data,triangles):
    r=Reader(data)
    check(r.i()==100,'无效的 NWD 图元标识')
    kind=r.i()
    if kind in (104,105):
        return analytic(r,kind,triangles)
    check(kind in (94,95,96),f'尚未支持的 NWD 几何类型 {kind}')
    check(tuple(r.ints(2))==(101,60),'尚未支持的 NWD 位置编码')
    count,coords=r.count(),r.count(12000000)
    check(coords%3==0 and count>0,'NWD 顶点数量无效')
    xyz=r.floats(coords).reshape(-1,3)
    mapping=tokens(r,count,len(xyz)) if count!=len(xyz) else None
    if r.i():
        check(r.i()==61,'NWD 纹理坐标类型未知')
        n=r.i()
        if n<0:
            check(n==-count,'NWD UV 数量无效')
            r.floats(4)
            widths=r.i()
            m=r.count()
            width=(widths&255)+((widths>>8)&255)
            r.take(((m*width+31)//32)*4)
        else:
            check(n==count,'NWD UV 数量无效')
            fc=r.count()
            r.floats(fc)
            m=fc//2
        if m!=count:tokens(r,count,m)
    if r.i():
        check(r.i()==100 and r.i()==-count,'NWD 法线编码未知')
        palette=r.count()
        r.take(((palette*24+31)//32)*4)
        if palette!=count:tokens(r,count,palette,True)
    if r.i():
        check(tuple(r.ints(3))==(58,5634,-count),'NWD 顶点色编码未知')
        palette=r.count()
        r.take(4*palette)
        if palette!=count:tokens(r,count,palette)
    if kind==96:
        check(r.i()==1,'NWD 点集编码未知')
        r.finish()
        return 0,xyz,mapping if mapping is not None else np.arange(count,dtype='<u4')
    strips=r.count()
    width=r.count(32)
    check(r.i()==strips and strips>0 and width>0,'NWD 图元条带格式未知')
    packed=np.frombuffer(r.take(4*((strips*width+31)//32)),'<u4').astype('>u4')
    bits=np.unpackbits(packed.view('u1'))[:strips*width].reshape(strips,width)
    lengths=bits @ (1<<np.arange(width-1,-1,-1,dtype='int64'))
    size=r.count() if kind==94 else 0
    corners=tokens(r,size,count) if size else np.arange(count,dtype='<u4')
    r.finish()
    check(lengths.sum()==len(corners),'NWD 条带与角点数量不同')
    if mapping is not None:
        corners=mapping[corners]
    faces=[]
    start=0
    for length in lengths:
        strip=corners[start:start+length]
        start+=length
        if kind==94:
            f=np.column_stack((strip[:-2],strip[1:-1],strip[2:]))
            f[1::2]=f[1::2][:,[1,0,2]]
        else:
            f=np.column_stack((strip[:-1],strip[1:]))
        faces.append(f.ravel())
    return 4 if kind==94 else 1,xyz,np.concatenate(faces)


class MeshChunk:
    """Keep source-node IDs on every instance; share its mesh within the chunk."""
    def __init__(self):
        self.nodes=[]
        self.meshes=[]
        self.materials={}
        self.mesh_ids={}
        self.attributes={}
        self.binary=bytearray()
        self.accessors=[]
        self.views=[]

    def attribute(self, array, kind, component):
        data=array.tobytes()
        self.views.append(dict(buffer=0,byteOffset=len(self.binary),byteLength=len(data)))
        self.binary.extend(data)
        self.accessors.append(dict(bufferView=len(self.views)-1,type=kind,count=len(array),componentType=component))
        return len(self.accessors)-1

    def add(self, key, mesh, world, node, color):
        if key not in self.attributes:
            mode,points,indices=mesh
            self.attributes[key]=mode,self.attribute(points,'VEC3',5126),self.attribute(indices,'SCALAR',5125)
        mode,pos,ix=self.attributes[key]
        material=self.materials.setdefault(color,len(self.materials))
        shape=key,material
        if shape not in self.mesh_ids:
            self.mesh_ids[shape]=len(self.meshes)
            self.meshes.append({'primitives':[dict(mode=mode,attributes={'POSITION':pos},indices=ix,material=material)]})
        self.nodes.append(dict(mesh=self.mesh_ids[shape],matrix=world.T.ravel().tolist(),extras={'sourceNode':node}))

    def write(self, path):
        doc=dict(asset={'version':'2.0'},nodes=self.nodes,meshes=self.meshes,accessors=self.accessors,
                 materials=[dict(pbrMetallicRoughness=dict(baseColorFactor=c)) for c in self.materials],
                 bufferViews=self.views,buffers=[dict(byteLength=len(self.binary))])
        meta=json.dumps(doc,separators=(',',':')).encode()
        meta+=b' '*(-len(meta)%4)
        with path.open('wb') as f:
            f.write(struct.pack('<4sIIII',b'glTF',2,28+len(meta)+len(self.binary),len(meta),0x4e4f534a))
            f.write(meta)
            f.write(struct.pack('<I4s',len(self.binary),b'BIN\0'))
            f.write(self.binary)


def extract(source, work):
    parts=work/'parts'
    parts.mkdir()
    with source.open('rb') as f:
        entries=directory(f)
        def entry(suffix):
            name='LcOpNwd'+suffix
            check(name in entries,'源文件缺少 '+name)
            return entries[name]
        h=Hierarchy(segment(f,entry('LogicalHierarchy')),101).read(source)
        fragments=Fragments(segment(f,entry('Fragments')),100).read()
        records=geometry_records(f,entry('Geometry'))
    world_axes=np.array([[1,0,0,0],[0,0,1,0],[0,-1,0,0],[0,0,0,1]])
    chunk=MeshChunk()
    cache={}
    page=rendered=empty=0
    parents=set(h['parent'][1:])
    for node,count,pose,color,ref in fragments:
        check(0<=node<len(h['parent']) and node not in parents,'几何未对应到源构件树叶节点')
        if ref is None:
            check(count==0,'构件缺少几何引用')
            empty+=1
            continue
        record,box,center=ref
        if record==0 and count==0:
            empty+=1
            continue
        check(1<=record<=len(records),'NWD 几何编号越界')
        raw=records[record-1]
        if not raw and count==0:
            empty+=1
            continue
        key=(record,count)
        if key not in cache:
            mesh=geometry(raw,count)
            if mesh is not None and struct.unpack_from('<i',raw,4)[0] in (94,95,96):
                points=mesh[1]
                extents=np.r_[points.min(0),points.max(0)]
                check(np.allclose(extents,box,rtol=1e-5,atol=1e-5),'图元顶点范围与源构件记录不符')
            cache[key]=mesh
        mesh=cache[key]
        if mesh is None:
            empty+=1
            continue
        mode,points,indices=mesh
        check(len(indices)==count*{4:3,1:2,0:1}[mode],'源片段与图元数量不一致')
        if pose is None:
            pose=np.eye(4)
            pose[:3,3]=center
        chunk.add(key,mesh,world_axes@pose,node,color or (.7,.7,.7,1.))
        rendered+=1
        if len(chunk.nodes)>=3000 or len(chunk.binary)>=16*1024**2:
            chunk.write(parts/f'{page:06}.glb')
            page+=1
            chunk=MeshChunk()
            cache.clear()
    check(rendered>0,'模型内没有可显示的构件')
    if chunk.nodes:
        chunk.write(parts/f'{page:06}.glb')
    hierarchy=work/'hierarchy.json'
    hierarchy.write_text(json.dumps(h,ensure_ascii=False),encoding='utf-8')
    return parts,hierarchy,dict(fragments=len(fragments),rendered=rendered,empty=empty,records=len(records),nodes=len(h['parent']))
