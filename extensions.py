from flask import session
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from authlib.integrations.flask_client import OAuth


def _limiter_key():
    return session.get("user") or get_remote_address()


limiter = Limiter(key_func=_limiter_key, default_limits=[], storage_uri="memory://")
oauth = OAuth()
