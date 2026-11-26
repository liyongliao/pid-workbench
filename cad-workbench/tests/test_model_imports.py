import gzip
import io
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from model_imports import convert, receive, status


def assembly():
    data = struct.pack('<9f', 0,0,0, 1,0,0, 0,1,0)
    doc = dict(asset={'version':'2.0'},scene=0,scenes=[{'nodes':[0]}],
               nodes=[dict(name='模块',translation=[2,0,0],children=[1,2]),
                      dict(name='构件 A',mesh=0),dict(name='构件 B',mesh=0,translation=[0,5,0])],
               meshes=[{'primitives':[{'attributes':{'POSITION':0}}]}],
               accessors=[dict(bufferView=0,componentType=5126,count=3,type='VEC3')],
               bufferViews=[dict(buffer=0,byteLength=len(data))],buffers=[dict(byteLength=len(data))])
    header=json.dumps(doc).encode()
    header+=b' '*(-len(header)%4)
    return (struct.pack('<4sIIII',b'glTF',2,28+len(data)+len(header),len(header),0x4e4f534a)
            +header+struct.pack('<I4s',len(data),b'BIN\0')+data)


class ImportTests(unittest.TestCase):
    def test_instances_world_transforms_and_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            raw=assembly()
            job=receive(root,io.BytesIO(raw),len(raw),'新模型.glb')['id']
            convert(root,job)
            result=status(root,job)
            self.assertEqual(result['status'],'complete')
            model=root/'models'/result['model']
            index=json.loads((model/'editor/index.json').read_bytes())
            tree=json.loads(gzip.decompress((model/'editor'/(index['tree']+'.gz')).read_bytes()))
            self.assertEqual(tree[1][:3],[0,3,'模块'])
            self.assertEqual(tree[2][4],[2,0,0,3,1,0])
            self.assertEqual(tree[3][4],[2,5,0,3,6,0])
            self.assertEqual((model/'original/新模型.glb').read_bytes(),raw)
            convert(root,job)
            self.assertEqual(len(list((root/'models').iterdir())),1)

    def test_waiting_nwd_and_incomplete_upload(self):
        with tempfile.TemporaryDirectory() as tmp, patch('model_imports.converter',return_value=None):
            root=Path(tmp)
            data=b'#LcUStream-V1.1'
            job=receive(root,io.BytesIO(data),len(data),'新模型.nwd')['id']
            convert(root,job)
            self.assertEqual(status(root,job)['status'],'waiting')
            with self.assertRaises(ValueError):
                receive(root,io.BytesIO(data),len(data)+3,'断开.nwd')
            self.assertEqual(len(list((root/'model-imports/queue').iterdir())),1)
