const state = {
  apiBase: initialApiBase(),
  token: localStorage.getItem("salesAiToken") || "",
  user: JSON.parse(localStorage.getItem("salesAiUser") || "null"),
  view: "dashboard",
  leadIntent: "高意向",
  previewObjectUrls: [],
};

function initialApiBase() {
  const saved = localStorage.getItem("salesAiApiBase");
  if (!saved) return defaultApiBase();
  try {
    const url = new URL(saved);
    const isLocalStaticServer = ["127.0.0.1", "localhost"].includes(url.hostname) && url.port === "8080";
    return isLocalStaticServer ? `${url.protocol}//${url.hostname}:8000` : saved;
  } catch {
    return defaultApiBase();
  }
}

function defaultApiBase() {
  if (window.SALES_AI_API_BASE) return window.SALES_AI_API_BASE;
  if (window.location.protocol === "http:" || window.location.protocol === "https:") {
    if (["127.0.0.1", "localhost"].includes(window.location.hostname) && window.location.port === "8080") {
      return `${window.location.protocol}//${window.location.hostname}:8000`;
    }
    return window.location.origin;
  }
  return "http://127.0.0.1:8000";
}

const demoCustomers = [
  {
    id: "demo-1",
    name: "王先生",
    phone: "13800000000",
    intent_level: "高意向",
    intent_score: 86,
    demand_summary: "询问价格、安装时间和优惠政策",
    next_action: "今天电话跟进，重点确认预算和交付时间",
  },
  {
    id: "demo-2",
    name: "李女士",
    phone: "13900000000",
    intent_level: "中意向",
    intent_score: 62,
    demand_summary: "正在对比方案，关心售后",
    next_action: "发送案例和售后说明，明天下午回访",
  },
  {
    id: "demo-3",
    name: "周先生",
    phone: "13700001111",
    intent_level: "低意向",
    intent_score: 28,
    demand_summary: "先看看产品资料，暂时没有预算",
    next_action: "发送基础资料，月底再回访",
  },
  {
    id: "demo-4",
    name: "孙女士",
    phone: "13600002222",
    intent_level: "暂无意向",
    intent_score: 0,
    demand_summary: "今年不考虑，明年再看",
    next_action: "暂缓跟进，保留客户信息",
  },
  {
    id: "demo-5",
    name: "未命名客户",
    phone: "",
    intent_level: "无法判断",
    intent_score: 0,
    demand_summary: "资料内容不足，无法判断购买意向",
    next_action: "补充微信截图或录音后重新分析",
  },
];

const demoUploads = [
  { id: "demo-u1", file_name: "微信聊天截图.jpg", file_type: "image", status: "completed", customer_id: "demo-1", created_at: new Date().toISOString() },
  { id: "demo-u2", file_name: "电话录音.mp3", file_type: "audio", status: "completed", customer_id: "demo-2", created_at: new Date().toISOString() },
];

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));

const views = {
  dashboard: { title: "销售 AI 线索雷达", el: $("#dashboardView"), load: loadDashboard },
  customers: { title: "客户池", el: $("#customersView"), load: loadCustomers },
  uploads: { title: "资料分析", el: $("#uploadsView"), load: loadUploads },
  leads: { title: "意向线索", el: $("#leadsView"), load: loadLeads },
  users: { title: "销售账号", el: $("#usersView"), load: loadUsers },
};

document.addEventListener("DOMContentLoaded", () => {
  $("#apiBase").value = state.apiBase;
  $("#todayText").textContent = new Date().toLocaleDateString("zh-CN", {
    year: "numeric",
    month: "long",
    day: "numeric",
    weekday: "long",
  });
  bindEvents();
  updateAuthUi();
  switchView("dashboard");
});

function bindEvents() {
  $("#loginForm").addEventListener("submit", handleLogin);
  $("#logoutBtn").addEventListener("click", logout);
  $("#railLoginBtn").addEventListener("click", openLogin);
  $("#loginOpenBtn").addEventListener("click", openLogin);
  $("#testAiBtn").addEventListener("click", testDeepSeek);
  $("#refreshBtn").addEventListener("click", () => views[state.view].load());
  $("#openUploadBtn").addEventListener("click", () => requireLogin(() => $("#uploadDialog").showModal()));
  $("#heroUploadBtn").addEventListener("click", () => requireLogin(() => $("#uploadDialog").showModal()));
  $("#uploadForm").addEventListener("submit", handleUpload);
  $("#detailDialog").addEventListener("close", clearPreviewObjectUrls);
  $("#searchCustomersBtn").addEventListener("click", loadCustomers);
  $("#searchUploadsBtn").addEventListener("click", loadUploads);
  $("#createUserForm").addEventListener("submit", handleCreateUser);
  $("#userKeyword").addEventListener("input", () => state.token && state.user?.role === "admin" && loadUsers());
  $$("[data-dashboard-intent]").forEach((card) => {
    card.addEventListener("click", () => {
      state.leadIntent = card.dataset.dashboardIntent;
      switchView("leads");
    });
  });
  $$("#leadIntentTabs .segment").forEach((button) => {
    button.addEventListener("click", () => {
      state.leadIntent = button.dataset.intent;
      loadLeads();
    });
  });

  $$("[data-open-login]").forEach((button) => button.addEventListener("click", openLogin));
  $$(".nav-btn").forEach((button) => button.addEventListener("click", () => switchView(button.dataset.view)));
  $$("[data-view-link]").forEach((button) => button.addEventListener("click", () => switchView(button.dataset.viewLink)));
  $$("[data-close]").forEach((button) => button.addEventListener("click", () => $(`#${button.dataset.close}`).close()));
}

async function handleLogin(event) {
  event.preventDefault();
  hideLoginError();
  state.apiBase = $("#apiBase").value.trim().replace(/\/$/, "");
  localStorage.setItem("salesAiApiBase", state.apiBase);

  try {
    const result = await api("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({
        username: $("#loginUsername").value.trim(),
        password: $("#loginPassword").value,
      }),
      auth: false,
    });
    state.token = result.access_token;
    state.user = result.user;
    localStorage.setItem("salesAiToken", state.token);
    localStorage.setItem("salesAiUser", JSON.stringify(state.user));
    $("#loginDialog").close();
    updateAuthUi();
    showNotice("登录成功，已切换为真实数据。", "ok");
    await views[state.view].load();
  } catch (error) {
    showLoginError(readableError(error));
  }
}

function updateAuthUi() {
  const isLogin = Boolean(state.token && state.user);
  $("#accountName").textContent = isLogin ? state.user.name : "未登录";
  $("#accountHint").textContent = isLogin ? (state.user.role === "admin" ? "管理员可查看全部数据。" : "销售只能查看自己的线索。") : "可以先浏览示例，登录后查看真实数据。";
  $("#userRole").textContent = isLogin ? (state.user.role === "admin" ? "管理员" : "销售") : "未登录";
  $("#loginOpenBtn").hidden = isLogin;
  $("#railLoginBtn").hidden = isLogin;
  $("#logoutBtn").hidden = !isLogin;
  $("#modeBanner").hidden = isLogin;
  $("#connectionPill").textContent = isLogin ? "真实数据" : "示例浏览";
  document.querySelector('[data-view="users"]').style.display = isLogin && state.user.role === "admin" ? "" : "none";
}

function logout() {
  localStorage.removeItem("salesAiToken");
  localStorage.removeItem("salesAiUser");
  state.token = "";
  state.user = null;
  updateAuthUi();
  switchView("dashboard");
  showNotice("已退出登录，当前显示示例数据。", "ok");
}

function openLogin() {
  hideLoginError();
  $("#apiBase").value = state.apiBase;
  $("#loginDialog").showModal();
}

function requireLogin(action) {
  if (state.token) {
    action();
    return true;
  }
  showNotice("这个操作需要登录。你可以先看示例，再登录使用真实数据。");
  openLogin();
  return false;
}

function switchView(name) {
  if (name === "users" && (!state.user || state.user.role !== "admin")) {
    showNotice("销售账号管理需要管理员登录。");
    openLogin();
    return;
  }
  state.view = name;
  Object.entries(views).forEach(([key, view]) => view.el.classList.toggle("active-view", key === name));
  $$(".nav-btn").forEach((button) => button.classList.toggle("active", button.dataset.view === name));
  $("#viewTitle").textContent = views[name].title;
  hideNotice();
  views[name].load();
}

async function loadDashboard() {
  if (!state.token) return renderDashboardDemo();
  try {
    const [stats, priorities, uploads] = await Promise.all([
      api("/api/dashboard/stats"),
      api("/api/dashboard/followup-priorities?limit=5"),
      api("/api/uploads?page_size=5"),
    ]);
    const counts = {
      高意向: stats.intent_distribution?.["高意向"] ?? 0,
      中意向: stats.intent_distribution?.["中意向"] ?? 0,
      低意向: stats.intent_distribution?.["低意向"] ?? 0,
      暂无意向: stats.intent_distribution?.["暂无意向"] ?? 0,
      无法判断: stats.intent_distribution?.["无法判断"] ?? 0,
    };
    renderIntentMetrics(counts);
    renderLeadStack($("#dashboardLeads"), priorities);
    renderTimeline($("#dashboardUploads"), uploads.items);
  } catch (error) {
    showNotice(readableError(error));
    renderIntentMetrics(null);
  }
}

function renderDashboardDemo() {
  renderIntentMetrics({
    高意向: 24,
    中意向: 48,
    低意向: 31,
    暂无意向: 12,
    无法判断: 13,
  });
  renderLeadStack($("#dashboardLeads"), demoCustomers.map((item, index) => ({
    ...item,
    next_followup_at: new Date(Date.now() + (index + 1) * 60 * 60 * 1000).toISOString(),
    followup_content: `跟进优先级：${item.intent_level === "高意向" ? "紧急跟进，建议2小时内联系" : "按节奏培育"}\n下一步建议：${item.next_action}`,
  })));
  renderTimeline($("#dashboardUploads"), demoUploads);
}

function renderIntentMetrics(counts) {
  const fallback = counts || { 高意向: "--", 中意向: "--", 低意向: "--", 暂无意向: "--", 无法判断: "--" };
  $("#metricHighIntent").textContent = fallback["高意向"];
  $("#metricMidIntent").textContent = fallback["中意向"];
  $("#metricLowIntent").textContent = fallback["低意向"];
  $("#metricNoIntent").textContent = fallback["暂无意向"];
  $("#metricUnknownIntent").textContent = fallback["无法判断"];
}

async function loadCustomers() {
  if (!state.token) {
    $("#customersTable").innerHTML = demoCustomers.map(renderCustomerRow).join("");
    return;
  }
  try {
    const params = new URLSearchParams({
      page_size: "50",
      keyword: $("#customerKeyword").value.trim(),
      intent_level: $("#customerIntent").value,
    });
    const data = await api(`/api/customers?${params}`);
    $("#customersTable").innerHTML = data.items.length ? data.items.map(renderCustomerRow).join("") : emptyTableRow(6, "暂无客户。上传资料后会自动生成客户。");
  } catch (error) {
    showNotice(readableError(error));
  }
}

async function loadUploads() {
  if (!state.token) {
    $("#uploadsTable").innerHTML = demoUploads.map(renderUploadRow).join("");
    return;
  }
  try {
    const params = new URLSearchParams({
      page_size: "50",
      status: $("#uploadStatus").value,
      file_type: $("#uploadType").value,
    });
    const data = await api(`/api/uploads?${params}`);
    $("#uploadsTable").innerHTML = data.items.length ? data.items.map(renderUploadRow).join("") : emptyTableRow(6, "暂无上传记录。");
  } catch (error) {
    showNotice(readableError(error));
  }
}

async function loadLeads() {
  $$("#leadIntentTabs .segment").forEach((button) => {
    button.classList.toggle("active", button.dataset.intent === state.leadIntent);
  });
  if (!state.token) {
    $("#leadsTable").innerHTML = demoCustomers
      .filter((item) => item.intent_level === state.leadIntent)
      .map(renderLeadRow)
      .join("") || emptyTableRow(6, `暂无${state.leadIntent}客户。`);
    return;
  }
  try {
    const params = new URLSearchParams({
      page_size: "50",
      intent_level: state.leadIntent,
    });
    const data = await api(`/api/leads?${params}`);
    $("#leadsTable").innerHTML = data.items.length ? data.items.map(renderLeadRow).join("") : emptyTableRow(6, `暂无${state.leadIntent}客户。`);
  } catch (error) {
    showNotice(readableError(error));
  }
}

async function loadUsers() {
  if (!state.token || state.user?.role !== "admin") {
    $("#usersList").innerHTML = `<p class="empty">管理员登录后可以查看和新增销售账号。</p>`;
    return;
  }
  try {
    const keyword = encodeURIComponent($("#userKeyword").value.trim());
    const data = await api(`/api/users?keyword=${keyword}`);
    $("#usersList").innerHTML = data.length ? data.map(renderUserRow).join("") : `<p class="empty">暂无销售账号。</p>`;
  } catch (error) {
    showNotice(readableError(error));
  }
}

async function handleUpload(event) {
  event.preventDefault();
  if (!state.token) return openLogin();
  const form = event.currentTarget;
  try {
    const result = await api("/api/uploads", { method: "POST", body: new FormData(form), isForm: true });
    $("#uploadDialog").close();
    form.reset();
    showNotice(`上传成功，记录编号：${result.id}`, "ok");
    await views[state.view].load();
  } catch (error) {
    showNotice(readableError(error));
  }
}

async function handleCreateUser(event) {
  event.preventDefault();
  if (!state.token || state.user?.role !== "admin") return openLogin();
  const form = event.currentTarget;
  const data = Object.fromEntries(new FormData(form).entries());
  data.role = "sales";
  try {
    await api("/api/users", { method: "POST", body: JSON.stringify(data) });
    form.reset();
    showNotice("销售账号已创建。", "ok");
    await loadUsers();
  } catch (error) {
    showNotice(readableError(error));
  }
}

async function testDeepSeek() {
  if (!state.token) return openLogin();
  if (state.user?.role !== "admin") {
    showNotice("检测 AI 需要管理员账号。");
    return;
  }
  try {
    const status = await api("/api/ai/deepseek/status");
    if (!status.configured) {
      showNotice("DeepSeek Key 还没有配置。请先在后端 .env 文件填写 DEEPSEEK_API_KEY，然后重启后端。");
      return;
    }
    const result = await api("/api/ai/deepseek/test", { method: "POST" });
    showNotice(`DeepSeek 连接成功：${result.intent_level} · ${result.intent_score}`, "ok");
  } catch (error) {
    showNotice(readableError(error));
  }
}

async function showUploadDetail(id) {
  if (String(id).startsWith("demo")) return openLogin();
  if (!state.token) return openLogin();
  try {
    const upload = await api(`/api/uploads/${id}`);
    const analysis = upload.analysis;
    clearPreviewObjectUrls();
    let originalPreview = "";
    if (upload.file_type === "image") {
      try {
        const imageUrl = rememberPreviewUrl(await apiBlob(`/api/uploads/${id}/file`));
        originalPreview = `<section class="original-image-panel full">
          <span>原始图片</span>
          <a href="${esc(imageUrl)}" target="_blank" rel="noopener" title="点击查看原图">
            <img class="original-image" src="${esc(imageUrl)}" alt="${esc(upload.file_name)}" />
          </a>
        </section>`;
      } catch (error) {
        originalPreview = detailItem("原始图片", `加载失败：${esc(readableError(error))}`, true);
      }
    } else if (upload.file_type === "audio") {
      try {
        const audioUrl = rememberPreviewUrl(await apiBlob(`/api/uploads/${id}/file`));
        originalPreview = `<section class="original-audio-panel full">
          <span>原始录音</span>
          <audio class="original-audio" controls preload="metadata" src="${esc(audioUrl)}"></audio>
          <a class="media-open-link" href="${esc(audioUrl)}" target="_blank" rel="noopener">打开原始录音</a>
        </section>`;
      } catch (error) {
        originalPreview = detailItem("原始录音", `加载失败：${esc(readableError(error))}`, true);
      }
    }
    $("#detailTitle").textContent = upload.file_name;
    $("#detailContent").innerHTML = analysis
      ? `<div class="detail-grid">
          ${originalPreview}
          ${detailItem("处理状态", statusBadge(upload.status))}
          ${detailItem("文件类型", fileTypeText(upload.file_type))}
          ${detailItem("内容摘要", esc(analysis.summary || "未提及"), true)}
          ${detailItem("购买意向", intentBadge(analysis.intent_level, analysis.intent_score))}
          ${detailItem("判断理由", esc(analysis.intent_reason || "未提及"), true)}
          ${detailItem("关键证据", esc(analysis.evidence || "未提及"), true)}
          ${detailItem("客户需求", esc(analysis.customer_needs || "未提及"), true)}
          ${detailItem("推荐话术", esc(analysis.sales_script || "未提及"), true)}
          ${detailItem("原始识别文字", esc(analysis.raw_text || "未提及"), true)}
        </div>`
      : `<p class="empty">该记录还在处理中，请稍后刷新。</p>`;
    if (!$("#detailDialog").open) $("#detailDialog").showModal();
  } catch (error) {
    showNotice(readableError(error));
  }
}

function renderLeadStack(container, items) {
  container.innerHTML = items.length
    ? items.map((item) => `
      <article class="lead-card">
        <div class="lead-top">
          <div>
            <strong>${esc(item.name || item.phone || "未命名客户")}</strong>
            <p>${esc(item.demand_summary || item.followup_content || "未提及")}</p>
          </div>
          ${intentBadge(item.intent_level, item.intent_score)}
        </div>
        <div class="lead-due">${followupDueText(item.next_followup_at)} · ${esc(firstFollowupLine(item.followup_content))}</div>
        <div class="lead-actions">
          <p>${esc(item.next_action || "暂无下一步建议")}</p>
          <button class="quiet-btn" type="button" onclick="showCustomerDetail('${item.id}')">跟进</button>
        </div>
      </article>`).join("")
    : `<p class="empty">暂无待跟进客户。新截图或录音分析完成后会自动出现在这里。</p>`;
}

function firstFollowupLine(content = "") {
  const line = String(content || "").split("\n").find(Boolean);
  return line ? line.replace(/^跟进优先级：/, "") : "等待AI生成跟进建议";
}

function followupDueText(value) {
  if (!value) return "未设置提醒";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "未设置提醒";
  const diffMs = date.getTime() - Date.now();
  const absHours = Math.abs(diffMs) / 36e5;
  if (diffMs < 0) return absHours < 24 ? "已到跟进时间" : `已逾期${Math.ceil(absHours / 24)}天`;
  if (absHours < 1) return "1小时内跟进";
  if (absHours < 24) return `${Math.ceil(absHours)}小时内跟进`;
  return `${Math.ceil(absHours / 24)}天后跟进`;
}

function renderTimeline(container, items) {
  container.innerHTML = items.length
    ? items.map((item) => `
      <article class="timeline-row">
        <div><strong>${esc(item.file_name)}</strong><p>${fileTypeText(item.file_type)} · ${formatDate(item.created_at)}</p></div>
        ${statusBadge(item.status)}
      </article>`).join("")
    : `<p class="empty">暂无上传记录。</p>`;
}

function renderCustomerRow(customer) {
  return `<tr>
    <td><span class="cell-main">${esc(customer.name || "未命名客户")}</span><span class="cell-sub">ID ${customer.id}</span></td>
    <td>${phoneLink(customer.phone)}</td>
    <td>${intentBadge(customer.intent_level, customer.intent_score)}</td>
    <td><span class="cell-main">${esc(customer.demand_summary || "未提及")}</span></td>
    <td><span class="cell-main">${esc(customer.next_action || "未提及")}</span></td>
    <td><div class="row-actions"><button class="quiet-btn" onclick="showCustomerDetail('${customer.id}')">查看</button></div></td>
  </tr>`;
}

function renderUploadRow(upload) {
  return `<tr>
    <td><span class="cell-main">${esc(upload.file_name)}</span><span class="cell-sub">ID ${upload.id}</span></td>
    <td>${fileTypeText(upload.file_type)}</td>
    <td>${statusBadge(upload.status)}</td>
    <td>${upload.customer_id ? `客户 ${upload.customer_id}` : "未归档"}</td>
    <td>${formatDate(upload.created_at)}</td>
    <td><div class="row-actions"><button class="quiet-btn" onclick="showUploadDetail('${upload.id}')">分析</button><button class="quiet-btn" onclick="reanalyzeUpload('${upload.id}')">重跑</button></div></td>
  </tr>`;
}

function renderLeadRow(customer) {
  return `<tr>
    <td><span class="cell-main">${esc(customer.name || "未命名客户")}</span></td>
    <td>${phoneLink(customer.phone)}</td>
    <td>${intentBadge(customer.intent_level, customer.intent_score)}</td>
    <td><span class="cell-main">${esc(customer.demand_summary || "未提及")}</span></td>
    <td><span class="cell-main">${esc(customer.next_action || "未提及")}</span></td>
    <td><div class="row-actions"><button class="quiet-btn" onclick="showCustomerDetail('${customer.id}')">跟进</button></div></td>
  </tr>`;
}

function renderUserRow(user) {
  return `<article class="user-row">
    <div><strong>${esc(user.name)}</strong><p>${esc(user.username)} · ${esc(user.phone || "未填手机号")}</p></div>
    <span class="badge ${user.status === "active" ? "ok" : "none"}">${user.status === "active" ? "启用" : "停用"}</span>
  </article>`;
}

function detailItem(label, value, full = false) {
  return `<section class="detail-item ${full ? "full" : ""}"><span>${label}</span><p>${value}</p></section>`;
}

function emptyTableRow(colspan, text) {
  return `<tr><td colspan="${colspan}" class="empty">${text}</td></tr>`;
}

function intentBadge(level, score = 0) {
  const cls = level === "高意向" ? "high" : level === "中意向" ? "mid" : level === "低意向" ? "low" : level === "暂无意向" ? "none" : "unknown";
  return `<span class="badge ${cls}">${esc(level || "无法判断")} · ${score ?? 0}</span>`;
}

function statusBadge(status) {
  const cls = status === "completed" ? "ok" : status === "failed" ? "none" : "wait";
  return `<span class="badge ${cls}">${statusText(status)}</span>`;
}

function statusText(status) {
  return { pending: "待处理", processing: "处理中", completed: "已完成", failed: "失败" }[status] || status || "未知";
}

function fileTypeText(type) {
  return { image: "图片", audio: "录音", document: "文档", unknown: "其他" }[type] || type || "其他";
}

function phoneLink(phone) {
  if (!phone) return "未提及";
  const dialNumber = normalizeDialNumber(phone);
  if (!dialNumber) return esc(phone);
  return `<span class="phone-actions">
    <a class="call-link" href="tel:${esc(dialNumber)}" onclick="showDialHint('${esc(dialNumber)}')">${esc(phone)}</a>
    <a class="dial-button" href="tel:${esc(dialNumber)}" onclick="showDialHint('${esc(dialNumber)}')">一键拨号</a>
  </span>`;
}

function normalizeDialNumber(phone) {
  const value = String(phone || "").trim();
  const prefix = value.startsWith("+") ? "+" : "";
  const body = value.replace(/[^0-9*#]/g, "");
  return body ? `${prefix}${body}` : "";
}

function showDialHint(phone) {
  showNotice(`正在调起系统拨号：${phone}`, "ok");
}

function formatDate(value) {
  if (!value) return "";
  return new Date(value).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}

function showNotice(message, type = "error") {
  const box = $("#alertBox");
  box.hidden = false;
  box.textContent = message;
  box.style.color = type === "ok" ? "var(--green)" : "var(--red)";
  box.style.background = type === "ok" ? "#eefbf4" : "#fff6f4";
  box.style.borderColor = type === "ok" ? "#ccebd8" : "#ffd6cf";
}

function hideNotice() {
  $("#alertBox").hidden = true;
}

function showLoginError(message) {
  $("#loginError").textContent = message;
  $("#loginError").hidden = false;
}

function hideLoginError() {
  $("#loginError").hidden = true;
}

function readableError(error) {
  const message = error.message || String(error);
  if (message.includes("Failed to fetch")) return "连接不到后端。请确认后端已经启动，并且地址是 http://127.0.0.1:8000。";
  return message;
}

async function api(path, options = {}) {
  const headers = options.isForm ? {} : { "Content-Type": "application/json" };
  if (options.auth !== false && state.token) headers.Authorization = `Bearer ${state.token}`;
  const response = await fetch(`${state.apiBase}${path}`, { ...options, headers: { ...headers, ...(options.headers || {}) } });
  const text = await response.text();
  let data = null;
  if (text) {
    try { data = JSON.parse(text); } catch { data = text; }
  }
  if (!response.ok) {
    const message = typeof data === "object" && data?.detail ? data.detail : `请求失败：${response.status}`;
    throw new Error(message);
  }
  return data;
}

async function apiBlob(path) {
  const headers = {};
  if (state.token) headers.Authorization = `Bearer ${state.token}`;
  const response = await fetch(`${state.apiBase}${path}`, { headers });
  if (!response.ok) {
    let message = `请求失败：${response.status}`;
    try {
      const data = await response.json();
      if (data?.detail) message = data.detail;
    } catch {}
    throw new Error(message);
  }
  return response.blob();
}

function rememberPreviewUrl(blob) {
  const url = URL.createObjectURL(blob);
  state.previewObjectUrls.push(url);
  return url;
}

function clearPreviewObjectUrls() {
  state.previewObjectUrls.forEach((url) => URL.revokeObjectURL(url));
  state.previewObjectUrls = [];
}

function esc(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

window.showUploadDetail = showUploadDetail;
window.reanalyzeUpload = reanalyzeUpload;
window.showDialHint = showDialHint;

async function reanalyzeUpload(id) {
  if (String(id).startsWith("demo")) return openLogin();
  if (!state.token) return openLogin();
  try {
    const result = await api(`/api/uploads/${id}/reanalyze`, { method: "POST" });
    showNotice(`已重新分析，记录编号：${result.id}`, "ok");
    await loadUploads();
  } catch (error) {
    showNotice(readableError(error));
  }
}

async function showCustomerDetail(id) {
  if (String(id).startsWith("demo")) return openLogin();
  if (!state.token) return openLogin();
  try {
    const [customer, records, followups] = await Promise.all([
      api(`/api/customers/${id}`),
      api(`/api/customers/${id}/records`),
      api(`/api/customers/${id}/followups`),
    ]);

    $("#detailTitle").textContent = customer.name || customer.phone || `客户 ${customer.id}`;
    $("#detailContent").innerHTML = `
      <section class="customer-profile">
        <div class="profile-main">
          <span class="panel-kicker">客户档案</span>
          <h2>${esc(customer.name || "未命名客户")}</h2>
          <p>${phoneLink(customer.phone)} · ${esc(customer.source || "AI上传")}</p>
        </div>
        <div class="profile-score">
          ${intentBadge(customer.intent_level, customer.intent_score)}
          <span>当前意向</span>
        </div>
      </section>

      <section class="detail-grid">
        ${detailItem("客户需求", esc(customer.demand_summary || "未提及"), true)}
        ${detailItem("疑问/异议", esc(customer.concerns || "未提及"), true)}
        ${detailItem("关注产品", esc(customer.product_interest || "未提及"))}
        ${detailItem("预算", esc(customer.budget || "未提及"))}
        ${detailItem("购买时间", esc(customer.purchase_time || "未提及"))}
        ${detailItem("下一步建议", esc(customer.next_action || "未提及"), true)}
      </section>

      <section class="detail-section">
        <div class="section-title">
          <h3>历史资料和 AI 判断</h3>
          <span>${records.length} 条</span>
        </div>
        <div class="record-list">${renderRecordCards(records)}</div>
      </section>

      <section class="detail-section">
        <div class="section-title">
          <h3>AI自动跟进</h3>
          <span>${followups.length} 条</span>
        </div>
        <form class="followup-form" onsubmit="submitCustomerMaterial(event, '${customer.id}', '${esc(customer.phone || "")}', '${esc(customer.name || "")}')">
          <label>
            <span>上传微信图片/聊天截图/客户资料</span>
            <input name="file" type="file" accept="image/*,.jpg,.jpeg,.png,.webp,.bmp,.txt,.md,.csv,.doc,.docx,.pdf" required />
          </label>
          <div class="followup-row">
            <label>
              <span>资料说明</span>
              <input name="note" placeholder="例如：微信报价截图、客户需求截图、合同照片" />
            </label>
            <button class="primary-btn" type="submit">上传资料并生成跟进</button>
          </div>
        </form>
        <form class="followup-form" onsubmit="submitCallRecording(event, '${customer.id}', '${esc(customer.phone || "")}')">
          <label>
            <span>上传通话录音</span>
            <input name="file" type="file" accept="audio/*,.mp3,.wav,.m4a,.flac,.ogg,.opus" required />
          </label>
          <div class="followup-row">
            <label>
              <span>客户电话</span>
              <input name="callee_phone" value="${esc(customer.phone || "")}" />
            </label>
            <button class="primary-btn" type="submit">上传录音并生成跟进</button>
          </div>
        </form>
        <form class="followup-form muted-form" onsubmit="submitManualNote(event, '${customer.id}')">
          <textarea name="content" rows="2" placeholder="补充备注：只用于人工补充，不作为主要跟进来源。" required></textarea>
          <div class="followup-row">
            <label>
              <span>提醒时间</span>
              <input name="next_followup_at" type="datetime-local" />
            </label>
            <button class="quiet-btn" type="submit">保存补充备注</button>
          </div>
        </form>
        <div class="followup-list">${renderFollowupCards(followups)}</div>
      </section>
    `;
    await hydrateRecordImagePreviews();
    if (!$("#detailDialog").open) $("#detailDialog").showModal();
  } catch (error) {
    showNotice(readableError(error));
  }
}

async function submitManualNote(event, customerId) {
  event.preventDefault();
  if (!state.token) return openLogin();
  const form = event.currentTarget;
  const content = form.content.value.trim();
  const nextFollowup = form.next_followup_at.value;
  if (!content) return;

  try {
    await api(`/api/customers/${customerId}/followups`, {
      method: "POST",
      body: JSON.stringify({
        content,
        next_followup_at: nextFollowup ? new Date(nextFollowup).toISOString() : null,
      }),
    });
    showNotice("补充备注已保存。", "ok");
    await showCustomerDetail(customerId);
  } catch (error) {
    showNotice(readableError(error));
  }
}

async function submitCallRecording(event, customerId, customerPhone) {
  event.preventDefault();
  if (!state.token) return openLogin();
  const form = event.currentTarget;
  const file = form.file.files[0];
  if (!file) return;
  const data = new FormData();
  data.append("file", file);
  data.append("customer_id", customerId);
  data.append("callee_phone", form.callee_phone.value || customerPhone || "");

  try {
    const result = await api("/api/call-recordings", {
      method: "POST",
      body: data,
      isForm: true,
    });
    showNotice(`通话录音已上传，上传记录编号：${result.upload_record_id}`, "ok");
    await showCustomerDetail(customerId);
  } catch (error) {
    showNotice(readableError(error));
  }
}

async function submitCustomerMaterial(event, customerId, customerPhone, customerName) {
  event.preventDefault();
  if (!state.token) return openLogin();
  const form = event.currentTarget;
  const file = form.file.files[0];
  if (!file) return;
  const data = new FormData();
  data.append("file", file);
  data.append("customer_id", customerId);
  data.append("customer_phone", customerPhone || "");
  data.append("customer_name", customerName || "");
  data.append("note", form.note.value || "");

  try {
    const result = await api("/api/uploads", {
      method: "POST",
      body: data,
      isForm: true,
    });
    showNotice(`客户资料已上传，AI正在分析，上传记录编号：${result.id}`, "ok");
    await showCustomerDetail(customerId);
  } catch (error) {
    showNotice(readableError(error));
  }
}

function renderRecordCards(records) {
  if (!records.length) return `<p class="empty compact-empty">暂无上传资料。</p>`;
  return records.map((record) => {
    const analysis = record.analysis;
    return `
      <article class="record-card">
        <div class="record-head">
          <div>
            <strong>${esc(record.file_name)}</strong>
            <p>${fileTypeText(record.file_type)} · ${formatDate(record.created_at)}</p>
          </div>
          ${statusBadge(record.status)}
        </div>
        ${record.file_type === "image" ? `<div class="record-image-preview" data-upload-image-id="${record.id}"><span>正在加载原始图片...</span></div>` : ""}
        ${record.file_type === "audio" ? `<div class="record-audio-preview" data-upload-audio-id="${record.id}"><span>正在加载原始录音...</span></div>` : ""}
        <div class="record-body">
          <p><b>摘要：</b>${esc(analysis?.summary || "未提及")}</p>
          <p><b>判断依据：</b>${esc(analysis?.evidence || "未提及")}</p>
          <p><b>推荐话术：</b>${esc(analysis?.sales_script || "未提及")}</p>
        </div>
        <div class="record-actions">
          <button class="quiet-btn" type="button" onclick="showUploadDetail('${record.id}')">查看分析</button>
          <button class="quiet-btn" type="button" onclick="reanalyzeUpload('${record.id}')">重新分析</button>
        </div>
      </article>
    `;
  }).join("");
}

async function hydrateRecordImagePreviews() {
  const imageContainers = Array.from(document.querySelectorAll("[data-upload-image-id]"));
  const audioContainers = Array.from(document.querySelectorAll("[data-upload-audio-id]"));
  await Promise.all(imageContainers.map(async (container) => {
    try {
      const blob = await apiBlob(`/api/uploads/${container.dataset.uploadImageId}/file`);
      const imageUrl = rememberPreviewUrl(blob);
      container.innerHTML = `<a href="${esc(imageUrl)}" target="_blank" rel="noopener" title="点击查看原图"><img src="${esc(imageUrl)}" alt="原始上传图片" /></a>`;
    } catch (error) {
      container.innerHTML = `<span>原图加载失败：${esc(readableError(error))}</span>`;
    }
  }));
  await Promise.all(audioContainers.map(async (container) => {
    try {
      const blob = await apiBlob(`/api/uploads/${container.dataset.uploadAudioId}/file`);
      const audioUrl = rememberPreviewUrl(blob);
      container.innerHTML = `<audio controls preload="metadata" src="${esc(audioUrl)}"></audio><a class="media-open-link" href="${esc(audioUrl)}" target="_blank" rel="noopener">打开原始录音</a>`;
    } catch (error) {
      container.innerHTML = `<span>录音加载失败：${esc(readableError(error))}</span>`;
    }
  }));
}

function renderFollowupCards(followups) {
  if (!followups.length) return `<p class="empty compact-empty">暂无AI跟进记录。</p>`;
  return followups.map((item) => `
    <article class="followup-card ${item.source === "manual_note" ? "manual" : "auto"}">
      <div>
        <strong>${followupSourceText(item.source)} · ${formatDate(item.created_at)}</strong>
        <p>${esc(item.content)}</p>
      </div>
      <span>${item.next_followup_at ? `下次：${formatDate(item.next_followup_at)}` : "未设置下次时间"}</span>
    </article>
  `).join("");
}

function followupSourceText(source) {
  return {
    call_auto: "通话自动记录",
    material_auto: "资料自动记录",
    manual_note: "人工补充备注",
    manual: "人工补充备注",
  }[source] || "跟进记录";
}

window.showCustomerDetail = showCustomerDetail;
window.submitManualNote = submitManualNote;
window.submitCallRecording = submitCallRecording;
window.submitCustomerMaterial = submitCustomerMaterial;
