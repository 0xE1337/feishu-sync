# Changelog

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 格式；版本号遵循 [SemVer](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### Added
- `.github/workflows/shellcheck.yml` — CI 里对 bash 脚本跑 shellcheck + `bash -n` 语法检查

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
