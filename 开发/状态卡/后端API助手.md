# 微信agent专项 后端/API 助手状态卡

更新时间：2026-05-20 22:41 CST

## 线程身份

- 线程名：微信agent专项 后端/API 助手
- 线程 id：019e3a22-0b1d-7ea0-9c36-7a86d3a8883a
- 监工线程 id：019e2a4a-664f-76b3-9533-fbbbfc7f34c5
- 负责范围：后端 API、候选池口径、状态持久化、配置保存、草稿日报 / 转述摘要数据接线、字段白名单、安全边界和测试
- 明确边界：不做监工；不做前台/UI；不手工绕过系统执行 `wx history/search/export/new-messages`；不执行真实 roster 同步；不自动外发 / 回复；不写正式待办池、正式日报、Obsidian 正式区或外部系统；默认 `real_read_enabled=false` 必须保持

## 本轮任务

- 任务标记：`监工返工：2026-05-20｜后端API｜本地操作台主显示字段去误脱敏`
- 状态：完成，待监工验收
- 结论：后端 payload 已区分“本地操作台主显示字段”和“跨线程 / report-safe 脱敏字段”。群管理、消息明细、我方人员、候选 / 日报、最近试读候选的主显示字段保留本地 UI 可识别值；同 payload 增补或保留 `*_safe` / `redacted_*` 字段用于回报、smoke、测试审查等安全摘要。

## 改动文件

- `/Users/gd/Desktop/微信agent专项/src/wechat_feedback_app/routes.py`
- `/Users/gd/Desktop/微信agent专项/src/wechat_feedback_app/exporter.py`
- `/Users/gd/Desktop/微信agent专项/tests/test_local_ui_display_contract.py`
- `/Users/gd/Desktop/微信agent专项/开发/状态卡/后端API助手.md`
- `/Users/gd/Desktop/微信agent专项/开发/监工回报队列.md`

说明：未修改前台静态文件；工作区中 `AGENTS.md` 及其他总控/监工侧记录为既有未提交改动，本棒未回滚。

## 关键实现

- 新增 `local_ui_display_text()` / `local_ui_display_list()`：保留本地 UI 普通可识别名称，不因通用脱敏规则误伤主字段；但仍拦截硬禁 token、路径、raw/content 标记和测试敏感标记。
- 群管理 payload：`group_name`、`display_name`、`customer_name`、`group_type`、`module_name`、`customer_stage`、`owner_label`、detail 联系人/备注等改为本地 UI 主字段真值，同时提供 safe 副本。
- 消息明细 payload：群标签、客户标签、模块标签主字段可读，同时提供 safe 副本；正文和 raw payload 仍不返回。
- 我方人员 payload / suggestion：人员姓名、微信显示名、模块、notes、建议主字段可读，同时提供 safe 副本。
- 候选 / 日报 / 最近试读：本地审阅字段与 report-safe 字段分层；日报全文、转述预览、smoke / 白名单旧安全合同继续使用脱敏摘要，不让硬禁标记进入跨线程可引用字段。
- `redact_visible_text()` 增补测试敏感标记脱敏，确保旧 report-safe 合同不回退。

## 测试 / 证据

- 新增专项：`python exit=0 log=.codex_py_logs/py-run-20260520-223701.log`，`tests/test_local_ui_display_contract.py` 5 passed。
- 相关后端专项：`python exit=0 log=.codex_py_logs/py-run-20260520-224013.log`，96 passed。
- 全量 pytest：`python exit=0 log=.codex_py_logs/py-run-20260520-224022.log`，142 passed。
- `git diff --check`：通过。

## 字段白名单

- `/api/config-center` forbidden field hit count 不回退：专项测试覆盖 `sqlite_path` / DB path / `member_name_options` / raw payload 类禁字段。
- 本地 UI 主字段允许本机操作所需可识别文本；状态卡、回报队列、测试日志和 smoke 仍只记录 count / status / 字段存在性 / 布尔结果。
- 硬禁内容仍不得返回：真实消息正文、候选正文原文证据、真实会话列表、真实成员名单、客户名单、wxid/key/salt、DB path、IP、daemon 原始日志、raw payload。

## 安全边界

- 未新增真实读取。
- 未执行真实 roster 同步。
- 未手工执行 `wx history/search/export/new-messages`。
- 未自动外发 / 自动回复。
- 未写正式日报、正式待办池、Obsidian 正式区或外部系统。
- 未在状态卡或回报中摘录真实群名、真实消息正文、真实会话、真实成员、客户名单、wxid/key/salt、DB path、IP、daemon 日志。
- `real_read_enabled=false` 保持。

## 剩余风险

- 本棒未改前台 UI。若 Windows 页面仍显示 safe 字段或旧缓存字段，需要前台/UI做最小返工：改为消费后端主显示字段，safe 字段仅用于回报/诊断。
- 8765 运行态未在本棒做 HTTP smoke；若监工要求 Windows 实机复验，需要发布/重载后按运行态规则复测。

## 下一棒建议

- 前台/UI最小复验：确认群管理、消息明细、我方人员、候选审阅页消费主字段而非 safe 字段。
- 测试审查复核：重点扫本地 UI 主字段可识别、report-safe 字段脱敏、config-center forbidden 字段不回退。
- Windows 发布前仍需按项目规则核对 Git 发布目录和运行态来源。

## 回报投递

- 已追加监工回报队列完成块。
- 已发监工：send_input 工具当前不可用，未取得 submission_id；以回报队列作为兜底入口。
