# 微信agent专项 后端/API 助手状态卡

更新时间：2026-05-20 14:25 CST

## 线程身份

- 线程名：微信agent专项 后端/API 助手
- 线程 id：019e3a22-0b1d-7ea0-9c36-7a86d3a8883a
- 监工线程 id：019e2a4a-664f-76b3-9533-fbbbfc7f34c5
- 负责范围：后端 API、候选池口径、状态持久化、配置保存、草稿日报 / 转述摘要数据接线、字段白名单、安全边界和测试
- 明确边界：不做监工；不做前台/UI；不执行新的真实读取；不执行 `wx history`、`wx search`、`wx export`、`wx new-messages`；不写正式待办池、正式日报、Obsidian 正式区或外部系统；默认 `real_read_enabled=false` 必须保持

## 本轮任务

- 任务标记：`监工派工：2026-05-20｜后端API｜下一轮日报产品化与配置减负数据底座`
- 状态：完成，待测试审查 / 监工验收
- 结论：已在 Windows P0 冻结基准之外补齐下一轮后端数据底座：日报中心产品化分区、监控群稳定下拉 / 保存读回契约、我方人员建议 / 保存读回契约、消息明细 group-first 摘要字段。8765 已重载，新字段运行态 HTTP smoke 通过，敏感命中 0。
- 回传状态：`send_input` 不在当前工具列表，无法直发监工线程；按规则追加监工回报队列。已发监工：send_input 不可用。

## 改动文件

- `/Users/gd/Desktop/微信agent专项/src/wechat_feedback_app/routes.py`
- `/Users/gd/Desktop/微信agent专项/tests/test_next_round_product_backend.py`
- `/Users/gd/Desktop/微信agent专项/开发/状态卡/后端API助手.md`
- `/Users/gd/Desktop/微信agent专项/开发/监工回报队列.md`

说明：工作区另有前台/UI并行改动；本棒只改后端/API和后端专项测试，未覆盖 Windows P0 实机复验口径。

## 日报中心字段

- `/api/daily-center` 新增 `today_top_followups`、`unfinished_followups`、`historical_unfinished`，每项只返回 `display_id / summary_safe / human_status / action_label / risk_label / source_label / count/status` 级安全字段。
- 新增 `report_full_text`、`report_human_text`，并在 `report` 内同步提供同名字段，便于前台直接渲染人话日报全文。
- 新增 `generation_status` 内嵌摘要，复用已有 `feedback_state / running / success / failed / old_report_preserved` 口径。
- 新增 `source` 摘要，返回本地候选、本地草稿、监控群、未完成和历史未完成 count/status，不暴露正文证据。

## 群管理下拉字段

- `/api/monitor-groups` 和 `/api/monitor-groups/{group_id}` 补齐 `field_options`、`customer_name_options`、`group_type_options`、`customer_stage_options`、`owner_options`、`module_options`、`option_source_summary`。
- 保留已通过的新增、编辑、停用、归档、删除、客户识别、roster 授权同步字段。
- 新增 `save_contract`，标明保存 payload 与读回字段，前台可以稳定保存并再读回客户、群类型、客户阶段、负责人等配置。

## 我方人员建议 / 保存读回

- `/api/internal-people` 新增 `suggestion_contract`、`save_readback_contract`、`downstream_status`。
- `/api/internal-people/suggestions` 新增 `suggestion_contract` 和每条建议的 `suggested_fields`，来源仍限本地人员库、最近发送人、监控群 roster / 成员池。
- 保存人员后返回 `readback_fields`，并继续保证 aliases 分割去重、保存 / 更新 / 停用读回、下游 sender/candidate/group/daily/transfer count/status 级接线。
- 只有内部 ID / wxid 且无显示名时仍返回 `requires_display_name=true`，不允许保存成用户不可读标识。

## 消息多群口径

- `/api/messages/v1` 新增 `message_count`、`group_count`、`groups_count`、`group_status`、`single_group_no_fallback`、`empty_state_label`、`group_first_contract`。
- 单群查询继续按 `group_id` 过滤；单群 0 条时不回退全部群，只返回空态。
- 群列表继续提供 count/status 级字段，右侧详情定位仍使用 `detail_target`。

## 测试 / 证据

- 新增专项：`.codex_py_logs/py-run-20260520-142056.log`，4 tests OK。
- 相关后端专项：`.codex_py_logs/py-run-20260520-142101.log`，65 tests OK。
- 全量 pytest：`.codex_py_logs/py-run-20260520-142107.log`，105 passed。
- `git diff --check`：exit=0。
- 8765 重载：`.codex_runtime_logs/restart-8765-next-round-product-20260520-142135.log`，exit=0，新进程启动于 2026-05-20 14:21:35 CST。
- HTTP smoke：`.codex_runtime_logs/http-smoke-next-round-product-20260520-142214.log`，exit=0。

## 运行态 HTTP Smoke

- `/api/daily-center`：HTTP 200，`today_top_followups / unfinished_followups / historical_unfinished / report_full_text / report_human_text / generation_status` 字段存在。
- `/api/monitor-groups`：HTTP 200，`field_options / customer_options / group_type_options / customer_stage_options / owner_options / save_contract` 字段存在。
- `/api/internal-people`：HTTP 200，`suggestion_contract / save_readback_contract / downstream_status` 字段存在。
- `/api/internal-people/suggestions`：HTTP 200，`status=ok`，建议字段契约存在。
- `/api/messages/v1`：HTTP 200，`group_first_contract` 字段存在；单群查询 HTTP 200，`single_group_no_fallback=true`。
- 运行态字段白名单：敏感命中 0。

## 字段白名单 / 安全边界

- 本轮状态卡、回报队列和 smoke 只记录 HTTP status、count/status、字段存在性、布尔值和日志路径；未摘录真实消息正文、候选正文、草稿正文、真实会话列表、真实成员名单、客户名单或真实路径明细。
- 未执行新的真实读取，未执行真实 roster 同步，未执行 `wx history/search/export/new-messages`。
- 未打开或摘录真实 SQLite / exports 正文。
- 未写正式日报、正式待办池、Obsidian 正式区或外部系统。
- `config/app.yaml`、`config/app.example.yaml`、`config/app.windows.example.yaml` 均保持 `real_read_enabled=false`。

## 剩余风险

- 本轮是下一轮产品化数据底座，不代表 Windows P0 实机部署验收通过；Windows 实机线仍只按冻结基准验 wx-cli.exe、归档/删除可用、服务重启自启。
- 客户 / 人员 / 群下拉选项只来自现有本地配置、只读客户源、已保存群档案、已有 roster / 已出现成员；没有执行新的真实同步。
- 前台/UI仍需消费这些新增字段，把日报中心、群管理和人员配置页做成更少手填的产品化体验。

## 下一棒建议

- 派前台/UI接入：日报中心分区、群管理稳定下拉、我方人员建议字段、messages/v1 group-first 摘要。
- 派测试审查复核本轮新增字段、字段白名单、`real_read_enabled=false`、全量测试和运行态 smoke。
- Windows 实机复验线继续隔离，不把本轮下一轮开发字段作为实机通过前置条件。
