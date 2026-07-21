<template>
  <div>
    <div class="toolbar assignment-toolbar">
      <el-input v-model="keyword" clearable placeholder="搜客户/电话/微信/来源" @keyup.enter="load" />
      <el-select
        v-model="selectedSalesIds"
        multiple
        collapse-tags
        collapse-tags-tooltip
        clearable
        placeholder="参与随机分配销售"
        class="sales-select"
      >
        <el-option v-for="user in salesUsers" :key="user.id" :label="salesLabel(user)" :value="user.id" />
      </el-select>
      <el-button type="primary" @click="load">查询未分配线索</el-button>
      <el-button type="success" :loading="randomLoading" @click="randomAssign">一键随机分配</el-button>
    </div>

    <div class="assignment-summary">
      <article>
        <span>未分配线索</span>
        <strong>{{ total }}</strong>
      </article>
      <article>
        <span>参与销售</span>
        <strong>{{ selectedSalesCount }}</strong>
      </article>
    </div>

    <el-table :data="items" v-loading="loading" class="table-card">
      <template #empty>
        <div class="table-empty">
          <strong>当前没有未分配线索</strong>
          <span>客户池里未分配的客户会出现在这里，可以手动分配或一键随机分配。</span>
        </div>
      </template>
      <el-table-column label="客户" min-width="150">
        <template #default="{ row }"><strong>{{ row.name || "未命名客户" }}</strong><div class="muted">ID {{ row.id }}</div></template>
      </el-table-column>
      <el-table-column prop="phone" label="电话" min-width="130" />
      <el-table-column prop="wechat_id" label="微信" min-width="130" />
      <el-table-column prop="lead_source" label="来源" min-width="120" />
      <el-table-column prop="demand_summary" label="客户需求" min-width="220" show-overflow-tooltip />
      <el-table-column label="分配给" width="190">
        <template #default="{ row }">
          <el-select v-model="assignMap[row.id]" placeholder="选择销售">
            <el-option v-for="user in salesUsers" :key="user.id" :label="salesLabel(user)" :value="user.id" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="操作" fixed="right" width="120">
        <template #default="{ row }"><el-button type="primary" @click="assign(row)">分配</el-button></template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import http from "../api/http";

const keyword = ref("");
const loading = ref(false);
const randomLoading = ref(false);
const items = ref([]);
const total = ref(0);
const salesUsers = ref([]);
const selectedSalesIds = ref([]);
const assignMap = reactive({});

const selectedSalesCount = computed(() => {
  return selectedSalesIds.value.length || salesUsers.value.length;
});

async function loadSales() {
  salesUsers.value = await http.get("/api/users?role=sales&status=active&page_size=200");
  selectedSalesIds.value = salesUsers.value.map((user) => user.id);
}

async function load() {
  loading.value = true;
  try {
    const params = new URLSearchParams({ lead_status: "unassigned", page_size: "100" });
    if (keyword.value) params.set("keyword", keyword.value);
    const data = await http.get(`/api/customers?${params}`);
    items.value = data.items || [];
    total.value = data.total || 0;
  } finally {
    loading.value = false;
  }
}

async function assign(row) {
  const ownerId = assignMap[row.id];
  if (!ownerId) return ElMessage.warning("请先选择销售");
  await http.post(`/api/customers/${row.id}/assign`, { owner_id: ownerId });
  ElMessage.success("线索已分配");
  load();
}

async function randomAssign() {
  const salesIds = selectedSalesIds.value.length ? selectedSalesIds.value : salesUsers.value.map((user) => user.id);
  if (!salesIds.length) return ElMessage.warning("请先创建或启用销售账号");
  if (!total.value) return ElMessage.warning("当前没有未分配线索");

  await ElMessageBox.confirm(
    `将全部 ${total.value} 条未分配线索随机分配给 ${salesIds.length} 个销售，确定继续吗？`,
    "一键随机分配",
    { type: "warning" }
  );

  randomLoading.value = true;
  try {
    const result = await http.post("/api/customers/assign-random", { sales_user_ids: salesIds });
    const detail = (result.items || [])
      .filter((item) => item.assigned_count > 0)
      .map((item) => `${item.sales_name} ${item.assigned_count} 条`)
      .join("，");
    ElMessage.success(`已分配 ${result.assigned_count || 0} 条${detail ? `：${detail}` : ""}`);
    await load();
  } finally {
    randomLoading.value = false;
  }
}

function salesLabel(user) {
  return user.phone ? `${user.name}（${user.phone}）` : user.name;
}

onMounted(() => {
  loadSales();
  load();
});
</script>

<style scoped>
.assignment-toolbar {
  align-items: center;
}

.sales-select {
  min-width: 240px;
}

.assignment-summary {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 180px));
  gap: 12px;
  margin: 0 0 14px;
}

.assignment-summary article {
  padding: 12px 14px;
  border: 1px solid #dce7f2;
  border-radius: 8px;
  background: #fff;
}

.assignment-summary span {
  display: block;
  color: #667085;
  font-size: 12px;
  font-weight: 800;
}

.assignment-summary strong {
  display: block;
  margin-top: 4px;
  color: #111827;
  font-size: 26px;
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

@media (max-width: 760px) {
  .assignment-summary {
    grid-template-columns: 1fr;
  }

  .sales-select {
    min-width: 100%;
  }
}
</style>
