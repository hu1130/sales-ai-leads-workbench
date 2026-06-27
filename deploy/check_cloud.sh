#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${1:-http://127.0.0.1}"

echo "Checking Sales AI cloud deployment: ${BASE_URL}"

echo "1) Docker services"
docker compose ps

echo
echo "2) Health endpoint"
curl -fsS "${BASE_URL%/}/health"
echo

echo
echo "3) Frontend index"
curl -fsS "${BASE_URL%/}/index.html" >/dev/null
echo "Frontend OK"

echo
echo "4) Backend logs tail"
docker compose logs --tail=40 backend

echo
echo "Sales AI cloud deployment check finished."
