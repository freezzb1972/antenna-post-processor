#!/bin/bash
# 更新翻译文件
# pyside6-lupdate → 扫描 .py 和 .ui → 生成 .ts
# pyside6-lrelease → .ts → .qm

set -e
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"

echo "Updating translations..."
.venv/bin/pyside6-lupdate main.py ui/main_window.py ui/designer/main_window.ui -ts i18n/app_zh_CN.ts i18n/app_en_US.ts 2>&1 || true

echo "Compiling translations..."
.venv/bin/pyside6-lrelease i18n/app_zh_CN.ts -qm i18n/app_zh_CN.qm 2>&1 || true
.venv/bin/pyside6-lrelease i18n/app_en_US.ts -qm i18n/app_en_US.qm 2>&1 || true

echo "Done."
