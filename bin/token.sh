#!/usr/bin/env bash
# feishu-sync/scripts/token.sh — 取 tenant_access_token
#
# 输出 token 到 stdout；失败退出码非 0。
# 用法：TOKEN=$(bash token.sh)
set -euo pipefail

: "${FEISHU_APP_ID:?FEISHU_APP_ID 必须设置}"
: "${FEISHU_APP_SECRET:?FEISHU_APP_SECRET 必须设置}"

HOST="${FEISHU_HOST:-open.feishu.cn}"

RES=$(curl -sS -X POST "https://${HOST}/open-apis/auth/v3/tenant_access_token/internal" \
  -H "Content-Type: application/json" \
  -d "{\"app_id\":\"${FEISHU_APP_ID}\",\"app_secret\":\"${FEISHU_APP_SECRET}\"}")

TOKEN=$(echo "$RES" | python3 -c "
import sys, json
d = json.load(sys.stdin)
if d.get('code') != 0:
    print(f'[AUTH_FAIL] code={d.get(\"code\")} msg={d.get(\"msg\")}', file=sys.stderr)
    sys.exit(1)
print(d.get('tenant_access_token',''))
")

if [ -z "$TOKEN" ]; then
  echo "[AUTH_FAIL] 响应里没有 tenant_access_token：$RES" >&2
  exit 1
fi

echo "$TOKEN"
