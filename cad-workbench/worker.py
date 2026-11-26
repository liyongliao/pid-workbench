"""Publish verified whole-library generations. Web restarts never own CAD jobs."""
import fcntl
import json
import os
import shutil
import sys
import tempfile
import threading
import time
from pathlib import Path

from vault import Vault, clone
from management import Manager, read_json, write_json
from attribute_drafts import draft_owner, run
from cad_runtime import converter_status, drawing_font


def capabilities():
    info=converter_status()
    try:
        font=bool(drawing_font())
    except ValueError:
        font=False
    return {"converter":info,"font":font,"ready":bool(font and info["available"])}


def restore_drawings(vault, stage, payload):
    import references
    past=vault.view(payload["target"])
    previous={r["id"]:r for r in read_json(past/"data/manifest.json")}
    for index in ("manifest","catalog"):
        prior={r["id"]:r for r in read_json(past/f"data/{index}.json")}
        current=read_json(stage/f"data/{index}.json")
        write_json(stage/f"data/{index}.json",[prior[r["id"]] if r["id"] in payload["affected"] else r for r in current])
    state=read_json(stage/"data/attribute-edits.json",{"revisions":{},"blocks":{},"history":[]})
    old_state=read_json(past/"data/attribute-edits.json",{})
    for drawing in payload["affected"]:
        dest=stage/"output"/drawing
        shutil.rmtree(dest)
        clone(past/"output"/drawing,dest)
        for key in ("workingDxf","workingRoundtrip","dxf"):
            rel=previous[drawing].get(key)
            if rel:
                (stage/rel).parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(past/rel,stage/rel)
        state["revisions"][drawing]=state["revisions"].get(drawing,0)+1
        state["blocks"][drawing]=old_state.get("blocks",{}).get(drawing,{})
    write_json(stage/"data/attribute-edits.json",state)
    references.BASE=stage
    references.rebuild()


def execute(vault, job):
    payload=json.loads(job["payload"])
    work=vault.root/"work"
    work.mkdir(exist_ok=True)
    destination=vault.view(job["id"])
    # A restarted worker owns the exclusive worker lock and can reclaim its interrupted attempt.
    for abandoned in work.glob(job["id"]+"-*"):
        if abandoned.is_dir() and not abandoned.is_symlink():
            shutil.rmtree(abandoned)
    with tempfile.TemporaryDirectory(dir=work,prefix=job["id"]+"-") as attempt:
        stage=Path(attempt)/"library"
        clone(vault.view(job["parent"]),stage)
        write_json(stage/"data/manual-links.json",vault.overrides())
        manager=Manager(stage,recovery=False)
        manager.import_lock.acquire()
        token=draft_owner.set(payload.get("owner",""))
        try:
            if job["kind"]=="rollback":
                restore_drawings(vault,stage,payload)
            else:
                if job["kind"]=="upload":
                    manager.run_import(job["id"])
                    result=read_json(stage/"data/upload-jobs"/(job["id"]+".json"))
                    if result["status"]=="complete":
                        (stage/"uploads"/job["id"]/result["filename"]).unlink(missing_ok=True)
                else:
                    run(manager,job["id"])
                    result=read_json(stage/"data/attribute-batches"/job["id"]/"job.json")
                if result["status"]!="complete":
                    logs=vault.root/"logs"
                    logs.mkdir(exist_ok=True)
                    for report in stage.rglob("*.log"):
                        if job["id"] in str(report.relative_to(stage)):
                            shutil.copy2(report,logs/(job["id"]+"-"+report.name))
                    raise ValueError(result["message"])
        finally:
            draft_owner.reset(token)
        # A killed worker may leave a fully staged generation without a committed pointer.
        if destination.exists():
            shutil.rmtree(destination)
        destination.parent.mkdir(exist_ok=True)
        stage.rename(destination)
        try:
            vault.commit(job,destination)
        except Exception:
            # A failed pointer transaction must not grow subsequent backups with an unused revision.
            if vault.head()!=job["id"]:
                shutil.rmtree(destination.parent)
            raise


def serve(vault):
    lock=(vault.root/".worker.lock").open("a")
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    from model_imports import worker as import_models
    threading.Thread(target=import_models,args=(vault.root,),daemon=True).start()
    status=capabilities()
    status["test"]="引擎或字体缺失"
    if status["ready"]:
        from cad_runtime import probe
        try:
            status["test"]=probe()
        except Exception as error:
            status.update(ready=False,test=str(error))
    engine=Path(status["converter"].get("path") or ".")
    candidates=[Path("/engine/build.txt"),engine.parent/"build.txt",engine.parent.parent/"Resources/build.txt"]
    status["version"]=next((p.read_text(errors="replace").strip()[:120] for p in candidates if p.is_file()),"未提供版本号")
    plist=engine.parent.parent/"Info.plist"
    if plist.is_file():
        import plistlib
        with plist.open("rb") as stream:status["version"]=plistlib.load(stream).get("CFBundleShortVersionString",status["version"])
    def heartbeat():
        while True:
            with vault.transaction() as db:
                db.execute("INSERT OR REPLACE INTO heartbeat VALUES(1,?,?)",(time.time(),json.dumps(status)))
            time.sleep(5)
    threading.Thread(target=heartbeat,daemon=True).start()
    while True:
        with vault.transaction() as db:
            job=vault.active(db)
            if job:db.execute("UPDATE jobs SET status='processing',message='正在准备、转换和校验' WHERE id=?",(job["id"],))
        if not job:
            time.sleep(.4)
            continue
        try:
            execute(vault,job)
        except Exception as exc:
            with vault.transaction() as db:
                db.execute("UPDATE jobs SET status='failed',message=? WHERE id=?",(str(exc),job["id"]))
            print("任务失败",job["id"],str(exc),file=sys.stderr,flush=True)

if __name__=="__main__":
    serve(Vault(os.environ["PID_VAULT"]))
