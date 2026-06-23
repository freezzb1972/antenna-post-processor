"""
启动闪屏
========
QSplashScreen + QProgressBar, 在初始化阶段显示进度。
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QProgressBar, QSplashScreen, QVBoxLayout, QWidget


class SplashScreen:
    """应用启动闪屏, 含进度条和状态文字。"""

    def __init__(self, app: QApplication):
        # 生成纯色背景 pixmap (430×200)
        pixmap = QPixmap(430, 200)
        pixmap.fill(QColor("#1a1a2e"))

        self._splash = QSplashScreen(pixmap, Qt.WindowStaysOnTopHint)
        self._splash.setWindowOpacity(1.0)

        # 进度条 (叠加在 splash 底部)
        self._progress = QProgressBar(self._splash)
        self._progress.setGeometry(30, 140, 370, 20)
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setTextVisible(True)
        self._progress.setStyleSheet("""
            QProgressBar {
                border: 1px solid #555;
                border-radius: 8px;
                background: #2d2d44;
                text-align: center;
                color: #ccc;
                font-size: 11px;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #0d7377, stop:1 #14a3a8);
                border-radius: 7px;
            }
        """)

        # 消息标签 (手动绘制)
        self._message = ""
        self._splash.show()
        app.processEvents()

    def advance(self, message: str, progress: int):
        """更新进度和消息。"""
        self._message = message
        self._progress.setValue(progress)
        self._progress.setFormat(f"  {message}  %p%")
        QApplication.processEvents()

    def finish(self, window):
        """关闭闪屏。"""
        self._splash.finish(window)
