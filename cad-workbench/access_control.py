"""Two shared role passwords; credentials stay on disk, sessions stay in memory."""
import hashlib,hmac,json,secrets,time,threading,os,ipaddress
from http.cookies import SimpleCookie,CookieError

ROLES=('viewer','admin')
COOKIE='pid_session'
TTL=8*60*60
ROUNDS=600_000

class AccessError(Exception):
 def __init__(self,message,status=400):super().__init__(message);self.status=status

def local_client(address):
 try:return ipaddress.ip_address(address).is_loopback
 except ValueError:return False

def validate(password):
 if not isinstance(password,str) or not 8<=len(password)<=128:raise AccessError('密码须为 8–128 个字符')

def password_record(password):
 validate(password);salt=secrets.token_hex(24)
 return {'salt':salt,'rounds':ROUNDS,'hash':hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(salt),ROUNDS).hex()}

def verify(password,record):
 if not isinstance(password,str) or len(password)>128:return False
 digest=hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(record['salt']),record['rounds']).hex()
 return hmac.compare_digest(digest,record['hash'])

class AccessControl:
 def __init__(self,base):
  self.path=base/'data/access-control.json';self.lock=threading.RLock();self.sessions={};self.attempts={};self.config=None
  if self.path.exists():
   self.config=json.loads(self.path.read_text(encoding='utf-8'))
   if self.config.get('version')!=1:raise RuntimeError('访问密码配置版本无效，请在服务器本机修复')
   for role in ROLES:
    record=self.config['passwords'][role]
    if len(bytes.fromhex(record['salt']))!=24 or len(bytes.fromhex(record['hash']))!=32 or record['rounds']!=ROUNDS:raise RuntimeError('访问密码配置损坏，请在服务器本机修复')
 def write(self,config):
  self.path.parent.mkdir(parents=True,exist_ok=True);temp=self.path.with_suffix('.tmp')
  fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
  with os.fdopen(fd,'w',encoding='utf-8') as f:json.dump(config,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
  os.replace(temp,self.path);self.config=config
 def session(self,cookie):
  try:
   jar=SimpleCookie();jar.load(cookie or '');token=jar[COOKIE].value
  except (KeyError,ValueError,CookieError):return None
  key=hashlib.sha256(token.encode()).hexdigest()
  with self.lock:
   session=self.sessions.get(key)
   if session and session['expires']>time.time():return dict(session,key=key)
   self.sessions.pop(key,None);return None
 def new_session(self,role):
  now=time.time();self.sessions={k:v for k,v in self.sessions.items() if v['expires']>now}
  if len(self.sessions)>=4096:self.sessions.pop(next(iter(self.sessions)))
  token=secrets.token_urlsafe(32);self.sessions[hashlib.sha256(token.encode()).hexdigest()]={'role':role,'csrf':secrets.token_urlsafe(32),'expires':now+TTL}
  return token
 def guard_attempt(self,ip):
  now=time.time();self.attempts={k:v for k,v in self.attempts.items() if now-v['start']<60}
  if self.attempts.get(ip,{}).get('count',0)>=5:raise AccessError('密码错误次数过多，请 1 分钟后重试',429)
 def fail(self,ip):
  if len(self.attempts)>=4096:self.attempts.pop(next(iter(self.attempts)))
  item=self.attempts.setdefault(ip,{'count':0,'start':time.time()});item['count']+=1
  raise AccessError('身份或密码不正确',401)
 def setup(self,data,ip):
  with self.lock:
   if not local_client(ip):raise AccessError('首次密码请在服务器本机通过 127.0.0.1 设置',403)
   if self.config:raise AccessError('密码已设置，请登录后修改',409)
   viewer=data.get('viewerPassword');admin=data.get('adminPassword');validate(viewer);validate(admin)
   if viewer==admin:raise AccessError('管理员与普通用户请设置不同密码')
   self.write({'version':1,'passwords':{r:password_record(p) for r,p in zip(ROLES,(viewer,admin))}})
   return self.new_session('admin')
 def login(self,data,ip,old_session=None):
  with self.lock:
   if not self.config:raise AccessError('请等待管理员在服务器本机设置访问密码',409)
   self.guard_attempt(ip);role=data.get('role');password=data.get('password')
   record=self.config['passwords'].get(role) if isinstance(role,str) else None
   valid=verify(password,record or self.config['passwords']['viewer'])
   if not record or not valid:self.fail(ip)
   self.attempts.pop(ip,None)
   if old_session:self.sessions.pop(old_session['key'],None)
   return self.new_session(role)
 def change(self,data,session,ip):
  with self.lock:
   self.guard_attempt(ip)
   if not verify(data.get('currentPassword'),self.config['passwords']['admin']):self.fail(ip)
   updates={r:data.get(r+'Password') for r in ROLES if data.get(r+'Password')}
   if not updates:raise AccessError('请至少填写一种新密码')
   for password in updates.values():validate(password)
   if len(updates)==2:
    if updates['viewer']==updates['admin']:raise AccessError('两种身份不能使用相同密码')
   else:
    role=next(iter(updates));other='admin' if role=='viewer' else 'viewer'
    if verify(updates[role],self.config['passwords'][other]):raise AccessError('两种身份不能使用相同密码')
   records=dict(self.config['passwords']);records.update({r:password_record(p) for r,p in updates.items()})
   self.write({'version':1,'passwords':records});self.sessions.clear();self.attempts.clear()
   return {'message':'密码已更新，所有已登录用户需重新登录'}
 def logout(self,session):
  with self.lock:self.sessions.pop(session['key'],None)

def cookie_header(token=None):
 return f'{COOKIE}={token or ""}; Path=/; HttpOnly; SameSite=Strict; Max-Age={TTL if token else 0}'
