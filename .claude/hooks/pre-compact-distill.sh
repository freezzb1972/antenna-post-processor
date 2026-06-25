#!/usr/bin/env bash
# PreCompact hook: ticket 模型 — distill 创建通行证, compact 消费它
#
# 流程:
#   1. 始终写兜底备份 (.claude/auto-save-before-compact.md)
#   2. 检查 .claude/.distill-done 是否存在
#      - 存在 → rm 消费掉, exit 0 (放行 compact)
#      - 不存在 → exit 2 (阻止 — 自上次 compact 后没有 distill)
#
# Ticket 生命周期:
#   /distill-session → touch .claude/.distill-done (发通行证)
#   PreCompact hook  → rm .claude/.distill-done  (消费通行证, 放行)
#   下次 PreCompact  → 无通行证 → 阻止 → Claude auto-distill → 发新通行证 → 放行
#
# 兜底: 如果 .distill-done 和 CURRENT_STATE.md 都不存在 (新项目首次),
#       自动创建 .distill-done 放行 (无需 distill 空会话).

set -euo pipefail
cd "$(dirname "$0")/../.."

DISTILL_DONE=".claude/.distill-done"
AUTO_BACKUP=".claude/auto-save-before-compact.md"

# ── 始终写兜底备份 ──
{
    BRANCH=$(git branch --show-current 2>/dev/null || echo "unknown")
    LAST_COMMIT=$(git log -1 --format="%h %s" 2>/dev/null || echo "unknown")
    cat << EOF
# SESSION BACKUP — $(date '+%Y-%m-%d %H:%M') (PreCompact hook safety net)

**Branch:** $BRANCH
**Last commit:** $LAST_COMMIT

## Recent commits

$(git log --oneline -20 2>/dev/null || echo "none")

## Recently changed files

$(git diff --name-only HEAD~5..HEAD 2>/dev/null | sort -u | head -20 || echo "none")

> 此文件由 PreCompact hook 自动生成。完整 distill 见 CURRENT_STATE.md。
EOF
} > "$AUTO_BACKUP"

# ── Ticket 检查 ──
if [[ -f "$DISTILL_DONE" ]]; then
    rm -f "$DISTILL_DONE"
    echo "✅ distill 通行证已消费, 压缩放行"
    exit 0
fi

# 兜底: 新项目首次运行 (无 CURRENT_STATE.md 也无 ticket)
# 自动放行 — 空会话没什么可 distill 的
if [[ ! -f "CURRENT_STATE.md" ]]; then
    echo "🆕 新项目首次 compact, 自动放行 (无需预 distill)"
    exit 0
fi

cat << EOF
╔══════════════════════════════════════════════════════════════╗
║ ⛔ 压缩被 PreCompact hook 阻止                              ║
╠══════════════════════════════════════════════════════════════╣
║ 原因: 自上次 compact 后没有运行 /distill-session           ║
║                                                            ║
║ Claude 将自动运行 /distill-session 保存会话状态,           ║
║ distill 完成后 touch .claude/.distill-done 发通行证,       ║
║ 下次 compact 触发时自动消费放行。                           ║
║                                                            ║
║ 兜底备份已保存至: $AUTO_BACKUP
╚══════════════════════════════════════════════════════════════╝
EOF
exit 2
