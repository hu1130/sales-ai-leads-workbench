# 销售 AI 系统生产部署说明

这一步解决的是“不能靠个人电脑开着跑”的问题。部署后，系统由 Docker 常驻运行：

- `mysql`: 生产数据库，保存客户、资料、AI 分析、外呼任务等业务数据
- `backend`: FastAPI 后端，固定容器内端口 `8100`
- `web`: Vue 前端 + Nginx，公网访问入口，默认端口 `8081`
- `sales_ai_uploads`: Docker volume，保存截图、录音、文档原文件

## MySQL 可以用吗

可以。这个项目的数据结构主要是客户、上传记录、分析结果、跟进记录、外呼任务，MySQL 完全适合。

我没有把你绑死在 PostgreSQL 上。当前生产部署默认用 MySQL，因为它更常见、更容易买云数据库、更方便后续找人维护。PostgreSQL 也支持，只要把 `DATABASE_URL` 换成 PostgreSQL，并在 Compose 里换数据库服务即可。

## 第一次上线

在服务器上进入项目目录：

```bash
cd /opt/sales-ai/deploy
cp .env.prod.example .env.prod
nano .env.prod
```

至少修改这些值：

```text
MYSQL_PASSWORD
MYSQL_ROOT_PASSWORD
DATABASE_URL 里的 MySQL 密码
JWT_SECRET_KEY
DEFAULT_ADMIN_PASSWORD
DEEPSEEK_API_KEY
DASHSCOPE_API_KEY
```

启动：

```bash
docker compose up -d --build
docker compose ps
```

检查：

```bash
curl http://127.0.0.1/health
bash check_cloud.sh http://你的服务器IP
```

浏览器访问：

```text
http://你的服务器IP:8081
```

## 日常更新

```bash
cd /opt/sales-ai/deploy
docker compose up -d --build
docker compose ps
```

## 备份

每天至少备份一次数据库和上传文件：

```bash
cd /opt/sales-ai/deploy
bash backup_mysql.sh
```

备份会生成：

```text
deploy/backups/sales_ai_mysql_时间.sql
deploy/backups/sales_ai_uploads_时间.tar.gz
```

## 重要提醒

- `deploy/.env.prod` 不能提交到 GitHub，里面有数据库密码和 API Key。
- 线上不要继续使用默认 `admin123`。
- 如果要绑定域名和 HTTPS，下一步在 Nginx 前面接宝塔、1Panel、Caddy 或证书版 Nginx。
- 如果服务器 `80/443` 已经被其他项目占用，先保持 `WEB_PORT=8081`，不要直接停旧项目。
- 旧的本地 SQLite 数据迁移到 MySQL 是单独步骤，部署前要先确认是否需要迁移历史数据。
