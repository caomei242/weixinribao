# Windows 可实战第一版 P0 验收清单

更新时间：2026-05-20

本文用于验收“Windows 可实战第一版”。目标不是继续补零散按钮，而是确认 Windows 机器能独立跑通用户主流程：打开系统、确认本机配置、配置监控群、配置我方人员、按群看消息、看到候选、生成日报，并且不混用 Mac 测试微信号配置。

## 2026-05-20 代码侧状态

Windows 可实战第一版 P0 已在 Mac 开发机运行态通过测试审查联动复验：

- 后端主路径接口返回 200，且字段白名单保持通过。
- 前台消费 `/api/windows-readiness`，不再只靠浏览器平台判断 Windows 配置隔离。
- 消息明细消费 `/api/messages/v1`，单群 0 条时显示空态，不回退展示全部群。
- 日报中心首屏三档视口无重叠 / 无横向溢出。
- 群管理已补本地归档 / 删除入口、二次确认、失败保留旧列表和统计读回。
- 日报生成已补点击后 1 秒内的生成中 / 失败原因 / 旧日报保留反馈。
- `real_read_enabled=false` 保持，未执行真实读取、真实 roster 同步或写正式区。

该状态只代表代码侧和 Mac 运行态验收通过。Windows 实机仍需单独复验微信登录、wx-cli 能力、路径权限、配置隔离和开机后服务可用性。后续不要把 Mac 开发配置通过误判成 Windows 正式挂机已通过。

2026-05-20 13:51 CST 封版口径：当前代码可作为 Windows P0 实机部署复验版本。部署线只做代码同步、启动服务和只读复验，不再混入日报产品化、群管理增强、我方人员减负、Slock Agent 或长期挂机新需求。新需求另起开发线排期。

2026-05-20 15:19 CST Windows 实机整机重启复验已完成通过：重启标记变化，Slock daemon、本地服务、页面访问、wx-cli readiness/test 均返回 `status=ok`，只记录 count/status/error_code/字段存在性。Windows P0 冻结版可作为正式挂机机放行；这不等于授权真实读取、真实 roster 同步、自动外发、写正式区或把下一轮开发版自动同步到 Windows。

## 验收路径

按以下顺序验收，不要只看单点 API：

1. 打开 `http://127.0.0.1:8765`。
2. 日报中心默认第一屏可见，且能看懂当前是否是 Windows 正式挂机配置。
3. 群管理能新增 / 编辑 / 停用监控群；新增群默认待验证，保存后全员 roster 同步必须有二次确认或等价授权说明。
4. 我方人员页能通过固定表单配置人员，能从后端 API 保存并读回。
5. 消息明细必须先选群再看；单群没有消息时显示空态，不回退展示全部群消息。
6. 候选收件箱能看到候选 count/status，并能进入本地确认流。
7. 点击生成 / 刷新日报后，1 秒内必须看到生成中、失败原因或旧日报保留提示。

## 后端运行态接口

后端/API 改动后，必须重启或重载 8765，再用运行态 HTTP smoke 复核。源码测试通过但运行态仍旧，不能验收。

必须返回 200 的主路径：

```text
GET /api/windows-readiness
GET /api/monitor-groups
GET /api/internal-people
GET /api/internal-people/suggestions
GET /api/messages/v1
GET /api/daily-center/generation-status
```

只允许记录 HTTP status、count、status 字段、error_code 和布尔结果。不得记录真实消息、真实成员名单、客户名单、wxid、key、salt、真实 DB 路径或 daemon 原始日志。

## 前台验收点

- Windows 状态面板必须使用 `/api/windows-readiness` 的后端脱敏摘要，不得只靠浏览器平台判断。
- 消息明细必须使用 `/api/messages/v1` 或等价带 `group_id` 的安全接口。
- 我方人员页必须接 `/api/internal-people` 和 `/api/internal-people/suggestions`，保存后能从后端读回。
- 群管理的成员池只能把本地已出现成员标成本地已出现；完整群成员必须来自显式授权的 roster 同步。
- 客户识别可以消费本地配置客户和草莓客户系统只读客户源，但页面和回报只显示状态 / 数量 / 匹配结果，不摘录客户名单。
- 日报生成按钮点击后必须立即进入可见状态，不让用户干等。

## 首屏布局验收

日报中心首屏要稳定，不得挤压或覆盖：

- 标题 / 说明、操作按钮、状态 / KPI 卡片、日报全文区域必须分层清楚。
- “今天最要跟进”区域要自然撑开，不能用固定高度压住下方卡片。
- 按钮组必须允许换行。
- 状态 / KPI 卡片必须在独立 grid / section 中排列。
- 禁止用会导致覆盖的 absolute、负 margin 或硬固定高度撑版。
- 至少检查 2048x1152、1440x900、窄屏三档。

## 安全边界

- 默认 `real_read_enabled=false`。
- 不执行新的真实读取。
- 不执行真实授权 roster 同步，除非用户在前台明确二次确认。
- 不执行 `wx history`、`wx search`、`wx export`、`wx new-messages`。
- 不写正式待办池、正式日报、Obsidian 正式区或外部系统。
- 状态卡、回报队列、测试日志、README 和 smoke 不得摘录真实消息正文、候选正文、草稿正文、真实会话列表、真实成员名单、客户名单或敏感路径。

## 通过标准

- 后端相关测试、全量 pytest、`git diff --check` 通过，并有运行态 HTTP smoke。
- 前台 `node --check`、静态 smoke、DOM / count-status smoke 通过。
- 测试审查按用户路径复核，不只看接口。
- Windows 配置与 Mac 开发测试配置隔离说明可见。
- 用户主路径没有空白页、旧接口 404、消息混排、日报按钮无反馈或首屏重叠。

## 下一步复验顺序

1. 产品助手做轻量产品走查，只判断用户路径是否顺手、文案是否能懂、是否还有明显断裂；不扩写新需求、不混入 Slock Agent 第二阶段。
2. Windows 实机部署助手按 `docs/windows-deploy.md` 启动服务、跑健康检查、打开前台。
3. Windows 实机验收按本文“验收路径”逐项走，只记录 count / status / error_code / 字段存在性。
4. 若 Windows 实机通过，再把该机器标为可继续做真实微信连接与授权试点；若失败，按最小阻塞项返工。
