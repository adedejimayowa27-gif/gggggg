"""
Transactional email via Resend's HTTP API.

Provider-specific by design, matching this project's existing
HTTP-client-per-integration convention (see google_oauth.py,
microsoft_graph.py) rather than a generic "email provider" abstraction:
there's exactly one call site to change if the provider ever changes
(this module), and no speculative interface for providers this app
doesn't use.

Every send here is best-effort: a missing RESEND_API_KEY or a failed
HTTP call is logged and returns False rather than raising, so an email
failure never takes down the request that triggered it (password
reset, a team invite, an alert firing) -- same "degrade, don't crash"
posture this app already applies to Groq and Stripe.
"""
import logging

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

RESEND_API_URL = "https://api.resend.com/emails"


def send_email(to: str, subject: str, html: str) -> bool:
    """
    Sends one HTML email. Returns True if Resend accepted it, False on
    any failure (missing config, network error, non-2xx response) --
    logged either way, so a silent failure is still visible in server
    logs even though callers don't have to handle an exception.
    """
    if not settings.RESEND_API_KEY:
        logger.warning("Email not sent (RESEND_API_KEY not configured): %r to %s", subject, to)
        return False

    try:
        response = httpx.post(
            RESEND_API_URL,
            headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}"},
            json={
                "from": settings.EMAIL_FROM_ADDRESS,
                "to": [to],
                "subject": subject,
                "html": html,
            },
            timeout=10.0,
        )
        response.raise_for_status()
        return True
    except httpx.HTTPError as exc:
        logger.error("Failed to send email %r to %s: %s", subject, to, exc)
        return False


def _base_template(heading: str, body_html: str) -> str:
    """
    A minimal, inbox-safe HTML shell. No external assets or <style>
    blocks -- most email clients strip or block both unpredictably --
    so every rule here is an inline style, and the whole thing is one
    plain div rather than a table-based layout, which is fine at this
    level of simplicity (a heading, a paragraph, one button).
    """
    return f"""
    <div style="font-family: -apple-system, Helvetica, Arial, sans-serif; max-width: 480px; margin: 0 auto; padding: 32px 24px; color: #1a1a1a;">
      <div style="font-size: 20px; font-weight: 700; margin-bottom: 24px;">BizIntel</div>
      <div style="font-size: 16px; font-weight: 700; margin-bottom: 12px;">{heading}</div>
      {body_html}
      <div style="margin-top: 32px; padding-top: 16px; border-top: 1px solid #e5e5e5; font-size: 12px; color: #888888;">
        BizIntel -- turning your sales records into decisions.
      </div>
    </div>
    """


def render_password_reset_email(reset_url: str) -> tuple[str, str]:
    """Returns (subject, html) for a password-reset email."""
    subject = "Reset your BizIntel password"
    body = f"""
      <p style="font-size: 14px; line-height: 1.6;">
        We received a request to reset your BizIntel password. This link expires in
        {settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES} minutes.
      </p>
      <p style="margin: 24px 0;">
        <a href="{reset_url}" style="background: #ffd60a; color: #14151a; padding: 12px 24px; border-radius: 6px; text-decoration: none; font-weight: 700; font-size: 14px; display: inline-block;">
          Reset password
        </a>
      </p>
      <p style="font-size: 13px; color: #666666; line-height: 1.6;">
        If you didn't request this, you can safely ignore this email -- your password won't change.
      </p>
    """
    return subject, _base_template("Reset your password", body)
