# 工程图纸与模型工作台

一个面向工程资料管理的自托管网页系统。把 CAD 图纸、设备位号、专业权限和三维模型集中在同一个工作台，使用者通过浏览器查图、检索、查看关联和维护资料，无需安装 CAD 软件。

支持按项目设置系统名称和专业，可用于不同工程或单位。源码仓库不包含任何现场图纸、模型、账号、密码、专用装配配置或商业 DWG 转换器。

## 可以做什么

- 首次访问通过五步网页向导创建管理员、设置名称、配置专业、导入资料并确认功能。
- 上传 DWG，生成浏览视图、设备索引和跨图关联，原件独立保存。支持逐张批量导入。
- 图纸查看、位号搜索、专业筛选、收藏与打印；已访问图纸在页面内按版本缓存。
- 为编辑账号分配专业权限，修改块属性并发布修订，保留修改记录。
- 导入支持的 NWD 或 GLB，浏览模型、保存审查视图和批注。模型分块支持浏览器缓存。
- 没有对应资料时不开放相关功能；系统设置中也可手动关闭。三维示意默认关闭。

工艺、动力、机械、电气为内置专业，可新增仪表、土建等专业。高级 CAD 字段规则仍可放在资料盘的 `profiles.json`。因果逻辑沿用项目已有的数据导入流程，尚不支持任意格式因果表的一键识别。

## 部署前准备

推荐 **Linux x86-64 / NAS + Docker Engine 与 Compose v2**。程序分两个容器：

| 容器 | 职责 |
| --- | --- |
| `workbench` | 网页、登录、查询、配置和任务提交 |
| `worker` | DWG 转换与回读校验、模型后台处理 |

两个容器共享同一个资料盘；“后台在线”不代表 DWG 引擎已配置。

准备可写的本地磁盘目录，避免将 SQLite 工作库放在 SMB/NFS。首次构建需要联网下载基础镜像和依赖。Linux ARM64 当前采用 amd64 镜像，需宿主支持模拟运行，速度与兼容性需自行验证。

**DWG 导入需要单独安装经授权的 Linux x64 ODA File Converter。** 挂载的是完整运行目录，内含可执行的 `ODAFileConverter`、Qt 库及插件，不能只复制一个可执行文件。程序镜像提供中文字体与启动器。没有转换器也能完成网页初始化、查看已入库资料，DWG 导入暂不可用。

## 方式一：Linux 引导安装

在已安装 Docker、Compose 和 Python 3 的服务器上执行：

```sh
git clone https://github.com/liyongliao/pid-workbench.git
cd pid-workbench
bash scripts/install-linux.sh
```

按提示输入浏览器访问地址，例如 `http://192.168.1.20:8765`。脚本创建新的 `instance` 目录，生成 `.env`、构建两个镜像并启动服务。若 Docker 需要管理员权限，可用 `sudo bash scripts/install-linux.sh`。

已有转换器时，可以一次传入配置：

```sh
bash scripts/install-linux.sh \
  --origin 'http://192.168.1.20:8765,https://drawings.example.com' \
  --engine /opt/ODAFileConverter \
  --directory /srv/drawing-workbench \
  --port 8765
```

加 `--dry-run` 可只查看生成的配置与命令，不创建目录、不启动服务。脚本拒绝使用非空实例目录，避免把“新建项目”当成“升级项目”。未传 `--engine` 时创建空引擎目录，后续修改实例 `.env` 中的 `PID_ENGINE_DIR` 并重建 worker 即可。

启动后，在资料盘 `data/setup-token.txt` 读取一次性安装码，打开所配置的网址，按网页完成初始化。请由部署人员把安装码交给项目管理员；管理员创建成功后安装码文件删除。新项目不需要恢复任何旧资料盘。

## 方式二：手动 Docker / NAS Compose 部署

下载或克隆本仓库。创建一个新的空资料盘，准备 `.env`（放在仓库根目录）：

```dotenv
PID_VAULT_DIR=/srv/drawing-workbench/vault
PID_ENGINE_DIR=/opt/ODAFileConverter
PID_BIND_IP=0.0.0.0
PID_PUBLISHED_PORT=8765
PID_PUBLIC_ORIGINS=http://192.168.1.20:8765,https://drawings.example.com
```

```sh
mkdir -p /srv/drawing-workbench/vault
sudo chown 1000:1000 /srv/drawing-workbench/vault
docker compose config --quiet
docker compose build
docker compose up -d --wait
docker compose ps
```

只给新建资料盘调整权限，不要对已有项目或整个磁盘递归修改权限。没有转换器时可以先创建空目录作为 `PID_ENGINE_DIR`，完成其他设置。NAS 的 Compose 项目界面也可加载本仓库的 `compose.yaml` 与上述环境变量。

已有离线镜像时可先 `docker load -i workbench-linux-amd64.tar.gz`，再执行 `docker compose up -d --no-build`。镜像标签必须与 Compose 的版本一致；GitHub 源码不等于已发布的镜像或离线安装包，本仓库默认从源码构建。

### Lucky / HTTPS 反向代理

`PID_PUBLIC_ORIGINS` 必须包含浏览器真正访问的完整来源，包括协议和非默认端口。例如：

```dotenv
PID_PUBLIC_ORIGINS=http://192.168.1.20:8765,https://drawings.example.com:8880
```

代理上游使用已配置的内部主机地址。不要把 `/login` 等路径写入来源，不要使用 `*` 或关闭来源校验。更改 `.env` 后执行 `docker compose up -d --force-recreate workbench`，仅重启旧容器不会更新环境变量。

## 首次使用

1. 用安装码创建管理员，并设置普通查看用户的共享密码。
2. 设置系统名称、项目名称和欢迎说明。
3. 选择或新增专业；需要时配置设备位号与搜索属性名。
4. 导入 DWG 或模型，也可以稍后再导入。DWG 每张最大 64 MB；NWD / GLB 最大 2 GB。
5. 确认功能状态并进入工作台。管理员之后可从顶部“系统设置”继续维护。

原图、账号、修订及设置都保存在资料盘。导入 NWD 的支持范围取决于文件布局，无法解析时会保留原件并显示原因，不保证所有 Navisworks 特性均可导入。

## 更新、备份与项目精细模型

**更新程序使用完整镜像构建，不要在旧容器内清空 `/opt/workbench` 再覆盖源码。** 旧版本将 DWG 启动器放在程序目录，这种增量更新会误删启动器。3.5.1 起启动器位于 `/usr/local/bin/pid-oda-headless`，独立于程序目录。

更新前做一致性备份，目标必须是独立的新目录；发布任务进行中备份工具会拒绝执行：

```sh
docker compose run --rm --no-deps \
  -v /srv/workbench-backups:/backups \
  workbench python backup.py backup /vault /backups/before-update

git pull --ff-only
docker compose build
docker compose up -d --wait
```

使用引导安装的实例时，上述 Compose 命令要加上同样的 `--project-name` 和 `--env-file /实例目录/.env`，与脚本 dry-run 输出一致。保留旧镜像、配置和备份，回退时使用原版本与对应备份，不能把不同现场修改的资料盘直接互相覆盖。

### 专用精细模型为什么可能不显示

整个平台模型、逐图发布记录与专门编写的装配脚本是不同资料。仅保留 GLB 或几个 `*-assembly.js`，不代表已经完整保留现场精细模型。特别需要保留 `project-settings.js`，它注册图号、视角及装配加载方法。

从 3.5.1 起推荐把项目私有扩展放在资料盘内：

```text
vault/
  site/
    project_assemblies.py          # 可选的项目规则
    static/
      project-settings.js         # 项目注册入口
      test-separator.js           # 示例：现场私有装配模块
      ...                         # 注册入口依赖的模块
  models/                         # 模型、构件库与派生资源
  data/                           # 账号与系统配置
  revisions/                      # 图纸修订
  workbench.sqlite3               # 发布记录等
```

迁移旧项目的扩展时，在有原始项目目录的机器执行：

```sh
python3 scripts/preserve_site.py /旧项目/cad-workbench /目标资料盘
```

工具会保留已知项目扩展，缺少注册入口或目标有不同版本时拒绝覆盖。此脚本不复制图纸、模型或数据库，完整迁移仍需资料盘备份。资料盘内 `site`、`models` 和 `legends` 都纳入备份。项目扩展属于可信管理员维护的代码，不应接受普通用户上传的任意脚本，也不应提交到公共仓库。

## 常见问题

| 现象 | 检查方法 |
| --- | --- |
| 两个容器在线，仍显示引擎未配置 | 在 worker 内检查 `test -x /usr/local/bin/pid-oda-headless`、`test -x /engine/ODAFileConverter`；检查实际挂载目录及权限。不能只看 `build.txt` 的版本号。 |
| 引擎和字体存在，自检仍失败 | 查看 `docker compose logs --tail 100 worker` 和运行环境中的自检结果，排查共享库、Qt 插件与转换器平台。 |
| 精细模型消失 | 检查 `site/static/project-settings.js` 及其依赖模块、图纸同版发布记录、模型构件库。不要用空通用安装包替换资料盘。 |
| 反代提示访问地址未通过校验 | 检查完整外部来源、端口与协议，保存环境变量后重建网页容器。 |
| 模型刷新仍需等待 | HTTPS / localhost 下可持久缓存内容分块，但解析和 GPU 上传仍需时间。浏览器空间不足、清理缓存或更换登录会话会重新下载。 |

## Mac 与 Windows

Mac 已有桌面安装继续使用原启动方式，并保留运行环境和资料盘。Mac 的 Docker 模式同样遵循上述配置，但 amd64 模拟运行可能较慢。

Windows 推荐 Docker Desktop 的 **Linux 容器模式**，通过终端或 Compose 界面按“手动 Docker 部署”操作，路径填写 Windows 上 Docker 可访问的绝对路径。使用 Linux 版 DWG 转换器，不能挂载 Windows EXE 作为 Linux 引擎。本次不新增原生 Windows 多进程部署脚本，避免把未验收的运行方式作为正式方案。

## 开发与验证

```sh
python -m pip install -r cad-workbench/requirements.txt
python -m unittest discover -s cad-workbench/tests -v
node --test tests/*.test.js
python scripts/check_source_only.py
```

真实 DWG 转换测试需额外配置本机转换器与字体并设置 `PID_TEST_DWG=1`。源码检查限制现场数据与凭据进入仓库。CI 检查通过不等于已经完成某台 NAS 的现场验收。
