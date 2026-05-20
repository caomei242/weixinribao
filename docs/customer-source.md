# 客户识别与只读客户源

更新时间：2026-05-20

本文说明群管理里“客户名称”字段如何使用本地配置客户与客户系统只读客户源。本文只记录字段契约、状态和交互，不记录真实群名、真实客户名单或真实消息内容。

## 目标

新增或编辑监控群时，用户输入群名后，系统应尽量识别客户归属，并让用户能确认后保存。识别结果只用于本地配置与页面选择，不触发真实微信读取，不外发，不写正式日报、正式待办池、Obsidian 正式区或外部系统。

## 数据来源

客户选项可以来自多个只读来源：

- 本地配置客户：项目 `sessions` / 已保存监控群中已有的客户字段。
- 客户系统只读客户源：后端从 `/Users/gd/Desktop/主业--草莓客户管理系统` 复用该项目现有 Markdown store 读取客户选项摘要，不在本项目新建平行客户库。
- 未接通 / 不可读状态：后端无法读取客户系统源时，仍应返回 `source_status` / `source_error_code` / `customer_options_count` 等摘要字段，前台据此显示人话提示。

前台不得伪造客户名单。没有后端选项时，只显示空态和下一步。

## API 字段契约

客户选项接口与监控群接口统一提供：

```json
{
  "status": "ok",
  "customer_options_count": 0,
  "customer_options": [],
  "source_status": "ok | partial",
  "source_error_code": "",
  "sources": []
}
```

主要入口：

```text
GET /api/customer-options
GET /api/config-center
GET /api/monitor-groups
```

`source_status=ok` 表示本地配置客户与草莓客户系统只读源均已接通；`source_status=partial` 表示至少一个来源不可读或未接通，前台必须把它当成“客户系统源未接通 / 不可读”的提示依据，不能把剩余本地选项当作完整客户库。

客户识别 suggestion 接口：

```text
GET /api/monitor-groups/customer-suggestion?group_name=<URL encoded group name>
```

兼容路径可保留：

```text
GET /api/customer-suggestions?group_name=...
GET /api/customers/suggestions?group_name=...
GET /api/monitor-groups/customer-suggestions?group_name=...
```

suggestion 响应应尽量提供：

```json
{
  "status": "ok",
  "customer_options_count": 0,
  "source_status": "ok | partial",
  "source_error_code": "",
  "suggested_customer_name": "",
  "suggested_customer_id": "",
  "match_status": "matched | needs_manual_selection",
  "reason_code": "exact_match | normalized_match | single_option_with_suggestion | no_reliable_match | no_customer_options"
}
```

## 前台交互规则

前台必须保留三态：

1. 可靠命中：`match_status=matched` 且有 `suggested_customer_name` / `suggested_customer_id`，自动选中客户，并提示用户确认后保存。
2. 疑似客户需确认：有 `suggested_customer_name` / `suggested_customer_id`，但不是可靠命中，显示“已找到疑似客户，需要确认”，并提供 `采用建议客户`。
3. 无 suggestion / 客户源不可用：显示“客户系统源未接通 / 不可读 / 客户选项不足”等人话提示；不要只显示“未识别客户”。

保存监控群时，payload 仍使用：

```json
{
  "customer_name": "...",
  "customer_id": "..."
}
```

保存成功后必须从后端重新读取群档案并展示读回状态。

## 证据与日志白名单

状态卡、回报队列、测试日志和 smoke 输出只允许记录：

- HTTP status
- `status`
- `source_status`
- `source_error_code`
- `customer_options_count`
- `match_status`
- `reason_code`
- 布尔结果，例如 `wouldAutoSelect=true`

禁止记录：

- 真实群名
- 真实客户名单
- 真实消息正文
- 候选正文或草稿正文
- 真实会话列表
- 真实成员名单
- `wxid`
- `key` / `salt`
- 真实 DB 路径
- daemon 原始日志

## Smoke 建议

前台 smoke 可记录以下布尔值：

```text
reliableWouldAutoSelect=true
suggestedNeedsConfirmVisible=true
adoptPayloadHasCustomerFields=true
noSuggestionShowsSourceWarning=true
sourceStatusConsumed=true
sourceStatusDom=true
```

运行态 smoke 只记录接口 HTTP status、count/status 字段存在性和布尔值，不摘录真实业务内容。
