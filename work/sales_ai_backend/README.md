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
