# 销售 AI 线索系统：迭代 PRD 与项目知识库

版本：v0.4  
日期：2026-06-17  
状态：MVP 主流程已跑通，正在接入 OCR 与录音链路

## 1. 项目目标

建设一个给销售和老板使用的 AI 线索管理系统。销售把微信截图、客户资料、电话录音等沟通材料上传或自动同步进系统，系统自动识别内容、整理客户信息、判断购买意向，并生成下一步跟进建议。

最终目标：

- 销售不用手动写大量跟进记录。
- 老板能看到每个销售上传了什么、哪些客户最值得跟进。
- 电话录音、微信截图、文档资料都能沉淀到客户档案。
- AI 自动判断客户购买意向：高意向、中意向、低意向、暂无意向、无法判断。

## 2. 当前系统组成

### 2.1 销售 AI 后端

路径：

```text
work/sales_ai_backend
```

技术：

- FastAPI
- SQLite
- JWT 登录
- REST API

已实现：

- 登录系统
- 管理员创建销售账号
- 客户池
- 上传记录
- AI 分析结果
- 跟进记录
- 电话录音记录
- 意向线索分层
- Dashboard 统计
- DeepSeek 文本分析入口
- DashScope/Qwen-VL 图片 OCR 配置入口
- 录音转文字 ASR 配置入口

默认账号：

```text
admin / admin123
```

### 2.2 前端工作台

路径：

```text
outputs/sales_ai_frontend
```

技术：

- 原生 HTML
- CSS
- JavaScript
- REST API

已实现页面：

- 今日销售工作台
- 客户池
- 资料分析
- 意向线索
- 销售账号
- 登录弹窗
- 上传资料弹窗
- 客户详情弹窗

工作台目前展示：

- 高意向
- 中意向
- 低意向
- 暂无意向
- 无法判断
- 优先跟进客户
- AI 分析进度

### 2.3 同事录音工具

路径：

```text
work/Automatic-Phone-Recording-main
```

用途：

手机自动录音同步到电脑本地后，该工具负责扫描本地录音目录，并把录音自动上传到销售 AI 后端。

已实现：

- 从 `data/inbox` 导入录音
- 从文件名解析手机号和通话时间
- 写入本地 SQLite
- 防重复上传
- 自动 POST 到销售 AI 后端 `/api/call-recordings`
- 可选 FFmpeg 转 WAV
- 预留 FunASR 转文字

当前建议运行模式：

```text
ENABLE_SALES_AI_UPLOAD=1
ENABLE_WAV_CONVERT=0
```

因为当前电脑还未安装 FFmpeg/FunASR，先把原始录音上传进主系统。

## 3. 当前已跑通的主流程

### 3.1 文档上传分析

```text
销售上传 txt/docx/csv
↓
后端读取文字
↓
DeepSeek 或本地规则分析
↓
生成客户
↓
生成意向等级和下一步建议
```

### 3.2 图片上传分析

```text
销售上传微信截图/图片
↓
Qwen-VL OCR 识别图片文字
↓
DeepSeek 或本地规则判断意向
↓
生成客户档案和跟进记录
```

说明：需要在 `.env` 填写 `DASHSCOPE_API_KEY`。

### 3.3 电话录音自动进入系统

```text
手机自动录音
↓
录音同步到电脑 data/inbox
↓
同事录音工具 pipeline 扫描
↓
自动上传到销售 AI 后端
↓
后端生成通话记录和跟进记录
```

已用真实录音测试：

- 成功导入 3 条 `.m4a`
- 成功上传到销售 AI 后端
- 后端生成上传记录 ID：16、17、18
- 后端生成通话记录 ID：2、3、4
- 自动解析手机号：15800000000（脱敏示例）

## 4. 当前功能清单

### 4.1 登录和权限

- 管理员登录
- 销售账号创建
- JWT 鉴权
- 管理员可查看全部数据
- 销售后续可限制只看自己的客户

### 4.2 客户管理

- 客户自动生成
- 手机号匹配客户
- 客户姓名、电话、需求、异议、预算、购买时间
- 客户详情页
- 历史资料记录
- 跟进记录时间线

### 4.3 AI 意向判断

意向等级：

- 高意向
- 中意向
- 低意向
- 暂无意向
- 无法判断

输出内容：

- 内容摘要
- 客户需求
- 客户问题
- 客户异议
- 关注产品
- 预算
- 购买时间
- 判断理由
- 关键证据
- 下一步建议
- 推荐话术

### 4.4 资料上传

支持：

- 图片
- 录音
- 文档
- txt
- docx
- csv
- pdf 占位

### 4.5 电话录音

已实现：

- 手动上传录音
- 同事工具自动上传录音
- 录音绑定客户
- 生成通话跟进记录

待实现：

- 真正转文字
- 录音摘要和客户异议提取

已补充：

- FunASR 转写结果回传接口
- 转写回传后自动重新分析
- 自动回填通话跟进记录
- 录音处理状态与上传状态分离

## 5. 当前技术债和风险

### 5.1 录音转文字未完成

当前录音能进入系统，但还不能真正听懂内容。

方案 A：

- 安装 FFmpeg
- 安装 FunASR
- 本地转写

方案 B：

- 接阿里云语音识别
- 需要本地录音上传 OSS 或变成可访问 URL

当前建议先走方案 A，把本地转写跑通。

### 5.2 图片 OCR 需要真实 Key 测试

代码已接入 Qwen-VL OCR，但需要填写：

```text
DASHSCOPE_API_KEY=
```

然后用真实微信截图测试识别效果。

### 5.3 前端仍需继续专业化

当前前端已经从说明页改成工作台，但客户详情页仍可以继续升级：

- 右侧抽屉式客户详情
- 更清楚的 AI 判断依据
- 跟进时间线
- 一键拨号按钮
- 上传微信截图/上传录音分区更强

### 5.4 数据库仍是 SQLite

MVP 阶段可以用。后续多人正式使用时建议迁移：

- PostgreSQL
- MySQL
- SQL Server

## 6. 下一阶段迭代路线

### v0.5：录音转文字

目标：

- 安装并接入 FFmpeg
- 安装并接入 FunASR
- 录音上传后自动转文字
- 转写文本进入 AI 分析
- 跟进记录自动更新为通话摘要

验收标准：

- 上传一条真实电话录音
- 系统能看到转写文本
- 客户详情显示通话摘要
- AI 能根据录音判断客户意向

### v0.6：OCR 真实业务测试

目标：

- 配置 DashScope Key
- 上传真实微信聊天截图
- OCR 识别聊天内容
- DeepSeek 分析客户意向

验收标准：

- 微信截图文字可读
- 手机号/姓名能提取则自动归档
- 高/中/低意向判断合理

### v0.7：老板看板

目标：

- 每个销售上传数量
- 每个销售高意向客户数量
- 今日新增客户
- 未跟进客户
- 销售排行榜

### v0.8：拨号和录音闭环

目标：

- 前端一键拨号
- 通话录音自动回传
- 自动转文字
- 自动生成跟进

## 7. 一键启动

根目录已有：

```text
启动销售AI系统.bat
```

同事解压后双击即可：

1. 创建后端虚拟环境
2. 安装后端依赖
3. 创建 `.env`
4. 启动 FastAPI 后端
5. 打开前端页面

默认访问：

```text
http://127.0.0.1:8000
```

登录：

```text
admin / admin123
```

## 8. 交接注意事项

- 不要把真实 `.env`、数据库、上传录音、客户数据打包给外部。
- 测试包只包含代码和示例文档。
- 同事如果要测试录音自动上传，先把录音放到：

```text
work/Automatic-Phone-Recording-main/data/inbox
```

然后运行：

```powershell
cd work/Automatic-Phone-Recording-main
$env:ENABLE_SALES_AI_UPLOAD="1"
$env:SALES_AI_BASE_URL="http://127.0.0.1:8000"
$env:SALES_AI_USERNAME="admin"
$env:SALES_AI_PASSWORD="admin123"
$env:ENABLE_WAV_CONVERT="0"
python -m app.pipeline
```

## 9. 当前关键文件

后端：

```text
work/sales_ai_backend/app/services/ai_service.py
work/sales_ai_backend/app/api/routes/uploads.py
work/sales_ai_backend/app/api/routes/call_recordings.py
work/sales_ai_backend/app/api/routes/leads.py
```

前端：

```text
outputs/sales_ai_frontend/index.html
outputs/sales_ai_frontend/app.js
outputs/sales_ai_frontend/styles.css
```

录音工具：

```text
work/Automatic-Phone-Recording-main/app/pipeline.py
work/Automatic-Phone-Recording-main/app/local_import.py
work/Automatic-Phone-Recording-main/app/recording_metadata.py
work/Automatic-Phone-Recording-main/app/sales_ai_upload.py
```

测试：

```text
work/sales_ai_backend/tests/run_full_tests.py
work/Automatic-Phone-Recording-main/tests/test_sales_ai_upload.py
```
