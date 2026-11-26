"""Durable job queue, immutable originals and transactional publication pointers."""
import contextlib
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
from types import SimpleNamespace
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

TEAMS = ("工艺", "动力", "机械", "电气")


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def clone(src, dst):
    """Clone a directory on APFS or reflink-capable Linux filesystems."""
    if dst.exists():
        raise FileExistsError(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    if sys.platform == "darwin":
        args = ["cp", "-cRp", str(src), str(dst)]
    elif sys.platform.startswith("linux"):
        args = ["cp", "-a", "--reflink=auto", str(src), str(dst)]
    else:
        shutil.copytree(src, dst)
        return
    if subprocess.run(args, stderr=subprocess.DEVNULL).returncode:
        shutil.rmtree(dst, ignore_errors=True)
        shutil.copytree(src, dst)


def original(base, record):
    if record.get("archived"):
        digest = record["sha256"]
        if not re.fullmatch("[0-9a-f]{64}", digest):
            raise ValueError("原件摘要无效")
        return Path(os.environ["PID_VAULT"]) / "originals" / digest[:2] / (digest + ".dwg")
    root = base.parent.resolve()
    path = (root / record["source"]).resolve()
    if not path.is_relative_to(root):
        raise ValueError("原件路径无效")
    return path


def archive(root, source, digest):
    if sha(source) != digest:
        raise ValueError("原件校验失败：" + source.name)
    target = root / "originals" / digest[:2] / (digest + ".dwg")
    if target.exists():
        if sha(target) != digest:
            raise ValueError("资料盘原件校验失败")
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix("." + uuid.uuid4().hex)
    try:
        shutil.copyfile(source, temp)
        if sha(temp) != digest:
            raise ValueError("原件复制过程中发生变化")
        temp.chmod(0o444)
        os.replace(temp, target)
    finally:
        temp.unlink(missing_ok=True)
    return target


class Vault:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.db = self.root / "workbench.sqlite3"
        self.local = threading.local()
        with contextlib.closing(self.connect()) as db, db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS head(id INTEGER PRIMARY KEY CHECK(id=1), generation TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS assets(drawing TEXT NOT NULL,name TEXT NOT NULL,digest TEXT NOT NULL,generation TEXT NOT NULL,
                    PRIMARY KEY(drawing,name,digest));
                CREATE TABLE IF NOT EXISTS drawings(id TEXT PRIMARY KEY, team TEXT NOT NULL, code TEXT NOT NULL, revision INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, kind TEXT NOT NULL, parent TEXT NOT NULL,
                    status TEXT NOT NULL, actor TEXT NOT NULL, payload TEXT NOT NULL, created TEXT NOT NULL, message TEXT NOT NULL);
                CREATE UNIQUE INDEX IF NOT EXISTS one_active_job ON jobs((1)) WHERE status IN ('queued','processing');
                CREATE TABLE IF NOT EXISTS releases(id TEXT PRIMARY KEY, parent TEXT NOT NULL, actor TEXT NOT NULL,
                    created TEXT NOT NULL, kind TEXT NOT NULL, drawings TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS accounts(login TEXT PRIMARY KEY, name TEXT NOT NULL, secret TEXT NOT NULL,
                    teams TEXT NOT NULL, enabled INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS sheet_ai_config(id INTEGER PRIMARY KEY CHECK(id=1),endpoint TEXT,model TEXT,secret TEXT);
                CREATE TABLE IF NOT EXISTS sheet_ai_jobs(
                    id INTEGER PRIMARY KEY, drawing TEXT NOT NULL, digest TEXT NOT NULL, generation TEXT NOT NULL,
                    state TEXT NOT NULL, actor TEXT NOT NULL, model TEXT NOT NULL, created TEXT NOT NULL,
                    recipe TEXT, message TEXT DEFAULT '', reviewer TEXT, reviewed TEXT);
                CREATE UNIQUE INDEX IF NOT EXISTS sheet_ai_active ON sheet_ai_jobs(drawing,digest)
                    WHERE state IN ('queued','running');
                DROP INDEX IF EXISTS sheet_ai_pending;
                CREATE UNIQUE INDEX IF NOT EXISTS sheet_ai_live ON sheet_ai_jobs(drawing) WHERE state='published';
                CREATE INDEX IF NOT EXISTS sheet_ai_queue ON sheet_ai_jobs(state,id);
                CREATE TABLE IF NOT EXISTS nwd_scenes(model TEXT,digest TEXT,revision INTEGER,document TEXT NOT NULL,actor TEXT NOT NULL,stamp TEXT NOT NULL,PRIMARY KEY(model,digest,revision));
                CREATE TABLE IF NOT EXISTS model_links(drawing TEXT, handle TEXT, model TEXT, digest TEXT, object INTEGER NOT NULL, PRIMARY KEY(drawing,handle,model,digest));
                CREATE TABLE IF NOT EXISTS manual_links(id INTEGER PRIMARY KEY CHECK(id=1), document TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS drawing_references(drawing TEXT NOT NULL, handle TEXT NOT NULL, code TEXT NOT NULL, targets TEXT NOT NULL, preferred TEXT);
                CREATE INDEX IF NOT EXISTS references_by_source ON drawing_references(drawing,handle);
                CREATE TABLE IF NOT EXISTS audit(event TEXT PRIMARY KEY, stamp TEXT NOT NULL, record TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS audit_by_time ON audit(stamp);
                CREATE TABLE IF NOT EXISTS heartbeat(id INTEGER PRIMARY KEY CHECK(id=1), stamp REAL NOT NULL, capabilities TEXT NOT NULL);
            """)

        self.db.chmod(0o600)

    def connect(self):
        db = sqlite3.connect(self.db, timeout=20)
        db.row_factory = sqlite3.Row
        return db

    @contextlib.contextmanager
    def transaction(self):
        if getattr(self.local, "db", None) is not None:
            yield self.local.db
            return
        with contextlib.closing(self.connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            self.local.db = db
            try:
                yield db
            finally:
                self.local.db = None

    def head(self):
        with contextlib.closing(self.connect()) as db, db:
            row = db.execute("SELECT generation FROM head").fetchone()
        return row[0] if row else None

    def view(self, generation):
        if not generation or not re.fullmatch("[a-zA-Z0-9_-]+", generation):
            raise ValueError("资料盘尚未初始化或修订号无效")
        return self.root / "revisions" / generation / "library"

    def index(self, db, base):
        def read(name, default):
            path = base / "data" / name
            return json.loads(path.read_text()) if path.exists() else default
        validators={}
        for item in read("manifest.json",[]):
            for name in ("drawing.json","chinese.svg","original.svg"):
                path=base/"output"/item["id"]/name
                validators[item["id"]+"/"+name]=sha(path)
        (base/"data/validators.json").write_text(json.dumps(validators))
        db.executemany("INSERT OR IGNORE INTO assets VALUES(?,?,?,?)",[
            (*key.split("/"),digest,base.parent.name) for key,digest in validators.items() if key.endswith(".svg")
        ])
        revisions = read("attribute-edits.json", {}).get("revisions", {})
        db.execute("DELETE FROM drawings")
        db.executemany("INSERT INTO drawings VALUES(?,?,?,?)", [
            (r["id"], r.get("team","工艺"), r["code"], revisions.get(r["id"],0))
            for r in read("manifest.json", [])
        ])

        self.seed_metadata(db,base)

    def overrides(self):
        with contextlib.closing(self.connect()) as db:
            row=db.execute("SELECT document FROM manual_links WHERE id=1").fetchone()
        return json.loads(row[0]) if row else {"revision":0,"links":{},"history":[]}

    def seed_metadata(self, db, base):
        from management import read_json
        catalog=read_json(base/"data/catalog.json",[])
        links=read_json(base/"data/manual-links.json",{"revision":0,"links":{},"history":[]})
        self.index_links(db,catalog,links)
        self.sync_audit(db,SimpleNamespace(base=base,overrides=links,catmap={d["id"]:d for d in catalog}))

    def index_links(self, db, catalog, overrides):
        db.execute("INSERT OR REPLACE INTO manual_links VALUES(1,?)",(json.dumps(overrides,ensure_ascii=False),))
        db.execute("DELETE FROM drawing_references")
        manual={}
        for key,ref in overrides["links"].items():
            manual.setdefault(ref["drawing"],{})[(ref["handle"],ref["code"])]=ref
        rows=[]
        for drawing in catalog:
            patches=manual.get(drawing["id"],{})
            refs={(r["handle"],r["code"]):r for r in drawing.get("references",[])}
            refs.update(patches)
            for key,ref in refs.items():
                targets=ref.get("targets",[])
                preferred=ref.get("preferredTarget") if key in patches else targets[0] if len(targets)==1 else None
                rows.append((drawing["id"],*key,json.dumps(targets),preferred))
        db.executemany("INSERT INTO drawing_references VALUES(?,?,?,?,?)",rows)

    def sync_audit(self, db, manager):
        from change_log import entries
        for event in entries(manager,limit=None)["records"]:
            self.audit_event(db,event)

    def audit_event(self, db, event):
        record=json.dumps(event,ensure_ascii=False,sort_keys=True)
        key=hashlib.sha256(record.encode()).hexdigest()
        db.execute("INSERT OR IGNORE INTO audit VALUES(?,?,?)",(key,event["time"],record))

    def history(self, query, offset):
        with contextlib.closing(self.connect()) as db:
            where="WHERE instr(lower(record),lower(?))>0"
            total=db.execute("SELECT count(*) FROM audit "+where,(query,)).fetchone()[0]
            rows=db.execute("SELECT record FROM audit "+where+" ORDER BY stamp DESC,rowid DESC LIMIT 50 OFFSET ?",(query,offset))
            return {"total":total,"records":[json.loads(row[0]) for row in rows]}

    def active(self, db):
        return db.execute("SELECT * FROM jobs WHERE status IN ('queued','processing')").fetchone()

    def enqueue(self, kind, job, drawings):
        with self.transaction() as db:
            if self.active(db):
                raise ValueError("已有发布任务正在处理")
            payload = dict(job, affected=list(drawings))
            db.execute("INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?)", (
                job["id"], kind, self.head(), "queued", job["actor"],
                json.dumps(payload, ensure_ascii=False), now(), "等待后台处理"))
        return job

    def jobs(self):
        with contextlib.closing(self.connect()) as db, db:
            rows = db.execute("SELECT * FROM jobs ORDER BY rowid DESC LIMIT 40").fetchall()
        return [(r["kind"], dict(json.loads(r["payload"]), status=r["status"], message=r["message"])) for r in rows]

    def commit(self, job, base):
        payload = json.loads(job["payload"])
        with self.transaction() as db:
            if db.execute("SELECT generation FROM head").fetchone()[0] != job["parent"]:
                raise ValueError("发布所依据的图库版本已变化")
            self.index(db, base)
            db.execute("INSERT INTO releases VALUES(?,?,?,?,?,?)", (job["id"],job["parent"],job["actor"],now(),job["kind"],json.dumps(payload["affected"])))
            if job["kind"]=="rollback":
                for drawing in payload["affected"]:
                    self.audit_event(db,dict(type="回滚图纸",drawing=drawing,code=db.execute("SELECT code FROM drawings WHERE id=?",(drawing,)).fetchone()[0],
                        title="",handle="",time=now(),actor=job["actor"],changes=[dict(field="修订",before=job["parent"],after=job["id"])],description="恢复来源 "+payload["target"]))
            db.execute("UPDATE head SET generation=?",(job["id"],))
            db.execute("UPDATE jobs SET status='complete',message='已发布' WHERE id=?", (job["id"],))


def initialize_empty(root):
    from workspace import initialize
    store=Vault(root)
    with store.transaction() as db:
        if not db.execute("SELECT 1 FROM head").fetchone():
            initialize(store.view("baseline"))
            (store.root/"data").mkdir(exist_ok=True)
            db.execute("INSERT INTO head VALUES(1,'baseline')")
        if not db.execute("SELECT 1 FROM manual_links").fetchone():
            store.seed_metadata(db,store.view(db.execute("SELECT generation FROM head").fetchone()[0]))
    return store
