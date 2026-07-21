#!/usr/bin/env bash
set -euo pipefail

BACKUP_DIR="${1:-./backups}"
STAMP="$(date +%Y%m%d_%H%M%S)"

mkdir -p "${BACKUP_DIR}"

echo "Backing up MySQL database..."
docker compose exec -T mysql sh -c 'mysqldump -u"$MYSQL_USER" -p"$MYSQL_PASSWORD" "$MYSQL_DATABASE"' \
  > "${BACKUP_DIR}/sales_ai_mysql_${STAMP}.sql"

echo "Backing up uploaded files..."
docker compose exec -T backend tar czf - -C /app/uploads . \
  > "${BACKUP_DIR}/sales_ai_uploads_${STAMP}.tar.gz"

echo "Backup finished:"
echo "${BACKUP_DIR}/sales_ai_mysql_${STAMP}.sql"
echo "${BACKUP_DIR}/sales_ai_uploads_${STAMP}.tar.gz"
