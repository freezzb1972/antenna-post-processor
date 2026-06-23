"""
统一配置管理器
==============
所有用户配置集中存储在 EXE 同目录的 ``antenna_config.json`` 中。
敏感字段 (API Key) 使用 AES-256-GCM 加密，密钥由机器特征派生。

特性:
  - 开发模式: 文件存储在 CWD
  - 打包模式: 文件存储在 EXE 同目录
  - API Key 加密存储，防止明文泄露
  - 首次启动自动从 QSettings 迁移旧配置
  - 线程安全的读写
"""

from __future__ import annotations

import base64
import hashlib
import hmac as _hmac
import json
import os
import secrets
import sys
import threading
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ── 可选: cryptography 库 (AES-GCM) ──
try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    _HAS_AES = True
except ImportError:
    _HAS_AES = False


# ═══════════════════════════════════════════════════════════════
# 试用期防篡改密钥（内嵌，编译进 EXE）
# ═══════════════════════════════════════════════════════════════
# 注意：此密钥仅用于防止普通用户篡改试用期，不能阻止逆向工程。
# 真正的保护在正式许可的 ECDSA 签名里。轮换此密钥需重新编译。
_TRIAL_HMAC_KEY = bytes([
    0x9e, 0x3f, 0x72, 0xa1, 0x4b, 0x8c, 0x2d, 0x55,
    0x6e, 0x1a, 0x3f, 0x7b, 0x92, 0x4c, 0x5d, 0x88,
    0x3a, 0x6f, 0x9e, 0x2c, 0x4b, 0x7d, 0x1e, 0x5a,
    0x8f, 0x3c, 0x6b, 0x9d, 0x2e, 0x4a, 0x7f, 0x1c,
])


# ═══════════════════════════════════════════════════════════════
# 试用期签名工具
# ═══════════════════════════════════════════════════════════════

def _sign_trial(machine_id: str, trial_start: str, trial_days: int) -> str:
    """对试用数据进行 HMAC-SHA256 签名。

    签名绑定 (machine_id + trial_start + trial_days)，
    任何篡改都会导致签名验证失败。
    """
    payload = f"{machine_id}|{trial_start}|{trial_days}".encode('utf-8')
    h = _hmac.new(_TRIAL_HMAC_KEY, payload, hashlib.sha256)
    return h.hexdigest()


def _verify_trial(machine_id: str, trial_start: str, trial_days: int, signature: str) -> bool:
    """验证试用数据的 HMAC 签名。"""
    if not signature or not trial_start:
        return False
    expected = _sign_trial(machine_id, trial_start, trial_days)
    return _hmac.compare_digest(expected, signature)


# ═══════════════════════════════════════════════════════════════
# 编译时固化试用配置 (内嵌于 EXE)
# ═══════════════════════════════════════════════════════════════
# trial_config.json 由 generate_trial_config.py 在打包前生成，
# 通过 PyInstaller --add-data 嵌入 EXE。
# 包含: build_date (编译日期), trial_days (试用天数), public_key_pem
#
# 试用期 = 首次运行日期 + trial_days，但首次运行日期不能晚于
# build_date + trial_days。这防止了"备份旧 EXE 恢复后重新试用"的攻击。

_build_config_cache: Optional[dict] = None


def _load_build_config() -> dict:
    """加载编译时嵌入的试用配置。

    打包模式: 从 sys._MEIPASS 读取
    开发模式: 从 CWD 读取
    """
    global _build_config_cache
    if _build_config_cache is not None:
        return _build_config_cache

    config = {"build_date": "", "trial_days": 30, "public_key_pem": ""}
    search_paths = []

    if getattr(sys, 'frozen', False):
        # PyInstaller 打包: 内嵌数据在 sys._MEIPASS
        search_paths.append(Path(sys._MEIPASS) / "trial_config.json")
    else:
        # 开发模式: 当前目录
        search_paths.append(Path.cwd() / "trial_config.json")
        search_paths.append(Path(__file__).resolve().parent.parent / "trial_config.json")

    for p in search_paths:
        try:
            if p.exists():
                data = json.loads(p.read_text(encoding='utf-8'))
                config["build_date"] = data.get("build_date", "")
                config["trial_days"] = int(data.get("trial_days", 30))
                config["public_key_pem"] = data.get("public_key_pem", "")
                break
        except Exception:
            continue

    _build_config_cache = config
    return config


def _get_last_seen_paths() -> List[Path]:
    """获取单调时间戳的冗余存储路径（防止时间回滚）。"""
    paths = []
    if sys.platform == 'win32':
        paths.append(Path(os.environ.get('APPDATA', '')) / '.antpp_last_seen')
    elif sys.platform == 'darwin':
        paths.append(Path.home() / 'Library' / 'Application Support' / '.antpp_last_seen')
    else:
        paths.append(Path.home() / '.local' / 'share' / '.antpp_last_seen')
    paths.append(Path.home() / '.antpp_last_seen')
    return paths


def _get_last_seen() -> Optional[str]:
    """读取单调时间戳（从所有冗余位置，取最大值即最新）。

    如果某位置不存在或损坏，忽略该位置继续检查其他位置。
    返回 ISO 格式日期字符串 "YYYY-MM-DD"，或 None（首次运行）。
    """
    from datetime import date as _date
    latest: Optional[_date] = None

    # 1. QSettings
    try:
        from PySide6.QtCore import QSettings
        s = QSettings("AntennaPP", "AntennaPostProcessor")
        val = s.value("trial/last_seen", "")
        if val:
            latest = _date.fromisoformat(str(val))
    except Exception:
        pass

    # 2. 隐藏文件
    for p in _get_last_seen_paths():
        try:
            if p.exists():
                val = p.read_text().strip()
                if val:
                    d = _date.fromisoformat(val)
                    if latest is None or d > latest:
                        latest = d
        except Exception:
            pass

    return latest.isoformat() if latest else None


def _update_last_seen(date_str: str):
    """更新单调时间戳到所有冗余位置。

    仅在日期变大时才写入（保证单调递增）。
    """
    from datetime import date as _date
    new_date = _date.fromisoformat(date_str)

    # 检查是否需要更新
    current = _get_last_seen()
    if current:
        cur_date = _date.fromisoformat(current)
        if new_date <= cur_date:
            return  # 不需要更新

    # 1. QSettings
    try:
        from PySide6.QtCore import QSettings
        s = QSettings("AntennaPP", "AntennaPostProcessor")
        s.setValue("trial/last_seen", date_str)
        s.sync()
    except Exception:
        pass

    # 2. 隐藏文件
    for p in _get_last_seen_paths():
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(date_str)
            if sys.platform != 'win32':
                os.chmod(str(p), 0o600)
        except Exception:
            pass

# ═══════════════════════════════════════════════════════════════
# 数据模型
# ═══════════════════════════════════════════════════════════════

@dataclass
class LLMConfig:
    """LLM API 配置。"""
    enabled: bool = False
    api_base: str = "https://api.anthropic.com/v1/messages"
    model: str = "claude-sonnet-4-6"
    use_local: bool = False
    local_model: str = "qwen2.5:7b"
    local_endpoint: str = "http://localhost:11434"
    # 加密存储
    _api_key: str = ""


@dataclass
class AIConfig:
    """AI 辅助识别配置 (独立于 RAG 问答)。"""
    enabled: bool = False
    mode: str = "cloud"        # "cloud" | "local"
    api_base: str = "https://api.anthropic.com/v1/messages"
    model: str = "claude-sonnet-4-6"
    local_endpoint: str = "http://localhost:11434"
    # 加密存储
    _api_key: str = ""


@dataclass
class LicenseConfig:
    """许可配置（ECDSA 签名 + 防篡改试用期）。"""
    product: str = "AntennaPostProcessor"
    licensee: str = ""
    expiry: str = "PERMANENT"          # "YYYY-MM-DD" 或 "PERMANENT"
    features: List[str] = field(default_factory=lambda: ["full"])
    issued: str = ""
    machine_id: str = ""               # 绑定机器（必填，签发时填入）
    signature: str = ""                # ECDSA base64 签名（正式许可）
    trial_start: str = ""              # 试用起始日期 "YYYY-MM-DD"
    trial_days: int = 30               # 试用天数
    trial_hmac: str = ""               # HMAC-SHA256 签名（防篡改）

    @property
    def is_active(self) -> bool:
        """正式许可已激活（有 ECDSA 签名）。"""
        return bool(self.signature and self.licensee)

    @property
    def is_trial(self) -> bool:
        """是否处于试用期。"""
        return bool(self.trial_start) and not self.is_active

    @property
    def trial_remaining(self) -> int:
        """试用期剩余天数。负数表示已过期。"""
        if not self.trial_start:
            return -1
        from datetime import date as _date
        try:
            start = _date.fromisoformat(self.trial_start)
            elapsed = (_date.today() - start).days
            return max(-1, self.trial_days - elapsed)
        except Exception:
            return -1

    @property
    def is_trial_expired(self) -> bool:
        """试用期是否已过期。"""
        return self.is_trial and self.trial_remaining < 0

    def to_license_dict(self) -> dict:
        return {
            "product": self.product,
            "licensee": self.licensee,
            "expiry": self.expiry,
            "features": self.features,
            "issued": self.issued,
            "machine_id": self.machine_id,
        }


@dataclass
class AppConfig:
    """应用程序完整配置。"""
    version: int = 1
    # 通用
    font_size: int = 13
    theme: str = "dark"
    language: str = "zh_CN"
    # 路径
    last_template_path: str = ""
    last_output_dir: str = ""
    last_csv_paths: List[str] = field(default_factory=list)
    # LLM
    llm: LLMConfig = field(default_factory=LLMConfig)
    # AI 辅助
    ai: AIConfig = field(default_factory=AIConfig)
    # 窗口
    window_geometry: str = ""
    # 许可
    license: LicenseConfig = field(default_factory=LicenseConfig)


# ── 兼容旧代码的类型别名 ──
AIConfig = AIConfig
LLMConfig = LLMConfig
AppConfig = AppConfig


# ═══════════════════════════════════════════════════════════════
# 配置路径
# ═══════════════════════════════════════════════════════════════

def _get_config_dir() -> Path:
    """获取配置文件目录。

    - 打包模式 (PyInstaller): EXE 所在目录
    - 开发模式: 当前工作目录
    """
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    return Path.cwd()


def _get_config_path() -> Path:
    return _get_config_dir() / "antenna_config.json"


# ═══════════════════════════════════════════════════════════════
# 加密 (AES-256-GCM)
# ═══════════════════════════════════════════════════════════════

def _derive_key(salt: bytes = None) -> tuple:
    """从机器特征派生 256-bit 加密密钥。

    使用机器 ID + MAC 地址 + 用户名组合，
    即使拷贝到另一台机器也无法解密。
    返回 (key: bytes, salt: bytes)。
    """
    if salt is None:
        salt = secrets.token_bytes(16)

    # 机器特征
    import uuid as _uuid
    machine_id = str(_uuid.getnode())  # MAC 地址
    try:
        node = _uuid.UUID(int=_uuid.getnode())
    except Exception:
        node = _uuid.uuid4()
    hostname = os.uname().nodename if hasattr(os, 'uname') else os.environ.get('COMPUTERNAME', 'unknown')
    username = os.environ.get('USER', os.environ.get('USERNAME', 'unknown'))

    # 组合特征 → 派生密钥
    material = f"{machine_id}:{hostname}:{username}:{salt.hex()}".encode('utf-8')
    key = hashlib.pbkdf2_hmac('sha256', material, salt, 100_000, dklen=32)
    return key, salt


def encrypt_api_key(plaintext: str) -> str:
    """加密 API Key。

    使用 AES-256-GCM 加密（如果 cryptography 可用），
    否则回退到 XOR 混淆。

    返回格式: ``<method>:<base64_data>``
      - ``aes:<base64(salt + iv + ciphertext + tag)>``
      - ``xor:<base64(ciphertext)>``  (fallback)
    """
    if not plaintext:
        return ""

    if _HAS_AES:
        key, salt = _derive_key()
        aesgcm = AESGCM(key)
        iv = secrets.token_bytes(12)
        ciphertext = aesgcm.encrypt(iv, plaintext.encode('utf-8'), None)
        # salt (16) + iv (12) + ciphertext (variable + 16 tag)
        blob = salt + iv + ciphertext
        return "aes:" + base64.b64encode(blob).decode('ascii')
    else:
        # Fallback: XOR with machine-derived key
        key = _derive_key(b"config-xor-salt")[0]
        data = plaintext.encode('utf-8')
        encrypted = bytes(d ^ key[i % len(key)] for i, d in enumerate(data))
        return "xor:" + base64.b64encode(encrypted).decode('ascii')


def decrypt_api_key(ciphertext: str) -> str:
    """解密 ``encrypt_api_key()`` 的输出。"""
    if not ciphertext:
        return ""

    try:
        method, data = ciphertext.split(':', 1)
    except ValueError:
        # 旧格式 (base64 encoded XOR) → 试解密
        import base64 as _b64
        try:
            raw = _b64.b64decode(ciphertext)
            key = _derive_key(b"config-xor-salt")[0]
            decrypted = bytes(d ^ key[i % len(key)] for i, d in enumerate(raw))
            return decrypted.decode('utf-8')
        except Exception:
            return ""

    if method == "aes" and _HAS_AES:
        try:
            blob = base64.b64decode(data)
            salt = blob[:16]
            iv = blob[16:28]
            ct = blob[28:]
            key, _ = _derive_key(salt)
            aesgcm = AESGCM(key)
            return aesgcm.decrypt(iv, ct, None).decode('utf-8')
        except Exception:
            return ""  # 解密失败 (换机器/损坏)

    elif method == "xor":
        try:
            key = _derive_key(b"config-xor-salt")[0]
            raw = base64.b64decode(data)
            decrypted = bytes(d ^ key[i % len(key)] for i, d in enumerate(raw))
            return decrypted.decode('utf-8')
        except Exception:
            return ""

    return ""


# ═══════════════════════════════════════════════════════════════
# 配置管理器
# ═══════════════════════════════════════════════════════════════

class ConfigManager:
    """线程安全的配置管理器单例。"""

    _instance: Optional["ConfigManager"] = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._config: AppConfig = AppConfig()
        self._dirty = False
        self._lock = threading.Lock()

    # ── 加载 / 保存 ──

    def load(self) -> AppConfig:
        """加载配置。如果文件不存在，尝试从 QSettings 迁移。"""
        config_path = _get_config_path()

        if config_path.exists():
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    raw = json.load(f)
                self._config = self._from_dict(raw)
            except Exception:
                pass  # 损坏 → 使用默认值
        else:
            # 首次启动: 从 QSettings 迁移
            self._migrate_from_qsettings()
            self._config = self._load_from_qsettings()

        # 如果旧版 XOR 加密的 key 存在，迁移到新版 AES
        self._migrate_encryption()

        return self._config

    def save(self):
        """保存配置到文件。"""
        config_path = _get_config_path()
        with self._lock:
            raw = self._to_dict(self._config)
            # 确保目录存在
            config_path.parent.mkdir(parents=True, exist_ok=True)
            # 原子写入
            tmp = config_path.with_suffix('.tmp')
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(raw, f, indent=2, ensure_ascii=False)
            tmp.replace(config_path)
            self._dirty = False

    # ── 属性访问 ──

    @property
    def config(self) -> AppConfig:
        return self._config

    def get_api_key(self, which: str = "llm") -> str:
        """获取解密后的 API Key。

        Args:
            which: ``"llm"`` (RAG 问答) 或 ``"ai"`` (AI 辅助识别)
        """
        encrypted = ""
        if which == "ai":
            encrypted = self._config.ai._api_key
        else:
            encrypted = self._config.llm._api_key
        if not encrypted:
            return ""
        return decrypt_api_key(encrypted)

    def set_api_key(self, which: str, plaintext: str):
        """加密并存储 API Key。

        Args:
            which: ``"llm"`` 或 ``"ai"``
            plaintext: 明文 API Key
        """
        encrypted = encrypt_api_key(plaintext) if plaintext else ""
        if which == "ai":
            self._config.ai._api_key = encrypted
        else:
            self._config.llm._api_key = encrypted
        self._dirty = True

    def update(self, **kwargs):
        """批量更新配置字段并自动保存。"""
        for key, value in kwargs.items():
            if hasattr(self._config, key):
                setattr(self._config, key, value)
        self._dirty = True

    # ── 许可管理 ──

    def set_license(self, license_json: str) -> bool:
        """加载并验证许可字符串，成功后保存到配置文件。

        正式许可激活后自动清除试用状态。
        返回 True 表示许可有效且已保存。
        """
        from src.license import LicenseManager, get_machine_id
        mgr = LicenseManager()
        if not mgr.load_from_string(license_json):
            self._config.license = LicenseConfig()  # 清空
            self._dirty = True
            return False

        info = mgr.license_info
        if info is None:
            return False

        # 验证机器绑定: 许可中的 machine_id 必须匹配当前机器
        current_mid = get_machine_id()
        if info.machine_id and info.machine_id != current_mid:
            return False

        # 保存到配置（正式许可 → 清除试用状态）
        data = info.to_dict()
        data['signature'] = info.signature
        self._config.license = LicenseConfig(
            product=data.get('product', 'AntennaPostProcessor'),
            licensee=data.get('licensee', ''),
            expiry=data.get('expiry', 'PERMANENT'),
            features=data.get('features', ['full']),
            issued=data.get('issued', ''),
            machine_id=data.get('machine_id', ''),
            signature=data.get('signature', ''),
            trial_start="",         # 正式许可清除试用
            trial_days=0,
        )
        self._dirty = True
        self.save()
        return True

    def start_trial(self) -> bool:
        """启动试用期。使用 build_date 作为试用窗口上限防止备份攻击。

        核心逻辑:
          - 试用窗口上限 = build_date + trial_days（编译时固化）
          - trial_start = min(首次运行日期, 试用窗口上限)
          - 备份旧 EXE → build_date 不变 → 超过窗口后仍过期

        HMAC 签名绑定 (machine_id + trial_start + trial_days) 防止篡改。
        单调时间戳 (last_seen) 记录在各冗余位置，防止时间回滚。

        返回 True 表示试用已启动或仍在有效期内。
        """
        from datetime import date as _date

        lic = self._config.license
        if lic.is_active:
            return False  # 已有正式许可

        today = _date.today()
        build_cfg = _load_build_config()
        build_date = _date.fromisoformat(build_cfg["build_date"]) if build_cfg["build_date"] else today
        trial_days = build_cfg["trial_days"]
        trial_window_end = build_date + _date.resolution * trial_days

        # ── 检查时间回滚 (monotonic last_seen) ──
        last_seen_str = _get_last_seen()
        if last_seen_str:
            last_seen = _date.fromisoformat(last_seen_str)
            if today < last_seen:
                # 系统时间被回滚
                if last_seen > trial_window_end:
                    return False  # 已过期，回滚无效
                # 否则: 允许（可能是合法的时钟校正），但仍使用 last_seen 作为基准
                today = last_seen
        _update_last_seen(today.isoformat())

        machine_id = _get_machine_id_for_trial()

        # ── 检查是否已有试用记录 (从配置文件) ──
        if lic.trial_start:
            if _verify_trial(machine_id, lic.trial_start, lic.trial_days, lic.trial_hmac):
                # 已有有效试用 → 检查是否过期
                if lic.is_trial_expired:
                    return False
                # 更新 last_seen 到最新
                return True
            else:
                # HMAC 无效 → 被篡改，拒绝
                return False

        # ── 首次启动: 创建试用 ──
        # trial_start 不能晚于试用窗口上限（防止备份攻击）
        capped_start = min(today, trial_window_end)
        trial_start_str = capped_start.isoformat()
        hmac_sig = _sign_trial(machine_id, trial_start_str, trial_days)

        lic.trial_start = trial_start_str
        lic.trial_days = trial_days
        lic.trial_hmac = hmac_sig
        self._dirty = True
        self.save()

        # ── 检查是否已过期 ──
        if capped_start < today:
            # trial_start 被 cap 在窗口上限，且今天已超过上限
            return False

        return True

    def is_license_valid(self) -> bool:
        """检查当前许可是否有效。

        优先级: 正式许可 > 试用期内 > 无效

        试用期验证:
          1. HMAC 签名验证 (防篡改 trial_start/trial_days)
          2. 机器 ID 匹配 (防拷贝到别的机器)
          3. 单调时间戳检测 (防系统时间回滚)
          4. build_date 窗口上限 (防备份旧 EXE 重置试用)
        """
        lic = self._config.license

        # 1. 正式许可（ECDSA 签名）
        if lic.is_active:
            from src.license import LicenseManager, get_machine_id
            mgr = LicenseManager()
            data = lic.to_license_dict()
            data['signature'] = lic.signature
            if mgr.load_from_string(json.dumps(data)):
                if lic.machine_id:
                    if lic.machine_id != get_machine_id():
                        return False
                return True

        # 2. 试用期
        if lic.trial_start and not lic.is_active:
            current_machine = _get_machine_id_for_trial()

            # 2a. HMAC 签名验证（防篡改）
            if not _verify_trial(current_machine, lic.trial_start, lic.trial_days, lic.trial_hmac):
                return False

            # 2b. 单调时间戳检测（防时间回滚）
            from datetime import date as _date
            today = _date.today()
            last_seen_str = _get_last_seen()
            if last_seen_str:
                last_seen = _date.fromisoformat(last_seen_str)
                if today < last_seen:
                    # 系统时间被回滚了
                    trial_start = _date.fromisoformat(lic.trial_start)
                    trial_end = trial_start + _date.resolution * lic.trial_days
                    if last_seen > trial_end:
                        return False  # 试用已过期，回滚无效
            _update_last_seen(today.isoformat())

            # 2c. 检查试用是否已过期
            if lic.is_trial_expired:
                return False

            # 2d. build_date 窗口验证（防备份旧 EXE 攻击）
            build_cfg = _load_build_config()
            if build_cfg.get("build_date"):
                build_date = _date.fromisoformat(build_cfg["build_date"])
                trial_start = _date.fromisoformat(lic.trial_start)
                trial_window_end = build_date + _date.resolution * build_cfg["trial_days"]
                if trial_start > trial_window_end:
                    # trial_start 不应超过窗口上限 → 可能被篡改
                    return False

            return True

        return False

    def get_license_info(self) -> "LicenseConfig":
        """获取当前许可信息。"""
        return self._config.license

    # ── 内部方法 ──

    def _to_dict(self, cfg: AppConfig) -> dict:
        d = asdict(cfg)
        d.pop('version', None)
        d['version'] = cfg.version
        # 防止 QByteArray 等不可序列化类型进入 JSON
        d['window_geometry'] = str(d.get('window_geometry', ''))
        return d

    def _from_dict(self, raw: dict) -> AppConfig:
        version = raw.get('version', 1)
        cfg = AppConfig(
            version=version,
            font_size=raw.get('font_size', 13),
            theme=raw.get('theme', 'dark'),
            language=raw.get('language', 'zh_CN'),
            last_template_path=raw.get('last_template_path', ''),
            last_output_dir=raw.get('last_output_dir', ''),
            last_csv_paths=raw.get('last_csv_paths', []),
            window_geometry=str(raw.get('window_geometry', '')),
        )
        # LLM
        llm = raw.get('llm', {})
        cfg.llm = LLMConfig(
            enabled=llm.get('enabled', False),
            api_base=llm.get('api_base', 'https://api.anthropic.com/v1/messages'),
            model=llm.get('model', 'claude-sonnet-4-6'),
            use_local=llm.get('use_local', False),
            local_model=llm.get('local_model', 'qwen2.5:7b'),
            local_endpoint=llm.get('local_endpoint', 'http://localhost:11434'),
        )
        cfg.llm._api_key = llm.get('_api_key', '')
        # AI
        ai = raw.get('ai', {})
        cfg.ai = AIConfig(
            enabled=ai.get('enabled', False),
            mode=ai.get('mode', 'cloud'),
            api_base=ai.get('api_base', 'https://api.anthropic.com/v1/messages'),
            model=ai.get('model', 'claude-sonnet-4-6'),
            local_endpoint=ai.get('local_endpoint', 'http://localhost:11434'),
        )
        cfg.ai._api_key = ai.get('_api_key', '')
        # 许可
        lic = raw.get('license', {})
        cfg.license = LicenseConfig(
            product=lic.get('product', 'AntennaPostProcessor'),
            licensee=lic.get('licensee', ''),
            expiry=lic.get('expiry', 'PERMANENT'),
            features=lic.get('features', ['full']),
            issued=lic.get('issued', ''),
            machine_id=lic.get('machine_id', ''),
            signature=lic.get('signature', ''),
            trial_start=lic.get('trial_start', ''),
            trial_days=lic.get('trial_days', 30),
            trial_hmac=lic.get('trial_hmac', ''),
        )
        return cfg

    def _load_from_qsettings(self) -> AppConfig:
        """从 QSettings 加载配置。"""
        try:
            from PySide6.QtCore import QSettings
        except ImportError:
            return AppConfig()

        s = QSettings("AntennaPP", "AntennaPostProcessor")
        cfg = AppConfig(
            font_size=int(s.value("font/size", 13) or 13),
            theme=s.value("theme", "dark") or "dark",
            language=s.value("language", "zh_CN") or "zh_CN",
            last_template_path=s.value("template_path", "") or "",
            last_output_dir=s.value("output_dir", "") or "",
            window_geometry=str(s.value("window_geometry", "") or ""),
        )
        # CSV paths
        csv = s.value("csv_path", "")
        if csv:
            cfg.last_csv_paths = [csv] if isinstance(csv, str) else list(csv)

        # LLM
        cfg.llm.enabled = s.value("rag/enabled", False, type=bool)
        cfg.llm.api_base = s.value("rag/api_base", "https://api.anthropic.com/v1/messages") or "https://api.anthropic.com/v1/messages"
        cfg.llm.model = s.value("rag/model", "claude-sonnet-4-6") or "claude-sonnet-4-6"
        # 旧版加密 API Key → 迁移到新版
        old_key = s.value("rag/api_key", "") or ""
        if old_key:
            try:
                from src.license import decrypt_secret
                plain = decrypt_secret(old_key)
                if plain:
                    cfg.llm._api_key = encrypt_api_key(plain)
            except Exception:
                pass

        # AI
        cfg.ai.enabled = s.value("llm_ai/enabled", False, type=bool)
        cfg.ai.mode = s.value("llm_ai/mode", "cloud") or "cloud"
        cfg.ai.api_base = s.value("llm_ai/api_base", "https://api.anthropic.com/v1/messages") or "https://api.anthropic.com/v1/messages"
        cfg.ai.model = s.value("llm_ai/model", "claude-sonnet-4-6") or "claude-sonnet-4-6"
        cfg.ai.local_endpoint = s.value("llm_ai/local_endpoint", "http://localhost:11434") or "http://localhost:11434"
        old_ai_key = s.value("llm_ai/api_key", "") or ""
        if old_ai_key:
            try:
                from src.license import decrypt_secret
                plain = decrypt_secret(old_ai_key)
                if plain:
                    cfg.ai._api_key = encrypt_api_key(plain)
            except Exception:
                pass

        return cfg

    def _migrate_from_qsettings(self):
        """从 QSettings 迁移配置到文件。"""
        # 仅当 QSettings 有旧数据且文件不存在时
        pass  # 已在 _load_from_qsettings 中处理

    def _migrate_encryption(self):
        """如果 API Key 使用旧版 XOR 加密，升级到 AES。"""
        changed = False
        for which in ('llm', 'ai'):
            target = self._config.llm if which == 'llm' else self._config.ai
            encrypted = target._api_key
            if encrypted and not encrypted.startswith('aes:'):
                plain = decrypt_api_key(encrypted)
                if plain:
                    target._api_key = encrypt_api_key(plain)
                    changed = True
        if changed:
            self.save()


# ── 试用期机器 ID ──

def _get_machine_id_for_trial() -> str:
    """获取试用期机器标识（与 license.py 一致）。"""
    import uuid as _uuid
    node = _uuid.getnode()
    return hashlib.sha256(str(node).encode()).hexdigest()[:16]


# ── 全局单例 ──
_config_manager: Optional[ConfigManager] = None


def get_config() -> AppConfig:
    """获取全局配置单例。"""
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager()
        _config_manager.load()
    return _config_manager.config


def save_config():
    """保存全局配置。"""
    global _config_manager
    if _config_manager is not None:
        _config_manager.save()


def get_config_manager() -> ConfigManager:
    """获取配置管理器实例。"""
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager()
        _config_manager.load()
    return _config_manager
