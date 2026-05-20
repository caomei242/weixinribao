# 微信agent专项 前台/UI 助手状态卡

线程名：微信agent专项 前台/UI 助手
线程 id：019e3a21-b1f1-7fa0-a8ff-4ce933048d87
更新时间：2026-05-20 14:24 CST
结论：完成 `监工派工：2026-05-20｜前台UI｜下一轮日报产品化与配置减负工作台`。本轮是 Windows P0 冻结后的下一轮前台/UI开发状态，不覆盖 Windows P0 实机复验口径；只做日报中心产品化、配置减负和主路径轻量接线。

## 任务标记

监工派工：2026-05-20｜前台UI｜下一轮日报产品化与配置减负工作台

## 改动文件

- `/Users/gd/Desktop/微信agent专项/src/wechat_feedback_app/static/index.html`
- `/Users/gd/Desktop/微信agent专项/src/wechat_feedback_app/static/styles.css`
- `/Users/gd/Desktop/微信agent专项/src/wechat_feedback_app/static/app.js`
- `/Users/gd/Desktop/微信agent专项/开发/状态卡/前台UI助手.md`
- `/Users/gd/Desktop/微信agent专项/开发/监工回报队列.md`

## 日报中心产品化

- 日报中心继续默认首页，标题 / 说明、操作区、状态卡、日报正文保持自然流布局，不回到挤压结构。
- 接入 `/api/daily-center` 的 count/status 摘要，用于区分新发现、未完成跟进、历史未跟进和日报状态。
- 日报右侧新增 `待处理工作台`，只展示 count/status/action 级任务：未完成跟进事项、历史未跟进、配置减负、日报生成反馈。
- 待处理工作台按钮仍走固定页切换，不跳下方、不弹技术面板。

## 群管理下拉化 / 配置减负

- 群管理表单新增 `配置减负` 状态条，展示客户选项、群类型、业务模块、客户阶段和成员角色分配的 count/status。
- 群类型、业务模块、客户阶段、试读范围、验证状态优先消费后端 `field_options`，再叠加本地安全默认值和已有群档案选项。
- 客户名称继续消费后端 `customer_options` / suggestion 三态；已有新增 / 编辑 / 停用 / 归档 / 删除 / 成员同步授权能力未回退。
- 负责人、常用联系人、我方人员仍保持统一成员池 + 角色分配，不退回三处手输名单。

## 我方人员自动补齐

- 我方人员页保留固定表单 / 识别向导。
- 输入微信号或微信显示名时新增 debounce 自动调用 `/api/internal-people/suggestions`；按钮识别入口仍保留。
- 后端建议命中后自动预填人员姓名、微信显示名、别名、角色、负责模块、启用状态和影响范围；保存仍走 `/api/internal-people`，保存后读回。
- 若后端只拿到内部标识且无显示名，仍提示“未识别到名字，请补一个显示名”，不把 ID 当主名称保存。

## 消息先选群

- 消息明细保留 `/api/messages/v1` 主路径。
- 单群 0 条仍显示空态，不回退全部群；不把多群消息混排成用户看不懂的列表。

## 测试 / 证据

- `node --check src/wechat_feedback_app/static/app.js`：exit=0
- `git diff --check -- src/wechat_feedback_app/static/index.html src/wechat_feedback_app/static/styles.css src/wechat_feedback_app/static/app.js`：exit=0
- `git diff --check`：exit=0
- HTTP count/status smoke：`/api/daily-center`、`/api/monitor-groups`、`/api/internal-people`、`/api/messages/v1`、`/api/windows-readiness` 均 HTTP 200，只记录 status/count/字段存在性。
- 运行态 Chrome/CDP DOM smoke：日报待处理工作台 rows=4；`/api/daily-center` 可载入；群管理配置减负状态存在，客户 / 群类型 / 模块 / 阶段下拉均有 option；归档 / 删除 / 成员池存在；我方人员输入后 suggestion 调用 count>=1，表单字段自动预填，别名 chip 可见；messages/v1 和单群不回退空态保留。
- 本轮未运行 Python。

## 字段白名单 / 安全边界

- 状态卡、回报和 smoke 只记录 HTTP status、count/status、error_code、字段存在性、布尔值和接口路径。
- 未执行新的真实读取、未执行真实 roster 同步、未执行 `wx history/search/export/new-messages`。
- 未打开或摘录真实 SQLite / exports 正文。
- 未记录真实消息正文、候选正文、草稿正文、真实会话列表、真实成员名单、客户名单、wxid、key、salt、真实 DB 路径或 daemon 原始日志。
- 未写正式日报、正式待办池、Obsidian 正式区或外部系统。
- `real_read_enabled=false` 口径未改。

## 剩余风险

- 本轮只做前台/UI产品化和配置减负，不做多人使用、Slock 专属 agent、Windows 长期挂机方案或自动外发 / 自动写正式区。
- 运行态 smoke 对我方人员 suggestion 使用前台拦截的 synthetic 返回，只验证前台自动补齐链路，不读取真实人员名单。
- Windows P0 实机复验基准需继续按冻结口径单独验收，不应把本轮新开发混入 P0 通过条件。

## 下一棒建议

- 测试审查可按下一轮口径复验：日报工作台 rows/count/status、群管理后端选项驱动、我方人员自动补齐、messages/v1 单群空态不回退。
- 后端/API若继续扩展配置减负字段，优先补充 `field_options` 与 suggestion 摘要字段，不要要求前台手填散文本。

## 回报状态

- 状态卡：已写入
- 监工短回：send_input 工具不可用，本轮按项目协议走 `/Users/gd/Desktop/微信agent专项/开发/监工回报队列.md`
