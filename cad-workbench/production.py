"""WSGI entry point for the managed library. The worker alone activates CAD revisions."""
import contextlib
from email.message import Message
import http
import io
import json
import os
from pathlib import Path
import threading
import time
from types import SimpleNamespace
import urllib.parse
import uuid

from vault import TEAMS,initialize_empty
from accounts import require_team, manage
from access_control import AccessControl,AccessError
from attribute_drafts import draft_owner,drafts
from management import Manager,read_json,write_json

import sys
sys.modules.setdefault("production",sys.modules[__name__])

store=initialize_empty(os.environ["PID_VAULT"])
generation=store.head()
os.environ["PID_DATA_ROOT"]=str(store.view(generation))
import server

server.access=AccessControl(store.root)
server.manager.vault=store
server.manager.reload()
guard=threading.RLock()


def sync():
    global generation
    latest=store.head()
    if generation!=latest:
        new=store.view(latest)
        manager=Manager(new,recovery=False)
        manager.vault=store
        manager.reload()
        manager.token=server.manager.token
        server.BASE,server.ROOT,server.manager=new,new.parent,manager
        generation=latest


def health():
    with contextlib.closing(store.connect()) as db, db:
        row=db.execute("SELECT * FROM heartbeat WHERE id=1").fetchone()
    caps=json.loads(row["capabilities"]) if row else {}
    online=bool(row and time.time()-row["stamp"]<25)
    return dict(caps,online=online,ready=bool(online and caps.get("ready")))


class Request(server.Handler):
    def __init__(self,env):
        self.command=env["REQUEST_METHOD"]
        self.path=urllib.parse.quote_from_bytes(env["PATH_INFO"].encode("latin-1"),safe="/")+("?"+env["QUERY_STRING"] if env["QUERY_STRING"] else "")
        self.headers=Message()
        for key,value in env.items():
            if key.startswith("HTTP_"):self.headers[key[5:].replace("_","-")]=value
        for key in ("CONTENT_LENGTH","CONTENT_TYPE"):
            if env.get(key):self.headers[key.replace("_","-")]=env[key]
        self.client_address=(env["REMOTE_ADDR"],0)
        self.rfile=env["wsgi.input"]
        self.wfile=io.BytesIO()
        self.fields=[]
        self.connection=SimpleNamespace(getsockname=lambda:(env["SERVER_NAME"],int(env["SERVER_PORT"])),settimeout=lambda _:None)
        self.server=SimpleNamespace(server_port=int(env["SERVER_PORT"]))
        self.close_connection=False

    def send_response(self,code):self.status=code
    def send_header(self,k,v):
        if k.lower()!="connection":self.fields.append((k,str(v)))
    def end_headers(self):pass

    def authorize(self,admin=False):
        path=self.path.split("?")[0]
        session=server.access.session(self.headers.get("Cookie"))
        if session and session["role"] in ("admin","editor") and (admin or path.startswith("/api/admin/")):
            self.session=session
            return True
        return super().authorize(admin)

    def get(self):
        path=self.path.split("?")[0]
        if path.startswith("/project-legends/"):
            assets={"catalog.json":"application/json", "old.pdf":"application/pdf", "new.pdf":"application/pdf",
                    "manual.pdf":"application/pdf", "valves.png":"image/png"}
            name=path.removeprefix("/project-legends/")
            file=store.root / "legends" / name
            if name not in assets or not file.is_file():
                return self.send({"error":"图例资料未安装"},404)
            stat=file.stat()
            return self.cached((path,stat.st_mtime_ns,stat.st_size),file.read_bytes,assets[name])
        if path.startswith("/api/nwd/"):
            from nwd_editor import get
            return get(self,store,path)
        if path=="/api/admin/sheet-ai":
            from sheet_ai import panel
            q=urllib.parse.parse_qs(self.path.partition("?")[2])
            try:return self.send(panel(store,server.manager,self.session,q.get("preview",[None])[0]))
            except (AccessError,ValueError) as exc:return self.send({"error":str(exc)},getattr(exc,"status",400))
        if path=="/api/platforms":
            return self.send([p for p in ("k","l") if (store.root / "models/native" / p / "index.json").is_file()])
        if path=="/api/models" or path.startswith("/api/models/"):
            from platform_models import serve
            try:return serve(self,store,server.manager,path,urllib.parse.parse_qs(self.path.partition("?")[2]))
            except (TypeError,ValueError) as exc:return self.send({"error":str(exc)},400)
        if path.startswith("/output/") and "asset=" in self.path:
            parts=path.split("/")
            if len(parts)!=4 or parts[3] not in ("original.svg","chinese.svg"):
                return self.send({"error":"图形地址无效"},404)
            digest=urllib.parse.parse_qs(self.path.partition("?")[2]).get("asset",[""])[0]
            with contextlib.closing(store.connect()) as db, db:
                row=db.execute("SELECT generation FROM assets WHERE drawing=? AND name=? AND digest=?",(*parts[2:],digest)).fetchone()
            if not row:return self.send({"error":"图纸版本不存在"},404)
            file=store.view(row[0])/"output"/parts[2]/parts[3]
            return self.cached((path,digest),file.read_bytes,"image/svg+xml")
        if path=="/api/admin/nwd-import":
            if self.session['role']!='admin':return self.send({'error':'仅管理员可查看导入任务'},403)
            from model_imports import status
            job=urllib.parse.parse_qs(self.path.partition('?')[2]).get('id',[''])[0]
            return self.send(status(store.root,job))
        if path=="/api/admin/accounts":
            if self.session["role"]!="admin":return self.send({"error":"仅管理员可维护账号"},403)
            with contextlib.closing(store.connect()) as db, db:
                rows=db.execute("SELECT login,name,teams,enabled FROM accounts WHERE secret!='' ORDER BY login")
                return self.send([dict(r,teams=json.loads(r["teams"])) for r in rows])
        if path=="/api/admin/job":
            jid=urllib.parse.parse_qs(self.path.partition("?")[2]).get("id",[""])[0]
            with contextlib.closing(store.connect()) as db, db:
                row=db.execute("SELECT status,message FROM jobs WHERE id=?",(jid,)).fetchone()
            return self.send(dict(row) if row else {"error":"找不到任务"},200 if row else 404)
        if path=="/api/admin/releases":
            with contextlib.closing(store.connect()) as db, db:
                return self.send([dict(r,drawings=json.loads(r["drawings"])) for r in db.execute("SELECT * FROM releases ORDER BY rowid DESC LIMIT 100")])
        if path=="/api/auth/session":
            s=self.session or {}
            return self.send(dict(configured=bool(server.access.config),canSetup=not server.access.config and server.local_client(self.client_address[0]),authenticated=bool(s),named=True,**{k:s[k] for k in ("role","csrf","login","name","teams") if k in s}))
        if path=="/api/health":
            return self.send(dict(name="cad-workbench",version=server.VERSION,instance=server.instance_id(store.root),drawings=len(server.manager.catalog),generation=generation))
        if path=="/api/admin/state":
            state=server.manager.state()
            for kind,target in (("upload",state["uploads"]),("batch",state["drafts"]["jobs"])):
                recent=[job for k,job in store.jobs() if k==kind]
                ids={row["id"] for row in recent}
                target[:]=recent+[row for row in target if row["id"] not in ids and row.get("status") in ("complete","failed")]
            status=health()
            state["system"].update(worker=status,canImport=status["ready"])
            state["cadRuntime"]["available"]=status["ready"]
            return self.send(state)
        if path=="/api/admin/system":
            from diagnostics import snapshot
            status=health()
            info=snapshot(server.manager)
            info.update(worker=status,canImport=status["ready"],dataDirectory=str(store.root),font=dict(available=status.get("font",False)),converter=status.get("converter",info["converter"]))
            return self.send(info)
        return super().get()


def application(env,start_response):
    req=Request(env)
    try:
        path=req.path.partition("?")[0]
        if req.command=="GET" and path.startswith("/api/platforms/"):
            from native_models import serve
            return serve(req,env,start_response,store.root,path)
        model_asset=req.path.partition("?")[0] in ("/api/models/overview","/api/models/palette","/api/models/detail","/api/models/nearby","/api/models/objects")
        if req.command=="GET" and (model_asset or path.startswith("/api/nwd/")):
            # Immutable model geometry can be served while drawings and drafts are in use.
            if req.authorize():req.get()
            start_response(f"{req.status} {http.HTTPStatus(req.status).phrase}",req.fields)
            return [req.wfile.getvalue()]
        if req.command=="POST" and path=="/api/admin/nwd-import":
            req.do_POST()
            start_response(f"{req.status} {http.HTTPStatus(req.status).phrase}",req.fields)
            return [req.wfile.getvalue()]
        with guard:
            sync()
            s=server.access.session(req.headers.get("Cookie")) or {}
            token=draft_owner.set(s.get("login","") if s.get("role")=="editor" else "")
            try:
                if req.command=="GET":req.do_GET()
                elif req.command=="POST":
                    with store.transaction():
                        sync()
                        req.do_POST()
                else:req.send({"error":"方法无效"},405)
            finally:draft_owner.reset(token)
    except (AccessError,ValueError) as exc:
        req.send({"error":str(exc)},getattr(exc,"status",400))
    except Exception:
        import traceback
        traceback.print_exc()
        req.send({"error":"服务内部错误"},500)
    start_response(f"{req.status} {http.HTTPStatus(req.status).phrase}",req.fields)
    return [req.wfile.getvalue()]


def mutation(handler,path,data):
    session=handler.session
    actor=session.get("name","")+" ("+session.get("login","")+")"
    if not session.get("login"):
        raise AccessError("请使用具名账号重新登录",403)
    data["_actor"]=actor
    if path.startswith("/api/admin/sheet-ai/"):
        from sheet_ai import mutation as sheet_mutation
        return sheet_mutation(store,server.manager,session,path.rsplit("/",1)[-1],data)
    if path=="/api/admin/nwd-entry":
        from nwd_editor import edit_entry
        return edit_entry(store,data,session)
    if path=="/api/admin/nwd-scene":
        from nwd_editor import publish
        return publish(store,data,session)
    if path=="/api/admin/accounts":
        if session["role"]!="admin":raise AccessError("仅管理员可维护账号",403)
        return manage(server.access,store,data)
    manager=server.manager
    with store.transaction() as db:
        active=store.active(db)
        if active:
            previous=json.loads(active["payload"])
            if path.endswith("/publish") and active["actor"]==actor and previous.get("counter")==data.get("counter"):
                return dict(previous,status=active["status"])
            raise ValueError("已有任务正在发布，请待其完成后保存")
    if path.endswith("/publish"):
        for kind,previous in store.jobs():
            if kind=="batch" and previous.get("actor")==actor and previous.get("counter")==data.get("counter") and previous["status"]=="complete":
                return previous
    if path.endswith("/upload"):
        require_team(session,data.get("team"))
        if not health()["ready"]:raise ValueError("后台转换引擎未就绪")
    elif path.endswith("/publish"):
        blocks=drafts(manager.base)["blocks"]
        for row in blocks.values():require_team(session,manager.catmap[row["drawing"]]["team"])
        if not health()["ready"]:raise ValueError("后台转换引擎未就绪，草稿已保留")
    elif path=="/api/admin/rollback":
        if data.get("generation")!=generation:raise ValueError("图库版本已变化，请重新选择修订")
        with contextlib.closing(store.connect()) as db, db:
            release=db.execute("SELECT * FROM releases WHERE id=?",(data.get("release"),)).fetchone()
        if not release or release["kind"]=="upload":raise ValueError("所选修订没有可恢复的前一版")
        ids=json.loads(release["drawings"])
        for drawing in ids:require_team(session,manager.catmap[drawing]["team"])
        return store.enqueue("rollback",dict(id="r"+uuid.uuid4().hex,actor=actor,target=release["parent"],status="queued"),ids)
    else:
        drawing=data.get("drawing")
        require_team(session,manager.catmap.get(drawing,{}).get("team"))
    if path=="/api/admin/model-link":
        from platform_models import bind
        return bind(store,manager,data,actor)
    return None


if __name__=="__main__":
    import fcntl
    lock=(store.root/".web.lock").open("a")
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    from sheet_ai import retire_api_jobs
    retire_api_jobs(store)
    from waitress import serve
    serve(application,host=os.environ.get("PID_HOST","0.0.0.0"),port=int(os.environ.get("PID_PORT",8765)),
          threads=12,max_request_body_size=2*1024**3+1, ident="Drawing Workbench")
