# 重启后核验（红线：DSH 每次重启后必做「补丁存活 + 凭据加载」）

> 由 SKILL.md §二 指针引入。**入口 = 一条命令，不要手搓判据**。
> 建立 2026-09-24；原脚本仅覆盖 6 项（proxy 补丁 + DEEPSEEK），本轮补第 7/8 项（jev 侧）；2026-09-25 补第 9 项（活动实例端点真应答 + `--selftest` 变异探针）；2026-09-25 补第 10 项（recovery-gap 观测，闭环潜伏缺口可观测化）；2026-09-30 补第 11 项（gate 接线真走 choice，堵「trace 只证加载」的推断式假绿）；2026-09-30 补第 12 项（**规格合规**：核验**动作自身**是否越界，填四维之「规格合规」空洞）。

## 入口

```bash
bash ~/.workbuddy/scripts/dsh_health_probe.sh   # 纯只读；rc=0 = 全绿
bash ~/.workbuddy/scripts/dsh_health_probe.sh --quiet      # 仅 FAIL 项 + 结论（CI 友好）
bash ~/.workbuddy/scripts/dsh_health_probe.sh --dimensions # 四维覆盖性消融（须每次映射变更后重跑）
```

## 12 项检查

| # | 项 | 判据 |
|---|---|---|
| 1 | `dsh.sh` 适配器 | 文件存在 |
| 2 | `NODE` | `versions/current` 可解析且二进制存在 |
| 3 | `DSH_BIN` | `@deepseek-ai/dsh/lib/bin.js` 存在 |
| 4 | **proxy 补丁** | `<DSH_HOME>/.env` 含 `HTTP_PROXY`/`HTTPS_PROXY`/`NO_PROXY` 三元组 |
| 5 | DEEPSEEK 凭据 | `DEEPSEEK_API_KEY` 经 HKCU\Environment 可加载 |
| 6 | 引擎存活 | `dsh --version` 能起（实测 `0.1.5-rc.2`） |
| 7 | **jev 补丁存活** | `.dsh-jev-trace.log` 末行 `apply pid=` 与 `harness.log` 末条 `dsh web:` **同一实例**（时间差 <300s） |
| 8 | **OPENROUTER 凭据** | `~/.workbuddy/models.json` 含 openrouter 条目（jev 的实际依赖） |
| 9 | **活动实例端点真应答** | 提取 `harness.log` 末条 `dsh web:` 的 port/token → cookie 交换 → `GET /` 断言 200；**真打运行中实例**，堵第 7 项「只看 trace 日志」的日志推断式假绿 |
| 10 | **recovery-gap 观测** | 扫 `harness.log` 近 14 天 `[recovery-gap]`；出现 ⇒ pnpm 输出含 rename-blocker 码但 `lockedRenameTarget` 取不到 target，recovery 静默不触发（潜伏缺口已激活）⇒ FAIL |
| 11 | **gate 接线走 choice** | 跑 `gate-choice.runtime.mjs`（**真 apply + 真触发** `tools/pre-execute`）⇒ `VERDICT=CHOICE_OK kind=choice`；`NOUL` = 接线退化为旧问法 ⇒ FAIL |
| 12 | **规格合规（动作不越界）** | 调 `~/.workbuddy/scripts/dsh_spec_compliance.py --scan $SELF` ⇒ `VERDICT=COMPLIANT`：写目标须在临时面/白名单、无破坏性原语、无 `--apply`。往本探针注入 `rm -f` 即 FAIL（探针 **M16**） |

## 关键穷证：一行双证

trace 末行形态：

```
apply pid=13768 v=0.2.0 hooks=post-execute,pre-execute,request-error jev=ready
```

`jev=ready` **同时**证明「补丁存活」与「凭据已加载」——因为 `JevClient` 构造函数**缺 key 即 `throw`**
（`plugin-manager-src/github.com-inovance-dsh-jev/src/jev-client.js:48-49`）；构造失败则 trace 写 `jev=unavailable`。
⇒ 见到 `jev=ready` 就**不必**再单独验 OPENROUTER 是否被 jev 读到（第 8 项是防「补丁在、key 没了下次才炸」的前置冗余）。

**活动实例判定**：`trace 末行 apply pid` 必须对应 `harness.log` **最后一条** `dsh web: http://127.0.0.1:<port>/?token=<T>` 那次启动（差 <300s）；
否则那条 `apply` 属**已死实例**，不算数。

## 第 9 项：活动实例端点真应答（2026-09-25）
- 动机：第 7 项只看 `trace jev=ready` + 与活动实例时间差 <300s，**从不真打运行中实例**；若实例启动后崩/端口失效，探针仍会判绿 → 日志推断式假绿（与既往「判据空心」同型）。
- 实现：`probe_endpoint(port, token)` 用 urllib（stdlib）做 `GET /?token` 换 cookie → 带 cookie `GET /` 断言 200；纯只读 GET，不碰启动链路。
- **变异自检**（`bash dsh_health_probe.sh --selftest`）：负控（死端口 1 ⇒ 必须判 FAIL，证有牙）+ 正控（活实例 ⇒ 必须判 OK）。两控覆盖两个危险方向（恒真 OK 被负控抓、恒假 FAIL 被正控抓）。
- ⚠️ 实现坑：python 成功分支必须 `print("OK")` 而非仅 `sys.exit(0)` —— 否则 `$()` 捕获空串，活实例也被判 FAIL，且负控「碰巧」判 FAIL 形成**假绿变异探针**（空输出同样 ≠ OK）。已修。
- 该脚本是 DSH 域红线工具，**已**登记进 WB 回归第 62 项（`wb_selftest_all.py` 调 `dsh_health_probe.sh --selftest`），与手动/重启后触发双重覆盖。

## 第 10 项：recovery-gap 观测（2026-09-25）
- 动机：B 线 EPERM 工作把 `lockedRenameTarget` 取不到 target 时的**静默早退**改成了「打 `[recovery-gap]` 诊断」（pnpm-runner.mjs L446/L784/L803）。但日志会写、无人读 ⇒ 潜伏缺口仍未被主动捕获。本项把"可观测"闭环为"被观测"，纳入重启红线核验。
- 实现：`scan_recovery_gap(logpath)` 用正则 `\[([^\]]+)\].*\[recovery-gap\]` 扫日志，解析行内 ISO 时间戳，仅判**近 14 天**内的命中（避免历史陈旧行永久 FAIL）；时间不可解析 → fail-safe 视为近期（宁可误报不漏报）。只读 `harness.log`，零副作用。
- **变异自检**（`bash dsh_health_probe.sh --selftest`）：正控（注入含近期 `[recovery-gap]` 的临时日志 ⇒ 必须判 FAIL，证有牙）+ 负控（无 `[recovery-gap]` 的临时日志 ⇒ 必须判 PASS，证不误报）。临时文件用 Python 兜底删除，零残留。
- 触发后果：`[recovery-gap]` 出现 ⇒ 第 10 项 FAIL（rc=1），提示 pnpm 错误消息格式可能已漂移，需核 `lockedRenameTarget` 正则（pnpm 升级或下次 EPERM 现场时优先攻此）。

## 第 11 项：gate 接线走 choice（2026-09-30）
- 动机：第 7 项 `jev=ready` 只能证「插件加载了 + key 在」，**证不了运行时选的是 choice 还是 noul**。
  实证事故：`src/index.js` 曾**硬编码** `new JevRiskBackend(jev)`、不读 config ⇒ config 写了
  `questionKind:'choice'`，trace 与单测**全绿**，运行时仍是旧问法（noul 无 confidence）。
  这是与第 9 项同型的「日志/配置推断式假绿」，只是换了个层级（加载 vs 分支）。
- 实现：调 `skills/jev-decide/scripts/gate-choice.runtime.mjs`，走**真实 `apply()` + 真实 Jev 后端**
  注册 cordis 钩子后触发 `tools/pre-execute`（破坏性 `rm -rf /var/data` + 安全 `ls -la` 两例）。
  判据 = reason 含 `choice=` ⇒ choice 生效；只含 `destructive=`/`highImpact=` ⇒ 仍是 noul。
  脚本收尾打机器可读行 `VERDICT=<CHOICE_OK|NOUL|ERROR> kind=<choice|noul> bad=<n> noSignal=<bool>`。
- **三态语义**（勿把故障误报成接线错）：`CHOICE_OK`=PASS；`NOUL`=接线退化⇒FAIL（查 index.js 是否又硬编码）；
  `ERROR`=破坏性用例拿不到任何 reason（凭据/网络/后端不可用）⇒ 也判 FAIL 但措辞指向第 8 项。
  ⚠️ 出网 2 次/轮（P50 ~0.7 s），是**全部检查项里唯一有网络依赖的**；**失败先区分「退化」还是「不通」**再动手。
- **变异自检**（`bash dsh_health_probe.sh --selftest`）：
  - 负控：`GATE_CHOICE_MUTATION=noul` 强制旧问法 ⇒ 必须判非 `CHOICE_OK`，
    且**附加 `kind=noul` 断言**——只判「非 OK」会被「网络故障碰巧判红」蒙混，须同时证注入真生效。
  - 正控：默认 ⇒ 必须判 `CHOICE_OK`（证判据能给出 OK，非恒假）。
- 与其余三项的关系：`test.mjs`（零出网，证策略分支）/ `compare.mjs`（12 例，证一致率与延迟）/
  本项 `runtime.mjs`（证接线）。三者分工不同，**不要用前者替代本项**。

## 第 12 项：规格合规 —— 核验**动作自身**不越界（2026-09-30）

- 动机：四维覆盖性论证（下节）照出**整类空洞** —— 其余各项证的全是「判据有牙 / 不误报」
  （各判据的 `--selftest` 正负两控），**没有一项**检查核验或修复**动作自己**是否越界。
  换言之：探针从不误报**别人**，但**它自己**会不会顺手删文件，此前无人问。
- 实现：调 `~/.workbuddy/scripts/dsh_spec_compliance.py --scan "$SELF"`。**判据不内联**（单一来源），
  逻辑全在该器：`R1` 写重定向目标白名单（仅 `/dev/null` 与 `${SELFTMP_DIR|TMPDIR}` 系）、
  `R1b` **变量洗白拦截**（白名单变量还须**赋值落在临时面**，光声明不放行）、
  `R1c` python 内联写须带 `# SPEC-WRITE-EXEMPT:` 标注、`R2` 破坏性原语禁用、
  `R3` 禁自动 `--apply`（本库红线：apply 前须 `--approve` 痕迹）。
- 白名单登记唯一格式：本脚本内 `# SPEC-WRITELIST: LIVE_PORT_F TMPG TMPG2 DPOISON`
  —— **登记即声明，声明须可落地**；写进真路径的白名单变量会被 `R1b` 判违规。
- **变异自检**：`--selftest` 内挂该器自检（正控＝**真本脚本必须判 COMPLIANT**）。
  探针 **M16** 往本脚本注入 `rm -f` ⇒ 正控红 ⇒ 第 12 项 FAIL ⇒ **WB 回归第 62 项转红**（实测 KILLED）。
  该器自身的反恒真由 **M17** 覆盖（唯一判定出口恒判 `COMPLIANT` ⇒ WB 回归第 **116** 项转红）。
- 如实记的三处边界：
  ① **静态面**：覆盖 shell 重定向、shell 破坏性原语、常见 python 写调用；**不可静态判定**的写
     （外部命令内部写、动态拼路径）不在面内 ⇒ 由自检动态夹具 ＋ 人工复核补足，**勿当全称证明**。
  ② `--quiet` 曾因 `report()` 在静默态返回 1 而**假 FAIL 4 项**（1/2/3/5）——
     **用改前备份复现**确认是**预存在缺陷**，已补 `return 0` 并加自检用例（子壳验静默态返回码）。
  ③ **①的边界已做成「每次可见」**（260930 五次处置轮）：该器每次运行都打印「**契约面覆盖性**」
     三行 —— ✓ 面内六条判据 ／ ✗ **面外**（外部命令内部的写、运行期动态拼路径：本机**无系统调用
     拦截能力**（Windows 无 strace）⇒ 静态不可判定）／ ⇒ 只证「**核验器自己**」不证「被它调用的
     外部程序」。⇒ 边界从**文档里的一句话**变成**读数**（＝机制二「覆盖性论证」手法用于该器自身）。
     **未**重构宿主 26 处重定向（代价 > 收益，按预案降级为「可见化」）。
     ★ **口径对齐**：这里的「26 处」= **25 处 shell 写重定向 ＋ 1 处 python 内联写**
     （实跑读数 `n_writes=25 n_py=1`）—— 两者**不可混算**，也**不是**「26 处重定向」。
     ★ **该降级的升级触发条件**（本库纪律：**降级必须带触发条件**，否则「降级」与「忘做」不可区分）：
     (i) 本机获得**系统调用拦截能力**（Linux 侧 `strace` 类、Windows 侧等效 API 钩子）⇒ 面外部分可入面；
     (ii) 宿主写重定向点数**降到 ≤ 15**（原提案阈值）⇒ 重构代价 < 收益，须补 `R1d` 单一写出口 ＋ 运行期对账；
     (iii) 出现**真实越界实例**（面外的写造成副作用）⇒ 立即补面，不等阈值。
     当前实况（260930 五次处置轮）：`n_writes=25 > 15` ⇒ 走**降级支**，**未做 R1d** —— 这是**判定**，不是遗漏。

## 反思纪律（本轮实测）

- **新检查项必须做 mutation 探针**，否则可能是恒真：`USERPROFILE=/tmp/probe-empty APPDATA=/tmp/probe-empty bash dsh_health_probe.sh`
  ⇒ 第 7/8 项 **FAIL、rc=1**，其余 6 项不受影响 = 判据精准。探针后确认无 `MUTATION-PROBE` 残留。
- **改脚本先判引用关系**：`dsh_health_probe.sh` 在 `scripts/`、`hooks/`、`skills/`、`settings.json` 中**零引用**、未登记 hook 桶
  ⇒ 独立工具，改动安全（但仍须备份 `.bak-<日期>-<事由>`）。**当时技能正文也无任何指针** → 红线执行入口不可发现，本文件即为此而生。

## 日志判读陷阱（重启后常见噪声）

- 🔹 `paoding-config-ui: cannot locate role blocks … role search_external: expected exactly 1 toolFilter.allow block, found 0`
  **非故障**：① 该 `toolFilter.allow` 在 yml 中**确实存在**（`presets/orchestrator/agent.cordis.yml` L220–230）⇒ 是该 UI 组件自身解析偏差；
  ② `dsh-paoding` **不引用** `dsh-jev`（grep 零命中）。warn 级、与出口补丁无关，**勿去追**。
- 🔹 非工具型插件（只注册路由/会话投影，如 clearAI）**本就不打印注册行** ⇒ **不能**用「harness.log 有没有提到插件」判它是否加载。
  正确判据见技能 `dsh-desktop-plugin-register`：`/api/<ns>/*` 真应答 + RPC **新建**会话带 `record.rows.<ns>`。

## 四维契约：逐项清单的覆盖性论证（2026-09-30；当时 11 项，260930 第三轮补至 12 项）

来源：外部框架 ScientistTwo 的 CoE 完整性审计四维（`harness-governance/references/external-mechanism-hardening.md` §二）。
**用途不是替代逐项清单，是给逐项清单一个覆盖性论证** —— 逐项清单回答「查了什么」，四维回答「有没有整类没查」。

| 维度 | 本文件对应项 | 强度 |
|---|---|---|
| 分数复现（真跑取数，非读日志） | 第 6 项（`--version` 实测）、第 9 项（真打活动实例断言 200）、第 11 项（真跑 runtime 取 `VERDICT`） | 🟢 三项皆真跑 |
| 规格合规（动作本身不越界） | **第 12 项**（`~/.workbuddy/scripts/dsh_spec_compliance.py`，见上「第 12 项」节） | 🟢 真跑：扫**核验器自身**；M16（往宿主注入 `rm -f`）／M17（合规器恒判合规）**双向有牙** |
| 引用可溯（指称指向真实对象） | 第 7 项（trace 末行 ↔ `harness.log` 末条须同一实例、差 <300s）、第 8 项（凭据存在性） | 🟡 |
| 方法-代码对齐（声称 vs 实际分支） | 第 11 项（config 声称 `choice` vs 代码实际走 `noul`） | 🟢 直接命中 |

**本次映射的产出 = 发现的空洞**：「规格合规」维度**零覆盖**。当时的 11 项证的是「判据有牙 / 不误报」（`--selftest` 的正负两控），**没有一项**检查核验或修复**动作自身**是否越界。

> **【260930 闭合】** 该空洞**已填**：新增**第 12 项**（`~/.workbuddy/scripts/dsh_spec_compliance.py`，见上节），
> 本表「规格合规」行由 ⚠️ 空洞 改为 🟢。该闭合同时进了 WB 回归第 **116** 项，并配 **M16/M17** 两条探针。
> 原文保留在上（如实记录当时的空洞状态），**勿再按「零覆盖」引用**。

**第 12 项（260930 已实施，见上「第 12 项」节）**：
核验默认只读；一旦核验脚本产生写动作，该写动作须落在显式白名单路径内，越界即 FAIL；修复动作**不得**自动触发 apply，须留 `--approve` 痕迹。与本库既有红线（apply 前须显式批准）同向。
—— 上文「未实施，待定，勿当已生效判据引用」的限定**自 260930 起失效**；现可作为已生效判据引用。

**反恒真要求（260930 已执行）**：**禁用某一维对应的检查项 ⇒ 该维度必须出现 FAIL**。
本脚本新增 `--dimensions` 模式专用此验，四维**逐一毒化其代表判据**、全部复用既有注入（不复制判据）：

```
$ bash scripts/dsh_health_probe.sh --dimensions
  ✅ ① 分数复现  有牙：死端口取数判 UNREACH（非 OK）
  ✅ ② 引用可溯  有牙：空对象集 ⇒ 第 7/8 项判 FAIL
  ✅ ③ 方法-代码对齐 有牙：注入 noul ⇒ VERDICT=NOUL（默认 CHOICE_OK）
  ✅ ④ 规格合规  有牙：毒化夹具判 VIOLATION
✅ 四维消融：4/4 维已证有牙 ⇒ 映射非装饰
```

⚠️ 本模式**不并入** `--selftest`（含真实例/网络/引擎依赖，并入会让 WB 回归第 62 项变慢变脆）
⇒ **每次四维映射变更后须手动重跑并把读数回填本节**。某维因环境不可判定而跳过时，脚本**响亮跳过**
（`⏭`）并计入「未证」，**不得**记作已证。
