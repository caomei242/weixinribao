# 微信反馈防漏收件箱 V1

本项目默认运行 fixture 模式本地闭环：本地静态页面、FastAPI API、SQLite 去重入库、规则候选抽取、人工确认、日报中心和 Markdown 导出。2026-05-19 起，V1 前台默认首页是 `日报中心`，旧防漏流程收进固定应用壳里的二级工作页：日报中心 -> 今日防漏 -> 候选收件箱 / 消息明细 -> 群管理 -> 转述摘要 / 配置中心。真实 `wx-cli` 默认只做连接测试；真实消息读取必须显式开启安全开关，并且当前只允许单一试点会话、最近 2 小时 / 最多 50 条。

## 边界

- 默认不接真实微信，不读取真实聊天库。
- 真实模式必须显式配置 `wx_cli.mode: real` 才会启用连接测试。
- 真实消息读取还必须显式配置 `wx_cli.real_read_enabled: true`；默认值为 `false`。
- 当前真实读取试点只允许读取一个已授权白名单会话，且限制为最近 2 小时 / 最多 50 条；README、状态卡、回报队列和测试日志不得写入真实会话名。
- 不执行 `new_messages`，不读取白名单外会话，不扩大真实读取窗口。
- 不调用外部 LLM，不外发客户原文。
- 不自动回复，不写正式待办池，不写 Obsidian 正式区。
- fixture 数据只来自 `fixtures/wx_messages.sample.json`。

## 本地启动

复制配置后按需调整：

```bash
cp config/app.example.yaml config/app.yaml
```

启动后台：

```bash
python3 -m wechat_feedback_app serve --config config/app.yaml
```

默认地址：`http://127.0.0.1:8765`

页面顶部会显示 `模式：fixture`，用于避免误认为正在读取真实微信。

## V1 前台主线

首页第一屏是 `日报中心`。页面采用固定应用壳：顶部状态与全局动作固定，左侧导航固定，右侧唯一主工作区随导航切换。

- 左侧导航：日报中心、今日防漏、候选收件箱、消息明细、群管理、我方人员、配置中心。
- 日报中心首屏：日报状态、沉淀状态、监控群数、新发现问题、历史未跟进，并直接展示日报全文；未生成时显示清楚空态和生成入口。
- 全局动作：日报中心右上提供生成 / 刷新日报、复制全文、导出 Markdown；日报全文底部提供确认沉淀。
- 今日防漏：承载旧防漏主线说明、状态卡、流程步骤和收口清单，不再长期压在所有页面上方。
- 候选收件箱与消息明细：继续区分原始消息数量和候选事项数量；原始消息是本地审阅明细，候选事项是系统从消息中抽出的待确认事项。
- 群管理：按 `监控群` 管理群档案，支持新增、编辑、停用；成员配置使用一处 `成员名单` 池，在同一成员行内勾选 `群负责人 / 常用联系人 / 我方人员`，保存时仍兼容 `owner_names / common_contacts / internal_people` 数组字段。
- 成员名单口径：成员池会明确区分 `本地已出现成员` 与 `微信群全员名单`。全员名单只允许通过显式授权的 roster 同步获取；未授权时接口返回授权所需状态，不执行读取。新增监控群可以在保存前确认“保存后同步微信群全员名单”，该流程只读取成员 roster 元数据，不读取聊天消息、不外发、不写正式区；已有群只保留手动同步入口。
- 客户识别：新增 / 编辑监控群时，客户下拉和群名识别会消费后端返回的 `customer_options`、`customer_options_count`、`source_status` / `source_label` 和 suggestion 字段。前台必须区分本地配置客户、客户系统只读客户源、客户源未接通 / 不可读或客户选项不足。
- 客户选择交互：可靠命中自动选中；有 `suggested_customer_name` / `suggested_customer_id` 但不是可靠命中时，页面显示“疑似客户需确认”并提供 `采用建议客户`；没有 suggestion 时才显示未识别空态。保存 payload 仍使用 `customer_name` / `customer_id`，保存后从后端读回展示。
- 客户源证据边界：文档、状态卡、回报队列和 smoke 只记录 `source_status`、`source_label`、`customer_options_count`、`match_status`、`reason_code`、HTTP status 和布尔结果；不得摘录真实群名、真实客户名单或真实消息内容。

客户识别字段契约、兼容别名、草莓客户管理系统只读来源和 smoke 白名单见：[docs/customer-source.md](docs/customer-source.md)。

草稿日报、转述摘要和群管理只写本地预览 / 本地 Markdown / 本地配置，不写正式待办池、正式日报、Obsidian 正式区或外部系统。

## 前台查看最近真实试读

如果后台服务仍用 `config/app.example.yaml` 启动，主页面候选事项列表显示的是 fixture / 当前服务数据库内容，不代表最近真实试读已经进入主库。页面顶部的“最近真实试读”区域会单独读取本地试读产物，并提示：

- 当前页面是否为 real 配置服务。
- 最近真实试读来源标识，例如 `recent50`。
- `raw_count`、`candidate_count`、`risk_count`。
- 试读 SQLite 和导出目录是否存在。
- 默认真实读取开关是否仍为关闭。

也可以直接查看只读接口：

```bash
curl http://127.0.0.1:8765/api/real-trial/latest
```

该接口只扫描本项目本地 `data/real_trial_recent50_*.sqlite3` 试读库，选择最新一份并返回脱敏统计和项目相对路径，例如：

```json
{
  "status": "ok",
  "source_label": "recent50",
  "raw_count": 50,
  "candidate_count": 3,
  "risk_count": 0,
  "sqlite_path": "data/real_trial_recent50_YYYYMMDD-HHMMSS.sqlite3",
  "export_directory": "exports/real_trial_recent50_YYYYMMDD-HHMMSS",
  "default_real_read_enabled": false
}
```

接口和页面不会返回真实消息正文、候选正文、真实会话名列表、wxid、key、salt、真实数据库路径或 daemon 原始日志。真实试读库不会合并进主库；它只用于本地试点验证。

如果需要启动 real 配置服务用于连接测试或后续授权试点，请显式指定真实配置：

```bash
python3 -m wechat_feedback_app serve --config config/app.yaml
```

即使使用 `config/app.yaml`，默认 `wx_cli.real_read_enabled` 也必须保持 `false`；真实读取只能在获得明确授权后通过受控流程临时开启。

## Windows 长期挂机部署

Windows 24 小时挂机机部署入口：[docs/windows-deploy.md](docs/windows-deploy.md)。

Windows 可实战第一版的验收清单见：[docs/windows-p0-acceptance.md](docs/windows-p0-acceptance.md)。验收必须按用户真实路径走一遍：打开系统、看 Windows readiness、配置监控群、配置我方人员、按群查看消息、看到候选、生成日报；不能只看单点 API 或源码测试。

2026-05-20 代码侧状态：Windows 可实战第一版 P0 已在 Mac 开发机运行态通过测试审查联动复验，覆盖 Windows readiness、监控群、我方人员、消息多群视图、候选入口、日报生成即时反馈和首屏布局。该结论不等于 Windows 实机已通过；下一步是轻量产品走查确认用户路径，再到 Windows 机器按 `docs/windows-p0-acceptance.md` 做实机验收。

配套脚本位于 `scripts/windows/`，覆盖启动服务、停止服务、健康检查、注册任务计划和移除任务计划。脚本默认只启动本地服务与健康检查；不会自动读取真实聊天正文，真实读取试点也必须手动开启 `real_read_enabled`。

## fixture 采集

工作台点击“立即采集”，或调用：

```bash
curl -X POST http://127.0.0.1:8765/api/collect
```

重复采集同一份 fixture 时：

- `raw_messages` 不重复写入。
- `candidate_items` 不重复生成。
- 白名单外会话不落库、不导出。

## 真实 wx-cli 连接测试

真实模式需要人工显式配置，示例：

```yaml
wx_cli:
  mode: "real"
  binary: "wx"
  timeout_seconds: 15
  real_read_enabled: false
  real_allowed_session: "<已授权单一白名单会话>"
  real_lookback_hours: 2
  real_limit: 50
```

也可以把 `binary` 配置为已本地构建的源码副本二进制，例如：

```yaml
wx_cli:
  binary: "/Users/gd/Documents/Codex/2026-05-15/wx-cli-v0.2.0/target/debug/wx"
```

wx-cli 准备状态接口：

```bash
curl http://127.0.0.1:8765/api/wx-cli/readiness
```

准备状态会返回 `configured_binary`、`binary_path`、`is_executable`、`status` 和 `next_action`。如果当前机器没有 `wx`，会返回 `missing_binary`，并提示安装 wx-cli、确认 `command -v wx` 有输出，或在 `config/app.yaml` 的 `wx_cli.binary` 填写绝对路径。

连接测试接口：

```bash
curl http://127.0.0.1:8765/api/wx-cli/test
```

工作台配置弹窗也提供“测试 wx-cli 连接”按钮。

连接测试只运行安全探测命令：

```text
wx sessions --json
```

它用于确认二进制可执行、输出可解析、权限/初始化/微信登录状态是否满足后续接入条件。连接测试不会执行真实消息读取命令，不会自动拉取 `history` 或 `new_messages`。

连接测试 API / 页面只展示脱敏结果：`status`、`error_code`、`session_count`、安全提示、二进制可执行状态和下一步建议。即使 `sessions --json` 返回真实会话列表，项目也只统计数量，不返回会话名、wxid、消息正文、key、salt、真实数据库路径或 daemon 原始日志。

连接测试状态码：

- `ok`：二进制可执行，`sessions --json` 输出可解析。
- `missing_binary`：找不到 `wx` 或配置路径错误。
- `not_initialized`：需要先人工初始化 `wx-cli`。
- `wechat_not_running`：微信未运行、未登录或本地数据不可读。
- `permission_denied`：权限不足。
- `parse_error`：输出格式变化、非 JSON/YAML 或命令返回异常。
- `timeout`：命令超时。

如果在 `real` 模式点击“立即采集”，后台会先检查 `real_read_enabled`、试点会话白名单和连接状态；任一失败都会写入 `collection_runs` 失败记录并在 API / 页面状态中可见，不会清空现有数据、不会混入 fixture、不会静默成功。

只有同时满足以下条件，才会执行真实试点读取：

- `wx_cli.mode: real`
- `wx_cli.real_read_enabled: true`
- `wx_cli.real_allowed_session` 指向已授权的单一白名单会话，真实会话名不得写入 README、状态卡、回报队列或测试日志。
- `sessions` 中启用白名单会话数量必须等于 1，且必须等于该已授权单一白名单会话。

执行的读取命令形态被限制为：

```text
wx history "<已授权单一白名单会话>" --since "YYYY-MM-DD HH:MM" -n 50 --json
```

失败时错误会记录到 `collection_runs`，但错误信息不会携带真实消息正文。真实客户原文不得写入 README、状态卡、监工回报、测试日志或版本控制。

## 导出

页面点击“导出日报”或“导出待办”，文件写入：

```text
exports/YYYY-MM-DD/
```

文件名：

- `YYYY-MM-DD 微信反馈日报.md`
- `YYYY-MM-DD 待跟进事项.md`

## 测试

本项目 Python 命令必须静默写日志。推荐包装：

```bash
mkdir -p .codex_py_logs
ts=$(date +"%Y%m%d-%H%M%S")
log=".codex_py_logs/py-run-$ts.log"
PYTHONPATH=src python3 -m unittest discover -s tests >"$log" 2>&1
exit_code=$?
printf 'python exit=%s log=%s\n' "$exit_code" "$log"
```

当前单元测试覆盖：

- fixture 重复采集去重。
- 规则抽取分类和风险标记。
- 反馈日报与待跟进事项 Markdown 模板。
- fake `wx-cli` 成功、缺失、解析失败、超时、权限错误。
- `real` 模式失败时不污染已有 fixture 数据。
- 真实读取试点安全开关、单会话白名单、2 小时 / 50 条参数、fake `wx history` 映射、重复去重和失败不污染。
- wx-cli 缺失时的准备状态、修复建议，以及多启用白名单会话时阻断 `history`。

## 配置

配置样例：`config/app.example.yaml`

核心配置项：

- `wx_cli.mode`: 默认 `fixture`；显式改为 `real` 时启用真实连接测试。
- `wx_cli.real_read_enabled`: 默认 `false`；只有显式改为 `true` 才允许试点读取。
- `wx_cli.real_allowed_session`: 已授权单一白名单会话；真实会话名不得写入项目文档、状态卡、回报队列或测试日志。
- `wx_cli.real_lookback_hours` / `wx_cli.real_limit`: 读取窗口会被限制在最多 2 小时 / 50 条。
- `database.path`: SQLite 路径。
- `export.directory`: Markdown 导出目录。
- `sessions`: 白名单会话、客户、渠道、模块映射。
- `internal_people`: 我方人员与别名。
- `risk.keywords`: 风险关键词。
