#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
dsh-desktop-selfcheck — DSH Desktop 启动一致性自检（复发预警）

定位：与 `dsh-health-selfcheck.py`（CLI 安装健康）互补，本脚本专检
**Desktop profile / harness 一致性**——即"启动修复框 / 每次开机必现告警"这类
静默可用性故障。全部判据来自 2026-09-21 实测，固化两个已知坑 + 两类残留。

覆盖项：
  ① claude-code 误报判定：patch 层报 `@deepseek-ai/dsh-hooks-claude-code not installed`
     实为 checker 只看 profile 层、看不见 app 层 in-box 包的认知盲区（非缺陷）。
  ② git-prepare 放行门（github: 简写绕开正则）：下一次冷重启若某个「需要 prepare 脚本」
     的 git 依赖 sha 未进 pnpm-workspace.yaml 的 allowBuilds，会在 profile maintenance
     阶段 ERR_PNPM_GIT_DEP_PREPARE_NOT_ALLOWED 复弹启动修复。
     —— 仅对「有 prepare 类脚本」的 git 依赖判定（纯 JS 包 pnpm 不拦，避免误报）。
  ③ 陈旧 / 孤儿墓碑：plugin-removals.json 中 status != removed（如 cleanup-pending）
     会每次开机 enforced N pending tombstone；磁盘目录无 JSON 记录 = 孤儿残留。
  ④ 卫星缺宿主（本次故障根因类）：任意「同伴插件」peerDependencies 宿主未安装且非
     optional ⇒ 运行时 waiting for service → 1 entry did not activate → 启动修复。
     —— 仅查 @deepseek-ai/ 框架命名空间之外的 peer（框架包运行时必提供，跳过以免误报）。

退出码：0=无 RISK/STALE/REAL 项（含已定性可忽略的误报）  1=存在需处理项
依赖：仅标准库。可用环境变量覆盖路径：
  DSH_HOME      默认 C:\Users\wenlj\AppData\Roaming\dsh-desktop\harness
  DSH_APP_ROOT  默认自动探测 F:\dsh_exe\DSH Desktop\resources\app 等
"""
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

# —— 路径发现（env 覆盖优先，其余按实测候选）——
DSH_HOME = Path(os.environ.get("DSH_HOME", r"C:\Users\wenlj\AppData\Roaming\dsh-desktop\harness"))

APP_CANDIDATES = [
    os.environ.get("DSH_APP_ROOT", ""),
    r"F:\dsh_exe\DSH Desktop\resources\app",
    r"C:\Program Files\DSH Desktop\resources\app",
    r"F:\DSH Desktop\resources\app",
]
APP_ROOT = None
for c in APP_CANDIDATES:
    if c and Path(c).exists():
        APP_ROOT = Path(c)
        break

PROFILE = DSH_HOME / "profiles" / "web"
GEN_LIVE = DSH_HOME / "profiles" / ".generations" / "live"
REMOVALS_JSON = DSH_HOME / "recovery" / "plugin-removals.json"
REMOVALS_DIR = DSH_HOME / "recovery" / "plugin-removals"
HOOKS_JSON = DSH_HOME / "hooks" / "hooks.json"
LOG = Path(os.environ.get("APPDATA", r"C:\Users\wenlj\AppData\Roaming")) / "dsh-desktop" / "logs" / "harness.log"

SHA_RE = re.compile(r"\b([0-9a-f]{40})\b")
# git 依赖在 lock 中的真实形态：version: https://codeload.github.com/<owner>/<repo>/tar.gz/<sha>
GIT_DEP_RE = re.compile(r"github\.com/([\w.\-]+)/([\w.\-]+)/tar\.gz/([0-9a-f]{40})")
# pnpm onlyBuiltDependencies 实际门控的「构建脚本」集合（触发 ERR_PNPM_GIT_DEP_PREPARE_NOT_ALLOWED 的脚本）。
# 注意：build / prepublishOnly 不在内（它们在发布/自定义阶段运行，非 pnpm 安装时的 git 构建门控）。
PREPARE_KEYS = ("preinstall", "install", "postinstall", "preprepare", "prepare", "postprepare")


def find_app_pkg(name):
    if not APP_ROOT:
        return None
    cand = [APP_ROOT / "node_modules" / name]
    if name.startswith("@"):
        scope, _, rest = name.partition("/")
        cand.append(APP_ROOT / "node_modules" / scope / rest)
    for p in cand:
        if p.exists():
            return p
    return None


def is_installed_in_profile(name):
    """同伴插件是否已装在 profile 可解析范围（顶层或 .pnpm 虚拟仓）。"""
    nm = PROFILE / "node_modules"
    if (nm / name).exists():
        return True
    if name.startswith("@"):
        scope, _, rest = name.partition("/")
        if (nm / scope / rest).exists():
            return True
    pnpm = nm / ".pnpm"
    if pnpm.exists():
        token = name.replace("/", "+")
        try:
            for d in pnpm.iterdir():
                if d.name.startswith(token + "@"):
                    return True
        except OSError:
            pass
    return False


def git_dep_has_prepare(name, sha):
    """该 git 依赖（按唯一 sha 定位）是否带 pnpm 门控的构建脚本。

    定位策略：① 顶层 node_modules/<name>（git 直接依赖装顶层）；② .pnpm 中目录名含
    该 sha 的嵌套包。用 sha 精确定位避免按 basename 误匹配同名传递依赖
    （反伪证：曾因 basename 碰撞对未实装依赖误报 4 条）。
    未在 node_modules 实装的 git 依赖（lock 有声明但未安装）返回 False，不计入风险。
    """
    nm = PROFILE / "node_modules"
    # ① 顶层直接依赖
    top_cands = [nm / name]
    if name.startswith("@"):
        scope, _, rest = name.partition("/")
        top_cands.append(nm / scope / rest)
    for c in top_cands:
        pkg = c / "package.json"
        if pkg.exists():
            try:
                data = json.loads(pkg.read_text("utf-8", errors="ignore"))
            except (OSError, ValueError):
                pass
            else:
                if any(k in (data.get("scripts") or {}) for k in PREPARE_KEYS):
                    return True
    # ② .pnpm 中按 sha 精确定位的嵌套 git 依赖
    pnpm = nm / ".pnpm"
    if pnpm.exists():
        try:
            for d in pnpm.iterdir():
                if sha not in d.name:
                    continue
                cand = d / "node_modules" / name
                if not cand.exists():
                    continue
                try:
                    data = json.loads(cand.read_text("utf-8", errors="ignore"))
                except (OSError, ValueError):
                    continue
                if any(k in (data.get("scripts") or {}) for k in PREPARE_KEYS):
                    return True
        except OSError:
            pass
    return False


def extract_git_deps_from_lock():
    """返回 [(owner_repo, sha)]，来自 pnpm-lock.yaml 的 github tar.gz 形态。"""
    lock = PROFILE / "pnpm-lock.yaml"
    if not lock.exists():
        return [], False
    text = lock.read_text("utf-8", errors="ignore")
    deps = []
    seen = set()
    for m in GIT_DEP_RE.finditer(text):
        owner_repo, repo, sha = m.group(1), m.group(2), m.group(3)
        key = (owner_repo, sha)
        if key in seen:
            continue
        seen.add(key)
        deps.append((owner_repo, repo, sha))
    return deps, True


def extract_allowbuild_shas():
    """从 pnpm-workspace.yaml 的 allowBuilds 块提取 sha 集合。"""
    ws = PROFILE / "pnpm-workspace.yaml"
    if not ws.exists():
        return set(), False
    lines = ws.read_text("utf-8", errors="ignore").splitlines()
    shas = set()
    in_block = False
    base_indent = None
    for ln in lines:
        if re.match(r"^\s*allowBuilds\s*:\s*$", ln):
            in_block = True
            base_indent = len(ln) - len(ln.lstrip())
            continue
        if in_block:
            if ln.strip() == "":
                continue
            indent = len(ln) - len(ln.lstrip())
            if base_indent is not None and indent < base_indent:
                in_block = False
                continue
            for m in SHA_RE.finditer(ln):
                shas.add(m.group(1))
    return shas, True


def scan_satellite_without_host():
    """扫描已装插件，找 @deepseek-ai/ 框架命名空间之外的 peer 宿主未安装（非 optional）。"""
    risks = []
    if not GEN_LIVE.exists():
        return risks
    try:
        pkgs = list(GEN_LIVE.rglob("package.json"))
    except OSError:
        return risks
    for pkg in pkgs:
        if "node_modules" not in str(pkg):
            continue
        try:
            data = json.loads(pkg.read_text("utf-8", errors="ignore"))
        except (OSError, ValueError):
            continue
        peers = data.get("peerDependencies") or {}
        meta = data.get("peerDependenciesMeta") or {}
        if not peers:
            continue
        for dep, _ in peers.items():
            # 框架命名空间内的 peer 由运行时保证，跳过（避免 13 条框架包误报）
            if dep.startswith("@deepseek-ai/"):
                continue
            opt = meta.get(dep, {}).get("optional", False)
            if is_installed_in_profile(dep):
                continue
            if opt:
                continue
            risks.append({
                "plugin": data.get("name", str(pkg.parent.name)),
                "missing_host": dep,
                "path": str(pkg.parent.relative_to(DSH_HOME)).replace("\\", "/"),
            })
    return risks


def read_removals():
    if not REMOVALS_JSON.exists():
        return None, False
    try:
        d = json.loads(REMOVALS_JSON.read_text("utf-8", errors="ignore"))
        return d.get("removals", {}), True
    except (OSError, ValueError):
        return None, True


def orphan_dirs(removals):
    if not REMOVALS_DIR.exists():
        return []
    orphans = []
    try:
        for d in REMOVALS_DIR.iterdir():
            if not d.is_dir() or d.name.startswith("."):
                continue
            if d.name not in removals:
                orphans.append(d.name)
    except OSError:
        pass
    return orphans


def recent_log_signals():
    """锚定最后一次 launch requested 之后，才是当前 boot 状态。"""
    out = {"claude_code_warn": False, "did_not_activate": 0, "enforced_tombstone": 0}
    if not LOG.exists():
        return out
    try:
        lines = LOG.read_text("utf-8", errors="ignore").splitlines()
    except OSError:
        return out
    # 找最后一次 launch requested
    last = -1
    for i, l in enumerate(lines):
        if "launch requested" in l:
            last = i
    tail = lines[last + 1:] if last >= 0 else lines[-400:]
    out["claude_code_warn"] = any("dsh-hooks-claude-code" in l and "not installed" in l for l in tail)
    out["did_not_activate"] = sum(1 for l in tail if "did not activate" in l)
    out["enforced_tombstone"] = sum(1 for l in tail if "enforced" in l and "tombstone" in l)
    return out


def main():
    now = datetime.now().isoformat(timespec="seconds")
    problems, warns, infos = [], [], []

    # —— ① claude-code 误报判定 ——
    cc_pkg = find_app_pkg("@deepseek-ai/dsh-hooks-claude-code")
    hooks_ok = HOOKS_JSON.exists()
    if cc_pkg and hooks_ok:
        rel = str(cc_pkg.relative_to(APP_ROOT)).replace("\\", "/") if APP_ROOT else str(cc_pkg)
        infos.append(
            "claude-code 误报：@deepseek-ai/dsh-hooks-claude-code 装在 app 内 (%s) 且 hooks.json 存在 ⇒ "
            "桥功能正常；'not installed' 告警是 inspectProfileConsistency() 只看 profile 层的认知盲区，非缺陷，可忽略" % rel
        )
    elif cc_pkg is None and hooks_ok:
        problems.append("claude-code 桥异常：hooks.json 存在但 app 内 @deepseek-ai/dsh-hooks-claude-code 缺失 ⇒ 桥可能断裂，需重装 app 或核查安装")
    elif not hooks_ok:
        warns.append("harness/hooks/hooks.json 缺失 ⇒ claude-code 桥配置不在，告警可能属实")

    # —— ② git-prepare 放行门（仅对有 prepare 脚本的 git 依赖判定）——
    git_deps, lock_ok = extract_git_deps_from_lock()
    allow_shas, ws_ok = extract_allowbuild_shas()
    if lock_ok and ws_ok:
        missing = []
        for owner_repo, repo, sha in git_deps:
            if sha in allow_shas:
                continue
            if git_dep_has_prepare(repo, sha):
                missing.append((owner_repo, sha))
        if missing:
            problems.append(
                "git-prepare 放行缺口：%d 个「需 prepare 的 git 依赖」sha 未进 allowBuilds ⇒ 下次冷启动 "
                "profile maintenance 会 ERR_PNPM_GIT_DEP_PREPARE_NOT_ALLOWED 复弹启动修复。缺失：%s"
                % (len(missing), ", ".join("%s@%s…" % (o, s[:8]) for o, s in missing[:6]))
            )
        else:
            infos.append("git-prepare 放行门对齐：%d 个 git 依赖（需 prepare 且已实装的均已在 allowBuilds）⇒ 下次冷重启不会被 git-prepare 卡住" % len(git_deps))
        infos.append(
            "已知坑：pnpm-runner.mjs 的 GIT_PREPARE_KEY_PATTERN 仅认 git+ssh 形态，对 github: 简写解析出的 git+https 匹配不上 ⇒ "
            "不会自动补 sha；须手动把新 sha 补进 allowBuilds"
        )
    else:
        infos.append("git-prepare 门跳过：pnpm-lock.yaml / pnpm-workspace.yaml 不可读（lock_ok=%s ws_ok=%s）" % (lock_ok, ws_ok))

    # —— ③ 陈旧 / 孤儿墓碑 ——
    removals, rj_ok = read_removals()
    if removals is not None:
        stale = [(k, v.get("pluginName"), v.get("status")) for k, v in removals.items()
                 if v.get("status") not in ("removed", None)]
        for k, name, st in stale:
            problems.append("陈旧墓碑：%s 状态=%s（非 removed）⇒ 每次开机 enforced pending tombstone。需停 Desktop 后清 plugin-removals.json 该记录" % (name, st))
        orph = orphan_dirs(removals)
        for o in orph:
            warns.append("孤儿备份目录：%s 在磁盘但无 JSON 记录（残留，可移入暂存区清理）" % o)
    else:
        infos.append("plugin-removals.json 不可读/不存在 ⇒ 跳过墓碑检查")

    # —— ④ 卫星缺宿主（仅同伴插件类）——
    sat = scan_satellite_without_host()
    for s in sat:
        problems.append("卫星缺宿主：%s 依赖宿主 %s 未安装（非 optional）⇒ 运行时 waiting for service → 启动修复。路径 %s"
                        % (s["plugin"], s["missing_host"], s["path"]))

    # —— 启动日志信号（锚定当前 boot）——
    sig = recent_log_signals()
    if sig["claude_code_warn"]:
        infos.append("harness.log 当前 boot 仍见 claude-code 'not installed' 告警（与 ① 一致，确认为误报）")
    if sig["did_not_activate"]:
        warns.append("harness.log 当前 boot 仍有 %d 处 'did not activate'（可能尚未冷重启清扫）" % sig["did_not_activate"])
    if sig["enforced_tombstone"]:
        warns.append("harness.log 当前 boot 仍有 %d 处 enforced tombstone（陈旧墓碑未清）" % sig["enforced_tombstone"])

    verdict = "ALERT" if problems else ("WARN" if warns else "HEALTHY")
    report = {
        "checked_at": now,
        "dsh_home": str(DSH_HOME),
        "app_root": str(APP_ROOT) if APP_ROOT else None,
        "verdict": verdict,
        "problems": problems,
        "warns": warns,
        "infos": infos,
        "git_deps_total": len(git_deps) if lock_ok else None,
        "allowbuild_shas_total": len(allow_shas) if ws_ok else None,
        "removals_records": len(removals) if removals is not None else None,
    }

    print(json.dumps(report, ensure_ascii=False, indent=2))
    print()
    if problems:
        print("⚠️ 需处理项（%d）：" % len(problems))
        for p in problems:
            print("  ✗ %s" % p)
    if warns:
        print("ⓘ 提示项（%d）：" % len(warns))
        for w in warns:
            print("  • %s" % w)
    if infos:
        print("✓ 信息项（%d）：" % len(infos))
        for i in infos:
            print("  - %s" % i)

    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
