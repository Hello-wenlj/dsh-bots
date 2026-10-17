# ~/.dsh 直连通道写锁死锁（2026-09-14 修复）

> 归属 `dsh-rollback-recovery` §十。dsh 0.1.5-rc.2（官方 npm 分发）。

**现象**：`DSH_HOME=~/.dsh` 起 dsh → `atomic-write: timed out waiting for the writer lock at ~/.dsh/profiles/node_modules.lock`；换 dsh.sh 的隔离 home 则正常 ⇒ 易误判为「配置写错」。

**根因链**：
1. 首启时 `healProfilesModuleFallback`（`dsh-app-boot/lib/index.js:657`）判定 `profiles/node_modules` 与当前安装代际不符（遗留**旧 pnpm 源码树时代**目录，193 顶层条目），进 `withFileLock` 修复。
2. 修复需替换该旧目录 → 触发应用级删除门 → 进程异常终止、`finally` 未执行 ⇒ **锁残留**（内容为已死 PID）。
3. 此后每次启动：锁已存在 ⇒ `wx` 冲突 ⇒ 默认仅等 **2 秒**（`DEFAULT_LOCK_WAIT_MS=2e3`）⇒ 报 timed out。`withFileLock` **刻意不清理孤儿锁**（原文：orphan recovery is an operator action）。

**判据**：锁内 PID 用 `OpenProcess(0x1000, False, pid)` 验证已不存在（err=87）；对照 dsh.sh 的隔离 home，`profiles/node_modules` 应为 **28664** 项。

**修复（可逆，rename 不触发删除门）**：

```bash
mv ~/.dsh/profiles/node_modules.lock ~/.dsh/profiles/node_modules.lock.stale-<ts>
mv ~/.dsh/profiles/node_modules      ~/.dsh/profiles/node_modules.old-pnpm-<ts>
```

重跑自动重建；实测修复后 `~/.dsh` 直连首跑通（exit=0）。`node_modules.old-pnpm-*` 可后续清理（junction 穿透，实际不占空间）。

**易混点**：与模型配置无关。改完 `settings.yaml` 后若直连仍报写锁超时，先按本节判锁内 PID 是否存活，勿回头改配置。

# §10 补充：~/.dsh 写锁死锁（自 SKILL.md 下沉） —— 下沉明细

> 由 `SKILL.md` 下沉（Gate9 体积门禁 10240 字节）。**原文逐字保留**，
> 未做任何改写：本文件的内容是从 SKILL.md 的行区间原样搬过来的，
> 因此「信息零损失」是构造性的，不是声称的。判定口径/阈值/纪律仍以 SKILL.md 为准。

## 十、写锁死锁 → 留口径 + 修复（原 SKILL.md L193–L196）

## 十、~/.dsh 写锁死锁（2026-09-14 修复）

**现象**：`DSH_HOME=~/.dsh` 起 dsh → `atomic-write: timed out waiting for the writer lock`；换隔离 home 则正常 ⇒ 易误判为「配置写错」。
**口径**：旧 pnpm 残留 `profiles/node_modules` 触发 heal → 删除门杀进程 → 锁残留且**无孤儿锁回收**（仅等 2s）。**修复 = 残留锁与旧目录改名隔离**，重跑自动重建。详见 `references/dsh-home-lock-deadlock.md`。
