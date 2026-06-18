"""
软件许可管理
============
基于 HMAC-SHA256 签名的许可系统。

许可文件格式（JSON）:
  {
    "product": "AntennaPostProcessor",
    "licensee": "公司/用户名称",
    "expiry": "2026-12-31",      // 日期 或 "PERMANENT"
    "features": ["full"],        // 功能列表
    "issued": "2026-06-18",
    "machine_id": "",            // 可选: 绑定机器
    "signature": "HMAC-SHA256 hex"
  }

安全机制:
  - 内置密钥签名，防止篡改
  - 过期检查
  - 可选机器绑定（MAC 地址哈希）
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Dict, Optional, Tuple


# ═══════════════════════════════════════════════════════════════
# 内置密钥（发布时建议混淆或从环境变量读取）
# ═══════════════════════════════════════════════════════════════

_SECRET_KEY = b"AntennaPP-License-Secret-Key-2026-v2"

# 许可文件查找路径
_LICENSE_SEARCH_PATHS = [
    "license.json",
    "license.key",
    ".antenna_license",
    str(Path.home() / ".antenna_pp_license.json"),
]


# ═══════════════════════════════════════════════════════════════
# 数据模型
# ═══════════════════════════════════════════════════════════════

@dataclass
class LicenseInfo:
    """许可信息。"""
    product: str = "AntennaPostProcessor"
    licensee: str = ""
    expiry: str = "PERMANENT"       # "YYYY-MM-DD" 或 "PERMANENT"
    features: list = field(default_factory=lambda: ["full"])
    issued: str = ""
    machine_id: str = ""
    signature: str = ""

    @property
    def is_permanent(self) -> bool:
        return self.expiry.upper() == "PERMANENT"

    @property
    def expiry_date(self) -> Optional[date]:
        if self.is_permanent:
            return None
        try:
            return datetime.strptime(self.expiry, "%Y-%m-%d").date()
        except ValueError:
            return None

    @property
    def is_expired(self) -> bool:
        ed = self.expiry_date
        if ed is None:
            return False  # 永久许可不过期
        return date.today() > ed

    @property
    def days_remaining(self) -> Optional[int]:
        ed = self.expiry_date
        if ed is None:
            return None  # 永久
        return (ed - date.today()).days

    def to_dict(self) -> dict:
        d = {
            "product": self.product,
            "licensee": self.licensee,
            "expiry": self.expiry,
            "features": self.features,
            "issued": self.issued,
            "machine_id": self.machine_id,
        }
        return d


# ═══════════════════════════════════════════════════════════════
# 许可验证器
# ═══════════════════════════════════════════════════════════════

class LicenseManager:
    """许可管理器。"""

    def __init__(self, secret_key: bytes = None):
        self._key = secret_key or _SECRET_KEY
        self._license: Optional[LicenseInfo] = None
        self._error: str = ""

    # ── 属性 ──

    @property
    def is_valid(self) -> bool:
        return self._license is not None and not self._license.is_expired

    @property
    def license_info(self) -> Optional[LicenseInfo]:
        return self._license

    @property
    def error_message(self) -> str:
        return self._error

    @property
    def status_text(self) -> str:
        if self._license is None:
            return "未许可"
        if self._license.is_expired:
            return f"已过期 ({self._license.expiry})"
        if self._license.is_permanent:
            return "永久许可"
        remaining = self._license.days_remaining
        return f"有效 (剩余 {remaining} 天)"

    # ── 加载 ──

    def load_from_file(self, path: str) -> bool:
        """从许可文件加载并验证。"""
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return self._verify(data)
        except FileNotFoundError:
            self._error = f"许可文件未找到: {path}"
            return False
        except json.JSONDecodeError:
            self._error = "许可文件格式错误"
            return False
        except Exception as e:
            self._error = f"许可加载失败: {e}"
            return False

    def load_from_string(self, license_text: str) -> bool:
        """从许可字符串（JSON）加载并验证。"""
        try:
            data = json.loads(license_text)
            return self._verify(data)
        except json.JSONDecodeError:
            self._error = "许可字符串格式错误"
            return False
        except Exception as e:
            self._error = f"许可验证失败: {e}"
            return False

    def auto_load(self) -> bool:
        """自动搜索并加载许可文件。"""
        for search_path in _LICENSE_SEARCH_PATHS:
            p = Path(search_path)
            # 也搜索可执行文件同级目录
            if getattr(sys, 'frozen', False):
                exe_dir = Path(sys.executable).parent
                p2 = exe_dir / search_path
                if p2.exists() and self.load_from_file(str(p2)):
                    return True
            if p.exists() and self.load_from_file(str(p)):
                return True
        self._error = "未找到有效许可文件"
        return False

    # ── 验证 ──

    def _verify(self, data: dict) -> bool:
        """验证许可数据。"""
        # 提取签名字段
        raw_signature = data.pop("signature", "")
        if not raw_signature:
            self._error = "许可缺少签名"
            return False

        # 验证签名
        expected = self._sign(data)
        if not hmac.compare_digest(expected, raw_signature):
            self._error = "许可签名无效（已篡改或伪造）"
            return False

        # 解析为 LicenseInfo
        try:
            li = LicenseInfo(
                product=data.get("product", "AntennaPostProcessor"),
                licensee=data.get("licensee", ""),
                expiry=data.get("expiry", "PERMANENT"),
                features=data.get("features", ["full"]),
                issued=data.get("issued", ""),
                machine_id=data.get("machine_id", ""),
                signature=raw_signature,
            )
        except Exception as e:
            self._error = f"许可数据无效: {e}"
            return False

        # 产品检查
        if li.product != "AntennaPostProcessor":
            self._error = f"许可产品不匹配: {li.product}"
            return False

        # 过期检查
        if li.is_expired:
            self._error = f"许可已过期 ({li.expiry})"
            self._license = li  # 仍保存以便显示信息
            return False

        # 机器绑定检查（如果指定了 machine_id）
        if li.machine_id:
            current_machine = get_machine_id()
            if current_machine != li.machine_id:
                self._error = "许可绑定机器不匹配"
                return False

        self._license = li
        self._error = ""
        return True

    def _sign(self, data: dict) -> str:
        """对数据字典签名。"""
        payload = json.dumps(data, sort_keys=True, ensure_ascii=False)
        return hmac.new(self._key, payload.encode(), hashlib.sha256).hexdigest()


# ═══════════════════════════════════════════════════════════════
# 许可生成器（仅用于 vendor 生成许可）
# ═══════════════════════════════════════════════════════════════

def generate_license(
    licensee: str,
    expiry: str = "PERMANENT",       # "YYYY-MM-DD" 或 "PERMANENT"
    features: list = None,
    machine_id: str = "",
    secret_key: bytes = None,
) -> LicenseInfo:
    """生成许可信息（含签名）。"""
    key = secret_key or _SECRET_KEY
    li = LicenseInfo(
        product="AntennaPostProcessor",
        licensee=licensee,
        expiry=expiry,
        features=features or ["full"],
        issued=date.today().isoformat(),
        machine_id=machine_id,
    )
    # 签名
    data = li.to_dict()
    payload = json.dumps(data, sort_keys=True, ensure_ascii=False)
    sig = hmac.new(key, payload.encode(), hashlib.sha256).hexdigest()
    li.signature = sig
    return li


def generate_license_file(
    output_path: str,
    licensee: str,
    expiry: str = "PERMANENT",
    features: list = None,
    machine_id: str = "",
    secret_key: bytes = None,
) -> str:
    """生成许可文件。"""
    li = generate_license(licensee, expiry, features, machine_id, secret_key)
    data = li.to_dict()
    data["signature"] = li.signature

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    return output_path


# ═══════════════════════════════════════════════════════════════
# 机器 ID
# ═══════════════════════════════════════════════════════════════

def get_machine_id() -> str:
    """获取机器标识（基于 MAC 地址哈希，跨平台）。"""
    node = uuid.getnode()
    return hashlib.sha256(str(node).encode()).hexdigest()[:16]
