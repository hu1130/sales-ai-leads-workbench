const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));

const state = {
  apiBase: initialApiBase(),
  token: localStorage.getItem("salesAiToken") || "",
  user: JSON.parse(localStorage.getItem("salesAiUser") || "null"),
  view: "dashboard",
  salesUsers: [],
  previewUrls: [],
};

const views = {
  dashboard: { title: "今日工作台", load: loadDashboard },
  customers: { title: "客户池", load: loadCustomers },
  uploads: { title: "资料处理", load: loadUploads },
  assignment: { title: "线索分配", load: loadAssignment, admin: true },
  team: { title: "团队看板", load: loadTeam, admin: true },
  scripts: { title: "销售话术", load: loadScripts },
  users: { title: "销售账号", load: loadUsers, admin: true },
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
  updateDateLabels();
  switchView("dashboard");
});

function initialApiBase() {
  const saved = localStorage.getItem("salesAiApiBase");
  if (saved) return saved;
  if (location.hostname === "127.0.0.1" || location.hostname === "localhost") {
    return `${location.protocol}//${location.hostname}:8100`;
  }
  return location.origin || "http://127.0.0.1:8100";
}

function bindEvents() {
  $("#loginOpenBtn").addEventListener("click", openLogin);
  $("#logoutBtn").addEventListener("click", logout);
  $("#loginForm").addEventListener("submit", login);
  $("#refreshBtn").addEventListener("click", () => views[state.view].load());
  $("#testAiBtn").addEventListener("click", testAi);
  $("#openUploadBtn").addEventListener("click", openUpload);
  $$("[data-open-upload]").forEach((button) => button.addEventListener("click", openUpload));
  $("#uploadForm").addEventListener("submit", submitUpload);
  $("#detailDialog").addEventListener("close", clearPreviewUrls);

  $$(".nav-btn").forEach((button) => button.addEventListener("click", () => switchView(button.dataset.view)));
  $$("[data-view-link]").forEach((button) => button.addEventListener("click", () => switchView(button.dataset.viewLink)));
  $$("[data-close]").forEach((button) => button.addEventListener("click", () => $(`#${button.dataset.close}`).close()));

  $("#searchCustomersBtn").addEventListener("click", loadCustomers);
  $("#customerKeyword").addEventListener("keydown", enterTo(loadCustomers));
  $("#customerOwner").addEventListener("change", loadCustomers);
  $("#customerIntent").addEventListener("change", loadCustomers);
  $("#customerDateQuick").addEventListener("change", () => clearExactDate("customer", loadCustomers));
  $("#customerDateExact").addEventListener("change", () => clearQuickDate("customer", loadCustomers));

  $("#searchUploadsBtn").addEventListener("click", loadUploads);
  $("#uploadKeyword").addEventListener("keydown", enterTo(loadUploads));
  $("#uploadStage").addEventListener("change", loadUploads);
  $("#uploadType").addEventListener("change", loadUploads);
  $("#uploadDateQuick").addEventListener("change", () => clearExactDate("upload", loadUploads));
  $("#uploadDateExact").addEventListener("change", () => clearQuickDate("upload", loadUploads));

  $("#searchAssignmentBtn").addEventListener("click", loadAssignment);
  $("#assignmentKeyword").addEventListener("keydown", enterTo(loadAssignment));
  $("#assignmentSource").addEventListener("change", loadAssignment);
  $("#openLeadCreateBtn").addEventListener("click", () => requireAdmin(() => $("#leadCreateDialog").showModal()));
  $("#leadCreateForm").addEventListener("submit", submitLead);

  $("#searchScriptsBtn").addEventListener("click", loadScripts);
  $("#scriptKeyword").addEventListener("keydown", enterTo(loadScripts));
  $("#scriptCategory").addEventListener("keydown", enterTo(loadScripts));
  $("#openScriptCreateBtn").addEventListener("click", () => requireAdmin(() => $("#scriptCreateDialog").showModal()));
  $("#scriptCreateForm").addEventListener("submit", submitScript);
  $("#createUserForm").addEventListener("submit", submitUser);
}

function enterTo(fn) {
  return (event) => {
    if (event.key === "Enter") fn();
  };
}

async function login(event) {
  event.preventDefault();
  $("#loginError").hidden = true;
  state.apiBase = $("#apiBase").value.trim().replace(/\/$/, "");
  localStorage.setItem("salesAiApiBase", state.apiBase);
  try {
    const result = await api("/api/auth/login", {
      method: "POST",
      auth: false,
      body: JSON.stringify({
        username: $("#loginUsername").value.trim(),
        password: $("#loginPassword").value,
      }),
    });
    state.token = result.access_token;
    state.user = result.user;
    localStorage.setItem("salesAiToken", state.token);
    localStorage.setItem("salesAiUser", JSON.stringify(state.user));
    $("#loginDialog").close();
    updateAuthUi();
    showNotice("登录成功，已切换到真实数据。", "ok");
    await views[state.view].load();
  } catch (error) {
    $("#loginError").textContent = readableError(error);
    $("#loginError").hidden = false;
  }
}

function logout() {
  state.token = "";
  state.user = null;
  state.salesUsers = [];
  localStorage.removeItem("salesAiToken");
  localStorage.removeItem("salesAiUser");
  updateAuthUi();
  switchView("dashboard");
  showNotice("已退出登录。", "ok");
}

function openLogin() {
  $("#apiBase").value = state.apiBase;
  $("#loginDialog").showModal();
}

function openUpload() {
  requireLogin(() => $("#uploadDialog").showModal());
}

function requireLogin(action) {
  if (state.token) {
    action();
    return true;
  }
  openLogin();
  showNotice("请先登录后再操作。");
  return false;
}

function requireAdmin(action) {
  if (!state.token) return requireLogin(action);
  if (state.user?.role !== "admin") {
    showNotice("这个功能需要管理员账号。");
    return false;
  }
  action();
  return true;
}

function updateAuthUi() {
  const loggedIn = Boolean(state.token && state.user);
  $("#accountName").textContent = loggedIn ? state.user.name || state.user.username : "未登录";
  $("#accountHint").textContent = loggedIn
    ? state.user.role === "admin" ? "主管可查看全部客户、分配线索和团队进度。" : "销售只看自己负责的客户。"
    : "登录后查看真实客户和 AI 分析结果。";
  $("#loginOpenBtn").hidden = loggedIn;
  $("#logoutBtn").hidden = !loggedIn;
  $$(".admin-only").forEach((item) => {
    item.hidden = !(loggedIn && state.user?.role === "admin");
  });
  $("#connectionPill").textContent = loggedIn ? (state.user.role === "admin" ? "主管视角" : "销售视角") : "请先登录";
  if (loggedIn && state.user.role === "admin") loadSalesUsers();
}

function switchView(name) {
  const view = views[name];
  if (!view) return;
  if (view.admin && state.user?.role !== "admin") {
    showNotice("这个页面需要管理员账号。");
    return openLogin();
  }
  state.view = name;
  $(".active-view")?.classList.remove("active-view");
  $(`#${name}View`).classList.add("active-view");
  $$(".nav-btn").forEach((button) => button.classList.toggle("active", button.dataset.view === name));
  $("#viewTitle").textContent = view.title;
  view.load();
}

async function loadDashboard() {
  if (!state.token) {
    renderLockedDashboard();
    return;
  }
  try {
    const [stats, priorities, uploads] = await Promise.all([
      api("/api/dashboard/stats"),
      api("/api/dashboard/followup-priorities?limit=8"),
      api("/api/uploads?page_size=6"),
    ]);
    const dist = stats.intent_distribution || {};
    $("#metricHigh").textContent = dist["高意向"] || stats.high_intent_customers || 0;
    $("#metricMid").textContent = dist["中意向"] || 0;
    $("#metricLow").textContent = dist["低意向"] || 0;
    $("#metricUnassigned").textContent = stats.unassigned_customers || 0;
    renderPriorityList(priorities);
    renderUploadTimeline(uploads.items || []);
  } catch (error) {
    showNotice(readableError(error));
  }
}

function renderLockedDashboard() {
  ["metricHigh", "metricMid", "metricLow", "metricUnassigned"].forEach((id) => $(`#${id}`).textContent = "--");
  $("#priorityList").innerHTML = `<p class="empty">登录后显示今天最该跟进的客户。</p>`;
  $("#uploadTimeline").innerHTML = `<p class="empty">登录后显示最近处理的截图、录音和资料。</p>`;
}

function renderPriorityList(items) {
  $("#priorityList").innerHTML = items.length ? items.map((item) => `
    <article class="lead-card">
      <div class="lead-top">
        <div>
          <strong>${esc(item.name || item.wechat_nickname || item.phone || "未命名客户")}</strong>
          <p>${esc(item.owner_name || item.owner_username || "未分配销售")} · ${esc(item.demand_summary || item.followup_content || "暂无需求摘要")}</p>
        </div>
        ${intentBadge(item.intent_level, item.intent_score)}
      </div>
      <p>${esc(item.next_action || firstLine(item.followup_content) || "等待补充下一步动作")}</p>
      <div class="row-actions">
        <button class="ghost-btn" type="button" onclick="showCustomerDetail(${item.customer_id || item.id})">查看客户</button>
        ${item.followup_id ? `<button class="primary-btn" type="button" onclick="markFollowup(${item.followup_id}, 'completed')">标记完成</button>` : ""}
      </div>
    </article>`).join("") : `<p class="empty">暂无待跟进客户。</p>`;
}

function renderUploadTimeline(items) {
  $("#uploadTimeline").innerHTML = items.length ? items.map((item) => `
    <article class="timeline-row">
      <div><strong>${esc(item.file_name)}</strong><p>${fileTypeText(item.file_type)} · ${sourceTimeText(item)} · 入库 ${formatDate(item.created_at)}</p></div>
      ${statusBadge(item.material_stage || item.status)}
    </article>`).join("") : `<p class="empty">暂无资料记录。</p>`;
}

async function loadCustomers() {
  if (!state.token) return $("#customersTable").innerHTML = emptyRow(8, "请先登录后查看客户。");
  try {
    const params = new URLSearchParams({ page_size: "80" });
    const keyword = joinKeywords($("#customerKeyword").value.trim(), selectedDateKeyword("customer"));
    if (keyword) params.set("keyword", keyword);
    if ($("#customerIntent").value) params.set("intent_level", $("#customerIntent").value);
    if ($("#customerOwner").value === "__unassigned") params.set("lead_status", "unassigned");
    else if ($("#customerOwner").value) params.set("owner_id", $("#customerOwner").value);
    const data = await api(`/api/customers?${params}`);
    $("#customersTable").innerHTML = data.items.length ? data.items.map(renderCustomerRow).join("") : emptyRow(8, "没有找到客户。");
  } catch (error) {
    showNotice(readableError(error));
  }
}

function renderCustomerRow(item) {
  return `<tr>
    <td><span class="cell-main">${esc(item.name || "未命名客户")}</span><span class="cell-sub">ID ${item.id}</span></td>
    <td>${wechatCell(item)}</td>
    <td>${phoneCell(item.phone)}</td>
    <td>${ownerCell(item)}</td>
    <td>${intentBadge(item.intent_level, item.intent_score)}</td>
    <td><span class="cell-main">${esc(item.demand_summary || "未提及")}</span></td>
    <td><span class="cell-main">${esc(item.next_action || "未提及")}</span></td>
    <td><div class="row-actions"><button class="ghost-btn" type="button" onclick="showCustomerDetail(${item.id})">查看</button></div></td>
  </tr>`;
}

async function loadUploads() {
  if (!state.token) return $("#uploadsTable").innerHTML = emptyRow(7, "请先登录后查看资料。");
  try {
    const params = new URLSearchParams({ page_size: "80" });
    const keyword = joinKeywords($("#uploadKeyword").value.trim(), selectedDateKeyword("upload"));
    if (keyword) params.set("keyword", keyword);
    if ($("#uploadStage").value) params.set("material_stage", $("#uploadStage").value);
    if ($("#uploadType").value) params.set("file_type", $("#uploadType").value);
    const data = await api(`/api/uploads?${params}`);
    $("#uploadsTable").innerHTML = data.items.length ? data.items.map(renderUploadRow).join("") : emptyRow(7, "暂无资料记录。");
  } catch (error) {
    showNotice(readableError(error));
  }
}

function renderUploadRow(item) {
  return `<tr>
    <td><span class="cell-main">${esc(item.file_name)}</span><span class="cell-sub">ID ${item.id}</span></td>
    <td>${fileTypeText(item.file_type)}</td>
    <td>${statusBadge(item.material_stage || item.status)}<span class="cell-sub">${statusText(item.status)}</span></td>
    <td>${item.customer_id ? `<span class="cell-main">${esc(item.customer_name || `客户 ${item.customer_id}`)}</span><span class="cell-sub">${esc(item.customer_phone || `ID ${item.customer_id}`)}</span>` : "未归档"}</td>
    <td>${uploaderCell(item)}</td>
    <td><span class="cell-main">${sourceTimeText(item)}</span><span class="cell-sub">入库 ${formatDate(item.created_at)}</span></td>
    <td><div class="row-actions"><button class="ghost-btn" type="button" onclick="showUploadDetail(${item.id})">分析</button><button class="ghost-btn" type="button" onclick="reanalyzeUpload(${item.id})">重跑</button></div></td>
  </tr>`;
}

async function loadAssignment() {
  if (!state.token || state.user?.role !== "admin") return;
  if (!state.salesUsers.length) await loadSalesUsers();
  try {
    const params = new URLSearchParams({ page_size: "100", lead_status: "unassigned" });
    if ($("#assignmentKeyword").value.trim()) params.set("keyword", $("#assignmentKeyword").value.trim());
    if ($("#assignmentSource").value) params.set("lead_source", $("#assignmentSource").value);
    const data = await api(`/api/customers?${params}`);
    $("#assignmentTable").innerHTML = data.items.length ? data.items.map(renderAssignmentRow).join("") : emptyRow(6, "暂无未分配线索。");
  } catch (error) {
    showNotice(readableError(error));
  }
}

function renderAssignmentRow(item) {
  return `<tr>
    <td><span class="cell-main">${esc(item.name || item.wechat_nickname || "未命名客户")}</span><span class="cell-sub">ID ${item.id}</span></td>
    <td>${esc(item.lead_source || item.source || "外部线索")}</td>
    <td>${phoneCell(item.phone)}<span class="cell-sub">${esc(item.wechat_id || item.wechat_nickname || "微信未提及")}</span></td>
    <td>${esc(item.demand_summary || "未提及")}</td>
    <td><select data-assign="${item.id}">${salesOptions()}</select></td>
    <td><div class="row-actions"><button class="primary-btn" type="button" onclick="assignCustomer(${item.id})">分配</button><button class="ghost-btn" type="button" onclick="showCustomerDetail(${item.id})">查看</button></div></td>
  </tr>`;
}

async function loadTeam() {
  if (!state.token || state.user?.role !== "admin") return;
  try {
    const data = await api("/api/dashboard/team-today");
    const totals = (data.items || []).reduce((acc, item) => {
      acc.customers += item.today_customers || 0;
      acc.followups += item.today_followups || 0;
      acc.uploads += item.today_uploads || 0;
      return acc;
    }, { customers: 0, followups: 0, uploads: 0 });
    $("#teamUnassigned").textContent = data.unassigned_customers || 0;
    $("#teamTodayCustomers").textContent = totals.customers;
    $("#teamTodayFollowups").textContent = totals.followups;
    $("#teamTodayUploads").textContent = totals.uploads;
    $("#teamTable").innerHTML = data.items.length ? data.items.map(renderTeamRow).join("") : emptyRow(8, "暂无销售账号。");
  } catch (error) {
    showNotice(readableError(error));
  }
}

function renderTeamRow(item) {
  return `<tr>
    <td><span class="cell-main">${esc(item.name)}</span><span class="cell-sub">${esc(item.username)} · ${esc(item.phone || "未填手机号")}</span></td>
    <td>${item.today_customers}</td><td>${item.today_followups}</td><td>${item.today_uploads}</td>
    <td>${item.high_intent_customers}</td><td>${item.pending_followup_customers}</td><td>${item.total_customers}</td>
    <td><button class="ghost-btn" type="button" onclick="openSalesCustomers(${item.user_id})">看客户</button></td>
  </tr>`;
}

async function loadScripts() {
  if (!state.token) return $("#scriptList").innerHTML = `<p class="empty">请先登录后查看话术库。</p>`;
  try {
    const params = new URLSearchParams({ page_size: "100" });
    if ($("#scriptKeyword").value.trim()) params.set("keyword", $("#scriptKeyword").value.trim());
    if ($("#scriptCategory").value.trim()) params.set("category", $("#scriptCategory").value.trim());
    const data = await api(`/api/scripts?${params}`);
    $("#scriptList").innerHTML = data.items.length ? data.items.map(renderScriptCard).join("") : `<p class="empty">暂无话术。</p>`;
  } catch (error) {
    showNotice(readableError(error));
  }
}

function renderScriptCard(item) {
  return `<article class="script-card">
    <strong>${esc(item.title)}</strong>
    <p>${esc(item.category || "general")}</p>
    <pre>${esc(item.content)}</pre>
    ${state.user?.role === "admin" ? `<div class="row-actions"><button class="danger-btn" type="button" onclick="deleteScript(${item.id})">删除</button></div>` : ""}
  </article>`;
}

async function loadUsers() {
  if (!state.token || state.user?.role !== "admin") return;
  try {
    const users = await api("/api/users?role=sales&page_size=100");
    $("#userList").innerHTML = users.length ? users.map((user) => `
      <article class="user-row"><div><strong>${esc(user.name)}</strong><p>${esc(user.username)} · ${esc(user.phone || "未填手机号")}</p></div>${statusBadge(user.status === "active" ? "ok" : "none", user.status === "active" ? "启用" : "停用")}</article>
    `).join("") : `<p class="empty">暂无销售账号。</p>`;
  } catch (error) {
    showNotice(readableError(error));
  }
}

async function loadSalesUsers() {
  if (!state.token || state.user?.role !== "admin") return [];
  try {
    state.salesUsers = await api("/api/users?role=sales&status=active&page_size=200");
    populateSalesSelectors();
  } catch (error) {
    console.warn(error);
  }
  return state.salesUsers;
}

function populateSalesSelectors() {
  const options = state.salesUsers.map((user) => `<option value="${user.id}">${esc(user.name)}（${esc(user.username)}）</option>`).join("");
  const currentOwner = $("#customerOwner").value;
  $("#customerOwner").innerHTML = `<option value="">全部销售</option><option value="__unassigned">未分配</option>${options}`;
  $("#customerOwner").value = currentOwner;
  $("#leadCreateOwner").innerHTML = `<option value="">先放入未分配池</option>${options}`;
}

async function submitUpload(event) {
  event.preventDefault();
  if (!state.token) return openLogin();
  const form = event.currentTarget;
  const file = form.file.files[0];
  if (!file) return;
  const data = new FormData(form);
  try {
    const result = await api("/api/uploads", { method: "POST", body: data, isForm: true });
    form.reset();
    $("#uploadDialog").close();
    showNotice(`上传成功，记录 ${result.id} 正在分析。`, "ok");
    await loadUploads();
  } catch (error) {
    showNotice(readableError(error));
  }
}

async function submitLead(event) {
  event.preventDefault();
  if (!state.token || state.user?.role !== "admin") return openLogin();
  const form = event.currentTarget;
  const data = Object.fromEntries(new FormData(form).entries());
  if (data.owner_id) {
    data.owner_id = Number(data.owner_id);
    data.lead_status = "assigned";
  } else {
    delete data.owner_id;
    data.lead_status = "unassigned";
  }
  data.source = data.lead_source || "外部线索";
  try {
    await api("/api/customers", { method: "POST", body: JSON.stringify(data) });
    form.reset();
    $("#leadCreateDialog").close();
    showNotice("线索已保存。", "ok");
    await loadAssignment();
  } catch (error) {
    showNotice(readableError(error));
  }
}

async function submitScript(event) {
  event.preventDefault();
  if (!state.token || state.user?.role !== "admin") return openLogin();
  const form = event.currentTarget;
  const data = Object.fromEntries(new FormData(form).entries());
  try {
    await api("/api/scripts", { method: "POST", body: JSON.stringify(data) });
    form.reset();
    $("#scriptCreateDialog").close();
    showNotice("话术已保存。", "ok");
    await loadScripts();
  } catch (error) {
    showNotice(readableError(error));
  }
}

async function submitUser(event) {
  event.preventDefault();
  if (!state.token || state.user?.role !== "admin") return openLogin();
  const form = event.currentTarget;
  const data = Object.fromEntries(new FormData(form).entries());
  data.role = "sales";
  try {
    await api("/api/users", { method: "POST", body: JSON.stringify(data) });
    form.reset();
    showNotice("销售账号已创建。", "ok");
    await loadSalesUsers();
    await loadUsers();
  } catch (error) {
    showNotice(readableError(error));
  }
}

async function assignCustomer(id) {
  const select = document.querySelector(`[data-assign="${id}"]`);
  const ownerId = Number(select?.value || 0);
  if (!ownerId) return showNotice("请先选择销售。");
  try {
    await api(`/api/customers/${id}/assign`, { method: "POST", body: JSON.stringify({ owner_id: ownerId }) });
    showNotice("线索已分配。", "ok");
    await loadAssignment();
  } catch (error) {
    showNotice(readableError(error));
  }
}

async function showCustomerDetail(id) {
  if (!state.token) return openLogin();
  try {
    const [customer, records, followups, quotes] = await Promise.all([
      api(`/api/customers/${id}`),
      api(`/api/customers/${id}/records`),
      api(`/api/customers/${id}/followups`),
      api(`/api/quotations/${id}`).catch(() => []),
    ]);
    $("#detailTitle").textContent = customer.name || customer.phone || `客户 ${customer.id}`;
    $("#detailSubtitle").textContent = `${customer.owner_name || customer.owner_username || "未分配销售"} · ${customer.lead_source || customer.source || "AI上传"}`;
    $("#detailContent").innerHTML = `
      <section class="detail-grid">
        ${detailItem("负责销售", ownerCell(customer))}
        ${detailItem("微信号", esc(customer.wechat_id || "未提及"))}
        ${detailItem("微信昵称/备注", esc(customer.wechat_nickname || "未提及"))}
        ${detailItem("客户电话", phoneCell(customer.phone))}
        ${detailItem("当前意向", intentBadge(customer.intent_level, customer.intent_score))}
        ${detailItem("销售阶段", stageText(customer.pipeline_stage))}
        ${detailItem("客户需求", esc(customer.demand_summary || "未提及"), true)}
        ${detailItem("疑问/异议", esc(customer.concerns || "未提及"), true)}
        ${detailItem("下一步建议", esc(customer.next_action || "未提及"), true)}
      </section>
      <details class="detail-item full" open>
        <summary><strong>编辑客户资料</strong></summary>
        <form class="form-grid" onsubmit="submitCustomerEdit(event, ${customer.id})">
          <label>客户姓名<input name="name" value="${esc(customer.name || "")}" /></label>
          <label>客户电话<input name="phone" value="${esc(customer.phone || "")}" /></label>
          <label>微信号<input name="wechat_id" value="${esc(customer.wechat_id || "")}" /></label>
          <label>微信昵称/备注<input name="wechat_nickname" value="${esc(customer.wechat_nickname || "")}" /></label>
          <label>意向等级<select name="intent_level">${intentOptions(customer.intent_level)}</select></label>
          <label>意向评分<input name="intent_score" type="number" min="0" max="100" value="${Number(customer.intent_score || 0)}" /></label>
          <label>销售阶段<select name="pipeline_stage">${stageOptions(customer.pipeline_stage)}</select></label>
          <label>关注产品<input name="product_interest" value="${esc(customer.product_interest || "")}" /></label>
          <label class="full">客户需求<textarea name="demand_summary" rows="2">${esc(customer.demand_summary || "")}</textarea></label>
          <label class="full">下一步建议<textarea name="next_action" rows="2">${esc(customer.next_action || "")}</textarea></label>
          <div class="modal-actions full"><button class="primary-btn" type="submit">保存修改</button><button class="danger-btn" type="button" onclick="deleteCustomer(${customer.id})">删除客户</button></div>
        </form>
      </details>
      <section class="detail-item full">
        <span>历史资料</span>
        ${records.length ? records.map(renderRecordCard).join("") : "<p>暂无资料。</p>"}
      </section>
      <section class="detail-item full">
        <span>跟进记录</span>
        ${followups.length ? followups.map(renderFollowupCard).join("") : "<p>暂无跟进记录。</p>"}
      </section>
      <section class="detail-item full">
        <span>报价单</span>
        ${renderQuotationBox(customer.id, quotes)}
      </section>
    `;
    await hydrateRecordPreviews();
    openDetailAtTop();
  } catch (error) {
    showNotice(readableError(error));
  }
}

function renderRecordCard(record) {
  const analysis = record.analysis || {};
  return `<article class="lead-card">
    <div class="lead-top"><div><strong>${esc(record.file_name)}</strong><p>${fileTypeText(record.file_type)} · ${formatDate(record.created_at)}</p></div>${statusBadge(record.status)}</div>
    ${record.file_type === "image" ? `<div class="media-box" data-image="${record.id}">正在加载原图...</div>` : ""}
    ${record.file_type === "audio" ? `<div class="media-box" data-audio="${record.id}">正在加载录音...</div>` : ""}
    <p><b>摘要：</b>${esc(analysis.summary || "未提及")}</p>
    <p><b>话术：</b>${esc(analysis.sales_script || "未提及")}</p>
    <div class="row-actions"><button class="ghost-btn" type="button" onclick="showUploadDetail(${record.id})">查看分析</button></div>
  </article>`;
}

function renderFollowupCard(item) {
  return `<article class="lead-card">
    <div class="lead-top"><strong>${followupSourceText(item.source)}</strong>${statusBadge(item.status || "pending")}</div>
    <p>${esc(item.content)}</p>
    <div class="row-actions">
      <button class="ghost-btn" type="button" onclick="markFollowup(${item.id}, 'contacted')">已联系</button>
      <button class="primary-btn" type="button" onclick="markFollowup(${item.id}, 'completed')">完成</button>
    </div>
  </article>`;
}

function renderQuotationBox(customerId, quotes) {
  return `
    <form class="inline-form" onsubmit="submitQuotation(event, ${customerId})">
      <input name="title" placeholder="报价标题" />
      <input name="item_name" placeholder="项目名称" required />
      <input name="qty" type="number" min="1" value="1" required />
      <input name="unit_price" type="number" min="0" step="0.01" placeholder="单价" required />
      <button class="primary-btn" type="submit">生成报价</button>
    </form>
    ${quotes.length ? quotes.map((q) => `<article class="lead-card"><div class="lead-top"><strong>${esc(q.title || `报价 ${q.id}`)}</strong>${statusBadge(q.status)}</div><p>金额：${q.total_amount} 元 · ${formatDate(q.created_at)}</p><div class="row-actions"><button class="ghost-btn" type="button" onclick="updateQuotationStatus(${q.id}, 'sent', ${customerId})">标记已发送</button><button class="primary-btn" type="button" onclick="updateQuotationStatus(${q.id}, 'accepted', ${customerId})">已成交</button></div></article>`).join("") : "<p>暂无报价单。</p>"}
  `;
}

async function showUploadDetail(id) {
  if (!state.token) return openLogin();
  try {
    const upload = await api(`/api/uploads/${id}`);
    clearPreviewUrls();
    let media = "";
    if (upload.file_type === "image" || upload.file_type === "audio") {
      try {
        const url = rememberPreviewUrl(await apiBlob(`/api/uploads/${id}/file`));
        media = upload.file_type === "image"
          ? `<section class="media-box full"><span>原始图片</span><img src="${esc(url)}" alt="${esc(upload.file_name)}" /></section>`
          : `<section class="media-box full"><span>原始录音</span><audio controls src="${esc(url)}"></audio></section>`;
      } catch (error) {
        media = detailItem("原文件", `加载失败：${esc(readableError(error))}`, true);
      }
    }
    const analysis = upload.analysis;
    $("#detailTitle").textContent = upload.file_name;
    $("#detailSubtitle").textContent = `${fileTypeText(upload.file_type)} · ${statusText(upload.status)}`;
    $("#detailContent").innerHTML = analysis ? `<section class="detail-grid">
      ${media}
      ${detailItem("处理状态", statusBadge(upload.material_stage || upload.status))}
      ${detailItem("上传销售", uploaderCell(upload))}
      ${detailItem("客户姓名", esc(analysis.customer_name || "未提及"))}
      ${detailItem("微信号", esc(analysis.customer_wechat_id || "未提及"))}
      ${detailItem("微信昵称/备注", esc(analysis.customer_wechat_nickname || "未提及"))}
      ${detailItem("购买意向", intentBadge(analysis.intent_level, analysis.intent_score))}
      ${detailItem("内容摘要", esc(analysis.summary || "未提及"), true)}
      ${detailItem("客户需求", esc(analysis.customer_needs || "未提及"), true)}
      ${detailItem("判断依据", esc(analysis.evidence || "未提及"), true)}
      ${detailItem("推荐话术", esc(analysis.sales_script || "未提及"), true)}
      ${detailItem("原始识别文本", esc(analysis.raw_text || "未提及"), true)}
    </section>` : `<p class="empty">资料还在处理中，请稍后刷新。</p>`;
    openDetailAtTop();
  } catch (error) {
    showNotice(readableError(error));
  }
}

async function submitCustomerEdit(event, id) {
  event.preventDefault();
  const form = event.currentTarget;
  const data = Object.fromEntries(new FormData(form).entries());
  data.intent_score = Number(data.intent_score || 0);
  try {
    await api(`/api/customers/${id}`, { method: "PATCH", body: JSON.stringify(data) });
    showNotice("客户资料已保存。", "ok");
    await showCustomerDetail(id);
    if (state.view === "customers") await loadCustomers();
  } catch (error) {
    showNotice(readableError(error));
  }
}

async function deleteCustomer(id) {
  if (!confirm("确定删除这个客户吗？关联资料、分析和跟进记录也会删除。")) return;
  try {
    await api(`/api/customers/${id}`, { method: "DELETE" });
    $("#detailDialog").close();
    showNotice("客户已删除。", "ok");
    await views[state.view].load();
  } catch (error) {
    showNotice(readableError(error));
  }
}

async function submitQuotation(event, customerId) {
  event.preventDefault();
  const form = event.currentTarget;
  const data = Object.fromEntries(new FormData(form).entries());
  try {
    await api(`/api/quotations/${customerId}`, {
      method: "POST",
      body: JSON.stringify({
        title: data.title,
        items: [{ name: data.item_name, qty: Number(data.qty), unit_price: Number(data.unit_price) }],
      }),
    });
    showNotice("报价单已生成。", "ok");
    await showCustomerDetail(customerId);
  } catch (error) {
    showNotice(readableError(error));
  }
}

async function updateQuotationStatus(id, status, customerId) {
  try {
    await api(`/api/quotations/${id}/status`, { method: "PATCH", body: JSON.stringify({ status }) });
    showNotice("报价状态已更新。", "ok");
    await showCustomerDetail(customerId);
  } catch (error) {
    showNotice(readableError(error));
  }
}

async function markFollowup(id, status) {
  try {
    await api(`/api/customers/followups/${id}/status`, { method: "PATCH", body: JSON.stringify({ status }) });
    showNotice("跟进状态已更新。", "ok");
    await views[state.view].load();
  } catch (error) {
    showNotice(readableError(error));
  }
}

async function reanalyzeUpload(id) {
  try {
    await api(`/api/uploads/${id}/reanalyze`, { method: "POST" });
    showNotice("已提交重新分析。", "ok");
    await loadUploads();
  } catch (error) {
    showNotice(readableError(error));
  }
}

async function deleteScript(id) {
  if (!confirm("确定删除这条话术吗？")) return;
  try {
    await api(`/api/scripts/${id}`, { method: "DELETE" });
    showNotice("话术已删除。", "ok");
    await loadScripts();
  } catch (error) {
    showNotice(readableError(error));
  }
}

async function testAi() {
  if (!state.token) return openLogin();
  try {
    const status = await api("/api/ai/deepseek/status");
    if (!status.configured) return showNotice("DeepSeek Key 未配置，请先检查后端 .env。");
    const result = await api("/api/ai/deepseek/test", { method: "POST" });
    showNotice(`DeepSeek 连接成功：${result.intent_level} · ${result.intent_score}`, "ok");
  } catch (error) {
    showNotice(readableError(error));
  }
}

async function hydrateRecordPreviews() {
  const images = $$("[data-image]");
  const audios = $$("[data-audio]");
  await Promise.all(images.map(async (box) => {
    try {
      const url = rememberPreviewUrl(await apiBlob(`/api/uploads/${box.dataset.image}/file`));
      box.innerHTML = `<img src="${esc(url)}" alt="原始图片" />`;
    } catch (error) {
      box.textContent = `原图加载失败：${readableError(error)}`;
    }
  }));
  await Promise.all(audios.map(async (box) => {
    try {
      const url = rememberPreviewUrl(await apiBlob(`/api/uploads/${box.dataset.audio}/file`));
      box.innerHTML = `<audio controls src="${esc(url)}"></audio>`;
    } catch (error) {
      box.textContent = `录音加载失败：${readableError(error)}`;
    }
  }));
}

function openSalesCustomers(userId) {
  $("#customerOwner").value = String(userId);
  $("#customerIntent").value = "";
  $("#customerKeyword").value = "";
  switchView("customers");
}

function openDetailAtTop() {
  const dialog = $("#detailDialog");
  const content = $("#detailContent");
  [dialog, content].forEach((el) => {
    if (el) {
      el.scrollTop = 0;
      el.scrollLeft = 0;
    }
  });
  if (!dialog.open) dialog.showModal();
  requestAnimationFrame(() => {
    dialog.scrollTop = 0;
    content.scrollTop = 0;
  });
}

function clearExactDate(scope, reload) {
  $(`#${scope}DateExact`).value = "";
  updateDateLabels();
  reload();
}

function clearQuickDate(scope, reload) {
  $(`#${scope}DateQuick`).value = "";
  updateDateLabels();
  reload();
}

function updateDateLabels() {
  ["customer", "upload"].forEach((scope) => {
    const input = $(`#${scope}DateExact`);
    const label = $(`#${scope}DateLabel`);
    if (!input || !label) return;
    label.textContent = input.value ? friendlyDate(input.value) : "选择日期";
  });
}

function selectedDateKeyword(scope) {
  const exact = $(`#${scope}DateExact`)?.value;
  if (exact) return compactDate(exact);
  const quick = $(`#${scope}DateQuick`)?.value;
  if (quick === "today") return compactDate(offsetDate(0));
  if (quick === "yesterday") return compactDate(offsetDate(-1));
  if (quick === "7days") return Array.from({ length: 7 }, (_, index) => compactDate(offsetDate(-index))).join(",");
  return "";
}

function joinKeywords(text, dateKeyword) {
  if (!dateKeyword) return text;
  return text ? `${text} ${dateKeyword}` : dateKeyword;
}

function offsetDate(days) {
  const date = new Date();
  date.setDate(date.getDate() + days);
  return date;
}

function compactDate(value) {
  const date = value instanceof Date ? value : new Date(`${value}T00:00:00`);
  return `${date.getFullYear()}${String(date.getMonth() + 1).padStart(2, "0")}${String(date.getDate()).padStart(2, "0")}`;
}

function friendlyDate(value) {
  return new Date(`${value}T00:00:00`).toLocaleDateString("zh-CN", { month: "numeric", day: "numeric" });
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
    throw new Error(Array.isArray(message) ? message.map((item) => item.msg).join("；") : message);
  }
  return data;
}

async function apiBlob(path) {
  const headers = state.token ? { Authorization: `Bearer ${state.token}` } : {};
  const response = await fetch(`${state.apiBase}${path}`, { headers });
  if (!response.ok) throw new Error(`文件读取失败：${response.status}`);
  return response.blob();
}

function rememberPreviewUrl(blob) {
  const url = URL.createObjectURL(blob);
  state.previewUrls.push(url);
  return url;
}

function clearPreviewUrls() {
  state.previewUrls.forEach((url) => URL.revokeObjectURL(url));
  state.previewUrls = [];
}

function showNotice(message, type = "error") {
  const box = $("#notice");
  box.textContent = message;
  box.className = `notice ${type}`;
  box.hidden = false;
  clearTimeout(showNotice.timer);
  showNotice.timer = setTimeout(() => box.hidden = true, 4200);
}

function readableError(error) {
  const message = error?.message || String(error);
  if (message.includes("Failed to fetch")) return "连接不到后端，请确认后端服务已启动。";
  return message;
}

function detailItem(label, value, full = false) {
  return `<section class="detail-item ${full ? "full" : ""}"><span>${label}</span><p>${value}</p></section>`;
}

function emptyRow(colspan, text) {
  return `<tr><td class="empty" colspan="${colspan}">${esc(text)}</td></tr>`;
}

function esc(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function intentBadge(level, score = 0) {
  const cls = level === "高意向" ? "high" : level === "中意向" ? "mid" : level === "低意向" ? "low" : level === "暂无意向" ? "none" : "unknown";
  return `<span class="badge ${cls}">${esc(level || "无法判断")} · ${score ?? 0}</span>`;
}

function statusBadge(status, label) {
  const cls = ["completed", "customer_created", "accepted", "sent", "ok"].includes(status) ? "ok"
    : ["failed", "rejected", "none"].includes(status) ? "none"
    : ["pending", "processing", "unlinked", "draft", "contacted", "meeting"].includes(status) ? "wait"
    : "unknown";
  return `<span class="badge ${cls}">${esc(label || statusText(status))}</span>`;
}

function statusText(status) {
  return {
    pending: "待处理",
    processing: "处理中",
    completed: "已完成",
    failed: "失败",
    customer_created: "已生成客户",
    unlinked: "待归档资料",
    draft: "草稿",
    sent: "已发送",
    accepted: "已成交",
    rejected: "已拒绝",
    contacted: "已联系",
    meeting: "已约见",
    ok: "正常",
    none: "无",
  }[status] || status || "未知";
}

function fileTypeText(type) {
  return { image: "图片", audio: "录音", document: "文档", unknown: "其他" }[type] || type || "其他";
}

function sourceTimeText(item) {
  const match = String(item.file_name || "").match(/(?:Screenshot_|IMG_|VID_)?(20\d{6})[_-](\d{6})/i);
  if (!match) return "资料时间未知";
  const [, datePart, timePart] = match;
  const date = new Date(Number(datePart.slice(0, 4)), Number(datePart.slice(4, 6)) - 1, Number(datePart.slice(6, 8)), Number(timePart.slice(0, 2)), Number(timePart.slice(2, 4)));
  return `资料 ${formatDate(date)}`;
}

function formatDate(value) {
  if (!value) return "";
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}

function firstLine(value = "") {
  return String(value).split("\n").find(Boolean) || "";
}

function phoneCell(phone) {
  if (!phone) return "未提及";
  const dial = String(phone).replace(/[^\d+*#]/g, "");
  return `<span class="cell-main">${esc(phone)}</span><a class="cell-sub" href="tel:${esc(dial)}">一键拨号</a>`;
}

function wechatCell(item) {
  if (!item.wechat_id && !item.wechat_nickname) return "未提及";
  return `<span class="cell-main">${esc(item.wechat_nickname || "未提及")}</span><span class="cell-sub">${esc(item.wechat_id || "微信号未提及")}</span>`;
}

function ownerCell(item) {
  if (!item.owner_name && !item.owner_username) return "未分配";
  return `<span class="cell-main">${esc(item.owner_name || item.owner_username)}</span><span class="cell-sub">${esc(item.owner_username || "")}</span>`;
}

function uploaderCell(item) {
  if (!item.uploader_name && !item.uploader_username) return "未记录";
  return `<span class="cell-main">${esc(item.uploader_name || item.uploader_username)}</span><span class="cell-sub">${esc(item.uploader_username || "")}</span>`;
}

function salesOptions() {
  return `<option value="">选择销售</option>${state.salesUsers.map((user) => `<option value="${user.id}">${esc(user.name)}（${esc(user.username)}）</option>`).join("")}`;
}

function intentOptions(selected) {
  return ["高意向", "中意向", "低意向", "暂无意向", "无法判断"].map((item) => `<option ${item === selected ? "selected" : ""}>${item}</option>`).join("");
}

function stageText(stage) {
  return { lead: "新线索", followup: "跟进中", negotiation: "谈判中", closed_won: "已成交", closed_lost: "已流失" }[stage] || "新线索";
}

function stageOptions(selected) {
  return [["lead", "新线索"], ["followup", "跟进中"], ["negotiation", "谈判中"], ["closed_won", "已成交"], ["closed_lost", "已流失"]]
    .map(([value, label]) => `<option value="${value}" ${value === selected ? "selected" : ""}>${label}</option>`).join("");
}

function followupSourceText(source) {
  return { call_auto: "通话自动跟进", material_auto: "资料自动跟进", manual_note: "人工备注", manual: "人工备注" }[source] || "跟进记录";
}

window.showCustomerDetail = showCustomerDetail;
window.showUploadDetail = showUploadDetail;
window.reanalyzeUpload = reanalyzeUpload;
window.assignCustomer = assignCustomer;
window.openSalesCustomers = openSalesCustomers;
window.submitCustomerEdit = submitCustomerEdit;
window.deleteCustomer = deleteCustomer;
window.submitQuotation = submitQuotation;
window.updateQuotationStatus = updateQuotationStatus;
window.markFollowup = markFollowup;
window.deleteScript = deleteScript;
