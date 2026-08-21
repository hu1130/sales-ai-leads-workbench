# 销售 AI 分析系统后端

FastAPI 后端第一版骨架，包含登录、客户、上传记录、AI 分析结果、跟进记录和电话录音上传接口。

## 快速启动

```powershell
cd work/sales_ai_backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload --host 0.0.0.0 --port 8100
```

启动后访问：

- API 文档：http://127.0.0.1:8100/docs
- 健康检查：http://127.0.0.1:8100/health

## 平台服务身份

我淘淘 Core 调用 AI 外呼启动接口时使用独立服务 Token，不使用员工管理员登录 JWT：

```env
PLATFORM_SERVICE_TOKEN=通过秘密管理系统注入的长随机值
PLATFORM_TENANT_ID=1
```

Core 侧 `SALES_AI_BACKEND_TOKEN` 与 Provider 侧 `PLATFORM_SERVICE_TOKEN` 使用同一运行时秘密，但不得写入 Git。调用方式：

```http
POST /api/call-campaigns/{campaign_id}/ai-robot/start
Authorization: Bearer <platform-service-token>
```

停止已经持久化的 Provider 外呼任务使用独立幂等命令；员工管理员 JWT 无权调用：

```http
POST /api/ai-robot-calls/{robot_call_id}/stop
Authorization: Bearer <platform-service-token>
Idempotency-Key: AI_CALL_STOP:{call_task_id}
```

首次受理返回 `202/CANCEL_REQUESTED`，同键同载荷重放返回原回执并标记
`replayed=true`；同键不同载荷返回 `409 IDEMPOTENCY_CONFLICT`。`202` 不代表已经
停止，最终状态仍以查单或回调为准。

服务 Token 只能操作 `PLATFORM_TENANT_ID` 对应租户；跨租户 campaign 按不存在处理。轮换 Token 后重启 Provider 和 Core，再通过批准的测试 campaign 验证。

## 默认账号

系统启动时会自动创建管理员账号：

```text
username: admin
password: admin123
```

请上线前修改默认密码。

## 当前状态

已实现：

- JWT 登录
- 管理员创建/修改销售账号
- 用户表
- 客户表
- 上传记录表
- AI 分析结果表
- 跟进记录表
- 电话录音表
- 文件上传
- 异步 AI 分析流程占位
- 客户自动归档基础逻辑
- DeepSeek 文本分析接入入口
- DashScope/Qwen-VL 图片 OCR 接入入口
- 录音转文字 ASR 配置入口

图片识别已经接入 DashScope/Qwen-VL 配置入口；语音识别已经预留配置入口，本地录音文件需要先变成可访问音频地址或上传到 OSS 后，再调用录音文件识别服务。

## 主要接口

登录：

```text
POST /api/auth/login
```

用户管理：

```text
GET /api/users
POST /api/users
PATCH /api/users/{user_id}
```

上传：

```text
POST /api/uploads
GET /api/uploads
GET /api/uploads/{upload_id}
```

客户：

```text
GET /api/customers
GET /api/customers/{customer_id}
GET /api/customers/{customer_id}/records
POST /api/customers/{customer_id}/followups
GET /api/customers/{customer_id}/followups
```

线索：

```text
GET /api/leads?intent_level=高意向
GET /api/leads/high-intent
```

电话录音：

```text
POST /api/call-recordings
POST /api/call-recordings/{recording_id}/transcript
```

录音工具上传完成后，可以把 FunASR 转写文本回传到 transcript 接口。后端会重新执行意向分析并更新自动跟进记录。

后台统计：

```text
GET /api/dashboard/stats
GET /api/dashboard/high-intent
```

AI 状态：

```text
GET /api/ai/deepseek/status
GET /api/ai/recognition/status
POST /api/ai/deepseek/test
```

## DeepSeek 配置

在 `.env` 中填写：

```text
DEEPSEEK_API_KEY=你的 key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash
```

## 图片 OCR 配置

在 `.env` 中填写阿里云百炼/DashScope Key：

```text
DASHSCOPE_API_KEY=你的百炼 key
DASHSCOPE_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
DASHSCOPE_OCR_MODEL=qwen-vl-plus
```

当前图片流程是：

```text
上传微信截图/客户图片
↓
Qwen-VL 识别图片文字
↓
DeepSeek 或本地规则判断购买意向
↓
保存客户、上传记录、AI 分析结果
```

## 录音转文字配置

手机录音同步到电脑后，可以先走本地上传流程。录音文件识别通常需要音频文件有一个可访问 URL，因此后续需要补一个 OSS/文件服务中转。

预留配置：

```text
DASHSCOPE_ASR_MODEL=paraformer-v2
ASR_AUDIO_BASE_URL=
ASR_PROVIDER=dashscope
ASR_API_KEY=
```
