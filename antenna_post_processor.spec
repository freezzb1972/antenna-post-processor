# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller 打包配置
====================
构建单文件 Windows .exe:
    pyinstaller antenna_post_processor.spec

构建单目录调试版:
    pyinstaller --onedir antenna_post_processor.spec

体积优化:
  仅打包实际使用的 PySide6.QtCore/Gui/Widgets（~20MB DLL），
  排除 WebEngine(195MB)、QML、Multimedia 等未使用模块。
"""

import sys
from pathlib import Path

block_cipher = None

PROJECT_ROOT = Path(SPECPATH).resolve()

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
        (str(PROJECT_ROOT / 'config' / 'templates.json'), 'config'),
        # 模板文件（可选，打包后也可以在运行时选择外部模板）
        (str(PROJECT_ROOT / 'data' / 'template_5G1.xlsx'), 'templates'),
        # 帮助手册
        (str(PROJECT_ROOT / 'USER_GUIDE.html'), '.'),
        # 内嵌试用许可（30 天，到期后引导在线激活）
        (str(PROJECT_ROOT / 'license.json'), '.'),
        # 试用配置（编译时固化: build_date + trial_days，防备份攻击）
        (str(PROJECT_ROOT / 'trial_config.json'), '.'),
    ],
    hiddenimports=[
        # ---- PySide6 — 仅引用实际使用的模块，避免 collect_submodules 拉入全部 426MB ----
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',

        # ---- matplotlib backends（Agg 必需，SVG 可选但小） ----
        'matplotlib.backends.backend_agg',
        'matplotlib.backends.backend_svg',

        # ---- numpy ----
        'numpy.lib.format',

        # ---- requests (CloudRenderer) ----
        'requests',

        # ---- openpyxl ----
        'openpyxl.cell._writer',

        # ---- cryptography (ECDSA 许可签名) ----
        'cryptography.hazmat.primitives',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 排除 PySide6 其他子模块（防止被间接引入）
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
        'PySide6.QtQml',
        'PySide6.QtQuick',
        'PySide6.QtQuickWidgets',
        'PySide6.QtQuick3D',
        'PySide6.QtQuickControls2',
        'PySide6.QtOpenGL',
        'PySide6.QtOpenGLWidgets',
        'PySide6.QtPrintSupport',
        'PySide6.QtSvg',
        'PySide6.QtSvgWidgets',
        'PySide6.QtDesigner',
        'PySide6.QtCharts',
        'PySide6.QtDataVisualization',
        'PySide6.QtGraphs',
        'PySide6.QtGraphsWidgets',
        'PySide6.QtHttpServer',
        'PySide6.QtNetworkAuth',
        'PySide6.QtPdf',
        'PySide6.QtPdfWidgets',
        'PySide6.QtScxml',
        'PySide6.QtSerialBus',
        'PySide6.QtSpatialAudio',
        'PySide6.QtStateMachine',
        'PySide6.QtTextToSpeech',
        'PySide6.QtWebSockets',
        'PySide6.QtWebView',
        # 排除不需要的 matplotlib backends
        'matplotlib.backends.backend_qt',
        'matplotlib.backends.backend_tkagg',
        'matplotlib.backends.backend_wxagg',
        'matplotlib.backends.backend_gtk3agg',
        # openpyxl 可选依赖（自动降级到 stdlib xml，不影响功能）
        'lxml',
        'lxml.*',
        # 排除环境中的污染包（chromadb/openai/huggingface 等间接引入）
        # 注意：不排除 PIL（matplotlib 保存图片需要）和 lxml（openpyxl 可选优化）
        'pandas',
        'pandas.*',
        'sqlalchemy',
        'sqlalchemy.*',
        'pydantic',
        'pydantic.*',
        'tqdm',
        'tqdm.*',
        'rich',
        'rich.*',
        'chromadb',
        'chromadb.*',
        'openai',
        'openai.*',
        'huggingface_hub',
        'huggingface_hub.*',
        'tokenizers',
        'tokenizers.*',
        'transformers',
        'transformers.*',
        'torch',
        'torch.*',
        'scipy',
        'scipy.*',
        'pyarrow',
        'pyarrow.*',
        'numba',
        'numba.*',
        'numexpr',
        'numexpr.*',
        'pydantic_core',
        'pydantic_core.*',
        'dotenv',
        'dotenv.*',
        'google',
        'google.*',
        'grpc',
        'grpc.*',
        'yaml',
        'yaml.*',
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
