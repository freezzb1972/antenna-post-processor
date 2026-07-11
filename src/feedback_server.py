#!/usr/bin/env python3
"""
反馈服务端 (独立进程, 与激活服务隔离)
======================================
接收桌面 App 的反馈, 验 HMAC 签名 → 存 SQLite feedback.db (去重), 供 Phase 3
的 triage claude 读取处理。纯 stdlib (http.server + sqlite3 + hmac), 无 Qt/无外部依赖。

部署 (ARM): 绑 127.0.0.1:8898, 由 nginx `location /feedback` 代理走公网 80。
  与激活服务 (8899) 独立进程/端口 → 反馈被刷不拖垮收费授权。

路由:
  POST /feedback            提交反馈 (验签 → 去重 → 存库)
  GET  /health              健康检查
  GET  /admin/feedback?token=…   查看反馈列表 (admin token)

安全: HMAC-SHA256 验签 (与客户端共享密钥) + 正文长度上限 + 简单限流 + dedup。
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import sqlite3
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

# HMAC 共享密钥 (与 src/feedback_client.py 一致); 可用 FEEDBACK_HMAC_KEY(hex) 覆盖。
_DEFAULT_HMAC_KEY = "d687edb748314e930ebde38ae7f325fbae98db7b1edb0f0898b86932ebe4e41d"

MAX_BODY = 3_000_000          # 正文 ≤3MB (含 base64 截图)
RATE_MAX = 30                 # 每 IP 每窗口最多请求数
RATE_WINDOW = 60              # 限流窗口 (秒)

_DB_PATH = "feedback.db"
_ADMIN_TOKEN = ""
_HMAC_KEY = b""

# 每 IP 请求时间戳 (内存滑动窗口限流)
_rate: dict[str, deque] = {}


def log(msg: str):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


# ── SQLite ──
def _init_db(path: str):
    con = sqlite3.connect(path)
    con.execute("""
        CREATE TABLE IF NOT EXISTS feedback (
            id           TEXT PRIMARY KEY,
            ts           TEXT,
            received_ts  TEXT,
            machine_id   TEXT,
            app_version  TEXT,
            category     TEXT,
            text         TEXT,
            attachments  TEXT,
            dedup_hash   TEXT UNIQUE,
            client_ip    TEXT,
            status       TEXT DEFAULT 'new',
            triage       TEXT
        )
    """)
    con.commit()
    con.close()


def _store(record: dict, client_ip: str) -> str:
    """存一条反馈。返回 'stored' | 'duplicate'。"""
    con = sqlite3.connect(_DB_PATH)
    try:
        cur = con.execute(
            """INSERT OR IGNORE INTO feedback
               (id, ts, received_ts, machine_id, app_version, category, text,
                attachments, dedup_hash, client_ip, status, triage)
               VALUES (?,?,?,?,?,?,?,?,?,?, 'new', NULL)""",
            (
                record.get("id", ""),
                record.get("ts", ""),
                time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                record.get("machine_id", ""),
                record.get("app_version", ""),
                record.get("category", "other"),
                (record.get("text", "") or "")[:8000],
                json.dumps(record.get("attachments", {}), ensure_ascii=False),
                record.get("dedup_hash", ""),
                client_ip,
            ),
        )
        con.commit()
        return "stored" if cur.rowcount > 0 else "duplicate"
    finally:
        con.close()


# ── 限流 ──
def _rate_ok(ip: str) -> bool:
    now = time.time()
    dq = _rate.setdefault(ip, deque())
    while dq and now - dq[0] > RATE_WINDOW:
        dq.popleft()
    if len(dq) >= RATE_MAX:
        return False
    dq.append(now)
    return True


def _verify_sig(raw: bytes, sig: str) -> bool:
    if not sig:
        return False
    expected = hmac.new(_HMAC_KEY, raw, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig)


class FeedbackHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        log(f"{self.client_address[0]} — {args[0]}")

    def _json(self, code: int, data: dict):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _client_ip(self) -> str:
        # nginx 代理后取 X-Forwarded-For, 否则 socket 地址
        xff = self.headers.get("X-Forwarded-For", "")
        return xff.split(",")[0].strip() if xff else self.client_address[0]

    def do_GET(self):
        path = urlparse(self.path).path.rstrip("/") or "/"
        if path == "/health":
            self._json(200, {"ok": True, "service": "feedback"})
            return
        if path == "/admin/feedback":
            qs = parse_qs(urlparse(self.path).query)
            token = qs.get("token", [""])[0]
            if not _ADMIN_TOKEN or not hmac.compare_digest(token, _ADMIN_TOKEN):
                self._json(403, {"ok": False, "error": "forbidden"})
                return
            con = sqlite3.connect(_DB_PATH)
            try:
                rows = con.execute(
                    "SELECT id, received_ts, category, status, substr(text,1,120) "
                    "FROM feedback ORDER BY received_ts DESC LIMIT 200"
                ).fetchall()
            finally:
                con.close()
            self._json(200, {"ok": True, "count": len(rows),
                             "items": [dict(zip(
                                 ("id", "received_ts", "category", "status", "preview"), r))
                                 for r in rows]})
            return
        self._json(404, {"ok": False, "error": "not found"})

    def do_POST(self):
        path = urlparse(self.path).path.rstrip("/") or "/"
        if path != "/feedback":
            self._json(404, {"ok": False, "error": "not found"})
            return

        ip = self._client_ip()
        if not _rate_ok(ip):
            self._json(429, {"ok": False, "error": "rate limited"})
            return

        length = int(self.headers.get("Content-Length", 0))
        if length <= 0 or length > MAX_BODY:
            self._json(413, {"ok": False, "error": "body too large or empty"})
            return
        raw = self.rfile.read(length)

        if not _verify_sig(raw, self.headers.get("X-Signature", "")):
            self._json(401, {"ok": False, "error": "bad signature"})
            return

        try:
            record = json.loads(raw.decode("utf-8"))
        except Exception:
            self._json(400, {"ok": False, "error": "invalid json"})
            return

        if not record.get("text") or not record.get("dedup_hash"):
            self._json(400, {"ok": False, "error": "missing fields"})
            return

        try:
            result = _store(record, ip)
        except Exception as e:
            log(f"存储失败: {e}")
            self._json(500, {"ok": False, "error": "storage error"})
            return

        msg = "已收到反馈" if result == "stored" else "反馈已存在(去重)"
        self._json(200, {"ok": True, "message": msg, "result": result})


def main():
    global _DB_PATH, _ADMIN_TOKEN, _HMAC_KEY
    ap = argparse.ArgumentParser(description="反馈服务端")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8898)
    ap.add_argument("--db", default=str(Path.home() / ".antenna_feedback" / "feedback.db"))
    args = ap.parse_args()

    key_hex = os.environ.get("FEEDBACK_HMAC_KEY", _DEFAULT_HMAC_KEY)
    _HMAC_KEY = bytes.fromhex(key_hex)
    _ADMIN_TOKEN = os.environ.get("FEEDBACK_ADMIN_TOKEN", "")
    _DB_PATH = args.db
    Path(_DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    _init_db(_DB_PATH)

    log(f"反馈服务启动: http://{args.host}:{args.port}  db={_DB_PATH}")
    if not _ADMIN_TOKEN:
        log("  ⚠ 未设 FEEDBACK_ADMIN_TOKEN — /admin/feedback 将拒绝所有请求")
    server = ThreadingHTTPServer((args.host, args.port), FeedbackHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log("停止")
        server.shutdown()


if __name__ == "__main__":
    main()
