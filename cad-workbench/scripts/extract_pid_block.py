"""Extract one named source node, including all its fragments, as an offline P&ID template."""
import argparse
import hashlib
import json
import os
import struct
import sys
import tempfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from platform_models import array, read_header


def write_atomic(file, content):
    with tempfile.NamedTemporaryFile(dir=file.parent, delete=False) as tmp:
        tmp.write(content)
    os.replace(tmp.name, file)


def extract(root, platform, node_id, family, yaw, origin, unit):
    model = root / platform
    info = json.loads((model / 'info.json').read_bytes())
    positions, indices, colors, normals, fragments = [], [], [], [], []
    vertex_count = 0
    for file in sorted((model / 'parts').glob('*.glb')):
        doc, offset = read_header(file)
        nodes = [n for n in doc['nodes'] if n.get('extras', {}).get('sourceNode') == node_id and 'mesh' in n]
        if not nodes:
            continue
        with file.open('rb') as stream:
            stream.seek(offset)
            raw = stream.read()
        for n in nodes:
            matrix = np.array(n['matrix']).reshape(4, 4)
            for p in doc['meshes'][n['mesh']]['primitives']:
                if p.get('mode', 4) != 4:
                    continue
                pos = array(doc, raw, p['attributes']['POSITION']) @ matrix[:3, :3] + matrix[3, :3]
                idx = array(doc, raw, p['indices']).ravel() if 'indices' in p else np.arange(len(pos))
                if np.linalg.det(matrix[:3, :3]) < 0:
                    idx = idx.reshape(-1, 3)[:, ::-1].ravel()
                if 'NORMAL' in p['attributes']:
                    normal = array(doc, raw, p['attributes']['NORMAL']) @ np.linalg.inv(matrix[:3, :3]).T
                else:
                    triangles = idx.reshape(-1, 3)
                    face = np.cross(pos[triangles[:, 1]] - pos[triangles[:, 0]], pos[triangles[:, 2]] - pos[triangles[:, 0]])
                    normal = np.zeros_like(pos)
                    for corner in triangles.T:
                        np.add.at(normal, corner, face)
                normals.append(normal / np.maximum(np.linalg.norm(normal, axis=1, keepdims=True), 1e-12))
                material = doc['materials'][p['material']] if 'material' in p else {}
                rgb = material.get('pbrMetallicRoughness', {}).get('baseColorFactor', [.45, .45, .45])[:3]
                indices.append(idx.astype('<u4') + vertex_count)
                positions.append(pos)
                colors.append(np.tile(np.round(np.clip(rgb, 0, 1) * 255).astype('u1'), (len(pos), 1)))
                vertex_count += len(pos)
            fragments.append(n['extras']['sourceId'])
            name = n['name']
    if not positions:
        raise ValueError('所选源节点没有三角网格')
    xyz = np.concatenate(positions)
    xyz -= xyz.min(0) + np.ptp(xyz, axis=0) * origin
    angle = np.radians(yaw)
    c, s = np.cos(angle), np.sin(angle)
    rotation = np.array([[c, 0, -s], [0, 1, 0], [s, 0, c]])
    xyz = xyz @ rotation / unit
    normal = np.concatenate(normals) @ rotation
    idx = np.concatenate(indices)
    payload = struct.pack('<II', len(xyz), len(idx)) + xyz.astype('<f4').tobytes() + idx.astype('<u4').tobytes() + normal.astype('<f4').tobytes() + np.concatenate(colors).tobytes()
    key = hashlib.sha256(payload).hexdigest()
    folder = root / 'blocks'
    folder.mkdir(exist_ok=True)
    write_atomic(folder / (key + '.bin'), payload)
    manifest = folder / 'catalog.json'
    catalog = json.loads(manifest.read_bytes()) if manifest.exists() else {}
    catalog[family] = dict(asset=key, platform=info['name'], name=name, digest=info['digest'],
                           node=node_id, fragments=len(fragments), triangles=len(idx) // 3)
    write_atomic(manifest, json.dumps(catalog, ensure_ascii=False, indent=2).encode())
    print(family, name, len(fragments), len(idx) // 3)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('models', type=Path)
    parser.add_argument('platform', choices=['k', 'l'])
    parser.add_argument('node', type=int)
    parser.add_argument('family', choices=['ball', 'gate', 'gauge', 'flange', 'pump', 'check'])
    parser.add_argument('--yaw', type=float, default=0)
    parser.add_argument('--origin', nargs=3, type=float, required=True, help='Anchor as fractions of source bounds')
    parser.add_argument('--unit', type=float, required=True, help='Source length corresponding to one template unit')
    args = parser.parse_args()
    if args.unit <= 0:
        parser.error('--unit must be positive')
    extract(args.models, args.platform, args.node, args.family, args.yaw, np.array(args.origin), args.unit)
