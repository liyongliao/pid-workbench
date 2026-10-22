"""Start this library and open its browser, without reusing a different project."""
from pathlib import Path
import urllib.request,json,subprocess,sys,os,time,socket,webbrowser
from workspace import initialize,data_root,instance_id
BASE=Path(__file__).resolve().parent

def main():
 root=initialize(data_root());ports=[int(os.environ['PID_PORT'])] if os.environ.get('PID_PORT') else range(8765,8775)
 def ready(url):
  try:
   with urllib.request.urlopen(url+'/api/health',timeout=.5) as r:health=json.load(r)
   return health.get('name')=='cad-workbench' and health.get('instance')==instance_id(root)
  except (OSError,ValueError):return False
 def show(url):
  if not os.environ.get('PID_NO_BROWSER'):webbrowser.open(url)
  print('图纸工作台：'+url,flush=True)
 for port in ports:
  if not 1<=port<=65535:raise SystemExit('PID_PORT 必须在 1—65535 之间')
  url=f'http://127.0.0.1:{port}'
  if ready(url):show(url);return
  with socket.socket() as sock:
   if sock.connect_ex(('127.0.0.1',port))==0:continue
  env=dict(os.environ,PID_PORT=str(port),PID_DATA_ROOT=str(root),PYTHONUTF8='1')
  with (root/'data/server.log').open('a',encoding='utf-8') as log:
   options={'creationflags':subprocess.DETACHED_PROCESS|subprocess.CREATE_NEW_PROCESS_GROUP} if os.name=='nt' else {'start_new_session':True}
   child=subprocess.Popen([sys.executable,'-X','utf8','-u',str(BASE/'server.py')],cwd=BASE,stdout=log,stderr=log,env=env,stdin=subprocess.DEVNULL,**options)
  for _ in range(50):
   if ready(url):show(url);return
   if child.poll() is not None:break
   time.sleep(.2)
  raise SystemExit('启动失败，请查看 '+str(root/'data/server.log'))
 raise SystemExit('请求的端口已被其他服务占用，请设置 PID_PORT 为可用端口。')
if __name__=='__main__':main()
