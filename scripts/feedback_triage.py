#!/usr/bin/env python3
"""
反馈汇总器 (Phase 3, ARM 上 cron 定时跑)
========================================
读 feedback.db 未处理反馈 → 调 headless claude 核实+三分类 → 写回 db →
生成 FEEDBACK_TRIAGE.md 并 push 到 GitHub (用户在 Windows git pull/网页看)。

- claude 在 dev copy (有代码/数据/记忆) 里跑, 只返回 JSON 判定 (git 操作由本脚本做, 可控)。
- MD 交付用独立干净 clone (triage-repo), 避开 dev copy 的 rsync 脏树 + 与本地 push 冲突。
- claude 环境 (ANTHROPIC_*) 从 ~/.paseo/config.json 读, 单一真源。

用法: python3 scripts/feedback_triage.py --once [--no-push] [--limit N]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

HOME = Path.home()
DEV_REPO = os.environ.get("ANTENNA_REPO", str(HOME / "projects" / "antenna-post-processor"))
DB_PATH = os.environ.get("FEEDBACK_DB", str(HOME / ".antenna_feedback" / "feedback.db"))
TRIAGE_REPO = str(HOME / ".antenna_feedback" / "triage-repo")
PROMPT_FILE = os.path.join(DEV_REPO, "scripts", "feedback_triage_prompt.md")
REPO_URL = "https://github.com/freezzb1972/antenna-post-processor.git"
MD_NAME = "FEEDBACK_TRIAGE.md"


def log(m: str):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {m}", flush=True)


def load_claude_env() -> dict:
    """从 paseo config 读 claude provider 的 ANTHROPIC_* 环境。"""
    try:
        cfg = json.loads((HOME / ".paseo" / "config.json").read_text())
        return dict(cfg["agents"]["providers"]["claude"]["env"])
    except Exception as e:
        log(f"⚠ 读 paseo claude env 失败: {e}")
        return {}


def get_new_feedback(limit: int) -> list[dict]:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            "SELECT id, ts, category, app_version, text, attachments "
            "FROM feedback WHERE status='new' ORDER BY received_ts ASC LIMIT ?",
            (limit,),
        ).fetchall()
    finally:
        con.close()
    items = []
    for r in rows:
        att = {}
        try:
            att = json.loads(r["attachments"] or "{}")
        except Exception:
            pass
        # 附件只给摘要 (不塞 base64 截图)
        att_summary = {k: (f"<{len(str(v))} chars>" if k == "screenshot" else v)
                       for k, v in att.items()}
        items.append({
            "id": r["id"], "ts": r["ts"], "category": r["category"],
            "app_version": r["app_version"], "text": r["text"],
            "attachments": att_summary,
        })
    return items


def sync_dev_repo() -> None:
    """把 dev copy 的已跟踪代码 reset 到 origin/master (gitignore 的 data/memory 不受影响),
    确保 claude 对最新代码核实, 而非 rsync 的旧代码。"""
    try:
        subprocess.run(["git", "-C", DEV_REPO, "fetch", "origin", "master"],
                       check=True, capture_output=True)
        subprocess.run(["git", "-C", DEV_REPO, "reset", "--hard", "origin/master"],
                       check=True, capture_output=True)
        log("dev copy 已同步到 origin/master")
    except Exception as e:
        log(f"⚠ dev copy 同步失败 (用现有代码继续): {e}")


def run_claude(prompt: str, env: dict, timeout: int = 1800) -> str:
    """headless claude, 返回其最终响应文本。"""
    cmd = ["claude", "-p", prompt, "--output-format", "json",
           "--dangerously-skip-permissions"]
    full_env = {**os.environ, **env}
    r = subprocess.run(cmd, cwd=DEV_REPO, env=full_env,
                       capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        log(f"⚠ claude 退出码 {r.returncode}; stderr: {r.stderr[:300]}")
    try:
        out = json.loads(r.stdout)
        return out.get("result", "") if isinstance(out, dict) else r.stdout
    except Exception:
        return r.stdout  # 非 JSON 包装时直接用


def extract_json_array(text: str) -> list:
    """从 claude 响应里抽取 JSON 数组 (容忍前后有解释文字)。"""
    m = re.search(r"\[.*\]", text, re.DOTALL)
    if not m:
        return []
    try:
        return json.loads(m.group(0))
    except Exception:
        return []


def save_triage(verdicts: list) -> int:
    con = sqlite3.connect(DB_PATH)
    n = 0
    try:
        for v in verdicts:
            fid = v.get("id")
            if not fid:
                continue
            cur = con.execute(
                "UPDATE feedback SET status='triaged', triage=? WHERE id=?",
                (json.dumps(v, ensure_ascii=False), fid),
            )
            n += cur.rowcount
        con.commit()
    finally:
        con.close()
    return n


def render_markdown() -> str:
    """从所有已 triaged 反馈生成汇总 MD (按 verdict 分组)。"""
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            "SELECT id, received_ts, category, app_version, text, triage "
            "FROM feedback WHERE status='triaged' ORDER BY received_ts DESC"
        ).fetchall()
    finally:
        con.close()

    buckets: dict[str, list] = {"real_bug": [], "duplicate": [], "feature": [], "invalid": []}
    for r in rows:
        try:
            t = json.loads(r["triage"] or "{}")
        except Exception:
            t = {}
        buckets.setdefault(t.get("verdict", "invalid"), []).append((r, t))

    titles = {"real_bug": "🐞 真 Bug", "feature": "💡 需求/建议",
              "duplicate": "🔁 重复/已知", "invalid": "⚪ 无效/信息不足"}
    lines = [f"# 反馈汇总 (自动生成)", "",
             f"更新: {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())} · "
             f"共 {len(rows)} 条已核实", ""]
    for key in ("real_bug", "feature", "duplicate", "invalid"):
        items = buckets.get(key, [])
        lines.append(f"## {titles[key]} ({len(items)})")
        if not items:
            lines.append("_（无）_")
        for r, t in items:
            sev = t.get("severity", "")
            lines.append(f"- **{r['text'][:80]}**  "
                         f"`{r['category']}` `{r['app_version']}` "
                         f"{'`'+sev+'`' if sev else ''}")
            if t.get("evidence"):
                lines.append(f"  - 核实: {t['evidence']}")
            if t.get("suggested_fix"):
                lines.append(f"  - 建议: {t['suggested_fix']}")
        lines.append("")
    return "\n".join(lines)


def push_markdown(md: str, no_push: bool) -> None:
    """写 MD 到独立干净 clone 并 push。"""
    tr = Path(TRIAGE_REPO)
    if not (tr / ".git").exists():
        log(f"clone triage-repo → {TRIAGE_REPO}")
        tr.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "clone", "--depth", "1", REPO_URL, TRIAGE_REPO], check=True)
    subprocess.run(["git", "-C", TRIAGE_REPO, "fetch", "origin", "master"], check=True)
    subprocess.run(["git", "-C", TRIAGE_REPO, "reset", "--hard", "origin/master"], check=True)
    (tr / MD_NAME).write_text(md, encoding="utf-8")
    diff = subprocess.run(["git", "-C", TRIAGE_REPO, "status", "--porcelain"],
                          capture_output=True, text=True).stdout.strip()
    if not diff:
        log("MD 无变化, 跳过提交")
        return
    subprocess.run(["git", "-C", TRIAGE_REPO, "add", MD_NAME], check=True)
    subprocess.run(["git", "-C", TRIAGE_REPO, "-c", "user.name=feedback-triage",
                    "-c", "user.email=triage@antenna.local", "commit", "-m",
                    f"chore(反馈): 自动汇总 {time.strftime('%Y-%m-%d', time.gmtime())}"],
                   check=True)
    if no_push:
        log("--no-push: 已提交未推送")
        return
    subprocess.run(["git", "-C", TRIAGE_REPO, "push", "origin", "HEAD:master"], check=True)
    log("✓ FEEDBACK_TRIAGE.md 已 push 到 GitHub")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--no-push", action="store_true")
    ap.add_argument("--limit", type=int, default=20)
    args = ap.parse_args()

    if not os.path.exists(DB_PATH):
        log(f"无反馈库 {DB_PATH}, 退出")
        return
    items = get_new_feedback(args.limit)
    if not items:
        log("无新反馈, 退出")
        return
    log(f"待核实 {len(items)} 条")

    sync_dev_repo()
    env = load_claude_env()
    prompt = Path(PROMPT_FILE).read_text(encoding="utf-8")
    prompt += "\n```json\n" + json.dumps(items, ensure_ascii=False, indent=2) + "\n```\n"

    text = run_claude(prompt, env)
    verdicts = extract_json_array(text)
    if not verdicts:
        log(f"⚠ claude 未返回有效 JSON 判定, 本轮不落库。响应前200: {text[:200]}")
        sys.exit(1)
    n = save_triage(verdicts)
    log(f"已写回 {n} 条 triage")

    md = render_markdown()
    push_markdown(md, args.no_push)
    log("完成")


if __name__ == "__main__":
    main()
