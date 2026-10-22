"""Offline recovery. Stop the workbench service before running this script."""
from pathlib import Path
import getpass,sys
BASE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(BASE))
from workspace import data_root
from access_control import AccessControl,password_record,verify,AccessError

def main():
 print('本机密码恢复：请先停止图纸工作台服务，修改完成后重新启动。')
 if input('确认服务已停止？输入 YES 继续：').strip()!='YES':return
 auth=AccessControl(data_root())
 if not auth.config:print('尚未设置密码，请启动服务后在本机网页完成首次设置。');return
 password=getpass.getpass('新管理员密码（至少 8 个字符）：')
 if password!=getpass.getpass('再次输入新管理员密码：'):raise AccessError('两次密码不一致')
 if verify(password,auth.config['passwords']['viewer']):raise AccessError('管理员与普通用户密码必须不同')
 config=auth.config;config['passwords']['admin']=password_record(password);auth.write(config)
 print('管理员密码已重置，请重新启动服务。')
if __name__=='__main__':
 try:main()
 except (AccessError,EOFError,KeyboardInterrupt) as ex:print(str(ex) or '已取消');sys.exit(1)
