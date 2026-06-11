# 天线参数后处理工具 (Antenna Post-Processor)

车企天线 OTA 测试数据自动分析工具。从 EMQuest 测试系统导出的 CSV 数据，计算 Directivity、Efficiency、Gain、LAG、Axial Ratio 等天线指标，输出格式化 Excel 报告，并生成 3D 辐射方向图。

## 功能

- 📡 **自动天线参数计算**：Peak Gain、Directivity、Efficiency、LAG、Axial Ratio
- 📐 **灵活 LAG 配置**：任意 θ 单角度 + 任意 θ 范围平均 LAG，起始+步进批量生成
- 📊 **3D 辐射方向图**：EMQuest 风格球面曲面图，可设视角、分辨率，嵌入 Excel
- 📋 **模板驱动**：自动读取 Excel 模板列头 → 识别所需参数 → 填入正确位置
- 🔄 **批处理**：单 CSV → 自动匹配多工作表（多天线），一站式处理
- 🎨 **现代化 GUI**：qt-material Material Design 主题，Qt Designer 设计界面
- 🌐 **中英文双语**：Qt Linguist 运行时切换

## 快速开始

### 环境要求

- Python 3.8+
- Windows / Linux / macOS

### 安装

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 运行 GUI

```bash
python main.py
```

### 处理流程

1. 选择输入 CSV（EMQuest merged 格式）和模板 Excel
2. 在 LAG 配置页确认/调整角度设置（或从模板自动加载）
3. 设置 3D 图形选项（视角、是否嵌入 Excel）
4. 点击"开始处理"

## 项目结构

```
antenna-post-processor/
├── main.py                 # GUI 应用入口
├── antenna_post_processor.spec  # PyInstaller 打包配置
├── requirements.txt
├── src/
│   ├── parser.py           # EMQuest CSV 流式解析器（byte-offset 索引）
│   ├── calculator.py       # 天线参数计算引擎（NumPy 向量化）
│   ├── lag_config.py       # LAG 配置模型 + 模板列头解析
│   ├── excel_reader.py     # Excel 模板结构读取
│   ├── exporter.py         # Excel 数据写入 + 图片嵌入
│   ├── plotter.py          # 3D 辐射方向图（matplotlib）
│   ├── pipeline.py         # 批处理管线（parser→calc→plot→export）
│   └── worker.py           # QThread 后台处理
├── ui/
│   ├── designer/           # Qt Designer .ui 源文件
│   ├── compiled/           # pyside6-uic 编译产物
│   ├── main_window.py      # 主窗口逻辑
│   └── theme_manager.py    # qt-material 主题管理
├── i18n/                   # Qt Linguist 翻译文件 (.ts/.qm)
├── config/bands.json       # 频段分配配置
├── tests/                  # 单元测试
├── scripts/                # 编译/翻译辅助脚本
├── data/                   # 输入数据样本
└── output/                 # 默认输出目录
```

## 计算说明

| 参数 | 公式 |
|------|------|
| **Gain (dBi)** | G = 10·log₁₀( 10^(θ_mag/10) + 10^(φ_mag/10) ) |
| **Directivity (dBi)** | D = 10·log₁₀( 4π·U_max / ΣΣ G·sinθ·dθ·dφ ) |
| **Efficiency (%)** | η = 10^((G-D)/10) × 100 |
| **LAG (dB)** | LAG(θ) = 10·log₁₀( mean_φ[ G_lin(θ,φ) ] ) |
| **LAG Range (dB)** | LAG(θ₁→θ₂) = mean_{θ∈[θ₁,θ₂]} [ LAG(θ) ] |
| **Axial Ratio (dB)** | AR = 20·log₁₀( E_major / E_minor ) — 基于 Stokes 参数 |

## 打包为 exe

```bash
# 调试版（推荐先测试）
pyinstaller --onedir antenna_post_processor.spec

# 发布版（单文件）
pyinstaller --onefile antenna_post_processor.spec
```

## 测试

```bash
pytest tests/ -v
```
