"""Interactive Docker setup; only creates a new instance, never rewrites one."""
import argparse,json,os,subprocess,re,hashlib
from pathlib import Path
from urllib.parse import urlsplit

def origins(value):
    entries=value.split(',')
    if any(urlsplit(v).scheme not in ('http','https') or not urlsplit(v).hostname or urlsplit(v).path not in ('','/') or urlsplit(v).query or urlsplit(v).fragment or urlsplit(v).username for v in entries):
        raise ValueError('访问地址应为 http(s)://主机:端口，不能包含路径或账号')
    return ','.join(v.rstrip('/') for v in entries)

def main():
    p=argparse.ArgumentParser(description='创建新的 Docker 图纸工作台实例')
    p.add_argument('--origin');p.add_argument('--engine',default='');p.add_argument('--directory',default='./instance');p.add_argument('--port',type=int,default=8765);p.add_argument('--dry-run',action='store_true')
    args=p.parse_args()
    if not 1<=args.port<=65535:raise ValueError('端口须在 1–65535 之间')
    origin=origins(args.origin or input('浏览器访问地址（例如 http://192.168.1.20:8765）：').strip())
    instance=Path(args.directory).expanduser().resolve()
    if instance.exists() and any(instance.iterdir()):raise ValueError('实例目录不是空目录；更新已有项目请按 README 操作')
    engine=Path(args.engine).expanduser().resolve() if args.engine else instance/'engine'
    if args.engine and not (engine/'ODAFileConverter').is_file():raise ValueError('转换器目录内未找到 ODAFileConverter，请选择完整运行目录')
    values=dict(PID_VAULT_DIR=str(instance/'vault'),PID_ENGINE_DIR=str(engine),PID_BIND_IP='0.0.0.0',PID_PUBLISHED_PORT=str(args.port),PID_PUBLIC_ORIGINS=origin)
    if any(any(c in v for c in '\n\r$`') for v in values.values()):raise ValueError('配置值包含不支持的字符')
    repo=Path(__file__).resolve().parents[1]
    project='pid-'+(re.sub('[^a-z0-9_-]+','-',instance.name.lower()).strip('-') or 'instance')+'-'+hashlib.sha256(str(instance).encode()).hexdigest()[:8]
    cmd=['docker','compose','--project-name',project,'--env-file',str(instance/'.env'),'-f',str(repo/'compose.yaml')]
    if args.dry_run:
        print(json.dumps(dict(environment=values,commands=[cmd+['build'],cmd+['up','-d','--wait']]),ensure_ascii=False,indent=2));return
    subprocess.run(['docker','compose','version'],check=True)
    instance.mkdir(parents=True,exist_ok=True);(instance/'vault').mkdir()
    if not args.engine:engine.mkdir()
    with (instance/'.env').open('x') as f:
        for k,v in values.items():f.write(k+'='+json.dumps(v)+'\n')
    os.chmod(instance/'.env',0o600)
    subprocess.run(cmd+['config','--quiet'],check=True)
    subprocess.run(cmd+['build'],check=True)
    # Only change ownership of the newly created empty vault.
    subprocess.run(cmd+['run','--rm','--no-deps','--user','0','workbench','chown','1000:1000','/vault'],check=True)
    subprocess.run(cmd+['up','-d','--wait'],check=True)
    print('启动完成。请打开 '+origin.split(',')[0]+' ，安装码位于 '+str(instance/'vault/data/setup-token.txt'))
    if not args.engine:print('未安装 DWG 转换器：可完成设置与查看已有资料；导入 DWG 前请补齐转换器配置。')

if __name__=='__main__':
    try:main()
    except (ValueError,subprocess.CalledProcessError) as e:raise SystemExit(str(e))
