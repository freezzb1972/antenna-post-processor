"""
RSP 预设管理器
==============
存储命名的 RSP 校准文件路径组，按测试模式索引，支持默认值设定。
持久化到 config/rsp_presets.json。

用法:
    mgr = RspPresetManager()
    mgr.add_or_update(RspPreset(name="无源-标准", test_mode=0, ...))
    best = mgr.get_best_match(0)  # 优先返回该模式的默认预设
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

# 与 src/file_entry.py 保持一致的测试模式常量
MODE_PASSIVE = 0   # 无源天线
MODE_TRP = 1       # 有源发射 TRP
MODE_TIS = 2       # 有源接收 TIS
MODE_ANY = -1      # 通用 (匹配所有模式)

MODE_LABELS = {
    MODE_PASSIVE: "无源天线",
    MODE_TRP: "有源发射 TRP",
    MODE_TIS: "有源接收 TIS",
    MODE_ANY: "通用",
}

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "rsp_presets.json"


@dataclass
class RspPreset:
    """单个 RSP 校准预设。"""
    name: str
    test_mode: int = MODE_ANY
    rsp_h_path: str = ""
    rsp_v_path: str = ""
    description: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "test_mode": self.test_mode,
            "rsp_h_path": self.rsp_h_path,
            "rsp_v_path": self.rsp_v_path,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, d: dict) -> RspPreset:
        return cls(
            name=d.get("name", ""),
            test_mode=d.get("test_mode", MODE_ANY),
            rsp_h_path=d.get("rsp_h_path", ""),
            rsp_v_path=d.get("rsp_v_path", ""),
            description=d.get("description", ""),
        )


class RspPresetManager:
    """RSP 预设的加载、查询和 CRUD 操作。

    预设存储在 config/rsp_presets.json，格式:
    {
        "defaults": {"0": "无源-无预放", "1": "TRP-标准"},
        "presets": [...]
    }
    """

    def __init__(self, config_path: str | None = None):
        self._path = Path(config_path) if config_path else CONFIG_PATH
        self._presets: list[RspPreset] = []
        self._defaults: dict[int, str] = {}  # test_mode → preset_name
        self.load()

    # ── 持久化 ──

    def load(self):
        if self._path.exists():
            try:
                with open(self._path, encoding="utf-8") as f:
                    data = json.load(f)
                self._presets = [RspPreset.from_dict(p) for p in data.get("presets", [])]
                raw_defaults = data.get("defaults", {})
                self._defaults = {int(k): v for k, v in raw_defaults.items()}
            except (json.JSONDecodeError, OSError, ValueError):
                self._presets = []
                self._defaults = {}

    def save(self):
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump({
                "defaults": {str(k): v for k, v in self._defaults.items()},
                "presets": [p.to_dict() for p in self._presets],
            }, f, ensure_ascii=False, indent=2)

    # ── 默认值管理 ──

    def set_default(self, test_mode: int, preset_name: str | None):
        """设置某测试模式的默认 RSP 预设。preset_name 为 None 则清除。"""
        if preset_name:
            self._defaults[test_mode] = preset_name
        else:
            self._defaults.pop(test_mode, None)
        self.save()

    def get_default(self, test_mode: int) -> str | None:
        """获取某测试模式的默认预设名。"""
        return self._defaults.get(test_mode)

    @property
    def defaults(self) -> dict[int, str]:
        return dict(self._defaults)

    # ── 查询 ──

    @property
    def presets(self) -> list[RspPreset]:
        return self._presets.copy()

    @property
    def names(self) -> list[str]:
        return [p.name for p in self._presets]

    def get_by_name(self, name: str) -> RspPreset | None:
        for p in self._presets:
            if p.name == name:
                return p
        return None

    def get_by_test_mode(self, test_mode: int) -> list[RspPreset]:
        """返回匹配指定测试模式的预设（包括 MODE_ANY 通用预设）。"""
        return [p for p in self._presets
                if p.test_mode in (test_mode, MODE_ANY)]

    def get_best_match(self, test_mode: int) -> RspPreset | None:
        """返回最匹配的预设。

        优先级:
        1. 该 mode 的 defaults 映射 → 返回指定预设
        2. 精确 mode 匹配 → 返回第一个
        3. MODE_ANY(-1) 通用预设 → 返回第一个
        4. None
        """
        # 1. 默认值优先
        default_name = self._defaults.get(test_mode)
        if default_name:
            preset = self.get_by_name(default_name)
            if preset:
                return preset

        # 2. 精确匹配
        exact = [p for p in self._presets if p.test_mode == test_mode]
        if exact:
            return exact[0]

        # 3. 通用预设
        any_mode = [p for p in self._presets if p.test_mode == MODE_ANY]
        return any_mode[0] if any_mode else None

    # ── CRUD ──

    def add_or_update(self, preset: RspPreset) -> bool:
        """添加或更新预设（按名称匹配）。成功返回 True。"""
        if not preset.name:
            return False
        for i, p in enumerate(self._presets):
            if p.name == preset.name:
                self._presets[i] = preset
                self.save()
                return True
        self._presets.append(preset)
        self.save()
        return True

    def delete(self, name: str) -> bool:
        """按名称删除预设。同时清除关联的默认值。成功返回 True。"""
        for i, p in enumerate(self._presets):
            if p.name == name:
                self._presets.pop(i)
                # 清除引用此预设的默认值
                for mode, dn in list(self._defaults.items()):
                    if dn == name:
                        del self._defaults[mode]
                self.save()
                return True
        return False
