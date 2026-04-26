# feishu-sync

**飞书 ↔ Markdown 双向同步工具链**。下载飞书 docx/wiki 为 markdown，上传 markdown 到飞书（自动检测 LaTeX 公式并正确渲染）。

面向 **AI agent + 团队**设计：portable、自装依赖、错误可操作、链接由任务传入不硬编码。可作为 Claude Code skill 使用，也可以独立 bash 调用。

## 核心特性

- **双向**：下载（docx / wiki 空间）+ 上传（含公式渲染）
- **薄编排**：不重复造轮子，只做决策路由 + 依赖装配
  - 下载走 [feishu-docx](https://github.com/JessonChan/feishu-docx)
  - 上传有公式走 [feishu-markdown-uploader](https://github.com/0xE1337/feishu-markdown-uploader)（LaTeX → equation 块）
  - 上传无公式走 feishu-docx（最简路径）
- **表格独立通道**：CSV/MD-table/TSV → 飞书电子表格（Sheets，类 Excel 独立页面），纯 stdlib，零额外依赖
- **agent-friendly**：首次调用自装依赖，失败有明确错误码和修法
- **portable**：零硬编码业务信息，一套脚本跑任何飞书/Lark 租户
- **open knowledge**：[权限模型](docs/permission-model.md) / [错误码手册](docs/error-codes.md) / [鉴权模式选择](docs/auth-modes.md) 都是实测归纳

## 适合谁

- 把飞书知识库文档同步给 AI agent 做分析/审核
- 团队成员需要把本地 md（论文、技术笔记）发布到飞书空间
- CI / 自动化脚本需要和飞书云文档协作
- 想把已有的"手工飞书 ops"沉淀成可复用工具链

## 快速开始

### 前提

1. **飞书自建应用**：[https://open.feishu.cn/app](https://open.feishu.cn/app) 创建，拿到 `APP_ID` + `APP_SECRET`
2. **应用身份权限**（应用管理员在开放平台开通并发版）：
   - 读：`wiki:wiki:readonly` + `docx:document:readonly`
   - 写 docx：`docx:document` + `drive:drive`
   - 写 spreadsheet：`sheets:spreadsheet`（含创建+读写）；指定 `--folder` 还需 `drive:drive`
3. **运行环境**：Python 3.8+、Node.js 18+、git、bash（macOS / Linux）。`upload-sheet.sh` 仅依赖 python3 stdlib，无需安装 feishu-docx / uploader。

### 安装

```bash
git clone <this-repo> ~/code/feishu-sync
cd ~/code/feishu-sync
bash install.sh
```

`install.sh` 做两件事：
1. 在 `~/.claude/skills/feishu-sync` 建软链接（供 Claude Code 当 skill 用）
2. 跑 `bin/setup.sh` 装依赖（feishu-docx via pipx/uv，uploader 克隆到 `~/.feishu-sync/`）

不用 Claude Code？也可以独立用：

```bash
bash install.sh --no-deps   # 仅装依赖跳过 skill 链接
# 或者只跑 bin/setup.sh
```

### 配置凭证

```bash
cp .env.example .env
# 编辑 .env，填入真实的 FEISHU_APP_ID / FEISHU_APP_SECRET
source .env
```

### 自检

```bash
bash bin/probe.sh                                      # 凭证 + token
bash bin/probe.sh --wiki "https://xxx.feishu.cn/wiki/YYY"   # 加验 wiki 可读
```

三步全绿才算就绪。

## 常用命令

### 下载单个 docx

```bash
bash bin/download.sh "https://xxx.feishu.cn/docx/<token>" -o ./out/
```

### 下载整个 wiki 空间（递归）

```bash
bash bin/download.sh "https://xxx.feishu.cn/wiki/<root_token>" -o ./out/ --recursive
```

### 上传 markdown（自动检测公式）

```bash
# 无公式 → 走 feishu-docx create
bash bin/upload.sh ./note.md --title "我的笔记"

# 有 $...$ 或 $$...$$ → 自动路由到 uploader
bash bin/upload.sh ./paper.md --title "论文"

# 强制走 uploader（即使检测不到公式）
bash bin/upload.sh ./x.md --force-latex

# 指定飞书 folder_token
bash bin/upload.sh ./x.md --folder fldcn_xxxx
```

### 上传单张表格 → 飞书电子表格（Sheets）

> 区别：上面的 `upload.sh` 把 markdown 整体当 docx 文档传，里面的表格是 markdown 表格块；
> 下面的 `upload-sheet.sh` 把单张表格作为**独立电子表格**上传，得到一个类 Excel 的飞书页面，可在线筛选/排序/编辑公式。

```bash
# CSV → 独立飞书 spreadsheet
bash bin/upload-sheet.sh ./data.csv --title "Q1 销售"

# 从一份 markdown 抓第一张 GFM 表格（自动忽略其他段落/标题）
bash bin/upload-sheet.sh ./report.md --title "演示"

# TSV / 强制格式
bash bin/upload-sheet.sh ./data.tsv --title "原始日志"
bash bin/upload-sheet.sh ./data.txt --format csv --title "无后缀"

# 指定飞书目录
bash bin/upload-sheet.sh ./data.csv --title "Q1 销售" --folder fldcn_xxxx

# Dry-run：只解析 + 打印请求骨架，不真发请求
bash bin/upload-sheet.sh ./data.csv --dry-run
```

成功后会输出 `[DONE] https://xxx.feishu.cn/sheets/<token>`。

**约束**（飞书侧）：单次最多 5000 行 × 100 列；单元格 ≤ 40000 字符。超出会在调用前 fail-fast。

## 作为 Claude Code skill 使用

`install.sh` 之后，skill `feishu-sync` 立即可用。在 Claude Code 对话里自然语言调用，skill 会引导选择 download/upload 和相应参数。

详细 skill 入口：[SKILL.md](./SKILL.md)

## 作为 Multica agent 的工具

把本 repo 作为 Multica agent 的 skill 之一。agent 启动时自 clone + 自装，用 tenant_access_token 直接读写飞书。详见 [docs/multica-integration.md](./docs/multica-integration.md)。

## 目录结构

```
feishu-sync/
├── README.md
├── LICENSE                 (MIT)
├── SKILL.md                (Claude Code skill 入口)
├── install.sh / uninstall.sh
├── .env.example
│
├── bin/                    (可执行脚本)
│   ├── setup.sh            - 幂等装依赖
│   ├── probe.sh            - 自检
│   ├── token.sh            - 取 tenant_access_token
│   ├── download.sh         - 下载路由
│   ├── upload.sh           - 上传路由（含 LaTeX 检测）
│   ├── upload-sheet.sh     - 单张表格 → 飞书电子表格（thin wrapper）
│   └── upload-sheet.py     - upload-sheet 实现（纯 stdlib，CSV/TSV/MD-table 解析 + Sheets API）
│
├── docs/                   (实测归纳的知识)
│   ├── permission-model.md - 飞书 3 层权限模型
│   ├── error-codes.md      - 错误码操作手册
│   ├── auth-modes.md       - 鉴权模式选择（CDP / OAuth / Tenant）
│   └── multica-integration.md - Multica agent 接入
│
└── examples/               (可运行示例)
    ├── download-wiki-space.sh
    └── upload-with-latex.sh
```

## 设计原则

1. **薄编排 > 重实现**：能调现成工具的不自己写
2. **链接/参数由调用方传**：脚本里零硬编码，换租户/换项目不用改代码
3. **自证可用**：`setup.sh` + `probe.sh` 让 agent 独立诊断环境
4. **错误可操作**：每个失败点都对应 `docs/error-codes.md` 里具体修法，不让人干瞪眼
5. **优雅降级**：LaTeX 检测失败时退回到 feishu-docx，保证基础能力不中断

## 故障排查

遇到问题先跑 `bash bin/probe.sh` 看哪一步失败。常见错误码速查：

| 错误码 | 含义 | 快速修法 |
|-------|------|--------|
| `99991672` | 应用身份 scope 不足 | 开放平台加 scope 并发版 |
| `131006` | 非成员或 wiki 非公开 | 读：加应用为 wiki 成员；写：加 edit 角色 |
| `20027` | OAuth scope 不足 | 用 `OAuth2Authenticator(scopes=[...])` 只请最小集 |
| `20029` | redirect_uri 不匹配 | 开放平台安全设置加 `http://127.0.0.1:9527/`（带结尾斜杠） |

完整手册见 [docs/error-codes.md](./docs/error-codes.md)。

## 致谢

本项目站在这些工具肩膀上：

- [feishu-docx](https://github.com/JessonChan/feishu-docx) — Python SDK + CLI，下载链路核心
- [feishu-markdown-uploader](https://github.com/0xE1337/feishu-markdown-uploader) — Node uploader，LaTeX 渲染独家
- [feishu-markdown](https://github.com/huandu/feishu-markdown) — uploader 依赖的底层 markdown → 飞书块转换库

我们做的是**决策路由**和**知识沉淀**，不是重复造轮。

## 贡献

PR 欢迎。开源时请注意：

- 不要提交真实的 `FEISHU_APP_ID` / `FEISHU_APP_SECRET`（`.gitignore` 已防 `.env`）
- 不要在 examples/ docs/ 里写具体业务 wiki 链接或 token
- 新增错误码处理请更新 [docs/error-codes.md](./docs/error-codes.md)
- 新增鉴权路径请更新 [docs/auth-modes.md](./docs/auth-modes.md)

## License

[MIT](./LICENSE)
