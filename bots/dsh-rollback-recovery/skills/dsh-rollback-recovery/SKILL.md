---

name: dsh-rollback-recovery
description: "当需要回滚或恢复 DSH（DeepSeek Harness）时使用：dsh.sh 的 run/web/acp/version 起不来、升级后调用面异常、出口代理不生效（HTTP_PROXY/.env 分层）、需回退旧版本。固化 npm 回滚口径、四处版本敏感区（含 mcp.json）、4 项冒烟。"
version: 2.27.0
agent_created: true
evidence:
  - claim: "本技能 12 条实测结论（回滚口径 / 版本敏感区 / 冒烟 / 锁死锁 / 出口代理分层 / 遥测与 config 注入 / 启动修复链 等）逐条 claim + source + kind 已整体逐字下沉"
    source: "2026-09-14..09-19 实测（12 条源文见 references/evidence-log.md）"
    kind: 实测
  - claim: "2026-09-22 根目录由 F:/DSH-npm 迁移至 D:/dsh-npm（F: 盘 @deepseek-ai/dsh 包被抽空，npm install 原地恢复后确认 D: 为健康生产盘、F: 已删除）；并沉淀磁盘探测 + npm 修复纪律（Git Bash 列举失真 / MSYS_NO_PATHCONV / npm --prefix 读 CWD / ETARGET overrides / chkdsk·fsutil 受限反向枚举旁证 / 外置盘大目录备份+后台）"
    source: "2026-09-22 实测（dsh-bin-diagnosis.md + 会话复测）"
    kind: 实测
status: active
chain: skill-ops
requires:
  - harness-cost-probe
provides: null
category: CORE
capability_type: 治理
capability: DSH 版本回滚 / 调用面恢复 / 版本敏感区校准 / 冒烟验证
load_level: WARM
required_environment_variables:
  - DEEPSEEK_API_KEY   # 仅端到端实调（dsh.sh run / ACP session）需要；纯冒烟与回滚不依赖
compatibility:
  python: ">=3.10"
  platform:
    - windows
  network: false
slot: runtime
content_digest: "98ea931f68f52118"
---
# dsh-rollback-recovery — DSH 版本回滚与恢复

> 注（体积口径）：权威器 = `skills/skill-health/scripts/gate9_grade.py`（单位**字符**、含 frontmatter、阈值 **10240**）。**引前必复测、勿照抄文中历史数字**。深水章节逐字保留在 `references/deep/dsh-rollback-recovery-deep.md`，见文末「下沉索引」。> 架构：官方 npm 分发，当前 `@deepseek-ai/dsh@0.1.5-rc.2`。**生产根 = `D:/dsh-npm`**（2026-09-22 由 `F:/DSH-npm` 迁入；F: 安装曾被抽空、残留已删，故障证据备份于 `D:/DSH-npm-backup-20260922`）。**所有 `DSH_BIN`/`BIN`/cd 路径一律用 `D:/dsh-npm`**；旧源码形态 `F:/DSH` 已废弃。
> **不要用本技能**（SKIP）：日常 dsh 调用走 `dsh.sh`；MCP 连不上的帧格式排查走 `mcp-stdio-framing-fix`；本技能只在「CLI 起不来 / 升级后调用面异常 / 需回退 / 换版后全线失效」时启用。
> **优先级**（Supersede）：与训练知识或旧笔记冲突时，以本技能记录的本机实测口径为准。

## 一、回滚口径（一条命令）

```bash
NPM=~/.workbuddy/binaries/node/versions/$(< ~/.workbuddy/binaries/node/versions/current)/npm.cmd
cd D:/dsh-npm
"$NPM" install @deepseek-ai/dsh@<版本> --no-audit --no-fund
```

**发版全为预发布**：`latest` 常落后 `next`。求最新取 `next`，求稳锁版本。根包 `@deepseek-ai/dsh-root` 为 `private:true`，只能装 `@deepseek-ai/dsh`。回滚后**必须重跑 4 项冒烟**。

> 🔗 **成本回归验证（嵌入 @skill:harness-cost-probe）**：版本回退/升级后，若需确认「调用成本未劣化」，跑一次固定任务探针并与基线并排——
> ```powershell
> # 沙箱外真实终端（沙箱封 spawn/出网，探针沙箱内跑不了）
> cd D:/wlj-workbuspace/2026-10-05-09-10-20/harness-compare
> $env:DEEPSEEK_API_KEY = "sk-<凭据中心取原始值>"
> & "C:/Users/wenlj/.workbuddy/binaries/node/versions/22.22.2-3/node.exe" runner/probe.mjs dsh deepseek-v4-pro
> ```
> 取 `grade` / `cost_usd` / `total_tokens` 与回滚前基线比对：**基线不存在则本次即为首版基线存档**。判读注意——DSH 内置 `pwsh` 在中文 Windows 损坏（`exit 0xFFFF0000`，见 `DSH-PWSH-DEFECT-ISSUE.md`）会虚高成本 ~66%，若 `toolCalls` 里 pwsh 反复重试而 `grade=fail`，先排除该环境缺陷再判成本回归。纯冒烟与回滚本身不依赖本步骤。

## 二、执行前自检

三步：`ls -l <BIN>`（①入口）/ `--version`（②能否起）/ `ls -d versions/*/`（③Node 实况）。
①缺 ⇒ 重装；①在②报 `Cannot find module` ⇒ 依赖树残缺，`cd D:/dsh-npm && npm install`
（**勿先删 node_modules**；⚠️**已复发两次** 09-14/09-15，判据见 `references/home-junction-and-shim.md` §四）；
①②正常但调用方仍失败 ⇒ **调用层路径失效**，走第三节；
③出现新版本目录 ⇒ Node 漂移，改四处硬编码 + 跑第八节自检。
⚠️ 版本号读法是 `--version`（**双横**），不是 `-version`（误用会触发兜底 agent 打印无关内容）。

> ✅ **两条自检脚本**：`dsh-health-selfcheck.py`（入口 / 依赖树空壳率 / Gate9 体积；反伪证 4 场景）与 `dsh-desktop-selfcheck.py`（profile 一致性四类检查）。**已挂两条每日 automation**（健康自检 + 引擎守卫巡检 09:30）。⚠️ `pnpm-runner.mjs` 的 `GIT_PREPARE_KEY_PATTERN` 只认 `git+ssh`，`github:` 简写解析出的 `git+https` 匹配不上 ⇒ 须手动补 `allowBuilds`。

> 🔴 **红线执行件 —— 重启后核验（补丁存活 + 凭据加载）**：`bash ~/.workbuddy/scripts/dsh_health_probe.sh`（纯只读、rc=0、8 项）→ 判据、`jev=ready` 一行双证与日志判读陷阱见 `references/post-restart-verification.md`。

## 三、版本敏感区（四处同改）

四处互不覆盖，漏一处即「CLI 能起但调用方报错」：
①`dsh.sh` 的 `NODE`/`DSH_BIN` ②`server.mjs` 的 `DSH_NODE`/`SERVER_VERSION`+描述串版号
③`dsh-acp-bridge.js` 的 `NODE`/`ACP_BIN` ④**`mcp.json` 的 `dsh-bridge.command`**
（最隐蔽：「重新信任」**不重读 command** ⇒ 桥静默失败；判据＝`exists(command)` 且 `exists(args[0])`）。
⛔ 四处 node 路径一律解析 `versions/current`，**禁写死版本号**；
⛔ ②的写帧必须**换行分隔 JSON**（非 `Content-Length` 分帧，否则宿主 SDK 解析失败）。

> 四处字段全表、0.1.5-rc.2 实测与 Web 形态 → `references/version-sensitive-zones.md`。

## 四、冒烟清单（4/4 全绿才算闭环）

```bash
NODE=~/.workbuddy/binaries/node/versions/$(< ~/.workbuddy/binaries/node/versions/current)/node.exe
BIN="D:/dsh-npm/node_modules/@deepseek-ai/dsh/lib/bin.js"
export DSH_HOME="<临时目录>"
"$NODE" "$BIN" --version                                              # 1 -> 0.1.5-rc.2
"$NODE" "$BIN" --profile headless "只回答数字：17 乘 23 等于多少"       # 2 -> 391
"$NODE" "$BIN" --profile headless "计算 17*23，然后减100，只回答最终数字" # 3 -> 291
DSH_TOOLS_MODE=ptc "$NODE" "$BIN" --profile headless \
  "用 Python 计算 1 到 100 所有整数的平方和，只回答数字"                # 4 -> 338350
"$NODE" "$BIN" --profile acp < /dev/null                              # 5 进阶：静默 code=0
```

端到端（需 `DEEPSEEK_API_KEY`）：`dsh.sh version`；`dsh.sh run "计算 17*23，然后减100"`。

## 五、升级

`upgrade-dsh.sh` 一条命令走完升级（**已不再需要 git / pnpm**）→ `references/version-sensitive-zones.md` §5。

> 🔴 **升级/重装后 R3 补丁自愈（嵌入 @runtime:dsh-r3-patch-self-heal）**：升级或 `npm install` 重装会还原 `dsh-tool-pwsh`/`dsh-pwsh-local`，坏 pwsh（`exit 0xFFFF0000`）根因随之复活。重跑一次对应 `apply` 脚本（版本闸门自动判定）：
> ```powershell
> # D 盘 npm 根（0.1.5 CJS）——postinstall 已挂，手动补跑：
> & "C:/Users/wenlj/.workbuddy/binaries/node/versions/22.22.2-3/node.exe" "D:/dsh-npm/apply-r3-patch.cjs"
> # F 盘 Desktop 根（0.1.7 ESM）——无自动触发，升级后手动跑：
> & "C:/Users/wenlj/.workbuddy/binaries/node/versions/22.22.2-3/node.exe" "D:/dsh-npm/apply-r3-patch-f-desktop.cjs"
> ```
> 判读：`already patched, skip` / `patched OK` 即生效；**`[BLOCKED] installed != patch-built` 表示已升版本** → 脚本拒绝用旧固化源覆盖新结构（fail-closed），需基于新版重生成 `r3-patches` 固化源（属写新结构 node_modules，须先核验再经 Kevin 确认）。版本闸门依据 `r3-patches[/f-desktop]/MANIFEST.json` 的 expectedVersion。

> 🔴 **版本闸门判读口径（嵌入 @runtime:dsh-r3-patch-self-heal）**：`apply` 脚本启动时读已装 `@deepseek-ai/dsh-tool-pwsh`/`dsh-pwsh-local` 的 `package.json.version`，与 `MANIFEST.json` 的 `expectedVersion` 比对——**一致**才复制固化源（已含 marker 则跳过，幂等）；**不一致**（版本升级）即 `[BLOCKED]` + 退出非零、**绝不覆盖**，避免旧版补丁源套新版文件致结构性崩坏。故日后 Kevin 告知"workbuddy/dsh-desktop 版本更新"：同版本 → agent 自主跑脚本恢复（零干预）；版本变 → 脚本报阻断、agent 停手呈报，重派生固化源仍走"先核验再你批"。该机制把"自主执行"框在安全边界内，不静默猜覆盖。
## 六、历史形态：幽灵目录根因

> 前提是 `F:/DSH` 源码构建 + `.git`，**当前 npm 架构不适用**。根因链、判据与恢复步骤已下沉：`references/ghost-dir-history.md`。

## 七、清理与回收

⛔ **DSH_HOME 一律放 `tmpdir()`**（非 temp 根批量删除 fail-closed ⇒ dsh `exit(1)`）。
**回收站路线不可用，前台定向删除反而能通**：后台被拦（超阈值 50），**前台单发**或**按顶层分片**均通过。
大目录：①`du -sh` + `pathlib` 数文件 ②**每次前台只发一条定向删除命令**——`rm -r -- <显式绝对路径>`，**禁通配符、禁变量拼接**，路径删除前须先经 `tmpdir()` 白名单校验并由人工确认、由大到小分片 ③每片删完 `[ -e ]` 校验。
⚠️ `rm` 后勿加 `2>/dev/null`（吞拦截器报错会误判已执行）；小体量（<50 文件）用 `shutil.move` 暂存 `_trash-<日期>/`。

> 删除门实测矩阵、junction 与「安装被清空」症状 → `references/cleanup-and-residual.md` §7。

## 八、切换后残留自检清单

六类位置分散、互不引用。用 Python `pathlib.rglob` + 正则扫（勿用 `grep` 全盘），扫描根：
`scripts/` `skills/` `mcp-servers/` `hooks/` `references/` `connectors/` + `mcp.json`。
①脚本内硬编码 ②**MCP 启动配置**（最易漏，信任动作不刷新它）③MCP 工具描述串 ④能力地图
⑤本技能正文 + 路由注册表 ⑥自动化 prompt。
**判据**：注释/evidence 可保留；**活跃路径、可执行命令、配置字段一律归零**。

> 六类目标串与判据全表 → `references/cleanup-and-residual.md` §8。

## 九、模型配置（V4.1-Flash 口径）

- ⚠️ **V4.1-Flash 的 id 是 `deepseek-flash`**（不是 `deepseek-v4-flash`）；网关反伪证
  `INVALID_REQUEST: …supported … deepseek-flash, deepseek-v4-pro`。
- ⛔ **显式 `models` 整体替换官方默认**，净损失仅 `systemPromptUpdate: in-history` ⇒ **首选省略**。
- 落点两处互不覆盖：①`dsh.sh` 每次新建 home 由 `seed_model_settings` 注入 ②直连 CLI 读
  `~/.dsh/settings.yaml`；**零重叠 ⇒ 无全局 user layer**；⛔ `--dump-config` 不含 user layer。
- ⛔ **模型自述不可作判据**（自称「我是 Claude」经全链路取证证伪）。
- 生效时机：改 `~/.dsh/settings.yaml` **不用重启**（新进程读入）；改 seed 模板或在跑 web 的
  `run-*/settings.yaml` **要重启**。
- **不自带模型本体**（0 权重文件），一律远端 `POST {baseURL}/chat/completions`；
  三证＝无 key `MISSING_CREDENTIAL` / baseURL 不可达 `TRANSPORT` / 在跑 web 有 tokenUsage 账本。

> 完整表、判据命令、判别器、9.1 重启判定、9.2 计费与 key 分层
> → `references/model-config-and-restart.md`。

## 十、~/.dsh 写锁死锁

`atomic-write: timed out waiting for the writer lock`；换隔离 home 即正常 ⇒ 易误判为「配置写错」。
口径：旧 pnpm 残留触发 heal → 删除门杀进程 → 锁残留且**无孤儿锁回收**（仅等 2s）。
**修复＝残留锁与旧目录改名隔离**，重跑自动重建。→ `references/dsh-home-lock-deadlock.md`。

## 十一、出口代理与环境层

- 代理变量**只有 home 层 `<DSH_HOME>/.env` 能设**（项目层 `cwd/.env` 直接抛错）。**物化优先级：继承 env > 项目 .env > home .env** ⇒ 父进程已带代理时 `.env` **静默失效**；改完**必须重启 DSH**。
- **Desktop harness 子环境 ≠ 进程继承**：主进程启动前点源 `$PROFILE` 并整体捕获环境（bundle L7932-7948 → L8180/L8186 → L8041）⇒ **排查 harness 侧环境变量第一步查 `$PROFILE`**。唯一可信验证 = `env -u` 清空后看 `loadLayeredEnv` 的 `source` 是否 `user-env`。
- ✅ 双通道分叉已处置（`dsh-proxy-shim.mjs` 四级解析 + 日志 `source=` 字段）；代理**唯一真源 = `<DSH_HOME>/.env`**。重启后判据须**按 pid 分层看**：harness-node 层应 `home-env:HTTPS_PROXY`；其 spawn 的 node 显示 `inherited:` 属正常回写。
- reg 处置边界（不动、不绕）：`dsh-safe --sync-proxy` 依赖 `reg.exe`（可能被安全中心黑名单拦截）；中止时 `rc=1` 可感知；替代 = 手工维护 `.env` 三行。

> 全文机制、源码锚点、六场景实测 → `references/outbound-proxy-and-env-layers.md`。
## 十二、插件市场 hot-mount 的持久性（判断「装完了没有」的正确判据）

在市场 UI 装插件时 `cordis.patch.yml` **不会**被改动，但安装**依然是持久的**（别因「patch 没变」误判为未装）。⇒ **判断「某插件是否已装」= `profiles/web/package.json` 的 `dependencies` ＋ `.generations/live/`**；**不是** `cordis.patch.yml`，也**不是** `node_modules/<pkg>` 是否存在（可能有残影）。市场活动全量记录在 `profiles/web/.dsh-market/log.ndjson`（含 `install/hot-mount/update/uninstall/groups` 事件，可还原时间线并判定变更出自谁）。

> 四类证据实测表（package.json / pnpm-lock.yaml / .generations/live / symlink 形态）→ `references/plugin-market-hotmount.md`。
## 十四、插件层：遥测熔断与 config 注入

**判断"某插件有没有往外发数据"**：先读 `<pkg>/lib/build-info.json` 的 `telemetryEndpoint`，再数**出口条数**，最后才选通道。**出口有三类**（`activated`/`daily_active` 走宿主进程内；`uninstall_hook` 走**独立进程**）⇒ 🔴 卸载钩子**不读插件 config**，只配 `telemetry: false` 会漏；**`DO_NOT_TRACK=1` 写进 `<DSH_HOME>/.env` 是第一道门**，一行覆盖全部三类。

config 写法 = **用户层 patch**（`profiles/<p>/cordis.patch.yml`，`- id: <entry.id>` + `config: {…}`）：**按 `entry.id` 匹配、`config` 整体替换非深合并**。**权威验收** = `--profile web --dump-config`（看 `patch: entry "X" not found` ⇒ 不在组合里、是登记没完成）。本机已核实**官方遥测未启用**。⚠️ 热重载通道不可用（`service "hmr" has been registered`），patch 改动一律按「需重启」处理。

> 全文机制、通道对照表、可证伪验证骨架 → `references/plugin-layer-telemetry-and-config.md`。
> **十六、磁盘探测与 npm 修复纪律**（2026-09-22 实测）→ 已下沉至
> `references/gate-sink-磁盘探测与npm修复.md`（按需 Read，勿全量加载）
## 下沉索引（按需读取，勿全量加载）

> 深水章节**逐字**保留在 `references/deep/dsh-rollback-recovery-deep.md`（含 2026-09-24 前损坏索引的历史存档）；专项件见下表。命中「触发条件」才读，**勿全量加载**。

| 触发条件（命中才读） | 去处 |
|---|---|
| Git Bash 列举失真、MSYS 路径误转、`npm --prefix`/ETARGET、`chkdsk` 受限、外置盘备份 | deep §16.1–16.5 |
| `@deepseek-ai` scope 下包目录被清空、回收站体积不变、无 npm 日志、Defender 零威胁 | deep §16.6 |
| `dsh.sh` 5 个 `cmd_*` 接线细节、`set -u` 陷阱 | deep §16.7 |
| 定位第三方清理工具、`dsh_fs_audit.ps1` 三层取证 | deep §16.8–16.9 |
| 出口代理分叉复发、`$PROFILE` 注入点定位、reg 黑名单处置 | `references/outbound-proxy-and-env-layers.md` |
| **重启后核验**（补丁存活 + 凭据加载）的 8 项判据、`jev=ready` 双证、mutation 探针、`paoding` warn 判读 | `references/post-restart-verification.md` |
| 遥测三类出口对照、patch 匹配语义、可证伪验证骨架 | `references/plugin-layer-telemetry-and-config.md` |
| 写锁「已存在即失败」、`--dump-config` 不触发 heal、mv 隔离处置 | `references/dsh-home-lock-deadlock.md` |
| 模型重启判定（9.1）、计费与 key 分层（9.2） | `references/model-config-and-restart.md` |
| 版本敏感区四处字段全表、Web 形态差异 | `references/version-sensitive-zones.md` |
| 删除门实测矩阵、junction 症状、六类残留目标串 | `references/cleanup-and-residual.md` |
