"""Read-only audit of a mounted PID library. No drawing content is printed."""
import argparse
import hashlib
import json
from pathlib import Path


def audit(base):
    base = Path(base).resolve()
    root = base.parent
    def read(file):
        return json.loads(file.read_text(encoding="utf-8"))
    records = read(base / "data/manifest.json")
    catalog = read(base / "data/catalog.json")
    ids = {r["id"] for r in records}
    if ids != {d["id"] for d in catalog} or len(ids) != len(records):
        raise ValueError("目录与清单的图纸 ID 不一致")
    verified = 0
    for record in records:
        original = (root / record["source"]).resolve()
        if not original.is_relative_to(root):
            raise ValueError("原图超出资料目录")
        with original.open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != record["sha256"]:
                raise ValueError("原始 DWG 校验失败：" + record["id"])
        out = base / "output" / record["id"]
        for name in ("drawing.json", "original.svg", "chinese.svg", "中文图纸.dxf", "中文图纸.dwg"):
            if (out / name).stat().st_size == 0: raise ValueError("缺少图纸产物：" + record["id"])
        if not (base / record["dxf"]).is_file(): raise ValueError("缺少源 DXF：" + record["id"])
        verified += 1
    links = [r for d in catalog for r in d["references"] if r.get("targets")]
    if any(target not in ids for r in links for target in r["targets"]):
        raise ValueError("关联指向目录以外的图纸")
    return {"drawings":len(records),"verifiedOriginals":verified,"resolvedReferences":len(links),
            "accessConfigured":(base / "data/access-control.json").is_file()}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("library", type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(args.library), ensure_ascii=False))
