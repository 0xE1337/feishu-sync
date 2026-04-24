#!/usr/bin/env bash
# uninstall.sh — 卸载 feishu-sync
#
# 做两件事（可选）：
# 1) 移除 ~/.claude/skills/feishu-sync 符号链接/拷贝
# 2) 移除 ~/.feishu-sync/ 里装的依赖（uploader clone）
#
# 用法：
#   bash uninstall.sh                    # 只卸 skill，保留依赖
#   bash uninstall.sh --purge            # 连依赖目录也删除
set -euo pipefail

SKILL_ROOT="${HOME}/.claude/skills/feishu-sync"
DEPS_ROOT="${FEISHU_SYNC_HOME:-${HOME}/.feishu-sync}"
PURGE=0

while [ $# -gt 0 ]; do
  case "$1" in
    --purge) PURGE=1; shift ;;
    -h|--help) sed -n '2,12p' "$0" | sed 's|^# \?||'; exit 0 ;;
    *) echo "未知参数: $1" >&2; exit 2 ;;
  esac
done

if [ -e "$SKILL_ROOT" ] || [ -L "$SKILL_ROOT" ]; then
  rm -rf "$SKILL_ROOT"
  echo "[rm] ${SKILL_ROOT}"
else
  echo "[skip] ${SKILL_ROOT} 本来就不在"
fi

if [ "$PURGE" -eq 1 ] && [ -d "$DEPS_ROOT" ]; then
  rm -rf "$DEPS_ROOT"
  echo "[rm] ${DEPS_ROOT}"
elif [ "$PURGE" -eq 1 ]; then
  echo "[skip] ${DEPS_ROOT} 不存在"
fi

echo ""
echo "[DONE] feishu-sync 卸载完成"
echo ""
echo "注意：feishu-docx CLI（如果是 pipx/uv 全局装）和 npm 全局依赖不会被移除。"
echo "完整清理可以手动跑："
echo "  pipx uninstall feishu-docx  (如适用)"
echo "  uv tool uninstall feishu-docx  (如适用)"
