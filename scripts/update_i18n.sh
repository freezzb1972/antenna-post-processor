#!/bin/bash
# 更新翻译文件 + 反查表
#   pyside6-lupdate  → 扫描 .py/.ui → 更新 .ts
#   pyside6-lrelease → .ts → .qm
#   build_i18n_table → .ts → i18n/trans_table.json (运行时语言切换的反查表)
#
# 用法: bash scripts/update_i18n.sh
#
# 改完 .ts 里的英文译文后必须重跑本脚本 —— .qm 与 trans_table.json 都是从
# .ts 派生的, 不重跑则界面与运行时切换都用不上新译文。
set -e
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"

# ── 工具链 ──────────────────────────────────────────────────────────
# 优先用 PATH 上的 pyside6-* (WSL 下在 ~/.local/bin); 否则回退 Windows Python
# (WSL 可直接 exec .exe)。旧版脚本硬编码 .venv/bin/... 而本 checkout 无 .venv。
if command -v pyside6-lupdate >/dev/null 2>&1; then
    LUPDATE=pyside6-lupdate
    LRELEASE=pyside6-lrelease
elif [ -x /mnt/d/Python312/Scripts/pyside6-lupdate.exe ]; then
    LUPDATE=/mnt/d/Python312/Scripts/pyside6-lupdate.exe
    LRELEASE=/mnt/d/Python312/Scripts/pyside6-lrelease.exe
else
    echo "错误: 找不到 pyside6-lupdate。请安装 PySide6 工具或改用 Windows Python。" >&2
    exit 1
fi

# ── 扫描清单 ────────────────────────────────────────────────────────
# ⚠️ 这份清单必须保持完整。旧版只列了 main.py + main_window.py + main_window.ui,
# 照它重跑会把其余文件从 .ts 中移除 —— 实测会丢掉约 61% 的译文条目。
SOURCES="main.py \
 ui/main_window.py ui/pages.py ui/dialogs.py ui/widgets.py \
 ui/template_recognizer.py ui/project_manager.py ui/multi_antenna_page.py \
 ui/feedback_dialog.py ui/shell_window.py ui/graph_viewer.py \
 ui/rsp_picker_dialog.py ui/splash_screen.py \
 ui/i18n_catalog.py \
 ui/designer/main_window.ui"

echo "1/4 扫描源文件 → .ts"
$LUPDATE $SOURCES -ts i18n/app_zh_CN.ts i18n/app_en_US.ts

echo "2/4 编译 .qm"
$LRELEASE i18n/app_zh_CN.ts -qm i18n/app_zh_CN.qm
$LRELEASE i18n/app_en_US.ts -qm i18n/app_en_US.qm

echo "3/4 生成运行时反查表"
python3 scripts/build_i18n_table.py

echo "4/4 漏包检查"
python3 scripts/check_i18n.py || true

echo
echo "完成。若上一步报出未包 tr() 的中文字面量, 请逐个判断:"
echo "  - UI 文案 → 用 self.tr(...) 包裹后重跑本脚本"
echo "  - 日志/正则/内部状态串 → 属正常, 可忽略"
