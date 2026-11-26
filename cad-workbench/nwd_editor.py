"""Read-only NWD derivatives and versioned project presentations."""
from collections import defaultdict, deque
import contextlib
import gzip
import json
import math
import re
from functools import lru_cache
from urllib.parse import parse_qs

from access_control import AccessError
from vault import now


@lru_cache(maxsize=8)
def manifest(path, stamp):
    return json.loads(path.read_bytes())


def source(store, model):
    if not isinstance(model,str) or not re.fullmatch('[a-z0-9][a-z0-9_-]{0,63}',model):
        raise ValueError('模型编号无效')
    root = store.root/'models'/model/'editor'
    path = root/'index.json'
    if not path.is_file():
        raise ValueError('该模型的网页审查数据尚未准备好')
    data = manifest(path, path.stat().st_mtime_ns)
    return root, data


def get(req, store, path):
    if path=='/api/nwd/models':
        models=[]
        for file in sorted((store.root/'models').glob('*/editor/index.json')):
            model=file.parent.parent.name
            _,index=source(store,model)
            info_path=file.parent.parent/'info.json'
            info=json.loads(info_path.read_bytes()) if info_path.is_file() else {}
            models.append(dict(id=model,name=index.get('name') or info.get('name',model),
                               source=index.get('sourceFile') or info.get('source',model),
                               view=info.get('view') or index.get('view')))
        return req.send(models)
    query = parse_qs(req.path.partition('?')[2])
    model = query.get('model',['l'])[0]
    root, index = source(store,model)
    if path=='/api/nwd/index':
        return req.cached((model,(root/'index.json').stat().st_mtime_ns),lambda:index,'application/json')
    if path=='/api/nwd/asset':
        key = query.get('id',[''])[0]
        if not re.fullmatch('[0-9a-f]{64}',key) or not (root/(key+'.gz')).is_file():
            return req.send({'error':'找不到模型分块'},404)
        file = root/(key+'.gz')
        etag = '"'+key+'"'
        headers = {'ETag':etag,'Cache-Control':'private, max-age=31536000, immutable','Vary':'Cookie, Accept-Encoding'}
        if req.headers.get('If-None-Match')==etag:
            req.send_response(304)
            for k,v in headers.items():
                req.send_header(k,v)
            return req.end_headers()
        packed = file.read_bytes()
        if re.search(r'(?:^|,)\s*gzip\s*(?:,|$)',req.headers.get('Accept-Encoding',''),re.I):
            headers['Content-Encoding']='gzip'
        else:
            packed=gzip.decompress(packed)
        return req.send(packed,ctype='application/json' if key==index['tree'] else 'application/octet-stream',headers=headers)
    if path=='/api/nwd/scene':
        revision = query.get('rev',['latest'])[0]
        where = 'model=? AND digest=?'
        args = [model,index['digest']]
        if revision!='latest':
            where += ' AND revision=?'
            args.append(int(revision))
        with contextlib.closing(store.connect()) as db:
            row=db.execute('SELECT revision,document,stamp FROM nwd_scenes WHERE '+where+' ORDER BY revision DESC LIMIT 1',args).fetchone()
        if row:
            return req.send(dict(revision=row[0],scene=json.loads(row[1]),stamp=row[2]))
        if revision not in ('latest','0'):
            return req.send({'error':'该发布版本不存在'},404)
        return req.send(dict(revision=0,scene={},stamp=None))
    return req.send({'error':'未知的审查请求'},404)


def vector(value):
    if not isinstance(value,list) or len(value)!=3 or not all(type(i) in (float,int) and math.isfinite(i) and abs(i)<1e8 for i in value):
        raise ValueError('坐标无效')
    return value


def camera(data):
    result={k:vector(data[k]) for k in ('eye','target','up')}
    fov=data['fov']
    if type(fov) not in (int,float) or not 1<=fov<=175 or math.dist(result['eye'],result['target'])<1e-7 or math.hypot(*result['up'])<.01:
        raise ValueError('相机参数无效')
    return dict(result,fov=fov)


def node_ids(ids,nodes):
    if not isinstance(ids,list) or any(type(i)!=int or not 0<=i<nodes for i in ids):
        raise ValueError('模型节点无效')
    return sorted(set(ids))


def section_plane(section):
    if section is None:
        return None
    if not isinstance(section,dict) or section.get('axis') not in ('x','y','z') or type(section.get('value')) not in (int,float) or not math.isfinite(section['value']):
        raise ValueError('剖切面无效')
    return {'axis':section['axis'],'value':section['value']}


def copy_environment(source, target):
    if 'environment' in source:
        name = source['environment']
        if name not in ('overview','all','top','deck','lower','equipment','pipe'):
            raise ValueError('模型显示环境无效')
        target['environment'] = name


def clean_scene(scene,nodes):
    if not isinstance(scene,dict):
        raise ValueError('审查版本无效')
    result={key:node_ids(scene.get(key,[]),nodes) for key in ('hidden','removed')}
    names=scene.get('names',{})
    if not isinstance(names,dict):raise ValueError('构件名称无效')
    if names:
        result['names']={}
        for key,value in names.items():
            if not isinstance(key,str) or not re.fullmatch(r'0|[1-9][0-9]{0,9}',key) or int(key)>=nodes:
                raise ValueError('名称对应的构件无效')
            if not isinstance(value,str) or not 0<len(value.strip())<=120:
                raise ValueError('构件名称须为 1 到 120 个字符')
            result['names'][key]=value.strip()
    result['camera']=camera(scene['camera'])
    copy_environment(scene, result)
    result['views']=[clean_view(v,nodes) for v in scene.get('views',[])]
    result['notes']=[clean_note(v) for v in scene.get('notes',[])]
    result['section']=section_plane(scene.get('section'))
    return result


def clean_view(view,nodes):
    name=view['name']
    if not isinstance(name,str) or not 0<len(name.strip())<=120:
        raise ValueError('视图名称无效')
    item=dict(name=name.strip(),camera=camera(view['camera']))
    copy_environment(view, item)
    if 'hidden' in view:
        item.update(hidden=node_ids(view['hidden'],nodes),section=section_plane(view.get('section')))
    if 'focus' in view:
        item['focus'] = node_ids([view['focus']], nodes)[0]
        if type(view.get('context', True)) is not bool:
            raise ValueError('视图线稿状态无效')
        item['context'] = view.get('context', True)
    return item


def clean_note(mark):
    label=mark['text']
    if not isinstance(label,str) or not 0<len(label.strip())<=300:
        raise ValueError('标记内容无效')
    return dict(text=label.strip(),point=vector(mark['point']))


def credit_entries(submitted, cleaned, previous, session):
    # Old clients may resubmit records without IDs. Match each old occurrence
    # at most once. An unknown historical author stays unknown.
    for key in ('notes','views'):
        prior_by_id = {item['id']: item for item in previous.get(key, []) if 'id' in item}
        by_value = defaultdict(deque)
        def content(item):
            def freeze(value):
                if isinstance(value,dict):
                    return tuple(sorted((k,freeze(v)) for k,v in value.items()))
                if isinstance(value,list):
                    return tuple(freeze(v) for v in value)
                return value
            return freeze({k:v for k,v in item.items() if k not in ('id','author','authorLogin')})
        for item in previous.get(key, []):
            by_value[content(item)].append(item)
        seen = set()
        claimed = set()
        for raw, item in zip(submitted.get(key, []), cleaned[key]):
            token = raw.get('id')
            if token is not None:
                if not isinstance(token,str) or not re.fullmatch(r'[0-9a-f]{32}',token) or token in seen:
                    raise ValueError('审查记录编号无效')
                seen.add(token)
                item['id'] = token
                prior = prior_by_id.get(token)
            else:
                candidates = by_value[content(item)]
                while candidates and id(candidates[0]) in claimed:
                    candidates.popleft()
                prior = candidates.popleft() if candidates else None
            if prior is not None and content(prior) == content(item):
                if id(prior) in claimed:
                    raise ValueError('审查记录编号重复')
                claimed.add(id(prior))
                if 'id' in prior:
                    item['id'] = prior['id']
                if prior.get('authorLogin'):
                    item['authorLogin'] = prior['authorLogin']
                if prior.get('author'):
                    item['author'] = prior['author']
            else:
                item['author'] = session.get('name') or session['login']
                item['authorLogin'] = session['login']


def publish(store,data,session):
    if session.get('role')!='admin':
        raise AccessError('全平台模型的发布需要管理员权限',403)
    model=data['model']
    _,index=source(store,model)
    if data['digest']!=index['digest']:
        raise ValueError('源模型已更新，请重新打开')
    scene=clean_scene(data['scene'],index['nodes'])
    with store.transaction() as db:
        params=(model,index['digest'])
        prior=db.execute('SELECT revision,document FROM nwd_scenes WHERE model=? AND digest=? ORDER BY revision DESC LIMIT 1',params).fetchone()
        revision=prior[0] if prior else 0
        if data['base']!=revision:
            raise AccessError('已有新版本，请在新标签页核对后再发布',409)
        previous = json.loads(prior[1]) if prior else {}
        credit_entries(data['scene'],scene,previous,session)
        removed_views = data['scene'].get('removedViews',previous.get('removedViews',[]))
        if removed_views:
            scene['removedViews']=node_ids(removed_views,len(index.get('views',[])))
        db.execute('INSERT INTO nwd_scenes VALUES(?,?,?,?,?,?)',(*params,revision+1,json.dumps(scene,ensure_ascii=False),session['login'],now()))
    return dict(revision=revision+1)

def edit_entry(store, data, session):
    """Named reviewers can change their own contributions to the current model."""
    login = session.get('login')
    if session.get('role') != 'editor' or not login:
        raise AccessError('请使用专业编辑账号', 403)
    model, kind, action = data['model'], data['kind'], data['action']
    _, index = source(store, model)
    if index['digest'] != data['digest']:
        raise AccessError('源模型已更新，请重新打开', 409)
    ident = data['id']
    if kind not in ('notes','views') or action not in ('add','delete') or not isinstance(ident,str) or not re.fullmatch('[0-9a-f]{32}',ident):
        raise ValueError('审查记录参数无效')
    with store.transaction() as db:
        key = (model,index['digest'])
        prior = db.execute('SELECT revision,document FROM nwd_scenes WHERE model=? AND digest=? ORDER BY revision DESC LIMIT 1',key).fetchone()
        revision = prior[0] if prior else 0
        if revision != data['base']:
            raise AccessError('审查版本已更新，请刷新后重试',409)
        scene = json.loads(prior[1]) if prior else {}
        entries = scene.setdefault(kind,[])
        existing = next((v for v in entries if v.get('id') == ident),None)
        if action == 'add':
            if existing is not None:
                raise ValueError('审查记录已存在')
            entry = clean_note(data['entry']) if kind == 'notes' else clean_view(data['entry'],index['nodes'])
            entry.update(id=ident,authorLogin=login,author=session.get('name') or login)
            entries.append(entry)
        else:
            if existing is None or existing.get('authorLogin') != login:
                raise AccessError('仅可删除本人创建的记录',403)
            entries.remove(existing)
        db.execute('INSERT INTO nwd_scenes VALUES(?,?,?,?,?,?)',(*key,revision+1,json.dumps(scene,ensure_ascii=False),login,now()))
        return dict(revision=revision+1,entries=entries)
