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
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
    QFileDialog, QFrame, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QScrollArea, QSlider, QSpinBox, QSplitter,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
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
import matplotlib.pyplot as plt

# 方向图数据 key → 显示名称 (从统一注册表 pattern_types 派生; 含相位/Total Power)
from src.pattern_types import PATTERN_TYPES as _PT
PATTERN_DATA_MAP = {}
for _p in _PT:
    PATTERN_DATA_MAP.setdefault(_p.viewer_key, _p.display)   # eirp≡gain 去重
# 默认显示的数据类型 (按注册顺序)
DEFAULT_PATTERN_KEYS = list(PATTERN_DATA_MAP.keys())

GRID_OPTIONS = ["1×1", "1×2", "2×2", "3×3", "2×2+1"]
PLOT_TYPES = ["Spherical 3D", "Polar 2D", "Cartesian 3D"]

# 7 视角预设 (elev, azim, roll) — 与报告 A 类弹窗 7 预设一致 (Iso + 上下左右前后)
VIEW_PRESETS = {
    "Iso":    (30, -60, 0),
    "Top":    (90, -90, 0),
    "Bottom": (-90, -90, 0),
    "Front":  (0, -90, 0),
    "Back":   (0, 90, 0),
    "Left":   (0, 180, 0),
    "Right":  (0, 0, 0),
}

# Frequency curve definitions: (display_label, result_key_prefix, match_mode)
# match_mode "exact" requires exact key match, "prefix" matches key.startswith(prefix)
# 查看器频点曲线定义 — 对应 ChartConfig 的 B 类图表
# (display_label, result_key, match_mode)
# match_mode "exact": 精确匹配 row key
#          "prefix": 匹配 row key 前缀 (如 lag_range_0_90)
FREQ_CURVE_DEFS = [
    # 共用 (所有测试类型)
    ("Efficiency vs Freq",        "efficiency_pct", "exact"),
    ("Peak Gain vs Freq",         "gain",           "exact"),
    ("Directivity vs Freq",       "directivity",    "exact"),
    ("Gain @θ vs Freq",           "lag_range",      "prefix"),
    ("Average Gain vs Freq",      "avg_gain",       "exact"),
    # 仅无源
    ("AR vs Freq",                "ar_single",      "exact"),
    # 仅有源发射
    ("TRP vs Freq",               "trp",            "exact"),
    ("NHPRP ±45° vs Freq",        "nhprp_45",       "exact"),
    ("NHPRP ±30° vs Freq",        "nhprp_30",       "exact"),
    ("Peak EIRP vs Freq",         "peak_eirp",      "exact"),
]

# 模式过滤: 哪些曲线在哪个测试模式下显示
_FREQ_CURVE_MODE_FILTER = {
    "AR vs Freq":           {0},           # 仅无源
    "TRP vs Freq":          {1},           # 仅有源发射
    "NHPRP ±45° vs Freq":   {1},
    "NHPRP ±30° vs Freq":   {1},
    "Peak EIRP vs Freq":    {1},
    # 未列出的为所有模式可用
}

def get_freq_curves_for_mode(mode: int) -> list:
    """返回当前测试模式可用的频率曲线定义。"""
    return [
        d for d in FREQ_CURVE_DEFS
        if mode in _FREQ_CURVE_MODE_FILTER.get(d[0], {0, 1, 2})
    ]


class SubPlotPanel:
    """单个子图面板。"""
    def __init__(self, fig, position, title="", data_key="gain_db"):
        self.title = title
        self.data_key = data_key   # 直接存储数据 key, e.g. "gain_db", "ar_linear"
        self._elev, self._azim, self._roll = 30, -60, 0
        self.selected = False       # 点选高亮 (联动关闭时控件作用于选中子图)
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

    def set_view(self, elev, azim, roll=None):
        self._elev, self._azim = elev, azim
        if roll is not None:
            self._roll = roll
        if hasattr(self.ax, "view_init"):
            self.ax.view_init(elev=self._elev, azim=self._azim, roll=self._roll)

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
        # 标题着色: 选中=黄, Polar 2D 背景白→黑字, 其余黑底→白字
        if self.selected:
            tcolor = "#ffd700"
        else:
            tcolor = "black" if self._plot_type == "Polar 2D" else "white"
        self.ax.set_title(self.title, fontsize=8, color=tcolor)

    # ── 绘图模式 ──

    def _draw_spherical_3d(self, theta_deg, phi_deg, data, cmap):
        """球面 3D: 复用 pattern_geometry.build_3d_surface (与报告导出同算法 → 所见即所得)。

        旧 `r=max(data,eps)` 会让负增益全压中心 → 形状失真; 现用标准半径归一化。
        """
        import matplotlib
        from src.pattern_geometry import build_3d_surface

        key = getattr(self, "data_key", "gain_db")
        if key == "ar_linear":                       # 线性比值 → dB
            values = 20.0 * np.log10(np.maximum(data, 1e-15))
            kind = "magnitude"
        elif key in ("theta_phase", "phi_phase"):    # 相位 (批B启用)
            values = data
            kind = "phase"
        else:                                        # gain_db/theta_db/phi_db/rhcp_db/lhcp_db/cpxpi_db 已是 dB
            values = data
            kind = "magnitude"

        # data 形状 (n_phi, n_theta) 与 build_3d_surface 一致
        X, Y, Z, cvals, vmin, vmax = build_3d_surface(theta_deg, phi_deg, values, kind=kind)
        cmap_obj = matplotlib.colormaps[cmap] if isinstance(cmap, str) else cmap
        mnorm = matplotlib.colors.Normalize(vmin, vmax)
        self.ax.plot_surface(X, Y, Z, facecolors=cmap_obj(mnorm(cvals)),
                             rstride=1, cstride=1, alpha=0.85,
                             linewidth=0, antialiased=True)
        self.ax.set_box_aspect([1, 1, 1])
        self.ax.view_init(elev=self._elev, azim=self._azim, roll=self._roll)
        self.ax.set_axis_off()                       # 天线图无笛卡尔轴意义

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
        self._selected_idx = 0                       # 点选的子图 (分别控制时的目标)
        self._suppress_view = False                  # 抑制数值框信号 (预设/回填时)
        self._ov_combos: List[QComboBox] = []        # per-子图数据类型叠加下拉
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
        self._canvas.mpl_connect("button_press_event", self._on_canvas_click)
        self._canvas.mpl_connect("draw_event", self._reposition_overlays)

    def update_mode_display(self):
        """根据当前测试模式更新模式标签和可选曲线。"""
        if not hasattr(self, '_mw') or not self._mw:
            return
        mode = getattr(self._mw, '_test_mode', 0)
        names = {0: "无源天线", 1: "有源发射 TRP", 2: "有源接收 TIS"}
        if hasattr(self, '_lbl_mode'):
            self._lbl_mode.setText(f"测试类型: {names.get(mode, '')}")

    def get_mode(self) -> int:
        return getattr(self._mw, '_test_mode', 0) if hasattr(self, '_mw') and self._mw else 0

    def set_antenna_list(self, names: list[str], current: str = ""):
        """设置天线列表（从 MainWindow 同步）。"""
        self._antenna_list = names
        self._cmb_ant.blockSignals(True)
        self._cmb_ant.clear()
        self._cmb_ant.addItems(names)
        if current:
            idx = self._cmb_ant.findText(current)
            if idx >= 0: self._cmb_ant.setCurrentIndex(idx)
        self._current_antenna = current
        self._cmb_ant.blockSignals(False)

    def set_antenna_results(self, name: str, results: dict):
        """存储某个天线的 results 并切换显示。"""
        self._antenna_results[name] = results
        if name == self._current_antenna:
            import copy
            self.load_data(copy.deepcopy(results), self._step_deg)

    def _on_antenna_changed(self, idx: int):
        """图表查看器天线切换 → 加载对应数据。"""
        if idx < 0:
            return
        name = self._cmb_ant.itemText(idx)
        self._current_antenna = name
        results = self._antenna_results.get(name)
        if results:
            import copy
            self.load_data(copy.deepcopy(results), self._step_deg)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        # 单行主工具栏: 视角预设 + 视图模式 + 频点 + 设置按钮
        layout.addWidget(self._build_advanced_toolbar())
        # 2D Cuts 控制栏 (默认隐藏)
        layout.addWidget(self._build_2d_cuts_bar())
        # 隐藏控件仍在 _build_advanced_toolbar 中创建(保持信号连接)
        self._init_hidden_controls()
        self._splitter, self._figure, self._canvas, self._table = self._build_graph_area()
        layout.addWidget(self._splitter, stretch=1)

    def _build_2d_cuts_bar(self) -> QWidget:
        """2D Cuts 模式工具栏: 频点范围+自定义 + θ角度 + 数据源 + 类型。"""
        w = QWidget()
        w.setObjectName("cuts2dBar")
        w.setVisible(False)
        self._cuts2d_bar = w
        lay = QVBoxLayout(w)
        lay.setContentsMargins(4, 2, 4, 2)
        lay.setSpacing(4)

        # Row 1: 频点选择 (范围滑块 + 自定义)
        freq_row = QHBoxLayout()
        freq_row.addWidget(QLabel("频点:"))
        self._spin_freq_from = QSpinBox()
        self._spin_freq_from.setRange(0, 20000); self._spin_freq_from.setSuffix(" MHz")
        self._spin_freq_from.setFixedWidth(100)
        self._spin_freq_from.valueChanged.connect(self._on_freq_range_changed)
        freq_row.addWidget(self._spin_freq_from)
        freq_row.addWidget(QLabel("–"))
        self._spin_freq_to = QSpinBox()
        self._spin_freq_to.setRange(0, 20000); self._spin_freq_to.setSuffix(" MHz")
        self._spin_freq_to.setFixedWidth(100)
        self._spin_freq_to.valueChanged.connect(self._on_freq_range_changed)
        freq_row.addWidget(self._spin_freq_to)
        self._spin_step_freq = QSpinBox()
        self._spin_step_freq.setRange(1, 1000); self._spin_step_freq.setValue(1)
        self._spin_step_freq.setPrefix("步:"); self._spin_step_freq.setSuffix("MHz")
        self._spin_step_freq.setFixedWidth(80)
        self._spin_step_freq.valueChanged.connect(self._on_freq_range_changed)
        freq_row.addWidget(self._spin_step_freq)
        btn_custom_freq = QPushButton("自定义...")
        btn_custom_freq.setFixedWidth(70)
        btn_custom_freq.clicked.connect(self._show_freq_picker)
        freq_row.addWidget(btn_custom_freq)
        self._lbl_freq_count = QLabel("")
        freq_row.addWidget(self._lbl_freq_count)
        freq_row.addStretch()
        lay.addLayout(freq_row)

        # Row 2: 角度选择 + 数据源 + 类型
        angle_row = QHBoxLayout()
        angle_row.addWidget(QLabel("θ:"))
        btn_theta = QPushButton("⚙ 角度...")
        btn_theta.setFixedWidth(80)
        btn_theta.clicked.connect(lambda: self._show_2d_angle_picker("theta"))
        angle_row.addWidget(btn_theta)
        self._lbl_theta_angles = QLabel("")
        self._lbl_theta_angles.setStyleSheet("color: #4472C4;")
        angle_row.addWidget(self._lbl_theta_angles)

        angle_row.addWidget(QLabel("  φ:"))
        btn_phi = QPushButton("⚙ 角度...")
        btn_phi.setFixedWidth(80)
        btn_phi.clicked.connect(lambda: self._show_2d_angle_picker("phi"))
        angle_row.addWidget(btn_phi)
        self._lbl_phi_angles = QLabel("")
        self._lbl_phi_angles.setStyleSheet("color: #4472C4;")
        angle_row.addWidget(self._lbl_phi_angles)

        angle_row.addWidget(QLabel("  数据源:"))
        self._cmb_2d_data = QComboBox()
        self._cmb_2d_data.setEditable(True)
        self._cmb_2d_data.setInsertPolicy(QComboBox.NoInsert)
        self._cmb_2d_data.lineEdit().setPlaceholderText("搜索...")
        self._cmb_2d_data.addItems(["Gain", "AR", "E_θ", "E_φ", "RHCP", "LHCP", "CP-XPI"])
        self._cmb_2d_data.currentIndexChanged.connect(self._on_2d_cuts_update)
        angle_row.addWidget(self._cmb_2d_data)

        angle_row.addWidget(QLabel("类型:"))
        self._cmb_2d_type = QComboBox()
        self._cmb_2d_type.setEditable(True)
        self._cmb_2d_type.setInsertPolicy(QComboBox.NoInsert)
        self._cmb_2d_type.lineEdit().setPlaceholderText("搜索...")
        self._cmb_2d_type.addItems(["Polar", "Rectangular"])
        self._cmb_2d_type.currentIndexChanged.connect(self._on_2d_cuts_update)
        angle_row.addWidget(self._cmb_2d_type)
        angle_row.addStretch()
        lay.addLayout(angle_row)

        # 2D cuts state
        self._2d_freqs: list[float] = []
        self._2d_theta_angles: list[float] = []
        self._2d_phi_angles: list[float] = [0]  # default

        return w

    def _on_freq_range_changed(self):
        """Range slider → rebuild frequency list."""
        f0, f1 = self._spin_freq_from.value(), self._spin_freq_to.value()
        step = self._spin_step_freq.value()
        if f0 <= f1 and step > 0:
            self._2d_freqs = list(range(f0, f1 + 1, step))
            self._lbl_freq_count.setText(f"({len(self._2d_freqs)}个)")
            self._on_2d_cuts_update()

    def _show_freq_picker(self):
        """弹出频点勾选对话框。"""
        if not self._graph_data:
            return
        all_freqs = sorted(self._graph_data.keys())
        dlg = QDialog(self)
        dlg.setWindowTitle("选择频点")
        dlg.setMinimumSize(300, 400)
        layout = QVBoxLayout(dlg)
        search = QLineEdit(); search.setPlaceholderText("搜索频点..."); layout.addWidget(search)
        checks = {}
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        cw = QWidget(); cl = QVBoxLayout(cw)
        for f in all_freqs:
            cb = QCheckBox(f"{f:.0f} MHz")
            cb.setChecked(f in self._2d_freqs)
            cl.addWidget(cb); checks[f] = cb
        scroll.setWidget(cw); layout.addWidget(scroll)
        search.textChanged.connect(lambda t: [cb.setVisible(t in cb.text()) for cb in checks.values()])

        btn_row = QHBoxLayout()
        btn_all = QPushButton("全选"); btn_all.clicked.connect(lambda: [cb.setChecked(True) for cb in checks.values()])
        btn_none = QPushButton("清空"); btn_none.clicked.connect(lambda: [cb.setChecked(False) for cb in checks.values()])
        btn_row.addWidget(btn_all); btn_row.addWidget(btn_none); btn_row.addStretch()
        layout.addLayout(btn_row)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(lambda: (
            self._2d_freqs.clear(),
            [self._2d_freqs.append(f) for f in all_freqs if checks[f].isChecked()],
            self._lbl_freq_count.setText(f"({len(self._2d_freqs)}个)"),
            self._on_2d_cuts_update(),
            dlg.accept()))
        btns.rejected.connect(dlg.reject)
        layout.addWidget(btns)
        dlg.exec()

    def _show_2d_angle_picker(self, axis: str):
        """弹出 AnglePicker 选择 theta 或 phi 角度。"""
        dlg = QDialog(self)
        dlg.setWindowTitle(f"选择 {axis.upper()} 角度")
        dlg.setMinimumSize(400, 300)
        layout = QVBoxLayout(dlg)
        spin = QDoubleSpinBox(); spin.setRange(0, 360); spin.setValue(0); spin.setSuffix("°")
        add_btn = QPushButton("+ 添加")
        angles = list(self._2d_theta_angles if axis == "theta" else self._2d_phi_angles)
        tags_layout = QHBoxLayout()

        def _refresh_tags():
            while tags_layout.count():
                item = tags_layout.takeAt(0)
                if item.widget(): item.widget().deleteLater()
            for a in sorted(set(angles)):
                tag = QWidget()
                tl = QHBoxLayout(tag); tl.setContentsMargins(2,1,2,1)
                tl.addWidget(QLabel(f"{a:.0f}°"))
                btn_del = QPushButton("×"); btn_del.setFixedSize(18,18)
                btn_del.clicked.connect(lambda checked, v=a: (angles.remove(v), _refresh_tags()))
                tl.addWidget(btn_del); tags_layout.addWidget(tag)
            tags_layout.addStretch()

        row = QHBoxLayout(); row.addWidget(spin); row.addWidget(add_btn)
        add_btn.clicked.connect(lambda: (angles.append(spin.value()), _refresh_tags()))
        layout.addLayout(row); layout.addLayout(tags_layout)
        _refresh_tags()

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(lambda: (
            (self._2d_theta_angles if axis == "theta" else self._2d_phi_angles).clear(),
            (self._2d_theta_angles if axis == "theta" else self._2d_phi_angles).extend(sorted(set(angles))),
            self._update_angle_labels(),
            self._on_2d_cuts_update(),
            dlg.accept()))
        btns.rejected.connect(dlg.reject)
        layout.addWidget(btns)
        dlg.exec()

    def _update_angle_labels(self):
        self._lbl_theta_angles.setText(", ".join(f"{a:.0f}°" for a in self._2d_theta_angles[:5])
                                       + (f" +{len(self._2d_theta_angles)-5}" if len(self._2d_theta_angles) > 5 else ""))
        self._lbl_phi_angles.setText(", ".join(f"{a:.0f}°" for a in self._2d_phi_angles[:5])
                                     + (f" +{len(self._2d_phi_angles)-5}" if len(self._2d_phi_angles) > 5 else ""))

    def _build_advanced_toolbar(self) -> QWidget:
        """单行主工具栏：视角预设 + 视图模式 + 频点选择 + ⚙ 设置。"""
        w = QWidget()
        w.setObjectName("graphCtrlBar")
        lay = QHBoxLayout(w)
        lay.setContentsMargins(4, 2, 4, 2)
        lay.setSpacing(6)

        # ── 视角预设 (下拉) + el/az/roll 数值框 ──
        lay.addWidget(QLabel("视角:"))
        self._cmb_preset = QComboBox()
        self._cmb_preset.addItems(list(VIEW_PRESETS.keys()))
        self._cmb_preset.setFixedWidth(72)
        self._cmb_preset.setToolTip("7 视角预设 (Iso/上下左右前后)")
        self._cmb_preset.currentIndexChanged.connect(self._on_view_preset_changed)
        lay.addWidget(self._cmb_preset)

        self._spin_elev = QDoubleSpinBox()
        self._spin_elev.setRange(-90, 90); self._spin_elev.setValue(30)
        self._spin_elev.setPrefix("el "); self._spin_elev.setSuffix("°")
        self._spin_elev.setFixedWidth(80)
        self._spin_elev.valueChanged.connect(self._apply_view_spins)
        lay.addWidget(self._spin_elev)
        self._spin_azim = QDoubleSpinBox()
        self._spin_azim.setRange(-180, 360); self._spin_azim.setValue(-60)
        self._spin_azim.setPrefix("az "); self._spin_azim.setSuffix("°")
        self._spin_azim.setFixedWidth(84)
        self._spin_azim.valueChanged.connect(self._apply_view_spins)
        lay.addWidget(self._spin_azim)
        self._spin_roll = QDoubleSpinBox()
        self._spin_roll.setRange(-180, 360); self._spin_roll.setValue(0)
        self._spin_roll.setPrefix("roll "); self._spin_roll.setSuffix("°")
        self._spin_roll.setFixedWidth(92)
        self._spin_roll.valueChanged.connect(self._apply_view_spins)
        lay.addWidget(self._spin_roll)

        sep = QFrame(); sep.setFrameShape(QFrame.VLine); lay.addWidget(sep)

        # ── 图型 (作用于选中子图, 联动时作用全部) ──
        lay.addWidget(QLabel("图型:"))
        self._cmb_plot_type = QComboBox()
        self._cmb_plot_type.addItems(PLOT_TYPES)
        self._cmb_plot_type.setFixedWidth(112)
        self._cmb_plot_type.setToolTip("3D曲面 / 极坐标2D切面 / 直角3D — 作用于点选的子图")
        self._cmb_plot_type.currentIndexChanged.connect(self._on_toolbar_plot_type)
        lay.addWidget(self._cmb_plot_type)

        # ── 联动 / 分别控制 ──
        self._chk_view_link = QCheckBox("联动")
        self._chk_view_link.setChecked(True)
        self._chk_view_link.setToolTip("联动: 视角/图型作用所有子图; 取消: 仅作用点选的子图")
        self._chk_view_link.toggled.connect(self._on_view_link_toggled)
        lay.addWidget(self._chk_view_link)

        sep_v = QFrame(); sep_v.setFrameShape(QFrame.VLine); lay.addWidget(sep_v)

        # ── 视图模式 ──
        lay.addWidget(QLabel("视图:"))
        self._cmb_view_mode = QComboBox()
        self._cmb_view_mode.setEditable(True)
        self._cmb_view_mode.setInsertPolicy(QComboBox.NoInsert)
        self._cmb_view_mode.lineEdit().setPlaceholderText("搜索...")
        self._cmb_view_mode.addItems(["3D Pattern", "Freq Curves", "2D Cuts"])
        self._cmb_view_mode.currentIndexChanged.connect(self._on_view_mode_changed)
        lay.addWidget(self._cmb_view_mode)

        # ── 频点选择 (可输入搜索) ──
        lay.addWidget(QLabel("频点:"))
        self._cmb_freq = QComboBox()
        self._cmb_freq.setEditable(True)
        self._cmb_freq.setInsertPolicy(QComboBox.NoInsert)
        self._cmb_freq.lineEdit().setPlaceholderText("搜索或选择频点...")
        self._cmb_freq.currentIndexChanged.connect(self._on_update)
        lay.addWidget(self._cmb_freq)

        # ── 双Y轴 (自动/手动) ──
        self._cmb_dual_y = QComboBox()
        self._cmb_dual_y.setEditable(True)
        self._cmb_dual_y.setInsertPolicy(QComboBox.NoInsert)
        self._cmb_dual_y.lineEdit().setPlaceholderText("搜索...")
        self._cmb_dual_y.addItems(["单Y轴", "双Y轴(自动)", "双Y轴(强制)"])
        self._cmb_dual_y.setToolTip(
            "双Y轴模式: 曲线单位/量级差异大时自动或强制启用左右双Y轴")
        self._cmb_dual_y.currentIndexChanged.connect(self._on_update)
        lay.addWidget(self._cmb_dual_y)

        sep2 = QFrame(); sep2.setFrameShape(QFrame.VLine); lay.addWidget(sep2)

        # ── 设置按钮 ──
        btn_settings = QPushButton("⚙ 设置")
        btn_settings.setToolTip("图形显示设置: 色图/导出/布局/精度/类型/切面/动画")
        btn_settings.clicked.connect(self._show_viewer_settings)
        lay.addWidget(btn_settings)

        # ── 测试模式标签 ──
        self._lbl_mode = QLabel("")
        self._lbl_mode.setStyleSheet("color: #888; font-style: italic;")
        lay.addWidget(self._lbl_mode)

        # ── 天线选择 ──
        sep3 = QFrame(); sep3.setFrameShape(QFrame.VLine); lay.addWidget(sep3)
        lay.addWidget(QLabel("天线:"))
        self._cmb_ant = QComboBox()
        self._cmb_ant.setMinimumWidth(100)
        self._cmb_ant.setToolTip("选择查看的天线数据")
        self._cmb_ant.currentIndexChanged.connect(self._on_antenna_changed)
        lay.addWidget(self._cmb_ant)
        self._check_ant_link = QCheckBox("联动")
        self._check_ant_link.setChecked(True)
        self._check_ant_link.setToolTip("跟随主天线选择器")
        lay.addWidget(self._check_ant_link)
        self._antenna_list: list[str] = []
        self._antenna_results: dict[str, dict] = {}
        self._current_antenna: str = ""

        # ── 右侧信息 ──
        lay.addStretch()
        self._lbl_zoom = QLabel("100%")
        lay.addWidget(self._lbl_zoom)

        return w

    def _init_hidden_controls(self):
        """创建隐藏控件 — 保持信号连接，通过 ⚙ 设置对话框控制。"""
        # 色图选择
        self._cmb_cmap = QComboBox()
        self._cmb_cmap.addItems(["jet", "viridis", "plasma", "inferno", "magma", "cividis",
                                  "turbo", "hot", "coolwarm", "rainbow"])
        self._cmb_cmap.setCurrentText("jet")
        self._cmb_cmap.currentTextChanged.connect(self._on_cmap_changed)
        self._cmb_cmap.hide()

        # 布局
        self._cmb_grid = QComboBox()
        self._cmb_grid.addItems(GRID_OPTIONS)
        self._cmb_grid.setCurrentIndex(2)
        self._cmb_grid.currentIndexChanged.connect(self._on_grid_changed)
        self._cmb_grid.hide()

        # 精度
        self._spin_step = QSpinBox()
        self._spin_step.setRange(1, 30); self._spin_step.setValue(5)
        self._spin_step.setSuffix("°"); self._spin_step.setFixedWidth(70)
        self._spin_step.valueChanged.connect(self._on_step_changed)
        self._spin_step.hide()

        # 联动视角
        self._chk_link = QCheckBox("联动视角")
        self._chk_link.setChecked(True)
        self._chk_link.toggled.connect(self._on_link_toggled)
        self._chk_link.hide()

        # 子图类型 / 信息标签 (per-子图下拉已取代旧的 _plot_type_layout)
        if not hasattr(self, '_lbl_info') or self._lbl_info is None:
            self._lbl_info = QLabel("")

        # 剖切
        self._cut_checks: Dict[str, QCheckBox] = {}
        for lbl in ["X-Z", "Y-Z", "X-Y"]:
            cb = QCheckBox(lbl)
            cb.toggled.connect(self._on_cut_changed)
            self._cut_checks[lbl] = cb
            cb.hide()

        # Theta 截面
        self._slider_theta = QSlider(Qt.Horizontal)
        self._slider_theta.setMinimum(0); self._slider_theta.setMaximum(0)
        self._slider_theta.setFixedWidth(120)
        self._slider_theta.valueChanged.connect(self._on_theta_slider_changed)
        self._slider_theta.hide()
        self._lbl_theta_val = QLabel("--°")
        self._lbl_theta_val.setFixedWidth(40); self._lbl_theta_val.hide()

        # 动画 — 重新创建 (清除 init 中的旧引用)
        if hasattr(self, '_anim_timer') and self._anim_timer is not None:
            self._anim_timer.stop()
        self._anim_timer = QTimer(self)
        self._anim_timer.timeout.connect(self._on_anim_tick)
        self._anim_playing = False
        self._btn_play = QPushButton("▶ 播放")
        self._btn_play.setFixedWidth(80)
        self._btn_play.clicked.connect(self._on_play_pause)
        self._btn_play.hide()
        self._slider_speed = QSlider(Qt.Horizontal)
        self._slider_speed.setMinimum(1); self._slider_speed.setMaximum(10)
        self._slider_speed.setValue(5); self._slider_speed.setFixedWidth(100)
        self._slider_speed.valueChanged.connect(self._on_speed_changed)
        self._slider_speed.hide()
        self._lbl_speed_val = QLabel("600ms"); self._lbl_speed_val.setFixedWidth(50)
        self._lbl_speed_val.hide()
        self._lbl_anim_progress = QLabel("0 / 0")
        self._lbl_anim_progress.hide()

    # ==================================================================
    # 视角控制 (工具栏: 预设下拉 + el/az/roll 数值 + 图型 + 联动)
    # ==================================================================

    def _view_targets(self):
        """联动 → 所有子图; 分别控制 → 仅点选的子图。"""
        if self._linked or not self._subplots:
            return self._subplots
        idx = min(getattr(self, '_selected_idx', 0), len(self._subplots) - 1)
        return [self._subplots[idx]]

    def _on_view_preset_changed(self):
        name = self._cmb_preset.currentText()
        if name not in VIEW_PRESETS:
            return
        el, az, rl = VIEW_PRESETS[name]
        self._suppress_view = True
        self._spin_elev.setValue(el); self._spin_azim.setValue(az); self._spin_roll.setValue(rl)
        self._suppress_view = False
        self._apply_view_spins()

    def _apply_view_spins(self):
        """数值框变化 → 作用于目标子图 (联动全部 / 分别选中)。"""
        if getattr(self, '_suppress_view', False):
            return
        el = self._spin_elev.value(); az = self._spin_azim.value(); rl = self._spin_roll.value()
        for sp in self._view_targets():
            sp.set_view(el, az, rl)
        self._elev, self._azim = el, az
        if hasattr(self, '_lbl_zoom'):
            self._lbl_zoom.setText(f" el={el:.0f}° az={az:.0f}° roll={rl:.0f}°")
        self._canvas.draw_idle()

    def _on_view_link_toggled(self, checked):
        self._linked = checked
        if hasattr(self, '_chk_link'):
            self._chk_link.setChecked(checked)   # 保持隐藏控件同步

    def _on_toolbar_plot_type(self):
        pt = self._cmb_plot_type.currentText()
        for sp in self._view_targets():
            sp.set_plot_type(pt)
        self._on_update()

    def _sync_spins_to_selected(self):
        """点选子图后, 工具栏数值框回填该子图当前视角。"""
        if not self._subplots:
            return
        sp = self._subplots[min(getattr(self, '_selected_idx', 0), len(self._subplots) - 1)]
        self._suppress_view = True
        self._spin_elev.setValue(sp._elev)
        self._spin_azim.setValue(sp._azim)
        self._spin_roll.setValue(sp._roll)
        self._suppress_view = False

    # ==================================================================
    # per-子图数据类型叠加下拉 (Q1) + 点选子图 (Q2)
    # ==================================================================

    def _available_data_keys(self) -> List[str]:
        """当前数据实际可用的方向图类型 key (按注册顺序)。无数据 → 全部默认。"""
        if not self._graph_data:
            return list(DEFAULT_PATTERN_KEYS)
        fd0 = next(iter(self._graph_data.values()))
        avail = [k for k in DEFAULT_PATTERN_KEYS if fd0.get(k) is not None]
        return avail or list(DEFAULT_PATTERN_KEYS)

    def _rebuild_subplot_overlays(self):
        """重建每个子图左上角的数据类型下拉 (parented to canvas, draw_event 定位)。"""
        for c in self._ov_combos:
            c.setParent(None); c.deleteLater()
        self._ov_combos = []
        avail = self._available_data_keys()
        for i, sp in enumerate(self._subplots):
            c = QComboBox(self._canvas)
            for k in avail:
                c.addItem(PATTERN_DATA_MAP.get(k, k), k)
            j = c.findData(sp.data_key)
            c.setCurrentIndex(j if j >= 0 else 0)
            c.setFixedWidth(118)
            c.setToolTip("选择此子图显示的数据类型")
            c.currentIndexChanged.connect(lambda _=0, idx=i: self._on_overlay_type_changed(idx))
            c.show()
            self._ov_combos.append(c)
        self._reposition_overlays()

    def _on_overlay_type_changed(self, idx: int):
        if idx >= len(self._subplots) or idx >= len(self._ov_combos):
            return
        dk = self._ov_combos[idx].currentData()
        if dk is None:
            return
        sp = self._subplots[idx]
        sp.data_key = dk
        sp.title = PATTERN_DATA_MAP.get(dk, dk)
        self._on_update()

    def _reposition_overlays(self, event=None):
        """draw_event 后按各子图 axes 位置摆放叠加下拉 (自动适配缩放/分隔条)。"""
        if not self._ov_combos:
            return
        w = self._canvas.width(); h = self._canvas.height()
        for sp, c in zip(self._subplots, self._ov_combos):
            try:
                bb = sp.ax.get_position()
            except Exception:
                continue
            x = int(bb.x0 * w)
            y = int((1.0 - bb.y1) * h)
            c.move(max(0, x), max(0, y))
            c.raise_()

    def _set_overlays_visible(self, vis: bool):
        for c in self._ov_combos:
            c.setVisible(vis)

    def _on_canvas_click(self, event):
        """点选子图 → 高亮 + 回填工具栏数值 (分别控制时的目标)。"""
        if event.inaxes is None or not self._subplots:
            return
        for i, sp in enumerate(self._subplots):
            if sp.ax is event.inaxes:
                self._selected_idx = i
                for j, s in enumerate(self._subplots):
                    s.selected = (j == i)
                    if s.ax is not None and hasattr(s.ax, "title"):
                        s.ax.title.set_color("#ffd700" if s.selected else
                                             ("black" if s._plot_type == "Polar 2D" else "white"))
                self._sync_spins_to_selected()
                self._canvas.draw_idle()
                break

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


    @staticmethod
    def _build_graph_area():
        splitter = QSplitter(Qt.Horizontal)
        fig = Figure(figsize=(7, 7), dpi=80, facecolor="black")
        canvas = FigureCanvas(fig)
        canvas.setStyleSheet("background-color: black;")
        table = QTableWidget()
        table.setMinimumWidth(220)
        table.setStyleSheet("background-color: #1e1e1e; color: #ddd; gridline-color: #444;")
        splitter.addWidget(canvas)
        splitter.addWidget(table)
        splitter.setSizes([650, 250])
        return splitter, fig, canvas, table

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
        # 保存旧子图的视角 (按 data_key 索引, 含 roll)
        old_views = {sp.data_key: (sp._elev, sp._azim, sp._roll) for sp in self._subplots}
        self._figure.clear()
        self._subplots = []
        grid = self._cmb_grid.currentText()
        if grid == "2×2+1":
            self._rebuild_2x2plus1(old_views)
        else:
            rows, cols = self._grid_dims()
            keys = self._active_pattern_keys[:rows * cols]
            for i, dk in enumerate(keys):
                self._add_subplot((rows, cols, i + 1), dk, old_views)
        # 恢复选中高亮 (索引可能越界 → 收敛到 0)
        if self._subplots:
            self._selected_idx = min(self._selected_idx, len(self._subplots) - 1)
            self._subplots[self._selected_idx].selected = True
        self._rebuild_subplot_overlays()
        self._canvas.draw()

    def _add_subplot(self, pos, dk, old_views):
        """在指定位置(rows,cols,idx 元组 或 GridSpec spec 单元组)加一个子图。"""
        title = PATTERN_DATA_MAP.get(dk, dk)
        sp = SubPlotPanel(self._figure, pos, title=title, data_key=dk)
        ev, az, rl = old_views.get(dk, (self._elev, self._azim, 0))
        sp.set_view(ev, az, rl)
        self._subplots.append(sp)

    def _rebuild_2x2plus1(self, old_views):
        """特殊布局: 2×2 (θLog/θPhase/φLog/φPhase) + Total Power 右列跨两格 (EMQuest 风格)。"""
        from matplotlib.gridspec import GridSpec
        gs = GridSpec(2, 3, figure=self._figure)
        layout = [(gs[0, 0], "theta_db"), (gs[0, 1], "theta_phase"),
                  (gs[1, 0], "phi_db"), (gs[1, 1], "phi_phase"),
                  (gs[0:2, 2], "total_power")]
        for spec, dk in layout:
            self._add_subplot((spec,), dk, old_views)

    def _grid_dims(self):
        mapping = {"1×1": (1, 1), "1×2": (1, 2), "2×2": (2, 2),
                   "3×3": (3, 3), "2×2+1": (2, 3)}
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
        if self._cmb_view_mode.currentText() == "2D Cuts":
            self._plot_2d_cuts()
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
                lbl_3d_count.setStyleSheet("font-weight: bold; color: #e67e22;")
            else:
                lbl_3d_count.setStyleSheet("")

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

        # ═══ 显示选项 ═══
        grp_display = QGroupBox("显示选项")
        disp_layout = QHBoxLayout(grp_display)
        # 色图
        disp_layout.addWidget(QLabel("色图:"))
        cmb_cmap = QComboBox()
        cmb_cmap.addItems(["jet", "viridis", "plasma", "inferno", "magma", "cividis",
                           "turbo", "hot", "coolwarm", "rainbow"])
        cmb_cmap.setCurrentText(self._cmb_cmap.currentText())
        cmb_cmap.setFixedWidth(100)
        disp_layout.addWidget(cmb_cmap)
        disp_layout.addSpacing(12)
        # 联动视角
        chk_link = QCheckBox("联动视角")
        chk_link.setChecked(self._chk_link.isChecked())
        disp_layout.addWidget(chk_link)
        # 导出
        btn_export = QPushButton("💾 导出视图...")
        btn_export.clicked.connect(self._on_export_view)
        disp_layout.addWidget(btn_export)
        disp_layout.addStretch()
        layout.addWidget(grp_display)

        # ═══ 子图类型 & 剖切 ═══
        grp_cuts = QGroupBox("子图类型 & 剖切")
        cuts_layout = QHBoxLayout(grp_cuts)
        cuts_layout.addWidget(QLabel("类型:"))
        plot_type_combos = []
        for sp in self._subplots:
            combo = QComboBox()
            combo.addItems(PLOT_TYPES)
            combo.setCurrentText(sp._plot_type)
            short = sp.title.split("(")[0].strip()
            cuts_layout.addWidget(QLabel(short + ":"))
            cuts_layout.addWidget(combo)
            plot_type_combos.append(combo)
        cuts_layout.addSpacing(12)
        cuts_layout.addWidget(QLabel("剖切:"))
        cut_checks_dlg = {}
        for lbl in ["X-Z", "Y-Z", "X-Y"]:
            cb = QCheckBox(lbl)
            cb.setChecked(self._cut_checks[lbl].isChecked())
            cut_checks_dlg[lbl] = cb
            cuts_layout.addWidget(cb)
        cuts_layout.addStretch()
        layout.addWidget(grp_cuts)

        # ═══ 动画 ═══
        grp_anim = QGroupBox("频点动画")
        anim_layout = QHBoxLayout(grp_anim)
        btn_play = QPushButton(self._btn_play.text())
        btn_play.setFixedWidth(80)
        btn_play.clicked.connect(self._on_play_pause)
        anim_layout.addWidget(btn_play)
        anim_layout.addWidget(QLabel("速度:"))
        slider_speed = QSlider(Qt.Horizontal)
        slider_speed.setMinimum(1); slider_speed.setMaximum(10)
        slider_speed.setValue(self._slider_speed.value())
        slider_speed.setFixedWidth(100)
        anim_layout.addWidget(slider_speed)
        anim_layout.addStretch()
        layout.addWidget(grp_anim)

        # ═══ 按钮 ═══
        layout.addStretch()
        def _on_accept():
            # 更新方向图类型
            self._active_pattern_keys = [dk for dk, cb in key_checkboxes.items() if cb.isChecked()]
            # 更新频率曲线选择
            self._active_freq_curve_indices = [i for i, cb in enumerate(curve_checkboxes) if cb.isChecked()]
            # 更新布局
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
            # 更新色图
            self._cmb_cmap.setCurrentText(cmb_cmap.currentText())
            # 更新联动
            self._chk_link.setChecked(chk_link.isChecked())
            # 更新子图类型
            for sp, combo in zip(self._subplots, plot_type_combos):
                sp.set_plot_type(combo.currentText())
            # 更新剖切
            for lbl, cb in cut_checks_dlg.items():
                self._cut_checks[lbl].setChecked(cb.isChecked())
            # 更新动画速度
            self._slider_speed.setValue(slider_speed.value())
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
        # 停止动画定时器，防止旧数据残余
        if self._anim_timer.isActive():
            self._anim_timer.stop()
            self._anim_playing = False
            self._btn_play.setText("▶ 播放")
        self._results = results
        self._step_deg = step_deg
        self._graph_data = extract_graph_data(results, step_deg)
        # 验证可配置状态在新数据中的有效性（取第一个频点的 keys 即可，所有频点 keys 相同）
        fd0 = next(iter(self._graph_data.values()), {})
        available_keys = fd0.keys() - {"theta", "phi"}
        self._active_pattern_keys = [k for k in self._active_pattern_keys if k in available_keys]
        if not self._active_pattern_keys:
            self._active_pattern_keys = list(DEFAULT_PATTERN_KEYS)
        freq_count = len(self._graph_data)
        if freq_count > 0:
            self._active_freq_curve_indices = [i for i in self._active_freq_curve_indices if i < freq_count]
        self._spin_step.blockSignals(True)
        self._spin_step.setValue(int(step_deg))
        self._spin_step.blockSignals(False)
        # 用 blockSignals 防止 setCurrentIndex 触发 _on_update（此时 _subplots 还是旧的）
        self._cmb_freq.blockSignals(True)
        self._cmb_freq.clear()
        for f in sorted(self._graph_data.keys()):
            self._cmb_freq.addItem(f"{f:.1f} MHz", f)
        if self._cmb_freq.count() > 0:
            self._cmb_freq.setCurrentIndex(0)
        self._cmb_freq.blockSignals(False)
        # 初始化 2D Cuts 频点范围和 θ 角度
        freqs = sorted(self._graph_data.keys())
        if freqs:
            self._spin_freq_from.setValue(int(freqs[0]))
            self._spin_freq_to.setValue(int(freqs[-1]))
            self._2d_freqs = list(freqs)
            self._lbl_freq_count.setText(f"({len(freqs)}个)")
        # 默认 θ = 0°, φ = 0°
        if not self._2d_theta_angles:
            self._2d_theta_angles = [0.0]
        if not self._2d_phi_angles:
            self._2d_phi_angles = [0.0]
        self._update_angle_labels()

        self._rebuild_subplots()
        self._on_update()

    # ==================================================================
    # 视图模式切换
    # ==================================================================

    def _on_view_mode_changed(self, index):
        mode = self._cmb_view_mode.currentText()
        is_pattern = (mode == "3D Pattern")
        is_2d = (mode == "2D Cuts")
        # 显示/隐藏 2D Cuts 控制栏
        if hasattr(self, '_cuts2d_bar'):
            self._cuts2d_bar.setVisible(is_2d)
        # per-子图叠加下拉仅在 3D Pattern 模式显示
        self._set_overlays_visible(is_pattern)
        if is_pattern:
            self._rebuild_subplots()
            self._on_update()
        elif is_2d:
            self._plot_2d_cuts()
        else:
            self._plot_freq_curves()

    # ── 2D Cuts 模式 ──

    def _on_2d_cuts_update(self):
        """2D Cuts 控件变化 → 重新绘制。"""
        if self._cmb_view_mode.currentText() == "2D Cuts":
            self._plot_2d_cuts()

    def _plot_2d_cuts(self):
        """2D Cuts 主绘制: 多频点 × 多角度 × 多数据源 × 两种切面方向。"""
        freqs = self._2d_freqs if self._2d_freqs else list(self._graph_data.keys())[:1]
        theta_angles = self._2d_theta_angles if self._2d_theta_angles else [0]
        phi_angles = self._2d_phi_angles if self._2d_phi_angles else [0]
        source_key = self._cmb_2d_data.currentText()
        is_polar = self._cmb_2d_type.currentText() == "Polar"
        is_theta_cut = hasattr(self, '_cmb_2d_dir') and "Theta" in self._cmb_2d_dir.currentText()

        # 数据源映射
        data_map = {
            "Gain": "gain_db", "AR": "ar_linear", "E_θ": "theta_db", "E_φ": "phi_db",
            "RHCP": "rhcp_db", "LHCP": "lhcp_db", "CP-XPI": "cpxpi_db",
        }
        data_key = data_map.get(source_key, "gain_db")

        # 清除旧图
        for ax in list(self._figure.axes):
            self._figure.delaxes(ax)

        ax = self._figure.add_subplot(111, projection="polar" if is_polar else None)
        colors = plt.cm.tab10.colors if hasattr(plt, 'cm') else None

        ci = 0
        for freq in freqs:
            if freq not in self._graph_data:
                continue
            d = self._graph_data[freq]
            theta_arr = d.get("theta"); phi_arr = d.get("phi")
            if theta_arr is None or phi_arr is None:
                continue
            cut_data = d.get(data_key, d.get("gain_db"))
            if cut_data is None:
                continue

            if is_theta_cut:
                # Theta切面: 固定θ, 扫描φ — 需要绘制多条θ曲线
                for th in theta_angles:
                    th_idx = int(np.argmin(np.abs(theta_arr - th)))
                    nearest_th = float(theta_arr[th_idx])
                    cut = cut_data[:, th_idx]
                    if source_key == "AR":
                        cut = 20.0 * np.log10(np.maximum(cut, 1e-15))
                    color = colors[ci % len(colors)] if colors is not None else None
                    label = f"{freq:.0f}MHz θ={nearest_th:.0f}°"
                    if is_polar:
                        phi_rad = np.deg2rad(phi_arr)
                        ax.plot(phi_rad, cut, label=label, color=color)
                        ax.set_theta_zero_location("N"); ax.set_theta_direction(-1)
                    else:
                        ax.plot(phi_arr, cut, label=label, color=color)
                        ax.set_xlabel("φ (°)")
                    ci += 1
            else:
                # Phi切面: 固定φ, 扫描θ
                for ph in phi_angles:
                    ph_idx = int(np.argmin(np.abs(phi_arr - ph)))
                    nearest_ph = float(phi_arr[ph_idx])
                    cut = cut_data[ph_idx, :]
                    if source_key == "AR":
                        cut = 20.0 * np.log10(np.maximum(cut, 1e-15))
                    color = colors[ci % len(colors)] if colors is not None else None
                    label = f"{freq:.0f}MHz φ={nearest_ph:.0f}°"
                    if is_polar:
                        theta_rad = np.deg2rad(theta_arr)
                        ax.plot(theta_rad, cut, label=label, color=color)
                        ax.set_theta_zero_location("N"); ax.set_theta_direction(-1)
                    else:
                        ax.plot(theta_arr, cut, label=label, color=color)
                        ax.set_xlabel("θ (°)")
                    ci += 1

        ax.set_title(f"{source_key} — 2D Cut", fontsize=9)
        if ci > 1:
            ax.legend(fontsize=7, loc='upper right')
        self._canvas.draw()

    def _get_available_freq_curves(self):
        """返回可用的频率曲线列表: [(label, actual_key), ...]."""
        if not self._results:
            return []
        all_keys = set()
        for rows in self._results.values():
            for row in rows:
                all_keys.update(row.keys())

        mode = self.get_mode()
        curves = get_freq_curves_for_mode(mode)
        available = []
        for label, key_prefix, match_mode in curves:
            if match_mode == "prefix":
                found = [k for k in all_keys if k.startswith(key_prefix)]
                if found:
                    available.append((label, found[0]))
            else:
                if key_prefix in all_keys:
                    available.append((label, key_prefix))
        return available

    def _plot_freq_curves(self):
        """绘制选中的频率曲线为 2D Cartesian 子图, 垂直堆叠。

        多段频率自动用 GridSpec 断轴 (与 Word 报告 render_freq_curve 一致)。
        """
        self._figure.clear()
        all_available = self._get_available_freq_curves()
        if not all_available:
            self._canvas.draw()
            self._lbl_info.setText("无频率曲线数据可用")
            return

        if self._active_freq_curve_indices:
            available = [all_available[i] for i in self._active_freq_curve_indices
                         if i < len(all_available)]
        else:
            available = all_available

        if not available:
            self._canvas.draw()
            self._lbl_info.setText("未选择任何频率曲线")
            return

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

        # 检测频段间隙 (与 renderer 一致: >30MHz)
        _gap_segments = []
        _seg_start = 0
        for i in range(1, len(freqs)):
            if freqs[i] - freqs[i-1] > 30.0:
                _gap_segments.append((_seg_start, i))
                _seg_start = i
        _gap_segments.append((_seg_start, len(freqs)))
        has_gap = len(_gap_segments) > 1

        # 双Y轴模式
        dual_mode = self._cmb_dual_y.currentIndex() if hasattr(self, '_cmb_dual_y') else 0
        _PCT_KEYS = {"efficiency_pct", "total_efficiency_pct"}

        if dual_mode == 0:
            # 单Y轴: 计算行数
            rows_count = n
            pairs_list = [(a, None, False) for a in available]
        else:
            pairs_list = []
            for i in range(0, n, 2):
                a = available[i]
                b = available[i + 1] if i + 1 < n else None
                need_dual = dual_mode == 2
                if dual_mode == 1 and b is not None:
                    va = [freq_data[f].get(a[1]) for f in freqs if freq_data[f].get(a[1]) is not None]
                    vb = [freq_data[f].get(b[1]) for f in freqs if freq_data[f].get(b[1]) is not None]
                    if va and vb:
                        ra = (max(va) - min(va)) or 1
                        rb = (max(vb) - min(vb)) or 1
                        if max(ra, rb) / min(ra, rb) > 50:
                            need_dual = True
                        if (a[1] in _PCT_KEYS) != (b[1] in _PCT_KEYS):
                            need_dual = True
                pairs_list.append((a, b, need_dual))
            rows_count = len(pairs_list)

        fig_height = max(3, rows_count * 2.5)
        self._figure.set_size_inches(8, fig_height, forward=True)

        import matplotlib.gridspec as gridspec
        ncols = len(_gap_segments) if has_gap else 1
        gs = gridspec.GridSpec(rows_count, ncols,
                               width_ratios=[1] * ncols,
                               wspace=0.05 if has_gap else 0.2,
                               hspace=0.35)

        for row_i, (a, b, need_dual) in enumerate(pairs_list):
            is_last = (row_i == rows_count - 1)

            if has_gap:
                ax_left = self._figure.add_subplot(gs[row_i, 0])
                ax_right = self._figure.add_subplot(gs[row_i, 1])
                if row_i > 0:
                    ax_right.sharey(ax_left)  # 同列不share, 同行可share
                # 隐藏相邻 spine + 断点标记
                ax_left.spines['right'].set_visible(False)
                ax_right.spines['left'].set_visible(False)
                d = 0.015
                kw = dict(transform=ax_left.transAxes, color='k', clip_on=False, linewidth=1)
                ax_left.plot((1-d, 1+d), (-d, +d), **kw)
                ax_left.plot((1-d, 1+d), (1-d, 1+d), **kw)
                kw.update(transform=ax_right.transAxes)
                ax_right.plot((-d, +d), (-d, +d), **kw)
                ax_right.plot((-d, +d), (1-d, 1+d), **kw)

                # 绘制每个段
                for seg_i, (si, ei) in enumerate(_gap_segments):
                    ax = ax_left if seg_i == 0 else ax_right
                    sf = freqs[si:ei]
                    if need_dual and b is not None:
                        v1 = [freq_data[f].get(a[1]) for f in sf]
                        v2 = [freq_data[f].get(b[1]) for f in sf]
                        from src.renderer import _render_dual_y_axes
                        _render_dual_y_axes(ax, sf, v1, a[0], v2, b[0])
                    else:
                        v1 = [freq_data[f].get(a[1]) for f in sf]
                        ax.plot(sf, v1, 'o-', markersize=4, color='#1f77b4')
                        ax.set_ylabel(a[0])
                        ax.grid(True, alpha=0.3)
                        if b is not None:
                            v2 = [freq_data[f].get(b[1]) for f in sf]
                            ax.plot(sf, v2, 's--', markersize=4, color='#d62728')
                            lines = ax.get_lines()
                            ax.legend(lines, [a[0], b[0]], fontsize=7)
                    # x 轴标注段首尾频率
                    tick_f = [sf[0], sf[-1]]
                    if len(sf) > 3:
                        tick_f.insert(1, sf[len(sf)//2])
                    ax.set_xticks(tick_f)
                    ax.set_xticklabels([f"{f:.0f}" for f in tick_f], fontsize=7)

                if not is_last:
                    ax_left.tick_params(labelbottom=False)
                    ax_right.tick_params(labelbottom=False)
                else:
                    ax_left.set_xlabel("Frequency (MHz)")
                    ax_right.set_xlabel("Frequency (MHz)")
            else:
                ax = self._figure.add_subplot(gs[row_i, 0])
                sf = freqs
                if need_dual and b is not None:
                    v1 = [freq_data[f].get(a[1]) for f in sf]
                    v2 = [freq_data[f].get(b[1]) for f in sf]
                    from src.renderer import _render_dual_y_axes
                    _render_dual_y_axes(ax, sf, v1, a[0], v2, b[0])
                else:
                    v1 = [freq_data[f].get(a[1]) for f in sf]
                    ax.plot(sf, v1, 'o-', markersize=4, color='#1f77b4')
                    ax.set_ylabel(a[0])
                    ax.grid(True, alpha=0.3)
                    if b is not None:
                        v2 = [freq_data[f].get(b[1]) for f in sf]
                        ax.plot(sf, v2, 's--', markersize=4, color='#d62728')
                        lines = ax.get_lines()
                        ax.legend(lines, [a[0], b[0]], fontsize=7)
                if not is_last:
                    ax.tick_params(labelbottom=False)
                else:
                    ax.set_xlabel("Frequency (MHz)")

        self._canvas.draw()
        _mode_label = ["单Y轴", "双Y轴(自动)", "双Y轴(强制)"][dual_mode]
        self._lbl_info.setText(f"频率曲线: {n} 项, {len(freqs)} 个频点 [{_mode_label}]")

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

        若已存在同名 tab 则更新其数据后选中；否则创建新 tab 并选中。
        """
        for i in range(tab_widget.count()):
            if tab_widget.tabText(i) == cls.TAB_NAME:
                tab = tab_widget.widget(i)
                if isinstance(tab, cls) and hasattr(tab, 'load_data'):
                    tab.load_data(results)
                tab_widget.setCurrentIndex(i)
                return i
        tab = cls(results)
        idx = tab_widget.addTab(tab, cls.TAB_NAME)
        tab_widget.setTabVisible(idx, True)
        tab_widget.setCurrentIndex(idx)
        return idx
