"""Read the published, content-addressed Mac platform scene files."""
import gzip
import re
from wsgiref.util import FileWrapper


def serve(req, env, start, root, path):
    if req.authorize():
        match = re.fullmatch(r"/api/platforms/([kl])/(index\.json|[a-f0-9]{64})", path)
        if match:
            platform, asset = match.groups()
            directory = root / "models" / "native" / platform
            if asset == "index.json" and (directory / asset).is_file():
                index = directory / asset
                req.cached((platform, index.stat().st_mtime_ns), index.read_bytes, "application/json")
            elif asset != "index.json" and (directory / (asset + ".bin.gz")).is_file():
                file = directory / (asset + ".bin.gz")
                etag = 'W/"' + asset + '"'
                headers = [("ETag", etag), ("Cache-Control", "private, max-age=31536000, immutable"), ("Vary", "Accept-Encoding")]
                if req.headers.get("If-None-Match") == etag:
                    start("304 Not Modified", headers)
                    return []
                if re.search(r"(?:^|,)\s*gzip\s*(?:,|$)", req.headers.get("Accept-Encoding", "")):
                    stream = file.open("rb")
                    headers.extend([("Content-Encoding", "gzip"), ("Content-Length", str(file.stat().st_size))])
                else:
                    stream = gzip.open(file, "rb")
                start("200 OK", headers + [("Content-Type", "application/octet-stream")])
                return FileWrapper(stream, 128 * 1024)
            else:
                req.send({"error": "模型资源不存在"}, 404)
        else:
            req.send({"error": "模型地址无效"}, 404)
    from http import HTTPStatus
    start(f"{req.status} {HTTPStatus(req.status).phrase}", req.fields)
    return [req.wfile.getvalue()]
