#!/usr/bin/env bash
# feishu-sync/bin/download.sh — 从飞书下载为 Markdown
#
# 用法：
#   bash download.sh <URL> [-o OUT_DIR] [--recursive]
#
# URL 支持：
#   https://xxx.feishu.cn/docx/<token>                  (单文档)
#   https://xxx.feishu.cn/wiki/<wiki_token>             (单 wiki 节点；+ --recursive 整个空间)
#
# 环境变量：
#   FEISHU_APP_ID, FEISHU_APP_SECRET   (必需)
#   FEISHU_HOST                        (可选，默认 open.feishu.cn)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
URL=""
OUT_DIR="./out"
RECURSIVE=0
AUTH_MODE="tenant"

while [ $# -gt 0 ]; do
  case "$1" in
    -o|--out)    OUT_DIR="$2"; shift 2 ;;
    --recursive) RECURSIVE=1; shift ;;
    --auth)      AUTH_MODE="$2"; shift 2 ;;
    -h|--help)   awk '/^[^#]/{exit} NR>1{sub(/^# ?/,""); print}' "$0"; exit 0 ;;
    -*)          echo "未知参数: $1" >&2; exit 2 ;;
    *)           URL="$1"; shift ;;
  esac
done

[ -z "$URL" ] && { echo "[MISSING] URL 必须提供" >&2; exit 2; }
mkdir -p "$OUT_DIR"

command -v feishu-docx >/dev/null 2>&1 || {
  echo "[ERR] 未找到 feishu-docx，先跑 bash $(dirname "$SCRIPT_DIR")/install.sh 或 bash $SCRIPT_DIR/setup.sh" >&2
  exit 1
}

# 用 feishu-docx config 设置 app_id / app_secret（如果尚未配）
# 这一步幂等
feishu-docx config set \
  --app-id "${FEISHU_APP_ID:?必须设置}" \
  --app-secret "${FEISHU_APP_SECRET:?必须设置}" \
  --auth-mode "$AUTH_MODE" >/dev/null 2>&1 || true

# 分支
if [[ "$URL" == *"/wiki/"* ]] && [ "$RECURSIVE" -eq 1 ]; then
  echo "[mode] wiki-space 全量导出 → ${OUT_DIR}"
  feishu-docx export-wiki-space "$URL" -o "$OUT_DIR" -b
elif [[ "$URL" == *"/wiki/"* ]] || [[ "$URL" == *"/docx/"* ]] || [[ "$URL" == *"/docs/"* ]]; then
  echo "[mode] 单文档导出 → ${OUT_DIR}"
  feishu-docx export "$URL" -o "$OUT_DIR" -b
else
  echo "[ERR] URL 不是 /docx/ /docs/ /wiki/ 开头：$URL" >&2
  exit 2
fi

echo ""
echo "[DONE] 产物："
find "$OUT_DIR" -name "*.md" -type f 2>/dev/null | head -20
echo "..."
echo "总计 $(find "$OUT_DIR" -name '*.md' -type f 2>/dev/null | wc -l | xargs) 个 md 文件"
