# A-evidence

> 由 dsh-rollback-recovery/SKILL.md 于 2026-09-20 **逐字下沉**，零改写。
> 动因：Gate9 体积门只量 SKILL.md（阈值 10240 字符）。

evidence:
  - claim: "插件启动失败恢复链（2026-09-19）：弹「启动修复」= 插件自身 bug（访问 ctx.webServer 未声明 inject）→ harness 停 → 自动隔离成功但 `dsh plugin install` 重建被 pnpm git-prepare 门拦 ⇒ status 停在 cleanup-pending 反复弹窗；市场的 HTTP 404 是次生症状（GitHub 源插件不在 npm）。pnpm 该门有两条通道两套 id：tarball 通道键=codeload URL（无 sha 的『稳定键』永不匹配），clone 通道键=createGitHostedPkgId=git+${repo}#${commit}；且 DSH 自带 runner 的正则只认 git+ssh 形态 ⇒ 对 git+https 形态不会自动补键"
    source: "harness.log / plugin.log / recovery/plugin-removals.json / pnpm.cjs 源码(createGitHostedPkgId、preparePackage) / pnpm-runner.mjs 正则 / 7 组隔离复现，2026-09-19"
    kind: 实测
  - claim: "写锁源码级取证（2026-09-18）：withFileLock 以『已存在即失败』创建、永不抢占；注释逐字『orphan recovery is an operator action』⇒ 不回收系刻意设计；锁内容=持有者 PID；仅强杀留孤儿；--dump-config 不经过 heal ⇒ 锁被占时 dump 仍 rc=0，可作『锁残留 vs 配置写错』的区分判据；实测处置 4 把孤儿锁（mv 留痕）"
    source: "dsh-atomic-write/lib/index.js 通读 + 4 把孤儿锁实测处置，2026-09-18"
    kind: 实测
  - claim: "架构切换（2026-09-14）：F:/DSH 源码树损坏（249 子包仅 37 正常），改装官方 npm 分发 F:/DSH-npm，0.1.2-rc.1→0.1.5-rc.2"
    source: "pathlib 分类遍历 + npm install，2026-09-14"
    kind: 实测
  - claim: "冒烟 4/4（0.1.5-rc.2）：--version=0.1.5-rc.2 / 391 / 291 / 338350；acp 内置 profile 首用自动初始化；settings.yaml 注入被原样保留"
    source: "headless + --dump-config，2026-09-14"
    kind: 实测
  - claim: "版本敏感区实为四处：mcp.json 的 dsh-bridge command 仍指向已删 node，且重新信任不重读 command → 桥静默失败"
    source: "mcp.json 解析 + MCP 帧探针，2026-09-14"
    kind: 实测
  - claim: "清理口径：rm -rf 放后台被拦（31978 文件超阈值 50），前台单发/分片均可（1.6G 约 2m52s）；小体量改 shutil.move 暂存 _trash-<日期>/"
    source: "F:/DSH 系列 + _dsh-smoke 清理，2026-09-14"
    kind: 实测
  - claim: "Web 首启（2026-09-14）：监听 127.0.0.1:3080，打印 ?token= URL 并自动开浏览器；token 换 dsh-auth-* cookie 后根路径 200、无 token 401；长驻独占 .dsh.lock"
    source: "dsh.sh web + cookiejar 探针，2026-09-14"
    kind: 实测
  - claim: "模型口径 + 写锁修复（2026-09-14）：V4.1-Flash 的 dsh id = deepseek-flash（网关报 INVALID_REQUEST: supported names are deepseek-flash, deepseek-v4-pro）；~/.dsh 旧 pnpm 残留致 heal 写锁死锁，改名隔离后首跑通（exit=0）"
    source: "DEFAULT_MODELS 提取 + 反伪证 run + 改名隔离，2026-09-14"
    kind: 实测
  - claim: "配置生效时机（2026-09-14）：web 与 ~/.dsh 解耦（cmd_web 每次新建 run home + seed）；在跑 web（PID 46012）实读 run-*/settings.yaml，model=deepseek-flash，与 UI 档位名互印；~/.dsh 植入无效 id + 空 home 仍跑通 391（无全局 user layer）；省略 models 仍可看图（A=红 B=蓝）"
    source: "dsh.sh 源码 + 逐字节 diff + GetProcessTimes + 反伪证/视觉双探针，2026-09-14"
    kind: 实测
  - claim: "模型本体（2026-09-14）：包内只有目录元数据、0 权重文件、无本地推理后端；推理一律远端 POST {baseURL}/chat/completions；三证＝无 key⇒MISSING_CREDENTIAL / baseURL 不可达⇒TRANSPORT / 在跑 web 会话 tokenUsage 实账"
    source: "包扫描 + 双反伪证 run + session 元数据，2026-09-14"
    kind: 实测
  - claim: "模型自述不可作判据（2026-09-14）：会话自述『我是 Claude』经全链路取证证伪（system/request 命中 0）；六组 ACP 对照全答 DeepSeek"
    source: "会话 zstd 取证 + 六组对照，2026-09-14"
    kind: 实测
  - claim: "出口代理与环境分层（2026-09-19）：代理变量仅 home 层 .env 可设（项目层声明直接抛错）；物化顺序为『继承 env > 项目 .env > home .env』，.env 只补位不覆盖 ⇒ 父进程带代理时 .env 静默失效；清空代理 env 后调官方 loadLayeredEnv，两套 home 均得 source=user-env 指向 <DSH_HOME>/.env（此为唯一可信验证法，用 dsh_run 看 env 会因继承 WorkBuddy 代理而假阳性）；另发现 NODE_OPTIONS 垫片 dsh-proxy-shim 与 .env 双通道并行（硬编码默认 7897），注入点**已定位并消除**（2026-09-19）：Desktop 主进程启动 harness 前会点源 $PROFILE 并整体捕获其环境作为 harness 子环境（bundle L7932-L7948 → L8180 → L8186）⇒ 分叉真源是 profile 内硬编码 `$env:DSH_SEARCH_PROXY`，已删除；垫片四级解析下沉后**代理唯一真源 = <DSH_HOME>/.env**"
    source: "dsh-app-boot/lib/index.js L1050-L1136 通读 + loadLayeredEnv 双 home 实测 + NODE_OPTIONS 垫片日志(1641行)与进程命令行比对，2026-09-19"
    kind: 实测

---

## Gate9 体积裁定（2026-09-20，Kevin 回「A」）

- **裁定**：本技能 SKILL.md 保留 **14,946 字符**，不做任何改动。按权威阈值 10,240 记 FAIL，
  作为**已裁定的已知偏差**入账，不再逐轮重查。
- **基线**（2026-09-20 全库实测）：102 技能 → PASS 78 / **FAIL 1** / SKIP 23 / WARN 0。
  本技能是**全库唯一 FAIL**；另 78 个技能均在 10,240 内 ⇒ 阈值可达，非"系统性偏严"。
- **未采纳**：B（§十四/§十五 执行细节外移 —— 事发时需多开文件，违背 runbook 定位）；
  C（`gate9_exempt` 判据是机器契约，本技能是人工 runbook，不属豁免对象）；
  D（合并重复叙述 —— **推迟**，须先实证与既有 references 存在逐字重复）。
- **⚠️ 禁止用 frontmatter 伪装休眠消 FAIL**：`gate9_grade.py:_skill_is_dormant()` 读 frontmatter
  `status: disabled` ⇒ 判 SKIP；但加载器**不读** frontmatter、只读 settings.json 的
  `skillOverrides` ⇒ 技能照常加载、照常占注入预算，体积门却报 SKIP ＝ **假达标**。
  见 skill-health 的 `hard-facts.md` 第 1、6 条。

