<template>
  <div>
    <div class="toolbar">
      <el-input v-model="keyword" clearable placeholder="搜标题/内容" @keyup.enter="load" />
      <el-select v-model="category" clearable placeholder="全部分类">
        <el-option label="通用" value="general" />
        <el-option label="高意向" value="high_intent" />
        <el-option label="报价" value="quotation" />
        <el-option label="异议处理" value="objection" />
      </el-select>
      <el-button type="primary" @click="load">查询</el-button>
      <el-button @click="openCreate">新增话术</el-button>
    </div>

    <el-row v-loading="loading" :gutter="16">
      <el-col v-for="item in items" :key="item.id" :xs="24" :md="12" :lg="8">
        <el-card class="script-card">
          <template #header>
            <div class="script-head">
              <strong>{{ item.title || "未命名话术" }}</strong>
              <el-tag>{{ categoryText(item.category) }}</el-tag>
            </div>
          </template>
          <p>{{ item.content || "暂无内容" }}</p>
          <el-button type="danger" plain size="small" @click="remove(item)">删除</el-button>
        </el-card>
      </el-col>
    </el-row>

    <el-empty v-if="!items.length && !loading" description="暂无话术" />

    <el-dialog v-model="visible" title="新增销售话术" width="620px">
      <el-form :model="form" label-position="top">
        <el-form-item label="标题"><el-input v-model="form.title" /></el-form-item>
        <el-form-item label="分类">
          <el-select v-model="form.category">
            <el-option label="通用" value="general" />
            <el-option label="高意向" value="high_intent" />
            <el-option label="报价" value="quotation" />
            <el-option label="异议处理" value="objection" />
          </el-select>
        </el-form-item>
        <el-form-item label="内容"><el-input v-model="form.content" type="textarea" :rows="6" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="visible = false">取消</el-button>
        <el-button type="primary" @click="save">保存话术</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import http from "../api/http";

const loading = ref(false);
const items = ref([]);
const keyword = ref("");
const category = ref("");
const visible = ref(false);
const form = reactive({ title: "", category: "general", content: "" });

function categoryText(value) {
  return ({
    general: "通用",
    high_intent: "高意向",
    quotation: "报价",
    objection: "异议处理"
  })[value] || value || "通用";
}

async function load() {
  loading.value = true;
  try {
    const params = new URLSearchParams();
    if (keyword.value) params.set("keyword", keyword.value);
    if (category.value) params.set("category", category.value);
    const data = await http.get(`/api/scripts?${params}`);
    items.value = Array.isArray(data) ? data : (data.items || []);
  } finally {
    loading.value = false;
  }
}

function openCreate() {
  Object.assign(form, { title: "", category: "general", content: "" });
  visible.value = true;
}

async function save() {
  await http.post("/api/scripts", form);
  ElMessage.success("话术已保存");
  visible.value = false;
  load();
}

async function remove(item) {
  await ElMessageBox.confirm(`确定删除「${item.title || item.id}」吗？`, "删除话术", { type: "warning" });
  await http.delete(`/api/scripts/${item.id}`);
  ElMessage.success("已删除");
  load();
}

onMounted(load);
</script>

<style scoped>
.script-card { margin-bottom: 16px; border-radius: 20px; }
.script-head { display: flex; justify-content: space-between; gap: 12px; align-items: center; }
.script-card p { min-height: 92px; color: #334155; white-space: pre-wrap; }
</style>
