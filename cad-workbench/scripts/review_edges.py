"""Build compact, node-addressable review outlines from full-precision editor pages."""
import argparse
import gzip
import hashlib
import json
import math
import stat
import struct
import tempfile
from pathlib import Path

import numpy as np


def page_edges(raw):
    header_size, = struct.unpack_from('<I', raw)
    offset = 4 + (header_size + 3) // 4 * 4

    def take(dtype, count):
        nonlocal offset
        values = np.frombuffer(raw, dtype, count, offset)
        offset += (values.nbytes + 3) // 4 * 4
        return values

    for mode, n, ni, nr, _, _, _, _, full in json.loads(raw[4:4 + header_size]):
        if not full:
            raise ValueError('线稿需要原始精度分块')
        xyz = take('<f4', n * 3).reshape(-1, 3)
        take('u1', n * 3)
        indices = take('<u4', ni)
        runs = take('<u4', nr * 2).reshape(-1, 2)
        if mode == 0:
            continue
        width = 3 if mode == 4 else 2
        ids = np.repeat(runs[:, 1], np.diff(runs[:, 0], prepend=0) // width)
        if mode == 1:
            yield xyz[indices.reshape(-1, 2)], ids
            continue
        # Weld duplicated CAD vertices before classifying shared edges.
        q = np.rint((xyz - xyz.min(axis=0)) * 2000).astype(np.uint64)
        if q.max() < (1 << 21):
            keys = (q[:, 0] << 42) | (q[:, 1] << 21) | q[:, 2]
            _, first, welded = np.unique(keys, return_index=True, return_inverse=True)
        else:
            _, first, welded = np.unique(q, axis=0, return_index=True, return_inverse=True)
        points = xyz[first]
        triangles = welded[indices].reshape(-1, 3)
        normals = np.cross(points[triangles[:, 1]] - points[triangles[:, 0]], points[triangles[:, 2]] - points[triangles[:, 0]])
        lengths = np.linalg.norm(normals, axis=1)
        valid = lengths > 1e-10
        triangles, ids = triangles[valid], ids[valid]
        if not len(ids):
            continue
        normals = normals[valid] / lengths[valid, None]
        edges = np.stack((triangles, np.roll(triangles, -1, axis=1)), axis=-1).reshape(-1, 2)
        edges.sort(axis=1)
        owner = np.repeat(ids, 3)
        key = (owner.astype(np.uint64) * n + edges[:, 0].astype(np.uint64)) * n + edges[:, 1].astype(np.uint64)
        order = np.argsort(key)
        starts = np.flatnonzero(np.r_[True, np.diff(key[order]) != 0])
        counts = np.diff(starts, append=len(order))
        keep = counts != 2
        pair = starts[~keep]
        a, b = normals[order[pair] // 3], normals[order[pair + 1] // 3]
        dot = (a * b).sum(axis=1)
        b = np.where((dot < 0)[:, None], -b, b)
        # Sharp creases and principal silhouettes keep cylinders legible without facet diagonals.
        keep[~keep] = (np.abs(dot) < math.cos(math.radians(25))) | (((a > .0001) != (b > .0001)).any(axis=1) & (np.abs(dot) < .99998))
        pick = order[starts[keep]]
        yield points[edges[pick]], owner[pick]


def build(folder, index):
    access = stat.S_IMODE((folder / (index['overview'] + '.gz')).stat().st_mode)
    output = []
    total = sum(t['count'] for t in index['tiles'])
    for tile in index['tiles']:
        segments, owners = [], []
        for page in tile['pages']:
            raw = gzip.decompress((folder / (page + '.gz')).read_bytes())
            for edges, ids in page_edges(raw):
                segments.append(edges)
                owners.append(ids)
        if not segments:
            continue
        lines, ids = np.concatenate(segments), np.concatenate(owners)
        length = np.linalg.norm(lines[:, 1] - lines[:, 0], axis=1)
        # Reserve a representative edge per component before distributing the spatial budget.
        ranking = np.lexsort((-length, ids))
        representatives = ranking[np.r_[True, np.diff(ids[ranking]) != 0]] if len(ids) else ranking
        score = length.copy()
        score[representatives] = np.inf
        budget = max(len(representatives), 150, round(1500000 * tile['count'] / total))
        take = np.flatnonzero((length > .025) | np.isinf(score))
        if len(take) > budget:
            take = take[np.argpartition(score[take], -budget)[-budget:]]
        if not len(take):
            continue
        take = take[np.argsort(ids[take], kind='stable')]
        lines, ids = lines[take], ids[take]
        lo, hi = lines.min(axis=(0, 1)), lines.max(axis=(0, 1))
        packed = np.rint((lines - lo) * (65535 / np.maximum(hi - lo, .000001))).astype('<u2')
        ends = np.r_[np.flatnonzero(np.diff(ids)) + 1, len(ids)]
        runs = np.column_stack((ends * 2, ids[ends - 1])).astype('<u4')
        raw = packed.tobytes() + runs.tobytes()
        key = hashlib.sha256(raw).hexdigest()
        target = folder / (key + '.gz')
        if not target.exists():
            with tempfile.NamedTemporaryFile(dir=folder, delete=False) as f:
                f.write(gzip.compress(raw, compresslevel=3, mtime=0))
            Path(f.name).chmod(access)
            Path(f.name).replace(target)
        output.append(dict(asset=key, lines=len(ids), min=lo.tolist(), max=hi.tolist()))
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('editor', type=Path)
    args = parser.parse_args()
    path = args.editor / 'index.json'
    index = json.loads(path.read_bytes())
    index['outlines'] = build(args.editor, index)
    with tempfile.NamedTemporaryFile(dir=args.editor, delete=False) as f:
        f.write(json.dumps(index, ensure_ascii=False, separators=(',', ':')).encode())
    Path(f.name).chmod(stat.S_IMODE(path.stat().st_mode))
    Path(f.name).replace(path)
    print(path, sum(t['lines'] for t in index['outlines']), '条特征线')
