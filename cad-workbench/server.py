from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from pathlib import Path
import gzip,hashlib,json,urllib.parse,mimetypes,re,os,threading
from rapidfuzz import fuzz
from management import Manager
from workspace import CODE_ROOT,VERSION,data_root,initialize,instance_id
from access_control import AccessControl,AccessError,local_client,cookie_header
BASE=initialize(data_root());ROOT=BASE.parent
access=AccessControl(BASE)
manager=Manager(BASE)
logic=json.loads((BASE/'data/logic.json').read_text(encoding='utf-8')) if (BASE/'data/logic.json').exists() else {}
def norm(s):return re.sub(r'[^A-Z0-9\u4e00-\u9fff]','',s.upper())
def shorttag(s):return re.sub(r'^(CEPD?|WHP[A-Z]|WP[A-Z]|PRP)-','',s.upper())
class Handler(BaseHTTPRequestHandler):
 protocol_version='HTTP/1.1'
 def setup(self):
  super().setup();self.connection.settimeout(30)
 def log_message(self,*a):pass
 def send(self,data,code=200,ctype='application/json; charset=utf-8',filename=None,headers=None):
  if getattr(self,'defer_send',False):
   self.pending_response=(data,code,ctype,filename,headers);return
  if not isinstance(data,bytes):data=json.dumps(data,ensure_ascii=False).encode()
  if headers and 'ETag' in headers and len(data)>1024 and re.search(r'(?:^|,)\s*gzip\s*(?:,|$)',self.headers.get('Accept-Encoding',''),re.I):
   data=gzip.compress(data,compresslevel=3,mtime=0);headers['Content-Encoding']='gzip'
  self.send_response(code);self.send_header('Content-Type',ctype);self.send_header('Content-Length',str(len(data)));self.send_header('Cache-Control',(headers or {}).get('Cache-Control','no-store'));self.send_header('X-Frame-Options','DENY');self.send_header('Referrer-Policy','same-origin');self.send_header('X-Content-Type-Options','nosniff')
  if self.command=='POST' and code>=400:
   self.close_connection=True;self.send_header('Connection','close')
  if filename:self.send_header('Content-Disposition',"attachment; filename*=UTF-8''"+urllib.parse.quote(filename))
  for key,value in (headers or {}).items():
   if key!='Cache-Control':self.send_header(key,value)
  self.end_headers();self.wfile.write(data)
 def cached(self,revision,content,ctype):
  # Authorization is checked in do_GET before evaluating any validator.
  etag='W/"'+hashlib.sha256(str(revision).encode()).hexdigest()+'"'
  headers={'Cache-Control':'private, no-cache, must-revalidate','ETag':etag,'Vary':'Cookie, Accept-Encoding'}
  if etag in [s.strip() for s in self.headers.get('If-None-Match','').split(',')]:
   self.send_response(304)
   for name,value in headers.items():self.send_header(name,value)
   self.end_headers();return
  body=content()
  if not isinstance(body,bytes):body=json.dumps(body,ensure_ascii=False,separators=(',',':')).encode()
  self.send(body,ctype=ctype,headers=headers)
 def do_GET(self):
  try:
   if not self.authorize():return
   self.defer_send=True;self.pending_response=None
   try:
    with manager.lock:self.get()
   finally:self.defer_send=False
   if self.pending_response:self.send(*self.pending_response)
  except (BrokenPipeError,ConnectionResetError):pass
  except Exception as ex:self.send({'error':str(ex)},500)
 def do_POST(self):
  try:
   host=self.headers.get('Host','');origin=self.headers.get('Origin')
   local_address=self.connection.getsockname()[0]
   allowed_hosts={f'{address}:{self.server.server_port}' for address in ('127.0.0.1','localhost',local_address)}
   # Containers see a bridge address; trust only explicitly configured external origins.
   public={entry.strip() for entry in os.environ.get('PID_PUBLIC_ORIGINS','').split(',') if entry.strip()}
   origins={'http://'+value for value in allowed_hosts}|public
   if not any(urllib.parse.urlsplit(o).netloc==host for o in origins) or (origin and (origin not in origins or urllib.parse.urlsplit(origin).netloc!=host)):
    self.send({'error':'管理请求校验失败，请刷新页面后重试'},403);return
   u=urllib.parse.urlparse(self.path)
   if u.path.startswith('/api/auth/'):
    self.auth_post(u.path);return
   if not self.authorize(admin=True):return
   if self.headers.get('X-Management-Token')!=manager.token:
    self.send({'error':'管理请求校验失败，请刷新页面后重试'},403);return
   length=int(self.headers.get('Content-Length','0'))
   if u.path=='/api/admin/upload':
    self.connection.settimeout(120)
    meta={k:v[0] for k,v in urllib.parse.parse_qs(u.query).items()};meta['_actor']='管理员 · '+self.client_address[0];self.send(manager.upload(self.rfile,length,meta),202);return
   if length<2 or length>1024*1024:raise ValueError('请求内容大小无效')
   data=json.loads(self.rfile.read(length))
   if not isinstance(data,dict):raise ValueError('请求必须为对象')
   data['_actor']='管理员 · '+self.client_address[0]
   if u.path=='/api/admin/link':self.send(manager.edit_link(data));return
   if u.path=='/api/admin/attributes':
    from attribute_drafts import save
    self.send(save(manager,data));return
   if u.path=='/api/admin/attributes/publish':
    from attribute_drafts import submit
    self.send(submit(manager,data),202);return
   if u.path=='/api/admin/attributes/discard':
    from attribute_drafts import discard
    self.send(discard(manager,data));return
   self.send({'error':'未知管理操作'},404)
  except (ValueError,TypeError,KeyError) as ex:self.send({'error':str(ex)},400)
  except (BrokenPipeError,ConnectionResetError):pass
  except Exception as ex:self.send({'error':str(ex)},500)
 def authorize(self,admin=False):
  p=urllib.parse.unquote(urllib.parse.urlparse(self.path).path)
  self.session=access.session(self.headers.get('Cookie'))
  if not admin and p in ('/login','/login.css','/login.js','/api/auth/session','/api/health'):return True
  if not self.session:
   if self.command=='GET' and p in ('/','/index.html'):
    self.send(b'',302,headers={'Location':'/login?next='+urllib.parse.quote(self.path,safe='')})
   else:self.send({'error':'请先登录','loginRequired':True},401)
   return False
  if (admin or p.startswith('/api/admin/')) and self.session['role']!='admin':
   self.send({'error':'此操作仅限管理员'},403);return False
  return True
 def auth_post(self,path):
  try:
   if self.headers.get('Content-Type','').split(';')[0]!='application/json':raise AccessError('登录请求必须使用 JSON')
   size=int(self.headers.get('Content-Length','0'))
   if not 2<=size<=4096:raise AccessError('请求内容大小无效')
   data=json.loads(self.rfile.read(size))
   if not isinstance(data,dict):raise AccessError('请求必须为对象')
   ip=self.client_address[0];session=access.session(self.headers.get('Cookie'))
   if path=='/api/auth/setup':
    token=access.setup(data,ip);self.send({'role':'admin'},headers={'Set-Cookie':cookie_header(token)});return
   if path=='/api/auth/login':
    token=access.login(data,ip,session);self.send({'role':data['role']},headers={'Set-Cookie':cookie_header(token)});return
   if not session:raise AccessError('请先登录',401)
   if self.headers.get('X-CSRF-Token')!=session['csrf']:raise AccessError('请求校验失败，请刷新后重试',403)
   if path=='/api/auth/logout':
    access.logout(session);self.send({'message':'已退出登录'},headers={'Set-Cookie':cookie_header()});return
   if path=='/api/auth/passwords':
    if session['role']!='admin':raise AccessError('此操作仅限管理员',403)
    result=access.change(data,session,ip);self.send(result,headers={'Set-Cookie':cookie_header()});return
   raise AccessError('未知账户操作',404)
  except AccessError as ex:self.send({'error':str(ex)},ex.status)
 def get(self):
  catalog=manager.catalog;manifest=manager.manifest;catmap=manager.catmap
  u=urllib.parse.urlparse(self.path);p=urllib.parse.unquote(u.path);q=urllib.parse.parse_qs(u.query)
  if p=='/api/auth/session':
   self.send({'configured':bool(access.config),'canSetup':not access.config and local_client(self.client_address[0]),'authenticated':bool(self.session),**({'role':self.session['role'],'csrf':self.session['csrf']} if self.session else {})});return
  if p=='/login':
   self.send((CODE_ROOT/'static/login.html').read_bytes(),ctype='text/html; charset=utf-8');return
  if p=='/api/admin/system':
   from diagnostics import snapshot
   self.send(snapshot(manager));return
  if p=='/api/library-version':self.send({'version':manager.library_version});return
  if p=='/api/admin/change-log':
   from change_log import entries
   try:offset=max(0,int(q.get('offset',['0'])[0]))
   except ValueError:offset=0
   self.send(entries(manager,q.get('q',[''])[0],offset));return
  if p=='/api/admin/state':self.send(manager.state());return
  if p=='/api/admin/attributes':
   from attribute_editor import block_info
   try:self.send(block_info(manager,q.get('drawing',[''])[0],q.get('handle',[''])[0]))
   except ValueError as ex:self.send({'error':str(ex)},400)
   return
  if p=='/api/missing-references':self.send(manager.report);return
  if p.startswith('/reports/'):
   allowed={'缺失关联图号清单.html','缺失关联图号清单.txt','missing-references.json'};name=p.removeprefix('/reports/')
   if name not in allowed:self.send({'error':'无此清单'},404);return
   # Downloaded reports must point back to the serving computer, not the reader's localhost.
   origin=f'http://{self.connection.getsockname()[0]}:{self.server.server_port}'
   origin=next((o.strip() for o in os.environ.get('PID_PUBLIC_ORIGINS','').split(',') if urllib.parse.urlsplit(o.strip()).netloc==self.headers.get('Host')),origin)
   report=(BASE/'reports'/name).read_bytes().replace(b'http://127.0.0.1:8765',origin.encode())
   self.send(report,ctype=('text/html; charset=utf-8' if name.endswith('.html') else 'text/plain; charset=utf-8'),filename=name if q.get('download') else None);return
  if p=='/api/health':self.send({'name':'cad-workbench','drawings':len(catalog),'version':VERSION,'instance':instance_id(BASE)});return
  if p=='/api/catalog':
   self.cached(('catalog',manager.library_version),lambda:[{k:v for k,v in r.items() if k!='search'} for r in catalog],'application/json; charset=utf-8');return
  if p=='/api/search':
   term=q.get('q',[''])[0].strip();platform=q.get('platform',[''])[0];needle=norm(term);out=[];eq=[]
   for r in catalog:
    if platform and r['platform']!=platform:continue
    score=100 if needle and needle in norm(r.get('search','')) else fuzz.partial_ratio(needle,norm(r['title']+' '+r['code'])) if needle else 100
    titlehit=needle and needle in norm(r['title']+' '+r['code'])
    first=len(eq)
    if score>=65:out.append({'id':r['id'],'score':score+ (30 if titlehit else 0),'title':r['title'],'code':r['code'],'platform':r['platform'],'entityCount':r.get('entityCount',0)})
    if needle:
     for e in r.get('equipment',[]):
      if needle in norm(e['tag']+' '+e['name']+' '+e.get('search','')):eq.append(dict(e,drawingId=r['id'],drawingTitle=r['title'],platform=r['platform']))
    if len(eq)>first:
     rank=200+max(30 if norm(e['tag'])==needle or norm(shorttag(e['tag']))==needle else 10 if needle in norm(e['tag']) else 0 for e in eq[first:])
     if score>=65:out[-1]['score']=max(rank,out[-1]['score'])
     else:out.append(dict(id=r['id'],score=rank,title=r['title'],code=r['code'],platform=r['platform'],entityCount=r.get('entityCount',0)))
   eq.sort(key=lambda e:(0 if norm(e['tag'])==needle else 1 if norm(shorttag(e['tag']))==needle else 2 if needle in norm(e['tag']) else 3,e['tag'],e['drawingId']))
   self.send({'drawings':sorted(out,key=lambda x:-x['score'])[:100],'equipment':eq[:100],'total':len(out),'equipmentTotal':len(eq)});return
  if p.startswith('/api/drawing/'):
   id=p.split('/')[-1]
   if id not in manifest:self.send({'error':'未找到图纸'},404);return
   path=BASE/'output'/id/'drawing.json';st=path.stat()
   def drawing():
    data=json.loads(path.read_bytes());data['references']=catmap[id]['references'];return data
   self.cached((id,st.st_mtime_ns,st.st_ctime_ns,st.st_size,manager.ref_versions[id]),drawing,'application/json; charset=utf-8');return
  if p=='/api/logic':self.send(logic);return
  if p=='/api/quality':
   quality=json.loads((BASE/'data/quality.json').read_text(encoding='utf-8'));quality['missingReferences']=[dict(r,drawing=d['id']) for d in catalog for r in d['references'] if not r.get('targets') and not r.get('selfReference')]
   quality['review']=[dict(t,drawing=d['id'],code=d['code']) for d in catalog for t in manager.drawing(d['id'])['translations'] if t['review']]
   self.send(quality);return
  if p=='/api/related':
   tag=q.get('tag',[''])[0];platform=q.get('platform',[''])[0];target=norm(shorttag(tag));matches=[]
   for r in catalog:
    if r['platform']!=platform:continue
    for e in r.get('equipment',[]):
     if norm(shorttag(e['tag']))==target:matches.append(dict(e,drawingId=r['id'],drawingTitle=r['title'],code=r['code']))
   causes=[c for c in logic.get('causes',[]) if c['platform']==platform and (norm(shorttag(c['tag']))==target or any(norm(shorttag(t))==target for t in re.findall(r'(?:[A-Z]+-)?[A-Z]{1,6}-?\d+[A-Z]?',c['original'])))]
   effects=[e for e in logic.get('effects',[]) if norm(shorttag(e['tag']))==target] if platform=='CEPD' else []
   self.send({'drawings':matches,'causes':causes,'effects':effects});return
  if p.startswith('/download/'):
   parts=p.split('/')
   if len(parts)!=4:self.send({'error':'下载地址无效'},404);return
   _,_,id,kind=parts
   if id not in manifest:self.send({'error':'未找到图纸'},404);return
   name=manifest[id]['filename'];folder=BASE/'output'/id
   if kind=='original':f=(ROOT/manifest[id]['source']).resolve()
   if kind=='original':
    if not f.is_relative_to(ROOT):self.send({'error':'源文件路径无效'},404);return
   elif kind=='dwg':f=folder/'中文图纸.dwg';name=Path(name).stem+'-中文.dwg'
   elif kind=='dxf':f=folder/'中文图纸.dxf';name=Path(name).stem+'-中文.dxf'
   elif kind=='pdf':
    f=folder/'中文图纸.pdf';name=Path(name).stem+'-中文.pdf'
    if not f.exists() or f.stat().st_mtime < (folder/'chinese.svg').stat().st_mtime:
     import pymupdf
     s=pymupdf.open(stream=(folder/'chinese.svg').read_bytes(),filetype='svg');f.write_bytes(s.convert_to_pdf())
   elif kind=='ledger':f=folder/'drawing.json';name=Path(name).stem+'-图元与译文.json'
   else:self.send({'error':'未知格式'},404);return
   if not f.exists():self.send({'error':'该文件尚未生成'},404);return
   self.send(f.read_bytes(),ctype=mimetypes.guess_type(name)[0] or 'application/octet-stream',filename=name);return
  if p.startswith('/output/'):
   f=(BASE/p.lstrip('/')).resolve()
   if not f.is_relative_to(BASE/'output') or f.suffix!='.svg':self.send({'error':'无此文件'},404);return
  else:
   f=(CODE_ROOT/'static'/('index.html' if p=='/' else p.lstrip('/'))).resolve()
   if not f.is_relative_to(CODE_ROOT/'static'):self.send({'error':'无此页面'},404);return
  if not f.is_file():self.send({'error':'无此页面'},404);return
  if p.startswith('/output/'):
   st=f.stat();self.cached((p,st.st_mtime_ns,st.st_ctime_ns,st.st_size),f.read_bytes,'image/svg+xml');return
  self.send(f.read_bytes(),ctype=mimetypes.guess_type(f.name)[0] or 'application/octet-stream')
if __name__=='__main__':
 port=int(os.environ.get('PID_PORT','8765'));host=os.environ.get('PID_HOST','0.0.0.0');print(f'PID 图纸工作台：监听 {host}:{port}，本机访问 http://127.0.0.1:{port}',flush=True);ThreadingHTTPServer((host,port),Handler).serve_forever()
