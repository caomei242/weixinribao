# 微信agent专项 后端/API 助手状态卡

更新时间：2026-05-20 21:18 CST

## 线程身份

- 线程名：微信agent专项 后端/API 助手
- 线程 id：019e3a22-0b1d-7ea0-9c36-7a86d3a8883a
- 监工线程 id：019e2a4a-664f-76b3-9533-fbbbfc7f34c5
- 负责范围：后端 API、候选池口径、状态持久化、配置保存、草稿日报 / 转述摘要数据接线、字段白名单、安全边界和测试
- 明确边界：不做监工；不做前台/UI；不手工绕过系统执行 `wx history/search/export/new-messages`；不执行真实 roster 同步；不自动外发 / 回复；不写正式待办池、正式日报、Obsidian 正式区或外部系统；默认 `real_read_enabled=false` 必须保持

## 本轮任务

- 任务标记：`监工返工：2026-05-20｜后端API｜all_wechat_groups 非群英文误判修复`
- 关联复核：`监工派工：2026-05-20｜测试审查｜persistent 首跑范围扩为全部微信群复核`
- 状态：完成，待测试审查 / 监工验收
- 结论：已收紧 `all_wechat_groups` 微信群识别逻辑。英文 `room` / `group` 不再从 display/name/haystack 里做短 token 模糊命中；英文真实群必须依赖明确布尔字段、`@chatroom`、`chatroom` / `group` 类型字段或 `room_id/chatroom_id` 等结构化信号。
- 回传状态：已尝试 `send_input` 直发监工线程，返回 `agent not found`；按规则追加监工回报队列。已发监工：直发失败，已走回报队列。

## 改动文件

- `/Users/gd/Desktop/微信agent专项/src/wechat_feedback_app/routes.py`
- `/Users/gd/Desktop/微信agent专项/tests/test_persistent_real_read_contract.py`
- `/Users/gd/Desktop/微信agent专项/开发/状态卡/后端API助手.md`
- `/Users/gd/Desktop/微信agent专项/开发/监工回报队列.md`

说明：工作区仍包含前序任务与其他线程历史脏改；本棒只做 all_wechat_groups 非群英文误判修复与测试补证，未回滚其他内容。

## 识别规则修复

- 保留强信号：
  - `is_group`、`is_group_chat`、`group`、`is_chatroom` 等布尔字段为 true。
  - 会话 id / room id 中包含 `@chatroom`。
  - 类型字段明确为 `chatroom`、`group`、`wechat_group`、`group_chat`。
  - 存在 `room_id` / `chatroom_id` 结构化字段。
  - 中文 display/name 中出现“微信群 / 群聊”。
- 移除误判来源：
  - 不再用英文短 token `group` / `room` 扫完整 display/name/haystack。
  - 非群英文名称即使包含 `room` / `group`，没有明确结构化群信号也不会入选。
- 负向过滤仍保留：公众号、单聊、系统 / filehelper 等非群会话排除。

## 测试补证

- 新增 fake/stub 测试：非群英文会话名含 `room` / `group` 不入选；英文真实群名只有带 `chatroom` 结构化信号才入选。
- 保持原有通过项：`all_wechat_groups` / `include_all_detected_groups` 进入 fake executor、探针失败 blocked 不调用 executor、旧 `include_all_enabled_whitelist` 白名单模式不回退。
- 字段白名单继续断言响应不返回探针名称、会话 id、真实正文、成员、客户、wxid、DB path、daemon 等敏感字段。

## 测试 / 证据

- 红灯证据：`.codex_py_logs/py-run-20260520-211711.log`，新增英文误判测试失败，`detected_group_count` 误为 3。
- persistent 专项：`.codex_py_logs/py-run-20260520-211744.log`，16 passed。
- 相关后端专项：`.codex_py_logs/py-run-20260520-211751.log`，93 passed。
- 全量 pytest：`.codex_py_logs/py-run-20260520-211759.log`，137 passed。
- `git diff --check`：exit=0。

## 字段白名单 / 安全边界

- 响应只返回 count/status/error_code、detected/excluded count、入库/候选/去重/失败摘要。
- `groups_returned=false`、`session_names_returned=false` 保持。
- 本轮未执行真实读取、未执行真实 roster 同步、未执行 `wx history/search/export/new-messages`。
- 未自动外发 / 自动回复。
- 未写正式日报、正式待办池、Obsidian 正式区或外部系统。
- 未摘录真实消息正文、候选正文、草稿正文、真实群名、真实会话、真实成员、客户名单、wxid/key/salt、DB 路径、IP、daemon 原始日志或 Windows 敏感路径。
- `real_read_enabled=false` / `real_read_enabled_after=false` 保持。

## 剩余风险

- 本轮只用 fake/stub 验证，没有在 Windows 执行真实会话探针或真实首读。
- Windows wx-cli 实际 `sessions --json` 字段形态仍需发布后用 count/status smoke 验证；不得输出真实会话名。
- all scope 会把检测到的群落成本地可管理监控群；过滤规则已收紧，但真实环境仍需观察 excluded count 是否合理。

## 下一棒建议

- 派测试审查最小复验：重点看英文 `room/group` 非群误判已修复、英文真实群依赖结构化信号入选、旧白名单模式不回退、字段白名单不回退。
- 复验通过后再进入发布收口 / Windows Git 发布目录拉取；当前仍不要执行 Windows persistent 首跑。
