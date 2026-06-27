# 销售 AI 系统云端上线清单

## 必须上传到服务器

```text
deploy/
outputs/sales_ai_frontend/
work/sales_ai_backend/app/
work/sales_ai_backend/Dockerfile
work/sales_ai_backend/requirements.txt
```

## 不要上传到服务器仓库或交付包

```text
work/sales_ai_backend/.env
work/sales_ai_backend/sales_ai.db
work/sales_ai_backend/uploads/
work/sales_ai_backend/.venv/
work/Automatic-Phone-Recording-main/.venv/
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

## 更新代码

```bash
cd /opt/sales-ai/deploy
docker compose up -d --build
docker compose ps
```

## 数据备份

当前默认使用 Docker volume：

```text
sales_ai_data
sales_ai_uploads
```

建议每天备份：

```text
/app/data/sales_ai.db
/app/uploads
```
