# 微信agent专项 Windows 实机部署预演接力包

- 生成时间：2026-05-18 16:31 CST
- Mac 项目路径：`/Users/gd/Desktop/微信agent专项`
- Windows 目标路径：`D:\wechat-agent\app`
- 本轮目标：先把 Windows 机器跑通本地服务、fixture 页面、健康检查和任务计划预演。

> 2026-05-20 更新：本文仍是“Windows 预演”接力包。当前 Windows 可实战第一版的正式验收清单已经迁移到 `docs/windows-p0-acceptance.md`；后续不要只按本文的 fixture 预演标准验收 P0 主流程。

> 2026-05-20 12:07 CST 更新：Windows 可实战第一版 P0 已在 Mac 开发机运行态完成代码侧测试审查，通过项包括 Windows readiness、监控群、我方人员、消息多群视图、候选入口、日报生成即时反馈和日报中心首屏布局。Windows 机器仍未实机复验；接力时请按 `docs/windows-p0-acceptance.md` 做完整用户路径验收。

> 2026-05-20 13:51 CST 封版更新：P0 小返工已补齐群管理本地归档 / 删除和日报生成点击反馈，测试审查完成通过。当前版本可以进入 Windows 实机部署 + 只读复验；部署线只做运行环境、服务启动、页面打开和主路径 count/status 复验，不加新功能。

## 先说人话

这一步不是正式接微信消息，也不是让它开始每 30 分钟抓群。

这一步只验证三件事：

1. Windows 那台电脑能不能跑这个后台。
2. 页面能不能打开。
3. 以后要长期挂机时，开机启动和每 30 分钟健康检查能不能挂上。

## 硬边界

Windows 预演阶段必须遵守：

- 不读取真实微信聊天正文。
- 不打开真实 SQLite、exports 正文或微信数据库。
- 不摘录真实消息、候选正文、真实会话列表、wxid、key、salt、真实 DB 路径或 daemon 原始日志。
- 不自动回复。
- 不写正式待办池、正式日报、Obsidian 正式区或外部系统。
- 默认保持 `wx_cli.mode: fixture`。
- 任务计划只允许启动本地服务和健康检查，不允许触发真实消息读取。

## 你在 Mac 上怎么做

1. 把交付 zip 通过 Slock 发到另一台 Windows 电脑。
2. Windows 那台电脑下载 zip。
3. 解压到：

```text
D:\wechat-agent\app
```

4. 在 Windows Codex 里粘贴下面这段话。

```text
你是微信agent专项 Windows 实机部署预演助手。

项目路径：D:\wechat-agent\app

请先阅读：
D:\wechat-agent\app\WINDOWS_HANDOFF.md
D:\wechat-agent\app\docs\windows-deploy.md
D:\wechat-agent\app\README.md

目标：只做 Windows 本机预演，把本地服务、fixture 页面、健康检查和可选任务计划跑通。

硬边界：
- 不读取真实微信聊天正文。
- 不打开真实 SQLite、exports 正文或微信数据库。
- 不摘录真实消息、候选正文、真实会话列表、wxid、key、salt、真实 DB 路径或 daemon 原始日志。
- 不自动回复。
- 不写正式待办池、正式日报、Obsidian 正式区或外部系统。
- 默认保持 wx_cli.mode: fixture。

请一步步执行，并最后回我一张状态卡：
- 项目目录：
- Python / venv：
- 依赖安装：
- config/app.yaml：
- 本地服务：
- 页面地址：
- 健康检查：
- wx-cli 连接测试状态：
- 任务计划：
- 卡住点：
- 下一步建议：
```

## Windows 那台电脑执行步骤

### 1. 打开 PowerShell

```powershell
cd D:\wechat-agent\app
```

### 2. 创建虚拟环境

优先用 Python 3.12：

```powershell
py -3.12 -m venv .venv
```

如果这条失败，再试 Python 3.11：

```powershell
py -3.11 -m venv .venv
```

### 3. 安装依赖

```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install .
```

### 4. 创建配置

```powershell
Copy-Item .\config\app.example.yaml .\config\app.yaml
```

确认 `config\app.yaml` 里还是 fixture：

```yaml
wx_cli:
  mode: "fixture"
```

### 5. 启动本地服务

```powershell
.\scripts\windows\start_server.ps1
```

打开：

```text
http://127.0.0.1:8765
```

页面能打开，就先算第一关过。

### 6. 跑健康检查

```powershell
.\scripts\windows\health_check.ps1
```

fixture 模式下，期望看到的是服务状态能返回、测试文件能读。这里不要求真实微信消息可读。

### 7. 可选：注册任务计划

只有前面都过了，再跑：

```powershell
.\scripts\windows\install_task.ps1
```

这一步会注册：

- 登录后启动本地服务。
- 每 30 分钟做一次健康检查。

注意：这不是每 30 分钟抓微信消息，只是健康检查。

## 回传给 Mac 这边的状态卡模板

```text
【Windows 预演状态卡】

- 项目目录：D:\wechat-agent\app
- Python / venv：
- 依赖安装：
- config/app.yaml：
- 本地服务：
- 页面地址：http://127.0.0.1:8765
- 健康检查：
- wx-cli 连接测试状态：
- 任务计划：
- 卡住点：
- 下一步建议：
```

## 判断标准

通过标准：

- `D:\wechat-agent\app` 目录完整。
- `.venv` 创建成功。
- `pip install .` 成功。
- `config\app.yaml` 存在，且默认 fixture。
- `start_server.ps1` 能启动服务。
- `http://127.0.0.1:8765` 能打开。
- `health_check.ps1` 能跑完。
- 如果注册任务计划，明确知道它只是服务和健康检查，不是抓消息。

Windows 可实战第一版 P0 通过标准另见 `docs/windows-p0-acceptance.md`。仅通过本节 fixture 预演不能代表 Windows P0 已可实战。

需要返工：

- 页面打不开。
- 服务启动失败。
- 健康检查失败且没有日志。
- 配置默认变成 real。
- 任何步骤尝试读取真实聊天正文。

## Slock 投递状态

- 2026-05-18 16:47：已在 Slock 私聊 `微信部署助手` 投递任务 `#1`，并附上 `wechat-agent-windows-preflight-20260518-163317.zip`。
- 2026-05-18 16:47：任务已进入 `微信部署助手` 的 `TODO` 列。
- 当前卡点：`微信部署助手` 挂在 Windows `运营主机`，但页面显示 `Offline`；已尝试普通 `Restart`，仍未稳定在线。
- 下一步：在 Windows 电脑确认 Slock / Codex CLI 运行态，确保 `微信部署助手` 在线后再让它领取任务 `#1`。
