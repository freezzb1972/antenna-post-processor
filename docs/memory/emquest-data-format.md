---
name: emquest-data-format
description: EMQuest CSV 数据格式参考 — 结构、维度、频段、解析方式
---

# EMQuest Merged CSV 数据格式

## 文件结构
- 4 Section: Theta LogMag, Theta Phase, Phi LogMag, Phi Phase
- 每 Section 105 频点 × 362 行（1 freq头 + 1 phi头 + 360 数据行）
- 111 Theta (0-110°, step 1°) × 360 Phi (0-359°, step 1°)
- 总计 ~1680万数据点，151MB

## 频段
| 频段 | 范围 | 频点数 |
|------|------|--------|
| Low  | 690-960 MHz | 30 |
| Mid  | 1710-2690 MHz | 43 |
| High | 3300-5000 MHz | 32 |
| **总计** | | **105** |

## 解析方式
- `src/parser.py` MergedCSVParser 类
- Byte-offset 索引：首次扫描记录文件偏移，后续 seek+read 按需读取
- 峰值内存 ~1.3MB/频点
- 编码：UTF-8-BOM

## 输出模板列头（Row 8）
```
Frequency | Directivity | Efficiency（%） | Efficiency(dB) | Gain |
Theta=0-90 LAG | Theta=60-90 LAG | Theta=60 | Theta=70 | Theta=80 | Theta=90
```

## 5G4 特殊结构
- 13 列（多一个 Gain 重复列）
- 列头: `Efficiency`（无%号）, `Gain`, `Gain`（重复）
- columns 存储为 List 而非 Dict（处理重复列头）
