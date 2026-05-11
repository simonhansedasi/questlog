"""
Route tests for the world ownership transfer feature.
Covers: initiate, cancel, transfer lock, accept (free + paid path), decline.
"""
import json
import pytest
from unittest.mock import patch, MagicMock
from tests.conftest import make_campaign, set_users, read_campaign, login_as

_USERS = {
    "alice": {"email": "alice@gmail.com", "display_name": "Alice", "world_limit": 3, "extra_worlds": 0},
    "bob":   {"email": "bob@gmail.com",   "display_name": "Bob",   "world_limit": 3, "extra_worlds": 0},
}


# ── Initiate ──────────────────────────────────────────────────────────────────

def test_initiate_stores_pending_transfer(client, dirs):
    campaigns, users_file = dirs
    set_users(users_file, _USERS)
    make_campaign(campaigns, "myworld", owner="alice")
    login_as(client, "alice", dm_slug="myworld")

    resp = client.post("/myworld/dm/transfer", data={"email": "bob@gmail.com"})
    assert resp.status_code == 302

    meta = read_campaign(campaigns, "myworld")
    pt = meta.get("pending_transfer")
    assert pt is not None
    assert pt["to_username"] == "bob"
    assert pt["to_email"] == "bob@gmail.com"
    assert pt["from_display_name"] == "Alice"
    assert "initiated_at" in pt


def test_initiate_email_normalised_to_lowercase(client, dirs):
    campaigns, users_file = dirs
    set_users(users_file, _USERS)
    make_campaign(campaigns, "myworld", owner="alice")
    login_as(client, "alice", dm_slug="myworld")

    client.post("/myworld/dm/transfer", data={"email": "BOB@GMAIL.COM"})
    meta = read_campaign(campaigns, "myworld")
    assert meta["pending_transfer"]["to_email"] == "bob@gmail.com"


def test_initiate_unknown_email_returns_error(client, dirs):
    campaigns, users_file = dirs
    set_users(users_file, _USERS)
    make_campaign(campaigns, "myworld", owner="alice")
    login_as(client, "alice", dm_slug="myworld")

    resp = client.post("/myworld/dm/transfer", data={"email": "nobody@gmail.com"},
                       follow_redirects=True)
    assert b"No RippleForge account" in resp.data
    meta = read_campaign(campaigns, "myworld")
    assert "pending_transfer" not in meta


def test_initiate_self_transfer_rejected(client, dirs):
    campaigns, users_file = dirs
    set_users(users_file, _USERS)
    make_campaign(campaigns, "myworld", owner="alice")
    login_as(client, "alice", dm_slug="myworld")

    resp = client.post("/myworld/dm/transfer", data={"email": "alice@gmail.com"},
                       follow_redirects=True)
    assert b"can&#39;t transfer" in resp.data or b"can't transfer" in resp.data
    meta = read_campaign(campaigns, "myworld")
    assert "pending_transfer" not in meta


def test_initiate_overwrites_existing_transfer(client, dirs):
    campaigns, users_file = dirs
    users = {
        **_USERS,
        "carol": {"email": "carol@gmail.com", "display_name": "Carol", "world_limit": 3, "extra_worlds": 0},
    }
    set_users(users_file, users)
    make_campaign(campaigns, "myworld", owner="alice", pending_transfer={
        "to_username": "carol", "to_email": "carol@gmail.com",
    })
    login_as(client, "alice", dm_slug="myworld")

    client.post("/myworld/dm/transfer", data={"email": "bob@gmail.com"})
    meta = read_campaign(campaigns, "myworld")
    assert meta["pending_transfer"]["to_username"] == "bob"


def test_initiate_requires_owner(client, dirs):
    campaigns, users_file = dirs
    set_users(users_file, _USERS)
    make_campaign(campaigns, "myworld", owner="alice")
    login_as(client, "bob", dm_slug="myworld")  # DM access but not owner

    resp = client.post("/myworld/dm/transfer", data={"email": "alice@gmail.com"})
    assert resp.status_code == 403
    meta = read_campaign(campaigns, "myworld")
    assert "pending_transfer" not in meta


# ── Cancel ────────────────────────────────────────────────────────────────────

def test_cancel_clears_pending_transfer(client, dirs):
    campaigns, users_file = dirs
    set_users(users_file, _USERS)
    make_campaign(campaigns, "myworld", owner="alice", pending_transfer={
        "to_username": "bob", "to_email": "bob@gmail.com", "from_display_name": "Alice",
    })
    login_as(client, "alice", dm_slug="myworld")

    resp = client.post("/myworld/dm/transfer/cancel")
    assert resp.status_code == 302

    meta = read_campaign(campaigns, "myworld")
    assert "pending_transfer" not in meta


# ── Transfer lock ─────────────────────────────────────────────────────────────

def test_transfer_lock_blocks_post_to_write_routes(client, dirs):
    campaigns, users_file = dirs
    set_users(users_file, _USERS)
    make_campaign(campaigns, "myworld", owner="alice", pending_transfer={
        "to_username": "bob", "to_email": "bob@gmail.com", "from_display_name": "Alice",
    })
    login_as(client, "alice", dm_slug="myworld")

    resp = client.post("/myworld/dm/settings", data={"name": "New Name"},
                       follow_redirects=True)
    assert b"locked" in resp.data
    # Name must not have changed
    meta = read_campaign(campaigns, "myworld")
    assert meta["name"] != "New Name"


def test_transfer_lock_allows_get_requests(client, dirs):
    campaigns, users_file = dirs
    set_users(users_file, _USERS)
    make_campaign(campaigns, "myworld", owner="alice", pending_transfer={
        "to_username": "bob", "to_email": "bob@gmail.com", "from_display_name": "Alice",
    })
    login_as(client, "alice", dm_slug="myworld")

    resp = client.get("/myworld/dm")
    assert resp.status_code == 200


def test_transfer_lock_cancel_is_exempt(client, dirs):
    campaigns, users_file = dirs
    set_users(users_file, _USERS)
    make_campaign(campaigns, "myworld", owner="alice", pending_transfer={
        "to_username": "bob", "to_email": "bob@gmail.com", "from_display_name": "Alice",
    })
    login_as(client, "alice", dm_slug="myworld")

    resp = client.post("/myworld/dm/transfer/cancel")
    assert resp.status_code == 302
    meta = read_campaign(campaigns, "myworld")
    assert "pending_transfer" not in meta


# ── Accept ────────────────────────────────────────────────────────────────────

def test_accept_under_limit_transfers_ownership(client, dirs):
    campaigns, users_file = dirs
    set_users(users_file, _USERS)
    make_campaign(campaigns, "myworld", owner="alice", pending_transfer={
        "to_username": "bob", "to_email": "bob@gmail.com", "from_display_name": "Alice",
    })
    login_as(client, "bob")

    resp = client.post("/transfer/myworld/accept")
    assert resp.status_code == 302

    meta = read_campaign(campaigns, "myworld")
    assert meta["owner"] == "bob"
    assert "pending_transfer" not in meta


def test_accept_grants_dm_session(client, dirs):
    campaigns, users_file = dirs
    set_users(users_file, _USERS)
    make_campaign(campaigns, "myworld", owner="alice", pending_transfer={
        "to_username": "bob", "to_email": "bob@gmail.com", "from_display_name": "Alice",
    })
    login_as(client, "bob")

    client.post("/transfer/myworld/accept")
    with client.session_transaction() as sess:
        assert sess.get("dm_myworld") is True


def test_accept_at_limit_redirects_to_stripe(client, dirs):
    campaigns, users_file = dirs
    users = dict(_USERS)
    # Bob already has 3 worlds — at his limit
    for i in range(3):
        make_campaign(campaigns, f"bobs_world_{i}", owner="bob")
    set_users(users_file, users)
    make_campaign(campaigns, "myworld", owner="alice", pending_transfer={
        "to_username": "bob", "to_email": "bob@gmail.com", "from_display_name": "Alice",
    })
    login_as(client, "bob")

    fake_session = MagicMock()
    fake_session.url = "https://checkout.stripe.com/pay/fake"
    with patch("routes.transfer.stripe.checkout.Session.create", return_value=fake_session):
        resp = client.post("/transfer/myworld/accept")

    assert resp.status_code == 302
    assert "stripe.com" in resp.headers["Location"]
    # Ownership must NOT have changed yet
    meta = read_campaign(campaigns, "myworld")
    assert meta["owner"] == "alice"


def test_accept_wrong_user_rejected(client, dirs):
    campaigns, users_file = dirs
    set_users(users_file, _USERS)
    make_campaign(campaigns, "myworld", owner="alice", pending_transfer={
        "to_username": "bob", "to_email": "bob@gmail.com", "from_display_name": "Alice",
    })
    login_as(client, "alice")  # sender tries to accept their own transfer

    resp = client.post("/transfer/myworld/accept", follow_redirects=True)
    assert b"No pending transfer" in resp.data
    meta = read_campaign(campaigns, "myworld")
    assert meta["owner"] == "alice"


# ── Billing transfer success ──────────────────────────────────────────────────

def test_billing_transfer_success_completes_transfer(client, dirs):
    campaigns, users_file = dirs
    set_users(users_file, _USERS)
    make_campaign(campaigns, "myworld", owner="alice", pending_transfer={
        "to_username": "bob", "to_email": "bob@gmail.com", "from_display_name": "Alice",
    })
    login_as(client, "bob")

    fake_cs = MagicMock()
    fake_cs.payment_status = "paid"
    fake_cs.metadata.username = "bob"
    fake_cs.metadata.action = "accept_transfer"
    fake_cs.metadata.transfer_slug = "myworld"

    with patch("routes.billing.stripe.checkout.Session.retrieve", return_value=fake_cs):
        resp = client.get("/billing/transfer/success?session_id=cs_fake")

    assert resp.status_code == 302
    meta = read_campaign(campaigns, "myworld")
    assert meta["owner"] == "bob"
    assert "pending_transfer" not in meta


def test_billing_transfer_success_wrong_user_rejected(client, dirs):
    campaigns, users_file = dirs
    set_users(users_file, _USERS)
    make_campaign(campaigns, "myworld", owner="alice", pending_transfer={
        "to_username": "bob", "to_email": "bob@gmail.com", "from_display_name": "Alice",
    })
    login_as(client, "alice")  # alice tries to use bob's payment session

    fake_cs = MagicMock()
    fake_cs.payment_status = "paid"
    fake_cs.metadata.username = "bob"  # payment was for bob, not alice
    fake_cs.metadata.action = "accept_transfer"
    fake_cs.metadata.transfer_slug = "myworld"

    with patch("routes.billing.stripe.checkout.Session.retrieve", return_value=fake_cs):
        resp = client.get("/billing/transfer/success?session_id=cs_fake")

    assert resp.status_code == 403
    meta = read_campaign(campaigns, "myworld")
    assert meta["owner"] == "alice"  # unchanged


# ── Decline ───────────────────────────────────────────────────────────────────

def test_decline_clears_pending_transfer(client, dirs):
    campaigns, users_file = dirs
    set_users(users_file, _USERS)
    make_campaign(campaigns, "myworld", owner="alice", pending_transfer={
        "to_username": "bob", "to_email": "bob@gmail.com", "from_display_name": "Alice",
    })
    login_as(client, "bob")

    resp = client.post("/transfer/myworld/decline")
    assert resp.status_code == 302

    meta = read_campaign(campaigns, "myworld")
    assert meta["owner"] == "alice"
    assert "pending_transfer" not in meta


def test_decline_wrong_user_rejected(client, dirs):
    campaigns, users_file = dirs
    set_users(users_file, _USERS)
    make_campaign(campaigns, "myworld", owner="alice", pending_transfer={
        "to_username": "bob", "to_email": "bob@gmail.com", "from_display_name": "Alice",
    })
    login_as(client, "alice")

    resp = client.post("/transfer/myworld/decline", follow_redirects=True)
    assert b"No pending transfer" in resp.data
    meta = read_campaign(campaigns, "myworld")
    assert "pending_transfer" in meta  # unchanged
