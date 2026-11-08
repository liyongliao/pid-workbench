# 在 NAS 的 Docker 中运行

Docker 镜像只包含程序。原始图纸的上级目录挂到 `/library`（只读）；其中的 `cad-workbench/` 单独可写，保存索引、中文副本、密码与草稿。目录必须事先存在，运行用户 UID/GID 1000 需有相应权限。若迁移已有库，停旧服务后完整复制，保留源 DWG 与 manifest 中的相对位置。

**构建：** 在仓库根目录执行。浏览已有库可用 `docker build --target viewer -t pid-workbench:2.3.0-fnos .`。如需导入和统一保存 DWG，Intel/AMD 64 位 NAS 使用完整版本：
从 [ODA](https://www.opendesign.com/guestfiles/oda_file_converter) 获取 Linux x64 DEB，放在 `docker/runtime/oda.deb`；将 Noto Sans CJK SC 字体及对应许可证放为 `docker/runtime/NotoSansCJKsc-Regular.otf`、`docker/runtime/OFL.txt`，再执行：

```sh
docker build --platform linux/amd64 --target cad -t pid-workbench:2.3.0-fnos .
```

上述本机运行包不提交 Git。可选 `--build-context wheels=/path/to/verified/wheels` 从已校验的目标架构 wheel 目录离线安装 Python 依赖。若 NAS 离线，可在同架构或支持 linux/amd64 构建的电脑制作镜像，使用 Docker save/load 传至 NAS；无需把镜像推到公共仓库。

**启动：** 在 compose.yaml 旁创建本机 .env，设置 PID_LIBRARY_DIR（原始图纸上级目录）、PID_BIND_IP（NAS 局域网地址）、PID_PUBLISHED_PORT（例如 8765）、PID_PUBLIC_ORIGINS（浏览器实际使用的完整来源，例如 http://192.0.2.10:8765）。只填写可信来源，不支持通配符。然后运行：

```sh
docker compose config --quiet
docker compose up -d
docker compose ps
```

迁移已有库时沿用原访问密码。空库的首次密码只能在容器本机设置，可从 NAS 终端进入服务执行：

```sh
docker compose exec workbench python -c 'import getpass,json,urllib.request; a=getpass.getpass("管理员新密码："); v=getpass.getpass("普通用户新密码："); req=urllib.request.Request("http://127.0.0.1:8765/api/auth/setup",data=json.dumps({"adminPassword":a,"viewerPassword":v}).encode(),headers={"Content-Type":"application/json"});print(urllib.request.urlopen(req).status)'
```

只读验收脚本 `scripts/verify_library.py /path/to/library/cad-workbench` 逐一比对 DWG SHA-256，检查中文产物和索引关联。备份库时保留数据目录和全部原始相对路径；更新容器无需覆盖图纸库。
