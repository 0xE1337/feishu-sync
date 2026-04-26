# 飞书 Open API 权限模型（实测归纳）

飞书对每个 API 端点独立鉴权，不是"加成员 or 不加"的二元问题。权限分**三层独立**检查：

## 第 1 层：应用身份 scope

**在哪里配**：开放平台 → 应用 → 权限管理 → 「应用身份可获取的权限」

**典型 scope**（本项目需要）：
- `wiki:wiki` 或 `wiki:wiki:readonly` — 读 wiki 节点
- `docx:document:readonly` — 读 docx 正文
- `docx:document` — 写 docx 正文（创建/更新）
- `drive:drive` — 云盘文件管理（用于 create 到指定 folder）
- `sheets:spreadsheet` — 创建/读/写电子表格（`upload-sheet.sh` 必需）
- `sheets:spreadsheet:create` — 仅创建空电子表格（颗粒度更细的最小集，配合 `drive:drive` 用）

**没过这层**：`code: 99991672 insufficient scope`

## 第 2 层：空间级公共可读（wiki 专有）

**在哪里配**：wiki 知识库设置 → 权限 → 空间可见性

- `本租户可读` — 租户内任何带 scope 的应用都能读节点内容（**常见默认值**）
- `链接可访问` — 拿到 wiki_token 就能读
- `仅成员可读` — 必须第 3 层有记录

**没过这层 + 非成员**：`code: 131006` on 节点读取

## 第 3 层：应用是否是空间成员

**在哪里配**：wiki 知识库 → 成员管理 → 添加应用

- 是成员 → 可列 spaces / 可读 space 元信息 / 按 role 决定能否写
- 不是成员 → 列 spaces 返空、读 space 元信息拒、写操作拒

## 实测 API ↔ 权限对应表

同租户 + scope 齐全 + 租户可读开 + **非成员**的场景（2026-04-24 实测）：

| API | 可用？ | 失败错误码 | 需要哪层 |
|-----|-------|---------|--------|
| `wiki/v2/spaces/get_node?token=X` | ✅ | - | 1 + 2 |
| `wiki/v2/spaces/{id}/nodes?parent_node_token=X` | ✅ | - | 1 + 2 |
| `docx/v1/documents/{obj_token}/raw_content` | ✅ | - | 1 + 2 |
| `docx/v1/documents/{obj_token}/blocks` | ✅ | - | 1 + 2 |
| `wiki/v2/spaces/{id}/members` 列成员 | ✅ | - | 1（此端点较宽松） |
| `wiki/v2/spaces` 列应用可访问的所有 space | ⚠️ 返回空 | - | 第 3 层 |
| `wiki/v2/spaces/{id}` 读 space 元信息 | ❌ | `131006` | 第 3 层 |
| `POST wiki/v2/spaces/{id}/nodes` 创建节点 | ❌ | `131006` tenant needs edit | 第 3 层 + edit role |
| `POST sheets/v3/spreadsheets` 创建电子表格 | ✅ | - | 1 (`sheets:spreadsheet` 或 `sheets:spreadsheet:create`)；指定 `folder_token` 还要 `drive:drive` |
| `GET sheets/v3/spreadsheets/{tok}/sheets/query` | ✅ | - | 1 (同上) |
| `POST sheets/v2/spreadsheets/{tok}/values_batch_update` 写值 | ✅ | - | 1 (`sheets:spreadsheet`) |

## 排查决策树（遇到 code:131006 时）

```
code:131006
├── 是写操作？（POST/PATCH/PUT/DELETE）
│   └── 是 → 需要应用成员身份 + edit role
├── 是读操作但是读节点内容（get_node / blocks / raw_content）？
│   └── 是 → wiki 可能是"仅成员可读"，需要加应用为 read 成员
├── 是读 space 元信息（/spaces/{id}）或列 spaces？
│   └── 是 → 正常现象。非成员不能读元信息/列空间。**绕到** get_node?token=X 定向读
```

## 什么时候必须加成员

| 场景 | 必须加？ |
|------|--------|
| 对方 wiki 关掉了"本租户可读" | ✅ |
| 跨租户 wiki | ✅ |
| 需要写（评论/创建/更新） | ✅ edit role |
| 需要列应用能访问的所有 wiki | ✅ |
| 仅读节点内容（同租户 + 租户可读开着） | ❌ 不需要 |

## 对本项目的意义

如果你的目标 wiki **同租户 + 开了本租户可读**：
- 只需要在开放平台开通 scope 并发版（一次性）
- **不需要**打扰 wiki 管理员
- 设置 `FEISHU_APP_ID` + `FEISHU_APP_SECRET` 环境变量即可调 API

如果是**跨租户** 或 **仅成员可读**：
- 必须联系 wiki 所有者把你的应用加为成员
- 应用在对方"添加文档应用"里搜索得到 = 第 1 层"应用可用范围"开为全员可用
