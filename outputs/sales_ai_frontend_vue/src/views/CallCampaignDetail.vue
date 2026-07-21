<template>
  <div>
    <div class="toolbar">
      <el-button @click="$router.back()">返回</el-button>
      <el-button type="success" :loading="robotStarting" @click="startAiRobot">启动 AI 机器人外呼</el-button>
      <el-button type="primary" @click="load">刷新</el-button>
    </div>

    <section class="panel" v-if="campaign">
      <div class="panel-head">
        <div>
          <span class="section-kicker">外呼任务</span>
          <h3 class="panel-title">{{ campaign.name }}</h3>
        </div>
        <el-tag>{{ campaignStatusText(campaign.status) }}</el-tag>
      </div>
      <div class="metric-grid">
        <article class="metric-card"><span>客户数</span><strong>{{ campaign.total_count }}</strong></article>
        <article class="metric-card blue"><span>已拨打</span><strong>{{ campaign.called_count }}</strong></article>
        <article class="metric-card amber"><span>接通</span><strong>{{ campaign.connected_count }}</strong></article>
        <article class="metric-card red"><span>高意向</span><strong>{{ campaign.high_intent_count }}</strong></article>
      </div>
      <el-alert
        class="robot-alert"
        type="success"
        :closable="false"
        show-icon
        title="AI 机器人会先批量外呼并生成通话记录，高意向客户会进入销售一键回拨队列。"
      />
    </section>

    <el-table :data="targets" v-loading="loading" class="table-card">
      <template #empty>
        <div class="table-empty">
          <strong>这个任务还没有客户</strong>
          <span>外呼任务需要先选择客户，之后才能启动 AI 机器人外呼并生成通话记录。</span>
          <el-button @click="$router.push('/call-center/campaigns')">返回任务列表</el-button>
        </div>
      </template>
      <el-table-column label="客户" min-width="210">
        <template #default="{ row }">
          <strong>{{ row.customer_name || row.contact_name || '未命名客户' }}</strong>
          <div class="muted ellipsis">{{ row.customer_demand_summary || '-' }}</div>
        </template>
      </el-table-column>
      <el-table-column label="电话" width="130">
        <template #default="{ row }"><strong v-if="row.phone">{{ row.phone }}</strong><span v-else>-</span></template>
      </el-table-column>
      <el-table-column prop="assigned_user_name" label="销售" width="105" />
      <el-table-column label="意向" width="130">
        <template #default="{ row }">
          <el-tag :type="isHighIntent(row) ? 'danger' : 'info'">{{ row.customer_intent_level || '-' }} {{ row.customer_intent_score || 0 }}</el-tag>
          <div v-if="isHighIntent(row)" class="robot-hint">AI高意向，建议一键回拨</div>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="100">
        <template #default="{ row }"><el-tag>{{ callStatusText(row.status) }}</el-tag></template>
      </el-table-column>
      <el-table-column label="操作" width="230" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" :loading="callbackLoadingTargetId === row.id" @click="dial(row)">一键回拨</el-button>
          <el-button link type="success" @click="openFinish(row)">填结果</el-button>
          <el-button link type="warning" @click="openTranscript(row)">AI分析</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="finishVisible" title="填写通话结果" width="520px">
      <el-form :model="finishForm" label-position="top">
        <el-form-item label="通话状态">
          <el-select v-model="finishForm.call_status">
            <el-option label="已接通" value="connected" />
            <el-option label="未接通" value="no_answer" />
            <el-option label="忙线" value="busy" />
            <el-option label="拒接" value="rejected" />
            <el-option label="空号" value="empty_number" />
            <el-option label="需回拨" value="callback" />
          </el-select>
        </el-form-item>
        <el-form-item label="通话时长（秒）"><el-input-number v-model="finishForm.duration_seconds" :min="0" /></el-form-item>
        <el-form-item label="备注"><el-input v-model="finishForm.remark" type="textarea" :rows="3" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="finishVisible=false">取消</el-button>
        <el-button type="primary" @click="finishAttempt">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="transcriptVisible" title="粘贴通话文本并分析" width="720px">
      <el-input v-model="transcript" type="textarea" :rows="10" placeholder="把通话转写文本粘贴到这里，系统会立即做意向分析并回写客户。" />
      <template #footer>
        <el-button @click="transcriptVisible=false">取消</el-button>
        <el-button type="primary" @click="submitTranscript">开始 AI 分析</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from "vue";
import { useRoute } from "vue-router";
import { ElMessage } from "element-plus";
import http from "../api/http";

const route = useRoute();
const loading = ref(false);
const campaign = ref(null);
const targets = ref([]);
const activeAttempt = ref(null);
const activeTarget = ref(null);
const finishVisible = ref(false);
const transcriptVisible = ref(false);
const transcript = ref("");
const callbackLoadingTargetId = ref(null);
const robotStarting = ref(false);
const finishForm = reactive({ call_status: "connected", duration_seconds: 0, remark: "" });

async function load() {
  loading.value = true;
  try {
    campaign.value = await http.get(`/api/call-campaigns/${route.params.id}`);
    const data = await http.get(`/api/call-campaigns/${route.params.id}/targets?page_size=200`);
    targets.value = data.items || [];
  } finally {
    loading.value = false;
  }
}

async function ensureAttempt(row) {
  if (activeAttempt.value && activeTarget.value?.id === row.id) return activeAttempt.value;
  activeTarget.value = row;
  activeAttempt.value = await http.post("/api/call-attempts", { target_id: row.id, call_mode: "manual" });
  return activeAttempt.value;
}

async function dial(row) {
  const phone = dialPhone(row.phone);
  if (!phone) return ElMessage.warning("这个客户没有可回拨电话");
  callbackLoadingTargetId.value = row.id;
  try {
    const callback = await http.post(`/api/customers/${row.customer_id}/callback`, {
      customer_phone: phone,
      remark: `外呼任务 ${campaign.value?.name || ""} 一键回拨`
    });
    ElMessage.success(`已发起服务商回拨，通话ID：${callback.provider_call_id}`);
    await load();
  } finally {
    callbackLoadingTargetId.value = null;
  }
}

async function startAiRobot() {
  robotStarting.value = true;
  try {
    const result = await http.post(`/api/call-campaigns/${route.params.id}/ai-robot/start`, {
      max_calls: 50,
      only_pending: true
    });
    ElMessage.success(`AI机器人外呼已启动：${result.launched || 0} 个客户，跳过 ${result.skipped || 0} 个`);
    await load();
  } finally {
    robotStarting.value = false;
  }
}

async function openFinish(row) {
  await ensureAttempt(row);
  finishVisible.value = true;
}

async function finishAttempt() {
  await http.post(`/api/call-attempts/${activeAttempt.value.id}/finish`, finishForm);
  ElMessage.success("通话结果已保存");
  finishVisible.value = false;
  load();
}

async function openTranscript(row) {
  await ensureAttempt(row);
  transcript.value = "";
  transcriptVisible.value = true;
}

async function submitTranscript() {
  if (!transcript.value.trim()) return ElMessage.warning("请先粘贴通话文本");
  await http.post(`/api/call-attempts/${activeAttempt.value.id}/submit-transcript`, { transcript: transcript.value });
  ElMessage.success("AI 分析已完成，客户意向已回写");
  transcriptVisible.value = false;
  load();
}

onMounted(load);

function dialPhone(phone) {
  return String(phone || "").replace(/[^\d+*#]/g, "");
}

function isHighIntent(row) {
  return Number(row.customer_intent_score || 0) >= 80 || String(row.customer_intent_level || "").includes("高");
}

function campaignStatusText(status) {
  return ({ draft: "草稿", running: "进行中", paused: "已暂停", completed: "已完成", cancelled: "已取消" })[status] || status || "-";
}

function callStatusText(status) {
  return ({
    pending: "待拨打",
    calling: "拨打中",
    connected: "已接通",
    no_answer: "未接通",
    busy: "忙线",
    rejected: "拒接",
    empty_number: "空号",
    callback: "需回拨",
    completed: "已完成",
    failed: "失败"
  })[status] || status || "-";
}
</script>

<style scoped>
.robot-alert {
  margin-top: 14px;
}

.robot-hint {
  margin-top: 6px;
  color: #d93050;
  font-size: 12px;
  font-weight: 800;
  line-height: 1.3;
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
</style>
