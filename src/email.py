import os
import logging
import resend

resend.api_key = os.environ.get("RESEND_API_KEY", "")
_log = logging.getLogger(__name__)

FROM_ADDRESS = "RippleForge <noreply@rippleforge.gg>"


def _wrap(body: str) -> str:
    return (
        f'<div style="font-family:Arial,sans-serif;max-width:520px;margin:0 auto;'
        f'background:#ffffff;color:#222222;padding:32px 24px;">'
        f'<p style="font-size:0.8rem;color:#888;margin:0 0 24px;">RippleForge</p>'
        f'{body}'
        f'<p style="font-size:0.75rem;color:#aaa;margin:32px 0 0;border-top:1px solid #eee;padding-top:16px;">'
        f'You received this because someone added your email to a RippleForge campaign. '
        f'If this was unexpected, you can ignore it.</p>'
        f'</div>'
    )


def _link(url: str, label: str) -> str:
    return f'<a href="{url}" style="color:#2563eb;">{label}</a>'


def send_turn_notification(to: str, character_name: str, campaign_name: str, turn_url: str) -> bool:
    html = _wrap(
        f'<p style="font-size:1rem;font-weight:bold;margin:0 0 8px;">{campaign_name}</p>'
        f'<p style="margin:0 0 20px;line-height:1.6;color:#444;">It\'s {character_name}\'s turn. '
        f'The world is waiting.</p>'
        f'<p style="margin:0;">{_link(turn_url, "Take your turn →")}</p>'
    )
    return send(to, f"Your turn in {campaign_name}", html)


def send_invite(to: str, campaign_name: str, inviter_display: str, join_url: str) -> bool:
    html = _wrap(
        f'<p style="font-size:1rem;font-weight:bold;margin:0 0 8px;">{inviter_display} invited you to {campaign_name}</p>'
        f'<p style="margin:0 0 20px;line-height:1.6;color:#444;">'
        f'You\'ve been added to a campaign on RippleForge. Sign in with Google to join.</p>'
        f'<p style="margin:0;">{_link(join_url, "Open the campaign →")}</p>'
    )
    return send(to, f"You're invited to {campaign_name} on RippleForge", html)


def send_skip_notification(to: str, character_name: str, campaign_name: str) -> bool:
    html = _wrap(
        f'<p style="font-size:1rem;font-weight:bold;margin:0 0 8px;">{campaign_name}</p>'
        f'<p style="margin:0;line-height:1.6;color:#444;">{character_name}\'s turn was skipped — '
        f'the deadline passed. You\'re back in the rotation.</p>'
    )
    return send(to, f"Your turn was skipped in {campaign_name}", html)


def send(to: str, subject: str, html: str) -> bool:
    """Send a transactional email. Returns True on success, False on failure."""
    if not resend.api_key:
        _log.error("Resend: RESEND_API_KEY is not set")
        return False
    try:
        resend.Emails.send({
            "from": FROM_ADDRESS,
            "to": [to],
            "subject": subject,
            "html": html,
        })
        return True
    except Exception as e:
        _log.error("Resend send failed to=%s subject=%r: %s", to, subject, e)
        return False
