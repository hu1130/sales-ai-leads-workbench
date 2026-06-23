# 销售 AI 系统交付包

打包日期：2026-06-22

## 已包含

- FastAPI 销售 AI 后端
- 原生 HTML/CSS/JavaScript 工作台
- 产品落地页 `outputs/sales_ai_frontend/landing.html`
- 手机录音同步与实时 watcher
- Docker FunASR 本地转写配置
- DeepSeek 意向分析与客户归档
- 图片 OCR、原图预览与录音播放
- 一键外拨 `tel:` 功能
- Syncthing + Windows 登录实时启动脚本
- Linux/Docker 云端部署配置
- 脱敏图片、文本和录音测试数据

## 安全排除项

交付包未包含以下本机数据：

- `.env` 与 API Key
- 客户数据库与数据库备份
- 真实客户手机号、录音、图片和上传文件
- Python `.venv`
- Docker 镜像、缓存和临时文件

## 首次运行

1. 安装 Python。
2. 在后端目录将 `.env.example` 复制为 `.env`，填写 DeepSeek/DashScope 等配置。
3. 双击根目录 `启动销售AI系统.bat` 启动普通版本。
4. 本地实时录音环境完成 Docker、Syncthing 配置后，双击 `启动实时销售AI系统.bat`。

默认测试登录：

```text
admin / admin123
```

正式使用前必须修改默认密码与 JWT 密钥。

## 前端入口

- 产品落地页：`outputs/sales_ai_frontend/landing.html`
- 销售工作台：`outputs/sales_ai_frontend/index.html`

## 说明

FunASR Docker 镜像体积较大，未放入压缩包。请在录音项目目录执行：

```powershell
docker build -f Dockerfile.funasr -t sales-ai-funasr:local .
```
