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
from routes.utils import (
    login_required, dm_required, campaign_access, char_or_dm_required,
    ai_required, admin_required,
    load_users, save_users, load_invites, save_invites, generate_invite_code,
    load, campaigns, _validate_slug, _user_world_count, _allowed_image_url,
    _get_backlinks, _compute_site_stats,
    CAMPAIGNS, USERS_FILE, INVITES_FILE,
    _DEFAULT_TERMS, _BLANK_TEMPLATES,
    STRIPE_PUBLISHABLE_KEY, STRIPE_WEBHOOK_SECRET,
    STRIPE_PRICE_PRO, STRIPE_PRICE_PRO_ANNUAL, STRIPE_PRICE_WORLD, STRIPE_PRICE_PARTY,
    DEMO_SOURCE, DEMO_DIR, DEMO_STAMP, DEMO_COUNTS_FILE,
    _load_demo_counts, _save_demo_counts, reset_demo,
    _build_diffs, _create_onboarding_campaign,
)
from extensions import limiter, oauth

party_game_bp = Blueprint('party_game', __name__)

def _party_game_access(slug):
    """Load and return campaign meta for a party-mode campaign. No auth required."""
    _validate_slug(slug)
    meta = load(slug, "campaign.json")
    if meta.get("onboarding_mode") != "party":
        abort(404)
    return meta


@party_game_bp.route("/<slug>/play")
def party_play(slug):
    meta = _party_game_access(slug)
    game = db.get_party_game(slug)
    # Gate second plays for non-Pro owners
    owner = meta.get("owner")
    if owner and not game.get("phase"):
        users = load_users()
        user = users.get(owner, {})
        is_pro = user.get("subscription_status") in ("active", "trialing") or bool(user.get("ks_tier"))
        if user.get("party_plays", 0) >= 3 and not is_pro:
            try:
                checkout = stripe.checkout.Session.create(
                    payment_method_types=["card"],
                    mode="subscription",
                    line_items=[{"price": STRIPE_PRICE_PRO, "quantity": 1}],
                    metadata={"username": owner},
                    subscription_data={"trial_period_days": 14},
                    success_url=request.host_url.rstrip("/") + f"/{slug}/play",
                    cancel_url=request.host_url.rstrip("/") + url_for("player.index"),
                )
                return redirect(checkout.url)
            except stripe.StripeError:
                flash("Upgrade to Pro for unlimited Party Mode games.", "error")
                return redirect(url_for("player.index"))
    return render_template("party_play.html", slug=slug, meta=meta, game=game)


@party_game_bp.route("/<slug>/play/action", methods=["POST"])
@limiter.limit("60 per hour")
def party_play_action(slug):
    meta = _party_game_access(slug)
    data = request.get_json() or {}
    action = data.get("action")
    game = db.get_party_game(slug)
    current_session = 1

    if action == "init":
        game = {
            "phase": "setup",
            "entities": {"characters": [], "factions": [], "locations": []},
            "relations": [],
            "history": [],
        }
        db.save_party_game(slug, game)
        return jsonify({"ok": True, "phase": "setup"})

    elif action == "add_entity":
        entity_type = data.get("entity_type")
        name = (data.get("name") or "").strip()[:100]
        if not name:
            return jsonify({"error": "Enter a name first."}), 400
        entities = game.setdefault("entities", {"characters": [], "factions": [], "locations": []})

        if entity_type == "character":
            db.add_npc(slug, name, role="Character", relationship="neutral", description="", hidden=False)
            entity_id = db.slugify(name)
            if not any(e["id"] == entity_id for e in entities["characters"]):
                entities["characters"].append({"id": entity_id, "name": name})
        elif entity_type == "faction":
            db.add_faction(slug, name, relationship="neutral", description="", hidden=False)
            entity_id = db.slugify(name)
            if not any(e["id"] == entity_id for e in entities["factions"]):
                entities["factions"].append({"id": entity_id, "name": name})
        elif entity_type == "location":
            db.add_location(slug, name, hidden=False)
            entity_id = db.slugify(name)
            if not any(e["id"] == entity_id for e in entities["locations"]):
                entities["locations"].append({"id": entity_id, "name": name})
        else:
            return jsonify({"error": "Unknown entity type."}), 400

        hist = game.setdefault("history", [])
        hist.append({"type": "add_entity", "entity_type": entity_type, "name": name})
        db.save_party_game(slug, game)
        return jsonify({"ok": True, "entities": game["entities"]})

    elif action == "begin_play":
        entities = game.get("entities", {})
        if not entities.get("characters"):
            return jsonify({"error": "Add at least one character first."}), 400
        if not entities.get("factions"):
            return jsonify({"error": "Add at least one group or organization first."}), 400
        if not entities.get("locations"):
            return jsonify({"error": "Add at least one place first."}), 400
        genre = (data.get("genre") or "action-adventure").lower()
        if genre not in ("action-adventure", "drama", "mystery"):
            genre = "action-adventure"
        game["genre"] = genre
        game["inciting_incident"] = (data.get("inciting_incident") or "").strip()[:300]
        game["phase"] = "arc"
        db.save_party_game(slug, game)
        return jsonify({"ok": True, "phase": "arc"})

    elif action == "start_play":
        if game.get("phase") in ("arc", "secrets"):
            game["phase"] = "play"
            game["play_started_at"] = datetime.datetime.utcnow().isoformat()
            db.save_party_game(slug, game)
            owner = meta.get("owner")
            if owner:
                _users = load_users()
                if owner in _users:
                    _users[owner]["party_plays"] = _users[owner].get("party_plays", 0) + 1
                    save_users(_users)
        return jsonify({"ok": True})

    elif action == "log_event":
        source_id = (data.get("source_id") or "").strip()
        source_type = data.get("source_type")
        source_name = (data.get("source_name") or "").strip()
        action_text = (data.get("action_text") or "").strip()[:500]
        target_id = (data.get("target_id") or "").strip() or None
        target_type = data.get("target_type") or None
        target_name = (data.get("target_name") or "").strip()

        if not source_id or not action_text:
            return jsonify({"error": "Pick a source and describe the action."}), 400

        actor_id = target_id if target_type in ("character", "faction") else None
        actor_type = {"character": "npc", "faction": "faction"}.get(target_type or "")

        if source_type == "character":
            db.log_npc(slug, source_id, current_session, action_text,
                       polarity="neutral", intensity=1, event_type="other", visibility="public",
                       actor_id=actor_id, actor_type=actor_type)
        elif source_type == "faction":
            db.log_faction(slug, source_id, current_session, action_text,
                           polarity="neutral", intensity=1, event_type="other", visibility="public",
                           actor_id=actor_id, actor_type=actor_type)
        else:
            return jsonify({"error": "Invalid source type."}), 400

        hist_entry = {"type": "log_event", "source": source_name, "action": action_text}
        if target_name:
            hist_entry["target"] = target_name
        hist = game.setdefault("history", [])
        hist.append(hist_entry)
        game["history"] = hist[-20:]
        db.save_party_game(slug, game)
        return jsonify({"ok": True})

    elif action == "formalize_relation":
        id1 = (data.get("id1") or "").strip()
        type1 = data.get("type1")
        name1 = (data.get("name1") or "").strip()
        id2 = (data.get("id2") or "").strip()
        type2 = data.get("type2")
        name2 = (data.get("name2") or "").strip()
        relation = data.get("relation", "ally")
        if relation not in ("ally", "rival"):
            relation = "ally"

        if not id1 or not id2 or id1 == id2:
            return jsonify({"error": "Pick two different entities."}), 400

        db_type1 = "npc" if type1 == "character" else "faction"
        db_type2 = "npc" if type2 == "character" else "faction"

        if type1 == "character":
            db.add_npc_relation(slug, id1, id2, db_type2, relation, 0.8)
        else:
            db.add_faction_relation(slug, id1, id2, db_type2, relation, 0.8)
        if type2 == "character":
            db.add_npc_relation(slug, id2, id1, db_type1, relation, 0.8)
        else:
            db.add_faction_relation(slug, id2, id1, db_type1, relation, 0.8)

        game.setdefault("relations", []).append({"a": name1, "b": name2, "relation": relation})
        game.setdefault("history", []).append(
            {"type": "formalize_relation", "a": name1, "b": name2, "relation": relation}
        )
        db.save_party_game(slug, game)
        return jsonify({"ok": True})

    return jsonify({"error": "unknown action"}), 400


@party_game_bp.route("/<slug>/play/generate-scenario", methods=["POST"])
@limiter.limit("10 per hour")
def party_generate_scenario(slug):
    _party_game_access(slug)
    game = db.get_party_game(slug)
    if game.get("phase") not in ("setup", None, ""):
        return jsonify({"error": "can only generate scenario during setup"}), 400
    data = request.get_json() or {}
    genre = (data.get("genre") or "action-adventure").lower()
    if genre not in ("action-adventure", "drama", "mystery"):
        genre = "action-adventure"
    count = int(data.get("count") or 3)
    count = max(1, min(6, count))
    result = ai.generate_party_scenario(genre, count)
    return jsonify({"ok": True, "scenario": result})


@party_game_bp.route("/<slug>/play/referee", methods=["POST"])
@limiter.limit("30 per hour")
def party_referee(slug):
    meta = _party_game_access(slug)
    game = db.get_party_game(slug)
    d = request.get_json() or {}
    source_name = (d.get("source_name") or "Someone").strip()
    action_text = (d.get("action_text") or "").strip()[:500]
    target_name = (d.get("target_name") or "").strip()
    if not action_text:
        return jsonify({"ok": True, "warning": None})
    history = [h for h in game.get("history", []) if h.get("type") == "log_event"]
    relations = game.get("relations", [])
    objectives = game.get("arc", {}).get("objectives", [])
    campaign_name = meta.get("name") or "Our World"
    result = ai.referee_party_action(campaign_name, history, source_name, action_text, target_name, relations, objectives)
    return jsonify(result)


@party_game_bp.route("/<slug>/play/generate-arc", methods=["POST"])
@limiter.limit("10 per hour")
def party_generate_arc(slug):
    meta = _party_game_access(slug)
    game = db.get_party_game(slug)
    if game.get("phase") != "arc":
        return jsonify({"error": "not in arc phase"}), 400
    campaign_name = meta.get("name") or "Our World"
    entities = game.get("entities", {})
    location_name = next((e["name"] for e in entities.get("locations", [])), "")
    faction_name = next((e["name"] for e in entities.get("factions", [])), "")
    arc = ai.generate_party_arc(
        campaign_name,
        entities,
        location_name,
        faction_name,
        genre=game.get("genre", "action-adventure"),
        inciting_incident=game.get("inciting_incident", ""),
    )
    objectives = arc.get("objectives", [])
    game["arc"] = {
        "description": arc.get("description", ""),
        "objectives": objectives,
        "completed": [False] * len(objectives),
    }
    game["phase"] = "arc"
    if arc.get("title"):
        meta_path = CAMPAIGNS / slug / "campaign.json"
        campaign_meta = json.loads(meta_path.read_text())
        campaign_meta["name"] = arc["title"]
        meta_path.write_text(json.dumps(campaign_meta, indent=2))
    # Persist arc as a quest so it appears in the world after the game
    quest_title = (arc.get("description") or "The Party Arc")[:80]
    db.add_quest(slug, quest_title, description=arc.get("description", ""), hidden=False)
    quest_id = db.slugify(quest_title)
    for obj in objectives:
        db.add_objective(slug, quest_id, obj)
    game["quest_id"] = quest_id
    db.save_party_game(slug, game)
    return jsonify({"ok": True, "arc": game["arc"], "phase": "arc", "title": arc.get("title", "")})


@party_game_bp.route("/<slug>/play/generate-secrets", methods=["POST"])
@limiter.limit("10 per hour")
def party_generate_secrets(slug):
    meta = _party_game_access(slug)
    game = db.get_party_game(slug)
    if game.get("phase") not in ("arc", "secrets"):
        return jsonify({"error": "wrong phase"}), 400
    entities = game.get("entities", {})
    characters = entities.get("characters", [])
    arc = game.get("arc", {})
    secrets = ai.generate_secret_objectives(
        meta.get("name") or "Our World",
        characters,
        arc.get("description", ""),
        game.get("genre", "action-adventure"),
    )
    game["secret_objectives"] = secrets
    game["phase"] = "secrets"
    db.save_party_game(slug, game)
    return jsonify({"ok": True, "secret_objectives": secrets})


@party_game_bp.route("/<slug>/play/generate-summary", methods=["POST"])
@limiter.limit("5 per hour")
def party_generate_summary(slug):
    meta = _party_game_access(slug)
    game = db.get_party_game(slug)
    result = ai.generate_party_summary(
        meta.get("name") or "Our World",
        game.get("history", []),
        game.get("entities", {}).get("characters", []),
        game.get("secret_objectives", []),
        game.get("arc", {}),
    )
    return jsonify(result)


@party_game_bp.route("/<slug>/play/complete", methods=["POST"])
@limiter.limit("5 per hour")
def party_play_complete(slug):
    meta = _party_game_access(slug)
    game = db.get_party_game(slug)
    completed = (request.get_json() or {}).get("completed", [])
    if "arc" in game:
        game["arc"]["completed"] = completed
    game["phase"] = "done"
    db.save_party_game(slug, game)
    db.inject_wikilinks_into_world(slug)
    all_entries = db.get_all_log_entries(slug)
    return jsonify({
        "ok": True,
        "world_url": f"/{slug}/world",
        "events_logged": len(all_entries),
        "characters": [{"name": p["npc_name"]} for p in game.get("players", [])],
        "arc": game.get("arc", {}),
    })

