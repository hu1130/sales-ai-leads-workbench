<template>
  <div>
    <div class="toolbar call-toolbar">
      <el-button type="primary" :loading="loading" @click="load">刷新我的外呼</el-button>
      <span class="toolbar-note">
        {{ isAdmin ? "管理员可查看客户池回拨入口；销售账号只显示分配给自己的客户。" : "管理员分配给你的客户，会出现在这里。" }}
      </span>
    </div>

    <div class="call-summary-grid">
      <section class="summary-tile">
        <span>待回拨客户</span>
        <strong>{{ customers.length }}</strong>
      </section>
      <section class="summary-tile">
        <span>可一键回拨</span>
        <strong>{{ callableCustomerCount }}</strong>
      </section>
      <section class="summary-tile">
        <span>待补电话</span>
        <strong>{{ missingPhoneCount }}</strong>
      </section>
      <section class="summary-tile">
        <span>外呼任务</span>
        <strong>{{ campaigns.length }}</strong>
      </section>
    </div>

    <el-tabs v-model="activeTab" class="work-tabs">
      <el-tab-pane :label="customerTabLabel" name="customers">
        <el-table :data="customers" v-loading="loading" class="table-card customer-work-table">
          <template #empty>
            <div class="table-empty">
              <strong>{{ isAdmin ? "客户池暂无可跟进客户" : "还没有分配给你的客户" }}</strong>
              <span>{{ isAdmin ? "管理员可以先在客户池分配销售，销售登录后会在这里看到自己的客户。" : "管理员在客户池分配客户后，你就能在这里回拨和查看跟进记录。" }}</span>
            </div>
          </template>
          <el-table-column label="客户" min-width="150">
            <template #default="{ row }">
              <strong>{{ row.name || "未命名客户" }}</strong>
              <el-tag v-if="isHighIntent(row)" class="high-intent-tag" size="small" type="danger">AI高意向</el-tag>
              <div class="muted">ID {{ row.id }}</div>
            </template>
          </el-table-column>
          <el-table-column label="联系信息" min-width="190">
            <template #default="{ row }">
              <strong>{{ row.phone || "电话未提及" }}</strong>
              <div class="muted">微信：{{ row.wechat_id || row.wechat_nickname || "未提及" }}</div>
            </template>
          </el-table-column>
          <el-table-column v-if="isAdmin" label="负责销售" min-width="130">
            <template #default="{ row }">{{ row.owner_name || "未分配" }}</template>
          </el-table-column>
          <el-table-column label="意向" min-width="130">
            <template #default="{ row }">
              <el-tag :type="isHighIntent(row) ? 'danger' : 'info'">{{ row.intent_level || "无法判断" }} · {{ row.intent_score || 0 }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="demand_summary" label="客户需求" min-width="220" show-overflow-tooltip />
          <el-table-column prop="next_action" label="下一步" min-width="220" show-overflow-tooltip />
          <el-table-column label="操作" fixed="right" width="230" align="center">
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
                  v-else-if="dialPhone(row.phone) && !hasCurrentSalesPhone()"
                  class="action-missing-contact"
                  size="small"
                  type="warning"
                  plain
                  @click="showCurrentSalesPhoneHint"
                >
                  补销售手机号
                </el-button>
                <el-button v-else class="action-missing-contact" size="small" type="warning" plain @click="goCustomerFollowup(row)">
                  补电话
                </el-button>
                <el-button link type="primary" @click="goCustomerFollowup(row)">跟进记录</el-button>
              </div>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <el-tab-pane label="外呼任务" name="campaigns">
        <el-table :data="campaigns" v-loading="loading" class="table-card">
          <template #empty>
            <div class="table-empty">
              <strong>还没有分配给你的外呼任务</strong>
              <span>外呼任务是批量拨打计划；普通客户分配会先出现在“我的待回拨客户”。</span>
            </div>
          </template>
          <el-table-column prop="name" label="任务" min-width="180" />
          <el-table-column label="状态" width="110">
            <template #default="{ row }"><el-tag>{{ campaignStatusText(row.status) }}</el-tag></template>
          </el-table-column>
          <el-table-column label="进度" min-width="170">
            <template #default="{ row }">{{ row.called_count || 0 }} / {{ row.total_count || 0 }}</template>
          </el-table-column>
          <el-table-column label="操作" width="130">
            <template #default="{ row }"><el-button type="primary" @click="router.push(`/call-center/campaigns/${row.id}`)">进入外呼</el-button></template>
          </el-table-column>
        </el-table>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import http from "../api/http";
import { useAuthStore } from "../stores/auth";

const router = useRouter();
const auth = useAuthStore();
const isAdmin = computed(() => auth.isAdmin);
const loading = ref(false);
const activeTab = ref("customers");
const campaigns = ref([]);
const customers = ref([]);
const callbackLoadingId = ref(null);

const customerTabLabel = computed(() => (isAdmin.value ? "客户池回拨入口" : "我的待回拨客户"));
const callableCustomerCount = computed(() => customers.value.filter((row) => canDirectCallback(row)).length);
const missingPhoneCount = computed(() => customers.value.filter((row) => !dialPhone(row.phone)).length);

async function load() {
  loading.value = true;
  try {
    const [campaignData, customerData] = await Promise.all([
      http.get("/api/call-campaigns?page_size=100"),
      http.get("/api/customers?page_size=100")
    ]);
    campaigns.value = campaignData.items || [];
    customers.value = customerData.items || [];
  } finally {
    loading.value = false;
  }
}

function dialPhone(phone) {
  return String(phone || "").replace(/[^\d+*#]/g, "");
}

function hasCurrentSalesPhone() {
  return isAdmin.value || Boolean(dialPhone(auth.user?.phone));
}

function canDirectCallback(row) {
  return Boolean(dialPhone(row?.phone) && hasCurrentSalesPhone());
}

function showCurrentSalesPhoneHint() {
  ElMessage.warning("当前销售账号没有手机号，请让管理员先在销售账号里补手机号");
}

function isHighIntent(row) {
  return Number(row?.intent_score || 0) >= 80 || String(row?.intent_level || "").includes("高");
}

async function dialCustomer(row) {
  const phone = dialPhone(row.phone);
  if (!phone) return ElMessage.warning("这个客户没有可回拨电话，请先补电话");
  if (!hasCurrentSalesPhone()) return showCurrentSalesPhoneHint();
  callbackLoadingId.value = row.id;
  try {
    const callback = await http.post(`/api/customers/${row.id}/callback`, {
      customer_phone: phone,
      remark: isAdmin.value ? "管理员客户池回拨入口" : "我的外呼一键回拨"
    });
    ElMessage.success(`已发起服务商回拨，通话ID：${callback.provider_call_id}`);
    await load();
  } finally {
    callbackLoadingId.value = null;
  }
}

function goCustomerFollowup(row) {
  router.push({ path: "/customers", query: { followup_customer_id: row.id } });
}

function campaignStatusText(status) {
  return ({ draft: "草稿", running: "进行中", paused: "已暂停", completed: "已完成", cancelled: "已取消" })[status] || status || "-";
}

onMounted(load);
</script>

<style scoped>
.call-toolbar {
  align-items: center;
}

.toolbar-note {
  color: #667085;
  font-size: 13px;
}

.call-summary-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
  margin-bottom: 18px;
}

.summary-tile {
  display: grid;
  gap: 8px;
  padding: 16px 18px;
  border: 1px solid #d8e4ef;
  border-radius: 18px;
  background: rgba(255, 255, 255, .86);
}

.summary-tile span {
  color: #667085;
  font-weight: 800;
}

.summary-tile strong {
  color: #101828;
  font-size: 30px;
  line-height: 1;
}

.work-tabs {
  padding: 16px;
  border: 1px solid #d8e4ef;
  border-radius: 18px;
  background: rgba(255, 255, 255, .9);
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

@media (max-width: 980px) {
  .call-summary-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
