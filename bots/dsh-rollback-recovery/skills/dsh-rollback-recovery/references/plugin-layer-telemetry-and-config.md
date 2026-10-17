# 插件层：遥测熔断与 config 注入

> 2026-09-19 实测。对象：第三方 DSH 插件（以 `dsh-univer-office@0.3.2` 为样本）。
> 本文解决两件事：① 怎么把某个插件的外发遥测**真正**关掉；② 怎么给已装插件**安全地**注入 config（含"改哪个文件"的机制依据）。

## 1. 遥测：先找到端点，再判定有几条出口

**第一步永远是找端点，不要凭 README 下判断。** 端点常藏在版本元数据里：

```bash
# dsh-univer-office 的实例
cat <profile>/node_modules/dsh-univer-office/lib/build-info.json
# → { "commit": "952e…", "telemetryEndpoint": "https://univer.ai/api/telemetry/cli", "version": "0.3.2" }
```

⇒ 端点 `https://univer.ai/api/telemetry/cli` 是**境外域名**。只要装机就等于把上报路径铺好了，与用户是否知情无关。

**第二步：数清出口条数。** 同一插件可能有多个独立入口，配置项只覆盖其中一部分：

| 出口 | 触发时机 | 入口形态 |
|---|---|---|
| `dsh_plugin_activated` | 插件首次激活 | 宿主进程内（`apply()` → `runHostTelemetry()`） |
| `dsh_plugin_daily_active` | 每自然日一次 | 同上 |
| `dsh_plugin_uninstall_hook` | 卸载时 | **独立进程入口**：`node lib/telemetry-entry.js capture dsh_plugin_uninstall_hook` |

⚠️ **卸载钩子是配置盲区**：它不经过插件的 `apply()`，因此**不读插件 config**。
`lib/telemetry-entry.js` 的 `if (process.argv[2] === "capture" && event === "dsh_plugin_uninstall_hook")`
是文件级的顶层判断，随后 `captureTelemetry()` 只检查两件事：`DO_NOT_TRACK` 与 endpoint 是否为空。
⇒ **只配 `telemetry: false` 会漏掉卸载那一次。**

## 2. 三条关闭通道与优先级

按"覆盖面 × 侵入性"排序：

| 通道 | 写法 | 覆盖范围 | 备注 |
|---|---|---|---|
| **DO_NOT_TRACK** | `<DSH_HOME>/.env` 加 `DO_NOT_TRACK=1` | **全部**（含独立进程入口） | 非空即生效，值不参与判断（W3C 通行约定）；跨插件、属有意耦合 |
| **插件 config** | `profiles/<p>/cordis.patch.yml` 加 `- id: <entry-id>` + `config: {telemetry: false}` | 宿主内两条 | 声明式、语义最明确；**漏卸载钩子** |
| **端点置空** | `<DSH_HOME>/.env` 加 `UNIVER_TELEMETRY_ENDPOINT=`（空串） | **全部** | 该插件的私有变量：`telemetryEndpointFor()` 见 `override !== void 0` 即取 `trim()`，空串 ⇒ `endpoint.length === 0` ⇒ `missing-endpoint` 跳过 |

**实证判据（`lib/index.js` 中 `captureTelemetry` 的前两道门）**：

```js
if (isDoNotTrack(env)) return { reason: "do-not-track", status: "skipped" };
if (input.endpoint.length === 0) return { reason: "missing-endpoint", status: "skipped" };
```

⇒ `DO_NOT_TRACK` 是**第一道门**，覆盖最广、成本最低（一行 env）。推荐组合：**`DO_NOT_TRACK=1`（主）+ `telemetry: false`（声明式冗余）**，两条互为独立解释、任一生效即熔断。

## 3. 验证：三件套，缺一不可

```bash
# ① env 层真的加载进去了吗（不是"我写了"而是"它读到了"）
#    用官方 loadLayeredEnv，看 source 与 path
node --input-type=module -e '…loadLayeredEnv("probe","C:/Users/wenlj")…'   # 见 §十一 的脚本骨架
# 期望： DO_NOT_TRACK | get={"value":"1","source":"user-env","path":"…\\harness\\.env"}
# 反伪证：对照组换另一个 DSH_HOME（其 .env 无此变量）→ get=undefined

# ② 配置合成是否真的生效
DSH_HOME="…/dsh-desktop/harness" node "<dsh>/lib/bin.js" --profile web --dump-config | grep -A8 "id: <entry>"

# ③ 是否已经上报过（**事后**才知道，用于评估暴露面）
cat <DSH_HOME>/telemetry/<package>/state.json
```

`state.json` 字段语义（`lib/telemetry-entry.js` 的 `markTelemetryEvent`）：
`activatedAttemptedAt` = 激活上报时间戳；`dailyActiveSentDate` = 已标记的日活日期（**每自然日只报一次**）。
⚠️ 注意写入顺序为 **先写 state 再 send** ⇒ **`dailyActiveSentDate` 存在 = 已"尝试"上报，不等于必然送达**；但"尝试"本身即已出网，评估暴露面时应按已发出计。

## 4. 注入 config：改哪个文件、按什么匹配

**权威落点 = `<DSH_HOME>/profiles/<profile>/cordis.patch.yml`**（"patch layer，applied after every bundle layer"）。
不要去改 `node_modules/<pkg>/cordis.patch.yml` —— 那是**包自带**的 bundle 层，会被重装覆盖。

机制（`@deepseek-ai/dsh-app-boot/lib/index.js:59-108` `applyEntryPatches`，逐字确认）：

```js
const { id, insert, name, ...overrides } = patch;          // L71
if (insert) { … }                                          // insert 分支见下
const target = entryMap.get(id);                           // L93 —— 按 **entry.id** 精确匹配
if (!target) { warn("patch: entry %C not found", id); continue; }
if (name && name !== target.name) { warn("… name mismatch …"); continue; }   // L98-101 可选防呆
for (const [key, value] of Object.entries(overrides)) target[key] = value;   // L104 —— 顶层整替换
```

三条必须记住的语义：

1. **匹配键是 `entry.id`**（不是 `name`）。包的 bundle patch 写 `- insert: [{id: univer, name: 'dsh-univer-office'}]` ⇒ 用户层要写 `- id: univer`。
2. **`config` 是整体赋值，不是深度合并** ⇒ 写了 `config:`，该插件的整个 config 就被你这份替换掉。
3. **`name` 可选但建议写** —— 不符会 warn 并跳过，等于给自己加了一道防打错 id 的闸。

**"只写差异字段"何时安全**：当且仅当该插件 `resolveConfig()` 对**每个字段**都用 `?? 默认值` 兜底、
且 schema 带 `.default()`。此时 `config` 从 `{}` 变为 `{telemetry:false}` 与改前**行为等价**（例：`dsh-univer-office`
`lib/index.js:3751-3774` 全字段 `??`）。**反之**（字段直接透传、无 schema default，如 `dsh-md-convert` 的
`outDir/ocrScale/legacy.backend`）必须**显式写全**，漏写即以 `undefined` 进 core。

> 故意不全写的理由：写全会把插件升级后的新默认值**静默钉死**在旧值上。安全前提成立时，少写更抗漂移。

## 5. 改完为什么"看起来没生效"：三种拦截

| 现象 | 原因 | 判据 / 处置 |
|---|---|---|
| `patch: entry "X" not found` | 该 entry **不在 profile 组合里**（bundle 未登记，见 SKILL §十二） | `--dump-config` 里 grep 不到它 ⇒ 先修登记，配置本身没错 |
| 配置写了但行为不变 | 插件 config 在 **profile boot 装配，无热重载** | 必须重启 Desktop |
| 改了 patch 文件、热重载报错 | `[plugin-manager] patch watch recompose failed: … service "hmr" has been registered` | 这是**既有通道故障**：watch recompose 失败 ⇒ 只能靠重启，别指望热生效 |

## 6. 附：本机 2026-09-19 的实际处置（留痕）

- 关闭对象：`dsh-univer-office@0.3.2`，端点 `https://univer.ai/api/telemetry/cli`（境外）。
- 暴露面（不可撤销）：`state.json` 记录 `activatedAttemptedAt=2026-09-19T11:09:22.716Z`、
  `dailyActiveSentDate=2026-09-19` ⇒ 插件 19:09 装机时**激活 + 当日日活各一次，已出网**。
- 上报字段（`lib/index.js` 内 capture 对象）：`distinctId`（`<DSH_HOME>/telemetry/…/state.json` 里的随机 UUID）
  \+ `arch` / `build_commit` / `event_source` / `node_major_version` / `package_name` / `package_version` /
  `platform` / `telemetry_state_version`。**不含文件内容、不含路径。**
- 已做：`profiles/web/cordis.patch.yml` 追加 `- id: univer` + `config: {telemetry: false}`；
  `<DSH_HOME>/.env` 追加 `DO_NOT_TRACK=1`（经 `loadLayeredEnv` 实测 `source: "user-env"` 生效）。
- 同时核过 **DSH 官方遥测未启用**：`dsh-session-telemetry-otel` 无 insert 条目、不在 `dsh.profile.bundles`、
  且 `exporter.url` 为**必填**（无默认端点）⇒ 无配置即起不来。`.anonymous-user-id` 文件存在但那是
  telemetry **与 feedback 共用**的身份文件，**不能**据它判定遥测在跑。
- 顺带发现的不兼容（与本处置无关，另案）：`dsh-subagent-pool` 加载失败 ——
  `The requested module '@deepseek-ai/dsh-settings' does not provide an export named 'settingsNamespace'`，
  该异常会**中断整个 plugin tree 加载**（`DSH entry failed: … plugin tree failed to load`）。
  本机 `dsh-settings` 的导出只有 `SettingsConflictError / SettingsProvider / redactSecrets` 三个符号。
