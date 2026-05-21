# 微信agent专项 前台/UI 助手状态卡

线程名：微信agent专项 前台/UI 助手
线程 id：019e3a21-b1f1-7fa0-a8ff-4ce933048d87
更新时间：2026-05-21 11:59 CST
结论：完成 `2026-05-21｜前台UI｜Windows 6 个 unresolved 群名人工命名入口预案`。只读判断显示已有“监控群名称 + 保存群档案”链路，但对 unresolved 群不够明确；本轮做了最小 UI 明示，把入口改成“本地显示名 / 监控群名称”，并在 unresolved 时提示用户手动填写后替换“群名待解析”。

## 任务标记

2026-05-21｜前台UI｜Windows 6 个 unresolved 群名人工命名入口预案

## 改动文件

- `/Users/gd/Desktop/微信agent专项/src/wechat_feedback_app/static/index.html`
- `/Users/gd/Desktop/微信agent专项/src/wechat_feedback_app/static/app.js`
- `/Users/gd/Desktop/微信agent专项/开发/状态卡/前台UI助手.md`
- `/Users/gd/Desktop/微信agent专项/开发/监工回报队列.md`

## 现有入口判断

- 现有链路：群管理详情已有 `monitorGroupDisplayName` 输入框和 `saveMonitorGroupBtn` 保存按钮。
- 保存 payload：`monitorGroupToPayload()` 会发送 `group_name` 与 `display_name`，值来自用户在 `monitorGroupDisplayName` 填写的本地显示名。
- 读回路径：保存后 `loadSelectedMonitorGroupDetail()` 会读回群档案；左侧列表和详情标题走 `monitorGroupTitle()`；消息筛选走 `readableGroupDisplayLabel()`；候选 / 日报关联 label 走可读群名 helper。
- 问题：旧文案只是“监控群名称”，unresolved 时 placeholder 为“待补群名”，入口存在但不够显眼，不足以让用户明确这是人工命名入口。

## 前台最小实现

- 将详情字段标签改为 `本地显示名 / 监控群名称`。
- 新增 `monitorGroupDisplayNameHint` 提示。
- 正常有可读名时提示：保存后用于左侧列表、消息筛选和候选 / 日报关联。
- unresolved / 无可读名时提示：当前没有可读群名；请在这里手动填写本地显示名，保存后替换“群名待解析”。
- 未改布局大结构，未新增真实读取，未改后端接口。

## 测试 / 证据

- `node --check src/wechat_feedback_app/static/app.js`：exit=0
- `git diff --check -- src/wechat_feedback_app/static/index.html src/wechat_feedback_app/static/styles.css src/wechat_feedback_app/static/app.js`：exit=0
- `git diff --check`：exit=0
- 静态 smoke：`hasLocalDisplayNameLabel=true`；`hasDisplayNameHintNode=true`；`unresolvedHintText=true`；`normalHintText=true`；`savePayloadHasGroupName=true`；`savePayloadHasDisplayName=true`；`readbackUsesTitleHelper=true`；`messageDropdownUsesReadableLabel=true`。
- 本轮未运行 Python。

## 字段白名单 / 安全边界

- 本地 UI 可以显示真实群名和真实正文。
- 状态卡、回报和 smoke 只记录 count/status/字段存在性/布尔结果；未摘录真实群名、真实正文、真实会话、成员名单、客户名单、wxid、key、salt、真实 DB 路径、IP 或 daemon 日志。
- 未执行新的真实读取。
- 未执行真实 roster 同步。
- 未执行 `wx history/search/export/new-messages`。
- 未外发 / 回复，未写正式日报、正式待办池、Obsidian 正式区或外部系统。
- 未修改 `real_read_enabled=false` 口径。

## 剩余风险

- 本轮只做前台入口明确化；保存后是否能让 6 个 unresolved 群全部变 resolved，取决于后端保存 / 读回是否把用户填的本地显示名作为主显示字段返回。
- 如 Windows 保存后仍显示“群名待解析”，下一步应先查保存接口返回的 `display_name/group_name/display_name_status/group_name_status` 字段级结果，再判断前台是否未消费。

## 下一棒建议

- 测试审查或 Windows smoke 可用 fake / 运行态字段级方式验证：unresolved 群选中后输入框提示存在，保存 payload 含 `group_name/display_name`，保存后列表主 label、详情标题、消息筛选、候选 / 日报关联 label 读回新显示名。
- 回传仍只写 count/status/字段存在性/布尔结果，不摘录真实群名。

## 回报状态

- 状态卡：已写入
- 监工短回：send_input 工具不可用，本轮按项目协议走 `/Users/gd/Desktop/微信agent专项/开发/监工回报队列.md`
