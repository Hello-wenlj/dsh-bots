# dsh-bots

把 WorkBuddy skill 打成 DSH（DeepSeek Harness）plugin bundle 的公开分发仓。
由 WorkBuddy 技能 `dsh-bundle-export` 生成，**运行时零第三方依赖**。

## 结构

```
docs/index.json                     自用插件清单（format 字段为本仓自定义，见「关于市场」）
bots/<slug>/
  package.json                      dsh.manifestVersion=1 + dsh.bundle.patch
  cordis.patch.yml                  声明式 patch：- insert: @deepseek-ai/dsh-agent-preset
  skills.mjs                        零依赖 ESM，ctx.skills.register()
  setup-prompt.md                   安装后建档用
  skills/<slug>/SKILL.md            技能本体
  skills/<slug>/references/         判据与深水文档（与 SKILL.md 同级，保持相对引用有效）
  skills/<slug>/scripts/            自检/辅助脚本
```

## 安装（手工，当前唯一可用路径）

```bash
# 1) 取仓库
git clone https://github.com/Hello-wenlj/dsh-bots.git
cd dsh-bots

# 2) 只取技能本体，拷进 DSH 的 skills 根
#    dshHome = %APPDATA%/dsh-desktop/harness （Windows；不是 ~/.dsh）
cp -r bots/dsh-rollback-recovery/skills/dsh-rollback-recovery \
      "$APPDATA/dsh-desktop/harness/skills/"

# 3) 重启 DSH Desktop
#    skills 根是 rank-400、watch:true（热加载），重启更稳
```

验证是否真的加载 —— 问一句只有该技能答得出的问题：

> 回滚 DSH 之前有没有自检脚本？叫什么，怎么跑？

答出 `dsh-health-selfcheck.py` / `dsh-desktop-selfcheck.py`、且说明 exit 0=健康 ⇒ 命中。
**问句里别带技能名**，否则无法区分「路由命中」和「复述你给的词」。

## 关于市场（为什么市场里搜不到）

**结论：本仓库目前进不了 dsh-market，只能手工装。这不是配置问题。**

实测（2026-10-18，从 `app.asar` 提取 market 安装器 + 读本机缓存）：

1. 市场消费的是**远程 discovery feed**，不是任意 index URL。其缓存
   `<dshHome>/profiles/<p>/.dsh-market/discovery-compatibility-v1.json` 的
   `schema = "dsh-market/discovery-compatibility-cache/v1"`，结构为
   `{schema, entries{npm包名: {checkedAt, facts}}}`（本机 740 条）。
2. 市场的 `state.json` 只有 `{disabled, groups, groupOrder, region, regionAuto}`，
   **没有任何自定义源字段** —— 没法把 `docs/index.json` 指给它。
3. 安装器 `market-install.mjs` 支持三种 distribution，这也说明「将来要进市场」需要什么：

| distribution.type | 需要什么 | 需要发布到 npm 吗 |
|---|---|---|
| `npm` | `name` + `version` + `integrity`（tgz 的 sha512） | 是 |
| `github-release` | Release 里 tgz 的 `url` + `sha256` | 否 |
| `github-source` | `url`（`https://github.com/<owner>/<repo>`）+ `commit`：安装器去 raw 取该 commit 的 `package.json`，再以 `github:<owner>/<repo>#<commit>` 安装 | 否 |

即：技术上**不必发 npm**（`github-source` 就够），卡点在于**条目必须出现在那个远程 feed 里**，
而 feed 的来源不由本机配置决定。

`docs/index.json` 是本仓库**自用清单**（记录 pin 与来源），`format` 是本仓自定义值，
不被市场读取 —— 不要当市场 feed 用。

### 公开目录 `awesome-dsh-workbench` 也进不了（品类不符，非结构问题）

`dataelement/awesome-dsh-workbench` 是公开投稿目录，容易误以为「整理好目录结构就能投」。
读其源码（2026-10-18，`scripts/probe-lib.mjs` + `catalog/README.md` + `schema/workbench.schema.json`）后确认**不收纯 skill bundle**：

1. **探测硬读根目录** —— `probeEntry()` 里是
   `fetchJsonFile(..., commit.sha, 'package.json')`，拼死路径
   `raw.githubusercontent.com/{owner}/{repo}/{sha}/package.json`。**即使填 `tarball`
   走 Release 分支，也先读根 `package.json` 过 `validatePackage()`**。本仓 bundle 在
   `bots/<slug>/`，根目录没有 `package.json`，第一步就 404。
2. **但它收的是「工作台」** —— `catalog/README.md`「包与宿主」原文：
   > 当前只支持仓库根目录的一个工作台，暂不支持 monorepo 子目录。

   且 `validatePackage()` 强制要求 `dsh.client.inject` 含 `dsh-desktop-workbenches`、
   存在 `exports["./client"]`。这是**带 UI 的客户端插件**契约 —— 会在 Desktop 里注册
   自己的前端面板。本仓是纯 skill bundle（`skills.mjs` + `cordis.patch.yml`），
   没有 client 入口，也没有 UI。
3. **分类枚举不覆盖** —— `category` 只有 7 个值：
   `development / productivity / content / data / research / operations / other`，无 skill 类。

所以这不是「差一张实拍截图」「改成根目录单包」能补的 —— 要进去得先把它变成带前端面板的
工作台，那是另一个产品形态。**技能类 bundle 目前没有官方市场入口，手工拷贝是唯一路径。**

## 供应链校验

`index.json` 里每个 version 的 `source.commit` 是 **40 位 commit pin**，不是分支名。
上游 force-push 或仓库失陷不会静默改掉安装内容。

```bash
git clone https://github.com/Hello-wenlj/dsh-bots.git
cd dsh-bots
PIN=$(python -c "import json;print(json.load(open('docs/index.json'))['plugins'][0]['versions'][0]['source']['commit'])")
git rev-parse "$PIN"                       # 必须存在
git ls-tree -r --name-only "$PIN" -- bots  # 该 commit 必须真含 bundle
```

## 依赖约定

插件运行时零第三方依赖：`package.json` **不含 `dependencies`**，
`skills.mjs` 只 import `node:fs` / `node:path` / `node:url`。
这条约定是为了绕开 Windows 上 pnpm 在依赖物化阶段对 junction 触发的 EPERM
——零依赖 bundle 不走那条路径。
