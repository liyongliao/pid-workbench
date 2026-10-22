from pathlib import Path
import urllib.request,json,subprocess,sys,os,time,socket,webbrowser
BASE=Path(__file__).resolve().parent
for port in range(8765,8775):
 url=f'http://127.0.0.1:{port}'
 try:
  with urllib.request.urlopen(url+'/api/health',timeout=.5) as response:
   if json.load(response).get('name')=='cad-workbench':
    webbrowser.open(url);print('已打开图纸工作台：'+url);sys.exit(0)
 except Exception:pass
 with socket.socket() as sock:
  if sock.connect_ex(('127.0.0.1',port))==0:continue
 env=dict(os.environ,PID_PORT=str(port))
 with (BASE/'data/server.log').open('a') as log:
  launch_options={'creationflags':subprocess.DETACHED_PROCESS|subprocess.CREATE_NEW_PROCESS_GROUP} if os.name=='nt' else {'start_new_session':True}
  subprocess.Popen([sys.executable,'-u',str(BASE/'server.py')],cwd=BASE,stdout=log,stderr=log,env=env,stdin=subprocess.DEVNULL,**launch_options)
 for _ in range(50):
  try:
   with urllib.request.urlopen(url+'/api/health',timeout=.3) as r:ready=json.load(r).get('name')=='cad-workbench'
   if ready:
    webbrowser.open(url);print('图纸工作台已启动：'+url);sys.exit(0)
  except Exception:time.sleep(.2)
 print('启动失败，请查看 cad-workbench/data/server.log');sys.exit(1)
print('8765—8774 端口均被占用。');sys.exit(1)
