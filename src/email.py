import os
import resend

resend.api_key = os.environ.get("RESEND_API_KEY", "")

FROM_ADDRESS = "RippleForge <noreply@rippleforge.gg>"


def _btn(url: str, label: str) -> str:
    return (f'<a href="{url}" style="display:inline-block;background:#4caf50;color:#fff;'
            f'padding:10px 24px;border-radius:5px;text-decoration:none;font-weight:700;">'
            f'{label}</a>')


def _wrap(body: str) -> str:
    return (f'<div style="font-family:sans-serif;max-width:480px;margin:0 auto;'
            f'background:#1a1a1a;color:#e0e0e0;padding:32px;border-radius:8px;">'
            f'{body}</div>')


def send_turn_notification(to: str, character_name: str, campaign_name: str, turn_url: str) -> bool:
    html = _wrap(
        f'<p style="font-size:1.05rem;font-weight:700;color:#fff;margin:0 0 10px;">{campaign_name}</p>'
        f'<p style="margin:0 0 24px;line-height:1.6;">It\'s <strong>{character_name}</strong>\'s turn. The world is waiting.</p>'
        + _btn(turn_url, 'Take your turn →')
    )
    return send(to, f"Your turn in {campaign_name}", html)


def send_invite(to: str, campaign_name: str, inviter_display: str, join_url: str) -> bool:
    html = _wrap(
        f'<p style="font-size:1.05rem;font-weight:700;color:#fff;margin:0 0 10px;">{campaign_name}</p>'
        f'<p style="margin:0 0 24px;line-height:1.6;">{inviter_display} invited you to play '
        f'<em>{campaign_name}</em> on RippleForge — a turn-based collaborative story game. '
        f'Sign in and claim your character to join.</p>'
        + _btn(join_url, 'Join the campaign →')
    )
    return send(to, f"You're invited to {campaign_name}", html)


def send_skip_notification(to: str, character_name: str, campaign_name: str) -> bool:
    html = _wrap(
        f'<p style="font-size:1.05rem;font-weight:700;color:#fff;margin:0 0 10px;">{campaign_name}</p>'
        f'<p style="margin:0;line-height:1.6;">{character_name}\'s turn was skipped — the deadline passed. '
        f'You\'re back in the rotation.</p>'
    )
    return send(to, f"Your turn was skipped in {campaign_name}", html)


def send(to: str, subject: str, html: str) -> bool:
    """Send a transactional email. Returns True on success, False on failure."""
    if not resend.api_key:
        return False
    try:
        resend.Emails.send({
            "from": FROM_ADDRESS,
            "to": [to],
            "subject": subject,
            "html": html,
        })
        return True
    except Exception:
        return False
