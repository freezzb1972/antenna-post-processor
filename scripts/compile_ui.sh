#!/bin/bash
# 编译 UI 文件
# pyside6-uic → .ui → .py
# pyside6-rcc → .qrc → .py

set -e
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"

echo "Compiling UI..."
.venv/bin/pyside6-uic ui/designer/main_window.ui -o ui/compiled/ui_main_window.py

echo "Done."
