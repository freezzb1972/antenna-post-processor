"""
任务包 (.ant) — 自包含的任务存档
===================================
ZIP 包，包含任务配置快照、原始数据副本、模板副本、计算结果缓存。

格式:
    task_<name>_<YYMMDD>.ant
    ├─ task.json      元数据 + 配置快照 + 计算结果 (JSON)
    ├─ data/          原始数据文件副本
    │   ├─ file1.csv
    │   └─ file2.xlsx
    └─ template/      模板副本
        └─ template.xlsx
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


TASK_PACKAGE_EXT = ".ant"
TASK_PACKAGE_VERSION = 1


def save_task_package(
    output_path: str,
    task_name: str,
    data_file_paths: List[str],
    template_path: str,
    config_snapshot: Dict[str, Any],
    results: Optional[Dict[str, List[Dict]]] = None,
    images: Optional[Dict[str, List[str]]] = None,
) -> str:
    """保存任务包到 .ant 文件。"""
    p = Path(output_path)
    if p.suffix.lower() != TASK_PACKAGE_EXT:
        p = p.with_suffix(TASK_PACKAGE_EXT)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)

        # 元数据
        data_files_info = []
        for fp in data_file_paths:
            f = Path(fp)
            if f.exists():
                data_files_info.append({
                    "original_path": str(f.resolve()),
                    "filename": f.name,
                    "size": f.stat().st_size,
                    "sha256": _file_hash(f),
                })

        tpl = Path(template_path)
        task_json = {
            "version": TASK_PACKAGE_VERSION,
            "created": datetime.now().isoformat(),
            "task_name": task_name,
            "data_files": data_files_info,
            "template": {
                "original_path": str(tpl.resolve()) if tpl.exists() else "",
                "filename": tpl.name if tpl.exists() else "",
                "sha256": _file_hash(tpl) if tpl.exists() else "",
            },
            "config_snapshot": config_snapshot,
            "results": results or {},
            "image_count": sum(len(v) for v in (images or {}).values()),
        }

        # 写入 task.json
        (tmp / "task.json").write_text(
            json.dumps(task_json, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )

        # 复制数据文件
        data_dir = tmp / "data"
        data_dir.mkdir()
        for fp in data_file_paths:
            f = Path(fp)
            if f.exists():
                shutil.copy2(str(f), str(data_dir / f.name))

        # 复制模板
        if tpl.exists():
            tpl_dir = tmp / "template"
            tpl_dir.mkdir()
            shutil.copy2(str(tpl), str(tpl_dir / tpl.name))

        # 打包
        if p.exists():
            p.unlink()
        with zipfile.ZipFile(str(p), "w", zipfile.ZIP_DEFLATED) as zf:
            for fpath in tmp.rglob("*"):
                if fpath.is_file():
                    arcname = str(fpath.relative_to(tmp))
                    zf.write(str(fpath), arcname)

    return str(p)


def load_task_package(path: str) -> Dict[str, Any]:
    """加载 .ant 任务包，返回 task.json 内容。"""
    p = Path(path)
    if not p.exists() or p.suffix.lower() != TASK_PACKAGE_EXT:
        raise ValueError(f"不是有效的任务包: {path}")

    with zipfile.ZipFile(str(p), "r") as zf:
        if "task.json" not in zf.namelist():
            raise ValueError(f"任务包损坏: 缺少 task.json")
        with zf.open("task.json") as f:
            return json.loads(f.read().decode("utf-8"))


def verify_data_integrity(task_meta: Dict[str, Any]) -> Dict[str, str]:
    """验证任务包中的数据文件是否与原文件一致。

    返回: {"原文件路径": "ok|modified|missing"}
    """
    result = {}
    for fi in task_meta.get("data_files", []):
        orig = fi.get("original_path", "")
        if not orig or not Path(orig).exists():
            result[orig] = "missing"
        else:
            current_hash = _file_hash(Path(orig))
            if current_hash == fi.get("sha256", ""):
                result[orig] = "ok"
            else:
                result[orig] = "modified"
    return result


def _file_hash(path: Path) -> str:
    """计算文件 SHA256。"""
    h = hashlib.sha256()
    with open(str(path), "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def next_available_filename(directory: str, base_name: str) -> str:
    """生成不重复的任务包文件名。"""
    d = Path(directory)
    d.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y%m%d")
    seq = 1
    while True:
        name = f"{base_name}_{today}_{seq:02d}{TASK_PACKAGE_EXT}"
        if not (d / name).exists():
            return str(d / name)
        seq += 1
