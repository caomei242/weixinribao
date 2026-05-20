# Windows 长期挂机部署

本文件用于把微信反馈采集工作台部署到 Windows 24 小时挂机机。当前版本默认运行 `fixture` 模式；`real` 模式只允许 `wx sessions --json` 连接测试，不读取真实聊天正文，不自动回复，不写正式待办池。真实消息采集仍会返回 `real_collection_disabled`，需要未来单独授权后再开发。

2026-05-20 状态：Windows 可实战第一版 P0 已在 Mac 开发机运行态通过测试审查联动复验，但 Windows 实机尚未验收。部署到 Windows 后，必须重新执行本文件的服务启动 / 健康检查，并按 [windows-p0-acceptance.md](windows-p0-acceptance.md) 做用户路径验收；不得直接复用 Mac 开发机通过结论。

## 1. 目录建议

建议放在固定目录：

```text
D:\wechat-agent\
  app\
    README.md
    pyproject.toml
    config\
      app.yaml
      app.example.yaml
    data\
    exports\
    fixtures\
    logs\
    scripts\
      windows\
    src\
    .venv\
```

本文后续假设项目根目录是 `D:\wechat-agent\app`。

## 2. Python 与虚拟环境

推荐 Python 3.11 或 3.12。最低按项目声明支持 Python 3.9，但 Windows 新机器建议直接装 3.12。

在 PowerShell 中执行：

```powershell
cd D:\wechat-agent\app
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install .
```

如果只想先跑 fixture 演示，不需要安装或登录真实微信，也不需要真实 `wx-cli`。

## 3. 配置文件

复制样例配置：

```powershell
Copy-Item .\config\app.example.yaml .\config\app.yaml
```

关键字段：

```yaml
app:
  host: "127.0.0.1"
  port: 8765

database:
  path: "data/wechat_feedback.sqlite3"

wx_cli:
  mode: "fixture"
  binary: "wx"
  timeout_seconds: 15
  fixture_dir: "fixtures"

export:
  directory: "exports"
```

`fixture` 与 `real` 区别：

- `fixture`：只读取 `fixtures/wx_messages.sample.json`，适合安装验证和演示。
- `real`：只启用 `wx-cli` 连接测试，运行 `wx sessions --json` 检查二进制、初始化、微信登录和输出格式。
- 当前版本不会读取真实聊天正文；即使配置 `real`，采集真实消息仍返回 `real_collection_disabled`。

### 客户源与成员名单

群管理客户识别会合并本地配置客户与草莓客户管理系统只读客户源。Windows 正式挂机机如果要获得完整客户选项，需要同步或挂载 `/Users/gd/Desktop/主业--草莓客户管理系统` 对应的客户资料工程，并保持只读接入；如果该来源不可访问，接口应返回 `source_status=partial` 和 `source_error_code`，页面提示客户源未接通 / 不可读 / 客户选项不足，不得把本地少量客户选项当作完整客户库。

该客户源只用于客户选项和群名识别，不触发真实微信读取、不读取聊天正文、不写正式日报 / 待办 / Obsidian 正式区。运维记录和 smoke 只写 `customer_options_count`、`source_status`、`source_error_code`、`match_status`、布尔结果，不摘录客户名单。

微信群全员名单不是本地已出现成员。全员 roster 同步只允许在用户显式授权后执行，读取范围限群成员 roster 元数据，不读取聊天消息，不写正式区。部署验收时只记录 `status`、`count`、`source_status`、`roster_status`、`error_code` 等摘要字段，不摘录成员名单。

## 4. 启动服务

推荐使用脚本：

```powershell
cd D:\wechat-agent\app
.\scripts\windows\start_server.ps1
```

启动后访问：

```text
http://127.0.0.1:8765
```

日志位置：

```text
D:\wechat-agent\app\logs\server-YYYYMMDD-HHMMSS.out.log
D:\wechat-agent\app\logs\server-YYYYMMDD-HHMMSS.err.log
D:\wechat-agent\app\logs\wechat-feedback.pid
```

## 5. 健康检查

执行：

```powershell
.\scripts\windows\health_check.ps1
```

它会检查：

- `/api/status`
- `/api/wx-cli/test`
- `/api/windows-readiness` 的运行环境、配置隔离和路径隔离摘要
- `/api/customer-options` 的 count/status/source 字段
- `/api/daily-center/generation-status` 的生成状态字段

健康检查日志：

```text
D:\wechat-agent\app\logs\health-YYYYMMDD.log
```

Windows 可实战第一版的完整用户路径验收见 [windows-p0-acceptance.md](windows-p0-acceptance.md)。健康检查只证明服务接口可用，不等于用户路径已经可用；测试审查还必须打开前台，按“日报中心 -> 群管理 -> 我方人员 -> 消息明细 -> 候选 -> 生成日报”的顺序做 count/status 级联动复核。

后端代码更新后必须重启或重载 8765 运行态，再跑健康检查和 HTTP smoke。若源码测试通过但运行态仍旧、接口返回 404 或页面仍消费旧接口，不得判定 Windows P0 通过。

Windows 实机通过前，任何从 Mac 带过去的监控群、我方人员或 wx-cli 配置都应视为待验证；不要把 Mac 测试微信号、Mac 本地路径或 Mac 试读产物当作 Windows 正式挂机配置。

`fixture` 模式下，连接测试应返回 `ok` 和 `fixture 文件可读取`。`real` 模式下，连接测试可能返回：

- `ok`
- `missing_binary`
- `not_initialized`
- `wechat_not_running`
- `permission_denied`
- `parse_error`
- `timeout`

这些状态会在页面和 API 中可见，失败不会清空 SQLite、不会混入 fixture 数据、不会静默成功。

## 6. 注册任务计划

以当前用户登录时自动启动服务：

```powershell
cd D:\wechat-agent\app
.\scripts\windows\install_task.ps1
```

默认注册两个任务：

- `WechatFeedbackWorkbench`：用户登录后启动本地服务。
- `WechatFeedbackWorkbenchHealth`：每 30 分钟做一次健康检查。

如需自定义任务名：

```powershell
.\scripts\windows\install_task.ps1 -TaskName "WechatFeedbackWorkbench"
```

任务计划只启动本地服务和健康检查，不会触发真实消息正文读取。

## 7. 停止、移除与卸载

停止当前服务：

```powershell
.\scripts\windows\stop_server.ps1
```

移除任务计划：

```powershell
.\scripts\windows\remove_task.ps1
```

卸载时可保留 `data\wechat_feedback.sqlite3` 和 `exports\` 作为本地证据。若要彻底清理，再人工删除项目目录。

## 8. 常见失败处理

### 页面打不开

1. 执行 `health_check.ps1`。
2. 查看 `logs\server-*.err.log`。
3. 确认端口 `8765` 未被占用。
4. 确认 `.venv\Scripts\python.exe` 存在，依赖已安装。

### `missing_binary`

`wx_cli.binary` 找不到。先确认 `config\app.yaml` 中的路径；如果只是 fixture 演示，请保持：

```yaml
wx_cli:
  mode: "fixture"
```

### `not_initialized`

需要先人工完成 `wx-cli` 初始化。本项目不会自动初始化，也不会自动读取真实聊天正文。

### `wechat_not_running`

微信未运行、未登录或本地数据不可读。当前版本只提示，不会进一步读取消息。

### `permission_denied`

检查 `wx-cli`、配置目录和数据目录权限。不要为了绕过权限把真实聊天库复制进 fixture 或测试目录。

### `parse_error`

`wx-cli` 输出格式变化或不是 JSON/YAML。保留 `logs\health-YYYYMMDD.log`，交给开发线程排查。

### `timeout`

增大 `wx_cli.timeout_seconds` 或检查本机负载。超时不会修改已有候选事项。

## 9. 安全边界

- 默认 `fixture`。
- `real` 只做连接测试。
- 不读取真实聊天正文。
- 不自动回复。
- 不调用外部 LLM、Webhook 或云 API。
- 不写正式待办池。
- 所有数据保存在本地 SQLite、日志和 Markdown 导出目录。
- 真实消息读取必须未来单独授权，且应另开开发任务。
