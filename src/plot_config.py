"""PlotConfig — 3D 方向图配置，独立于 pipeline 模块避免过早加载 matplotlib。"""

from __future__ import annotations
from typing import Optional


class PlotConfig:
    """3D 方向图生成配置。"""

    elev: float = 30.0
    azim: float = -60.0
    dpi: int = 150
    embed_in_excel: bool = True
    save_png_folder: Optional[str] = None

    def __init__(self, *, elev=30.0, azim=-60.0, dpi=150,
                 embed_in_excel=True, save_png_folder=None):
        self.elev = elev
        self.azim = azim
        self.dpi = dpi
        self.embed_in_excel = embed_in_excel
        self.save_png_folder = save_png_folder
