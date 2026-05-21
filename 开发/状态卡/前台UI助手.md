# 微信agent专项 前台/UI 助手状态卡

线程名：微信agent专项 前台/UI 助手
线程 id：019e3a21-b1f1-7fa0-a8ff-4ce933048d87
更新时间：2026-05-21 10:48 CST
结论：完成字段名对齐复核，并收到监工补证：后端运行态字段已闭合。当前 `app.js` 已覆盖后端给出的消息正文 / 预览字段名，无需新增前台业务改动；等待测试审查最终通过。

## 任务标记

2026-05-21｜前台UI｜本地消息明细真实内容展示与群名可读回填｜字段名对齐复核

## 改动文件

- `/Users/gd/Desktop/微信agent专项/开发/状态卡/前台UI助手.md`
- `/Users/gd/Desktop/微信agent专项/开发/监工回报队列.md`

## 字段名对齐结论

- 消息明细主行消费字段已覆盖：`content_text`、`content_preview`、`message_text`、`summary`、`content_status`。
- 前台也兼容此前预留字段：`message_preview`、`text_preview`、`preview`。
- `message_ref` / `m-00xx` 不再作为“消息摘要”路径；只保留为详情定位字段。
- 群名 label 继续使用 `readableGroupDisplayLabel()`，保留 `group_label` / `display_label` / `display_name` / `group_name` 优先消费和 unresolved / `internal_identifier_only` 兜底，不回退内部 ID。
- 本地 UI 不主动打码主内容；状态卡、回报队列、smoke 和跨线程消息仍不摘录真实正文或真实群名。

## 测试 / 证据

- `node --check src/wechat_feedback_app/static/app.js`：exit=0
- `git diff --check -- src/wechat_feedback_app/static/index.html src/wechat_feedback_app/static/styles.css src/wechat_feedback_app/static/app.js`：exit=0
- `git diff --check`：exit=0
- 静态字段 smoke：正文 / 预览字段覆盖=true；无 `message_ref` 摘要路径=true；`message_ref` 仅详情定位=true；群名内部 ID guard=true；旧下拉 ID fallback 已移除=true。
- 本机 HTTP count/status smoke：`/api/messages/v1` HTTP 200，message row count=6；早前前台复核时当前进程 rowsWithAnyContentField=0，说明当时 8765 仍是旧回包或未重启 / 未发布到当前进程。
- 监工补证：本机 8765 已从当前工作区重启，后端运行态字段已闭合；日志 `.codex_runtime_logs/http-smoke-local-ui-content-20260521-104821.log` 显示 message_count=6，`content_text/content_preview/message_text/summary/content_status/content_returned` 字段存在行数均为 6，`local_ui_payload=true`，`content_returned=true`，`raw_payload_returned=false`，`report_safe_payload=false`。
- 本轮未运行 Python。

## 字段白名单 / 安全边界

- 本地 UI 允许展示已入库真实消息正文 / 可读摘要。
- 状态卡、回报和 smoke 只记录 HTTP status、count/status、字段存在性、布尔结果；未摘录真实消息正文、候选正文、草稿正文、真实会话、成员名单、客户名单、真实群名、真实 id、wxid、key、salt、真实 DB 路径、IP 或 daemon 日志。
- 未执行新的真实读取。
- 未执行真实 roster 同步。
- 未执行 `wx history/search/export/new-messages`。
- 未打开真实 SQLite / exports 正文。
- 未外发，未写正式日报、正式待办池、Obsidian 正式区或外部系统。
- 未修改 `real_read_enabled=false` 口径。

## 剩余风险

- 前台字段名已对齐；后端运行态字段已闭合，等待测试审查最终通过。
- 若后端最终字段名再次调整，前台只需在 `messageReadablePreview()` 增补字段，不需要改布局。

## 下一棒建议

- 测试审查可基于后端运行态字段级 smoke 做最终复验：`local_ui_payload=true`、`content_returned=true`、`raw_payload_returned=false`、`report_safe_payload=false`，并确认 content/preview 字段存在行数 > 0。
- 后续 Windows smoke 仍只写 count/status/字段存在性/布尔结果，不摘录正文。

## 回报状态

- 状态卡：已写入
- 监工短回：send_input 工具不可用，本轮按项目协议走 `/Users/gd/Desktop/微信agent专项/开发/监工回报队列.md`
