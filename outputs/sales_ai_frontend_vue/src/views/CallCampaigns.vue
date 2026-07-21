<template>
  <div>
    <div class="toolbar">
      <el-select v-model="query.status" clearable placeholder="全部状态" @change="load">
        <el-option label="草稿" value="draft" />
        <el-option label="进行中" value="running" />
        <el-option label="已暂停" value="paused" />
        <el-option label="已完成" value="completed" />
      </el-select>
      <el-button type="primary" @click="openCreate">新建外呼任务</el-button>
      <el-button @click="refreshAll">刷新</el-button>
    </div>

    <el-alert
      v-if="providerStatusError"
      class="provider-alert"
      type="warning"
      :title="providerStatusError"
      show-icon
      :closable="false"
    />

    <el-table :data="items" v-loading="loading" class="table-card">
      <template #empty>
        <div class="table-empty">
          <strong>还没有外呼任务</strong>
          <span>先新建任务并选择客户，再启动 AI 机器人外呼；结果会进入通话记录。</span>
          <el-button type="primary" @click="openCreate">新建外呼任务</el-button>
        </div>
      </template>
      <el-table-column prop="name" label="任务" min-width="180" />
      <el-table-column label="外呼目的" width="130">
        <template #default="{ row }">{{ scenarioText(row.scenario) }}</template>
      </el-table-column>
      <el-table-column prop="status" label="状态" width="110">
        <template #default="{ row }"><el-tag>{{ statusText(row.status) }}</el-tag></template>
      </el-table-column>
      <el-table-column label="进度" min-width="180">
        <template #default="{ row }">{{ row.called_count || 0 }} / {{ row.total_count || 0 }}，接通 {{ row.connected_count || 0 }}</template>
      </el-table-column>
      <el-table-column prop="high_intent_count" label="高意向" width="90" />
      <el-table-column label="操作" width="340" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="$router.push(`/call-center/campaigns/${row.id}`)">查看任务</el-button>
          <el-tooltip :content="robotStartDisabledReason(row)" :disabled="canStartAiRobot(row)" placement="top">
            <span class="inline-action-wrap">
              <el-button
                link
                type="success"
                :disabled="!canStartAiRobot(row)"
                :loading="robotStartingId === row.id"
                @click="startAiRobot(row)"
              >
                AI机器人外呼
              </el-button>
            </span>
          </el-tooltip>
          <el-button v-if="row.status !== 'running'" link type="success" @click="changeStatus(row, 'start')">开始</el-button>
          <el-button v-if="row.status === 'running'" link type="warning" @click="changeStatus(row, 'pause')">暂停</el-button>
          <el-button link type="info" @click="changeStatus(row, 'complete')">结束</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="visible" title="新建外呼任务" width="820px" destroy-on-close>
      <el-form :model="form" label-position="top">
        <el-row :gutter="14">
          <el-col :span="12"><el-form-item label="任务名称"><el-input v-model="form.name" /></el-form-item></el-col>
          <el-col :span="12">
            <el-form-item label="外呼目的">
              <el-select v-model="form.scenario">
                <el-option label="销售线索筛选" value="lead_filter" />
                <el-option label="客户回访" value="customer_callback" />
                <el-option label="活动邀约" value="activity_invite" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="分配销售">
              <el-select v-model="form.assigned_user_id" clearable placeholder="不选则沿用客户负责人">
                <el-option v-for="user in salesUsers" :key="user.id" :label="user.name" :value="user.id" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="24"><el-form-item label="说明"><el-input v-model="form.description" type="textarea" :rows="2" /></el-form-item></el-col>
          <el-col :span="24">
            <el-form-item label="选择客户">
              <el-select v-model="form.customer_ids" multiple filterable placeholder="选择要外呼的客户" style="width:100%">
                <el-option v-for="customer in customers" :key="customer.id" :label="`${customer.name || '未命名客户'} ${customer.phone || ''}`" :value="customer.id" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
      <template #footer>
        <el-button @click="visible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存任务</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import http from "../api/http";

const loading = ref(false);
const saving = ref(false);
const visible = ref(false);
const items = ref([]);
const customers = ref([]);
const salesUsers = ref([]);
const robotStartingId = ref(null);
const providerStatusLoading = ref(false);
const providerStatusError = ref("");
const callProviderStatus = ref(null);
const query = reactive({ status: "" });
const form = reactive({ name: "", scenario: "lead_filter", description: "", assigned_user_id: null, customer_ids: [] });

function statusText(value) {
  return ({ draft: "草稿", running: "进行中", paused: "已暂停", completed: "已完成", cancelled: "已取消" })[value] || value;
}

function scenarioText(value) {
  return ({
    lead_filter: "线索筛选",
    ai_robot_lead_filter: "线索筛选",
    customer_callback: "客户回访",
    activity_invite: "活动邀约"
  })[value] || value || "-";
}

async function refreshAll() {
  await Promise.all([load(), loadCallProviderStatus()]);
}

async function load() {
  loading.value = true;
  try {
    const params = new URLSearchParams();
    if (query.status) params.set("status", query.status);
    const data = await http.get(`/api/call-campaigns?${params}`);
    items.value = data.items || [];
  } finally {
    loading.value = false;
  }
}

async function loadCallProviderStatus() {
  providerStatusLoading.value = true;
  providerStatusError.value = "";
  try {
    callProviderStatus.value = await http.get("/api/call-provider/status");
  } catch (error) {
    callProviderStatus.value = null;
    providerStatusError.value = error.message || "无法读取外呼服务商状态";
  } finally {
    providerStatusLoading.value = false;
  }
}

async function loadOptions() {
  const customerData = await http.get("/api/customers?page_size=100");
  customers.value = Array.isArray(customerData) ? customerData : (customerData.items || []);
  try {
    const userData = await http.get("/api/users?role=sales&status=active&page_size=200");
    salesUsers.value = Array.isArray(userData) ? userData : (userData.items || []);
  } catch {
    salesUsers.value = [];
  }
}

async function openCreate() {
  Object.assign(form, { name: "", scenario: "lead_filter", description: "", assigned_user_id: null, customer_ids: [] });
  visible.value = true;
  try {
    await loadOptions();
  } catch (error) {
    ElMessage.error(error.message || "Failed to load customers");
  }
}

async function save() {
  if (!form.name.trim()) return ElMessage.warning("请填写任务名称");
  saving.value = true;
  try {
    await http.post("/api/call-campaigns", form);
    ElMessage.success("外呼任务已创建");
    visible.value = false;
    load();
  } finally {
    saving.value = false;
  }
}

async function changeStatus(row, action) {
  await http.post(`/api/call-campaigns/${row.id}/${action}`);
  ElMessage.success("状态已更新");
  load();
}

async function startAiRobot(row) {
  const disabledReason = robotStartDisabledReason(row);
  if (disabledReason) return ElMessage.warning(disabledReason);

  const pendingCount = pendingCustomerCount(row);
  const maxCalls = robotBatchLimit(row);
  try {
    await ElMessageBox.confirm(
      robotConfirmHtml(row, pendingCount, maxCalls),
      "确认启动 AI 机器人外呼",
      {
        type: "warning",
        dangerouslyUseHTMLString: true,
        confirmButtonText: "立即启动",
        cancelButtonText: "取消"
      }
    );
  } catch {
    return;
  }

  robotStartingId.value = row.id;
  try {
    const result = await http.post(`/api/call-campaigns/${row.id}/ai-robot/start`, {
      provider: callProvider(),
      max_calls: maxCalls,
      only_pending: true
    });
    ElMessage.success(`AI机器人外呼已启动：${result.launched || 0} 个客户，跳过 ${result.skipped || 0} 个`);
    await load();
  } finally {
    robotStartingId.value = null;
  }
}

onMounted(() => {
  load();
  loadOptions();
  loadCallProviderStatus();
});

function canStartAiRobot(row) {
  return !robotStartDisabledReason(row);
}

function robotStartDisabledReason(row) {
  if (robotStartingId.value === row.id) return "";
  if (providerStatusLoading.value && !callProviderStatus.value) return "正在读取外呼服务商状态";
  if (providerStatusError.value) return providerStatusError.value;
  if (!callProviderStatus.value) return "未读取到外呼服务商状态";
  if (!callProviderStatus.value.configured) return "外呼服务商配置未完整";
  if (totalCustomerCount(row) <= 0) return "这个任务还没有客户";
  if (pendingCustomerCount(row) <= 0) return "没有待拨客户";
  if (row.status === "completed" || row.status === "cancelled") return "已结束任务不能启动机器人外呼";
  return "";
}

function totalCustomerCount(row) {
  return Number(row.total_count || 0);
}

function pendingCustomerCount(row) {
  return Math.max(totalCustomerCount(row) - Number(row.called_count || 0), 0);
}

function robotBatchLimit(row) {
  return Math.max(1, Math.min(pendingCustomerCount(row), 20));
}

function callProvider() {
  return String(callProviderStatus.value?.provider || "mock");
}

function providerText(value) {
  return ({
    mock: "演示服务商",
    tencent: "腾讯云呼叫中心",
    aliyun: "阿里云语音外呼",
    sip: "自建 SIP 网关"
  })[value] || value || "未配置";
}

function robotConfirmHtml(row, pendingCount, maxCalls) {
  const rows = [
    ["任务", row.name || "-"],
    ["外呼目的", scenarioText(row.scenario)],
    ["外呼服务商", providerText(callProvider())],
    ["本次待拨客户", `${pendingCount} 个`],
    ["本次最多拨打", `${maxCalls} 个，只拨未拨客户`]
  ];
  return `<div class="robot-confirm">${rows.map(([label, value]) => (
    `<div class="robot-confirm-row"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`
  )).join("")}</div>`;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}
</script>

<style scoped>
.provider-alert {
  margin-bottom: 12px;
}

.inline-action-wrap {
  display: inline-flex;
}

.table-empty {
  display: grid;
  justify-items: center;
  gap: 8px;
  padding: 26px 12px;
  color: #667085;
  line-height: 1.6;
}

.table-empty strong {
  color: #111827;
  font-size: 16px;
}

:global(.robot-confirm) {
  display: grid;
  gap: 8px;
  margin-top: 4px;
}

:global(.robot-confirm-row) {
  display: grid;
  grid-template-columns: 98px minmax(0, 1fr);
  gap: 10px;
  align-items: start;
  line-height: 1.6;
}

:global(.robot-confirm-row span) {
  color: #667085;
}

:global(.robot-confirm-row strong) {
  color: #101828;
  font-weight: 800;
}
</style>
