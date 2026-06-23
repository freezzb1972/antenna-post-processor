"""
布局工具
========
跨对话框复用的通用布局组件和辅助函数。
"""

from __future__ import annotations

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtWidgets import (
    QApplication, QDialog, QDialogButtonBox, QLayout,
    QScrollArea, QVBoxLayout, QWidget,
)


# ═══════════════════════════════════════════════════════════════
# FlowLayout — 流式布局, 用于角度标签自动换行显示
# ═══════════════════════════════════════════════════════════════

class FlowLayout(QLayout):
    """水平流式布局: 子项从左到右排列, 超出宽度自动换行。"""

    def __init__(self, parent=None, margin=0, h_spacing=4, v_spacing=4):
        super().__init__(parent)
        self._items = []
        self._h_spacing = h_spacing
        self._v_spacing = v_spacing
        self.setContentsMargins(margin, margin, margin, margin)

    def addItem(self, a0):
        self._items.append(a0)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientations(Qt.Orientation(0))

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        h = max((item.sizeHint().height() for item in self._items), default=0)
        m = self.contentsMargins()
        return QSize(m.left() + m.right() + 40, h + m.top() + m.bottom() + self._v_spacing * 2)

    def _do_layout(self, rect, test_only=False):
        margins = self.contentsMargins()
        x = margins.left()
        y = margins.top()
        line_h = 0
        usable = rect.width() - margins.left() - margins.right()

        for item in self._items:
            hint = item.sizeHint()
            w, h = hint.width(), hint.height()
            if x + w > usable and line_h > 0:
                x = margins.left()
                y += line_h + self._v_spacing
                line_h = 0
            if not test_only:
                item.setGeometry(QRect(x, y, w, h))
            x += w + self._h_spacing
            line_h = max(line_h, h)

        return y + line_h + margins.bottom()


# ═══════════════════════════════════════════════════════════════
# 对话框布局辅助
# ═══════════════════════════════════════════════════════════════

def auto_size_dialog(dlg: QDialog, min_width: int = 520, min_height: int = 420):
    """通用对话框初始化: 限制最大高度为屏幕 90%, 允许手动调整。"""
    screen = QApplication.primaryScreen().availableGeometry()
    max_h = int(screen.height() * 0.9)
    hint = dlg.sizeHint()
    w = max(min_width, hint.width() + 20)
    dlg.setMinimumSize(w, min(min_height, max_h))
    dlg.setMaximumHeight(max_h)
    dlg.resize(w, min(hint.height() + 40, max_h))


def wrap_in_scroll(dlg: QDialog, content_widgets: list, buttons: QDialogButtonBox):
    """将对话框内容包入 QScrollArea, 按钮保留在底部固定。

    前置条件: 调用者不能在 dlg 上已设置 layout。此函数会
    通过 dlg.setLayout(outer) 设置新布局，替换任何已有布局。
    """
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QScrollArea.NoFrame)
    inner = QWidget()
    inner_layout = QVBoxLayout(inner)
    inner_layout.setSpacing(6)
    for w in content_widgets:
        inner_layout.addWidget(w)
    inner_layout.addStretch()
    scroll.setWidget(inner)

    outer = QVBoxLayout(dlg)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.addWidget(scroll)
    outer.addWidget(buttons)
