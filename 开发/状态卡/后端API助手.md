# 微信agent专项 后端/API 助手状态卡

更新时间：2026-05-21 12:33 CST

## 线程身份

- 线程名：微信agent专项 后端/API 助手
- 线程 id：019e3a22-0b1d-7ea0-9c36-7a86d3a8883a
- 监工线程 id：019e2a4a-664f-76b3-9533-fbbbfc7f34c5
- 负责范围：后端 API、候选池口径、状态持久化、配置保存、草稿日报 / 转述摘要数据接线、字段白名单、安全边界和测试
- 明确边界：不做监工；不做前台/UI；不手工绕过系统执行 `wx history/search/export/new-messages`；不执行真实 roster 同步；不自动外发 / 回复；不写正式待办池、正式日报、Obsidian 正式区或外部系统；默认 `real_read_enabled=false` 必须保持

## 本轮任务

- 任务标记：`2026-05-21｜后端API｜群名人工命名保存读回确认/补契约`
- 状态：完成 / 待监工验收
- 结论：现有后端已支持 `group_name/display_name` 保存并在列表、详情、消息筛选读回；本轮补齐人工命名别名字段和候选/日报关联 label 读回，确保 6 个 `unresolved_without_readable_source` 群人工填写本地显示名后可升级为 resolved，并降低 unresolved count。

## 插队记录

- 被插队任务：`2026-05-21｜后端API｜真实首跑入库候选 0 最小补证`
- 当前处理：已暂停；该任务只做了只读判断和状态记录，未改业务代码。后续可继续补 raw/candidate 0 的安全 summary 字段。

## 改动文件

- `/Users/gd/Desktop/微信agent专项/src/wechat_feedback_app/routes.py`
- `/Users/gd/Desktop/微信agent专项/src/wechat_feedback_app/daily_control.py`
- `/Users/gd/Desktop/微信agent专项/tests/test_local_ui_display_contract.py`
- `/Users/gd/Desktop/微信agent专项/开发/状态卡/后端API助手.md`
- `/Users/gd/Desktop/微信agent专项/开发/监工回报队列.md`

说明：工作区仍有前台/UI和调度材料未提交改动，本线程未回滚、未覆盖；本 P0 业务补丁只收口后端/API 人工命名契约和测试。

## 保存 / 读回契约

- 保存接口继续支持前台已发送的 `group_name/display_name`。
- 新增兼容别名：`manual_display_name`、`local_display_name`、`local_alias`、`display_alias`、`alias`。
- 保存人工名后，`display_name_status=resolved`，`display_name_source=user_input`，人工名作为本地 UI 主 label。
- 保存响应新增 count/readback 摘要：`manual_display_name_saved`、`display_name_readback_status`、`display_name_readback_source`、`readable_group_label_count`、`unresolved_group_label_count`、`readback_contract`。
- 不同 unresolved 群不按占位名误合并；只更新指定 `group_id` 对应会话。

## 读回覆盖

- `/api/monitor-groups` 列表：`group_name/display_name` 返回人工名，readable count 增加，unresolved count 降低。
- `/api/monitor-groups/{group_id}` 详情：`group.group_name` 返回人工名。
- `/api/messages/v1` 群筛选：`message_group_options[].group_name` 返回人工名。
- 候选 / 日报：`candidate_inbox`、`daily_center.today_focus`、`daily_followup_items_payload`、`daily_center_today_focus_payload`、`build_candidate_inbox_items` 可从候选证据链的 session id 映射到 config 中的人工名，返回 `group_label`。

## 测试 / 证据

- 本地 UI 合同专项：`python exit=0 log=.codex_py_logs/py-run-20260521-123305.log`，12 passed。
- 相关后端专项：`python exit=0 log=.codex_py_logs/py-run-20260521-123312.log`，117 passed。
- 全量 pytest：`python exit=0 log=.codex_py_logs/py-run-20260521-123321.log`，158 passed。
- `git diff --check`：exit=0。

## 字段白名单 / 安全边界

- 未执行真实消息读取。
- 未执行真实 roster 同步。
- 未手工执行 `wx history/search/export/new-messages`。
- 未自动外发 / 自动回复。
- 未写正式日报、正式待办池、Obsidian 正式区或外部系统。
- `real_read_enabled=false` 事后保持。
- 状态卡、回报队列、测试日志和最终回复不摘录真实 token、真实群名、真实消息正文、真实会话、成员名单、客户名单、wxid/key/salt、DB path、IP、daemon 原始日志。

## Windows smoke 建议回传字段

- 保存前后：`readable_group_label_count`、`unresolved_group_label_count`、目标项 `display_name_status`、`group_name_status`。
- 读回路径：列表 / 详情 / 消息筛选 / 候选或日报 label 是否均为 resolved。
- 只回 count/status/布尔，不回传真实人工名。

## 剩余风险

- 本轮未在 Windows 运行态保存真实 6 个群；需要发布后由 Windows 页面保存其中一个 unresolved 群并回传 count/status。
- 若前台保存 payload 未带 `group_id` 或运行态仍是旧后端，会导致未命中指定群；需同步确认发布来源和请求路径。

## 下一棒建议

- Windows 发布后先对 1 个 unresolved 群保存人工名，回传 count/status/布尔；通过后批量处理剩余 unresolved 群。
- 本 P0 收口后，回接 `真实首跑入库候选 0 最小补证`，解释 raw inserted/candidate created 为 0 的原因。

## 回报投递

- 已追加监工回报队列完成块。
- 已发监工：send_input 调用失败，返回 `agent not found`；未取得 submission_id；以回报队列作为兜底入口。
