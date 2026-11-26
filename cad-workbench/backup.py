"""Consistent offline archive with a verified manifest and non-overwriting restore."""
import argparse
import contextlib
import json
import os
import sqlite3
import tempfile
from pathlib import Path
from vault import Vault,clone,sha

def inventory(folder):
    return {str(p.relative_to(folder)):sha(p) for p in sorted(folder.rglob('*')) if p.is_file()}

def transfer(task,source,destination):
    source,destination=Path(source).resolve(),Path(destination).resolve()
    if destination.exists() or destination.is_relative_to(source):
        raise ValueError("备份或恢复目标必须是独立的新目录")
    destination.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent,prefix=".transfer-") as temp:
        result=Path(temp)/"result"
        if task=="backup":
            if not (source/"workbench.sqlite3").is_file():raise ValueError("未找到图库数据库")
            store=Vault(source)
            data=result/"vault"
            data.mkdir(parents=True)
            with store.transaction() as db:
                if store.active(db):raise ValueError("正在发布，请在任务结束后备份")
                with contextlib.closing(store.connect()) as src, contextlib.closing(sqlite3.connect(data/"workbench.sqlite3")) as dst:
                    src.backup(dst)
                    dst.execute("DELETE FROM heartbeat");dst.commit()
                for name in ("originals","revisions","data","models","site","legends"):
                    if (source/name).exists():clone(source/name,data/name)
                if (source/"profiles.json").is_file():
                    (data/"profiles.json").write_bytes((source/"profiles.json").read_bytes())
            (result/"sha256.json").write_text(json.dumps(inventory(data),ensure_ascii=False))
        else:
            expected=json.loads((source/"sha256.json").read_text())
            clone(source/"vault",result)
            if inventory(result)!=expected:raise ValueError("备份文件校验失败")
            with contextlib.closing(sqlite3.connect(result/"workbench.sqlite3")) as db:
                if db.execute("PRAGMA integrity_check").fetchone()[0]!="ok":raise ValueError("数据库校验失败")
        result.rename(destination)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("operation",choices=["backup","restore"]);p.add_argument("source");p.add_argument("destination")
    args=p.parse_args();transfer(args.operation,args.source,args.destination)
