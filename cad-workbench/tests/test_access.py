import unittest,tempfile,secrets,time
from pathlib import Path
from support import Service
from access_control import AccessControl,AccessError,COOKIE

class AccessUnitTests(unittest.TestCase):
 def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.auth=AccessControl(Path(self.tmp.name));self.admin=secrets.token_urlsafe(18);self.viewer=secrets.token_urlsafe(18)
 def tearDown(self):self.tmp.cleanup()
 def setup(self):return self.auth.setup({'adminPassword':self.admin,'viewerPassword':self.viewer},'127.0.0.1')
 def test_remote_setup_forbidden(self):
  with self.assertRaises(AccessError) as e:self.auth.setup({},'192.0.2.10')
  self.assertEqual(e.exception.status,403)
 def test_distinct_and_minimum_passwords(self):
  for admin,viewer in [('short',self.viewer),(self.admin,self.admin)]:
   with self.assertRaises(AccessError):self.auth.setup({'adminPassword':admin,'viewerPassword':viewer},'127.0.0.1')
 def test_passwords_persist_as_hashes(self):
  self.setup();text=self.auth.path.read_text(encoding='utf-8');self.assertNotIn(self.admin,text);self.assertNotIn(self.viewer,text)
  restored=AccessControl(Path(self.tmp.name));token=restored.login({'role':'viewer','password':self.viewer},'127.0.0.1');self.assertEqual(restored.session(COOKIE+'='+token)['role'],'viewer')
 def test_throttle(self):
  self.setup()
  for _ in range(5):
   with self.assertRaises(AccessError):self.auth.login({'role':'admin','password':'wrong'},'127.0.0.1')
  with self.assertRaises(AccessError) as e:self.auth.login({'role':'admin','password':self.admin},'127.0.0.1')
  self.assertEqual(e.exception.status,429)
 def test_session_expires(self):
  token=self.setup();s=self.auth.session(COOKIE+'='+token);self.auth.sessions[s['key']]['expires']=time.time()-1;self.assertIsNone(self.auth.session(COOKIE+'='+token))
 def test_malformed_cookie_rejected(self):
  for cookie in ('[invalid]=x','pid_session=bad','garbage'):self.assertIsNone(self.auth.session(cookie))
 def test_corrupt_configuration_fails_closed(self):
  self.setup();self.auth.path.write_text('{}',encoding='utf-8')
  with self.assertRaises((RuntimeError,KeyError,ValueError)):AccessControl(Path(self.tmp.name))

class AccessHTTPTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.s=Service();cls.s.setup()
 @classmethod
 def tearDownClass(cls):cls.s.close()
 def setUp(self):self.admin=self.s.login();self.viewer=self.s.login('viewer')
 def test_anonymous_protected_resources(self):
  self.assertEqual(self.s.request('/')[0],302)
  for path in ('/api/catalog','/api/drawing/synthetic','/api/logic','/api/admin/state','/api/admin/system','/api/%61dmin/state','/api/quality','/api/missing-references','/output/synthetic/chinese.svg','/download/synthetic/original','/reports/missing-references.json'):
   with self.subTest(path=path):self.assertEqual(self.s.request(path)[0],401)
 def test_viewer_can_read_not_manage(self):
  self.assertEqual(self.s.request('/api/catalog',cookie=self.viewer)[0],200)
  for path in ('/api/admin/state','/api/admin/system','/api/admin/attributes?drawing=x'):
   with self.subTest(path=path):self.assertEqual(self.s.request(path,cookie=self.viewer)[0],403)
 def test_stolen_management_token_does_not_grant_role(self):
  headers={'X-Management-Token':self.s.state(self.admin)['token']}
  for path in ('/api/admin/link','/api/admin/upload','/api/admin/attributes','/api/admin/attributes/publish','/api/admin/attributes/discard'):
   with self.subTest(path=path):self.assertEqual(self.s.request(path,'POST',{},self.viewer,headers)[0],403)
 def test_cross_origin_and_csrf(self):
  self.assertEqual(self.s.request('/api/auth/logout','POST',{},self.admin)[0],403)
  self.assertEqual(self.s.request('/api/auth/login','POST',{},headers={'Origin':'http://untrusted.invalid'})[0],403)
  self.assertEqual(self.s.request('/api/auth/setup','POST',{},headers={'Host':'untrusted.invalid'})[0],403)
 def test_password_change_revokes_all_sessions(self):
  csrf={'X-CSRF-Token':self.s.request('/api/auth/session',cookie=self.admin)[1]['csrf']};password=secrets.token_urlsafe(18)
  self.assertEqual(self.s.request('/api/auth/passwords','POST',{'currentPassword':self.s.admin_password,'viewerPassword':password},self.admin,csrf)[0],200)
  self.s.viewer_password=password
  for cookie in (self.admin,self.viewer):self.assertEqual(self.s.request('/api/catalog',cookie=cookie)[0],401)
 def test_logout_invalidates_cookie(self):
  csrf={'X-CSRF-Token':self.s.request('/api/auth/session',cookie=self.viewer)[1]['csrf']}
  self.assertEqual(self.s.request('/api/auth/logout','POST',{},self.viewer,csrf)[0],200);self.assertEqual(self.s.request('/api/catalog',cookie=self.viewer)[0],401)
 def test_cookie_and_no_cache(self):
  status,_,headers=self.s.request('/api/auth/login','POST',{'role':'viewer','password':self.s.viewer_password})
  self.assertEqual(status,200)
  for value in ('HttpOnly','SameSite=Strict','Max-Age=28800'):self.assertIn(value,headers['Set-Cookie'])
  self.assertEqual(self.s.request('/api/auth/session',cookie=self.viewer)[2]['Cache-Control'],'no-store')

class ContainerOriginTests(unittest.TestCase):
 def test_only_declared_browser_origin_may_login_through_port_mapping(self):
  import os
  from unittest.mock import patch
  origin='http://nas.example.test:19000'
  with patch.dict(os.environ,{'PID_PUBLIC_ORIGINS':origin}):
   service=Service()
  try:
   service.setup()
   login={'role':'viewer','password':service.viewer_password}
   headers={'Host':'nas.example.test:19000','Origin':origin}
   self.assertEqual(service.request('/api/auth/login','POST',login,headers=headers)[0],200)
   self.assertEqual(service.request('/api/auth/login','POST',login,headers=dict(headers,Origin='http://other.example.test'))[0],403)
   self.assertEqual(service.request('/api/auth/login','POST',login,headers=dict(headers,Host='other.example.test'))[0],403)
  finally:service.close()
