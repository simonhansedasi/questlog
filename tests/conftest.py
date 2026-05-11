"""
Shared fixtures and helpers for the RippleForge test suite.

Strategy: CAMPAIGNS and USERS_FILE are module-level Path constants imported
into every route module. We patch them in routes.utils (so load() and helpers
use the temp dir) AND in each route module that writes directly via
(CAMPAIGNS / slug / ...).write_text(...).
"""
import json
import os
import pytest

# Must be set before app is imported so SESSION_COOKIE_SECURE defaults to False.
os.environ.setdefault("QUESTBOOK_HTTPS", "0")
os.environ.setdefault("QUESTBOOK_SECRET", "test-secret-key")
os.environ.setdefault("STRIPE_SECRET_KEY", "sk_test_fake")
os.environ.setdefault("STRIPE_PUBLISHABLE_KEY", "pk_test_fake")
os.environ.setdefault("STRIPE_SIGNING_SECRET", "whsec_fake")


# ── Path-patching fixture ─────────────────────────────────────────────────────

@pytest.fixture()
def dirs(tmp_path, monkeypatch):
    """Create temp campaigns + users dirs and patch all CAMPAIGNS/USERS_FILE refs."""
    campaigns = tmp_path / "campaigns"
    campaigns.mkdir()
    users_file = tmp_path / "users.json"
    users_file.write_text(json.dumps({"users": {}}))

    import routes.utils as utils
    import routes.dm as dm_mod
    import routes.billing as billing_mod
    import routes.transfer as transfer_mod
    import routes.player as player_mod
    import src.data as data_mod

    monkeypatch.setattr(utils, "CAMPAIGNS", campaigns)
    monkeypatch.setattr(utils, "USERS_FILE", users_file)
    monkeypatch.setattr(dm_mod, "CAMPAIGNS", campaigns)
    monkeypatch.setattr(billing_mod, "CAMPAIGNS", campaigns)
    monkeypatch.setattr(transfer_mod, "CAMPAIGNS", campaigns)
    monkeypatch.setattr(player_mod, "CAMPAIGNS", campaigns)
    monkeypatch.setattr(data_mod, "CAMPAIGNS", campaigns)

    return campaigns, users_file


# ── Flask test client ─────────────────────────────────────────────────────────

@pytest.fixture()
def client(dirs):
    """Flask test client with paths patched and TESTING mode on."""
    from app import app
    app.config["TESTING"] = True
    app.config["SESSION_COOKIE_SECURE"] = False
    with app.test_client() as c:
        yield c


# ── Data helpers ──────────────────────────────────────────────────────────────

def make_campaign(campaigns, slug, **kwargs):
    """Write a minimal campaign.json into campaigns/<slug>/."""
    d = campaigns / slug
    d.mkdir(exist_ok=True)
    meta = {
        "slug": slug,
        "name": kwargs.pop("name", slug),
        "owner": kwargs.pop("owner", "alice"),
        "system": "",
        "dm_pin": "1234",
        **kwargs,
    }
    (d / "campaign.json").write_text(json.dumps(meta))
    return meta


def set_users(users_file, users_dict):
    """Overwrite users.json with the given user dict."""
    users_file.write_text(json.dumps({"users": users_dict}))


def read_campaign(campaigns, slug):
    """Read and return campaign.json for slug."""
    return json.loads((campaigns / slug / "campaign.json").read_text())


def login_as(client, username, *, dm_slug=None):
    """Set session to simulate a logged-in user, optionally with DM access."""
    with client.session_transaction() as sess:
        sess["user"] = username
        sess["display_name"] = username
        if dm_slug:
            sess[f"dm_{dm_slug}"] = True
