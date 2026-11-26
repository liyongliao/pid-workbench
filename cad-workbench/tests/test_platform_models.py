from contextlib import closing
import json
import sqlite3
import struct
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
import support
from platform_models import component,geometry,matches,nearby,index_space
from vault import initialize_empty


class PlatformModelTests(unittest.TestCase):
    def test_branch_identity_keeps_valve_and_instrument_separate(self):
        branch=' of BRANCH /4"-FW-60003-A/B1'
        self.assertEqual(component('ELBOW 3'+branch,'f1'),('管线','4"-FW-60003-A','4"-FW-60003-A'))
        self.assertEqual(component('VALVE 3'+branch,'f2'),('阀门','VALVE 3'+branch,''))
        self.assertEqual(component('INSTRUMENT 1'+branch,'f3')[0],'仪表')
        self.assertEqual(component('BOX 8 of EQUIPMENT /WHPL-P-001/BASE','a'),('设备','WHPL-P-001','WHPL-P-001'))

    def test_same_tag_requires_platform_and_unique_candidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault=initialize_empty(Path(tmp)/'vault')
            root=vault.root/'models'/'l';root.mkdir(parents=True)
            (root/'info.json').write_text(json.dumps(dict(id='l',platform='WHPL',digest='test')))
            with closing(sqlite3.connect(root/'objects.sqlite')) as db, db:
                db.execute('CREATE TABLE objects(id INTEGER,tag TEXT)')
                db.executemany('INSERT INTO objects VALUES(?,?)',[(5,'P-1'),(6,'PI-2'),(7,'PI-2')])
            base=vault.view(vault.head());folder=base/'output'/'d0';folder.mkdir()
            (folder/'drawing.json').write_text(json.dumps(dict(items=[dict(handle='A',tag='P-1'),dict(handle='B',tag='PI-2')])))
            manager=SimpleNamespace(base=base,catmap={'d0':{'platform':'CEPD'}})
            self.assertEqual(matches(vault,manager,root,'d0'),{})
            manager.catmap['d0']['platform']='WHPL'
            self.assertEqual(matches(vault,manager,root,'d0'),{'A':5})

    def test_pick_ranges_and_local_geometry_use_source_transform(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'parts').mkdir();file='part-1.glb'
            d=dict(nodes=[dict(mesh=0,matrix=[1,0,0,0,0,1,0,0,0,0,1,0,10,20,30,1])],
                   meshes=[dict(primitives=[dict(attributes={'POSITION':0},indices=1)])],
                   accessors=[dict(type='VEC3',componentType=5126,count=3,bufferView=0,min=[0,0,0],max=[1,1,0]),dict(type='SCALAR',componentType=5125,count=3,bufferView=1)],
                   bufferViews=[{},dict(byteOffset=36)])
            header=json.dumps(d).encode();header+=b' '*(-len(header)%4)
            raw=struct.pack('<9f3I',0,0,0,1,0,0,0,1,0,0,1,2)
            (root/'parts'/file).write_bytes(struct.pack('<4sIII4s',b'glTF',2,28+len(header)+len(raw),len(header),b'JSON')+header+struct.pack('<I4s',len(raw),b'BIN\0')+raw)
            with closing(sqlite3.connect(root/'objects.sqlite')) as db, db:
                db.executescript('CREATE TABLE fragments(part TEXT,node INTEGER,object INTEGER,tri INTEGER);CREATE TABLE objects(id INTEGER,kind TEXT);')
                db.execute('INSERT INTO fragments VALUES(?,0,7,1)',(file,));db.execute("INSERT INTO objects VALUES(7,'阀门')")
            index_space(root)
            n,more,data,_=nearby(root,[10,20,30],0)
            self.assertEqual((n,more),(1,False))
            length=struct.unpack_from('<I',data)[0]
            self.assertEqual(json.loads(data[4:4+length])['ranges'],[[3,7]])
            self.assertEqual(struct.unpack_from('<3f',data,4+length),(10,20,30))
            self.assertEqual(nearby(root,[0,0,0],0)[0],0)
