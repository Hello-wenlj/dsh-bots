#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test-dsh-health-selfcheck — dsh-health-selfcheck.py 的反伪证用例

为什么需要：一个「恒定返回健康」或「恒定返回故障」的监控脚本毫无价值。
本测试造 3 个合成场景，验证判据**能区分**健康与故障。

场景（全部为合成目录，不触碰真实安装）：
  A 健康     488 包全有文件 + 入口在位            → 期望 HEALTHY / exit 0
  B 复发     488 包全空壳 + 入口在位              → 期望 ALERT   / exit 1
  C 入口缺失 488 包全有文件、入口不在             → 期望 ALERT   / exit 1
  D 单点空壳 488 包全有文件，仅 1 个空壳          → 期望 HEALTHY / exit 0  ← 防过度报警

用法：python test-dsh-health-selfcheck.py     退出码 0=全过
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT = Path(__file__).with_name("dsh-health-selfcheck.py")
PY = sys.executable
VALID_PKGS = 488


def build(root: Path, alive: int, empty: int, with_bin: bool):
    (root / "@deepseek-ai/dsh/lib").mkdir(parents=True, exist_ok=True)
    if with_bin:
        (root / "@deepseek-ai/dsh/lib/bin.js").write_bytes(b"x" * 9165)
    for i in range(alive):
        d = root / f"pkg{i}"
        d.mkdir(parents=True, exist_ok=True)
        (d / "index.js").write_text("//")
    for i in range(empty):
        (root / f"empty{i}").mkdir(parents=True, exist_ok=True)


def run(root: Path):
    env = dict(os.environ)
    env["DSH_ROOT"] = str(root)
    env["DSH_SKILLS_DIR"] = str(Path(tempfile.gettempdir()) / "_no_skills_under_test")
    r = subprocess.run([PY, str(SCRIPT)], capture_output=True, text=True, env=env, timeout=300)
    try:
        j = json.loads(r.stdout[: r.stdout.rindex("}") + 1])
    except (ValueError, json.JSONDecodeError):
        j = None
    return r.returncode, j


CASES = [
    ("A 健康（488 包有文件 + 入口）", 488, 0, True, "HEALTHY", 0),
    ("B 复发（488 包全空壳 + 入口）", 0, 488, True, "ALERT", 1),
    ("C 入口缺失", 488, 0, False, "ALERT", 1),
    ("D 单点空壳（1/488，不应报警）", 488, 1, True, "HEALTHY", 0),
]


def main():
    tmp = Path(tempfile.mkdtemp(prefix="dsh-selfcheck-test-"))
    all_ok = True
    print(f"用例根目录: {tmp}\n")
    for label, alive, empt, wb, want_v, want_rc in CASES:
        root = tmp / label.split()[0]
        build(root, alive, empt, wb)
        rc, j = run(root)
        got = j["verdict"] if j else "?"
        ok = got == want_v and rc == want_rc
        all_ok &= ok
        print(f"{'PASS' if ok else 'FAIL'}  {label}")
        print(f"      期望 {want_v}/exit={want_rc}   实际 {got}/exit={rc}")
        if j:
            for p in j.get("problems", [])[:2]:
                print(f"        ! {p[:110]}")
            for n in j.get("notes", [])[:2]:
                print(f"        · {n[:110]}")
        print()

    print("总结论:", "全部通过 —— 判据能区分健康/故障，且不过度报警" if all_ok else "存在判定错误")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
