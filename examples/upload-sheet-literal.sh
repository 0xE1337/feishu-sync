#!/usr/bin/env bash
# examples/upload-sheet-literal.sh
# 演示：--literal 模式与默认模式的对比
#
# 场景：上传一份航班/订单表，里面有：
#   - 前导零航班号（CA0123 / 007）
#   - 看起来像公式的字符串（=A1+B1，但实际是用户备注里的文本）
#   - 看起来像数字的 ID（应保持字符串）
#
# 默认模式：飞书会"聪明地"把 007 → 7，把 =A1+B1 当公式执行
# --literal：所有内容当字符串原样保留
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck disable=SC1091
[ -f "${PROJECT_ROOT}/.env" ] && set -a && source "${PROJECT_ROOT}/.env" && set +a
bash "${PROJECT_ROOT}/bin/probe.sh"

# 生成样本：含前导零、公式样字符串、纯数字 ID
SAMPLE=$(mktemp /tmp/sheet-literal-XXXXXX.csv)
cat > "$SAMPLE" <<'EOF'
航班号,公式备注,纯数字ID,中文
CA0123,=A1+B1,001,北京-上海
MU007,=SUM(C2:C5),042,上海-广州
CZ0456,=AVG(B:B),100,广州-深圳
EOF

echo "[sample] $SAMPLE"
echo ""
echo "=== 默认模式（USER_ENTERED + escape）==="
echo "  预期：=A1+B1 在飞书显示为字符串（带 ' 前缀防注入），CA0123 保留前导零"
TS=$(date +%H%M%S)
bash "${PROJECT_ROOT}/bin/upload-sheet.sh" "$SAMPLE" --title "literal-DEFAULT-${TS}"

echo ""
echo "=== --literal 模式（RAW，全部当字符串）==="
echo "  预期：=A1+B1 字符串原样，001/042/100 保留前导零"
bash "${PROJECT_ROOT}/bin/upload-sheet.sh" "$SAMPLE" --title "literal-RAW-${TS}" --literal

rm -f "$SAMPLE"
echo ""
echo "=== 完成 ==="
echo "去飞书里对比两份："
echo "  - 默认模式：A 列 (航班号) CA0123 是字符串，B 列公式带 ' 不被执行"
echo "  - literal 模式：所有内容都是 raw 字符串，C 列 001/042/100 都保留前导零"
