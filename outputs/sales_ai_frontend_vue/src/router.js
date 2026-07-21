import { createRouter, createWebHashHistory } from "vue-router";
import { useAuthStore } from "./stores/auth";

const routes = [
  { path: "/", redirect: "/dashboard" },
  { path: "/dashboard", name: "dashboard", component: () => import("./views/Dashboard.vue"), meta: { title: "今日工作台", icon: "House" } },
  { path: "/customers", name: "customers", component: () => import("./views/Customers.vue"), meta: { title: "客户池", icon: "User" } },
  { path: "/uploads", name: "uploads", component: () => import("./views/Uploads.vue"), meta: { title: "资料处理", icon: "UploadFilled" } },
  { path: "/call-center/dashboard", redirect: "/call-center/settings" },
  { path: "/call-center/campaigns", name: "callCampaigns", component: () => import("./views/CallCampaigns.vue"), meta: { title: "外呼任务", icon: "Tickets", adminOnly: true } },
  { path: "/call-center/campaigns/:id", name: "callCampaignDetail", component: () => import("./views/CallCampaignDetail.vue"), meta: { title: "任务详情", icon: "Tickets", hidden: true } },
  { path: "/call-center/my-tasks", name: "myCallTasks", component: () => import("./views/MyCallTasks.vue"), meta: { title: "我的外呼", icon: "PhoneFilled" } },
  { path: "/call-center/records", name: "callRecords", component: () => import("./views/CallRecords.vue"), meta: { title: "通话记录", icon: "Memo" } },
  { path: "/assignment", name: "assignment", component: () => import("./views/Assignment.vue"), meta: { title: "线索分配", icon: "Switch" } },
  { path: "/team", name: "team", component: () => import("./views/Team.vue"), meta: { title: "团队看板", icon: "DataAnalysis" } },
  { path: "/scripts", name: "scripts", component: () => import("./views/Scripts.vue"), meta: { title: "话术库", icon: "ChatLineRound" } },
  { path: "/users", name: "users", component: () => import("./views/Users.vue"), meta: { title: "销售账号", icon: "Avatar" } },
  { path: "/call-center/settings", name: "callSettings", component: () => import("./views/CallDashboard.vue"), meta: { title: "外呼配置", icon: "Setting", adminOnly: true } }
];

const router = createRouter({
  history: createWebHashHistory(),
  routes
});

const ADMIN_ROUTE_NAMES = new Set(["assignment", "team", "users", "callCampaigns", "callCampaignDetail", "callSettings"]);

router.beforeEach((to) => {
  const auth = useAuthStore();
  if ((to.meta.adminOnly || ADMIN_ROUTE_NAMES.has(to.name)) && !auth.isAdmin) {
    return { path: "/dashboard" };
  }
  return true;
});

export default router;

export const navRoutes = routes.filter((route) => route.name);
