<template>
  <div>
    <div class="toolbar">
      <el-input v-model="query.keyword" clearable placeholder="搜客户/电话/微信/聊天关键词" @keyup.enter="load" />
      <el-select v-if="isAdmin" v-model="query.owner_id" clearable placeholder="全部销售">
        <el-option v-for="user in salesUsers" :key="user.id" :label="user.name" :value="user.id" />
      </el-select>
      <el-select v-model="query.intent_level" clearable placeholder="全部意向">
        <el-option label="高意向" value="高意向" /><el-option label="中意向" value="中意向" /><el-option label="低意向" value="低意向" /><el-option label="无法判断" value="无法判断" />
      </el-select>
      <el-button type="primary" @click="load">查询</el-button>
      <el-button v-if="isAdmin" class="dedupe-button" @click="openDuplicates">查看疑似重复</el-button>
      <el-button v-if="isAdmin" class="dedupe-button danger" type="warning" @click="autoDeduplicate">一键合并重复</el-button>
    </div>

    <el-table
      :data="items"
      v-loading="loading && items.length === 0"
      class="table-card customer-table"
      row-key="id"
      height="calc(100vh - 250px)"
      :empty-text="loadError || '暂无客户数据。上传资料或新增客户后会出现在这里。'"
    >
      <el-table-column label="客户" min-width="160">
        <template #default="{ row }">
          <strong>{{ row.name || "未命名客户" }}</strong>
          <el-tag v-if="isHighIntent(row)" class="high-intent-tag" type="danger" size="small">AI高意向</el-tag>
          <div class="muted">ID {{ row.id }}</div>
        </template>
      </el-table-column>
      <el-table-column label="联系信息" min-width="260">
        <template #default="{ row }">
          <div class="contact-line">
            <strong>{{ row.phone || "电话未提及" }}</strong>
          </div>
          <div class="muted">微信：{{ row.wechat_id || row.wechat_nickname || "未提及" }}</div>
        </template>
      </el-table-column>
      <el-table-column label="负责销售" min-width="140">
        <template #default="{ row }">{{ row.owner_name || "未分配" }}<div class="muted">{{ row.owner_username || "" }}</div></template>
      </el-table-column>
      <el-table-column label="意向" min-width="140">
        <template #default="{ row }">
          <el-tag :type="isHighIntent(row) ? 'danger' : 'info'">{{ row.intent_level || "无法判断" }} · {{ row.intent_score || 0 }}</el-tag>
          <div v-if="isHighIntent(row)" class="robot-hint">建议一键回拨</div>
        </template>
      </el-table-column>
      <el-table-column prop="demand_summary" label="客户需求" min-width="220" show-overflow-tooltip />
      <el-table-column prop="next_action" label="下一步" min-width="240" show-overflow-tooltip />
      <el-table-column prop="created_at" label="入库时间" width="140">
        <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="270" align="center" fixed="right">
        <template #default="{ row }">
          <div class="table-actions">
            <el-button
              v-if="canDirectCallback(row)"
              class="action-call"
              size="small"
              type="primary"
              :loading="callbackLoadingId === row.id"
              @click="dialCustomer(row)"
            >
              一键回拨
            </el-button>
            <el-button
              v-else-if="!row.phone"
              class="action-missing-contact"
              size="small"
              type="warning"
              plain
              @click="edit(row)"
            >
              补电话
            </el-button>
            <el-button
              v-else-if="isAdmin"
              class="action-missing-contact"
              size="small"
              type="warning"
              plain
              @click="edit(row)"
            >
              {{ row.owner_id ? "调整销售" : "分配销售" }}
            </el-button>
            <el-button
              v-else-if="row.phone && !hasCurrentSalesPhone()"
              class="action-missing-contact"
              size="small"
              type="warning"
              plain
              @click="showCurrentSalesPhoneHint"
            >
              补销售手机号
            </el-button>
            <el-button link type="primary" @click="openDetail(row)">跟进记录</el-button>
            <el-button link type="primary" @click="edit(row)">编辑</el-button>
            <el-button v-if="isAdmin" link type="danger" @click="remove(row)">删除</el-button>
          </div>
        </template>
      </el-table-column>
    </el-table>

    <el-pagination v-model:current-page="query.page" v-model:page-size="query.page_size" :total="total" layout="total, prev, pager, next, sizes" @change="load" />

    <el-dialog v-model="dialogVisible" title="编辑客户信息" width="780px" destroy-on-close>
      <el-form :model="form" label-position="top">
        <el-row :gutter="14">
          <el-col :span="12"><el-form-item label="客户姓名"><el-input v-model="form.name" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="客户电话"><el-input v-model="form.phone" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="微信号"><el-input v-model="form.wechat_id" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="微信昵称"><el-input v-model="form.wechat_nickname" /></el-form-item></el-col>
          <el-col v-if="isAdmin" :span="12"><el-form-item label="负责销售"><el-select v-model="form.owner_id" clearable><el-option v-for="user in salesUsers" :key="user.id" :label="user.name" :value="user.id" /></el-select></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="意向等级"><el-select v-model="form.intent_level"><el-option label="高意向" value="高意向" /><el-option label="中意向" value="中意向" /><el-option label="低意向" value="低意向" /><el-option label="无法判断" value="无法判断" /></el-select></el-form-item></el-col>
          <el-col :span="24"><el-form-item label="客户需求"><el-input v-model="form.demand_summary" type="textarea" :rows="3" /></el-form-item></el-col>
          <el-col :span="24"><el-form-item label="下一步"><el-input v-model="form.next_action" type="textarea" :rows="3" /></el-form-item></el-col>
        </el-row>
      </el-form>
      <template #footer><el-button @click="dialogVisible = false">取消</el-button><el-button type="primary" @click="save">保存修改</el-button></template>
    </el-dialog>

    <el-dialog v-model="duplicatesVisible" title="疑似重复客户" width="960px" destroy-on-close>
      <div v-loading="duplicatesLoading">
        <el-empty v-if="!duplicateGroups.length" description="暂未发现疑似重复客户" />
        <div v-for="group in duplicateGroups" v-else :key="`${group.reason}-${group.match_value}`" style="margin-bottom: 18px;">
          <el-alert
            :title="`${group.reason}：${group.match_value}`"
            type="warning"
            :closable="false"
            show-icon
            style="margin-bottom: 10px;"
          />
          <el-table :data="group.customers" border>
            <el-table-column label="客户" min-width="150">
              <template #default="{ row, $index }">
                <strong>{{ row.name || "未命名客户" }}</strong>
                <el-tag v-if="$index === 0" size="small" type="success" style="margin-left: 6px;">建议保留</el-tag>
                <div class="muted">ID {{ row.id }}</div>
              </template>
            </el-table-column>
            <el-table-column label="联系信息" min-width="190">
              <template #default="{ row }">
                <div>{{ row.phone || "电话未提及" }}</div>
                <div class="muted">微信：{{ row.wechat_id || row.wechat_nickname || "未提及" }}</div>
              </template>
            </el-table-column>
            <el-table-column label="负责销售" min-width="130">
              <template #default="{ row }">{{ row.owner_name || "未分配" }}</template>
            </el-table-column>
            <el-table-column label="意向" width="120">
              <template #default="{ row }">{{ row.intent_level }} · {{ row.intent_score || 0 }}</template>
            </el-table-column>
            <el-table-column prop="demand_summary" label="客户需求" min-width="220" show-overflow-tooltip />
            <el-table-column label="操作" width="150" align="center">
              <template #default="{ row, $index }">
                <el-tag v-if="$index === 0" type="success">主客户</el-tag>
                <el-button v-else link type="danger" @click="mergeDuplicate(group.customers[0], row)">合并到主客户</el-button>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </div>
      <template #footer>
        <el-button @click="duplicatesVisible = false">关闭</el-button>
        <el-button type="primary" @click="loadDuplicates">重新扫描</el-button>
      </template>
    </el-dialog>

    <el-drawer v-model="detailVisible" title="客户详情与跟进记录" size="640px" destroy-on-close>
      <section v-if="detailCustomer" class="detail-section">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="客户">{{ detailCustomer.name || "未命名客户" }}</el-descriptions-item>
          <el-descriptions-item label="电话">{{ detailCustomer.phone || "未提及" }}</el-descriptions-item>
          <el-descriptions-item label="微信">{{ detailCustomer.wechat_id || detailCustomer.wechat_nickname || "未提及" }}</el-descriptions-item>
          <el-descriptions-item label="负责销售">{{ detailCustomer.owner_name || "未分配" }}</el-descriptions-item>
          <el-descriptions-item label="意向">
            <el-tag :type="isHighIntent(detailCustomer) ? 'danger' : 'info'">{{ detailCustomer.intent_level || "无法判断" }} · {{ detailCustomer.intent_score || 0 }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="下一步">{{ detailCustomer.next_action || "-" }}</el-descriptions-item>
        </el-descriptions>

        <el-alert
          v-if="isHighIntent(detailCustomer)"
          class="detail-alert"
          type="warning"
          show-icon
          :closable="false"
          title="系统已判定高意向，建议销售一键回拨。"
        />

        <div class="drawer-actions">
          <el-button
            v-if="canDirectCallback(detailCustomer)"
            type="primary"
            :loading="callbackLoadingId === detailCustomer.id"
            @click="dialCustomer(detailCustomer)"
          >
            一键回拨
          </el-button>
          <el-button v-else-if="!detailCustomer.phone || isAdmin" type="warning" plain @click="edit(detailCustomer)">
            {{ !detailCustomer.phone ? "补充电话" : (detailCustomer.owner_id ? "调整销售" : "分配销售") }}
          </el-button>
          <el-button v-else-if="!hasCurrentSalesPhone()" type="warning" plain @click="showCurrentSalesPhoneHint">
            补销售手机号
          </el-button>
          <el-button @click="loadFollowups()">刷新跟进记录</el-button>
        </div>

        <el-divider content-position="left">跟进记录</el-divider>
        <div v-loading="followupsLoading">
          <el-empty v-if="!followups.length" description="暂无跟进记录。一键回拨或 AI机器人外呼完成后会自动写入这里。" />
          <el-timeline v-else>
            <el-timeline-item
              v-for="item in followups"
              :key="item.id"
              :timestamp="formatTime(item.created_at)"
              :type="followupTimelineType(item.source)"
              placement="top"
            >
              <article class="followup-card">
                <div class="followup-head">
                  <el-tag :type="followupTagType(item.source)" size="small">{{ followupSourceText(item.source) }}</el-tag>
                  <span v-if="item.call_recording_id" class="muted">录音 ID {{ item.call_recording_id }}</span>
                  <span v-if="item.upload_record_id" class="muted">资料 ID {{ item.upload_record_id }}</span>
                </div>
                <pre>{{ item.content }}</pre>
              </article>
            </el-timeline-item>
          </el-timeline>
        </div>
      </section>
    </el-drawer>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import { useRoute } from "vue-router";
import dayjs from "dayjs";
import { ElMessage, ElMessageBox } from "element-plus";
import http from "../api/http";
import { useAuthStore } from "../stores/auth";

const loading = ref(false);
const loadError = ref("");
const items = ref([]);
const total = ref(0);
const salesUsers = ref([]);
const dialogVisible = ref(false);
const duplicatesVisible = ref(false);
const duplicatesLoading = ref(false);
const duplicateGroups = ref([]);
const callbackLoadingId = ref(null);
const detailVisible = ref(false);
const detailCustomer = ref(null);
const followups = ref([]);
const followupsLoading = ref(false);
const form = reactive({});
const query = reactive({ keyword: "", owner_id: "", intent_level: "", page: 1, page_size: 20 });
const pollTimer = ref(null);
const lastDataSignature = ref("");
const auth = useAuthStore();
const route = useRoute();
const isAdmin = computed(() => auth.isAdmin);

const POLL_INTERVAL_MS = 5000;

async function loadSales() {
  if (!isAdmin.value) {
    salesUsers.value = [];
    return;
  }
  try { salesUsers.value = await http.get("/api/users?role=sales&status=active&page_size=200"); } catch { salesUsers.value = []; }
}

function customerDataSignature(records, nextTotal) {
  return JSON.stringify({
    total: nextTotal,
    rows: records.map((row) => ({
      id: row.id,
      name: row.name,
      phone: row.phone,
      wechat_id: row.wechat_id,
      wechat_nickname: row.wechat_nickname,
      owner_id: row.owner_id,
      owner_name: row.owner_name,
      owner_username: row.owner_username,
      intent_level: row.intent_level,
      intent_score: row.intent_score,
      demand_summary: row.demand_summary,
      next_action: row.next_action,
      updated_at: row.updated_at
    }))
  });
}

function applyCustomerData(nextItems, nextTotal, options = {}) {
  const signature = customerDataSignature(nextItems, nextTotal);
  if (!options.force && signature === lastDataSignature.value) {
    total.value = nextTotal;
    return false;
  }

  lastDataSignature.value = signature;
  const currentById = new Map(items.value.map((item) => [item.id, item]));
  items.value = nextItems.map((nextItem) => {
    const existing = currentById.get(nextItem.id);
    if (!existing) return nextItem;
    Object.assign(existing, nextItem);
    return existing;
  });
  total.value = nextTotal;
  return true;
}

async function load(options = {}) {
  const silent = options.silent === true;
  if (!silent) loading.value = true;
  try {
    loadError.value = "";
    const params = new URLSearchParams();
    Object.entries(query).forEach(([key, value]) => value && params.set(key, value));
    const data = await http.get(`/api/customers?${params}`);
    applyCustomerData(data.items || [], data.total || 0, { force: !silent });
  } catch (error) {
    if (silent) return;
    loadError.value = error.message || "客户数据加载失败";
    items.value = [];
    total.value = 0;
    lastDataSignature.value = "";
    if (loadError.value !== "登录已失效，请重新登录") ElMessage.error(loadError.value);
  } finally {
    if (!silent) loading.value = false;
  }
}

function startPolling() {
  if (pollTimer.value) return;
  pollTimer.value = window.setInterval(() => {
    load({ silent: true });
  }, POLL_INTERVAL_MS);
}

function stopPolling() {
  if (!pollTimer.value) return;
  window.clearInterval(pollTimer.value);
  pollTimer.value = null;
}
function edit(row) {
  Object.assign(form, JSON.parse(JSON.stringify(row)));
  dialogVisible.value = true;
}
async function save() {
  const payload = { ...form };
  if (!isAdmin.value) {
    delete payload.owner_id;
    delete payload.lead_status;
    delete payload.lead_source;
    delete payload.source;
  }
  await http.patch(`/api/customers/${form.id}`, payload);
  ElMessage.success("客户信息已保存");
  dialogVisible.value = false;
  await load({ silent: true });
}
function formatTime(value) {
  return value ? dayjs(value).format("MM-DD HH:mm") : "-";
}

function dialPhone(phone) {
  return String(phone || "").replace(/[^\d+*#]/g, "");
}

function callbackSalesUser(row) {
  return salesUsers.value.find((user) => Number(user.id) === Number(row?.owner_id));
}

function hasCallbackSalesPhone(row) {
  return Boolean(dialPhone(callbackSalesUser(row)?.phone));
}

function hasCurrentSalesPhone() {
  return Boolean(dialPhone(auth.user?.phone));
}

function canDirectCallback(row) {
  if (!dialPhone(row?.phone)) return false;
  if (!isAdmin.value) return hasCurrentSalesPhone();
  return hasCallbackSalesPhone(row);
}

function callbackSalesHint(row) {
  if (!row?.owner_id) return "请先分配有手机号的销售，再发起一键回拨";
  return "负责销售没有手机号，请先在销售账号补手机号或改派给有手机号的销售";
}

function showCurrentSalesPhoneHint() {
  ElMessage.warning("当前销售账号没有手机号，请让管理员先在销售账号里补手机号");
}

async function dialCustomer(row) {
  const phone = dialPhone(row.phone);
  if (!phone) return ElMessage.warning("这个客户没有可回拨电话");
  if (!isAdmin.value && !hasCurrentSalesPhone()) return showCurrentSalesPhoneHint();
  if (isAdmin.value && !hasCallbackSalesPhone(row)) return ElMessage.warning(callbackSalesHint(row));
  callbackLoadingId.value = row.id;
  try {
    const payload = {
      customer_phone: phone,
      remark: isAdmin.value ? "客户池一键回拨" : "销售客户池一键回拨"
    };
    if (isAdmin.value && row.owner_id) payload.sales_id = row.owner_id;
    const callback = await http.post(`/api/customers/${row.id}/callback`, payload);
    ElMessage.success(`已发起服务商回拨，通话ID：${callback.provider_call_id}`);
    await load({ silent: true });
    if (detailVisible.value && detailCustomer.value?.id === row.id) {
      await loadFollowups(row.id);
    }
  } finally {
    callbackLoadingId.value = null;
  }
}

async function openDetail(row) {
  detailCustomer.value = row;
  detailVisible.value = true;
  await loadFollowups(row.id);
}

async function loadFollowups(customerId = detailCustomer.value?.id) {
  if (!customerId) return;
  followupsLoading.value = true;
  try {
    followups.value = await http.get(`/api/customers/${customerId}/followups`);
  } finally {
    followupsLoading.value = false;
  }
}

async function openDetailById(customerId) {
  const id = Number(customerId);
  if (!id) return;
  const existing = items.value.find((item) => Number(item.id) === id);
  if (existing) {
    await openDetail(existing);
    return;
  }
  try {
    const customer = await http.get(`/api/customers/${id}`);
    await openDetail(customer);
  } catch (error) {
    ElMessage.warning(error.message || "无法打开客户跟进记录");
  }
}

async function handleRouteFollowupQuery() {
  const customerId = route.query.followup_customer_id || route.query.customer_id;
  if (customerId) await openDetailById(customerId);
}

function isHighIntent(row) {
  return Number(row?.intent_score || 0) >= 80 || String(row?.intent_level || "").includes("高");
}

function followupSourceText(source) {
  return ({
    assignment: "线索分配",
    ai_robot: "AI机器人外呼",
    sales_callback: "销售回拨",
    manual_note: "人工跟进"
  })[source] || source || "跟进记录";
}

function followupTagType(source) {
  return ({
    assignment: "primary",
    ai_robot: "success",
    sales_callback: "warning",
    manual_note: "info"
  })[source] || "info";
}

function followupTimelineType(source) {
  return ({
    assignment: "primary",
    ai_robot: "success",
    sales_callback: "warning"
  })[source] || "primary";
}

async function remove(row) {
  if (!isAdmin.value) return ElMessage.warning("只有管理员可以删除客户");
  await ElMessageBox.confirm(`确定删除客户「${row.name || row.id}」吗？`, "删除客户", { type: "warning" });
  await http.delete(`/api/customers/${row.id}`);
  ElMessage.success("已删除");
  await load({ silent: true });
}
async function openDuplicates() {
  if (!isAdmin.value) return;
  duplicatesVisible.value = true;
  await loadDuplicates();
}
async function loadDuplicates() {
  if (!isAdmin.value) return;
  duplicatesLoading.value = true;
  try {
    const data = await http.get("/api/customers/duplicates?limit=100");
    duplicateGroups.value = data.items || [];
  } finally {
    duplicatesLoading.value = false;
  }
}
async function autoDeduplicate() {
  if (!isAdmin.value) return ElMessage.warning("只有管理员可以合并重复客户");
  await ElMessageBox.confirm(
    "系统会按手机号和微信号自动合并重复客户，资料、跟进、录音和外呼记录都会迁移到保留客户下。确定继续吗？",
    "自动合并重复客户",
    { type: "warning" }
  );
  const result = await http.post("/api/customers/deduplicate");
  ElMessage.success(`已合并 ${result.merged_count || 0} 个重复客户`);
  await Promise.all([load({ silent: true }), duplicatesVisible.value ? loadDuplicates() : Promise.resolve()]);
}
async function mergeDuplicate(target, source) {
  if (!isAdmin.value) return;
  await ElMessageBox.confirm(
    `确定把「${source.name || source.id}」合并到「${target.name || target.id}」吗？资料、跟进、录音和外呼记录都会迁移到主客户。`,
    "合并重复客户",
    { type: "warning" }
  );
  await http.post(`/api/customers/${target.id}/merge`, { source_customer_id: source.id });
  ElMessage.success("重复客户已合并");
  await Promise.all([load({ silent: true }), loadDuplicates()]);
}
watch(() => route.query.followup_customer_id, () => {
  handleRouteFollowupQuery();
});

onMounted(async () => {
  await loadSales();
  await load();
  await handleRouteFollowupQuery();
  startPolling();
});

onBeforeUnmount(() => {
  stopPolling();
});
</script>

<style scoped>
.contact-line {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.contact-line strong {
  font-size: 17px;
  letter-spacing: .01em;
}
.dedupe-button {
  font-weight: 900;
}
.dedupe-button.danger {
  color: #8a3b00;
  background: #fff7ed;
  border-color: #fed7aa;
}
.table-actions {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  white-space: nowrap;
}
.action-call {
  min-width: 76px;
  border: 0;
  border-radius: 999px;
  font-weight: 900;
  background: linear-gradient(135deg, #0f63ff, #08a7a7);
  box-shadow: 0 8px 18px rgba(15, 99, 255, .18);
}
.action-missing-contact {
  min-width: 76px;
  border-radius: 999px;
  font-weight: 900;
}
.high-intent-tag {
  margin-left: 8px;
  vertical-align: 1px;
}
.robot-hint {
  margin-top: 5px;
  color: #d93050;
  font-size: 12px;
  font-weight: 800;
}
.detail-section {
  display: grid;
  gap: 16px;
}
.detail-alert {
  margin-top: 2px;
}
.drawer-actions {
  display: flex;
  gap: 10px;
}
.followup-card {
  border: 1px solid #e4edf3;
  border-radius: 12px;
  padding: 12px;
  background: #fbfdff;
}
.followup-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}
.followup-card pre {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  color: #17202a;
  font-family: inherit;
  line-height: 1.7;
}
</style>
