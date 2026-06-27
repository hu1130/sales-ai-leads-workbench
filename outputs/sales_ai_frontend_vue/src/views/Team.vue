<template>
  <div>
    <div class="metric-grid">
      <article class="metric-card"><span>未分配线索</span><strong>{{ data.unassigned_customers || 0 }}</strong><p>管理员待处理</p></article>
      <article class="metric-card blue"><span>今日新增客户</span><strong>{{ totals.customers }}</strong><p>按销售归属统计</p></article>
      <article class="metric-card amber"><span>今日跟进</span><strong>{{ totals.followups }}</strong><p>通话/资料/手动记录</p></article>
      <article class="metric-card red"><span>高意向客户</span><strong>{{ totals.high }}</strong><p>团队当前重点</p></article>
    </div>

    <section class="panel">
      <div class="panel-head">
        <h3 class="panel-title">销售今日情况</h3>
        <el-button type="primary" @click="load">刷新</el-button>
      </div>
      <el-table :data="data.items || []" v-loading="loading" class="table-card">
        <el-table-column label="销售" min-width="150">
          <template #default="{ row }"><strong>{{ row.name }}</strong><div class="muted">{{ row.username }}</div></template>
        </el-table-column>
        <el-table-column prop="today_customers" label="今日客户" />
        <el-table-column prop="today_followups" label="今日跟进" />
        <el-table-column prop="today_uploads" label="今日资料" />
        <el-table-column prop="high_intent_customers" label="高意向" />
        <el-table-column prop="pending_followup_customers" label="待跟进" />
        <el-table-column prop="total_customers" label="总客户" />
      </el-table>
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import http from "../api/http";

const loading = ref(false);
const data = ref({ items: [] });
const totals = computed(() => (data.value.items || []).reduce((acc, item) => {
  acc.customers += item.today_customers || 0;
  acc.followups += item.today_followups || 0;
  acc.high += item.high_intent_customers || 0;
  return acc;
}, { customers: 0, followups: 0, high: 0 }));

async function load() {
  loading.value = true;
  try { data.value = await http.get("/api/dashboard/team-today"); } finally { loading.value = false; }
}
onMounted(load);
</script>
