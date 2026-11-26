"""Project-owned installation settings, independent of drawing revisions."""
import copy
import json
import os
import re
import threading
from pathlib import Path
from access_control import AccessError

DEFAULT_TEAMS = ('工艺', '动力', '机械', '电气')
FEATURES = ('drawings', 'equipment', 'models', 'logic', 'schematic')
LOCK = threading.RLock()


def root_path(base=None):
    return Path(os.environ.get('PID_VAULT') or base or os.environ.get('PID_DATA_ROOT') or Path(__file__).parent)


def read(base=None):
    root = root_path(base)
    file = root / 'data/system-settings.json'
    defaults = dict(version=1, revision=0, systemName='工程图纸管理系统', projectName='工程资料中心',
                    description='集中管理图纸、专业与模型，让工程资料更易查找。', setupComplete=False,
                    teams=[dict(name=t, enabled=True, tagFields=[], searchFields=[]) for t in DEFAULT_TEAMS],
                    features={key: 'off' if key == 'schematic' else 'auto' for key in FEATURES})
    if file.is_file():
        defaults.update(json.loads(file.read_text(encoding='utf-8')))
    else:
        # Existing installations are not forced back through account creation.
        defaults['setupComplete'] = (root / 'data/access-control.json').is_file()
    return defaults


def team_names(base=None, include_disabled=False):
    return [t['name'] for t in read(base)['teams'] if include_disabled or t['enabled']]


def public(base=None):
    data = read(base)
    return {key: data[key] for key in ('systemName', 'projectName', 'description')}


def validate(data):
    out = {}
    for key, title, limit in [('systemName', '系统名称', 40), ('projectName', '项目名称', 60), ('description', '欢迎说明', 180)]:
        value = data.get(key)
        if not isinstance(value, str) or not value.strip() or len(value.strip()) > limit or not value.isprintable():
            raise ValueError(f'{title}请填写 1–{limit} 个可显示字符')
        out[key] = value.strip()
    teams = data.get('teams')
    if not isinstance(teams, list) or not 1 <= len(teams) <= 30:
        raise ValueError('请设置 1–30 个专业')
    out['teams'] = []
    for team in teams:
        if not isinstance(team, dict):raise ValueError('专业配置格式无效')
        name = team.get('name')
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 24 or not name.isprintable():
            raise ValueError('专业名称请填写 1–24 个可显示字符')
        name = name.strip()
        if name in [t['name'] for t in out['teams']]:raise ValueError('专业名称不能重复：' + name)
        if type(team.get('enabled')) is not bool:raise ValueError('请选择专业是否启用')
        cleaned = dict(name=name, enabled=team['enabled'])
        for key in ('tagFields', 'searchFields'):
            fields = team.get(key, [])
            if not isinstance(fields, list) or len(fields) > 30 or any(not isinstance(f, str) or not re.fullmatch(r'[\w.$-]{1,64}', f) for f in fields):
                raise ValueError('CAD 属性名只能包含文字、数字、下划线、点、短横线或 $')
            cleaned[key] = list(dict.fromkeys(fields))
        out['teams'].append(cleaned)
    if not any(t['enabled'] for t in out['teams']):raise ValueError('请至少启用一个专业')
    modes = data.get('features')
    if not isinstance(modes, dict) or set(modes) != set(FEATURES) or any(m not in ('auto', 'off') for m in modes.values()):
        raise ValueError('功能设置无效，请选择按资料自动启用或关闭')
    out['features'] = copy.deepcopy(modes)
    return out


def save(base, data, catalog=()):
    with LOCK:
        current = read(base)
        if data.get('revision') != current['revision']:raise AccessError('设置已被其他管理员更新，请刷新后重新修改', 409)
        out = validate(data)
        names = {t['name'] for t in out['teams']}
        # Keep names stable for existing drawings and authorizations; disable instead.
        removed = {t['name'] for t in current['teams']} - names
        if removed:raise ValueError('已有专业请使用停用，不能直接删除或改名：' + '、'.join(sorted(removed)))
        out.update(version=1, revision=current['revision'] + 1,
                   setupComplete=current['setupComplete'] or data.get('complete') is True)
        write(base, out)
        return out


def write(base, data):
    file = root_path(base) / 'data/system-settings.json'
    file.parent.mkdir(parents=True, exist_ok=True)
    temp = file.with_suffix('.tmp')
    with temp.open('w', encoding='utf-8') as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
        stream.flush(); os.fsync(stream.fileno())
    os.replace(temp, file)


def begin(base):
    with LOCK:
        settings = read(base)
        settings['setupComplete'] = False
        write(base, settings)


def capabilities(manager):
    root = manager.vault.root if getattr(manager, 'vault', None) else manager.base
    settings = read(root)
    catalog = manager.catalog
    models = list((root / 'models').glob('*/editor/index.json'))
    platform_models = list((root / 'models').glob('[kl]/info.json'))
    logic_file = manager.base / 'data/logic.json'
    logic = json.loads(logic_file.read_text(encoding='utf-8')) if logic_file.is_file() else {}
    available = dict(drawings=bool(catalog), equipment=any(r.get('equipment') for r in catalog),
                     models=bool(models), logic=bool(logic.get('causes') or logic.get('effects')), schematic=bool(catalog))
    enabled = {key: available[key] and settings['features'][key] == 'auto' for key in FEATURES}
    enabled['equipment'] &= enabled['drawings']
    enabled['schematic'] &= enabled['drawings']
    return dict(enabled=enabled, available=available, drawingCount=len(catalog), modelCount=len(models),
                modelPolicy=settings['features']['models'], linkedModels=bool(platform_models) and settings['features']['models']=='auto',
                hasLegends=(root/'legends/catalog.json').is_file(), teams=settings['teams'], setupRequired=not settings['setupComplete'],
                **public(root))
