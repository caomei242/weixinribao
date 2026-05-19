const state = {
  items: [],
  realTrialItems: [],
  selected: null,
  realTrialMessages: [],
  realTrialSenders: [],
  selectedSender: null,
  typeFilter: "",
  itemSource: "workspace",
  trialPreset: "",
  configCenter: null,
  dailyControl: null,
  dailyDraftPreview: null,
  inboxV1: null,
  monitorGroups: [],
  selectedMonitorGroupId: "",
  activePage: "daily",
  transferTask: "internal_sync",
};

const WORKSPACE_STATE_VERSION = "20260519-daily-center-p0";
const MONITOR_GROUP_META_STORAGE = "wechat_daily_monitor_group_meta_v1";
const DAILY_SETTLEMENT_STORAGE = "wechat_daily_settlement_status_v1";

function storedWorkspaceState() {
  try {
    return JSON.parse(localStorage.getItem("inbox_v1_state") || "{}");
  } catch (_error) {
    return {};
  }
}

function storedJson(key, fallback = {}) {
  try {
    return JSON.parse(localStorage.getItem(key) || JSON.stringify(fallback));
  } catch (_error) {
    return fallback;
  }
}

const savedWorkspaceState = storedWorkspaceState();
const today = new Date().toISOString().slice(0, 10);
document.querySelector("#filterDate").value = savedWorkspaceState.filterDate || today;
document.querySelector("#exportTemplateDate").value = today;
if (savedWorkspaceState.itemSource) state.itemSource = savedWorkspaceState.itemSource;

const labels = {
  pending: "待确认",
  confirmed: "已确认",
  rejected: "已驳回",
  requirement: "客户需求",
  bug: "问题 / Bug",
  consultation: "咨询",
  conclusion: "沟通结论",
  followup: "待我方跟进",
  none: "无风险",
  low: "低风险",
  high: "高风险",
};

const downstreamLabels = {
  product: "产品处理",
  tech: "技术处理",
  ops: "运营处理",
  none: "暂不同步",
};

const sourceLabels = {
  workspace: "今日候选",
  realTrial: "来自最近试读",
};

const transferTaskPresets = {
  internal_sync: {
    title: "给内部产品或技术同步",
    lead: "整理一段发给内部同事的同步摘要，保留问题、影响范围和待确认点。",
    templateIds: ["product_tech_summary"],
    confirmedOnly: false,
    includePending: true,
  },
  client_reply: {
    title: "给客户回复",
    lead: "先给出一段更克制的回复草稿，只带可对外复述的信息。",
    templateIds: ["product_tech_summary"],
    confirmedOnly: true,
    includePending: false,
  },
  self_recap: {
    title: "给自己留今日复盘",
    lead: "回看今天收到了什么、哪些还没处理、下一步该追谁。",
    templateIds: ["daily_review", "followup_checklist"],
    confirmedOnly: false,
    includePending: true,
  },
};

const monitorGroupSeed = {
  external_id: "local-qiajie-gaoding-ecommerce",
  display_name: "洽姐x稿定电商",
  customer_name: "稿定电商",
  channel_name: "",
  module_name: "电商设计",
  owner_name: "",
  customer_stage: "待验证",
  group_type: "测试群",
  common_contacts: [],
  reply_notes: "待验证监控群；试读成功前不纳入日报统计。",
  is_whitelisted: true,
  enabled: true,
  daily_monitor: false,
  include_in_daily: false,
  verification_status: "待验证",
  trial_range: "recent50",
  internal_people: [],
};

const monitorGroupOptions = {
  groupTypes: ["测试群", "客户群", "渠道群", "内部群"],
  modules: ["订单", "售后", "登录", "电商设计", "渠道", "待确认模块"],
  stages: ["待验证", "试用期", "交付期", "合作期", "稳定服务期", "暂停跟进"],
  trialRanges: [
    ["recent50", "最近50条"],
    ["2h", "最近2小时"],
    ["today", "今天"],
  ],
  verifyStatuses: ["待验证", "已验证", "暂停验证"],
};

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json();
}

async function refreshStatus() {
  const data = await api("/api/status");
  const run = data.latest_run || {};
  const trialState = data.real_trial || {};
  const readText = trialState.enabled ? "只读试读临时开启" : "只读试读保持关闭";
  const groupText = `监控群：${trialState.enabled_whitelist_count ?? 0} 个`;
  const latestText = `上次整理：${run.finished_at || "还未运行"}`;
  document.querySelector("#statusLine").textContent =
    `日报中心就绪｜${readText}｜${groupText}｜${latestText}｜不会自动外发或写正式区`;
}

async function refreshRealTrialSummary() {
  const line = document.querySelector("#realTrialLine");
  try {
    const realTrial = await api("/api/real-trial/latest");
    line.textContent = renderRealTrialSummary(realTrial);
  } catch (_error) {
    line.textContent = "真实试读摘要暂不可用｜status：api_error｜请刷新页面或检查本地服务";
  }
}

async function refreshInboxV1() {
  const controlDate = document.querySelector("#filterDate")?.value || today;
  const data = await api(`/api/inbox/v1?control_date=${encodeURIComponent(controlDate)}`);
  state.inboxV1 = data;
  renderInboxV1(data);
}

function renderInboxV1(data) {
  const top = data.top_status || {};
  const safety = data.safety || {};
  const human = data.human_status || {};
  document.querySelector("#humanStatusCards").innerHTML = (human.cards || [
    { label: "服务健康", value: "载入中", hint: "" },
    { label: "真实读取", value: safety.default_real_read_enabled ? "临时开启" : "默认关闭", hint: "" },
    { label: "最近一次可用结果", value: `${top.raw_count || 0} 条原始消息 / ${top.candidate_count || 0} 条候选`, hint: "" },
    { label: "候选事项", value: `待确认 ${top.pending_count || 0} 条`, hint: "" },
    { label: "草稿日报", value: top.draft_status || "未生成", hint: "" },
    { label: "今日收口", value: top.collection_status || "未运行", hint: "" },
  ]).map((card) => `
    <div class="status-cell">
      <span>${escapeHtml(card.label)}</span>
      <b>${escapeHtml(card.value)}</b>
      <small>${escapeHtml(card.hint || "")}</small>
    </div>
  `).join("");
  renderDiagnosticDetails(human.diagnostic_details || {});
  renderTrialDraftPrompt(data.trial_draft_prompt || {});
  document.querySelector("#inboxV1Explain").textContent =
    data.message_vs_candidate_explain || "50 条是原始消息，3 条是抽出来的候选事项；候选仍需人工确认。";
  document.querySelector("#inboxV1Workflow").innerHTML = (data.workflow_steps || [])
    .map((step) => `
      <button class="workflow-step" data-workflow-key="${escapeAttr(step.key)}">
        <span>${escapeHtml(step.label)}</span>
        <small>${escapeHtml(step.status)}</small>
      </button>
    `).join("");
  renderGroupProfile(data.group_profile || {}, "#inboxV1GroupProfile");
  renderGroupProfile(data.group_profile || {}, "#runtimeGroupProfileBody");
  renderGroupProfile(data.group_profile || {}, "#groupTagsPageProfile");
  document.querySelector("#runtimeGroupProfileBody").insertAdjacentHTML(
    "beforeend",
    `<p class="safe-note">默认真实读取：${safety.default_real_read_enabled ? "开启" : "关闭"}｜正式写入：禁用</p>`
  );
}

function renderDiagnosticDetails(details) {
  const body = document.querySelector("#diagnosticDetailsBody");
  const html = Object.entries(details)
    .map(([key, value]) => `<div><b>${escapeHtml(key)}</b>：${escapeHtml(value)}</div>`)
    .join("") || "暂无诊断信息";
  body.innerHTML = html;
  const dailyDiagnostics = document.querySelector("#dailyCenterDiagnostics");
  if (dailyDiagnostics) dailyDiagnostics.innerHTML = html;
}

function renderTrialDraftPrompt(prompt) {
  const node = document.querySelector("#trialDraftPrompt");
  if (!node) return;
  if (!prompt.visible) {
    node.textContent = "草稿会优先跟着当前最该处理的候选走；如果今天处理区为空，会自动优先最近试读候选。";
    return;
  }
  node.innerHTML = `
    <strong>${escapeHtml(prompt.message)}</strong>
    <button id="draftTrialBtn" type="button">${escapeHtml(prompt.primary_action_label || "生成试读草稿")}</button>
  `;
  document.querySelector("#draftTrialBtn")?.addEventListener("click", async () => {
    document.querySelector("#draftDataSourceChoice").value = "real_trial";
    await regenerateDraftReport();
  });
}

function customerLabel(value) {
  return value || "待确认客户";
}

function downstreamLabel(value) {
  return downstreamLabels[value] || "暂不同步";
}

function riskLabel(value) {
  return labels[value] || value || "无风险";
}

function sourceLabel(value) {
  return sourceLabels[value] || "当前候选";
}

function humanStatusText(value) {
  return {
    success: "正常",
    failed: "失败",
    blocked: "已拦截",
    ok: "可用",
    not_found: "未找到",
    api_error: "暂不可用",
    draft_ready: "草稿已生成",
    disabled: "关闭",
    enabled: "开启",
  }[value] || value || "未知";
}

function humanDataSourceLabel(value) {
  if (!value) return "当前候选";
  if (String(value).includes("workspace")) return "今日候选";
  if (String(value).includes("real_trial")) return "最近试读候选";
  return value;
}

function preferredCandidateSource() {
  return state.items.length ? "workspace" : state.realTrialItems.length ? "realTrial" : "workspace";
}

function preferredDataSourceValue() {
  return preferredCandidateSource() === "realTrial" ? "real_trial" : "workspace";
}

function syncCandidatePresentation() {
  state.itemSource = preferredCandidateSource();
  const poolLine = document.querySelector("#candidatePoolLine");
  const importButton = document.querySelector("#importRealTrialBtn");
  const exportButton = document.querySelector("#realTrialExportTemplateBtn");
  if (importButton) {
    importButton.hidden = !(state.itemSource === "realTrial" && state.realTrialItems.length);
  }
  if (exportButton) {
    exportButton.textContent = state.itemSource === "realTrial"
      ? "用这批候选生成转述摘要"
      : "用当前候选生成转述摘要";
  }
  if (!poolLine) return;
  if (state.itemSource === "realTrial" && state.realTrialItems.length) {
    poolLine.textContent = `正在展示最近试读的 ${state.realTrialItems.length} 条候选。先看清这批候选，再决定是否加入今天处理。`;
    return;
  }
  if (state.itemSource === "workspace" && state.items.length) {
    poolLine.textContent = `正在展示今天处理区的 ${state.items.length} 条候选。确认后会继续进入草稿日报和转述摘要。`;
    return;
  }
  poolLine.textContent = "当前还没有可处理候选。下一步：先去试读消息确认今天有没有新反馈。";
}

function renderGroupProfile(profile, selector) {
  const node = document.querySelector(selector);
  if (!node) return;
  const rows = `
    <div><dt>客户名称</dt><dd>${escapeHtml(profile.customer_name || "未配置")}</dd></div>
    <div><dt>群负责人</dt><dd>${escapeHtml(profile.group_owner || "未配置")}</dd></div>
    <div><dt>业务模块</dt><dd>${escapeHtml(profile.module_name || "未配置")}</dd></div>
    <div><dt>客户阶段</dt><dd>${escapeHtml(profile.customer_stage || "未配置")}</dd></div>
    <div><dt>群类型</dt><dd>${escapeHtml(profile.group_type || "未配置")}</dd></div>
    <div><dt>常用联系人</dt><dd>${escapeHtml(profile.common_contacts_count ?? 0)} 人</dd></div>
    <div><dt>回复注意事项</dt><dd>${profile.reply_notes_configured ? "已配置" : "未配置"}</dd></div>
  `;
  if (selector === "#runtimeGroupProfileBody") {
    node.innerHTML = rows;
    return;
  }
  node.innerHTML = `<h3>监控群档案</h3><dl class="profile-list">${rows}</dl>`;
}

async function refreshDailyControl() {
  const controlDate = document.querySelector("#filterDate").value || today;
  const data = await api(`/api/daily-control?control_date=${encodeURIComponent(controlDate)}`);
  state.dailyControl = data;
  renderDailyControl(data);
}

function renderDailyControl(data) {
  const top = data.top_status || {};
  document.querySelector("#dailyTopLine").textContent =
    `日期：${data.control_date}｜采集状态：${humanStatusText(top.collection_status || "未运行")}｜候选：${top.candidate_count || 0}｜待确认：${top.pending_count || 0}｜待整理：${top.settlement_ready_count || 0}｜规则反馈：${top.rule_feedback_count || 0}${top.error_code ? `｜提醒：${top.error_code}` : ""}`;
  document.querySelector("#dailyCards").innerHTML = (data.cards || [])
    .map((card) => `
      <article class="daily-card">
        <span>${escapeHtml(card.title)}</span>
        <b>${escapeHtml(card.count ?? 0)}</b>
        <small>状态：${escapeHtml(card.status || "")}${card.error_code ? `｜错误：${escapeHtml(card.error_code)}` : ""}</small>
      </article>
    `)
    .join("");
  renderDailyPendingRows(data.pending_items || []);
  renderSettlementChecklist(data.settlement_check || {});
  renderDailyTimeline(data.timeline || []);
  renderQualityFeedback(data.quality_feedback || {});
  renderDailyRealTrial(data.real_trial || {}, data.real_trial_items || {}, data.real_trial_notice || {});
  renderDailyReportCenter();
  refreshDraftReportPreview();
  document.querySelector("#writeFormalBtn").disabled = true;
}

function reportControlDate() {
  return document.querySelector("#filterDate")?.value || today;
}

function settlementStore() {
  return storedJson(DAILY_SETTLEMENT_STORAGE, {});
}

function writeSettlementStatus(date, status) {
  const store = settlementStore();
  store[date] = {
    status,
    updated_at: new Date().toISOString(),
  };
  localStorage.setItem(DAILY_SETTLEMENT_STORAGE, JSON.stringify(store));
}

function currentSettlementStatus(date) {
  return settlementStore()[date]?.status || "未沉淀";
}

function enabledDailyMonitorGroups() {
  return (state.monitorGroups || []).filter((group) =>
    group.enabled !== false
    && group.daily_monitor !== false
    && group.include_in_daily !== false
    && group.verification_status !== "待验证"
  );
}

function dailyCenterCounts() {
  const top = state.dailyControl?.top_status || {};
  return {
    monitorGroups: enabledDailyMonitorGroups().length,
    newIssues: Number(top.candidate_count || 0),
    pendingFollowups: Number(top.pending_count || 0),
  };
}

function renderDailyReportCenter() {
  const page = document.querySelector("#dailyReportCenterPage");
  if (!page) return;
  const date = reportControlDate();
  const preview = state.dailyDraftPreview || {};
  const top = state.dailyControl?.top_status || {};
  const counts = dailyCenterCounts();
  const hasGenerated = Boolean(preview.generated_at || preview.local_preview_saved);
  const hasReportText = Boolean((preview.preview_markdown || "").trim());
  const settlementStatus = currentSettlementStatus(date);
  document.querySelector("#dailyCenterDate").textContent = date;
  document.querySelector("#dailyCenterLine").textContent = hasGenerated
    ? `日报已生成，当前还有 ${counts.pendingFollowups} 条未收口事项。`
    : "日报还未生成。下一步：先生成/刷新日报，再确认是否沉淀。";
  document.querySelector("#dailyCenterCards").innerHTML = [
    ["日报状态", hasGenerated ? "已生成" : "未生成", hasGenerated ? "可直接查看全文" : "点击右上生成"],
    ["沉淀状态", settlementStatus, settlementStatus === "已确认沉淀" ? "已人工确认" : "全文底部可确认"],
    ["监控群数", counts.monitorGroups, "启用监控并纳入日报"],
    ["新发现问题", counts.newIssues, "今天候选事项"],
    ["历史未跟进", counts.pendingFollowups, "仍需人工收口"],
  ].map(([label, value, hint]) => `
    <article class="daily-center-card">
      <span>${escapeHtml(label)}</span>
      <b>${escapeHtml(value)}</b>
      <small>${escapeHtml(hint)}</small>
    </article>
  `).join("");
  const text = preview.preview_markdown || "";
  const empty = document.querySelector("#dailyReportEmpty");
  const report = document.querySelector("#dailyReportFullText");
  empty.classList.toggle("hidden", hasGenerated && hasReportText);
  report.classList.toggle("hidden", !(hasGenerated && hasReportText));
  report.textContent = hasGenerated && hasReportText ? text : "";
  document.querySelector("#dailyReportMetaLine").textContent = hasGenerated
    ? `生成时间：${preview.generated_at || "刚刚生成"}｜候选：${preview.candidate_count || 0}｜风险：${preview.risk_count || 0}｜来源：${humanDataSourceLabel(preview.data_source_label)}`
    : `状态：未生成｜候选：${top.candidate_count || 0}｜下一步：生成/刷新日报`;
  document.querySelector("#confirmDailySettlementBtn").disabled = !(hasGenerated && hasReportText);
  document.querySelector("#markDailyReviewBtn").disabled = !(hasGenerated && hasReportText);
  renderDailySettlementRows();
}

function nearbyDates(date) {
  const base = new Date(`${date}T00:00:00`);
  return [0, -1, -2].map((offset) => {
    const next = new Date(base);
    next.setDate(base.getDate() + offset);
    return next.toISOString().slice(0, 10);
  });
}

function renderDailySettlementRows() {
  const container = document.querySelector("#dailySettlementRows");
  if (!container) return;
  const date = reportControlDate();
  const counts = dailyCenterCounts();
  const preview = state.dailyDraftPreview || {};
  const hasGenerated = Boolean(preview.generated_at || preview.local_preview_saved);
  container.innerHTML = nearbyDates(date).map((rowDate, index) => {
    const isCurrent = index === 0;
    const reportStatus = isCurrent ? (hasGenerated ? "已生成" : "未生成") : "待查看";
    const groupCount = isCurrent ? counts.monitorGroups : "-";
    const newIssues = isCurrent ? counts.newIssues : "-";
    const pending = isCurrent ? counts.pendingFollowups : "-";
    return `
      <article class="settlement-row">
        <div>
          <strong>${escapeHtml(rowDate)}</strong>
          <small>监控群 ${escapeHtml(groupCount)}｜新问题 ${escapeHtml(newIssues)}｜历史未跟进 ${escapeHtml(pending)}</small>
          <small>日报：${escapeHtml(reportStatus)}｜沉淀：${escapeHtml(currentSettlementStatus(rowDate))}</small>
        </div>
        <button data-settlement-date="${escapeAttr(rowDate)}">${isCurrent ? "刷新" : "查看"}</button>
      </article>
    `;
  }).join("");
}

function currentDailyReportText() {
  const preview = state.dailyDraftPreview || {};
  if (!(preview.generated_at || preview.local_preview_saved)) return "";
  return preview.preview_markdown || "";
}

async function copyDailyReport() {
  const text = currentDailyReportText();
  const result = document.querySelector("#dailySettlementResult");
  if (!text.trim()) {
    result.textContent = "还没有可复制的日报。请先生成/刷新日报。";
    return;
  }
  await navigator.clipboard.writeText(text);
  result.textContent = "已复制日报全文。";
}

function exportDailyMarkdown() {
  const text = currentDailyReportText();
  const result = document.querySelector("#dailySettlementResult");
  if (!text.trim()) {
    result.textContent = "还没有可导出的日报。请先生成/刷新日报。";
    return;
  }
  const blob = new Blob([text], { type: "text/markdown;charset=utf-8" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = `${reportControlDate()}-微信反馈日报.md`;
  link.click();
  URL.revokeObjectURL(link.href);
  result.textContent = "已生成 Markdown 下载文件；不会写正式区。";
}

function renderDailyPendingRows(items) {
  const tbody = document.querySelector("#dailyPendingRows");
  if (!items.length) {
    tbody.innerHTML = '<tr><td colspan="7" class="empty">今天还没有待确认候选。下一步：先去候选收件箱看看最新一批候选。</td></tr>';
    return;
  }
  tbody.innerHTML = items.map((item) => `
    <tr data-daily-item-id="${item.id}">
      <td>${escapeHtml(item.item_code)}</td>
      <td>${escapeHtml(customerLabel(item.customer_name || item.channel_name))}</td>
      <td>${escapeHtml(labels[item.item_type] || item.item_type)}</td>
      <td>${escapeHtml(item.summary)}</td>
      <td>${escapeHtml(riskLabel(item.risk_level))}${(item.risk_tags || []).length ? `｜${escapeHtml(item.risk_tags.join("、"))}` : ""}</td>
      <td>${escapeHtml(item.owner_name || "未填写")}</td>
      <td>
        <div class="row-actions">
          <button data-action="confirm">确认</button>
          <button data-action="reject">驳回</button>
          <button data-action="change_type">改类型</button>
          <button data-action="mark_risk">标风险</button>
          <button data-action="assign_owner">补负责人</button>
        </div>
      </td>
    </tr>
  `).join("");
}

function renderSettlementChecklist(check) {
  const checks = [
    ["已确认事项", (check.confirmed_count || 0) > 0],
    ["风险项已复核", Boolean(check.risk_reviewed)],
    ["负责人已填写", Boolean(check.owner_filled)],
    ["下游同步对象已确认", Boolean(check.downstream_confirmed)],
    ["生成待沉淀草稿", Boolean(check.draft_generated)],
  ];
  document.querySelector("#settlementChecklist").innerHTML = checks.map(([label, ok]) => `
    <div class="check-item">${ok ? "✓" : "□"} ${escapeHtml(label)}</div>
  `).join("") + `<div class="check-item">正式日报 / 正式待办：保持关闭｜${escapeHtml(check.formal_write_reason || "未配置正式路径")}</div>`;
}

function renderDailyTimeline(events) {
  document.querySelector("#dailyTimeline").innerHTML = events.map((event) => `
    <div class="timeline-item">
      <strong>${escapeHtml(event.label)}</strong>
      <span>状态：${escapeHtml(labels[event.status] || humanStatusText(event.status))}｜数量：${escapeHtml(event.count ?? 0)}${event.error_code ? `｜提醒：${escapeHtml(event.error_code)}` : ""}</span>
    </div>
  `).join("");
}

function renderQualityFeedback(feedback) {
  const counts = feedback.counts || {};
  const labelsByType = {
    false_positive: "误提",
    missed: "漏提补录",
    type_correction: "类型修正",
    risk_correction: "风险修正",
  };
  document.querySelector("#qualityFeedbackPanel").innerHTML = Object.entries(labelsByType)
    .map(([key, label]) => `<div class="quality-pill">${label}：${counts[key] || 0}</div>`)
    .join("");
}

function renderDailyRealTrial(realTrial, realTrialItems, notice) {
  const line = document.querySelector("#dailyRealTrialLine");
  const noticeBox = document.querySelector("#dailyRealTrialNotice");
  const list = document.querySelector("#dailyRealTrialItems");
  const realTrialGapMessage = "当前主工作台无待确认事项；最近真实试读有候选，尚未合并进主工作台。";
  if (!realTrial || realTrial.status === "not_found") {
    line.textContent = "未找到最近真实试读产物。";
    noticeBox.textContent = "";
    list.innerHTML = "";
    return;
  }
  if (realTrial.status !== "ok") {
    line.textContent = `最近试读暂不可用｜状态：${humanStatusText(realTrial.status)}`;
    noticeBox.textContent = "";
    list.innerHTML = "";
    return;
  }
  const defaultSwitch = realTrial.default_real_read_enabled ? "已开启" : "关闭";
  line.textContent =
    `最近试读时间：${realTrial.trial_finished_at || "未知"}｜原始消息：${realTrial.raw_count || 0}｜候选：${realTrial.candidate_count || 0}｜风险：${realTrial.risk_count || 0}｜默认真实读取：${defaultSwitch}`;
  noticeBox.textContent = notice?.visible
    ? (notice.message || realTrialGapMessage)
    : "这批候选还没有自动并进今天处理区，但你已经可以先在候选收件箱里直接处理。";
  const items = realTrialItems.items || [];
  if (!items.length) {
    list.innerHTML = '<div class="empty">最近真实试读暂无候选摘要。</div>';
    return;
  }
  list.innerHTML = items.map((item) => `
    <article class="trial-item">
      <strong>${escapeHtml(item.item_code)}｜${escapeHtml(labels[item.item_type] || item.item_type)}｜${escapeHtml(labels[item.status] || item.status)}</strong>
      <span>${escapeHtml(item.title)}</span>
      <small>${escapeHtml(item.summary)}｜风险：${escapeHtml(riskLabel(item.risk_level))}｜建议：${escapeHtml(downstreamLabel(item.suggested_downstream))}</small>
    </article>
  `).join("");
}

function renderRealTrialSummary(realTrial) {
  if (!realTrial || realTrial.status === "not_found") {
    return "还没有找到最近试读结果。下一步：先去试读消息确认今天有没有抓到新内容。";
  }
  if (realTrial.status !== "ok") {
    return `最近试读暂不可用｜状态：${humanStatusText(realTrial.status)}｜请刷新页面或检查本地服务。`;
  }
  const defaultSwitch = realTrial.default_real_read_enabled ? "已开启" : "关闭";
  return `最近试读时间：${realTrial.trial_finished_at || "未知"}｜原始消息：${realTrial.raw_count || 0}｜候选：${realTrial.candidate_count || 0}｜风险：${realTrial.risk_count || 0}｜默认真实读取：${defaultSwitch}`;
}

async function refreshRealTrialMessages() {
  const data = await api("/api/real-trial/latest/messages");
  state.realTrialMessages = data.messages || [];
  state.realTrialSenders = data.senders || [];
  renderRealTrialMessages(data);
  renderSenderReview(data.senders || []);
}

function renderRealTrialMessages(data) {
  const container = document.querySelector("#realTrialMessages");
  if (!data || data.status === "not_found") {
    container.innerHTML = '<div class="empty">未找到最近真实试读消息明细。</div>';
    return;
  }
  const messages = data.messages || [];
  if (!messages.length) {
    container.innerHTML = '<div class="empty">本次试读没有可审阅消息。</div>';
    return;
  }
  container.innerHTML = messages.map((message) => `
    <article class="message-row">
      <strong>${escapeHtml(message.sent_at)}｜${escapeHtml(message.sender_display_name)}｜${escapeHtml(identityLabel(message.sender_identity))}</strong>
      <span>${escapeHtml(message.content)}</span>
      <small>类型：${escapeHtml(message.message_type)}｜关联候选：${escapeHtml((message.linked_candidate_codes || []).join("、") || "无")}｜风险：${message.has_risk ? "是" : "否"}</small>
    </article>
  `).join("");
}

function renderSenderReview(senders) {
  const container = document.querySelector("#senderReviewList");
  if (!senders.length) {
    container.innerHTML = '<div class="empty">暂无发送人。</div>';
    state.selectedSender = null;
    return;
  }
  state.selectedSender = state.selectedSender || senders[0];
  container.innerHTML = senders.map((sender, index) => `
    <button class="sender-pill ${state.selectedSender?.sender_display_name === sender.sender_display_name ? "active" : ""}" data-sender-index="${index}">
      <strong>${escapeHtml(sender.sender_display_name)}</strong>
      <span>${escapeHtml(identityLabel(sender.sender_identity))}｜${escapeHtml(sender.sender_resolution)}｜${escapeHtml(sender.message_count)} 条</span>
    </button>
  `).join("");
  container.querySelectorAll("[data-sender-index]").forEach((button) => {
    button.addEventListener("click", () => {
      state.selectedSender = senders[Number(button.dataset.senderIndex)];
      renderSenderReview(senders);
    });
  });
}

async function loadRealTrialCandidateMessages(item) {
  if (!item?.id) return;
  const data = await api(`/api/real-trial/latest/items/${item.id}/messages`);
  const container = document.querySelector("#realTrialSourceMessages");
  if (data.status !== "ok" || !(data.messages || []).length) {
    container.innerHTML = '<div class="empty">暂无来源消息。</div>';
    return;
  }
  container.innerHTML = (data.messages || []).map((message) => `
    <article class="message-row">
      <strong>${escapeHtml(data.candidate_ref)}｜${escapeHtml(message.sent_at)}｜${escapeHtml(message.sender_display_name)}｜${escapeHtml(identityLabel(message.sender_identity))}</strong>
      <span>${escapeHtml(message.content)}</span>
      <small>消息：${escapeHtml(message.message_ref)}｜类型：${escapeHtml(message.message_type)}</small>
    </article>
  `).join("");
}

async function importLatestRealTrialCandidates() {
  const result = await api("/api/real-trial/latest/import", {
    method: "POST",
    body: "{}",
  });
  document.querySelector("#importRealTrialResult").textContent =
    `已加入今天处理区：新增 ${result.imported_count || 0}｜重复 ${result.duplicated_count || 0}｜不会自动写入正式日报`;
  await loadItems();
  await refreshDailyControl();
  await refreshInboxV1();
}

async function saveSenderMapping() {
  const sender = state.selectedSender;
  if (!sender) {
    document.querySelector("#senderMappingResult").textContent = "请先选择一个发送人。";
    return;
  }
  const result = await api("/api/real-trial/sender-map", {
    method: "POST",
    body: JSON.stringify({
      sender_display_name: sender.sender_display_name,
      role: document.querySelector("#senderRoleSelect").value,
      person_name: document.querySelector("#senderPersonName").value || "本地人工映射",
      add_alias: true,
    }),
  });
  document.querySelector("#senderMappingResult").textContent =
    `映射保存：${result.status}｜身份：${identityLabel(result.role)}｜${result.alias_saved ? "已保存别名" : "未保存别名"}`;
}

function identityLabel(value) {
  return {
    internal: "我方",
    customer: "客户方",
    channel: "渠道方",
    unknown: "未知",
  }[value] || "未知";
}

function selectedExportTemplateIds() {
  return Array.from(document.querySelectorAll('input[name="exportTemplate"]:checked'))
    .map((input) => input.value);
}

function exportTemplateOptions() {
  return {
    export_date: document.querySelector("#exportTemplateDate").value || today,
    data_source: document.querySelector("#exportDataSource").value || preferredDataSourceValue(),
    include_pending: document.querySelector("#exportIncludePending").checked,
    confirmed_only: document.querySelector("#exportConfirmedOnly").checked,
    separate_risks: document.querySelector("#exportSeparateRisks").checked,
  };
}

function applyTransferTask(taskKey, options = {}) {
  const task = transferTaskPresets[taskKey] || transferTaskPresets.internal_sync;
  state.transferTask = Object.prototype.hasOwnProperty.call(transferTaskPresets, taskKey)
    ? taskKey
    : "internal_sync";
  document.querySelectorAll("[data-transfer-task]").forEach((button) => {
    button.classList.toggle("active", button.dataset.transferTask === state.transferTask);
  });
  document.querySelector("#transferTaskLead").textContent = task.lead;
  document.querySelector("#transferTaskMeta").textContent =
    `${task.title}｜当前候选 ${currentItems().length} 条｜${sourceLabel(state.itemSource)}`;
  document.querySelectorAll('input[name="exportTemplate"]').forEach((input) => {
    input.checked = task.templateIds.includes(input.value);
  });
  document.querySelector("#exportConfirmedOnly").checked = task.confirmedOnly;
  document.querySelector("#exportIncludePending").checked = task.includePending;
  if (!options.skipPreview) {
    refreshExportTemplatePreview();
  }
}

async function refreshExportTemplatePreview() {
  const selected = selectedExportTemplateIds();
  const preview = document.querySelector("#exportTemplatePreview");
  const filename = document.querySelector("#exportFilenamePreview");
  const status = document.querySelector("#exportTemplateStatus");
  if (!selected.length) {
    preview.textContent = "请至少选择一个转述摘要模板。";
    filename.textContent = "文件名预览：未选择";
    return;
  }
  const result = await api("/api/export/templates/preview", {
    method: "POST",
    body: JSON.stringify({
      ...exportTemplateOptions(),
      template_id: selected[0],
    }),
  });
  preview.textContent = result.markdown || "";
  filename.textContent = `本机文件名：${result.filename || ""}`;
  status.textContent =
    `${transferTaskPresets[state.transferTask]?.title || "转述摘要"}｜候选：${result.item_count}｜风险：${result.risk_count}｜${result.safety_boundary}`;
  document.querySelector("#transferTaskMeta").textContent =
    `${transferTaskPresets[state.transferTask]?.title || "转述摘要"}｜当前候选 ${result.item_count} 条｜${sourceLabel(state.itemSource)}`;
}

async function exportTemplates(exportAll = false) {
  const selected = selectedExportTemplateIds();
  const output = document.querySelector("#exportTemplateResult");
  if (!exportAll && !selected.length) {
    output.textContent = "请至少选择一个转述摘要模板。";
    return;
  }
  const result = await api("/api/export/templates", {
    method: "POST",
    body: JSON.stringify({
      ...exportTemplateOptions(),
      export_all: exportAll,
      template_ids: exportAll ? undefined : selected,
    }),
  });
  output.textContent =
    `已生成 ${result.results?.length || 0} 份本机文件，不会自动写正式日报或正式待办。`;
  await refreshExportTemplatePreview();
}

async function openExportTemplateDialog(source = "") {
  document.querySelector("#exportTemplateDate").value = document.querySelector("#filterDate").value || today;
  document.querySelector("#exportDataSource").value =
    source === "realTrial" ? "real_trial" : (source || preferredDataSourceValue());
  setWorkspacePage("transfer");
  applyTransferTask(state.transferTask, { skipPreview: true });
  await refreshExportTemplatePreview();
}

async function loadItems() {
  const date = document.querySelector("#filterDate").value || today;
  const status = document.querySelector("#statusFilter").value;
  const params = new URLSearchParams({ export_date: date });
  if (status) params.set("status", status);
  const [workspaceData, realTrialData] = await Promise.all([
    api(`/api/items?${params.toString()}`),
    api("/api/real-trial/latest/items").catch(() => ({ items: [] })),
  ]);
  state.items = workspaceData.items || [];
  state.realTrialItems = realTrialData.items || [];
  syncCandidatePresentation();
  document.querySelector("#exportDataSource").value = preferredDataSourceValue();
  renderItems();
  applyTransferTask(state.transferTask, { skipPreview: true });
}

function currentItems() {
  return state.itemSource === "realTrial" ? state.realTrialItems : state.items;
}

function visibleItems() {
  const riskOnly = document.querySelector("#riskOnly").checked;
  return currentItems().filter((item) => {
    if (state.typeFilter && item.item_type !== state.typeFilter) return false;
    if (riskOnly && item.risk_level === "none") return false;
    return true;
  });
}

function renderItems() {
  const items = visibleItems();
  const container = document.querySelector("#items");
  document.querySelector("#itemCount").textContent = items.length;
  container.innerHTML = "";
  if (!items.length) {
    const sourceText = "当前还没有可处理候选。下一步：先去试读消息确认今天有没有新反馈，或者刷新状态看看最新结果。";
    container.innerHTML = `<div class="empty">${sourceText}</div>`;
    showEmpty();
    return;
  }
  for (const item of items) {
    const button = document.createElement("button");
    button.className = "item";
    button.innerHTML = `
      <span class="badges">
        ${item.risk_level !== "none" ? '<b class="risk">风险</b>' : ""}
        <b>${escapeHtml(labels[item.status] || item.status)}</b>
        <b>${escapeHtml(sourceLabel(state.itemSource))}</b>
      </span>
      <strong>${escapeHtml(item.item_code)} ${escapeHtml(customerLabel(item.customer_name || item.channel_name || ""))}</strong>
      <span>${escapeHtml(item.title)}</span>
      <small>类型：${escapeHtml(item.human_item_type || labels[item.item_type] || item.item_type)}｜来源：${escapeHtml(sourceLabel(state.itemSource))}｜模块：${escapeHtml(item.module_name || "待补业务模块")}｜建议：${escapeHtml(downstreamLabel(item.suggested_downstream))}｜证据链：${escapeHtml(item.source_message_count ?? item.evidence?.length ?? 0)} 条</small>
      <small>${escapeHtml(item.extraction_reason || "抽取理由：按消息语义形成候选，需人工确认。")}</small>
    `;
    button.addEventListener("click", () => {
      if (state.itemSource === "realTrial") {
        selectRealTrialItem(item);
      } else {
        selectItem(item.id);
      }
    });
    container.appendChild(button);
  }
  if (state.itemSource === "realTrial") {
    selectRealTrialItem(items[0]);
  } else {
    selectItem(items[0].id);
  }
}

async function selectItem(id) {
  const item = await api(`/api/items/${id}`);
  state.selected = item;
  document.querySelector("#detailEmpty").classList.add("hidden");
  document.querySelector("#reviewForm").classList.remove("hidden");
  document.querySelector("#detailMeta").innerHTML = `
    <p><strong>${escapeHtml(item.item_code)}</strong>｜${escapeHtml(labels[item.item_type])}｜${escapeHtml(labels[item.status])}</p>
    <p>客户/渠道：${escapeHtml(customerLabel(item.customer_name || item.channel_name))}｜模块：${escapeHtml(item.module_name || "待补业务模块")}</p>
    <p>摘要：${escapeHtml(item.summary)}</p>
    <p>风险：${escapeHtml(JSON.parse(item.risk_tags_json || "[]").join("、") || "无风险")}</p>
  `;
  document.querySelector("#evidence").textContent = item.evidence.map((row) => row.content_text).join("\n");
  const review = item.reviews?.[0] || {};
  document.querySelector("#reviewStatus").value = item.status;
  document.querySelector("#ownerName").value = review.owner_name || "";
  document.querySelector("#priority").value = review.priority || "P2";
  document.querySelector("#downstream").value = review.downstream || item.suggested_downstream || "none";
  document.querySelector("#note").value = review.note || "";
}

function selectRealTrialItem(item) {
  state.selected = item;
  document.querySelector("#detailEmpty").classList.add("hidden");
  document.querySelector("#reviewForm").classList.remove("hidden");
  document.querySelector("#detailMeta").innerHTML = `
    <p><strong>${escapeHtml(item.item_code)}</strong>｜${escapeHtml(item.human_item_type || labels[item.item_type] || item.item_type)}｜${escapeHtml(labels[item.status] || item.status)}</p>
    <p>摘要：${escapeHtml(item.summary)}</p>
    <p>抽取理由：${escapeHtml(item.extraction_reason || "需人工确认")}</p>
    <p>风险：${escapeHtml((item.risk_tags || []).join("、") || riskLabel(item.risk_level))}</p>
    <p>建议同步：${escapeHtml(downstreamLabel(item.suggested_downstream))}</p>
  `;
  document.querySelector("#reviewStatus").value = item.status || "pending";
  document.querySelector("#ownerName").value = "";
  document.querySelector("#priority").value = "P2";
  document.querySelector("#downstream").value = item.suggested_downstream || "none";
  document.querySelector("#note").value = "";
  document.querySelector("#evidence").textContent =
    "来源消息链只在右侧本机显示；确认前可先把本次试读候选加入今天处理，不会自动写入正式日报或外部系统。";
  loadRealTrialCandidateMessages(item);
}

function showEmpty() {
  state.selected = null;
  document.querySelector("#detailEmpty").classList.remove("hidden");
  document.querySelector("#reviewForm").classList.add("hidden");
}

function setItemSource(source) {
  state.itemSource = source;
  saveWorkspaceState();
  loadItems();
}

document.querySelector("#collectBtn").addEventListener("click", async () => {
  await openConfigCenter();
  showConfigPanel("trial");
});

document.querySelector("#refreshStatusBtn").addEventListener("click", async () => {
  await refreshStatus();
  await refreshRealTrialSummary();
  await refreshDailyControl();
  await refreshInboxV1();
  await loadItems();
});

document.querySelector("#dailyCollectBtn").addEventListener("click", async () => {
  await api("/api/collect", { method: "POST", body: "{}" });
  await refreshStatus();
  await refreshDailyControl();
  await loadItems();
});

document.querySelector("#dailyDraftReportBtn").addEventListener("click", async () => {
  const export_date = document.querySelector("#filterDate").value || today;
  const result = await api("/api/export/report", {
    method: "POST",
    body: JSON.stringify({ export_date }),
  });
  alert(`已生成本机待审日报：${result.file_path}`);
});

document.querySelector("#generateDraftBtn").addEventListener("click", generateDailyDraft);
document.querySelector("#topGenerateDraftBtn").addEventListener("click", async () => {
  setWorkspacePage("daily");
  await regenerateDraftReport();
});
document.querySelector("#dailyReportRegenerateInlineBtn").addEventListener("click", regenerateDraftReport);
document.querySelector("#dailyReportEmptyGenerateBtn").addEventListener("click", regenerateDraftReport);
document.querySelector("#copyDailyReportBtn").addEventListener("click", copyDailyReport);
document.querySelector("#exportDailyMarkdownBtn").addEventListener("click", exportDailyMarkdown);
document.querySelector("#confirmDailySettlementBtn").addEventListener("click", () => {
  const text = currentDailyReportText();
  if (!text.trim()) {
    document.querySelector("#dailySettlementResult").textContent = "请先生成日报全文，再确认沉淀。";
    return;
  }
  writeSettlementStatus(reportControlDate(), "已确认沉淀");
  document.querySelector("#dailySettlementResult").textContent = "已确认沉淀；不会自动写正式区。";
  renderDailyReportCenter();
});
document.querySelector("#markDailyReviewBtn").addEventListener("click", () => {
  writeSettlementStatus(reportControlDate(), "需要重看");
  document.querySelector("#dailySettlementResult").textContent = "已标记需要重看。";
  renderDailyReportCenter();
});
document.querySelector("#refreshDailySettlementBtn").addEventListener("click", renderDailyReportCenter);
document.querySelector("#dailySettlementRows").addEventListener("click", async (event) => {
  const button = event.target.closest("[data-settlement-date]");
  if (!button) return;
  document.querySelector("#filterDate").value = button.dataset.settlementDate;
  await refreshDailyControl();
  await refreshDraftReportPreview();
});

document.querySelector("#dailyControlBtn").addEventListener("click", () => {
  setWorkspacePage("draft");
});
document.querySelector("#dailyViewRealTrialBtn").addEventListener("click", () => {
  setWorkspacePage("candidates");
});
document.querySelector("#dailyImportRealTrialBtn").addEventListener("click", importLatestRealTrialCandidates);
document.querySelector("#dailyExportRealTrialBtn").addEventListener("click", () => openExportTemplateDialog("realTrial"));

document.querySelector("#exportTemplateBtn").addEventListener("click", openExportTemplateDialog);
document.querySelector("#closeExportTemplateBtn").addEventListener("click", () => {
  setWorkspacePage("candidates");
});
document.querySelector("#refreshExportPreviewBtn").addEventListener("click", refreshExportTemplatePreview);
document.querySelector("#exportSelectedTemplateBtn").addEventListener("click", () => exportTemplates(false));
document.querySelector("#exportAllTemplatesBtn").addEventListener("click", () => exportTemplates(true));
document.querySelectorAll('input[name="exportTemplate"], #exportTemplateDate, #exportDataSource, #exportConfirmedOnly, #exportIncludePending, #exportSeparateRisks')
  .forEach((control) => control.addEventListener("change", refreshExportTemplatePreview));
document.querySelectorAll("[data-transfer-task]").forEach((button) => {
  button.addEventListener("click", () => applyTransferTask(button.dataset.transferTask));
});

document.querySelector("#exportReportBtn").addEventListener("click", async () => {
  if (!confirm("旧版日报只会读取今天处理区。推荐优先用转述摘要；仍继续旧版日报？")) return;
  const export_date = document.querySelector("#filterDate").value || today;
  const result = await api("/api/export/report", {
    method: "POST",
    body: JSON.stringify({ export_date }),
  });
  alert(`已导出：${result.file_path}`);
});

document.querySelector("#exportFollowupBtn").addEventListener("click", async () => {
  if (!confirm("旧版待办只会读取今天处理区。推荐优先用转述摘要；仍继续旧版待办？")) return;
  const export_date = document.querySelector("#filterDate").value || today;
  const result = await api("/api/export/followups", {
    method: "POST",
    body: JSON.stringify({ export_date }),
  });
  alert(`已导出：${result.file_path}`);
});

document.querySelector("#reviewForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!state.selected) return;
  if (state.itemSource !== "workspace") {
    document.querySelector("#importRealTrialResult").textContent =
      "这批候选还没并进今天处理区。先点“把本次试读候选加入待确认”，再继续确认 / 驳回 / 改类型。";
    return;
  }
  await api(`/api/items/${state.selected.id}/review`, {
    method: "POST",
    body: JSON.stringify({
      review_status: document.querySelector("#reviewStatus").value,
      owner_name: document.querySelector("#ownerName").value,
      priority: document.querySelector("#priority").value,
      downstream: document.querySelector("#downstream").value,
      note: document.querySelector("#note").value,
    }),
  });
  await loadItems();
});

document.querySelector("#cancelBtn").addEventListener("click", () => {
  if (state.selected && state.itemSource === "workspace") selectItem(state.selected.id);
});

document.querySelector("#candidateActionBar").addEventListener("click", async (event) => {
  const button = event.target.closest("[data-candidate-action]");
  if (!button || !state.selected) return;
  const action = button.dataset.candidateAction;
  if (state.itemSource !== "workspace") {
    document.querySelector("#importRealTrialResult").textContent =
      "请先点击“把本次试读候选加入待确认”，再继续处理确认动作。";
    return;
  }
  if (action === "confirm") document.querySelector("#reviewStatus").value = "confirmed";
  if (action === "reject") document.querySelector("#reviewStatus").value = "rejected";
  if (action === "undo") document.querySelector("#reviewStatus").value = "pending";
  if (action === "change-type") {
    const value = prompt("改为类型：requirement / bug / consultation / conclusion / followup");
    if (!value) return;
    state.selected.item_type = value;
  }
  if (action === "note") {
    document.querySelector("#note").focus();
    return;
  }
  await api(`/api/items/${state.selected.id}/review`, {
    method: "POST",
    body: JSON.stringify({
      review_status: document.querySelector("#reviewStatus").value,
      item_type: state.selected.item_type,
      owner_name: document.querySelector("#ownerName").value,
      priority: document.querySelector("#priority").value,
      downstream: document.querySelector("#downstream").value,
      note: document.querySelector("#note").value,
    }),
  });
  await loadItems();
  await refreshDailyControl();
  await refreshInboxV1();
});

document.querySelector("#statusFilter").addEventListener("change", loadItems);
document.querySelector("#filterDate").addEventListener("change", async () => {
  await loadItems();
  await refreshDailyControl();
  await refreshDraftReportPreview();
});
document.querySelector("#riskOnly").addEventListener("change", renderItems);

document.querySelectorAll("[data-type]").forEach((button) => {
  button.addEventListener("click", () => {
    state.typeFilter = state.typeFilter === button.dataset.type ? "" : button.dataset.type;
    document.querySelectorAll("[data-type]").forEach((node) => node.classList.remove("active"));
    if (state.typeFilter) button.classList.add("active");
    renderItems();
  });
});

document.querySelector("#configBtn").addEventListener("click", openConfigCenter);
document.querySelector("#configBackBtn").addEventListener("click", () => {
  setWorkspacePage("daily");
});
document.querySelector("#addMonitorGroupBtn").addEventListener("click", async () => {
  await ensureConfigCenterLoaded();
  addMonitorGroupDraft();
});
document.querySelector("#monitorGroupSearch").addEventListener("input", renderMonitoringGroups);
document.querySelector("#saveMonitorGroupBtn").addEventListener("click", saveSelectedMonitorGroup);
document.querySelector("#disableMonitorGroupBtn").addEventListener("click", disableSelectedMonitorGroup);
document.querySelector("#addPeoplePagePersonBtn").addEventListener("click", async () => {
  await ensureConfigCenterLoaded();
  state.configCenter.editable.internal_people.push({ person_name: "", aliases: [] });
  renderPeoplePage();
});
document.querySelector("#savePeoplePageBtn").addEventListener("click", savePeoplePage);
document.querySelector("#addSessionBtn").addEventListener("click", () => {
  state.configCenter.editable.sessions.push(emptySession());
  renderSessionRows(state.configCenter.editable.sessions);
  renderGroupTagRows(state.configCenter.editable.sessions);
});
document.querySelector("#addPersonBtn").addEventListener("click", () => {
  state.configCenter.editable.internal_people.push({ person_name: "", aliases: [] });
  renderPersonRows(state.configCenter.editable.internal_people);
});
document.querySelector("#saveConfigBtn").addEventListener("click", saveConfigCenter);
document.querySelector("#startTrialBtn").addEventListener("click", confirmAndPlanTrialRun);

document.querySelector("#testWxCliBtn").addEventListener("click", async () => {
  const result = await api("/api/wx-cli/test");
  document.querySelector("#wxCliTestResult").textContent =
    `${result.status}｜会话数：${result.session_count || 0}${result.error_code ? `｜错误：${result.error_code}` : ""}｜${result.message || ""}${binaryConfiguredText(result)}｜建议：${result.next_action || ""}`;
  await refreshStatus();
});

document.querySelectorAll("#configCenterNav [data-panel]").forEach((button) => {
  button.addEventListener("click", () => showConfigPanel(button.dataset.panel));
});

document.querySelectorAll("[data-trial-preset]").forEach((button) => {
  button.addEventListener("click", () => applyTrialPreset(button.dataset.trialPreset));
});

document.querySelector("#refreshRealTrialMessagesBtn").addEventListener("click", refreshRealTrialMessages);
document.querySelector("#importRealTrialBtn").addEventListener("click", importLatestRealTrialCandidates);
document.querySelector("#realTrialExportTemplateBtn").addEventListener("click", () => openExportTemplateDialog("realTrial"));
document.querySelector("#saveSenderMappingBtn").addEventListener("click", saveSenderMapping);
document.querySelector("#refreshDraftReportBtn").addEventListener("click", refreshDraftReportPreview);
document.querySelector("#regenerateDraftReportBtn").addEventListener("click", regenerateDraftReport);

document.querySelector("#dailyPendingRows").addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-action]");
  if (!button) return;
  const row = button.closest("[data-daily-item-id]");
  if (!row) return;
  const itemId = row.dataset.dailyItemId;
  const action = button.dataset.action;
  const payload = {};
  if (action === "confirm") payload.review_status = "confirmed";
  if (action === "reject") payload.review_status = "rejected";
  if (action === "change_type") {
    const value = prompt("改为类型：requirement / bug / consultation / conclusion / followup");
    if (!value) return;
    payload.item_type = value;
  }
  if (action === "mark_risk") {
    const value = prompt("风险等级：none / low / high", "high");
    if (!value) return;
    payload.risk_level = value;
    payload.risk_tags = value === "none" ? [] : ["人工补标"];
  }
  if (action === "assign_owner") {
    const value = prompt("负责人");
    if (!value) return;
    payload.owner_name = value;
  }
  await api(`/api/daily-control/items/${itemId}`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
  await refreshDailyControl();
  await loadItems();
});

document.querySelector("#saveQualityFeedbackBtn").addEventListener("click", async () => {
  const feedback_date = document.querySelector("#filterDate").value || today;
  const feedback_type = document.querySelector("#qualityFeedbackType").value;
  const note = document.querySelector("#qualityFeedbackNote").value;
  const result = await api("/api/daily-control/feedback", {
    method: "POST",
    body: JSON.stringify({ feedback_date, feedback_type, note }),
  });
  document.querySelector("#qualityFeedbackResult").textContent = `已保存：${result.feedback_type || result.status}`;
  document.querySelector("#qualityFeedbackNote").value = "";
  await refreshDailyControl();
});

async function openConfigCenter(options = {}) {
  const data = await api("/api/config-center");
  state.configCenter = data;
  renderConfigCenter(data);
  if (options.setPage !== false) {
    setWorkspacePage("config");
  }
}

function renderConfigCenter(data) {
  const status = data.status || {};
  const latest = status.latest_trial || {};
  const trialDefaults = data.editable?.trial_defaults || {};
  const fallbackRange = defaultTrialRange();
  document.querySelector("#configCenterStatus").textContent =
    `模式：${status.mode}｜默认真实读取：${status.real_read_enabled ? "开启" : "关闭"}｜wx-cli：${status.wx_cli_status}｜白名单：${status.enabled_whitelist_count || 0}｜最近试读：${latest.status || "unknown"}`;
  document.querySelector("#trialLimitInput").value = trialDefaults.limit || 50;
  document.querySelector("#trialLookbackInput").value = trialDefaults.lookback_hours || 2;
  document.querySelector("#trialStartInput").value = normalizeDateTimeInput(trialDefaults.start_at) || fallbackRange.start;
  document.querySelector("#trialEndInput").value = normalizeDateTimeInput(trialDefaults.end_at) || fallbackRange.end;
  renderTrialCards(latest);
  renderSessionRows(data.editable?.sessions || []);
  renderGroupTagRows(data.editable?.sessions || []);
  renderPersonRows(data.editable?.internal_people || []);
  document.querySelector("#riskKeywords").value = (data.editable?.risk?.keywords || []).join("\n");
  document.querySelector("#sensitiveKeywords").value = (data.editable?.risk?.sensitive_keywords || []).join("\n");
  document.querySelector("#safetySummary").textContent =
    `保存不会采集｜试读需确认｜最大条数 ${data.safety?.max_limit || 50}｜最大回看 ${data.safety?.max_lookback_hours || 2} 小时｜默认真实读取：关闭${data.safety?.fixture_service_notice ? "｜当前页面不是 real 配置服务" : ""}`;
  renderMonitoringGroups();
  renderPeoplePage();
}

async function ensureConfigCenterLoaded() {
  if (state.configCenter) {
    renderMonitoringGroups();
    renderPeoplePage();
    return state.configCenter;
  }
  const data = await api("/api/config-center");
  state.configCenter = data;
  renderConfigCenter(data);
  return data;
}

function monitorGroupMeta() {
  return storedJson(MONITOR_GROUP_META_STORAGE, {});
}

function saveMonitorGroupMeta(groups = state.monitorGroups) {
  const meta = {};
  groups.forEach((group) => {
    meta[group.external_id] = {
      daily_monitor: Boolean(group.daily_monitor),
      include_in_daily: Boolean(group.include_in_daily),
      verification_status: group.verification_status || "待验证",
      trial_range: group.trial_range || "recent50",
      internal_people: group.internal_people || [],
    };
  });
  localStorage.setItem(MONITOR_GROUP_META_STORAGE, JSON.stringify(meta));
}

function normalizeMonitorGroup(session, meta = {}) {
  return {
    external_id: session.external_id || makeMonitorGroupId(),
    display_name: session.display_name || "",
    customer_name: session.customer_name || "",
    channel_name: session.channel_name || "",
    module_name: session.module_name || "",
    owner_name: session.owner_name || "",
    customer_stage: session.customer_stage || "",
    group_type: session.group_type || "",
    common_contacts: session.common_contacts || [],
    reply_notes: session.reply_notes || "",
    is_whitelisted: session.is_whitelisted !== false,
    enabled: session.enabled !== false,
    daily_monitor: meta.daily_monitor ?? (session.enabled !== false && session.is_whitelisted !== false),
    include_in_daily: meta.include_in_daily ?? (session.enabled !== false && session.is_whitelisted !== false),
    verification_status: meta.verification_status || "已验证",
    trial_range: meta.trial_range || "recent50",
    internal_people: meta.internal_people || [],
  };
}

function makeMonitorGroupId() {
  return `local-monitor-${Date.now()}`;
}

function buildMonitorGroups() {
  const meta = monitorGroupMeta();
  const sessions = state.configCenter?.editable?.sessions || [];
  const groups = sessions.map((session) =>
    normalizeMonitorGroup(session, meta[session.external_id] || {})
  );
  if (!groups.some((group) => group.display_name === monitorGroupSeed.display_name)) {
    groups.push({ ...monitorGroupSeed, ...(meta[monitorGroupSeed.external_id] || {}) });
  }
  return groups;
}

function optionValuesFromGroups(field) {
  const values = new Set(
    (state.monitorGroups || [])
      .map((group) => group[field])
      .filter(Boolean)
  );
  if (field === "customer_name") {
    values.add("稿定电商");
    values.add("待确认客户");
    values.add("新建本地客户占位");
  }
  return Array.from(values);
}

function internalPeopleNames() {
  const people = state.configCenter?.editable?.internal_people || [];
  const names = new Set(people.map((person) => person.person_name).filter(Boolean));
  (state.monitorGroups || []).forEach((group) => {
    if (group.owner_name) names.add(group.owner_name);
    (group.internal_people || []).forEach((name) => names.add(name));
  });
  return Array.from(names);
}

function contactOptions() {
  const values = new Set();
  (state.monitorGroups || []).forEach((group) => {
    (group.common_contacts || []).forEach((contact) => values.add(contact));
  });
  values.add("常用联系人待补");
  return Array.from(values);
}

function setOptions(select, options, selected, { allowEmpty = true, multiple = false } = {}) {
  const selectedValues = new Set(Array.isArray(selected) ? selected : [selected].filter(Boolean));
  const normalized = options.map((option) => Array.isArray(option) ? option : [option, option]);
  select.innerHTML = [
    ...(allowEmpty && !multiple ? [["", "待选择"]] : []),
    ...normalized,
  ].map(([value, label]) =>
    `<option value="${escapeAttr(value)}" ${selectedValues.has(value) ? "selected" : ""}>${escapeHtml(label)}</option>`
  ).join("");
}

function selectedValues(select) {
  return Array.from(select.selectedOptions || []).map((option) => option.value).filter(Boolean);
}

function groupCompleteness(group) {
  const required = [
    group.display_name,
    group.customer_name,
    group.group_type,
    group.module_name,
    group.customer_stage,
    group.owner_name,
  ];
  const done = required.filter(Boolean).length;
  return {
    done,
    total: required.length,
    label: done === required.length ? "配置完整" : `待补 ${required.length - done} 项`,
  };
}

function renderMonitoringGroups() {
  const list = document.querySelector("#monitorGroupList");
  if (!list || !state.configCenter) return;
  const query = (document.querySelector("#monitorGroupSearch")?.value || "").trim();
  const baseGroups = buildMonitorGroups();
  const transientGroups = (state.monitorGroups || []).filter((group) =>
    !baseGroups.some((base) => base.external_id === group.external_id)
  );
  state.monitorGroups = [...baseGroups, ...transientGroups];
  if (!state.selectedMonitorGroupId || !state.monitorGroups.some((group) => group.external_id === state.selectedMonitorGroupId)) {
    state.selectedMonitorGroupId = state.monitorGroups[0]?.external_id || "";
  }
  const filtered = state.monitorGroups.filter((group) => {
    if (!query) return true;
    return [group.display_name, group.customer_name, group.owner_name, group.module_name]
      .some((value) => String(value || "").includes(query));
  });
  list.innerHTML = filtered.map((group) => {
    const complete = groupCompleteness(group);
    const monitorText = group.enabled === false
      ? "已停用"
      : group.daily_monitor && group.include_in_daily && group.verification_status !== "待验证"
        ? "已纳入日报"
        : "待验证 / 未纳入日报";
    return `
      <button class="monitor-group-card ${group.external_id === state.selectedMonitorGroupId ? "active" : ""}" data-monitor-group-id="${escapeAttr(group.external_id)}">
        <strong>${escapeHtml(group.display_name || "未命名监控群")}</strong>
        <span>${escapeHtml(group.customer_name || "待选择客户")}｜${escapeHtml(group.group_type || "待选群类型")}</span>
        <small>${escapeHtml(monitorText)}｜${escapeHtml(complete.label)}｜负责人：${escapeHtml(group.owner_name || "待指定")}</small>
      </button>
    `;
  }).join("") || '<div class="empty">没有匹配的监控群。</div>';
  list.querySelectorAll("[data-monitor-group-id]").forEach((button) => {
    button.addEventListener("click", () => {
      state.selectedMonitorGroupId = button.dataset.monitorGroupId;
      renderMonitoringGroups();
    });
  });
  renderMonitorGroupEditor();
  renderDailyReportCenter();
}

function renderMonitorGroupEditor() {
  const group = state.monitorGroups.find((item) => item.external_id === state.selectedMonitorGroupId);
  const title = document.querySelector("#monitorGroupEditorTitle");
  if (!title || !group) return;
  const completeness = groupCompleteness(group);
  title.textContent = group.display_name || "新监控群";
  document.querySelector("#monitorGroupEditorStatus").textContent =
    `${group.verification_status || "待验证"}｜${group.enabled === false ? "已停用" : "启用中"}｜试读成功前不会自动纳入日报统计`;
  document.querySelector("#monitorGroupCompleteness").textContent = completeness.label;
  document.querySelector("#monitorGroupDisplayName").value = group.display_name || "";
  setOptions(document.querySelector("#monitorGroupCustomer"), optionValuesFromGroups("customer_name"), group.customer_name);
  setOptions(document.querySelector("#monitorGroupType"), monitorGroupOptions.groupTypes, group.group_type);
  setOptions(document.querySelector("#monitorGroupModule"), [
    ...new Set([...monitorGroupOptions.modules, ...optionValuesFromGroups("module_name")]),
  ], group.module_name);
  setOptions(document.querySelector("#monitorGroupStage"), monitorGroupOptions.stages, group.customer_stage);
  setOptions(document.querySelector("#monitorGroupOwner"), internalPeopleNames(), group.owner_name);
  setOptions(document.querySelector("#monitorGroupContacts"), contactOptions(), group.common_contacts || [], { allowEmpty: false, multiple: true });
  setOptions(document.querySelector("#monitorGroupInternalPeople"), internalPeopleNames(), group.internal_people || [], { allowEmpty: false, multiple: true });
  setOptions(document.querySelector("#monitorGroupTrialRange"), monitorGroupOptions.trialRanges, group.trial_range || "recent50", { allowEmpty: false });
  setOptions(document.querySelector("#monitorGroupVerifyStatus"), monitorGroupOptions.verifyStatuses, group.verification_status || "待验证", { allowEmpty: false });
  document.querySelector("#monitorGroupDailyMonitor").checked = Boolean(group.daily_monitor);
  document.querySelector("#monitorGroupIncludeDaily").checked = Boolean(group.include_in_daily);
  document.querySelector("#monitorGroupReplyNotes").value = group.reply_notes || "";
}

function readMonitorGroupForm() {
  const current = state.monitorGroups.find((group) => group.external_id === state.selectedMonitorGroupId) || {
    external_id: makeMonitorGroupId(),
  };
  return {
    ...current,
    display_name: document.querySelector("#monitorGroupDisplayName").value.trim(),
    customer_name: document.querySelector("#monitorGroupCustomer").value,
    group_type: document.querySelector("#monitorGroupType").value,
    module_name: document.querySelector("#monitorGroupModule").value,
    customer_stage: document.querySelector("#monitorGroupStage").value,
    owner_name: document.querySelector("#monitorGroupOwner").value,
    common_contacts: selectedValues(document.querySelector("#monitorGroupContacts")),
    internal_people: selectedValues(document.querySelector("#monitorGroupInternalPeople")),
    trial_range: document.querySelector("#monitorGroupTrialRange").value,
    daily_monitor: document.querySelector("#monitorGroupDailyMonitor").checked,
    include_in_daily: document.querySelector("#monitorGroupIncludeDaily").checked,
    verification_status: document.querySelector("#monitorGroupVerifyStatus").value,
    reply_notes: document.querySelector("#monitorGroupReplyNotes").value.trim(),
    is_whitelisted: true,
  };
}

function monitorGroupToSession(group) {
  return {
    external_id: group.external_id || makeMonitorGroupId(),
    display_name: group.display_name || "未命名监控群",
    customer_name: group.customer_name || "",
    channel_name: group.channel_name || "",
    module_name: group.module_name || "",
    owner_name: group.owner_name || "",
    customer_stage: group.customer_stage || "",
    group_type: group.group_type || "",
    common_contacts: group.common_contacts || [],
    reply_notes: group.reply_notes || "",
    is_whitelisted: true,
    enabled: group.enabled !== false,
  };
}

async function saveConfigFromState() {
  const editable = state.configCenter?.editable || {};
  const result = await api("/api/config-center", {
    method: "POST",
    body: JSON.stringify({
      sessions: (state.monitorGroups || []).map(monitorGroupToSession),
      internal_people: editable.internal_people || [],
      risk: editable.risk || {},
      trial_defaults: {
        ...(editable.trial_defaults || {}),
        real_read_enabled: false,
      },
    }),
  });
  state.configCenter.editable = result.editable;
  renderConfigCenter(state.configCenter);
  return result;
}

async function saveSelectedMonitorGroup() {
  const group = readMonitorGroupForm();
  if (!group.display_name) {
    document.querySelector("#monitorGroupSaveResult").textContent = "请先填写监控群名称。";
    return;
  }
  const index = state.monitorGroups.findIndex((item) => item.external_id === group.external_id);
  if (index >= 0) state.monitorGroups[index] = group;
  else state.monitorGroups.push(group);
  state.selectedMonitorGroupId = group.external_id;
  saveMonitorGroupMeta();
  try {
    await saveConfigFromState();
    document.querySelector("#monitorGroupSaveResult").textContent = "已保存监控群档案；不会自动读取或外发。";
  } catch (_error) {
    document.querySelector("#monitorGroupSaveResult").textContent = "已暂存在本机浏览器；配置保存暂不可用。";
  }
  renderMonitoringGroups();
}

async function disableSelectedMonitorGroup() {
  const group = readMonitorGroupForm();
  group.enabled = false;
  group.daily_monitor = false;
  group.include_in_daily = false;
  const index = state.monitorGroups.findIndex((item) => item.external_id === group.external_id);
  if (index >= 0) state.monitorGroups[index] = group;
  saveMonitorGroupMeta();
  try {
    await saveConfigFromState();
    document.querySelector("#monitorGroupSaveResult").textContent = "已停用该监控群。";
  } catch (_error) {
    document.querySelector("#monitorGroupSaveResult").textContent = "已在本机页面停用；配置保存暂不可用。";
  }
  renderMonitoringGroups();
}

function addMonitorGroupDraft() {
  const group = {
    ...monitorGroupSeed,
    external_id: makeMonitorGroupId(),
    display_name: "",
    customer_name: "",
    module_name: "",
    owner_name: "",
    common_contacts: [],
    internal_people: [],
    reply_notes: "",
  };
  state.monitorGroups = [...(state.monitorGroups || []), group];
  state.selectedMonitorGroupId = group.external_id;
  renderMonitoringGroups();
  document.querySelector("#monitorGroupDisplayName")?.focus();
}

function renderPeoplePage() {
  const container = document.querySelector("#peoplePageRows");
  if (!container || !state.configCenter) return;
  const people = state.configCenter.editable?.internal_people || [];
  container.innerHTML = people.map((person, index) => `
    <div class="editor-row" data-people-page-index="${index}">
      <label>人员名称<input data-field="person_name" value="${escapeAttr(person.person_name)}" /></label>
      <label class="wide">别名，逗号分隔<input data-field="aliases" value="${escapeAttr((person.aliases || []).join(", "))}" /></label>
    </div>
  `).join("") || '<div class="empty">还没有我方人员。下一步：新增人员后保存。</div>';
}

async function savePeoplePage() {
  await ensureConfigCenterLoaded();
  state.configCenter.editable.internal_people = Array.from(document.querySelectorAll("[data-people-page-index]")).map((row) => {
    const data = readEditorRow(row);
    return {
      person_name: data.person_name,
      aliases: String(data.aliases || "").split(",").map((item) => item.trim()).filter(Boolean),
    };
  }).filter((person) => person.person_name);
  try {
    await saveConfigFromState();
    document.querySelector("#peoplePageResult").textContent = "已保存我方人员。";
  } catch (_error) {
    document.querySelector("#peoplePageResult").textContent = "人员已在本机页面更新；配置保存暂不可用。";
  }
  renderPeoplePage();
  renderMonitoringGroups();
}

function renderTrialCards(latest) {
  const cards = [
    ["读取", latest.raw_count || 0],
    ["入库", latest.collection_run?.raw_messages_inserted || 0],
    ["重复", latest.collection_run?.raw_messages_duplicated || 0],
    ["候选", latest.candidate_count || 0],
    ["风险", latest.risk_count || 0],
  ];
  document.querySelector("#configTrialCards").innerHTML = cards
    .map(([label, value]) => `<div class="metric"><span>${escapeHtml(label)}</span><b>${escapeHtml(value)}</b></div>`)
    .join("");
}

function renderSessionRows(sessions) {
  document.querySelector("#sessionRows").innerHTML = sessions.map((session, index) => `
    <div class="editor-row" data-session-index="${index}">
      <label class="wide">会话标识<input data-field="external_id" value="${escapeAttr(session.external_id)}" /></label>
      <label class="wide">显示名称<input data-field="display_name" value="${escapeAttr(session.display_name)}" /></label>
      <label>客户<input data-field="customer_name" value="${escapeAttr(session.customer_name)}" /></label>
      <label>渠道<input data-field="channel_name" value="${escapeAttr(session.channel_name)}" /></label>
      <label>模块<input data-field="module_name" value="${escapeAttr(session.module_name)}" /></label>
      <label>负责人<input data-field="owner_name" value="${escapeAttr(session.owner_name)}" /></label>
      <label class="toggle"><input type="checkbox" data-field="is_whitelisted" ${session.is_whitelisted ? "checked" : ""} />白名单</label>
      <label class="toggle"><input type="checkbox" data-field="enabled" ${session.enabled ? "checked" : ""} />启用</label>
    </div>
  `).join("");
}

function renderGroupTagRows(sessions) {
  document.querySelector("#groupTagRows").innerHTML = sessions.map((session, index) => `
    <div class="editor-row group-tag-row" data-group-tag-index="${index}">
      <label class="wide">会话标识<input data-field="external_id" value="${escapeAttr(session.external_id)}" readonly /></label>
      <label>客户名称<input data-field="customer_name" value="${escapeAttr(session.customer_name)}" /></label>
      <label>群负责人<input data-field="owner_name" value="${escapeAttr(session.owner_name)}" /></label>
      <label>业务模块<input data-field="module_name" value="${escapeAttr(session.module_name)}" /></label>
      <label>客户阶段<input data-field="customer_stage" value="${escapeAttr(session.customer_stage)}" /></label>
      <label>群类型<input data-field="group_type" value="${escapeAttr(session.group_type)}" /></label>
      <label class="wide">常用联系人，逗号分隔<input data-field="common_contacts" value="${escapeAttr((session.common_contacts || []).join(", "))}" /></label>
      <label class="wide">回复注意事项<textarea data-field="reply_notes" rows="3">${escapeHtml(session.reply_notes || "")}</textarea></label>
    </div>
  `).join("");
}

function renderPersonRows(people) {
  document.querySelector("#personRows").innerHTML = people.map((person, index) => `
    <div class="editor-row" data-person-index="${index}">
      <label>人员名称<input data-field="person_name" value="${escapeAttr(person.person_name)}" /></label>
      <label class="wide">别名，逗号分隔<input data-field="aliases" value="${escapeAttr((person.aliases || []).join(", "))}" /></label>
    </div>
  `).join("");
}

function showConfigPanel(panel) {
  document.querySelectorAll("#configCenterNav [data-panel]").forEach((button) => {
    button.classList.toggle("active", button.dataset.panel === panel);
  });
  document.querySelectorAll("[data-panel-view]").forEach((view) => {
    view.classList.toggle("hidden", view.dataset.panelView !== panel);
  });
}

async function saveConfigCenter() {
  const payload = collectConfigCenterPayload();
  const result = await api("/api/config-center", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  state.configCenter.editable = result.editable;
  renderSessionRows(result.editable?.sessions || []);
  renderGroupTagRows(result.editable?.sessions || []);
  document.querySelector("#configSaveResult").textContent =
    `已保存到 ${result.saved_to}｜默认真实读取：${result.real_read_enabled ? "开启" : "关闭"}`;
  await refreshStatus();
  await refreshInboxV1();
}

function collectConfigCenterPayload() {
  const sessions = Array.from(document.querySelectorAll("[data-session-index]")).map((row) => readEditorRow(row));
  const tagsBySession = new Map(
    Array.from(document.querySelectorAll("[data-group-tag-index]")).map((row) => {
      const data = readEditorRow(row);
      data.common_contacts = String(data.common_contacts || "").split(",").map((item) => item.trim()).filter(Boolean);
      return [data.external_id, data];
    })
  );
  const mergedSessions = sessions.map((session) => ({
    ...session,
    ...(tagsBySession.get(session.external_id) || {}),
  }));
  const internalPeople = Array.from(document.querySelectorAll("[data-person-index]")).map((row) => {
    const data = readEditorRow(row);
    return {
      person_name: data.person_name,
      aliases: String(data.aliases || "").split(",").map((item) => item.trim()).filter(Boolean),
    };
  });
  return {
    sessions: mergedSessions,
    internal_people: internalPeople,
    risk: {
      keywords: document.querySelector("#riskKeywords").value.split("\n").map((item) => item.trim()).filter(Boolean),
      sensitive_keywords: document.querySelector("#sensitiveKeywords").value.split("\n").map((item) => item.trim()).filter(Boolean),
    },
    trial_defaults: {
      limit: Number(document.querySelector("#trialLimitInput").value || 50),
      lookback_hours: Number(document.querySelector("#trialLookbackInput").value || 2),
      start_at: document.querySelector("#trialStartInput").value || "",
      end_at: document.querySelector("#trialEndInput").value || "",
      real_read_enabled: false,
    },
  };
}

function readEditorRow(row) {
  const data = {};
  row.querySelectorAll("[data-field]").forEach((input) => {
    data[input.dataset.field] = input.type === "checkbox" ? input.checked : input.value;
  });
  return data;
}

async function confirmAndPlanTrialRun() {
  const limit = Number(document.querySelector("#trialLimitInput").value || 50);
  const startAt = document.querySelector("#trialStartInput").value || "";
  const endAt = document.querySelector("#trialEndInput").value || "";
  const ok = confirm(
    `开始只读试读前请确认：仅限单一启用白名单会话，范围 ${startAt || "最近50条"} 至 ${endAt || "不限定结束"}，最多 ${Math.min(limit, 50)} 条；不会外发，不会自动回复，不会写正式待办池、正式日报或 Obsidian 正式区。`
  );
  if (!ok) return;
  const result = await api("/api/real-trial/run", {
    method: "POST",
    body: JSON.stringify({
      confirmed: true,
      limit,
      lookback_hours: document.querySelector("#trialLookbackInput").value || "",
      start_at: startAt,
      end_at: endAt,
      preset: state.trialPreset || "",
    }),
  });
  document.querySelector("#trialRunResult").textContent =
    `${result.status}${result.error_code ? `｜${result.error_code}` : ""}｜${result.message || ""}`;
}

function applyTrialPreset(preset) {
  state.trialPreset = preset || "";
  const now = new Date();
  document.querySelector("#trialLimitInput").value = "50";
  if (preset === "2h") {
    const start = new Date(now.getTime() - 2 * 60 * 60 * 1000);
    document.querySelector("#trialStartInput").value = formatDateTimeLocal(start);
    document.querySelector("#trialEndInput").value = formatDateTimeLocal(now);
    document.querySelector("#trialLookbackInput").value = "2";
    return;
  }
  if (preset === "today") {
    const start = new Date(now);
    start.setHours(0, 0, 0, 0);
    document.querySelector("#trialStartInput").value = formatDateTimeLocal(start);
    document.querySelector("#trialEndInput").value = formatDateTimeLocal(now);
    document.querySelector("#trialLookbackInput").value = "2";
    return;
  }
  if (preset === "recent50") {
    const range = defaultTrialRange();
    document.querySelector("#trialStartInput").value = range.start;
    document.querySelector("#trialEndInput").value = range.end;
    document.querySelector("#trialLookbackInput").value = "2";
  }
}

function defaultTrialRange() {
  const now = new Date();
  const start = new Date(now.getTime() - 2 * 60 * 60 * 1000);
  return {
    start: formatDateTimeLocal(start),
    end: formatDateTimeLocal(now),
  };
}

function normalizeDateTimeInput(value) {
  if (!value) return "";
  return String(value).replace(" ", "T").slice(0, 16);
}

function formatDateTimeLocal(date) {
  const pad = (number) => String(number).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

async function generateDailyDraft() {
  const control_date = document.querySelector("#filterDate").value || today;
  const result = await api("/api/daily-control/draft", {
    method: "POST",
    body: JSON.stringify({ control_date }),
  });
  document.querySelector("#draftReportMeta").textContent =
    `已生成本机草稿｜候选：${result.item_count || 0}｜正式日报 / 正式待办：保持关闭`;
  await refreshDailyControl();
}

async function refreshDraftReportPreview() {
  const controlDate = document.querySelector("#filterDate").value || today;
  const source = document.querySelector("#draftDataSourceChoice")?.value || preferredDataSourceValue();
  const query = new URLSearchParams({ control_date: controlDate });
  if (source) query.set("data_source", source);
  const data = await api(`/api/daily-control/draft-preview?${query.toString()}`);
  if (document.querySelector("#draftDataSourceChoice") && data.data_source) {
    document.querySelector("#draftDataSourceChoice").value = data.data_source;
  }
  renderDraftReportPreview(data);
}

async function regenerateDraftReport() {
  const controlDate = document.querySelector("#filterDate").value || today;
  const source = document.querySelector("#draftDataSourceChoice")?.value || preferredDataSourceValue();
  const data = await api("/api/daily-control/draft-preview", {
    method: "POST",
    body: JSON.stringify({ control_date: controlDate, data_source: source }),
  });
  if (document.querySelector("#draftDataSourceChoice") && data.data_source) {
    document.querySelector("#draftDataSourceChoice").value = data.data_source;
  }
  renderDraftReportPreview(data);
  await refreshDailyControl();
}

function renderDraftReportPreview(data) {
  state.dailyDraftPreview = data;
  document.querySelector("#draftReportMeta").textContent =
    `生成时间：${data.generated_at || "未保存"}｜数据来源：${humanDataSourceLabel(data.data_source_label)}｜候选：${data.candidate_count || 0}｜风险：${data.risk_count || 0}｜状态：${data.draft_status || "机器初稿 / 待审阅"}｜正式日报 / 正式待办：${humanStatusText(data.formal_write_status || "保持关闭")}｜下一步：${data.next_step || "人工审阅"}`;
  document.querySelector("#draftReportPreview").textContent = data.preview_markdown || "";
  document.querySelector("#draftReportLinks").innerHTML = (data.items || []).map((item) => `
    <button class="trial-item" data-draft-target="${escapeAttr(item.target)}" data-draft-item-id="${escapeAttr(item.item_id)}">
      ${escapeHtml(item.item_code || "候选")}｜${escapeHtml(labels[item.item_type] || item.item_type)}｜${escapeHtml(labels[item.status] || item.status)}｜风险：${escapeHtml(riskLabel(item.risk_level))}
    </button>
  `).join("") || '<div class="empty">暂无草稿关联候选。</div>';
  document.querySelectorAll("[data-draft-target]").forEach((button) => {
    button.addEventListener("click", () => openDraftLinkedItem(button.dataset.draftTarget, button.dataset.draftItemId));
  });
  renderDailyReportCenter();
}

function openDraftLinkedItem(target, itemId) {
  if (target === "real_trial_messages") {
    setItemSource("realTrial");
    const item = state.realTrialItems.find((row) => String(row.id) === String(itemId));
    if (item) selectRealTrialItem(item);
    setWorkspacePage("messages");
    return;
  }
  if (itemId) {
    setItemSource("workspace");
    selectItem(Number(itemId));
    setWorkspacePage("candidates");
  }
}

function emptySession() {
  return {
    external_id: "",
    display_name: "",
    customer_name: "",
    channel_name: "",
    module_name: "",
    owner_name: "",
    customer_stage: "",
    group_type: "",
    common_contacts: [],
    reply_notes: "",
    is_whitelisted: true,
    enabled: true,
  };
}

function escapeAttr(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll('"', "&quot;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function binaryConfiguredText(info) {
  const configured = Boolean(info.binary_configured) || Boolean(info.configured_binary);
  const executable = String(info.is_executable) === "true";
  return `｜本地程序：${configured ? "已配置" : "未配置"}｜执行：${executable ? "可执行" : "不可执行"}`;
}

function saveWorkspaceState() {
  localStorage.setItem("inbox_v1_state", JSON.stringify({
    version: WORKSPACE_STATE_VERSION,
    page: state.activePage,
    itemSource: state.itemSource,
    filterDate: document.querySelector("#filterDate")?.value || today,
    statusFilter: document.querySelector("#statusFilter")?.value || "",
    riskOnly: Boolean(document.querySelector("#riskOnly")?.checked),
    draftDataSource: document.querySelector("#draftDataSourceChoice")?.value || "",
  }));
}

function restoreWorkspaceState() {
  const saved = savedWorkspaceState || {};
  const isCurrentVersion = saved.version === WORKSPACE_STATE_VERSION;
  if (document.querySelector("#statusFilter") && saved.statusFilter !== undefined) {
    document.querySelector("#statusFilter").value = saved.statusFilter;
  }
  if (document.querySelector("#riskOnly")) {
    document.querySelector("#riskOnly").checked = Boolean(saved.riskOnly);
  }
  if (document.querySelector("#draftDataSourceChoice") && saved.draftDataSource !== undefined) {
    document.querySelector("#draftDataSourceChoice").value = saved.draftDataSource;
  }
  state.itemSource = saved.itemSource || state.itemSource || "workspace";
  setWorkspacePage(isCurrentVersion ? (saved.page || "daily") : "daily");
}

function pageShouldBeVisible(node, page) {
  if (node.id === "inboxMainGrid") return page === "messages" || page === "candidates";
  return node.dataset.page === page;
}

function setWorkspacePage(page) {
  state.activePage = page || "daily";
  document.body.dataset.activePage = state.activePage;
  document.querySelector("#appShell")?.setAttribute("data-active-page", state.activePage);
  document.querySelectorAll("#inboxV1Nav [data-page-target]").forEach((button) => {
    button.classList.toggle("active", button.dataset.pageTarget === state.activePage);
  });
  document.querySelectorAll(".workspace-page").forEach((node) => {
    node.classList.toggle("active-page", pageShouldBeVisible(node, state.activePage));
  });
  if (state.activePage === "candidates") setItemSource(state.itemSource || "workspace");
  if (state.activePage === "transfer") refreshExportTemplatePreview();
  if (state.activePage === "draft") refreshDraftReportPreview();
  if (state.activePage === "group-management" || state.activePage === "people") {
    ensureConfigCenterLoaded();
  }
  saveWorkspaceState();
}

document.querySelectorAll("#inboxV1Nav [data-page-target]").forEach((button) => {
  button.addEventListener("click", () => {
    const page = button.dataset.pageTarget;
    if (page === "config") {
      openConfigCenter();
      return;
    }
    if (page === "transfer") {
      openExportTemplateDialog("real_trial");
      return;
    }
    setWorkspacePage(page);
  });
});

restoreWorkspaceState();
if (state.activePage === "config") {
  openConfigCenter({ setPage: false });
} else {
  ensureConfigCenterLoaded();
}
applyTransferTask(state.transferTask, { skipPreview: true });
refreshStatus().then(loadItems).then(refreshDailyControl).then(refreshInboxV1);
refreshRealTrialSummary();
refreshRealTrialMessages();
