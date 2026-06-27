# 销售 AI 线索工作台 Vue 版前端

这是新的 Vue 3 + Element Plus 前端，旧版静态前端仍保留在 `outputs/sales_ai_frontend`。

## 本地启动

先启动后端：

```powershell
cd C:\Users\HYF05\Documents\Codex\2026-06-22\ai\work\sales_ai_backend
..\..\.venv\Scripts\python.exe run_server.py
```

再启动 Vue 前端：

```powershell
cd C:\Users\HYF05\Documents\Codex\2026-06-22\ai\outputs\sales_ai_frontend_vue
npm install
npm run dev
```

浏览器打开：

```text
http://127.0.0.1:5173
```

默认登录：

```text
账号：admin
密码：admin123
```

## 已接入页面

- 今日工作台
- 客户池
- 资料处理
- 线索分配
- 团队看板
- 话术库
- 销售账号

## 说明

开发模式下前端会连接 `http://127.0.0.1:8100`，避免和其他本地项目抢 8000 端口。
