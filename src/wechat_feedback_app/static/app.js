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
  monitorGroupDetails: {},
  monitorGroupFieldOptions: {},
  customerOptions: null,
  customerSuggestion: null,
  customerSuggestionTimer: null,
  selectedMonitorGroupId: "",
  refreshingMonitorGroupId: "",
  syncingRosterGroupId: "",
  internalPeople: null,
  runtimeStatus: null,
  runtimeStatusError: "",
  windowsReadiness: null,
  windowsReadinessError: "",
  messageGroupFilter: "",
  messageGroupsV1: [],
  messagesV1Status: null,
  peopleAliases: [],
  editingPeopleIndex: null,
  editingPersonId: "",
  peopleSuggestionTimer: null,
  generatingDailyReport: false,
  dailyGenerationStatus: "",
  dailyGenerationFeedback: "",
  dailyCenter: null,
  dailyCenterError: "",
  activePage: "daily",
  transferTask: "internal_sync",
};

const WORKSPACE_STATE_VERSION = "20260520-readiness-messages-v1";
const MONITOR_GROUP_META_STORAGE = "wechat_daily_monitor_group_meta_v1";
const DAILY_SETTLEMENT_STORAGE = "wechat_daily_settlement_status_v1";
const FULL_ROSTER_SYNC_CONFIRM_TEXT = [
  "确认同步微信群全员名单？",
  "这会读取该微信群的成员名单元数据，不读取聊天消息。",
  "不会外发，不会写正式日报、待办、Obsidian 或外部系统。",
  "成功后只在本地页面用于成员选择。",
].join("\n");
const FULL_ROSTER_CREATE_CONFIRM_TEXT = [
  "保存后同步微信群全员名单？",
  "这会在新监控群保存成功后读取该微信群的成员名单元数据，不读取聊天消息。",
  "不会外发，不会写正式日报、待办、Obsidian 或外部系统。",
  "成功后只在本地页面用于成员选择；如果同步失败，群档案仍会保留。",
  "选择取消会只保存群档案，不同步全员名单。",
].join("\n");
const ARCHIVE_MONITOR_GROUP_CONFIRM_TEXT = [
  "确认归档这个监控群？",
  "归档只会把它移出日常监控和日报统计。",
  "不会删除真实微信群，不会外发，也不会写正式区。",
  "失败时会保留当前列表。",
].join("\n");
const DELETE_MONITOR_GROUP_CONFIRM_TEXT = [
  "确认删除这个监控群配置？",
  "删除只会移除本项目本地监控群配置。",
  "不会影响真实微信群、客户系统、正式日报、待办、Obsidian 或外部系统。",
  "失败时会保留当前列表。",
].join("\n");

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
  owner_names: [],
  daily_monitor: false,
  include_in_daily: false,
  verification_status: "待验证",
  trial_range: "recent50",
  internal_people: [],
  member_options: [],
  member_options_complete: false,
  sync_roster_on_create: true,
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

const peopleRoleOptions = ["我方负责人", "产品", "技术", "运营", "售后", "待确认角色"];
const peopleModuleOptions = ["订单", "售后", "登录", "电商设计", "渠道", "日报整理", "待确认模块"];
const peopleImpactText = "保存后会影响：试读消息、发送人识别、候选事项、群负责人下拉、日报、转述摘要。";

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
  await refreshWindowsReadiness();
  try {
    const data = await api("/api/status");
    state.runtimeStatus = data;
    state.runtimeStatusError = "";
    const run = data.latest_run || {};
    const trialState = data.real_trial || {};
    const readText = trialState.enabled ? "只读试读临时开启" : "只读试读保持关闭";
    const groupText = `监控群：${trialState.enabled_whitelist_count ?? 0} 个`;
    const latestText = `上次整理：${run.finished_at || "还未运行"}`;
    const isWindows = isWindowsRuntime();
    const environmentText = isWindows ? "Windows 正式挂机" : "Mac 开发测试";
    document.querySelector("#statusLine").textContent =
      `${environmentText}｜日报中心就绪｜${readText}｜${groupText}｜${latestText}｜不会自动外发或写正式区`;
    const environmentBanner = document.querySelector("#environmentStatusBanner");
    if (environmentBanner) {
      environmentBanner.classList.toggle("warning", !isWindows);
      environmentBanner.textContent = isWindows
        ? "当前按 Windows 正式挂机入口展示。请使用本机微信配置，Mac 测试配置不会自动混用；Slock Agent 本阶段仅保留只读状态卡方向。"
        : "当前识别为 Mac / 本地开发测试环境。请勿把这里的测试微信配置当作 Windows 正式挂机配置；正式挂机要在 Windows 本机单独配置；Slock Agent 本阶段仅保留只读状态卡方向。";
    }
  } catch (_error) {
    state.runtimeStatus = null;
    state.runtimeStatusError = "api_error";
    document.querySelector("#statusLine").textContent =
      "本地服务状态暂不可用｜请刷新页面或检查 8765 服务；不会自动读取微信或写正式区";
    const environmentBanner = document.querySelector("#environmentStatusBanner");
    if (environmentBanner) {
      environmentBanner.classList.add("warning");
      environmentBanner.textContent = "暂未读到本机运行状态。请确认当前打开的是 Windows 正式挂机服务，或在 Mac 开发测试环境中仅做配置验证。";
    }
  }
  renderWindowsReadiness();
}

async function refreshWindowsReadiness() {
  try {
    state.windowsReadiness = await api("/api/windows-readiness");
    state.windowsReadinessError = "";
  } catch (_error) {
    state.windowsReadiness = null;
    state.windowsReadinessError = "api_error";
  }
}

function isWindowsRuntime() {
  return /Win/i.test(`${navigator.platform || ""} ${navigator.userAgent || ""}`);
}

function firstMeaningfulValue(...values) {
  return values.find((value) => value !== undefined && value !== null && String(value).trim() !== "") || "";
}

function runtimeStatusTone(value) {
  const normalized = String(value || "").toLowerCase();
  if (!normalized) return "warn";
  if (["ok", "success", "ready", "enabled", "running", "connected"].includes(normalized)) return "ok";
  if (["failed", "error", "blocked", "api_error", "unavailable"].includes(normalized)) return "danger";
  return "warn";
}

function runtimeNextStep(value) {
  const normalized = String(value || "").toLowerCase();
  if (!normalized) return "请刷新状态；接口未返回本机连接摘要。";
  if (normalized.includes("config") || normalized.includes("missing") || normalized.includes("not_found")) {
    return "请补齐 Windows 本机微信配置后再试读。";
  }
  if (normalized.includes("old") || normalized.includes("stale")) {
    return "请重启本机服务后刷新页面。";
  }
  if (normalized.includes("failed") || normalized.includes("error") || normalized.includes("blocked") || normalized.includes("unavailable")) {
    return "请检查本机服务和微信连接；页面不会自动读取。";
  }
  return "真实读取默认关闭，需要人工确认后再试读。";
}

function runtimeConnectionSummary() {
  const readiness = state.windowsReadiness || {};
  if (state.windowsReadinessError) {
    return {
      value: "暂不可用",
      hint: "Windows readiness 接口暂不可用；请检查本机服务。",
      tone: "danger",
    };
  }
  const readinessStatus = firstMeaningfulValue(
    readiness.wechat_connection?.status,
    readiness.wx_cli?.connection_status,
    readiness.wx_cli?.status
  );
  if (readinessStatus) {
    return {
      value: readiness.wechat_connection?.label || readiness.wx_cli?.connection_label || humanStatusText(readinessStatus),
      hint: readiness.real_read_enabled
        ? "真实读取开关不应在 P0 默认开启，请先关闭后再验收。"
        : runtimeNextStep(readinessStatus),
      tone: readiness.real_read_enabled ? "danger" : runtimeStatusTone(readinessStatus),
    };
  }
  const data = state.runtimeStatus || {};
  if (state.runtimeStatusError) {
    return {
      value: "暂不可用",
      hint: "刷新页面或检查本机 8765 服务；不会自动读取微信。",
      tone: "danger",
    };
  }
  const rawStatus = firstMeaningfulValue(
    data.wx_cli_status,
    data.wechat_status,
    data.wx_status,
    data.runtime_status,
    data.wx_cli?.status,
    data.wechat?.status,
    data.daemon?.status,
    data.real_trial?.status
  );
  const label = rawStatus ? humanStatusText(rawStatus) : "待确认";
  return {
    value: label,
    hint: runtimeNextStep(rawStatus),
    tone: runtimeStatusTone(rawStatus),
  };
}

function configIsolationReadinessSummary() {
  const readiness = state.windowsReadiness || {};
  if (state.windowsReadinessError) {
    return {
      value: "待确认",
      hint: "未读到 /api/windows-readiness，不能只靠浏览器判断配置隔离。",
      tone: "danger",
    };
  }
  const configStatus = readiness.config_isolation_status || "";
  const pathStatus = readiness.path_isolation?.status || "";
  const realReadEnabled = readiness.real_read_enabled === true;
  if (!readiness.status) {
    return {
      value: "读取中",
      hint: "正在读取 Windows 配置隔离摘要。",
      tone: "warn",
    };
  }
  const ok = configStatus === "ok" && pathStatus === "ok" && !realReadEnabled;
  const parts = [
    `配置隔离：${humanStatusText(configStatus || "待确认")}`,
    `路径隔离：${humanStatusText(pathStatus || "待确认")}`,
    `真实读取：${realReadEnabled ? "开启" : "关闭"}`,
  ];
  return {
    value: ok ? "已隔离" : "需检查",
    hint: `${parts.join("｜")}。${readiness.ready_label || "请按 Windows readiness 摘要处理。"}`,
    tone: ok ? "ok" : "warn",
  };
}

function monitorGroupReadinessSummary() {
  const groups = state.monitorGroups || [];
  if (!groups.length) {
    return {
      value: "待配置",
      hint: "请先新增监控群；新增群默认待验证，不会静默纳入日报。",
      tone: "warn",
    };
  }
  const pendingVerify = groups.filter((group) =>
    group.enabled !== false && (group.verification_status || "待验证") === "待验证"
  ).length;
  const enabledCount = groups.filter((group) => group.enabled !== false).length;
  const includedCount = enabledDailyMonitorGroups().length;
  return {
    value: pendingVerify ? `待验证 ${pendingVerify} 个` : `纳入日报 ${includedCount} 个`,
    hint: `共 ${groups.length} 个｜启用 ${enabledCount} 个｜已有群保留手动成员同步`,
    tone: pendingVerify ? "warn" : "ok",
  };
}

function internalPeopleReadinessSummary() {
  const data = state.internalPeople;
  const apiPeople = data?.people || [];
  const configPeople = state.configCenter?.editable?.internal_people || [];
  const count = Number(data?.count ?? (apiPeople.length || configPeople.length || 0));
  if (data) {
    return {
      value: count ? `${count} 人` : "待配置",
      hint: count
        ? "已接入后端身份库；支持识别建议、保存、更新和停用。"
        : "请用识别向导保存我方人员，保存后会读回后端。",
      tone: count ? "ok" : "warn",
    };
  }
  if (configPeople.length) {
    return {
      value: `${configPeople.length} 人`,
      hint: "配置中心已有身份；进入我方人员页会读回后端接口。",
      tone: "warn",
    };
  }
  return {
    value: "待读取",
    hint: "正在连接 /api/internal-people；不可用时请稍后刷新。",
    tone: "warn",
  };
}

function dailyGenerationReadinessSummary() {
  const preview = state.dailyDraftPreview || {};
  const hasGenerated = Boolean(preview.generated_at || preview.local_preview_saved);
  if (state.generatingDailyReport || state.dailyGenerationStatus === "running") {
    return {
      value: "生成中",
      hint: state.dailyGenerationFeedback || "正在整理候选和日报正文，旧日报会保留。",
      tone: "warn",
    };
  }
  if (state.dailyGenerationStatus === "failed") {
    return {
      value: "生成失败",
      hint: state.dailyGenerationFeedback || "请检查本地服务；旧日报已保留。",
      tone: "danger",
    };
  }
  if (hasGenerated) {
    return {
      value: "已生成",
      hint: `候选 ${preview.candidate_count || 0}｜风险 ${preview.risk_count || 0}｜可复制或导出`,
      tone: "ok",
    };
  }
  return {
    value: "待生成",
    hint: "点击生成/刷新日报后会立即显示进度。",
    tone: "warn",
  };
}

function renderWindowsReadinessCard(card) {
  return `
    <article class="windows-readiness-card ${escapeAttr(card.tone || "warn")}">
      <span>${escapeHtml(card.label)}</span>
      <b>${escapeHtml(card.value)}</b>
      <small>${escapeHtml(card.hint || "")}</small>
    </article>
  `;
}

function renderWindowsReadiness() {
  const grid = document.querySelector("#windowsReadinessCards");
  if (!grid) return;
  const readiness = state.windowsReadiness || {};
  const runtimeEnvironment = readiness.runtime_environment || (isWindowsRuntime() ? "windows" : "mac_development");
  const isWindowsProfile = readiness.profile === "windows_formal" || runtimeEnvironment === "windows";
  const runtime = runtimeConnectionSummary();
  const configIsolation = configIsolationReadinessSummary();
  const monitorGroups = monitorGroupReadinessSummary();
  const people = internalPeopleReadinessSummary();
  const daily = dailyGenerationReadinessSummary();
  const cards = [
    {
      label: "运行环境",
      value: isWindowsProfile ? "Windows 正式挂机" : "Mac 开发测试",
      hint: readiness.title || (isWindowsProfile ? "按后端 Windows readiness 摘要展示。" : "正式挂机需在 Windows 本机配置。"),
      tone: isWindowsProfile ? "ok" : "warn",
    },
    { label: "配置隔离", ...configIsolation },
    { label: "微信连接", ...runtime },
    { label: "监控群", ...monitorGroups },
    { label: "我方人员", ...people },
    { label: "日报生成", ...daily },
  ];
  grid.innerHTML = cards.map(renderWindowsReadinessCard).join("");
  const line = document.querySelector("#windowsReadinessLine");
  if (!line) return;
  const nextSteps = [];
  if (!isWindowsProfile) nextSteps.push("在 Windows 本机完成正式挂机配置");
  if (configIsolation.tone !== "ok") nextSteps.push("检查配置隔离");
  if (runtime.tone !== "ok") nextSteps.push("确认微信连接状态");
  if (monitorGroups.tone !== "ok") nextSteps.push("验证监控群");
  if (people.tone !== "ok") nextSteps.push("补我方人员");
  if (daily.tone !== "ok") nextSteps.push("生成日报");
  line.textContent = nextSteps.length
    ? `下一步：${nextSteps.slice(0, 3).join("、")}。`
    : "P0 日常路径就绪：按群看消息、处理候选、生成并确认日报。";
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

function groupDisplayCandidates(source = {}) {
  return [
    source.group_label,
    source.display_label,
    source.readable_name,
    source.group_display_name,
    source.display_name,
    source.group_name,
    source.session_display_name,
    source.session_name,
    source.channel_name,
  ].map((value) => String(value || "").trim()).filter(Boolean);
}

function groupIdentifierCandidates(source = {}) {
  return [
    source.group_id,
    source.external_id,
    source.session_id,
    source.id,
    source.value,
  ].map((value) => String(value || "").trim()).filter(Boolean);
}

function internalGroupIdentifierLike(value) {
  const text = String(value || "").trim();
  if (!text) return false;
  return /@chatroom\b/i.test(text)
    || /^wxid[_-]/i.test(text)
    || /^local-monitor-\d+$/i.test(text);
}

function groupDisplayUnresolved(source = {}) {
  const statusValues = [
    source.display_name_status,
    source.group_name_status,
    source.group_label_status,
  ].map((value) => String(value || "").trim());
  const reasonValues = [
    source.display_name_reason_code,
    source.group_name_reason_code,
    source.group_label_reason_code,
    source.reason_code,
  ].map((value) => String(value || "").trim());
  return statusValues.includes("unresolved")
    || reasonValues.includes("internal_identifier_only");
}

function groupDisplayHasInternalCandidate(source = {}) {
  const identifiers = new Set(groupIdentifierCandidates(source));
  return groupDisplayCandidates(source).some((value) =>
    internalGroupIdentifierLike(value) || identifiers.has(value)
  );
}

function readableGroupDisplayLabel(source = {}, fallback = "群名待解析") {
  if (groupDisplayUnresolved(source)) return fallback;
  const identifiers = new Set(groupIdentifierCandidates(source));
  const readable = groupDisplayCandidates(source).find((value) =>
    !internalGroupIdentifierLike(value) && !identifiers.has(value)
  );
  if (readable) return readable;
  return fallback;
}

function monitorGroupTitle(group = {}) {
  if (!isSavedMonitorGroup(group) && !group.display_name && !group.group_name) {
    return "新监控群";
  }
  return readableGroupDisplayLabel(group, "群名待解析");
}

function monitorGroupEditableName(group = {}) {
  if (groupDisplayUnresolved(group) || groupDisplayHasInternalCandidate(group)) return "";
  const label = readableGroupDisplayLabel(group, "");
  return label === "群名待解析" ? "" : label;
}

function itemGroupContextLabel(item = {}, fallback = "当前候选") {
  if (groupDisplayUnresolved(item) || groupDisplayHasInternalCandidate(item)) {
    return "群名待解析";
  }
  return readableGroupDisplayLabel(item, "")
    || item.customer_name
    || item.channel_name
    || fallback;
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
	  needs_review: "需检查",
	  missing_binary: "未配置 wx-cli",
	  permission_denied: "权限待处理",
	  needs_connection_test: "待连接测试",
	  connected: "已连接",
	  unavailable: "不可用",
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
  await refreshDailyCenterProductState(controlDate);
  renderDailyControl(data);
}

async function refreshDailyCenterProductState(controlDate) {
  try {
    state.dailyCenter = await api(`/api/daily-center?control_date=${encodeURIComponent(controlDate)}`);
    state.dailyCenterError = "";
  } catch (_error) {
    state.dailyCenter = null;
    state.dailyCenterError = "daily_center_unavailable";
  }
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
  const summary = state.dailyCenter?.summary || {};
  const unfinishedFollowups = Number(top.pending_count || 0);
  const historicalUnfollowed = Number(summary.historical_unfollowed_count ?? top.historical_unfollowed_count ?? unfinishedFollowups);
  return {
    monitorGroups: Number(summary.monitor_group_count ?? enabledDailyMonitorGroups().length),
    newIssues: Number(summary.new_issue_count ?? top.candidate_count ?? 0),
    unfinishedFollowups,
    historicalUnfollowed,
    pendingFollowups: unfinishedFollowups,
  };
}

function dailyGenerationStatusLabel() {
  if (state.generatingDailyReport || state.dailyGenerationStatus === "running") return "生成中";
  if (state.dailyGenerationStatus === "failed") return "生成失败";
  if (state.dailyGenerationStatus === "success") return "已刷新";
  const status = state.dailyCenter?.report?.status_label || state.dailyCenter?.summary?.report_status_label || "";
  return status || "待生成";
}

function renderDailyWorkbenchQueue(counts, hasGenerated, settlementStatus, groupGap) {
  const container = document.querySelector("#dailyWorkbenchQueue");
  const status = document.querySelector("#dailyWorkbenchStatus");
  if (!container || !status) return;
  const generationStatus = dailyGenerationStatusLabel();
  const rows = [
    {
      label: "未完成跟进事项",
      value: `${counts.unfinishedFollowups} 条`,
      hint: counts.unfinishedFollowups ? "先处理候选收件箱里的待确认事项。" : "当前没有新的待确认事项。",
      page: "candidates",
      tone: counts.unfinishedFollowups ? "warn" : "ok",
    },
    {
      label: "历史未跟进",
      value: `${counts.historicalUnfollowed} 条`,
      hint: counts.historicalUnfollowed ? "优先收口跨日遗留，避免日报继续滚动堆积。" : "暂无历史遗留需要单独收口。",
      page: "candidates",
      tone: counts.historicalUnfollowed ? "warn" : "ok",
    },
    {
      label: "配置减负",
      value: groupGap ? `${groupGap} 项待补` : "已顺手",
      hint: groupGap ? "补齐监控群和我方人员配置，后续日报会少填字段。" : "监控群和身份配置暂无明显缺口。",
      page: groupGap ? "group-management" : "people",
      tone: groupGap ? "warn" : "ok",
    },
    {
      label: "日报生成反馈",
      value: generationStatus,
      hint: hasGenerated ? `全文已可见，沉淀状态：${settlementStatus}。` : "点击生成后会立即显示进度，旧日报保留到新版完成。",
      page: "daily",
      tone: hasGenerated ? "ok" : "warn",
    },
  ];
  status.textContent = rows.some((row) => row.tone === "warn") ? "需处理" : "顺畅";
  container.innerHTML = rows.map((row) => `
    <article class="workbench-row ${escapeAttr(row.tone)}">
      <div>
        <strong>${escapeHtml(row.label)}</strong>
        <small>${escapeHtml(row.hint)}</small>
      </div>
      <div class="workbench-row-action">
        <b>${escapeHtml(row.value)}</b>
        <button type="button" data-jump-page="${escapeAttr(row.page)}">${row.page === "daily" ? "查看" : "去处理"}</button>
      </div>
    </article>
  `).join("");
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
    ? `日报已生成，未完成跟进 ${counts.unfinishedFollowups} 条，历史未跟进 ${counts.historicalUnfollowed} 条。`
    : "日报还未生成。下一步：先生成/刷新日报，再确认是否沉淀。";
  const groupGap = Math.max(0, (state.monitorGroups || []).length - counts.monitorGroups);
  const priorityTitle = counts.unfinishedFollowups
    ? `先收口 ${counts.unfinishedFollowups} 条未完成跟进`
    : counts.newIssues
      ? `先处理 ${counts.newIssues} 条新发现`
      : counts.historicalUnfollowed
        ? `回看 ${counts.historicalUnfollowed} 条历史未跟进`
        : hasGenerated
          ? "今天先确认日报沉淀"
          : "先生成今天日报";
  const priorityParts = [
    counts.newIssues ? `候选 ${counts.newIssues} 条` : "暂无新候选",
    counts.unfinishedFollowups ? `未完成 ${counts.unfinishedFollowups} 条` : "未完成跟进清零",
    counts.historicalUnfollowed ? `历史未跟进 ${counts.historicalUnfollowed} 条` : "历史未跟进清零",
    counts.monitorGroups ? `日报监控群 ${counts.monitorGroups} 个` : "还没有已纳入日报的监控群",
    groupGap ? `有 ${groupGap} 个监控群配置待确认` : "监控群配置暂无明显缺口",
  ];
  document.querySelector("#todayPriorityTitle").textContent = priorityTitle;
  document.querySelector("#todayPriorityLine").textContent =
    `${priorityParts.join("｜")}。日常路径：先按群看消息，再处理候选，最后生成并确认日报。`;
  document.querySelector("#dailyCenterCards").innerHTML = [
    ["日报状态", hasGenerated ? "已生成" : "未生成", hasGenerated ? "可直接查看全文" : "点击右上生成"],
    ["沉淀状态", settlementStatus, settlementStatus === "已确认沉淀" ? "已人工确认" : "全文底部可确认"],
    ["监控群数", counts.monitorGroups, "启用监控并纳入日报"],
    ["新发现问题", counts.newIssues, "今天候选事项"],
    ["历史未跟进", counts.historicalUnfollowed, "仍需人工收口"],
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
  const reportMetaLine = document.querySelector("#dailyReportMetaLine");
  reportMetaLine.textContent = state.generatingDailyReport || state.dailyGenerationStatus === "running"
    ? state.dailyGenerationFeedback || "生成中：正在整理日报，旧日报会保留到新版完成。"
    : hasGenerated
      ? `生成时间：${preview.generated_at || "刚刚生成"}｜候选：${preview.candidate_count || 0}｜风险：${preview.risk_count || 0}｜来源：${humanDataSourceLabel(preview.data_source_label)}`
      : `状态：未生成｜候选：${top.candidate_count || 0}｜下一步：生成/刷新日报`;
  document.querySelector("#confirmDailySettlementBtn").disabled = !(hasGenerated && hasReportText);
  document.querySelector("#markDailyReviewBtn").disabled = !(hasGenerated && hasReportText);
  renderDailyWorkbenchQueue(counts, hasGenerated, settlementStatus, groupGap);
  renderWindowsReadiness();
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
    const pending = isCurrent ? counts.historicalUnfollowed : "-";
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
  const initialGroup = state.messageGroupFilter || "";
  let data = await loadMessagesV1(initialGroup || "all");
  if (!initialGroup) {
    const firstSingleGroup = (data.groups || []).find((group) => group.group_id && group.group_id !== "all");
    if (firstSingleGroup) {
      state.messageGroupFilter = firstSingleGroup.group_id;
      data = await loadMessagesV1(firstSingleGroup.group_id);
    }
  }
  state.realTrialMessages = data.messages || [];
  state.realTrialSenders = sendersFromMessagesV1(data.messages || []);
  renderRealTrialMessages(data);
  renderSenderReview(state.realTrialSenders);
  renderPeopleRecentSenderOptions();
}

async function loadMessagesV1(groupId = "all") {
  const query = new URLSearchParams();
  if (groupId && groupId !== "all") query.set("group_id", groupId);
  const data = await api(`/api/messages/v1${query.toString() ? `?${query.toString()}` : ""}`);
  state.messagesV1Status = {
    status: data.status || "ok",
    selected_group_id: data.selected_group_id || groupId || "all",
    count: data.count || 0,
    safety: data.safety || {},
  };
  state.messageGroupsV1 = data.groups || [];
  return data;
}

function messageGroupLabel(message) {
  if (groupDisplayUnresolved(message) || groupDisplayHasInternalCandidate(message)) {
    return "群名待解析";
  }
  return readableGroupDisplayLabel(message, "")
    || message?.customer_label
    || message?.customer_name
    || "";
}

function messageGroupId(message) {
  return message?.group_id || messageGroupLabel(message) || "";
}

function messageReadablePreview(message = {}) {
  const candidates = [
    message.content_text,
    message.content_preview,
    message.message_text,
    message.message_preview,
    message.text_preview,
    message.preview,
    message.summary,
  ];
  const text = candidates.map((value) => String(value || "").trim()).find(Boolean);
  return text || "";
}

function messagePreviewLine(message = {}) {
  const text = messageReadablePreview(message);
  if (text) return `正文预览：${text}`;
  const status = message.content_status || message.preview_status || message.message_status || "";
  if (status === "not_collected" || status === "empty" || status === "hidden_for_safety") {
    return "正文预览：未抓到正文；请确认本机已授权真实读取并完成入库。";
  }
  return "正文预览：未抓到正文；不会用消息编号冒充摘要。";
}

function messageGroupOptions() {
  if ((state.messageGroupsV1 || []).length) {
    return state.messageGroupsV1.map((group) => ({
      value: group.group_id || group.group_name || "",
      label: readableGroupDisplayLabel(group, "群名待解析"),
      count: group.message_count,
    })).filter((group) => group.value);
  }
  const options = new Map();
  (state.monitorGroups || []).forEach((group) => {
    const value = group.group_id || groupIdentity(group);
    const label = monitorGroupTitle(group);
    if (value && label) options.set(value, { value, label, count: group.message_count });
  });
  return Array.from(options.values());
}

function sendersFromMessagesV1(messages = []) {
  const senders = new Map();
  messages.forEach((message) => {
    const name = message.sender_display_name || "";
    if (!name) return;
    const existing = senders.get(name) || {
      sender_display_name: name,
      sender_identity: message.sender_identity || "unknown",
      sender_resolution: "来自消息明细",
      message_count: 0,
    };
    existing.message_count += 1;
    senders.set(name, existing);
  });
  return Array.from(senders.values());
}

function renderMessageGroupFilter() {
  const select = document.querySelector("#messageGroupFilter");
  if (!select) return { selected: "all", options: [] };
  const groups = messageGroupOptions();
  if (!state.messageGroupFilter) {
    state.messageGroupFilter = groups.find((group) => group.value !== "all")?.value || "all";
  }
  if (!groups.some((group) => group.value === state.messageGroupFilter)) {
    state.messageGroupFilter = groups.find((group) => group.value !== "all")?.value || "all";
  }
  const normalizedGroups = groups.some((group) => group.value === "all")
    ? groups
    : [{ value: "all", label: "全部群（排查用）", count: undefined }, ...groups];
  select.innerHTML = normalizedGroups.map((group) => {
    const countText = group.count === undefined || group.count === null ? "" : `（${group.count}）`;
    return `<option value="${escapeAttr(group.value)}" ${state.messageGroupFilter === group.value ? "selected" : ""}>${escapeHtml(group.label)}${escapeHtml(countText)}</option>`;
  }
  ).join("");
  return { selected: state.messageGroupFilter, options: normalizedGroups };
}

function renderRealTrialMessages(data) {
  const container = document.querySelector("#realTrialMessages");
  if (!data || data.status === "not_found") {
    state.messageGroupsV1 = data?.groups || state.messageGroupsV1 || [];
    container.innerHTML = '<div class="empty">未找到消息明细。请先在群管理配置监控群，或稍后刷新。</div>';
    renderMessageGroupFilter();
    return;
  }
  const messages = data.messages || [];
  state.messageGroupsV1 = data.groups || state.messageGroupsV1 || [];
  if (data.selected_group_id) state.messageGroupFilter = data.selected_group_id;
  const groupState = renderMessageGroupFilter();
  const visibleMessages = messages;
  const status = document.querySelector("#messageGroupFilterStatus");
  if (status) {
    const safety = data.safety || {};
    const safetyText = safety.content_returned === false && safety.raw_payload_returned === false
      ? "未返回正文 / 原始 payload"
      : "请检查消息安全摘要";
    status.textContent = groupState.options.length
      ? `当前视图：${groupState.selected === "all" ? "全部群排查" : "单群主流程"}｜消息 ${visibleMessages.length} 条｜${safetyText}`
      : "暂无可选监控群；请先到群管理配置监控群。";
  }
  if (!visibleMessages.length && groupState.selected !== "all") {
    container.innerHTML = '<div class="empty">当前群暂无消息；已保持单群视图，没有回退显示全部群。可以切到“全部群”排查，或先刷新消息明细。</div>';
    return;
  }
  if (!visibleMessages.length) {
    container.innerHTML = '<div class="empty">暂无可审阅消息。请先选择监控群，或到群管理确认群配置。</div>';
    return;
  }
  container.innerHTML = visibleMessages.map((message) => `
    <article class="message-row">
      <strong>${escapeHtml(message.sent_at || "")}｜${escapeHtml(messageGroupLabel(message) || "未标注群")}｜${escapeHtml(message.sender_display_name || "发送人已脱敏")}｜${escapeHtml(message.sender_identity_label || identityLabel(message.sender_identity))}</strong>
      <span>${escapeHtml(messagePreviewLine(message))}｜候选关联 ${escapeHtml(message.candidate_count ?? 0)} 条</span>
      <small>客户：${escapeHtml(message.customer_label || "未标客户")}｜模块：${escapeHtml(message.module_label || "未标模块")}｜详情定位：${escapeHtml(message.detail_target?.message_ref || message.message_ref || "无")}</small>
    </article>
  `).join("");
}

function updateMessageDetailGroupStatus(groupLabel) {
  const status = document.querySelector("#messageGroupFilterStatus");
  if (!status || !groupLabel) return;
  status.textContent = `当前详情所属群：${groupLabel}｜右侧详情会跟随当前候选 / 消息。`;
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
  updateMessageDetailGroupStatus(itemGroupContextLabel(item, "当前候选"));
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
  updateMessageDetailGroupStatus(itemGroupContextLabel(item, "最近试读监控群"));
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
document.querySelector("#dailyFocusPanel").addEventListener("click", (event) => {
  const button = event.target.closest("[data-jump-page]");
  if (!button) return;
  setWorkspacePage(button.dataset.jumpPage);
});
document.querySelector("#dailyWorkbenchQueue").addEventListener("click", (event) => {
  const button = event.target.closest("[data-jump-page]");
  if (!button) return;
  setWorkspacePage(button.dataset.jumpPage);
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
document.querySelector("#groupManagementPage").addEventListener("change", (event) => {
  if (event.target.matches("[data-member-role]")) {
    persistCurrentMemberRolesFromDom();
    renderAllMemberChips();
  }
  if (event.target.matches("#monitorGroupCustomer")) {
    const group = state.monitorGroups.find((item) => groupIdentity(item) === state.selectedMonitorGroupId);
    const selectedCustomer = selectedCustomerFromSelect();
    state.customerSuggestion = null;
    setCustomerSuggestionAction(null);
    if (group) {
      group.customer_id = selectedCustomer.customer_id;
      group.customer_name = selectedCustomer.customer_name;
      group.customer_label = selectedCustomer.customer_name;
      renderMonitoringGroups();
    }
    setCustomerHint(selectedCustomer.customer_name ? "已选择客户；保存后会写入群档案并读回确认。" : "未识别客户，请选择客户或先补客户配置。", selectedCustomer.customer_name ? "ok" : "warning");
  }
  if (event.target.matches("#monitorGroupSyncRosterOnCreate")) {
    const group = state.monitorGroups.find((item) => groupIdentity(item) === state.selectedMonitorGroupId);
    if (group) group.sync_roster_on_create = event.target.checked;
  }
});
document.querySelector("#groupManagementPage").addEventListener("click", (event) => {
  const suggestionButton = event.target.closest("#acceptCustomerSuggestionBtn");
  if (suggestionButton) {
    acceptCustomerSuggestion();
    return;
  }
  const button = event.target.closest("[data-remove-member]");
  if (!button) return;
  document.querySelectorAll(`[data-member-name="${cssEscape(button.dataset.removeMember)}"]`).forEach((input) => {
    input.checked = false;
  });
  const group = state.monitorGroups.find((item) => groupIdentity(item) === state.selectedMonitorGroupId);
  if (group) {
    group.owner_names = (group.owner_names || []).filter((name) => name !== button.dataset.removeMember);
    group.owner_name = group.owner_names[0] || "";
    group.common_contacts = (group.common_contacts || []).filter((name) => name !== button.dataset.removeMember);
    group.internal_people = (group.internal_people || []).filter((name) => name !== button.dataset.removeMember);
  }
  persistCurrentMemberRolesFromDom();
  renderCurrentMemberPool();
  renderAllMemberChips();
});
document.querySelector("#monitorGroupMemberSearch").addEventListener("input", renderCurrentMemberPool);
document.querySelector("#monitorGroupDisplayName").addEventListener("input", (event) => {
  const group = state.monitorGroups.find((item) => groupIdentity(item) === state.selectedMonitorGroupId);
  if (group) {
    group.display_name = event.target.value.trim();
    renderDailyReportCenter();
  }
  scheduleCustomerSuggestion();
});
document.querySelector("#saveMonitorGroupBtn").addEventListener("click", saveSelectedMonitorGroup);
document.querySelector("#disableMonitorGroupBtn").addEventListener("click", disableSelectedMonitorGroup);
document.querySelector("#archiveMonitorGroupBtn").addEventListener("click", archiveSelectedMonitorGroup);
document.querySelector("#deleteMonitorGroupBtn").addEventListener("click", deleteSelectedMonitorGroup);
document.querySelector("#refreshMonitorGroupMembersBtn").addEventListener("click", refreshSelectedMonitorGroupMembers);
document.querySelector("#syncMonitorGroupRosterBtn").addEventListener("click", syncSelectedMonitorGroupRoster);
document.querySelector("#addPeoplePagePersonBtn").addEventListener("click", async () => {
  await ensureConfigCenterLoaded();
  resetPeopleForm();
});
document.querySelector("#savePeoplePageBtn").addEventListener("click", savePeoplePage);
document.querySelector("#peopleMatchByWxidBtn").addEventListener("click", () => matchPeopleFromInput("wxid"));
document.querySelector("#peopleMatchByNameBtn").addEventListener("click", () => matchPeopleFromInput("display_name"));
document.querySelector("#peopleLookupWxid").addEventListener("input", () => schedulePeopleSuggestion("wxid"));
document.querySelector("#peopleLookupDisplayName").addEventListener("input", () => schedulePeopleSuggestion("display_name"));
document.querySelector("#peopleUseRecentSenderBtn").addEventListener("click", useRecentSenderForPeople);
document.querySelector("#peopleAddAliasBtn").addEventListener("click", () => {
  addPeopleAliases(splitAliasInput(document.querySelector("#peopleAliasPasteInput").value));
  document.querySelector("#peopleAliasPasteInput").value = "";
});
document.querySelector("#peopleAliasPasteInput").addEventListener("keydown", (event) => {
  if (event.key !== "Enter") return;
  event.preventDefault();
  document.querySelector("#peopleAddAliasBtn").click();
});
document.querySelector("#peopleAliasChips").addEventListener("click", (event) => {
  const button = event.target.closest("[data-remove-people-alias]");
  if (!button) return;
  state.peopleAliases = state.peopleAliases.filter((alias) => alias !== button.dataset.removePeopleAlias);
  renderPeopleAliasChips();
});
document.querySelector("#peoplePageRows").addEventListener("click", (event) => {
  const button = event.target.closest("[data-edit-people-index]");
  if (button) {
    editPeopleFromList(Number(button.dataset.editPeopleIndex));
    return;
  }
  const disableButton = event.target.closest("[data-disable-person-id]");
  if (disableButton) {
    disablePeopleFromList(disableButton.dataset.disablePersonId);
  }
});
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
document.querySelector("#messageGroupFilter").addEventListener("change", (event) => {
  state.messageGroupFilter = event.target.value;
  refreshRealTrialMessages();
});
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
    meta[groupIdentity(group)] = {
      daily_monitor: Boolean(group.daily_monitor),
      include_in_daily: Boolean(group.include_in_daily),
      verification_status: group.verification_status || "待验证",
      trial_range: group.trial_range || "recent50",
      owner_names: group.owner_names || [],
      internal_people: group.internal_people || [],
      customer_id: group.customer_id || "",
      customer_name: group.customer_name || "",
      archived: Boolean(group.archived),
    };
  });
  localStorage.setItem(MONITOR_GROUP_META_STORAGE, JSON.stringify(meta));
}

function groupIdentity(group) {
  return group?.group_id || group?.external_id || "";
}

function normalizeMonitorGroup(session, meta = {}) {
  return {
    group_id: session.group_id || "",
    external_id: session.external_id || makeMonitorGroupId(),
    group_name: session.group_name || session.display_name || "",
    group_label: session.group_label || "",
    display_name: session.display_name || session.group_name || "",
    display_name_status: session.display_name_status || session.group_name_status || "",
    display_name_reason_code: session.display_name_reason_code || session.group_name_reason_code || "",
    group_name_status: session.group_name_status || session.display_name_status || "",
    group_name_reason_code: session.group_name_reason_code || session.display_name_reason_code || "",
    group_label_status: session.group_label_status || "",
    group_label_reason_code: session.group_label_reason_code || "",
    customer_id: session.customer_id || session.customer_key || "",
    customer_name: session.customer_name || "",
    customer_label: session.customer_label || session.customer_name || "",
    channel_name: session.channel_name || "",
    module_name: session.module_name || "",
    owner_name: session.owner_name || "",
    owner_label: session.owner_label || session.owner_name || "",
    customer_stage: session.customer_stage || "",
    group_type: session.group_type || "",
    common_contacts: session.common_contacts || [],
    reply_notes: session.reply_notes || "",
    is_whitelisted: session.is_whitelisted !== false,
    enabled: session.enabled !== false,
    archived: Boolean(meta.archived ?? session.archived),
    owner_names: meta.owner_names || session.owner_names || [session.owner_name].filter(Boolean),
    daily_monitor: meta.daily_monitor ?? session.daily_monitor ?? session.daily_monitor_enabled ?? (session.enabled !== false && session.is_whitelisted !== false),
    include_in_daily: meta.include_in_daily ?? session.include_in_daily ?? (session.enabled !== false && session.is_whitelisted !== false),
    verification_status: meta.verification_status || humanVerificationStatus(session.verification_status) || "已验证",
    trial_range: meta.trial_range || session.trial_scope || "recent50",
    internal_people: meta.internal_people || [],
    member_options: session.member_options || emptyMemberOptions(),
    member_detail_loaded: Boolean(session.member_options),
  };
}

function makeMonitorGroupId() {
  return `local-monitor-${Date.now()}`;
}

function humanVerificationStatus(value) {
  return {
    pending_verification: "待验证",
    verified: "已验证",
    "待验证": "待验证",
    "已验证": "已验证",
  }[value] || "";
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

function normalizeMonitorGroupApi(group, detailPayload = {}) {
  const id = group.group_id || group.external_id || "";
  const meta = monitorGroupMeta()[id] || {};
  const memberOptions = detailPayload.member_options || group.member_options || emptyMemberOptions();
  return {
    group_id: id,
    external_id: group.external_id || id || makeMonitorGroupId(),
    group_name: group.group_name || group.display_name || "",
    group_label: group.group_label || "",
    display_name: group.display_name || group.group_name || "",
    display_name_status: group.display_name_status || group.group_name_status || "",
    display_name_reason_code: group.display_name_reason_code || group.group_name_reason_code || "",
    group_name_status: group.group_name_status || group.display_name_status || "",
    group_name_reason_code: group.group_name_reason_code || group.display_name_reason_code || "",
    group_label_status: group.group_label_status || "",
    group_label_reason_code: group.group_label_reason_code || "",
    customer_id: group.customer_id || group.customer_key || "",
    customer_name: group.customer_name || "",
    customer_label: group.customer_label || group.customer_name || "",
    channel_name: group.channel_name || "",
    module_name: group.module_name || "",
    owner_name: group.owner_name || "",
    owner_label: group.owner_label || group.owner_name || "",
    customer_stage: group.customer_stage || "",
    group_type: group.group_type || "",
    common_contacts: group.common_contacts || [],
    reply_notes: group.reply_notes || "",
    enabled: group.enabled !== false,
    archived: Boolean(meta.archived ?? group.archived),
    owner_names: meta.owner_names || group.owner_names || [group.owner_name].filter(Boolean),
    daily_monitor: meta.daily_monitor ?? group.daily_monitor_enabled ?? group.daily_monitor ?? false,
    include_in_daily: meta.include_in_daily ?? group.include_in_daily ?? false,
    verification_status: meta.verification_status || humanVerificationStatus(group.verification_status) || "待验证",
    trial_range: meta.trial_range || group.trial_scope || "最近50条",
    internal_people: meta.internal_people || group.internal_people || [],
    member_options: memberOptions,
    member_detail_loaded: Boolean(detailPayload.member_options || group.member_options),
    counts_in_daily_center: Boolean(group.counts_in_daily_center),
  };
}

function emptyMemberOptions() {
  return {
    scope: "appeared_members",
    complete: false,
    status_label: "暂无本地已出现成员；可先完成试读后再选择。",
    source_label: "本地已出现成员",
    count: 0,
    available_count: 0,
    roster_count: 0,
    names: [],
    items: [],
    refresh_available: true,
    refresh_label: "刷新本地已出现成员",
    refresh_status: "empty_local_sources",
    full_sync_available: false,
    full_sync_status_label: "完整成员名单需要同步授权或后端能力支持。",
    sync_action_label: "同步微信群全员名单",
  };
}

async function ensureMonitorGroupsLoaded({ force = false } = {}) {
  if (!force && state.monitorGroups.length) {
    renderMonitoringGroups();
    return;
  }
  const data = await api("/api/monitor-groups");
  state.monitorGroupFieldOptions = data.field_options || state.monitorGroupFieldOptions || {};
  updateCustomerOptionsFromPayload(data);
  const groups = (data.groups || []).map((group) => normalizeMonitorGroupApi(group));
  if (!groups.some((group) => group.display_name === monitorGroupSeed.display_name)) {
    groups.push({ ...monitorGroupSeed });
  }
  state.monitorGroups = groups;
  if (!state.selectedMonitorGroupId || !state.monitorGroups.some((group) => groupIdentity(group) === state.selectedMonitorGroupId)) {
    state.selectedMonitorGroupId = groupIdentity(state.monitorGroups[0]) || "";
  }
  renderMonitoringGroups();
}

async function loadSelectedMonitorGroupDetail(groupId) {
  if (!groupId || groupId.startsWith("local-")) return;
  const data = await api(`/api/monitor-groups/${encodeURIComponent(groupId)}`);
  if (data.status !== "ok" || !data.group) return;
  state.monitorGroupFieldOptions = data.field_options || state.monitorGroupFieldOptions || {};
  updateCustomerOptionsFromPayload(data);
  const detail = normalizeMonitorGroupApi(data.group, data);
  state.monitorGroupDetails[groupId] = detail;
  const index = state.monitorGroups.findIndex((group) => groupIdentity(group) === groupId);
  if (index >= 0) state.monitorGroups[index] = detail;
  if (state.selectedMonitorGroupId === groupId) {
    renderMonitoringGroups();
  }
}

function optionValuesFromGroups(field) {
  const values = new Set(
    (state.monitorGroups || [])
      .map((group) => group[field])
      .filter(Boolean)
  );
  return Array.from(values);
}

function normalizeFieldOption(option) {
  if (Array.isArray(option)) return String(option[1] || option[0] || "").trim();
  if (typeof option === "object" && option) {
    return String(option.label || option.name || option.value || option.title || "").trim();
  }
  return String(option || "").trim();
}

function fieldOptionValues(keys, fallback = [], groupField = "") {
  const values = new Set();
  const fieldOptions = state.monitorGroupFieldOptions || {};
  keys.forEach((key) => {
    const raw = fieldOptions[key];
    if (!Array.isArray(raw)) return;
    raw.map(normalizeFieldOption).filter(Boolean).forEach((value) => values.add(value));
  });
  fallback.map(normalizeFieldOption).filter(Boolean).forEach((value) => values.add(value));
  if (groupField) optionValuesFromGroups(groupField).forEach((value) => values.add(value));
  return Array.from(values);
}

function renderMonitorGroupOptionStatus(group) {
  const node = document.querySelector("#monitorGroupOptionStatus");
  if (!node) return;
  const customerCount = Number(state.customerOptions?.count || state.customerOptions?.options?.length || 0);
  const groupTypeCount = fieldOptionValues(["group_types", "group_type_options"], monitorGroupOptions.groupTypes, "group_type").length;
  const moduleCount = fieldOptionValues(["modules", "module_options"], monitorGroupOptions.modules, "module_name").length;
  const stageCount = fieldOptionValues(["customer_stages", "customer_stage_options"], monitorGroupOptions.stages, "customer_stage").length;
  const selectedRoles = [
    group?.owner_names?.length ? `负责人 ${group.owner_names.length} 人` : "",
    group?.common_contacts?.length ? `联系人 ${group.common_contacts.length} 人` : "",
    group?.internal_people?.length ? `我方人员 ${group.internal_people.length} 人` : "",
  ].filter(Boolean).join("｜") || "尚未分配成员角色";
  node.innerHTML = `
    <strong>配置减负</strong>
    <span>客户选项 ${escapeHtml(customerCount)} 项｜群类型 ${escapeHtml(groupTypeCount)} 项｜业务模块 ${escapeHtml(moduleCount)} 项｜客户阶段 ${escapeHtml(stageCount)} 项</span>
    <small>字段优先使用后端选项 / 建议；负责人、联系人和我方人员从统一成员池分配。${escapeHtml(selectedRoles)}</small>
  `;
}

function normalizeCustomerOption(option) {
  if (!option) return null;
  if (typeof option === "string") {
    const text = option.trim();
    return text ? { customer_id: "", customer_name: text, label: text, source: "backend_text" } : null;
  }
  const customerName = String(
    option.customer_name
    || option.suggested_customer_name
    || option.name
    || option.display_name
    || option.label
    || option.value
    || ""
  ).trim();
  const customerId = String(option.customer_id || option.suggested_customer_id || option.id || option.key || option.value || "").trim();
  const label = String(option.label || option.customer_label || customerName || customerId || "").trim();
  if (!customerName && !customerId) return null;
  return {
    customer_id: customerId,
    customer_name: customerName || label || customerId,
    label: label || customerName || customerId,
    source: option.source || option.source_label || "",
  };
}

function normalizeCustomerOptions(options = []) {
  const seen = new Set();
  const normalized = [];
  (Array.isArray(options) ? options : []).forEach((option) => {
    const item = normalizeCustomerOption(option);
    if (!item) return;
    const key = item.customer_id || item.customer_name;
    if (!key || seen.has(key)) return;
    seen.add(key);
    normalized.push(item);
  });
  return normalized;
}

function extractCustomerOptions(payload = {}) {
  return normalizeCustomerOptions(
    payload.customer_options
    || payload.customer_name_options
    || payload.customers
    || payload.options
    || payload.items
    || payload.editable?.customer_options
    || payload.editable?.customers
    || payload.editable?.customer_names
    || payload.field_options?.customer_options
    || payload.field_options?.customers
    || payload.field_options?.customer_names
    || []
  );
}

function firstText(...values) {
  for (const value of values) {
    const text = String(value || "").trim();
    if (text) return text;
  }
  return "";
}

function customerSourceMetaFromPayload(payload = {}, optionCount = 0) {
  const editable = payload.editable || {};
  const fieldOptions = payload.field_options || {};
  const sourceStatus = firstText(
    payload.customer_options_source_status,
    payload.customer_source_status,
    payload.source_status,
    editable.customer_options_source_status,
    editable.customer_source_status,
    editable.source_status,
    fieldOptions.customer_options_source_status,
    fieldOptions.customer_source_status,
    fieldOptions.source_status
  );
  const sourceLabel = firstText(
    payload.customer_options_source_label,
    payload.customer_source_label,
    payload.source_label,
    editable.customer_options_source_label,
    editable.customer_source_label,
    editable.source_label,
    fieldOptions.customer_options_source_label,
    fieldOptions.customer_source_label,
    fieldOptions.source_label,
    optionCount ? "本地配置客户" : ""
  );
  const sourceMessage = firstText(
    payload.customer_options_source_message,
    payload.customer_source_message,
    payload.source_message,
    payload.customer_options_message,
    payload.message,
    editable.customer_options_source_message,
    editable.customer_source_message,
    editable.source_message,
    fieldOptions.customer_options_source_message,
    fieldOptions.customer_source_message,
    fieldOptions.source_message
  );
  return { sourceStatus, sourceLabel, sourceMessage };
}

function customerSourceLabelFromOptions(options = []) {
  const labels = Array.from(new Set(
    (options || [])
      .map((option) => option.source)
      .filter(Boolean)
  ));
  if (labels.length > 1) return labels.join(" / ");
  return labels[0] || "";
}

function customerSourceLooksUnavailable(meta = {}) {
  return /unavailable|not_available|not_connected|not_configured|unconfigured|unreachable|disabled|error|failed|blocked|unreadable|empty|不可用|未接通|不可读|未配置|失败|错误/.test(
    `${meta.status || ""} ${meta.sourceStatus || ""} ${meta.message || ""} ${meta.sourceMessage || ""}`
  );
}

function customerSourceSummary(meta = state.customerOptions || {}) {
  const count = Number(meta.count || 0);
  const sourceLabel = meta.sourceLabel || "客户系统源";
  const optionWord = count ? `客户选项 ${count} 项` : "客户选项不足";
  if (!count || customerSourceLooksUnavailable(meta)) {
    const sourceText = meta.sourceStatus
      ? `${sourceLabel}状态：${meta.sourceStatus}`
      : `${sourceLabel}状态未确认`;
    return `${sourceText}｜${optionWord}。如客户系统源未接通 / 不可读，请先补客户配置或稍后刷新。`;
  }
  return `客户来源：${sourceLabel}｜${optionWord}。`;
}

function setCustomerSourceStatus(message, tone = "") {
  const node = document.querySelector("#monitorGroupCustomerSourceStatus");
  if (!node) return;
  node.textContent = message;
  node.dataset.tone = tone;
}

function updateCustomerOptionsFromPayload(payload = {}) {
  const options = extractCustomerOptions(payload);
  const sourceMeta = customerSourceMetaFromPayload(payload, options.length);
  sourceMeta.sourceLabel = sourceMeta.sourceLabel || customerSourceLabelFromOptions(options);
  const hasCustomerContract = [
    "customer_options",
    "customer_name_options",
    "customer_options_status",
    "customer_options_count",
    "customer_options_message",
    "customer_options_source_status",
    "customer_options_source_label",
    "customer_source_status",
    "customer_source_label",
    "source_status",
    "source_label",
  ].some((key) => Object.prototype.hasOwnProperty.call(payload, key))
    || Boolean(sourceMeta.sourceStatus || sourceMeta.sourceLabel || sourceMeta.sourceMessage)
    || Boolean(
      payload.editable?.customer_options
      || payload.editable?.customers
      || payload.editable?.customer_names
      || payload.field_options?.customer_options
      || payload.field_options?.customers
      || payload.field_options?.customer_names
    );
  if (options.length || hasCustomerContract) {
    state.customerOptions = {
      status: payload.customer_options_status || payload.status || (options.length ? "ok" : "empty"),
      count: Number(payload.customer_options_count ?? payload.count ?? options.length) || options.length,
      options,
      message: payload.customer_options_message || payload.message || "",
      sourceStatus: sourceMeta.sourceStatus,
      sourceLabel: sourceMeta.sourceLabel,
      sourceMessage: sourceMeta.sourceMessage,
    };
  }
}

async function loadCustomerOptions({ force = false } = {}) {
  if (state.customerOptions && !force) return state.customerOptions;
  const endpoints = [
    "/api/customer-options",
    "/api/customers/options",
    "/api/monitor-groups/customer-options",
  ];
  for (const endpoint of endpoints) {
    try {
      const data = await api(endpoint);
      const options = extractCustomerOptions(data);
      const sourceMeta = customerSourceMetaFromPayload(data, options.length);
      sourceMeta.sourceLabel = sourceMeta.sourceLabel || customerSourceLabelFromOptions(options);
      state.customerOptions = {
        status: data.status || (options.length ? "ok" : "empty"),
        count: Number(data.count ?? data.customer_options_count ?? options.length) || options.length,
        options,
        message: data.message || data.customer_options_message || "",
        sourceStatus: sourceMeta.sourceStatus,
        sourceLabel: sourceMeta.sourceLabel,
        sourceMessage: sourceMeta.sourceMessage,
      };
      return state.customerOptions;
    } catch (_error) {
      // Try the next compatible endpoint.
    }
  }
  state.customerOptions = state.customerOptions || {
    status: "unavailable",
    count: 0,
    options: [],
    message: "客户选项接口暂不可用，请先补客户配置或稍后刷新。",
    sourceStatus: "unavailable",
    sourceLabel: "客户系统源",
    sourceMessage: "客户选项接口暂不可用",
  };
  return state.customerOptions;
}

function selectedCustomerFromSelect() {
  const select = document.querySelector("#monitorGroupCustomer");
  const option = select?.selectedOptions?.[0];
  if (!select || !option || !select.value) return { customer_id: "", customer_name: "" };
  return {
    customer_id: option.dataset.customerId || "",
    customer_name: option.dataset.customerName || option.textContent.trim() || select.value,
  };
}

function setCustomerHint(message, tone = "") {
  const node = document.querySelector("#monitorGroupCustomerHint");
  if (!node) return;
  node.textContent = message;
  node.dataset.tone = tone;
}

function setCustomerSuggestionAction(suggestion = null) {
  const button = document.querySelector("#acceptCustomerSuggestionBtn");
  if (!button) return;
  const canConfirm = Boolean(suggestion?.option && !suggestion.reliable);
  button.classList.toggle("hidden", !canConfirm);
  button.disabled = !canConfirm;
}

function renderCustomerSelect(group) {
  const select = document.querySelector("#monitorGroupCustomer");
  if (!select) return;
  setCustomerSuggestionAction(null);
  const backendOptions = normalizeCustomerOptions(state.customerOptions?.options || []);
  const sourceTone = customerSourceLooksUnavailable(state.customerOptions) || !(state.customerOptions?.count || backendOptions.length) ? "warning" : "ok";
  setCustomerSourceStatus(customerSourceSummary(state.customerOptions || { count: backendOptions.length, sourceLabel: customerSourceLabelFromOptions(backendOptions) }), sourceTone);
  const selectedId = group.customer_id || "";
  const selectedName = group.customer_name || "";
  const selectedKey = selectedId || selectedName;
  const options = [...backendOptions];
  if (selectedName && !options.some((option) => (option.customer_id || option.customer_name) === selectedKey || option.customer_name === selectedName)) {
    options.unshift({
      customer_id: selectedId,
      customer_name: selectedName,
      label: `${selectedName}（已保存）`,
      source: "saved_group",
    });
  }
  if (!options.length) {
    select.innerHTML = '<option value="">暂无本地客户选项</option>';
    select.value = "";
    setCustomerHint(`${customerSourceSummary(state.customerOptions || {})} 请先补客户配置，或等待后端客户识别建议。`, "warning");
    return;
  }
  select.innerHTML = [
    '<option value="">待选择</option>',
    ...options.map((option) => {
      const value = option.customer_id || option.customer_name;
      const selected = value === selectedKey || option.customer_name === selectedName;
      return `<option value="${escapeAttr(value)}" data-customer-id="${escapeAttr(option.customer_id)}" data-customer-name="${escapeAttr(option.customer_name)}" ${selected ? "selected" : ""}>${escapeHtml(option.label || option.customer_name)}</option>`;
    }),
  ].join("");
  const count = state.customerOptions?.count ?? options.length;
  setCustomerHint(`已加载客户选项 ${count} 项；请确认客户归属后保存。`, "ok");
}

function normalizeCustomerSuggestion(payload = {}) {
  const directSuggestion = (payload.suggested_customer_name || payload.suggested_customer_id)
    ? {
      customer_name: payload.suggested_customer_name,
      customer_id: payload.suggested_customer_id,
      label: payload.suggested_customer_name,
      match_status: payload.match_status,
      reason_code: payload.reason_code,
    }
    : null;
  const raw = payload.customer_suggestion
    || payload.suggestion
    || payload.customer
    || (Array.isArray(payload.suggestions) ? payload.suggestions[0] : null)
    || (Array.isArray(payload.matches) ? payload.matches[0] : null)
    || directSuggestion;
  const option = normalizeCustomerOption(raw);
  const matchStatus = String(raw?.match_status || payload.match_status || "").trim();
  const sourceMeta = customerSourceMetaFromPayload(payload, Number(payload.customer_options_count || 0));
  const confidence = String(
    raw?.confidence
    || payload.confidence
    || payload.match_confidence
    || matchStatus
    || payload.status
    || ""
  ).trim();
  const score = Number(raw?.confidence_score ?? raw?.score ?? payload.confidence_score ?? payload.score);
  const reliable = Boolean(
    raw?.reliable
    || payload.reliable
    || (Number.isFinite(score) && score >= 0.8)
    || ["reliable", "high", "exact", "matched", "已匹配", "可靠命中"].includes(confidence)
    || ["matched", "exact", "reliable"].includes(matchStatus)
  );
  return {
    status: payload.status || (option ? "ok" : "empty"),
    reliable,
    confidence,
    matchStatus,
    reasonCode: raw?.reason_code || payload.reason_code || "",
    customerOptionsCount: Number(payload.customer_options_count ?? payload.count ?? 0) || 0,
    sourceStatus: sourceMeta.sourceStatus,
    sourceLabel: sourceMeta.sourceLabel,
    sourceMessage: sourceMeta.sourceMessage,
    needsConfirmation: Boolean(option && !reliable),
    option,
    message: payload.message || raw?.message || "",
  };
}

async function requestCustomerSuggestion(groupName) {
  const params = new URLSearchParams({ group_name: groupName, query: groupName });
  const endpoints = [
    `/api/monitor-groups/customer-suggestion?${params.toString()}`,
    `/api/customer-suggestions?${params.toString()}`,
    `/api/customers/suggestions?${params.toString()}`,
    `/api/monitor-groups/customer-suggestions?${params.toString()}`,
  ];
  for (const endpoint of endpoints) {
    try {
      const data = await api(endpoint);
      updateCustomerOptionsFromPayload(data);
      return normalizeCustomerSuggestion(data);
    } catch (_error) {
      // Try the next compatible endpoint.
    }
  }
  return {
    status: "unavailable",
    reliable: false,
    confidence: "",
    option: null,
    message: "客户识别接口暂不可用，请手动选择客户或先补客户配置。",
  };
}

function applyCustomerSelection(option) {
  const normalized = normalizeCustomerOption(option);
  if (!normalized) return false;
  const group = state.monitorGroups.find((item) => groupIdentity(item) === state.selectedMonitorGroupId);
  if (group) {
    group.customer_id = normalized.customer_id || "";
    group.customer_name = normalized.customer_name || "";
    group.customer_label = normalized.label || normalized.customer_name || "";
  }
  if (normalized.customer_id || normalized.customer_name) {
    const current = state.customerOptions || { status: "ok", count: 0, options: [] };
    const options = normalizeCustomerOptions(current.options || []);
    if (!options.some((item) => (item.customer_id || item.customer_name) === (normalized.customer_id || normalized.customer_name))) {
      options.unshift(normalized);
      state.customerOptions = { ...current, count: Math.max(current.count || 0, options.length), options };
    }
  }
  renderCustomerSelect(group || { customer_id: normalized.customer_id, customer_name: normalized.customer_name });
  return true;
}

function scheduleCustomerSuggestion() {
  clearTimeout(state.customerSuggestionTimer);
  state.customerSuggestionTimer = setTimeout(() => {
    autoSuggestCustomerForCurrentGroup();
  }, 350);
}

async function autoSuggestCustomerForCurrentGroup() {
  const group = state.monitorGroups.find((item) => groupIdentity(item) === state.selectedMonitorGroupId);
  const groupName = document.querySelector("#monitorGroupDisplayName")?.value.trim() || group?.display_name || "";
  if (!group || !groupName) {
    setCustomerHint("填写监控群名称后，会尝试识别客户。", "");
    return;
  }
  group.display_name = groupName;
  await loadCustomerOptions();
  setCustomerHint("正在识别客户归属...", "");
  const suggestion = await requestCustomerSuggestion(groupName);
  state.customerSuggestion = suggestion;
  if (suggestion.sourceStatus || suggestion.sourceLabel || suggestion.customerOptionsCount) {
    const meta = {
      ...state.customerOptions,
      count: suggestion.customerOptionsCount || state.customerOptions?.count || 0,
      sourceStatus: suggestion.sourceStatus || state.customerOptions?.sourceStatus || "",
      sourceLabel: suggestion.sourceLabel || state.customerOptions?.sourceLabel || "",
      sourceMessage: suggestion.sourceMessage || state.customerOptions?.sourceMessage || "",
    };
    setCustomerSourceStatus(customerSourceSummary(meta), customerSourceLooksUnavailable(meta) ? "warning" : "ok");
  }
  if (suggestion.reliable && suggestion.option) {
    applyCustomerSelection(suggestion.option);
    setCustomerSuggestionAction(null);
    renderMonitoringGroups();
    setCustomerHint("已根据监控群名称自动识别客户；请确认无误后保存。", "ok");
    return;
  }
  renderCustomerSelect(group);
  if (suggestion.option) {
    setCustomerSuggestionAction(suggestion);
    setCustomerHint("已找到疑似客户，需要确认。可点击采用建议客户，或从下拉中手动选择。", "warning");
    return;
  }
  setCustomerSuggestionAction(null);
  const sourceWarning = customerSourceLooksUnavailable(state.customerOptions) || !(state.customerOptions?.count || 0);
  setCustomerHint(
    suggestion.message
      || (sourceWarning ? `${customerSourceSummary(state.customerOptions || {})} 暂未识别客户，请选择客户或补客户配置。` : "未识别客户，请选择客户或先补客户配置。"),
    "warning"
  );
}

function acceptCustomerSuggestion() {
  const suggestion = state.customerSuggestion;
  if (!suggestion?.option) {
    setCustomerSuggestionAction(null);
    setCustomerHint("暂无可采用的客户建议，请选择客户或先补客户配置。", "warning");
    return false;
  }
  const applied = applyCustomerSelection(suggestion.option);
  if (!applied) {
    setCustomerHint("客户建议暂不可用，请从下拉中选择客户。", "warning");
    return false;
  }
  state.customerSuggestion = null;
  setCustomerSuggestionAction(null);
  renderMonitoringGroups();
  setCustomerHint("已采用建议客户；保存后会写入群档案并读回确认。", "ok");
  return true;
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

function memberOptionLabel(option) {
  if (typeof option === "string") return option;
  return option?.display_name || option?.name || option?.nickname || option?.remark || option?.label || "";
}

function safeCount(value, fallback = 0) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

function isSavedMonitorGroup(group) {
  return Boolean(group?.group_id && !group.group_id.startsWith("local-"));
}

function isRosterMemberOptions(memberOptions) {
  return memberOptions?.scope === "roster_members" && memberOptions?.complete === true;
}

function memberOptionsForGroup(group) {
  const memberOptions = group.member_options || emptyMemberOptions();
  const rawItems = Array.isArray(memberOptions.items) ? memberOptions.items : [];
  const rawNames = Array.isArray(memberOptions.names) ? memberOptions.names : [];
  const pairs = rawItems.length
    ? rawItems.map((item) => [
      String(item.value || item.name || item.display_name || item.label || ""),
      String(item.label || item.display_name || item.name || item.value || ""),
    ])
    : rawNames.map((name) => [String(name), String(name)]);
  const normalized = [];
  const seen = new Set();
  pairs.forEach(([value, label]) => {
    if (!value || seen.has(value)) return;
    seen.add(value);
    normalized.push([value, label || value]);
  });
  const scope = memberOptions.scope || "appeared_members";
  const complete = Boolean(memberOptions.complete);
  const rosterReady = isRosterMemberOptions({ scope, complete });
  return {
    scope,
    complete,
    rosterReady,
    sourceLabel: memberOptions.source_label || (rosterReady ? "微信群全员名单" : "本地已出现成员"),
    count: safeCount(memberOptions.count, normalized.length),
    availableCount: safeCount(memberOptions.available_count, normalized.length),
    rosterCount: safeCount(memberOptions.roster_count, 0),
    refreshAvailable: memberOptions.refresh_available !== false,
    refreshLabel: memberOptions.refresh_label || "刷新本地已出现成员",
    refreshStatus: memberOptions.refresh_status || "",
    fullSyncAvailable: Boolean(memberOptions.full_sync_available),
    fullSyncStatusLabel: safeFullSyncStatusLabel(memberOptions.full_sync_status_label),
    syncActionLabel: memberOptions.sync_action_label || "同步微信群全员名单",
    rosterStatusLabel: memberOptions.roster_status_label || "",
    statusLabel: memberOptions.status_label || (normalized.length ? "当前只列出已识别成员，可先保存，后续刷新成员。" : "当前只拿到本地出现过的成员，暂无可选成员。"),
    options: normalized,
  };
}

function safeFullSyncStatusLabel() {
  return "完整成员名单需要同步授权或后端能力支持。";
}

function setOptions(select, options, selected, { allowEmpty = true, multiple = false, appendSelected = true } = {}) {
  const selectedValues = new Set(Array.isArray(selected) ? selected : [selected].filter(Boolean));
  const normalized = options.map((option) => Array.isArray(option) ? option : [option, option]);
  if (appendSelected) {
    selectedValues.forEach((value) => {
      if (![...normalized].some(([optionValue]) => optionValue === value)) {
        normalized.push([value, value]);
      }
    });
  }
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

function cssEscape(value) {
  if (window.CSS?.escape) return window.CSS.escape(value);
  return String(value).replace(/["\\]/g, "\\$&");
}

function emptyMemberRoleSets() {
  return {
    owner: new Set(),
    contact: new Set(),
    internal: new Set(),
  };
}

function memberRoleSetsFromGroup(group) {
  return {
    owner: new Set(group.owner_names || [group.owner_name].filter(Boolean)),
    contact: new Set(group.common_contacts || []),
    internal: new Set(group.internal_people || []),
  };
}

function memberRoleSetsFromDom(group) {
  const roles = memberRoleSetsFromGroup(group);
  const roleInputs = document.querySelectorAll("[data-member-role]");
  if (!roleInputs.length) return roles;
  const visibleNames = new Set(Array.from(roleInputs).map((input) => input.dataset.memberName));
  visibleNames.forEach((name) => {
    roles.owner.delete(name);
    roles.contact.delete(name);
    roles.internal.delete(name);
  });
  roleInputs.forEach((input) => {
    if (input.checked && roles[input.dataset.memberRole]) {
      roles[input.dataset.memberRole].add(input.dataset.memberName);
    }
  });
  return roles;
}

function currentMemberRoleSets(group) {
  return memberRoleSetsFromDom(group);
}

function memberRoleArrays(group) {
  const roles = currentMemberRoleSets(group);
  return {
    owner_names: Array.from(roles.owner),
    common_contacts: Array.from(roles.contact),
    internal_people: Array.from(roles.internal),
  };
}

function memberRoleLabels(name, roles) {
  const labels = [];
  if (roles.owner.has(name)) labels.push("群负责人");
  if (roles.contact.has(name)) labels.push("常用联系人");
  if (roles.internal.has(name)) labels.push("我方人员");
  return labels;
}

function renderAllMemberChips() {
  const container = document.querySelector("#monitorGroupMemberChips");
  if (!container) return;
  const group = state.monitorGroups.find((item) => groupIdentity(item) === state.selectedMonitorGroupId);
  const roles = group ? currentMemberRoleSets(group) : emptyMemberRoleSets();
  const names = Array.from(new Set([
    ...roles.owner,
    ...roles.contact,
    ...roles.internal,
  ]));
  container.innerHTML = names.length
    ? names.map((name) => `
      <span class="selected-chip">
        ${escapeHtml(name)} · ${escapeHtml(memberRoleLabels(name, roles).join("/"))}
        <button type="button" data-remove-member="${escapeAttr(name)}" aria-label="移除 ${escapeAttr(name)}">×</button>
      </span>
    `).join("")
    : '<span class="selected-chip-empty">还未给成员分配角色</span>';
}

function renderCurrentMemberPool() {
  const group = state.monitorGroups.find((item) => groupIdentity(item) === state.selectedMonitorGroupId);
  if (!group) return;
  persistCurrentMemberRolesFromDom();
  renderMemberPool(group, memberOptionsForGroup(group));
}

function persistCurrentMemberRolesFromDom() {
  const group = state.monitorGroups.find((item) => groupIdentity(item) === state.selectedMonitorGroupId);
  if (!group) return;
  const roleInputs = document.querySelectorAll("[data-member-role]");
  if (!roleInputs.length) return;
  const roleArrays = memberRoleArrays(group);
  group.owner_names = roleArrays.owner_names;
  group.owner_name = roleArrays.owner_names[0] || "";
  group.common_contacts = roleArrays.common_contacts;
  group.internal_people = roleArrays.internal_people;
}

function renderMemberPool(group, memberOptions) {
  const pool = document.querySelector("#monitorGroupMemberPool");
  if (!pool) return;
  const roles = currentMemberRoleSets(group);
  const query = (document.querySelector("#monitorGroupMemberSearch")?.value || "").trim();
  const options = memberOptions.options.filter(([value, label]) => {
    if (!query) return true;
    return `${value} ${label}`.includes(query);
  });
  if (!memberOptions.options.length) {
    pool.innerHTML = memberOptions.rosterReady
      ? '<div class="empty">已切到微信群全员名单，但暂时没有可选成员；可稍后再同步一次。</div>'
      : '<div class="empty">暂无本地已出现成员；可先刷新成员或完成试读后再回来选择。</div>';
    renderAllMemberChips();
    return;
  }
  const sourceLine = memberOptions.rosterReady
    ? "来源：微信群全员名单 · scope=roster_members · complete=true"
    : "来源：本地已出现成员 · 不是群全员名单";
  pool.innerHTML = options.map(([value, label]) => `
    <div class="member-role-row" data-member-row="${escapeAttr(value)}">
      <div>
        <strong>${escapeHtml(label || value)}</strong>
        <small>${escapeHtml(sourceLine)}</small>
      </div>
      <div class="member-role-actions">
        <label><input type="checkbox" data-member-role="owner" data-member-name="${escapeAttr(value)}" ${roles.owner.has(value) ? "checked" : ""} /> 群负责人</label>
        <label><input type="checkbox" data-member-role="contact" data-member-name="${escapeAttr(value)}" ${roles.contact.has(value) ? "checked" : ""} /> 常用联系人</label>
        <label><input type="checkbox" data-member-role="internal" data-member-name="${escapeAttr(value)}" ${roles.internal.has(value) ? "checked" : ""} /> 我方人员</label>
      </div>
    </div>
  `).join("") || `<div class="empty">没有匹配的${memberOptions.rosterReady ? "微信群全员名单成员" : "本地已出现成员"}。</div>`;
  renderAllMemberChips();
}

function groupCompleteness(group) {
  const required = [
    monitorGroupEditableName(group),
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
  if (!list) return;
  const query = (document.querySelector("#monitorGroupSearch")?.value || "").trim();
  if (!state.selectedMonitorGroupId || !state.monitorGroups.some((group) => groupIdentity(group) === state.selectedMonitorGroupId)) {
    state.selectedMonitorGroupId = groupIdentity(state.monitorGroups[0]) || "";
  }
  const filtered = state.monitorGroups.filter((group) => {
    if (!query) return true;
    return [monitorGroupTitle(group), group.customer_name, group.owner_name, group.owner_label, group.module_name]
      .some((value) => String(value || "").includes(query));
  });
  list.innerHTML = filtered.map((group) => {
    const complete = groupCompleteness(group);
    const monitorText = group.archived
      ? "已归档"
      : group.enabled === false
      ? "已停用"
      : group.daily_monitor && group.include_in_daily && group.verification_status !== "待验证"
        ? "已纳入日报"
        : "待验证 / 未纳入日报";
    return `
      <button class="monitor-group-card ${groupIdentity(group) === state.selectedMonitorGroupId ? "active" : ""}" data-monitor-group-id="${escapeAttr(groupIdentity(group))}">
        <strong>${escapeHtml(monitorGroupTitle(group))}</strong>
        <span>${escapeHtml(group.customer_name || "待选择客户")}｜${escapeHtml(group.group_type || "待选群类型")}</span>
        <small>${escapeHtml(monitorText)}｜${escapeHtml(complete.label)}｜负责人：${escapeHtml(group.owner_name || group.owner_label || "待指定")}</small>
      </button>
    `;
  }).join("") || '<div class="empty">没有匹配的监控群。</div>';
  list.querySelectorAll("[data-monitor-group-id]").forEach((button) => {
    button.addEventListener("click", () => {
      state.selectedMonitorGroupId = button.dataset.monitorGroupId;
      renderMonitoringGroups();
      loadSelectedMonitorGroupDetail(state.selectedMonitorGroupId);
    });
  });
  renderMonitorGroupEditor();
  renderDailyReportCenter();
}

function renderMonitorGroupEditor() {
  const group = state.monitorGroups.find((item) => groupIdentity(item) === state.selectedMonitorGroupId);
  const title = document.querySelector("#monitorGroupEditorTitle");
  if (!title) return;
  if (!group) {
    title.textContent = "监控群档案";
    document.querySelector("#monitorGroupEditorStatus").textContent = "暂无监控群；请新增后保存。";
    document.querySelector("#monitorGroupCompleteness").textContent = "待完善";
    ["#disableMonitorGroupBtn", "#archiveMonitorGroupBtn", "#deleteMonitorGroupBtn", "#trialMonitorGroupBtn"].forEach((selector) => {
      const button = document.querySelector(selector);
      if (button) button.disabled = true;
    });
    return;
  }
  if (!state.customerOptions) {
    loadCustomerOptions().then(() => {
      if (state.selectedMonitorGroupId === groupIdentity(group)) renderMonitorGroupEditor();
    });
  }
  if (group.group_id && !group.member_detail_loaded) {
    loadSelectedMonitorGroupDetail(group.group_id);
  }
  const completeness = groupCompleteness(group);
  const visibleGroupName = monitorGroupTitle(group);
  const editableGroupName = monitorGroupEditableName(group);
  title.textContent = visibleGroupName;
  const monitorStatusText = group.archived ? "已归档" : group.enabled === false ? "已停用" : "启用中";
  document.querySelector("#monitorGroupEditorStatus").textContent =
    `${group.verification_status || "待验证"}｜${monitorStatusText}｜试读成功前不会自动纳入日报统计`;
  document.querySelector("#monitorGroupCompleteness").textContent = completeness.label;
  const displayNameInput = document.querySelector("#monitorGroupDisplayName");
  const displayNameHint = document.querySelector("#monitorGroupDisplayNameHint");
  displayNameInput.value = editableGroupName;
  displayNameInput.placeholder = editableGroupName ? "请输入监控群名称" : "待补群名";
  if (displayNameHint) {
    displayNameHint.textContent = editableGroupName
      ? "保存后用于左侧列表、消息筛选和候选 / 日报关联。"
      : "当前没有可读群名；请在这里手动填写本地显示名，保存后替换“群名待解析”。";
  }
  renderCustomerSelect(group);
  renderMonitorGroupOptionStatus(group);
  setOptions(document.querySelector("#monitorGroupType"), fieldOptionValues(["group_types", "group_type_options"], monitorGroupOptions.groupTypes, "group_type"), group.group_type);
  setOptions(document.querySelector("#monitorGroupModule"), fieldOptionValues(["modules", "module_options"], monitorGroupOptions.modules, "module_name"), group.module_name);
  setOptions(document.querySelector("#monitorGroupStage"), fieldOptionValues(["customer_stages", "customer_stage_options"], monitorGroupOptions.stages, "customer_stage"), group.customer_stage);
  const memberOptions = memberOptionsForGroup(group);
  const memberCount = memberOptions.count || memberOptions.options.length;
  const rosterReady = memberOptions.rosterReady;
  const memberNotice = !group.member_detail_loaded
    ? "正在加载该群成员选项..."
    : rosterReady
      ? `当前展示：微信群全员名单｜${memberCount} 位｜scope=roster_members｜complete=true`
      : memberOptions.options.length
        ? `当前展示：${memberOptions.sourceLabel}｜${memberCount} 位｜不是群全员名单`
        : `当前展示：${memberOptions.sourceLabel}｜暂无可选成员｜不是群全员名单`;
  const memberSearch = document.querySelector("#monitorGroupMemberSearch");
  if (memberSearch) memberSearch.placeholder = rosterReady ? "搜索微信群全员名单" : "搜索本地已出现成员";
  document.querySelector("#monitorGroupMemberNotice").textContent = memberNotice;
  const refreshButton = document.querySelector("#refreshMonitorGroupMembersBtn");
  const rosterButton = document.querySelector("#syncMonitorGroupRosterBtn");
  const archiveButton = document.querySelector("#archiveMonitorGroupBtn");
  const deleteButton = document.querySelector("#deleteMonitorGroupBtn");
  const syncOnCreateWrap = document.querySelector("#monitorGroupSyncRosterOnCreateWrap");
  const syncOnCreateCheckbox = document.querySelector("#monitorGroupSyncRosterOnCreate");
  const syncOnCreateHint = document.querySelector("#monitorGroupSyncRosterOnCreateHint");
  const syncStatus = document.querySelector("#monitorGroupMemberSyncStatus");
  const isRefreshing = state.refreshingMonitorGroupId === group.group_id;
  const isSyncingRoster = state.syncingRosterGroupId === group.group_id;
  const isNewGroup = !isSavedMonitorGroup(group);
  refreshButton.textContent = isRefreshing ? "刷新中..." : memberOptions.refreshLabel;
  refreshButton.disabled = isRefreshing || isSyncingRoster || !isSavedMonitorGroup(group) || !memberOptions.refreshAvailable;
  rosterButton.textContent = isSyncingRoster ? "同步中..." : memberOptions.syncActionLabel;
  rosterButton.disabled = isRefreshing || isSyncingRoster || !isSavedMonitorGroup(group);
  if (archiveButton) {
    const archived = group.archived || (group.enabled === false && !group.daily_monitor && !group.include_in_daily);
    archiveButton.textContent = archived ? "已归档" : "归档";
    archiveButton.disabled = isRefreshing || isSyncingRoster || !isSavedMonitorGroup(group) || archived;
  }
  if (deleteButton) {
    deleteButton.disabled = isRefreshing || isSyncingRoster || !groupIdentity(group);
  }
  if (syncOnCreateCheckbox) {
    syncOnCreateCheckbox.checked = isNewGroup ? group.sync_roster_on_create !== false : false;
    syncOnCreateCheckbox.disabled = !isNewGroup || isRefreshing || isSyncingRoster;
  }
  if (syncOnCreateWrap) {
    syncOnCreateWrap.classList.toggle("disabled", !isNewGroup);
  }
  if (syncOnCreateHint) {
    syncOnCreateHint.textContent = isNewGroup
      ? "默认保存后同步全员名单；只读取成员名单元数据，不读取聊天消息，不外发，不写正式区。"
      : "已有监控群不会自动同步；成员变化时请使用右侧同步按钮。";
  }
  const statusParts = [];
  if (!isSavedMonitorGroup(group)) {
    statusParts.push("保存为监控群后才能刷新或同步成员。");
  } else if (!group.member_detail_loaded) {
    statusParts.push("正在读取该群成员选项。");
  } else if (rosterReady) {
    statusParts.push("已同步微信群全员名单；scope=roster_members；complete=true。");
    statusParts.push("成员只用于本地页面选人，不读取聊天消息，不写正式区。");
  } else {
    statusParts.push("当前展示：本地已出现成员；不是群全员名单。");
    statusParts.push(memberOptions.statusLabel);
    statusParts.push(memberOptions.fullSyncAvailable
      ? "如需全员名单，请点击同步微信群全员名单并确认授权。"
      : safeFullSyncStatusLabel(memberOptions.fullSyncStatusLabel));
  }
  syncStatus.textContent = statusParts.join(" ");
  renderMemberPool(group, memberOptions);
  setOptions(document.querySelector("#monitorGroupTrialRange"), fieldOptionValues(["trial_scopes", "trial_ranges"], monitorGroupOptions.trialRanges), group.trial_range || "recent50", { allowEmpty: false });
  setOptions(document.querySelector("#monitorGroupVerifyStatus"), fieldOptionValues(["verification_statuses", "verify_statuses"], monitorGroupOptions.verifyStatuses), group.verification_status || "待验证", { allowEmpty: false });
  document.querySelector("#monitorGroupDailyMonitor").checked = Boolean(group.daily_monitor);
  document.querySelector("#monitorGroupIncludeDaily").checked = Boolean(group.include_in_daily);
  document.querySelector("#monitorGroupReplyNotes").value = group.reply_notes || "";
}

function readMonitorGroupForm() {
  const current = state.monitorGroups.find((group) => groupIdentity(group) === state.selectedMonitorGroupId) || {
    external_id: makeMonitorGroupId(),
  };
  const roleArrays = memberRoleArrays(current);
  return {
    ...current,
    display_name: document.querySelector("#monitorGroupDisplayName").value.trim(),
    customer_id: selectedCustomerFromSelect().customer_id,
    customer_name: selectedCustomerFromSelect().customer_name,
    group_type: document.querySelector("#monitorGroupType").value,
    module_name: document.querySelector("#monitorGroupModule").value,
    customer_stage: document.querySelector("#monitorGroupStage").value,
    owner_name: roleArrays.owner_names[0] || "",
    owner_names: roleArrays.owner_names,
    common_contacts: roleArrays.common_contacts,
    internal_people: roleArrays.internal_people,
    trial_range: document.querySelector("#monitorGroupTrialRange").value,
    daily_monitor: document.querySelector("#monitorGroupDailyMonitor").checked,
    include_in_daily: document.querySelector("#monitorGroupIncludeDaily").checked,
    verification_status: document.querySelector("#monitorGroupVerifyStatus").value,
    reply_notes: document.querySelector("#monitorGroupReplyNotes").value.trim(),
    is_whitelisted: true,
    sync_roster_on_create: Boolean(document.querySelector("#monitorGroupSyncRosterOnCreate")?.checked),
  };
}

function monitorGroupToSession(group) {
  return {
    external_id: group.external_id || makeMonitorGroupId(),
    display_name: group.display_name || "未命名监控群",
    customer_id: group.customer_id || "",
    customer_name: group.customer_name || "",
    channel_name: group.channel_name || "",
    module_name: group.module_name || "",
    owner_name: group.owner_name || "",
    owner_names: group.owner_names || [],
    customer_stage: group.customer_stage || "",
    group_type: group.group_type || "",
    common_contacts: group.common_contacts || [],
    reply_notes: group.reply_notes || "",
    is_whitelisted: true,
    enabled: group.enabled !== false,
    archived: Boolean(group.archived),
    verification_status: group.verification_status === "已验证" ? "verified" : "pending_verification",
    daily_monitor_enabled: Boolean(group.daily_monitor),
    include_in_daily: Boolean(group.include_in_daily),
    trial_scope: group.trial_range || "最近50条",
    internal_people: group.internal_people || [],
  };
}

function monitorGroupToPayload(group) {
  return {
    group_name: group.display_name || "未命名监控群",
    display_name: group.display_name || "未命名监控群",
    customer_id: group.customer_id || "",
    customer_name: group.customer_name || "",
    channel_name: group.channel_name || "",
    module_name: group.module_name || "",
    owner_names: group.owner_names || [],
    owner_name: group.owner_name || "",
    customer_stage: group.customer_stage || "",
    group_type: group.group_type || "测试群",
    common_contacts: group.common_contacts || [],
    reply_notes: group.reply_notes || "",
    enabled: group.enabled !== false,
    archived: Boolean(group.archived),
    verification_status: group.verification_status === "已验证" ? "verified" : "pending_verification",
    daily_monitor_enabled: Boolean(group.daily_monitor),
    include_in_daily: Boolean(group.include_in_daily),
    trial_scope: group.trial_range || "最近50条",
    internal_people: group.internal_people || [],
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
  if (!group.customer_name) {
    document.querySelector("#monitorGroupSaveResult").textContent = "未识别客户，请先选择客户或补客户配置后再保存。";
    setCustomerHint(`${customerSourceSummary(state.customerOptions || {})} 请先选择客户或补客户配置后再保存。`, "warning");
    return;
  }
  const isCreatingGroup = !isSavedMonitorGroup(group);
  const syncRosterOnCreate = isCreatingGroup && Boolean(document.querySelector("#monitorGroupSyncRosterOnCreate")?.checked);
  const authorizeRosterSyncOnCreate = syncRosterOnCreate && window.confirm(FULL_ROSTER_CREATE_CONFIRM_TEXT);
  const index = state.monitorGroups.findIndex((item) => groupIdentity(item) === groupIdentity(group));
  if (index >= 0) state.monitorGroups[index] = group;
  else state.monitorGroups.push(group);
  state.selectedMonitorGroupId = groupIdentity(group);
  saveMonitorGroupMeta();
  try {
    const groupId = group.group_id || "";
    const result = await api(groupId ? `/api/monitor-groups/${encodeURIComponent(groupId)}` : "/api/monitor-groups", {
      method: groupId ? "PUT" : "POST",
      body: JSON.stringify(monitorGroupToPayload(group)),
    });
    updateCustomerOptionsFromPayload(result);
    let savedGroup = normalizeMonitorGroupApi(result.group || {}, result);
    if (savedGroup.group_id) {
      state.selectedMonitorGroupId = savedGroup.group_id;
      state.monitorGroupDetails[savedGroup.group_id] = savedGroup;
      await loadSelectedMonitorGroupDetail(savedGroup.group_id);
      savedGroup = state.monitorGroupDetails[savedGroup.group_id] || savedGroup;
    }
    const savedIndex = state.monitorGroups.findIndex((item) => groupIdentity(item) === groupIdentity(group) || groupIdentity(item) === savedGroup.group_id);
    if (savedIndex >= 0) state.monitorGroups[savedIndex] = savedGroup;
    else state.monitorGroups.push(savedGroup);
    let saveMessage = "已保存监控群档案；不会自动读取聊天消息或外发。";
    if (syncRosterOnCreate && !authorizeRosterSyncOnCreate) {
      saveMessage = "已保存监控群档案；已取消全员名单同步，可稍后使用手动同步按钮。";
    } else if (authorizeRosterSyncOnCreate) {
      if (!savedGroup.group_id) {
        saveMessage = "群已保存，但暂未拿到可同步的监控群 id；请稍后使用手动同步按钮。";
      } else {
        state.syncingRosterGroupId = savedGroup.group_id;
        renderMonitoringGroups();
        try {
          const syncResult = await api(`/api/monitor-groups/${encodeURIComponent(savedGroup.group_id)}/sync-roster`, {
            method: "POST",
            body: JSON.stringify({ authorize_full_roster_sync: true }),
          });
          const applied = applyRosterSyncResultToGroup(savedGroup, syncResult);
          saveMessage = applied.synced
            ? `已保存监控群档案。${applied.message}`
            : `群已保存，但全员名单同步失败/待授权。${applied.message}`;
        } catch (_syncError) {
          saveMessage = "群已保存，但全员名单同步失败/待授权；请稍后使用手动同步按钮重试。";
        } finally {
          state.syncingRosterGroupId = "";
        }
      }
    }
    document.querySelector("#monitorGroupSaveResult").textContent = saveMessage;
  } catch (_error) {
    document.querySelector("#monitorGroupSaveResult").textContent = "已暂存在本机浏览器；配置保存暂不可用，因此未同步微信群全员名单。";
  }
  renderMonitoringGroups();
}

async function refreshSelectedMonitorGroupMembers() {
  const group = state.monitorGroups.find((item) => groupIdentity(item) === state.selectedMonitorGroupId);
  const status = document.querySelector("#monitorGroupMemberSyncStatus");
  if (!group) {
    status.textContent = "请先选择一个监控群。";
    return;
  }
  if (!group.group_id || group.group_id.startsWith("local-")) {
    status.textContent = "这个监控群还没保存，保存后才能刷新成员。";
    renderMonitorGroupEditor();
    return;
  }
  state.refreshingMonitorGroupId = group.group_id;
  renderMonitorGroupEditor();
  let finalMessage = "";
  try {
    const result = await api(`/api/monitor-groups/${encodeURIComponent(group.group_id)}/refresh-members`, {
      method: "POST",
      body: "{}",
    });
    if (!["refreshed", "empty", "ok"].includes(result.status)) {
      throw new Error(result.status || "refresh_failed");
    }
    const memberOptions = result.member_options || emptyMemberOptions();
    const nextGroup = {
      ...group,
      member_options: memberOptions,
      member_detail_loaded: true,
    };
    state.monitorGroupDetails[group.group_id] = nextGroup;
    const index = state.monitorGroups.findIndex((item) => groupIdentity(item) === group.group_id);
    if (index >= 0) state.monitorGroups[index] = nextGroup;
    const count = Number.isFinite(Number(result.member_count)) ? Number(result.member_count) : Number(memberOptions.count || 0);
    finalMessage = [
      `已刷新 ${count} 位本地已出现成员。`,
      "不是群全员名单。",
      memberOptions.status_label || "",
      safeFullSyncStatusLabel(result.full_sync_status_label || memberOptions.full_sync_status_label),
    ].filter(Boolean).join(" ");
  } catch (_error) {
    finalMessage = "刷新成员失败；请确认本地服务正常，或稍后再试。";
  } finally {
    state.refreshingMonitorGroupId = "";
    renderMonitoringGroups();
    const currentStatus = document.querySelector("#monitorGroupMemberSyncStatus");
    if (currentStatus && finalMessage) currentStatus.textContent = finalMessage;
  }
}

function rosterSyncSummaryMessage(result) {
  const authorization = result.authorization || {};
  const statusText = result.roster_status_label
    || authorization.status_label
    || result.error_code
    || result.status
    || "同步未完成";
  const countText = [
    `本地可用 ${safeCount(result.available_count)} 位`,
    `roster ${safeCount(result.roster_count)} 位`,
  ].join("，");
  const authText = result.full_sync_requires_authorization || authorization.required
    ? "需要显式授权或后端能力支持。"
    : "";
  return [
    `未切换到微信群全员名单：${statusText}。`,
    countText,
    authText,
    "页面未展示名单明细，仍保留本地已出现成员池。",
  ].filter(Boolean).join(" ");
}

function applyRosterSyncResultToGroup(group, result) {
  if (result.status !== "synced") {
    return {
      synced: false,
      message: rosterSyncSummaryMessage(result),
    };
  }
  const memberOptions = result.member_options || emptyMemberOptions();
  if (!isRosterMemberOptions(memberOptions)) {
    return {
      synced: false,
      message: "同步返回的全员名单状态不完整；暂不切换成员池，页面仍保留本地已出现成员。",
    };
  }
  const nextGroup = {
    ...group,
    member_options: memberOptions,
    member_detail_loaded: true,
  };
  state.monitorGroupDetails[group.group_id] = nextGroup;
  const index = state.monitorGroups.findIndex((item) => groupIdentity(item) === group.group_id);
  if (index >= 0) state.monitorGroups[index] = nextGroup;
  const count = safeCount(result.roster_count, safeCount(memberOptions.roster_count, safeCount(memberOptions.count, 0)));
  return {
    synced: true,
    group: nextGroup,
    message: `已同步微信群全员名单：${count} 位；scope=roster_members；complete=true。成员只用于本地页面选人，不读取聊天消息，不写正式区。`,
  };
}

async function syncSelectedMonitorGroupRoster() {
  const group = state.monitorGroups.find((item) => groupIdentity(item) === state.selectedMonitorGroupId);
  const status = document.querySelector("#monitorGroupMemberSyncStatus");
  if (!group) {
    status.textContent = "请先选择一个监控群。";
    return;
  }
  if (!isSavedMonitorGroup(group)) {
    status.textContent = "这个监控群还没保存，保存后才能同步微信群全员名单。";
    renderMonitorGroupEditor();
    return;
  }
  if (!window.confirm(FULL_ROSTER_SYNC_CONFIRM_TEXT)) {
    status.textContent = "已取消同步；当前仍展示本地已出现成员，不是群全员名单。";
    return;
  }
  state.syncingRosterGroupId = group.group_id;
  renderMonitorGroupEditor();
  let finalMessage = "";
  try {
    const result = await api(`/api/monitor-groups/${encodeURIComponent(group.group_id)}/sync-roster`, {
      method: "POST",
      body: JSON.stringify({ authorize_full_roster_sync: true }),
    });
    finalMessage = applyRosterSyncResultToGroup(group, result).message;
  } catch (_error) {
    finalMessage = "同步微信群全员名单失败；请确认本地服务正常、已具备授权或后端能力后再试。页面仍保留本地已出现成员池。";
  } finally {
    state.syncingRosterGroupId = "";
    renderMonitoringGroups();
    const currentStatus = document.querySelector("#monitorGroupMemberSyncStatus");
    if (currentStatus && finalMessage) currentStatus.textContent = finalMessage;
  }
}

async function disableSelectedMonitorGroup() {
  const group = readMonitorGroupForm();
  group.enabled = false;
  group.daily_monitor = false;
  group.include_in_daily = false;
  const index = state.monitorGroups.findIndex((item) => groupIdentity(item) === groupIdentity(group));
  if (index >= 0) state.monitorGroups[index] = group;
  saveMonitorGroupMeta();
  try {
    if (group.group_id) {
      const result = await api(`/api/monitor-groups/${encodeURIComponent(group.group_id)}/disable`, {
        method: "POST",
        body: "{}",
      });
      const savedGroup = normalizeMonitorGroupApi(result.group || {});
      if (savedGroup.group_id) {
        const savedIndex = state.monitorGroups.findIndex((item) => groupIdentity(item) === savedGroup.group_id);
        if (savedIndex >= 0) state.monitorGroups[savedIndex] = savedGroup;
      }
    }
    document.querySelector("#monitorGroupSaveResult").textContent = "已停用该监控群。";
  } catch (_error) {
    document.querySelector("#monitorGroupSaveResult").textContent = "已在本机页面停用；配置保存暂不可用。";
  }
  renderMonitoringGroups();
}

function monitorGroupActionStatusNode() {
  return document.querySelector("#monitorGroupSaveResult");
}

function selectedMonitorGroup() {
  return state.monitorGroups.find((item) => groupIdentity(item) === state.selectedMonitorGroupId);
}

function monitorGroupSnapshot() {
  return {
    groups: JSON.parse(JSON.stringify(state.monitorGroups || [])),
    details: JSON.parse(JSON.stringify(state.monitorGroupDetails || {})),
    selected: state.selectedMonitorGroupId,
  };
}

function restoreMonitorGroupSnapshot(snapshot) {
  state.monitorGroups = snapshot.groups || [];
  state.monitorGroupDetails = snapshot.details || {};
  state.selectedMonitorGroupId = snapshot.selected || groupIdentity(state.monitorGroups[0]) || "";
  saveMonitorGroupMeta();
  renderMonitoringGroups();
}

function monitorGroupActionEndpointMissing(error) {
  return /404|405|not found|not allowed|method not allowed/i.test(String(error?.message || error || ""));
}

function blockedMonitorGroupAction(result = {}) {
  return ["blocked", "failed", "error", "forbidden", "not_found", "confirmation_required"].includes(String(result.status || "").toLowerCase());
}

function mergeArchivedMonitorGroup(group, result = {}) {
  const savedGroup = result.group ? normalizeMonitorGroupApi(result.group, result) : {};
  return {
    ...group,
    ...savedGroup,
    group_id: savedGroup.group_id || group.group_id,
    external_id: savedGroup.external_id || group.external_id,
    enabled: false,
    archived: true,
    daily_monitor: false,
    include_in_daily: false,
  };
}

function removeMonitorGroupFromState(group) {
  const identity = groupIdentity(group);
  state.monitorGroups = (state.monitorGroups || []).filter((item) => groupIdentity(item) !== identity);
  if (state.monitorGroupDetails && group.group_id) {
    delete state.monitorGroupDetails[group.group_id];
  }
  state.selectedMonitorGroupId = groupIdentity(state.monitorGroups[0]) || "";
  saveMonitorGroupMeta();
}

async function archiveSelectedMonitorGroup() {
  const status = monitorGroupActionStatusNode();
  const group = selectedMonitorGroup();
  if (!group) {
    status.textContent = "请先选择一个监控群。";
    return;
  }
  if (!isSavedMonitorGroup(group)) {
    status.textContent = "这个监控群还没保存；请先保存群档案，再执行归档。";
    return;
  }
  if (!window.confirm(ARCHIVE_MONITOR_GROUP_CONFIRM_TEXT)) {
    status.textContent = "已取消归档；当前列表未变化。";
    return;
  }
  const snapshot = monitorGroupSnapshot();
  status.textContent = "归档中：正在移出日常监控和日报统计，旧列表会保留到操作成功。";
  try {
    let result;
    try {
      result = await api(`/api/monitor-groups/${encodeURIComponent(group.group_id)}/archive`, {
        method: "POST",
        body: JSON.stringify({ archive_monitor_group: true }),
      });
    } catch (error) {
      if (!monitorGroupActionEndpointMissing(error)) throw error;
      result = await api(`/api/monitor-groups/${encodeURIComponent(group.group_id)}/disable`, {
        method: "POST",
        body: JSON.stringify({ archive_monitor_group: true }),
      });
    }
    if (blockedMonitorGroupAction(result)) throw new Error("blocked");
    const nextGroup = mergeArchivedMonitorGroup(group, result);
    const index = state.monitorGroups.findIndex((item) => groupIdentity(item) === groupIdentity(group));
    if (index >= 0) state.monitorGroups[index] = nextGroup;
    state.selectedMonitorGroupId = groupIdentity(nextGroup);
    saveMonitorGroupMeta();
    renderMonitoringGroups();
    monitorGroupActionStatusNode().textContent =
      "已归档：该监控群已移出日常监控和日报统计；不会删除真实微信群，不会外发，也不会写正式区。";
  } catch (_error) {
    restoreMonitorGroupSnapshot(snapshot);
    monitorGroupActionStatusNode().textContent =
      "归档失败或被拦截；旧列表已保留，请稍后重试或检查本机服务状态。";
  }
}

async function deleteMonitorGroupViaEndpoint(group) {
  try {
    const result = await api(`/api/monitor-groups/${encodeURIComponent(group.group_id)}/delete`, {
      method: "POST",
      body: JSON.stringify({ confirm_delete: true }),
    });
    if (blockedMonitorGroupAction(result)) throw new Error("blocked");
    return result;
  } catch (error) {
    if (!monitorGroupActionEndpointMissing(error)) throw error;
  }
  try {
    const result = await api(`/api/monitor-groups/${encodeURIComponent(group.group_id)}`, {
      method: "DELETE",
      body: JSON.stringify({ confirm_delete: true, delete_local_monitor_group_config: true }),
    });
    if (blockedMonitorGroupAction(result)) throw new Error("blocked");
    return result;
  } catch (error) {
    if (monitorGroupActionEndpointMissing(error)) return null;
    throw error;
  }
}

async function deleteSelectedMonitorGroup() {
  const status = monitorGroupActionStatusNode();
  const group = selectedMonitorGroup();
  if (!group) {
    status.textContent = "请先选择一个监控群。";
    return;
  }
  if (!window.confirm(DELETE_MONITOR_GROUP_CONFIRM_TEXT)) {
    status.textContent = "已取消删除；当前列表未变化。";
    return;
  }
  const snapshot = monitorGroupSnapshot();
  status.textContent = "删除中：只删除本项目本地监控群配置，旧列表会保留到操作成功。";
  try {
    let endpointResult = null;
    if (isSavedMonitorGroup(group)) {
      endpointResult = await deleteMonitorGroupViaEndpoint(group);
    }
    removeMonitorGroupFromState(group);
    if (!endpointResult) {
      await ensureConfigCenterLoaded();
      await saveConfigFromState();
    }
    renderMonitoringGroups();
    monitorGroupActionStatusNode().textContent =
      "已删除本地监控群配置；不影响真实微信群、客户系统、正式区或外部系统。";
  } catch (_error) {
    restoreMonitorGroupSnapshot(snapshot);
    monitorGroupActionStatusNode().textContent =
      "删除失败或被拦截；旧列表已保留，请稍后重试或检查本机服务状态。";
  }
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
    sync_roster_on_create: true,
  };
  state.monitorGroups = [...(state.monitorGroups || []), group];
  state.selectedMonitorGroupId = group.external_id;
  renderMonitoringGroups();
  document.querySelector("#monitorGroupDisplayName")?.focus();
}

function normalizePersonForPage(person, index) {
  const aliases = Array.isArray(person.aliases)
    ? person.aliases
    : Array.isArray(person.common_names)
      ? person.common_names
      : [];
  return {
    index,
    person_id: person.person_id || "",
    person_name: person.person_name || "",
    aliases,
    wechat_display_name: person.wechat_display_name || person.display_name || "",
    nickname: person.nickname || "",
    role: person.role || "待确认角色",
    modules: Array.isArray(person.modules) ? person.modules : [],
    enabled: person.enabled !== false,
    notes: person.notes || "",
    match_status: person.confidence || person.match_status || "未找到",
    impact: person.impact || {},
  };
}

function splitAliasInput(text) {
  return String(text || "")
    .split(/[,\s，、\n]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function addPeopleAliases(aliases) {
  const next = new Set(state.peopleAliases || []);
  aliases.forEach((alias) => {
    if (!looksLikeRawWxid(alias)) next.add(alias);
  });
  state.peopleAliases = Array.from(next);
  renderPeopleAliasChips();
}

function renderPeopleAliasChips() {
  const container = document.querySelector("#peopleAliasChips");
  if (!container) return;
  container.innerHTML = state.peopleAliases.length
    ? state.peopleAliases.map((alias) => `
      <span class="selected-chip">
        ${escapeHtml(alias)}
        <button type="button" data-remove-people-alias="${escapeAttr(alias)}" aria-label="移除 ${escapeAttr(alias)}">×</button>
      </span>
    `).join("")
    : '<span class="selected-chip-empty">还没有别名标签</span>';
}

function looksLikeRawWxid(value) {
  return /^wxid[_-]/i.test(String(value || ""));
}

function maskedWxid(value) {
  const text = String(value || "");
  if (!text) return "";
  return "已脱敏内部 ID";
}

function setPeopleMatchResult(status, message, details = "") {
  const container = document.querySelector("#peopleMatchResult");
  if (!container) return;
  const className = status === "已匹配" ? "" : status === "可能是" ? "maybe" : "missing";
  container.innerHTML = `
    <span class="confidence-tag ${className}">${escapeHtml(status)}</span>
    <strong>${escapeHtml(message)}</strong>
    <small>${escapeHtml(details || "如果后端暂未提供匹配来源，可以先人工补齐字段再保存。")}</small>
  `;
}

function formatPeopleDownstreamStatus(status = {}) {
  if (!status || !Object.keys(status).length) return peopleImpactText;
  const parts = [
    `身份库 ${status.people_count ?? status.people_library_count ?? 0} 人`,
    `别名 ${status.alias_count ?? 0} 个`,
    `发送人匹配 ${status.sender_match_count ?? status.local_sender_count ?? 0} 条`,
    `群成员下拉 ${status.group_option_count ?? status.monitor_group_count ?? 0} 项`,
    status.candidate_status || "候选事项会读取同一身份库",
    status.daily_status || "日报会读取同一身份库",
    status.transfer_status || "转述摘要会读取同一身份库",
  ];
  return `保存后影响：${parts.filter(Boolean).join("｜")}`;
}

function syncConfigPeopleFromInternalApi(people = []) {
  if (!state.configCenter?.editable) return;
  state.configCenter.editable.internal_people = people.map((person) => ({
    person_name: person.person_name || person.name || "",
    aliases: person.aliases || person.common_names || [],
    wechat_display_name: person.wechat_display_name || "",
    role: person.role || "我方人员",
    modules: person.modules || [],
    enabled: person.enabled !== false,
  })).filter((person) => person.person_name);
}

async function loadInternalPeoplePage({ force = false, render = true } = {}) {
  if (state.internalPeople && !force) {
    if (render) renderPeoplePage();
    return state.internalPeople;
  }
  try {
    const data = await api("/api/internal-people");
    state.internalPeople = data;
    syncConfigPeopleFromInternalApi(data.people || []);
    const impact = data.downstream_status || data.impact || {};
    const source = data.suggestion_sources || {};
	    document.querySelector("#peopleApiStatus").textContent =
	      `我方人员接口：${humanStatusText(data.status || "ok")}｜身份 ${data.count || 0} 人｜本地发送人 ${source.local_sender_count || 0} 个｜监控群 ${source.monitor_group_count || 0} 个｜roster 成员源 ${source.roster_member_count || 0} 个`;
	    document.querySelector("#peopleImpactScope").textContent = formatPeopleDownstreamStatus(impact);
	    if (render) renderPeoplePage();
	    renderWindowsReadiness();
	    return data;
	  } catch (_error) {
	    if (render) {
	      document.querySelector("#peopleApiStatus").textContent = "我方人员接口暂不可用；页面不会触发真实读取。";
	      document.querySelector("#peoplePageResult").textContent = "我方人员后端接口暂不可用；请稍后刷新。";
	      renderPeoplePage();
	    }
	    renderWindowsReadiness();
	    return null;
	  }
}

async function requestPeopleSuggestions(payload) {
  const params = new URLSearchParams();
  Object.entries(payload).forEach(([key, value]) => {
    if (value !== undefined && value !== null && String(value).trim()) params.set(key, String(value).trim());
  });
  try {
    const response = await fetch(`/api/internal-people/suggestions?${params.toString()}`, {
      headers: { "Content-Type": "application/json" },
    });
    if (response.ok) return response.json();
  } catch (_error) {
    // Fall through to the deployed POST contract.
  }
  return api("/api/internal-people/suggestions", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

function applyPeopleSuggestion(person, status = "") {
  resetPeopleForm({
    ...normalizePersonForPage(person || {}),
    match_status: status || person?.confidence || person?.match_status || "可能是",
  });
}

function resetPeopleForm(person = {}) {
  state.editingPeopleIndex = Number.isInteger(person.index) ? person.index : null;
  state.editingPersonId = person.person_id || "";
  state.peopleAliases = Array.isArray(person.aliases) ? [...person.aliases] : [];
  document.querySelector("#peoplePersonNameInput").value = person.person_name || "";
  document.querySelector("#peopleWechatDisplayInput").value = person.wechat_display_name || "";
  document.querySelector("#peopleNicknameInput").value = person.nickname || "";
  document.querySelector("#peopleNotesInput").value = person.notes || "";
  document.querySelector("#peopleEnabledCheckbox").checked = person.enabled !== false;
  setOptions(document.querySelector("#peopleRoleSelect"), peopleRoleOptions, person.role || "待确认角色", { allowEmpty: false });
  setOptions(document.querySelector("#peopleModulesSelect"), peopleModuleOptions, person.modules || [], { multiple: true, allowEmpty: false });
  renderPeopleAliasChips();
  setPeopleMatchResult(person.match_status || "未找到", person.person_name ? "已带入身份字段，可继续确认后保存。" : "请选择一种方式开始识别。", peopleImpactText);
}

function peopleCandidates() {
  if (state.internalPeople?.people) {
    return state.internalPeople.people.map(normalizePersonForPage);
  }
  return (state.configCenter?.editable?.internal_people || []).map(normalizePersonForPage);
}

function matchExistingPerson(input) {
  const value = String(input || "").trim();
  if (!value) return null;
  return peopleCandidates().find((person) =>
    person.person_name === value
    || person.wechat_display_name === value
    || person.aliases.includes(value)
  ) || peopleCandidates().find((person) =>
    [person.person_name, person.wechat_display_name, ...(person.aliases || [])].some((item) => item && item.includes(value))
  );
}

function peopleLookupRaw(type) {
  return type === "wxid"
    ? document.querySelector("#peopleLookupWxid").value.trim()
    : document.querySelector("#peopleLookupDisplayName").value.trim();
}

function schedulePeopleSuggestion(type) {
  clearTimeout(state.peopleSuggestionTimer);
  const raw = peopleLookupRaw(type);
  if (!raw) {
    setPeopleMatchResult("未找到", "请选择一种方式开始识别。", peopleImpactText);
    return;
  }
  if (raw.length < 2 && type !== "wxid") {
    setPeopleMatchResult("可能是", "继续输入后会自动查找建议。", "不会触发真实消息读取。");
    return;
  }
  setPeopleMatchResult("可能是", "正在准备自动补齐建议。", "输入停顿后会查询我方人员建议接口。");
  state.peopleSuggestionTimer = setTimeout(() => {
    matchPeopleFromInput(type, { auto: true });
  }, 550);
}

async function matchPeopleFromInput(type, { auto = false } = {}) {
  clearTimeout(state.peopleSuggestionTimer);
  const raw = type === "wxid"
    ? document.querySelector("#peopleLookupWxid").value.trim()
    : document.querySelector("#peopleLookupDisplayName").value.trim();
  if (!raw) {
    if (!auto) setPeopleMatchResult("未找到", "请先输入微信号或微信显示名。");
    return;
  }
  setPeopleMatchResult("可能是", "正在从我方人员接口查找建议。", "只读取身份建议和 count/status，不触发真实消息读取。");
  try {
    const result = await requestPeopleSuggestions(type === "wxid" ? { wechat_id: raw } : { display_name: raw });
    if (result.requires_display_name || result.status === "requires_display_name") {
      document.querySelector("#peopleWechatDisplayInput").value = "";
      setPeopleMatchResult("未找到", "未识别到名字，请补一个显示名。", "后端只拿到内部标识，不能保存成用户看不懂的 ID。");
      document.querySelector("#peopleImpactScope").textContent = formatPeopleDownstreamStatus(result.source_summary || {});
      return;
    }
    const suggestion = (result.suggestions || [])[0];
    document.querySelector("#peopleImpactScope").textContent = formatPeopleDownstreamStatus(suggestion?.impact || result.source_summary || {});
    if (suggestion) {
      applyPeopleSuggestion(suggestion, suggestion.confidence || (result.count ? "可能是" : "未找到"));
      setPeopleMatchResult(suggestion.confidence || "可能是", `已从后端建议带入 ${suggestion.person_name || suggestion.wechat_display_name || "身份字段"}。`, `${suggestion.source_label || "本地可见来源"}｜${formatPeopleDownstreamStatus(suggestion.impact || {})}`);
      return;
    }
  } catch (_error) {
    setPeopleMatchResult("可能是", "后端建议暂不可用，已使用本页已有身份兜底。", "稍后可刷新我方人员页重试。");
  }
  if (type === "wxid" && looksLikeRawWxid(raw)) {
    document.querySelector("#peopleWechatDisplayInput").value = "";
    setPeopleMatchResult("未找到", "未识别到名字，请补一个显示名。", `收到的是脱敏 ID：${maskedWxid(raw)}。不能把 ID 当作主名称保存。`);
    return;
  }
  const matched = matchExistingPerson(raw);
  if (matched) {
    resetPeopleForm({ ...matched, match_status: matched.person_name === raw || matched.wechat_display_name === raw ? "已匹配" : "可能是" });
    setPeopleMatchResult(matched.person_name === raw || matched.wechat_display_name === raw ? "已匹配" : "可能是", `已带入 ${matched.person_name} 的配置。`, peopleImpactText);
    return;
  }
  document.querySelector("#peopleWechatDisplayInput").value = raw;
  if (!document.querySelector("#peoplePersonNameInput").value.trim()) {
    document.querySelector("#peoplePersonNameInput").value = raw;
  }
  addPeopleAliases([raw]);
  setPeopleMatchResult("未找到", "没有找到已保存身份，已按输入内容预填。", "请补齐姓名、角色和负责模块后保存。");
}

function renderPeopleRecentSenderOptions() {
  const select = document.querySelector("#peopleRecentSenderSelect");
  if (!select) return;
  const senders = state.realTrialSenders || [];
  select.innerHTML = senders.length
    ? senders.map((sender, index) => `<option value="${index}">${escapeHtml(sender.sender_display_name || `发送人 ${index + 1}`)}｜${escapeHtml(identityLabel(sender.sender_identity))}</option>`).join("")
    : '<option value="">暂无最近发送人</option>';
}

function useRecentSenderForPeople() {
  const index = Number(document.querySelector("#peopleRecentSenderSelect").value);
  const sender = (state.realTrialSenders || [])[index];
  if (!sender) {
    setPeopleMatchResult("未找到", "还没有最近发送人可选。", "如果后端暂未提供最近发送人，请先用微信显示名手动识别。");
    return;
  }
  const name = sender.sender_display_name || "";
  document.querySelector("#peopleWechatDisplayInput").value = name;
  if (!document.querySelector("#peoplePersonNameInput").value.trim()) {
    document.querySelector("#peoplePersonNameInput").value = name;
  }
  addPeopleAliases([name]);
  document.querySelector("#peopleLookupDisplayName").value = name;
  matchPeopleFromInput("display_name");
}

function editPeopleFromList(index) {
  const person = peopleCandidates()[index];
  if (!person) return;
  resetPeopleForm(person);
}

function renderPeoplePage() {
  const container = document.querySelector("#peoplePageRows");
  if (!container || (!state.configCenter && !state.internalPeople)) return;
  setOptions(document.querySelector("#peopleRoleSelect"), peopleRoleOptions, document.querySelector("#peopleRoleSelect").value || "待确认角色", { allowEmpty: false });
  setOptions(document.querySelector("#peopleModulesSelect"), peopleModuleOptions, selectedValues(document.querySelector("#peopleModulesSelect")), { multiple: true, allowEmpty: false });
  renderPeopleRecentSenderOptions();
  renderPeopleAliasChips();
  if (!document.querySelector("#peopleMatchResult").textContent.trim()) {
    setPeopleMatchResult("未找到", "请选择一种方式开始识别。", peopleImpactText);
  }
  const people = peopleCandidates();
  container.innerHTML = people.length
    ? people.map((person, index) => `
      <div class="people-row">
        <strong>${escapeHtml(person.person_name)}</strong>
        <span>${escapeHtml(person.wechat_display_name || "待补显示名")}</span>
        <span>${escapeHtml(person.role || "待确认角色")}</span>
        <small>${escapeHtml(person.aliases.length)} 个别名</small>
        <small>${escapeHtml(person.match_status || "未找到")}</small>
        <small>${person.enabled ? "启用" : "停用"}</small>
        <div class="people-row-actions">
          <button type="button" data-edit-people-index="${index}">编辑</button>
          <button type="button" data-disable-person-id="${escapeAttr(person.person_id)}" ${person.person_id && person.enabled ? "" : "disabled"}>停用</button>
        </div>
      </div>
    `).join("")
    : '<div class="empty">还没有我方人员。下一步：从微信显示名、微信号或最近发送人开始识别。</div>';
}

async function savePeoplePage() {
  await ensureConfigCenterLoaded();
  const personName = document.querySelector("#peoplePersonNameInput").value.trim();
  const displayName = document.querySelector("#peopleWechatDisplayInput").value.trim();
  const rawWechatId = document.querySelector("#peopleLookupWxid").value.trim();
  if (!personName) {
    document.querySelector("#peoplePageResult").textContent = "请先填写人员姓名。";
    return;
  }
  if (!displayName && looksLikeRawWxid(rawWechatId)) {
    document.querySelector("#peoplePageResult").textContent = "未识别到名字，请补一个显示名后再保存。";
    return;
  }
  const aliases = Array.from(new Set([
    ...state.peopleAliases,
    displayName,
    document.querySelector("#peopleNicknameInput").value.trim(),
  ].filter(Boolean).filter((alias) => !looksLikeRawWxid(alias))));
  const payload = {
    person_name: personName,
    wechat_display_name: displayName,
    wechat_id: rawWechatId && looksLikeRawWxid(rawWechatId) ? rawWechatId : "",
    aliases,
    common_names: aliases,
    role: document.querySelector("#peopleRoleSelect").value,
    modules: selectedValues(document.querySelector("#peopleModulesSelect")),
    enabled: document.querySelector("#peopleEnabledCheckbox").checked,
    notes: document.querySelector("#peopleNotesInput").value.trim(),
  };
  try {
    const endpoint = state.editingPersonId
      ? `/api/internal-people/${encodeURIComponent(state.editingPersonId)}`
      : "/api/internal-people";
    const result = await api(endpoint, {
      method: state.editingPersonId ? "PUT" : "POST",
      body: JSON.stringify(payload),
    });
    if (result.status === "blocked" || result.requires_display_name) {
      document.querySelector("#peoplePageResult").textContent = result.message || "未识别到名字，请补一个显示名后再保存。";
      return;
    }
    state.internalPeople = null;
    await loadInternalPeoplePage({ force: true, render: true });
    const impactText = formatPeopleDownstreamStatus(result.downstream_status || result.person?.impact || {});
    document.querySelector("#peopleImpactScope").textContent = impactText;
    document.querySelector("#peoplePageResult").textContent = `已保存到我方人员接口。${impactText}`;
  } catch (_error) {
    document.querySelector("#peoplePageResult").textContent = "保存暂不可用，请稍后重试；不会触发真实读取。";
  }
  state.editingPeopleIndex = null;
  state.editingPersonId = "";
  renderPeoplePage();
  renderMonitoringGroups();
}

async function disablePeopleFromList(personId) {
  if (!personId) {
    document.querySelector("#peoplePageResult").textContent = "该人员暂缺后端 ID，请先保存后再停用。";
    return;
  }
  try {
    const result = await api(`/api/internal-people/${encodeURIComponent(personId)}/disable`, {
      method: "POST",
      body: "{}",
    });
    state.internalPeople = null;
    await loadInternalPeoplePage({ force: true, render: true });
    const impactText = formatPeopleDownstreamStatus(result.downstream_status || result.person?.impact || {});
    document.querySelector("#peopleImpactScope").textContent = impactText;
    document.querySelector("#peoplePageResult").textContent = `已停用该身份。${impactText}`;
  } catch (_error) {
    document.querySelector("#peoplePageResult").textContent = "停用暂不可用，请稍后重试；不会触发真实读取。";
  }
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

function setDailyGenerationState(active, message = "") {
  state.generatingDailyReport = active;
  if (active) {
    state.dailyGenerationStatus = "running";
    state.dailyGenerationFeedback = message;
  } else if (state.dailyGenerationStatus === "running" && !message) {
    state.dailyGenerationStatus = "";
  }
  ["#topGenerateDraftBtn", "#dailyReportRegenerateInlineBtn", "#dailyReportEmptyGenerateBtn", "#regenerateDraftReportBtn"].forEach((selector) => {
    const button = document.querySelector(selector);
    if (!button) return;
    button.disabled = active;
    if (active) {
      button.dataset.idleText = button.dataset.idleText || button.textContent;
      button.textContent = "生成中...";
    } else if (button.dataset.idleText) {
      button.textContent = button.dataset.idleText;
    }
  });
  const meta = document.querySelector("#dailyReportMetaLine");
  if (meta && message) meta.textContent = message;
  const empty = document.querySelector("#dailyReportEmpty");
  if (empty && !empty.classList.contains("hidden") && message) {
    empty.querySelector("p").textContent = message;
  }
  renderWindowsReadiness();
}

async function regenerateDraftReport() {
  if (state.generatingDailyReport) return;
  const controlDate = document.querySelector("#filterDate").value || today;
  const source = document.querySelector("#draftDataSourceChoice")?.value || preferredDataSourceValue();
  setDailyGenerationState(true, "生成中：正在整理候选和日报正文，旧日报会保留到新版完成。");
  try {
    const data = await api("/api/daily-control/draft-preview", {
      method: "POST",
      body: JSON.stringify({ control_date: controlDate, data_source: source }),
    });
    if (document.querySelector("#draftDataSourceChoice") && data.data_source) {
      document.querySelector("#draftDataSourceChoice").value = data.data_source;
    }
    renderDraftReportPreview(data);
    await refreshDailyControl();
  } catch (_error) {
    state.dailyGenerationStatus = "failed";
    state.dailyGenerationFeedback = "生成失败：请确认本地服务正常，稍后重试；旧日报已保留。";
    document.querySelector("#dailyReportMetaLine").textContent =
      "生成失败：请确认本地服务正常，稍后重试；旧日报已保留。";
    document.querySelector("#draftReportMeta").textContent =
      "生成失败：请确认本地服务正常，稍后重试；不会写正式区。";
    renderWindowsReadiness();
  } finally {
    setDailyGenerationState(false);
  }
}

function renderDraftReportPreview(data) {
  state.dailyDraftPreview = data;
  if (data.generated_at || data.local_preview_saved) {
    state.dailyGenerationStatus = "success";
    state.dailyGenerationFeedback = "日报已生成；旧日报已由新版预览接替。";
  }
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
  if (state.activePage === "group-management") {
    ensureMonitorGroupsLoaded();
  }
  if (state.activePage === "people") {
    ensureConfigCenterLoaded().then(() => loadInternalPeoplePage({ force: true })).catch(() => renderPeoplePage());
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
} else if (state.activePage === "group-management") {
  ensureMonitorGroupsLoaded();
} else {
  ensureConfigCenterLoaded();
  ensureMonitorGroupsLoaded();
}
applyTransferTask(state.transferTask, { skipPreview: true });
refreshStatus().then(loadItems).then(refreshDailyControl).then(refreshInboxV1);
refreshRealTrialSummary();
refreshRealTrialMessages();
loadInternalPeoplePage({ render: false }).then(() => renderWindowsReadiness());
