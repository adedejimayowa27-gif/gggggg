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
    except httpx.HTTPStatusError as exc:
        # Log the response body, not just the exception -- Resend puts the
        # actual reason (e.g. "You can only send testing emails to your own
        # email address" for an unverified sending domain) in the JSON body,
        # which str(exc) doesn't include. Without this, a recipient-address
        # rejection and a bad API key look identical in the logs.
        logger.error(
            "Failed to send email %r to %s: %s -- response body: %s",
            subject, to, exc, exc.response.text,
        )
        return False
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


def render_verification_email(verify_url: str) -> tuple[str, str]:
    """Returns (subject, html) for a "confirm your email" message, sent at signup and on request via /auth/resend-verification."""
    subject = "Confirm your BizIntel email address"
    body = f"""
      <p style="font-size: 14px; line-height: 1.6;">
        Thanks for signing up for BizIntel. Please confirm this is your email address.
        This link expires in {settings.EMAIL_VERIFICATION_TOKEN_EXPIRE_MINUTES // 60} hours.
      </p>
      <p style="margin: 24px 0;">
        <a href="{verify_url}" style="background: #ffd60a; color: #14151a; padding: 12px 24px; border-radius: 6px; text-decoration: none; font-weight: 700; font-size: 14px; display: inline-block;">
          Confirm email address
        </a>
      </p>
      <p style="font-size: 13px; color: #666666; line-height: 1.6;">
        If you didn't create a BizIntel account, you can safely ignore this email.
      </p>
    """
    return subject, _base_template("Confirm your email", body)


def render_team_invite_email(business_name: str, inviter_email: str, signup_url: str) -> tuple[str, str]:
    """
    Returns (subject, html) for a team invite email.

    Unlike password reset, there's no token in this link -- inviting
    someone only creates a pending TeamMember row keyed by email (see
    app/services/team.py's link_pending_invites); whoever signs up with
    this exact email address is automatically linked. The link here is
    just a convenience straight to signup, not a credential.
    """
    subject = f"You've been invited to {business_name} on BizIntel"
    body = f"""
      <p style="font-size: 14px; line-height: 1.6;">
        <strong>{inviter_email}</strong> has invited you to join <strong>{business_name}</strong> on BizIntel.
        Sign up using this exact email address to get access automatically.
      </p>
      <p style="margin: 24px 0;">
        <a href="{signup_url}" style="background: #ffd60a; color: #14151a; padding: 12px 24px; border-radius: 6px; text-decoration: none; font-weight: 700; font-size: 14px; display: inline-block;">
          Create your account
        </a>
      </p>
    """
    return subject, _base_template(f"Join {business_name}", body)


SEVERITY_COLOR = {
    "CRITICAL": "#f87171",
    "HIGH": "#f87171",
    "MEDIUM": "#ffd60a",
    "LOW": "#8b8d96",
}


def render_alert_notification_email(business_name: str, alerts: list) -> tuple[str, str]:
    """
    Returns (subject, html) for a batch of newly-detected alerts --
    one email per detection run per recipient, not one email per alert,
    so five alerts firing at once produces one email to open, not five.
    `alerts` is a list of Alert ORM objects (severity/title/message).
    """
    count = len(alerts)
    subject = f"{count} new {'alert' if count == 1 else 'alerts'} for {business_name}"

    rows = "".join(
        f"""
        <div style="padding: 12px 0; border-bottom: 1px solid #e5e5e5;">
          <span style="display: inline-block; font-size: 11px; font-weight: 700; color: {SEVERITY_COLOR.get(a.severity, '#8b8d96')}; margin-bottom: 4px;">
            {a.severity}
          </span>
          <div style="font-size: 14px; font-weight: 700; color: #1a1a1a;">{a.title}</div>
          <div style="font-size: 13px; color: #555555; margin-top: 2px;">{a.message}</div>
        </div>
        """
        for a in alerts
    )
    body = f"""
      <p style="font-size: 14px; line-height: 1.6;">
        BizIntel found {count} new {"issue" if count == 1 else "issues"} worth a look in <strong>{business_name}</strong>:
      </p>
      {rows}
      <p style="font-size: 13px; color: #666666; margin-top: 16px;">
        Open the Alerts page in BizIntel to review, resolve, or dismiss these.
      </p>
    """
    return subject, _base_template(f"New activity in {business_name}", body)


def notify_team_of_new_alerts(db, business, alerts: list) -> None:
    """
    Emails every active team member (owner included -- the owner has
    their own "owner"-role TeamMember row, same as everyone else) about
    a batch of newly-detected alerts, restricted to HIGH/CRITICAL
    severity only. LOW/MEDIUM alerts still show up in-app -- they're
    just not urgent enough to interrupt someone's inbox for, matching
    how a Critical production incident gets paged but a minor one
    doesn't.

    Local imports (TeamMember, User) avoid a hard dependency from this
    module on the ORM at import time, consistent with this app's other
    service modules (see alert_engine.py's own local Alert import).
    """
    from app.models.team_member import TeamMember
    from app.models.user import User

    urgent = [a for a in alerts if a.severity in ("HIGH", "CRITICAL")]
    if not urgent:
        return

    recipients = (
        db.query(User.email)
        .join(TeamMember, TeamMember.user_id == User.id)
        .filter(TeamMember.business_id == business.id, TeamMember.status == "active")
        .distinct()
        .all()
    )
    if not recipients:
        return

    subject, html = render_alert_notification_email(business.name, urgent)
    for (email,) in recipients:
        send_email(email, subject, html)
