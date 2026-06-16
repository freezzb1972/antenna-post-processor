---
name: size-gate
description: PyInstaller EXE 体积门禁 — 大小限制、污染包扫描、spec 完整性检查
---

# 打包体积门禁 (/size-gate)

适配任何 PyInstaller Python 项目。

## 触发条件

- 修改 `*.spec` 文件后
- PyInstaller 构建后
- 打包前 / 提交前
- 用户说 "/size-gate" 或 "检查体积"

## 验证阶段

| 阶段 | 检查内容 | 阻塞 |
|------|---------|------|
| S1 | 体积上限（Windows ≤80MB, Linux ≤110MB） | GATE |
| S2 | 体积趋势（不超过上次 110%） | WARN |
| S3 | 污染包（pandas/sqlalchemy/pydantic 等） | GATE |
| S4 | Spec 完整性（hiddenimports 数量、excludes） | GATE |
| S5 | 必需模块（PySide6/matplotlib/numpy） | GATE |

## 命令

```bash
python3 build_size_gate.py                  # 完整检查
python3 build_size_gate.py --spec-only      # 仅 spec（无需构建）
python3 build_size_gate.py --baseline        # 更新基线
python3 build_size_gate.py --json            # CI 集成
```

## 跨项目使用

```bash
# 在新项目中初始化
python3 build_size_gate.py --init            # 生成 .size-gate.json
```
