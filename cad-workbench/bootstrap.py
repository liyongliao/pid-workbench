"""Create an OS-local Python runtime after relocating the project."""
from pathlib import Path
import os,platform,subprocess,sys
BASE=Path(__file__).resolve().parent
if sys.version_info<(3,12):raise SystemExit('需要 Python 3.12 或更新版本。')
folder=BASE/'.runtime'/(sys.platform+'-'+platform.machine().lower());python=folder/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
if not python.exists():subprocess.run([sys.executable,'-m','venv',str(folder)],check=True)
requirements=BASE/'requirements.txt';marker=folder/'requirements.installed'
if not marker.exists() or marker.read_bytes()!=requirements.read_bytes():
 print('首次启动：正在安装本机 Python 依赖，之后启动无需重复安装。',flush=True)
 subprocess.run([str(python),'-m','pip','install','-r',str(requirements)],check=True);marker.write_bytes(requirements.read_bytes())
subprocess.run([str(python),'-X','utf8',str(BASE/'launch.py')],check=True,env=dict(os.environ,PYTHONUTF8='1'))
