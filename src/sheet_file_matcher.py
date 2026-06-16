"""
工作表 ↔ 数据文件 命名匹配引擎
==============================
纯函数、无副作用。从模板工作表名称和数据文件名中提取关键词，
自动建立匹配关系。

匹配策略：
  1. 提取键: 从名称中提取标识模式（如 "5G1"→"G1"、"G1Final"→"G1"）
  2. 精确匹配: sheet 键 == file 键 → 1.0 置信度
  3. 子串匹配: sheet 键 in file 键 或反之 → 0.8 置信度
  4. 回退分配: 未匹配的 sheet 分配未使用的 file → 0.5 置信度
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# 键提取
# ---------------------------------------------------------------------------

def extract_key(name: str) -> str:
    """从工作表名称或文件名中提取规范化标识键。

    优先级：
      1. digit+G+digit 模式（如 5G1、G2） → "G1"、"G2"
      2. 末尾数字编号（如 Antenna3） → "ANTENNA3"
      3. 去除路径扩展名后的大写词干
    """
    stem = Path(name).stem  # 去除 .xlsx / .csv 等扩展名

    # 方式 1: 识别 "5G1" / "G1" / "G2Final" 中的 G+数字 组合
    m = re.search(r'(\d*G\d+)', stem, re.IGNORECASE)
    if m:
        # 去除前导数字 → "5G1"→"G1","G2Final"→"G2"
        return re.sub(r'^\d+', '', m.group(1)).upper()

    # 方式 2: 通用 fallback — 整个词干大写
    return stem.upper()


# ---------------------------------------------------------------------------
# 匹配结果
# ---------------------------------------------------------------------------

@dataclass
class MatchResult:
    sheet_name: str
    file_path: Optional[str] = None
    confidence: float = 0.0  # 1.0 = 精确, 0.8 = 子串, 0.5 = 回退, 0.0 = 未匹配


# ---------------------------------------------------------------------------
# 自动匹配
# ---------------------------------------------------------------------------

def auto_match(
    sheet_names: List[str],
    file_paths: List[str],
) -> List[MatchResult]:
    """自动将工作表名称匹配到数据文件路径。

    Args:
        sheet_names: 模板中的工作表名称列表（如 ["5G1","5G2","5G3","5G4"]）。
        file_paths:  数据文件路径列表。

    Returns:
        每个工作表一个 MatchResult，按工作表名称顺序排列。
    """
    if not file_paths:
        return [MatchResult(sheet_name=sn) for sn in sheet_names]

    # 提取所有键
    sheet_keys: Dict[str, str] = {sn: extract_key(sn) for sn in sheet_names}
    file_keys: Dict[str, str] = {fp: extract_key(fp) for fp in file_paths}

    results: List[MatchResult] = []
    used_files: set = set()

    # ------- 第一轮: 精确键匹配 -------
    for sn in sheet_names:
        sk = sheet_keys[sn]
        best_file = None
        best_conf = 0.0

        for fp in file_paths:
            if fp in used_files:
                continue
            fk = file_keys[fp]
            if sk == fk:
                best_file = fp
                best_conf = 1.0
                break

        if best_file:
            used_files.add(best_file)
            results.append(MatchResult(sheet_name=sn, file_path=best_file, confidence=best_conf))
        else:
            results.append(MatchResult(sheet_name=sn))  # 暂未匹配

    # ------- 第二轮: 子串匹配（键 A 包含键 B 或反之） -------
    for r in results:
        if r.file_path is not None:
            continue
        sk = sheet_keys[r.sheet_name]
        best_file = None
        best_conf = 0.0

        for fp in file_paths:
            if fp in used_files:
                continue
            fk = file_keys[fp]
            # 双向子串检查
            if sk in fk or fk in sk:
                best_file = fp
                best_conf = 0.8
                break

        if best_file:
            used_files.add(best_file)
            r.file_path = best_file
            r.confidence = best_conf

    # ------- 第三轮: 回退分配（贪心分配剩余未使用的文件） -------
    remaining_files = [fp for fp in file_paths if fp not in used_files]
    for r in results:
        if r.file_path is not None:
            continue
        if remaining_files:
            r.file_path = remaining_files.pop(0)
            r.confidence = 0.5
            used_files.add(r.file_path)

    return results
