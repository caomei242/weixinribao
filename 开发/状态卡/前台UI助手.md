# 微信agent专项 前台/UI 助手状态卡

线程名：微信agent专项 前台/UI 助手
线程 id：019e3a21-b1f1-7fa0-a8ff-4ce933048d87
更新时间：2026-05-20 23:19 CST
结论：完成 `2026-05-20｜前台UI｜内部 ID 主显示兜底最小配合`。本轮只做本地操作台主显示 label/title/dropdown fallback 最小前台配合，未扩展新功能、未改布局大结构。

## 任务标记

2026-05-20｜前台UI｜内部 ID 主显示兜底最小配合

## 改动文件

- `/Users/gd/Desktop/微信agent专项/src/wechat_feedback_app/static/app.js`
- `/Users/gd/Desktop/微信agent专项/开发/状态卡/前台UI助手.md`
- `/Users/gd/Desktop/微信agent专项/开发/监工回报队列.md`

## 前台最小配合说明

- 新增统一群名显示 helper：读取 `group_label` / `display_label` / `display_name` / `group_name` / `session_display_name` 等可读字段，并识别 `display_name_status`、`group_name_status`、`group_label_status` 与 `internal_identifier_only` 原因码。
- 群管理列表卡片：主标题改为 `monitorGroupTitle(group)`，遇到 unresolved / 内部标识时显示“群名待解析”，不把 `group_id` / `external_id` 当标题。
- 群管理详情标题与输入框：标题显示用户态文案；输入框不填入内部 ID，unresolved 时 placeholder 为“待补群名”。
- 消息明细群筛选：`messageGroupOptions()` 的 label 改为 `readableGroupDisplayLabel(group, "群名待解析")`，不再用 `group.group_name || group.group_id` 当 label。
- 消息明细消息行：`messageGroupLabel()` 优先走可读群名和后端状态字段，内部 ID / unresolved 统一显示“群名待解析”。
- 候选 / 最近试读详情归属：`updateMessageDetailGroupStatus()` 调用改为 `itemGroupContextLabel()`，避免 `item.group_name || item.session_display_name` 把内部标识当作可读文案。
- 配置中心 session 编辑未改，保留受控配置字段；本轮只限制主操作卡片、标题、下拉 label 和详情归属文案。

## 测试 / 证据

- `node --check src/wechat_feedback_app/static/app.js`：exit=0
- `git diff --check -- src/wechat_feedback_app/static/index.html src/wechat_feedback_app/static/styles.css src/wechat_feedback_app/static/app.js`：exit=0
- `git diff --check`：exit=0
- 静态 JS smoke：可读群名 helper 存在；unresolved / `internal_identifier_only` guard 存在；消息明细下拉使用可读 label；群管理卡片使用安全标题 helper；详情输入框使用 editable helper；候选详情归属使用 context helper；旧 `group.group_name || group.group_id` label fallback 已移除；旧 `group.display_name || group.customer_name || value` label fallback 已移除。
- 静态 grep：主 label fallback 中未再命中 `label: group.group_name || group.group_id`、`group.display_name || group.customer_name || value`、`updateMessageDetailGroupStatus(item.group_name...)`。
- helper 行为 smoke：unresolved、`@chatroom`、id-only 均回落“群名待解析”；可读名仍优先显示。
- 本机 HTTP count/status smoke：`/api/monitor-groups` HTTP 200，group count=4，当前主 label 内部标识命中=false；`/api/messages/v1` HTTP 200，group count=5，message row count=6，消息正文安全标志为未返回正文。
- 本轮未运行 Python。

## 字段白名单 / 安全边界

- 状态卡和回报只记录 HTTP status、count/status、字段存在性、布尔结果，不摘录真实群名、真实 id、消息正文、候选正文、草稿正文、真实会话、成员名单、客户名单、wxid、key、salt、真实 DB 路径、IP 或 daemon 日志。
- 未执行新的真实读取。
- 未执行真实 roster 同步。
- 未执行 `wx history/search/export/new-messages`。
- 未打开真实 SQLite / exports 正文。
- 未写正式日报、正式待办池、Obsidian 正式区或外部系统。
- 未修改 `real_read_enabled=false` 口径。

## 剩余风险

- 当前本机运行态没有 unresolved 样本，已通过静态 helper 行为 smoke 覆盖 unresolved / internal-only 兜底；Windows 实机仍需用后端新回包复核。
- 如果 Windows 仍看到内部 ID，优先排查静态资源缓存、8765 服务未重启或 Windows 发布目录未更新。
- 配置中心受控编辑字段仍可能显示会话标识，这是允许的配置字段，不应拿来当主操作标题。

## 下一棒建议

- Windows 实机复验：强刷 / 重启服务后检查群管理列表标题、详情标题、输入框、消息明细群筛选、消息行、候选详情归属文案。
- 若仍有具体 selector 显示内部 ID，请按 selector 派前台/UI最小补丁；不要扩大到真实读取、roster 或正式区。

## 回报状态

- 状态卡：已写入
- 监工短回：send_input 工具不可用，本轮按项目协议走 `/Users/gd/Desktop/微信agent专项/开发/监工回报队列.md`
