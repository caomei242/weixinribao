# 微信agent专项 后端/API 助手状态卡

更新时间：2026-05-21 12:14 CST

## 线程身份

- 线程名：微信agent专项 后端/API 助手
- 线程 id：019e3a22-0b1d-7ea0-9c36-7a86d3a8883a
- 监工线程 id：019e2a4a-664f-76b3-9533-fbbbfc7f34c5
- 负责范围：后端 API、候选池口径、状态持久化、配置保存、草稿日报 / 转述摘要数据接线、字段白名单、安全边界和测试
- 明确边界：不做监工；不做前台/UI；不手工绕过系统执行 `wx history/search/export/new-messages`；不执行真实 roster 同步；不自动外发 / 回复；不写正式待办池、正式日报、Obsidian 正式区或外部系统；默认 `real_read_enabled=false` 必须保持

## 本轮任务

- 任务标记：`2026-05-21｜后端API｜persistent all_wechat_groups history target 修复`
- 状态：完成 / 待监工验收
- 结论：已按最小稳定方案修复 all_wechat_groups 的 history target。保留 `detected-wechat-group-*` 作为本地配置 / 展示 / 关联键，同时新增本地执行专用 `history_target / wx_session_token / source_session_id`，wx history 调用优先使用底层 wx session token，不再把 detected hash 传给 wx-cli。

## 最小方案选择

- 选择：新增 `history_target`，不直接把 `external_id` 改成真实 token。
- 原因：保留既有 detected hash 作为本地去重 / 关联键，迁移风险更小；同时真实执行链路用底层 token 跑通 wx history。
- 配置保存：本地 `config/app.yaml` 可保存执行专用 target；`/api/config-center`、状态卡、回报队列和 smoke 不返回 token 明细。

## 改动文件

- `/Users/gd/Desktop/微信agent专项/src/wechat_feedback_app/config.py`
- `/Users/gd/Desktop/微信agent专项/src/wechat_feedback_app/routes.py`
- `/Users/gd/Desktop/微信agent专项/tests/test_persistent_real_read_contract.py`
- `/Users/gd/Desktop/微信agent专项/开发/状态卡/后端API助手.md`
- `/Users/gd/Desktop/微信agent专项/开发/监工回报队列.md`

说明：工作区仍有前台/UI和调度材料未提交改动，本线程未回滚、未覆盖；本 P0 业务补丁只收口后端/API target 合同和测试。

## history target 合同

- all_wechat_groups 探针从 `id / external_id / username / room_id / chat_id / conversation_id / session_id` 等字段提取底层 wx history target。
- `SessionConfig` 新增本地执行字段：`history_target`、`wx_session_token`、`source_session_id`。
- wx history target 选择顺序：`history_target` / `wx_session_token` / `source_session_id` > resolved 可读 display name > external_id。
- 若最终 target 仍是 `detected-wechat-group-*` / `local-monitor-*` 这类本地 hash，则不调用 wx history，直接计入 `session_identifier_mismatch`，并返回 `invalid_history_target_count`。
- `upsert_detected_monitor_groups` 会为已存在 detected 群补齐缺失的 target；同 external_id 后续可升级，旧白名单模式不回退。

## failure classification 保留

- 保留上一棒分类字段：`history_failure_classification`、`history_failure_category_counts`、`history_failure_categories`、`details_returned=false`。
- 仍不透传 raw stdout/stderr、命令明细、真实 token、群名、正文、路径或 daemon 原文。

## 测试 / 证据

- persistent 专项：`python exit=0 log=.codex_py_logs/py-run-20260521-121331.log`，25 passed。
- 相关后端专项：`python exit=0 log=.codex_py_logs/py-run-20260521-121338.log`，116 passed。
- 全量 pytest：`python exit=0 log=.codex_py_logs/py-run-20260521-121346.log`，157 passed。
- `git diff --check`：exit=0。

## 验收覆盖

- fake wx sessions 只有底层 token、无可读名时，persistent all_wechat_groups 调 history 使用底层 token，不使用 detected hash。
- 本地 config/session 仍保留 detected external_id 作为关联键，并持有本地执行 target。
- target 仍是 detected hash 时，不调用 wx history，直接安全分类为 `session_identifier_mismatch`，并计入 `invalid_history_target_count`。
- all_wechat_groups 旧探针、非群过滤、英文 room/group 误判防线、persistent 默认关闭、字段白名单不回退。

## 字段白名单 / 安全边界

- 未执行真实消息读取。
- 未执行真实 roster 同步。
- 未手工执行 `wx history/search/export/new-messages`。
- 未自动外发 / 自动回复。
- 未写正式日报、正式待办池、Obsidian 正式区或外部系统。
- `real_read_enabled=false` 事后保持。
- 本地配置可保存执行 target；状态卡、回报队列、测试日志和最终回复不摘录真实 token、真实群名、真实消息正文、真实会话、成员名单、客户名单、wxid/key/salt、DB path、IP、daemon 原始日志。

## 剩余风险

- 本轮未在 Windows 执行真实读取；需要发布到 Windows 后复跑 persistent all_wechat_groups。
- 若仍失败，预期 failure category 不应再是 `session_identifier_mismatch`；需要按返回分类继续定位 wx-cli 参数、权限/DB/连接或窗口问题。

## 下一棒建议

- 发布到 Windows 后复跑 all_wechat_groups / persistent / 30 天真实首跑，只回传 sessions_success/raw_messages_seen/raw_messages_inserted/candidate_items_created/failure_category/count。
- 若成功转正，再回接被插队的 6 个 unresolved 群名人工命名入口。

## 回报投递

- 已追加监工回报队列完成块。
- 已发监工：send_input 调用失败，返回 `agent not found`；未取得 submission_id；以回报队列作为兜底入口。
