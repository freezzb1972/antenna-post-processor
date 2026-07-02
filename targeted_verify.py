#!/usr/bin/env python3
"""针对性验证 — git diff → 受影响控件 → 最少测试集

原理:
  1. git diff --name-only 获取变更文件
  2. 对 ui/ 文件: 解析 diff 提取改动的 widget 名称 → 查映射
  3. 对 src/ 文件: 直接查模块映射
  4. 合并去重 → 只运行必要的测试

用法:
  python3 targeted_verify.py              # 自动检测改动
  python3 targeted_verify.py --all        # 强制全量
  python3 targeted_verify.py --dry-run    # 只打印会跑哪些测试
"""

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MAP_PATH = ROOT / ".claude" / "verify-map.json"


def load_map() -> dict:
    if MAP_PATH.exists():
        return json.loads(MAP_PATH.read_text())
    return {}


def get_changed_files(scope: str = "working") -> list:
    """获取变更文件列表。
    scope: "working" = 未暂存改动 (日常开发)
           "HEAD"    = 最新一次 commit 的改动 (commit 后验证)
           "both"    = 合并两者
    """
    files = set()
    if scope in ("working", "both"):
        r = subprocess.run(["git", "diff", "--name-only"], capture_output=True, text=True, cwd=ROOT)
        if r.returncode == 0:
            files.update(f.strip() for f in r.stdout.split("\n") if f.strip())
    if scope in ("HEAD", "both"):
        r = subprocess.run(["git", "diff", "--name-only", "HEAD~1"], capture_output=True, text=True, cwd=ROOT)
        if r.returncode == 0:
            files.update(f.strip() for f in r.stdout.split("\n") if f.strip())
    return sorted(files)


def get_changed_widgets(ui_file: str) -> set:
    """从 ui 文件的 git diff 中提取改动的 widget/函数名。"""
    widgets = set()
    r = subprocess.run(
        ["git", "diff", "--", ui_file], capture_output=True, text=True, cwd=ROOT
    )
    if r.returncode != 0:
        return widgets

    diff = r.stdout
    # 查找新增/修改行中的 widget 名:
    #   self.ui.btnXxx / self._btn_xxx / window.ui.spinXxx
    #   def _on_xxx / class XxxDialog / QPushButton("text")
    for pattern in [
        r'self\.ui\.(\w+)',           # self.ui.btnStart
        r'self\._(\w+)',               # self._btn_add_files
        r'window\.ui\.(\w+)',          # window.ui.editTemplatePath
        r'def (_on_\w+|\w+dialog)',    # def _on_start, def _show_xxx_dialog
        r'class (\w+Dialog)',          # class SystemSettingsDialog
    ]:
        for m in re.finditer(pattern, diff, re.IGNORECASE):
            widgets.add(m.group(1))

    return widgets


def find_tests_for_changes(changed_files: list, verify_map: dict) -> set:
    """根据变更文件查找应运行的测试。"""
    tests = set()
    ui_widgets = verify_map.get("ui_widgets", {})
    src_modules = verify_map.get("src_modules", {})
    ui_files_map = verify_map.get("ui_files", {})

    for f in changed_files:
        # 只处理 Python 源文件
        if not f.endswith(".py"):
            continue
        base = Path(f).name

        # src/ 模块
        if f.startswith("src/") and base in src_modules:
            for t in src_modules[base]:
                # 标准化路径: test_xxx.py → tests/test_xxx.py
                if not t.startswith("tests/"):
                    t = f"tests/{t}"
                tests.add(t)

        # ui/ 文件 → 提取改动的 widget 名
        if f.startswith("ui/"):
            # 先加整个文件的映射 (兜底)
            if base in ui_files_map:
                for t in ui_files_map[base]:
                    tests.add(t)

            # 再精确匹配 widget 名
            changed_widgets = get_changed_widgets(f)
            for w in changed_widgets:
                if w in ui_widgets:
                    for t in ui_widgets[w]:
                        tests.add(t)
                # 前缀匹配 (如 btnQuick60 → btnQuick)
                for prefix in ["btnQuick", "btnBrowse", "btnLoad", "btnSave",
                               "_btn_", "edit", "spin", "tab"]:
                    if w.startswith(prefix) and not any(
                        w in ui_widgets for w in [w]
                    ):
                        for uw_name, uw_tests in ui_widgets.items():
                            if uw_name.startswith(prefix[:6]):
                                for t in uw_tests:
                                    tests.add(t)

        # tests/ 自身改了 → 直接跑该文件
        if f.startswith("tests/") and f.endswith(".py"):
            tests.add(f)

    return tests


def main():
    dry_run = "--dry-run" in sys.argv
    force_all = "--all" in sys.argv

    verify_map = load_map()

    if force_all:
        changed_files = ["ALL"]
        test_set = set()
        for mapping in verify_map.get("ui_files", {}).values():
            test_set.update(mapping)
        for mapping in verify_map.get("src_modules", {}).values():
            test_set.update(mapping)
    else:
        changed_files = get_changed_files(scope="working")
        if not changed_files:
            print("✅ No changes detected — nothing to verify")
            return

        test_set = find_tests_for_changes(changed_files, verify_map)

    if not test_set:
        print(f"Changed files: {changed_files}")
        print("⚠ No matching tests found — running full gui-smoke + gui-health")
        test_set = {"tests/test_gui_smoke.py", "tests/test_gui_health.py"}

    # 展开通配符
    final_tests = []
    for t in sorted(test_set):
        if t.endswith("*"):
            # 运行整个文件
            final_tests.append(t.replace("::*", ""))
        else:
            final_tests.append(t)

    # 去重合并: 同文件多个 test 合并为 -k 过滤
    # 先标准化所有路径为 tests/xxx.py 格式
    normalized = set()
    for t in final_tests:
        if "/" not in t and not t.startswith("tests/"):
            t = f"tests/{t}"
        normalized.add(t)

    file_groups = {}
    standalone = []
    for t in sorted(normalized):
        if "::" in t:
            file_part, test_part = t.split("::", 1)
            file_groups.setdefault(file_part, []).append(test_part)
        else:
            standalone.append(t)

    cmds = []
    for f, tests in file_groups.items():
        k_filter = " or ".join(t.replace("[", r"\[").replace("]", r"\]") for t in tests)
        cmds.append(f"python3 -m pytest {f} -q -k \"{k_filter}\"")

    for f in standalone:
        cmds.append(f"python3 -m pytest {f} -q")

    # 输出
    if dry_run:
        print(f"Changed files ({len(changed_files)}):")
        for f in changed_files:
            print(f"  {f}")
        print(f"\nWould run ({len(cmds)} commands):")
        for cmd in cmds:
            print(f"  {cmd}")
    else:
        print(f"Changed files: {changed_files}")
        print(f"Targeted tests: {len(cmds)} groups")
        for cmd in cmds:
            print(f"  $ {cmd}")
            r = subprocess.run(cmd, shell=True, cwd=ROOT)
            if r.returncode != 0:
                sys.exit(r.returncode)

    print("✅ Targeted verification complete")


if __name__ == "__main__":
    main()
