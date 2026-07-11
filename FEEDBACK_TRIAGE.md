# 反馈汇总 (自动生成)

更新: 2026-07-11 04:24 UTC · 共 1 条已核实

## 🐞 真 Bug (0)
_（无）_

## 💡 需求/建议 (1)
- **出报告时底部状态栏会多出一行冗余信息(无源|Gain..|就绪),没必要**  `bug` `1.0.0` `low`
  - 核实: ui/main_window.py:_extract_execution_bar() 有意组装执行栏三元素: _mode_freq_label('📡 无源', line 3226) + _params_display('参数: Gain...', line 3201) + lblProgressMsg('就绪', 编译UI line 588)。功能正常无崩溃, 值也正确, 无 QStatusBar; 用户所述'冗余'是主观 UX 偏好(信息与右侧面板重复), 属建议非缺陷。
  - 建议: 若确认冗余, 可在 _extract_execution_bar 中隐藏 _mode_freq_label 或将 _params_display 折叠, 需先与用户确认哪部分保留 (进度 lblProgressMsg 建议保留)。

## 🔁 重复/已知 (0)
_（无）_

## ⚪ 无效/信息不足 (0)
_（无）_
