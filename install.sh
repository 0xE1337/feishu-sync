#!/usr/bin/env bash
# install.sh — 把 feishu-sync 安装为 Claude Code skill
#
# 做两件事：
# 1) 符号链接本项目到 ~/.claude/skills/feishu-sync（Claude Code 读这里）
# 2) 跑 bin/setup.sh 装依赖（feishu-docx + uploader）
#
# 用法：
#   bash install.sh              # 正常安装（符号链接）
#   bash install.sh --copy       # 用复制代替符号链接（离线环境或 Windows）
#   bash install.sh --no-deps    # 只装 skill，不装依赖
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="${HOME}/.claude/skills/feishu-sync"

MODE="symlink"
INSTALL_DEPS=1

while [ $# -gt 0 ]; do
  case "$1" in
    --copy)     MODE="copy"; shift ;;
    --no-deps)  INSTALL_DEPS=0; shift ;;
    -h|--help)  sed -n '2,13p' "$0" | sed 's|^# \?||'; exit 0 ;;
    *) echo "未知参数: $1" >&2; exit 2 ;;
  esac
done

# ─── 1. 安装 skill ───────────────────────────────────────────────────
mkdir -p "${HOME}/.claude/skills"

if [ -e "$SKILL_ROOT" ] || [ -L "$SKILL_ROOT" ]; then
  echo "[clean] 移除旧安装：${SKILL_ROOT}"
  rm -rf "$SKILL_ROOT"
fi

case "$MODE" in
  symlink)
    ln -s "$PROJECT_ROOT" "$SKILL_ROOT"
    echo "[link] ${SKILL_ROOT} → ${PROJECT_ROOT}"
    ;;
  copy)
    cp -r "$PROJECT_ROOT" "$SKILL_ROOT"
    echo "[copy] ${PROJECT_ROOT} → ${SKILL_ROOT}"
    ;;
esac

# ─── 2. 装依赖 ────────────────────────────────────────────────────────
if [ "$INSTALL_DEPS" -eq 1 ]; then
  bash "${PROJECT_ROOT}/bin/setup.sh"
else
  echo "[skip] 跳过依赖安装（--no-deps）"
fi

# ─── 3. 给 bin/ 下的脚本加执行权限 ────────────────────────────────────
chmod +x "${PROJECT_ROOT}"/bin/*.sh 2>/dev/null || true
chmod +x "${PROJECT_ROOT}"/examples/*.sh 2>/dev/null || true

echo ""
echo "[DONE] feishu-sync 安装完成"
echo ""
echo "下一步："
echo "  1) 把凭证复制到 .env 并填好：cp ${PROJECT_ROOT}/.env.example ${PROJECT_ROOT}/.env"
echo "  2) 自检：source ${PROJECT_ROOT}/.env && bash ${PROJECT_ROOT}/bin/probe.sh"
echo "  3) 在 Claude Code 里，skill 'feishu-sync' 现在可用"
