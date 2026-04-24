#!/usr/bin/env bash
# feishu-sync/bin/upload.sh — 上传 Markdown 到飞书
#
# 自动检测 LaTeX 公式：
#   有公式 → 走 feishu-markdown-uploader（公式渲染为 equation 块）
#   无公式 → 走 feishu-docx create（快速、无多余转换）
#
# 用法：
#   bash upload.sh <file.md> [--title "标题"] [--folder <folder_token>] [--force-latex] [--force-simple]
#
# 环境变量：
#   FEISHU_APP_ID, FEISHU_APP_SECRET     (必需)
#   FEISHU_SYNC_HOME                     (可选，默认 ~/.feishu-sync；uploader 安装位置)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FEISHU_SYNC_HOME="${FEISHU_SYNC_HOME:-${HOME}/.feishu-sync}"
UPLOADER_DIR="${FEISHU_SYNC_HOME}/uploader"

FILE=""
TITLE=""
FOLDER=""
FORCE_LATEX=0
FORCE_SIMPLE=0

while [ $# -gt 0 ]; do
  case "$1" in
    --title)        TITLE="$2"; shift 2 ;;
    --folder)       FOLDER="$2"; shift 2 ;;
    --force-latex)  FORCE_LATEX=1; shift ;;
    --force-simple) FORCE_SIMPLE=1; shift ;;
    -h|--help)      sed -n '2,16p' "$0" | sed 's|^# \?||'; exit 0 ;;
    -*)             echo "未知参数: $1" >&2; exit 2 ;;
    *)              FILE="$1"; shift ;;
  esac
done

[ -z "$FILE" ] && { echo "[MISSING] 文件路径必须提供" >&2; exit 2; }
[ ! -f "$FILE" ] && { echo "[ERR] 文件不存在：$FILE" >&2; exit 1; }
: "${FEISHU_APP_ID:?必须设置}"
: "${FEISHU_APP_SECRET:?必须设置}"

# 默认 title 用文件名去掉扩展
[ -z "$TITLE" ] && TITLE="$(basename "$FILE" .md)"

# ─── LaTeX 检测（heuristic）──────────────────────────────────────────
# 信号 1: $$ ... $$
# 信号 2: 单行内 $...$ 且包含 LaTeX 符号（\frac, ^, _, \{）
# 注意：$10M 这种货币不算公式
HAS_LATEX=0
if grep -qE '\$\$' "$FILE"; then HAS_LATEX=1; fi
if grep -qE '\$[^$]*\\(frac|sum|int|prod|sqrt|alpha|beta|gamma|delta|theta|lambda|mu|nu|pi|rho|sigma|tau|phi|omega)' "$FILE"; then HAS_LATEX=1; fi
if grep -qE '\$[^$]*[\^_{]' "$FILE"; then HAS_LATEX=1; fi

# 决策
if [ "$FORCE_LATEX" -eq 1 ]; then
  ROUTE="uploader"
elif [ "$FORCE_SIMPLE" -eq 1 ]; then
  ROUTE="feishu-docx"
elif [ "$HAS_LATEX" -eq 1 ]; then
  ROUTE="uploader"
else
  ROUTE="feishu-docx"
fi

echo "[detect] LaTeX=${HAS_LATEX} → 路由到 ${ROUTE}"

# ─── 路由执行 ────────────────────────────────────────────────────────
case "$ROUTE" in
  uploader)
    [ ! -f "${UPLOADER_DIR}/upload.mjs" ] && {
      echo "[ERR] uploader 未安装，跑 bash $SCRIPT_DIR/setup.sh" >&2
      exit 1
    }
    echo "[exec] node ${UPLOADER_DIR}/upload.mjs ${FILE} ${TITLE}"
    (cd "$UPLOADER_DIR" && node upload.mjs "$FILE" "$TITLE")
    ;;
  feishu-docx)
    command -v feishu-docx >/dev/null 2>&1 || {
      echo "[ERR] feishu-docx 未安装，跑 bash $SCRIPT_DIR/setup.sh" >&2
      exit 1
    }
    feishu-docx config set \
      --app-id "$FEISHU_APP_ID" \
      --app-secret "$FEISHU_APP_SECRET" \
      --auth-mode tenant >/dev/null 2>&1 || true

    CMD="feishu-docx create \"$TITLE\" -f \"$FILE\""
    [ -n "$FOLDER" ] && CMD="$CMD --folder $FOLDER"
    echo "[exec] $CMD"
    eval "$CMD"
    ;;
esac

echo "[DONE] 上传完成"
