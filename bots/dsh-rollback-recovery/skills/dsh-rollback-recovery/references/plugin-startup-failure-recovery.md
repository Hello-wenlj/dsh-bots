# 插件启动失败 → DSH Desktop「启动修复」对话框：完整恢复链

> 2026-09-19 本机实证（DSH Desktop / Windows / 内嵌 pnpm 10.34.5）。适用于任何
> 「Harness 在加载插件时发生错误」+ 弹「发现导致启动失败的插件」的场合。

## 一、症状与两层错误（极易混淆主次）

弹窗里同时出现两条信息，**必须分清主次**：

| 信息 | 性质 |
|---|---|
| `插件启动失败` + 插件名 | **主因**（插件本身把 harness 打死） |
| `未能获取市场版本信息…HTTP 404` | **次生症状**：市场按 npm 查该插件版本，而 GitHub 源插件不在 npm 上 ⇒ 必然 404。**不是**根因，也解释不了启动失败 |

⇒ **不要被 404 带走**。先看 `<DSH_HOME>/logs/harness.log` 里真正的 `DSH entry failed:` 行。

## 二、真实故障链（本机 2026-09-19 21:08-21:10 全链路）

```
资金链路：市场装 dsh-anydoc-markdown（GitHub: SeerableOfficial/dsh-anydoc-markdown，20:50）
  ↓
插件调用 ctx.webServer 却未声明 inject
  → index.js:561 `new apply()` → @deepseek-ai/dsh-client-connection/lib/index.js:618
  → Error: cannot get property "webServer" without inject
  → [harness-node] DSH entry failed: … plugin tree failed to load …
  → [desktop] Harness entry failed during startup; stopping immediately
  ↓
Desktop 自动隔离（plugin-recovery）：把插件搬进 recovery/plugin-removals/<id>/，并从 package.json
  的 dependencies + dsh.profile.bundles 摘掉（**摘除本身是成功的**，diff 证实唯一差异就是这两处）
  ↓
随后必须重跑 `dsh plugin install --profile web --no-frozen-lockfile` 才能落定
  ↓
重建在 pnpm 的 git 依赖 prepare 门被拦：
  ERR_PNPM_GIT_DEP_PREPARE_NOT_ALLOWED  Failed to prepare git-hosted package fetched from
  "https://github.com/jiruidai/dsh-meta-orchestrator.git"
  ↓
recovery/plugin-removals.json 里该条 status = `cleanup-pending`
  ↓
清不掉 ⇒ 每次开机重复弹「启动修复」
```

要点：**插件已被摘掉、但事务没收尾**。所以「进安全模式」「卸载此插件」「重新检查更新」三颗按钮
都不解决它（卸载=重跑同一条失败的重建；检查更新=查 npm 版本必然 404）。

## 三、pnpm 的两条通道、两套 id（这是本次最难的一环）

`ERR_PNPM_GIT_DEP_PREPARE_NOT_ALLOWED` 的键 = `<包名>@<pkgResolutionId>`。
pnpm 对 git 托管包有**两条独立代码路径，id 算法不同**——只补一条会继续被拦：

| 通道 | 触发 | id 算法（源码位置） | 键形 |
|---|---|---|---|
| tarball | 解析结果带 `resolution.tarball` | `prepareGitHostedPkg` → `createGitHostedTarballPkgResolutionId` = `resolution.tarball` | `name@https://codeload.github.com/<owner>/<repo>/tar.gz/<sha>` |
| **git clone** | 解析结果只有 `repo`+`commit` | `preparePackage(gitRootDir)` → `createGitHostedPkgId` = `git+${repo}#${commit}` | `name@git+<repo URL>#<sha>` |

**判据（一眼分辨走的哪条）**：报错文案里的取件地址。
`fetched from "…/tar.gz/<sha>"` = tarball 通道；`fetched from "https://github.com/<owner>/<repo>.git"` = **clone 通道**。

两条硬结论：

1. **不带 `#<sha>` 的「稳定键」永不匹配**（pnpm 的 git 托管 id 一律带 commit）。
   仓库里同时写 stable 键 + codeload 键「以防万一」是无效的，必须带 sha。
2. **DSH 自带的自动补键救不了 clone 通道的 https 形态**：
   `pnpm-runner.mjs#gitPrepareApprovalKey` 的正则**只认** `git+ssh://git@github.com/…`，
   对 `git+https://…` 直接返回 `undefined` ⇒ 不追加、不重试 ⇒ 重建失败。
   这解释了「为什么 yaml 时间戳没变、自动修复没生效」。

### 键的精确推导（不必猜，pnpm 源码可算）

```
报错里的 repo 形如 https://github.com/<owner>/<repo>.git   （含 "://" ⇒ 不补协议前缀）
createGitHostedPkgId({repo, commit}) ⇒ `git+https://github.com/<owner>/<repo>.git#<commit>`
commit = 该仓库默认分支 HEAD（用 git ls-remote <repo> refs/heads/main 取，40 位十六进制）
```

## 四、修复动作

在 `<DSH_HOME>/profiles/web/pnpm-workspace.yaml` 的 `allowBuilds:` 块内补**带 sha 的两条**：

```yaml
allowBuilds:
  'dsh-meta-orchestrator@git+https://github.com/jiruidai/dsh-meta-orchestrator.git#<sha40>': true
  'dsh-meta-orchestrator@git+ssh://git@github.com/jiruidai/dsh-meta-orchestrator.git#<sha40>': true
```

- 写 https 形态：clone 通道 id 的实际形态。
- 同写 ssh 形态：让 DSH 自带 runner 的正则也能命中（它只认 ssh 形态），未来 sha 变化时可由自动补键兜住。
- 两个来源都只放行**这一个包 + 这一个 sha**，不留通配（区别于 `dangerouslyAllowAllBuilds`）。

⚠️ **上游推新 commit 后 sha 变化，键会再次失配** ⇒ 复发时按 pnpm 打印的 hint 追加新键即可
（hint 原文形如 `onlyBuiltDependencies:\n  - "<name>@<id>"`）。**根治办法**是把该依赖固定提交
（`github:owner/repo#<sha>`）。

## 五、验收（重启后）

```bash
H="<DSH_HOME>"
grep -n "plugin-recovery\|Profile repair\|ERR_PNPM" "$H/../logs/harness.log" | tail -20
python -c "import json;d=json.load(open(r'$H/recovery/plugin-removals.json',encoding='utf-8'));print({k:v['status'] for k,v in d['removals'].items()})"
ls -la "$H/profiles/web/pnpm-lock.yaml"     # 重建成功后锁文件应回来
```

- 闭环判据：该 removal 的 status 由 `cleanup-pending` → **`removed`**；harness.log 无 `ERR_PNPM`；锁文件重建。
- 首启可能较久（整 profile 重装）；**期间不要杀进程**（skill §十：被强杀会留孤儿锁 / 半装 node_modules）。

## 六、附带必查的两处

1. **市场分组残留**：`profiles/web/.dsh-market/state.json` 的 groups 里该插件仍是成员
   （本次 `解析能力` 组含 `dsh-anydoc-markdown`）⇒ 将来点「应用分组」会把它装回来、当场复崩。
   要在市场 UI 里把它移出分组。
2. **启动失败报告已入队**：`desktop-service/outbox/<uuid>.json`
   （`kind: "startup-failure"`，含日志尾部，路径做了 `[USER]` 脱敏）。想避免外发就先确认反馈开关。

## 七、可复现的取证脚本（隔离环境，不碰真 profile）

```bash
NODE="F:/dsh_exe/DSH Desktop/resources/app/node_modules/node/bin/node.exe"
PNPM="F:/dsh_exe/DSH Desktop/resources/app/node_modules/pnpm/bin/pnpm.cjs"
# 目录内：package.json 放目标 git 依赖 + pnpm-workspace.yaml 控制 allowBuilds
cd <tmp> && "$NODE" "$PNPM" install --no-frozen-lockfile   # 故意不给键 ⇒ pnpm 会打印它要的精确键
```

⚠️ 坑：在 WorkBuddy 会话里跑上述命令，`NODE_OPTIONS` 注入的 safe-delete 垫片会让 pnpm 的临时目录
清理报 `[safe-delete] … ETIMEDOUT`（**与 pnpm/allowlist 无关的假故障**）。
判据：只要门禁错误（`ERR_PNPM_GIT_DEP_PREPARE_NOT_ALLOWED`）没出现，就说明放行已通过，
后面的报错可忽略。
