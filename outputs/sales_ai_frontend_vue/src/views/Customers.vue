<template>
  <div>
    <div class="toolbar">
      <el-input v-model="query.keyword" clearable placeholder="搜客户/电话/微信/聊天关键词" @keyup.enter="load" />
      <el-select v-model="query.owner_id" clearable placeholder="全部销售">
        <el-option v-for="user in salesUsers" :key="user.id" :label="user.name" :value="user.id" />
      </el-select>
      <el-select v-model="query.intent_level" clearable placeholder="全部意向">
        <el-option label="高意向" value="高意向" /><el-option label="中意向" value="中意向" /><el-option label="低意向" value="低意向" /><el-option label="无法判断" value="无法判断" />
      </el-select>
      <el-button type="primary" @click="load">查询</el-button>
    </div>

    <el-table :data="items" v-loading="loading" class="table-card customer-table" row-key="id" height="calc(100vh - 250px)">
      <el-table-column label="客户" min-width="160">
        <template #default="{ row }"><strong>{{ row.name || "未命名客户" }}</strong><div class="muted">ID {{ row.id }}</div></template>
      </el-table-column>
      <el-table-column label="联系信息" min-width="190">
        <template #default="{ row }">
          <strong>{{ row.phone || "电话未提及" }}</strong>
          <div class="muted">微信：{{ row.wechat_id || row.wechat_nickname || "未提及" }}</div>
        </template>
      </el-table-column>
      <el-table-column label="负责销售" min-width="140">
        <template #default="{ row }">{{ row.owner_name || "未分配" }}<div class="muted">{{ row.owner_username || "" }}</div></template>
      </el-table-column>
      <el-table-column label="意向" min-width="120">
        <template #default="{ row }"><el-tag>{{ row.intent_level || "无法判断" }} · {{ row.intent_score || 0 }}</el-tag></template>
      </el-table-column>
      <el-table-column prop="demand_summary" label="客户需求" min-width="220" show-overflow-tooltip />
      <el-table-column prop="next_action" label="下一步" min-width="240" show-overflow-tooltip />
      <el-table-column prop="created_at" label="入库时间" width="140">
        <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="120" align="center">
        <template #default="{ row }">
          <div class="table-actions">
            <el-button link type="primary" @click="edit(row)">编辑</el-button>
            <el-button link type="danger" @click="remove(row)">删除</el-button>
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
          <el-col :span="12"><el-form-item label="负责销售"><el-select v-model="form.owner_id" clearable><el-option v-for="user in salesUsers" :key="user.id" :label="user.name" :value="user.id" /></el-select></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="意向等级"><el-select v-model="form.intent_level"><el-option label="高意向" value="高意向" /><el-option label="中意向" value="中意向" /><el-option label="低意向" value="低意向" /><el-option label="无法判断" value="无法判断" /></el-select></el-form-item></el-col>
          <el-col :span="24"><el-form-item label="客户需求"><el-input v-model="form.demand_summary" type="textarea" :rows="3" /></el-form-item></el-col>
          <el-col :span="24"><el-form-item label="下一步"><el-input v-model="form.next_action" type="textarea" :rows="3" /></el-form-item></el-col>
        </el-row>
      </el-form>
      <template #footer><el-button @click="dialogVisible = false">取消</el-button><el-button type="primary" @click="save">保存修改</el-button></template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from "vue";
import dayjs from "dayjs";
import { ElMessage, ElMessageBox } from "element-plus";
import http from "../api/http";

const loading = ref(false);
const items = ref([]);
const total = ref(0);
const salesUsers = ref([]);
const dialogVisible = ref(false);
const form = reactive({});
const query = reactive({ keyword: "", owner_id: "", intent_level: "", page: 1, page_size: 20 });

async function loadSales() {
  try { salesUsers.value = await http.get("/api/users?role=sales&status=active&page_size=200"); } catch { salesUsers.value = []; }
}
async function load() {
  loading.value = true;
  try {
    const params = new URLSearchParams();
    Object.entries(query).forEach(([key, value]) => value && params.set(key, value));
    const data = await http.get(`/api/customers?${params}`);
    items.value = data.items || [];
    total.value = data.total || 0;
  } finally { loading.value = false; }
}
function edit(row) {
  Object.assign(form, JSON.parse(JSON.stringify(row)));
  dialogVisible.value = true;
}
async function save() {
  await http.patch(`/api/customers/${form.id}`, form);
  ElMessage.success("客户信息已保存");
  dialogVisible.value = false;
  load();
}
function formatTime(value) {
  return value ? dayjs(value).format("MM-DD HH:mm") : "-";
}
async function remove(row) {
  await ElMessageBox.confirm(`确定删除客户「${row.name || row.id}」吗？`, "删除客户", { type: "warning" });
  await http.delete(`/api/customers/${row.id}`);
  ElMessage.success("已删除");
  load();
}
onMounted(() => { loadSales(); load(); });
</script>
