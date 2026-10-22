# PID 图纸工作台

本地运行的中文 CAD 图纸查看与管理系统。读取 DWG 原始图元，建立设备查询、跨图跳转和中文副本；不通过 PDF 或 OCR 重建图纸。

**源码仓库不包含任何工程图纸、派生矢量图、设备台账、原始因果表、账户密码或本机运行包。** 全新运行时图纸库为空，数据由管理员在本机导入。

## 使用功能

- 普通用户 / 管理员两种密码登录；服务端保护图纸、下载及管理接口。
- 中文 / 原文切换保持缩放和位置；全屏、网页大屏、设备点击查询。
- 收藏 / 最近浏览按图纸库和登录身份保存在当前浏览器，最多 100 个收藏和 20 条最近记录。
- 图名、图号、位号和拼音检索；图内关联跳转及按平台生成缺图清单。
- 上传 DWG；手动指定跨图目标；编辑及新增 CAD 块属性。
- 多块、多图暂存后统一生成 DWG，回读检查图元及属性；失败保留已发布版本与草稿。
- 空库引导和运行环境诊断；缺少引擎时可查看已有图纸、暂存属性，导入前说明所缺依赖。

## 启动

源码版需要 **Python 3.12 或更新版本**。Windows 双击 `启动工作台-Windows.cmd`；macOS / Linux 运行：

```sh
./启动工作台.sh
```

首次启动创建平台独立虚拟环境并安装锁定依赖，之后复用。也可手动启动：

```sh
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS / Linux: source .venv/bin/activate
python -m pip install -r cad-workbench/requirements.txt
python -X utf8 cad-workbench/launch.py
```

在服务所在电脑打开启动器给出的地址（默认 `http://127.0.0.1:8765`），设置管理员和普通用户各自的密码。两个密码必须不同且至少 8 个字符；没有默认密码。局域网用户不能执行首次设置。

已有离线运行包可放回 `cad-workbench/tools/`；Windows 启动入口优先使用其中的嵌入式 Python。源码仓库不重新分发第三方引擎或 Python 二进制。

## DWG 引擎与字体

管理员打开右上角 **管理员 → 运行环境** 查看检查结果。

原生 DWG 导入及生成需要本机 ODA File Converter 完整运行包。按其许可从 [ODA 官方页面](https://www.opendesign.com/guestfiles/oda_file_converter) 获取，并放到对应目录，或设置 `PID_DWG_CONVERTER` 指向可执行文件：

| 环境 | 相对于 cad-workbench 的位置 |
| --- | --- |
| Windows x64 | `tools/converters/windows-x86_64/ODAFileConverter.exe` |
| macOS Apple Silicon | `tools/converters/darwin-arm64/ODAFileConverter.app/Contents/MacOS/ODAFileConverter` |
| macOS Intel | `tools/converters/darwin-x86_64/ODAFileConverter.app/Contents/MacOS/ODAFileConverter` |
| Linux x64 | `tools/converters/linux-x86_64/ODAFileConverter` |

保留引擎运行包所需的 DLL、插件等完整目录。中文字体可放置于 `tools/fonts/NotoSansCJKsc-Regular.otf`，或用 `PID_CAD_FONT` 指向已有中文字体；macOS 也会检查系统 Arial Unicode。未配置字体时不会偷偷替换成不支持中文的字体。

仓库自带通用仪表术语。可在本机 `data/terms.tsv`、`data/sentences.tsv` 和 `data/translations.json` 扩充术语；后两者用于精确译文。它们均不进入 Git。未知内容保留原文，不能把自动处理理解为工程审定。

当前图号识别保留原系统的 CEP、CEPD、CEPK、PRP、WHP 等平台规则，非该体系的图号需扩展 `scripts/references.py`；不宣称能正确识别任意行业编号。

## 数据与迁移

默认工作目录为 `cad-workbench`。`PID_DATA_ROOT` 可设置为独立的库目录；静态页面始终从程序目录读取，数据目录无需复制程序文件。

| 本机目录 | 用途 |
| --- | --- |
| `data/` | 索引、密码哈希、术语、属性草稿、修改记录及回读验证 |
| `uploads/` | 用户上传的原始 DWG 和导入记录 |
| `output/` | 中文 DWG/DXF、原文/中文矢量图和设备索引 |
| `reports/` | 缺失关联清单 |

升级前停止服务并备份以上目录，更新源码后保留它们；旧项目还需保留原始 DWG 的相对路径。不要把自己的数据复制到 `resources/` 或 `static/`。密码哈希随库保留，服务重启后用户重新登录。

- `PID_PORT`：指定端口；未指定时启动器尝试 8765—8774。
- `PID_HOST`：监听地址，默认 `0.0.0.0`；设为 `127.0.0.1` 则仅限本机。
- `PID_NO_BROWSER=1`：启动后不打开浏览器。
- `PID_DISABLE_DWG_CONVERTER=1`：明确禁用转换，包括配置过的引擎路径。

局域网用户访问 `http://服务器IPv4:端口`，服务器防火墙只需向可信本地子网放行该 TCP 端口。当前服务使用 HTTP，应部署在可信局域网，未提供直接公网托管能力。

管理员可在账户菜单修改两种访问密码，改密撤销所有登录会话。忘记密码时，停止服务后运行 `python -X utf8 cad-workbench/scripts/reset_access_password.py`；如使用独立库，保留相同的 `PID_DATA_ROOT`。

## 验证

以下检查不需要实际工程图纸或 ODA：

```sh
python scripts/check_source_only.py
node --test tests/library.test.js
python -m unittest discover -s cad-workbench/tests -p "test_*.py" -v
```

可选真实 DWG 集成测试：配置本机引擎和中文字体，设置 `PID_TEST_DWG=1`，再执行相同测试命令。测试在临时目录用代码创建全新的简单 CAD，验证上传、中文提取、属性新增、统一发布和原始文件保留，不读取任何实际工程图纸。无引擎的 CI 会明确跳过此项。

提交前建议执行 `git config core.hooksPath .githooks`，启用本仓库的源码边界检查。CI 也执行相同检查。

GitHub Actions 在 Windows / Linux、Python 3.12 / 3.13 上运行权限和空库测试，另检查 JavaScript 语法及仓库文件边界。CAD 引擎实际执行能力需在目标平台验收。

更多迭代内容见 [CHANGELOG.md](CHANGELOG.md)。
