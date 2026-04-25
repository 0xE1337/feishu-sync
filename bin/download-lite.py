#!/usr/bin/env python3
"""
download-lite.py — 纯 stdlib 下载飞书 wiki/docx + cache 控制

输出：
  <out>/<title>.md            每个 docx 一个文件，内容为 raw_content（纯文本）
  <out>/.meta/<obj_token>.json  对应文件的 metadata（用于下次 cache 比对）

用法：
  python3 download-lite.py <URL> [-o OUT_DIR] [--recursive] [--cache-mode MODE]

子命令（供 download.sh 调用）：
  python3 download-lite.py --probe <URL> -o <OUT_DIR>
    探测鲜度，输出 JSON：{action, obj_token, title, sanitized_filename, file_path?, ...}
    退出码：0=cache 命中（无需下载）；1=需要下载；≥2=参数/网络错误

  python3 download-lite.py --save-meta <URL> -o <OUT_DIR> --file-path <PATH>
    在外部下载器（feishu-docx）下载完成后调用，记录本地 meta

cache-mode：
  auto    （默认）拉远端 metadata（revision_id / obj_edit_time），与本地 .meta 比对；
          一致跳过；不一致重新下载并更新 meta
  force   不检查鲜度，直接重下载并覆盖
  skip    本地有 .md + 有 meta 就直接打印路径；本地没有则报错（不联网）

限制（相比 feishu-docx export）：
  - 输出是 raw_content，格式保真度低
  - 不下载图片附件
  - 表格压成纯文本

环境变量：
  FEISHU_APP_ID, FEISHU_APP_SECRET   (必需)
  FEISHU_HOST                        (可选，默认 open.feishu.cn)

兼容性：Python 3.6+ stdlib only，不依赖 requests/feishu-docx/任何第三方包
"""
import argparse
import datetime
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

FEISHU_HOST = os.environ.get("FEISHU_HOST", "open.feishu.cn")
META_DIR_NAME = ".meta"


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


def get_docx_metadata(token, obj_token):
    """轻量调用，只拿 metadata（含 revision_id）"""
    r = api(
        "/open-apis/docx/v1/documents/{}".format(obj_token),
        token=token,
    )
    if r.get("code") != 0:
        raise RuntimeError("docx metadata 失败 obj={}: {}".format(obj_token, r))
    return r.get("data", {}).get("document", {}) or {}


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


def iso_now():
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


# ─── meta cache helpers ───────────────────────────────────────────────

def meta_dir(out_dir):
    d = out_dir / META_DIR_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def meta_path(out_dir, obj_token):
    return meta_dir(out_dir) / "{}.json".format(obj_token)


def load_meta(out_dir, obj_token):
    p = meta_path(out_dir, obj_token)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def save_meta_to_disk(out_dir, obj_token, meta):
    p = meta_path(out_dir, obj_token)
    p.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def fetch_remote_metadata(token, kind, tok):
    """拿远端 metadata（不下载正文），返回 dict"""
    if kind == "wiki":
        node = get_wiki_node(token, tok)
        obj_token = node.get("obj_token")
        meta = {
            "url_kind": "wiki",
            "wiki_token": tok,
            "obj_token": obj_token,
            "obj_type": node.get("obj_type"),
            "obj_edit_time": node.get("obj_edit_time"),
            "title": node.get("title") or "untitled",
            "space_id": node.get("space_id"),
        }
        # docx 类型再补一次精确的 revision_id
        if node.get("obj_type") == "docx" and obj_token:
            try:
                doc = get_docx_metadata(token, obj_token)
                meta["revision_id"] = doc.get("revision_id")
            except Exception:
                pass
        return meta
    else:
        # docx 直接访问
        doc = get_docx_metadata(token, tok)
        return {
            "url_kind": "docx",
            "obj_token": tok,
            "obj_type": "docx",
            "revision_id": doc.get("revision_id"),
            "title": doc.get("title") or "untitled",
        }


def is_fresh(local_meta, remote_meta):
    """本地 meta 与远端 meta 是否一致（cache 命中）"""
    if not local_meta:
        return False
    # 优先 revision_id（精确）
    r_rev = remote_meta.get("revision_id")
    l_rev = local_meta.get("revision_id")
    if r_rev is not None and l_rev is not None:
        return r_rev == l_rev
    # fallback obj_edit_time
    r_t = remote_meta.get("obj_edit_time")
    l_t = local_meta.get("obj_edit_time")
    if r_t is not None and l_t is not None:
        return r_t == l_t
    return False


def local_file_exists(out_dir, meta):
    if not meta or not meta.get("file_path"):
        return False
    return (out_dir / meta["file_path"]).exists()


def cache_decision(out_dir, token, kind, tok):
    """探测：返回 (decision_dict, is_hit:bool)"""
    remote = fetch_remote_metadata(token, kind, tok)
    obj_token = remote["obj_token"]
    local = load_meta(out_dir, obj_token)
    fresh = is_fresh(local, remote) and local_file_exists(out_dir, local)
    sanitized = sanitize(remote.get("title") or "untitled")
    decision = {
        "action": "use_cache" if fresh else "download",
        "obj_token": obj_token,
        "obj_type": remote.get("obj_type"),
        "title": remote.get("title"),
        "sanitized_filename": sanitized + ".md",
        "remote": remote,
        "local": local,
        "file_path": local.get("file_path") if (local and fresh) else None,
    }
    return decision, fresh


# ─── 下载 ──────────────────────────────────────────────────────────────

def download_docx_to(token, out_dir, remote_meta, file_name=None):
    """下载 docx 正文到本地，写 meta，返回 file_path（相对 out_dir）"""
    obj_token = remote_meta["obj_token"]
    title = remote_meta.get("title") or "untitled"
    fname = file_name or (sanitize(title) + ".md")
    dest = out_dir / fname
    content = get_docx_raw(token, obj_token)
    dest.write_text(content, encoding="utf-8")
    rec = dict(remote_meta)
    rec["file_path"] = fname
    rec["downloaded_at"] = iso_now()
    rec["size_bytes"] = len(content.encode("utf-8"))
    save_meta_to_disk(out_dir, obj_token, rec)
    return fname


def save_node(token, node, out_dir, cache_mode):
    """递归 walk 用：单节点处理，按 cache_mode 决定是否下载"""
    title = node.get("title") or "untitled"
    obj_type = node.get("obj_type")
    obj_token = node.get("obj_token")
    if obj_type != "docx" or not obj_token:
        print("[skip] {} (obj_type={})".format(title, obj_type), flush=True)
        return False
    remote = {
        "url_kind": "wiki",
        "obj_token": obj_token,
        "obj_type": "docx",
        "obj_edit_time": node.get("obj_edit_time"),
        "title": title,
    }
    if cache_mode == "skip":
        local = load_meta(out_dir, obj_token)
        if local and local_file_exists(out_dir, local):
            print("[cache:skip-mode] use {}".format(local["file_path"]), flush=True)
            return True
        print("[cache:skip-mode] miss obj={} (本地无副本)".format(obj_token), file=sys.stderr)
        return False
    if cache_mode == "auto":
        local = load_meta(out_dir, obj_token)
        if is_fresh(local, remote) and local_file_exists(out_dir, local):
            print(
                "[cache] hit {} (edit_time={})".format(
                    local["file_path"], remote.get("obj_edit_time")
                ),
                flush=True,
            )
            return True
    # force 或 auto-miss → 下载
    fname = download_docx_to(token, out_dir, remote)
    tag = "force" if cache_mode == "force" else "stale"
    print("[fetch] {} ({})".format(out_dir / fname, tag), flush=True)
    return True


def walk(token, space_id, parent_token, out_dir, cache_mode, depth=0):
    children = list_wiki_children(token, space_id, parent_token)
    for ch in children:
        save_node(token, ch, out_dir, cache_mode)
        if ch.get("has_child"):
            walk(token, space_id, ch.get("node_token", ""), out_dir, cache_mode, depth + 1)


# ─── 命令分发 ─────────────────────────────────────────────────────────

def cmd_probe(args, token):
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    kind, tok = extract_token(args.url)
    decision, hit = cache_decision(out_dir, token, kind, tok)
    print(json.dumps(decision, ensure_ascii=False))
    sys.exit(0 if hit else 1)


def cmd_save_meta(args, token):
    """download.sh 调外部下载器完成后调用：记录 meta"""
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    kind, tok = extract_token(args.url)
    remote = fetch_remote_metadata(token, kind, tok)
    obj_token = remote["obj_token"]
    fp = Path(args.file_path)
    # 接受相对或绝对路径，存进 meta 时统一成相对 out_dir
    if fp.is_absolute():
        try:
            fp = fp.relative_to(out_dir)
        except ValueError:
            pass
    rec = dict(remote)
    rec["file_path"] = str(fp)
    rec["downloaded_at"] = iso_now()
    if (out_dir / fp).exists():
        rec["size_bytes"] = (out_dir / fp).stat().st_size
    save_meta_to_disk(out_dir, obj_token, rec)
    print(
        "[meta] saved obj={} → {}/{}.json".format(obj_token, META_DIR_NAME, obj_token),
        flush=True,
    )


def cmd_download(args, token):
    """主下载路径（lite fallback 用）"""
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    kind, tok = extract_token(args.url)
    cache_mode = args.cache_mode

    if kind == "docx":
        if cache_mode == "skip":
            local = load_meta(out_dir, tok)
            if local and local_file_exists(out_dir, local):
                print("[cache:skip-mode] use {}".format(local["file_path"]))
                return
            print("[ERR] skip 模式但本地无副本 obj={}".format(tok), file=sys.stderr)
            sys.exit(1)
        remote = fetch_remote_metadata(token, kind, tok)
        if cache_mode == "auto":
            local = load_meta(out_dir, tok)
            if is_fresh(local, remote) and local_file_exists(out_dir, local):
                print(
                    "[cache] hit {} (revision={})".format(
                        local["file_path"], remote.get("revision_id")
                    )
                )
                return
        fname = download_docx_to(token, out_dir, remote)
        print("[done] {}".format(out_dir / fname))
        return

    # kind == "wiki"
    if cache_mode == "skip":
        # wiki URL 给的是 wiki_token，不联网拿不到 obj_token，没法定位本地 meta
        print(
            "[ERR] skip 模式不支持 wiki URL（无法离线解析 obj_token）；"
            "请用 docx URL，或改 cache-mode=auto",
            file=sys.stderr,
        )
        sys.exit(1)

    node = get_wiki_node(token, tok)
    space_id = node.get("space_id", "")
    save_node(token, node, out_dir, cache_mode)
    if args.recursive:
        if not space_id:
            print("[WARN] 节点无 space_id，无法递归", file=sys.stderr)
        else:
            walk(token, space_id, tok, out_dir, cache_mode)
    print("[done] 写入目录 {}".format(out_dir))


def main():
    p = argparse.ArgumentParser(
        description="飞书 wiki/docx → markdown，纯 stdlib，带 cache 控制",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("url", nargs="?", help="飞书 wiki 或 docx URL")
    p.add_argument("-o", "--out", default="./out", help="输出目录（默认 ./out）")
    p.add_argument("--recursive", action="store_true", help="wiki 节点下递归拉子节点")
    p.add_argument(
        "--cache-mode",
        choices=["auto", "force", "skip"],
        default="auto",
        help="缓存模式：auto=metadata 比对（默认）；force=强制重下；skip=只用本地",
    )
    p.add_argument(
        "--probe",
        action="store_true",
        help="探测模式：输出 JSON 决策，退出码 0=cache 命中 / 1=需要下载",
    )
    p.add_argument(
        "--save-meta",
        action="store_true",
        help="写 meta 模式：在外部下载器完成后调用，记录 metadata",
    )
    p.add_argument(
        "--file-path",
        help="--save-meta 模式必须指定：相对 out 的文件路径",
    )
    args = p.parse_args()

    if not args.url:
        p.error("url 必填")

    app_id = os.environ.get("FEISHU_APP_ID")
    app_secret = os.environ.get("FEISHU_APP_SECRET")
    if not app_id or not app_secret:
        print("[ERR] 必须设置 FEISHU_APP_ID / FEISHU_APP_SECRET", file=sys.stderr)
        sys.exit(2)

    token = get_tenant_token(app_id, app_secret)

    if args.probe:
        cmd_probe(args, token)
    elif args.save_meta:
        if not args.file_path:
            p.error("--save-meta 必须配合 --file-path")
        cmd_save_meta(args, token)
    else:
        cmd_download(args, token)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:
        print("[ERR] {}".format(e), file=sys.stderr)
        sys.exit(1)
