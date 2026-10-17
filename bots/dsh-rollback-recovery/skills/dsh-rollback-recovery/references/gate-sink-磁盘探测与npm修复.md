# 下沉存档（Gate9 body sink · 2026-10-06）

> 原文从 `SKILL.md` 的「## 十六、磁盘探测与 npm 修复纪律（2026-09-22 实测）」逐字搬入，**零删减**。
> 复原方式：把本文件内容原样贴回 SKILL.md 的原锚点位置。

---

## 十六、磁盘探测与 npm 修复纪律（2026-09-22 实测）

**背景**：`F:/DSH-npm` 的 `@deepseek-ai/dsh` 曾被抽空（目录在、`lib/` 缺失）⇒ `dsh.sh version` 报 `Cannot find module`；原地 `npm install` 恢复后确认 D: 为健康生产盘。

**四条纪律骨架**：① **列举失真** —— F: 盘 Git Bash `ls` 返回空/残缺 ⇒ 取证走 PowerShell 落盘读，直传 node 用 `MSYS_NO_PATHCONV=1`；② **npm 两坑** —— `npm --prefix` 仍读 CWD ⇒ 必须 `cd <dir> && npm install`，ETARGET 用 `overrides` 锁回已发布版本；③ **卷健康** —— `chkdsk`/`fsutil` 非提权必拒（**被拒 = 权限不足，不是卷故障**）⇒ 用「根目录完整枚举零 I/O 错误」反证；④ **外置盘大目录** —— `cp -r` 必须后台；**删前必整目录备份 + 验证副本**。

**引擎守卫（2026-09-23）**：唯一判据 = `@deepseek-ai` scope 下含 `package.json` 的包数（期望 **240**，得 0 即空壳，**不要看目录是否存在**）。`dsh_engine_guard.py`（`check`/`record`/`restore`/`selftest`） + `dsh.sh` 8 处 `_engine_guard || return 1` 接线。🔴 **`set -u` 陷阱**：可能未导出的开关一律写 `${VAR:-}`。

> §16.1–16.9 逐字全文 → `references/deep/dsh-rollback-recovery-deep.md`。
