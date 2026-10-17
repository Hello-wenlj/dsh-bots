# dsh-bots

DSH (DeepSeek Harness) 自定义插件市场仓库。由 WorkBuddy 技能
`dsh-bundle-export` 从 `~/.workbuddy/skills/<skill>/SKILL.md` 导出生成。

## 结构

```
docs/index.json          ← 唯一 catalog（真相源），安装端只读这一个 URL
bots/<slug>/             ← 插件 bundle
  package.json           dsh.manifestVersion=1, bundle.patch 指向 cordis.patch.yml
  cordis.patch.yml       声明式 patch：插入 @deepseek-ai/dsh-agent-preset
  skills.mjs             注册 skills/<slug>/SKILL.md，仅用 node: 内置模块
  setup-prompt.md        安装后建档用
  skills/<slug>/SKILL.md
  skills/<slug>/references/   ← 与 SKILL.md 同级，保持相对引用有效
```

## 供应链校验

`index.json` 里每个 version 的 `source.commit` 是 **40 位 commit pin**，
不是分支名——上游 force-push 或仓库失陷不会静默改掉安装内容。

安装前可自行复核：

```bash
git clone https://github.com/Hello-wenlj/dsh-bots.git
cd dsh-bots
PIN=$(python -c "import json;print(json.load(open('docs/index.json'))['plugins'][0]['versions'][0]['source']['commit'])")
git rev-parse "$PIN"                       # 必须存在
git ls-tree -r --name-only "$PIN" -- bots  # 该 commit 必须真含 bundle
```

## 在 DSH Desktop 中安装

走 Discover tab（不经 pnpm，避开 Windows junction EPERM）：

Plugins → Experimental plugins 旁的 **More** → **Custom plugin markets**
→ 添加本仓库 `docs/index.json` 的 raw URL。

不要走 CLI 的 `npx @deepseek-ai/dsh plugin add`，那条路径需要 pnpm。

## 依赖约定

插件运行时零第三方依赖：`package.json` **不含 `dependencies`**，
`skills.mjs` 只 import `node:fs` / `node:path` / `node:url`。
需要依赖的插件应显式 opt-in 并走独立沙箱。
