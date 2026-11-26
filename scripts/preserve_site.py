"""Copy legacy private extensions into a vault, without overwriting existing files."""
import argparse,shutil
from pathlib import Path
FILES=('project-settings.js','test-separator.js','gas-cooler.js','process-assembly.js','deck-drain-assembly.js','fire-pump-assembly.js')
def preserve(source,vault):
    source,vault=Path(source),Path(vault)
    if not (source/'static/project-settings.js').is_file():raise ValueError('源目录缺少 static/project-settings.js，请从原项目备份补齐，不能只复制装配脚本')
    pairs=[(source/'static'/n,vault/'site/static'/n) for n in FILES if (source/'static'/n).is_file()]
    if (source/'project_assemblies.py').is_file():pairs.append((source/'project_assemblies.py',vault/'site/project_assemblies.py'))
    for src,dst in pairs:
        if dst.exists() and dst.read_bytes()!=src.read_bytes():raise ValueError('目标已有不同版本，未覆盖：'+str(dst))
    for src,dst in pairs:
        dst.parent.mkdir(parents=True,exist_ok=True)
        if not dst.exists():shutil.copy2(src,dst)
    return len(pairs)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('source');p.add_argument('vault');a=p.parse_args()
    print('已保留',preserve(a.source,a.vault),'个项目配置文件')
