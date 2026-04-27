#!/usr/bin/env bash
# feishu-sync/bin/upload-sheet.sh — 上传单张表格到飞书电子表格（Sheets，类似 Excel）
#
# 区别于 upload.sh：
#   upload.sh         markdown 全文 → 飞书 docx（表格被压成 markdown 表格块）
#   upload-sheet.sh   单张表格      → 飞书 spreadsheet（独立电子表格，可像 Excel 一样编辑）
#
# 用法：
#   bash upload-sheet.sh <file> [--title "标题"] [--folder <folder_token>]
#                              [--format auto|csv|tsv|md] [--dry-run]
#                              [--plain] [--literal] [--header-bg "#RRGGBB"]
#
# 输入格式：
#   .csv  逗号分隔
#   .tsv  制表符分隔
#   .md   抓取文件中第一张 GFM 表格（| col | col |）
#   显式 --format 覆盖扩展名推断
#
# 美观度（默认全开）：
#   表头加粗 + 浅蓝底 (#E8F0FE) + 居中
#   冻结首行
#   列宽自适应（CJK 字符按 2 算）
#   --plain               一次跳过所有美化
#   --no-header-style     只跳过表头样式（保留冻结+列宽）
#   --no-freeze           只跳过冻结（保留样式+列宽）
#   --no-autosize         只跳过列宽（保留样式+冻结）
#   --header-bg "#RRGGBB" 自定义表头背景色
#
# 刷新已有表（不新建）：
#   --update URL_OR_TOKEN 传 sheet URL 或 raw spreadsheet_token，
#                         跳过 create + 自动跳过样式，数据从 A1 覆盖写入
#
# 数据保真：
#   默认走 USER_ENTERED + 转义保护：
#     - 前导零 (007) 保留为字符串
#     - 科学计数法 (1.23e10) 识别为 float
#     - = / + / - / @ 开头字符串自动加 ' 前缀，防止飞书把它当公式执行
#   --literal             切到 RAW 模式，所有内容当字符串原样上传（不识别数字、不加前缀）
#
# 环境变量：
#   FEISHU_APP_ID, FEISHU_APP_SECRET   (必需)
#   FEISHU_HOST                        (可选，默认 open.feishu.cn)
#
# 权限 scope（应用身份）：
#   sheets:spreadsheet                              （含创建+读写，最常用）
#   或 sheets:spreadsheet:create + drive:drive       （颗粒度更细的最小集）
#   指定 --folder 时必须有 drive:drive
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="${SCRIPT_DIR}/upload-sheet.py"

if [ ! -f "$PY" ]; then
  echo "[ERR] 找不到 ${PY}" >&2
  exit 1
fi
if ! command -v python3 >/dev/null 2>&1; then
  echo "[ERR] 需要 python3（>=3.6，纯 stdlib，无额外依赖）" >&2
  exit 1
fi

# 解析 -h / --help 时直接打印本文件 header
if [ $# -eq 0 ] || [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
  awk '/^[^#]/{exit} NR>1{sub(/^# ?/,""); print}' "$0"
  echo ""
  echo "（详细参数说明见 python3 ${PY} --help）"
  exit 0
fi

# 必需的凭证检查（--dry-run 模式 Python 内部仍要走鉴权流程会失败，
# 但 dry-run 实际上跳过 API 调用，所以提前放过）
DRY_RUN=0
for a in "$@"; do
  [ "$a" = "--dry-run" ] && DRY_RUN=1
done

if [ "$DRY_RUN" -eq 0 ]; then
  : "${FEISHU_APP_ID:?必须设置 FEISHU_APP_ID}"
  : "${FEISHU_APP_SECRET:?必须设置 FEISHU_APP_SECRET}"
fi

# 直接转发给 Python 实现，参数全保留
exec python3 "$PY" "$@"
