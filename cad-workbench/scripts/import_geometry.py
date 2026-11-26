"""Map a standard self-contained GLB scene onto the reviewer's stable preorder IDs."""
import numpy as np


def normalize(doc, source):
    if doc.get('asset', {}).get('version') != '2.0' or len(doc.get('buffers', [])) != 1 or 'uri' in doc['buffers'][0]:
        raise ValueError('需要带内嵌几何的 GLB 2.0 文件')
    if doc.get('extensionsRequired') or doc.get('skins') or any('sparse' in a for a in doc['accessors']):
        raise ValueError('该模型含未支持的扩展、蒙皮或稀疏几何，请导出静态、未压缩的 GLB')
    nodes = doc['nodes']
    roots = doc['scenes'][doc.get('scene', 0)]['nodes']
    parents, names, classes = [-1], [source.stem], ['模型']
    stack = [(i, 0, np.eye(4)) for i in reversed(roots)]
    visited, flat = set(), []
    while stack:
        i, parent, world = stack.pop()
        if not 0 <= i < len(nodes) or i in visited:
            raise ValueError('模型层级包含无效或重复的节点')
        visited.add(i)
        obj = nodes[i]
        if 'matrix' in obj:
            local = np.asarray(obj['matrix']).reshape(4, 4).T
        else:
            x, y, z, w = obj.get('rotation', [0, 0, 0, 1])
            rot = [[1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)],
                   [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)],
                   [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)]]
            local = np.eye(4)
            local[:3, :3] = np.asarray(rot) * obj.get('scale', [1, 1, 1])
            local[:3, 3] = obj.get('translation', [0, 0, 0])
        transform = world @ local
        if not np.isfinite(transform).all():
            raise ValueError('模型变换含无效坐标')
        node_id = len(names)
        mesh = doc['meshes'][obj['mesh']] if 'mesh' in obj else {}
        names.append(str(obj.get('name') or mesh.get('name') or '节点 '+str(i+1)))
        classes.append('构件' if mesh else '分组')
        parents.append(parent)
        if mesh:
            flat.append(dict(mesh=obj['mesh'], matrix=transform.T.ravel(), extras={'sourceNode': node_id}))
        stack.extend((child, node_id, transform) for child in reversed(obj.get('children', [])))
    if not flat:
        raise ValueError('该文件没有可显示的构件')
    doc['nodes'] = flat
    materials = doc.setdefault('materials', [])
    default_material = len(materials)
    materials.append({})
    for material in materials:
        material.setdefault('pbrMetallicRoughness', {}).setdefault('baseColorFactor', [1, 1, 1, 1])
    for mesh in doc['meshes']:
        for prim in mesh['primitives']:
            prim.setdefault('material', default_material)
    return dict(parent=parents, name=names, className=classes)
