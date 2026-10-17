# 模型配置：生效时机与重启判定

> 归属 `dsh-rollback-recovery` §9.1。实测 2026-09-14，dsh 0.1.5-rc.2（官方 npm 分发 F:/DSH-npm）。

## 1. 两条链路互不覆盖

| 链路 | 配置来源 | 落点 |
|---|---|---|
| `dsh.sh run/acp/web` | 每次启动新建 run home + `seed_model_settings` 注入 | `dshhome/run-<epoch>-<pid>/settings.yaml` |
| 直连 `dsh` CLI | 手写 | `~/.dsh/settings.yaml` 的 `agent-default-model.model` |

`cmd_web` 链路：`new_run_home`（先 `rm -rf "$DSH_BASE_HOME"/run-*`，再 `mkdir run-$(date +%s)-$$`）→ `seed_model_settings "$run_home"` → `build_env` → `exec "$NODE" "$DSH_BIN" web --port "$port"`。脚本注释即写明「默认独立 DSH_HOME，与 `~/.dsh` 隔离，避免污染 Kevin 正式配置」。

## 2. 改动何时生效（要不要重启）

| 改动对象 | 生效时机 | 需重启? |
|---|---|---|
| `~/.dsh/settings.yaml`（直连 CLI） | 每次新进程启动时读入 | **否**（无长驻体；已在跑的进程不回溯） |
| `dsh.sh` 的 `seed_model_settings` 模板 | 下次重建 run home | **是**（web 停→起） |
| 在跑 web 的 `run-*/settings.yaml` | 该进程启动时读入 | **是**（停 web → 重起） |

- **web 与 `~/.dsh` 完全解耦**：改 `~/.dsh` 不影响在跑的 web，反之亦然。
- **run home 一次性、不继承**：每次启动重建 ⇒ web 界面里的模型档位/语言等运行时偏好**不跨重启保留**。
- **`settings.yaml` 兼作运行时状态载体**：dsh 运行中会回写（实测追加 `ui-onboarding.welcomeNoticeVersion`、`locale.preference: zh`）⇒ mtime **晚于**进程启动时间属正常，不代表被外部改写。

## 3. 判据：某 web 会话到底用的什么模型

```bash
netstat -ano | grep ":3080 .*LISTENING"        # → PID
ls -l ~/.workbuddy/dshhome/                    # run-<epoch>-<pid>，mtime 对上 PID 启动时刻即为它
grep -A3 "agent-default-model" ~/.workbuddy/dshhome/run-<...>/settings.yaml
```

与 UI 右下角档位名互印：`name: DeepSeek-V4.1-Flash` + `reasoningEffort: high` ⇒ 显示「DeepSeek-V4.1-Flash High」。

⛔ **模型自述身份不可作判据**：实测 V4.1-Flash 自称「我是 Claude，由 Anthropic 开发的模型」。全量检索 `@deepseek-ai` 包**无**任何 Claude 身份提示词注入（命中仅为 `dsh-llm-pi-ai` 的 Anthropic 模型列表接口注释、可接入的 `claude-code` 子代理 provider、`dsh-hooks-claude-code` 兼容模块）。判底层模型只认**端点回执**与**配置字段**。

## 4. 本次实证（2026-09-14）

- 在跑 web：PID 46012，起动 15:38:53（`GetProcessTimes` 取准），监听 `127.0.0.1:3080`。
- 其 run home：`dshhome/run-1789371533-389`（目录名 epoch 与起动时刻差 1s）。
- 该 home 的 `settings.yaml`：`model=deepseek-flash` / `name=DeepSeek-V4.1-Flash` / `reasoningEffort=high`。
- 该文件 mtime 15:41:54（晚于进程启动）：与同模板上一版逐字节 diff，多出 `ui-onboarding` 与 `locale` 两段 ⇒ 回写确证。

## 5. 官方模型目录（完整字段，0.1.5-rc.2）

| id | 显示名 | 模态 | 其他声明 |
|---|---|---|---|
| `deepseek-flash` | **DeepSeek-V41-Flash**（注意官方名**无小数点**） | text+image | `contextWindow: 1e6`、`imagePixelBudget: 64e4`、`imageMaxBytes: 1MiB`、`systemPromptUpdate: in-history` |
| `deepseek-v4-flash` | DeepSeek-V4-Flash | text | `contextWindow: 1e6` |
| `deepseek-v4-pro` | DeepSeek-V4-Pro | text | `contextWindow: 1e6` |
| `deepseek-v4-flash-vision-exp` | DeepSeek-V4-Flash-Vision-Exp | text+image | `imagePixelBudget: 64e4`、`imageMaxBytes: 1MiB` |

**显式 `models` 是整体替换**（源码 `resolveModels`: `models ?? DEFAULT_MODELS`；schema 默认值即 `DEFAULT_MODELS`），不合并。

**净损失盘点（把官方默认 vs 手写副本逐字段比）**：

| 字段 | 写副本（旧 seed） | 省略 models | 结论 |
|---|---|---|---|
| `inputModalities` | 手写 `[text, image]` | 官方 `[text, image]` | 相同 |
| `imagePixelBudget` | 省略 → 回落 `64e4` | `64e4` | **相同**（⚠️ 曾误判为「会降级」，实为同值） |
| `imageMaxBytes` | 省略 → 回落 `1048576` | `1048576` | **相同** |
| `systemPromptUpdate` | 丢失 | `in-history` | **唯一真实损失** |
| `contextWindow` | 丢失（回落 `defaultContextWindow`） | `1e6` | 相同 |
| `name` | 手写「DeepSeek-V4.1-Flash」 | 官方「DeepSeek-V41-Flash」 | 仅显示名差异 |

`systemPromptUpdate: in-history` 的语义（`dsh-agent-loop` 消费）：系统提示词/工具面变化时，以 `systemPrompt.project(..., { inHistory: true })` **把更新追加进会话历史**，而非原地替换基础 system message。

## 6. 判别器：某会话读的是哪一份配置

| 观察点 | 读 seed（run home） | 读 `~/.dsh` |
|---|---|---|
| UI 档位名 | 旧 seed 写「DeepSeek-V4.1-Flash」（**带小数点**） | 官方名「DeepSeek-V41-Flash」（无点） |

⇒ 截图里若显示带小数点的「DeepSeek-V4.1-Flash」，即证明该会话走的是 seed 副本而非官方默认。

## 7. 配置源隔离的决定性实验（2026-09-14）

| 步骤 | 操作 | 结果 |
|---|---|---|
| 1 | `~/.dsh/settings.yaml` 的 `model` 改为 `deepseek-invalid-probe-xyz` | — |
| 2 | 全新空 DSH_HOME（`mktemp -d`，无 settings.yaml）跑 headless「17*23」 | **exit=0，输出 391** |
| 3 | 还原 ~/.dsh 并校验 sha256 | 一致 |

⇒ 若存在全局 user layer，第 2 步必报 `INVALID_REQUEST`；实测跑通 **⇒ 配置源只有 `DSH_HOME/settings.yaml`，两通道零重叠**。

## 8. 视觉能力探针（省略 models 是否仍可看图）

纯 Python 生成 192×192 纯色 PNG（红 `#C8201C` / 蓝 `#1E5ABE`），配置**不含 `models` 列表**，headless 提问：

> 用文件读取工具分别查看 A.png 和 B.png，只回答：A=?,B=?

**实测输出：`A=红,B=蓝`（exit=0）** ⇒ 官方默认目录已声明 `inputModalities:[text,image]`，seed 无需再写副本。

## 9. seed 口径变更（2026-09-14）

`dsh.sh` 的 `seed_model_settings` 已由「注入模型副本」改为**只钉默认档位**（输出仅 `agent-default-model` + `llm-deepseek{thinking,reasoningEffort}`），同步更正了原注释中「dsh 内置默认只公布 flash/pro（无视觉声明）」的过期说法。备份：`~/.workbuddy/scripts/dsh.sh.bak-20260914-160335`。该改动**仅影响此后新起的 run/acp/web**，不影响运行中的 web 会话。

## 10. 模型本体来源与计费出口（2026-09-14 实测）

**问法**：「web 自带了官方模型吗？需要走 API 流量吗？」
**答**：自带的是**模型目录元数据**，不是模型本体；推理**一律走远端 API**，web 与 CLI 在此无差别。

### 10.1 「自带」的边界（扫描根 `F:/DSH-npm/node_modules/@deepseek-ai`）

| 检查项 | 结果 |
|---|---|
| 权重文件（.gguf/.safetensors/.onnx/.pt/.h5） | **0 个** |
| >20MB 文件 | **0 个** |
| ollama / llama.cpp / gguf / transformers / onnxruntime 依赖 | **无** |
| 内置「模型」 | 仅 `dsh-llm-deepseek` 的 `DEFAULT_MODELS`（4 条元数据：id / name / 模态 / contextWindow / imagePixelBudget / imageMaxBytes / systemPromptUpdate） |

⇒ 「官方模型」= **catalog**：告诉 dsh 端点接受哪些模型名、各自模态与预算。不含参数、不含推理引擎。

### 10.2 推理出口（远端 HTTP）

| 项 | 值 |
|---|---|
| 端点 | `POST {baseURL}/chat/completions` |
| 默认 baseURL | `https://api.deepseek.com`（源码 `PUBLIC_BASE_URL`；env `DEEPSEEK_BASE_URL` 可覆盖） |
| 鉴权 | `Authorization: Bearer <apiKey>` |
| 附件 | 同域 Files API（`{baseURL}/files`），有 per-key 存储/文件数配额 |
| 联网搜索 | **另一端点** `https://api.deepseek.com/anthropic/v1/messages`（Anthropic Messages 兼容；env `DEEPSEEK_SEARCH_BASE_URL`，或 Settings > Plugins > Web search 改） |
| 适配器 | `@deepseek-ai/dsh-llm-deepseek` 0.1.5-rc.2，唯一路由 `deepseek-official` |

### 10.3 三条实测证据

| # | 实验 | 结果 |
|---|---|---|
| 1 | 不注入 key 跑 headless | `MISSING_CREDENTIAL: llm-deepseek: no API key for provider route "deepseek-official"` |
| 2 | 注入 key + `DEEPSEEK_BASE_URL=http://127.0.0.1:9` | `TRANSPORT: DeepSeek API request to http://127.0.0.1:9 failed` |
| 3 | 读在跑 web 会话自带账本（`storages/session_projcache/sessions/*.json`） | `tokenUsage.totals`：uncachedInput 12517 / output 269 / cacheRead 12288；`sessionStats`：llmMs 4378、ttftMs 2734 |

⇒ 若有本地兜底，第 2 条本应成功；第 3 条是 **web 通道**（非 CLI）自己记的用量账。

### 10.4 密钥分层（`dsh-credentials-local`，高 → 低）

```text
inherited process environment   (read-only, wins)
> $DSH_HOME/.credentials.yaml   (provider-managed, writable；Web「Models」页写入，只写不显)
> <invocation cwd>/.env         (read-only fallback)
> $DSH_HOME/.env                (read-only fallback)
```

- Models 页主字段就是**一个 API 密钥输入框**（从不询问环境变量名）；保存经 `credentials.set` 只写入 profile 引用，**settings.yaml 从不携带密钥值**。
- 在跑 web 的 run home 里 `.credentials.yaml` 只存了 `client-connection/browser-session`（grant，43 字符）——即该会话的模型密钥来自**启动时注入的环境变量层**（dsh.sh），不是文件层。

### 10.5 隐性计费（默认 bundle 另挂的 LLM 调用）

`@deepseek-ai/dsh-base` 的 `cordis.patch.yml` 默认挂载：

| 插件 | 作用 | 计费口径 |
|---|---|---|
| `dsh-session-title-first-prompt-llm` | 用首条提问让 LLM 生成会话标题 | 每次新会话 1 次调用 |
| `dsh-web-search-deepseek` | 联网搜索 | 走 `…/anthropic/v1/messages`，独立计费 |
| `dsh-llm-deepseek` | 对话 / 工具循环主体 | 主计费项 |

⇒ 「只打开 web 界面」不耗流量（静态资源由本地 3080 服务）；**只要产生一次模型回合就计费**，含自动标题。

### 10.6 不消耗官方流量的可行做法

1. **换端点**：`DEEPSEEK_BASE_URL`（或 Models 页「自定义设置」的 `baseURL`，deepseek 家族占位符即公共端点）指向自建/兼容网关；README 明确 localhost、IPv4/IPv6 字面量与自定义端口均有效。
2. **加自定义提供方**：走 `llm-pi-ai` 路由新增一条（Provider ID + 端点 + 协议 + 至少一个模型；协议可选 OpenAI / Anthropic 兼容）；留空密钥可保留提供方原生认证（如 Bedrock 凭据链、Vertex ADC）。
3. ⛔ **dsh 自身无本地推理**：要真正零 API 流量，必须自带推理服务（vLLM / Ollama / llama.cpp server 等 OpenAI 兼容端点），dsh 只作客户端接入。

---

## 11. 可直接复用的接入三元组（2026-09-14 实测）

**问法示范**：「给我 V4.1-Flash 的 API key 与 URL」

### 11.1 三元组

| 项 | 值 | 来源 |
|---|---|---|
| baseURL | `https://api.deepseek.com` | 源码 `PUBLIC_BASE_URL`（`dsh-llm-deepseek/lib/index.js:1911`）；env `DEEPSEEK_BASE_URL` 可覆盖 |
| 对话端点 | `POST {baseURL}/chat/completions` | 源码 `:1770`；`{baseURL}/v1/chat/completions` 实测同样可用 |
| 模型 id | `deepseek-flash` | 源码 `DEFAULT_MODELS`；即用户口中的「V4.1-Flash」，官方显示名 `DeepSeek-V41-Flash` |
| API key | `HKCU\\Environment\\DEEPSEEK_API_KEY`（35 字符，`sk-` 前缀） | `dsh.sh` 的 `build_env` 仅 `export DEEPSEEK_API_KEY`，脚本内不做解码或转换 |
| 文件 API | `{baseURL}/files` | 同域，per-key 配额 |
| 搜索端点 | `https://api.deepseek.com/anthropic/v1/messages` | env `DEEPSEEK_SEARCH_BASE_URL`；Anthropic Messages 兼容 |

### 11.2 ⚠️ 关键概念澄清：key 是**账号级**，不按模型划分

**不存在「V4.1-Flash 专属的 key」**。同一把 key 同时可访问端点下的全部模型——实测 `GET /models` 返回：

```json
{"object":"list","data":[
  {"id":"deepseek-flash","object":"model","owned_by":"deepseek"},
  {"id":"deepseek-v4-pro","object":"model","owned_by":"deepseek"}]}
```

选模型靠**请求体的 `model` 字段**，不是换 key。任何「为某模型单独申请 key」的说法都是误解。

### 11.3 四项实测（2026-09-14，均为只读或最小调用）

| # | 探针 | 结果 |
|---|---|---|
| 1 | `GET https://api.deepseek.com/models`（带 Bearer） | **200**，返回上列 2 个模型 |
| 2 | `GET https://api.deepseek.com/v1/models` | **200**，同上（带 `/v1` 亦可） |
| 3 | `POST /chat/completions`，`{"model":"deepseek-flash","max_tokens":1}` | **200**，回执 `"model":"deepseek-flash"`，`usage.total_tokens=32` |
| 4 | `POST /v1/chat/completions` 同参 | **200**，同回执 |

⇒ 端点、路径、模型名、key 四者互洽；`/models` 的返回即该端点**权威模型清单**——与更早 `INVALID_REQUEST` 报出的两个名字完全一致，互为交叉验证。

### 11.4 接第三方 OpenAI 兼容客户端的写法

```text
base_url = https://api.deepseek.com      # 或 https://api.deepseek.com/v1，两者均实测 200
api_key  = <HKCU\Environment\DEEPSEEK_API_KEY>
model    = deepseek-flash
```

### 11.5 key 的取回方式（避免明文散布）

Windows 环境变量层取回：

```text
[Environment]::GetEnvironmentVariable("DEEPSEEK_API_KEY","User")
```

Python 注册表直读：

```bash
python -c "import winreg;print(winreg.QueryValueEx(winreg.OpenKey(winreg.HKEY_CURRENT_USER,'Environment'),'DEEPSEEK_API_KEY')[0])"
```

⛔ 本技能与全部 notes **不落 key 明文**；新会话需要时按上式现场取。

---

## 12. 模型页「API 密钥：由启动环境提供（只读）」诊断

**现象**：Web「设置 > 模型 > DeepSeek」的 API 密钥输入框灰显，文案「由启动环境提供（只读）」，无法编辑、无法保存。

**判定：不是故障，是官方明示的设计（intentional）。** 且对 `dsh.sh` 通道而言这个只读态**更优**，不建议改。

### 12.1 判定链（源码级，0.1.5-rc.2）

| 环节 | 位置 | 内容 |
|---|---|---|
| 优先级声明 | `dsh-credentials-local/lib/index.js:16-21` | `inherited process environment (read-only, wins)` > `$DSH_HOME/.credentials.yaml (provider-managed, writable)` > `cwd/.env` > `$DSH_HOME/.env` |
| 设计理由 | 同文件 `:23-28` | 「The inherited environment wins because `DEEPSEEK_API_KEY=… dsh`, a CI secret, or a container `-e` is **this run's explicit intent**; it cannot be edited from inside, so it must be **visibly read-only** rather than silently shadow writes.」 |
| 取值 | `:473-478` | `resolve(ref)` 若 `inherited(ref) !== undefined` → 返回 `{value, source:"env"}`（env 层直接短路，不看文件层） |
| UI 判据 | `:491-496` | `describe(ref)` → `{configured:true, source:"env", writable:false}` ← **UI 就是靠 `writable:false` 渲染只读** |
| 写入拦截 | `:632-637` | 任何写操作若被 env 层遮蔽，直接抛错：`credentials-local: "<ref>" is supplied read-only by the launching environment, so <verb> would be shadowed; unset it in the shell you start dsh from instead` |
| UI 文案 | `dsh-client-ui-settings-models/lib/client.js:2781` | `keyEnvLocked: "由启动环境提供（只读）"` |

⇒ `dsh.sh` 的 `build_env` 做了 `export DEEPSEEK_API_KEY`，于是该 ref 落在最高优先级的 **inherited environment** 层 ⇒ UI 必然只读。**这是链路设计的必然结果，不是配置错误。**

### 12.2 为什么对 dsh.sh 通道「UI 可编辑」反而是劣解

`new_run_home()` 每次启动先 `rm -rf "$DSH_BASE_HOME"/run-*` 再建 `run-<epoch>-<pid>`。**整个 run home 被清空重建** ⇒ UI 写进 `$DSH_HOME/.credentials.yaml` 的 key 会**随 web 重启一并消失**，每次都得重填。

对照：`dsh.sh plugin` 用的是**持久**目录 `web-persist`（`cmd_plugin` 中 `DSH_BASE_HOME/web-persist`，且 `run-*` 的清理 glob 不覆盖它）。所以**只有 `web-persist` 这类持久 home 才适合承载 UI 写入的 key**。

### 12.3 三种诉求的正确处理

| 诉求 | 正确做法 |
|---|---|
| 已能用，只是好奇为何灰显 | **无需处理**——key 由 `dsh.sh` 从 Windows 用户环境变量注入，全通道统一生效（四项探针实测 200） |
| 想换 key | 改 Windows 用户环境变量（`[Environment]::SetEnvironmentVariable("DEEPSEEK_API_KEY","<新值>","User")` 或注册表 `HKCU\Environment`），**重开终端**，再**停-起 web**（已运行的进程沿用旧值） |
| 想给**别的**提供方配 key | 不受影响——只有被 env 遮蔽的那个 ref 只读；其他 provider 的 key 字段照常可编辑，或用「添加自定义提供方」 |

### 12.4 若确实要 UI 可编辑（可选改造，代价明确）

需同时满足两个前提，缺一不可：

1. **启动时不注入该 key**：`dsh.sh` 的 `build_env` 不 `export DEEPSEEK_API_KEY`（或加开关控制）。否则无论怎么配都会被 env 层遮蔽。
2. **改用持久 home**：把 `cmd_web` 的 `DSH_HOME` 从 `new_run_home` 换成 `DSH_BASE_HOME/web-persist`（与 `cmd_plugin` 同款），否则每次重启仍会丢。

代价：key 从「Windows 环境变量统一管理」退化为「散落在某个 home 的 `.credentials.yaml`」，跨机/跨通道复用性下降，且需要人工保证该目录不被清理。

### 12.5 屏幕上的另一处可对照项

截图「模型目录：已自定义模型目录」显示 `deepseek-flash` / **`DeepSeek-V4.1-Flash`**（显示名**带小数点**）——这是**旧 seed 副本**的指纹（见 §6 判别器）。2026-09-14 起 `seed_model_settings` 只钉档位、不写 `models` 副本，故**新起的 run/acp/web 此处会回落「默认模型」**。点「恢复默认模型」只改当前 run home，重启即被重建，无长期影响。

## 13. 「官方模型」走的到底是不是我们配的 key（2026-09-14 进程级实证）

**问法**：「那官方这个模型走的是我们配置的 API key 吗？」
**答**：**是。不存在「官方自带渠道」。** web 会话（PID 46012）的进程环境里就带着这把 key，且与 HKCU 注册表值**逐字节完全一致**；出口是 `https://api.deepseek.com`，计费落在同一把 key 上。

### 13.1 判定链（四层，全部实测）

| # | 证据 | 结果 |
|---|---|---|
| 1 | 内存扫描 PID 46012（3080 监听者）内 `DEEPSEEK_API_KEY` | len 35 / head `sk-27dd4` / tail `...e7af` ⇒ **与 HKCU `Environment\DEEPSEEK_API_KEY` 逐字节一致 = True** |
| 2 | 同批扫描的 `DSH_HOME` | `C:/Users/wenlj/.workbuddy/dshhome/run-1789371533-389` —— 正是 §1 认定的那个 run home，两证互锁 |  <!-- path-ref-ok: 证据引述：内存扫描实测值（与 §1 认定结论两证互锁） -->
| 3 | 同批扫描的 `DEFAULT_DSH_MODEL` / `DEFAULT_DSH_TIER` / `DEFAULT_DSH_EFFORT` | `deepseek-flash` / `pro` / `high` —— 即 dsh.sh 导出、seed 注入的那套档位 |
| 4 | run home `.credentials.yaml` | 只有 `client-connection/browser-session`（grant），**无模型 key** ⇒ 不可能来自文件层 |

⇒ 该 web 会话的模型密钥唯一来源 = `dsh.sh` 启动时注入的**进程环境层**（写入 `.credentials.yaml` 只经 Web「Models」页，且被 env 层遮蔽为只读，见 §12）。

### 13.2 「官方模型」不存在独立渠道（源码级）

- `@deepseek-ai/dsh-base/cordis.patch.yml:484-487` 原注释：*"The native DeepSeek adapter. **No key or endpoint is inlined**: both resolve per request from the `llm-deepseek:` settings section over this entry, with the key coming from the credential store below."*
- 未配 key 的分支（`dsh-llm-deepseek/lib/index.js:2040-2048`）：`credentials.resolve(ref)` → 否则 `launchEnvironmentOf(ctx).get(ref)` → 否则抛 `MISSING_CREDENTIAL`。**无任何内置或兜底 key 分支。**
- 全仓 grep `builtin key / official key / free tier / trial / defaultApiKey / FALLBACK_API_KEY` ⇒ 命中全为 cordis 的 `builtin` 模块与 `node:module isBuiltin`，**无密钥类实现**。
- 多提供方适配器 `llm-pi-ai` 默认**休眠**（`cordis.patch.yml:100-104`：*"mounted dormant: zero routes (and no extra models in the picker) until a `llm-pi-ai:` settings section supplies provider profiles"*）；当前 run home 的 `profiles/web/cordis.patch.yml` 为 `[]` ⇒ **实际生效的 LLM 路由只有 `deepseek-official` 一条**。
- 模型选择器里的「DeepSeek-V4.1-Flash High」是官方**目录条目**（catalog entry），不是独立计费通道；它指向的仍是 `api.deepseek.com`。

### 13.3 复现命令（已固化为可复用脚本）

```bash
netstat -ano | grep ":3080 .*LISTENING"        # → PID
python ~/.workbuddy/scripts/proc_env_scan.py <pid> --grep DEEPSEEK --grep DSH
python ~/.workbuddy/scripts/proc_env_scan.py <pid> --grep DEEPSEEK_API_KEY --reveal   # 仅本地核对，勿贴日志
```

脚本口径（`~/.workbuddy/scripts/proc_env_scan.py`）：**不用 PEB 逐级解引用** —— `RTL_USER_PROCESS_PARAMETERS` 的 `Environment` 偏移随 Windows 构建与进程位数变化，实测按 0x80（64 位）与 0x48（32 位）两种常规偏移**均失败**（`IsWow64Process=False`、`PEB=0x3eb000`、读到的 UNICODE_STRING `Buffer` 恒为 0）。改为「`VirtualQueryEx` 枚举已提交区域 → UTF-16LE 搜索 `SystemRoot=` 锚点 → 就地解析环境块」，与偏移解耦；默认脱敏，`--reveal` 才输出明文。

### 13.4 附带结论：模型自述仍不可作判据

截图那句「我是 Claude，由 Anthropic 开发的模型」与本节结论**无冲突**——模型自述不改变请求的实际去向。请求确实带着 `sk-27dd4f745…` 发往 `api.deepseek.com`，端点 `/models` 也只承认 `deepseek-flash` 与 `deepseek-v4-pro` 两个名字。身份误报属模型侧行为（§9.1 已记）。

# §9 补充：模型配置（含 9.1 重启判定 / 9.2 计费与 key 分层） —— 下沉明细

> 由 `SKILL.md` 下沉（Gate9 体积门禁 10240 字节）。**原文逐字保留**，
> 未做任何改写：本文件的内容是从 SKILL.md 的行区间原样搬过来的，
> 因此「信息零损失」是构造性的，不是声称的。判定口径/阈值/纪律仍以 SKILL.md 为准。

## 九、模型配置（含 9.1/9.2）→ 留六条硬口径（原 SKILL.md L161–L191）

## 九、模型配置（V4.1-Flash 口径）

> 适配器 `@deepseek-ai/dsh-llm-deepseek`；唯一路由 `deepseek-official`。

**官方目录**（源码 `DEFAULT_MODELS`；省略 `models` 时生效）：`deepseek-flash`(V41-Flash, **text+image**, in-history) / `deepseek-v4-flash` / `deepseek-v4-pro` / `deepseek-v4-flash-vision-exp`(text+image)。

- ⚠️ **V4.1-Flash 的 id 是 `deepseek-flash`**，不是 `deepseek-v4-flash`（那是 V4-Flash，纯文本）。网关反伪证：`INVALID_REQUEST: …supported API model names are deepseek-flash, deepseek-v4-pro`。
- ⛔ **显式 `models` 整体替换官方默认**（`models ?? DEFAULT_MODELS`）：净损失仅 `systemPromptUpdate: in-history`；图像预算**不受影响**（省略回落 `64e4`/`1MiB`）。**首选省略。**
- 落点两处、互不覆盖：① `dsh.sh` 每次新建 DSH_HOME 由 `seed_model_settings` 注入（只钉档位）② 直连 CLI 读 `~/.dsh/settings.yaml` 的 `agent-default-model.model`。**零重叠**：~/.dsh 换无效 id、另起空 home 仍跑通 391 ⇒ **无全局 user layer**。
- **验证**：`agent-default-model.model` 改无效 id → `INVALID_REQUEST`。⛔ `--dump-config` **不含** user layer。

### 9.1 生效时机与重启判定

| 改动对象 | 需重启? |
|---|---|
| `~/.dsh/settings.yaml`（直连 CLI） | **否**——新进程启动读入；在跑进程不回溯 |
| seed 模板 / 在跑 web 的 `run-*/settings.yaml` | **是**——停 web → 重起 |

- **web 与 `~/.dsh` 解耦**：`cmd_web` 每次新建 run home + seed；run home 一次性、不继承（UI 档位不跨重启保留）。
- ⛔ **模型自述不可作判据**：自称「我是 Claude」经全链路取证证伪（system、skills、request 三处命中 **0**，仅 assistant 输出命中）；只认 `request/context` 的 model 字段。取证法见 `references/session-forensics.md`。
- ⚠️ key/baseURL 按请求解析（源码注释）；settings.yaml 热加载**未实测**，上表保守。
- 完整表 / 判据命令 / 判别器（UI 档位名有无小数点即区分读哪份配置）：`references/model-config-and-restart.md`。

### 9.2 模型本体来源与计费出口

- **不自带模型本体**：只有目录元数据（4 项）；全仓 **0 权重文件**、无本地推理依赖。
- **一律走远端**：`POST {baseURL}/chat/completions`（默认 `https://api.deepseek.com`，env `DEEPSEEK_BASE_URL` 可换）+ `Bearer <key>`；附件走同域 Files API；搜索另走 `…/anthropic/v1/messages`。
- **实测三证**：无 key ⇒ `MISSING_CREDENTIAL`；baseURL 不可达 ⇒ `TRANSPORT`；在跑 web 会话自带 tokenUsage 账本。
- **key 分层**：进程环境（最高）> `.credentials.yaml`（Models 页只写）> cwd `.env` > `$DSH_HOME/.env`。
- **隐性计费**：默认 bundle 另挂 `session-title-first-prompt-llm`、`web-search-deepseek`；**密钥归属**：web 进程环境内 key 与 HKCU 逐字节一致（进程级实证），无独立官方渠道。
- 细节：`references/model-config-and-restart.md` §10/§13。
