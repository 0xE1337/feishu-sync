# 飞书 Open API 错误码操作手册

遇到错误时按本表查。每条给出：含义、触发条件、修法、**无需打扰他人就能做**的自助动作。

## 99991672 — insufficient scope

**含义**：应用身份 scope 不够调这个 API。

**典型触发**：
- 调 `wiki/...` 但应用没申请 `wiki:wiki` / `wiki:wiki:readonly`
- 调 `docx/...` 但应用没申请 `docx:document:readonly` / `docx:document`

**修法**（自助可做）：
1. 开放平台 → 应用 → 权限管理
2. 在「应用身份可获取的权限」tab 搜需要的 scope → 勾选
3. 版本管理 → 新版本 → 把新 scope 列在「权限变更」里 → 发布
4. 等管理员审批（一次性；公司/个人应用都要审批）

**绕开**：换成 OAuth 用户身份模式（`feishu-docx` 的 `--auth-mode oauth`），用用户个人权限代替。

## 131006 — permission denied / wiki space permission denied

**含义**：第 2 层（空间可见性）或第 3 层（成员身份）权限不过。

**区分读 vs 写**：

### 131006 on 读操作

**典型**：`wiki/v2/spaces/get_node` 返这个 code

**原因**：wiki 可能是"仅成员可读"

**修法**：
1. **自助**：先尝试 OAuth 用户身份（如果你本人是 wiki 读者）
2. **需要协调**：让 wiki 所有者 → 知识库设置 → 成员管理 → 添加应用 → 读权限

### 131006 on 写操作

**典型**：`POST wiki/v2/spaces/.../nodes` 或 `PATCH docx/.../blocks` 返 `tenant needs edit permission`

**修法**：让 wiki 所有者加应用为成员，role = edit

## 1254040 — resource permission

**含义**：针对单个 docx 文档的协作者级别权限不足（不是 wiki 级）

**修法**：文档右上角 分享 → 添加协作者 → 添加应用 → 可编辑

**注意**：飞书 doc 级协作者 dialog **不支持**搜应用——只能在 wiki 知识库级加成员。所以这个错误码如果出现在游离 docx（不属于 wiki）上，通常没有好的自助修法，只能让文档所有者操作。

## 20027 — OAuth scope 不足

**含义**：OAuth 授权时请求的 scope 超过应用实际拥有的 scope。

**典型触发**：`feishu-docx auth` CLI 默认请求 9 个 scope，用户应用只开了 3 个。

**修法**（绕过 CLI 默认）：直接用 SDK：
```python
from feishu_docx.auth.oauth import OAuth2Authenticator
auth = OAuth2Authenticator(
    app_id=APP_ID, app_secret=APP_SECRET,
    scopes=["docx:document", "wiki:wiki", "docx:document.block:convert"]  # 只请必需的
)
token = auth.authenticate()
```

## 20029 — redirect_uri 不匹配

**含义**：OAuth 授权回调 URL 跟开放平台配置的不一致。

**修法**：
1. 开放平台 → 应用 → 安全设置 → 重定向 URL
2. 添加一行**完全一样**的字符串：`http://127.0.0.1:9527/`（注意结尾斜杠）

**3 个常见失败**：
- 写成 `localhost` 代替 `127.0.0.1` → 挂
- 写成 `https://` → 挂（飞书对 127.0.0.1 特殊允许 http）
- 漏掉结尾斜杠 → 挂

## 10002 / 10003 — 请求参数错误

**修法**：看响应里的 `msg` 字段，通常明确指出哪个参数有问题。

## 常见组合症状

### "搜不到应用"（别人无法添加你的应用到文档）

**根因**：应用可用范围默认仅创建者可见。

**修法**：开放平台 → 应用 → 基础信息 → 应用可用范围 → 改为「全员可用」→ 重新发版。

### "申请 scope 后 API 仍返 99991672"

**根因**：scope 申请后必须**重新发版并通过审批**，当前运行版本的 scope 才会更新。

**验证**：权限管理页面，对应 scope 右边状态应该是「已开通」而不是「审核中」。

### OAuth token 2 小时后过期但拿不到 refresh_token

**根因**：`offline_access` scope 未开通或未在当前版本勾选。

**修法**：申请 `offline_access` scope 并重新发版，再次 OAuth 授权时就会返 refresh_token。

---

## 通用排查步骤（任何错误码都先这 3 步）

1. **跑 `bin/probe.sh`** 确认凭证和基础可达性
2. **看响应的 `msg` 字段** — 飞书的 msg 通常比 code 号人类可读
3. **对照本表 + [permission-model.md](./permission-model.md)** 找到对应层级
