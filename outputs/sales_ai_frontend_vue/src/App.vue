<template>
  <el-config-provider size="default">
    <div class="app-shell">
      <aside class="sidebar">
        <div class="brand">
          <div class="brand-mark">AI</div>
          <div>
            <strong>销售线索工作台</strong>
            <span>获客资料自动分析与分配</span>
          </div>
        </div>

        <el-menu :default-active="$route.path" router class="nav-menu">
          <el-menu-item v-for="item in visibleRoutes" :key="item.path" :index="item.path">
            <el-icon><component :is="item.meta.icon" /></el-icon>
            <span>{{ item.meta.title }}</span>
          </el-menu-item>
        </el-menu>

        <section class="account-card">
          <span>当前账号</span>
          <strong>{{ auth.user?.name || "未登录" }}</strong>
          <p>{{ roleText }}</p>
          <p v-if="auth.user?.tenant_name" class="tenant-line">当前公司：{{ auth.user.tenant_name }}</p>
          <el-button v-if="!auth.isLogin" type="primary" class="full-btn" @click="loginVisible = true">登录系统</el-button>
          <el-button v-else class="full-btn" @click="logout">退出登录</el-button>
        </section>
      </aside>

      <main class="workspace">
        <header class="topbar">
          <div>
            <p class="eyebrow">{{ todayText }}</p>
            <h1>{{ currentTitle }}</h1>
          </div>
          <div class="top-actions">
            <el-button @click="reloadPage">刷新数据</el-button>
            <el-button type="primary" @click="loginVisible = true">{{ auth.isLogin ? "切换账号" : "登录" }}</el-button>
          </div>
        </header>

        <router-view v-slot="{ Component }">
          <component :is="Component" :key="$route.fullPath" />
        </router-view>
      </main>

      <el-dialog v-model="loginVisible" title="登录系统" width="430px" destroy-on-close class="login-dialog">
        <el-form :model="loginForm" label-position="top" @submit.prevent="login">
          <el-form-item label="账号">
            <el-input v-model="loginForm.username" placeholder="admin" autofocus />
          </el-form-item>
          <el-form-item label="密码">
            <el-input v-model="loginForm.password" type="password" show-password placeholder="admin123" />
          </el-form-item>
          <el-alert v-if="loginError" :title="loginError" type="error" show-icon :closable="false" />
        </el-form>
        <template #footer>
          <el-button @click="loginVisible = false">取消</el-button>
          <el-button type="primary" :loading="loginLoading" @click="login">进入工作台</el-button>
        </template>
      </el-dialog>
    </div>
  </el-config-provider>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import dayjs from "dayjs";
import { ElMessage } from "element-plus";
import { navRoutes } from "./router";
import { useAuthStore } from "./stores/auth";

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();

const loginVisible = ref(!auth.isLogin);
const loginLoading = ref(false);
const loginError = ref("");
const loginForm = ref({ username: "admin", password: "admin123" });

const todayText = computed(() => dayjs().format("YYYY年MM月DD日"));
const currentTitle = computed(() => route.meta.title || "销售 AI 线索工作台");
const roleText = computed(() => {
  if (!auth.user) return "请先登录";
  return auth.user.role === "admin" ? "系统管理员" : "销售账号";
});
const visibleRoutes = computed(() =>
  navRoutes.filter((item) => {
    if (item.meta.hidden) return false;
    if (item.meta.adminOnly && !auth.isAdmin) return false;
    return auth.isAdmin || !["assignment", "team", "users"].includes(item.name);
  })
);

function handleAuthExpired() {
  if (auth.isLogin || auth.user) {
    auth.logout();
    ElMessage.warning("登录已失效，请重新登录");
  }
  loginVisible.value = true;
}

async function login() {
  loginLoading.value = true;
  loginError.value = "";
  try {
    await auth.login(loginForm.value);
    loginVisible.value = false;
    ElMessage.success("登录成功");
    router.replace(route.fullPath);
  } catch (error) {
    loginError.value = error.message;
  } finally {
    loginLoading.value = false;
  }
}

function logout() {
  auth.logout();
  loginVisible.value = true;
  router.push("/dashboard");
}

function reloadPage() {
  window.location.reload();
}

onMounted(() => {
  window.addEventListener("sales-ai-auth-expired", handleAuthExpired);
});

onBeforeUnmount(() => {
  window.removeEventListener("sales-ai-auth-expired", handleAuthExpired);
});
</script>
