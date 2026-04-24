#!/usr/bin/env bash
# examples/upload-with-latex.sh
# 演示：创建一个带 LaTeX 公式的 md，上传到飞书，验证公式正确渲染
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
[ -f "${PROJECT_ROOT}/.env" ] && set -a && source "${PROJECT_ROOT}/.env" && set +a

# 自检
bash "${PROJECT_ROOT}/bin/probe.sh"

# 生成一个包含公式的样本文件
SAMPLE=$(mktemp /tmp/latex-sample-XXXXXX.md)
cat > "$SAMPLE" <<'EOF'
# LaTeX 渲染测试文档

## 行内公式

爱因斯坦质能方程：$E = mc^2$。

二次方程求根：$x = \frac{-b \pm \sqrt{b^2 - 4ac}}{2a}$。

## 块级公式

$$
\sum_{i=1}^{n} i = \frac{n(n+1)}{2}
$$

$$
\int_{-\infty}^{\infty} e^{-x^2} dx = \sqrt{\pi}
$$

## 普通文字

本段没有公式，应作为正文显示。`$10M` 是货币金额（不应该被识别为公式）。

EOF

echo "[sample] 文件：$SAMPLE"
echo ""

# 上传（应自动检测到 LaTeX 并路由到 uploader）
bash "${PROJECT_ROOT}/bin/upload.sh" "$SAMPLE" --title "LaTeX 渲染测试 $(date +%Y%m%d-%H%M%S)"

# 清理样本
rm -f "$SAMPLE"
echo ""
echo "=== 完成 ==="
echo "去飞书里检查：公式应该渲染为数学符号，而不是原始 \$...\$ 文本"
