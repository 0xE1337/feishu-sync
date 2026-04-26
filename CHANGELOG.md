# Changelog

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 格式；版本号遵循 [SemVer](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### Added
- **`bin/upload-sheet.sh` + `bin/upload-sheet.py`** — 把单张表格（CSV / TSV / Markdown GFM 表格）作为**独立飞书电子表格（Sheets）**上传，得到一个类 Excel 的飞书页面。区别于 `upload.sh`（markdown → docx 内表格块）。纯 Python stdlib，零额外依赖；走 `sheets/v3` (创建/查 sheet) + `sheets/v2/values_batch_update` (写值) API。支持 `--title` / `--folder` / `--format` / `--dry-run`，自动数字类型识别（`USER_ENTERED`），fail-fast 校验飞书侧 5000×100 / 40000-char 上限。
- **美观度增强（默认开启）**：上传后自动应用 ① 表头加粗 + 浅蓝底 (`#E8F0FE`) + 居中 ② 冻结首行 ③ 列宽自适应（CJK 字符按 2 算，连续同宽列合并成单次 API 调用）。三个可关闭：`--plain` 一次跳过所有美化。`--header-bg "#FFE5E5"` 自定义表头色。
- **`--literal` flag**：切到 RAW 上传模式，所有单元格当字符串原样保留（不做数字识别、不做公式 `=` 转义）。适合上传代码片段、保留前导零的 ID（航班号/邮编）。
- **3 个数据保真 bug 修复**：
  - 前导零保护：`007` 不再被吞成 `int 7`，保留为 `str "007"`
  - 科学计数法识别：`1.23e10` 现在识别为 `float`（之前 regex 不匹配 `e`）
  - 公式注入防护：`=SUM(B2:B4)` 字符串自动加 `'` 前缀，防止飞书 USER_ENTERED 模式把它当公式执行（同样的 `+`/`-`/`@` 开头处理）
- **2 个美化 silent-fail bug 修复**（API 调用看似成功但样式没生效）：
  - `fontSize` 必须传字符串 `"11pt/1.5"` 格式，不是 int（飞书错误消息 `must between 9 and 36` 误导）
  - `dimension_range` API 必须用 **PUT** 而不是 POST（POST 会走错 handler 报误导性 `length is nil`）
  - 现在所有 styling 函数都校验 `code != 0` 并 raise，再被 main() 的 try/except wrap 成 warn 但不致命
- **HTTP 层鲁棒性**：
  - 5xx + 429 自动重试（指数退避：500ms → 1500ms → ...，默认最多 3 次尝试）
  - 网络错误（DNS / 连接超时）也走重试
  - 4xx 业务错误立即失败不浪费时间
  - 错误消息附带修复建议，指向 `docs/error-codes.md` 具体段落（已知 code：99991672/131006/131005/1254040/20027/20029）
  - User-Agent 标识 `feishu-sync/0.2 (upload-sheet)`
- `bin/test-upload-sheet.py` — mock 飞书 API 的端到端测试套件，57 个断言（数据路径 + 美化路径 + literal 模式 + 错误透传 + retry/error-format）
- `.github/workflows/shellcheck.yml` — CI 里对 bash 脚本跑 shellcheck + `bash -n` 语法检查
- `examples/upload-sheet.sh` — 端到端示例：生成样本 CSV → dry-run → 真实上传
- `examples/upload-sheet-literal.sh` — 默认模式 vs `--literal` 模式对比演示（航班号/前导零 ID/公式样字符串场景）

### Docs
- `SKILL.md` 决策树新增"产出 docx vs 产出 sheet"分支；`README.md` 加上传 sheet 命令段
- `docs/error-codes.md` 加 `sheets:spreadsheet` scope 说明，`docs/permission-model.md` 补 sheets API 端点 ↔ 权限层映射

## [0.1.0] - 2026-04-24

首次发布。核心目标：为 AI agent 和团队提供 **飞书 ↔ Markdown** 的双向同步工具链。

### Added

**脚本 (`bin/`)**
- `setup.sh` — 幂等装依赖：pipx/uv/pip 装 `feishu-docx`，`git clone` + `npm install` 装 `feishu-markdown-uploader` 到 `~/.feishu-sync/uploader/`
- `probe.sh` — 3 步自检（凭证 → tenant_access_token → wiki 可读）；支持 `--wiki` / `--doc` 参数追加验证
- `token.sh` — 取 tenant_access_token 的工具函数，其他脚本共用
- `download.sh` — 路由到 `feishu-docx export` 或 `export-wiki-space`；支持 `--recursive` / `--auth` / `-o`
- `upload.sh` — LaTeX 启发式检测（`$$...$$`、`\frac` / `\sum` / `^` / `_` 等符号）：有公式走 uploader，无公式走 `feishu-docx create`；支持 `--force-latex` / `--force-simple` / `--folder`

**文档 (`docs/`)**（实测归纳）
- `permission-model.md` — 飞书 Open API **3 层权限模型**（应用身份 scope + 空间可见性 + 成员身份），附 API 端点 ↔ 权限层对应表（2026-04-24 实测）
- `error-codes.md` — 操作化错误码手册：`99991672` / `131006`（读/写分情境）/ `1254040` / `20027` / `20029`，每条给自助修法和绕开方案
- `auth-modes.md` — 三条鉴权路径对比（CDP / OAuth / Tenant）+ 部署决策树
- `multica-integration.md` — Multica agent 接入指南（custom_env 配置 + 自装指令 + 任务协议）

**开源门面**
- `README.md` — 项目概述、核心特性、快速开始、命令参考、设计原则、致谢
- `LICENSE` — MIT
- `.gitignore` — 过滤 `.env` / `out/` / `node_modules/` / 编辑器临时文件
- `.env.example` — 凭证模板（纯 placeholder）
- `install.sh` / `uninstall.sh` — Claude Code skill 安装 / 卸载（`--copy` 模式替代 symlink；`--no-deps` 跳过依赖；`--purge` 连依赖一起删）
- `SKILL.md` — Claude Code skill 入口（决策树 + 错误排查表）

**示例 (`examples/`)**
- `download-wiki-space.sh` — 批量下载一个飞书 wiki 空间
- `upload-with-latex.sh` — 生成含公式 md 并上传，验证公式渲染

### Design Principles

1. **薄编排 > 重实现** — 依赖现有工具（feishu-docx、feishu-markdown-uploader），不重复造轮
2. **零硬编码业务信息** — 所有 wiki URL / app_id / repo 名由运行时参数传入
3. **自证可用** — `setup.sh` + `probe.sh` 让 agent 独立诊断环境
4. **错误可操作** — 每个失败点都对应 `docs/error-codes.md` 里具体修法
5. **优雅降级** — LaTeX 检测失败时退回到 feishu-docx，基础能力不中断

### Verified End-to-End

- `install.sh --no-deps` 建立 `~/.claude/skills/feishu-sync → ~/code/feishu-sync` symlink ✅
- `probe.sh --wiki <url>` 带真实凭证全绿（凭证 → token 42 字符 → wiki 根节点可读）✅
- Sanity check 无真实 app_id / secret / wiki_token 残留 ✅

[Unreleased]: https://github.com/YOUR_USER/feishu-sync/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/YOUR_USER/feishu-sync/releases/tag/v0.1.0
