# 历史形态：幽灵目录根因（仅诊断参照）

> 由 `SKILL.md §六` 下沉（Gate9 体积门禁 10240 字节）。**内容逐字保留**。

## 前提

`F:/DSH` 由 `git checkout` 回滚且 `.git` 存在。**当前 npm 分发架构（`F:/DSH-npm`）不适用** —— 本文件仅供遇到同类症状时对照排查。

## 根因链

`git revert/checkout` 只删被跟踪源码，`lib/` 产物（gitignore）残留 → 下游版本独有的包成**幽灵目录**（无 `package.json`、0 跟踪文件但 `lib/` 还在）→ tsdown 按 workspace glob 当构建目标 → 找不到 package.json → 回溯根 `dsh-root` → 报 `Cannot find entry`。

## 判据与处置

- **⛔ 禁忌**：绝不把 tsdown entry 指向 `src/*.ts`；根配置 entry 永远是 `lib/types/{index,invariant,startup}.js`（`tsc -b` 产物），改 `src/X.ts` 会造出让人去追不存在的「rolldown 重定位 bug」的假象。
- **判据**：逐个 `packages/*/*` 取 `list(pkg.iterdir())` → 空=纯空；非空但无 `package.json`=幽灵；其余=正常。**幽灵类才是 CLI 起不来的直接原因**（只数空目录会漏掉占比更大的幽灵类）。
- **恢复**：① pathlib 遍历，把 `git ls-files --error-unmatch` 判为未跟踪的幽灵目录 `mv` 进 trash（勿用 bash find，Windows 有假阴性）；② `git checkout -- .`；③ `tsc -b tsconfig.host.json` + `tsdown --env.DSH_BUILD_FACE host`。
