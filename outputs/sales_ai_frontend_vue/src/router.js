import { createRouter, createWebHashHistory } from "vue-router";

const routes = [
  { path: "/", redirect: "/dashboard" },
  { path: "/dashboard", name: "dashboard", component: () => import("./views/Dashboard.vue"), meta: { title: "今日工作台", icon: "House" } },
  { path: "/customers", name: "customers", component: () => import("./views/Customers.vue"), meta: { title: "客户池", icon: "User" } },
  { path: "/uploads", name: "uploads", component: () => import("./views/Uploads.vue"), meta: { title: "资料处理", icon: "UploadFilled" } },
  { path: "/assignment", name: "assignment", component: () => import("./views/Assignment.vue"), meta: { title: "线索分配", icon: "Switch" } },
  { path: "/team", name: "team", component: () => import("./views/Team.vue"), meta: { title: "团队看板", icon: "DataAnalysis" } },
  { path: "/scripts", name: "scripts", component: () => import("./views/Scripts.vue"), meta: { title: "话术库", icon: "ChatLineRound" } },
  { path: "/users", name: "users", component: () => import("./views/Users.vue"), meta: { title: "销售账号", icon: "Avatar" } }
];

export default createRouter({
  history: createWebHashHistory(),
  routes
});

export const navRoutes = routes.filter((route) => route.name);
