import axios from "axios";

const http = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || "",
  timeout: 60000
});

http.interceptors.request.use((config) => {
  const token = localStorage.getItem("sales_ai_token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

http.interceptors.response.use(
  (response) => response.data,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem("sales_ai_token");
      localStorage.removeItem("sales_ai_user");
      window.dispatchEvent(new CustomEvent("sales-ai-auth-expired"));
      return Promise.reject(new Error("登录已失效，请重新登录"));
    }

    const detail = error.response?.data?.detail;
    const networkMessage = error.code === "ERR_NETWORK" ? "无法连接后端服务，请确认 8100 后端已启动" : "";
    const message = Array.isArray(detail)
      ? detail.map((item) => item.msg).join("; ")
      : detail || networkMessage || error.message || "请求失败";

    return Promise.reject(new Error(message));
  }
);

export default http;

export function downloadUrl(path) {
  return `${path}?t=${Date.now()}`;
}
