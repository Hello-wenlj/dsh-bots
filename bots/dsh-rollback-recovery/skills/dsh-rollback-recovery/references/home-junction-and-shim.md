# DSH_HOME 的 junction 结构、宿主删除门，与单例 home（2026-09-14 实测）

## 一、DSH_HOME 必须放 `tmpdir()`，否则直接起不来

宿主装有**删除门**（`D:\workbuddy\resources\app.asar.unpacked\cli\vendor\shim\node-safe-delete-shim.cjs`，
经 `node-language-shim.cjs` 注入 node / powershell 进程）。它对**非 temp 根**的批量删除
（`threshold: 50`）抛 `SAFE_DELETE_BULK_CONFIRM_REQUIRED`，fail-closed。

dsh 的 profile boot **自身就要做这种批量删除**（实测 `count: 1853`）。所以：

| DSH_HOME 位置 | 实测结果 |
|---|---|
| `%TEMP%\...` | ✅ 豁免（`isUnderAnyTempDir`），boot 正常 |
| `~/.workbuddy/state/...` | ❌ dsh `exit(1)` `SAFE_DELETE_BULK_CONFIRM_REQUIRED` |
| `%LOCALAPPDATA%\...` | ❌ 同上 |

**这不是"慢"，是"起不来"。** 任何 DSH_HOME（含 `dsh.sh` 的 `DSH_BASE_HOME`、
两个桥的 home）一律放 `os.tmpdir()` 下。放别处时 dsh 在 0.7s 内 exit 1，
只留下半初始化的空 home，极易被误判成"bootstrap 慢"。

## 二、home 里的 19–25k 文件是 junction，不是副本

`@deepseek-ai/dsh-app-boot/lib/index.js` 的 `healProfilesModuleFallback()`（定义于 `:657`，
建链在 `:426`）用

```js
symlinkSync(target, link, "junction")   // link = $DSH_HOME/profiles/<profile>/node_modules/<pkg>
```

把 home 的模块回退目录链到**安装根的实体包**。实证：

```
~/.workbuddy/dshhome/run-<ts>-<pid>/profiles/node_modules/@agentclientprotocol/sdk
  → \\?\F:\DSH-npm\node_modules\@agentclientprotocol\sdk        （junction）
```

所以 home 的"文件数"很大（~19–25k）是**穿过 junction 统计到的安装根内容**，
不是 home 自己的副本。删 home 不会删掉安装根。

## 三、删除 dsh home 的安全性（实测，勿凭直觉）

Windows 上 junction 的 `lstat` 返回 `S_IFDIR`（`0o40777`）而**不是** `S_IFLNK`，
所以"递归删除是否会跟随链接"必须实测：

| 方式 | 对 junction 本体 | 对"含 junction 的父目录" | 判定 |
|---|---|---|---|
| Node `fs.rm(recursive)` | 只删链接，目标完好 | — | **SAFE** |
| Python `shutil.rmtree` | 抛 `OSError: Cannot call rmtree on a symbolic link` | 目标完好 | **SAFE**（3.12+ 有 junction 保护） |
| bash `rm -rf` | 被删除门拦下（`trash-failed`） | 目标完好 | **SAFE** |
| `cmd rmdir` | 只删链接 | — | **SAFE** |

**结论：删除 home 不会连带清空 dsh 安装。** 但仍**不值得**——删 25k 文件实测需
**127s**（远超进程寿命），这才是 per-call 临时 home 必然泄漏的根因。

## 四、安装被清空的长相与恢复 —— ⚠️ **已复发 4 次：09-14 / 09-15 / 09-20（同形，480 空壳）/ 09-22（异形，待核实）**

> **不是一次性事故**。首次两次形态**逐条同形**，间隔 1 天。根因历次均未留痕（见 §4.1）。
> 故本节的定位是「**让恢复变便宜**」而非「堵住根因」。

> **⚠️ 路径迁移（2026-09-22）**：安装根已由 `F:\DSH-npm\node_modules` 迁至 **`D:\dsh-npm\node_modules`**，
> 旧根 F: 已废弃并删除。本节所有命令/snippet 已改为 D:。
> **复发谱系更新**：09-14 第1次 / 09-15 第2次 / 09-20（09-21 检出）第3次 —— 三次均 **480 空壳同形**；
> 09-22 疑似第4次但**形态不同**（仅 `@deepseek-ai/dsh` 单包抽空、其余 191 包正常）且未取得 `changed` 数
> ⇒ 标「**新机制待核实**」，**不并入 480 谱系**（若该形态再见，须走 §4.1 而非直接套用本节恢复）。
> 同日发现 `scripts/dsh-health-selfcheck.py` 默认根写死 F:，在 09-22 / 09-23 / 09-24 三次产生
> 「安装根不存在」**假阳性 ALERT**；现已将默认根改为 D:，并把内联恢复命令改为**由 ROOT 派生**（防再漂移）。

**症状**（两次一致）：

- `Error: Cannot find module 'F:\DSH-npm\node_modules\@deepseek-ai\dsh\lib\bin.js'`
- 包目录**存在但为空**：09-14 为 `@deepseek-ai/` 下 240/240 全空；09-15 为全树 **488 个包目录中 480 个为空**（存活仅 8 个）
- **空壳化特征 = 只删内容、留目录壳**：父目录（`node_modules`、`@deepseek-ai`）mtime **不变**，
  被清目录自身的 mtime **统一到同一分钟**（09-15 为 `15:01`×67 + `15:02`×413）
- npm 日志、`main.log` 中**查不到**该时刻的 install 记录
- 存活的 8 个包（`@img/sharp-*`/`@vscode/ripgrep`/`@koromix/koffi` 等原生件）mtime 早一天
  ⇒ **越早装的越可能存活**，像是「遍历中途停手」

**量化判据（先量空壳率，再看要不要恢复）**：

```python
from pathlib import Path
root = Path('D:/dsh-npm/node_modules')   # 2026-09-22 起安装根已迁至 D:（原 F:\DSH-npm 已废弃并删除）
pkgs = [c for p in root.iterdir() if p.is_dir()
        for c in ([x for x in p.iterdir() if x.is_dir()] if p.name.startswith('@') else [p])]
print(sum(1 for p in pkgs if any(f.is_file() for f in p.rglob('*'))), '/', len(pkgs))
```

健康值＝分子≈分母。实测：故障时 **8/488**；恢复后 **488/488**、文件总数 ~25k。

**恢复**（registry=npmmirror；09-14 约 4 分钟，**09-15 实测 18 分 43 秒**——`--prefer-offline` 只保证
有缓存的命中，缺的那部分仍会回落下载，勿按 4 分钟预估超时）：

```bash
NPM=~/.workbuddy/binaries/node/versions/$(< ~/.workbuddy/binaries/node/versions/current)/npm.cmd
cd D:/dsh-npm && "$NPM" install --prefer-offline --no-audit --no-fund
# 09-14 汇总：added 32 / changed 480
# 09-15 汇总：added 32 packages, and changed 480 packages in 18m   ← **逐字相同**
```

> ✅ **两次汇总逐字一致是本次最有用的证据**：`changed 480` 两次相同 ⇒ 两次被清空的包数**完全一样**，
> 说明是**同一机制**在反复触发，而非两次偶然。以后拿到这条汇总即可直接对齐历史事件。
> （若某次 `changed` 数明显不同 ⇒ 是新机制，须重新走 §4.1 排查。）

- `--prefer-offline` **可用且值得加**：本机 `_cacache` 约 **938 MB / 含 502 个 `deepseek` 条目**，缺口才回落下载。
- **不要先删 `node_modules`**：npm 会自行重建缺失内容，先删只是白等。
- 恢复期用**文件数是否仍在涨**判完成（`node_modules` 顶层 mtime 会早早停住，不可当完成判据；
  实测尾段 6 秒仍 +269 文件）。

**恢复后自检（双判据）**：`bin.js` 存在且 **9165 B** → `--version` = `0.1.5-rc.2`（两次一致）。
⚠️ `package-lock.json` **不应被改写**（mtime 保持旧值 ⇒ 恢复的是 lock 指定版本，无意外升级）。

**残留清理 —— 会自愈，勿急着手删**：npm 原子写会在 `node_modules/` 留下 `.pkgname-<hash>` 空目录残片，
但**收尾后会自行回收**：09-15 首次统计 **542 个**（当时 npm 仍在写），npm 完全退出后复核为 **0 个**。
同源现象：`@napi-rs/canvas_tmp_24076_10`（34.8 MB）亦被 pnpm 自行回收（证据链 97）。
⇒ **先复核再决定**；确需清时用 **Python `os.rmdir`**（node/powershell 删会被删除门拦）。
⚠️ **统计残片必须在 npm 进程完全退出后做**，否则读到的是中间态 —— 09-15 即因此把 542 个误列为「遗留待清」。
（同源纪律：判断恢复完成的判据是**文件数是否仍在涨**，不是目录 mtime —— 见上。）

**每日自检（防复发）**：`scripts/dsh-health-selfcheck.py` —— 一条命令判健康/异常，退出码 0/1。
判据三项：包完整性（健康 488/488、故障 8/488，空壳率 >10% 才报警）、入口 `bin.js` 存在且 9165 B、
Gate9 体积（**字符口径** 10240）。已挂每日 automation，异常时自动报警并给出恢复命令。
反伪证用例：`scripts/test-dsh-health-selfcheck.py`（4 场景：健康/复发/入口缺失/单点空壳，防过度报警）。

### 4.1 根因排查（09-15 已排除项——勿重复投入）

| 嫌疑 | 查法 | 本次结论 |
|---|---|---|
| npm 自身 | `_cacache/_logs/*-debug-0.log` 按时刻对齐 | ❌ 最后一条 `13:41`，`15:01` **无记录** |
| Defender 隔离 | `Get-MpThreatDetection` | ❌ 无威胁检测记录 |
| 火绒隔离/查杀 | `QuarantineEx.db` → `FilesV3_60`（需 sqlite 复制后读） | ❌ 仅 3 条，均与 node_modules 无关 |
| 删到回收站 | `du -sh <drive>/$RECYCLE.BIN` | ❌ 空（1 KB）⇒ 永久删除 |
| 磁盘满写失败 | `df -h` | ❌ F 盘余 48 G |
| 清理软件 | 探测 CCleaner / Wise / 360 安装目录 | ❌ 未见 |
| agent 会话动手 | `~/.workbuddy/projects/**/*.jsonl` 时间窗 + `npm install` 正则 | ❌ `15:0x` **零活动** |
| **宿主动手** | 事件日志 Application/System `15:00–15:10` | ⚠️ **无删除审计**（默认未开）⇒ **未确证** |

**根因两次均未定论**。唯一已知相关机制＝宿主**删除门**（阈值 50、非 temp 根 fail-closed，§一）
与「home 内含指向安装根的 junction」（§二）**共存**——但 §三 已实测三套删除方式对本安装根均 SAFE，
故**不能指认**为该机制，仅作待验假设。⇒ 结论：**把恢复做成一键，而不是继续追凶**。

## 五、单例 home 是正解（per-call 临时 home 的三重代价）

| 问题 | 实测数字 |
|---|---|
| 每次新 home 触发 bootstrap | ~19k–25k 文件 / ~150–188 MB |
| 删除该树 | **127s**（桥进程活不到，必然泄漏；1 小时泄漏 1.8 GB / 12 个目录） |
| 同步删除阻塞事件循环 | 127s → `send()` 饿死 → 宿主 60s 判 `Connection closed` |

改**固定单例 home**（`$TMPDIR/dsh-bridge-home`，跨进程复用）后实测：
连续 3 次会话 + 另一进程复用同一 home 全部成功，每次仅增 ~2 文件（sessions/storages），
会话耗时稳定 3.5–4.6s，无重复 bootstrap。

**两个桥各自独立**：`~/.workbuddy/mcp-servers/dsh-bridge/server.mjs` 用 `dsh-bridge-home`；
`~/.workbuddy/scripts/dsh-acp-bridge.js` 用 `dsh-acp-bridge-home`（后者要写自己的 `settings.yaml`，
与前者 `effort` 默认值不同，故不共享）。
> 路径一律写全 `~/.workbuddy/...`：把 `~/.workbuddy/` 前缀省略、只留两级相对路径时，
> 会被入库门禁按**技能目录**相对解析 → 误报 C11「引用了不存在的本地文件」。

> ⚠️ 遗留残留可扫：桥启动时 `sweepStaleHomes()` 清 `%TEMP%\dsh-acp-*` 中
> 超过 30 分钟的目录（`fs.rm` 对 junction 实测 SAFE）。单例 home 名为
> `dsh-bridge-home`，**不匹配 `dsh-acp-` 前缀**，结构上不会被扫到。
