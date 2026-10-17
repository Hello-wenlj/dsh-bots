# 模型身份取证：为什么「模型自述」不能作为判据

> 2026-09-14 实例。现象：dsh web UI 标签为 `deepseek-flash`（DeepSeek-V4.1-Flash High），
> 但问「你是什么模型」时模型连答两轮「我是 **Claude**，由 Anthropic 开发的模型」，
> 且主动否定 harness 声明（"那只是 harness 侧的一个配置名/标签，不代表我实际的底层模型身份"）。

## 1. 结论（三层归因）

| 层级 | 判定 | 证据 |
|---|---|---|
| 配置层 | ✅ **完全正确，无错配** | `request/context` = `{"provider":"deepseek-official","model":"deepseek-flash","contextWindow":1000000}` |
| 提示层 | ✅ **无 Claude/Anthropic 注入** | `system/message`(6977 字符) 开头即 `You are a coding agent powered by the deepseek-flash model.`；Claude/Anthropic 命中 **0** |
| 模型层 | ❌ **权重身份先验错误** | 模型 thinking 原文：`I should respond honestly that I'm Claude, built by Anthropic` / `We need to directly state that I'm Claude … and not claim to be a DeepSeek model` |

**一句话**：harness 没错、配置没错、请求没错——错的是**模型对自己是谁的认知**。
LLM 没有内省能力，「我是什么模型」是**从训练分布外推生成的文本**，不是查询真实元数据。

## 2. 分区关键词统计（决定性判据）

```
[ 9] system/message   len=6977    Claude=0  Anthropic=0   ← harness 注入
[10] user/message     len=6       Claude=0  Anthropic=0   ← 真实提问「你是什么模型」
[11] user/message     len=456     Claude=0  Anthropic=0   ← 运行时上下文
[12] user/message     len=10055   Claude=0  Anthropic=0   ← skills 注入
[13] request/header   len=29442   Claude=0  Anthropic=0   ← 工具定义 + config
[14] request/context  len=86      Claude=0  Anthropic=0   ← model/provider 字段
[18] assistant/message len=298    Claude=2  Anthropic=2   ← 第一轮回答
[26] assistant/message len=417    Claude=3  Anthropic=2   ← 第二轮回答
```

**输入侧全部为 0，Claude 只出现在输出侧** ⇒ 排除「提示词污染」假说。

## 3. 会话取证方法（可复用）

### 步骤 1：定位 web 进程与会话目录

```bash
# node 系进程 → 找到 dsh web PID（本机为 46012）
python ~/.workbuddy/scripts/list_node_procs.py
# 读该进程 DSH_HOME（决定会话落点）
python ~/.workbuddy/scripts/proc_env_scan.py <PID> --grep DSH_HOME
# 会话目录名 = cwd 加转义，例：--F-dsh-npm_wlj--  ⇒ cwd=F:\dsh-npm_wlj
```

### 步骤 2：解压多帧 zstd（关键坑）

⛔ **`zlib.zstdDecompressSync` 只解第一帧**；文件体是**每次 append 一个独立 zstd 帧**的拼接，
首帧常只有 ~195 B（session 头）。流式 API 同样在首帧后停止。

✅ **正解：按 magic `28 B5 2F FD` 手工切帧，逐帧解压再拼接**。

```bash
node ~/.workbuddy/scripts/dsh_session_dump.js <session.v3.jsonl.zstd> <out.jsonl>
# 实例：10 帧 / 26316 B → 81023 B / 28 条记录
```

⚠️ magic 序列理论上可能出现在压缩数据内部（本次未发生）；若解压帧数异常，改用
python `zstandard` 的 `decompressobj()` 做真流式解析。

### 步骤 3：分区统计，而非全文 grep

全文 grep 只会得到「Claude 出现 14 次」这种无法归因的数字。
必须**按记录类型（`system/message` / `user/message` / `assistant/message` / `request/*`）分别计数**——
判据是**输入侧是否为 0**。

### 步骤 4：读 assistant 记录的 thinking

dsh 的 `assistant/message` 里 thinking 与正文同段。thinking 会**明说**模型的身份判断依据，
这是最直接的归因材料（本次即为 thinking 直接断言 Claude）。

## 4. 为什么这次触发、对照实验却不触发

同模型同 provider 下做了 **6 组对照**（`dsh-bridge` 的 ACP 通道，`runAcp` 原样透传 prompt、
无任何包装，见 `server.mjs:236`），**全部回答 DeepSeek**：

| # | mode | effort | cwd | 问法 | 结果 |
|---|---|---|---|---|---|
| 1 | standard | low | 工作区 | 裸问「你是什么模型」 | DeepSeek |
| 2 | standard | low | — | 加系统事实约束 | DeepSeek-V41-Flash |
| 3 | standard | low | — | 三选一（A DeepSeek / B Claude / C 不确定） | 选 A |
| 4 | ptc | low | `F:/DSH-npm` | 裸问 | deepseek-v4-flash |
| 5 | standard | **high** | 工作区 | 裸问 | deepseek-v4-flash |
| 6 | ptc | high | `F:/DSH-npm` | **诱导「查 node_modules 推断模型」** | DeepSeek-V4-Flash（并主动区分外壳/模型） |

⇒ **「Claude」不是稳定复现的行为，是低概率采样路径**。

触发条件（web 会话侧同时具备）：
1. 提问极短（6 字符），**零约束** —— 没有「只回答名称」这类把模型推向照读上下文的指令；
2. **`reasoningEffort: high` + 长上下文**：system 6977 + skills 10055 + tools 29442 ≈ 46 K 字符，
   身份声明（一句话）在 context 中被稀释到极低权重；
3. **两轮连问**：第一轮的「我是 Claude」进入历史，第二轮受**自我一致性**强化
   （第 26 条措辞与第 18 条高度同构，属锚定而非独立采样）；
4. 用户连续追问「你是什么模型」本身构成一种**质疑性语境**，模型倾向于给出「不随大流」的断言。

## 5. 工程含义（沉淀为规则）

1. ⛔ **永不把模型自述当身份判据**。判据只有：`request/context` 的 `model` 字段、
   API 端点、服务端回执、计费账单。
2. ⛔ **不要用「你是什么模型」做模型指纹**。它测的是训练数据里的身份先验，不是部署配置。
   其错误方向有偏：蒸馏语料普遍含 Claude/GPT 身份，偏向性错误只会指向**教师模型**。
3. ⚠️ **UI 标签与模型自述冲突时，信标签 + 信 `request/context`**。UI 标签来自
   `dsh-llm-deepseek` 目录的 `name` 字段（本地硬编码），不依赖模型输出，是可信侧。
4. ℹ️ 该问题属**厂商侧**（官方 harness + 官方模型 + 官方渠道），非本地配置问题；
   若需压制，只能在 system prompt / `AGENTS.md` 里加身份约束——但本实例证明**即便 harness
   明说也会被模型推翻**，治标不治本。

## 6. 附带发现：dsh.sh 的 run home 会误删 web 会话

- `dsh.sh` 的 `new_run_home()` 在建新目录前 `rm -rf "$DSH_BASE_HOME"/run-*`（line 149-151）。
- web 与 headless **共用** `DSH_BASE_HOME`，因此**跑一次 headless 就会删掉在跑 web 的会话目录**。
- 本次未触发：`dsh-bridge` 用的是**独立持久 home**（"ONE persistent home, reused by every call,
  never deleted"，`server.mjs:67`），不走 `dsh.sh`。
- ⚠️ 风险真实存在：`dsh.sh web` 起的会话，会被随后任意一次 `dsh.sh run` 删除。

## 7. 关联文件

- 会话原始记录（zstd）：`<run home>/sessions/<cwd-escaped>/session-*/session.v3.jsonl.zstd`
- 解压工具：`~/.workbuddy/scripts/dsh_session_dump.js`
- 进程环境读取：`~/.workbuddy/scripts/proc_env_scan.py`
- 模型口径：同目录 `model-config-and-restart.md`
