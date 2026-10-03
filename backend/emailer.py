"""Resend transactional email sender.

Guardrails G1-G6 enforced:
- G1 brand name is "NEXBIT" (this app's own brand)
- G2 no credential harvesting (gate rejects form/input tags and ask-back phrasing)
- G3 all hrefs/srcs are absolute https (gate enforces)
- G4 no caller-supplied recipient/subject/body — all templates server-side
- G5 transactional only — triggered by signup / password reset / withdrawal events
"""
import os
import re
import ipaddress
import logging
import httpx
from html import escape
from html.parser import HTMLParser
from urllib.parse import urlparse
from pathlib import Path
from dotenv import load_dotenv
from fastapi import HTTPException

load_dotenv(Path(__file__).parent / ".env")
logger = logging.getLogger("nexbit.email")

# Resend REST API endpoint and credentials.
EMAIL_BASE_URL = "https://api.resend.com"
EMAIL_KEY = os.environ.get("NEXBIT_EMAIL_KEY", "")
EMAIL_FROM_NAME = os.environ.get("EMAIL_FROM_NAME", "NEXBIT")
EMAIL_FROM_ADDRESS = os.environ.get("EMAIL_FROM_ADDRESS", "onboarding@resend.dev")
EMAIL_REPLY_TO = os.environ.get("EMAIL_REPLY_TO")
APP_URL = os.environ.get("APP_URL", "http://localhost:3000").rstrip("/")

# -------------------- Guardrail Gate --------------------
_SHORTENERS = ("bit.ly", "tinyurl.com", "t.co", "is.gd", "cutt.ly", "goo.gl", "rebrand.ly")
_CRED_ASK = (
    "reply with your password", "reply with the code", "send your password", "cvv",
    "send us your password", "enter your password below", "confirm your card number",
    "your full card number", "seed phrase", "recovery phrase", "verify your card",
    "social security number", "confirm your bank details",
)
_HOSTISH = re.compile(r"\b(?:https?://)?((?:[a-z0-9-]+\.)+[a-z]{2,})", re.I)


def _host_ok(host: str) -> bool:
    if not host or "xn--" in host:
        return False
    try:
        ipaddress.ip_address(host)
        return False
    except ValueError:
        pass
    return not any(host == s or host.endswith("." + s) for s in _SHORTENERS)


def _same_site(shown: str, real: str) -> bool:
    return shown == real or real.endswith("." + shown) or shown.endswith("." + real)


class _EmailScan(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags, self.urls, self.anchors = set(), [], []
        self._href, self._text = None, []

    def handle_starttag(self, tag, attrs):
        self.tags.add(tag.lower())
        self.urls += [v for k, v in attrs if k.lower() in ("href", "src") and v]
        if tag.lower() == "a":
            self._href = dict((k.lower(), v) for k, v in attrs).get("href")
            self._text = []

    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag.lower() == "a" and self._href is not None:
            self.anchors.append((self._href, "".join(self._text)))
            self._href, self._text = None, []


def _assert_safe_email(subject: str, html: str) -> None:
    scan = _EmailScan()
    scan.feed(html)
    if scan.tags & {"form", "input", "textarea", "select"}:
        raise ValueError("No forms or input fields in email (G2)")
    body = f"{subject}\n{html}".lower()
    for p in _CRED_ASK:
        if p in body:
            raise ValueError(f"Email asks the recipient for credentials: {p!r} (G2)")
    for url in scan.urls:
        low = url.strip().lower()
        if low.startswith(("mailto:", "tel:", "cid:", "#")):
            continue
        if not low.startswith("https://"):
            raise ValueError(f"Email links/assets must be absolute https: {url!r} (G3)")
        host = urlparse(low).hostname or ""
        if not _host_ok(host) or urlparse(low).username is not None:
            raise ValueError(f"Shortened, numeric-host or credential-bearing URL: {url!r} (G3)")
    for href, text in scan.anchors:
        real = urlparse(href.strip().lower()).hostname or ""
        if not real:
            continue
        for m in _HOSTISH.finditer(text):
            if not _same_site(m.group(1).lower(), real):
                raise ValueError(f"Anchor text {m.group(1)!r} ≠ real link host {real!r} (G3)")


# -------------------- Core send --------------------
async def send_email(*, to: str, subject: str, html: str) -> str | None:
    if not EMAIL_KEY:
        logger.warning("NEXBIT_EMAIL_KEY missing — skipping send to %s", to)
        return None
    _assert_safe_email(subject, html)
    payload = {
        "from": f"{EMAIL_FROM_NAME} <{EMAIL_FROM_ADDRESS}>",
        "to": [to],
        "subject": subject,
        "html": html,
    }
    if EMAIL_REPLY_TO:
        payload["reply_to"] = EMAIL_REPLY_TO
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                f"{EMAIL_BASE_URL}/emails",
                headers={
                    "Authorization": f"Bearer {EMAIL_KEY}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        r.raise_for_status()
        return r.json().get("id")
    except httpx.HTTPStatusError as e:
        logger.error("Email send failed: %s %s", e.response.status_code, e.response.text)
        raise HTTPException(status_code=502, detail="Failed to send email")
    except Exception as e:  # pragma: no cover
        logger.error("Email send error: %s", e)
        raise HTTPException(status_code=500, detail="Failed to send email")


# -------------------- Shared template chrome --------------------
def _wrap(inner: str) -> str:
    return (
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="background:#070a12;padding:32px 0;font-family:Arial,Helvetica,sans-serif;color:#f1f5f9">'
        '<tr><td align="center">'
        '<table role="presentation" width="560" cellpadding="0" cellspacing="0" '
        'style="background:#0b0f1a;border:1px solid #1e293b;border-radius:14px;overflow:hidden">'
        '<tr><td style="padding:28px 32px 8px 32px">'
        '<div style="font-family:Arial,Helvetica,sans-serif;font-size:20px;font-weight:700;letter-spacing:2px;color:#00d4ff">NEXBIT</div>'
        '<div style="font-size:11px;color:#64748b;margin-top:4px;letter-spacing:2px;text-transform:uppercase">Crypto for what&#39;s next.</div>'
        '</td></tr>'
        f'<tr><td style="padding:16px 32px 24px 32px">{inner}</td></tr>'
        '<tr><td style="padding:16px 32px 28px 32px;border-top:1px solid #1e293b;color:#64748b;font-size:12px">'
        'This message was sent by NEXBIT. For your safety, we will never ask you for sensitive account details over email.'
        '<br/>If you did not request this action, you can safely ignore this email.'
        '</td></tr>'
        '</table></td></tr></table>'
    )


# -------------------- Transactional templates --------------------
async def send_welcome_verify(*, to: str, name: str, code: str) -> str | None:
    safe_name = escape(name or to.split("@")[0])
    safe_code = escape(code)
    inner = (
        f'<p style="font-size:16px;line-height:1.5;color:#f1f5f9">Hi <strong>{safe_name}</strong>,</p>'
        '<p style="font-size:14px;line-height:1.6;color:#cbd5e1">Welcome to NEXBIT. Use the code below to verify your email address and activate your account.</p>'
        f'<div style="margin:24px 0;padding:20px;background:#111726;border:1px solid #22e3ff33;border-radius:10px;text-align:center">'
        f'<div style="font-family:Menlo,Consolas,monospace;font-size:30px;letter-spacing:8px;color:#00d4ff;font-weight:700">{safe_code}</div>'
        f'<div style="font-size:11px;color:#64748b;margin-top:8px;text-transform:uppercase;letter-spacing:1px">Verification code · expires in 15 minutes</div>'
        f'</div>'
        f'<p style="font-size:13px;color:#94a3b8">Or verify instantly: '
        f'<a href="{APP_URL}/verify-email" style="color:#00d4ff;text-decoration:none">Open NEXBIT</a></p>'
    )
    return await send_email(to=to, subject="Verify your NEXBIT account", html=_wrap(inner))


async def send_password_reset(*, to: str, name: str, token: str) -> str | None:
    safe_name = escape(name or to.split("@")[0])
    link = f"{APP_URL}/reset?token={escape(token)}"
    inner = (
        f'<p style="font-size:16px;line-height:1.5;color:#f1f5f9">Hi <strong>{safe_name}</strong>,</p>'
        '<p style="font-size:14px;line-height:1.6;color:#cbd5e1">We received a request to reset your NEXBIT password. Click the button below to choose a new one. This link expires in 1 hour.</p>'
        f'<p style="margin:28px 0;text-align:center">'
        f'<a href="{link}" style="display:inline-block;background:#00d4ff;color:#040812;font-weight:700;text-decoration:none;padding:12px 24px;border-radius:10px;font-size:14px">Reset my password</a>'
        f'</p>'
        f'<p style="font-size:12px;color:#64748b;word-break:break-all">Or copy this link into your browser:<br/>'
        f'<a href="{link}" style="color:#00d4ff">{link}</a></p>'
    )
    return await send_email(to=to, subject="Reset your NEXBIT password", html=_wrap(inner))


async def send_withdrawal_update(*, to: str, name: str, asset: str, amount: float, status: str, note: str | None = None) -> str | None:
    safe_name = escape(name or to.split("@")[0])
    safe_asset = escape(asset)
    safe_status = escape(status.upper())
    status_color = "#00c389" if status == "approved" else "#ff4d6b"
    note_html = f'<p style="font-size:13px;color:#94a3b8">Note from NEXBIT: {escape(note)}</p>' if note else ""
    inner = (
        f'<p style="font-size:16px;line-height:1.5;color:#f1f5f9">Hi <strong>{safe_name}</strong>,</p>'
        f'<p style="font-size:14px;line-height:1.6;color:#cbd5e1">Your withdrawal request has been <strong style="color:{status_color}">{safe_status}</strong>.</p>'
        f'<div style="margin:20px 0;padding:16px 20px;background:#111726;border:1px solid #1e293b;border-radius:10px">'
        f'<div style="font-size:12px;color:#64748b;text-transform:uppercase;letter-spacing:1px">Amount</div>'
        f'<div style="font-family:Menlo,Consolas,monospace;font-size:22px;font-weight:700;color:#f1f5f9">{amount:.6f} {safe_asset}</div>'
        f'</div>'
        f'{note_html}'
        f'<p style="font-size:13px;color:#94a3b8">Review the full transaction in your wallet: '
        f'<a href="{APP_URL}/wallet" style="color:#00d4ff;text-decoration:none">Open wallet</a></p>'
    )
    return await send_email(to=to, subject=f"Withdrawal {status} · {amount:.6f} {asset}", html=_wrap(inner))
