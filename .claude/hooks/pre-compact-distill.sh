#!/usr/bin/env bash
# PreCompact hook: 压缩前自动保存会话状态
# 策略: 绝不覆盖手动 distill 的 CURRENT_STATE.md
#   - 若 CURRENT_STATE.md 在 10 分钟内被修改过 → 跳过 (保留手动 distill)
#   - 否则 → 写 .claude/auto-save-before-compact.md (不影响手动 distill)
#
# 两层防护:
#   1. 主输出文件: .claude/auto-save-before-compact.md (hook 专属, 始终覆盖)
#   2. CURRENT_STATE.md: 仅在不存在 或 超过 10 分钟未更新时写入 (保护手动 distill)

set -euo pipefail
cd "$(dirname "$0")/../.."

MANUAL_DISTILL="CURRENT_STATE.md"
AUTO_BACKUP=".claude/auto-save-before-compact.md"
NOW_EPOCH=$(date +%s)
NEW_COMMITS=$(git log --oneline -20 2>/dev/null || echo "")
LAST_COMMIT=$(git log -1 --format="%h %s" 2>/dev/null || echo "unknown")
BRANCH=$(git branch --show-current 2>/dev/null || echo "unknown")
FILES_CHANGED=$(git diff --name-only HEAD~5..HEAD 2>/dev/null | sort -u | head -20 || echo "")

# ── 判断 CURRENT_STATE.md 是否由手动 distill 生成 ──
SKIP_MANUAL_DISTILL=false
if [[ -f "$MANUAL_DISTILL" ]]; then
    M_TIME=$(stat -c %Y "$MANUAL_DISTILL" 2>/dev/null || echo 0)
    AGE_SEC=$(( NOW_EPOCH - M_TIME ))
    # 10分钟内有更新 → 很可能是手动 distill, 跳过覆盖
    if [[ $AGE_SEC -lt 600 ]]; then
        SKIP_MANUAL_DISTILL=true
    fi
fi

# ── 始终写入专属备份文件 ──
cat > "$AUTO_BACKUP" << EOF
# SESSION BACKUP — $(date '+%Y-%m-%d %H:%M') (PreCompact hook)

**Branch:** $BRANCH
**Last commit:** $LAST_COMMIT

## Recent commits

$NEW_COMMITS

## Recently changed files

$FILES_CHANGED

> 此文件由 PreCompact hook 自动生成，作为会话恢复的最低保障。
> 详细 distill 见 CURRENT_STATE.md（如有手动 distill）。
EOF

echo "✅ $AUTO_BACKUP written (PreCompact safety net)"

# ── 只在安全时更新 CURRENT_STATE.md ──
if $SKIP_MANUAL_DISTILL; then
    echo "⏭️  CURRENT_STATE.md 跳过 (最近已更新, 保留手动 distill)"
else
    if [[ -f "$MANUAL_DISTILL" ]]; then
        echo "📝 CURRENT_STATE.md 超过 10 分钟未更新, 更新为基础备份"
    else
        echo "📝 CURRENT_STATE.md 不存在, 创建基础备份"
    fi
    cat > "$MANUAL_DISTILL" << EOF
# CURRENT STATE — $(date '+%Y-%m-%d %H:%M') (auto-saved by PreCompact hook)

**Branch:** $BRANCH
**Last commit:** $LAST_COMMIT

## Recent commits

$NEW_COMMITS

## Recently changed files

$FILES_CHANGED

> ⚠️ 此文件由 PreCompact hook 自动生成。如有需要，下个会话应手动 distill。
EOF
fi

exit 0
