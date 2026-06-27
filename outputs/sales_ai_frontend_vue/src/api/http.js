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
    const detail = error.response?.data?.detail;
    const message = Array.isArray(detail)
      ? detail.map((item) => item.msg).join("; ")
      : detail || error.message || "请求失败";

    return Promise.reject(new Error(message));
  }
);

export default http;

export function downloadUrl(path) {
  return `${path}?t=${Date.now()}`;
}
