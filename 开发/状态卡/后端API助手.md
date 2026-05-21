# 微信agent专项 后端/API 助手状态卡

更新时间：2026-05-21 10:43 CST

## 线程身份

- 线程名：微信agent专项 后端/API 助手
- 线程 id：019e3a22-0b1d-7ea0-9c36-7a86d3a8883a
- 监工线程 id：019e2a4a-664f-76b3-9533-fbbbfc7f34c5
- 负责范围：后端 API、候选池口径、状态持久化、配置保存、草稿日报 / 转述摘要数据接线、字段白名单、安全边界和测试
- 明确边界：不做监工；不做前台/UI；不手工绕过系统执行 `wx history/search/export/new-messages`；不执行真实 roster 同步；不自动外发 / 回复；不写正式待办池、正式日报、Obsidian 正式区或外部系统；默认 `real_read_enabled=false` 必须保持

## 本轮任务

- 任务标记：`监工返工：2026-05-21｜后端API｜本地消息明细真实内容展示与群名可读回填`
- 状态：完成，待监工验收
- 接单来源：总控催办，监工 2.0 已落回报队列派工，submission_id=019e485b-ffbf-7713-a1ed-91466c0ea7d0
- 结论：后端/API 已区分本地 UI payload 与跨线程 / smoke / report payload；`/api/messages/v1` 本地 UI 消息项返回已入库正文 / 可读预览字段；群名 unresolved 时会从本地已入库 session/raw metadata 的可读字段回填升级，仍拿不到可读字段时保留 unresolved 状态与 reason_code。

## 改动文件

- `/Users/gd/Desktop/微信agent专项/src/wechat_feedback_app/routes.py`
- `/Users/gd/Desktop/微信agent专项/tests/test_local_ui_display_contract.py`
- `/Users/gd/Desktop/微信agent专项/tests/test_windows_p0_backend.py`
- `/Users/gd/Desktop/微信agent专项/tests/test_next_round_product_backend.py`
- `/Users/gd/Desktop/微信agent专项/tests/test_persistent_real_read_contract.py`
- `/Users/gd/Desktop/微信agent专项/开发/状态卡/后端API助手.md`
- `/Users/gd/Desktop/微信agent专项/开发/监工回报队列.md`

说明：工作区已有前台/UI与测试审查状态卡未提交改动，本线程未回滚；本轮后端主改动在 API 合同与后端测试。

## 关键实现

- `/api/messages/v1` 消息项新增 / 保持本地 UI 字段：`content_text`、`content_preview`、`message_text`、`summary`、`content_status`、`content_returned`。
- 同一消息项保留 report-safe 字段：`content_text_safe`、`content_preview_safe`、`summary_safe`；`message_ref` 仍只作为技术定位码，不作为摘要。
- payload 顶层 `safety` 标记 `local_ui_payload=true`、`content_returned=true`、`raw_payload_returned=false`、`report_safe_payload=false`。
- 群名回填增加本地安全来源：先看本项目 DB `sessions.display_name`，再看已入库消息 `raw_payload_json` 中 session/contact/chatroom metadata 的可读名字段；只用来升级本地配置，不输出 raw payload。
- unresolved 群仍保留 `display_name_status=unresolved`、`display_name_reason_code=internal_identifier_only`，内部 ID 只做匹配键，不做主标题。
- 继续保留：不同 unresolved 不误合并；同一 external_id 后续拿到可读名可升级 resolved。

## 测试 / 证据

- 新增 / 持续授权群名解析专项：`python exit=0 log=.codex_py_logs/py-run-20260521-104006.log`，30 passed。
- 相关后端专项：`python exit=0 log=.codex_py_logs/py-run-20260521-104012.log`，75 passed。
- 全量 pytest：`python exit=0 log=.codex_py_logs/py-run-20260521-104023.log`，151 passed。
- `git diff --check`：exit=0。

## 验收覆盖

- 本地 UI 消息明细可读正文 / 预览字段存在，且不再要求前台用 `message_ref` 冒充摘要。
- safe/report payload 不返回 raw payload；config-center forbidden 字段扫描不回退。
- 本地已入库 metadata 有可读群名时，monitor groups / detail / message group options 读回 resolved 主显示名。
- 只有内部标识时仍显示 unresolved 用户态状态，不把内部 ID 当群名。
- 英文 `room/group` 非群误判、旧白名单模式、all_wechat_groups 非群过滤不回退。

## 安全边界

- 未执行真实消息读取。
- 未执行真实 roster 同步。
- 未手工执行 `wx history/search/export/new-messages`。
- 未自动外发 / 自动回复。
- 未写正式日报、正式待办池、Obsidian 正式区或外部系统。
- 状态卡、回报队列、测试日志和最终回复不摘录真实群名、真实消息正文、真实会话、成员名单、客户名单、wxid/key/salt、DB path、IP、daemon 原始日志。
- `real_read_enabled=false` 保持。

## 是否需要前台配合

- 后端字段已给出；当前工作区已有前台/UI对 `content_text` / `content_preview` / `message_text` 的消费改动。
- 若 Windows 发布目录仍显示 `message_ref` / `m-00xx`，优先检查 Windows 是否拉取本轮后端与前台发布目录、服务是否重启；其次由前台/UI最小确认消息行消费 `content_preview` 而不是旧 `message_ref`。

## 剩余风险

- 若 Windows 上游 wx-cli / 本地 DB 确实没有任何可读群名 metadata，后端仍只能返回 unresolved 状态与 reason_code，不能凭内部 ID 猜群名。
- 本轮未执行 Windows 8765 运行态 smoke；需发布到 Git 管理目录并由 Windows 侧重启后复验用户路径。

## 下一棒建议

- 监工派测试审查只读复验：`/api/messages/v1` 字段存在性、内容字段与 safe 字段分层、群名回填 resolved/unresolved 两种口径、config-center forbidden 不回退。
- Windows 发布前确认当前本机改动已提交 / 推送，Windows 从 Git 发布目录拉取后再重启 8765。

## 回报投递

- 已追加监工回报队列完成块。
- 已发监工：send_input 调用失败，返回 `agent not found`；未取得 submission_id；以回报队列作为兜底入口。
