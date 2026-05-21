# 微信agent专项 前台/UI 助手状态卡

线程名：微信agent专项 前台/UI 助手
线程 id：019e3a21-b1f1-7fa0-a8ff-4ce933048d87
更新时间：2026-05-21 11:25 CST
结论：收到监工预警，前台/UI继续待命，不改前台代码。当前群管理“群名待解析”和消息明细 `m-00xx` 摘要问题均先等后端/API证明 API 字段值质量；只有 API 已给可读值但页面仍显示旧值时，再做前台最小修复。

## 任务标记

2026-05-21｜前台UI｜本地消息明细真实内容展示与群名可读回填｜DOM/count-status 复验

## 改动文件

- `/Users/gd/Desktop/微信agent专项/开发/状态卡/前台UI助手.md`
- `/Users/gd/Desktop/微信agent专项/开发/监工回报队列.md`

## 后端运行态字段闭合证据

- 监工补证日志：`.codex_runtime_logs/http-smoke-local-ui-content-20260521-104821.log`
- `/api/messages/v1` HTTP 200
- `messages_row_count=6`
- `content_text/content_preview/message_text/summary/content_status/content_returned` 字段存在行数均为 6
- `local_ui_payload=true`
- `content_returned=true`
- `raw_payload_returned=false`
- `report_safe_payload=false`
- `monitor_groups_internal_id_as_main_label_found=false`
- `strict_config_center_forbidden_hit_count=0`

## 前台 DOM 复验证据

- 运行态 DOM smoke：消息明细 row count=6
- `rowsWithPreviewLabel=6`
- `rowsWithNoBodyState=0`
- `rowsWithMessageSummaryLabel=0`
- `rowsWithDetailLocation=6`
- `filterOptionCount=5`
- `statusHasSingleGroupOrAll=true`
- `bodyTextNotReturnedToSmoke=true`
- 结论：页面消息明细主行存在正文 / 预览展示路径；旧 `message_ref` / `m-00xx` 当摘要路径未命中。

## 前台字段消费结论

- `app.js` 已覆盖 `content_text`、`content_preview`、`message_text`、`summary`、`content_status`。
- 也兼容 `message_preview`、`text_preview`、`preview`。
- `message_ref` 仅保留为详情定位字段，不再作为“消息摘要”。
- 群名 label 继续使用可读字段和 unresolved / `internal_identifier_only` 兜底；不回退内部 ID。

## 测试 / 证据

- `node --check src/wechat_feedback_app/static/app.js`：exit=0
- `git diff --check -- src/wechat_feedback_app/static/index.html src/wechat_feedback_app/static/styles.css src/wechat_feedback_app/static/app.js`：exit=0
- `git diff --check`：exit=0
- 本轮 DOM smoke 使用独立临时 Chrome profile，只回传 count/status/布尔结果。
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

- 前台和后端运行态字段已闭合；剩余为测试审查最终复验与 Windows 实机页面确认。
- 如果 Windows 页面仍显示旧摘要或无正文，优先排查静态缓存、Windows 发布目录未更新或服务未重启。
- 监工预警：当前 Windows 回传没有 `contains_commit_40ac49b=yes`，截图仍像旧前端 / 旧后端；在确认 `release_head=f2bdf18`、`contains_commit_40ac49b=yes`、`/api/messages/v1` 内容字段行数 > 0 前，不做前台代码返工。
- 监工预警：Windows 群管理页当前可见多个主标题仍为“群名待解析”；当前优先派后端/API补 `/api/monitor-groups` 当前列表维度 count 与 unresolved 可读来源诊断 / 回填。前台不改代码，等待后端证明 resolved/readable label 已提供。
- 监工预警：Windows 消息明细主行仍显示 `m-00xx` 类摘要；当前优先让后端/API证明 `/api/messages/v1` 字段值质量，包括 `human_readable_count`、`message_ref_like_count`、`empty_or_placeholder_count`。前台不改代码，等待 API 值质量判断。

## 下一棒建议

- 测试审查按本次 DOM/count-status 结果做最终复验：row count、preview label rows、message summary label rows=0、content field rows、safety flags。
- Windows smoke 继续只记录 count/status/字段存在性/布尔结果，不摘录正文。
- 若后续 Windows 同时满足版本 / 字段闭合条件，但 `message_main_line_uses_message_ref_as_summary=yes`，再派前台/UI做最小返工。
- 若后续证明 `/api/monitor-groups` 已给 resolved/readable label，且 `unresolved_with_readable_source_count=0` 或已升级，但页面仍显示“群名待解析”或未消费 resolved label，再派前台/UI做群管理主标题最小修复。
- 消息页分支：若 API `human_readable_count=0` 或 `message_ref_like_count>0`，先后端/API返工 payload 值选择或 fallback；若 API `human_readable_count>0` 且 `message_ref_like_count=0`，但页面仍显示 `m-00xx`，再回派前台/UI查 app.js 消费顺序、静态资源或缓存。

## 回报状态

- 状态卡：已写入
- 监工短回：send_input 工具不可用，本轮按项目协议走 `/Users/gd/Desktop/微信agent专项/开发/监工回报队列.md`
