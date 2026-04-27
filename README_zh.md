> [English](README.md) ｜ **简体中文**

# feishu-sync

**飞书 ↔ Markdown 双向同步工具链**。下载飞书 docx/wiki 为 markdown（带 metadata 增量缓存），上传 markdown 到飞书（自动检测 LaTeX 公式并正确渲染），CSV/MD-table/TSV 直传飞书电子表格。

面向**所有使用飞书的人**：开发者、技术写作者、知识管理团队、AI agent 用户都能用。portable、自装依赖、错误可操作、链接由任务传入不硬编码。

**三种用法**（任选）：
1. **Claude Code skill** — `bash install.sh` 之后在 Claude Code 对话里自然语言触发
2. **独立 bash CLI** — 直接 `bash bin/download.sh <url>` / `bash bin/upload.sh <md>`，不依赖任何 agent 框架
3. **AI agent 框架的工具** — 作为 Multica / LangChain / 自建 runtime 的 tool 集成，agent 自 clone + 自装依赖

## 核心特性

- **双向**：下载（docx / wiki 空间，带 metadata cache）+ 上传（含公式渲染）
- **薄编排 + 三层降级**：不重复造轮子，只做决策路由 + 依赖装配；任一外部依赖缺失时自动降到 stdlib
  - 下载首选 [feishu-docx](https://github.com/JessonChan/feishu-docx)（高保真），缺失时降到内置 `bin/download-lite.py`（纯 stdlib raw_content）
  - 上传有公式走 [feishu-markdown-uploader](https://github.com/0xE1337/feishu-markdown-uploader)（LaTeX → equation 块）；缺失时降到 feishu-docx
  - 上传无公式走 feishu-docx；缺失时降到 uploader
- **表格独立通道**：CSV/MD-table/TSV → 飞书电子表格（Sheets，类 Excel 独立页面），纯 stdlib，零额外依赖
- **agent-friendly**：首次调用自装依赖，失败有明确错误码和修法
- **portable**：零硬编码业务信息，一套脚本跑任何飞书/Lark 租户
- **open knowledge**：[权限模型](docs/permission-model.md) / [错误码手册](docs/error-codes.md) / [鉴权模式选择](docs/auth-modes.md) 都是实测归纳

## 与同类工具对比

`feishu-sync` 与 [riba2534/feishu-cli](https://github.com/riba2534/feishu-cli) 等项目是**互补关系**，不是替代：

| | feishu-cli | feishu-sync |
|---|---|---|
| 定位 | 飞书全栈 CLI（瑞士军刀） | 知识同步 + 表格上传专深（雕刻刀） |
| 命令数 | 200+，覆盖 doc/sheet/wiki/msg/calendar/task/meeting | 3 个聚焦命令：`download` / `upload` / `upload-sheet` |
| LaTeX 公式 | 降级为 inline（其 README 自述） | 真 `equation` block，走 [feishu-markdown-uploader](https://github.com/0xE1337/feishu-markdown-uploader) |
| Metadata 增量缓存 | 不支持 | ✅ `--cache-mode auto/force/skip`，比对 `revision_id` |
| CSV/TSV → 独立飞书 Sheet | 不支持 | ✅ 13 个 flag，含美化、`--literal`、`--update` |
| 三层 fallback（stdlib 兜底） | 不支持 | ✅ `download-lite.py` 在 feishu-docx 缺失时保住基础能力 |

**两个一起用**：装 `feishu-cli` 拿全栈飞书覆盖；当你需要增量 wiki 同步、CSV → 独立 Sheet 上传、或真 LaTeX 公式渲染时，再用 `feishu-sync`。两者作用域不重叠。

## 适合谁

- **个人开发者 / 技术写作者** — 把本地 md（论文、技术笔记、博客草稿）发布到飞书空间，含 LaTeX 公式
- **团队知识管理** — 把飞书 wiki/docx 批量同步到本地，做 AI 分析、审核、全文检索
- **Claude Code 用户** — 装上后直接在 Claude 对话里说"把这篇 md 传到飞书"或"把这个 wiki 拉下来分析"
- **AI agent 开发者** — 作为任意 agent 框架（Multica、LangChain、AutoGen、自建 runtime）的工具集成
- **CI / 自动化脚本** — 定时拉取飞书云文档（带 metadata cache，省带宽），或自动发布周报/数据表
- **数据分析师** — 把 CSV/TSV 一键传成飞书电子表格（带美化），团队直接在线协作筛选

## 快速开始

### 前提

1. **飞书自建应用**：[https://open.feishu.cn/app](https://open.feishu.cn/app) 创建，拿到 `APP_ID` + `APP_SECRET`
2. **应用身份权限**（应用管理员在开放平台开通并发版）：
   - 读：`wiki:wiki:readonly` + `docx:document:readonly`
   - 写 docx：`docx:document` + `drive:drive`
   - 写 spreadsheet：`sheets:spreadsheet`（含创建+读写）；指定 `--folder` 还需 `drive:drive`
3. **运行环境**：bash + python3 (>=3.6) + git（macOS / Linux）必需。**完整功能**额外装 Python 3.8+/feishu-docx + Node 18+/uploader（高保真下载 + LaTeX 渲染）。**最小集**：只有 bash + python3 也能跑——`download.sh` 自动降级到 stdlib raw_content，`upload-sheet.sh` 本身就是纯 stdlib，零外部依赖。

### 安装（3 种方式任选）

#### 方式 A：`npx skills add`（推荐 ⭐ 一行命令，跨 agent）

通过 [vercel-labs/skills](https://github.com/vercel-labs/skills)（16k stars 跨 agent 标准工具，支持 Claude Code / Cursor / Codex / OpenCode 等 45+ agent）：

```bash
# 全局安装（推荐）
npx skills add 0xE1337/feishu-sync -g

# 装完到 skill 目录跑一次依赖装配（可选，最小集不用跑）
cd ~/.claude/skills/feishu-sync && bash bin/setup.sh
```

> 不跑 `setup.sh` 也能用——`download.sh` 自动 fallback 到 stdlib，`upload-sheet.sh` 本身纯 stdlib。`setup.sh` 是为了装 feishu-docx（高保真下载）+ uploader（LaTeX 渲染），完整功能才需要。

#### 方式 B：Claude Code 原生 `/plugin install`

在 Claude Code 对话里：

```
/plugin marketplace add 0xE1337/feishu-sync
/plugin install feishu-sync@feishu-sync
```

#### 方式 C：手动 `git clone + install.sh`（兼容老路径，适合开发本项目）

```bash
git clone https://github.com/0xE1337/feishu-sync ~/code/feishu-sync
cd ~/code/feishu-sync
bash install.sh                # symlink 到 ~/.claude/skills/feishu-sync + 装依赖
bash install.sh --no-deps      # 只装 skill，不装依赖
bash install.sh --copy         # 用复制代替 symlink（离线环境/Windows）
```

`install.sh` 做两件事：① symlink 到 `~/.claude/skills/feishu-sync` ② 跑 `bin/setup.sh` 装依赖。

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

### 增量同步（cache 模式）

`download.sh` 默认走 metadata 比对：远端 `revision_id` / `obj_edit_time` 与本地一致则命中本地副本，不走网络。

```bash
# auto（默认）：比对 metadata，命中跳过下载
bash bin/download.sh "https://xxx.feishu.cn/docx/<token>" -o ./out/

# force：强制重下，覆盖本地（含 .meta）
bash bin/download.sh "https://xxx.feishu.cn/docx/<token>" -o ./out/ --cache-mode force

# skip：只用本地副本，不联网（仅单 docx URL 支持；无副本则报错）
bash bin/download.sh "https://xxx.feishu.cn/docx/<token>" -o ./out/ --cache-mode skip

# 也可以走环境变量（命令行参数优先级更高）
CACHE_MODE=force bash bin/download.sh <URL> -o ./out/
```

cache 元数据存在 `<out>/.meta/<obj_token>.json`。**约束**：wiki 全量递归（`--recursive`）+ feishu-docx 路径暂不做 per-node cache，按 force 行为重下整个 space；要 per-node cache 改走 lite 路径（卸载 feishu-docx 让它自动 fallback，或直接 `python3 bin/download-lite.py <wiki_url> --recursive --cache-mode auto`）。

### 上传 markdown（自动检测公式 + 双向降级）

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

`upload.sh` 双向降级：feishu-docx 不可用时降到 uploader，uploader 不可用时降到 feishu-docx——两个都没装才会失败。

### 上传单张表格 → 飞书电子表格（Sheets）

> 区别：上面的 `upload.sh` 把 markdown 整体当 docx 文档传，里面的表格是 markdown 表格块；
> 下面的 `upload-sheet.sh` 把单张表格作为**独立电子表格**上传，得到一个类 Excel 的飞书页面，可在线筛选/排序/编辑公式。

```bash
# CSV → 独立飞书 spreadsheet
# 默认开启美化：表头加粗 + 浅蓝底 (#E8F0FE) + 居中 / 冻结首行 / 列宽自适应
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

# 关闭所有美化，只写数据
bash bin/upload-sheet.sh ./data.csv --plain

# 颗粒度更细的样式开关（任意组合）
bash bin/upload-sheet.sh ./data.csv --no-freeze        # 不冻结首行
bash bin/upload-sheet.sh ./data.csv --no-autosize      # 不调列宽
bash bin/upload-sheet.sh ./data.csv --no-header-style  # 不加粗表头

# 自定义表头底色（默认浅蓝 #E8F0FE）
bash bin/upload-sheet.sh ./data.csv --header-bg "#FFE5E5"

# RAW 模式：保留前导零、不识别科学计数法、= 不当公式
bash bin/upload-sheet.sh ./flight-numbers.csv --literal

# 刷新已有 spreadsheet 内容（不新建，传 URL 或 raw token）
bash bin/upload-sheet.sh ./weekly.csv --update "https://my.feishu.cn/sheets/XYZ"
```

成功后会输出 `[DONE] https://xxx.feishu.cn/sheets/<token>`。

**数据保真**（已在真飞书 API 验证过）：
- 默认 `USER_ENTERED` 模式：纯数字识别为 int/float（含科学计数法 `1.23e10`），布尔由飞书自动识别，前导零 `007` 保留为字符串，`=SUM(...)` 等公式样字符串自动加 `'` 前缀防注入
- `--literal` `RAW` 模式：所有内容当字符串，适合上传代码片段、ID、保留特定数据格式

**约束**（飞书侧）：单次最多 5000 行 × 100 列；单元格 ≤ 40000 字符。超出会在调用前 fail-fast。

## 作为 Claude Code skill 使用

`install.sh` 之后，skill `feishu-sync` 立即可用。在 Claude Code 对话里自然语言调用，skill 会引导选择 download/upload 和相应参数。

详细 skill 入口：[SKILL.md](./SKILL.md)

## 作为 AI agent 框架的工具

本 repo 设计为**通用的 AI agent 飞书工具集**——任何能 `git clone` + 跑 bash 的 agent runtime 都能集成。agent 启动时自 clone + 自装依赖，用 tenant_access_token 直接读写飞书，无人工干预。

**已知集成示例**：
- [Multica](https://github.com/multica-ai/multica) — 详细接入指南见 [docs/multica-integration.md](./docs/multica-integration.md)（custom_env 配置 + 自装指令 + 任务协议）
- **其他 agent 框架**（LangChain Tools、AutoGen Skills、自建 runtime 等）— 按 Multica 示例类比适配，核心是 3 件事：① 把 `FEISHU_APP_ID/SECRET` 注入运行环境 ② 在 agent 启动脚本里 `bash install.sh` ③ 把 `bin/*.sh` 暴露为 agent 可调用的命令

如果你接入了新的 agent 框架，欢迎 PR 一份适配文档到 `docs/`。

## 目录结构

```
feishu-sync/
├── README.md
├── LICENSE                 (MIT)
├── SKILL.md                (Claude Code skill 入口，root 放 → npx skills add 直接识别)
├── install.sh / uninstall.sh
├── .env.example
│
├── .claude-plugin/         (Claude Code 原生 /plugin install 支持)
│   ├── plugin.json         - plugin manifest（name/version/author/keywords）
│   └── marketplace.json    - single-plugin marketplace（让本 repo 自己就是 marketplace）
│
├── bin/                    (可执行脚本)
│   ├── setup.sh            - 幂等装依赖
│   ├── probe.sh            - 自检
│   ├── token.sh            - 取 tenant_access_token
│   ├── download.sh         - 下载路由（feishu-docx → stdlib fallback，带 --cache-mode）
│   ├── download-lite.py    - 纯 stdlib 下载实现（fallback + cache probe/save-meta 子命令）
│   ├── upload.sh           - 上传路由（含 LaTeX 检测 + 双向 fallback）
│   ├── upload-sheet.sh     - 单张表格 → 飞书电子表格（thin wrapper）
│   ├── upload-sheet.py     - upload-sheet 实现（纯 stdlib，CSV/TSV/MD-table 解析 + 美化 + Sheets API）
│   └── test-upload-sheet.py - upload-sheet 的 mock 集成测试（76 断言）
│
├── docs/                   (实测归纳的知识)
│   ├── permission-model.md - 飞书 3 层权限模型
│   ├── error-codes.md      - 错误码操作手册
│   ├── auth-modes.md       - 鉴权模式选择（CDP / OAuth / Tenant）
│   └── multica-integration.md - AI agent 接入示例（以 Multica 为例，可类比其他 runtime）
│
└── examples/               (可运行示例)
    ├── download-wiki-space.sh
    ├── upload-with-latex.sh
    ├── upload-sheet.sh             - 端到端：CSV → 飞书 spreadsheet
    └── upload-sheet-literal.sh     - 默认 vs --literal 模式对比演示
```

## 设计原则

1. **薄编排 > 重实现**：能调现成工具的不自己写
2. **链接/参数由调用方传**：脚本里零硬编码，换租户/换项目不用改代码
3. **自证可用**：`setup.sh` + `probe.sh` 让 agent 独立诊断环境
4. **错误可操作**：每个失败点都对应 `docs/error-codes.md` 里具体修法，不让人干瞪眼
5. **优雅降级**：外部依赖（feishu-docx / uploader）缺失时自动降到 stdlib 或互为兜底；LaTeX 检测失败时退回到 feishu-docx——保证基础能力永不中断

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
