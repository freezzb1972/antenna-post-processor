#!/usr/bin/env python3
"""静态分析门禁 — 分层检查 (ruff safety + ruff quality + mypy)

用法:
    python3 static_analysis_gate.py              # 三层完整检查
    python3 static_analysis_gate.py --quick      # 仅 safety (F821 未定义名)
    python3 static_analysis_gate.py --json       # CI JSON 输出

分层设计:
    Phase 1 - SAFETY GATE:  ruff --select F821   (未定义名称 → 必过)
    Phase 2 - QUALITY WARN: ruff --select F      (所有 pyflakes → 建议过)
    Phase 3 - TYPE INFO:    mypy                  (类型检查 → 参考)
"""

import subprocess
import sys
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TARGETS = ["src/", "tests/", "main.py"]


def _run(cmd: list, description: str) -> tuple:
    """运行命令，返回 (exit_code, stdout, stderr)。"""
    try:
        result = subprocess.run(
            cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=120
        )
        return result.returncode, result.stdout, result.stderr
    except FileNotFoundError:
        return -1, "", f"{description}: 工具未安装 ({cmd[0]})"
    except subprocess.TimeoutExpired:
        return -1, "", f"{description}: 超时 (120s)"


def _count_lines(text: str) -> int:
    """计算非空行数。"""
    return sum(1 for line in text.strip().split("\n") if line.strip())


def check_ruff_safety() -> dict:
    """Phase 1: 仅 F821 (undefined name) — 真正的 bug。"""
    exit_code, stdout, stderr = _run(
        ["ruff", "check", "--select", "F821", "--output-format", "concise"] + TARGETS,
        "ruff (F821 safety)"
    )
    n = _count_lines(stdout)
    return {
        "phase": 1,
        "level": "GATE",
        "tool": "ruff:F821",
        "passed": exit_code == 0,
        "exit_code": exit_code,
        "issue_count": n,
        "issues": stdout.strip() if n > 0 else "",
    }


def check_ruff_quality() -> dict:
    """Phase 2: 所有 pyflakes 规则 (F) — 代码质量。"""
    exit_code, stdout, stderr = _run(
        ["ruff", "check", "--select", "F", "--output-format", "concise"] + TARGETS,
        "ruff (F: all pyflakes)"
    )
    n = _count_lines(stdout)
    return {
        "phase": 2,
        "level": "WARN",
        "tool": "ruff:F",
        "passed": exit_code == 0,
        "exit_code": exit_code,
        "issue_count": n,
        "issues": stdout.strip() if n > 0 else "",
    }


def check_mypy() -> dict:
    """Phase 3: mypy 类型检查 — 信息参考。"""
    exit_code, stdout, stderr = _run(
        ["mypy", "--no-error-summary"] + TARGETS,
        "mypy"
    )
    n = _count_lines(stdout)
    return {
        "phase": 3,
        "level": "INFO",
        "tool": "mypy",
        "passed": exit_code == 0,
        "exit_code": exit_code,
        "issue_count": n,
        "issues": stdout.strip() if n > 0 else "",
    }


def main():
    json_mode = "--json" in sys.argv
    quick_mode = "--quick" in sys.argv

    results = []

    # Phase 1: SAFETY GATE (always)
    r1 = check_ruff_safety()
    results.append(r1)
    if not json_mode:
        status = "✅" if r1["passed"] else "❌"
        print(f"F821 safety: {status} ({r1['issue_count']} undefined names)")

    if quick_mode:
        if json_mode:
            print(json.dumps({"gate": "static-analysis", "passed": r1["passed"],
                              "results": [r1]}, indent=2, ensure_ascii=False))
        else:
            print("✅ PASS" if r1["passed"] else f"❌ FAIL ({r1['issue_count']} issues)")
        sys.exit(0 if r1["passed"] else 1)

    # Phase 2: QUALITY (unless quick)
    r2 = check_ruff_quality()
    results.append(r2)
    if not json_mode:
        status = "✅" if r2["passed"] else "⚠"
        print(f"ruff F:      {status} ({r2['issue_count']} pyflakes issues)")

    # Phase 3: TYPE INFO
    r3 = check_mypy()
    results.append(r3)
    if not json_mode:
        status = "✅" if r3["passed"] else "ℹ"
        print(f"mypy:        {status} ({r3['issue_count']} type issues)")

    # Gate decision: Phase 1 MUST pass; Phase 2+3 are advisory
    gate_pass = r1["passed"]
    total_issues = sum(r["issue_count"] for r in results)

    if json_mode:
        output = {
            "gate": "static-analysis",
            "passed": gate_pass,
            "total_issues": total_issues,
            "results": results,
        }
        print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        print()
        if gate_pass:
            print("══════════════════════════════════")
            print(" Static Analysis: ✅ GATE PASSED")
            if not r2["passed"]:
                print(f" ({r2['issue_count']} quality issues — advisory)")
            print("══════════════════════════════════")
        else:
            print("══════════════════════════════════")
            print(f" Static Analysis: ❌ {r1['issue_count']} UNDEFINED NAMES")
            print("══════════════════════════════════")
            if r1["issues"]:
                print(r1["issues"])

    sys.exit(0 if gate_pass else 1)


if __name__ == "__main__":
    main()
