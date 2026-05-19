# Windows 长期挂机部署

本文件用于把微信反馈采集工作台部署到 Windows 24 小时挂机机。当前版本默认运行 `fixture` 模式；`real` 模式只允许 `wx sessions --json` 连接测试，不读取真实聊天正文，不自动回复，不写正式待办池。真实消息采集仍会返回 `real_collection_disabled`，需要未来单独授权后再开发。

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

健康检查日志：

```text
D:\wechat-agent\app\logs\health-YYYYMMDD.log
```

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
