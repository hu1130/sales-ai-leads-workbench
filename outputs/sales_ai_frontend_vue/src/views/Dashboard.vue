<template>
  <div>
    <section class="hero">
      <div class="hero-copy">
        <span class="hero-label">Lead radar</span>
        <h2>把今天最该跟的客户排到销售面前</h2>
        <p>截图、录音和外部表单进入分析队列后，系统自动提取客户信息、意向等级和下一步动作。销售只看自己该跟的，主管看团队全局。</p>
        <div class="hero-actions">
          <el-button type="primary" @click="$router.push('/uploads')">上传客户资料</el-button>
          <el-button @click="$router.push('/customers')">查看客户池</el-button>
        </div>
      </div>
      <div class="radar-card" aria-hidden="true">
        <div class="radar-ring ring-1"></div>
        <div class="radar-ring ring-2"></div>
        <div class="radar-sweep"></div>
        <span class="dot high"></span>
        <span class="dot mid"></span>
        <span class="dot low"></span>
      </div>
    </section>

    <div class="metric-grid">
      <article class="metric-card red"><span>高意向</span><strong>{{ stats.high_intent_customers || 0 }}</strong><p>今天优先拨号</p></article>
      <article class="metric-card amber"><span>总客户</span><strong>{{ stats.total_customers || 0 }}</strong><p>客户池累计</p></article>
      <article class="metric-card blue"><span>资料记录</span><strong>{{ stats.total_uploads || 0 }}</strong><p>截图与录音</p></article>
      <article class="metric-card"><span>未分配</span><strong>{{ stats.unassigned_customers || 0 }}</strong><p>管理员待分配</p></article>
    </div>

    <div class="two-col">
      <section class="panel">
        <div class="panel-head">
          <div>
            <span class="section-kicker">Action queue</span>
            <h3 class="panel-title">优先跟进客户</h3>
          </div>
          <el-button text type="primary" @click="$router.push('/customers')">全部客户</el-button>
        </div>
        <el-table :data="priorities" v-loading="loading" class="table-card">
          <el-table-column prop="name" label="客户" min-width="130">
            <template #default="{ row }">
              <strong>{{ row.name || "未命名客户" }}</strong>
              <div class="muted">ID {{ row.id }}</div>
            </template>
          </el-table-column>
          <el-table-column prop="intent_level" label="意向" width="130">
            <template #default="{ row }"><el-tag>{{ row.intent_level || "无法判断" }} · {{ row.intent_score || 0 }}</el-tag></template>
          </el-table-column>
          <el-table-column prop="next_action" label="下一步" min-width="220" show-overflow-tooltip />
        </el-table>
      </section>

      <section class="panel">
        <div class="panel-head">
          <div>
            <span class="section-kicker">AI pipeline</span>
            <h3 class="panel-title">资料分析进度</h3>
          </div>
          <el-button text type="primary" @click="$router.push('/uploads')">全部资料</el-button>
        </div>
        <el-table :data="uploads" v-loading="loading" class="table-card">
          <el-table-column prop="file_name" label="资料" min-width="210" show-overflow-tooltip />
          <el-table-column prop="file_type" label="类型" width="90" />
          <el-table-column prop="status" label="状态" width="100">
            <template #default="{ row }"><el-tag :type="row.status === 'completed' ? 'success' : 'warning'">{{ statusText(row.status) }}</el-tag></template>
          </el-table-column>
        </el-table>
      </section>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from "vue";
import http from "../api/http";

const loading = ref(false);
const stats = ref({});
const priorities = ref([]);
const uploads = ref([]);

function statusText(status) {
  return ({ pending: "排队中", processing: "分析中", completed: "已完成", failed: "失败" })[status] || status;
}

async function load() {
  loading.value = true;
  try {
    const [statData, priorityData, uploadData] = await Promise.all([
      http.get("/api/dashboard/stats"),
      http.get("/api/dashboard/followup-priorities?limit=8"),
      http.get("/api/uploads?page_size=6")
    ]);
    stats.value = statData;
    priorities.value = priorityData.items || priorityData || [];
    uploads.value = uploadData.items || [];
  } finally {
    loading.value = false;
  }
}

onMounted(load);
</script>
