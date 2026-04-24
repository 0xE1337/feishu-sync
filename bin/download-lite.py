#!/usr/bin/env python3
"""
download-lite.py — 纯 stdlib 下载飞书 wiki/docx（feishu-docx 不可用时的 fallback）

输出：
  <out>/<title>.md   每个 docx 一个文件，内容为 raw_content（纯文本，非严格 markdown）

用法：
  python3 download-lite.py <URL> [-o OUT_DIR] [--recursive]

限制（相比 feishu-docx export）：
  - 输出是 raw_content（飞书的纯文本端点），格式保真度低
  - 不下载图片附件
  - 表格会被压成纯文本
  够 agent 做 spec 审核用——review 依赖内容而非格式

环境变量：
  FEISHU_APP_ID, FEISHU_APP_SECRET   (必需)
  FEISHU_HOST                        (可选，默认 open.feishu.cn)

兼容性：Python 3.6+ stdlib only，不依赖 requests/feishu-docx/任何第三方包
"""
import argparse
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

FEISHU_HOST = os.environ.get("FEISHU_HOST", "open.feishu.cn")


def api(path, method="GET", body=None, token=None):
    url = "https://{}{}".format(FEISHU_HOST, path)
    headers = {"Content-Type": "application/json; charset=utf-8"}
    if token:
        headers["Authorization"] = "Bearer " + token
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get_tenant_token(app_id, app_secret):
    r = api(
        "/open-apis/auth/v3/tenant_access_token/internal",
        method="POST",
        body={"app_id": app_id, "app_secret": app_secret},
    )
    if r.get("code") != 0:
        raise RuntimeError("获取 tenant_access_token 失败: {}".format(r))
    return r["tenant_access_token"]


def extract_token(url):
    """从 URL 提取 (kind, token)，kind ∈ {'wiki', 'docx'}"""
    m = re.search(r"/(wiki|docx)/([A-Za-z0-9]+)", url)
    if not m:
        raise ValueError("URL 格式不支持（只识别 /wiki/<t> 或 /docx/<t>）: {}".format(url))
    return m.group(1), m.group(2)


def get_wiki_node(token, wiki_token):
    r = api(
        "/open-apis/wiki/v2/spaces/get_node?token={}".format(wiki_token),
        token=token,
    )
    if r.get("code") != 0:
        raise RuntimeError("wiki get_node 失败 token={}: {}".format(wiki_token, r))
    return r["data"]["node"]


def list_wiki_children(token, space_id, parent_token):
    nodes = []
    page_token = ""
    while True:
        path = (
            "/open-apis/wiki/v2/spaces/{}/nodes"
            "?parent_node_token={}&page_size=50"
        ).format(space_id, parent_token)
        if page_token:
            path += "&page_token=" + page_token
        r = api(path, token=token)
        if r.get("code") != 0:
            raise RuntimeError("list children 失败: {}".format(r))
        data = r.get("data", {})
        nodes.extend(data.get("items", []))
        if not data.get("has_more"):
            break
        page_token = data.get("page_token", "")
        if not page_token:
            break
    return nodes


def get_docx_raw(token, obj_token):
    r = api(
        "/open-apis/docx/v1/documents/{}/raw_content".format(obj_token),
        token=token,
    )
    if r.get("code") != 0:
        raise RuntimeError("raw_content 失败 obj={}: {}".format(obj_token, r))
    return r["data"].get("content", "")


_SAFE = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def sanitize(name):
    s = _SAFE.sub("_", name).strip()
    return s[:80] if s else "untitled"


def save_node(token, node, out_dir):
    title = node.get("title") or "untitled"
    obj_type = node.get("obj_type")
    obj_token = node.get("obj_token")
    fname = sanitize(title) + ".md"
    dest = out_dir / fname
    if obj_type == "docx" and obj_token:
        content = get_docx_raw(token, obj_token)
        dest.write_text(content, encoding="utf-8")
        print("[fetch] {}".format(dest), flush=True)
        return True
    else:
        print("[skip] {} (obj_type={})".format(title, obj_type), flush=True)
        return False


def walk(token, space_id, parent_token, out_dir, depth=0):
    children = list_wiki_children(token, space_id, parent_token)
    for ch in children:
        save_node(token, ch, out_dir)
        if ch.get("has_child"):
            walk(token, space_id, ch.get("node_token", ""), out_dir, depth + 1)


def main():
    p = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    p.add_argument("url", help="飞书 wiki 或 docx URL")
    p.add_argument("-o", "--out", default="./out", help="输出目录（默认 ./out）")
    p.add_argument(
        "--recursive",
        action="store_true",
        help="wiki 节点下递归拉子节点",
    )
    args = p.parse_args()

    app_id = os.environ.get("FEISHU_APP_ID")
    app_secret = os.environ.get("FEISHU_APP_SECRET")
    if not app_id or not app_secret:
        print("[ERR] 必须设置 FEISHU_APP_ID / FEISHU_APP_SECRET", file=sys.stderr)
        sys.exit(2)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    token = get_tenant_token(app_id, app_secret)
    kind, tok = extract_token(args.url)

    if kind == "docx":
        content = get_docx_raw(token, tok)
        dest = out_dir / (tok + ".md")
        dest.write_text(content, encoding="utf-8")
        print("[done] {}".format(dest))
        return

    # kind == "wiki"
    node = get_wiki_node(token, tok)
    space_id = node.get("space_id", "")
    save_node(token, node, out_dir)
    if args.recursive:
        if not space_id:
            print("[WARN] 节点无 space_id，无法递归", file=sys.stderr)
        else:
            walk(token, space_id, tok, out_dir)
    print("[done] 写入目录 {}".format(out_dir))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("[ERR] {}".format(e), file=sys.stderr)
        sys.exit(1)
