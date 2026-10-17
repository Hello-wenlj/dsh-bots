# dsh-rollback-recovery 下沉明细（三、版本敏感区四处同改） —— 下沉明细

> 由 `SKILL.md` 下沉（Gate9 体积门禁 10240 字节）。**原文逐字保留**，
> 未做任何改写：本文件的内容是从 SKILL.md 的行区间原样搬过来的，
> 因此「信息零损失」是构造性的，不是声称的。判定口径/阈值/纪律仍以 SKILL.md 为准。

## 三、版本敏感区（四处同改）→ 留四处清单 + 两条硬约束（原 SKILL.md L86–L105）

## 三、版本敏感区（四处同改）

四处互不覆盖，漏一处即「CLI 能起但调用方报错」：

| # | 文件 | 字段 |
|---|---|---|
| 1 | `~/.workbuddy/scripts/dsh.sh` | `NODE`、`DSH_BIN`（顶部集中） |
| 2 | `~/.workbuddy/mcp-servers/dsh-bridge/server.mjs` | `DSH_NODE`、`DSH_BIN`、`SERVER_VERSION`，**及 `dsh_run` 描述串里的版号** |
| 3 | `~/.workbuddy/scripts/dsh-acp-bridge.js` | `NODE` 默认值、`ACP_BIN` |
| 4 | **`~/.workbuddy/mcp.json` 的 `dsh-bridge` 条目** | **`command` 里写死的 node.exe 全路径**、`description` 版号 |

> ⚠️ 第 4 处最隐蔽：不在脚本内，只在 MCP 启动配置；「重新信任」**不重读 `command`**，写错时「信任过了但 `dsh_run` 始终不可用」，桥启动阶段即静默失败。
> 判据：`os.path.exists(command)` 与 `os.path.exists(args[0])` 须均为 True。
> ⛔ 第 2 处另有**硬约束**：写帧必须**换行分隔 JSON**（MCP 规范），非 `Content-Length` 分帧（LSP 约定）；否则宿主官方 SDK 解析失败（`-32000 Connection closed`）。分帧排障详见 `mcp-stdio-framing-fix`。

⛔ **四处 node 路径一律解析 `versions/current`，禁止写死版本号**：目录名随重新供给变化，写死即全线静默失效。`DSH_BIN`=`F:/DSH-npm/.../dsh/lib/bin.js`。

**0.1.5-rc.2 实测**：`ACP_PROFILE="acp"` 首用自动初始化；`DSH_TOOLS_MODE=ptc`；`--patch <yml>`；`dsh web`=`--profile web`。

**Web 形态（2026-09-14 首启实测）**：`dsh.sh web [--port <n>]` → 监听 `127.0.0.1:<port>`（默认 3080），打印 `?token=<43 位>` URL 并自动开浏览器（`--no-open` 关闭）；`?token=` 首访换 `dsh-auth-*` cookie 后根路径 200，无 token 401；长驻独占 `.dsh.lock`；`DSH_HOME` 走 `dshhome/run-*`。

# dsh-rollback-recovery 下沉明细 —— 下沉明细

> 由 `SKILL.md` 下沉（Gate9 体积门禁 10240 字节）。**原文逐字保留**，
> 未做任何改写：本文件的内容是从 SKILL.md 的行区间原样搬过来的，
> 因此「信息零损失」是构造性的，不是声称的。判定口径/阈值/纪律仍以 SKILL.md 为准。

## 五、升级（原 SKILL.md L103–L107）

## 五、升级

`bash ~/.workbuddy/scripts/upgrade-dsh.sh [--dry-run] [--version <x.y.z-rc.n>]`：
查本地版 → 查 npm `next`/`latest` → 停实例 → `npm install` → 冒烟比对。**已不再需要 git / pnpm**。

