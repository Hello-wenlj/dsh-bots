#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dsh-health-selfcheck — DSH 安装健康自检（复发监控）

用途：把「安装内容被清空」这类静默故障从「等人发现」变成「每日自动报警」。
     该故障 2026-09-14 / 09-15 各复发一次，根因未定论，故取监控而非追凶。

判据（全部本机实测标定，勿凭记忆改）：
  1. 包完整性：node_modules 下包目录含文件数。故障 8/488 ↔ 健康 488/488。
  2. 入口在位：@deepseek-ai/dsh/lib/bin.js 存在且 9165 B（两次一致）。
  3. 文件总数：健康 ~25k（25473）。
  4. Gate9 体积：单位 = **字符**（gate9_grade.py 口径），阈值 10240。
     ⚠️ 勿用字节数判定 —— gate9_size_scan.py 的字节线是「预警非判定」。

退出码：0=健康  1=异常（供 automation 判读）
"""
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# 允许环境变量覆盖安装根（供反伪证测试与异位置复用；默认本机口径）
# 2026-09-24 修正：安装根 2026-09-22 已由 F:\DSH-npm 迁至 D:\dsh-npm（见 SKILL.md §16.5）。
#   旧默认 F: 在 09-22 / 09-23 / 09-24 三次产生「安装根不存在」假阳性 ALERT，
#   故将默认改为当前真实根；异位置复用仍可用 DSH_ROOT 覆盖。
ROOT = Path(os.environ.get("DSH_ROOT", "D:/dsh-npm/node_modules"))
BIN = ROOT / "@deepseek-ai/dsh/lib/bin.js"
SKILLS = Path(os.environ.get("DSH_SKILLS_DIR", "")) if os.environ.get("DSH_SKILLS_DIR") \
    else Path(os.path.expanduser("~")) / ".workbuddy" / "skills"

# —— 实测标定基线（2026-09-15）——
BASELINE = {
    "pkg_total": 488,          # 包目录总数
    "pkg_with_files": 488,     # 健康判定线：空壳率为 0
    "files_total": 25473,
    "bin_bytes": 9165,
    "npm_changed": 480,        # 复发时 npm install 汇总的 changed 数（两次逐字相同）
}
GATE9_THRESHOLD = 10240        # 单位 = 字符，权威口径


def count_pkgs():
    """返回 (总包数, 含文件包数, 空壳路径列表)。"""
    if not ROOT.exists():
        return -1, -1, []
    total, alive, empties = 0, 0, []
    for p in ROOT.iterdir():
        if not p.is_dir():
            continue
        subs = []
        if p.name.startswith("@"):
            try:
                subs = [c for c in p.iterdir() if c.is_dir()]
            except OSError:
                subs = []
        elif not p.name.startswith("."):
            subs = [p]
        for c in subs:
            total += 1
            try:
                has_file = any(f.is_file() for f in c.rglob("*"))
            except OSError:
                has_file = False
            if has_file:
                alive += 1
            else:
                empties.append(str(c.relative_to(ROOT)).replace("\\", "/"))
    return total, alive, empties


def count_files():
    if not ROOT.exists():
        return -1
    try:
        return sum(1 for p in ROOT.rglob("*") if p.is_file())
    except OSError:
        return -1


def scan_gate9():
    """权威口径：字符数。返回 [(skill, chars, over_bool)]，只报超限的。"""
    over = []
    if not SKILLS.exists():
        return over
    for f in SKILLS.rglob("SKILL.md"):
        if any(part.startswith(".") or part == "node_modules" for part in f.parts):
            continue
        try:
            chars = len(f.read_text("utf-8"))
        except (OSError, UnicodeDecodeError):
            continue
        if chars > GATE9_THRESHOLD:
            over.append((str(f.parent.relative_to(SKILLS)).replace("\\", "/"), chars, chars - GATE9_THRESHOLD))
    return sorted(over, key=lambda x: -x[1])


def main():
    now = datetime.now().isoformat(timespec="seconds")
    total, alive, empties = count_pkgs()
    files = count_files()
    bin_ok = BIN.exists()
    bin_bytes = BIN.stat().st_size if bin_ok else 0
    gate9_over = scan_gate9()

    problems = []
    notes = []
    SHELL_RATE_ALERT = 0.10     # 空壳率阈值：真实复发为 480/488≈98%；单点空壳不报警

    if total == -1:
        problems.append(f"安装根不存在：{ROOT}")
    else:
        shell_rate = len(empties) / total if total else 0
        if shell_rate > SHELL_RATE_ALERT:
            problems.append(
                f"包完整性异常：{alive}/{total} 含文件，空壳 {len(empties)} 个（{shell_rate:.0%}）"
                f"——健康应为 {BASELINE['pkg_with_files']}/{BASELINE['pkg_total']}（空壳 0）"
                f" → 疑似「安装内容被清空」复发；恢复：cd {ROOT.parent.as_posix()} && npm install --prefer-offline --no-audit --no-fund"
                f"（勿先删 node_modules；核对 npm 汇总 changed 是否仍为 {BASELINE['npm_changed']}）"
            )
        elif len(empties):
            notes.append(f"存在 {len(empties)} 个空壳目录（未达 {SHELL_RATE_ALERT:.0%} 阈值，不报警）")
        if not bin_ok:
            problems.append(f"入口缺失：{BIN}")
        elif bin_bytes != BASELINE["bin_bytes"]:
            notes.append(f"入口体积 {bin_bytes} B ≠ 基线 {BASELINE['bin_bytes']} B → 多为版本变化，非故障")
        # 文件总数**不作警报项**：它绑定绝对基线、尺度相关（反伪证测试证明会误报），
        # 且「被清空」已被空壳率判据覆盖 ⇒ 仅作信息项。
        if files != -1 and files < BASELINE["files_total"]:
            notes.append(f"文件总数 {files} < 基线 {BASELINE['files_total']}（仅供参考）")

    for name, chars, over in gate9_over:
        problems.append(f"Gate9 超限（字符口径）：{name} {chars}/{GATE9_THRESHOLD}，超 {over}")

    report = {
        "checked_at": now,
        "root": str(ROOT),
        "pkg_total": total,
        "pkg_with_files": alive,
        "empty_shells": len(empties),
        "empty_sample": empties[:8],
        "files_total": files,
        "bin_exists": bin_ok,
        "bin_bytes": bin_bytes,
        "gate9_over": [{"skill": n, "chars": c, "over": o} for n, c, o in gate9_over],
        "baseline": BASELINE,
        "verdict": "ALERT" if problems else "HEALTHY",
        "problems": problems,
        "notes": notes,
    }

    print(json.dumps(report, ensure_ascii=False, indent=2))
    if problems:
        print("\n⚠️ 异常项：")
        for p in problems:
            print(f"  - {p}")
        return 1
    print(f"\n✅ 健康：包 {alive}/{total}，文件 {files}，入口 {bin_bytes} B，Gate9 无超限")
    return 0


if __name__ == "__main__":
    sys.exit(main())
