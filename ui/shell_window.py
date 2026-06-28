"""
Shell 窗口 — 轻量启动页
========================
Word 风格: 管理入口 + 最近任务列表 → 快速进入任务窗口。
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QMainWindow, QMessageBox, QPushButton, QVBoxLayout, QWidget,
)


class ShellWindow(QMainWindow):
    """Shell 窗口: 最近任务列表 + 新建任务入口。"""

    def __init__(self, app: QApplication):
        super().__init__()
        self.app = app
        self._task_windows: List = []
        self._setup_ui()
        self._setup_menu()
        self._new_task_window()
        self.setWindowTitle(self.tr("天线参数后处理"))
        self.setMinimumSize(520, 400)
        self.resize(520, 400)

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        # 标题
        title = QLabel("<h2>" + self.tr("📡 天线参数后处理") + "</h2>")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        subtitle = QLabel(self.tr("选择一个任务，或新建一个开始工作"))
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet("color: #888; margin-bottom: 12px;")
        layout.addWidget(subtitle)

        # 最近任务
        layout.addWidget(QLabel("<b>" + self.tr("最近任务") + "</b>"))
        self._recent_list = QListWidget()
        self._recent_list.setAlternatingRowColors(True)
        self._recent_list.setMinimumHeight(180)
        self._recent_list.itemDoubleClicked.connect(self._on_recent_double_click)
        layout.addWidget(self._recent_list)

        # 按钮
        btn_row = QHBoxLayout()
        btn_new = QPushButton(self.tr("🆕 新建任务"))
        btn_new.setMinimumHeight(40)
        btn_new.clicked.connect(self._new_task_window)
        btn_row.addWidget(btn_new)
        btn_open = QPushButton(self.tr("📂 打开任务包..."))
        btn_open.setMinimumHeight(40)
        btn_open.clicked.connect(self._on_open_task)
        btn_row.addWidget(btn_open)
        layout.addLayout(btn_row)

        layout.addStretch()

    def _setup_menu(self):
        menubar = self.menuBar()
        fm = menubar.addMenu(self.tr("&文件"))
        fm.addAction(self.tr("新建任务"), self._new_task_window, QKeySequence("Ctrl+N"))
        fm.addAction(self.tr("打开任务包..."), self._on_open_task)
        fm.addSeparator()
        fm.addAction(self.tr("关闭窗口"), self.close, QKeySequence("Ctrl+W"))

    def _new_task_window(self):
        """创建新任务窗口并注册到 WindowManager。"""
        from ui.main_window import MainWindow
        from ui.window_manager import WindowManager
        win = MainWindow(self.app)
        WindowManager.instance().register(win)
        # 当 MainWindow close 时从列表移除
        win.destroyed.connect(lambda: self._on_task_closed(win))
        self._task_windows.append(win)
        win.show()
        # 刷新最近任务
        self._refresh_recent()

    def _on_task_closed(self, win):
        if win in self._task_windows:
            self._task_windows.remove(win)
        if not self._task_windows:
            self.close()

    def _on_recent_double_click(self, item: QListWidgetItem):
        """双击最近任务 → 激活对应窗口。"""
        idx = self._recent_list.row(item)
        if 0 <= idx < len(self._task_windows):
            win = self._task_windows[idx]
            win.show()
            win.raise_()
            win.activateWindow()

    def _on_open_task(self):
        """打开 .ant 任务包（占位，待 P4 实现）。"""
        QMessageBox.information(self, self.tr("提示"),
            self.tr("任务包功能尚在开发中。"))

    def _refresh_recent(self):
        """刷新最近任务列表。"""
        self._recent_list.clear()
        for win in self._task_windows:
            title = win.window_title() if hasattr(win, 'window_title') else self.tr("未命名任务")
            item = QListWidgetItem(title)
            self._recent_list.addItem(item)

    def closeEvent(self, event):
        """关闭所有任务窗口后退出。"""
        for win in list(self._task_windows):
            win.close()
        event.accept()
