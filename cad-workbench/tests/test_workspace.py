import unittest,json,os,tempfile
from pathlib import Path
from unittest.mock import patch
from support import Service,BASE
from workspace import initialize,instance_id

class WorkspaceTests(unittest.TestCase):
 def test_initialize_never_overwrites(self):
  with tempfile.TemporaryDirectory() as td:
   root=initialize(Path(td));file=root/'data/catalog.json';file.write_text('[{"id":"synthetic"}]',encoding='utf-8');initialize(root)
   self.assertEqual(json.loads(file.read_text(encoding='utf-8')),[{'id':'synthetic'}])
   self.assertTrue((root/'output').is_dir());self.assertEqual(json.loads((root/'data/logic.json').read_text(encoding='utf-8'))['causes'],[])
 def test_distinct_libraries_have_distinct_id(self):self.assertNotEqual(instance_id(BASE),instance_id(BASE/'other'))
 def test_disabled_converter_overrides_environment(self):
  from cad_runtime import converter_status
  with patch.dict(os.environ,{'PID_DISABLE_DWG_CONVERTER':'1','PID_DWG_CONVERTER':str(Path(__file__).resolve())}):self.assertFalse(converter_status()['available'])

class FreshInstallHTTPTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.service=Service();cls.cookie=cls.service.setup()
 @classmethod
 def tearDownClass(cls):cls.service.close()
 def get(self,path):return self.service.request(path,cookie=self.cookie)
 def test_empty_library_endpoints(self):
  for path in ('/api/catalog','/api/logic','/api/quality','/api/missing-references','/api/search?q=pressure','/api/related?tag=PT-9999','/api/admin/state'):
   with self.subTest(path=path):self.assertEqual(self.get(path)[0],200)
  self.assertEqual(self.get('/api/catalog')[1],[])
 def test_static_assets_come_from_source_not_data_directory(self):
  self.assertFalse((self.service.root/'static').exists())
  for path in ('/','/login','/style.css','/app.js','/admin.js','/account.js','/system.js','/login.css','/login.js'):
   with self.subTest(path=path):self.assertEqual(self.get(path)[0],200)
 def test_diagnostics_preflight(self):
  s=self.get('/api/admin/system')[1];self.assertFalse(s['canImport']);self.assertEqual(s['drawingCount'],0);self.assertTrue(s['writable']);self.assertIn('version',s)
 def test_upload_rejected_before_retaining_bytes_without_engine(self):
  path='/api/admin/upload?filename=synthetic.dwg&platform=CEPD&code=CEPD-PR-9999&title=test'
  status,body,_=self.service.request(path,'POST',b'AC1032abcdef',self.cookie,{'X-Management-Token':self.service.state(self.cookie)['token']},raw=True)
  self.assertEqual(status,400);self.assertIn('DWG',body['error']);self.assertEqual(list((self.service.root/'uploads').iterdir()),[])
 def test_download_and_traversal_errors(self):
  for path in ('/download/','/download/x/original','/../data/access-control.json','/output/../data/access-control.json','/output/%2e%2e/data/access-control.json'):
   with self.subTest(path=path):self.assertEqual(self.get(path)[0],404)
 def test_empty_catalog_has_onboarding(self):
  js=self.get('/app.js')[1].decode();self.assertIn('renderEmptyLibrary()',js);self.assertIn('上传第一张图纸',js)

class VectorRenderingTests(unittest.TestCase):
 def test_clean_install_renders_original_cad_handle(self):
  import sys,ezdxf
  from xml.etree import ElementTree as ET
  sys.path.insert(0,str(BASE/'scripts'))
  from build import render
  doc=ezdxf.new();entity=doc.modelspace().add_line((1,1),(9,7))
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);render(doc,root,'original',[0,0,10,10])
   svg=ET.parse(root/'original.svg')
   self.assertTrue(any(n.get('data-handle')==entity.dxf.handle for n in svg.iter()))
