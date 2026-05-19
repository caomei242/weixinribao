# 微信agent专项 前台/UI 助手状态卡

线程名：微信agent专项 前台/UI 助手
线程 id：019e3a21-b1f1-7fa0-a8ff-4ce933048d87
更新时间：2026-05-18 18:23 CST
结论：已完成 `监工返工：2026-05-18｜前台UI｜右侧详情区证据链视觉二次返工`。这次不是只改标题文字，而是把右侧“候选详情与人工确认”和“候选来源消息”做成肉眼可分的两个分区，并处理了运行态资源缓存问题。

## 任务标记

监工返工：2026-05-18｜前台UI｜右侧详情区证据链视觉二次返工

## 改动文件

- `/Users/gd/Desktop/微信agent专项/src/wechat_feedback_app/static/index.html`
- `/Users/gd/Desktop/微信agent专项/src/wechat_feedback_app/static/styles.css`
- `/Users/gd/Desktop/微信agent专项/src/wechat_feedback_app/static/app.js`
- `/Users/gd/Desktop/微信agent专项/开发/状态卡/前台UI助手.md`
- `/Users/gd/Desktop/微信agent专项/开发/监工回报队列.md`

## 二次视觉修复说明

- 右侧来源区 `<section>` 增加独立类 `source-chain-block`，改成独立浅底卡片，不再只是标题下面直接接列表。
- `候选来源消息` 分区增加独立浅底容器、圆角、边框和额外内边距，和上方 `候选详情与人工确认` 形成明显区隔。
- `候选来源消息` 标题区下方说明和列表之间补了更清楚的上下间距，列表本身增加 `margin-top`，避免紧贴标题。
- 来源消息列表容器增加 `min-height`、`max-height` 和内部滚动条件，标题不会再被列表内容顶住。
- 空态继续明确显示 `暂无来源消息`。

## 运行态生效确认

- 为避免浏览器继续吃旧静态资源，已把 HTML 中静态资源版本号升级为：
  - `/static/styles.css?v=20260518-inbox-v1-detail2`
  - `/static/app.js?v=20260518-inbox-v1-detail2`
- 运行态抓取 `http://127.0.0.1:8765/` 后确认：页面实际引用了新的 CSS/JS 版本。
- 运行态抓取 `http://127.0.0.1:8765/static/styles.css?v=20260518-inbox-v1-detail2` 后确认：服务实际返回了 `source-chain-block`、来源列表 `margin-top: 8px`、`min-height: 120px` 等新样式。
- 运行态 HTML 确认存在：`候选详情与人工确认`、`候选来源消息`、`source-chain-block`。

## 测试 / 证据

- `node --check src/wechat_feedback_app/static/app.js`：exit=0
- `git diff --check -- src/wechat_feedback_app/static/index.html src/wechat_feedback_app/static/styles.css src/wechat_feedback_app/static/app.js`：exit=0
- 运行态 DOM/CSS smoke：
  - 新版 CSS/JS query version 已生效
  - `source-chain-block` DOM 存在
  - `候选详情与人工确认`、`候选来源消息` 标题存在
  - 来源列表新样式存在：独立容器、`margin-top`、`min-height`
  - 未恢复 `workspaceSourceBtn / realTrialSourceBtn`
  - `app-shell` 和转述摘要三类任务仍在
- 本轮未运行 Python

## P0 / P1 未回退确认

- 左侧固定导航、右侧唯一 `mainPanel` 保持不变
- 候选收件箱仍是一池展示，没有恢复旧数据源主切换
- 转述摘要仍保持三类用户任务页，没有退回旧模板中心

## 禁止项确认

- 未改 `routes.py`、`exporter.py`、后端测试或配置
- 未执行 `wx history/search/export/new-messages`
- 未打开真实 SQLite / exports 正文
- 未输出真实消息正文、候选正文、草稿正文、wxid 具体值、真实会话列表、key、salt、真实 DB 路径或 daemon 原始日志
- 未写正式日报、正式待办、Obsidian 正式区或外部系统

## 剩余风险

- 本轮只能确认运行态 HTML/CSS 已更新和结构/样式规则已生效；最终“肉眼舒服程度”仍建议监工或测试审查助手再看一眼截图位
- 当前工具列表未暴露 `send_input`，只能按项目协议走监工回报队列

## 下一棒建议

- 请监工或测试审查助手刷新 8765 后再做一次截图位肉眼复核
- 如果还需微调，只继续动右侧详情区视觉密度和容器层级，不需要回碰候选池、摘要页或应用壳

## 回报状态

- 状态卡：已写入
- 监工短回：send_input 不可用，已走回报队列
