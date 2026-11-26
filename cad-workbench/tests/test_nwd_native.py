"""A small, generated NWD fixture exercises the upload converter without a CAD runtime."""
import gzip
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
import zlib

import support
from model_imports import convert, receive, status


def ints(*values):
    return struct.pack('<'+'i'*len(values),*values)


def align(data, width):
    return data+bytes(-len(data)%width)


def string(value):
    raw=value.encode()
    return ints(len(raw))+align(raw,4)


def model_bytes():
    header=b'#LcUStream-V1.1 binary double release C lichunk-008\n'
    # Three point instances from one logical leaf, translated by its geometry offset.
    geometry=ints(100,96,101,60,3,9)+struct.pack('<9f',0,0,0, 1,0,0, 0,1,0)+ints(0,0,0,1)
    geometry=align(geometry,8)
    chunk=zlib.compress(geometry)
    toc=zlib.compress(align(ints(1,1,len(chunk),len(geometry)),8))
    hierarchy=align(ints(0,100,1,101,22)+string('测点')+ints(0,0,0,0,1),8)
    fragments=align(ints(1,100,13),8)+struct.pack('<d',1)+ints(3,0,0,1,0,0,101,93)
    fragments=align(fragments+struct.pack('<6f',0,0,0,1,1,0),8)
    fragments=align(fragments+struct.pack('<3dfii',3,4,5,1,0,1),8)
    segments=[('Geometry',ints(65536)+chunk+toc,4,len(toc)),
              ('LogicalHierarchy',zlib.compress(hierarchy),0,0),
              ('Fragments',zlib.compress(fragments),0,0)]
    data=header
    table=ints(-1,len(segments))
    for name,stored,prefix,tail in segments:
        table=align(table+string('cache\\LcOpNwd'+name)+ints(1),8)
        table+=struct.pack('<qqii',len(data),len(stored),prefix,tail)
        data+=stored
    return data+b'#LcUStream-V1.1 binary double release utf8 navisworks:448 lizlib\n'+bytes(7)+zlib.compress(table)+header


class NativeImportTests(unittest.TestCase):
    def test_nwd_to_review_and_world_coordinates_without_cli(self):
        import io
        raw=model_bytes()
        with tempfile.TemporaryDirectory() as tmp, patch('model_imports.converter',side_effect=AssertionError('unexpected external converter')):
            root=Path(tmp)
            job=receive(root,io.BytesIO(raw),len(raw),'测量站.nwd')['id']
            convert(root,job)
            result=status(root,job)
            self.assertEqual((result['rendered'],result['records'],result['nodes']),(1,1,2))
            editor=root/'models'/result['model']/'editor'
            index=json.loads((editor/'index.json').read_bytes())
            tree=json.loads(gzip.decompress((editor/(index['tree']+'.gz')).read_bytes()))
            self.assertEqual(tree[1][2],'测点')
            self.assertEqual(tree[1][4],[3,5,-5,4,5,-4])
            self.assertEqual(len(index['tiles']),1)
