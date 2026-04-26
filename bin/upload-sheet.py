#!/usr/bin/env python3
"""
upload-sheet.py — 把单张表格上传到飞书电子表格（Sheets，不是 docx 里的 markdown 表格）

支持输入格式：
  - .csv          标准逗号分隔
  - .tsv          制表符分隔
  - .md / .markdown   只取文件里第一张 GFM 表格（| col | col |）
  - 显式 --format 覆盖自动推断

链路：
  1. 解析输入文件 → 二维数组（第一行视为表头）
  2. POST /sheets/v3/spreadsheets             创建空表格
  3. GET  /sheets/v3/spreadsheets/{tok}/sheets/query   查默认 sheet_id
  4. POST /sheets/v2/spreadsheets/{tok}/values_batch_update   写入数据
  5. 打印飞书 sheet URL

权限：应用身份需要 `sheets:spreadsheet`（或 `sheets:spreadsheet:create` + 写权限），
     若指定 --folder，还需要 `drive:drive`。

用法：
  python3 upload-sheet.py data.csv --title "Q1 销售"
  python3 upload-sheet.py table.md --title "演示" --folder fldcn_xxx
  python3 upload-sheet.py data.csv --dry-run     # 解析 + 打印请求体，不真发请求

环境变量：
  FEISHU_APP_ID, FEISHU_APP_SECRET   (必需，--dry-run 时仍需要因为下一步要建 sheet)
  FEISHU_HOST                        (可选，默认 open.feishu.cn)

限制（飞书侧）：
  - 单次 values_batch_update：5000 行 × 100 列
  - 单元格 ≤ 40000 字符
  超出会在调用前 fail-fast 并提示拆分。
"""
from __future__ import annotations  # 让 `str | None` 等注解延迟求值，兼容 Python 3.7+

import argparse
import csv
import io
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Iterable

FEISHU_HOST = os.environ.get("FEISHU_HOST", "open.feishu.cn")
MAX_ROWS = 5000
MAX_COLS = 100
MAX_CELL_CHARS = 40000


# ─── HTTP / Auth ────────────────────────────────────────────────────────

# 飞书已知 error code → 修复指引（指向 docs/error-codes.md 里具体段落）
_ERROR_HINTS = {
    99991672: "应用身份 scope 不足。开放平台 → 应用 → 权限管理 → 加 sheets:spreadsheet → 发新版本。详见 docs/error-codes.md#99991672",
    131006: "权限不够。读：让 wiki 所有者把应用加为成员；写：加 edit 权限。详见 docs/error-codes.md#131006",
    131005: "资源不存在或无权访问。检查 token 拼写，并在浏览器里能否打开。详见 docs/error-codes.md#131005",
    1254040: "文档级协作者权限不足。文档分享 → 添加协作者 → 应用 → 可编辑。详见 docs/error-codes.md#1254040",
    20027: "OAuth scope 超出应用拥有的 scope。详见 docs/error-codes.md#20027",
    20029: "redirect_uri 不匹配。详见 docs/error-codes.md#20029",
}


def _format_error(code: int, msg: str, method: str, path: str) -> str:
    hint = _ERROR_HINTS.get(code, "")
    base = f"飞书 API 失败 [{method} {path}]：code={code} msg={msg}"
    return f"{base}\n  ↳ 修复建议：{hint}" if hint else base


# 默认重试策略：HTTP 5xx 和 429（限流）才重试，其它一次性失败
_RETRY_HTTP_CODES = {429, 500, 502, 503, 504}
_DEFAULT_MAX_RETRIES = 2  # 总共最多 1+2=3 次尝试


def _http_json(
    method: str,
    path: str,
    *,
    token: str | None = None,
    body: Any | None = None,
    timeout: int = 30,
    max_retries: int = _DEFAULT_MAX_RETRIES,
) -> dict:
    url = f"https://{FEISHU_HOST}{path}"
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "User-Agent": "feishu-sync/0.2 (upload-sheet)",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None

    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            try:
                payload = json.loads(e.read().decode("utf-8"))
            except Exception:
                payload = {"code": e.code, "msg": e.reason}
            # 只有 5xx / 429 重试，其它（4xx 业务错误）一次性退出
            if e.code in _RETRY_HTTP_CODES and attempt < max_retries:
                # 指数退避：500ms, 1500ms, ...
                wait = 0.5 * (3 ** attempt)
                print(
                    f"[retry] HTTP {e.code} {method} {path}，{wait:.1f}s 后第 {attempt+2}/{max_retries+1} 次尝试",
                    file=sys.stderr,
                )
                import time as _t
                _t.sleep(wait)
                last_error = e
                continue
            raise RuntimeError(
                f"HTTP {e.code} {method} {path}: code={payload.get('code')} msg={payload.get('msg')}"
            )
        except urllib.error.URLError as e:
            # 网络层错误（DNS / 连接超时）也重试
            if attempt < max_retries:
                wait = 0.5 * (3 ** attempt)
                print(
                    f"[retry] 网络错误 {method} {path}: {e.reason}；{wait:.1f}s 后第 {attempt+2}/{max_retries+1} 次尝试",
                    file=sys.stderr,
                )
                import time as _t
                _t.sleep(wait)
                last_error = e
                continue
            raise RuntimeError(f"网络错误 {method} {path}: {e.reason}")

    # 理论上走不到，因为 raise 在循环内
    if last_error:
        raise RuntimeError(f"重试 {max_retries+1} 次后仍失败 {method} {path}: {last_error}")
    raise RuntimeError(f"未知错误 {method} {path}")


def get_tenant_token(app_id: str, app_secret: str) -> str:
    path = "/open-apis/auth/v3/tenant_access_token/internal"
    r = _http_json("POST", path, body={"app_id": app_id, "app_secret": app_secret})
    if r.get("code") != 0:
        raise RuntimeError(_format_error(r.get("code", -1), r.get("msg", ""), "POST", path))
    return r["tenant_access_token"]


# ─── 解析：CSV / TSV / Markdown table → 2D array ───────────────────────

def parse_csv(text: str, delimiter: str = ",") -> list[list[str]]:
    rows = list(csv.reader(io.StringIO(text), delimiter=delimiter))
    # 去掉完全空行（reader 在尾部空行会产生 []）
    return [row for row in rows if any(cell.strip() != "" for cell in row)]


def parse_md_table(text: str) -> list[list[str]]:
    """
    抽出 markdown 文本里**第一张** GFM 表格，返回 2D 数组（表头 + 数据行）。
    GFM 表格规则：
      | header | header |
      | ------ | ------ |
      | data   | data   |
    分隔行（第二行）可包含冒号控制对齐，会被丢弃。
    """
    lines = text.splitlines()
    # 找第一行 |...| 形式
    start = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|") and stripped.count("|") >= 2:
            # 下一行必须是分隔行
            if i + 1 < len(lines):
                sep = lines[i + 1].strip()
                if re.fullmatch(r"\|[\s:|\-]+\|", sep) and "-" in sep:
                    start = i
                    break
    if start is None:
        raise ValueError("未在 markdown 中找到 GFM 表格（需要 | col | col | 格式 + 分隔行）")

    rows: list[list[str]] = []
    # 表头
    header = _split_md_row(lines[start])
    rows.append(header)
    # 数据行：从 start+2 开始，遇到非表格行停下
    for line in lines[start + 2:]:
        s = line.strip()
        if not (s.startswith("|") and s.endswith("|")):
            break
        cells = _split_md_row(line)
        # 对齐到表头长度
        if len(cells) < len(header):
            cells = cells + [""] * (len(header) - len(cells))
        elif len(cells) > len(header):
            cells = cells[: len(header)]
        rows.append(cells)
    return rows


def _split_md_row(line: str) -> list[str]:
    """切分一行 markdown 表格，处理转义的 \\|"""
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    # 用 placeholder 处理转义竖线
    s = s.replace(r"\|", "\x00")
    cells = [c.strip().replace("\x00", "|") for c in s.split("|")]
    return cells


def parse_input(file_path: Path, fmt: str) -> list[list[str]]:
    text = file_path.read_text(encoding="utf-8")
    if fmt == "csv":
        return parse_csv(text, ",")
    if fmt == "tsv":
        return parse_csv(text, "\t")
    if fmt == "md":
        return parse_md_table(text)
    raise ValueError(f"未知 format: {fmt}")


def detect_format(file_path: Path, override: str | None) -> str:
    if override and override != "auto":
        return override
    suf = file_path.suffix.lower()
    if suf == ".csv":
        return "csv"
    if suf == ".tsv":
        return "tsv"
    if suf in (".md", ".markdown"):
        return "md"
    raise ValueError(
        f"无法从扩展名推断格式：{file_path.name}；显式传 --format csv|tsv|md"
    )


# ─── 数据 → cell value（保留数字类型）──────────────────────────────────

# 整数 / 小数 / 科学计数法。前导零的整数会被显式排除（保留为字符串，避免破坏 ID/邮编）。
_INT_RE = re.compile(r"^-?(0|[1-9]\d*)$")
_DEC_RE = re.compile(r"^-?\d+\.\d+$")
_SCI_RE = re.compile(r"^-?\d+(\.\d+)?[eE][+-]?\d+$")


def coerce_cell(s: str) -> Any:
    """字符串 → 数字（如果纯数字），否则原样字符串。

    规则（顺序敏感）：
    - "" → ""（空保留）
    - 整数（不含前导零）→ int
    - 小数 → float
    - 科学计数法 → float
    - 其它 → 原样 str（包括 "007"/"42%"/日期串/中文/=公式 等）
    """
    if s == "":
        return ""
    if _INT_RE.fullmatch(s):
        try:
            return int(s)
        except ValueError:
            return s
    if _DEC_RE.fullmatch(s) or _SCI_RE.fullmatch(s):
        try:
            return float(s)
        except ValueError:
            return s
    return s


def escape_formula(s: str) -> str:
    """对以 `=`/`+`/`-`/`@` 开头的字符串加 `'` 前缀，防止 USER_ENTERED 模式把它当公式执行。

    注意：纯数字的 `-100` 不会走到这里（已在 coerce_cell 里转成 int），
    所以这里的 `-`/`+` 前缀只对非数字字符串（如 `-N/A`、`+200%`）生效。
    """
    if not s or not isinstance(s, str):
        return s
    if s[0] in ("=", "+", "-", "@"):
        return "'" + s
    return s


def coerce_rows(rows: Iterable[Iterable[str]], literal: bool = False) -> list[list[Any]]:
    """coerce 每个 cell。literal=True 时所有内容当字符串原样保留（含公式样字符串）。"""
    if literal:
        return [[c for c in row] for row in rows]
    out: list[list[Any]] = []
    for row in rows:
        new_row: list[Any] = []
        for c in row:
            v = coerce_cell(c)
            if isinstance(v, str):
                v = escape_formula(v)
            new_row.append(v)
        out.append(new_row)
    return out


def validate_size(rows: list[list[Any]]) -> None:
    if not rows:
        raise ValueError("解析结果为空（0 行），拒绝上传")
    if len(rows) > MAX_ROWS:
        raise ValueError(
            f"行数 {len(rows)} 超过单次写入上限 {MAX_ROWS}；请拆分文件后分多次上传"
        )
    max_cols = max(len(r) for r in rows)
    if max_cols > MAX_COLS:
        raise ValueError(
            f"列数 {max_cols} 超过单次写入上限 {MAX_COLS}；请减少列或转置"
        )
    for ri, row in enumerate(rows):
        for ci, cell in enumerate(row):
            if isinstance(cell, str) and len(cell) > MAX_CELL_CHARS:
                raise ValueError(
                    f"第 {ri+1} 行第 {ci+1} 列单元格长度 {len(cell)} 超过 {MAX_CELL_CHARS}"
                )


# ─── A1 notation: column index → letter(s) ──────────────────────────────

def col_letter(n: int) -> str:
    """1 → A, 26 → Z, 27 → AA"""
    if n < 1:
        raise ValueError("column index must be ≥ 1")
    s = ""
    while n > 0:
        n, r = divmod(n - 1, 26)
        s = chr(ord("A") + r) + s
    return s


def build_range(sheet_id: str, n_rows: int, n_cols: int) -> str:
    return f"{sheet_id}!A1:{col_letter(n_cols)}{n_rows}"


# ─── 飞书 Sheets API 封装 ──────────────────────────────────────────────

_TOKEN_RE = re.compile(r"^[A-Za-z0-9]{20,}$")


def parse_spreadsheet_token(url_or_token: str) -> str:
    """从 sheet URL 或 raw token 抽出 spreadsheet_token。

    支持的输入：
      https://my.feishu.cn/sheets/XYZabc123
      https://xxx.feishu.cn/sheets/XYZabc123?from=open_search
      https://open.larksuite.com/sheets/XYZabc123#anchor
      XYZabc123                    （raw token，27 字符通常）
    """
    s = url_or_token.strip()
    if "/sheets/" in s:
        # 取 /sheets/ 后面到下一个 ? # / 之前
        after = s.split("/sheets/", 1)[1]
        for stop in ("?", "#", "/"):
            idx = after.find(stop)
            if idx >= 0:
                after = after[:idx]
        s = after
    if not _TOKEN_RE.fullmatch(s):
        raise ValueError(
            f"无法从 {url_or_token!r} 解析出 spreadsheet_token；"
            f"期望形如 'https://xxx.feishu.cn/sheets/<token>' 或 raw token"
        )
    return s


def create_spreadsheet(token: str, title: str, folder_token: str | None) -> dict:
    body: dict = {"title": title}
    if folder_token:
        body["folder_token"] = folder_token
    path = "/open-apis/sheets/v3/spreadsheets"
    r = _http_json("POST", path, token=token, body=body)
    if r.get("code") != 0:
        raise RuntimeError(_format_error(r.get("code", -1), r.get("msg", ""), "POST", path))
    return r["data"]["spreadsheet"]


def query_default_sheet_id(token: str, spreadsheet_token: str) -> str:
    path = f"/open-apis/sheets/v3/spreadsheets/{spreadsheet_token}/sheets/query"
    r = _http_json("GET", path, token=token)
    if r.get("code") != 0:
        raise RuntimeError(_format_error(r.get("code", -1), r.get("msg", ""), "GET", path))
    sheets = (r.get("data") or {}).get("sheets") or []
    if not sheets:
        raise RuntimeError("新建 spreadsheet 没有默认 sheet（异常）")
    sid = sheets[0].get("sheet_id")
    if not sid:
        raise RuntimeError(f"sheets[0] 缺 sheet_id：{sheets[0]}")
    return sid


# ─── 美观度增强：表头样式 / 冻结首行 / 列宽自适应 ─────────────────────

DEFAULT_HEADER_BG = "#E8F0FE"      # 浅蓝灰，比纯白高亮但不刺眼，深浅模式都能看清
# 飞书 v2 style API 实测：fontSize 必须是 "字号pt/行高倍数" 格式字符串（错误消息有误导）
# 直接传 int 11 会报 "must between 9 and 36"，但其实是字符串解析失败
DEFAULT_HEADER_FONT_SIZE = "11pt/1.5"


def apply_header_style(
    token: str,
    spreadsheet_token: str,
    sheet_id: str,
    n_cols: int,
    *,
    bg: str = DEFAULT_HEADER_BG,
) -> dict:
    """给首行（A1:??1）加粗 + 加底色 + 居中。失败不致命，调用方决定是否 raise。"""
    rng = f"{sheet_id}!A1:{col_letter(n_cols)}1"
    body = {
        "appendStyle": {
            "range": rng,
            "style": {
                "font": {"bold": True, "fontSize": DEFAULT_HEADER_FONT_SIZE},
                "backColor": bg,
                "hAlign": 1,  # 0 左 / 1 中 / 2 右
                "vAlign": 1,
            },
        }
    }
    path = f"/open-apis/sheets/v2/spreadsheets/{spreadsheet_token}/style"
    r = _http_json("PUT", path, token=token, body=body)
    if r.get("code") != 0:
        raise RuntimeError(_format_error(r.get("code", -1), r.get("msg", ""), "PUT", path))
    return r


def freeze_rows(
    token: str, spreadsheet_token: str, sheet_id: str, count: int = 1
) -> dict:
    """冻结首 N 行。"""
    body = {
        "requests": [
            {
                "updateSheet": {
                    "properties": {
                        "sheetId": sheet_id,
                        "frozenRowCount": count,
                    }
                }
            }
        ]
    }
    path = f"/open-apis/sheets/v2/spreadsheets/{spreadsheet_token}/sheets_batch_update"
    r = _http_json("POST", path, token=token, body=body)
    if r.get("code") != 0:
        raise RuntimeError(_format_error(r.get("code", -1), r.get("msg", ""), "POST", path))
    return r


def _visual_width_chars(s: str) -> int:
    """估算字符串视觉宽度，CJK/全角按 2 算，其它按 1 算。"""
    n = 0
    for c in s:
        # CJK 中日韩统一表意 + 假名 + 韩文谚文音节
        if (
            "一" <= c <= "鿿"
            or "぀" <= c <= "ヿ"
            or "가" <= c <= "힯"
            or "＀" <= c <= "￯"  # 全角符号
        ):
            n += 2
        else:
            n += 1
    return n


def compute_column_widths(
    rows: list[list[Any]], *, min_w: int = 80, max_w: int = 300, char_px: int = 8
) -> list[int]:
    """根据每列最大单元格宽度估算像素宽。"""
    if not rows:
        return []
    n_cols = max(len(r) for r in rows)
    widths: list[int] = []
    for ci in range(n_cols):
        col_max = 0
        for row in rows:
            if ci < len(row):
                s = str(row[ci]) if row[ci] is not None else ""
                col_max = max(col_max, _visual_width_chars(s))
        # 加 24px 内边距 + 表头加粗系数 1.1
        px = int(col_max * char_px * 1.1) + 24
        widths.append(max(min_w, min(max_w, px)))
    return widths


def set_column_widths(
    token: str, spreadsheet_token: str, sheet_id: str, widths: list[int]
) -> list[dict]:
    """把同宽度的连续列合并成一次 dimension_range 调用，减少 API 次数。

    飞书 dimension_range 实测语义（关键!!!）：
      - **HTTP 方法是 PUT**（不是 POST，POST 会走到别的 handler 报误导性错误）
      - startIndex/endIndex 是 **1-indexed 半开区间** [startIndex, endIndex)
      - 比如设置第 1~3 列：startIndex=1, endIndex=4
      - 单列：startIndex=1, endIndex=2
    """
    results: list[dict] = []
    if not widths:
        return results
    n = len(widths)
    i = 0
    while i < n:
        j = i + 1
        while j < n and widths[j] == widths[i]:
            j += 1
        # i..j-1 是 0-indexed 的列索引；转 1-indexed 半开 → [i+1, j+1)
        body = {
            "dimension": {
                "sheetId": sheet_id,
                "majorDimension": "COLUMNS",
                "startIndex": i + 1,
                "endIndex": j + 1,
            },
            "dimensionProperties": {"fixedSize": widths[i]},
        }
        path = f"/open-apis/sheets/v2/spreadsheets/{spreadsheet_token}/dimension_range"
        r = _http_json("PUT", path, token=token, body=body)
        if r.get("code") != 0:
            raise RuntimeError(_format_error(r.get("code", -1), r.get("msg", ""), "PUT", path))
        results.append(r)
        i = j
    return results


def values_batch_update(
    token: str,
    spreadsheet_token: str,
    sheet_id: str,
    values: list[list[Any]],
    *,
    literal: bool = False,
) -> dict:
    n_rows = len(values)
    n_cols = max(len(r) for r in values) if values else 0
    # 把短行右补空串，飞书要求 valueRanges 内部为矩形
    padded = [row + [""] * (n_cols - len(row)) for row in values]
    rng = build_range(sheet_id, n_rows, n_cols)
    body = {
        "valueRanges": [{"range": rng, "values": padded}],
        # USER_ENTERED：飞书按显示规则解释（数字/日期识别 + 公式执行）
        # RAW：全部当字符串原样写（适合 literal 模式，保护代码片段/ID）
        "valueInputOption": "RAW" if literal else "USER_ENTERED",
    }
    path = f"/open-apis/sheets/v2/spreadsheets/{spreadsheet_token}/values_batch_update"
    r = _http_json("POST", path, token=token, body=body)
    if r.get("code") != 0:
        raise RuntimeError(_format_error(r.get("code", -1), r.get("msg", ""), "POST", path))
    return r


# ─── 主流程 ────────────────────────────────────────────────────────────

def main() -> int:
    p = argparse.ArgumentParser(
        description="上传单张表格到飞书电子表格（Sheets）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("file", help="输入文件路径（.csv / .tsv / .md）")
    p.add_argument("--title", help="飞书 spreadsheet 标题，默认用文件名（不含扩展名）")
    p.add_argument("--folder", help="飞书 folder_token，省略则落到应用云空间根目录")
    p.add_argument(
        "--format",
        choices=["auto", "csv", "tsv", "md"],
        default="auto",
        help="输入格式，默认从扩展名推断",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="只解析 + 打印请求体，不真发任何 API 调用",
    )
    p.add_argument(
        "--literal",
        action="store_true",
        help="所有单元格当字符串原样上传，不做数字识别、不做公式转义（适合上传代码片段、保留前导零的 ID 等）",
    )
    p.add_argument(
        "--plain",
        action="store_true",
        help="跳过所有美化（不加表头样式、不冻结首行、不调列宽），只写数据",
    )
    p.add_argument(
        "--no-header-style",
        action="store_true",
        help="只跳过表头样式（保留冻结+列宽）",
    )
    p.add_argument(
        "--no-freeze",
        action="store_true",
        help="只跳过冻结首行（保留表头样式+列宽）",
    )
    p.add_argument(
        "--no-autosize",
        action="store_true",
        help="只跳过列宽自适应（保留表头样式+冻结）",
    )
    p.add_argument(
        "--header-bg",
        default=DEFAULT_HEADER_BG,
        help=f"表头背景色（默认 {DEFAULT_HEADER_BG}），形如 #RRGGBB",
    )
    p.add_argument(
        "--update",
        metavar="URL_OR_TOKEN",
        help="刷新已有 spreadsheet：传 sheet URL 或 spreadsheet_token，"
             "跳过 create + 跳过样式（假定已有表已经设置好），"
             "数据从 A1 覆盖写入。注意：这会替换该 sheet 现有内容",
    )
    args = p.parse_args()

    # --plain 是 umbrella，等价于同时给 --no-header-style --no-freeze --no-autosize
    if args.plain:
        args.no_header_style = True
        args.no_freeze = True
        args.no_autosize = True

    file_path = Path(args.file)
    if not file_path.is_file():
        print(f"[ERR] 文件不存在: {file_path}", file=sys.stderr)
        return 2

    fmt = detect_format(file_path, args.format)
    title = args.title or file_path.stem

    print(f"[parse] file={file_path} format={fmt} literal={args.literal}", file=sys.stderr)
    raw_rows = parse_input(file_path, fmt)
    rows = coerce_rows(raw_rows, literal=args.literal)
    validate_size(rows)
    n_rows, n_cols = len(rows), max(len(r) for r in rows)
    print(
        f"[parse] {n_rows} 行 × {n_cols} 列，预览首行: {rows[0][:5]}{'…' if n_cols > 5 else ''}",
        file=sys.stderr,
    )

    if args.dry_run:
        print(
            "[dry-run] 跳过 API 调用。将要发送的请求骨架：",
            file=sys.stderr,
        )
        plan = {
            "step1_create": {
                "method": "POST",
                "path": "/open-apis/sheets/v3/spreadsheets",
                "body": {"title": title, **({"folder_token": args.folder} if args.folder else {})},
            },
            "step2_query_sheet": {
                "method": "GET",
                "path": "/open-apis/sheets/v3/spreadsheets/<spreadsheet_token>/sheets/query",
            },
            "step3_write": {
                "method": "POST",
                "path": "/open-apis/sheets/v2/spreadsheets/<spreadsheet_token>/values_batch_update",
                "body_preview": {
                    "valueRanges[0].range": f"<sheet_id>!A1:{col_letter(n_cols)}{n_rows}",
                    "valueRanges[0].values_shape": [n_rows, n_cols],
                    "valueInputOption": "RAW" if args.literal else "USER_ENTERED",
                },
            },
        }
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0

    app_id = os.environ.get("FEISHU_APP_ID")
    app_secret = os.environ.get("FEISHU_APP_SECRET")
    if not app_id or not app_secret:
        print("[ERR] 必须设置 FEISHU_APP_ID / FEISHU_APP_SECRET", file=sys.stderr)
        return 2

    token = get_tenant_token(app_id, app_secret)
    print(f"[auth] tenant_access_token 获取成功（长度={len(token)}）", file=sys.stderr)

    if args.update:
        # 刷新已有 spreadsheet：跳过 create + 默认跳过样式
        spreadsheet_token = parse_spreadsheet_token(args.update)
        sheet_url = f"https://{FEISHU_HOST.replace('open.', 'my.')}/sheets/{spreadsheet_token}"
        print(f"[update] spreadsheet_token={spreadsheet_token}（跳过 create）", file=sys.stderr)
        # --update 隐含 --plain：假定已有表已经设置好样式
        args.no_header_style = True
        args.no_freeze = True
        args.no_autosize = True
    else:
        sheet_meta = create_spreadsheet(token, title, args.folder)
        spreadsheet_token = sheet_meta["spreadsheet_token"]
        sheet_url = sheet_meta.get("url", "")
        print(f"[create] spreadsheet_token={spreadsheet_token}", file=sys.stderr)

    sheet_id = query_default_sheet_id(token, spreadsheet_token)
    print(f"[query] default sheet_id={sheet_id}", file=sys.stderr)

    write_resp = values_batch_update(token, spreadsheet_token, sheet_id, rows, literal=args.literal)
    updated = ((write_resp.get("data") or {}).get("responses") or [{}])[0]
    print(
        f"[write] updatedCells={updated.get('updatedCells')} "
        f"updatedRange={updated.get('updatedRange')}",
        file=sys.stderr,
    )

    # 美化：每个 --no-X flag 独立控制（--plain 是 umbrella，会一次置 3 个 True）
    if n_rows >= 1 and n_cols >= 1:
        if not args.no_header_style:
            try:
                apply_header_style(token, spreadsheet_token, sheet_id, n_cols, bg=args.header_bg)
                print(f"[style] 表头样式已应用（{n_cols} 列加粗+背景色）", file=sys.stderr)
            except Exception as e:
                print(f"[warn] 表头样式失败（继续）：{e}", file=sys.stderr)

        if not args.no_freeze and n_rows >= 2:
            try:
                freeze_rows(token, spreadsheet_token, sheet_id, count=1)
                print("[style] 首行已冻结", file=sys.stderr)
            except Exception as e:
                print(f"[warn] 冻结首行失败（继续）：{e}", file=sys.stderr)

        if not args.no_autosize:
            try:
                widths = compute_column_widths(rows)
                set_column_widths(token, spreadsheet_token, sheet_id, widths)
                print(
                    f"[style] 列宽已自适应（{len(widths)} 列，宽度 min={min(widths)} max={max(widths)}）",
                    file=sys.stderr,
                )
            except Exception as e:
                print(f"[warn] 列宽设置失败（继续）：{e}", file=sys.stderr)

    print(f"[DONE] {sheet_url}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as e:
        print(f"[ERR] {e}", file=sys.stderr)
        sys.exit(1)
