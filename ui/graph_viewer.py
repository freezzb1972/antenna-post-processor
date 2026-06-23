"""
交互式天线方向图 3D 查看器
==========================
支持 1×1, 1×2, 2×2, 3×3 多图布局，Link 联动视角。
Phase 2: Polar 2D / Cartesian 3D 图类型切换 + 球面剖切 + Theta 截面选择
Phase 3: 频点动画播放 (QTimer 驱动)
Matplotlib + mplot3d，数据降采样保证交互流畅。
"""

from __future__ import annotations

import numpy as np
from typing import Dict, List

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
    QGroupBox, QHBoxLayout, QLabel, QPushButton,
    QSlider, QSpinBox, QSplitter, QTableWidget, QTableWidgetItem,
    QToolBar, QVBoxLayout, QWidget,
)
import matplotlib
matplotlib.use("QtAgg")
# 设置中文字体支持
try:
    matplotlib.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'WenQuanYi Micro Hei', 'DejaVu Sans']
    matplotlib.rcParams['axes.unicode_minus'] = False
except Exception:
    pass
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

# 方向图数据 key → 显示名称
PATTERN_DATA_MAP = {
    "gain_db": "Gain (dBi)",
    "theta_db": "E_θ (dB)",
    "phi_db": "E_φ (dB)",
    "ar_linear": "AR (线性)",
}
# 默认显示的数据类型 (按序)
DEFAULT_PATTERN_KEYS = ["gain_db", "theta_db", "phi_db", "ar_linear"]

GRID_OPTIONS = ["1×1", "1×2", "2×2"]
PLOT_TYPES = ["Spherical 3D", "Polar 2D", "Cartesian 3D"]

# Frequency curve definitions: (display_label, result_key_prefix, match_mode)
# match_mode "exact" requires exact key match, "prefix" matches key.startswith(prefix)
FREQ_CURVE_DEFS = [
    ("Efficiency vs Freq", "efficiency_pct", "exact"),
    ("Peak Gain vs Freq", "gain", "exact"),
    ("Directivity vs Freq", "directivity", "exact"),
    ("AR vs Freq", "ar_single", "exact"),
    ("Gain @θ vs Freq", "lag_range", "prefix"),
]


class SubPlotPanel:
    """单个子图面板。"""
    def __init__(self, fig, position, title="", data_key="gain_db"):
        self.title = title
        self.data_key = data_key   # 直接存储数据 key, e.g. "gain_db", "ar_linear"
        self._elev, self._azim = 30, -60
        self._plot_type = "Spherical 3D"
        self._theta_idx = 0          # Polar 2D 截面索引
        self._cuts = {"X-Z": False, "Y-Z": False, "X-Y": False}
        self._fig = fig
        self._position = position
        self.ax = None
        self._create_axes()

    # ── 轴管理 ──

    def _create_axes(self):
        """根据当前 plot_type 创建对应 axes。"""
        if self.ax is not None:
            self.ax.remove()
        if self._plot_type == "Polar 2D":
            self.ax = self._fig.add_subplot(*self._position, projection="polar")
        else:
            self.ax = self._fig.add_subplot(*self._position, projection="3d")

    def set_plot_type(self, plot_type: str):
        if plot_type != self._plot_type:
            self._plot_type = plot_type
            self._create_axes()

    def set_theta_idx(self, idx: int):
        self._theta_idx = idx

    def set_cut(self, cut: str, enabled: bool):
        self._cuts[cut] = enabled

    def set_view(self, elev, azim):
        self._elev, self._azim = elev, azim
        if hasattr(self.ax, "view_init"):
            self.ax.view_init(elev=elev, azim=azim)

    # ── 主绘制入口 ──

    def draw(self, theta_deg, phi_deg, data, cmap="jet"):
        self.ax.clear()
        if self._plot_type == "Polar 2D":
            self._draw_polar(theta_deg, phi_deg, data, cmap)
        elif self._plot_type == "Cartesian 3D":
            self._draw_cartesian_3d(theta_deg, phi_deg, data, cmap)
        else:
            self._draw_spherical_3d(theta_deg, phi_deg, data, cmap)
        self._apply_cuts()
        self.ax.set_title(self.title, fontsize=8)

    # ── 绘图模式 ──

    def _draw_spherical_3d(self, theta_deg, phi_deg, data, cmap):
        """球面 3D: 将增益值映射到球面半径。"""
        theta_rad = np.deg2rad(theta_deg)
        phi_rad = np.deg2rad(phi_deg)
        tm, pm = np.meshgrid(theta_rad, phi_rad, indexing="ij")
        r = np.maximum(data.T, 1e-15)
        x = r * np.sin(tm) * np.cos(pm)
        y = r * np.sin(tm) * np.sin(pm)
        z = r * np.cos(tm)
        self.ax.plot_surface(x, y, z, cmap=cmap, alpha=0.85,
                             linewidth=0, antialiased=True)
        self.ax.set_xlabel(""); self.ax.set_ylabel(""); self.ax.set_zlabel("")
        self.ax.set_box_aspect([1, 1, 1])
        self.ax.view_init(elev=self._elev, azim=self._azim)

    def _draw_polar(self, theta_deg, phi_deg, data, cmap):
        """极坐标 2D: 增益 vs φ 在固定 θ 截面。"""
        idx = min(self._theta_idx, data.shape[1] - 1)
        phi_rad = np.deg2rad(phi_deg)
        r = np.maximum(data[:, idx], 1e-15)
        self.ax.plot(phi_rad, r)
        self.ax.set_theta_zero_location("N")
        self.ax.set_theta_direction(-1)
        theta_val = theta_deg[min(self._theta_idx, len(theta_deg) - 1)]
        self.ax.set_title(f"{self.title} — θ={theta_val:.0f}°", fontsize=8)

    def _draw_cartesian_3d(self, theta_deg, phi_deg, data, cmap):
        """直角坐标 3D: φ-θ-值 曲面。"""
        tm, pm = np.meshgrid(theta_deg, phi_deg, indexing="ij")
        z = data.T  # (n_theta, n_phi)
        self.ax.plot_surface(pm, tm, z, cmap=cmap, alpha=0.85,
                             linewidth=0, antialiased=True)
        self.ax.set_xlabel("φ (°)"); self.ax.set_ylabel("θ (°)"); self.ax.set_zlabel("")

    # ── 剖切 ──

    def _apply_cuts(self):
        """限制坐标轴范围以显示球面内部。"""
        if self._plot_type != "Spherical 3D":
            return
        try:
            if self._cuts["X-Z"]:
                self.ax.set_ylim(0, self.ax.get_ylim()[1])
            if self._cuts["Y-Z"]:
                self.ax.set_xlim(0, self.ax.get_xlim()[1])
            if self._cuts["X-Y"]:
                self.ax.set_zlim(0, self.ax.get_zlim()[1])
        except (ValueError, AttributeError):
            pass  # ax limits unavailable on empty/invalid axes (visual-only)

    # ── 工具 ──

    def display_name(self) -> str:
        """返回人类可读的数据类型名称。"""
        return PATTERN_DATA_MAP.get(self.data_key, self.data_key)


class GraphViewer(QWidget):
    """天线方向图交互查看器: 多子图 + 数据表 + 联动视角 + 动画。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._graph_data: Dict[float, Dict] = {}
        self._results = None
        self._subplots: List[SubPlotPanel] = []
        self._linked = True
        self._elev, self._azim = 30, -60
        self._step_deg = 5.0
        # 可配置状态: 方向图数据类型 (data key 列表)
        self._active_pattern_keys: List[str] = list(DEFAULT_PATTERN_KEYS)
        # 可配置状态: 频率曲线选择 (索引列表, None=全部)
        self._active_freq_curve_indices: List[int] = []
        # Animation state
        self._anim_timer = QTimer(self)
        self._anim_timer.timeout.connect(self._on_anim_tick)
        self._anim_playing = False
        self._setup_ui()
        self._canvas.mpl_connect("button_release_event", self._on_mouse_release)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._build_advanced_toolbar())  # 旋转预设 + 色图 + 导出
        layout.addLayout(self._build_ctrl_bar())
        layout.addWidget(self._build_phase2_bar())
        self._splitter, self._figure, self._canvas, self._table = self._build_graph_area()
        layout.addWidget(self._splitter, stretch=1)
        layout.addWidget(self._build_anim_bar())

    def _build_advanced_toolbar(self) -> QToolBar:
        """旋转预设 + 色图选择 + 导出按钮。"""
        tb = QToolBar()
        tb.setMovable(False)
        tb.setIconSize(tb.iconSize() * 0.7)

        # 旋转预设
        tb.addWidget(QLabel(" 视角: "))
        presets = [
            ("Iso", 30, -60), ("Top", 90, 0), ("Front", 0, 0),
            ("Side", 0, 90), ("Back", 0, 180), ("Bottom", -90, 0),
        ]
        for label, elev, azim in presets:
            btn = QPushButton(label)
            btn.setFixedWidth(60)
            btn.setToolTip(f"预设视角: {label} (el={elev}°, az={azim}°)")
            btn.clicked.connect(lambda checked, e=elev, a=azim: self._set_view_preset(e, a))
            tb.addWidget(btn)
        tb.addSeparator()

        # 色图选择
        tb.addWidget(QLabel(" 色图: "))
        self._cmb_cmap = QComboBox()
        self._cmb_cmap.addItems(["jet", "viridis", "plasma", "inferno", "magma", "cividis",
                                  "turbo", "hot", "coolwarm", "rainbow"])
        self._cmb_cmap.setCurrentText("jet")
        self._cmb_cmap.setFixedWidth(100)
        self._cmb_cmap.currentTextChanged.connect(self._on_cmap_changed)
        tb.addWidget(self._cmb_cmap)
        tb.addSeparator()

        # 导出按钮
        btn_export = QPushButton("💾 导出视图")
        btn_export.setToolTip("保存当前视图为 PNG 图片")
        btn_export.clicked.connect(self._on_export_view)
        tb.addWidget(btn_export)

        tb.addSeparator()

        # 图形设置按钮
        btn_settings = QPushButton("⚙ 图形设置")
        btn_settings.setToolTip("配置图形显示: 类型、数量、参数")
        btn_settings.clicked.connect(self._show_viewer_settings)
        tb.addWidget(btn_settings)

        # 缩放
        self._lbl_zoom = QLabel(" 100%")
        tb.addWidget(self._lbl_zoom)

        return tb

    def _set_view_preset(self, elev: float, azim: float):
        self._elev, self._azim = elev, azim
        for sp in self._subplots:
            sp.set_view(elev, azim)
        if hasattr(self, '_lbl_zoom'):
            self._lbl_zoom.setText(f" el={elev:.0f}° az={azim:.0f}°")
        self._canvas.draw_idle()

    def _on_cmap_changed(self, cmap_name: str):
        for sp in self._subplots:
            if hasattr(sp.ax, 'collections'):
                for col in sp.ax.collections:
                    col.set_cmap(cmap_name)
        self._canvas.draw_idle()
        # 强制重绘以应用新色图
        self._on_update()

    def _on_export_view(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "导出图形视图", "antenna_pattern.png",
            "PNG 图片 (*.png);;JPEG 图片 (*.jpg);;所有文件 (*)")
        if path:
            self._figure.savefig(path, dpi=150, bbox_inches='tight')
            if hasattr(self.parent(), 'parent') and hasattr(self.parent().parent(), '_log'):
                self.parent().parent()._log(f"✓ 图形已导出: {path}")

    def _build_ctrl_bar(self) -> QHBoxLayout:
        ctrl = QHBoxLayout()
        ctrl.addWidget(QLabel("视图:"))
        self._cmb_view_mode = QComboBox()
        self._cmb_view_mode.addItems(["3D Pattern", "Freq Curves"])
        self._cmb_view_mode.currentIndexChanged.connect(self._on_view_mode_changed)
        ctrl.addWidget(self._cmb_view_mode)
        ctrl.addSpacing(16)

        self._pattern_ctrl_panel = QWidget()
        pc = QHBoxLayout(self._pattern_ctrl_panel)
        pc.setContentsMargins(0, 0, 0, 0)
        pc.addWidget(QLabel("频点:"))
        self._cmb_freq = QComboBox()
        self._cmb_freq.currentIndexChanged.connect(self._on_update)
        pc.addWidget(self._cmb_freq)
        pc.addWidget(QLabel("  布局:"))
        self._cmb_grid = QComboBox()
        self._cmb_grid.addItems(GRID_OPTIONS)
        self._cmb_grid.setCurrentIndex(2)
        self._cmb_grid.currentIndexChanged.connect(self._on_grid_changed)
        pc.addWidget(self._cmb_grid)
        pc.addWidget(QLabel("  精度:"))
        self._spin_step = QSpinBox()
        self._spin_step.setRange(1, 30)
        self._spin_step.setValue(5)
        self._spin_step.setSuffix("°")
        self._spin_step.setFixedWidth(70)
        self._spin_step.setToolTip("3D 采样步进: 1°=最精细(~40K点), 30°=最快(~150点)")
        self._spin_step.valueChanged.connect(self._on_step_changed)
        pc.addWidget(self._spin_step)
        self._chk_link = QCheckBox("联动视角")
        self._chk_link.setChecked(True)
        self._chk_link.toggled.connect(self._on_link_toggled)
        pc.addWidget(self._chk_link)
        ctrl.addWidget(self._pattern_ctrl_panel)
        self._lbl_info = QLabel("")
        ctrl.addWidget(self._lbl_info)
        return ctrl

    def _build_phase2_bar(self) -> QWidget:
        self._pattern_phase2_panel = QWidget()
        phase2 = QHBoxLayout(self._pattern_phase2_panel)
        self._plot_type_combos: List[QComboBox] = []
        self._plot_type_layout = QHBoxLayout()
        phase2.addLayout(self._plot_type_layout)
        phase2.addSpacing(16)
        phase2.addWidget(QLabel("剖切:"))
        self._cut_checks: Dict[str, QCheckBox] = {}
        for label in ["X-Z", "Y-Z", "X-Y"]:
            cb = QCheckBox(label)
            cb.toggled.connect(self._on_cut_changed)
            self._cut_checks[label] = cb
            phase2.addWidget(cb)
        phase2.addSpacing(8)
        phase2.addWidget(QLabel("  θ截面:"))
        self._slider_theta = QSlider(Qt.Horizontal)
        self._slider_theta.setMinimum(0); self._slider_theta.setMaximum(0)
        self._slider_theta.setFixedWidth(120)
        self._slider_theta.valueChanged.connect(self._on_theta_slider_changed)
        phase2.addWidget(self._slider_theta)
        self._lbl_theta_val = QLabel("--°")
        self._lbl_theta_val.setFixedWidth(40)
        phase2.addWidget(self._lbl_theta_val)
        phase2.addStretch()
        return self._pattern_phase2_panel

    @staticmethod
    def _build_graph_area():
        splitter = QSplitter(Qt.Horizontal)
        fig = Figure(figsize=(7, 7), dpi=80)
        canvas = FigureCanvas(fig)
        table = QTableWidget()
        table.setMinimumWidth(220)
        splitter.addWidget(canvas)
        splitter.addWidget(table)
        splitter.setSizes([650, 250])
        return splitter, fig, canvas, table

    def _build_anim_bar(self) -> QWidget:
        self._pattern_anim_panel = QWidget()
        anim_bar = QHBoxLayout(self._pattern_anim_panel)
        self._btn_play = QPushButton("▶ 播放")
        self._btn_play.setFixedWidth(80)
        self._btn_play.clicked.connect(self._on_play_pause)
        anim_bar.addWidget(self._btn_play)
        anim_bar.addWidget(QLabel("  速度:"))
        self._slider_speed = QSlider(Qt.Horizontal)
        self._slider_speed.setMinimum(1); self._slider_speed.setMaximum(10)
        self._slider_speed.setValue(5); self._slider_speed.setFixedWidth(100)
        self._slider_speed.valueChanged.connect(self._on_speed_changed)
        anim_bar.addWidget(self._slider_speed)
        self._lbl_speed_val = QLabel("600ms"); self._lbl_speed_val.setFixedWidth(50)
        anim_bar.addWidget(self._lbl_speed_val)
        anim_bar.addSpacing(12)
        self._lbl_anim_progress = QLabel("0 / 0")
        anim_bar.addWidget(self._lbl_anim_progress)
        anim_bar.addStretch()
        return self._pattern_anim_panel

    # ==================================================================
    # 图类型控件 (per-subplot)
    # ==================================================================

    def _rebuild_plot_type_controls(self):
        """根据当前子图数量重建图类型下拉列表。"""
        for combo in self._plot_type_combos:
            self._plot_type_layout.removeWidget(combo)
            combo.deleteLater()
        self._plot_type_combos.clear()

        for sp in self._subplots:
            combo = QComboBox()
            combo.addItems(PLOT_TYPES)
            combo.currentIndexChanged.connect(self._on_plot_type_changed)
            self._plot_type_combos.append(combo)
            # 短标签: 取标题括号前的内容
            short = sp.title.split("(")[0].strip()
            self._plot_type_layout.addWidget(QLabel(short + ":"))
            self._plot_type_layout.addWidget(combo)

    def _on_plot_type_changed(self):
        for sp, combo in zip(self._subplots, self._plot_type_combos):
            sp.set_plot_type(combo.currentText())
        self._on_update()

    # ==================================================================
    # 球面剖切
    # ==================================================================

    def _on_cut_changed(self):
        cuts = {label: cb.isChecked() for label, cb in self._cut_checks.items()}
        for sp in self._subplots:
            for cut, enabled in cuts.items():
                sp.set_cut(cut, enabled)
        self._canvas.draw_idle()

    # ==================================================================
    # Theta 截面滑块
    # ==================================================================

    def _on_theta_slider_changed(self, value):
        theta_arr = self._current_theta()
        val_deg = theta_arr[min(value, len(theta_arr) - 1)] if theta_arr is not None else value
        self._lbl_theta_val.setText(f"{val_deg:.0f}°")
        for sp in self._subplots:
            sp.set_theta_idx(value)
        self._on_update()

    def _current_theta(self):
        freq = self._cmb_freq.currentData()
        if freq is not None and freq in self._graph_data:
            return self._graph_data[freq].get("theta")
        return None

    # ==================================================================
    # 布局 / 精度 / 联动
    # ==================================================================

    def _rebuild_subplots(self):
        # 保存旧子图的视角 (按 data_key 索引)
        old_views = {sp.data_key: (sp._elev, sp._azim) for sp in self._subplots}
        self._figure.clear()
        rows, cols = self._grid_dims()
        self._subplots = []
        # 使用可配置的数据类型列表
        keys = self._active_pattern_keys[:rows * cols]
        for i, dk in enumerate(keys):
            pos = (rows, cols, i + 1)
            title = PATTERN_DATA_MAP.get(dk, dk)
            sp = SubPlotPanel(self._figure, pos, title=title, data_key=dk)
            ev, az = old_views.get(dk, (self._elev, self._azim))
            sp.set_view(ev, az)
            self._subplots.append(sp)
        self._rebuild_plot_type_controls()
        self._canvas.draw()

    def _grid_dims(self):
        mapping = {"1×1": (1, 1), "1×2": (1, 2), "2×2": (2, 2), "3×3": (3, 3)}
        return mapping.get(self._cmb_grid.currentText(), (2, 2))

    def _on_grid_changed(self):
        self._rebuild_subplots()
        self._on_update()

    def _on_step_changed(self):
        self._step_deg = float(self._spin_step.value())
        if self._results is not None:
            from src.graph_data import extract_graph_data
            self._graph_data = extract_graph_data(self._results, self._step_deg)
            self._on_update()

    def _on_link_toggled(self, checked):
        self._linked = checked

    def _on_mouse_release(self, event):
        if self._linked and self._subplots:
            sp0 = self._subplots[0]
            if hasattr(sp0.ax, 'elev') and hasattr(sp0.ax, 'azim'):
                self._elev = sp0.ax.elev
                self._azim = sp0.ax.azim
                for sp in self._subplots[1:]:
                    sp.set_view(self._elev, self._azim)
            if hasattr(self, '_lbl_zoom'):
                self._lbl_zoom.setText(f" el={self._elev:.0f}° az={self._azim:.0f}°")
            self._canvas.draw_idle()

    # ==================================================================
    # 主刷新
    # ==================================================================

    def _on_update(self):
        if self._cmb_view_mode.currentText() == "Freq Curves":
            self._plot_freq_curves()
            return
        freq = self._cmb_freq.currentData()
        if freq is None or freq not in self._graph_data:
            return
        d = self._graph_data[freq]
        theta, phi = d["theta"], d["phi"]
        self._update_theta_slider(theta)

        cmap = self._cmb_cmap.currentText() if hasattr(self, '_cmb_cmap') else "jet"
        for sp in self._subplots:
            data = d.get(sp.data_key)
            if data is not None:
                sp.draw(theta, phi, data, cmap=cmap)
        self._canvas.draw()

        n = len(theta) * len(phi)
        self._lbl_info.setText(f"θ={len(theta)}×φ={len(phi)}={n}点")

        self._populate_table(theta, phi, d.get("gain_db"))
        self._update_anim_progress()

    def _update_theta_slider(self, theta_arr):
        was_blocked = self._slider_theta.blockSignals(True)
        self._slider_theta.setMaximum(max(0, len(theta_arr) - 1))
        if self._slider_theta.value() > self._slider_theta.maximum():
            self._slider_theta.setValue(0)
        if len(theta_arr) > 0:
            idx = self._slider_theta.value()
            self._lbl_theta_val.setText(
                f"{theta_arr[min(idx, len(theta_arr) - 1)]:.0f}°"
            )
        self._slider_theta.blockSignals(was_blocked)

    def _populate_table(self, theta, phi, data):
        max_c = min(len(theta), 12)
        max_r = min(len(phi), 20)
        ts = max(1, len(theta) // max_c)
        ps = max(1, len(phi) // max_r)
        headers = ["φ\\θ"] + [f"{theta[i]:.0f}°" for i in range(0, len(theta), ts)[:max_c]]
        self._table.setColumnCount(len(headers))
        self._table.setHorizontalHeaderLabels(headers)
        self._table.setRowCount(max_r)
        for ri in range(max_r):
            pi = min(ri * ps, len(phi) - 1)
            self._table.setItem(ri, 0, QTableWidgetItem(f"{phi[pi]:.0f}°"))
            for ci in range(max_c):
                ti = min(ci * ts, len(theta) - 1)
                val = data[pi, ti] if data is not None else 0
                txt = f"{val:.1f}" if np.isfinite(val) else "—"
                self._table.setItem(ri, ci + 1, QTableWidgetItem(txt))

    # ==================================================================
    # 图形设置对话框
    # ==================================================================

    def _show_viewer_settings(self):
        """打开图形显示设置对话框 — 配置子图类型、数量、频率曲线。"""
        dlg = QDialog(self)
        dlg.setWindowTitle("图形显示设置")
        dlg.setMinimumSize(550, 520)

        layout = QVBoxLayout(dlg)
        layout.setSpacing(8)

        # ── 状态拷贝 (Cancel 时恢复) ──
        import copy
        _pattern_keys = copy.deepcopy(self._active_pattern_keys)
        _freq_indices = copy.deepcopy(self._active_freq_curve_indices)
        _grid_text = self._cmb_grid.currentText() if hasattr(self, '_cmb_grid') else "2×2"
        _step_deg = self._step_deg

        # ═══ 3D 方向图: 数据类型选择 ═══
        grp_3d = QGroupBox("3D 方向图 — 显示数据类型")
        grp_3d_layout = QVBoxLayout(grp_3d)
        grp_3d_layout.setSpacing(3)

        # 提示: 哪些数据可用
        avail_keys = list(self._graph_data.values())[0].keys() if self._graph_data else set()
        key_checkboxes: Dict[str, QCheckBox] = {}
        for dk, label in PATTERN_DATA_MAP.items():
            row = QHBoxLayout()
            cb = QCheckBox(label)
            cb.setChecked(dk in _pattern_keys)
            # 检查数据是否实际可用
            if self._graph_data:
                first_freq = next(iter(self._graph_data.values()))
                if dk not in first_freq or first_freq.get(dk) is None:
                    cb.setEnabled(False)
                    cb.setToolTip("数据不可用 (缺少相位信息或无 AR 值)")
            else:
                cb.setEnabled(False)
                cb.setToolTip("请先运行处理以加载数据")
            row.addWidget(cb)
            key_checkboxes[dk] = cb
            # 显示数据形状信息
            if self._graph_data:
                first_freq = next(iter(self._graph_data.values()))
                d = first_freq.get(dk)
                if d is not None and hasattr(d, 'shape'):
                    row.addWidget(QLabel(f"({d.shape[0]}×{d.shape[1]})"))
            row.addStretch()
            grp_3d_layout.addLayout(row)

        # 布局
        grid_row = QHBoxLayout()
        grid_row.addWidget(QLabel("子图布局:"))
        cmb_grid = QComboBox()
        cmb_grid.addItems(GRID_OPTIONS)
        cmb_grid.setCurrentText(_grid_text)
        grid_row.addWidget(cmb_grid)
        grid_row.addStretch()

        # 精度
        grid_row.addWidget(QLabel("采样精度:"))
        spin_step = QSpinBox()
        spin_step.setRange(1, 30)
        spin_step.setValue(int(_step_deg))
        spin_step.setSuffix("°")
        spin_step.setFixedWidth(70)
        spin_step.setToolTip("1°=最精细(~40K点), 30°=最快(~150点)")
        grid_row.addWidget(spin_step)
        grp_3d_layout.addLayout(grid_row)

        # 选中计数提示
        lbl_3d_count = QLabel()
        grp_3d_layout.addWidget(lbl_3d_count)

        def _update_3d_count():
            n = sum(1 for cb in key_checkboxes.values() if cb.isChecked())
            gc = cmb_grid.currentText()
            rows, cols = (int(x) for x in gc.split("×"))
            max_n = rows * cols
            lbl_3d_count.setText(f"已选 {n} 项 / 布局可显示 {max_n} 项  (超出部分不显示)")
            if n > max_n:
                lbl_3d_count.setStyleSheet("color: #e74c3c;")
            else:
                lbl_3d_count.setStyleSheet("color: #888;")

        _update_3d_count()
        for cb in key_checkboxes.values():
            cb.toggled.connect(lambda: _update_3d_count())
        cmb_grid.currentIndexChanged.connect(lambda: _update_3d_count())

        layout.addWidget(grp_3d)

        # ═══ 频率曲线选择 ═══
        grp_fc = QGroupBox("频率曲线 — 显示选择")
        fc_layout = QVBoxLayout(grp_fc)
        fc_layout.setSpacing(3)

        available_curves = self._get_available_freq_curves()
        curve_checkboxes: List[QCheckBox] = []
        if available_curves:
            for i, (label, _) in enumerate(available_curves):
                cb = QCheckBox(label)
                # 用户未选择过 → 默认全选
                cb.setChecked(not _freq_indices or i in _freq_indices)
                curve_checkboxes.append(cb)
                fc_layout.addWidget(cb)
        else:
            fc_layout.addWidget(QLabel("(无频率曲线数据 — 请先运行处理)"))
        layout.addWidget(grp_fc)

        # ═══ 按钮 ═══
        layout.addStretch()
        def _on_accept():
            # 更新方向图类型
            self._active_pattern_keys = [dk for dk, cb in key_checkboxes.items() if cb.isChecked()]
            # 更新频率曲线选择
            self._active_freq_curve_indices = [i for i, cb in enumerate(curve_checkboxes) if cb.isChecked()]
            # 更新布局 — 直接设置 combo 文本
            target_grid = cmb_grid.currentText()
            for i in range(self._cmb_grid.count()):
                if self._cmb_grid.itemText(i) == target_grid:
                    self._cmb_grid.setCurrentIndex(i)
                    break
            # 更新精度
            self._step_deg = float(spin_step.value())
            if self._results is not None:
                from src.graph_data import extract_graph_data
                self._graph_data = extract_graph_data(self._results, self._step_deg)
            self._spin_step.blockSignals(True)
            self._spin_step.setValue(int(self._step_deg))
            self._spin_step.blockSignals(False)
            # 重建子图
            self._rebuild_subplots()
            self._on_update()
            dlg.accept()

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(_on_accept)
        btns.rejected.connect(dlg.reject)
        layout.addWidget(btns)

        dlg.exec()

    # ==================================================================
    # 数据加载
    # ==================================================================

    def load_data(self, results: Dict[str, List[Dict]], step_deg: float = 5.0):
        from src.graph_data import extract_graph_data
        self._results = results
        self._step_deg = step_deg
        self._graph_data = extract_graph_data(results, step_deg)
        self._spin_step.blockSignals(True)
        self._spin_step.setValue(int(step_deg))
        self._spin_step.blockSignals(False)
        self._cmb_freq.clear()
        for f in sorted(self._graph_data.keys()):
            self._cmb_freq.addItem(f"{f:.1f} MHz", f)
        if self._cmb_freq.count() > 0:
            self._cmb_freq.setCurrentIndex(0)
        self._rebuild_subplots()
        self._on_update()

    # ==================================================================
    # 视图模式切换
    # ==================================================================

    def _on_view_mode_changed(self, index):
        mode = self._cmb_view_mode.currentText()
        is_pattern = (mode == "3D Pattern")
        self._pattern_ctrl_panel.setVisible(is_pattern)
        self._pattern_phase2_panel.setVisible(is_pattern)
        self._pattern_anim_panel.setVisible(is_pattern)
        if is_pattern:
            self._rebuild_subplots()  # 始终重建，因为 _plot_freq_curves 会清除 axes
            self._on_update()
        else:
            self._plot_freq_curves()

    def _get_available_freq_curves(self):
        """返回可用的频率曲线列表: [(label, actual_key), ...]."""
        if not self._results:
            return []
        all_keys = set()
        for rows in self._results.values():
            for row in rows:
                all_keys.update(row.keys())

        available = []
        for label, key_prefix, match_mode in FREQ_CURVE_DEFS:
            if match_mode == "prefix":
                found = [k for k in all_keys if k.startswith(key_prefix)]
                if found:
                    available.append((label, found[0]))
            else:
                if key_prefix in all_keys:
                    available.append((label, key_prefix))
        return available

    def _plot_freq_curves(self):
        """绘制选中的频率曲线为 2D Cartesian 子图, 垂直堆叠."""
        self._figure.clear()
        all_available = self._get_available_freq_curves()
        if not all_available:
            self._canvas.draw()
            self._lbl_info.setText("无频率曲线数据可用")
            return

        # 根据用户选择过滤曲线
        if self._active_freq_curve_indices:
            available = [all_available[i] for i in self._active_freq_curve_indices
                         if i < len(all_available)]
        else:
            available = all_available

        if not available:
            self._canvas.draw()
            self._lbl_info.setText("未选择任何频率曲线")
            return

        # 收集数据: freq → {column_key: value}
        freq_data = {}
        for rows in self._results.values():
            for row in rows:
                freq = row.get("frequency")
                if freq is not None:
                    if freq not in freq_data:
                        freq_data[freq] = {}
                    for _, key in available:
                        val = row.get(key)
                        if val is not None:
                            freq_data[freq][key] = val

        if not freq_data:
            self._canvas.draw()
            self._lbl_info.setText("无频率曲线数据")
            return

        freqs = sorted(freq_data.keys())
        n = len(available)

        fig_height = max(3, n * 2.5)
        self._figure.set_size_inches(8, fig_height, forward=True)

        for i, (label, key) in enumerate(available):
            ax = self._figure.add_subplot(n, 1, i + 1)
            values = [freq_data[f].get(key) for f in freqs]
            ax.plot(freqs, values, 'o-', markersize=4)
            ax.set_ylabel(label)
            ax.grid(True, alpha=0.3)
            if i < n - 1:
                ax.tick_params(labelbottom=False)
            else:
                ax.set_xlabel("Frequency (MHz)")

        self._figure.tight_layout()
        self._canvas.draw()
        self._lbl_info.setText(f"频率曲线: {n} 项, {len(freqs)} 个频点")

        # 更新数据表
        self._populate_freq_table(freqs, freq_data, available)

    def _populate_freq_table(self, freqs, freq_data, available):
        """在数据表中显示频率曲线数据."""
        self._table.setColumnCount(len(available) + 1)
        headers = ["Frequency (MHz)"] + [label for label, _ in available]
        self._table.setHorizontalHeaderLabels(headers)
        self._table.setRowCount(len(freqs))
        for ri, freq in enumerate(freqs):
            item = QTableWidgetItem(f"{freq:.1f}")
            # 不允许编辑
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            self._table.setItem(ri, 0, item)
            for ci, (_, key) in enumerate(available):
                val = freq_data[freq].get(key)
                txt = f"{val:.2f}" if val is not None else "—"
                item = QTableWidgetItem(txt)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                self._table.setItem(ri, ci + 1, item)

    # ==================================================================
    # 动画 (Phase 3)
    # ==================================================================

    def _on_speed_changed(self):
        ms = self._anim_interval()
        self._lbl_speed_val.setText(f"{ms}ms")
        if self._anim_playing:
            self._anim_timer.setInterval(ms)

    def _anim_interval(self) -> int:
        """速度滑块 1-10 → 1000ms–100ms"""
        val = self._slider_speed.value()
        return max(100, 1100 - val * 100)

    def _update_anim_progress(self):
        total = self._cmb_freq.count()
        cur = self._cmb_freq.currentIndex() + 1
        self._lbl_anim_progress.setText(f"{cur} / {total}")

    def _on_play_pause(self):
        if self._anim_playing:
            self._stop_animation()
        else:
            self._start_animation()

    def _start_animation(self):
        total = self._cmb_freq.count()
        if total < 2:
            return
        # 如果在最后一个频点，从头开始
        if self._cmb_freq.currentIndex() >= total - 1:
            self._cmb_freq.setCurrentIndex(0)
        self._anim_playing = True
        self._btn_play.setText("⏸ 暂停")
        self._anim_timer.start(self._anim_interval())

    def _stop_animation(self):
        self._anim_playing = False
        self._anim_timer.stop()
        self._btn_play.setText("▶ 播放")

    def _on_anim_tick(self):
        idx = self._cmb_freq.currentIndex() + 1
        total = self._cmb_freq.count()
        if idx >= total:
            self._stop_animation()
            return
        self._cmb_freq.setCurrentIndex(idx)


# ═══════════════════════════════════════════════════════════════
# GraphDataTab — 图形原始数据表格 (频点选择 + 增益矩阵)
# ═══════════════════════════════════════════════════════════════

class GraphDataTab(QWidget):
    """独立标签页: 频点下拉选择 + 3D 增益矩阵数据表。

    从 pipeline results 中提取 _raw_data 并按频点展示
    增益矩阵 (phi × theta)。步进 5°，最多显示 30 个 phi 行。
    """

    TAB_NAME = "📊 图形数据"

    def __init__(self, results: dict, parent=None):
        super().__init__(parent)
        from src.graph_data import extract_graph_data
        import numpy as np
        self._gd = extract_graph_data(results)
        self._np = np
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        ctrl = QHBoxLayout()
        ctrl.addWidget(QLabel("频点:"))
        self._cmb = QComboBox()
        for f in sorted(self._gd.keys()):
            self._cmb.addItem(f"{f:.1f} MHz", f)
        ctrl.addWidget(self._cmb)
        ctrl.addStretch()
        ctrl.addWidget(QLabel(f"共 {len(self._gd)} 个频点, 步进 5°"))
        layout.addLayout(ctrl)

        self._table = QTableWidget()
        self._table.setObjectName("graphDataTable")
        layout.addWidget(self._table)

        self._cmb.currentIndexChanged.connect(self._show_freq_data)
        if self._cmb.count() > 0:
            self._show_freq_data(0)

    def _show_freq_data(self, freq_idx: int):
        freq = self._cmb.currentData()
        if freq is None or freq not in self._gd:
            return
        d = self._gd[freq]
        gain = d["gain_db"]
        theta, phi = d["theta"], d["phi"]
        self._table.setRowCount(min(len(phi), 30))
        self._table.setColumnCount(len(theta) + 1)
        self._table.setHorizontalHeaderLabels(["φ\\θ"] + [f"{t:.0f}°" for t in theta])
        for pi in range(min(len(phi), 30)):
            self._table.setItem(pi, 0, QTableWidgetItem(f"{phi[pi]:.0f}°"))
            for ti in range(len(theta)):
                val = gain[pi, ti] if pi < gain.shape[0] and ti < gain.shape[1] else 0
                self._table.setItem(pi, ti + 1,
                    QTableWidgetItem(f"{val:.1f}" if self._np.isfinite(val) else "—"))

    @classmethod
    def install_in(cls, tab_widget, results: dict):
        """在 tab_widget 中查找或创建 GraphDataTab，返回 tab index。

        若已存在同名 tab 则直接选中；否则创建新 tab 并选中。
        """
        for i in range(tab_widget.count()):
            if tab_widget.tabText(i) == cls.TAB_NAME:
                tab_widget.setCurrentIndex(i)
                return i
        tab = cls(results)
        idx = tab_widget.addTab(tab, cls.TAB_NAME)
        tab_widget.setTabVisible(idx, True)
        tab_widget.setCurrentIndex(idx)
        return idx
