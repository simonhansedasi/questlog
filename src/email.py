import os
import resend

resend.api_key = os.environ.get("RESEND_API_KEY", "")

FROM_ADDRESS = "RippleForge <noreply@rippleforge.gg>"


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
