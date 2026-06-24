#!/usr/bin/env bash
# PreCompact hook: 压缩前自动保存会话状态到 CURRENT_STATE.md
# 如果 Claude 已手动 distill 过，只更新 commit 信息；否则生成完整备份

set -euo pipefail
cd "$(dirname "$0")/../.."

STATE_FILE="CURRENT_STATE.md"
NEW_COMMITS=$(git log --oneline -20 2>/dev/null || echo "")
LAST_COMMIT=$(git log -1 --format="%h %s" 2>/dev/null || echo "unknown")
BRANCH=$(git branch --show-current 2>/dev/null || echo "unknown")
FILES_CHANGED=$(git diff --name-only HEAD~5..HEAD 2>/dev/null | sort -u | head -20 || echo "")

cat > "$STATE_FILE" << EOF
# CURRENT STATE — $(date '+%Y-%m-%d %H:%M') (auto-saved by PreCompact hook)

**Branch:** $BRANCH
**Last commit:** $LAST_COMMIT

## Recent commits

$NEW_COMMITS

## Recently changed files

$FILES_CHANGED

> ⚠️ 此文件由 PreCompact hook 自动生成。如有需要，下个会话应手动 distill。
EOF

echo "✅ CURRENT_STATE.md auto-saved before compaction"
exit 0
