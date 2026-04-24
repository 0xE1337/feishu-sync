#!/usr/bin/env bash
# feishu-sync setup — 幂等安装依赖
#
# 用法：bash setup.sh
# 装好后可用：
#   - feishu-docx CLI（pipx 装，隔离）
#   - ${FEISHU_SYNC_HOME}/uploader/upload.mjs（git clone + npm install）
#
# 环境变量（可选）：
#   FEISHU_SYNC_HOME  安装目录，默认 ${HOME}/.feishu-sync
#   UPLOADER_REPO     uploader 仓库地址，默认 https://github.com/0xE1337/feishu-markdown-uploader.git
#   UPLOADER_REF      branch/tag/commit，默认 main
set -euo pipefail

FEISHU_SYNC_HOME="${FEISHU_SYNC_HOME:-${HOME}/.feishu-sync}"
UPLOADER_REPO="${UPLOADER_REPO:-https://github.com/0xE1337/feishu-markdown-uploader.git}"
UPLOADER_REF="${UPLOADER_REF:-main}"
UPLOADER_DIR="${FEISHU_SYNC_HOME}/uploader"

mkdir -p "${FEISHU_SYNC_HOME}"

# ─── 1. feishu-docx（pipx 首选，pip 兜底）─────────────────────────────
install_feishu_docx() {
  if command -v feishu-docx >/dev/null 2>&1; then
    echo "[skip] feishu-docx 已安装：$(command -v feishu-docx)"
    return 0
  fi

  if command -v pipx >/dev/null 2>&1; then
    echo "[install] pipx install feishu-docx"
    pipx install feishu-docx
  elif command -v uv >/dev/null 2>&1; then
    echo "[install] uv tool install feishu-docx"
    uv tool install feishu-docx
  elif command -v pip3 >/dev/null 2>&1; then
    echo "[install] pip3 install --user feishu-docx"
    pip3 install --user feishu-docx
  else
    echo "[FAIL] 找不到 pipx / uv / pip3，请先装 Python 工具链" >&2
    return 1
  fi
}

# ─── 2. uploader (node) ──────────────────────────────────────────────
install_uploader() {
  if [ -d "${UPLOADER_DIR}/node_modules" ] && [ -f "${UPLOADER_DIR}/upload.mjs" ]; then
    echo "[skip] uploader 已安装：${UPLOADER_DIR}"
    return 0
  fi

  if ! command -v node >/dev/null 2>&1; then
    echo "[FAIL] 需要 Node.js（>=18），请先装：https://nodejs.org" >&2
    return 1
  fi
  if ! command -v npm >/dev/null 2>&1; then
    echo "[FAIL] 需要 npm，随 Node.js 一起装" >&2
    return 1
  fi

  if [ ! -d "${UPLOADER_DIR}/.git" ]; then
    echo "[install] git clone ${UPLOADER_REPO} → ${UPLOADER_DIR}"
    git clone --depth=1 -b "${UPLOADER_REF}" "${UPLOADER_REPO}" "${UPLOADER_DIR}"
  else
    echo "[update] git pull in ${UPLOADER_DIR}"
    git -C "${UPLOADER_DIR}" pull --ff-only
  fi

  echo "[install] npm install in ${UPLOADER_DIR}"
  (cd "${UPLOADER_DIR}" && npm install --no-audit --no-fund)
}

# ─── 3. 验证 ─────────────────────────────────────────────────────────
verify() {
  echo ""
  echo "=== 安装结果 ==="
  feishu-docx --version 2>&1 | head -3 || echo "[WARN] feishu-docx 不可用"
  [ -f "${UPLOADER_DIR}/upload.mjs" ] && echo "uploader: ${UPLOADER_DIR}/upload.mjs OK" || echo "[WARN] uploader 未就绪"
  echo ""
  echo "[ready] 下一步："
  echo "  export FEISHU_APP_ID=cli_xxxxx"
  echo "  export FEISHU_APP_SECRET=xxxxx"
  echo "  bash $(dirname "$(realpath "$0")")/probe.sh   # 自检"
}

install_feishu_docx
install_uploader
verify
