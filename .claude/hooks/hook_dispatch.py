#!/usr/bin/env python3
"""Claude Code hook 统一分发器。

为什么需要它
────────────
项目原有 hooks 有两处硬故障（2026-09-16 审核发现，均经 A/B 实测确认）：

1. **matcher 用了表达式写法**（`tool == "Edit" || tool == "Write"`）。
   Claude Code 的 matcher 只支持「精确字符串」或「`|`/`,` 分隔的列表」；
   含 `=`/`"`/`(` 的值会落到**正则**分支，编译成匹配字面量
   `tool == "Edit"` 的正则 —— 没有任何工具名长这样，于是**静默永不触发**。
   正确写法：`"Edit|Write"`。
   （参数级过滤本可用 `if: "Write(**/*.py)"`，但一个 handler 只能带一条
   `if` 规则，无法同时覆盖 Edit 与 Write，故过滤逻辑放在本脚本内。）

2. **`$CLAUDE_CODE_FILE_PATH` 并不存在**（该环境变量从未在文档中出现）。
   hook 的输入走 **stdin 的 JSON**：
     {"tool_name": "Write", "tool_input": {"file_path": "..."}, ...}
   Bash 事件则是 tool_input.command。

用法
────
    hook_dispatch.py <action>

action 一览见 ACTIONS。stdin 无有效 JSON 时静默退出 0（不干扰会话）。
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys

HOOKS_DIR = os.path.dirname(os.path.abspath(__file__))        # <root>/.claude/hooks
PROJECT_DIR = os.path.dirname(os.path.dirname(HOOKS_DIR))     # <root>
# 注意要 dirname 两次: 只算一次会得到 .claude, 于是 dev-flow.json /
# FUNC_CATALOG.md / targeted_verify.py 全部指向不存在的路径而静默失败。


# ── 输入解析 ────────────────────────────────────────────────────────

def read_event() -> dict:
    """从 stdin 读事件 JSON。失败返回空 dict（宁可静默，也不要报错打断会话）。"""
    try:
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    except Exception:
        return {}


def tool_file(ev: dict) -> str:
    """Edit/Write 事件的文件路径。"""
    ti = ev.get("tool_input") or {}
    return ti.get("file_path") or ""


def tool_command(ev: dict) -> str:
    """Bash 事件的命令字符串。"""
    ti = ev.get("tool_input") or {}
    return ti.get("command") or ""


def _norm(p: str) -> str:
    """统一分隔符，便于跨平台匹配目录片段。"""
    return p.replace("\\", "/")


def is_py(ev: dict) -> bool:
    return _norm(tool_file(ev)).endswith(".py")


def under(ev: dict, seg: str) -> bool:
    """.py 且位于指定目录段下。seg 形如 'src' / 'ui'。"""
    p = _norm(tool_file(ev))
    return p.endswith(".py") and f"/{seg}/" in p


# ── 工具 ────────────────────────────────────────────────────────────

def dev_flow_path() -> str:
    return os.path.join(PROJECT_DIR, ".claude", "dev-flow.json")


def bump_dev_flow(key: str, delta: int = 1) -> None:
    """更新 dev-flow.json 的统计计数（文件缺失或损坏时静默跳过）。"""
    p = dev_flow_path()
    try:
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        stats = d.setdefault("stats", {})
        stats[key] = stats.get(key, 0) + delta
        with open(p, "w", encoding="utf-8") as f:
            json.dump(d, f, indent=2, ensure_ascii=False)
    except Exception:
        return


def run(cmd: list[str], quiet: bool = True) -> str:
    """跑子进程并返回 stdout；任何异常都吞掉（hook 不该打断会话）。"""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120,
                           cwd=PROJECT_DIR)
        return r.stdout or ""
    except Exception:
        return "" if quiet else "(执行失败)"


# ── actions ─────────────────────────────────────────────────────────

def act_dev_flow(ev: dict) -> None:
    """修改 .py 文件 → dev-flow 计数，≥5 次提醒跑 /dev-flow check。"""
    if not is_py(ev):
        return
    bump_dev_flow("filesModified")
    try:
        with open(dev_flow_path(), encoding="utf-8") as f:
            c = json.load(f).get("stats", {}).get("filesModified", 0)
    except Exception:
        return
    msg = f"📊 文件修改 {c} 次"
    if c >= 5:
        msg += " — 建议运行 /dev-flow check"
    print(msg)


def act_func_catalog(ev: dict) -> None:
    """新增 src/ 函数前，提醒查 FUNC_CATALOG.md 避免重复造轮子。"""
    if not under(ev, "src"):
        return
    stem = os.path.basename(tool_file(ev))[:-3]          # 去掉 .py
    print(f"📋 修改 src/{stem}.py — 新增函数前先查 FUNC_CATALOG.md:")
    out = run(["grep", "-i", stem, "FUNC_CATALOG.md"])
    print(out.strip() if out.strip() else
          "  (未命中；若确需新函数，先确认没有 ≥80% 相似的已有实现)")


def act_ui_reminder(ev: dict) -> None:
    """修改 ui/ 文件 → 提醒跑 GUI 门禁 + 列出应跑的针对性测试。"""
    if not under(ev, "ui"):
        return
    print("🔔 UI 文件已修改 — 记得运行: python3 gui_integrity_check.py")
    out = run([sys.executable, "targeted_verify.py", "--dry-run"])
    if out.strip():
        print("\n".join(out.strip().splitlines()[:15]))


def act_interface_audit(ev: dict) -> None:
    """写 .py 后，检查接口变更是否遗漏消费方。"""
    if not is_py(ev):
        return
    fp = tool_file(ev)
    out = run([sys.executable, os.path.join(HOOKS_DIR, "interface-audit.py"), fp])
    if out.strip():
        print(out.strip())
    else:
        print("🔍 接口审计无告警")


def act_interface_audit_staged(ev: dict) -> None:
    """git commit **之前**审计暂存区接口变更。

    注意: 本 action 必须挂在 **PreToolUse**。原先挂在 PostToolUse，
    commit 已经完成，`--staged` 此时看不到任何内容 —— 与它的说明
    「每次 git commit 前」自相矛盾。
    """
    if "git commit" not in tool_command(ev):
        return
    out = run([sys.executable, os.path.join(HOOKS_DIR, "interface-audit.py"),
               "--staged"])
    if out.strip():
        print(out.strip())


def act_post_commit(ev: dict) -> None:
    """commit 之后的收尾: 清 __pycache__ + 重建 FUNC_CATALOG。"""
    if "git commit" not in tool_command(ev):
        return
    for root, dirs, files in os.walk(PROJECT_DIR):
        if any(s in root for s in (".venv", "venv", ".git", "build", "dist")):
            continue
        if os.path.basename(root) == "__pycache__":
            subprocess.run(["rm", "-rf", root], capture_output=True)
        for fn in files:
            if fn.endswith(".pyc"):
                try:
                    os.remove(os.path.join(root, fn))
                except OSError:
                    pass
    run([sys.executable, "generate_func_catalog.py"])
    out = run([sys.executable, "targeted_verify.py"])
    if out.strip():
        print("\n".join(out.strip().splitlines()[:20]))
    print("✅ commit 后处理完成 (清缓存 + 重建 FUNC_CATALOG + 针对性验证)")


def act_pytest_count(ev: dict) -> None:
    """pytest 运行后更新统计。"""
    cmd = tool_command(ev)
    if "pytest" not in cmd:
        return
    bump_dev_flow("testsRun")


def act_gui_audit(ev: dict) -> None:
    """修改 ui/ 后跑 GUI 审计（audit.py 不存在时提示走 SKILL.md 清单）。"""
    if not under(ev, "ui"):
        return
    script = os.path.join(PROJECT_DIR, ".claude", "skills", "gui-audit", "audit.py")
    if not os.path.exists(script):
        print("gui-audit: 无 audit.py — 请按 .claude/skills/gui-audit/SKILL.md 清单人工核对")
        return
    out = run([sys.executable, script])
    if out.strip():
        print("\n".join(out.strip().splitlines()[:10]))


ACTIONS = {
    "dev-flow": act_dev_flow,
    "func-catalog": act_func_catalog,
    "ui-reminder": act_ui_reminder,
    "interface-audit": act_interface_audit,
    "interface-audit-staged": act_interface_audit_staged,
    "post-commit": act_post_commit,
    "pytest-count": act_pytest_count,
    "gui-audit": act_gui_audit,
}


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in ACTIONS:
        print(f"用法: {os.path.basename(__file__)} <{'|'.join(ACTIONS)}>",
              file=sys.stderr)
        return 0                      # 不返回非 0，避免误判为阻断
    ACTIONS[sys.argv[1]](read_event())
    return 0


if __name__ == "__main__":
    sys.exit(main())
