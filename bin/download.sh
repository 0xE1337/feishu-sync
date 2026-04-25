#!/usr/bin/env bash
# feishu-sync/bin/download.sh — 从飞书下载为 Markdown（带 cache 控制）
#
# 用法：
#   bash download.sh <URL> [-o OUT_DIR] [--recursive] [--cache-mode MODE]
#
# URL 支持：
#   https://xxx.feishu.cn/docx/<token>                  (单文档)
#   https://xxx.feishu.cn/wiki/<wiki_token>             (单 wiki 节点；+ --recursive 整个空间)
#
# cache-mode（命令行参数 > 环境变量 CACHE_MODE > 默认 auto）：
#   auto    metadata 比对：远端未变跳过下载，省时间不漏更新
#   force   强制重下，覆盖本地（含 meta）
#   skip    只用本地副本，不联网（无副本则报错）
#
# 注：wiki 全量递归（--recursive）下，feishu-docx 路径暂不做 per-node cache，
#     按 force 行为重下整个 space；要 cache 请改用 lite 路径或单节点逐个拉。
#
# 环境变量：
#   FEISHU_APP_ID, FEISHU_APP_SECRET   (必需)
#   FEISHU_HOST                        (可选，默认 open.feishu.cn)
#   CACHE_MODE                         (可选，命令行 --cache-mode 优先)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
URL=""
OUT_DIR="./out"
RECURSIVE=0
AUTH_MODE="tenant"
CACHE_MODE="${CACHE_MODE:-auto}"

while [ $# -gt 0 ]; do
  case "$1" in
    -o|--out)      OUT_DIR="$2"; shift 2 ;;
    --recursive)   RECURSIVE=1; shift ;;
    --auth)        AUTH_MODE="$2"; shift 2 ;;
    --cache-mode)  CACHE_MODE="$2"; shift 2 ;;
    -h|--help)     awk '/^[^#]/{exit} NR>1{sub(/^# ?/,""); print}' "$0"; exit 0 ;;
    -*)            echo "未知参数: $1" >&2; exit 2 ;;
    *)             URL="$1"; shift ;;
  esac
done

[ -z "$URL" ] && { echo "[MISSING] URL 必须提供" >&2; exit 2; }
case "$CACHE_MODE" in
  auto|force|skip) ;;
  *) echo "[ERR] --cache-mode 必须为 auto|force|skip，给的是 '$CACHE_MODE'" >&2; exit 2 ;;
esac
mkdir -p "$OUT_DIR"

has_feishu_docx() { command -v feishu-docx >/dev/null 2>&1; }
LITE="${SCRIPT_DIR}/download-lite.py"

# ─── feishu-docx 不可用时降级到纯 Python fallback ───────────────────
if ! has_feishu_docx; then
  if [ -f "$LITE" ] && command -v python3 >/dev/null 2>&1; then
    echo "[fallback] feishu-docx 不可用（Python<3.7 或未安装）→ 降级到纯 Python stdlib 下载（raw_content，保真度降低）" >&2
    LITE_ARGS=("$URL" -o "$OUT_DIR" --cache-mode "$CACHE_MODE")
    [ "$RECURSIVE" -eq 1 ] && LITE_ARGS+=(--recursive)
    exec python3 "$LITE" "${LITE_ARGS[@]}"
  else
    echo "[ERR] feishu-docx 不可用，且 python3 fallback 也不可用；先跑 bash $SCRIPT_DIR/setup.sh" >&2
    exit 1
  fi
fi

# 用 feishu-docx config 设置 app_id / app_secret（幂等）
feishu-docx config set \
  --app-id "${FEISHU_APP_ID:?必须设置}" \
  --app-secret "${FEISHU_APP_SECRET:?必须设置}" \
  --auth-mode "$AUTH_MODE" >/dev/null 2>&1 || true

# ─── 工具函数 ────────────────────────────────────────────────────────
probe_url() {
  # echo PROBE_OUT to stdout, return 0=hit / 1=miss / >=2=error
  python3 "$LITE" --probe "$URL" -o "$OUT_DIR" 2>/dev/null
}

write_meta_for() {
  local FILE_PATH="$1"
  python3 "$LITE" --save-meta "$URL" -o "$OUT_DIR" --file-path "$FILE_PATH" >&2 \
    || echo "[WARN] meta 写入失败，下次 cache 会 miss" >&2
}

extract_json_field() {
  # usage: extract_json_field "$JSON" field
  python3 -c '
import sys, json
try:
    d = json.loads(sys.stdin.read() or "{}")
    print(d.get(sys.argv[1], "") or "")
except Exception:
    print("")
' "$2" <<<"$1" 2>/dev/null || echo ""
}

# ─── 分支：wiki 全量递归 ────────────────────────────────────────────
if [[ "$URL" == *"/wiki/"* ]] && [ "$RECURSIVE" -eq 1 ]; then
  if [ "$CACHE_MODE" != "force" ]; then
    echo "[NOTE] wiki 全量递归 + feishu-docx 路径：暂不做 per-node cache，本次按 force 重下整个 space。" >&2
    echo "       如需 per-node cache，改 lite 路径（卸载 feishu-docx 让它自动 fallback，或直接 python3 $LITE $URL --recursive --cache-mode auto）" >&2
  fi
  echo "[mode] wiki-space 全量导出 → ${OUT_DIR}"
  feishu-docx export-wiki-space "$URL" -o "$OUT_DIR" -b
  echo ""
  echo "[DONE] 产物："
  find "$OUT_DIR" -name "*.md" -type f 2>/dev/null | head -20
  echo "..."
  echo "总计 $(find "$OUT_DIR" -name '*.md' -type f 2>/dev/null | wc -l | xargs) 个 md 文件"
  exit 0
fi

# ─── 分支：单文档（docx / wiki 节点 / docs）─────────────────────────
if ! [[ "$URL" == *"/wiki/"* || "$URL" == *"/docx/"* || "$URL" == *"/docs/"* ]]; then
  echo "[ERR] URL 不是 /docx/ /docs/ /wiki/ 开头：$URL" >&2
  exit 2
fi

PROBE_OUT=""
PROBE_EXIT=0
if [ "$CACHE_MODE" != "force" ]; then
  PROBE_OUT=$(probe_url) || PROBE_EXIT=$?
  PROBE_EXIT="${PROBE_EXIT:-0}"
  if [ "$PROBE_EXIT" -ge 2 ]; then
    echo "[WARN] cache probe 失败（exit=$PROBE_EXIT），按 miss 处理走下载" >&2
    PROBE_OUT=""
  fi
fi

# cache 命中
if [ "$PROBE_EXIT" = "0" ] && [ -n "$PROBE_OUT" ]; then
  FP=$(extract_json_field "$PROBE_OUT" file_path)
  echo "[cache] hit ${OUT_DIR}/${FP}（远端未变，跳过下载）"
  exit 0
fi

# skip 模式但 miss → 报错
if [ "$CACHE_MODE" = "skip" ]; then
  echo "[ERR] skip 模式但本地无可用缓存（probe miss / 失败）" >&2
  [ -n "$PROBE_OUT" ] && echo "$PROBE_OUT" >&2
  exit 1
fi

# 拿 sanitized_filename 强制 feishu-docx 输出文件名（确保 save-meta 时知道 file_path）
SANITIZED_NAME=""
if [ -n "$PROBE_OUT" ]; then
  SANITIZED_NAME=$(extract_json_field "$PROBE_OUT" sanitized_filename)
fi

echo "[mode] 单文档导出 → ${OUT_DIR}（cache-mode=$CACHE_MODE）"

if [ -n "$SANITIZED_NAME" ]; then
  NAME_NO_EXT="${SANITIZED_NAME%.md}"
  feishu-docx export "$URL" -o "$OUT_DIR" -n "$NAME_NO_EXT" -b
  write_meta_for "$SANITIZED_NAME"
else
  # probe 没结果（force 模式或 probe 失败）→ 让 feishu-docx 自己决定文件名，事后扫描
  MARKER=$(mktemp -t feishu-sync-marker.XXXXXX)
  trap 'rm -f "$MARKER"' EXIT
  feishu-docx export "$URL" -o "$OUT_DIR" -b
  LATEST=$(find "$OUT_DIR" -maxdepth 1 -name "*.md" -newer "$MARKER" -type f 2>/dev/null | head -1)
  if [ -n "$LATEST" ]; then
    write_meta_for "$(basename "$LATEST")"
  else
    echo "[WARN] 未能识别本次下载文件，跳过 meta 写入；下次 cache 会 miss" >&2
  fi
fi

echo ""
echo "[DONE] 产物："
find "$OUT_DIR" -name "*.md" -type f 2>/dev/null | head -20
echo "..."
echo "总计 $(find "$OUT_DIR" -name '*.md' -type f 2>/dev/null | wc -l | xargs) 个 md 文件"
