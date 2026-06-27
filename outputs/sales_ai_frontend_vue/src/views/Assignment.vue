<template>
  <div>
    <div class="toolbar">
      <el-input v-model="keyword" clearable placeholder="搜客户/电话/微信/来源" @keyup.enter="load" />
      <el-button type="primary" @click="load">查询未分配线索</el-button>
    </div>

    <el-table :data="items" v-loading="loading" class="table-card">
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
            <el-option v-for="user in salesUsers" :key="user.id" :label="user.name" :value="user.id" />
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
import { onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import http from "../api/http";

const keyword = ref("");
const loading = ref(false);
const items = ref([]);
const salesUsers = ref([]);
const assignMap = reactive({});

async function loadSales() {
  salesUsers.value = await http.get("/api/users?role=sales&status=active&page_size=200");
}
async function load() {
  loading.value = true;
  try {
    const params = new URLSearchParams({ lead_status: "unassigned", page_size: "100" });
    if (keyword.value) params.set("keyword", keyword.value);
    const data = await http.get(`/api/customers?${params}`);
    items.value = data.items || [];
  } finally { loading.value = false; }
}
async function assign(row) {
  const ownerId = assignMap[row.id];
  if (!ownerId) return ElMessage.warning("请先选择销售");
  await http.post(`/api/customers/${row.id}/assign`, { owner_id: ownerId });
  ElMessage.success("线索已分配");
  load();
}
onMounted(() => { loadSales(); load(); });
</script>
