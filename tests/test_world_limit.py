"""
Unit tests for world count and incoming-transfer helpers in routes/utils.py.
These test pure logic against the filesystem — no Flask context needed.
"""
import json
import pytest
from tests.conftest import make_campaign, set_users


def test_count_owned_campaigns(dirs):
    campaigns, _ = dirs
    make_campaign(campaigns, "w1", owner="alice")
    make_campaign(campaigns, "w2", owner="alice")
    make_campaign(campaigns, "w3", owner="bob")

    from routes.utils import _user_world_count
    assert _user_world_count("alice") == 2
    assert _user_world_count("bob") == 1


def test_count_excludes_demo_flag(dirs):
    campaigns, _ = dirs
    make_campaign(campaigns, "w1", owner="alice")
    make_campaign(campaigns, "demo1", owner="alice", demo=True)

    from routes.utils import _user_world_count
    assert _user_world_count("alice") == 1


def test_count_excludes_demo_mode_flag(dirs):
    campaigns, _ = dirs
    make_campaign(campaigns, "w1", owner="alice")
    make_campaign(campaigns, "demo2", owner="alice", demo_mode=True)

    from routes.utils import _user_world_count
    assert _user_world_count("alice") == 1


def test_count_zero_when_no_campaigns(dirs):
    _, _ = dirs
    from routes.utils import _user_world_count
    assert _user_world_count("alice") == 0


def test_incoming_transfers_found(dirs):
    campaigns, _ = dirs
    make_campaign(campaigns, "w1", owner="alice", pending_transfer={
        "to_username": "bob", "to_email": "bob@gmail.com", "from_display_name": "Alice",
    })
    make_campaign(campaigns, "w2", owner="alice")

    from routes.utils import get_pending_incoming_transfers
    result = get_pending_incoming_transfers("bob")
    assert len(result) == 1
    slug, meta = result[0]
    assert slug == "w1"
    assert meta["pending_transfer"]["to_username"] == "bob"


def test_incoming_transfers_excludes_other_recipients(dirs):
    campaigns, _ = dirs
    make_campaign(campaigns, "w1", owner="alice", pending_transfer={
        "to_username": "carol", "to_email": "carol@gmail.com", "from_display_name": "Alice",
    })

    from routes.utils import get_pending_incoming_transfers
    assert get_pending_incoming_transfers("bob") == []


def test_incoming_transfers_empty_when_none(dirs):
    campaigns, _ = dirs
    make_campaign(campaigns, "w1", owner="alice")

    from routes.utils import get_pending_incoming_transfers
    assert get_pending_incoming_transfers("bob") == []


def test_world_limit_uses_world_limit_plus_extra_worlds(dirs):
    """Limit = world_limit (default 3) + extra_worlds (default 0)."""
    campaigns, users_file = dirs
    for i in range(3):
        make_campaign(campaigns, f"w{i}", owner="alice")
    set_users(users_file, {"alice": {"email": "alice@gmail.com", "world_limit": 3, "extra_worlds": 0}})

    from routes.utils import _user_world_count, load_users
    users = load_users()
    u = users["alice"]
    limit = u.get("world_limit", 3) + u.get("extra_worlds", 0)
    assert _user_world_count("alice") >= limit  # at the limit


def test_extra_worlds_extends_limit(dirs):
    campaigns, users_file = dirs
    for i in range(4):
        make_campaign(campaigns, f"w{i}", owner="alice")
    set_users(users_file, {"alice": {"email": "alice@gmail.com", "world_limit": 3, "extra_worlds": 1}})

    from routes.utils import _user_world_count, load_users
    users = load_users()
    u = users["alice"]
    limit = u.get("world_limit", 3) + u.get("extra_worlds", 0)
    assert limit == 4
    assert _user_world_count("alice") == 4  # at limit, not over
