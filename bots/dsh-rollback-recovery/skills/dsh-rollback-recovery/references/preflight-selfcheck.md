# dsh-rollback-recovery 下沉明细（二、执行前自检） —— 下沉明细

> 由 `SKILL.md` 下沉（Gate9 体积门禁 10240 字节）。**原文逐字保留**，
> 未做任何改写：本文件的内容是从 SKILL.md 的行区间原样搬过来的，
> 因此「信息零损失」是构造性的，不是声称的。判定口径/阈值/纪律仍以 SKILL.md 为准。

## 二、执行前自检 → 留三步与判据（原 SKILL.md L68–L84）

## 二、执行前自检

```bash
NODE=~/.workbuddy/binaries/node/versions/$(< ~/.workbuddy/binaries/node/versions/current)/node.exe
ls -l "F:/DSH-npm/node_modules/@deepseek-ai/dsh/lib/bin.js"   # ① 入口
"$NODE" "F:/DSH-npm/node_modules/@deepseek-ai/dsh/lib/bin.js" --version  # ② 能否起
ls -d ~/.workbuddy/binaries/node/versions/*/                  # ③ Node 目录实况
```

| 现象 | 层级 | 处理 |
|---|---|---|
| ① 缺 | 安装损坏 | 回第一节重装 |
| ① 在、② 报 `Cannot find module`（`@deepseek-ai/` 下包目录为空） | 依赖树残缺 / **安装内容被清空** | `cd F:/DSH-npm && npm install --prefer-offline`（**勿先删 node_modules**）<br>⚠️ **该故障已复发两次**（2026-09-14 / 09-15）⇒ 量化判据与 8 类取证排除见 `home-junction-and-shim.md` **§四 / §4.1** |
| ①② 正常、调用方仍失败 | **调用层路径失效** | 走第三节四处校准 |
| ③ 出现新 `22.22.2-*` | Node 版本漂移 | 改四处硬编码 + 跑第八节自检 |

**空壳率量化**（健康＝分子≈分母。实测：故障时 **8/488**，恢复后 **488/488**、文件总数 ~25k）：

```python
from pathlib import Path
root = Path('F:/DSH-npm/node_modules')
pkgs = [c for p in root.iterdir() if p.is_dir()
        for c in ([x for x in p.iterdir() if x.is_dir()] if p.name.startswith('@') else [p])]
print(sum(1 for p in pkgs if any(f.is_file() for f in p.rglob('*'))), '/', len(pkgs))
```

⚠️ 恢复期间**勿用 `node_modules` 顶层 mtime 判完成**（它会早早停住）；判据是**文件数是否仍在增长**。

> ⚠️ 版本号读法是 `--version`（双横），不是 `-version`（误用会触发兜底 agent 打印无关内容）。
