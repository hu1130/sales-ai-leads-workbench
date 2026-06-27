import { defineStore } from "pinia";
import http from "../api/http";

export const useAuthStore = defineStore("auth", {
  state: () => ({
    token: localStorage.getItem("sales_ai_token") || "",
    user: JSON.parse(localStorage.getItem("sales_ai_user") || "null")
  }),
  getters: {
    isLogin: (state) => Boolean(state.token),
    isAdmin: (state) => state.user?.role === "admin"
  },
  actions: {
    async login(form) {
      const data = await http.post("/api/auth/login", form);
      this.token = data.access_token;
      this.user = data.user;
      localStorage.setItem("sales_ai_token", data.access_token);
      localStorage.setItem("sales_ai_user", JSON.stringify(data.user));
    },
    logout() {
      this.token = "";
      this.user = null;
      localStorage.removeItem("sales_ai_token");
      localStorage.removeItem("sales_ai_user");
    }
  }
});
