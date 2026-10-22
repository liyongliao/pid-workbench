"""Read-only administrator checks; never convert drawings or disclose passwords."""
import platform,shutil,sys,os
from workspace import VERSION
from cad_runtime import converter_status,drawing_font

def snapshot(manager):
 runtime=converter_status()
 try:font=drawing_font();font_status={'available':True,'path':font}
 except ValueError as error:font_status={'available':False,'message':str(error)}
 writable=os.access(manager.base/'data',os.W_OK)
 return {'version':VERSION,'python':platform.python_version(),'platform':platform.system(),'architecture':platform.machine(),'converter':runtime,'font':font_status,'dataDirectory':str(manager.base),'writable':writable,'freeBytes':shutil.disk_usage(manager.base).free,'drawingCount':len(manager.catalog),'missingCount':manager.report['missingUnique'],'canImport':runtime['available'] and font_status['available'] and writable,'notes':['查看已导入图纸无需 DWG 引擎。','上传与统一保存需 DWG 引擎及中文字体。','升级程序时保留 data、output 和 uploads；这些目录不会提交 Git。']}
