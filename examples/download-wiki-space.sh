#!/usr/bin/env bash
# examples/download-wiki-space.sh
# 演示：批量下载一个飞书 wiki 空间到本地 markdown
#
# 先把 .env.example 复制为 .env 并填好值，再跑：
#   bash examples/download-wiki-space.sh <wiki_url>
set -euo pipefail

WIKI_URL="${1:-}"
[ -z "$WIKI_URL" ] && { echo "用法：bash $0 <wiki_url>"; exit 1; }

# 加载 .env（如果存在）
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck disable=SC1091  # .env 可能不存在或路径在运行时才确定
[ -f "${PROJECT_ROOT}/.env" ] && set -a && source "${PROJECT_ROOT}/.env" && set +a

# 自检
bash "${PROJECT_ROOT}/bin/probe.sh" --wiki "$WIKI_URL"

# 下载
OUT_DIR="./out-$(date +%Y%m%d-%H%M%S)"
bash "${PROJECT_ROOT}/bin/download.sh" "$WIKI_URL" -o "$OUT_DIR" --recursive

echo ""
echo "=== 完成 ==="
echo "产物：$(pwd)/${OUT_DIR}/"
