# 飞书 Open API 鉴权模式选择

飞书提供 3 条鉴权路径，选择取决于**部署环境**和**凭证权限**。

## 路径对比表

| 路径 | 用什么 | 优点 | 卡点 | 适合 |
|------|-------|------|------|------|
| **A. CDP** | 本机 Chrome + `web-access` skill | 零配置，继承已登录 session | 不能上云（依赖本机浏览器） | 本地一次性下载、wiki 私密但你本人有权限 |
| **B. OAuth 个人授权** | `app_id/secret` + `feishu-docx auth` | 继承用户本人权限，不用加应用到 wiki | token 2h 过期；`offline_access` 需单独开通才能 refresh_token | 云端 + 触发频繁的 agent，用户个人权限够用 |
| **C. Tenant 应用授权** | `app_id/secret` + `tenant_access_token` | 长期不过期；适合无人值守 | 见 [permission-model.md](./permission-model.md)——同租户 + 租户可读 wiki 可直用；跨租户 / 私密 wiki 需要加成员 | 生产级无人值守、同租户 wiki 读写 |

## 决策树

```
你要部署在哪？
├── 云端（CI、agent、服务器）
│   ├── wiki 所在租户 = 你应用所在租户？
│   │   ├── 是 + wiki 对租户可读 → C. Tenant ✅ 首选
│   │   ├── 是 + wiki 仅成员可读 → C. Tenant + 让 wiki 所有者加应用为成员
│   │   └── 否（跨租户） → B. OAuth（用户个人权限）
│   └── 只需要用户本人权限、且 token 2h 过期能接受 → B. OAuth
│
├── 本地一次性下载
│   ├── 你本人已登录目标 wiki → A. CDP（最省事）
│   └── 需要程序化批量 → C. Tenant（如适用）或 B. OAuth
│
└── 开发调试
    └── A. CDP 最快看到内容
```

## 什么时候用哪个 feishu-docx 命令行 flag

| 命令 | 鉴权模式 | 说明 |
|------|--------|------|
| `feishu-docx export URL` | 默认 tenant | 最常用 |
| `feishu-docx export URL --auth-mode oauth` | OAuth | 需先 `feishu-docx auth` |
| `feishu-docx export-browser URL` | 浏览器 session | 等价于 A. CDP，用 Playwright |

## 本项目的默认选择

`feishu-sync` 默认使用 **C. Tenant**，原因：

1. agent 场景下 tenant_access_token 每次现拿，无需维持用户 session
2. 同租户 wiki + 开租户可读的场景（本项目测试配置）可直接读，不打扰他人
3. 错误可恢复——token 过期自动重取；scope 不足有明确操作步骤

## 切到 OAuth 的场景

- 目标 wiki 跨租户（你租户的应用访问不了别人租户的 wiki）
- 目标文档是私人 docx，没挂载到任何 wiki
- 需要写操作但无法加应用为 wiki 成员（只能借用用户个人 edit 权限）

## 切到 CDP 的场景

- 一次性本地下载
- 应用 scope 都不想申请，只想用自己浏览器里的 session
- 遇到 Open API 未覆盖的文档类型（少数旧 doc）
