#!/usr/bin/env python3
"""
Antenna Post-Processor 许可服务中心
===================================
部署在 ARM 实例上，提供：
  1. 试用申请页面（公开）     GET  /
  2. 申请提交                 POST /apply
  3. 管理员审批面板（token 保护）GET  /admin
  4. 批准/拒绝申请            POST /admin/approve | /admin/reject
  5. 激活码验证 + 许可签发     POST /activate
  6. 健康检查                 GET  /health

零外部依赖，仅使用 Python 标准库 + cryptography（许可签名）。
E-mail 通过 SMTP（QQ/Gmail/企业邮箱均可）。

部署:
  1. 上传本文件到 ARM 实例 /opt/antenna-activation/
  2. 上传 ECDSA 私钥到同目录下 .license_ecdsa_key.pem
  3. 创建 config.json（复制 config.json.example 修改）
  4. pip3 install cryptography
  5. python3 activation_server.py
  6. systemd 持久化（见底部注释）
"""

from __future__ import annotations

import hmac
import json
import os
import smtplib
import time
from datetime import date, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

# ── 路径（环境变量可覆盖）─────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent

def _env_path(env_name: str, default_name: str) -> Path:
    if env_name in os.environ:
        return Path(os.environ[env_name])
    return BASE_DIR / default_name

CONFIG_FILE = _env_path("CONFIG_FILE", "config.json")
APPS_FILE = _env_path("APPS_FILE", "applications.json")
CODES_FILE = _env_path("CODES_FILE", "activation_codes.json")
LOG_FILE = _env_path("LOG_FILE", "activation.log")
KEY_FILE = _env_path("KEY_FILE", ".license_ecdsa_key.pem")

# ── 配置 ────────────────────────────────────────────────


def load_config() -> dict:
    """加载配置，不存在则用默认值。"""
    default = {
        "host": "0.0.0.0",
        "port": 8899,
        "admin_token": "",          # 管理面板访问令牌（建议随机生成 32 字符）
        "site_name": "Antenna Post-Processor",
        "site_url": "https://example.com",
        "smtp": {
            "host": "smtp.163.com",
            "port": 465,
            "user": "your-email@163.com",
            "password": "",         # 163 邮箱需用授权码，非登录密码（设置 → POP3/SMTP/IMAP → 新增授权码）
            "from_name": "Antenna PP 许可中心",
            "use_tls": False,       # 163 用 SSL (port 465)，非 STARTTLS
        },
    }
    if CONFIG_FILE.exists():
        loaded = json.loads(CONFIG_FILE.read_text())
        # 深度合并 smtp 子配置
        if "smtp" in loaded:
            default["smtp"].update(loaded.pop("smtp"))
        default.update(loaded)
    return default


CONFIG = load_config()
ADMIN_TOKEN = CONFIG["admin_token"] or os.environ.get("ADMIN_TOKEN", "")

# ── 工具函数 ────────────────────────────────────────────────


def log(msg: str):
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line)
    try:
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")
    except OSError:
        pass


def load_json(path: Path) -> list:
    if path.exists():
        return json.loads(path.read_text())
    return []


def save_json(path: Path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def generate_activation_code() -> str:
    """生成随机激活码: APP-XXXX-XXXX-XXXX。"""
    import random
    import string
    chars = string.ascii_uppercase + string.digits
    groups = ["APP"]
    for _ in range(3):
        groups.append("".join(random.choices(chars, k=4)))
    return "-".join(groups)


# ── ECDSA 许可签发 ──────────────────────────────────────────


def sign_license(licensee: str, expiry_days: int, machine_id: str = "") -> dict:
    """用 ECDSA 私钥签发许可，返回完整 license JSON。"""
    import base64

    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.hashes import SHA256
    from cryptography.hazmat.primitives.serialization import load_pem_private_key

    if not KEY_FILE.exists():
        raise FileNotFoundError(f"ECDSA 私钥未找到: {KEY_FILE}")

    private_key = load_pem_private_key(KEY_FILE.read_bytes(), password=None)
    expiry = (date.today() + timedelta(days=expiry_days)).isoformat()
    issued = date.today().isoformat()

    data = {
        "product": "AntennaPostProcessor",
        "licensee": licensee,
        "expiry": expiry,
        "features": ["full"],
        "issued": issued,
        "machine_id": machine_id,
    }

    payload = json.dumps(data, sort_keys=True, ensure_ascii=False).encode("utf-8")
    signature = private_key.sign(payload, ec.ECDSA(SHA256()))
    data["signature"] = base64.b64encode(signature).decode("ascii")
    return data


# ── 激活码管理 ──────────────────────────────────────────────


def consume_code(code_str: str, machine_id: str) -> tuple[bool, str]:
    """消耗一次激活码。返回 (成功, license_json 或 错误消息)。"""
    codes = load_json(CODES_FILE)
    for c in codes:
        if c["code"] != code_str:
            continue

        code_expiry = c.get("expiry_date", "")
        if code_expiry:
            try:
                if date.today() > date.fromisoformat(code_expiry):
                    return False, f"激活码已过期 ({code_expiry})"
            except ValueError:
                pass

        max_use = c.get("max_activations", 1)
        used = c.get("used", 0)
        if used >= max_use:
            return False, f"激活码已达使用上限 ({used}/{max_use})"

        c["used"] = used + 1
        c.setdefault("activations", []).append({
            "machine_id": machine_id,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        })
        save_json(CODES_FILE, codes)

        licensee = c.get("licensee", "Licensed User")
        licence_days = c.get("licence_days", 90)
        license_data = sign_license(licensee, licence_days, machine_id)
        return True, json.dumps(license_data, ensure_ascii=False)

    return False, "激活码无效"


# ── E-mail 发送 ─────────────────────────────────────────────


def send_email(to: str, subject: str, body_html: str) -> bool:
    """发送 HTML 邮件。成功返回 True。"""
    cfg = CONFIG["smtp"]
    if not cfg.get("password"):
        log(f"  ⚠ SMTP 未配置密码，邮件未发送: {subject}")
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{cfg['from_name']} <{cfg['user']}>"
    msg["To"] = to
    msg.attach(MIMEText(body_html, "html", "utf-8"))

    try:
        if cfg.get("use_tls", True):
            server = smtplib.SMTP(cfg["host"], cfg["port"], timeout=15)
            server.starttls()
        else:
            server = smtplib.SMTP_SSL(cfg["host"], cfg["port"], timeout=15)
        server.login(cfg["user"], cfg["password"])
        server.sendmail(cfg["user"], [to], msg.as_string())
        server.quit()
        log(f"  ✓ 邮件已发送: {to} — {subject}")
        return True
    except Exception as e:
        log(f"  ✗ 邮件发送失败: {e}")
        return False


def send_approval_email(to: str, name: str, activation_code: str):
    """发送批准邮件（含激活码）。"""
    site = CONFIG["site_name"]
    body = f"""\
<html><body style="font-family: sans-serif;">
<h2>🎉 申请已通过 — {site}</h2>
<p>{name}，您好：</p>
<p>您的 <b>{site}</b> 试用申请已获批准。</p>
<p>激活码：</p>
<pre style="font-size:18px;background:#f5f5f5;padding:12px;border-radius:6px;">
<b>{activation_code}</b>
</pre>
<p>请在软件启动时输入此激活码完成激活。许可有效期 30 天。</p>
<hr>
<p style="color:#888;font-size:12px;">此邮件由系统自动发送，请勿回复。</p>
</body></html>"""
    send_email(to, f"{site} — 试用申请已批准", body)


def send_rejection_email(to: str, name: str, reason: str):
    """发送拒绝邮件。"""
    site = CONFIG["site_name"]
    body = f"""\
<html><body style="font-family: sans-serif;">
<h2>申请状态更新 — {site}</h2>
<p>{name}，您好：</p>
<p>很遗憾，您的 <b>{site}</b> 试用申请暂未通过。</p>
<p>原因：{reason}</p>
<p>如有疑问，请联系客服。</p>
<hr>
<p style="color:#888;font-size:12px;">此邮件由系统自动发送，请勿回复。</p>
</body></html>"""
    send_email(to, f"{site} — 申请状态更新", body)


# ── HTML 页面 ────────────────────────────────────────────────


def _base_html(title: str, body: str, extra_head: str = "") -> str:
    return f"""\
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} — {CONFIG['site_name']}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, 'Microsoft YaHei', sans-serif; background: #f0f2f5; color: #333; }}
  .container {{ max-width: 520px; margin: 60px auto; padding: 32px; background: #fff; border-radius: 12px; box-shadow: 0 2px 12px rgba(0,0,0,.08); }}
  h1 {{ font-size: 22px; margin-bottom: 8px; }}
  .subtitle {{ color: #888; margin-bottom: 24px; font-size: 14px; }}
  label {{ display: block; margin: 16px 0 6px; font-weight: 600; font-size: 14px; }}
  input, textarea, select {{ width: 100%; padding: 10px 12px; border: 1px solid #d9d9d9; border-radius: 6px; font-size: 14px; }}
  textarea {{ resize: vertical; min-height: 80px; }}
  button {{ width: 100%; padding: 12px; background: #1677ff; color: #fff; border: none; border-radius: 6px; font-size: 16px; cursor: pointer; margin-top: 20px; }}
  button:hover {{ background: #4096ff; }}
  button.danger {{ background: #ff4d4f; }}
  button.danger:hover {{ background: #ff7875; }}
  button.success {{ background: #52c41a; }}
  button.success:hover {{ background: #73d13d; }}
  .msg {{ padding: 12px; border-radius: 6px; margin: 16px 0; font-size: 14px; }}
  .msg.success {{ background: #f6ffed; border: 1px solid #b7eb8f; color: #389e0d; }}
  .msg.error {{ background: #fff2f0; border: 1px solid #ffccc7; color: #cf1322; }}
  .app-item {{ border: 1px solid #e8e8e8; border-radius: 8px; padding: 16px; margin: 12px 0; }}
  .app-item .meta {{ color: #888; font-size: 13px; margin: 4px 0; }}
  .app-item .actions {{ margin-top: 12px; display: flex; gap: 8px; }}
  .app-item .actions button {{ width: auto; flex: 1; padding: 8px; margin: 0; font-size: 14px; }}
  .status-badge {{ display: inline-block; padding: 2px 10px; border-radius: 10px; font-size: 12px; }}
  .status-badge.pending {{ background: #fff7e6; color: #d46b08; }}
  .status-badge.approved {{ background: #f6ffed; color: #389e0d; }}
  .status-badge.rejected {{ background: #fff2f0; color: #cf1322; }}
  .login-form {{ max-width: 360px; margin: 120px auto; }}
  table {{ width: 100%; border-collapse: collapse; }}
  th, td {{ text-align: left; padding: 8px 12px; border-bottom: 1px solid #f0f0f0; font-size: 14px; }}
  th {{ background: #fafafa; font-weight: 600; }}
</style>
{extra_head}
</head>
<body>
<div class="container">
{body}
</div>
</body>
</html>"""


PAGE_APPLY = _base_html(
    "申请试用",
    f"""\
<h1>🎯 申请试用</h1>
<p class="subtitle">{CONFIG['site_name']} — 天线参数后处理工具</p>

<form method="post" action="/apply" id="applyForm">
  <label>姓名 *</label>
  <input type="text" name="name" required placeholder="您的姓名">

  <label>邮箱 *</label>
  <input type="email" name="email" required placeholder="your@email.com">

  <label>公司/机构</label>
  <input type="text" name="company" placeholder="（选填）">

  <label>用途说明</label>
  <textarea name="purpose" placeholder="简要说明使用场景，有助于加快审批"></textarea>

  <input type="hidden" name="csrftoken" value="__TOKEN__">

  <button type="submit">📩 提交申请</button>
</form>

<p style="margin-top:24px;color:#999;font-size:13px;">
  提交后，管理员将在 1-2 个工作日内审核。<br>
  审核通过后，激活码将发送至您的邮箱。
</p>

<script>
// 简单的 CSRF token 生成
document.querySelector('[name=csrftoken]').value = Date.now().toString(36);
</script>""",
)


PAGE_APPLY_OK = _base_html(
    "申请已提交",
    """\
<h1>✅ 申请已提交</h1>
<div class="msg success">
  <b>申请成功！</b><br>
  管理员将在 1-2 个工作日内审核。<br>
  审核通过后，激活码将发送至您填写的邮箱。
</div>
<p style="color:#888;font-size:14px;margin-top:16px;">
  如有疑问，请联系客服。
</p>
""",
)


# ── Admin 面板 ──


def _app_status_badge(status: str) -> str:
    labels = {"pending": "待审核", "approved": "已批准", "rejected": "已拒绝"}
    return f'<span class="status-badge {status}">{labels.get(status, status)}</span>'


def _render_admin_page(token: str, msg: str = "") -> str:
    apps = load_json(APPS_FILE)
    codes = load_json(CODES_FILE)

    # 统计
    pending_count = sum(1 for a in apps if a["status"] == "pending")
    approved_count = sum(1 for a in apps if a["status"] == "approved")
    total_codes = len(codes)

    rows = ""
    for i, app in enumerate(apps):
        rows += f"""\
<div class="app-item">
  <b>{app['name']}</b> — {app.get('email', '')}
  <div class="meta">
    {app.get('company', '未填写公司')} &nbsp;|&nbsp;
    提交: {app.get('created', '')[:10]} &nbsp;|&nbsp;
    {_app_status_badge(app['status'])}
  </div>
  <div class="meta" style="margin-top:6px;">{app.get('purpose', '')}</div>
  <div class="actions">
    <button class="success" onclick="act({i},'approve')">✅ 批准</button>
    <button class="danger" onclick="act({i},'reject')">❌ 拒绝</button>
  </div>
</div>"""

    return _base_html(
        "管理面板",
        f"""\
<h1>📋 管理面板</h1>
<p class="subtitle">
  待审核: {pending_count} &nbsp;|&nbsp; 已批准: {approved_count} &nbsp;|&nbsp; 激活码存量: {total_codes}
</p>
{'<div class="msg success">' + msg + '</div>' if msg else ''}
{rows if rows else '<p style="color:#999;margin-top:30px;">暂无申请记录。</p>'}

<div style="margin-top:30px;padding-top:20px;border-top:1px solid #eee;">
  <details>
    <summary style="cursor:pointer;color:#888;font-size:13px;">📊 激活码列表 ({total_codes})</summary>
    <table style="margin-top:12px;">
      <tr><th>激活码</th><th>使用</th><th>创建</th></tr>
      {''.join(f'<tr><td style="font-family:monospace;">{c.get("code","")}</td><td>{c.get("used",0)}/{c.get("max_activations",1)}</td><td>{c.get("created","")[:10]}</td></tr>' for c in codes[:50])}
    </table>
  </details>
</div>

<script>
async function act(idx, action) {{
  const reason = action === 'reject' ? prompt('拒绝原因（可选）：') : '';
  const body = {{ index: idx, token: '{token}' }};
  if (reason) body.reason = reason;

  const resp = await fetch('/admin/' + action, {{
    method: 'POST',
    headers: {{ 'Content-Type': 'application/json' }},
    body: JSON.stringify(body)
  }});
  const data = await resp.json();
  if (data.ok) location.reload();
  else alert('操作失败: ' + (data.error || '未知错误'));
}}
</script>""",
    )


PAGE_ADMIN_LOGIN = _base_html(
    "管理员登录",
    """\
<h1>🔐 管理员登录</h1>
<form method="get" action="/admin">
  <label>管理令牌</label>
  <input type="password" name="token" placeholder="请输入管理员令牌" autofocus>
  <button type="submit">登录</button>
</form>
""",
)


# ── HTTP Handler ─────────────────────────────────────────────


class ServerHandler(BaseHTTPRequestHandler):
    """多页面 HTTP 服务处理。"""

    # 类级别缓存
    _admin_token: str = ADMIN_TOKEN

    def log_message(self, format, *args):
        log(f"{self.client_address[0]} — {args[0]}")

    def _send_html(self, code: int, html: str):
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

    def _send_json(self, code: int, data: dict):
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode())

    def _read_body(self) -> dict | None:
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return None
        raw = self.rfile.read(length)
        content_type = self.headers.get("Content-Type", "")

        if "application/json" in content_type:
            return json.loads(raw)
        if "application/x-www-form-urlencoded" in content_type:
            qs = parse_qs(raw.decode("utf-8"))
            return {k: v[0] for k, v in qs.items()}
        return None

    def _check_admin(self, body_token: str = "") -> bool:
        """验证管理令牌。支持 URL query、Cookie、POST body。"""
        # POST body token
        if body_token and self._admin_token:
            return hmac.compare_digest(body_token, self._admin_token)
        # URL query param
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        token = qs.get("token", [""])[0]
        if token and self._admin_token:
            return hmac.compare_digest(token, self._admin_token)
        return False

    # ── 路由 ──

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"

        if path == "/":
            self._send_html(200, PAGE_APPLY)

        elif path == "/health":
            self._send_json(200, {"status": "ok", "service": "antenna-activation"})

        elif path == "/admin":
            if not self._admin_token:
                self._send_html(200, PAGE_ADMIN_LOGIN.replace(
                    '<form method="get" action="/admin">',
                    '<h2 style="color:#cf1322;">⚠ 管理令牌未配置</h2><p style="color:#888;">请在 config.json 中设置 admin_token 或设置 ADMIN_TOKEN 环境变量。</p>'
                ))
                return
            if not self._check_admin():
                self._send_html(200, PAGE_ADMIN_LOGIN)
                return
            qs_raw = parse_qs(parsed.query)
            self._send_html(200, _render_admin_page(
                qs_raw.get("token", [""])[0]))

        else:
            self._send_json(404, {"error": "not found"})

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"

        # ── 激活码验证 ──
        if path == "/activate":
            body = self._read_body()
            if not body:
                self._send_json(400, {"error": "请求体为空"})
                return
            code = body.get("activation_code", "").strip()
            mid = body.get("machine_id", "").strip()
            if not code or not mid:
                self._send_json(400, {"error": "activation_code 或 machine_id 缺失"})
                return

            ok, result = consume_code(code, mid)
            if ok:
                self._send_json(200, {"license": json.loads(result)})
            else:
                self._send_json(403, {"error": result})

        # ── 申请提交 ──
        elif path == "/apply":
            body = self._read_body()
            if not body:
                self._send_html(400, _base_html("错误", "<h1>❌ 请求无效</h1>"))
                return

            name = body.get("name", "").strip()
            email = body.get("email", "").strip()
            if not name or not email:
                self._send_html(400, _base_html("错误", "<h1>❌ 姓名和邮箱为必填项</h1>"))
                return

            apps = load_json(APPS_FILE)
            apps.append({
                "name": name,
                "email": email,
                "company": body.get("company", "").strip(),
                "purpose": body.get("purpose", "").strip()[:500],
                "status": "pending",
                "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "reviewed": "",
                "activation_code": "",
            })
            save_json(APPS_FILE, apps)
            log(f"新申请: {name} <{email}>")
            self._send_html(200, PAGE_APPLY_OK)

        # ── Admin: 批准 ──
        elif path == "/admin/approve":
            body = self._read_body()
            if not body:
                self._send_json(400, {"error": "请求体为空"})
                return
            self._handle_approve(body)

        # ── Admin: 拒绝 ──
        elif path == "/admin/reject":
            body = self._read_body()
            if not body:
                self._send_json(400, {"error": "请求体为空"})
                return
            self._handle_reject(body)

        else:
            self._send_json(404, {"error": "not found"})

    # ── 审批逻辑 ──

    def _handle_approve(self, body: dict):
        token = body.pop("token", "")
        if not self._check_admin(token):
            self._send_json(401, {"error": "unauthorized"})
            return
        idx = body.get("index", -1)
        apps = load_json(APPS_FILE)
        if idx < 0 or idx >= len(apps):
            self._send_json(400, {"ok": False, "error": "索引无效"})
            return

        app = apps[idx]
        if app["status"] != "pending":
            self._send_json(400, {"ok": False, "error": f"该申请已处理 ({app['status']})"})
            return

        # 生成激活码
        code = generate_activation_code()
        codes = load_json(CODES_FILE)
        codes.append({
            "code": code,
            "max_activations": 1,
            "used": 0,
            "licence_days": 30,
            "licensee": app["name"],
            "expiry_date": "",
            "created": date.today().isoformat(),
            "activations": [],
        })
        save_json(CODES_FILE, codes)

        # 更新申请
        app["status"] = "approved"
        app["activation_code"] = code
        app["reviewed"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        save_json(APPS_FILE, apps)

        # 发送邮件
        send_approval_email(app["email"], app["name"], code)

        log(f"批准: {app['name']} <{app['email']}> → {code}")
        self._send_json(200, {"ok": True, "code": code})

    def _handle_reject(self, body: dict):
        token = body.pop("token", "")
        if not self._check_admin(token):
            self._send_json(401, {"error": "unauthorized"})
            return
        idx = body.get("index", -1)
        reason = body.get("reason", "").strip() or "请与管理员联系获取详情。"
        apps = load_json(APPS_FILE)
        if idx < 0 or idx >= len(apps):
            self._send_json(400, {"ok": False, "error": "索引无效"})
            return

        app = apps[idx]
        if app["status"] != "pending":
            self._send_json(400, {"ok": False, "error": f"该申请已处理 ({app['status']})"})
            return

        app["status"] = "rejected"
        app["reviewed"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        save_json(APPS_FILE, apps)

        send_rejection_email(app["email"], app["name"], reason)

        log(f"拒绝: {app['name']} <{app['email']}>")
        self._send_json(200, {"ok": True})


# ── 入口 ──


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Antenna Post-Processor 许可服务中心")
    parser.add_argument("--port", type=int, default=CONFIG["port"])
    parser.add_argument("--host", default=CONFIG["host"])
    args = parser.parse_args()

    # 首次运行提示
    if not ADMIN_TOKEN:
        log("⚠ 管理员令牌未配置！")
        log("  请在 config.json 中设置 admin_token，或设置 ADMIN_TOKEN 环境变量。")
        log("  建议随机生成: python3 -c \"import secrets; print(secrets.token_urlsafe(24))\"")
    if not CONFIG["smtp"]["password"]:
        log("⚠ SMTP 密码未配置！邮件发送将不可用。请在 config.json 中设置 smtp.password。")

    log(f"启动许可服务中心: http://{args.host}:{args.port}")
    log(f"  申请页面:   http://{args.host}:{args.port}/")
    log(f"  管理面板:   http://{args.host}:{args.port}/admin?token=<令牌>")
    log(f"  申请数据:   {APPS_FILE}")
    log(f"  激活码数据: {CODES_FILE}")

    server = HTTPServer((args.host, args.port), ServerHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n服务已停止")
        server.server_close()


if __name__ == "__main__":
    main()


# ═══════════════════════════════════════════════════════════════
# Systemd 单元文件 — /etc/systemd/system/antenna-activation.service
# ═══════════════════════════════════════════════════════════════
#
# [Unit]
# Description=Antenna Post-Processor Activation Service
# After=network.target
#
# [Service]
# Type=simple
# User=ubuntu
# WorkingDirectory=/opt/antenna-activation
# ExecStart=python3 /opt/antenna-activation/activation_server.py --port 8899
# Restart=on-failure
# RestartSec=10
#
# [Install]
# WantedBy=multi-user.target
#
# 启动: sudo systemctl enable --now antenna-activation
