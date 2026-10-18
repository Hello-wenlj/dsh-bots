# R3 补丁自愈 / 版本闸门 / 成本回归验证（从 SKILL.md 下沉，逐字保留）

> 下沉原因：SKILL.md 超 Gate9 体积阈值（10240 字符），把这三块**命令细节**移出正文，
> 正文只留判读口径与指针。**内容逐字未改**，判读规则与原来一致。

## 一、成本回归验证（嵌入 @skill:harness-cost-probe）

版本回退/升级后，若需确认「调用成本未劣化」，跑一次固定任务探针并与基线并排：

```powershell
# 沙箱外真实终端（沙箱封 spawn/出网，探针沙箱内跑不了）
cd D:/wlj-workbuspace/2026-10-05-09-10-20/harness-compare
$env:DEEPSEEK_API_KEY = "sk-<凭据中心取原始值>"
& "C:/Users/wenlj/.workbuddy/binaries/node/versions/22.22.2-3/node.exe" runner/probe.mjs dsh deepseek-v4-pro
```

取 `grade` / `cost_usd` / `total_tokens` 与回滚前基线比对：**基线不存在则本次即为首版基线存档**。

判读注意——DSH 内置 `pwsh` 在中文 Windows 损坏（`exit 0xFFFF0000`，属环境缺陷、非版本问题）
会虚高成本 ~66%，若 `toolCalls` 里 pwsh 反复重试而 `grade=fail`，先排除该环境缺陷再判成本回归。

**纯冒烟与回滚本身不依赖本步骤。**

## 二、升级/重装后 R3 补丁自愈（嵌入 @runtime:dsh-r3-patch-self-heal）

升级或 `npm install` 重装会还原 `dsh-tool-pwsh`/`dsh-pwsh-local`，坏 pwsh（`exit 0xFFFF0000`）
根因随之复活。重跑一次对应 `apply` 脚本（版本闸门自动判定）：

```powershell
# D 盘 npm 根（0.1.5 CJS）——postinstall 已挂，手动补跑：
& "C:/Users/wenlj/.workbuddy/binaries/node/versions/22.22.2-3/node.exe" "D:/dsh-npm/apply-r3-patch.cjs"
# F 盘 Desktop 根（0.1.7 ESM）——无自动触发，升级后手动跑：
& "C:/Users/wenlj/.workbuddy/binaries/node/versions/22.22.2-3/node.exe" "D:/dsh-npm/apply-r3-patch-f-desktop.cjs"
```

判读：`already patched, skip` / `patched OK` 即生效；**`[BLOCKED] installed != patch-built` 表示已升版本**
→ 脚本拒绝用旧固化源覆盖新结构（fail-closed），需基于新版重生成 `r3-patches` 固化源
（属写新结构 node_modules，须先核验再经 Kevin 确认）。版本闸门依据 `r3-patches[/f-desktop]/MANIFEST.json`
的 expectedVersion。

## 三、版本闸门判读口径（嵌入 @runtime:dsh-r3-patch-self-heal）

`apply` 脚本启动时读已装 `@deepseek-ai/dsh-tool-pwsh`/`dsh-pwsh-local` 的 `package.json.version`，
与 `MANIFEST.json` 的 `expectedVersion` 比对——**一致**才复制固化源（已含 marker 则跳过，幂等）；
**不一致**（版本升级）即 `[BLOCKED]` + 退出非零、**绝不覆盖**，避免旧版补丁源套新版文件致结构性崩坏。

故日后 Kevin 告知「workbuddy/dsh-desktop 版本更新」：

| 情形 | 动作 |
|---|---|
| 同版本 | agent 自主跑脚本恢复（零干预） |
| 版本已变 | 脚本报阻断、agent 停手呈报；重派生固化源仍走「先核验再你批」 |

该机制把「自主执行」框在安全边界内，不静默猜覆盖。
