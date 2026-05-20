# 微信agent专项 后端/API 助手状态卡

更新时间：2026-05-20 12:45 CST

## 线程身份

- 线程名：微信agent专项 后端/API 助手
- 线程 id：019e3a22-0b1d-7ea0-9c36-7a86d3a8883a
- 监工线程 id：019e2a4a-664f-76b3-9533-fbbbfc7f34c5
- 负责范围：后端 API、候选池口径、状态持久化、配置保存、草稿日报 / 转述摘要数据接线、字段白名单、安全边界和测试
- 明确边界：不做监工；不做前台/UI；不执行新的真实读取；不执行 `wx history`、`wx search`、`wx export`、`wx new-messages`；不写正式待办池、正式日报、Obsidian 正式区或外部系统；默认 `real_read_enabled=false` 必须保持

## 本轮任务

- 任务标记：`监工返工：2026-05-20｜后端API｜群管理归档删除与日报生成反馈验收底座`
- 状态：完成，待测试审查 / 监工验收
- 结论：已补齐监控群归档 / 删除本地配置能力、统计读回口径和日报生成反馈状态字段；8765 已重载到当前代码，Windows P0 主路径接口继续 HTTP 200，运行态敏感命中 0。
- 回传状态：`send_input` 不在当前工具列表，无法直发监工线程；按规则追加监工回报队列。已发监工：send_input 不可用。

## 改动文件

- `/Users/gd/Desktop/微信agent专项/src/wechat_feedback_app/config.py`
- `/Users/gd/Desktop/微信agent专项/src/wechat_feedback_app/routes.py`
- `/Users/gd/Desktop/微信agent专项/tests/test_windows_p0_backend.py`
- `/Users/gd/Desktop/微信agent专项/tests/test_real_trial_latest_visibility.py`
- `/Users/gd/Desktop/微信agent专项/开发/状态卡/后端API助手.md`
- `/Users/gd/Desktop/微信agent专项/开发/监工回报队列.md`

说明：工作区仍有前序和并行线程未提交改动；本棒只做后端/API归档删除、日报生成反馈、测试和运行态收口，未回滚前台/UI或其他线程改动。

## 归档 / 删除接口与统计读回

- 新增 `POST /api/monitor-groups/{group_id}/archive`：本地软归档，设置 `archived=true`，同时移出启用、每日监控和日报统计；保留群档案，可继续在列表 / 详情读回归档状态。
- 新增 `POST /api/monitor-groups/{group_id}/delete`：要求 `confirm_delete=true` 或等价确认字段；只删除本项目本地监控群配置，不触碰真实微信、客户系统或正式区。
- `/api/monitor-groups` 补齐 `active_count`、`archived_count`、`daily_center_count`、`actions.archive/delete`、`can_archive`、`can_delete`、`delete_requires_confirmation`、`archived`、`status_label`、`counts_in_daily_center`。
- 统计口径：`counts_in_daily_center` 只允许启用、每日监控、纳入日报、已验证且未归档的群计入；待验证群和归档群不计入日报中心监控群数。
- 单测覆盖：归档后日报中心统计归 0；删除未确认返回 `confirmation_required`，确认后本地配置删除且详情 `not_found`。

## 日报生成反馈底座

- `/api/daily-center/generation-status` 补齐 `feedback_state`、`running`、`success`、`failed`、`old_report_preserved`，前台点击后可在 1 秒内拿到 idle / success / failed 等价状态字段。
- `/api/daily-center/generate` 失败路径返回 `failed=true`、`error_code`、`retry_available=true`、`old_report_preserved`；不清空旧日报正文，不写正式日报或外部系统。
- 成功 / 无新候选路径返回 `success=true`、`running=false` 和旧日报保留状态摘要。

## 测试 / 证据

- 相关专项：`.codex_py_logs/py-run-20260520-124114.log`，35 tests OK。
- 全量 pytest：`.codex_py_logs/py-run-20260520-124118.log`，101 passed。
- `git diff --check`：exit=0。
- 8765 重载：`.codex_runtime_logs/restart-8765-archive-delete-20260520-124132.log`，exit=0，新进程启动于 2026-05-20 12:41:43 CST。
- HTTP smoke：`.codex_runtime_logs/http-smoke-archive-delete-20260520-124232.log`，exit=0。

## 运行态 HTTP Smoke

- `/api/windows-readiness`：HTTP 200，`real_read_enabled=false`。
- `/api/monitor-groups`：HTTP 200，`total_count=4`，`daily_center_count=1`，`archived_count=0`，归档 / 删除动作字段存在，群级字段契约存在。
- `/api/internal-people`：HTTP 200，`count=1`。
- `/api/internal-people/suggestions`：HTTP 200。
- `/api/messages/v1`：HTTP 200，群筛选字段存在。
- `/api/customer-options`：HTTP 200，`count=21`。
- `/api/daily-center`：HTTP 200，`monitor_group_count=1`，today focus 存在。
- `/api/daily-center/generation-status`：HTTP 200，`status=idle`，`feedback_state=idle`，`running/success/failed/old_report_preserved` 字段存在。
- 运行态字段白名单：敏感命中 0。

## 字段白名单 / 安全边界

- 本轮状态卡、回报队列和 smoke 只记录 HTTP status、count/status、字段存在性、布尔值和日志路径；未摘录真实消息正文、候选正文、草稿正文、真实会话列表、真实成员名单、客户名单或真实路径明细。
- 未执行新的真实读取，未执行真实 roster 同步，未执行 `wx history/search/export/new-messages`。
- 未打开或摘录真实 SQLite / exports 正文。
- 未写正式日报、正式待办池、Obsidian 正式区或外部系统。
- `config/app.yaml`、`config/app.example.yaml`、`config/app.windows.example.yaml` 均保持 `real_read_enabled=false`；保存配置和归档 / 删除不会开启真实读取。

## 剩余风险

- 运行态 smoke 为 GET 字段级验证；为避免改动真实本地监控群配置，未在 8765 当前配置上实际归档或删除真实群，归档 / 删除 mutation 已由 fake/stub 单测覆盖。
- 当前 Mac 开发运行态 `/api/windows-readiness` 仍会正确提示配置隔离需复核；Windows 实机仍需使用本机正式配置再验收。
- 本轮不做前台按钮接线验收；前台需消费后端新增动作字段并在删除前做二次确认。

## 下一棒建议

- 派测试审查做后端/API复验：归档 / 删除单测证据、运行态 `/api/monitor-groups` 字段契约、日报生成状态字段、Windows P0 接口 200 和字段白名单。
- 派前台/UI补入口：群管理卡片增加归档、删除按钮；删除前弹二次确认；日报生成按钮点击后轮询或读取 `/api/daily-center/generation-status`。
- Windows 实机前最后复验只记录 count/status/字段存在性，不摘录真实群名、客户名、成员名或消息内容。
