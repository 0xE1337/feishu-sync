#!/usr/bin/env python3
"""
test-upload-sheet.py — 端到端集成测试（不依赖真实飞书凭证）

通过 monkey-patch upload_sheet._http_json，把所有飞书 API 调用劫持到本地 mock，
然后断言：
  1. 调用顺序：tenant_token → create → sheets/query → values_batch_update
  2. 每次调用的 method / path / body shape 和文档契约一致
  3. CSV / TSV / MD 三种输入解析后的 values 矩阵正确进入 API payload
  4. 数字类型保真（int / float vs str）
  5. folder_token 透传
  6. 最终 URL 打印正确

跑法：python3 bin/test-upload-sheet.py
退出码：0 全绿 / 1 失败
"""
from __future__ import annotations

import importlib.util
import io
import json
import os
import sys
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("upload_sheet", HERE / "upload-sheet.py")
us = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(us)


# ── Mock Feishu API ──────────────────────────────────────────────────────

class FakeFeishu:
    """录制所有调用，按 path 路由返回 canned response。"""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict | None]] = []
        self.fake_token = "t-" + "x" * 40
        self.fake_ss_token = "shtcnFAKE" + "S" * 18
        self.fake_sheet_id = "sht1234"
        self.fake_url = f"https://open.feishu.cn/sheets/{self.fake_ss_token}"

    def __call__(self, method, path, *, token=None, body=None, timeout=30):
        self.calls.append((method, path, body))
        # 路由
        if path.endswith("/auth/v3/tenant_access_token/internal"):
            return {"code": 0, "tenant_access_token": self.fake_token, "expire": 7200}
        if path == "/open-apis/sheets/v3/spreadsheets" and method == "POST":
            return {
                "code": 0,
                "msg": "success",
                "data": {
                    "spreadsheet": {
                        "title": (body or {}).get("title", ""),
                        "folder_token": (body or {}).get("folder_token", ""),
                        "url": self.fake_url,
                        "spreadsheet_token": self.fake_ss_token,
                    }
                },
            }
        if path.endswith("/sheets/query") and method == "GET":
            return {
                "code": 0,
                "data": {
                    "sheets": [
                        {
                            "sheet_id": self.fake_sheet_id,
                            "title": "Sheet1",
                            "index": 0,
                            "hidden": False,
                            "grid_properties": {"row_count": 200, "column_count": 20},
                            "resource_type": "sheet",
                        }
                    ]
                },
            }
        if path.endswith("/style") and method == "PUT":
            return {"code": 0, "data": {"spreadsheetToken": self.fake_ss_token, "revision": 8}}
        if path.endswith("/sheets_batch_update") and method == "POST":
            return {"code": 0, "data": {"replies": [{"updateSheet": {"properties": {"sheetId": self.fake_sheet_id}}}]}}
        if path.endswith("/dimension_range") and method == "POST":
            return {"code": 0, "data": {"spreadsheetToken": self.fake_ss_token}}
        if path.endswith("/values_batch_update") and method == "POST":
            ranges = (body or {}).get("valueRanges") or []
            total_cells = sum(
                len(r.get("values") or []) * len(((r.get("values") or [[]])[0]))
                for r in ranges
            )
            return {
                "code": 0,
                "data": {
                    "spreadsheetToken": self.fake_ss_token,
                    "revision": 7,
                    "responses": [
                        {
                            "updatedRange": ranges[0]["range"] if ranges else "",
                            "updatedRows": len(ranges[0]["values"]) if ranges else 0,
                            "updatedColumns": (
                                len(ranges[0]["values"][0]) if ranges and ranges[0]["values"] else 0
                            ),
                            "updatedCells": total_cells,
                        }
                    ],
                },
            }
        return {"code": -1, "msg": f"mock: unhandled {method} {path}"}


# ── 测试 harness ─────────────────────────────────────────────────────────

PASS = "\033[32m[PASS]\033[0m"
FAIL = "\033[31m[FAIL]\033[0m"

results: list[tuple[bool, str]] = []


def check(cond: bool, name: str, detail: str = "") -> None:
    results.append((cond, name))
    tag = PASS if cond else FAIL
    extra = f"  ↳ {detail}" if detail else ""
    print(f"{tag} {name}{extra}")


def run_main(
    file_path: Path,
    *,
    title: str,
    folder: str | None,
    fmt: str,
    plain: bool = True,  # 默认跳过美化，让既有测试只关注数据路径（4 次 API 调用）
    literal: bool = False,
) -> tuple[int, str, str]:
    """跑 us.main()，捕获 stdout/stderr，返回 (exit_code, stdout, stderr)。
    复刻 entry-point 的 try/except 行为：未捕获异常 → exit 1 + 错误打到 stderr。
    """
    argv = ["upload-sheet.py", str(file_path), "--title", title, "--format", fmt]
    if folder:
        argv += ["--folder", folder]
    if plain:
        argv.append("--plain")
    if literal:
        argv.append("--literal")
    old_argv = sys.argv
    sys.argv = argv
    out, err = io.StringIO(), io.StringIO()
    code = 0
    try:
        with redirect_stdout(out), redirect_stderr(err):
            try:
                code = us.main()
            except SystemExit as e:
                code = int(e.code or 0)
            except Exception as e:
                # 复刻 upload-sheet.py 入口的异常处理
                print(f"[ERR] {e}", file=sys.stderr)
                code = 1
    finally:
        sys.argv = old_argv
    return code, out.getvalue(), err.getvalue()


def case_csv_full_pipeline() -> None:
    print("\n── case 1: CSV 全链路（含数字类型 + 含逗号字段） ──")
    fake = FakeFeishu()
    us._http_json = fake  # type: ignore[attr-defined]
    os.environ["FEISHU_APP_ID"] = "cli_TEST_app"
    os.environ["FEISHU_APP_SECRET"] = "TEST_secret_xxxx"

    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as f:
        f.write('姓名,部门,Q1销售,达成率\n')
        f.write('张三,华东,1234.5,98.2\n')
        f.write('李四,华南,5678,105.0\n')
        f.write('王五,华北,890,72.5\n')
        f.write('"赵, 六","西\n南",-200,15\n')  # 含逗号 + 多行 + 负数
        path = Path(f.name)

    try:
        code, stdout, stderr = run_main(path, title="测试CSV", folder=None, fmt="auto")
    finally:
        path.unlink()

    check(code == 0, "exit code = 0", f"实际={code}; stderr={stderr.strip()[-200:]}")
    check(fake.fake_url in stdout, "stdout 含 sheet URL", f"stdout={stdout.strip()}")
    check(len(fake.calls) == 4, "正好 4 次 API 调用", f"实际={len(fake.calls)}")

    if len(fake.calls) >= 4:
        # 调用 1: tenant_access_token
        m, p, b = fake.calls[0]
        check(
            m == "POST" and p.endswith("/tenant_access_token/internal"),
            "call[0] = POST tenant_access_token",
            f"got {m} {p}",
        )
        check(
            b == {"app_id": "cli_TEST_app", "app_secret": "TEST_secret_xxxx"},
            "call[0] body 含 app_id/app_secret",
            f"got {b}",
        )
        # 调用 2: 创建表格
        m, p, b = fake.calls[1]
        check(
            m == "POST" and p == "/open-apis/sheets/v3/spreadsheets",
            "call[1] = POST sheets/v3/spreadsheets",
            f"got {m} {p}",
        )
        check(b == {"title": "测试CSV"}, "call[1] body 仅含 title（未传 folder）", f"got {b}")
        # 调用 3: 查 sheet_id
        m, p, b = fake.calls[2]
        check(
            m == "GET" and "/sheets/query" in p and fake.fake_ss_token in p,
            "call[2] = GET sheets/query 用 spreadsheet_token",
            f"got {m} {p}",
        )
        # 调用 4: 写值
        m, p, b = fake.calls[3]
        check(
            m == "POST" and p.endswith("/values_batch_update") and fake.fake_ss_token in p,
            "call[4] = POST values_batch_update",
            f"got {m} {p}",
        )
        ranges = (b or {}).get("valueRanges") or []
        check(len(ranges) == 1, "valueRanges 长度 = 1", f"got {len(ranges)}")
        if ranges:
            r0 = ranges[0]
            expected_range = f"{fake.fake_sheet_id}!A1:D5"  # 5 rows × 4 cols
            check(r0.get("range") == expected_range, f"range = {expected_range}", f"got {r0.get('range')}")
            vals = r0.get("values") or []
            check(len(vals) == 5, "5 行数据", f"got {len(vals)}")
            check(all(len(row) == 4 for row in vals), "每行 4 列（已右补齐）", "")
            # 数字类型保真
            check(
                vals[1] == ["张三", "华东", 1234.5, 98.2],
                "row[1] 数字字段是 float（USER_ENTERED 才能识别）",
                f"got {vals[1]} types={[type(c).__name__ for c in vals[1]]}",
            )
            check(
                vals[2] == ["李四", "华南", 5678, 105.0],
                "row[2]: 5678→int / 105.0→float",
                f"got {vals[2]} types={[type(c).__name__ for c in vals[2]]}",
            )
            check(
                vals[4] == ["赵, 六", "西\n南", -200, 15],
                "row[4]: 含逗号/多行/负数全保真",
                f"got {vals[4]}",
            )
            check(
                b.get("valueInputOption") == "USER_ENTERED",
                "valueInputOption = USER_ENTERED",
                f"got {b.get('valueInputOption')}",
            )


def case_md_with_folder() -> None:
    print("\n── case 2: Markdown 表格 + folder_token ──")
    fake = FakeFeishu()
    us._http_json = fake  # type: ignore[attr-defined]

    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as f:
        f.write("# 报表\n\n")
        f.write("引言段落\n\n")
        f.write("| col1 | col2 | col3 |\n")
        f.write("| :--- | :---: | ---: |\n")
        f.write("| a \\| b | 1 | 2.5 |\n")  # 转义竖线
        f.write("| c | 3 | 4 |\n\n")
        f.write("结尾段落（不应进入表格）\n")
        path = Path(f.name)

    try:
        code, stdout, stderr = run_main(path, title="测试MD", folder="fldcn_FAKE", fmt="md")
    finally:
        path.unlink()

    check(code == 0, "exit code = 0", f"stderr={stderr.strip()[-200:]}")
    if len(fake.calls) >= 2:
        b = fake.calls[1][2]
        check(
            b == {"title": "测试MD", "folder_token": "fldcn_FAKE"},
            "create body 包含 folder_token",
            f"got {b}",
        )
    if len(fake.calls) >= 4:
        b = fake.calls[3][2]
        ranges = (b or {}).get("valueRanges") or []
        if ranges:
            vals = ranges[0].get("values") or []
            check(len(vals) == 3, "MD 表格解析为 3 行（表头 + 2 数据）", f"got {len(vals)}")
            check(
                vals[1] == ["a | b", 1, 2.5],
                "转义竖线 \\| 还原为 | + 数字识别",
                f"got {vals[1]}",
            )
            check(
                ranges[0]["range"] == "sht1234!A1:C3",
                "range = sht1234!A1:C3 (3 行 × 3 列)",
                f"got {ranges[0]['range']}",
            )


def case_tsv() -> None:
    print("\n── case 3: TSV ──")
    fake = FakeFeishu()
    us._http_json = fake  # type: ignore[attr-defined]

    with tempfile.NamedTemporaryFile("w", suffix=".tsv", delete=False, encoding="utf-8") as f:
        f.write("a\tb\tc\n1\t2\t3\n")
        path = Path(f.name)

    try:
        code, stdout, stderr = run_main(path, title="TSV", folder=None, fmt="auto")
    finally:
        path.unlink()

    check(code == 0, "exit code = 0", f"stderr={stderr.strip()[-200:]}")
    if len(fake.calls) >= 4:
        b = fake.calls[3][2]
        ranges = (b or {}).get("valueRanges") or []
        if ranges:
            vals = ranges[0].get("values") or []
            check(vals == [["a", "b", "c"], [1, 2, 3]], "TSV 二维数组正确", f"got {vals}")


def case_error_propagation() -> None:
    print("\n── case 4: 飞书错误码透传（mock 返 99991672） ──")

    class ScopeFailFeishu(FakeFeishu):
        def __call__(self, method, path, *, token=None, body=None, timeout=30):
            if path == "/open-apis/sheets/v3/spreadsheets":
                self.calls.append((method, path, body))
                return {"code": 99991672, "msg": "Insufficient scope"}
            return super().__call__(method, path, token=token, body=body, timeout=timeout)

    fake = ScopeFailFeishu()
    us._http_json = fake  # type: ignore[attr-defined]

    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as f:
        f.write("x,y\n1,2\n")
        path = Path(f.name)

    try:
        code, stdout, stderr = run_main(path, title="x", folder=None, fmt="auto")
    finally:
        path.unlink()

    check(code != 0, "scope 错误 → 非 0 退出码", f"got code={code}")
    check("99991672" in stderr, "stderr 含错误码 99991672", f"stderr={stderr.strip()[-300:]}")
    check(
        "Insufficient scope" in stderr,
        "stderr 含原 msg 透传",
        f"stderr={stderr.strip()[-300:]}",
    )


def case_styling_pipeline() -> None:
    """非 --plain 模式：除 4 次基础调用，还要触发 PUT /style + POST /sheets_batch_update + POST /dimension_range。"""
    print("\n── case 5: 美化路径（表头样式 + 冻结 + 列宽） ──")
    fake = FakeFeishu()
    us._http_json = fake  # type: ignore[attr-defined]

    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as f:
        f.write("姓名,Q1,Q2\n张三,100,200\n李四,300,400\n")
        path = Path(f.name)
    try:
        code, stdout, stderr = run_main(path, title="美化", folder=None, fmt="auto", plain=False)
    finally:
        path.unlink()

    check(code == 0, "exit code = 0", f"stderr={stderr.strip()[-200:]}")

    methods_paths = [(m, p) for (m, p, _) in fake.calls]
    style_calls = [(m, p) for (m, p) in methods_paths if p.endswith("/style")]
    freeze_calls = [(m, p) for (m, p) in methods_paths if p.endswith("/sheets_batch_update")]
    dim_calls = [(m, p) for (m, p) in methods_paths if p.endswith("/dimension_range")]

    check(len(style_calls) == 1 and style_calls[0][0] == "PUT", "1 次 PUT /style", f"got {style_calls}")
    check(len(freeze_calls) == 1 and freeze_calls[0][0] == "POST", "1 次 POST /sheets_batch_update", f"got {freeze_calls}")
    check(len(dim_calls) >= 1, "至少 1 次 POST /dimension_range", f"got {dim_calls}")

    # 检查 style body
    style_body = next(b for (m, p, b) in fake.calls if p.endswith("/style"))
    s = (style_body or {}).get("appendStyle", {})
    check(s.get("range") == "sht1234!A1:C1", "style range = sht1234!A1:C1（首行 3 列）", f"got {s.get('range')}")
    check(s.get("style", {}).get("font", {}).get("bold") is True, "style.font.bold = True", f"got {s.get('style')}")
    check(s.get("style", {}).get("backColor", "").startswith("#"), "style.backColor 是十六进制", f"got {s.get('style', {}).get('backColor')}")

    # 检查 freeze body
    freeze_body = next(b for (m, p, b) in fake.calls if p.endswith("/sheets_batch_update"))
    props = (freeze_body or {}).get("requests", [{}])[0].get("updateSheet", {}).get("properties", {})
    check(props.get("frozenRowCount") == 1, "frozenRowCount = 1", f"got {props}")
    check(props.get("sheetId") == "sht1234", "sheetId 透传正确", f"got sheetId={props.get('sheetId')}")

    # 检查 dimension body
    dim_body = next(b for (m, p, b) in fake.calls if p.endswith("/dimension_range"))
    d = (dim_body or {}).get("dimension", {})
    check(d.get("majorDimension") == "COLUMNS", "dimension.majorDimension = COLUMNS", f"got {d}")
    fixed = (dim_body or {}).get("dimensionProperties", {}).get("fixedSize")
    check(isinstance(fixed, int) and 60 <= fixed <= 300, f"fixedSize 在 [60,300] 像素之间", f"got {fixed}")


def case_literal_mode() -> None:
    """--literal：007 / =SUM(A1) / 1.23e10 全部当字符串原样上传，且 valueInputOption=RAW。"""
    print("\n── case 6: --literal 模式（保留原始字符串）──")
    fake = FakeFeishu()
    us._http_json = fake  # type: ignore[attr-defined]

    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as f:
        f.write("id,公式,科学计数\n007,=SUM(A1:A3),1.23e10\n")
        path = Path(f.name)
    try:
        code, stdout, stderr = run_main(path, title="literal", folder=None, fmt="auto", literal=True)
    finally:
        path.unlink()

    check(code == 0, "exit code = 0", f"stderr={stderr.strip()[-200:]}")
    # 只看 values_batch_update 那次调用
    write_call = next(b for (m, p, b) in fake.calls if p.endswith("/values_batch_update"))
    check(write_call.get("valueInputOption") == "RAW", "valueInputOption = RAW", f"got {write_call.get('valueInputOption')}")
    vals = (write_call.get("valueRanges") or [{}])[0].get("values") or []
    check(
        vals[1] == ["007", "=SUM(A1:A3)", "1.23e10"],
        "literal 模式：007 / =SUM / 1.23e10 全部原样保留",
        f"got {vals[1]}",
    )


def case_default_mode_protections() -> None:
    """默认（非 literal）模式：007 保前导零、=SUM 加 ' 防执行、1.23e10 → float。"""
    print("\n── case 7: 默认模式数据保护（007/=SUM/1.23e10）──")
    fake = FakeFeishu()
    us._http_json = fake  # type: ignore[attr-defined]

    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as f:
        f.write("id,公式,科学计数,普通\n007,=SUM(A1:A3),1.23e10,42\n")
        path = Path(f.name)
    try:
        code, stdout, stderr = run_main(path, title="protect", folder=None, fmt="auto")
    finally:
        path.unlink()

    check(code == 0, "exit code = 0", f"stderr={stderr.strip()[-200:]}")
    write_call = next(b for (m, p, b) in fake.calls if p.endswith("/values_batch_update"))
    check(write_call.get("valueInputOption") == "USER_ENTERED", "valueInputOption = USER_ENTERED", f"got {write_call.get('valueInputOption')}")
    vals = (write_call.get("valueRanges") or [{}])[0].get("values") or []
    row1 = vals[1]
    check(row1[0] == "007", "B1 修复：007 保留前导零", f"got {row1[0]!r} type={type(row1[0]).__name__}")
    check(row1[1] == "'=SUM(A1:A3)", "B3 修复：=公式 加 ' 前缀防注入", f"got {row1[1]!r}")
    check(row1[2] == 12300000000.0 and isinstance(row1[2], float), "B2 修复：1.23e10 → float", f"got {row1[2]!r} type={type(row1[2]).__name__}")
    check(row1[3] == 42 and isinstance(row1[3], int), "正常整数仍识别", f"got {row1[3]!r} type={type(row1[3]).__name__}")


def main() -> int:
    print("=" * 60)
    print("upload-sheet.py 端到端集成测试（mock 飞书 API）")
    print("=" * 60)
    case_csv_full_pipeline()
    case_md_with_folder()
    case_tsv()
    case_error_propagation()
    case_styling_pipeline()
    case_literal_mode()
    case_default_mode_protections()

    total = len(results)
    passed = sum(1 for ok, _ in results if ok)
    print()
    print("=" * 60)
    print(f"总结: {passed}/{total} 通过")
    print("=" * 60)
    if passed != total:
        print("\n失败用例:")
        for ok, name in results:
            if not ok:
                print(f"  - {name}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
