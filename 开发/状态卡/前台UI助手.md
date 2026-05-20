# 微信agent专项 前台/UI 助手状态卡

线程名：微信agent专项 前台/UI 助手
线程 id：019e3a21-b1f1-7fa0-a8ff-4ce933048d87
更新时间：2026-05-20 12:49 CST
结论：完成 `监工返工：2026-05-20｜前台UI｜群管理归档删除入口与日报生成点击反馈`。本轮只做前台/UI最小实现：群管理补清楚的归档 / 删除入口和二次确认，日报生成补可验收点击反馈证据；未改后端、未执行真实读取或真实同步。

## 任务标记

监工返工：2026-05-20｜前台UI｜群管理归档删除入口与日报生成点击反馈

## 改动文件

- `/Users/gd/Desktop/微信agent专项/src/wechat_feedback_app/static/index.html`
- `/Users/gd/Desktop/微信agent专项/src/wechat_feedback_app/static/styles.css`
- `/Users/gd/Desktop/微信agent专项/src/wechat_feedback_app/static/app.js`
- `/Users/gd/Desktop/微信agent专项/开发/状态卡/前台UI助手.md`
- `/Users/gd/Desktop/微信agent专项/开发/监工回报队列.md`

## 归档 / 删除入口与二次确认

- 群管理操作区新增 `归档`、`删除` 两个入口；归档成功后卡片 / 编辑状态显示 `已归档`。
- `归档` 二次确认说明：只移出日常监控 / 日报统计，不删除真实微信群，不外发，不写正式区；失败保留当前列表。
- `删除` 二次确认说明：只删除本项目本地监控群配置，不影响真实微信群、客户系统、正式日报、待办、Obsidian 或外部系统；失败保留当前列表。
- 前台接线：归档优先调用 `POST /api/monitor-groups/{group_id}/archive`，若该最小契约未到位则降级到已有 disable 能力并标记归档；删除优先调用 `POST /api/monitor-groups/{group_id}/delete` 且带 `confirm_delete=true`，若未到位再尝试旧 DELETE / config-center 本地配置移除兜底。
- 成功 / 失败 / blocked 均给人话反馈；失败或被拦截时恢复旧列表，不给用户误删错觉。

## 日报生成 1 秒反馈点击证据

- 运行态拦截式 smoke，未调用真实日报生成接口正文，未摘录日报内容。
- 点击 `生成/刷新日报` 后 250ms 内：`postSeen=true`、`disabled=true`、`buttonGenerating=true`、`metaGenerating=true`、`oldReportRetained=true`、`activePage=daily`。
- 拦截响应后：`status=success`、`successFeedback=true`、`buttonsEnabled=true`。
- 生成中提示文案保留“旧日报会保留到新版完成”；失败路径保留“生成失败 / 旧日报已保留”的人话提示。

## Windows P0 回归

- 静态 / 运行态 smoke 均确认 readiness 仍保留 `/api/windows-readiness` 接线。
- 消息明细仍保留 `/api/messages/v1` 接线与单群 0 条“不回退显示全部群”空态。
- 日报中心默认首页、首屏布局、群管理新增 / 编辑 / 停用、我方人员页既有入口均未做回退改动。
- 静态资源版本更新为 `20260520-archive-delete-feedback`，降低刷新后旧前台资源缓存风险。

## 测试 / 证据

- `node --check src/wechat_feedback_app/static/app.js`：exit=0
- `git diff --check -- src/wechat_feedback_app/static/index.html src/wechat_feedback_app/static/styles.css src/wechat_feedback_app/static/app.js`：exit=0
- `git diff --check`：exit=0
- 静态 grep smoke：归档 / 删除按钮、确认文案、`/api/windows-readiness`、`/api/messages/v1`、单群不回退空态、生成中文案均存在。
- 运行态 Chrome/CDP smoke：root HTTP 200；归档按钮存在且可用；删除按钮存在且可用；归档确认安全文案存在；归档请求拦截命中；归档状态显示成功；删除确认安全文案存在；删除请求拦截命中；删除后本地列表移除；日报生成 250ms 内进入生成中。
- 本轮未运行 Python。

## 字段白名单 / 安全边界

- 状态卡、回报和 smoke 只记录 HTTP status、count/status、字段存在性、布尔值、按钮存在性、确认文案存在性和接口路径。
- 未执行新的真实读取、未执行真实 roster 同步、未执行 `wx history/search/export/new-messages`。
- 未打开或摘录真实 SQLite / exports 正文。
- 未记录真实消息正文、候选正文、草稿正文、真实会话列表、真实成员名单、客户名单、wxid、key、salt、真实 DB 路径或 daemon 原始日志。
- 未写正式日报、正式待办池、Obsidian 正式区或外部系统。

## 剩余风险

- 本轮不改后端；已按后端/API助手回报的新契约接入 `POST /archive` 与 `POST /delete(confirm_delete=true)`，同时保留旧服务兜底。
- 运行态 destructive smoke 使用临时 synthetic group + fetch 拦截，不触发真实归档 / 删除 / 日报生成；Windows 实机仍需后续按实机验收流程复验。

## 下一棒建议

- 测试审查复验群管理归档 / 删除按钮、二次确认、失败保留旧列表、日报生成 1 秒反馈。
- 优先复验前台是否走原生 `POST /archive`、`POST /delete(confirm_delete=true)`；旧服务场景再复验 config-center 删除本地配置的兜底链路。
- 通过后再进入 Windows 实机复验，继续只记录 count/status/source/error_code 和字段存在性。

## 回报状态

- 状态卡：已写入
- 监工短回：send_input 工具不可用，本轮按项目协议走 `/Users/gd/Desktop/微信agent专项/开发/监工回报队列.md`
