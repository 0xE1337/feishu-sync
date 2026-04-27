> **English** ｜ [简体中文](README_zh.md)

# feishu-sync

**Feishu ↔ Markdown two-way sync toolkit.** Download Feishu docx/wiki as markdown (with metadata-based incremental cache). Upload markdown to Feishu (auto-detects LaTeX formulas and renders them correctly). Upload CSV/MD-table/TSV directly as Feishu Sheets.

For **anyone using Feishu**: developers, technical writers, knowledge management teams, AI agent users. Portable, self-installing dependencies, actionable errors, no hardcoded business identifiers.

**Three ways to use it** (pick any):
1. **As a Claude Code skill** — after `bash install.sh`, trigger via natural language in Claude Code conversations
2. **As a standalone bash CLI** — run `bash bin/download.sh <url>` / `bash bin/upload.sh <md>` directly, no agent framework required
3. **As a tool in any AI agent framework** — integrate as a tool in Multica / LangChain / your own runtime; the agent self-clones and self-installs

## Core features

- **Two-way**: download (docx / wiki spaces, with metadata cache) + upload (with formula rendering)
- **Thin orchestration + 3-layer fallback**: don't reinvent wheels — just route decisions and assemble dependencies; falls back to stdlib if any external dep is missing
  - Download prefers [feishu-docx](https://github.com/JessonChan/feishu-docx) (high-fidelity); falls back to built-in `bin/download-lite.py` (pure stdlib raw_content) if missing
  - Upload with formulas uses [feishu-markdown-uploader](https://github.com/0xE1337/feishu-markdown-uploader) (LaTeX → real equation block, **not** inline-degraded); falls back to feishu-docx if missing
  - Upload without formulas uses feishu-docx; falls back to uploader if missing
- **Dedicated table channel**: CSV/MD-table/TSV → Feishu Sheets (Excel-like standalone page), pure stdlib, zero extra dependencies
- **Agent-friendly**: self-installs deps on first call; failures come with explicit error codes and fix recipes
- **Portable**: zero hardcoded business identifiers, one set of scripts works for any Feishu/Lark tenant
- **Open knowledge**: [permission model](docs/permission-model.md) / [error code manual](docs/error-codes.md) / [auth modes](docs/auth-modes.md) — all distilled from real testing

## How feishu-sync compares to alternatives

`feishu-sync` is **complementary**, not a replacement, to projects like [riba2534/feishu-cli](https://github.com/riba2534/feishu-cli):

| | feishu-cli | feishu-sync |
|---|---|---|
| Positioning | Full-stack Feishu CLI (Swiss Army knife) | Knowledge sync + table import (specialized chisel) |
| Command count | 200+ across docs/sheet/wiki/msg/calendar/task/meeting | 3 focused: `download` / `upload` / `upload-sheet` |
| LaTeX formulas | Inline-degraded (per its README) | Real `equation` block via [feishu-markdown-uploader](https://github.com/0xE1337/feishu-markdown-uploader) |
| Metadata-based incremental cache | Not supported | ✅ `--cache-mode auto/force/skip`, compares `revision_id` |
| CSV/TSV → standalone Feishu Sheet | Not supported | ✅ 13 flags incl. styling, `--literal`, `--update` |
| Three-layer fallback (stdlib safety net) | Not supported | ✅ `download-lite.py` keeps base capability alive when feishu-docx is missing |

**Use both together**: install `feishu-cli` for full-stack Feishu coverage, and `feishu-sync` whenever you specifically need incremental wiki sync, CSV→Sheet imports, or true LaTeX equation rendering. The scopes don't overlap.

## Who is this for

- **Individual developers / technical writers** — publish local markdown (papers, technical notes, blog drafts) to Feishu spaces, including LaTeX formulas
- **Knowledge management teams** — batch sync Feishu wiki/docx to local files for AI analysis, review, full-text search
- **Claude Code users** — after install, just say "upload this md to Feishu" or "pull this wiki for analysis" in Claude conversations
- **AI agent developers** — integrate as a tool in any agent framework (Multica, LangChain, AutoGen, custom runtime)
- **CI / automation scripts** — schedule pulls of Feishu cloud documents (with metadata cache, saving bandwidth), or auto-publish weekly reports / data tables
- **Data analysts** — one-shot upload CSV/TSV as Feishu Sheets (with styling), team can collaborate online with filtering

## Quick start

### Prerequisites

1. **Feishu self-built app**: create at [https://open.feishu.cn/app](https://open.feishu.cn/app), get `APP_ID` + `APP_SECRET`
2. **App identity scopes** (your app admin enables and publishes on the open platform):
   - Read: `wiki:wiki:readonly` + `docx:document:readonly`
   - Write docx: `docx:document` + `drive:drive`
   - Write spreadsheet: `sheets:spreadsheet` (includes create + read/write); using `--folder` also requires `drive:drive`
3. **Runtime**: bash + python3 (>=3.6) + git (macOS / Linux) required. **Full features** additionally need Python 3.8+/feishu-docx + Node 18+/uploader (high-fidelity download + LaTeX rendering). **Minimum**: bash + python3 alone works — `download.sh` auto-degrades to stdlib raw_content, `upload-sheet.sh` is pure stdlib with zero external deps.

### Install (3 ways, pick one)

#### Option A: `npx skills add` (recommended ⭐ one-line, cross-agent)

Via [vercel-labs/skills](https://github.com/vercel-labs/skills) (16k stars, cross-agent standard tool, supports 45+ agents including Claude Code / Cursor / Codex / OpenCode):

```bash
# Install globally (recommended)
npx skills add 0xE1337/feishu-sync -g

# Then run dependency setup once (optional — minimum mode doesn't need it)
cd ~/.claude/skills/feishu-sync && bash bin/setup.sh
```

> Skipping `setup.sh` works too — `download.sh` auto-falls back to stdlib, `upload-sheet.sh` is pure stdlib. `setup.sh` exists to install feishu-docx (high-fidelity download) + uploader (LaTeX rendering); only needed for full features.

#### Option B: Claude Code native `/plugin install`

In a Claude Code conversation:

```
/plugin marketplace add 0xE1337/feishu-sync
/plugin install feishu-sync@feishu-sync
```

#### Option C: Manual `git clone + install.sh` (legacy, suitable for hacking on this project)

```bash
git clone https://github.com/0xE1337/feishu-sync ~/code/feishu-sync
cd ~/code/feishu-sync
bash install.sh                # symlink to ~/.claude/skills/feishu-sync + install deps
bash install.sh --no-deps      # install skill only, skip deps
bash install.sh --copy         # copy instead of symlink (offline / Windows)
```

`install.sh` does two things: ① symlink to `~/.claude/skills/feishu-sync` ② run `bin/setup.sh` to install deps.

### Configure credentials

```bash
cp .env.example .env
# Edit .env, fill in real FEISHU_APP_ID / FEISHU_APP_SECRET
source .env
```

### Self-check

```bash
bash bin/probe.sh                                                # creds + token
bash bin/probe.sh --wiki "https://xxx.feishu.cn/wiki/YYY"        # also verify wiki readable
```

All three steps green = ready.

## Common commands

### Download a single docx

```bash
bash bin/download.sh "https://xxx.feishu.cn/docx/<token>" -o ./out/
```

### Download an entire wiki space (recursive)

```bash
bash bin/download.sh "https://xxx.feishu.cn/wiki/<root_token>" -o ./out/ --recursive
```

### Incremental sync (cache mode)

`download.sh` defaults to metadata comparison: if remote `revision_id` / `obj_edit_time` matches local, skip the download.

```bash
# auto (default): compare metadata, skip download on hit
bash bin/download.sh "https://xxx.feishu.cn/docx/<token>" -o ./out/

# force: re-download, overwrite local (including .meta)
bash bin/download.sh "https://xxx.feishu.cn/docx/<token>" -o ./out/ --cache-mode force

# skip: use local copy only, no network (single docx URL only; errors if no copy exists)
bash bin/download.sh "https://xxx.feishu.cn/docx/<token>" -o ./out/ --cache-mode skip

# Or via env var (CLI flag takes precedence)
CACHE_MODE=force bash bin/download.sh <URL> -o ./out/
```

Cache metadata lives in `<out>/.meta/<obj_token>.json`. **Constraint**: full wiki recursion (`--recursive`) + the feishu-docx path doesn't yet support per-node cache and behaves like force, re-downloading the whole space. For per-node caching, use the lite path (uninstall feishu-docx to trigger auto-fallback, or call `python3 bin/download-lite.py <wiki_url> --recursive --cache-mode auto` directly).

### Upload markdown (auto formula detection + bidirectional fallback)

```bash
# No formulas → uses feishu-docx create
bash bin/upload.sh ./note.md --title "My note"

# Has $...$ or $$...$$ → auto-routes to uploader
bash bin/upload.sh ./paper.md --title "Paper"

# Force uploader path (even if no formulas detected)
bash bin/upload.sh ./x.md --force-latex

# Specify Feishu folder_token
bash bin/upload.sh ./x.md --folder fldcn_xxxx
```

`upload.sh` falls back both ways: when feishu-docx is unavailable it uses uploader; when uploader is unavailable it uses feishu-docx — only fails if neither is installed.

### Upload a single table → Feishu Sheets

> Difference: `upload.sh` above treats markdown as a whole docx document, where tables become markdown table blocks;
> `upload-sheet.sh` below uploads a single table as a **standalone spreadsheet**, producing an Excel-like Feishu page with online filter/sort/formula editing.

```bash
# CSV → standalone Feishu spreadsheet
# Default styling: bold header + light-blue background (#E8F0FE) + center align / freeze first row / autosize columns
bash bin/upload-sheet.sh ./data.csv --title "Q1 Sales"

# Pull the first GFM table from a markdown file (other paragraphs/headings ignored)
bash bin/upload-sheet.sh ./report.md --title "Demo"

# TSV / explicit format
bash bin/upload-sheet.sh ./data.tsv --title "Raw logs"
bash bin/upload-sheet.sh ./data.txt --format csv --title "No extension"

# Specify Feishu folder
bash bin/upload-sheet.sh ./data.csv --title "Q1 Sales" --folder fldcn_xxxx

# Dry-run: parse + print request skeleton, no actual API call
bash bin/upload-sheet.sh ./data.csv --dry-run

# Disable all styling, write data only
bash bin/upload-sheet.sh ./data.csv --plain

# Granular style toggles (combine freely)
bash bin/upload-sheet.sh ./data.csv --no-freeze        # don't freeze first row
bash bin/upload-sheet.sh ./data.csv --no-autosize      # don't autosize columns
bash bin/upload-sheet.sh ./data.csv --no-header-style  # don't bold header

# Customize header background color (default light blue #E8F0FE)
bash bin/upload-sheet.sh ./data.csv --header-bg "#FFE5E5"

# RAW mode: preserve leading zeros, don't recognize scientific notation, treat = as plain text
bash bin/upload-sheet.sh ./flight-numbers.csv --literal

# Refresh existing spreadsheet content (no new sheet; pass URL or raw token)
bash bin/upload-sheet.sh ./weekly.csv --update "https://my.feishu.cn/sheets/XYZ"
```

On success prints `[DONE] https://xxx.feishu.cn/sheets/<token>`.

**Data fidelity** (verified against real Feishu API):
- Default `USER_ENTERED` mode: pure numbers parsed as int/float (including scientific notation `1.23e10`), booleans auto-detected by Feishu, leading-zero values like `007` preserved as strings, formula-like strings such as `=SUM(...)` get a leading `'` to prevent injection
- `--literal` `RAW` mode: everything as string — use for code snippets, IDs, or to preserve specific data formats

**Constraints** (Feishu side): max 5000 rows × 100 columns per write; cell ≤ 40000 chars. Exceeding fails fast before the call.

## Use as a Claude Code skill

After `install.sh`, the skill `feishu-sync` is immediately usable. Trigger it via natural language in Claude Code conversations — the skill guides you through choosing download/upload and the relevant parameters.

Skill entry point: [SKILL.md](./SKILL.md)

## Use as a tool in AI agent frameworks

This repo is designed as a **general AI agent toolkit for Feishu** — any agent runtime that can `git clone` + run bash can integrate it. The agent self-clones and self-installs at startup, then uses tenant_access_token to read/write Feishu directly with no human intervention.

**Known integrations**:
- [Multica](https://github.com/multica-ai/multica) — detailed integration guide at [docs/multica-integration.md](./docs/multica-integration.md) (custom_env config + self-install instructions + task protocol)
- **Other agent frameworks** (LangChain Tools, AutoGen Skills, custom runtimes, etc.) — adapt by analogy with the Multica example. Three things matter: ① inject `FEISHU_APP_ID/SECRET` into the runtime env ② run `bash install.sh` in the agent startup script ③ expose `bin/*.sh` as agent-callable commands

If you've integrated a new agent framework, PRs adding an adapter doc under `docs/` are welcome.

## Directory layout

```
feishu-sync/
├── README.md / README_zh.md   (English / 简体中文)
├── LICENSE                    (MIT)
├── SKILL.md                   (Claude Code skill entry; placed at root → npx skills add picks it up)
├── install.sh / uninstall.sh
├── .env.example
│
├── .claude-plugin/            (Claude Code native /plugin install support)
│   ├── plugin.json            - plugin manifest (name/version/author/keywords)
│   └── marketplace.json       - single-plugin marketplace (this repo IS its own marketplace)
│
├── bin/                       (executable scripts)
│   ├── setup.sh               - idempotent dependency installer
│   ├── probe.sh               - self-check
│   ├── token.sh               - fetch tenant_access_token
│   ├── download.sh            - download router (feishu-docx → stdlib fallback, with --cache-mode)
│   ├── download-lite.py       - pure stdlib download impl (fallback + cache probe/save-meta subcommands)
│   ├── upload.sh              - upload router (with LaTeX detection + bidirectional fallback)
│   ├── upload-sheet.sh        - single table → Feishu spreadsheet (thin wrapper)
│   ├── upload-sheet.py        - upload-sheet implementation (pure stdlib, CSV/TSV/MD-table parsing + styling + Sheets API)
│   └── test-upload-sheet.py   - upload-sheet mock integration tests (76 assertions)
│
├── docs/                      (knowledge distilled from real testing)
│   ├── permission-model.md    - Feishu's 3-layer permission model
│   ├── error-codes.md         - actionable error code manual
│   ├── auth-modes.md          - auth mode selection (CDP / OAuth / Tenant)
│   └── multica-integration.md - AI agent integration example (Multica; analogize for other runtimes)
│
└── examples/                  (runnable examples)
    ├── download-wiki-space.sh
    ├── upload-with-latex.sh
    ├── upload-sheet.sh             - end-to-end: CSV → Feishu spreadsheet
    └── upload-sheet-literal.sh     - default vs --literal mode comparison
```

## Design principles

1. **Thin orchestration > heavy implementation**: if an existing tool does it, don't write your own
2. **Let the caller pass links/parameters**: zero hardcoded values in scripts; switching tenants/projects requires no code change
3. **Self-diagnostic**: `setup.sh` + `probe.sh` let agents diagnose their environment independently
4. **Actionable errors**: every failure point maps to a specific fix recipe in `docs/error-codes.md` — no staring at a wall
5. **Graceful degradation**: when external dependencies (feishu-docx / uploader) are missing, fall back to stdlib or to each other; when LaTeX detection fails, retry via feishu-docx — base capability never breaks

## Troubleshooting

When something breaks, run `bash bin/probe.sh` first to see which step fails. Common error code cheat sheet:

| Code | Meaning | Quick fix |
|------|---------|-----------|
| `99991672` | Insufficient app identity scope | Add scope on open platform + publish a new version |
| `131006` | Not a member, or wiki not public | Read: add app as wiki member; Write: add edit role |
| `20027` | Insufficient OAuth scope | Use `OAuth2Authenticator(scopes=[...])` to request only the minimum set |
| `20029` | redirect_uri mismatch | Add `http://127.0.0.1:9527/` (with trailing slash) under open platform → security settings |

Full manual at [docs/error-codes.md](./docs/error-codes.md).

## Acknowledgements

This project stands on the shoulders of these tools:

- [feishu-docx](https://github.com/JessonChan/feishu-docx) — Python SDK + CLI, the core of the download path
- [feishu-markdown-uploader](https://github.com/0xE1337/feishu-markdown-uploader) — Node uploader, exclusive LaTeX equation rendering
- [feishu-markdown](https://github.com/huandu/feishu-markdown) — the underlying markdown → Feishu blocks library that uploader depends on

What we add is **decision routing** and **knowledge distillation** — not reinventing wheels.

## Contributing

PRs welcome. When opening one, please:

- Don't commit real `FEISHU_APP_ID` / `FEISHU_APP_SECRET` (`.gitignore` already filters `.env`)
- Don't put concrete business wiki links or tokens in `examples/` or `docs/`
- New error code handling → update [docs/error-codes.md](./docs/error-codes.md)
- New auth path → update [docs/auth-modes.md](./docs/auth-modes.md)

## License

[MIT](./LICENSE)
