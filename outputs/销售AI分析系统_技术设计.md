# 销售 AI 分析系统技术设计

## 1. 技术选型

### 1.1 后端

- 框架：FastAPI
- 接口风格：REST API
- 鉴权：JWT
- 数据库：PostgreSQL
- 文件存储：第一版可本地存储，后续可切换对象存储
- 异步任务：第一版可用 FastAPI BackgroundTasks，后续可升级 Celery/RQ

### 1.2 前端

- 官网后台：原生 HTML / CSS / JavaScript
- App：后续可使用 Flutter、React Native 或原生开发
- 接口调用：统一调用 FastAPI REST API

### 1.3 AI 服务

- 文本总结和意向判断：DeepSeek
- 图片识别和图片理解：阿里云百炼/Qwen
- 语音转文字：讯飞语音转写或阿里云语音识别

## 2. 系统模块

系统后端建议拆分为：

- 用户与登录模块
- 客户模块
- 文件上传模块
- AI 分析模块
- 跟进记录模块
- 电话录音接入模块
- 后台统计模块

## 3. 数据库表设计

### 3.1 users 用户表

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | bigint | 用户 ID |
| username | varchar | 登录账号 |
| password_hash | varchar | 密码哈希 |
| name | varchar | 姓名 |
| phone | varchar | 手机号 |
| role | varchar | 角色：sales/admin |
| status | varchar | 状态：active/disabled |
| created_at | datetime | 创建时间 |
| updated_at | datetime | 更新时间 |

### 3.2 customers 客户表

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | bigint | 客户 ID |
| owner_id | bigint | 所属销售 ID |
| name | varchar | 客户姓名 |
| phone | varchar | 客户电话 |
| address | varchar | 地址 |
| source | varchar | 来源 |
| intent_level | varchar | 意向等级 |
| intent_score | int | 意向评分 |
| demand_summary | text | 客户需求摘要 |
| concerns | text | 客户疑问/异议 |
| product_interest | text | 关注产品 |
| budget | varchar | 预算 |
| purchase_time | varchar | 预计购买时间 |
| next_action | text | 下一步建议 |
| last_followup_at | datetime | 最近跟进时间 |
| created_at | datetime | 创建时间 |
| updated_at | datetime | 更新时间 |

### 3.3 upload_records 上传记录表

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | bigint | 上传记录 ID |
| customer_id | bigint | 客户 ID |
| uploader_id | bigint | 上传人 ID |
| file_type | varchar | 文件类型：image/audio/document |
| file_name | varchar | 原始文件名 |
| file_path | varchar | 文件地址 |
| status | varchar | 状态：pending/processing/completed/failed |
| error_message | text | 失败原因 |
| created_at | datetime | 上传时间 |
| updated_at | datetime | 更新时间 |

### 3.4 ai_analysis_results AI 分析结果表

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | bigint | 分析结果 ID |
| upload_record_id | bigint | 上传记录 ID |
| customer_id | bigint | 客户 ID |
| raw_text | text | 原始识别文字 |
| summary | text | 内容摘要 |
| customer_name | varchar | AI 识别客户姓名 |
| customer_phone | varchar | AI 识别客户电话 |
| customer_address | varchar | AI 识别地址 |
| customer_needs | text | 客户需求 |
| customer_questions | text | 客户疑问 |
| customer_objections | text | 客户异议 |
| product_interest | text | 关注产品 |
| budget | varchar | 价格/预算 |
| purchase_time | varchar | 购买时间 |
| intent_level | varchar | 意向等级 |
| intent_score | int | 意向评分 |
| intent_reason | text | 判断理由 |
| evidence | text | 关键证据 |
| next_action | text | 下一步跟进建议 |
| sales_script | text | 推荐销售话术 |
| model_name | varchar | 使用模型 |
| created_at | datetime | 创建时间 |

### 3.5 followups 跟进记录表

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | bigint | 跟进 ID |
| customer_id | bigint | 客户 ID |
| user_id | bigint | 跟进人 ID |
| content | text | 跟进内容 |
| next_followup_at | datetime | 下次跟进时间 |
| created_at | datetime | 创建时间 |

### 3.6 call_recordings 通话录音表

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | bigint | 通话录音 ID |
| customer_id | bigint | 客户 ID |
| sales_id | bigint | 销售 ID |
| caller_phone | varchar | 主叫号码 |
| callee_phone | varchar | 被叫号码 |
| started_at | datetime | 通话开始时间 |
| ended_at | datetime | 通话结束时间 |
| duration_seconds | int | 通话时长 |
| recording_path | varchar | 录音地址 |
| upload_record_id | bigint | 对应上传记录 |
| created_at | datetime | 创建时间 |

## 4. REST API 设计

### 4.1 登录

```http
POST /api/auth/login
```

请求：

```json
{
  "username": "sales01",
  "password": "123456"
}
```

响应：

```json
{
  "access_token": "jwt-token",
  "token_type": "bearer",
  "user": {
    "id": 1,
    "name": "销售一",
    "role": "sales"
  }
}
```

### 4.2 上传文件

```http
POST /api/uploads
```

表单字段：

- file：文件
- customer_id：可选
- customer_phone：可选
- customer_name：可选
- note：可选

响应：

```json
{
  "id": 1001,
  "status": "pending",
  "message": "上传成功，正在分析"
}
```

### 4.3 查看上传记录

```http
GET /api/uploads/{upload_id}
```

响应：

```json
{
  "id": 1001,
  "file_type": "audio",
  "status": "completed",
  "customer_id": 2001,
  "analysis": {
    "summary": "客户询问价格和交付时间",
    "intent_level": "高意向",
    "intent_score": 86,
    "intent_reason": "客户主动询价并询问安装时间",
    "next_action": "建议 24 小时内电话跟进"
  }
}
```

### 4.4 客户列表

```http
GET /api/customers
```

查询参数：

- keyword
- owner_id
- intent_level
- start_date
- end_date
- page
- page_size

### 4.5 客户详情

```http
GET /api/customers/{customer_id}
```

返回：

- 客户基础信息
- 当前意向等级
- 最近 AI 分析摘要
- 历史上传记录
- 跟进记录

### 4.6 客户历史记录

```http
GET /api/customers/{customer_id}/records
```

返回该客户所有上传记录和 AI 分析结果。

### 4.7 添加跟进记录

```http
POST /api/customers/{customer_id}/followups
```

请求：

```json
{
  "content": "已电话联系，客户希望明天下午再确认价格。",
  "next_followup_at": "2026-06-16 15:00:00"
}
```

### 4.8 高意向客户

```http
GET /api/leads/high-intent
```

默认返回意向等级为高意向，或意向评分大于等于 80 的客户。

### 4.9 后台统计

```http
GET /api/dashboard/stats
```

返回：

- 今日上传数量
- 今日新增客户
- 高意向客户数量
- 各销售上传数量
- 各意向等级分布

### 4.10 电话录音上传

```http
POST /api/call-recordings
```

表单字段：

- file：录音文件
- sales_id：销售 ID
- caller_phone：主叫号码
- callee_phone：被叫号码
- started_at：通话开始时间
- ended_at：通话结束时间
- duration_seconds：通话时长

响应：

```json
{
  "recording_id": 3001,
  "upload_record_id": 1002,
  "status": "pending"
}
```

## 5. AI 分析输出 JSON 格式

DeepSeek 最终输出建议统一成 JSON：

```json
{
  "summary": "客户询问产品价格和交付时间，表现出较强购买意向。",
  "customer_name": "未提及",
  "customer_phone": "13800000000",
  "customer_address": "未提及",
  "customer_needs": "希望了解产品价格和安装周期",
  "customer_questions": "是否有优惠，什么时候可以安装",
  "customer_objections": "担心价格偏高",
  "product_interest": "某产品",
  "budget": "未提及",
  "purchase_time": "近期",
  "intent_level": "高意向",
  "intent_score": 86,
  "intent_reason": "客户主动询价，并询问安装和优惠，说明已有明确购买考虑。",
  "evidence": "客户提到：价格多少、什么时候能安装、有没有优惠。",
  "next_action": "建议销售 24 小时内电话跟进，重点说明价格方案、优惠政策和交付时间。",
  "sales_script": "您好，我看到您比较关注价格和安装时间，我这边可以根据您的情况给您确认一个更合适的方案。"
}
```

## 6. AI 防乱说规则

所有 AI 提示词必须包含以下规则：

1. 只能根据输入内容判断，不能猜测。
2. 没有出现的信息统一写“未提及”。
3. 证据不足时，购买意向写“无法判断”。
4. 不允许编造手机号、姓名、价格、地址、购买时间。
5. 意向评分必须和证据一致。
6. 输出必须是合法 JSON，方便后端保存。

## 7. 后端处理流程

```text
POST /api/uploads
↓
保存文件
↓
创建 upload_records
↓
后台任务开始处理
↓
判断文件类型
↓
图片：调用 Qwen/阿里云百炼
录音：调用讯飞/阿里云语音识别
↓
得到 raw_text
↓
调用 DeepSeek 进行结构化分析
↓
保存 ai_analysis_results
↓
匹配或创建 customers
↓
更新客户当前意向和摘要
↓
上传记录状态改为 completed
```

## 8. 第一版开发顺序

建议开发顺序：

1. 搭建 FastAPI 项目结构。
2. 建立数据库模型。
3. 实现登录和 JWT。
4. 实现文件上传和上传记录。
5. 实现 AI 分析任务框架。
6. 接入语音转文字。
7. 接入图片识别。
8. 接入 DeepSeek 分析。
9. 实现客户自动归档。
10. 实现客户列表、客户详情、上传记录接口。
11. 实现官网后台页面。
12. 实现 App 上传和拨号。
13. 接入电话系统录音上传。

## 9. 环境变量建议

```text
DATABASE_URL=
JWT_SECRET_KEY=
DEEPSEEK_API_KEY=
QWEN_API_KEY=
ASR_PROVIDER=
ASR_API_KEY=
UPLOAD_DIR=
```

## 10. 后续升级方向

后续可以增加：

- 更完整的权限系统
- 销售团队组织架构
- 网页端外呼
- 通话录音自动质检
- 销售话术评分
- 客户跟进提醒
- 订单转化统计
- CRM 对接
- 私有化部署

