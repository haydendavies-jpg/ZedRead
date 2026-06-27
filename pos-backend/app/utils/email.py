"""Email sending utility using the Resend API.

All outbound email goes through this module so the Resend client is
instantiated once and the API key is read from the environment in a
single place.
"""

import os

import resend
import structlog

log = structlog.get_logger(__name__)

# Resend client is initialised at import time — the API key must be set
# before any route that sends email is called.
resend.api_key = os.getenv("RESEND_API_KEY", "")

# The sender address shown in the From header.  Override via env var for
# custom domains; falls back to Resend's shared sandbox address for dev.
_FROM_ADDRESS: str = os.getenv("EMAIL_FROM", "ZedRead POS <onboarding@resend.dev>")

# Invite link base URL — the Android/portal app that handles /invite/accept
_INVITE_BASE_URL: str = os.getenv("INVITE_BASE_URL", "http://localhost:5173")

# Invite tokens expire after this many hours
INVITE_EXPIRY_HOURS: int = int(os.getenv("INVITE_EXPIRY_HOURS", "72"))

# Password reset link base URL — the portal app that handles /reset-password
_PORTAL_BASE_URL: str = os.getenv("PORTAL_BASE_URL", "http://localhost:5173")

# Password reset tokens expire after this many hours
PASSWORD_RESET_EXPIRY_HOURS: int = int(os.getenv("PASSWORD_RESET_EXPIRY_HOURS", "1"))


async def send_invite_email(
    to_email: str,
    inviter_name: str,
    brand_name: str,
    site_name: str,
    token: str,
) -> None:
    """
    Send a POS user invitation email via Resend.

    The email contains a link with the raw invite token embedded as a query
    parameter.  The receiving app (portal or Android) exchanges the token via
    POST /invites/accept.

    Args:
        to_email: Recipient email address.
        inviter_name: Display name of the person who sent the invite.
        brand_name: Name of the brand the invitee is joining.
        site_name: Name of the specific site they are being granted access to.
        token: The unique invite token to embed in the link.

    Returns:
        None

    Raises:
        Exception: Re-raised from the Resend SDK if the API call fails.
                   Callers should handle this and roll back the DB transaction.
    """
    invite_url = f"{_INVITE_BASE_URL}/invite/accept?token={token}"

    html_body = f"""
<html>
  <body style="font-family: sans-serif; color: #333; max-width: 560px; margin: 0 auto;">
    <h2 style="color: #7b1d2a;">You've been invited to ZedRead POS</h2>
    <p>
      <strong>{inviter_name}</strong> has invited you to join
      <strong>{brand_name}</strong> at <strong>{site_name}</strong>.
    </p>
    <p>Click the button below to set up your account. This link expires in {INVITE_EXPIRY_HOURS} hours.</p>
    <p>
      <a href="{invite_url}"
         style="display:inline-block;padding:12px 24px;background:#7b1d2a;color:#fff;
                text-decoration:none;border-radius:4px;font-weight:600;">
        Accept Invitation
      </a>
    </p>
    <p style="color:#888;font-size:0.85em;">
      Or copy this link: {invite_url}
    </p>
  </body>
</html>
"""

    log.info("email.invite.sending", to=to_email, brand=brand_name, site=site_name)
    try:
        resend.Emails.send({
            "from": _FROM_ADDRESS,
            "to": [to_email],
            "subject": f"You've been invited to {brand_name} on ZedRead POS",
            "html": html_body,
        })
        log.info("email.invite.sent", to=to_email)
    except Exception:
        log.error("email.invite.failed", to=to_email, exc_info=True)
        raise


async def send_password_reset_email(to_email: str, token: str) -> None:
    """
    Send a password reset email via Resend.

    The email contains a link with the raw reset token embedded as a query
    parameter. The portal exchanges the token via POST /auth/portal/reset-password.

    Args:
        to_email: Recipient email address.
        token: The unique password reset token to embed in the link.

    Returns:
        None

    Raises:
        Exception: Re-raised from the Resend SDK if the API call fails.
                   Callers should handle this and roll back the DB transaction.
    """
    reset_url = f"{_PORTAL_BASE_URL}/reset-password?token={token}"

    html_body = f"""
<html>
  <body style="font-family: sans-serif; color: #333; max-width: 560px; margin: 0 auto;">
    <h2 style="color: #7b1d2a;">Reset your ZedRead POS password</h2>
    <p>We received a request to reset the password for this account.</p>
    <p>Click the button below to choose a new password. This link expires in {PASSWORD_RESET_EXPIRY_HOURS} hour(s).</p>
    <p>
      <a href="{reset_url}"
         style="display:inline-block;padding:12px 24px;background:#7b1d2a;color:#fff;
                text-decoration:none;border-radius:4px;font-weight:600;">
        Reset Password
      </a>
    </p>
    <p style="color:#888;font-size:0.85em;">
      Or copy this link: {reset_url}
    </p>
    <p style="color:#888;font-size:0.85em;">
      If you did not request this, you can safely ignore this email.
    </p>
  </body>
</html>
"""

    log.info("email.password_reset.sending", to=to_email)
    try:
        resend.Emails.send({
            "from": _FROM_ADDRESS,
            "to": [to_email],
            "subject": "Reset your ZedRead POS password",
            "html": html_body,
        })
        log.info("email.password_reset.sent", to=to_email)
    except Exception:
        log.error("email.password_reset.failed", to=to_email, exc_info=True)
        raise
