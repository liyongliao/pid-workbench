"""Modelspace CAD centerlines projected into the published drawing coordinate system."""
import math
import re
from ezdxf.path import make_path

PROCESS_LAYER = re.compile(r'PROCESS|^AS_PIPE|^PIP(?:E|_|ING)|MAJORP|MINORP|^(?:MAJOR|MINOR)[ -]LINE|^0[12]-(?:MAJOR|MINOR)|主流程|次流程|工艺管|^LDL[123]A$|^SECONDARY$',re.I)


def extract(document, project, tolerance):
    result = {}
    for entity in document.modelspace():
        kind = entity.dxftype()
        layer = entity.dxf.get('layer','0')
        if not (PROCESS_LAYER.search(layer) or (layer == '0' and kind == 'LINE')):
            continue
        if kind == 'LINE':
            points = (entity.dxf.start, entity.dxf.end)
        elif kind in ('LWPOLYLINE','POLYLINE','ARC','SPLINE'):
            if kind == 'POLYLINE' and (entity.is_polygon_mesh or entity.is_poly_face_mesh):
                continue
            points = make_path(entity).flattening(tolerance, segments=4)
        else:
            continue
        path = []
        for point in points:
            x, y = project(point)
            if not (math.isfinite(x) and math.isfinite(y)):
                path = []
                break
            pair = [round(x,2),round(y,2)]
            if not path or path[-1] != pair:
                path.append(pair)
        if len(path)>1:
            result[entity.dxf.handle] = path
    return result
