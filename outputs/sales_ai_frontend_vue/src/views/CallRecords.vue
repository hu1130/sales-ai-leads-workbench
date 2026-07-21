<template>
  <div>
    <div class="toolbar">
      <el-segmented v-model="activeTab" :options="tabOptions" @change="handleTabChange" />

      <template v-if="activeTab === 'attempts'">
        <el-select v-model="query.call_status" clearable placeholder="全部状态" @change="load">
          <el-option label="拨打中" value="dialing" />
          <el-option label="已接通" value="connected" />
          <el-option label="未接通" value="no_answer" />
          <el-option label="拒接" value="rejected" />
          <el-option label="需回拨" value="callback" />
        </el-select>
        <el-select v-model="query.call_mode" clearable placeholder="全部类型" @change="load">
          <el-option label="旧版拨号" value="tel" />
          <el-option label="销售手动外呼" value="manual" />
          <el-option label="服务商双向回呼" value="provider_callback" />
          <el-option label="AI机器人外呼" value="ai_robot" />
        </el-select>
      </template>

      <template v-else>
        <el-select v-model="query.robot_status" clearable placeholder="全部机器人状态" @change="load">
          <el-option label="已提交" value="initiated" />
          <el-option label="拨打中" value="dialing" />
          <el-option label="已接通" value="answered" />
          <el-option label="已完成" value="completed" />
          <el-option label="未接通" value="no_answer" />
          <el-option label="失败" value="failed" />
        </el-select>
        <el-button :loading="syncPendingLoading" @click="syncPendingRobotCalls">同步未完成</el-button>
      </template>

      <el-button type="primary" @click="load">查询</el-button>
    </div>

    <el-table
      v-if="activeTab === 'attempts'"
      :data="visibleAttempts"
      v-loading="loading"
      class="table-card"
      :empty-text="attemptsEmptyText"
    >
      <el-table-column prop="customer_name" label="客户" min-width="150" />
      <el-table-column prop="phone" label="电话" width="140" />
      <el-table-column label="类型" width="140">
        <template #default="{ row }">
          <el-tag :type="row.call_mode === 'ai_robot' ? 'success' : row.call_mode === 'provider_callback' ? 'warning' : 'info'">
            {{ callModeText(row.call_mode) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="campaign_name" label="任务" min-width="160" />
      <el-table-column prop="sales_name" label="销售" width="110" />
      <el-table-column label="状态" width="110">
        <template #default="{ row }"><el-tag>{{ callStatusText(row.call_status) }}</el-tag></template>
      </el-table-column>
      <el-table-column label="AI 意向" width="140">
        <template #default="{ row }"><el-tag>{{ row.intent_level || '-' }} {{ row.intent_score || 0 }}</el-tag></template>
      </el-table-column>
      <el-table-column label="通话时长" width="110">
        <template #default="{ row }">{{ formatDuration(row.duration_seconds) }}</template>
      </el-table-column>
      <el-table-column prop="next_action" label="下一步" min-width="240" show-overflow-tooltip />
    </el-table>

    <el-table v-else :data="items" v-loading="loading" class="table-card" :empty-text="robotCallsEmptyText">
      <el-table-column prop="customer_name" label="客户" min-width="150" />
      <el-table-column prop="phone" label="电话" width="140" />
      <el-table-column prop="campaign_name" label="外呼任务" min-width="160" />
      <el-table-column label="机器人状态" width="120">
        <template #default="{ row }"><el-tag>{{ robotStatusText(row.status) }}</el-tag></template>
      </el-table-column>
      <el-table-column label="AI 意向" width="140">
        <template #default="{ row }">
          <el-tag :type="row.high_intent ? 'danger' : 'info'">{{ row.intent_level || '-' }} {{ row.intent_score || 0 }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="高意向" width="120">
        <template #default="{ row }">
          <el-tag v-if="row.high_intent" type="danger">建议回拨</el-tag>
          <span v-else>-</span>
        </template>
      </el-table-column>
      <el-table-column label="通话时长" width="110">
        <template #default="{ row }">{{ formatDuration(row.duration_seconds) }}</template>
      </el-table-column>
      <el-table-column prop="transcript" label="转写摘要" min-width="260" show-overflow-tooltip />
      <el-table-column label="开始时间" width="150">
        <template #default="{ row }">{{ formatTime(row.started_at || row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="250" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="openRobotDetail(row)">录音/分析</el-button>
          <el-button link type="primary" :loading="syncLoadingId === row.id" @click="syncRobotCall(row)">同步</el-button>
          <el-button
            v-if="row.high_intent && row.customer_id"
            link
            type="primary"
            :loading="callbackLoadingId === row.id"
            @click="callbackRobotLead(row)"
          >
            一键回拨
          </el-button>
          <span v-else class="muted">-</span>
        </template>
      </el-table-column>
    </el-table>

    <el-pagination
      v-model:current-page="query.page"
      v-model:page-size="query.page_size"
      :total="total"
      layout="total, prev, pager, next, sizes"
      @change="load"
    />

    <el-drawer v-model="robotDetailVisible" title="AI机器人通话详情" size="680px" destroy-on-close>
      <section v-if="activeRobotCall" class="robot-detail">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="客户">{{ activeRobotCall.customer_name || "-" }}</el-descriptions-item>
          <el-descriptions-item label="电话">{{ activeRobotCall.phone || "-" }}</el-descriptions-item>
          <el-descriptions-item label="外呼任务">{{ activeRobotCall.campaign_name || "-" }}</el-descriptions-item>
          <el-descriptions-item label="机器人状态">{{ robotStatusText(activeRobotCall.status) }}</el-descriptions-item>
          <el-descriptions-item label="AI意向">
            <el-tag :type="activeRobotCall.high_intent ? 'danger' : 'info'">
              {{ activeRobotCall.intent_level || "-" }} {{ activeRobotCall.intent_score || 0 }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="通话时长">{{ formatDuration(activeRobotCall.duration_seconds) }}</el-descriptions-item>
        </el-descriptions>

        <section class="detail-block analysis-block">
          <div class="detail-block-head">
            <div>
              <span class="section-kicker">智能分析</span>
              <h3>AI分析结果</h3>
            </div>
            <el-tag :type="activeRobotCall.high_intent ? 'danger' : 'info'">{{ activeRobotCall.high_intent ? "建议销售回拨" : "继续观察" }}</el-tag>
          </div>
          <div class="analysis-grid">
            <article v-for="item in robotAnalysisItems(activeRobotCall)" :key="item.label">
              <span>{{ item.label }}</span>
              <strong>{{ item.value }}</strong>
            </article>
          </div>
          <p class="analysis-summary">{{ robotAnalysisSummary(activeRobotCall) }}</p>
        </section>

        <section class="detail-block">
          <div class="detail-block-head">
            <div>
              <span class="section-kicker">通话录音</span>
              <h3>录音</h3>
            </div>
            <el-tag type="success" v-if="robotRecordingUrl(activeRobotCall)">已回传</el-tag>
            <el-tag type="info" v-else>等待回传</el-tag>
          </div>
          <audio v-if="robotRecordingUrl(activeRobotCall)" :src="robotRecordingUrl(activeRobotCall)" controls />
          <p v-else class="muted detail-empty">暂无录音地址。服务商回传录音后会在这里播放，并关联到客户跟进记录。</p>
        </section>

        <section class="detail-block">
          <div class="detail-block-head">
            <div>
              <span class="section-kicker">对话转写</span>
              <h3>对话内容</h3>
            </div>
            <el-tag>{{ robotTranscript(activeRobotCall).length }} 字</el-tag>
          </div>
          <pre>{{ robotTranscript(activeRobotCall) || "暂无转写内容。机器人通话完成后，这里展示客户与AI机器人的完整对话。" }}</pre>
        </section>

        <div class="drawer-actions">
          <el-button
            v-if="activeRobotCall"
            :loading="syncLoadingId === activeRobotCall.id"
            @click="syncRobotCall(activeRobotCall)"
          >
            同步结果
          </el-button>
          <el-button
            v-if="activeRobotCall.high_intent && activeRobotCall.customer_id"
            type="primary"
            :loading="callbackLoadingId === activeRobotCall.id"
            @click="callbackRobotLead(activeRobotCall)"
          >
            一键回拨
          </el-button>
        </div>
      </section>
    </el-drawer>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from "vue";
import dayjs from "dayjs";
import { ElMessage } from "element-plus";
import http from "../api/http";
import { useAuthStore } from "../stores/auth";

const loading = ref(false);
const items = ref([]);
const total = ref(0);
const activeTab = ref("attempts");
const callbackLoadingId = ref(null);
const syncLoadingId = ref(null);
const syncPendingLoading = ref(false);
const robotDetailVisible = ref(false);
const activeRobotCall = ref(null);
const auth = useAuthStore();
const tabOptions = [
  { label: "通话记录", value: "attempts" },
  { label: "AI机器人外呼", value: "robots" }
];
const attemptsEmptyText = "还没有通话记录。先在客户池发起一键回拨，或在外呼任务里启动 AI 机器人外呼。";
const robotCallsEmptyText = "还没有 AI 机器人通话。先进入外呼任务，选择客户后启动 AI 机器人外呼。";
const query = reactive({ call_status: "", call_mode: "", robot_status: "", page: 1, page_size: 20 });

const visibleAttempts = computed(() => {
  if (activeTab.value !== "attempts" || !query.call_mode) return items.value;
  return items.value.filter((item) => item.call_mode === query.call_mode);
});

async function load() {
  loading.value = true;
  try {
    if (activeTab.value === "robots") {
      const params = new URLSearchParams({ page: query.page, page_size: query.page_size });
      if (query.robot_status) params.set("status", query.robot_status);
      const data = await http.get(`/api/ai-robot-calls?${params}`);
      items.value = data.items || [];
      total.value = data.total || 0;
      return;
    }

    const params = new URLSearchParams({ page: query.page, page_size: query.page_size });
    if (query.call_status) params.set("call_status", query.call_status);
    const data = await http.get(`/api/call-attempts?${params}`);
    items.value = data.items || [];
    total.value = data.total || 0;
  } finally {
    loading.value = false;
  }
}

function handleTabChange() {
  query.page = 1;
  load();
}

async function callbackRobotLead(row) {
  if (!auth.isAdmin && !hasCurrentSalesPhone()) return showCurrentSalesPhoneHint();
  callbackLoadingId.value = row.id;
  try {
    const callback = await http.post(`/api/customers/${row.customer_id}/callback`, {
      customer_phone: row.phone,
      remark: "AI机器人判定高意向后销售一键回拨"
    });
    ElMessage.success(`已发起服务商回拨，通话ID：${callback.provider_call_id}`);
    await load();
  } finally {
    callbackLoadingId.value = null;
  }
}

async function syncRobotCall(row) {
  if (!row?.id) return;
  syncLoadingId.value = row.id;
  try {
    const updated = await http.post(`/api/ai-robot-calls/${row.id}/sync`);
    replaceRobotCall(updated);
    ElMessage.success("已同步阿里云通话结果");
  } catch (error) {
    ElMessage.error(error.message || "同步失败");
  } finally {
    syncLoadingId.value = null;
  }
}

async function syncPendingRobotCalls() {
  syncPendingLoading.value = true;
  try {
    const data = await http.post("/api/ai-robot-calls/sync-pending?limit=20");
    ElMessage.success(`已同步 ${data.synced || 0} 条，失败 ${data.failed || 0} 条`);
    await load();
  } catch (error) {
    ElMessage.error(error.message || "同步失败");
  } finally {
    syncPendingLoading.value = false;
  }
}

function replaceRobotCall(updated) {
  const index = items.value.findIndex((item) => item.id === updated.id);
  if (index >= 0) {
    items.value.splice(index, 1, updated);
  }
  if (activeRobotCall.value?.id === updated.id) {
    activeRobotCall.value = updated;
  }
}

function dialPhone(phone) {
  return String(phone || "").replace(/[^\d+*#]/g, "");
}

function hasCurrentSalesPhone() {
  return Boolean(dialPhone(auth.user?.phone));
}

function showCurrentSalesPhoneHint() {
  ElMessage.warning("当前销售账号没有手机号，请让管理员先在销售账号里补手机号");
}

onMounted(load);

function openRobotDetail(row) {
  activeRobotCall.value = row;
  robotDetailVisible.value = true;
}

function callModeText(mode) {
  return ({
    "tel": "旧版拨号",
    manual: "销售手动外呼",
    callback: "销售回拨",
    provider_callback: "服务商回呼",
    ai_robot: "AI机器人外呼"
  })[mode] || mode || "-";
}

function callStatusText(status) {
  return ({
    initiated: "已发起",
    dialing: "拨打中",
    ringing: "拨打中",
    connected: "已接通",
    answered: "已接通",
    no_answer: "未接通",
    busy: "忙线",
    rejected: "拒接",
    empty_number: "空号",
    failed: "失败",
    callback: "需回拨"
  })[status] || status || "-";
}

function robotStatusText(status) {
  return ({
    initiated: "已提交",
    dialing: "拨打中",
    answered: "已接通",
    completed: "已完成",
    no_answer: "未接通",
    busy: "忙线",
    rejected: "拒接",
    empty_number: "空号",
    failed: "失败"
  })[status] || status || "-";
}

function formatDuration(value) {
  if (!value) return "-";
  return `${value} 秒`;
}

function formatTime(value) {
  return value ? dayjs(value).format("MM-DD HH:mm") : "-";
}

function robotRecordingUrl(row) {
  return row?.recording_url || row?.audio_url || row?.recording_file_url || row?.call_recording_url || "";
}

function robotTranscript(row) {
  return row?.transcript || row?.conversation_text || row?.dialogue_text || row?.raw_text || "";
}

function robotAnalysisSummary(row) {
  if (row?.analysis_summary || row?.summary || row?.ai_summary || row?.next_action) {
    return row.analysis_summary || row.summary || row.ai_summary || row.next_action;
  }
  if (row?.high_intent) {
    return "AI 机器人已判定为高意向客户，建议销售尽快一键回拨，并补充报价、合同或部署周期等推进材料。";
  }
  if (row?.status === "completed") {
    return "通话已完成，建议销售结合转写内容继续培育，并在客户有明确预算、时间或付款信号时升级跟进。";
  }
  return "等待服务商回传完整录音和转写后，系统会继续沉淀意向判断、客户诉求和下一步建议。";
}

function robotAnalysisItems(row) {
  const transcript = robotTranscript(row);
  const hasTranscript = Boolean(transcript);
  const recording = robotRecordingUrl(row);
  return [
    { label: "客户诉求", value: row?.customer_needs || row?.demand_summary || row?.summary || (hasTranscript ? "关注报价、合同、付款和部署推进" : "等待转写回传") },
    { label: "判断依据", value: row?.intent_reason || row?.evidence || (row?.intent_score ? `${row.intent_level || "AI意向"} ${row.intent_score} 分，基于通话转写判断` : "等待完整通话后分析") },
    { label: "下一步", value: row?.next_action || (row?.high_intent ? "销售尽快一键回拨，发送报价和合同材料" : "继续观察或补充资料") },
    { label: "关联录音", value: row?.call_recording_id ? `录音 ID ${row.call_recording_id}` : (recording ? "录音已回传" : "等待录音回传") }
  ];
}
</script>

<style scoped>
.robot-detail {
  display: grid;
  gap: 14px;
}

.detail-block {
  padding: 14px;
  border: 1px solid #d9e2ef;
  border-radius: 16px;
  background: #fff;
}

.analysis-block {
  border-color: #b8d5ff;
  background: linear-gradient(180deg, #f8fbff 0%, #ffffff 100%);
}

.detail-block-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.detail-block-head h3 {
  margin: 0;
  font-size: 18px;
}

.detail-block audio {
  width: 100%;
}

.detail-block pre {
  min-height: 140px;
  max-height: 320px;
  margin: 0;
  padding: 14px;
  overflow: auto;
  border-radius: 14px;
  color: #d7e7ff;
  background: #0b1630;
  font-family: inherit;
  line-height: 1.8;
  white-space: pre-wrap;
  word-break: break-word;
}

.detail-empty {
  margin: 0;
  line-height: 1.7;
}

.analysis-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.analysis-grid article {
  padding: 12px;
  border: 1px solid #e4ebf5;
  border-radius: 12px;
  background: #f8fafc;
}

.analysis-grid span {
  display: block;
  color: #667085;
  font-size: 12px;
  font-weight: 900;
}

.analysis-grid strong {
  display: block;
  margin-top: 6px;
  line-height: 1.6;
}

.analysis-summary {
  margin: 12px 0 0;
  padding: 12px;
  border-radius: 12px;
  color: #0f3f91;
  background: #eff6ff;
  line-height: 1.7;
}

.drawer-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}

@media (max-width: 760px) {
  .analysis-grid {
    grid-template-columns: 1fr;
  }
}
</style>
