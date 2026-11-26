from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from pathlib import Path
import gzip,hashlib,json,urllib.parse,mimetypes,re,os,threading
from rapidfuzz import fuzz
from management import Manager
from workspace import CODE_ROOT,VERSION,data_root,initialize,instance_id
from access_control import AccessControl,AccessError,local_client,cookie_header
BASE=initialize(data_root());ROOT=BASE.parent
access=AccessControl(BASE)
manager=Manager(BASE,recovery=not bool(os.environ.get('PID_VAULT')))
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
  if headers and 'ETag' in headers and 'Content-Encoding' not in headers and len(data)>1024 and re.search(r'(?:^|,)\s*gzip\s*(?:,|$)',self.headers.get('Accept-Encoding',''),re.I):
   data=gzip.compress(data,compresslevel=3,mtime=0);headers['Content-Encoding']='gzip'
  self.send_response(code);self.send_header('Content-Type',ctype);self.send_header('Content-Length',str(len(data)));self.send_header('Cache-Control',(headers or {}).get('Cache-Control','no-store'));self.send_header('X-Frame-Options','SAMEORIGIN' if self.path.split('?')[0]=='/nwd.html' else 'DENY');self.send_header('Referrer-Policy','same-origin');self.send_header('X-Content-Type-Options','nosniff')
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
   if not any(urllib.parse.urlsplit(o).netloc==host for o in origins) or (origin and origin not in origins):
    self.send({'error':'访问地址未通过校验。请使用管理员提供的工作台网址。'},403);return
   u=urllib.parse.urlparse(self.path)
   if u.path.startswith('/api/auth/'):
    self.auth_post(u.path);return
   if not self.authorize(admin=True):return
   if self.headers.get('X-Management-Token')!=manager.token:
    self.send({'error':'管理请求校验失败，请刷新页面后重试'},403);return
   length=int(self.headers.get('Content-Length','0'))
   if u.path=='/api/admin/nwd-import' and getattr(manager,'vault',None):
    if self.session.get('role')!='admin' or not self.session.get('login'):
     raise AccessError('仅管理员可导入模型',403)
    from model_imports import receive
    name=urllib.parse.parse_qs(u.query).get('name',[''])[0]
    self.send(receive(manager.vault.root,self.rfile,length,name),202);return
   if u.path=='/api/admin/upload':
    self.connection.settimeout(120)
    meta={k:v[0] for k,v in urllib.parse.parse_qs(u.query).items()};meta['_actor']='管理员 · '+self.client_address[0]
    if getattr(manager,'vault',None):
     from production import mutation
     mutation(self,u.path,meta)
    self.send(manager.upload(self.rfile,length,meta),202);return
   if length<2 or length>1024*1024:raise ValueError('请求内容大小无效')
   data=json.loads(self.rfile.read(length))
   if not isinstance(data,dict):raise ValueError('请求必须为对象')
   data['_actor']='管理员 · '+self.client_address[0]
   if u.path=='/api/admin/settings':
    if self.session['role']!='admin':raise AccessError('仅管理员可修改系统设置',403)
    from site_config import save
    root=manager.vault.root if getattr(manager,'vault',None) else BASE
    self.send(save(root,data,manager.catalog));return
   if getattr(manager,'vault',None):
    from production import mutation
    result=mutation(self,u.path,data)
    if result is not None:self.send(result);return
   if u.path=='/api/admin/link':self.send(manager.edit_link(data));return
   if u.path=='/api/admin/attributes':
    from attribute_drafts import save
    result=save(manager,data)
    self.audit_draft()
    self.send(result);return
   if u.path=='/api/admin/attributes/publish':
    from attribute_drafts import submit
    self.send(submit(manager,data),202);return
   if u.path=='/api/admin/attributes/discard':
    from attribute_drafts import discard
    result=discard(manager,data)
    self.audit_draft()
    self.send(result);return
   self.send({'error':'未知管理操作'},404)
  except AccessError as ex:self.send({'error':str(ex)},ex.status)
  except (ValueError,TypeError,KeyError) as ex:self.send({'error':str(ex)},400)
  except (BrokenPipeError,ConnectionResetError):pass
  except Exception as ex:self.send({'error':str(ex)},500)
 def audit_draft(self):
  if getattr(manager,"vault",None):
   with manager.vault.transaction() as db:manager.vault.sync_audit(db,manager)
 def authorize(self,admin=False):
  p=urllib.parse.unquote(urllib.parse.urlparse(self.path).path)
  self.session=access.session(self.headers.get('Cookie'))
  if not admin and p in ('/setup', '/setup.html', '/setup.js', '/setup.css', '/workspace-ui.css', '/product-header.js', '/api/site', '/login','/login.css','/login.js','/login-art.webp','/api/auth/session','/api/health'):return True
  if not self.session:
   if self.command=='GET' and p in ('/','/index.html','/nwd.html','/twin.html','/accounts.html','/settings.html'):
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
    if getattr(manager,'vault',None):
     from accounts import identity,session_identity
     login=identity(data.get('login'))
    token=access.setup(data,ip)
    from site_config import begin
    begin(access.path.parent.parent)
    if getattr(manager,'vault',None):
     token=session_identity(access,manager.vault,dict(role='admin',login=login,password=data['adminPassword']),ip,access.session(cookie_header(token)))
    self.send({'role':'admin'},headers={'Set-Cookie':cookie_header(token)});return
   if path=='/api/auth/login':
    if getattr(manager,'vault',None):
     from accounts import session_identity
     token=session_identity(access,manager.vault,data,ip,session)
    else:token=access.login(data,ip,session)
    self.send({'role':data['role']},headers={'Set-Cookie':cookie_header(token)});return
   if not session:raise AccessError('请先登录',401)
   if self.headers.get('X-CSRF-Token')!=session['csrf']:raise AccessError('请求校验失败，请刷新后重试',403)
   if path=='/api/auth/logout':
    access.logout(session);self.send({'message':'已退出登录'},headers={'Set-Cookie':cookie_header()});return
   if path=='/api/auth/passwords':
    if session['role']!='admin':raise AccessError('此操作仅限管理员',403)
    result=access.change(data,session,ip);self.send(result,headers={'Set-Cookie':cookie_header()});return
   raise AccessError('未知账户操作',404)
  except AccessError as ex:self.send({'error':str(ex)},ex.status)
 def feature_access(self):
  path=urllib.parse.unquote(urllib.parse.urlparse(self.path).path)
  if path not in ('/nwd.html','/twin.html','/api/logic') and not path.startswith(('/api/nwd/','/api/models/','/api/platforms/','/api/drawing/','/output/','/download/')):return True
  from site_config import read,capabilities
  settings=read(access.path.parent.parent)
  feature='models' if path in ('/nwd.html','/twin.html') or path.startswith('/api/nwd/') and path!='/api/nwd/models' else 'logic' if path=='/api/logic' else None
  if path.startswith(('/api/models/','/api/platforms/')) and settings['features']['models']=='off':feature='models'
  if path.startswith(('/api/drawing/','/output/','/download/')) and settings['features']['drawings']=='off':feature='drawings'
  if feature and not capabilities(manager)['enabled'][feature]:
   if path.endswith('.html'):self.send(b'',302,headers={'Location':'/?notice='+feature+'-unavailable'})
   else:self.send({'error':'相关资料尚未配置，或管理员已关闭此功能','featureUnavailable':True},404)
   return False
  return True
 def get(self):
  if not self.feature_access():return
  catalog=manager.catalog;manifest=manager.manifest;catmap=manager.catmap
  u=urllib.parse.urlparse(self.path);p=urllib.parse.unquote(u.path);q=urllib.parse.parse_qs(u.query)
  if p=='/api/auth/session':
   self.send({'configured':bool(access.config),'canSetup':not access.config,'setupTokenRequired':not local_client(self.client_address[0]),'authenticated':bool(self.session),**({'role':self.session['role'],'csrf':self.session['csrf']} if self.session else {})});return
  if p=='/api/site':
   from site_config import public
   self.send(public(access.path.parent.parent));return
  if p=='/api/capabilities':
   from site_config import capabilities
   self.send(capabilities(manager));return
  if p=='/api/admin/settings':
   if self.session['role']!='admin':self.send({'error':'仅管理员可查看系统设置'},403);return
   from site_config import read,capabilities
   self.send(dict(settings=read(access.path.parent.parent),capabilities=capabilities(manager)));return
  if p in ('/setup','/setup.html','/settings.html'):
   self.send((CODE_ROOT/'static/setup.html').read_bytes(),ctype='text/html; charset=utf-8');return
  from site_assets import asset
  site_file=asset(access.path.parent.parent,p,CODE_ROOT/'static')
  if site_file:
   self.cached((p,site_file.stat().st_mtime_ns,site_file.stat().st_size),site_file.read_bytes,'text/javascript');return
  if p=='/project-settings.js' and not (CODE_ROOT/'static/project-settings.js').is_file():
   self.send(b'globalThis.PidProject = {};',ctype='text/javascript');return
  if p=='/login':
   page=(CODE_ROOT/'static/login.html').read_bytes()
   if (CODE_ROOT/'static/login-art.webp').is_file():
    page=page.replace(b'class="intro"',b'class="intro has-art"',1)
   self.send(page,ctype='text/html; charset=utf-8');return
  if p=='/api/admin/system':
   from diagnostics import snapshot
   self.send(snapshot(manager));return
  if p=='/api/library-version':self.send({'version':manager.library_version});return
  if p=='/api/admin/change-log':
   from change_log import entries
   try:offset=max(0,int(q.get('offset',['0'])[0]))
   except ValueError:offset=0
   query=q.get('q',[''])[0]
   self.send(manager.vault.history(query,offset) if getattr(manager,'vault',None) else entries(manager,query,offset));return
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
   from site_config import read
   if read(access.path.parent.parent)['features']['drawings']=='off':self.send([]);return
   self.cached(('catalog',manager.library_version),lambda:[{k:v for k,v in r.items() if k!='search'} for r in catalog],'application/json; charset=utf-8');return
  if p=='/api/search':
   from site_config import read
   modes=read(access.path.parent.parent)['features']
   if modes['drawings']=='off':self.send({'drawings':[],'equipment':[],'total':0,'equipmentTotal':0});return
   results=manager.search_index.search(q.get('q',[''])[0][:256],q.get('platform',[''])[0],q.get('team',[''])[0])
   if modes['equipment']=='off':results.update(equipment=[],equipmentTotal=0)
   self.send(results);return
  if p.startswith('/api/drawing/'):
   id=p.split('/')[-1]
   if id not in manifest:self.send({'error':'未找到图纸'},404);return
   path=BASE/'output'/id/'drawing.json';st=path.stat()
   digest=manager.validators.get(id+'/drawing.json')
   vault=os.environ.get('PID_VAULT')
   centerlines=Path(vault)/'cache/cad-centerlines-v1'/(digest+'.json') if vault and digest else None
   has_centerlines=bool(centerlines and centerlines.is_file())
   sheet_model=None
   if getattr(manager,'vault',None):
    from sheet_ai import published
    sheet_model=published(manager.vault,id,digest)
   def drawing():
    data=json.loads(path.read_bytes())
    if has_centerlines and 'centerlines' not in data:data['centerlines']=json.loads(centerlines.read_bytes())
    data['sheetModel']=sheet_model;data['drawingDigest']=digest
    data['references']=catmap[id]['references'];data['team']=catmap[id]['team'];data['revision']=catmap[id]['revision'];data['assets']={mode:manager.validators.get(id+'/'+mode+'.svg') for mode in ('original','chinese')};return data
   self.cached((id,sheet_model and sheet_model["id"],has_centerlines,manager.validators.get(id+'/drawing.json',(st.st_mtime_ns,st.st_ctime_ns,st.st_size)),manager.ref_versions[id],catmap[id]['revision'],manager.validators.get(id+'/chinese.svg'),manager.validators.get(id+'/original.svg')),drawing,'application/json; charset=utf-8');return
  if p=='/api/logic':self.send(logic);return
  if p=='/api/quality':
   quality=json.loads((BASE/'data/quality.json').read_text(encoding='utf-8'));quality['missingReferences']=[dict(r,drawing=d['id']) for d in catalog for r in d['references'] if not r.get('targets') and not r.get('selfReference')]
   quality['review']=[dict(t,drawing=d['id'],code=d['code']) for d in catalog for t in manager.drawing(d['id'])['translations'] if t['review']]
   self.send(quality);return
  if p=='/api/related':
   tag=q.get('tag',[''])[0];platform=q.get('platform',[''])[0];target=norm(shorttag(tag));matches=[];team=q.get('team',['工艺'])[0]
   for r in catalog:
    if r['platform']!=platform or r.get('team','工艺')!=team:continue
    for e in r.get('equipment',[]):
     if norm(shorttag(e['tag']))==target:matches.append(dict(e,drawingId=r['id'],drawingTitle=r['title'],code=r['code']))
   causes=[c for c in logic.get('causes',[]) if team=='工艺' and c['platform']==platform and (norm(shorttag(c['tag']))==target or any(norm(shorttag(t))==target for t in re.findall(r'(?:[A-Z]+-)?[A-Z]{1,6}-?\d+[A-Z]?',c['original'])))]
   effects=[e for e in logic.get('effects',[]) if norm(shorttag(e['tag']))==target] if platform=='CEPD' and team=='工艺' else []
   from site_config import capabilities
   if not capabilities(manager)['enabled']['logic']:causes=[];effects=[]
   self.send({'drawings':matches,'causes':causes,'effects':effects});return
  if p.startswith('/download/'):
   parts=p.split('/')
   if len(parts)!=4:self.send({'error':'下载地址无效'},404);return
   _,_,id,kind=parts
   if id not in manifest:self.send({'error':'未找到图纸'},404);return
   name=manifest[id]['filename'];folder=BASE/'output'/id
   if kind=='original':
    from vault import original
    f=original(BASE,manifest[id])
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
   f=(CODE_ROOT/'static'/('index.html' if p=='/' else 'nwd.html' if p=='/twin.html' else p.lstrip('/'))).resolve()
   if not f.is_relative_to(CODE_ROOT/'static'):self.send({'error':'无此页面'},404);return
  if not f.is_file():self.send({'error':'无此页面'},404);return
  if p.startswith('/output/'):
   st=f.stat();self.cached((p,manager.validators.get(p.removeprefix('/output/'),(st.st_mtime_ns,st.st_ctime_ns,st.st_size))),f.read_bytes,'image/svg+xml');return
  if f.suffix in ('.js','.css') or f.parent==CODE_ROOT/'static/appearance':
   self.cached((p,f.stat().st_mtime_ns,f.stat().st_size),f.read_bytes,mimetypes.guess_type(f.name)[0] or 'application/octet-stream');return
  self.send(f.read_bytes(),ctype=mimetypes.guess_type(f.name)[0] or 'application/octet-stream')
if __name__=='__main__':
 port=int(os.environ.get('PID_PORT','8765'));host=os.environ.get('PID_HOST','0.0.0.0');print(f'PID 图纸工作台：监听 {host}:{port}，本机访问 http://127.0.0.1:{port}',flush=True);ThreadingHTTPServer((host,port),Handler).serve_forever()
