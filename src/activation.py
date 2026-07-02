"""
在线激活客户端
==============
提供激活 API 调用和本地许可缓存管理。

激活流程:
  1. 用户输入激活码
  2. 客户端 POST /activate → 激活服务器
  3. 服务器验证激活码 + 签发 ECDSA 许可
  4. 客户端保存 license JSON 到本地
  5. 客户端启动 LicenseManager → 验证通过

服务器 URL 配置优先级:
  1. ACTIVATION_SERVER_URL 环境变量
  2. QSettings "activation/server_url"
  3. 默认值: http://activation.antenna-pp.local:8899
"""

from __future__ import annotations

import json
from pathlib import Path

# 默认激活服务器 URL（用户可通过 QSettings 或环境变量覆盖）
_DEFAULT_SERVER_URL = "http://activation.antenna-pp.local:8899"


def get_server_url() -> str:
    """获取激活服务器 URL。"""
    import os
    env = os.environ.get("ACTIVATION_SERVER_URL", "")
    if env:
        return env.rstrip("/")
    try:
        from PySide6.QtCore import QSettings
        s = QSettings("AntennaPP", "AntennaPostProcessor")
        url = s.value("activation/server_url", "")
        if url:
            return url.rstrip("/")
    except Exception:
        pass
    return _DEFAULT_SERVER_URL


def set_server_url(url: str):
    """持久化激活服务器 URL 到 QSettings。"""
    try:
        from PySide6.QtCore import QSettings
        s = QSettings("AntennaPP", "AntennaPostProcessor")
        s.setValue("activation/server_url", url)
    except Exception:
        pass


def activate(activation_code: str, machine_id: str,
             server_url: str | None = None) -> tuple[bool, str]:
    """
    向激活服务器请求许可。返回 (成功与否, 消息)。

    成功时自动保存许可到 ~/.antenna_pp_license.json。
    失败时返回错误消息。
    """
    import urllib.error
    import urllib.request

    url = (server_url or get_server_url()).rstrip("/") + "/activate"

    payload = json.dumps({
        "activation_code": activation_code.strip(),
        "machine_id": machine_id.strip(),
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            license_data = data.get("license")
            if not license_data:
                return False, "服务器响应缺少 license 字段"
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read().decode("utf-8"))
            return False, body.get("error", f"HTTP {e.code}")
        except Exception:
            return False, f"服务器返回 HTTP {e.code}"
    except urllib.error.URLError as e:
        return False, f"无法连接激活服务器: {e.reason}"
    except Exception as e:
        return False, f"激活失败: {e}"

    # 保存许可到本地
    try:
        # 1. 保存到配置文件 (antenna_config.json) — 主存储
        lic_json = json.dumps(license_data)
        from src.config_manager import get_config_manager
        cfg_mgr = get_config_manager()
        if not cfg_mgr.set_license(lic_json):
            return False, "许可保存到配置文件失败（签名验证未通过）"

        # 2. 同时保存到 ~/.antenna_pp_license.json — 向后兼容
        license_path = Path.home() / ".antenna_pp_license.json"
        license_path.write_text(
            json.dumps(license_data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return True, str(license_path)
    except OSError as e:
        return False, f"许可保存失败: {e}"


def get_machine_id() -> str:
    """获取当前机器 ID（与 src/license.py 中的实现一致）。"""
    import hashlib
    import uuid
    node = uuid.getnode()
    return hashlib.sha256(str(node).encode()).hexdigest()[:16]
