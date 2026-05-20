# 微信agent专项 后端/API 助手状态卡

更新时间：2026-05-20 20:10 CST

## 线程身份

- 线程名：微信agent专项 后端/API 助手
- 线程 id：019e3a22-0b1d-7ea0-9c36-7a86d3a8883a
- 监工线程 id：019e2a4a-664f-76b3-9533-fbbbfc7f34c5
- 负责范围：后端 API、候选池口径、状态持久化、配置保存、草稿日报 / 转述摘要数据接线、字段白名单、安全边界和测试
- 明确边界：不做监工；不做前台/UI；不手工绕过系统执行 `wx history/search/export/new-messages`；不执行真实 roster 同步；不自动外发 / 回复；不写正式待办池、正式日报、Obsidian 正式区或外部系统；默认 `real_read_enabled=false` 必须保持

## 本轮任务

- 任务标记：`监工返工：2026-05-20｜后端API｜config-center 字段白名单收紧`
- 归属任务：`监工派工：2026-05-20｜后端API｜长期真实读取授权实战版`
- 状态：完成，待测试审查 / 监工验收
- 结论：已收紧 `/api/config-center` full payload。`status.latest_trial` 改为 pathless 摘要，不再返回 `sqlite_path` / DB path；`editable.sessions[]` 的成员池改为 count/status 摘要，不再返回 `member_name_options`、`roster_member_names` 或 `member_options.names/items/appeared_members/roster_members/full_members`。
- 回传状态：`send_input` 不在当前工具列表，无法直发监工线程；按规则追加监工回报队列。已发监工：send_input 不可用，已走回报队列。

## 改动文件

- `/Users/gd/Desktop/微信agent专项/src/wechat_feedback_app/routes.py`
- `/Users/gd/Desktop/微信agent专项/tests/test_persistent_real_read_contract.py`
- `/Users/gd/Desktop/微信agent专项/tests/test_daily_center_monitor_groups.py`
- `/Users/gd/Desktop/微信agent专项/开发/状态卡/后端API助手.md`
- `/Users/gd/Desktop/微信agent专项/开发/监工回报队列.md`

说明：工作区仍包含前一棒长期授权实战版改动及其他线程历史脏改；本棒只做 config-center 白名单收紧与测试补证，未回滚其他线程内容。

## 字段白名单收紧

- `status.latest_trial`：由完整 `latest_real_trial_payload` 改为 `latest_real_trial_config_center_summary`，仅保留 status/count/布尔和 read_shape 摘要。
- 路径字段：不再返回 `sqlite_path`、`db_path`、`database_path`；`path_fields_returned=false`。
- 成员字段：`editable.sessions[].member_options` 改为 `monitor_group_member_options_summary`，只含 scope/complete/status_label/source_label/count/available_count/appeared_count/roster_count/refresh_status/roster_status/full_sync 状态等摘要。
- 移除名单级字段：`member_name_options`、`roster_member_names`、`member_options.names`、`items`、`appeared_members`、`roster_members`、`full_members`。
- 详情页兼容：`/api/monitor-groups/{group_id}` 和刷新/同步接口仍可作为前台成员选择器的数据源；本棒只收紧 `config-center` full payload 安全验收面。

## 保持不回退

- 长期授权主契约不回退：`authorization_mode=persistent`、默认关闭、手动触发、定时触发、暂停 blocked、多白名单群、去重、本地 raw/normalized/candidate 链路仍由相关测试覆盖。
- `/api/status` 与 `/api/real-trial/run` persistent 默认关闭路径未改。
- `real_read_enabled=false` / `real_read_enabled_after=false` 口径保持。

## 测试 / 证据

- 红灯证据：`.codex_py_logs/py-run-20260520-200717.log`，full payload scan 命中 `status.latest_trial.sqlite_path` 与成员名单级字段。
- 定向白名单测试：`.codex_py_logs/py-run-20260520-200831.log`，5 selected passed。
- 相关后端专项：`.codex_py_logs/py-run-20260520-200841.log`，75 passed，覆盖长期授权、群成员、expanded、一性入口、真实读取旧路径、字段白名单、wx-cli 适配和去重。
- 全量 pytest：`.codex_py_logs/py-run-20260520-200913.log`，132 passed。
- `git diff --check`：exit=0。
- 运行态 HTTP smoke：`.codex_runtime_logs/http-smoke-config-center-whitelist-20260520-201019.log`，node exit=0。

## 运行态 Smoke 摘要

- `/api/config-center`：HTTP 200。
- `status.latest_trial` 存在且 `path_fields_returned=false`。
- session count 仅记录数量；`first_session_member_list_returned=false`。
- forbidden field hit count = 0。
- `sqlite_path` 文本命中 false。
- `member_name_options` 文本命中 false。
- `raw_payload` 文本命中 false。

## 字段白名单 / 安全边界

- 本轮未执行真实读取、未执行真实 roster 同步、未执行 `wx history/search/export/new-messages`。
- 未写正式日报、正式待办池、Obsidian 正式区或外部系统。
- 未摘录真实消息正文、候选正文、草稿正文、真实群名、真实会话、真实成员、客户名单、wxid/key/salt、DB 路径、IP、daemon 原始日志或 Windows 敏感路径。
- 状态卡、回报队列和 smoke 只记录 status/count/error_code/字段存在性/布尔值和日志路径。

## 剩余风险

- 前台若此前依赖 `/api/config-center.editable.sessions[].member_name_options` 渲染成员下拉，需要改为调用 `/api/monitor-groups/{group_id}` 或 refresh/sync 成员接口获取详情页名单；本棒已在 config-center 提供 `member_options_detail_endpoint` 和摘要。
- Windows 仍需拉取包含本棒字段白名单收紧的新代码后再复验。

## 下一棒建议

- 派测试审查复核 `/api/config-center` full payload key-path 扫描，重点看 `sqlite_path`、DB path、`member_name_options`、成员名单级字段均为空命中。
- 前台/UI 若需要修复下拉来源，使用 `/api/monitor-groups/{group_id}` 详情接口，不再从 config-center full payload 取名单。
- 通过后再做发布收口与 Windows 拉取复验。
