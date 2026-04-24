# Multica Agent 集成

本项目可作为 [Multica](https://github.com/multica-ai/multica) agent 的 skill 使用，让 agent 能从飞书读写 Markdown。

## 前提

- Multica agent runtime（ECS 或其他 Linux 机器）已部署
- agent 能 `git clone` 和执行 bash 脚本
- 目标飞书应用已配好（至少 `wiki:wiki:readonly` + `docx:document:readonly` 应用身份权限，发版通过）

## 配置步骤

### 1. 在 Multica agent 的 `custom_env` 里设置凭证

```
FEISHU_APP_ID=cli_xxxxxxxxxxxxxxxx
FEISHU_APP_SECRET=xxxxxxxxxxxxxxxxxxxxxxxx
# 可选：Lark 国际版
FEISHU_HOST=open.larksuite.com
```

> ⚠️ `FEISHU_APP_SECRET` 属于应用密钥。Multica 的 `custom_env` 是明文存储在 Postgres 里的。建议定期在飞书开放平台重置 secret。

### 2. 在 Agent Instructions 里加一段自装逻辑

```markdown
## 首次启动：准备 feishu-sync 工具

```bash
# clone + install（幂等，已装则跳过）
[ ! -d /tmp/feishu-sync ] && git clone --depth=1 https://github.com/<YOUR_FORK>/feishu-sync.git /tmp/feishu-sync
bash /tmp/feishu-sync/bin/setup.sh

# 自检
bash /tmp/feishu-sync/bin/probe.sh
```

## 工具调用

- 下载飞书 wiki 空间：`bash /tmp/feishu-sync/bin/download.sh <wiki_url> -o <out_dir> --recursive`
- 下载单个 docx：`bash /tmp/feishu-sync/bin/download.sh <docx_url> -o <out_dir>`
- 上传 md（自动检测公式）：`bash /tmp/feishu-sync/bin/upload.sh <file.md> --title "标题"`
```

### 3. 任务协议示例

当用户要求 agent "把飞书 wiki 的 specs 同步下来"：

```
请下载以下飞书 wiki 到本地并返回路径：
wiki_url: https://xxx.feishu.cn/wiki/PQ3Hwf...
out_dir: /tmp/specs/
```

Agent 应：
1. 跑 `bash /tmp/feishu-sync/bin/probe.sh --wiki <wiki_url>` 自检
2. 跑 `bash /tmp/feishu-sync/bin/download.sh <wiki_url> -o <out_dir> --recursive`
3. 把下载结果路径返给用户

## 错误处理

Agent 执行失败时，必须：

1. 打印错误码（看 `bin/download.sh` / `bin/upload.sh` 的 stderr）
2. 对照 [`docs/error-codes.md`](./error-codes.md) 给出操作建议
3. 不要自己瞎猜修法——按文档走

## 为什么 agent 应该"自己拉"而不是用户推送文件

传统思路：用户在本机下载好 md → scp 到 ECS → agent 读。

**本项目推荐**：agent 有 bash/git/curl，让它自己 `git clone` 本工具，用 tenant_access_token 直接从飞书拉。

好处：
- 数据始终是最新版（飞书侧改了 agent 下一次拉就看到）
- 不依赖 ECS 管理员的 scp 权限
- 凭证集中在 `custom_env`，比分发文件安全

详见同目录下 `../README.md` 的"设计原则"章节。

## 与其他飞书工具的关系

| 工具 | 我们的态度 |
|------|----------|
| `feishu-docx` (Python CLI) | 依赖。下载全走它 |
| `feishu-markdown-uploader` (Node) | 依赖。有公式的上传走它 |
| `feishu-markdown` MCP server | 平行方案。agent 可以 MCP 或走我们的 bash，看场景。MCP 在 agent runtime 里启动成本高时，bash 更简单 |
| `web-access` skill 里的 `feishu.cn.md` site-pattern | 互补。本项目管 Open API；site-pattern 管 CDP 浏览器 |

## 开源化注意事项

如果你把这个 fork 出来开源，检查 3 件事：
1. 不要在 examples/ 或 docs/ 里放你们公司的真实 wiki_url / app_id
2. `.env.example` 必须用 placeholder，不能有真实 secret
3. README 里的 sample 数据应该泛化，不带具体业务语义
