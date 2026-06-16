#!/usr/bin/env python3
"""
打包体积门禁 (Harness S1-S5)
=============================
PyInstaller 构建后自动运行，检查 EXE 体积、污染包、spec 完整性。

用法:
    python3 build_size_gate.py                    # 检查最新构建
    python3 build_size_gate.py --baseline         # 更新基线
    python3 build_size_gate.py --spec-only        # 仅检查 spec 文件
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent
BASELINE_FILE = PROJECT_ROOT / ".build_baseline.json"

# ── 配置 ────────────────────────────────────────────────────────────────

# 体积上限 (MB)
SIZE_LIMITS = {
    "Windows": 80,
    "Linux": 110,
}

# 体积趋势告警阈值 (%)
SIZE_TREND_WARN = 10

# 禁止出现在构建产物中的包名
FORBIDDEN_PACKAGES = [
    "pandas", "sqlalchemy", "pydantic", "pydantic_core",
    "torch", "tensorflow", "chromadb", "openai", "huggingface",
    "tokenizers", "transformers", "tqdm", "rich",
    "scipy", "numba", "numexpr", "pyarrow",
    "google", "grpc", "dotenv",
]

# spec 文件中必须保留的最小 excludes 数量
MIN_EXCLUDES = 30

# spec 文件中 hiddenimports 不应超过的数量
MAX_HIDDENIMPORTS = 10

# 必须包含的关键模块
REQUIRED_MODULES = [
    "PySide6.QtCore", "PySide6.QtGui", "PySide6.QtWidgets",
    "matplotlib", "numpy", "openpyxl",
]


# ── 检查函数 ────────────────────────────────────────────────────────────

def get_exe_info() -> Optional[Tuple[Path, float, str]]:
    """查找构建产物，返回 (路径, 大小MB, 平台)。"""
    dist = PROJECT_ROOT / "dist"
    if not dist.exists():
        return None

    # 优先找 Windows .exe
    for name in ["AntennaPostProcessor.exe", "AntennaPostProcessor"]:
        exe = dist / name
        if exe.exists() and exe.is_file():
            size_mb = exe.stat().st_size / (1024 * 1024)
            platform = "Windows" if name.endswith(".exe") else "Linux"
            return exe, size_mb, platform
    return None


def check_s1_size_limit(size_mb: float, platform: str) -> List[str]:
    """S1: 体积上限检查。"""
    limit = SIZE_LIMITS.get(platform, 100)
    if size_mb > limit:
        return [f"SIZE: {size_mb:.0f}MB > {limit}MB limit for {platform}"]
    return []


def check_s2_trend(size_mb: float) -> List[str]:
    """S2: 体积趋势检查。"""
    if BASELINE_FILE.exists():
        baseline = json.loads(BASELINE_FILE.read_text())
        prev = baseline.get("size_mb", size_mb)
        if prev > 0:
            pct = (size_mb - prev) / prev * 100
            if pct > SIZE_TREND_WARN:
                return [f"TREND: {size_mb:.0f}MB is {pct:.0f}% larger than baseline {prev:.0f}MB"]
    return []


def check_s3_forbidden_packages() -> List[str]:
    """S3: 污染包扫描 — 检查 build 目录的 TOC。"""
    build_dir = PROJECT_ROOT / "build"
    if not build_dir.exists():
        return ["BUILD: no build directory found"]

    # 找 Analysis TOC 文件
    toc_files = list(build_dir.glob("**/Analysis-00.toc"))
    if not toc_files:
        return ["BUILD: no Analysis-00.toc found"]

    content = toc_files[0].read_text(encoding="utf-8", errors="ignore")
    found = []
    for pkg in FORBIDDEN_PACKAGES:
        if pkg in content:
            # 计算出现次数
            count = content.count(pkg)
            if count > 5:  # 忽略少量引用（如注释中的）
                found.append(f"{pkg} ({count} occurrences)")
    if found:
        return [f"FORBIDDEN: {', '.join(found)}"]
    return []


def check_s4_spec_integrity() -> List[str]:
    """S4: Spec 文件完整性。"""
    spec_path = PROJECT_ROOT / "antenna_post_processor.spec"
    if not spec_path.exists():
        return ["SPEC: antenna_post_processor.spec not found"]

    src = spec_path.read_text(encoding="utf-8")
    errors = []

    # 统计 excludes 数量
    exclude_count = len([l for l in src.split("\n") if l.strip().startswith("'") and l.strip().endswith("',")])
    if exclude_count < MIN_EXCLUDES:
        errors.append(f"SPEC: only {exclude_count} excludes (min {MIN_EXCLUDES})")

    # 统计 hiddenimports 数量
    hi_count = len([l for l in src.split("\n") if l.strip().startswith("'") and "hiddenimports" not in l])
    # 粗略统计：在 hiddenimports 列表中的条目
    in_hi = False
    hi_items = 0
    for l in src.split("\n"):
        ls = l.strip()
        if "hiddenimports=[" in ls:
            in_hi = True
        elif in_hi and ls == "],":
            in_hi = False
        elif in_hi and ls.startswith("'") and ls.endswith("',"):
            hi_items += 1
    if hi_items > MAX_HIDDENIMPORTS:
        errors.append(f"SPEC: {hi_items} hiddenimports (max recommended {MAX_HIDDENIMPORTS})")

    # 检查必需的排除项
    required_excludes = [
        "PySide6.QtWebEngine", "PySide6.QtQml", "PySide6.QtQuick",
        "matplotlib.backends.backend_qt", "matplotlib.backends.backend_tkagg",
    ]
    for rex in required_excludes:
        if rex not in src:
            errors.append(f"SPEC: missing exclude '{rex}'")

    # 检查无 collect_data_files('qt_material')
    if "collect_data_files('qt_material')" in src:
        errors.append("SPEC: collect_data_files('qt_material') should not be used")

    # 检查必需的 hiddenimports
    for mod in REQUIRED_MODULES:
        found = False
        for l in src.split("\n"):
            if mod in l and l.strip().startswith("'"):
                found = True
                break
        if not found:
            errors.append(f"SPEC: missing hiddenimport '{mod}'")

    return errors


def check_s5_required_modules() -> List[str]:
    """S5: 验证必需模块在 TOC 中。"""
    build_dir = PROJECT_ROOT / "build"
    toc_files = list(build_dir.glob("**/Analysis-00.toc")) if build_dir.exists() else []
    if not toc_files:
        return ["BUILD: no Analysis-00.toc found"]

    content = toc_files[0].read_text(encoding="utf-8", errors="ignore")
    missing = [mod for mod in REQUIRED_MODULES if mod not in content]
    if missing:
        return [f"MISSING_MODULES: {', '.join(missing)}"]
    return []


# ── 主入口 ──────────────────────────────────────────────────────────────

def run_all(spec_only: bool = False) -> Tuple[bool, dict]:
    results = {}
    all_pass = True

    # S4 和 S5 不需要构建产物
    for phase_id, name, func in [
        ("S4", "Spec 完整性", check_s4_spec_integrity),
    ]:
        errs = func()
        results[phase_id] = {"name": name, "errors": errs, "passed": len(errs) == 0}
        if errs:
            all_pass = False

    if spec_only:
        return all_pass, results

    # 需要构建产物的阶段
    exe_info = get_exe_info()
    if exe_info is None:
        results["BUILD"] = {"name": "构建产物", "errors": ["No EXE found in dist/"], "passed": False}
        return False, results

    exe_path, size_mb, platform = exe_info
    results["EXE"] = {"name": f"构建产物 ({platform})", "errors": [], "passed": True,
                       "size_mb": round(size_mb, 1), "platform": platform}

    for phase_id, name, func in [
        ("S1", f"体积上限 ({platform})", lambda: check_s1_size_limit(size_mb, platform)),
        ("S2", "体积趋势", lambda: check_s2_trend(size_mb)),
        ("S3", "污染包扫描", check_s3_forbidden_packages),
        ("S5", "必需模块", check_s5_required_modules),
    ]:
        errs = func()
        results[phase_id] = {"name": name, "errors": errs, "passed": len(errs) == 0}
        if errs:
            all_pass = False

    return all_pass, results


def save_baseline() -> None:
    """保存当前 EXE 体积为基线。"""
    info = get_exe_info()
    if info is None:
        print("ERROR: no EXE found to baseline")
        return
    _, size_mb, platform = info
    BASELINE_FILE.write_text(json.dumps({
        "size_mb": round(size_mb, 1),
        "platform": platform,
    }, indent=2))
    print(f"Baseline saved: {size_mb:.1f}MB ({platform})")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="打包体积门禁")
    parser.add_argument("--baseline", action="store_true", help="更新体积基线")
    parser.add_argument("--spec-only", action="store_true", help="仅检查 spec 文件")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    args = parser.parse_args()

    if args.baseline:
        save_baseline()
        return 0

    passed, results = run_all(spec_only=args.spec_only)

    if args.json:
        print(json.dumps({"passed": passed, "phases": results}, ensure_ascii=False, indent=2))
    else:
        for pid, r in results.items():
            icon = "✅" if r["passed"] else "❌"
            extra = ""
            if "size_mb" in r:
                extra = f" ({r['size_mb']}MB)"
            print(f"  {icon} {pid} {r['name']}{extra}: ", end="")
            if r["passed"]:
                print("PASSED")
            else:
                print(f"FAILED ({len(r['errors'])} issues)")
                for e in r["errors"]:
                    print(f"     └─ {e}")
        print()
        if passed:
            print("✅ 体积门禁通过")
        else:
            print("❌ 体积门禁失败 — 请在提交前修复上述问题")

    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
