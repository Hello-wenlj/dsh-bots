# B-market-evidence

> 由 dsh-rollback-recovery/SKILL.md 于 2026-09-20 **逐字下沉**，零改写。
> 动因：Gate9 体积门只量 SKILL.md（阈值 10240 字符）。

| 证据 | 本机实测 |
|---|---|
| `profiles/web/package.json` → `dependencies` | 30 项，含新装插件（19:09 更新）—— **这是首选判据** |
| `profiles/web/pnpm-lock.yaml` | 19:08 更新（依赖锁已写） |
| `profiles/.generations/live/<pkg>+<ver>+<hash>/` | 每包一个代际目录（如 `dsh-univer-office+0.3.2+e2dacd48c72c`）；`desired.json` 记「期望态」，原子切换 |
| 包目录形态 | **symlink**（指向 `.generations/live/…`）或实体目录，**两者都算装好** |
