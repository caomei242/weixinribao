# 微信agent专项 前台/UI 助手状态卡

线程名：微信agent专项 前台/UI 助手
线程 id：019e3a21-b1f1-7fa0-a8ff-4ce933048d87
更新时间：2026-05-20 22:49 CST
结论：完成 `监工派工：2026-05-20｜前台UI｜本地操作台主显示字段消费复核`。本轮为前台/UI轻量复核，未发现前台静态代码把 `*_safe`、`safe_*`、`redacted_*` 当成本地主显示字段使用，因此未改前台业务代码。

## 任务标记

监工派工：2026-05-20｜前台UI｜本地操作台主显示字段消费复核

## 改动文件

- `/Users/gd/Desktop/微信agent专项/开发/状态卡/前台UI助手.md`
- `/Users/gd/Desktop/微信agent专项/开发/监工回报队列.md`

## 复核范围

- `/Users/gd/Desktop/微信agent专项/src/wechat_feedback_app/static/app.js`
- `/Users/gd/Desktop/微信agent专项/src/wechat_feedback_app/static/index.html`
- `/Users/gd/Desktop/微信agent专项/src/wechat_feedback_app/static/styles.css`
- `/Users/gd/Desktop/微信agent专项/开发/状态卡/后端API助手.md`
- `/Users/gd/Desktop/微信agent专项/开发/状态卡/测试审查助手.md`
- `/Users/gd/Desktop/微信agent专项/tests/test_local_ui_display_contract.py`

## 主显示字段消费结论

- 群管理列表 / 详情 / 搜索 / 保存读回：前台归一化优先消费 `group_name` / `display_name`、`customer_name`、`module_name`、`owner_label` 等主字段；未发现把 `group_name_safe` 或 `redacted_group_label` 作为主标题。
- 消息明细：前台继续消费 `/api/messages/v1`，群标签、客户标签、模块标签读取 `group_name`、`customer_label` / `customer_name`、`module_label`；单群空态不回退全部群逻辑未改。
- 我方人员：姓名、微信显示名、负责模块、备注、suggestion 读取 `/api/internal-people` 和 `/api/internal-people/suggestions` 的主字段；safe 字段未进入主表单。
- 候选审阅 / 日报工作台：候选本地审阅使用 `title`、`summary`、`customer_name`、`module_name` 等主字段；日报全文、转述预览、跨线程回报仍保留 safe/report 口径。
- 静态资源检查：前台静态 JS 中主显示路径未命中 `*_safe`、`safe_*`、`redacted_*` 字段；无需做最小修复。

## 测试 / 证据

- `node --check src/wechat_feedback_app/static/app.js`：exit=0
- `git diff --check -- src/wechat_feedback_app/static/index.html src/wechat_feedback_app/static/styles.css src/wechat_feedback_app/static/app.js`：exit=0
- `git diff --check`：exit=0
- 静态 JS 字段 smoke：`staticSafeTokenCount=0`；群管理主字段、messages/v1 主字段、我方人员主字段、候选主审阅字段均为 true；日报 / 转述 safe 预览链路保留。
- 本机 HTTP count/status smoke：`/api/monitor-groups` HTTP 200，监控群 count=4，主字段存在性通过；`/api/messages/v1` HTTP 200，message count=6，消息正文安全标志为未返回正文；`/api/internal-people` HTTP 200，people count=1，主字段存在性通过；`/api/items` HTTP 200，当前候选 count=0，候选侧以静态渲染路径完成复核。
- 本轮未运行 Python。

## 字段白名单 / 安全边界

- 状态卡和回报只记录 HTTP status、count/status、字段存在性、布尔结果，不摘录真实群名、消息正文、候选正文、草稿正文、真实会话、成员名单、客户名单、wxid、key、salt、真实 DB 路径、IP 或 daemon 日志。
- 未执行新的真实读取。
- 未执行真实 roster 同步。
- 未执行 `wx history/search/export/new-messages`。
- 未打开真实 SQLite / exports 正文。
- 未写正式日报、正式待办池、Obsidian 正式区或外部系统。
- 未修改 `real_read_enabled=false` 口径。

## 剩余风险

- 运行态 `/api/monitor-groups` 当前返回的单条对象中 `group_name` 主字段存在，`display_name` 不一定同时存在；前台已有 `group_name || display_name` 归一化，不影响本地主显示。
- 候选接口当前 count=0，无法用运行态候选数据证明主文本可见；已用静态渲染路径确认候选页不会消费 safe 字段作为主审阅文本。
- 若 Windows 机器仍看到旧脱敏标题，优先排查静态资源缓存、服务未重启或 Windows 发布目录未更新。

## 下一棒建议

- Windows 实机复验时强刷或重启 8765 后再看群管理 / 消息明细 / 我方人员主字段，避免旧静态资源缓存误判。
- 如发现具体页面仍显示脱敏占位，请按页面 selector 和字段名派前台/UI最小修复；不要扩大到真实读取、roster 或正式区写入。

## 回报状态

- 状态卡：已写入
- 监工短回：send_input 工具不可用，本轮按项目协议走 `/Users/gd/Desktop/微信agent专项/开发/监工回报队列.md`
