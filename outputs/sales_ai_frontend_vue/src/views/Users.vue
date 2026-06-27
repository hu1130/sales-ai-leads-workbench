<template>
  <div>
    <div class="toolbar">
      <el-input v-model="keyword" clearable placeholder="搜姓名/账号/电话" @keyup.enter="load" />
      <el-button type="primary" @click="load">查询</el-button>
      <el-button @click="openCreate">新增销售</el-button>
    </div>

    <el-table :data="items" v-loading="loading" class="table-card">
      <el-table-column prop="name" label="姓名" min-width="120" />
      <el-table-column prop="username" label="账号" min-width="140" />
      <el-table-column prop="phone" label="电话" min-width="140" />
      <el-table-column prop="role" label="角色" width="110" />
      <el-table-column label="状态" width="110">
        <template #default="{ row }"><el-tag :type="row.status === 'active' ? 'success' : 'info'">{{ row.status === "active" ? "启用" : "停用" }}</el-tag></template>
      </el-table-column>
      <el-table-column label="操作" fixed="right" width="170">
        <template #default="{ row }">
          <el-button size="small" @click="edit(row)">编辑</el-button>
          <el-button size="small" plain @click="toggle(row)">{{ row.status === "active" ? "停用" : "启用" }}</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="visible" :title="form.id ? '编辑账号' : '新增销售账号'" width="560px">
      <el-form :model="form" label-position="top">
        <el-form-item label="姓名"><el-input v-model="form.name" /></el-form-item>
        <el-form-item label="账号"><el-input v-model="form.username" :disabled="Boolean(form.id)" /></el-form-item>
        <el-form-item label="电话"><el-input v-model="form.phone" /></el-form-item>
        <el-form-item label="角色"><el-select v-model="form.role"><el-option label="销售" value="sales" /><el-option label="管理员" value="admin" /></el-select></el-form-item>
        <el-form-item label="密码"><el-input v-model="form.password" type="password" show-password :placeholder="form.id ? '不修改请留空' : '请输入初始密码'" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="visible = false">取消</el-button><el-button type="primary" @click="save">保存账号</el-button></template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import http from "../api/http";

const loading = ref(false);
const items = ref([]);
const keyword = ref("");
const visible = ref(false);
const form = reactive({ id: null, username: "", password: "", name: "", phone: "", role: "sales" });

async function load() {
  loading.value = true;
  try {
    const params = new URLSearchParams({ page_size: "200" });
    if (keyword.value) params.set("keyword", keyword.value);
    items.value = await http.get(`/api/users?${params}`);
  } finally { loading.value = false; }
}
function openCreate() {
  Object.assign(form, { id: null, username: "", password: "", name: "", phone: "", role: "sales" });
  visible.value = true;
}
function edit(row) {
  Object.assign(form, { ...row, password: "" });
  visible.value = true;
}
async function save() {
  if (form.id) {
    const payload = { name: form.name, phone: form.phone, role: form.role };
    if (form.password) payload.password = form.password;
    await http.patch(`/api/users/${form.id}`, payload);
  } else {
    await http.post("/api/users", form);
  }
  ElMessage.success("账号已保存");
  visible.value = false;
  load();
}
async function toggle(row) {
  await http.patch(`/api/users/${row.id}`, { status: row.status === "active" ? "disabled" : "active" });
  ElMessage.success("状态已更新");
  load();
}
onMounted(load);
</script>
