#!/usr/bin/env bash
# 同步 antenna-post-processor 项目 + Claude 工具链到 ARM 服务器
# 用途: 让 ARM 上的 paseo claude 具备与本地同等的 bug 核实能力 (读代码/跑测试/带记忆/复现数据)
# 用法: bash scripts/sync_to_arm.sh   (在本地 WSL 执行)
#
# 坑1: 记忆目录 key 由项目路径派生。ARM 端须用 ARM 项目路径派生的 key。
# 坑2: 项目 .claude/skills 是指向 ~/.claude/global-skills 的绝对软链，用 --copy-unsafe-links 落成实体。
# 坑3: 不用 eval(会二次解析拆断带空格的 --exclude), 直接调用 rsync。
set -euo pipefail

# ── 连接参数 (来自全局 CLAUDE.md) ──
ARM="ubuntu@138.2.77.171"
SSH_CMD="ssh -p 20100 -i $HOME/.ssh/id_ed25519"

# ── 路径 ──
LOCAL_PROJ="/mnt/d/cc/antenna-post-processor"
ARM_PROJ="/home/ubuntu/projects/antenna-post-processor"  # ARM 实测路径 (paseo cwd, 已确认)
LOCAL_MEM="$HOME/.claude/projects/-mnt-d-cc-antenna-post-processor/memory/"
ARM_MEM_KEY="$(echo "$ARM_PROJ" | sed 's#/#-#g')"        # → -home-ubuntu-projects-antenna-post-processor
ARM_MEM="\$HOME/.claude/projects/${ARM_MEM_KEY}/memory/"  # 远端 shell 展开 $HOME

echo "▶ 记忆将同步到 ARM: ~/.claude/projects/${ARM_MEM_KEY}/memory/"

# ── 1. 项目代码 (排除大数据/缓存/构建/.git/垃圾大目录; 跨树软链落成实体) ──
# .git 本地 19G(历史含大文件) 不传; backup version 229M / CTIA 43M 是垃圾, 排除。
# .claude/skills/ 排除: 它是项目按需加载的软链, 由 ARM 端独立维护 (软链→ARM global-skills),
#   若同步会被 --copy-unsafe-links 落成实体, 破坏"全局管理+项目软链"架构。
rsync -avzP --copy-unsafe-links -e "$SSH_CMD" \
  --exclude='.venv/' --exclude='venv/' --exclude='__pycache__/' --exclude='*.pyc' \
  --exclude='build/' --exclude='dist/' --exclude='.git/' --exclude='data/' --exclude='output/' \
  --exclude='backup version/' --exclude='CTIA Test plan/' --exclude='.playwright-mcp/' \
  --exclude='.claude/skills/' \
  --exclude='*.zip' --exclude='*.png' \
  "$LOCAL_PROJ/" "$ARM:$ARM_PROJ/"

# ── 2. 标准复现集 (仅这两个真实文件, data/ 其余不传) ──
rsync -avzP -e "$SSH_CMD" \
  "$LOCAL_PROJ/data/NO1_withoutAMP.csv" \
  "$LOCAL_PROJ/data/GNSS_report_template.xlsx" \
  "$ARM:$ARM_PROJ/data/"

# ── 3. 记忆文件 ──
ssh -p 20100 -i "$HOME/.ssh/id_ed25519" "$ARM" "mkdir -p ~/.claude/projects/${ARM_MEM_KEY}/memory/"
rsync -avzP -e "$SSH_CMD" "$LOCAL_MEM" "$ARM:.claude/projects/${ARM_MEM_KEY}/memory/"

# ── 4. 技能库 (全局集中管理 + 核心通用技能) ──
# global-skills 内有 20 个软链指向树外仓库 (~/everything-claude-code), 用 --copy-unsafe-links
#   只把这些"指向树外"的软链落成实体 (ARM 上已是实体, 内容更新), 保留树内软链。
# 核心 ~/.claude/skills 用相对软链 (browse->../global-skills/...), 默认 -avzP 原样保留即可。
rsync -avzP --copy-unsafe-links -e "$SSH_CMD" "$HOME/.claude/global-skills/" "$ARM:.claude/global-skills/"
rsync -avzP -e "$SSH_CMD" "$HOME/.claude/skills/"        "$ARM:.claude/skills/"

# ── 5. 插件 ──
rsync -avzP -e "$SSH_CMD" "$HOME/.claude/plugins/" "$ARM:.claude/plugins/"

echo "✅ 同步完成。ARM 上启动 paseo claude 时 cwd 用: $ARM_PROJ"
echo "   (这样记忆 key 才匹配 ${ARM_MEM_KEY})"
