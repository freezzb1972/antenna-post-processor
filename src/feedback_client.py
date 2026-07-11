"""
反馈客户端 (纯逻辑, 无 Qt)
==========================
把用户反馈 POST 到反馈服务器 (ARM, 经 nginx /feedback 走公网 80)。
复用 activation 的结构: server_url(env/QSettings 可覆盖) + machine_id + HMAC 签名。

离线/失败时把反馈存本地队列 ~/.antenna/feedback_queue.jsonl, 下次启动重发。

服务器 URL 优先级:
  1. FEEDBACK_SERVER_URL 环境变量
  2. QSettings "feedback/server_url"
  3. 默认: http://138.2.77.171  (ARM, nginx 代理 /feedback → 127.0.0.1:8898)

安全: HMAC-SHA256 签名请求体 (完整性 + 防伪造刷屏), 密钥客户端/服务端共享。
      密钥内嵌于分发客户端, 属完整性校验非强鉴权 (可提取), 配合服务端限流+去重。
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from pathlib import Path

from .activation import get_machine_id

_DEFAULT_SERVER_URL = "http://138.2.77.171"

# HMAC 共享密钥 (与服务端 feedback_server 一致)。
_FEEDBACK_HMAC_KEY = bytes.fromhex(
    "d687edb748314e930ebde38ae7f325fbae98db7b1edb0f0898b86932ebe4e41d"
)

_QUEUE_PATH = Path.home() / ".antenna" / "feedback_queue.jsonl"

_MAX_TEXT = 8000  # 正文长度上限, 防滥用


def get_feedback_server_url() -> str:
    """获取反馈服务器 URL (env > QSettings > 默认)。"""
    import os
    env = os.environ.get("FEEDBACK_SERVER_URL", "")
    if env:
        return env.rstrip("/")
    try:
        from PySide6.QtCore import QSettings
        s = QSettings("AntennaPP", "AntennaPostProcessor")
        url = s.value("feedback/server_url", "")
        if url:
            return str(url).rstrip("/")
    except Exception:
        pass
    return _DEFAULT_SERVER_URL


def set_feedback_server_url(url: str) -> None:
    """持久化反馈服务器 URL 到 QSettings。"""
    try:
        from PySide6.QtCore import QSettings
        s = QSettings("AntennaPP", "AntennaPostProcessor")
        s.setValue("feedback/server_url", url)
    except Exception:
        pass


def _sign(body: bytes) -> str:
    return hmac.new(_FEEDBACK_HMAC_KEY, body, hashlib.sha256).hexdigest()


def _dedup_hash(machine_id: str, text: str) -> str:
    return hashlib.sha256(f"{machine_id}\x00{text}".encode("utf-8")).hexdigest()


def build_payload(category: str, text: str, *,
                  app_version: str = "",
                  machine_id: str | None = None,
                  attachments: dict | None = None) -> dict:
    """构造一条反馈记录 (契约见 FEEDBACK_SYSTEM_PLAN.md §6)。"""
    mid = (machine_id or get_machine_id()).strip()
    text = (text or "").strip()[:_MAX_TEXT]
    cat = category if category in ("bug", "feature", "other") else "other"
    return {
        "id": str(uuid.uuid4()),
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "machine_id": mid,
        "app_version": str(app_version or ""),
        "category": cat,
        "text": text,
        "attachments": attachments or {},
        "dedup_hash": _dedup_hash(mid, text),
        "status": "new",
    }


def submit_feedback(payload: dict, server_url: str | None = None,
                    timeout: int = 15) -> tuple[bool, str]:
    """POST 一条反馈到服务器。返回 (成功, 消息)。不落队列 (由 submit_or_queue 负责)。"""
    import urllib.error
    import urllib.request

    url = (server_url or get_feedback_server_url()).rstrip("/") + "/feedback"
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": "application/json", "X-Signature": _sign(body)},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("ok"):
                return True, str(data.get("message", "已提交"))
            return False, str(data.get("error", "服务器拒绝"))
    except urllib.error.HTTPError as e:
        try:
            return False, str(json.loads(e.read().decode("utf-8")).get("error", f"HTTP {e.code}"))
        except Exception:
            return False, f"服务器返回 HTTP {e.code}"
    except urllib.error.URLError as e:
        return False, f"无法连接反馈服务器: {e.reason}"
    except Exception as e:
        return False, f"提交失败: {e}"


def _queue_append(payload: dict) -> None:
    _QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _QUEUE_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def submit_or_queue(payload: dict, server_url: str | None = None) -> tuple[bool, str]:
    """提交反馈; 失败则存本地队列供下次重发。"""
    ok, msg = submit_feedback(payload, server_url)
    if not ok:
        _queue_append(payload)
        return False, f"{msg} — 已存本地队列, 下次启动自动重发"
    return True, msg


def resend_queue(server_url: str | None = None) -> tuple[int, int]:
    """重发本地队列。返回 (成功数, 剩余数)。全部成功则删除队列文件。"""
    if not _QUEUE_PATH.exists():
        return (0, 0)
    lines = [ln for ln in _QUEUE_PATH.read_text(encoding="utf-8").splitlines() if ln.strip()]
    remain: list[str] = []
    sent = 0
    for ln in lines:
        try:
            p = json.loads(ln)
        except Exception:
            continue  # 丢弃损坏行
        ok, _ = submit_feedback(p, server_url)
        if ok:
            sent += 1
        else:
            remain.append(ln)
    if remain:
        _QUEUE_PATH.write_text("\n".join(remain) + "\n", encoding="utf-8")
    else:
        try:
            _QUEUE_PATH.unlink()
        except OSError:
            pass
    return (sent, len(remain))
