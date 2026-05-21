# 微信agent专项 后端/API 助手状态卡

更新时间：2026-05-21 11:29 CST

## 线程身份

- 线程名：微信agent专项 后端/API 助手
- 线程 id：019e3a22-0b1d-7ea0-9c36-7a86d3a8883a
- 监工线程 id：019e2a4a-664f-76b3-9533-fbbbfc7f34c5
- 负责范围：后端 API、候选池口径、状态持久化、配置保存、草稿日报 / 转述摘要数据接线、字段白名单、安全边界和测试
- 明确边界：不做监工；不做前台/UI；不手工绕过系统执行 `wx history/search/export/new-messages`；不执行真实 roster 同步；不自动外发 / 回复；不写正式待办池、正式日报、Obsidian 正式区或外部系统；默认 `real_read_enabled=false` 必须保持

## 本轮任务

- 任务标记：`2026-05-21｜后端API｜Windows 群管理当前可见群名解析未达标` + `2026-05-21｜后端API｜Windows 消息明细正文值仍为技术定位码 / 不可读`
- 状态：完成 / 待监工验收
- 结论：已把 `/api/monitor-groups` 从“有来源时可 resolved”升级为当前列表维度诊断与自动回填；已把 `/api/messages/v1` 从字段存在性升级为正文值质量分类，防止 `m-00xx` / message_ref / 空值 / 占位文本冒充可读摘要。

## 改动文件

- `/Users/gd/Desktop/微信agent专项/src/wechat_feedback_app/routes.py`
- `/Users/gd/Desktop/微信agent专项/tests/test_local_ui_display_contract.py`
- `/Users/gd/Desktop/微信agent专项/开发/状态卡/后端API助手.md`
- `/Users/gd/Desktop/微信agent专项/开发/监工回报队列.md`

说明：工作区已有 AGENTS、前台/UI、测试审查状态卡和调度材料的未提交改动，本线程未回滚、未覆盖；本轮业务代码只改后端 API 合同与后端专项测试。

## 群名诊断 / 回填

- `/api/monitor-groups` 顶层新增当前列表维度计数：`monitor_group_count`、`readable_group_label_count`、`unresolved_group_label_count`、`unresolved_with_readable_source_count`、`unresolved_without_readable_source_count`。
- 新增 `display_name_diagnostics.before_refresh / after_refresh / backfilled_count`，只返回 count/status，不返回群名列表。
- unresolved 群会先检查本项目本地 monitor group config、DB session display name、已入库 raw metadata；有可读来源时自动回填为 resolved。
- 支持 all_wechat_groups 生成的 detected external id 与本地真实 session/raw metadata 之间的二段匹配；内部 ID 仍只作匹配键，不作主标题。
- 只有确实没有可读来源时，才保留 `群名待解析` 与 unresolved / reason_code。
- 保留既有合同：不同 unresolved 不误合并；同 external_id 后续拿到可读名可升级；英文 `room/group` 非群误判不回退。

## 消息正文值质量

- `/api/messages/v1` 顶层新增分类计数：`message_count`、`rows_with_content_text`、`rows_with_content_preview`、`rows_with_message_text`、`rows_with_summary`、`rows_with_content_returned`。
- 新增 human-readable 计数：`content_text_human_readable_count`、`content_preview_human_readable_count`、`message_text_human_readable_count`、`summary_human_readable_count`。
- 新增 message_ref-like / 空占位计数：`summary_message_ref_like_count`、`content_text_message_ref_like_count`、`content_preview_message_ref_like_count`、`empty_or_placeholder_content_count`。
- raw/normalized 有可读正文时，本地 UI 字段返回 `content_text/content_preview/message_text/summary`。
- 如果内容本身是 `m-00xx` / message_ref / 内部标识 / 空值 / 占位，不再塞进 `summary` 或 `content_preview`；改为 `content_status=placeholder_only / empty / unsupported_message_type` 与人话空态字段。
- 同一消息项继续保留 `content_text_safe/content_preview_safe/summary_safe`，供 report/smoke/跨线程路径使用。

## 测试 / 证据

- 本地 UI 合同专项：`python exit=0 log=.codex_py_logs/py-run-20260521-112830.log`，11 passed。
- 相关后端专项：`python exit=0 log=.codex_py_logs/py-run-20260521-112839.log`，108 passed。
- 全量 pytest：`python exit=0 log=.codex_py_logs/py-run-20260521-112848.log`，154 passed。
- `git diff --check`：exit=0。

## 验收覆盖

- fake monitor groups 覆盖当前列表 resolved / unresolved 五项 count。
- fake unresolved + raw/session metadata 可读来源：before 统计命中 with-readable，刷新后回填 resolved，after 顶层 unresolved-with-source 归零。
- fake unresolved 无可读来源：保留 unresolved，计入 without-readable。
- fake raw message 有真实正文：human-readable count > 0，message-ref-like count 为 0。
- fake 只有 message_ref：不把 message_ref 当 summary/content_preview，计入空 / 占位。
- fake 不支持消息类型 / 空内容：返回人话空态，不显示技术定位码。
- 不回退：消息正文 local UI 字段、safe/report 分层、config-center forbidden、all_wechat_groups、英文非群误判。

## 安全边界

- 未执行真实消息读取。
- 未执行真实 roster 同步。
- 未手工执行 `wx history/search/export/new-messages`。
- 未自动外发 / 自动回复。
- 未写正式日报、正式待办池、Obsidian 正式区或外部系统。
- 状态卡、回报队列、测试日志和最终回复不摘录真实群名、真实消息正文、真实会话、成员名单、客户名单、wxid/key/salt、DB path、IP、daemon 原始日志。
- Windows 本地 UI 允许显示真实群名和真实消息正文；跨线程 / smoke / 状态卡继续只写 count/status/error_code/字段存在性/布尔。
- `real_read_enabled=false` 保持。

## 是否需要前台配合

- 若 Windows API 返回 human-readable count 正常但页面仍显示 `m-00xx`，应回派前台/UI或部署线排查字段消费顺序、静态缓存和运行目录。
- 若 Windows API 返回 `unresolved_with_readable_source_count=0` 但仍有 unresolved，则说明当前本地数据没有可读群名来源，需要产品决定是人工命名入口还是补上游 metadata 能力。

## 剩余风险

- 本轮未执行 Windows 8765 运行态 smoke；需要发布 / 重启后由 Windows 侧读取新增 count 字段复核。
- 如果 Windows 本地 DB 与 raw metadata 确实没有可读群名，后端不能凭内部 ID 猜真实群名。

## 下一棒建议

- 测试审查只读复验新增 count 字段，不摘真实值：群名 before/after 诊断、消息正文 human-readable/ref-like/empty 分类、config-center forbidden。
- Windows 发布后 smoke 只回传分类计数与页面布尔：不要贴真实群名或正文。

## 回报投递

- 已追加监工回报队列完成块。
- 已发监工：send_input 调用失败，返回 `agent not found`；未取得 submission_id；以回报队列作为兜底入口。
