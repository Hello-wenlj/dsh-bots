# 出口代理与环境分层（DSH outbound proxy）

> 实测日期 2026-09-19。适用：DSH Desktop 0.9.0（bundled `@deepseek-ai/dsh`）+ CLI 侧 `~/.dsh`（0.1.5-rc.2）。

## 1. env 三层的**真实优先级**（源码锚点）

`@deepseek-ai/dsh-app-boot/lib/index.js`：

- L1077 `readEnvLayer(binName, dir, warn, home)`：读 `dir/.env`，`isHome = resolve(dir) === home`。
- L1050 `HOME_LAYER_PROXY_NAMES = Set{HTTP_PROXY, HTTPS_PROXY, ALL_PROXY, NO_PROXY}`。
  - 这四个名字**只有 home 层（`<DSH_HOME>/.env`）能设**；
  - 在**项目层（`cwd/.env`）**声明 → **直接抛错**，报错逐字：
    `…sets "HTTP_PROXY", which only the launching environment may set (…); export HTTP_PROXY, or put it in <home>\.env, which does not travel with a repository`
  - CA / TLS 类名字**两层都拒**（它们改变信任对象而非流量走向）。
- L1111 `loadLayeredEnv` → L1118 **物化顺序**：

  ```js
  for (const layer of [project, user]) {
    for (const [name, value] of Object.entries(layer.values))
      if (process.env[name] === void 0) process.env[name] = value;   // ← 继承优先
  }
  ```

  ⇒ **继承的 process env > 项目 .env > home .env**。`.env` 只**补位**，不覆盖。

### 1.1 由此推出的两条硬结论

1. **若父进程已带代理变量，`<DSH_HOME>/.env` 不生效**（被继承值挡住），**且不报错**。
2. **「在 DSH 里跑一条 node 看 env」不是干净的验证**：WorkBuddy 自身 env 带
   `HTTP_PROXY/HTTPS_PROXY=7897` 与 `NO_PROXY=<local>,localhost,127.*,10.*,172.16.*,…`（长串）；
   由 WorkBuddy 派生的 DSH（如 `dsh-bridge` 的 harness）会把这份 env **原样继承**下去，
   看起来「代理已生效」——**这是假阳性**。

   **判据＝`NO_PROXY` 指纹**：`.env` 里写的是 `localhost,127.0.0.1,::1,0.0.0.0`（短串），
   WorkBuddy 给的是带 `<local>` 与 `172.16.*` 的长串。

## 2. 唯一可信的验证方法（可证伪、零污染）

清空代理变量后调用**官方真实函数**，读分层溯源。**不要**读进程 env、**不要**用「能不能搜到」当判据。

```bash
export LC_ALL=C; cd /c/Users/wenlj
NODE="F:/dsh_exe/DSH Desktop/resources/app/node_modules/node/bin/node.exe"
CODE='const m=await import("file:///F:/dsh_exe/DSH%20Desktop/resources/app/node_modules/@deepseek-ai/dsh-app-boot/lib/index.js");
const snap=m.loadLayeredEnv("dsh-probe","C:/Users/wenlj",l=>console.log("WARN:"+String(l).trim()));
const s=["process","project-env","user-env"];
for(const k of ["HTTP_PROXY","HTTPS_PROXY","NO_PROXY"])console.log(k+" | from="+JSON.stringify(snap.getFrom(k,s)));'
env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u NO_PROXY -u http_proxy -u https_proxy -u NODE_OPTIONS \
  DSH_HOME="C:/Users/wenlj/AppData/Roaming/dsh-desktop/harness" \
  "$NODE" --input-type=module -e "$CODE"
```

2026-09-19 实测（**Desktop harness 与 CLI home 两套均通过**）：

```
HTTP_PROXY  | from={"value":"http://127.0.0.1:7897","source":"user-env","path":"…\harness\.env"}
HTTPS_PROXY | from={"value":"http://127.0.0.1:7897","source":"user-env","path":"…\harness\.env"}
NO_PROXY    | from={"value":"localhost,127.0.0.1,::1,0.0.0.0","source":"user-env","path":"…\harness\.env"}
```

要点：

- `snap.get(k)` 返回**对象**（快照），**`snap.getFrom(k, sources)` 才给 `{value, source, path}`**；
  漏传 `sources` 会 `TypeError: Cannot read properties of undefined (reading 'includes')`。
- **必须先 `env -u` 清空**，否则 `source` 会是 `process`（继承层），实验无效。
- `--input-type=module` + `-e` 支持 top-level await，可直接 `await import(...)`；
  URL 用 `file:///F:/…` 且**空格转义为 `%20`**。
- `loadLayeredEnv` **是 app-boot 的导出**（与 `loadEnv`、`renderConfigDump` 等同列），可直接调用。

## 3. 消费方与回写

`@deepseek-ai/dsh-http-proxy/lib/index.js`（bundled）：

- `resolveProxyPolicy` → `source` 只有 `"env"` / `"none"`（L252 / L260）；**不读 WinINET 注册表**。
- `createPolicyDispatcher`（L388）用 undici 的 `ProxyAgent` 按 origin 装配，`setGlobalDispatcher` 覆盖
  进程内所有 `fetch()` —— 插件不需要知道这个包存在。
- `applyPolicyEnv(policy)`（L334）把 policy **回写进 `process.env`**，让「读环境变量的消费者」与
  **每个派生子进程**都看到代理（注释明说这是 spawn 子进程能拿到代理的原因）。
- 因此改 `.env` 后**必须重启 DSH** 才生效（装配发生在 profile boot 阶段）。

## 4. ⚠️ 双通道并行（未决隐患）

本机存在**第二条代理注入通道**：`~/.dsh/dsh-proxy-shim.mjs`（人工垫片，由 `NODE_OPTIONS=--import` 触发），
自 2026-09-15 起持续生效，日志 `…\dsh-desktop\logs\dsh-proxy-shim.log`
（1641 行、2026-09-15 起、**0 条 FAILED / 0 条 direct**）：

```
[2026-09-19T07:47:57.953Z] pid=31400 node=v24.9.0 dispatcher=ProxyAgent(http://127.0.0.1:7897)
```

`pid=31400` 与本次启动的 harness-node 进程**一致**；而该进程的完整命令行（335 字符）为

```
node.exe --expose-internals …\harness-node-entry.mjs …\dsh\lib\bin.js web --patch …\dsh-desktop.patch.yml --no-open --host 127.0.0.1 --port 43129
```

**不含 `--import`** ⇒ 垫片只能由 `NODE_OPTIONS` 注入。
垫片取值 = `process.env.DSH_SEARCH_PROXY || 'http://127.0.0.1:7897'`（**默认值硬编码**）。

**风险**：系统代理换端口时 `.env` 会被 `dsh-safe --sync-proxy` 更新，而垫片仍走旧端口 ⇒ **两条通道分叉**。

**✅ 已处置（2026-09-19）**：垫片已收紧为四级解析 —— `DSH_SEARCH_PROXY`（显式）> 继承层
`HTTPS_PROXY/HTTP_PROXY/ALL_PROXY` > `<DSH_HOME>/.env`（home 层）> 直连，与 app-boot 的
`loadLayeredEnv` 语义严格对齐；日志新增 `source=` 字段。备份
`dsh-proxy-shim.mjs.bak-20260919-1557-pre-tighten`。六场景实测（`DSH_PROXY_SHIM_LOG` 指向临时文件，不污染真实日志）：

| 场景 | 期望 | 实测 |
|---|---|---|
| `DSH_HOME`=Desktop harness，无代理 env | home 层 7897 | `ProxyAgent(http://127.0.0.1:7897) source=home-env:HTTPS_PROXY(C:\…\harness\.env)` |
| `DSH_HOME`=CLI home，无代理 env | home 层 7897 | `ProxyAgent(http://127.0.0.1:7897) source=home-env:HTTPS_PROXY(C:\Users\wenlj\.dsh\.env)` |
| `DSH_SEARCH_PROXY=off` | 直连 | `direct source=DSH_SEARCH_PROXY (explicit off)` |
| `DSH_SEARCH_PROXY=http://127.0.0.1:9999` | 用 9999 | `ProxyAgent(http://127.0.0.1:9999) source=DSH_SEARCH_PROXY` |
| 继承层 `HTTPS_PROXY=http://127.0.0.1:1234` | 继承优先（与 app-boot 一致） | `ProxyAgent(http://127.0.0.1:1234) source=inherited:HTTPS_PROXY` |
| `DSH_HOME` 指向不存在目录 + 无任何代理 | 直连 | `direct source=none`（**反伪证：硬编码 7897 确已消失**） |

⚠️ 生效需**重启 DSH**（`NODE_OPTIONS` 只在进程启动时被读取一次）。

**⚠️ 踩坑**：首次六场景测试时**六个场景全部**显示 `source=inherited:HTTPS_PROXY` —— 原因是只 `env -u HTTPS_PROXY`
漏了小写：**Windows 环境变量大小写不敏感**，`process.env.HTTPS_PROXY` 会命中 `https_proxy`。大小写都要 `-u`。

**✅ 注入点已定位（2026-09-19）——机制推翻了「harness 环境 = 进程继承」这个前提**：

DSH Desktop 启动 harness 前会**点源 PowerShell profile 并整体捕获其环境**，捕获结果即 harness 子环境：

- 主 bundle `resources/app/out/main/index.js`
  - L7932-L7948 构造采集命令：
    `powershell -NoLogo -NonInteractive -OutputFormat Text -Command '[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; . $PROFILE 2>$null; Get-ChildItem Env: | ForEach-Object { "$($_.Name)=$($_.Value)" }'`
  - L8180 `const shellEnvironment = await prewarmShellEnvironment()`
  - L8186 传入 `buildHarnessSpawnOptions(launchDir, dshHome, platform, shellEnvironment)`
  - L8041-L8067 `buildHarnessSpawnOptions` 只做 `env: { ...parentEnvironment, DSH_HOME, NO_COLOR, npm_config_*, NODE_COMPILE_CACHE, Path }`
    —— **bundle 内 `PROXY` / `NODE_OPTIONS` 字面量命中数均为 0**；唯一 `environment` 来源就是上面的采集结果
  - L7981 采集失败时回落 `process.env`
- ⇒ 本机 `C:\Users\wenlj\Documents\WindowsPowerShell\Microsoft.PowerShell_profile.ps1` 中的
  `$env:DSH_SEARCH_PROXY = 'http://127.0.0.1:7897'` 与 `$env:NODE_OPTIONS += '--import …dsh-proxy-shim.mjs'`
  就是**全部真相**：垫片为何每次启动都被加载、为何读到硬编码端口，均源于 `$PROFILE` 被点源后捕获。

⚠️ 该机制否决了三条「排除项」推理：会话环境 / 注册表（User·Machine·Volatile·Session Manager）/ HuoChat 启动链
**都不是**载体。取证法：用 `explorer.exe <probe.bat>` 派生探针（子进程由 explorer 创建，拿到的是**会话环境**，
绕开 WorkBuddy 自身 env 污染），本机实测 106 个变量、含 HKCU/HKLM 级变量，而 `NODE_OPTIONS`/`DSH_SEARCH_PROXY`/任何代理变量**均不存在**。

**✅ 分叉已彻底消除（2026-09-19）**：删除 `$PROFILE` 里的 `$env:DSH_SEARCH_PROXY = …` 硬编码
（备份 `Microsoft.PowerShell_profile.ps1.bak-20260919-1620-pre-proxy-dedup`，md5 `ee3ffb00…`），只保留垫片加载器。
改后真实路径实测（环境只给 `NODE_OPTIONS` + `DSH_HOME`，代理变量全清）：

```
dispatcher=ProxyAgent(http://127.0.0.1:7897) source=home-env:HTTPS_PROXY(C:\Users\wenlj\AppData\Roaming\dsh-desktop\harness\.env)
dispatcher=ProxyAgent(http://127.0.0.1:7897) source=home-env:HTTPS_PROXY(C:\Users\wenlj\.dsh\.env)
```

⇒ **代理取值唯一真源 = `<DSH_HOME>/.env`**（由 `dsh-safe --sync-proxy` 从 WinINET 同步）；
垫片仍由 `NODE_OPTIONS` 加载，但自身不再携带任何端口。强制直连：在 shell 中设 `$env:DSH_SEARCH_PROXY = 'off'`（垫片最高优先级）。

### 运行实例的 `source` 判读（2026-09-19 实测 —— 勿误判为「分叉复发」）

| 进程层 | 实测 source | 判读 |
|---|---|---|
| **harness-node 本身**（`harness-node-entry.mjs`；本次 pid=38888 @18:36:43） | `home-env:HTTPS_PROXY(C:\…\harness\.env)` | ✅ 期望值 —— **这一层才是真源判据** |
| harness 之后 spawn 的 node 子进程（pid 13540 / 35008 / 16188 / 38476 / 27532 …） | `inherited:HTTPS_PROXY` | ✅ **正常下传** —— `dsh-http-proxy` 在 boot 时 `applyPolicyEnv` 把代理写回自身环境，子进程继承 |

⇒ **绝对判据：只认 harness-node 那一层。** 子进程出现 `inherited:HTTPS_PROXY` 是代理已生效并向下传递的证据。
把子进程的 `inherited` 当成「`.env` 失效」是**误判**（日志里两类 source 会共存，必须按 pid 分层看）。

## 5. 判读坑（都会导致误判）

- **Electron 主进程忽略 `NODE_OPTIONS`，纯 `node.exe` 子进程会读**。同一份 NODE_OPTIONS 只对
  harness-node 生效 —— 这既是垫片能工作、又难以被发现的原因。
- `dsh-bridge` 的 `dsh_run` 跑出来的 env **全部来自 WorkBuddy**，用它验证 `.env` 一定得到假阳性（见 §1.1）。
- `--dump-config` **不经过** boot 阶段的环境物化路径，看不到 env 生效与否；只能证明配置树可组合。
- 用户/系统级代理变量（`[Environment]::GetEnvironmentVariable('HTTP_PROXY','User'|'Machine')`）**本机为空**，
  所以 Desktop harness 的代理**唯一来源就是 `<DSH_HOME>/.env`** —— 这一条是上面「source: user-env」实验成立的前提。
