"""
全分辨率自适应框架
=================
ScaleManager + AdaptiveWidgetMixin — 仿 Web rem 机制的桌面 UI 缩放引擎。

基准设计稿: 1920×1080 (Full HD).
缩放公式: Factor = 当前窗口宽度 / 1920, 限制在 [min_factor, max_factor].
所有尺寸通过 factor 动态计算，无硬编码像素。

用法:
    from src.scale_manager import ScaleManager, AdaptiveWidgetMixin

    class MyWindow(AdaptiveWidgetMixin, QMainWindow):
        def __init__(self):
            super().__init__()
            self.init_scale_manager(base_width=1920)
            # ... 正常创建布局和控件 ...

    app = QApplication(sys.argv)
    app.setStyleSheet(ScaleManager.global_qss())
    window = MyWindow()
    window.show()
"""

from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QWidget


class ScaleManager:
    """全局缩放管理器 — 单例模式。

    管理一个全局缩放因子 factor，提供静态方法生成缩放后的 QSS。
    """

    # ── 配置 ──
    BASE_WIDTH: float = 1920.0
    MIN_FACTOR: float = 0.85
    MAX_FACTOR: float = 2.5
    BASE_FONT_SIZE: int = 14
    _font_scale: float = 1.0   # 用户手动调整字体的独立乘数

    # ── 全局状态 ──
    _factor: float = 1.0
    _current_width: float = 1920.0

    @classmethod
    def update(cls, window_width: float):
        """根据窗口宽度更新缩放因子。"""
        cls._current_width = max(window_width, 100.0)
        raw = cls._current_width / cls.BASE_WIDTH
        cls._factor = max(cls.MIN_FACTOR, min(cls.MAX_FACTOR, raw))

    @classmethod
    def factor(cls) -> float:
        return cls._factor

    @classmethod
    def apply_full_qss(cls, window: QWidget, base_qss: str = ""):
        """拼接 base QSS + 动态缩放 QSS, 仅设到 QApplication（子控件自动继承）。"""
        QApplication.instance().setStyleSheet(base_qss + cls.dynamic_qss())

    @classmethod
    def dynamic_qss(cls) -> str:
        """生成完整的动态 QSS 样式表 — 所有尺寸通过 factor 计算。

        调用方直接执行: app.setStyleSheet(original_theme_qss + ScaleManager.dynamic_qss())
        """
        f = cls._factor * cls._font_scale
        fs = cls.BASE_FONT_SIZE * f  # 缩放后字体大小
        return f"""
            /* === Auto-Scale Engine (ScaleManager) v2 === */
            /* 逐类覆盖 qt_material 的固定字号 — 全部通过 factor 缩放 */
            QWidget {{
                font-size: {fs:.1f}px;
            }}
            QPushButton {{
                font-size: {fs:.1f}px;
                min-height: {24 * f:.0f}px;
                padding: {3 * f:.0f}px {8 * f:.0f}px;
            }}
            QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
                font-size: {fs:.1f}px;
                min-width:  {80 * f:.0f}px;
                padding: {2 * f:.0f}px {6 * f:.0f}px;
            }}
            QGroupBox {{
                font-size: {fs:.1f}px;
                border: 1px solid rgba(128,128,128,50);
                border-radius: {4 * f:.0f}px;
                font-weight: bold;
                padding: {4 * f:.0f}px {4 * f:.0f}px {1 * f:.0f}px {4 * f:.0f}px;
                margin-top: {14 * f:.0f}px;
            }}
            QGroupBox::title {{
                font-size: {fs:.1f}px;
                subcontrol-origin: margin;
                left: {8 * f:.0f}px;
                padding: {1 * f:.0f}px {3 * f:.0f}px;
            }}
            QTabBar::tab {{
                font-size: {fs:.1f}px;
                padding: {4 * f:.0f}px {10 * f:.0f}px;
            }}
            QTabWidget::pane {{ padding: {2 * f:.0f}px; }}
            QTableWidget, QListWidget, QTreeWidget, QTextEdit, QPlainTextEdit {{
                font-size: {fs:.1f}px;
            }}
            QTableWidget::item, QListWidget::item {{
                padding: {2 * f:.0f}px {4 * f:.0f}px;
            }}
            QHeaderView::section {{
                font-size: {fs:.1f}px;
                padding: {2 * f:.0f}px {4 * f:.0f}px;
            }}
            QMenuBar, QMenuBar::item {{
                font-size: {fs:.1f}px;
                padding: {2 * f:.0f}px {6 * f:.0f}px;
            }}
            QMenu {{ font-size: {fs:.1f}px; }}
            QMenu::item {{
                font-size: {fs:.1f}px;
                padding: {3 * f:.0f}px {14 * f:.0f}px;
            }}
            QToolTip {{
                font-size: {fs:.1f}px;
                padding: {2 * f:.0f}px {4 * f:.0f}px;
            }}
            QStatusBar {{ font-size: {fs:.1f}px; }}
            QCheckBox, QRadioButton {{
                font-size: {fs:.1f}px;
                spacing: {4 * f:.0f}px;
            }}
            QLabel {{ font-size: {fs:.1f}px; }}
            QScrollBar:horizontal {{ height: {12 * f:.0f}px; }}
            QScrollBar:vertical   {{ width:  {12 * f:.0f}px; }}
            QSplitter::handle {{ width: {4 * f:.0f}px; height: {4 * f:.0f}px; }}
            QDialog {{
                min-width: {500 * f:.0f}px;
            }}
        """


class AdaptiveWidgetMixin:
    """自适应混入类 — 窗口缩放时自动刷新 QSS.

    使用方法: class MyWindow(AdaptiveWidgetMixin, QMainWindow):
                  def __init__(self):
                      super().__init__()
                      self.init_scale_manager(base_width=1920)

    特性:
      - resizeEvent 50ms 防抖, 避免拖拽卡顿
      - 自动保存/恢复窗口尺寸到 QSettings
    """

    def init_scale_manager(self, base_width: float = 1920.0):
        """初始化缩放管理器。在 __init__ 中调用。"""
        ScaleManager.BASE_WIDTH = base_width
        self._base_qss = ""
        self._resize_debounce_timer = QTimer(self)
        self._resize_debounce_timer.setSingleShot(True)
        self._resize_debounce_timer.timeout.connect(self._on_resize_debounced)

    def set_base_qss(self, qss: str):
        """保存基础 QSS 并应用 (app + window)。"""
        self._base_qss = qss
        ScaleManager.update(self.width())
        ScaleManager.apply_full_qss(self, qss)

    def resizeEvent(self, event):
        """窗口缩放 — 防抖刷新 QSS."""
        super().resizeEvent(event)
        if hasattr(self, '_resize_debounce_timer'):
            self._resize_debounce_timer.start(50)

    def _on_resize_debounced(self):
        """防抖回调 — 实际执行 QSS 刷新."""
        ScaleManager.update(self.width())
        if self._base_qss:
            ScaleManager.apply_full_qss(self, self._base_qss)
