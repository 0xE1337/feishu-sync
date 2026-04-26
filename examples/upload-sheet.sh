#!/usr/bin/env bash
# examples/upload-sheet.sh
# 演示：把一份 CSV 上传为飞书电子表格（独立 spreadsheet 页面，类似 Excel）。
#
# 流程：
#   1. 生成样本 CSV（含中文 + 数字 + 引号转义 + 多行）
#   2. dry-run 检查：解析 + 打印请求骨架，不真发请求
#   3. 真实上传到飞书，打印 sheet URL
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck disable=SC1091  # .env 可能不存在或路径在运行时才确定
[ -f "${PROJECT_ROOT}/.env" ] && set -a && source "${PROJECT_ROOT}/.env" && set +a

# 自检凭证
bash "${PROJECT_ROOT}/bin/probe.sh"

# 生成样本（含数字、负数、小数、含逗号的字符串、多行字符串）
SAMPLE=$(mktemp /tmp/sheet-sample-XXXXXX.csv)
cat > "$SAMPLE" <<'EOF'
姓名,部门,Q1销售,Q2销售,达成率,备注
张三,华东,1234.5,1567.8,98.2,"重点客户, A级"
李四,华南,5678,4321,105.0,"新签 3 单"
王五,华北,890,1100,72.5,"缺勤 2 周
需关注"
赵六,西南,-200,300,15.0,转岗审批中
EOF

echo "[sample] 文件：$SAMPLE"
echo ""

# 1) Dry-run：本地解析 + 打印 API 请求骨架，不真发请求
echo "=== STEP 1: dry-run（不发请求） ==="
bash "${PROJECT_ROOT}/bin/upload-sheet.sh" "$SAMPLE" --dry-run --title "Q1Q2 销售（dry-run）"
echo ""

# 2) 真实上传
echo "=== STEP 2: 真实上传到飞书 ==="
bash "${PROJECT_ROOT}/bin/upload-sheet.sh" "$SAMPLE" --title "Q1Q2 销售 $(date +%Y%m%d-%H%M%S)"

# 清理样本
rm -f "$SAMPLE"
echo ""
echo "=== 完成 ==="
echo "去飞书里检查："
echo "  - 应是独立电子表格页面（URL 形如 .../sheets/<token>），不是 docx"
echo "  - Q1销售/Q2销售/达成率列应被识别为数字（右对齐，可参与公式）"
echo "  - 含逗号 / 多行的备注列应保持完整不被切碎"
