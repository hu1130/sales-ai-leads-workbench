<template>
  <div class="call-settings-page">
    <section class="settings-summary">
      <article class="summary-card">
        <span>外呼服务商</span>
        <strong>{{ providerText(config.provider || status?.provider) }}</strong>
        <p>{{ status?.configured ? "配置完整" : "等待配置" }} · {{ sourceText(config.source) }}</p>
      </article>
      <article class="summary-card blue">
        <span>Webhook</span>
        <strong>{{ config.webhook_secret_configured ? "已保护" : "未设置" }}</strong>
        <p>{{ config.webhook_secret_configured ? config.webhook_secret_mask : "建议上线前设置密钥" }}</p>
      </article>
      <article class="summary-card amber">
        <span>销售回拨</span>
        <strong>{{ config.caller ? "可测试" : "待确认" }}</strong>
        <p>{{ config.caller || "测试时填写销售手机号" }}</p>
      </article>
      <article class="summary-card red">
        <span>接口超时</span>
        <strong>{{ config.timeout || status?.timeout || "-" }} 秒</strong>
        <p>后台保存，服务端生效</p>
      </article>
    </section>

    <section class="settings-layout">
      <div class="main-column">
        <section class="config-panel">
          <div class="config-head">
            <div>
              <span class="section-kicker">服务商配置</span>
              <h3>服务商配置</h3>
            </div>
            <div class="head-actions">
              <el-tag :type="config.enabled ? 'success' : 'info'">{{ config.enabled ? "启用" : "停用" }}</el-tag>
              <el-button :icon="Refresh" :loading="loading" @click="loadAll">刷新</el-button>
            </div>
          </div>

          <el-form :model="form" label-position="top" class="settings-form" v-loading="loading">
            <div class="config-grid">
              <el-form-item label="服务商">
                <el-select v-model="form.provider">
                  <el-option label="演示服务商" value="mock" />
                  <el-option label="腾讯云呼叫中心" value="tencent" />
                  <el-option label="阿里云语音外呼" value="aliyun" />
                  <el-option label="自建 SIP 网关" value="sip" />
                </el-select>
              </el-form-item>
              <el-form-item label="启用状态">
                <el-switch v-model="form.enabled" active-text="启用" inactive-text="停用" />
              </el-form-item>
              <el-form-item label="服务商 API 地址">
                <el-input v-model="form.base_url" placeholder="https://api.provider.example.com" />
              </el-form-item>
              <el-form-item label="App ID">
                <el-input v-model="form.app_id" placeholder="服务商 App ID，可选" />
              </el-form-item>
              <el-form-item label="App Key">
                <el-input v-model="form.app_key" :placeholder="secretPlaceholder(config.app_key_configured, config.app_key_mask)" show-password type="password" />
                <template #extra>
                  <button v-if="config.app_key_configured" class="clear-secret" type="button" @click="form.clear_app_key = !form.clear_app_key">
                    {{ form.clear_app_key ? "已选择清除" : "清除已保存 App Key" }}
                  </button>
                </template>
              </el-form-item>
              <el-form-item label="App Secret">
                <el-input v-model="form.app_secret" :placeholder="secretPlaceholder(config.app_secret_configured, config.app_secret_mask)" show-password type="password" />
                <template #extra>
                  <button v-if="config.app_secret_configured" class="clear-secret" type="button" @click="form.clear_app_secret = !form.clear_app_secret">
                    {{ form.clear_app_secret ? "已选择清除" : "清除已保存 App Secret" }}
                  </button>
                </template>
              </el-form-item>
              <el-form-item label="主叫号码">
                <el-input v-model="form.caller" placeholder="例如 4008001000 或销售主叫号码" />
              </el-form-item>
              <el-form-item label="请求超时">
                <el-input-number v-model="form.timeout" :min="1" :max="300" />
              </el-form-item>
              <el-form-item label="Webhook 共享密钥" class="wide">
                <el-input v-model="form.webhook_secret" :placeholder="secretPlaceholder(config.webhook_secret_configured, config.webhook_secret_mask)" show-password type="password" />
                <template #extra>
                  <button v-if="config.webhook_secret_configured" class="clear-secret" type="button" @click="form.clear_webhook_secret = !form.clear_webhook_secret">
                    {{ form.clear_webhook_secret ? "已选择清除" : "清除已保存 Webhook 密钥" }}
                  </button>
                </template>
              </el-form-item>
            </div>
            <div class="settings-actions">
              <el-button @click="resetForm">还原接口配置</el-button>
              <el-button type="primary" :loading="saving" @click="saveConfig">保存配置</el-button>
            </div>
          </el-form>
        </section>

        <section class="config-panel">
          <div class="config-head">
            <div>
              <span class="section-kicker">服务商状态</span>
              <h3>服务商状态</h3>
            </div>
            <el-tag :type="status?.configured ? 'success' : 'warning'">
              {{ status?.configured ? "配置完整" : "未完整" }}
            </el-tag>
          </div>
          <div class="status-grid">
            <div class="status-item">
              <span>当前服务商</span>
              <strong>{{ providerText(status?.provider) }}</strong>
            </div>
            <div class="status-item">
              <span>运行模式</span>
              <strong>{{ modeText(status?.mode) }}</strong>
            </div>
            <div class="status-item">
              <span>服务商地址</span>
              <el-tag :type="status?.base_url_configured ? 'success' : 'warning'">{{ status?.base_url_configured ? "已配置" : "未配置" }}</el-tag>
            </div>
            <div class="status-item">
              <span>App ID / Key</span>
              <el-tag :type="status?.app_id_configured || status?.app_key_configured ? 'success' : 'warning'">
                {{ status?.app_id_configured || status?.app_key_configured ? "已配置" : "未配置" }}
              </el-tag>
            </div>
            <div class="status-item">
              <span>App Secret</span>
              <el-tag :type="status?.app_secret_configured ? 'success' : 'warning'">{{ status?.app_secret_configured ? "已配置" : "未配置" }}</el-tag>
            </div>
            <div class="status-item">
              <span>主叫号码</span>
              <el-tag :type="status?.caller_configured ? 'success' : 'info'">{{ status?.caller_configured ? "已配置" : "测试时填写" }}</el-tag>
            </div>
          </div>
          <div v-if="translatedNotes.length" class="note-list">
            <div v-for="note in translatedNotes" :key="note" class="note-row">
              <el-icon><WarningFilled /></el-icon>
              <span>{{ note }}</span>
            </div>
          </div>
        </section>

        <section class="config-panel">
          <div class="config-head">
            <div>
              <span class="section-kicker">回调地址</span>
              <h3>回调地址</h3>
            </div>
            <el-tag type="info">复制给服务商</el-tag>
          </div>
          <div class="webhook-list">
            <div class="webhook-row">
              <div>
                <strong>AI 机器人外呼回调</strong>
                <p>服务商通话状态、录音、转写内容从这里回传。</p>
              </div>
              <el-input :model-value="status?.ai_robot_webhook_url || ''" readonly>
                <template #append>
                  <el-button :icon="CopyDocument" @click="copyText(status?.ai_robot_webhook_url)">复制</el-button>
                </template>
              </el-input>
            </div>
            <div class="webhook-row">
              <div>
                <strong>销售一键回拨回调</strong>
                <p>服务商双向回呼结果从这里回传。</p>
              </div>
              <el-input :model-value="status?.sales_callback_webhook_url || ''" readonly>
                <template #append>
                  <el-button :icon="CopyDocument" @click="copyText(status?.sales_callback_webhook_url)">复制</el-button>
                </template>
              </el-input>
            </div>
          </div>
        </section>

        <section class="config-panel">
          <div class="config-head">
            <div>
              <span class="section-kicker">测试拨打</span>
              <h3>测试拨打</h3>
            </div>
            <el-tag :type="status?.configured ? 'success' : 'warning'">{{ status?.configured ? "可测试" : "配置未完整" }}</el-tag>
          </div>
          <div class="test-grid">
            <div class="test-card">
              <div class="test-title">
                <el-icon><PhoneFilled /></el-icon>
                <strong>销售一键回拨</strong>
              </div>
              <el-form :model="callbackForm" label-position="top">
                <el-form-item label="销售手机号">
                  <el-input v-model="callbackForm.sales_phone" placeholder="留空则使用配置主叫号码" />
                </el-form-item>
                <el-form-item label="客户手机号">
                  <el-input v-model="callbackForm.customer_phone" placeholder="请输入测试客户手机号" />
                </el-form-item>
              </el-form>
              <el-button type="primary" :icon="PhoneFilled" :loading="testingCallback" :disabled="!status?.configured" @click="testCallback">
                发起回拨测试
              </el-button>
            </div>

            <div class="test-card">
              <div class="test-title">
                <el-icon><Connection /></el-icon>
                <strong>AI 机器人外呼</strong>
              </div>
              <el-form :model="robotForm" label-position="top">
                <el-form-item label="客户手机号">
                  <el-input v-model="robotForm.customer_phone" placeholder="请输入测试客户手机号" />
                </el-form-item>
                <el-form-item label="测试话术">
                  <el-input v-model="robotForm.script" type="textarea" :rows="3" />
                </el-form-item>
              </el-form>
              <el-button type="success" :icon="Connection" :loading="testingRobot" :disabled="!status?.configured" @click="testRobot">
                发起机器人测试
              </el-button>
            </div>
          </div>
          <div v-if="testResult" class="test-result">
            <span>最近测试</span>
            <strong>{{ testResult.message }}</strong>
            <p>服务商：{{ providerText(testResult.provider) }} · 通话 ID：{{ testResult.provider_call_id || "-" }}</p>
          </div>
        </section>
      </div>

      <aside class="status-panel">
        <section class="config-panel">
          <div class="config-head compact">
            <div>
              <span class="section-kicker">上线检查</span>
              <h3>上线前检查</h3>
            </div>
          </div>
          <div class="check-list">
            <div v-for="item in checklist" :key="item.label" class="check-row">
              <el-icon :class="item.ok ? 'ok' : 'warn'">
                <CircleCheckFilled v-if="item.ok" />
                <WarningFilled v-else />
              </el-icon>
              <div>
                <strong>{{ item.label }}</strong>
                <p>{{ item.text }}</p>
              </div>
            </div>
          </div>
        </section>

        <section class="config-panel security-panel">
          <div class="config-head compact">
            <div>
              <span class="section-kicker">安全边界</span>
              <h3>安全边界</h3>
            </div>
            <el-icon><Lock /></el-icon>
          </div>
          <div class="security-list">
            <p>密钥字段提交后由后端加密保存，页面只显示是否已配置和脱敏尾号。</p>
            <p>重新输入密钥会覆盖旧值；点击清除后保存，会删除对应密钥。</p>
            <p>配置来源显示为数据库时，说明后台配置已经覆盖环境变量。</p>
          </div>
        </section>
      </aside>
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import {
  CircleCheckFilled,
  Connection,
  CopyDocument,
  Lock,
  PhoneFilled,
  Refresh,
  WarningFilled
} from "@element-plus/icons-vue";
import http from "../api/http";
import { useAuthStore } from "../stores/auth";

const emptyConfig = {
  provider: "mock",
  base_url: "",
  app_id: "",
  app_key_configured: false,
  app_key_mask: "",
  app_secret_configured: false,
  app_secret_mask: "",
  caller: "",
  webhook_secret_configured: false,
  webhook_secret_mask: "",
  timeout: 30,
  enabled: true,
  source: "environment",
  updated_at: null,
  updated_by: null
};

const loading = ref(false);
const saving = ref(false);
const testingCallback = ref(false);
const testingRobot = ref(false);
const status = ref(null);
const config = reactive({ ...emptyConfig });
const testResult = ref(null);
const auth = useAuthStore();

const form = reactive({
  provider: "mock",
  enabled: true,
  base_url: "",
  app_id: "",
  app_key: "",
  app_secret: "",
  caller: "",
  webhook_secret: "",
  timeout: 30,
  clear_app_key: false,
  clear_app_secret: false,
  clear_webhook_secret: false
});

const callbackForm = reactive({
  sales_phone: "",
  customer_phone: ""
});

const robotForm = reactive({
  customer_phone: "",
  script: "您好，我是智能外呼助手，想确认您是否还需要进一步了解我们的销售线索分析方案。"
});

const checklist = computed(() => [
  {
    label: "服务商配置完整",
    ok: Boolean(status.value?.configured),
    text: status.value?.configured ? providerText(status.value.provider) : "请补齐服务商地址、Key/ID、Secret，并启用配置"
  },
  {
    label: "Webhook 地址可用",
    ok: Boolean(status.value?.ai_robot_webhook_url && status.value?.sales_callback_webhook_url),
    text: "AI 机器人和销售回拨各有独立回调地址"
  },
  {
    label: "Webhook 密钥已设置",
    ok: Boolean(status.value?.webhook_secret_configured),
    text: status.value?.webhook_secret_configured ? "服务商回调会校验共享密钥" : "建议上线前配置 Webhook 共享密钥"
  },
  {
    label: "主叫号码已配置",
    ok: Boolean(status.value?.caller_configured),
    text: status.value?.caller_configured ? "销售回拨可直接测试" : "测试回拨时需要填写销售手机号"
  },
  {
    label: "密钥脱敏显示",
    ok: true,
    text: "页面不返回 App Key、App Secret、Webhook Secret 明文"
  }
]);

const translatedNotes = computed(() => (status.value?.notes || []).map(noteText));

onMounted(loadAll);

watch(
  () => auth.token,
  (token, previousToken) => {
    if (token && token !== previousToken) loadAll();
  }
);

async function loadAll() {
  loading.value = true;
  try {
    const [configData, statusData] = await Promise.all([
      http.get("/api/call-provider/config"),
      http.get("/api/call-provider/status")
    ]);
    applyConfig(configData);
    status.value = statusData;
  } finally {
    loading.value = false;
  }
}

function applyConfig(data) {
  Object.assign(config, { ...emptyConfig, ...data });
  resetForm();
}

function resetForm() {
  Object.assign(form, {
    provider: config.provider || "mock",
    enabled: Boolean(config.enabled),
    base_url: config.base_url || "",
    app_id: config.app_id || "",
    app_key: "",
    app_secret: "",
    caller: config.caller || "",
    webhook_secret: "",
    timeout: Number(config.timeout || 30),
    clear_app_key: false,
    clear_app_secret: false,
    clear_webhook_secret: false
  });
}

async function saveConfig() {
  saving.value = true;
  try {
    const payload = {
      provider: form.provider,
      enabled: form.enabled,
      base_url: form.base_url,
      app_id: form.app_id,
      caller: form.caller,
      timeout: form.timeout,
      clear_app_key: form.clear_app_key,
      clear_app_secret: form.clear_app_secret,
      clear_webhook_secret: form.clear_webhook_secret
    };
    if (form.app_key.trim()) payload.app_key = form.app_key;
    if (form.app_secret.trim()) payload.app_secret = form.app_secret;
    if (form.webhook_secret.trim()) payload.webhook_secret = form.webhook_secret;

    const saved = await http.put("/api/call-provider/config", payload);
    ElMessage.success("外呼配置已保存");
    applyConfig(saved);
    status.value = await http.get("/api/call-provider/status");
  } finally {
    saving.value = false;
  }
}

async function testCallback() {
  if (!callbackForm.customer_phone.trim()) return ElMessage.warning("请填写测试客户手机号");
  testingCallback.value = true;
  try {
    testResult.value = await http.post("/api/call-provider/test-callback", {
      sales_phone: callbackForm.sales_phone || undefined,
      customer_phone: callbackForm.customer_phone
    });
    ElMessage.success("销售回拨测试已发起");
  } finally {
    testingCallback.value = false;
  }
}

async function testRobot() {
  if (!robotForm.customer_phone.trim()) return ElMessage.warning("请填写测试客户手机号");
  testingRobot.value = true;
  try {
    testResult.value = await http.post("/api/call-provider/test-ai-robot", {
      customer_phone: robotForm.customer_phone,
      script: robotForm.script
    });
    ElMessage.success("AI 机器人测试已发起");
  } finally {
    testingRobot.value = false;
  }
}

async function copyText(value) {
  if (!value) return ElMessage.warning("暂无可复制地址");
  await navigator.clipboard.writeText(value);
  ElMessage.success("已复制");
}

function secretPlaceholder(configured, mask) {
  return configured ? `已配置 ${mask || ""}，留空则不修改` : "未配置，请输入后保存";
}

function providerText(value) {
  return ({
    mock: "演示服务商",
    tencent: "腾讯云呼叫中心",
    aliyun: "阿里云语音外呼",
    sip: "自建 SIP 网关"
  })[value] || value || "未配置";
}

function modeText(value) {
  return ({
    mock: "演示模式",
    real: "真实服务商"
  })[value] || "未知模式";
}

function sourceText(value) {
  return ({
    database: "后台配置",
    environment: "环境变量"
  })[value] || "未加载";
}

function noteText(value) {
  if (value?.includes("mock provider")) return "当前为演示服务商，只用于流程测试，不会拨打真实电话。";
  if (value?.includes("required configuration")) return "真实服务商已选择，但服务商配置还没有补齐。";
  if (value?.includes("webhook secret")) return "尚未设置 Webhook 共享密钥，上线前建议启用回调密钥校验。";
  if (value?.includes("environment")) return "当前配置来自后端环境变量。";
  if (value?.includes("encrypted database")) return "当前配置来自后台加密保存的数据库配置。";
  return value;
}
</script>

<style scoped>
.call-settings-page {
  display: grid;
  gap: 16px;
}

.settings-summary {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
}

.summary-card {
  position: relative;
  min-height: 116px;
  padding: 18px;
  overflow: hidden;
  border: 1px solid rgba(216, 226, 239, .95);
  border-radius: 18px;
  background: rgba(255, 255, 255, .94);
  box-shadow: var(--shadow);
}

.summary-card::before {
  content: "";
  position: absolute;
  inset: 0 auto 0 0;
  width: 5px;
  background: var(--cyan);
}

.summary-card.blue::before { background: var(--blue); }
.summary-card.amber::before { background: var(--amber); }
.summary-card.red::before { background: var(--red); }

.summary-card span {
  color: var(--muted);
  font-size: 13px;
  font-weight: 900;
}

.summary-card strong {
  display: block;
  margin-top: 9px;
  font-size: 28px;
  line-height: 1.08;
  letter-spacing: 0;
}

.summary-card p {
  margin: 9px 0 0;
  color: var(--muted);
}

.settings-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 330px;
  gap: 16px;
  align-items: start;
}

.main-column,
.status-panel {
  display: grid;
  gap: 14px;
}

.config-panel {
  overflow: hidden;
  border: 1px solid rgba(216, 226, 239, .95);
  border-radius: 18px;
  background: rgba(255, 255, 255, .96);
  box-shadow: 0 14px 34px rgba(15, 35, 67, .08);
}

.config-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 16px 18px;
  border-bottom: 1px solid var(--line);
}

.config-head.compact {
  padding-bottom: 12px;
}

.config-head h3 {
  margin: 0;
  font-size: 20px;
  letter-spacing: 0;
}

.head-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.settings-form {
  display: grid;
  gap: 12px;
}

.config-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 2px 14px;
  padding: 16px 18px 4px;
}

.wide {
  grid-column: 1 / -1;
}

.clear-secret {
  margin-top: 6px;
  padding: 0;
  border: 0;
  color: #0b63ce;
  background: transparent;
  cursor: pointer;
  font-size: 12px;
  font-weight: 800;
}

.settings-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding: 0 18px 18px;
}

.status-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  padding: 16px 18px;
}

.status-item {
  min-height: 82px;
  padding: 14px;
  border: 1px solid #e5edf7;
  border-radius: 14px;
  background: #f8fbff;
}

.status-item span {
  display: block;
  color: var(--muted);
  font-size: 12px;
  font-weight: 800;
}

.status-item strong {
  display: block;
  margin-top: 9px;
  font-size: 18px;
}

.note-list {
  display: grid;
  gap: 8px;
  padding: 0 18px 18px;
}

.note-row {
  display: grid;
  grid-template-columns: 20px minmax(0, 1fr);
  gap: 8px;
  align-items: start;
  color: #7a4c04;
  font-size: 13px;
}

.webhook-list,
.security-list {
  display: grid;
  gap: 14px;
  padding: 16px 18px;
}

.webhook-row {
  display: grid;
  grid-template-columns: 230px minmax(0, 1fr);
  gap: 14px;
  align-items: center;
  padding-bottom: 14px;
  border-bottom: 1px dashed #e4ebf5;
}

.webhook-row:last-child {
  padding-bottom: 0;
  border-bottom: 0;
}

.webhook-row strong,
.test-title strong {
  display: block;
  font-size: 15px;
}

.webhook-row p,
.security-list p,
.test-result p {
  margin: 5px 0 0;
  color: var(--muted);
  font-size: 12px;
  line-height: 1.55;
}

.test-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
  padding: 16px 18px;
}

.test-card {
  display: grid;
  gap: 12px;
  align-content: start;
  padding: 16px;
  border: 1px solid #e5edf7;
  border-radius: 14px;
  background: #fbfdff;
}

.test-title {
  display: flex;
  align-items: center;
  gap: 8px;
}

.test-result {
  margin: 0 18px 18px;
  padding: 14px;
  border: 1px solid rgba(28, 197, 159, .22);
  border-radius: 14px;
  background: rgba(28, 197, 159, .08);
}

.test-result span {
  color: var(--green);
  font-size: 12px;
  font-weight: 900;
}

.test-result strong {
  display: block;
  margin-top: 4px;
}

.check-list {
  display: grid;
  gap: 12px;
  padding: 16px;
}

.check-row {
  display: grid;
  grid-template-columns: 24px minmax(0, 1fr);
  gap: 10px;
  padding-bottom: 12px;
  border-bottom: 1px dashed #e4ebf5;
}

.check-row:last-child {
  padding-bottom: 0;
  border-bottom: 0;
}

.check-row .el-icon {
  margin-top: 2px;
  font-size: 18px;
}

.check-row .ok { color: var(--green); }
.check-row .warn { color: var(--amber); }

.check-row strong {
  display: block;
  font-size: 14px;
}

.check-row p {
  margin: 4px 0 0;
  color: var(--muted);
  font-size: 12px;
  line-height: 1.55;
}

.security-panel .config-head > .el-icon {
  color: var(--green);
  font-size: 20px;
}

@media (max-width: 1180px) {
  .settings-summary,
  .settings-layout {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .status-panel {
    grid-column: 1 / -1;
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .status-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 760px) {
  .settings-summary,
  .settings-layout,
  .status-panel,
  .status-grid,
  .test-grid,
  .webhook-row,
  .config-grid {
    grid-template-columns: 1fr;
  }
}
</style>
