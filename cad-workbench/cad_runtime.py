"""Platform-aware CAD runtime. Reading indexed drawings and drafting need no converter."""
from pathlib import Path
import os,platform,shutil,subprocess
BASE=Path(__file__).resolve().parent

def native_compatible(path,system,arch):
 if system!='Darwin':return True
 try:
  with path.open('rb') as f:header=f.read(8)
  if header[:4]==b'\xcf\xfa\xed\xfe':return int.from_bytes(header[4:8],'little')=={'arm64':0x100000c,'x86_64':0x1000007}.get(arch)
 except OSError:return False
 return True

def converter_status():
 system=platform.system();arch=platform.machine().lower();arch={'aarch64':'arm64','amd64':'x86_64'}.get(arch,arch)
 override=os.environ.get('PID_DWG_CONVERTER')
 candidates=[]
 if override:candidates=[Path(override).expanduser()]
 elif not os.environ.get('PID_DISABLE_DWG_CONVERTER'):
  folder=BASE/'tools/converters'/f'{system.lower()}-{arch}'
  candidates=[folder/'ODAFileConverter.exe'] if system=='Windows' else [folder/'ODAFileConverter',folder/'ODAFileConverter.AppImage',folder/'ODAFileConverter.app/Contents/MacOS/ODAFileConverter']
  if system=='Darwin':candidates.append(BASE/'tools/ODAFileConverter.app/Contents/MacOS/ODAFileConverter')
  found=shutil.which('ODAFileConverter')
  if found:candidates.append(Path(found))
 path=next((p.resolve() for p in candidates if p.is_file() and (system=='Windows' or os.access(p,os.X_OK)) and native_compatible(p,system,arch)),None)
 bundled=bool(path and path.is_relative_to(BASE/'tools'))
 return {'available':bool(path),'bundled':bundled,'platform':system,'architecture':arch,'path':str(path) if path else None,'name':'内置 DWG 引擎' if bundled else '已配置 DWG 引擎' if path else '未配置 DWG 引擎','message':'统一保存时批量生成并校验 DWG' if path else '当前环境可浏览图纸和暂存修改；生成 DWG 需要此平台的转换运行包。'}

def convert(src,dst,kind,pattern):
 status=converter_status()
 if not status['available']:raise ValueError(status['message'])
 Path(dst).mkdir(parents=True,exist_ok=True)
 try:subprocess.run([status['path'],str(Path(src).resolve()),str(Path(dst).resolve()),'ACAD2018',kind,'0','0',pattern],check=True,timeout=300,cwd=str(Path(status['path']).parent))
 except (subprocess.SubprocessError,OSError) as ex:raise RuntimeError('DWG 引擎执行失败，正式图纸未替换；请检查运行包后重试。') from ex

def drawing_font():
 supplied=os.environ.get('PID_CAD_FONT')
 candidates=[Path(supplied)] if supplied else [Path('/System/Library/Fonts/Supplemental/Arial Unicode.ttf'),BASE/'tools/fonts/NotoSansCJKsc-Regular.otf']
 font=next((p for p in candidates if p.is_file()),None)
 if font is None:raise ValueError('未找到中文字体，请保留 tools/fonts 随系统迁移，或设置 PID_CAD_FONT')
 return str(font)
