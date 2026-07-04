"""
模板预设管理器
==============
两级模板系统: 厂商 → 模板列表。每个模板可预设输出目录。
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "templates.json"


class TemplatePreset:
    """单个模板预设。"""

    def __init__(self, name: str, path: str, default_output_dir: str = "",
                 manufacturer: str = "", word_template_path: str = ""):
        self.name = name
        self.path = path
        self.default_output_dir = default_output_dir
        self.manufacturer = manufacturer
        self.word_template_path = word_template_path

    def to_dict(self) -> dict[str, str]:
        return {
            "name": self.name,
            "path": self.path,
            "default_output_dir": self.default_output_dir,
            "word_template_path": self.word_template_path,
        }


class TemplateManager:
    """加载/查询模板预设 JSON。"""

    def __init__(self, config_path: str | None = None):
        self._path = Path(config_path) if config_path else CONFIG_PATH
        self._data: dict[str, Any] = {"manufacturers": []}
        self.load()

    def load(self):
        if self._path.exists():
            try:
                with open(self._path, encoding="utf-8") as f:
                    self._data = json.load(f)
            except (json.JSONDecodeError, OSError):
                self._data = {"manufacturers": []}

    def save(self):
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

    @property
    def manufacturers(self) -> list[str]:
        return [m["name"] for m in self._data.get("manufacturers", [])]

    def get_templates(self, manufacturer: str) -> list[TemplatePreset]:
        for m in self._data.get("manufacturers", []):
            if m["name"] == manufacturer:
                return [
                    TemplatePreset(
                        name=t["name"],
                        path=t["path"],
                        default_output_dir=t.get("default_output_dir", ""),
                        manufacturer=manufacturer,
                        word_template_path=t.get("word_template_path", ""),
                    )
                    for t in m.get("templates", [])
                ]
        return []

    def get_all_templates(self) -> list[TemplatePreset]:
        result: list[TemplatePreset] = []
        for m in self._data.get("manufacturers", []):
            for t in m.get("templates", []):
                result.append(TemplatePreset(
                    name=t["name"],
                    path=t["path"],
                    default_output_dir=t.get("default_output_dir", ""),
                    manufacturer=m["name"],
                    word_template_path=t.get("word_template_path", ""),
                ))
        return result

    def add_template(self, manufacturer: str, name: str, path: str,
                     default_output_dir: str = "", word_template_path: str = ""):
        """添加或更新模板预设。"""
        # 找或创建厂商
        mf = None
        for m in self._data.get("manufacturers", []):
            if m["name"] == manufacturer:
                mf = m
                break
        if mf is None:
            mf = {"name": manufacturer, "templates": []}
            self._data.setdefault("manufacturers", []).append(mf)

        # 找或更新模板
        for t in mf["templates"]:
            if t["name"] == name:
                t["path"] = path
                t["default_output_dir"] = default_output_dir
                t["word_template_path"] = word_template_path
                self.save()
                return

        mf["templates"].append({
            "name": name,
            "path": path,
            "default_output_dir": default_output_dir,
            "word_template_path": word_template_path,
        })
        self.save()

    @staticmethod
    def generate_output_filename(template_name: str) -> str:
        """生成输出文件名: {模板名}_{日期}_{序号}.xlsx"""
        today = date.today().strftime("%Y%m%d")
        name = template_name.replace("/", "_").replace("\\", "_")
        return f"{name}_{today}_01.xlsx"

    @staticmethod
    def next_available_filename(base_dir: str, template_name: str) -> str:
        """在 base_dir 中查找下一个可用序号。委托给 ui_utils 统一实现。"""
        from .ui_utils import next_available_filename as _next_fn
        return _next_fn(base_dir, template_name, ext=".xlsx", sanitize=True)
