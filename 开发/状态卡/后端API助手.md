# 微信agent专项 后端/API 助手状态卡

更新时间：2026-05-20 18:09 CST

## 线程身份

- 线程名：微信agent专项 后端/API 助手
- 线程 id：019e3a22-0b1d-7ea0-9c36-7a86d3a8883a
- 监工线程 id：019e2a4a-664f-76b3-9533-fbbbfc7f34c5
- 负责范围：后端 API、候选池口径、状态持久化、配置保存、草稿日报 / 转述摘要数据接线、字段白名单、安全边界和测试
- 明确边界：不做监工；不做前台/UI；不执行新的真实读取；不执行 `wx history`、`wx search`、`wx export`、`wx new-messages`；不执行真实 roster 同步；不写正式待办池、正式日报、Obsidian 正式区或外部系统；默认 `real_read_enabled=false` 必须保持

## 本轮任务

- 任务标记：`监工返工：2026-05-20｜后端API｜一次性真实试验授权执行入口与 Windows 配置上限契约`
- 归属任务：`监工派工：2026-05-20｜后端API｜真实读取扩大试验代码侧能力升级`
- 状态：完成，待测试审查 / 监工验收
- 结论：已补齐一次性真实试验授权执行入口契约，并明确 Windows 配置上限切换字段。默认仍关闭；只有 `execute_once=true`、一次性授权 token / marker、测试微信号确认、一次性试验确认、窗口 / 群 / 消息 / 批次上限均通过时，才进入执行分支。测试只用 fake executor，本机未执行真实读取。
- 回传状态：`send_input` 不在当前工具列表，无法直发监工线程；按规则追加监工回报队列。已发监工：send_input 不可用。

## 改动文件

- `/Users/gd/Desktop/微信agent专项/config/app.example.yaml`
- `/Users/gd/Desktop/微信agent专项/config/app.windows.example.yaml`
- `/Users/gd/Desktop/微信agent专项/src/wechat_feedback_app/collector.py`
- `/Users/gd/Desktop/微信agent专项/src/wechat_feedback_app/config.py`
- `/Users/gd/Desktop/微信agent专项/src/wechat_feedback_app/routes.py`
- `/Users/gd/Desktop/微信agent专项/tests/test_expanded_real_trial_contract.py`
- `/Users/gd/Desktop/微信agent专项/tests/test_real_connection_redaction.py`
- `/Users/gd/Desktop/微信agent专项/开发/状态卡/后端API助手.md`
- `/Users/gd/Desktop/微信agent专项/开发/监工回报队列.md`

说明：工作区进入本棒前已有 `AGENTS.md`、测试审查状态卡、监工回报队列等历史脏改；本棒未回滚其他线程改动。

## 授权执行入口字段

- 执行入口字段：`execute_once=true` / `run_once=true` / `execute_real_trial_once=true` / `open_execution_path=true`。
- 一次性授权字段：`one_time_authorization_token` / `authorization_token` / `one_time_token`，或 `one_time_authorization_marker=true` / `one_time_authorization_confirmed=true` / `authorization_marker=true`。
- 其它必需字段仍包括：`confirmed=true`、`authorize_expanded_real_read_trial=true`、`test_wechat_account_confirmed=true`、`one_time_expanded_trial=true`，以及合法白名单 / 监控群范围。
- 未打开执行入口时返回 `dry_run_ready`，但 `error_code/reason_code=real_trial_execution_entry_not_opened`、`will_run=false`、`no_real_read_executed=true`。
- 打开执行入口但缺少一次性授权 token / marker 时返回 `blocked`，`error_code/reason_code=one_time_authorization_token_required`。

## Windows 配置上限契约

- Windows 配置切换字段：`wx_cli.expanded_real_lookback_days` 控制 `max_allowed_lookback_days`。
- 样例配置已包含：`expanded_real_lookback_days`、`expanded_real_max_groups`、`expanded_real_max_total_messages`、`expanded_real_max_messages_per_group`、`expanded_real_batch_limit`。
- 若 Windows 仍是旧 2 小时上限，可设置为约 `0.0833` 天；请求 30 天会 blocked，`limit_reason=exceeds_configured_lookback`。
- 本次授权窗口如需 30 天，Windows 运行配置需把 `wx_cli.expanded_real_lookback_days` 切到 `30` 或更高授权值；这不是写死 30 天，60 / 90 天仍走配置和显式授权。

## Blocked 原因枚举

- `expanded_trial_authorization_required`：缺少扩大试验授权。
- `expanded_trial_test_account_required`：未确认测试微信号。
- `expanded_trial_one_time_required`：未声明一次性试验。
- `one_time_authorization_token_required`：执行入口已请求但缺少一次性授权 token / marker。
- `expanded_trial_lookback_days_too_large`：请求窗口超过配置上限。
- `expanded_trial_lookback_days_invalid` / `expanded_trial_time_range_invalid`：窗口参数非法。
- `expanded_trial_no_groups_selected` / `expanded_trial_group_count_too_large`：群范围不合法。
- `expanded_trial_total_limit_too_large` / `expanded_trial_group_limit_too_large` / `expanded_trial_batch_limit_too_large`：消息或批次上限不合法。

## 响应字段

- 窗口摘要：`requested_lookback_days`、`effective_lookback_days`、`max_allowed_lookback_days`、`window_start`、`window_end`、`limit_reason`。
- 执行摘要：`will_run`、`execution.entry_opened`、`execution.no_real_read_executed`、`execution.real_read_enabled_after`、`execution_summary`、`failure_summary`。
- 安全摘要：只返回数量和状态，不返回群名 / 会话名 / 正文 / 路径明细。

## 测试 / 证据

- 一次性授权执行入口专项：`.codex_py_logs/py-run-20260520-180758.log`，15 passed，覆盖未授权 blocked、旧 2 小时上限阻断 30 天、30 天配置 + 授权字段齐全进入 fake 执行路径、执行失败摘要、字段白名单、`real_read_enabled=false` 事后保持。
- 相关后端专项：`.codex_py_logs/py-run-20260520-180807.log`，72 passed。
- 全量 pytest：`.codex_py_logs/py-run-20260520-180815.log`，121 passed。
- `git diff --check`：exit=0。
- 运行态 HTTP smoke：`.codex_runtime_logs/http-smoke-real-trial-once-contract-20260520-180858.log`，node exit=0。

## 运行态 HTTP Smoke

- `/api/status`：HTTP 200，`real_read_enabled=false`，`scope_mode=configurable_window`，`default_preset_lookback_days=30`，`max_allowed_lookback_days=30`，`execute_once_field=execute_once`，`token_required=true`，敏感命中 false。
- `/api/real-trial/run` dry-run 未开执行入口：HTTP 200，`status=dry_run_ready`，`error_code=real_trial_execution_entry_not_opened`，`will_run=false`，`no_real_read_executed=true`，`entry_opened=false`，`real_read_enabled_after=false`，窗口字段存在，敏感命中 false。
- `/api/real-trial/run` 请求执行但缺 token：HTTP 200，`status=blocked`，`error_code=one_time_authorization_token_required`，`will_run=false`，`real_read_enabled_after=false`，窗口字段存在，敏感命中 false。
- smoke 未调用 token 齐全执行路径，避免本机真实读取；执行路径只在 fake 测试中验证。

## 字段白名单 / 安全边界

- 本轮状态卡、回报队列和 smoke 只记录 HTTP status、count/status、error_code、字段存在性、布尔值和日志路径。
- 未摘录真实消息正文、候选正文、草稿正文、真实会话列表、真实成员名单、客户名单、真实群名、wxid、key、salt、真实 DB 路径、IP、Windows 敏感路径或 daemon 原始日志。
- 未执行新的真实读取，未执行真实 roster 同步，未执行 `wx history/search/export/new-messages`。
- 未打开或摘录真实 SQLite / exports 正文。
- 未自动定时采集，未写正式日报、正式待办池、Obsidian 正式区或外部系统。

## 剩余风险

- 本棒只用 fake executor 验证授权执行入口；真正执行仍需 Windows 侧配置切换、一次性授权字段齐全，并由监工 / 总控发放明确授权包。
- Windows 若仍返回 `max_allowed_lookback_days=0.0833`，说明运行配置尚未切换到本次授权窗口；需要先改运行配置再执行。
- 前台如需要显式按钮，需要另派 UI 把 `execute_once` 与一次性授权 token / marker 做成二次确认交互。

## 下一棒建议

- 派测试审查复核：一次性授权执行入口、Windows 旧 2 小时上限 blocked、30 天配置 + fake 执行路径、失败摘要、字段白名单、默认关闭、运行态 smoke。
- 若测试通过，由监工 / 总控准备 Windows 一次性授权执行 payload，明确 `execute_once`、一次性授权 token / marker、窗口配置、群范围、消息 / 批次上限和禁止项。
- Windows 执行前先复核 `/api/status` 的 `max_allowed_lookback_days` 已切到授权值，且 `real_read_enabled=false` 仍为默认状态。
