"""
软件许可管理
============
基于 ECDSA P-256 签名的许可系统。

签名算法: ECDSA with SECP256R1 (P-256) + SHA-256
  私钥由 vendor 持有 (~/.antenna_pp_ecdsa_private.pem)，不随 EXE 分发。
  公钥硬编码在本文件中，编译进 EXE，用户无法替换。

许可文件格式（JSON）:
  {
    "product": "AntennaPostProcessor",
    "licensee": "公司/用户名称",
    "expiry": "2026-12-31",      // 日期 或 "PERMANENT"
    "features": ["full"],        // 功能列表
    "issued": "2026-06-18",
    "machine_id": "",            // 可选: 绑定机器
    "signature": "ECDSA base64"
  }

安全机制:
  - ECDSA 签名防止篡改（公钥内嵌，无法伪造）
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

# ═══════════════════════════════════════════════════════════════
# ECDSA 公钥（内嵌，编译进 EXE）
# 对应私钥: ~/.antenna_pp_ecdsa_private.pem（vendor 持有，不分发）
# ═══════════════════════════════════════════════════════════════

_ECDSA_PUBLIC_KEY_PEM = """-----BEGIN PUBLIC KEY-----
MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAE7jyH559KFDI2D4RTBn/I+4KFZgY3
UKymxSI0LXN5/5BPVCY/QCodWlml980JhhhpcRpuoJ+LOqa4fFoLY6H0TA==
-----END PUBLIC KEY-----"""

import secrets as _secrets_mod

# ═══════════════════════════════════════════════════════════════
# ECDSA 签名 / 验证
# ═══════════════════════════════════════════════════════════════

def _load_ecdsa_private_key():
    """加载 ECDSA 私钥（仅供 vendor 签发许可使用）。"""
    from cryptography.hazmat.primitives.serialization import load_pem_private_key
    key_path = Path.home() / ".antenna_pp_ecdsa_private.pem"
    if not key_path.exists():
        raise FileNotFoundError(
            f"ECDSA 私钥未找到: {key_path}\n"
            f"私钥仅 vendor 持有，用于签发许可。请确保私钥文件存在。"
        )
    return load_pem_private_key(key_path.read_bytes(), password=None)


def _load_ecdsa_public_key():
    """加载 ECDSA 公钥（内嵌常量，无需外部文件）。"""
    from cryptography.hazmat.primitives.serialization import load_pem_public_key
    return load_pem_public_key(_ECDSA_PUBLIC_KEY_PEM.encode())


def _sign_ecdsa(data: dict) -> str:
    """用 ECDSA 私钥对数据字典签名，返回 base64 字符串。"""
    import base64 as _b64

    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.hashes import SHA256
    payload = json.dumps(data, sort_keys=True, ensure_ascii=False).encode("utf-8")
    private_key = _load_ecdsa_private_key()
    signature = private_key.sign(payload, ec.ECDSA(SHA256()))
    return _b64.b64encode(signature).decode("ascii")


def _verify_ecdsa(data: dict, signature_b64: str) -> bool:
    """用内嵌 ECDSA 公钥验证签名。"""
    import base64 as _b64

    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.hashes import SHA256
    try:
        payload = json.dumps(data, sort_keys=True, ensure_ascii=False).encode("utf-8")
        signature = _b64.b64decode(signature_b64)
        public_key = _load_ecdsa_public_key()
        public_key.verify(signature, payload, ec.ECDSA(SHA256()))
        return True
    except Exception:
        return False


# ═══════════════════════════════════════════════════════════════
# 旧 HMAC 密钥（已弃用，仅用于向后兼容旧许可文件）
# ═══════════════════════════════════════════════════════════════

def _generate_random_key() -> bytes:
    """生成随机 32 字节密钥并持久化到 ~/.antenna_pp_secret。

    已弃用: 新许可使用 ECDSA 签名，此密钥仅供向后兼容旧 HMAC 许可。
    """
    key = _secrets_mod.token_bytes(32)
    try:
        secret_path = Path.home() / ".antenna_pp_secret"
        secret_path.write_bytes(key)
    except OSError as e:
        print(
            f"⚠ [antenna-post-processor] 无法持久化许可密钥到 {secret_path}: {e}",
            file=sys.stderr,
        )
        print(
            "⚠ 重启后密钥将丢失，所有已签发的 HMAC 许可将失效。"
            " 请检查磁盘空间和目录权限。",
            file=sys.stderr,
        )
    return key


def _load_secret_key() -> bytes:
    """从环境变量或密钥文件加载旧 HMAC 密钥。

    已弃用: 仅用于向后兼容旧的 HMAC 签名许可文件。
    """
    # 1. 环境变量
    env_key = os.environ.get("ANTENNA_LICENSE_SECRET")
    if env_key:
        return env_key.encode("utf-8")

    # 2. 密钥文件（可执行文件同级目录）
    if getattr(sys, 'frozen', False):
        exe_dir = Path(sys.executable).parent
        secret_file = exe_dir / ".license_secret"
        if secret_file.exists():
            return secret_file.read_bytes().strip()

    # 3. 密钥文件（当前工作目录）
    secret_file = Path(".license_secret")
    if secret_file.exists():
        return secret_file.read_bytes().strip()

    # 4. ~/.antenna_pp_secret (持久化的随机密钥)
    persisted = Path.home() / ".antenna_pp_secret"
    if persisted.exists():
        return persisted.read_bytes().strip()

    # 5. 随机生成（首次运行）
    return _generate_random_key()

# 模块加载时缓存旧 HMAC 密钥（向后兼容）
_SECRET_KEY = _load_secret_key()

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
    def expiry_date(self) -> date | None:
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
    def days_remaining(self) -> int | None:
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
        self._license: LicenseInfo | None = None
        self._error: str = ""

    # ── 属性 ──

    @property
    def is_valid(self) -> bool:
        return self._license is not None and not self._license.is_expired

    @property
    def license_info(self) -> LicenseInfo | None:
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
            with open(path, encoding="utf-8") as f:
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
        """自动搜索并加载许可文件。

        搜索顺序:
          1. PyInstaller 包内 (sys._MEIPASS) — 打包内嵌的试用许可
          2. 可执行文件同级目录 — 用户自行放入的许可
          3. 当前工作目录 — 开发环境 ./license.json
          4. 用户主目录 — 在线激活后保存的位置
        """
        # 1. PyInstaller 包内（内嵌试用许可）
        if getattr(sys, 'frozen', False):
            meipass = getattr(sys, '_MEIPASS', None)
            if meipass:
                for search_path in _LICENSE_SEARCH_PATHS:
                    p = Path(meipass) / search_path
                    if p.exists() and self.load_from_file(str(p)):
                        return True

        for search_path in _LICENSE_SEARCH_PATHS:
            p = Path(search_path)
            # 2. 可执行文件同级目录
            if getattr(sys, 'frozen', False):
                exe_dir = Path(sys.executable).parent
                p2 = exe_dir / search_path
                if p2.exists() and self.load_from_file(str(p2)):
                    return True
            # 3-4. CWD + home
            if p.exists() and self.load_from_file(str(p)):
                return True
        self._error = "未找到有效许可文件"
        return False

    # ── 验证 ──

    def _verify(self, data: dict) -> bool:
        """验证许可数据（ECDSA 签名，回退 HMAC 向后兼容）。"""
        # 提取签名字段
        raw_signature = data.pop("signature", "")
        if not raw_signature:
            self._error = "许可缺少签名"
            return False

        # 1. ECDSA 验证（主路径：公钥内嵌，无法伪造）
        if _verify_ecdsa(data, raw_signature):
            return self._parse_and_check(data, raw_signature)

        # 2. HMAC 回退（向后兼容旧许可文件）
        expected = self._sign(data)
        if hmac.compare_digest(expected, raw_signature):
            return self._parse_and_check(data, raw_signature)

        self._error = "许可签名无效（已篡改或伪造）"
        return False

    def _parse_and_check(self, data: dict, raw_signature: str) -> bool:
        """解析 LicenseInfo 并检查产品/过期/机器绑定。"""
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
# 许可生成器（仅 vendor 使用 — 需要 ECDSA 私钥）
# ═══════════════════════════════════════════════════════════════

def generate_license(
    licensee: str,
    expiry: str = "PERMANENT",       # "YYYY-MM-DD" 或 "PERMANENT"
    features: list = None,
    machine_id: str = "",
) -> LicenseInfo:
    """生成 ECDSA 签名的许可信息（需要私钥文件）。"""
    li = LicenseInfo(
        product="AntennaPostProcessor",
        licensee=licensee,
        expiry=expiry,
        features=features or ["full"],
        issued=date.today().isoformat(),
        machine_id=machine_id,
    )
    # ECDSA 签名
    data = li.to_dict()
    li.signature = _sign_ecdsa(data)
    return li


def generate_license_file(
    output_path: str,
    licensee: str,
    expiry: str = "PERMANENT",
    features: list = None,
    machine_id: str = "",
) -> str:
    """生成 ECDSA 签名的许可文件。"""
    li = generate_license(licensee, expiry, features, machine_id)
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


# ═══════════════════════════════════════════════════════════════
# QSettings 密钥加密 — 简单 XOR 混淆，杜绝明文存储
# ═══════════════════════════════════════════════════════════════

import base64 as _base64


def _derive_cipher_key() -> bytes:
    """从机器 ID 派生 256-bit AES-like 密钥（用于 QSettings 加密）。"""
    return hashlib.sha256(get_machine_id().encode()).digest()


def encrypt_secret(plaintext: str) -> str:
    """加密敏感文本，返回 Base64 字符串。

    使用机器 ID 派生的密钥做 XOR 混淆。比明文存储安全，
    但非密码学级别的算法——机器 ID 变化会导致无法解密。
    """
    if not plaintext:
        return ""
    key = _derive_cipher_key()
    data = plaintext.encode("utf-8")
    encrypted = bytes(d ^ key[i % len(key)] for i, d in enumerate(data))
    return _base64.b64encode(encrypted).decode("ascii")


def decrypt_secret(ciphertext: str) -> str:
    """解密 `encrypt_secret()` 的输出。"""
    if not ciphertext:
        return ""
    try:
        key = _derive_cipher_key()
        encrypted = _base64.b64decode(ciphertext)
        decrypted = bytes(e ^ key[i % len(key)] for i, e in enumerate(encrypted))
        return decrypted.decode("utf-8")
    except Exception:
        return ""  # 解密失败（机器 ID 变化或数据损坏）返回空字符串
