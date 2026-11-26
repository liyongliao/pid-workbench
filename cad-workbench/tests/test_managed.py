import contextlib
import http.client
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from support import BASE,Service
from vault import initialize_empty
import test_cad_pipeline


class Services(Service):
    def __init__(self,converter=False):
        self.temp=tempfile.TemporaryDirectory(prefix='vault-test-')
        self.vault=initialize_empty(Path(self.temp.name)/'vault')
        self.root=self.vault.view('baseline')
        self.log=(Path(self.temp.name)/'services.log').open('w')
        self.admin_password=secrets.token_urlsafe(15)
        self.viewer_password=secrets.token_urlsafe(15)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0))
            self.port=sock.getsockname()[1]
        self.env=dict(os.environ,PID_VAULT=str(self.vault.root),PID_HOST='127.0.0.1',PID_PORT=str(self.port))
        if not converter:self.env['PID_DISABLE_DWG_CONVERTER']='1'
        self.process=self.start('production.py')
        self.worker=self.start('worker.py')
        for _ in range(900):
            if self.process.poll() is not None or self.worker.poll() is not None:
                raise RuntimeError((Path(self.temp.name)/'services.log').read_text())
            try:
                if self.request('/api/health')[0]==200:
                    with contextlib.closing(self.vault.connect()) as db, db:
                        if db.execute('SELECT 1 FROM heartbeat').fetchone():return
            except OSError:pass
            time.sleep(.1)
        self.close()
        raise RuntimeError("services failed to start")

    def start(self,script):
        return subprocess.Popen([sys.executable,str(BASE/script)],env=self.env,stdout=self.log,stderr=self.log)
    def setup(self):
        result,body,h=self.request('/api/auth/setup','POST',dict(login='组长',adminPassword=self.admin_password,viewerPassword=self.viewer_password))
        assert result==200,body
        return h['Set-Cookie'].split(';')[0]
    def request(self,path,method='GET',data=None,cookie=None,headers=None,raw=False):
        if path.startswith('/api/admin/upload?') and 'team=' not in path:path+='&team=%E5%B7%A5%E8%89%BA'
        return super().request(path,method,data,cookie,headers,raw)
    def close(self):
        self.worker.terminate();self.worker.wait(timeout=15)
        super().close()


@unittest.skipIf(sys.platform=='win32','Linux/Mac managed service')
class ManagedTests(unittest.TestCase):
    def test_editor_scope(self):
        s=Services()
        try:
            admin=s.setup();pwd=secrets.token_urlsafe(14)
            payload=dict(login='amy',name='机械编辑',teams=['机械'],password=pwd,enabled=True)
            self.assertEqual(s.post_admin('/api/admin/accounts',payload,admin)[0],200)
            status,result,h=s.request('/api/auth/login','POST',dict(role='editor',login='amy',password=pwd))
            self.assertEqual(status,200,result)
            cookie=h['Set-Cookie'].split(';')[0]
            self.assertEqual(s.request('/api/admin/accounts',cookie=cookie)[0],403)
            self.assertEqual(s.request('/api/catalog',cookie=cookie)[0],200)
            self.assertEqual(s.post_admin('/api/admin/link',dict(drawing='outside'),cookie)[0],403)
            self.assertEqual(s.request('/api/admin/upload?team=other','POST',b'AC1032',cookie,{'X-Management-Token':s.state(cookie)['token']},True)[0],403)
            payload.update(enabled=False,password='')
            self.assertEqual(s.post_admin('/api/admin/accounts',payload,admin)[0],200)
            self.assertEqual(s.request('/api/catalog',cookie=cookie)[0],401)
        finally:s.close()

    @unittest.skipUnless(os.environ.get('PID_TEST_DWG')=='1','requires DWG engine')
    def test_worker_pipeline(self):
        with patch.object(test_cad_pipeline,'Service',Services):
            test_cad_pipeline.RealCADPipelineTests('test_import_edit_publish_and_link').test_import_edit_publish_and_link()
