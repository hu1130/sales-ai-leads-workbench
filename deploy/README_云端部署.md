# 销售 AI 系统云端部署说明

推荐当前阶段使用一台 Linux 云服务器部署：

- Nginx：负责前端页面和 `/api` 代理
- FastAPI：后端服务
- SQLite：先用 Docker volume 保存数据
- uploads：用 Docker volume 保存上传文件

## 1. 服务器要求

最低建议：

```text
2 核 CPU
4 GB 内存
40 GB 磁盘
Ubuntu 22.04 / Debian 12 / CentOS Stream
```

安全组开放：

```text
80
443 后续配置 HTTPS 时使用
22 仅管理员 SSH
```

## 2. 安装 Docker

在服务器安装 Docker 和 Docker Compose。安装完成后确认：

```bash
docker --version
docker compose version
```

## 3. 上传代码

把整个项目目录上传到服务器，例如：

```text
/opt/sales-ai
```

目录里需要包含：

```text
deploy/
outputs/sales_ai_frontend/
work/sales_ai_backend/
```

## 4. 配置生产环境变量

进入部署目录：

```bash
cd /opt/sales-ai/deploy
cp .env.prod.example .env.prod
```

编辑 `.env.prod`：

```bash
nano .env.prod
```

必须修改：

```text
JWT_SECRET_KEY=改成一串很长的随机字符串
DEFAULT_ADMIN_PASSWORD=改成正式管理员密码
```

如果要用 AI：

```text
DEEPSEEK_API_KEY=你的 DeepSeek Key
DASHSCOPE_API_KEY=你的阿里云百炼 Key
```

## 5. 启动

```bash
cd /opt/sales-ai/deploy
docker compose up -d --build
```

查看状态：

```bash
docker compose ps
docker compose logs -f backend
```

访问：

```text
http://服务器公网IP
```

登录：

```text
账号：admin
密码：.env.prod 里的 DEFAULT_ADMIN_PASSWORD
```

## 6. 录音工具连接云端

同事电脑上的录音工具不用放服务器。它仍然在本地电脑运行，只需要把后端地址改成云端：

```powershell
$env:ENABLE_SALES_AI_UPLOAD="1"
$env:SALES_AI_BASE_URL="http://服务器公网IP"
$env:SALES_AI_USERNAME="admin"
$env:SALES_AI_PASSWORD="你的管理员密码"
$env:ENABLE_WAV_CONVERT="0"
python -m app.pipeline
```

后续配置域名后，把 `SALES_AI_BASE_URL` 改成：

```text
https://你的域名
```

## 7. 更新代码

上传新代码后执行：

```bash
cd /opt/sales-ai/deploy
docker compose up -d --build
```

## 8. 备份数据

当前数据在 Docker volume：

```text
sales_ai_data
sales_ai_uploads
```

建议每天备份：

- `/app/data/sales_ai.db`
- `/app/uploads`

正式多人长期使用时，建议把 SQLite 升级到 PostgreSQL/MySQL。

## 9. HTTPS

正式给销售使用时必须配置域名和 HTTPS。

可选方式：

- 宝塔面板配置 Nginx + SSL
- 服务器 Nginx + Certbot
- 云厂商负载均衡 SSL

HTTPS 配置好后，前端和后端同域访问，不需要再手动填写后端地址。
