"""
Route tests for access control: dm_required, login_required, owner-only guards.
"""
import pytest
from tests.conftest import make_campaign, set_users, login_as

_USERS = {
    "alice": {"email": "alice@gmail.com", "display_name": "Alice", "world_limit": 3, "extra_worlds": 0},
    "bob":   {"email": "bob@gmail.com",   "display_name": "Bob",   "world_limit": 3, "extra_worlds": 0},
}


# ── login_required ────────────────────────────────────────────────────────────

def test_unauthenticated_redirected_from_dm(client, dirs):
    campaigns, users_file = dirs
    set_users(users_file, _USERS)
    make_campaign(campaigns, "myworld", owner="alice")

    resp = client.get("/myworld/dm")
    # Should redirect to login (not 200)
    assert resp.status_code in (302, 301)
    assert "login" in resp.headers["Location"].lower()


# ── dm_required ───────────────────────────────────────────────────────────────

def test_owner_auto_granted_dm_access(client, dirs):
    campaigns, users_file = dirs
    set_users(users_file, _USERS)
    make_campaign(campaigns, "myworld", owner="alice")
    login_as(client, "alice")  # no dm_slug set — relies on auto-grant

    resp = client.get("/myworld/dm")
    assert resp.status_code == 200


def test_non_owner_without_pin_redirected_to_dm_login(client, dirs):
    campaigns, users_file = dirs
    set_users(users_file, _USERS)
    make_campaign(campaigns, "myworld", owner="alice")
    login_as(client, "bob")  # not owner, no DM session

    resp = client.get("/myworld/dm")
    assert resp.status_code == 302
    assert "login" in resp.headers["Location"].lower()


def test_member_without_dm_session_redirected(client, dirs):
    campaigns, users_file = dirs
    set_users(users_file, _USERS)
    make_campaign(campaigns, "myworld", owner="alice", members=["bob"])
    login_as(client, "bob")  # member but no dm session

    resp = client.get("/myworld/dm")
    assert resp.status_code == 302


# ── Owner-only guards on write routes ─────────────────────────────────────────

def test_non_owner_cannot_post_to_settings(client, dirs):
    campaigns, users_file = dirs
    set_users(users_file, _USERS)
    make_campaign(campaigns, "myworld", owner="alice")
    login_as(client, "bob", dm_slug="myworld")  # has DM session, but not owner

    resp = client.post("/myworld/dm/settings", data={"name": "Hacked"})
    assert resp.status_code == 403


def test_non_owner_cannot_delete_campaign(client, dirs):
    campaigns, users_file = dirs
    set_users(users_file, _USERS)
    make_campaign(campaigns, "myworld", owner="alice")
    login_as(client, "bob", dm_slug="myworld")

    resp = client.post("/myworld/dm/delete", data={"confirm_name": "myworld"})
    assert resp.status_code == 403


def test_non_owner_cannot_initiate_transfer(client, dirs):
    campaigns, users_file = dirs
    set_users(users_file, _USERS)
    make_campaign(campaigns, "myworld", owner="alice")
    login_as(client, "bob", dm_slug="myworld")

    resp = client.post("/myworld/dm/transfer", data={"email": "alice@gmail.com"})
    assert resp.status_code == 403


def test_non_owner_cannot_cancel_transfer(client, dirs):
    campaigns, users_file = dirs
    set_users(users_file, _USERS)
    make_campaign(campaigns, "myworld", owner="alice", pending_transfer={
        "to_username": "bob", "to_email": "bob@gmail.com", "from_display_name": "Alice",
    })
    login_as(client, "bob", dm_slug="myworld")

    resp = client.post("/myworld/dm/transfer/cancel")
    assert resp.status_code == 403


# ── Public campaign access ────────────────────────────────────────────────────

def test_public_campaign_allows_unauthenticated_get(client, dirs):
    campaigns, users_file = dirs
    set_users(users_file, _USERS)
    make_campaign(campaigns, "public_world", owner="alice", public=True)

    resp = client.get("/public_world/")
    assert resp.status_code == 200


def test_public_campaign_dm_post_requires_login(client, dirs):
    """Unauthenticated POST to a DM write route is redirected to login (not 403)
    because login_required fires before the owner check."""
    campaigns, users_file = dirs
    set_users(users_file, _USERS)
    make_campaign(campaigns, "public_world", owner="alice", public=True)

    resp = client.post("/public_world/dm/settings", data={"name": "Hacked"})
    assert resp.status_code == 302
    assert "login" in resp.headers["Location"].lower()
