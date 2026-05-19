# 微信agent专项 后端/API 助手状态卡

更新时间：2026-05-18 18:01 CST

## 线程身份

- 线程名：微信agent专项 后端/API 助手
- 线程 id：019e3a22-0b1d-7ea0-9c36-7a86d3a8883a
- 监工线程 id：019e2a4a-664f-76b3-9533-fbbbfc7f34c5
- 负责范围：后端 API、候选池口径、状态持久化、配置保存、草稿日报 / 转述摘要数据接线、字段白名单、安全边界和测试
- 明确边界：不做监工；不做前台/UI；不执行新的真实读取；不执行 `wx history`、`wx search`、`wx export`、`wx new-messages`；不写正式待办池、正式日报、Obsidian 正式区或外部系统；默认 `real_read_enabled=false` 必须保持

## 本轮任务

- 任务标记：`监工派工：2026-05-18｜后端API｜V1 P1 候选池统一与人话文案数据口径`
- 状态：完成，待测试审查 / 监工验收
- 结论：已完成后端/API口径统一。`/api/inbox/v1` 新增统一候选收件箱和转述任务人话字段；转述摘要预览默认跟随统一候选池，在主池为空时自动使用最近试读候选；不改 `static/index.html`、`static/styles.css`，也未改 `static/app.js`。
- 回传状态：已向监工短回 `【完成回报】`；初始化回报已发监工：019e3a24-3f96-75d3-9cfa-069e385c496a；登记回执确认已发监工：019e3a25-cfde-7fc1-9a4a-35be83683939；脱敏源码返工完成回报已发监工：019e3a33-9481-73e1-bf64-8f8a8bf33300；运行态收口完成回报已发监工：019e3a3d-09cf-7f40-8797-bb5da4122eef；P1 候选池与人话文案口径完成回报已发监工：019e3a89-b988-71f2-9e06-7af2d277e8ed。`submission_id` 只算投递记录，不算验收通过。

## 已读范围

- `/Users/gd/Desktop/微信agent专项/AGENTS.md`
- `/Users/gd/Desktop/微信agent专项/README.md`
- `/Users/gd/Desktop/微信agent专项/开发/开发需求收件箱.md`
- `/Users/gd/Desktop/微信agent专项/开发/固定线程登记表.md`
- `/Users/gd/Desktop/微信agent专项/开发/监工回报队列.md`
- `/Users/gd/Desktop/微信agent专项/开发/产品走查/微信反馈采集工作台第一阶段产品走查.md`
- `/Users/gd/Desktop/微信agent专项/开发/产品走查/采集后台配置与导出模板产品走查.md`
- `/Users/gd/Desktop/微信agent专项/开发/产品走查/最近50条真实样本产品优化.md`
- `/Users/gd/Desktop/微信agent专项/开发/产品走查/微信反馈防漏收件箱V1-人工走查记录.md`
- `/Users/gd/Desktop/微信agent专项/开发/产品走查/微信反馈防漏收件箱V1-返工包草稿.md`
- `/Users/gd/Desktop/微信agent专项/开发/状态卡/产品助手.md`
- `/Users/gd/Desktop/微信agent专项/开发/状态卡/开发助手.md`
- `/Users/gd/Desktop/微信agent专项/开发/状态卡/测试审查助手.md`

## 当前项目判断

- 当前主线是 `微信反馈防漏收件箱 V1` 实战走查后的 P0 主流程闭环返工。
- 监工已把 P0 主流程返工派给开发助手；本线程后续适合承接其中的后端/API切片，例如候选池统一口径、配置保存约束、草稿日报 / 转述摘要数据源接线、状态持久化和字段白名单测试。
- 固定线程登记表已由监工登记 `后端/API 助手`；后续等监工按任务标记单独派后端/API切片。

## 后端/API关注点

- 默认真实读取关闭必须作为配置保存和 API 输出的稳定边界，保存配置不得把 `real_read_enabled=false` 持久改成开启。
- 候选池产品口径应对用户只暴露一个 `候选收件箱`；内部来源只作为状态标签或数据源元信息，不让用户理解多个池子。
- 草稿日报和转述摘要应能明确选择或继承数据源，支持最近试读候选与今日处理候选的安全接线，但不得写正式区。
- API、状态卡、回报队列、测试日志和截图证据只输出字段名、count、status、error_code、脱敏状态和必要日志路径，不输出真实消息正文、候选正文、草稿正文、真实会话列表、敏感标识、真实数据库路径或 daemon 原始日志。
- 后续如需读取草莓客户管理系统做群 / 客户打标匹配，只能只读匹配并写入微信项目本地配置，不反向修改客户系统资料。

## 测试 / 证据

- TDD 红灯：`.codex_py_logs/py-run-20260518-175120.log`，新增 `inbox_v1` 统一候选池和转述摘要默认来源测试按预期失败。
- TDD 绿灯：`.codex_py_logs/py-run-20260518-175804.log`，两条新增目标测试通过。
- 相关测试：`.codex_py_logs/py-run-20260518-175951.log`，`tests/test_real_trial_latest_visibility.py tests/test_daily_control.py tests/test_exporter.py` 通过。
- 全量 pytest：`.codex_py_logs/py-run-20260518-175958.log`，通过。
- 运行态重启：执行 launchctl 作业重启后，8765 监听进程更新为 PID 49953。
- 运行态 HTTP smoke：`.codex_runtime_logs/http-smoke-20260518-180050.log`，`/api/inbox/v1` 命中 `candidate_count=3`、`requires_source_switch=false`、人话字段开发词命中 0；转述摘要预览 `data_source=real_trial`、`item_count=3`、`human_task` 开发词命中 0。
- `git diff --check`：exit=0。
- 本轮未执行真实 `wx-cli`，未执行真实读取类命令。
- 本轮未打开真实 SQLite / exports 正文。
- 本轮未摘录真实消息正文、候选正文、草稿日报正文、真实会话列表、敏感标识、真实数据库路径或 daemon 原始日志。

## 脱敏覆盖范围

- 继续沿用既有 `redact_visible_text`。
- 新增 `summary_safe`、`reason_safe` 等候选人话字段时继续走脱敏安全摘要，而不是返回原文证据或 raw payload。
- 转述摘要 `human_task.copy_ready_lines` 继续走安全摘要，不回显敏感标识。

## 字段白名单结果

- `candidate_inbox` 人话字段不再要求前台先选 `workspace / real_trial`；运行态 smoke 显示开发词命中 0。
- 转述摘要预览默认来源会在主池为空时自动切到最近试读候选，不再先表现成 0 条。
- 关键人话字段测试继续限制不出现 `workspace / real_trial / pending / none / tech / ops / resolved / real_read_disabled / formal_write`。
- API 仍不返回真实消息正文、候选正文原文证据、raw payload、wxid、key、salt、真实 DB 路径或 daemon 原始日志。

## 改动文件

- `/Users/gd/Desktop/微信agent专项/src/wechat_feedback_app/routes.py`
- `/Users/gd/Desktop/微信agent专项/tests/test_real_trial_latest_visibility.py`
- `/Users/gd/Desktop/微信agent专项/tests/test_exporter.py`
- `/Users/gd/Desktop/微信agent专项/.codex_runtime_logs/http-smoke-20260518-180050.log`
- `/Users/gd/Desktop/微信agent专项/开发/状态卡/后端API助手.md`

## 剩余风险

- 仓库当前存在大量既有 untracked 文件，`git diff` 不展示普通文件级 diff；本轮改动文件已在上方列出，未执行 `git add` / `git commit`。
- 当前只统一了后端/API数据口径，前台是否完全消费 `candidate_inbox` / `human_task` 新字段，仍需前台/UI助手接线。
- 运行态当前已通过字段级 smoke；若后续再次编辑后端/API，需要同步重启 8765 服务或启用明确的重载策略。
- 源码层继续只覆盖 wxid 样式可见文本脱敏；其他未来新增敏感标识字段仍需保持字段白名单测试。
- P1 的客户系统只读匹配与全局我方人员库会触及跨项目只读数据，后续派工需单独明确读取范围和字段脱敏规则。

## 下一棒建议

- 建议派测试审查助手复核这棒的三件事：主池 0 + 最近试读 3 时统一候选池默认返回 3；`candidate_inbox` / `human_task` 人话字段无开发词；转述摘要预览默认来源已跟随统一候选池。
- 前台/UI助手下一棒可直接接 `candidate_inbox` 与 `transfer_task` / `human_task`，把“候选收件箱只暴露一套口径”和“转述摘要像用户任务”真正落到页面上。
