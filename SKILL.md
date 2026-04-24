---
name: feishu-sync
description: 双向同步 Markdown 与飞书文档。下载飞书 docx/wiki → md；上传 md → 飞书（自动检测 LaTeX 公式，有公式走 uploader 渲染，无公式走 feishu-docx）。为 Multica agent 和团队设计，portable，首次调用自装依赖。
---

# feishu-sync

Markdown ↔ 飞书云文档的双向同步 skill。一条命令搞定上传/下载，按内容特征自动选工具。

## 什么时候用这个 skill

- **要从飞书拉 docx 或 wiki 空间** → `bin/download.sh`
- **要把 md 上传到飞书**（含公式也能正确渲染）→ `bin/upload.sh`
- **遇到飞书 API 错误码搞不懂** → 查 `docs/error-codes.md`
- **不知道该用 tenant 还是 oauth 鉴权** → 查 `docs/auth-modes.md`
- **接入 Multica agent** → 查 `docs/multica-integration.md`

## 前置：环境变量

```bash
export FEISHU_APP_ID="cli_xxxxxxxxxxxxxxxx"
export FEISHU_APP_SECRET="xxxxxxxxxxxxxxxxxxxxxxxx"
# 可选：Lark 国际版用
# export FEISHU_HOST="open.larksuite.com"   # 默认 open.feishu.cn
```

**应用身份权限必需 scope**（应用管理员在开放平台开通并发版）：
- 读：`wiki:wiki:readonly` + `docx:document:readonly`
- 写：`docx:document` + `drive:drive`

## 首次使用：装依赖

```bash
bash bin/setup.sh
```

幂等。第二次跑会自动跳过已装的。装好后：
- `feishu-docx` 走 pipx（隔离，避免污染系统 Python）
- `feishu-markdown-uploader` 克隆到 `${HOME}/.feishu-sync/uploader/` 并 `npm install`

## 自检

```bash
bash bin/probe.sh
```

验 3 件事：
1. 凭证环境变量齐全
2. `tenant_access_token` 能取
3. 如果给了 `--wiki <url>`，验证 wiki 可达

## 主命令：下载

```bash
# 单个 docx
bash bin/download.sh "https://xxx.feishu.cn/docx/<token>" -o ./out/

# 整个 wiki 空间（递归）
bash bin/download.sh "https://xxx.feishu.cn/wiki/<root_token>" -o ./out/ --recursive

# 用 OAuth 模式（当 tenant 权限不够时）
bash bin/download.sh <url> -o ./out/ --auth oauth
```

## 主命令：上传

```bash
# 无公式：走 feishu-docx create，最简
bash bin/upload.sh ./my.md --title "我的文档"

# 有 LaTeX 公式：自动检测，走 uploader（带公式渲染）
bash bin/upload.sh ./paper.md --title "论文"

# 强制走 uploader（即使未检测到公式）
bash bin/upload.sh ./x.md --force-latex

# 指定飞书目录（folder_token）
bash bin/upload.sh ./x.md --folder fldcn_xxxx
```

## 决策树（agent 遇到"该用哪个"时看这里）

```
任务是要把 md 放到飞书？
├── md 里有 $...$ 或 $$...$$ 或 \\frac \\sum 之类的 LaTeX 符号？
│   ├── 是 → bin/upload.sh（自动路由到 uploader，公式会渲染）
│   └── 否 → bin/upload.sh（自动路由到 feishu-docx create）
│
任务是要从飞书拿内容？
├── URL 是 /docx/<token>？
│   └── bin/download.sh <url>（单文档导出）
├── URL 是 /wiki/<token> 且只要一个文档？
│   └── bin/download.sh <url>（自动走 wiki_token）
├── URL 是 /wiki/<token> 且要整个空间？
│   └── bin/download.sh <url> --recursive
│
任务是更新已有文档的某个 block？
├── 不走本 skill，直接 feishu-docx update（本 skill 不封装）
│
任务是删除文档？
├── 不走本 skill——本 skill 禁止写删除操作
```

## 错误排查（出错了先看这里）

agent 遇到 code 非 0 时，第一步到 `docs/error-codes.md` 查对应修法。常见 4 个：

| 错误码 | 含义 | 修法 |
|-------|------|------|
| `99991672` | 应用身份 scope 不足 | 回开放平台加 scope 并发版 |
| `131006` | 非成员或 wiki 不公开 | 读场景：加应用到 wiki 成员（只读）；写场景：加 edit 权限 |
| `20027` | OAuth scope 不足 | 换 `OAuth2Authenticator(scopes=[...])` 只请最小集 |
| `20029` | redirect_uri 不匹配 | 开放平台 → 安全设置加 `http://127.0.0.1:9527/`（带结尾斜杠） |

## 禁止清单

- **不删除**：skill 不封装 delete 操作，删除必须人工
- **不硬编码**：url、wiki_token、obj_token 都由调用方传入
- **不记日志含密钥**：`FEISHU_APP_SECRET` 不得出现在任何输出或错误信息中（脚本里已做脱敏）
- **不自动改权限**：skill 不会自己去改应用可用范围或加知识库成员——那是人工动作

## 设计原则

1. **薄编排 > 重实现**：skill 不重新写下载/上传，只做路由 + 决策
2. **链接/参数由调用方传**：skill 里零硬编码业务信息
3. **自证可用**：`setup.sh` 和 `probe.sh` 让 agent 能自己诊断环境
4. **错误可操作**：错误码直接指向 `docs/error-codes.md` 里具体修法
5. **优雅降级**：LaTeX 检测失败时退回到 feishu-docx，保证基础能力不中断
