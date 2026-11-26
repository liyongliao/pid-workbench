# Linux x86-64 离线部署

交付文件包括两个镜像、Compose 配置、示例环境设置和校验清单。宿主机需有 Docker Engine、Compose、本地磁盘和经授权的 Linux x64 DWG 引擎。程序和字体在镜像内。引擎由部署单位提供，单独只读挂载包含 ODAFileConverter、Qt 库及插件的完整版本目录。核实组织的生产使用许可后启用。工程图纸、账户和引擎二进制均不随软件分发。

1. 在发布包目录运行以下命令校验、装载镜像。复制 env.example 为 .env，填写资料盘和已安装引擎的绝对路径、监听 IP、端口和浏览器使用的完整来源。
```sh
sha256sum -c SHA256SUMS
docker load -i workbench-linux-amd64.tar.gz
cp env.example .env
```
2. 将一致性备份复制到目标机，准备一个本地目录供 UID/GID 1000 读写。在该目录下恢复为新的 vault。保留原备份直到完成验收。不要将 SQLite 工作库放在 SMB/NFS 共享上。
```sh
docker run --rm -v "/absolute/backup:/backup:ro" -v "/absolute/data:/restore" pid-workbench-web:3.2.0 python backup.py restore /backup /restore/vault
```
3. 将 PID_VAULT_DIR 设置为恢复后的目录。若是全新空库，可预先创建空目录并授予 UID 1000 写权限。确认配置后启动。
```sh
docker compose config --quiet
docker compose up -d --wait
docker compose ps
```
4. 恢复的图库沿用原有密码及实名账号。旧版迁入后的首次管理员登录，填写一个姓名或账号和现有管理员密码；此后按这个账号登录管理。空库可在容器本地使用下面的交互式命令初始化。
```sh
docker compose exec workbench python -c 'import getpass,json,urllib.request; data=dict(login=input("管理员姓名："),adminPassword=getpass.getpass("管理员密码："),viewerPassword=getpass.getpass("普通用户密码：")); req=urllib.request.Request("http://127.0.0.1:8765/api/auth/setup",data=json.dumps(data).encode(),headers={"Content-Type":"application/json"}); print(urllib.request.urlopen(req).status)'
```
5. 管理员打开“运行环境”，核对后台在线、引擎版本和 DWG 自检。核对目录数、历史和关键跨图跳转；在演练库上传测试 DWG、修改块属性并统一保存后再正式切换。NAS 与 Mac 有独立修改时先逐图比较哈希、修订和审计记录，不能整库覆盖合并。

## 备份与回退

备份命令在资料盘外创建一个新目录。它拒绝在途发布，并备份同一时间点的 SQLite、原件、修订与访问设置。备份包含账户校验值，限制读取权限。通过新的空目录恢复并校验所有文件。
```sh
docker compose run --rm --no-deps -v "/absolute/backups:/backups" workbench python backup.py backup /vault /backups/accepted-001
```
如需回退整个发行版本，停止本项目的两个服务，使用对应的旧镜像和切换前的数据备份。业务上的属性回滚使用网页“图纸修订”，保留回滚人和历史。保留充足空间：每次发布保留一个图库修订目录，支持文件系统克隆的磁盘优先复用数据块。

## 从源码构建

将 Noto 中文字体及 OFL 许可证放入 docker/runtime，分别用 Dockerfile 的 viewer 和 cad 目标构建 pid-workbench-web:3.2.0 与 pid-workbench-worker:3.2.0。指定 --platform linux/amd64。离线分发可使用 docker save 同时导出两个标签，不需访问公共镜像仓库。已有原件与旧版 data/output/uploads/reports 位于原来相对位置时，在停写副本运行 python migrate.py 旧工作台目录 新资料盘目录。
