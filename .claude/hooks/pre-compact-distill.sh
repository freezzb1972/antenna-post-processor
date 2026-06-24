#!/usr/bin/env bash
# PreCompact hook: 智能阻塞 — 无近期 distill 则阻止压缩，触发 Claude 自动 distill
#
# 流程:
#   1. 始终写 .claude/auto-save-before-compact.md (最低保障)
#   2. 检查 CURRENT_STATE.md 是否在 10 分钟内更新过
#      - 是 → exit 0 (有近期 distill, 安全压缩)
#      - 否 → exit 2 (阻止压缩, Claude 应自动运行 /distill-session)
#
# Claude 行为 (CLAUDE.md 规则):
#   当看到 "被 PreCompact hook 阻止" 消息时, 自动运行 /distill-session,
#   下次压缩触发时 CURRENT_STATE.md 已刷新, 自动放行。

set -euo pipefail
cd "$(dirname "$0")/../.."

MANUAL_DISTILL="CURRENT_STATE.md"
AUTO_BACKUP=".claude/auto-save-before-compact.md"
NOW_EPOCH=$(date +%s)
NEW_COMMITS=$(git log --oneline -20 2>/dev/null || echo "")
LAST_COMMIT=$(git log -1 --format="%h %s" 2>/dev/null || echo "unknown")
BRANCH=$(git branch --show-current 2>/dev/null || echo "unknown")
FILES_CHANGED=$(git diff --name-only HEAD~5..HEAD 2>/dev/null | sort -u | head -20 || echo "")

# ── 始终写兜底备份 ──
cat > "$AUTO_BACKUP" << EOF
# SESSION BACKUP — $(date '+%Y-%m-%d %H:%M') (PreCompact hook safety net)

**Branch:** $BRANCH
**Last commit:** $LAST_COMMIT

## Recent commits

$NEW_COMMITS

## Recently changed files

$FILES_CHANGED

> 此文件由 PreCompact hook 自动生成。详细 distill 见 CURRENT_STATE.md。
EOF

# ── 判断是否需要阻止压缩 ──
NEED_DISTILL=false
if [[ -f "$MANUAL_DISTILL" ]]; then
    M_TIME=$(stat -c %Y "$MANUAL_DISTILL" 2>/dev/null || echo 0)
    AGE_SEC=$(( NOW_EPOCH - M_TIME ))
    if [[ $AGE_SEC -ge 600 ]]; then
        NEED_DISTILL=true
    fi
else
    NEED_DISTILL=true  # 文件不存在, 需要首次 distill
fi

if $NEED_DISTILL; then
    cat << EOF
╔══════════════════════════════════════════════════════════════╗
║ ⛔ 压缩被 PreCompact hook 阻止                              ║
╠══════════════════════════════════════════════════════════════╣
║ CURRENT_STATE.md 超过 10 分钟未更新, 需要先 distill。       ║
║                                                            ║
║ Claude 将自动运行 /distill-session 保存会话状态,           ║
║ 下次压缩触发时会自动放行。                                  ║
║                                                            ║
║ 兜底备份已保存至: $AUTO_BACKUP
╚══════════════════════════════════════════════════════════════╝
EOF
    exit 2
fi

echo "✅ CURRENT_STATE.md 近期已更新, 压缩放行"
exit 0
