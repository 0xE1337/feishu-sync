#!/usr/bin/env bash
# feishu-sync/scripts/probe.sh — 自检
#
# 用法：
#   bash probe.sh                          # 只检凭证 + token
#   bash probe.sh --wiki <url>             # 再多检一条：wiki 可读性
#   bash probe.sh --doc <url>              # 检 docx 可读
#   bash probe.sh --sheets                 # 检 sheets:spreadsheet scope（创建+删除一份临时表）
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOST="${FEISHU_HOST:-open.feishu.cn}"

WIKI_URL=""
DOC_URL=""
CHECK_SHEETS=0
while [ $# -gt 0 ]; do
  case "$1" in
    --wiki)   WIKI_URL="$2"; shift 2 ;;
    --doc)    DOC_URL="$2"; shift 2 ;;
    --sheets) CHECK_SHEETS=1; shift ;;
    *) echo "未知参数: $1" >&2; exit 2 ;;
  esac
done

pass() { echo "  [✅] $1"; }
fail() { echo "  [❌] $1"; exit 1; }
warn() { echo "  [⚠️ ] $1"; }

echo "=== 1. 凭证环境变量 ==="
if [ -n "${FEISHU_APP_ID:-}" ]; then pass "FEISHU_APP_ID 存在"; else fail "FEISHU_APP_ID 未设置"; fi
if [ -n "${FEISHU_APP_SECRET:-}" ]; then pass "FEISHU_APP_SECRET 存在（脱敏不打印）"; else fail "FEISHU_APP_SECRET 未设置"; fi
pass "HOST=${HOST}"

echo ""
echo "=== 2. tenant_access_token 可取 ==="
TOKEN=$(bash "${SCRIPT_DIR}/token.sh" 2>&1) || {
  echo "$TOKEN"
  fail "取 tenant_access_token 失败（看上面 [AUTH_FAIL]）"
}
pass "token 长度=${#TOKEN}"

if [ -n "$WIKI_URL" ]; then
  echo ""
  echo "=== 3. wiki 可读性：${WIKI_URL} ==="
  WIKI_TOKEN=$(echo "$WIKI_URL" | sed -E 's|.*/wiki/([A-Za-z0-9]+).*|\1|')
  [ -z "$WIKI_TOKEN" ] && fail "wiki_url 解析不出 wiki_token"
  pass "wiki_token=${WIKI_TOKEN}"
  RES=$(curl -sS "https://${HOST}/open-apis/wiki/v2/spaces/get_node?token=${WIKI_TOKEN}" \
    -H "Authorization: Bearer $TOKEN")
  CODE=$(echo "$RES" | python3 -c "import sys,json;print(json.load(sys.stdin).get('code','?'))")
  case "$CODE" in
    0) TITLE=$(echo "$RES" | python3 -c "import sys,json;print(json.load(sys.stdin)['data']['node']['title'])")
       pass "wiki 根节点可读：title=${TITLE}"
       ;;
    99991672) fail "code 99991672 → scope 不足：加 wiki:wiki:readonly 并发版（docs/error-codes.md）" ;;
    131006)   fail "code 131006 → 非成员或 wiki 非公开：加应用到知识库成员（docs/error-codes.md）" ;;
    *)        MSG=$(echo "$RES" | python3 -c 'import sys,json;print(json.load(sys.stdin).get("msg",""))' 2>/dev/null)
              fail "不可读：code=$CODE msg=$MSG" ;;
  esac
fi

if [ -n "$DOC_URL" ]; then
  echo ""
  echo "=== 4. docx 可读性：${DOC_URL} ==="
  DOC_TOKEN=$(echo "$DOC_URL" | sed -E 's|.*/(docx\|docs)/([A-Za-z0-9]+).*|\2|')
  [ -z "$DOC_TOKEN" ] && fail "doc_url 解析不出 doc_token"
  pass "doc_token=${DOC_TOKEN}"
  RES=$(curl -sS "https://${HOST}/open-apis/docx/v1/documents/${DOC_TOKEN}/raw_content?lang=0" \
    -H "Authorization: Bearer $TOKEN")
  CODE=$(echo "$RES" | python3 -c "import sys,json;print(json.load(sys.stdin).get('code','?'))")
  case "$CODE" in
    0) pass "docx 正文可读" ;;
    99991672) fail "code 99991672 → scope 不足：加 docx:document:readonly 并发版" ;;
    *)        fail "不可读：code=$CODE" ;;
  esac
fi

if [ "$CHECK_SHEETS" -eq 1 ]; then
  echo ""
  echo "=== 5. sheets:spreadsheet scope 验证（创建临时表 + 立即删除）==="
  TITLE="probe-$(date +%s)"
  CREATE_RES=$(curl -sS -X POST "https://${HOST}/open-apis/sheets/v3/spreadsheets" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"title\":\"$TITLE\"}")
  CODE=$(echo "$CREATE_RES" | python3 -c "import sys,json;print(json.load(sys.stdin).get('code','?'))")
  case "$CODE" in
    0) SST=$(echo "$CREATE_RES" | python3 -c "import sys,json;print(json.load(sys.stdin)['data']['spreadsheet']['spreadsheet_token'])")
       pass "可创建 spreadsheet：token=${SST}"
       # 立即删除避免污染（用 drive 删除文件 API）
       DEL_RES=$(curl -sS -X DELETE "https://${HOST}/open-apis/drive/v1/files/${SST}?type=sheet" \
         -H "Authorization: Bearer $TOKEN")
       DEL_CODE=$(echo "$DEL_RES" | python3 -c "import sys,json;print(json.load(sys.stdin).get('code','?'))")
       if [ "$DEL_CODE" = "0" ]; then
         pass "可删除（drive:drive scope 也通）"
       else
         warn "无法自动删除（drive:drive 未开？）请手动到飞书云空间删 ${TITLE}（code=$DEL_CODE）"
       fi
       ;;
    99991672) fail "code 99991672 → 缺 sheets:spreadsheet scope，加 scope 并发新版本（docs/error-codes.md#99991672）" ;;
    *)        MSG=$(echo "$CREATE_RES" | python3 -c 'import sys,json;print(json.load(sys.stdin).get("msg",""))' 2>/dev/null)
              fail "创建失败：code=$CODE msg=$MSG" ;;
  esac
fi

echo ""
echo "[READY] 自检全绿"
