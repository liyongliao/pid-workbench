from pathlib import Path
import sys,os,json,tempfile,subprocess,time,socket,http.client,secrets
BASE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE))

class Service:
 def __init__(self,converter=False):
  self.temp=tempfile.TemporaryDirectory(prefix='pid-test-');self.root=Path(self.temp.name)/'library';self.root.mkdir();self.admin_password=secrets.token_urlsafe(20);self.viewer_password=secrets.token_urlsafe(20)
  with socket.socket() as s:s.bind(('127.0.0.1',0));self.port=s.getsockname()[1]
  env=dict(os.environ,PID_DATA_ROOT=str(self.root),PID_PORT=str(self.port),PID_HOST='127.0.0.1',PYTHONUTF8='1')
  if not converter:env.pop('PID_DWG_CONVERTER',None);env['PID_DISABLE_DWG_CONVERTER']='1'
  self.log=(self.root/'test-server.log').open('w',encoding='utf-8')
  self.process=subprocess.Popen([sys.executable,'-X','utf8',str(BASE/'server.py')],env=env,stdout=self.log,stderr=self.log)
  for _ in range(100):
   if self.process.poll() is not None:raise RuntimeError((self.root/'test-server.log').read_text(encoding='utf-8'))
   try:
    if self.request('/api/health')[0]==200:return
   except OSError:pass
   time.sleep(.1)
  self.close();raise RuntimeError('Server did not start')
 def request(self,path,method='GET',data=None,cookie=None,headers=None,raw=False):
  h={'Origin':f'http://127.0.0.1:{self.port}'}
  if cookie:h['Cookie']=cookie
  if data is not None:h['Content-Type']='application/octet-stream' if raw else 'application/json'
  h.update(headers or {});conn=http.client.HTTPConnection('127.0.0.1',self.port,timeout=30)
  conn.request(method,path,data if raw else json.dumps(data).encode() if data is not None else None,h)
  r=conn.getresponse();status=r.status;body=r.read();headers=dict(r.getheaders());conn.close()
  try:body=json.loads(body)
  except (ValueError,UnicodeDecodeError):pass
  return status,body,headers
 def setup(self):
  code,data,h=self.request('/api/auth/setup','POST',{'adminPassword':self.admin_password,'viewerPassword':self.viewer_password});assert code==200,(code,data);return h['Set-Cookie'].split(';')[0]
 def login(self,role='admin'):
  code,data,h=self.request('/api/auth/login','POST',{'role':role,'password':self.admin_password if role=='admin' else self.viewer_password});assert code==200,(code,data);return h['Set-Cookie'].split(';')[0]
 def state(self,cookie):return self.request('/api/admin/state',cookie=cookie)[1]
 def post_admin(self,path,data,cookie):return self.request(path,'POST',data,cookie,{'X-Management-Token':self.state(cookie)['token']})
 def close(self):
  self.process.terminate();self.process.wait(timeout=15);self.log.close();self.temp.cleanup()
