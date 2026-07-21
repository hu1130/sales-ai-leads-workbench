# 销售 AI 系统云端上线清单

## 必须上传到服务器

```text
deploy/
outputs/sales_ai_frontend_vue/
work/sales_ai_backend/app/
work/sales_ai_backend/Dockerfile
work/sales_ai_backend/requirements.txt
.dockerignore
```

## 不要上传到服务器仓库或交付包

```text
deploy/.env.prod
work/sales_ai_backend/.env
work/sales_ai_backend/sales_ai.db
work/sales_ai_backend/uploads/
work/sales_ai_backend/.venv/
outputs/sales_ai_frontend_vue/node_modules/
outputs/sales_ai_frontend_vue/dist/
真实客户截图
真实通话录音
API Key
```

## 服务器首次启动

```bash
cd /opt/sales-ai/deploy
cp .env.prod.example .env.prod
nano .env.prod
docker compose up -d --build
```

## 服务器日常检查

```bash
cd /opt/sales-ai/deploy
bash check_cloud.sh http://服务器公网IP
```

如果使用默认 `WEB_PORT=8081`，检查地址应改成：

```bash
bash check_cloud.sh http://服务器公网IP:8081
```

## 更新代码

```bash
cd /opt/sales-ai/deploy
docker compose up -d --build
docker compose ps
```

## 数据备份

当前生产部署默认使用 MySQL + Docker volume：

```text
sales_ai_mysql
sales_ai_uploads
```

建议每天备份：

```bash
cd /opt/sales-ai/deploy
bash backup_mysql.sh
```

更详细说明见：

```text
deploy/README_生产部署.md
```
