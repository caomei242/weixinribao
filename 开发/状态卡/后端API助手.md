# 微信agent专项 后端/API 助手状态卡

更新时间：2026-05-20 23:26 CST

## 线程身份

- 线程名：微信agent专项 后端/API 助手
- 线程 id：019e3a22-0b1d-7ea0-9c36-7a86d3a8883a
- 监工线程 id：019e2a4a-664f-76b3-9533-fbbbfc7f34c5
- 负责范围：后端 API、候选池口径、状态持久化、配置保存、草稿日报 / 转述摘要数据接线、字段白名单、安全边界和测试
- 明确边界：不做监工；不做前台/UI；不手工绕过系统执行 `wx history/search/export/new-messages`；不执行真实 roster 同步；不自动外发 / 回复；不写正式待办池、正式日报、Obsidian 正式区或外部系统；默认 `real_read_enabled=false` 必须保持

## 本轮任务

- 任务标记：`2026-05-20｜后端API｜unresolved 群名占位去重防误合并`
- 状态：完成，待监工验收
- 结论：已收口发布前小修。`upsert_detected_monitor_groups()` 的名称去重只允许 resolved 可读 `display_name` 参与；`unresolved`、`群名待解析`、`internal_identifier_only` 不再作为跨 external_id 去重键。

## 改动文件

- `/Users/gd/Desktop/微信agent专项/src/wechat_feedback_app/routes.py`
- `/Users/gd/Desktop/微信agent专项/tests/test_persistent_real_read_contract.py`
- `/Users/gd/Desktop/微信agent专项/开发/状态卡/后端API助手.md`
- `/Users/gd/Desktop/微信agent专项/开发/监工回报队列.md`

说明：未改前台静态文件；未回滚其他线程已存在改动。

## 关键实现

- `by_name` 只索引 resolved 可读群名，避免多个待解析群因为同一个占位文案被误合并。
- 同一 external_id 仍优先按 id 匹配。
- 同一 external_id 从 unresolved 后续拿到 resolved 可读名时仍可升级显示名。
- 不同 external_id 即使同为 unresolved / 待解析占位，也会新增为不同本地监控群记录。

## 测试 / 证据

- 最小相关：`python exit=0 log=.codex_py_logs/py-run-20260520-232615.log`，27 passed。
- 相关后端专项：`python exit=0 log=.codex_py_logs/py-run-20260520-232622.log`，102 passed。
- 全量 pytest：`python exit=0 log=.codex_py_logs/py-run-20260520-232630.log`，148 passed。
- `git diff --check`：通过。

## 验收覆盖

- 已有 unresolved session A，再检测不同 external_id 的 unresolved session B：B 会新增，不被占位名误合并。
- 已有 unresolved 同一 external_id，后续探针拿到 resolved 可读名：显示名会升级。
- 旧 all_wechat_groups、非群过滤、本地 UI 主显示字段、config-center forbidden 白名单均不回退。

## 安全边界

- 未执行真实消息读取。
- 未执行真实 roster 同步。
- 未手工执行 `wx history/search/export/new-messages`。
- 未自动外发 / 自动回复。
- 未写正式日报、正式待办池、Obsidian 正式区或外部系统。
- 状态卡和回报不摘录真实群名、真实 id、真实消息、成员名单、客户名单、wxid/key/salt、DB path、IP、daemon 原始日志。
- `real_read_enabled=false` 保持。

## 是否需要前台配合

- 本次是后端 upsert 去重小修，不需要前台配合。
- 前台仍需沿用上一棒 unresolved 显示合同：收到待解析状态时展示用户态文案，不用内部 id 兜底标题。

## 剩余风险

- 本棒未做 Windows 运行态重载 / HTTP smoke；发布后仍需 Windows 侧拉取、重启并复验。
- 若上游探针只给内部标识，页面只能显示待解析状态；真实可读群名仍依赖上游提供可读名称字段。

## 下一棒建议

- 监工发布前可合并本小修进同一批提交。
- 测试审查重点复验 unresolved 不误合并、同 external_id 可升级、config-center forbidden 不回退。

## 回报投递

- 已追加监工回报队列完成块。
- 已发监工：send_input 工具当前不可用，未取得 submission_id；以回报队列作为兜底入口。
