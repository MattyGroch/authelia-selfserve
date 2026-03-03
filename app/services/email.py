import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import aiosmtplib

from app.config import settings
from app.services.tokens import create_action_token

logger = logging.getLogger(__name__)


async def _send(to: str, subject: str, html_body: str) -> None:
    msg = MIMEMultipart("alternative")
    msg["From"] = settings.from_email
    msg["To"] = to
    msg["Subject"] = subject
    msg.attach(MIMEText(html_body, "html"))

    try:
        await aiosmtplib.send(
            msg,
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_user or None,
            password=settings.smtp_password or None,
            start_tls=settings.smtp_starttls,
        )
    except Exception:
        logger.exception("Failed to send email to %s", to)
        raise


async def send_admin_notification(
    request_id: int,
    username: str,
    display_name: str,
    email: str,
) -> None:
    approve_token = create_action_token(request_id, "approve")
    deny_token = create_action_token(request_id, "deny")

    approve_url = f"{settings.app_url}/action/{approve_token}"
    deny_url = f"{settings.app_url}/action/{deny_token}"

    html = f"""\
<html>
<body style="font-family: sans-serif; color: #333; max-width: 600px;">
  <h2>New Registration Request</h2>
  <table style="border-collapse: collapse; width: 100%;">
    <tr><td style="padding: 6px 12px; font-weight: bold;">Username</td><td style="padding: 6px 12px;">{username}</td></tr>
    <tr><td style="padding: 6px 12px; font-weight: bold;">Display Name</td><td style="padding: 6px 12px;">{display_name}</td></tr>
    <tr><td style="padding: 6px 12px; font-weight: bold;">Email</td><td style="padding: 6px 12px;">{email}</td></tr>
  </table>
  <p style="margin-top: 24px;">
    <a href="{approve_url}" style="display: inline-block; padding: 10px 24px; background: #16a34a; color: #fff; text-decoration: none; border-radius: 6px; margin-right: 12px;">Approve</a>
    <a href="{deny_url}" style="display: inline-block; padding: 10px 24px; background: #dc2626; color: #fff; text-decoration: none; border-radius: 6px;">Deny</a>
  </p>
  <p style="font-size: 0.85em; color: #888;">These links expire in {settings.token_expiry_hours} hours. You can also manage requests from the <a href="{settings.app_url}/admin">admin dashboard</a>.</p>
</body>
</html>"""

    await _send(settings.admin_email, f"Registration request: {username}", html)


async def send_welcome_email(email: str, username: str, display_name: str) -> None:
    html = f"""\
<html>
<body style="font-family: sans-serif; color: #333; max-width: 600px;">
  <h2>Welcome, {display_name}!</h2>
  <p>Your registration request has been approved. You can now log in with your username <strong>{username}</strong> and the password you chose during registration.</p>
</body>
</html>"""

    await _send(email, "Your account has been approved", html)


async def send_denial_email(email: str, display_name: str) -> None:
    html = f"""\
<html>
<body style="font-family: sans-serif; color: #333; max-width: 600px;">
  <h2>Registration Update</h2>
  <p>Hi {display_name}, unfortunately your registration request has been denied. If you believe this is a mistake, please contact the administrator.</p>
</body>
</html>"""

    await _send(email, "Your registration request has been denied", html)
