from flask import Blueprint, render_template, abort, redirect, url_for, request, session, Response, jsonify, flash
from markupsafe import Markup
from pathlib import Path
from functools import wraps
import json, os, re, secrets, datetime, uuid, shutil, time, random, zipfile, io
from concurrent.futures import ThreadPoolExecutor, as_completed
import stripe
import markdown

from src import data as db
from src import ai
from src import importer as vault_importer
try:
    from src import email as mail
except ImportError:
    mail = None
from routes.utils import (
    login_required, dm_required, campaign_access, char_or_dm_required,
    ai_required, admin_required,
    load_users, save_users, load_invites, save_invites, generate_invite_code,
    load, campaigns, _validate_slug, _user_world_count, _allowed_image_url,
    _get_backlinks, _compute_site_stats,
    CAMPAIGNS, USERS_FILE, INVITES_FILE,
    _DEFAULT_TERMS, _BLANK_TEMPLATES,
    STRIPE_PUBLISHABLE_KEY, STRIPE_WEBHOOK_SECRET,
    STRIPE_PRICE_PRO, STRIPE_PRICE_PRO_ANNUAL, STRIPE_PRICE_WORLD,
    DEMO_SOURCE, DEMO_DIR, DEMO_STAMP, DEMO_COUNTS_FILE,
    _load_demo_counts, _save_demo_counts, reset_demo,
    _build_diffs, _create_onboarding_campaign,
)
from extensions import limiter, oauth

async_camp_bp = Blueprint('async_camp', __name__)

def _advance_turn(slug, campaign_name, game, action_text="", events_logged=0, skipped=False):
    players = game.get("players", [])
    if not players:
        return
    current = players[game.get("current_player_index", 0)]
    game.setdefault("history", []).append({
        "turn": game.get("turn_number", 1),
        "username": current["username"],
        "character_name": current.get("character_name", ""),
        "action_text": action_text,
        "committed_at": datetime.datetime.utcnow().isoformat(),
        "events_logged": events_logged,
        "skipped": skipped,
    })
    game["turn_number"] = game.get("turn_number", 1) + 1
    game["current_player_index"] = (game.get("current_player_index", 0) + 1) % len(players)
    game["turn_started_at"] = datetime.datetime.utcnow().isoformat()
    db.save_async_campaign(slug, game)
    next_player = players[game["current_player_index"]]
    if next_player.get("email"):
        base = request.host_url.rstrip("/")
        mail.send_turn_notification(
            next_player["email"],
            next_player.get("character_name", ""),
            campaign_name,
            f"{base}/{slug}/campaign",
        )


def _check_async_deadline(slug, game, meta):
    if game.get("phase") != "active":
        return
    turn_started_str = game.get("turn_started_at")
    if not turn_started_str:
        return
    deadline_hours = game.get("deadline_hours", 24)
    try:
        turn_started = datetime.datetime.fromisoformat(turn_started_str)
    except ValueError:
        return
    if datetime.datetime.utcnow() <= turn_started + datetime.timedelta(hours=deadline_hours):
        return
    players = game.get("players", [])
    if not players:
        return
    current = players[game.get("current_player_index", 0)]
    if current.get("email"):
        mail.send_skip_notification(
            current["email"],
            current.get("character_name", ""),
            meta.get("name") or "Your Campaign",
        )
    _advance_turn(slug, meta.get("name") or "Your Campaign", game, skipped=True)
def _create_onboarding_campaign(username, onboarding_mode):
    """Clone the blank 'example' template for wizard/party onboarding. Returns new slug or a Stripe redirect Response."""
    src = CAMPAIGNS / "example"
    if not src.exists():
        return None
    users = load_users()
    user = users.get(username, {})
    limit = user.get("world_limit", 3) + user.get("extra_worlds", 0)
    if _user_world_count(username) >= limit:
        try:
            checkout = stripe.checkout.Session.create(
                payment_method_types=["card"],
                mode="payment",
                line_items=[{"price": STRIPE_PRICE_WORLD, "quantity": 1}],
                metadata={"username": username, "source_slug": "example", "template": "ttrpg"},
                success_url=request.host_url.rstrip("/") + "/billing/world/success?session_id={CHECKOUT_SESSION_ID}",
                cancel_url=request.host_url.rstrip("/") + url_for("player.index"),
            )
            return redirect(checkout.url)
        except stripe.StripeError:
            flash("World limit reached. Upgrade to create more worlds.", "error")
            return redirect(url_for("player.index"))
    new_slug = secrets.token_hex(4)
    dst = CAMPAIGNS / new_slug
    shutil.copytree(str(src), str(dst))
    new_meta = json.loads((dst / "campaign.json").read_text())
    new_meta["slug"] = new_slug
    new_meta["owner"] = username
    new_meta.pop("demo", None)
    new_meta.pop("public", None)
    new_meta["dm_pin"] = str(secrets.randbelow(9000) + 1000)
    new_meta["created"] = datetime.date.today().isoformat()
    if onboarding_mode == "party":
        new_meta["name"] = ""
        new_meta["mode"] = "fiction"
        tmpl = _BLANK_TEMPLATES["fiction"]
        new_meta["terminology"] = {k: v for k, v in tmpl.items() if k != "observer_default"}
        new_meta["observer_name"] = tmpl["observer_default"]
    elif onboarding_mode == "campaign":
        new_meta["name"] = ""
        new_meta["mode"] = "fiction"
        tmpl = _BLANK_TEMPLATES["fiction"]
        new_meta["terminology"] = {k: v for k, v in tmpl.items() if k != "observer_default"}
        new_meta["observer_name"] = tmpl["observer_default"]
    else:
        new_meta["name"] = ""
        new_meta["mode"] = "ttrpg"
        new_meta["observer_name"] = "The Party"
        new_meta.pop("terminology", None)
    new_meta["description"] = ""
    if onboarding_mode == "party":
        new_meta["system"] = "Party Mode"
    elif onboarding_mode == "campaign":
        new_meta["system"] = "Campaign Mode"
    else:
        new_meta["system"] = ""
    new_meta["party_name"] = ""
    new_meta["onboarding_mode"] = onboarding_mode
    (dst / "campaign.json").write_text(json.dumps(new_meta, indent=2))
    session[f"dm_{new_slug}"] = True
    return new_slug


# ── Async Campaign Mode ────────────────────────────────────────────────────────

def _sync_campaign_character(slug, char_name):
    """Create a world NPC for a campaign player character if one doesn't exist yet."""
    if not char_name:
        return
    existing = db.get_npcs(slug, include_hidden=True)
    if any(n["name"].lower() == char_name.lower() for n in existing):
        return
    db.add_npc(slug, char_name, role="Character", relationship="protagonist",
               description="", hidden=False, dm_notes="")

@async_camp_bp.route("/<slug>/campaign/lobby")
@dm_required
def async_campaign_lobby(slug):
    r = campaign_access(slug)
    if r: return r
    meta = load(slug, "campaign.json")
    if not meta:
        abort(404)
    game = db.get_async_campaign(slug)
    if not game:
        game = {"phase": "setup", "players": [], "invite_tokens": {},
                "history": [], "turn_number": 1, "current_player_index": 0, "deadline_hours": 24}
        db.save_async_campaign(slug, game)
    if game.get("phase") == "active":
        _check_async_deadline(slug, game, meta)
        game = db.get_async_campaign(slug)
    players = game.get("players", [])
    invite_tokens = game.get("invite_tokens", {})
    # Only unclaimed invites go in the pending list; claimed ones already appear in players
    pending_invites = [{**inv, "token": tok} for tok, inv in invite_tokens.items() if not inv.get("claimed_by")]
    # Token lookup keyed by username so the template can render Remove for joined players
    player_tokens = {inv["claimed_by"]: tok for tok, inv in invite_tokens.items() if inv.get("claimed_by")}
    all_claimed = all(inv.get("claimed_by") for inv in invite_tokens.values()) if invite_tokens else True
    all_named = all(p.get("character_name") for p in players) if players else False
    gm_player = next((p for p in players if p.get("username") == meta.get("owner")), None)
    can_start = game.get("phase") == "recruiting" and all_claimed and all_named and bool(players)
    return render_template("async_lobby.html", slug=slug, meta=meta, game=game,
                           players=players, pending_invites=pending_invites,
                           player_tokens=player_tokens,
                           can_start=can_start, all_claimed=all_claimed,
                           all_named=all_named, gm_player=gm_player)


@async_camp_bp.route("/<slug>/campaign/invite", methods=["POST"])
@dm_required
def async_campaign_invite(slug):
    r = campaign_access(slug)
    if r: return r
    meta = load(slug, "campaign.json")
    game = db.get_async_campaign(slug)
    if not game:
        game = {"phase": "setup", "players": [], "invite_tokens": {},
                "history": [], "turn_number": 1, "current_player_index": 0, "deadline_hours": 24}
    action = request.form.get("action", "setup_emails")
    username = session["user"]

    if action == "setup_emails":
        other_emails = [e.strip().lower() for e in request.form.getlist("emails") if e.strip() and "@" in e.strip()]
        include_self = request.form.get("include_self") == "1"
        story_mode = request.form.get("story_mode", "ai")
        genre = request.form.get("genre", "adventure")
        deadline_hours = max(1, min(168, int(request.form.get("deadline_hours", 24) or 24)))

        total_players = len(other_emails) + (1 if include_self else 0)
        if total_players == 0:
            flash("Add at least one player to continue.", "error")
            return redirect(url_for("async_camp.async_campaign_lobby", slug=slug))

        all_users_data = load_users()
        base = request.host_url.rstrip("/")
        inviter = all_users_data.get(username, {}).get("display_name", username)
        self_email = all_users_data.get(username, {}).get("email", "")
        campaign_name = meta.get("name") or "Our Campaign"

        def email_display(addr):
            return addr.split("@")[0] if "@" in addr else addr

        if story_mode == "manual":
            title = request.form.get("arc_title", "").strip()[:120]
            hook = request.form.get("arc_hook", "").strip()[:800]
            paths = [request.form.get(f"arc_path_{i}", "").strip()[:200] for i in range(1, 4)]
            arc_data = {"title": title or campaign_name, "description": hook, "objectives": [p for p in paths if p]}
            if title:
                meta["name"] = title
                (CAMPAIGNS / slug / "campaign.json").write_text(json.dumps(meta, indent=2))
        else:
            all_emails_list = ([self_email + "||self"] if include_self else []) + \
                              [e + "||invite" for e in other_emails]
            placeholder_chars = [{"id": f"player_{i+1}", "name": email_display(e.split("||")[0])}
                                  for i, e in enumerate(all_emails_list) if e.split("||")[0]]
            try:
                arc_data = ai.generate_party_arc(campaign_name, placeholder_chars,
                                                 "an untamed world", "the powers that be", genre, "")
            except Exception:
                arc_data = {"title": campaign_name, "description": "", "objectives": []}

        game["phase"] = "recruiting"
        game["genre"] = genre
        game["deadline_hours"] = deadline_hours
        game["arc"] = arc_data
        game["invite_tokens"] = {}
        game["players"] = []

        slot = 0
        if include_self:
            char_id = f"player_{slot + 1}"
            game["players"].append({
                "username": username,
                "email": self_email,
                "character_id": char_id,
                "character_name": "",
                "secret": {},
                "turn_order": slot,
                "last_action_at": None,
            })
            slot += 1

        for email_addr in other_emails:
            char_id = f"player_{slot + 1}"
            token = secrets.token_urlsafe(12)
            game["invite_tokens"][token] = {
                "email": email_addr,
                "character_id": char_id,
                "character_name": "",
                "secret": {},
                "claimed_by": None,
                "created_at": datetime.datetime.utcnow().isoformat(),
            }
            mail.send_invite(email_addr, campaign_name, inviter, f"{base}/{slug}/campaign/join/{token}")
            slot += 1

        db.save_async_campaign(slug, game)
        msg = "Campaign created!"
        if other_emails:
            msg += f" Invites sent to {len(other_emails)} player{'s' if len(other_emails) != 1 else ''}."
        if include_self:
            msg += " Name your character below to get ready."
        flash(msg, "success")

    return redirect(url_for("async_camp.async_campaign_lobby", slug=slug))


@async_camp_bp.route("/<slug>/campaign/arc", methods=["POST"])
@dm_required
def async_campaign_arc(slug):
    _validate_slug(slug)
    r = campaign_access(slug)
    if r: return r
    meta = load(slug, "campaign.json")
    game = db.get_async_campaign(slug)
    if not game:
        abort(404)
    campaign_name = meta.get("name") or "Our Campaign"
    action = request.form.get("action", "manual")

    if action == "generate":
        genre = game.get("genre", "adventure")
        players = game.get("players", [])
        chars = [{"id": p["character_id"],
                  "name": p.get("character_name") or p.get("email", "").split("@")[0]}
                 for p in players]
        for tok in game.get("invite_tokens", {}).values():
            if not tok.get("claimed_by"):
                chars.append({"id": tok["character_id"],
                               "name": tok.get("character_name") or tok["email"].split("@")[0]})
        try:
            arc_data = ai.generate_party_arc(campaign_name, chars,
                                             "an untamed world", "the powers that be", genre, "")
        except Exception:
            flash("AI generation failed. Try again.", "error")
            return redirect(url_for("async_camp.async_campaign_lobby", slug=slug))
    else:
        title = request.form.get("arc_title", "").strip()[:120]
        hook = request.form.get("arc_hook", "").strip()[:800]
        paths = [request.form.get(f"arc_path_{i}", "").strip()[:200] for i in range(1, 4)]
        arc_data = {"title": title or campaign_name, "description": hook, "objectives": [p for p in paths if p]}

    if arc_data.get("title") and arc_data["title"] != campaign_name:
        meta["name"] = arc_data["title"]
        (CAMPAIGNS / slug / "campaign.json").write_text(json.dumps(meta, indent=2))
    game["arc"] = arc_data
    db.save_async_campaign(slug, game)
    flash("Story updated.", "success")
    return redirect(url_for("async_camp.async_campaign_lobby", slug=slug))


@async_camp_bp.route("/<slug>/campaign/roles", methods=["POST"])
@dm_required
def async_campaign_roles(slug):
    _validate_slug(slug)
    r = campaign_access(slug)
    if r: return r
    meta = load(slug, "campaign.json")
    game = db.get_async_campaign(slug)
    if not game:
        abort(404)
    players = game.get("players", [])
    action = request.form.get("action", "save")
    campaign_name = meta.get("name") or "Our Campaign"

    if action == "generate":
        genre = game.get("genre", "adventure")
        arc_desc = game.get("arc", {}).get("description", "")
        eligible = [p for p in players
                    if not p.get("secret", {}).get("role") and not p.get("role_skipped")]
        if not eligible:
            flash("All players already have roles or have opted out.", "info")
            return redirect(url_for("async_camp.async_campaign_lobby", slug=slug))
        chars = [{"id": p["character_id"],
                  "name": p.get("character_name") or p.get("email", "").split("@")[0]}
                 for p in eligible]
        try:
            secrets_list = ai.generate_secret_objectives(campaign_name, chars, arc_desc, genre)
        except Exception:
            flash("AI generation failed. Try again.", "error")
            return redirect(url_for("async_camp.async_campaign_lobby", slug=slug))
        secrets_by_id = {s["character_id"]: s for s in secrets_list}
        for p in players:
            if p["character_id"] in secrets_by_id:
                p["secret"] = secrets_by_id[p["character_id"]]
                p.pop("role_skipped", None)
    else:
        _ROLES = ["Saboteur", "Protector", "Investigator", "Opportunist", "Loyalist", "Impostor", "Catalyst"]
        for p in players:
            cid = p["character_id"]
            role = request.form.get(f"role_{cid}", "none").strip()
            if role not in _ROLES:
                p["secret"] = {}
                p["role_skipped"] = True
            else:
                p.pop("role_skipped", None)
                objective = request.form.get(f"objective_{cid}", "").strip()[:500]
                bias_target = request.form.get(f"bias_target_{cid}", "").strip()
                bias_type = request.form.get(f"bias_type_{cid}", "").strip()[:60]
                p["secret"] = {
                    "character_id": cid,
                    "character_name": p.get("character_name", ""),
                    "role": role,
                    "objective": objective,
                    "bias_target": bias_target if bias_target else None,
                    "bias_type": bias_type if bias_type else None,
                }

    db.save_async_campaign(slug, game)
    flash("Roles saved.", "success")
    return redirect(url_for("async_camp.async_campaign_lobby", slug=slug))


@async_camp_bp.route("/<slug>/campaign/join/<token>", methods=["GET", "POST"])
@login_required
def async_campaign_join(slug, token):
    _validate_slug(slug)
    meta = load(slug, "campaign.json")
    if not meta:
        abort(404)
    game = db.get_async_campaign(slug)
    if not game:
        abort(404)
    invite = game.get("invite_tokens", {}).get(token)
    if not invite:
        flash("This invite link is invalid.", "error")
        return redirect(url_for("player.index"))
    username = session["user"]

    # Check claimed state
    if invite.get("claimed_by"):
        if invite["claimed_by"] == username:
            return redirect(url_for("async_camp.async_campaign_play", slug=slug))
        flash("This invite has already been claimed.", "error")
        return redirect(url_for("player.index"))

    # Email check first — before "already in campaign" so wrong-account users see a clear message
    all_users = load_users()
    user_email = all_users.get(username, {}).get("email", "").lower()
    invite_email = invite.get("email", "").lower()
    if user_email != invite_email:
        return render_template("async_join.html", slug=slug, meta=meta, token=token,
                               invite=invite, arc=game.get("arc", {}), wrong_account=True)

    if any(p["username"] == username for p in game.get("players", [])):
        flash("You're already in this campaign.", "info")
        return redirect(url_for("async_camp.async_campaign_play", slug=slug))

    if request.method == "POST":
        char_name = request.form.get("character_name", "").strip()[:60]
        if not char_name:
            flash("Enter a character name to continue.", "error")
            return render_template("async_join.html", slug=slug, meta=meta, token=token,
                                   invite=invite, arc=game.get("arc", {}))
        invite["character_name"] = char_name
        invite["claimed_by"] = username
        players = game.setdefault("players", [])
        players.append({
            "username": username,
            "email": invite["email"],
            "character_id": invite["character_id"],
            "character_name": char_name,
            "secret": invite.get("secret", {}),
            "turn_order": len(players),
            "last_action_at": None,
        })
        db.save_async_campaign(slug, game)
        _sync_campaign_character(slug, char_name)
        meta_path = CAMPAIGNS / slug / "campaign.json"
        members = meta.get("members", [])
        if username not in members:
            members.append(username)
            meta["members"] = members
            meta_path.write_text(json.dumps(meta, indent=2))
        return redirect(url_for("async_camp.async_campaign_play", slug=slug))

    return render_template("async_join.html", slug=slug, meta=meta, token=token,
                           invite=invite, arc=game.get("arc", {}))


@async_camp_bp.route("/<slug>/campaign/name", methods=["POST"])
@login_required
def async_campaign_name(slug):
    _validate_slug(slug)
    game = db.get_async_campaign(slug)
    if not game:
        abort(404)
    username = session["user"]
    char_name = request.form.get("character_name", "").strip()[:60]
    if char_name:
        for p in game.get("players", []):
            if p["username"] == username and not p.get("character_name"):
                p["character_name"] = char_name
                _sync_campaign_character(slug, char_name)
                break
        db.save_async_campaign(slug, game)
    phase = game.get("phase", "setup")
    if phase in ("setup", "recruiting"):
        return redirect(url_for("async_camp.async_campaign_lobby", slug=slug))
    return redirect(url_for("async_camp.async_campaign_play", slug=slug))


@async_camp_bp.route("/<slug>/campaign/start", methods=["POST"])
@dm_required
def async_campaign_start(slug):
    r = campaign_access(slug)
    if r: return r
    meta = load(slug, "campaign.json")
    game = db.get_async_campaign(slug)
    if not game:
        flash("Set up the campaign first.", "error")
        return redirect(url_for("async_camp.async_campaign_lobby", slug=slug))
    players = game.get("players", [])
    if not players:
        flash("Add at least one player before starting.", "error")
        return redirect(url_for("async_camp.async_campaign_lobby", slug=slug))

    campaign_name = meta.get("name") or "Our Campaign"
    game["phase"] = "active"
    game["turn_number"] = 1
    game["current_player_index"] = 0
    game["turn_started_at"] = datetime.datetime.utcnow().isoformat()
    db.save_async_campaign(slug, game)

    first = players[0]
    base = request.host_url.rstrip("/")
    if first.get("email"):
        mail.send_turn_notification(first["email"], first.get("character_name", ""),
                                    campaign_name, f"{base}/{slug}/campaign")
    flash("Campaign started! The first player has been notified.", "success")
    return redirect(url_for("async_camp.async_campaign_play", slug=slug))


@async_camp_bp.route("/<slug>/campaign")
@login_required
def async_campaign_play(slug):
    r = campaign_access(slug)
    if r: return r
    meta = load(slug, "campaign.json")
    if not meta:
        abort(404)
    game = db.get_async_campaign(slug)
    if not game:
        return redirect(url_for("async_camp.async_campaign_lobby", slug=slug))
    _check_async_deadline(slug, game, meta)
    game = db.get_async_campaign(slug)
    username = session["user"]
    players = game.get("players", [])
    is_dm = bool(session.get(f"dm_{slug}"))
    is_player = any(p["username"] == username for p in players)
    if not is_player and not is_dm:
        abort(403)
    phase = game.get("phase", "recruiting")
    current_index = game.get("current_player_index", 0)
    current_player = players[current_index] if players and current_index < len(players) else None
    is_my_turn = bool(current_player and current_player["username"] == username)
    my_player = next((p for p in players if p["username"] == username), None)
    deadline_str = None
    if phase == "active" and game.get("turn_started_at"):
        deadline_hours = game.get("deadline_hours", 24)
        try:
            turn_started = datetime.datetime.fromisoformat(game["turn_started_at"])
            deadline_str = (turn_started + datetime.timedelta(hours=deadline_hours)).isoformat()
        except ValueError:
            pass
    npcs = db.get_npcs(slug, include_hidden=False)
    factions = db.get_factions(slug, include_hidden=False)
    locations = db.get_locations(slug, include_hidden=False)
    return render_template("async_play.html", slug=slug, meta=meta, game=game,
                           phase=phase, players=players, current_player=current_player,
                           is_my_turn=is_my_turn, my_player=my_player, is_dm=is_dm,
                           deadline_str=deadline_str, npcs=npcs, factions=factions,
                           locations=locations)


@async_camp_bp.route("/<slug>/campaign/submit", methods=["POST"])
@login_required
def async_campaign_submit(slug):
    r = campaign_access(slug)
    if r: return r
    meta = load(slug, "campaign.json")
    if not meta:
        abort(404)
    game = db.get_async_campaign(slug)
    if not game or game.get("phase") != "active":
        flash("No active campaign.", "error")
        return redirect(url_for("player.campaign", slug=slug))
    username = session["user"]
    players = game.get("players", [])
    current_index = game.get("current_player_index", 0)
    current_player = players[current_index] if players else None
    if not current_player or current_player["username"] != username:
        flash("It's not your turn.", "error")
        return redirect(url_for("async_camp.async_campaign_play", slug=slug))
    all_users = load_users()
    owner = meta.get("owner", "")
    owner_data = all_users.get(owner, {})
    if not owner_data.get("ai_enabled") and not owner_data.get("admin"):
        flash("The campaign GM needs an AI-enabled account to process turns.", "error")
        return redirect(url_for("async_camp.async_campaign_play", slug=slug))
    action_text = (request.form.get("action_text") or "").strip()[:1000]
    if not action_text:
        flash("Write something before submitting.", "error")
        return redirect(url_for("async_camp.async_campaign_play", slug=slug))
    campaign_name = meta.get("name") or "Our Campaign"
    session_n = db.get_current_session(slug) or 1

    # Ensure all player characters exist as world entities before calling AI
    for p in players:
        if p.get("character_name"):
            _sync_campaign_character(slug, p["character_name"])

    npcs = db.get_npcs(slug, include_hidden=True)
    factions = db.get_factions(slug, include_hidden=True)
    locations = db.get_locations(slug, include_hidden=True)
    try:
        proposals = ai.propose_log_entries(action_text, campaign_name, session_n,
                                           npcs, factions, party=[], ships=[], conditions=[],
                                           locations=locations)
    except Exception as exc:
        flash(f"AI processing failed — turn recorded without world events. ({exc})", "error")
        _advance_turn(slug, campaign_name, game, action_text=action_text, events_logged=0)
        return redirect(url_for("async_camp.async_campaign_play", slug=slug))

    npc_by_name = {n["name"].lower(): n["id"] for n in npcs}
    faction_by_name = {f["name"].lower(): f["id"] for f in factions}
    location_by_name = {loc["name"].lower(): loc["id"] for loc in locations}

    # Pre-pass: create any new NPC/faction entities the AI named but that don't exist yet
    for entry in (proposals or []):
        etype = entry.get("entity_type", "npc")
        if etype not in ("npc", "faction"):
            continue
        name = (entry.get("entity_name") or "").strip()
        if not name:
            continue
        name_lower = name.lower()
        rel = "friendly" if entry.get("polarity") == "positive" else "hostile" if entry.get("polarity") == "negative" else "neutral"
        if etype == "faction" and name_lower not in faction_by_name:
            db.add_faction(slug, name, rel, description="", hidden=False)
            faction_by_name[name_lower] = db.slugify(name)
        elif etype == "npc" and name_lower not in npc_by_name and name_lower not in faction_by_name:
            db.add_npc(slug, name, role="", relationship=rel, description="", hidden=False, factions=[])
            npc_by_name[name_lower] = db.slugify(name)

    events_logged = 0
    for entry in (proposals or []):
        note = (entry.get("note") or "").strip()
        if not note:
            continue
        entity_type = entry.get("entity_type", "npc")
        entity_name = (entry.get("entity_name") or "").strip().lower()
        # Resolve entity_id by name lookup (more reliable than AI-returned ID on sparse worlds)
        if entity_type == "npc":
            entity_id = npc_by_name.get(entity_name) or entry.get("entity_id")
        elif entity_type == "faction":
            entity_id = faction_by_name.get(entity_name) or entry.get("entity_id")
        elif entity_type == "location":
            entity_id = location_by_name.get(entity_name) or entry.get("entity_id")
        else:
            entity_id = entry.get("entity_id")
        if not entity_id:
            continue
        polarity = entry.get("polarity")
        intensity = entry.get("intensity", 1)
        evt_type = entry.get("event_type", "other")
        visibility = entry.get("visibility", "public")
        actor_id = entry.get("actor_id")
        actor_type = entry.get("actor_type")
        src_evt = None
        try:
            if entity_type == "npc":
                src_evt = db.log_npc(slug, entity_id, session_n, note, polarity, intensity,
                                      evt_type, visibility, actor_id=actor_id, actor_type=actor_type)
            elif entity_type == "faction":
                src_evt = db.log_faction(slug, entity_id, session_n, note, polarity, intensity,
                                          evt_type, visibility, actor_id=actor_id, actor_type=actor_type)
            elif entity_type == "location":
                src_evt = db.log_location(slug, entity_id, session_n, note, visibility,
                                           polarity, intensity, evt_type,
                                           actor_id=actor_id, actor_type=actor_type)
        except Exception:
            continue
        if polarity and entity_id and src_evt:
            try:
                db.apply_ripple(slug, entity_id, entity_type, session_n, note,
                                polarity, intensity, evt_type, visibility, source_event_id=src_evt)
            except Exception:
                pass
        events_logged += 1
    _advance_turn(slug, campaign_name, game, action_text=action_text, events_logged=events_logged)
    flash(f"Turn submitted — {events_logged} event{'s' if events_logged != 1 else ''} logged to the world.", "success")
    return redirect(url_for("async_camp.async_campaign_play", slug=slug))


@async_camp_bp.route("/<slug>/campaign/leave", methods=["POST"])
@login_required
def async_campaign_leave(slug):
    _validate_slug(slug)
    game = db.get_async_campaign(slug)
    if not game or game.get("phase") not in ("recruiting",):
        flash("You can only leave during the recruiting phase.", "error")
        return redirect(url_for("async_camp.async_campaign_play", slug=slug))
    username = session["user"]
    meta = load(slug, "campaign.json")
    meta_path = CAMPAIGNS / slug / "campaign.json"

    # Pre-join decline: token submitted but player hasn't claimed yet
    token = request.form.get("token", "").strip()
    if token:
        invite = game.get("invite_tokens", {}).get(token)
        if invite and not invite.get("claimed_by"):
            del game["invite_tokens"][token]
            db.save_async_campaign(slug, game)
            flash("Invitation declined.", "success")
            return redirect(url_for("player.index"))

    # Post-join leave: remove from players list
    before = len(game.get("players", []))
    game["players"] = [p for p in game.get("players", []) if p["username"] != username]
    if len(game["players"]) == before:
        flash("You're not in this campaign.", "error")
        return redirect(url_for("player.index"))
    # Reset invite token so GM can re-invite
    for tok in game.get("invite_tokens", {}).values():
        if tok.get("claimed_by") == username:
            tok["claimed_by"] = None
            tok["character_name"] = None
            break
    db.save_async_campaign(slug, game)
    # Remove from campaign members
    members = meta.get("members", [])
    if username in members:
        members.remove(username)
        meta["members"] = members
        meta_path.write_text(json.dumps(meta, indent=2))
    flash("You've left the campaign.", "success")
    return redirect(url_for("player.index"))


@async_camp_bp.route("/<slug>/campaign/remove", methods=["POST"])
@dm_required
def async_campaign_remove(slug):
    _validate_slug(slug)
    game = db.get_async_campaign(slug)
    if not game or game.get("phase") not in ("recruiting",):
        flash("Can only remove players during recruiting.", "error")
        return redirect(url_for("async_camp.async_campaign_lobby", slug=slug))
    meta = load(slug, "campaign.json")
    token = request.form.get("token", "").strip()
    if not token or token not in game.get("invite_tokens", {}):
        flash("Invalid invite.", "error")
        return redirect(url_for("async_camp.async_campaign_lobby", slug=slug))
    invite = game["invite_tokens"][token]
    claimed_by = invite.get("claimed_by")
    # Remove player from players list if they've joined
    if claimed_by:
        game["players"] = [p for p in game.get("players", []) if p["username"] != claimed_by]
        # Remove from campaign members
        meta_path = CAMPAIGNS / slug / "campaign.json"
        members = meta.get("members", [])
        if claimed_by in members:
            members.remove(claimed_by)
            meta["members"] = members
            meta_path.write_text(json.dumps(meta, indent=2))
    del game["invite_tokens"][token]
    db.save_async_campaign(slug, game)
    flash("Removed.", "success")
    return redirect(url_for("async_camp.async_campaign_lobby", slug=slug))


@async_camp_bp.route("/<slug>/campaign/skip", methods=["POST"])
@login_required
def async_campaign_skip(slug):
    r = campaign_access(slug)
    if r: return r
    meta = load(slug, "campaign.json")
    game = db.get_async_campaign(slug)
    if not game or game.get("phase") != "active":
        return redirect(url_for("async_camp.async_campaign_play", slug=slug))
    username = session["user"]
    players = game.get("players", [])
    current_index = game.get("current_player_index", 0)
    current_player = players[current_index] if players else None
    is_dm = bool(session.get(f"dm_{slug}"))
    is_current = bool(current_player and current_player["username"] == username)
    if not is_dm and not is_current:
        abort(403)
    if current_player and current_player.get("email"):
        mail.send_skip_notification(current_player["email"],
                                    current_player.get("character_name", ""),
                                    meta.get("name") or "Our Campaign")
    _advance_turn(slug, meta.get("name") or "Our Campaign", game, skipped=True)
    flash("Turn skipped.", "success")
    return redirect(url_for("async_camp.async_campaign_play", slug=slug))


@async_camp_bp.route("/<slug>/campaign/end", methods=["POST"])
@dm_required
def async_campaign_end(slug):
    _validate_slug(slug)
    game = db.get_async_campaign(slug)
    if not game or game.get("phase") != "active":
        return redirect(url_for("async_camp.async_campaign_play", slug=slug))
    game["phase"] = "done"
    game["ended_at"] = datetime.datetime.utcnow().isoformat()
    db.save_async_campaign(slug, game)
    flash("Campaign ended. The world is yours to explore.", "success")
    return redirect(url_for("player.campaign", slug=slug))

