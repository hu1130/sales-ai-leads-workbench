<template>
  <div class="uploads-page">
    <section class="material-hero">
      <div>
        <span class="section-kicker">资料工作台</span>
        <h2>资料处理</h2>
        <p>微信截图、通话录音和客户资料都会进入这里。先搜客户，再看意向、原文件和下一步动作。</p>
      </div>
      <el-upload :auto-upload="false" :show-file-list="false" :on-change="pickFile">
        <el-button type="primary" size="large">上传资料</el-button>
      </el-upload>
    </section>

    <section class="search-panel">
      <el-input
        v-model="query.keyword"
        class="main-search"
        clearable
        size="large"
        placeholder="搜客户名、电话、微信号、文件名、需求关键词"
        @keyup.enter="load"
      />
      <el-select v-model="query.file_type" clearable size="large" placeholder="资料类型">
        <el-option label="图片" value="image" />
        <el-option label="录音" value="audio" />
        <el-option label="文档" value="document" />
      </el-select>
      <el-select v-model="query.status" clearable size="large" placeholder="分析状态">
        <el-option label="排队中" value="pending" />
        <el-option label="分析中" value="processing" />
        <el-option label="已完成" value="completed" />
        <el-option label="失败" value="failed" />
      </el-select>
      <el-button type="primary" size="large" @click="load">查询</el-button>
    </section>

    <section v-if="latestItem" class="latest-material">
      <div class="latest-copy">
        <span class="section-kicker">最新资料</span>
        <h3>最新进入资料</h3>
        <p>
          <strong>{{ latestItem.file_name }}</strong>
          <span>ID {{ latestItem.id }} · 客户 ID {{ latestItem.customer_id || "未关联" }} · {{ formatTime(latestItem.created_at) }}</span>
        </p>
      </div>
      <div class="latest-actions">
        <el-tag :type="fileTagType(latestItem.file_type)">{{ fileTypeText(latestItem.file_type) }}</el-tag>
        <el-tag :type="latestItem.status === 'completed' ? 'success' : 'warning'">{{ statusText(latestItem.status) }}</el-tag>
        <el-button type="primary" @click="detail(latestItem)">查看最新</el-button>
        <el-button @click="preview(latestItem)">预览原文件</el-button>
      </div>
    </section>

    <section v-if="selectedFile" class="upload-strip">
      <div>
        <strong>{{ selectedFile.name }}</strong>
        <span>可补充客户信息后上传，也可以直接上传让 AI 自动识别。</span>
      </div>
      <el-input v-model="uploadForm.customer_name" placeholder="客户姓名，可空" />
      <el-input v-model="uploadForm.customer_phone" placeholder="客户电话，可空" />
      <el-select v-if="isAdmin" v-model="uploadForm.sales_id" clearable placeholder="指定销售">
        <el-option v-for="user in salesUsers" :key="user.id" :label="user.name" :value="user.id" />
      </el-select>
      <el-button :loading="uploading" type="primary" @click="upload">开始分析</el-button>
    </section>

    <div class="quick-tabs">
      <button
        v-for="tab in quickTabs"
        :key="tab.value"
        :class="{ active: activeStage === tab.value }"
        type="button"
        @click="setStage(tab.value)"
      >
        {{ tab.label }}
      </button>
    </div>

    <el-table :data="items" v-loading="loading && items.length === 0" class="table-card material-table" height="calc(100vh - 390px)" :empty-text="loadError || '暂无资料数据'">
      <el-table-column label="客户资料" min-width="300">
        <template #default="{ row }">
          <div class="material-title">
            <strong>{{ displayCustomer(row) }}</strong>
            <el-tag size="small" :type="fileTagType(row.file_type)">{{ fileTypeText(row.file_type) }}</el-tag>
          </div>
          <div class="muted ellipsis">{{ row.file_name }}</div>
        </template>
      </el-table-column>

      <el-table-column label="AI 判断" min-width="170">
        <template #default="{ row }">
          <el-tag :type="intentTagType(row.analysis?.intent_level)">
            {{ intentText(row.analysis?.intent_level) }} · {{ row.analysis?.intent_score ?? 0 }}
          </el-tag>
          <div class="muted">{{ statusText(row.status) }}</div>
        </template>
      </el-table-column>

      <el-table-column label="关键信息" min-width="280">
        <template #default="{ row }">
          <strong>{{ keyInfoText(row) }}</strong>
          <div class="muted ellipsis">{{ nextActionText(row) }}</div>
        </template>
      </el-table-column>

      <el-table-column label="上传销售" min-width="140">
        <template #default="{ row }">
          {{ row.uploader_name || "未知" }}
          <div class="muted">{{ row.uploader_username || "" }}</div>
        </template>
      </el-table-column>

      <el-table-column prop="created_at" label="时间" width="150">
        <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
      </el-table-column>

      <el-table-column label="操作" width="168" align="center" fixed="right">
        <template #default="{ row }">
          <div class="table-actions">
            <el-button link type="primary" @click="detail(row)">详情</el-button>
            <el-button link type="success" @click="preview(row)">预览</el-button>
            <el-button link type="warning" @click="reanalyze(row)">重跑</el-button>
          </div>
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

    <el-dialog v-model="detailVisible" width="900px" destroy-on-close class="material-dialog" @closed="clearPreview">
      <template #header>
        <div class="dialog-title">
          <span>资料分析详情</span>
          <el-tag :type="intentTagType(analysis?.intent_level)">
            {{ intentText(analysis?.intent_level) }} · {{ analysis?.intent_score ?? 0 }}
          </el-tag>
        </div>
      </template>

      <div class="detail-lead">
        <div>
          <span class="section-kicker">客户画像</span>
          <h3>{{ displayCustomer(current) }}</h3>
          <p>{{ displayValue(analysis?.summary, "这条资料暂时没有提炼出明确摘要。") }}</p>
          <div v-if="detailPhone" class="detail-actions">
            <el-button type="primary" size="large" :loading="callbackLoading" @click="dialMaterialCustomer">
              一键回拨 {{ detailPhone }}
            </el-button>
          </div>
        </div>
        <div class="detail-meta">
          <span>{{ fileTypeText(current.file_type) }}</span>
          <strong>{{ statusText(current.status) }}</strong>
          <small>{{ formatTime(current.created_at) }}</small>
        </div>
      </div>

      <template v-if="analysis">
        <section v-if="setupHint" class="setup-alert">
          <div>
            <span>识别未完成</span>
            <strong>{{ setupHint.title }}</strong>
            <p>{{ setupHint.text }}</p>
          </div>
          <el-button type="primary" plain @click="reanalyze(current)">重新分析</el-button>
        </section>

        <div class="clean-grid">
          <InfoCard title="客户信息" :items="customerInfo" />
          <InfoCard title="需求线索" :items="needInfo" />
          <InfoCard title="判断依据" :items="decisionInfo" wide />
        </div>

        <section class="focus-card">
          <span>下一步建议</span>
          <strong>{{ setupHint?.action || displayValue(analysis.next_action, "先补充客户资料，再判断下一步。") }}</strong>
          <p>{{ setupHint?.script || displayValue(analysis.sales_script, "暂无推荐话术。") }}</p>
        </section>

        <section v-if="hasReadableTranscript" class="transcript-card">
          <div class="transcript-head">
            <div>
              <span class="section-kicker">原文内容</span>
              <h4>{{ transcriptTitle }}</h4>
            </div>
            <el-tag type="info">{{ analysis.raw_text.length }} 字</el-tag>
          </div>
          <pre>{{ analysis.raw_text }}</pre>
        </section>
      </template>

      <el-empty v-else description="暂无分析结果，完成分析后会显示客户信息和跟进建议。" />

      <FilePreview
        v-if="previewUrl"
        :url="previewUrl"
        :type="current.file_type"
        :name="current.file_name"
        :loading="previewLoading"
        :error="previewError"
        compact
        @loaded="markPreviewLoaded"
        @failed="markPreviewFailed"
      />
    </el-dialog>

    <el-dialog
      v-model="previewVisible"
      title="原文件预览"
      width="680px"
      destroy-on-close
      class="preview-dialog"
      @closed="clearPreview"
    >
      <FilePreview
        v-if="previewUrl"
        :url="previewUrl"
        :type="previewRecord.file_type"
        :name="previewRecord.file_name"
        :loading="previewLoading"
        :error="previewError"
        @loaded="markPreviewLoaded"
        @failed="markPreviewFailed"
      />
      <el-empty v-else description="正在加载原文件，或该文件暂不支持预览。" />
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, defineComponent, h, onBeforeUnmount, onMounted, reactive, ref } from "vue";
import dayjs from "dayjs";
import { ElMessage } from "element-plus";
import http from "../api/http";
import { useAuthStore } from "../stores/auth";

const InfoCard = defineComponent({
  name: "InfoCard",
  props: {
    title: { type: String, required: true },
    items: { type: Array, default: () => [] },
    wide: { type: Boolean, default: false }
  },
  setup(props) {
    return () =>
      h("section", { class: ["clean-card", props.wide ? "wide" : ""] }, [
        h("h4", props.title),
        ...props.items.map((item) =>
          h("div", { class: "clean-row" }, [
            h("span", item.label),
            h("strong", displayValue(item.value))
          ])
        )
      ]);
  }
});

const FilePreview = defineComponent({
  name: "FilePreview",
  props: {
    url: { type: String, required: true },
    type: { type: String, default: "" },
    name: { type: String, default: "" },
    compact: { type: Boolean, default: false },
    loading: { type: Boolean, default: false },
    error: { type: String, default: "" }
  },
  emits: ["loaded", "failed"],
  setup(props, { emit }) {
    return () => {
      if (props.type === "image") {
        return h("div", { class: ["file-preview", "image-viewer", props.compact ? "compact-preview" : ""] }, [
          h("div", { class: "preview-toolbar" }, [
            h("div", { class: "preview-file" }, [
              h("span", "图片预览"),
              h("strong", props.name || "截图")
            ]),
            h(
              "button",
              {
                class: "open-original",
                type: "button",
                onClick: () => window.open(props.url, "_blank", "noopener,noreferrer")
              },
              "打开原图"
            )
          ]),
          h("div", { class: "image-stage" }, [
            props.loading && !props.error ? h("div", { class: "preview-state" }, "正在读取原文件...") : null,
            props.error ? h("div", { class: "preview-state error" }, props.error) : null,
            h("img", {
              src: props.url,
              alt: props.name,
              onLoad: () => emit("loaded"),
              onError: () => emit("failed")
            })
          ])
        ]);
      }
      if (props.type === "audio") {
        return h("div", { class: "file-preview audio-preview" }, [
          h("strong", props.name || "录音文件"),
          props.loading && !props.error ? h("div", { class: "audio-state" }, "录音加载中...") : null,
          props.error ? h("div", { class: "audio-state error" }, props.error) : null,
          h("audio", {
            src: props.url,
            controls: true,
            onCanplay: () => emit("loaded"),
            onError: () => emit("failed")
          })
        ]);
      }
      return h("div", { class: "file-preview unsupported-preview" }, [
        h("strong", props.name || "原文件"),
        h("p", "该类型文件暂不支持内嵌预览。")
      ]);
    };
  }
});

const loading = ref(false);
const loadError = ref("");
const uploading = ref(false);
const previewLoading = ref(false);
const callbackLoading = ref(false);
const items = ref([]);
const total = ref(0);
const salesUsers = ref([]);
const selectedFile = ref(null);
const detailVisible = ref(false);
const previewVisible = ref(false);
const previewUrl = ref("");
const previewError = ref("");
const current = ref({});
const previewRecord = ref({});
const activeStage = ref("");
const pollTimer = ref(null);
const lastDataSignature = ref("");
const query = reactive({ keyword: "", file_type: "", status: "", material_stage: "", page: 1, page_size: 20 });
const uploadForm = reactive({ customer_name: "", customer_phone: "", sales_id: "" });
const auth = useAuthStore();
const isAdmin = computed(() => auth.isAdmin);

const POLL_INTERVAL_MS = 5000;

const quickTabs = [
  { label: "全部资料", value: "" },
  { label: "分析中", value: "processing" },
  { label: "已生成客户", value: "customer_created" },
  { label: "未关联客户", value: "unlinked" },
  { label: "分析失败", value: "failed" }
];

const analysis = computed(() => current.value?.analysis || null);
const latestItem = computed(() => items.value[0] || null);
const rawText = computed(() => analysis.value?.raw_text || "");
const modelName = computed(() => analysis.value?.model_name || "");
const detailPhone = computed(() => dialPhone(analysis.value?.customer_phone || current.value?.customer_phone));
const isTechnicalMissingText = computed(() => {
  const text = rawText.value;
  return (
    text.includes("DASHSCOPE_API_KEY") ||
    text.includes("当前无法读取图片内容") ||
    text.includes("未能读取图片内容") ||
    text.includes("未能读取录音内容") ||
    text.includes("当前没有可用于判断的真实文本内容") ||
    text.includes("本次分析没有拿到可用于判断的真实文本内容") ||
    text.includes("识别服务尚未接入")
  );
});
const rawLooksLikeJson = computed(() => {
  const text = rawText.value.trim();
  return text.startsWith("{") || text.startsWith("[");
});
const isFallbackText = computed(() => {
  const isEmptyImageFallback = current.value?.file_type === "image" && modelName.value === "rule-fallback-image" && !rawText.value.trim();
  return isTechnicalMissingText.value || isEmptyImageFallback;
});
const setupHint = computed(() => {
  if (!analysis.value) return null;
  const type = current.value?.file_type;
  if (type === "image" && isFallbackText.value) {
    return {
      title: "上次图片识别没有拿到文字",
      text: "这张微信截图已经入库，但上一次分析时没有成功读取聊天标题、微信号和聊天文字。如果现在 OCR 已经配置好，请点“重新分析”让系统重新提取。",
      action: "重新分析这张截图，系统会重新读取图片内容并生成客户意向。",
      script: "这条截图已经同步成功，不是上传失败；需要重新分析才能把旧结果更新掉。"
    };
  }
  if (type === "audio" && isFallbackText.value) {
    return {
      title: "录音转写还没拿到完整文字",
      text: "录音已经入库，但本次分析没有拿到完整转写结果。确认 FunASR 或 DashScope ASR 可用后，再重跑这条资料。",
      action: "确认语音转写服务可用后，重跑这条录音。",
      script: "录音文件已经收到，完成转写后会展示完整对话和销售建议。"
    };
  }
  if (isFallbackText.value) {
    return {
      title: "本次分析没有拿到可用正文",
      text: "系统已经收到文件，但这一次没有拿到可用于判断的文字内容。识别服务可用后可以重新分析。",
      action: "确认文件识别能力可用后，重新分析这条资料。",
      script: "当前资料先保留在系统里，等识别服务可用后再生成客户画像。"
    };
  }
  return null;
});
const hasReadableTranscript = computed(() => Boolean(rawText.value.trim()) && !isFallbackText.value && !rawLooksLikeJson.value);
const transcriptTitle = computed(() => (current.value?.file_type === "audio" ? "录音转文字全文" : "图片识别文字"));
const customerInfo = computed(() => [
  { label: "姓名", value: analysis.value?.customer_name || current.value?.customer_name },
  { label: "电话", value: analysis.value?.customer_phone || current.value?.customer_phone },
  { label: "微信号", value: analysis.value?.customer_wechat_id },
  { label: "微信昵称", value: analysis.value?.customer_wechat_nickname },
  { label: "地址", value: analysis.value?.customer_address }
]);
const needInfo = computed(() => [
  { label: "客户需求", value: analysis.value?.customer_needs },
  { label: "关注产品", value: analysis.value?.product_interest },
  { label: "预算", value: analysis.value?.budget },
  { label: "购买时间", value: analysis.value?.purchase_time }
]);
const decisionInfo = computed(() => [
  { label: "客户问题", value: analysis.value?.customer_questions },
  { label: "疑问/异议", value: analysis.value?.customer_objections },
  { label: "判断原因", value: analysis.value?.intent_reason },
  { label: "关键证据", value: analysis.value?.evidence }
]);

function pickFile(file) {
  selectedFile.value = file.raw;
}

function isBlankLike(value) {
  return value === null || value === undefined || String(value).trim() === "" || String(value).trim() === "未提及";
}

function displayValue(value, fallback = "未提及") {
  if (isBlankLike(value)) return fallback;
  return value;
}

function displayCustomer(row) {
  return displayValue(row?.analysis?.customer_name, displayValue(row?.customer_name, "未生成客户"));
}

function dialPhone(phone) {
  return String(phone || "").replace(/[^\d+*#]/g, "");
}

async function dialMaterialCustomer() {
  const phone = detailPhone.value;
  if (!phone) return ElMessage.warning("这条资料没有可回拨电话");
  if (!isAdmin.value && !hasCurrentSalesPhone()) return showCurrentSalesPhoneHint();
  if (!current.value?.customer_id) {
    return ElMessage.warning("这条资料还没有生成客户，暂不能发起服务商回拨");
  }

  callbackLoading.value = true;
  try {
    const callback = await http.post(`/api/customers/${current.value.customer_id}/callback`, {
      customer_phone: phone,
      remark: "资料详情一键回拨"
    });
    ElMessage.success(`已发起服务商回拨，通话ID：${callback.provider_call_id}`);
  } finally {
    callbackLoading.value = false;
  }
}

function hasCurrentSalesPhone() {
  return Boolean(dialPhone(auth.user?.phone));
}

function showCurrentSalesPhoneHint() {
  ElMessage.warning("当前销售账号没有手机号，请让管理员先在销售账号里补手机号");
}

function hasMissingRecognition(row) {
  const text = row?.analysis?.raw_text || "";
  const summary = row?.analysis?.summary || "";
  return (
    text.includes("DASHSCOPE_API_KEY") ||
    text.includes("当前无法读取图片内容") ||
    text.includes("未能读取图片内容") ||
    text.includes("未能读取录音内容") ||
    text.includes("当前没有可用于判断的真实文本内容") ||
    text.includes("本次分析没有拿到可用于判断的真实文本内容") ||
    text.includes("识别服务尚未接入") ||
    summary.includes("当前没有可用于判断的真实文本内容") ||
    summary.includes("本次分析没有拿到可用于判断的真实文本内容")
  );
}

function keyInfoText(row) {
  if (hasMissingRecognition(row)) {
    if (row?.file_type === "image") return "图片已入库，但上次没有识别出微信名和聊天内容";
    if (row?.file_type === "audio") return "录音已入库，但还没有拿到完整转写文本";
    return "资料已入库，但本次分析没有拿到可用正文";
  }
  return displayValue(row?.analysis?.customer_needs || row?.analysis?.summary, "暂无明确需求");
}

function nextActionText(row) {
  if (hasMissingRecognition(row)) {
    if (row?.file_type === "image") return "如果现在 OCR 已可用，请点重跑，系统会重新提取客户和意向";
    if (row?.file_type === "audio") return "确认转写服务可用后点重跑，系统会展示完整对话";
    return "确认识别服务可用后点重跑";
  }
  return displayValue(row?.analysis?.next_action || row?.error_message, "等待更多资料补充");
}

function setStage(value) {
  activeStage.value = value;
  query.material_stage = value;
  query.page = 1;
  load();
}

function statusText(status) {
  return ({ pending: "排队中", processing: "分析中", completed: "已完成", failed: "失败" })[status] || status || "-";
}

function fileTypeText(type) {
  return ({ image: "图片", audio: "录音", document: "文档" })[type] || type || "-";
}

function fileTagType(type) {
  return ({ image: "primary", audio: "success", document: "info" })[type] || "info";
}

function intentText(level) {
  return ({ high: "高意向", medium: "中意向", low: "低意向", none: "暂无意向", unknown: "无法判断" })[level] || level || "无法判断";
}

function intentTagType(level) {
  return ({ high: "danger", medium: "warning", low: "primary", none: "info", unknown: "info" })[level] || "info";
}

function formatTime(value) {
  return value ? dayjs(value).format("MM-DD HH:mm") : "-";
}

function clearPreview() {
  if (previewUrl.value?.startsWith("blob:")) URL.revokeObjectURL(previewUrl.value);
  previewUrl.value = "";
  previewError.value = "";
  previewLoading.value = false;
  previewRecord.value = {};
}

function previewFileUrl(record) {
  return `/api/uploads/public/${record.id}/file?t=${Date.now()}`;
}

function markPreviewLoaded() {
  previewLoading.value = false;
  previewError.value = "";
}

function markPreviewFailed() {
  previewLoading.value = false;
  previewError.value = "原文件暂时加载失败。请稍等几秒再打开，或点击“打开原图”直接查看文件。";
}

async function loadPreview(record) {
  clearPreview();
  if (!["image", "audio"].includes(record.file_type)) return;
  previewLoading.value = true;
  previewRecord.value = record;
  previewUrl.value = previewFileUrl(record);
}

async function loadSales() {
  if (!isAdmin.value) {
    salesUsers.value = [];
    return;
  }
  try {
    salesUsers.value = await http.get("/api/users?role=sales&status=active&page_size=200");
  } catch {
    salesUsers.value = [];
  }
}

function uploadDataSignature(records, nextTotal) {
  return JSON.stringify({
    total: nextTotal,
    rows: records.map((row) => ({
      id: row.id,
      status: row.status,
      customer_id: row.customer_id,
      updated_at: row.updated_at,
      error_message: row.error_message,
      analysis_id: row.analysis?.id,
      intent_level: row.analysis?.intent_level,
      intent_score: row.analysis?.intent_score,
      summary: row.analysis?.summary,
      customer_name: row.analysis?.customer_name,
      customer_phone: row.analysis?.customer_phone,
      customer_wechat_id: row.analysis?.customer_wechat_id,
      customer_needs: row.analysis?.customer_needs,
      next_action: row.analysis?.next_action
    }))
  });
}

function applyUploadData(nextItems, nextTotal, options = {}) {
  const signature = uploadDataSignature(nextItems, nextTotal);
  if (!options.force && signature === lastDataSignature.value) {
    total.value = nextTotal;
    return false;
  }

  lastDataSignature.value = signature;
  const currentById = new Map(items.value.map((item) => [item.id, item]));
  items.value = nextItems.map((nextItem) => {
    const existing = currentById.get(nextItem.id);
    if (!existing) return nextItem;
    Object.assign(existing, nextItem);
    return existing;
  });
  total.value = nextTotal;
  return true;
}

function hasRunningAnalysis(records = items.value) {
  return records.some((item) => ["pending", "processing"].includes(item.status));
}

function startPolling() {
  if (pollTimer.value) return;
  pollTimer.value = window.setInterval(() => {
    load({ silent: true });
  }, POLL_INTERVAL_MS);
}

function stopPolling() {
  if (!pollTimer.value) return;
  window.clearInterval(pollTimer.value);
  pollTimer.value = null;
}

function syncPolling() {
  startPolling();
}

async function refreshOpenDetailFromList() {
  if (!detailVisible.value || !current.value?.id) return;
  const latest = items.value.find((item) => item.id === current.value.id);
  if (latest) current.value = latest;
}

async function load(options = {}) {
  const silent = options.silent === true;
  if (!silent) loading.value = true;
  try {
    loadError.value = "";
    const params = new URLSearchParams();
    Object.entries(query).forEach(([key, value]) => value && params.set(key, value));
    const data = await http.get(`/api/uploads?${params}`);
    applyUploadData(data.items || [], data.total || 0, { force: !silent });
    await refreshOpenDetailFromList();
    syncPolling();
  } catch (error) {
    if (silent) return;
    loadError.value = error.message || "资料数据加载失败";
    items.value = [];
    total.value = 0;
    lastDataSignature.value = "";
    stopPolling();
    if (!silent && loadError.value !== "登录已失效，请重新登录") ElMessage.error(loadError.value);
  } finally {
    if (!silent) loading.value = false;
  }
}

async function upload() {
  if (!selectedFile.value) return ElMessage.warning("请先选择文件");
  uploading.value = true;
  try {
    const form = new FormData();
    form.append("file", selectedFile.value);
    if (uploadForm.customer_name) form.append("customer_name", uploadForm.customer_name);
    if (uploadForm.customer_phone) form.append("customer_phone", uploadForm.customer_phone);
    if (isAdmin.value && uploadForm.sales_id) form.append("sales_id", uploadForm.sales_id);
    const result = await http.post("/api/uploads", form);
    if (result.duplicate) {
      ElMessage.warning(result.message || `该文件已上传过，资料 ID ${result.duplicate_of_id || result.id}`);
    } else {
      ElMessage.success("已上传，后台正在分析");
    }
    selectedFile.value = null;
    uploadForm.customer_name = "";
    uploadForm.customer_phone = "";
    uploadForm.sales_id = "";
    query.page = 1;
    await load({ silent: true });
    startPolling();
  } finally {
    uploading.value = false;
  }
}

async function detail(row) {
  current.value = await http.get(`/api/uploads/${row.id}`);
  detailVisible.value = true;
  if (hasRunningAnalysis([current.value])) startPolling();
  await loadPreview(current.value);
}

async function preview(row) {
  previewVisible.value = true;
  await loadPreview(row);
}

async function reanalyze(row) {
  await http.post(`/api/uploads/${row.id}/reanalyze`);
  ElMessage.success("已重新加入分析队列");
  await load({ silent: true });
  startPolling();
}

onMounted(() => {
  loadSales();
  load();
  startPolling();
});

onBeforeUnmount(() => {
  stopPolling();
  clearPreview();
});
</script>

<style scoped>
.uploads-page { display: grid; gap: 14px; }
.material-hero {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  padding: 24px;
  border: 1px solid rgba(216, 226, 239, .95);
  border-radius: 26px;
  background: radial-gradient(circle at 88% 20%, rgba(17, 184, 166, .18), transparent 28%), rgba(255, 255, 255, .96);
  box-shadow: var(--shadow);
}
.material-hero h2 { margin: 4px 0 8px; font-size: 34px; line-height: 1; letter-spacing: -.06em; }
.material-hero p { margin: 0; color: #667085; }
.search-panel {
  display: grid;
  grid-template-columns: minmax(320px, 1fr) 150px 150px 96px;
  gap: 10px;
  padding: 12px;
  border: 1px solid rgba(216, 226, 239, .9);
  border-radius: 22px;
  background: rgba(255, 255, 255, .92);
  box-shadow: 0 12px 30px rgba(15, 35, 67, .07);
}
.main-search :deep(.el-input__wrapper) { min-height: 46px; padding-left: 16px; }
.latest-material {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 16px 18px;
  border: 1px solid rgba(37, 99, 235, .18);
  border-left: 5px solid #2563eb;
  border-radius: 22px;
  background: linear-gradient(135deg, #ffffff 0%, #eef7ff 100%);
  box-shadow: 0 14px 34px rgba(15, 35, 67, .08);
}
.latest-copy h3 {
  margin: 3px 0 8px;
  font-size: 20px;
  letter-spacing: -.03em;
}
.latest-copy p {
  display: grid;
  gap: 4px;
  margin: 0;
}
.latest-copy p strong {
  color: #111827;
  word-break: break-all;
}
.latest-copy p span {
  color: #667085;
  font-size: 13px;
}
.latest-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  flex-wrap: wrap;
}
.upload-strip {
  display: grid;
  grid-template-columns: minmax(220px, 1fr) 180px 180px 180px 110px;
  align-items: center;
  gap: 10px;
  padding: 14px;
  border: 1px solid rgba(37, 99, 235, .18);
  border-radius: 20px;
  background: #f8fbff;
}
.upload-strip strong, .upload-strip span { display: block; }
.upload-strip span { margin-top: 4px; color: #667085; font-size: 13px; }
.quick-tabs { display: flex; gap: 8px; flex-wrap: wrap; }
.quick-tabs button {
  padding: 9px 14px;
  border: 1px solid #d9e2ef;
  border-radius: 999px;
  color: #50627c;
  background: rgba(255, 255, 255, .9);
  cursor: pointer;
  font-weight: 800;
}
.quick-tabs button.active { color: #fff; border-color: transparent; background: linear-gradient(135deg, var(--blue), var(--cyan)); }
.material-table { min-height: 360px; }
.material-title { display: flex; align-items: center; gap: 8px; }
.material-title strong { font-size: 16px; }
.ellipsis { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.dialog-title { display: flex; align-items: center; gap: 12px; font-size: 18px; font-weight: 900; }
.detail-lead {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 150px;
  gap: 18px;
  padding: 20px;
  border-radius: 22px;
  color: #fff;
  background: radial-gradient(circle at 92% 28%, rgba(17, 184, 166, .42), transparent 30%), linear-gradient(135deg, #102b50, #08172b);
}
.detail-lead h3 { margin: 4px 0 8px; font-size: 30px; letter-spacing: -.05em; }
.detail-lead p { margin: 0; color: #c7d5ea; line-height: 1.7; }
.detail-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 16px;
}
.detail-actions :deep(.el-button) {
  border: 0;
  border-radius: 999px;
  font-weight: 900;
  color: #fff;
  background: linear-gradient(135deg, #0f63ff, #08a7a7);
  box-shadow: 0 12px 28px rgba(8, 167, 167, .24);
}
.detail-meta { display: grid; align-content: center; justify-items: end; gap: 6px; }
.detail-meta span, .detail-meta small { color: #a8bad3; }
.detail-meta strong { font-size: 22px; }
.setup-alert {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-top: 14px;
  padding: 16px;
  border: 1px solid rgba(245, 158, 11, .28);
  border-radius: 18px;
  background: linear-gradient(135deg, #fff8eb, #ffffff);
}
.setup-alert span {
  display: block;
  color: #b45309;
  font-size: 12px;
  font-weight: 900;
  letter-spacing: .08em;
  text-transform: uppercase;
}
.setup-alert strong {
  display: block;
  margin-top: 4px;
  color: #111827;
  font-size: 18px;
}
.setup-alert p {
  margin: 6px 0 0;
  color: #5f6f86;
  line-height: 1.7;
}
.file-preview {
  margin-top: 14px;
  padding: 0;
  border: 1px solid #d9e2ef;
  border-radius: 20px;
  background: #fff;
  overflow: hidden;
}
.image-viewer {
  background: #fff;
}
.preview-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 14px;
  border-bottom: 1px solid #e4ebf5;
  background: #f8fafc;
}
.preview-file {
  min-width: 0;
}
.preview-file span {
  display: block;
  color: #667085;
  font-size: 12px;
  font-weight: 800;
}
.preview-file strong {
  display: block;
  overflow: hidden;
  color: #111827;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.open-original {
  flex-shrink: 0;
  padding: 7px 12px;
  border: 1px solid #cbd8ea;
  border-radius: 999px;
  color: #2563eb;
  background: #fff;
  cursor: pointer;
  font-weight: 800;
}
.image-stage {
  position: relative;
  display: grid;
  place-items: center;
  width: 100%;
  height: min(58vh, 500px);
  min-height: 280px;
  padding: 14px;
  overflow: hidden;
  background:
    linear-gradient(45deg, rgba(255,255,255,.04) 25%, transparent 25%),
    linear-gradient(-45deg, rgba(255,255,255,.04) 25%, transparent 25%),
    #0b1630;
  background-size: 18px 18px;
}
.preview-state {
  position: absolute;
  z-index: 2;
  display: grid;
  place-items: center;
  min-width: 180px;
  padding: 10px 14px;
  border-radius: 999px;
  color: #d7e7ff;
  background: rgba(11, 22, 48, .82);
  box-shadow: 0 10px 30px rgba(0, 0, 0, .22);
  font-weight: 800;
}
.preview-state.error,
.audio-state.error {
  color: #991b1b;
  background: #fee2e2;
}
.audio-state {
  padding: 10px 12px;
  border-radius: 12px;
  color: #2563eb;
  background: #eff6ff;
  font-weight: 800;
}
.compact-preview .image-stage {
  height: 240px;
  min-height: 220px;
}
.image-stage img {
  position: absolute;
  inset: 14px;
  display: block;
  width: calc(100% - 28px);
  height: calc(100% - 28px);
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
  border-radius: 12px;
  box-shadow: 0 12px 34px rgba(15, 35, 67, .16);
}
.audio-preview { display: grid; gap: 12px; padding: 14px; }
.audio-preview audio { width: 100%; }
.unsupported-preview { padding: 14px; }
.unsupported-preview p { margin: 8px 0 0; color: #667085; }
:deep(.preview-dialog .el-dialog) {
  max-width: min(680px, calc(100vw - 48px));
}
:deep(.preview-dialog .el-dialog__body) {
  max-height: 78vh;
  overflow: hidden;
  padding-top: 8px;
}
:deep(.material-dialog .el-dialog) {
  max-height: calc(100vh - 48px);
  display: flex;
  flex-direction: column;
}
:deep(.material-dialog .el-dialog__body) {
  max-height: calc(100vh - 148px);
  overflow: auto;
}
.focus-card {
  margin-top: 14px;
  padding: 18px;
  border: 1px solid rgba(17, 184, 166, .24);
  border-radius: 20px;
  background: linear-gradient(135deg, #ffffff, #f2fffd);
}
.focus-card span { color: #07966d; font-size: 12px; font-weight: 900; letter-spacing: .08em; }
.focus-card strong { display: block; margin: 8px 0; font-size: 20px; line-height: 1.55; }
.focus-card p {
  margin: 0;
  padding: 14px;
  border-radius: 14px;
  color: #d7e7ff;
  background: #0b1630;
  line-height: 1.8;
  white-space: pre-wrap;
}
.transcript-card {
  margin-top: 14px;
  padding: 16px;
  border: 1px solid #d9e2ef;
  border-radius: 20px;
  background: #fff;
}
.transcript-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}
.transcript-head h4 {
  margin: 4px 0 0;
  font-size: 18px;
}
.transcript-card pre {
  max-height: 360px;
  margin: 0;
  padding: 16px;
  overflow: auto;
  border-radius: 16px;
  color: #d7e7ff;
  background: #0b1630;
  font-family: "Microsoft YaHei UI", "PingFang SC", "Segoe UI", Arial, sans-serif;
  font-size: 14px;
  line-height: 1.85;
  white-space: pre-wrap;
  word-break: break-word;
}
.clean-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; margin-top: 12px; }
.clean-card { padding: 16px; border: 1px solid #d9e2ef; border-radius: 18px; background: #fff; }
.clean-card.wide { grid-column: 1 / -1; }
.clean-card h4 { margin: 0 0 10px; }
.clean-row {
  display: grid;
  grid-template-columns: 88px minmax(0, 1fr);
  gap: 12px;
  padding: 9px 0;
  border-bottom: 1px dashed #e4ebf5;
}
.clean-row:last-child { border-bottom: 0; }
.clean-row span { color: #667085; font-size: 13px; }
.clean-row strong { line-height: 1.65; white-space: pre-wrap; }
@media (max-width: 980px) {
  .search-panel, .upload-strip, .detail-lead, .clean-grid { grid-template-columns: 1fr; }
  .latest-material { display: block; }
  .latest-actions { justify-content: flex-start; margin-top: 12px; }
  .material-hero { display: block; }
  .material-hero .el-button { margin-top: 14px; }
  .detail-meta { justify-items: start; }
}
</style>
