"""Create an independent data volume. The source library is opened read-only."""
import argparse
import json
import os
import shutil
import tempfile
from pathlib import Path
from vault import Vault, archive, clone


def migrate(source, target):
    source, target = Path(source).resolve(), Path(target).resolve()
    if target.exists() or target.is_relative_to(source):
        raise ValueError("请选择独立且尚不存在的目标目录")
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=target.parent, prefix=".migration-") as staging:
        root = Path(staging) / "vault"
        store = Vault(root)
        view = store.view("baseline")
        view.mkdir(parents=True)
        for name in ("data", "output", "reports", "uploads"):
            if (source/name).is_dir():
                clone(source/name, view/name)
            else:
                (view/name).mkdir()
        (root/"data").mkdir()
        config = view/"data/access-control.json"
        if config.exists():
            config.rename(root/"data/access-control.json")
        manifest = view/"data/manifest.json"
        records = json.loads(manifest.read_text())
        catalog = json.loads((view/"data/catalog.json").read_text())
        ids = {r["id"] for r in records}
        if len(ids)!=len(records) or ids != {r["id"] for r in catalog}:
            raise ValueError("目录与清单不一致")
        for r in records:
            path = (source.parent/r["source"]).resolve()
            if not path.is_relative_to(source.parent):
                raise ValueError("原件路径超出资料目录")
            archive(root, path, r["sha256"])
            for name in ("drawing.json","chinese.svg","original.svg","中文图纸.dxf","中文图纸.dwg"):
                if not (view/"output"/r["id"]/name).stat().st_size:
                    raise ValueError("图纸产物为空")
            r.update(team="工艺", archived=True)
        links = [ref for d in catalog for ref in d["references"] if ref["targets"]]
        if any(t not in ids for ref in links for t in ref["targets"]):
            raise ValueError("存在悬空的关联目标")
        manifest.write_text(json.dumps(records,ensure_ascii=False))
        with store.transaction() as db:
            store.index(db,view)
            db.execute("INSERT INTO head VALUES(1,'baseline')")
        os.replace(root,target)
        return {"drawings":len(ids),"originals":len({r["sha256"] for r in records}),"links":len(links)}


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("source")
    parser.add_argument("target")
    args=parser.parse_args()
    print(migrate(args.source,args.target))
