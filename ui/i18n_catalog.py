"""共享文本源目录 —— 仅供 pyside6-lupdate 静态提取, 运行时不执行。

由 scripts/gen_i18n_catalog.py 生成, 勿手改。
真源在 src/chart_config.py 与 ui/pages.py, 消费点用 i18n_manager.tr_shared()。
"""

from PySide6.QtCore import QCoreApplication


def _catalog():
    """下列调用只为让 lupdate 收录源串; 无运行时语义。"""
    # ── AntennaParamsPage (16 条) ──
    QCoreApplication.translate("AntennaParamsPage", 'AR')
    QCoreApplication.translate("AntennaParamsPage", 'Directivity')
    QCoreApplication.translate("AntennaParamsPage", 'Efficiency / 总效率')
    QCoreApplication.translate("AntennaParamsPage", 'Gain')
    QCoreApplication.translate("AntennaParamsPage", 'NHPIS')
    QCoreApplication.translate("AntennaParamsPage", 'NHPRP')
    QCoreApplication.translate("AntennaParamsPage", 'TIS')
    QCoreApplication.translate("AntennaParamsPage", 'TRP')
    QCoreApplication.translate("AntennaParamsPage", '交叉极化隔离度 (XPI)')
    QCoreApplication.translate("AntennaParamsPage", '功率统计')
    QCoreApplication.translate("AntennaParamsPage", '半球 PIS')
    QCoreApplication.translate("AntennaParamsPage", '半球 PRP')
    QCoreApplication.translate("AntennaParamsPage", '圆极化 (RHCP/LHCP)')
    QCoreApplication.translate("AntennaParamsPage", '比率')
    QCoreApplication.translate("AntennaParamsPage", '波束参数')
    QCoreApplication.translate("AntennaParamsPage", '相位中心')

    # ── ChartConfig (17 条) ──
    QCoreApplication.translate("ChartConfig", '3D AR 方向图')
    QCoreApplication.translate("ChartConfig", '3D EIRP 方向图')
    QCoreApplication.translate("ChartConfig", '3D Eθ 方向图')
    QCoreApplication.translate("ChartConfig", '3D Eφ 方向图')
    QCoreApplication.translate("ChartConfig", '3D Gain 方向图')
    QCoreApplication.translate("ChartConfig", 'A 类: 3D 方向图')
    QCoreApplication.translate("ChartConfig", 'AR vs 频率')
    QCoreApplication.translate("ChartConfig", 'B 类: 频率曲线')
    QCoreApplication.translate("ChartConfig", 'C 类: 2D 切面图')
    QCoreApplication.translate("ChartConfig", 'Directivity vs 频率')
    QCoreApplication.translate("ChartConfig", 'Efficiency vs 频率')
    QCoreApplication.translate("ChartConfig", 'Gain vs 频率')
    QCoreApplication.translate("ChartConfig", 'TRP vs 频率')
    QCoreApplication.translate("ChartConfig", '极坐标俯仰面切面图')
    QCoreApplication.translate("ChartConfig", '极坐标方位面切面图')
    QCoreApplication.translate("ChartConfig", '直角坐标俯仰面切面图')
    QCoreApplication.translate("ChartConfig", '直角坐标方位面切面图')

    # ── ThemeManager (7 条) ──
    QCoreApplication.translate("ThemeManager", '亮色 蓝色')
    QCoreApplication.translate("ThemeManager", '亮色 青绿')
    QCoreApplication.translate("ThemeManager", '暗色 复古暖')
    QCoreApplication.translate("ThemeManager", '暗色 琥珀')
    QCoreApplication.translate("ThemeManager", '暗色 白框白字')
    QCoreApplication.translate("ThemeManager", '暗色 蓝色')
    QCoreApplication.translate("ThemeManager", '暗色 青绿 ★')

