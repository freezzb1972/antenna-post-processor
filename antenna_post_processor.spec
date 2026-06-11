# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller 打包配置
====================
构建单文件 Windows .exe:
    pyinstaller antenna_post_processor.spec

构建单目录调试版:
    pyinstaller --onedir antenna_post_processor.spec
"""

import sys
from pathlib import Path

from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_submodules,
)

block_cipher = None

PROJECT_ROOT = Path(__file__).resolve().parent

a = Analysis(
    ['main.py'],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=[
        # i18n 翻译文件
        (str(PROJECT_ROOT / 'i18n' / 'app_zh_CN.qm'), 'i18n'),
        (str(PROJECT_ROOT / 'i18n' / 'app_en_US.qm'), 'i18n'),
        # 配置文件
        (str(PROJECT_ROOT / 'config' / 'bands.json'), 'config'),
        # 模板文件（可选，打包后也可以在运行时选择外部模板）
        (str(PROJECT_ROOT / 'data' / '20260601乐来_SVW 5G1.xlsx'), 'templates'),
    ],
    hiddenimports=[
        # PySide6
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
        # matplotlib backends
        'matplotlib.backends.backend_agg',
        'matplotlib.backends.backend_svg',
        # numpy
        'numpy.core._methods',
        'numpy.lib.format',
        # openpyxl
        'openpyxl.cell._writer',
    ] + collect_submodules('PySide6'),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 排除不使用的 PySide6 模块以减小体积
        'PySide6.QtWebEngine',
        'PySide6.QtWebEngineCore',
        'PySide6.QtWebEngineWidgets',
        'PySide6.QtWebChannel',
        'PySide6.QtNetwork',
        'PySide6.QtBluetooth',
        'PySide6.QtNfc',
        'PySide6.QtMultimedia',
        'PySide6.QtMultimediaWidgets',
        'PySide6.QtPositioning',
        'PySide6.QtLocation',
        'PySide6.QtSensors',
        'PySide6.QtSerialPort',
        'PySide6.QtSql',
        'PySide6.QtTest',
        'PySide6.QtXml',
        'PySide6.QtHelp',
        # 排除不需要的 matplotlib backends
        'matplotlib.backends.backend_qt',
        'matplotlib.backends.backend_tkagg',
        'matplotlib.backends.backend_wxagg',
        'matplotlib.backends.backend_gtk3agg',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='AntennaPostProcessor',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # --windowed（无控制台窗口）
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(PROJECT_ROOT / 'resources' / 'icon.ico') if (PROJECT_ROOT / 'resources' / 'icon.ico').exists() else None,
)

# 单目录打包（调试用）
# coll = COLLECT(
#     exe,
#     a.binaries,
#     a.zipfiles,
#     a.datas,
#     strip=False,
#     upx=True,
#     upx_exclude=[],
#     name='AntennaPostProcessor',
# )
