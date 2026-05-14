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
    STRIPE_PRICE_PRO, STRIPE_PRICE_PRO_ANNUAL, STRIPE_PRICE_WORLD,
    DEMO_SOURCE, DEMO_DIR, DEMO_STAMP, DEMO_COUNTS_FILE,
    _load_demo_counts, _save_demo_counts, reset_demo,
    _build_diffs, _create_onboarding_campaign,
)
from extensions import limiter, oauth

demo_bp = Blueprint('demo_bp', __name__)

@demo_bp.route("/demo/reset", methods=["GET", "POST"])
def demo_reset():
    reset_demo(force=True)
    return redirect("/demo/")


@demo_bp.route("/demo/")
def demo_splash():
    reset_demo()
    r = campaign_access("demo")
    if r: return r
    meta = load("demo", "campaign.json")
    return render_template("demo_splash.html", meta=meta, slug="demo")


@demo_bp.route("/demo/ai")
def demo_ai_page():
    reset_demo()
    r = campaign_access("demo")
    if r: return r
    meta = load("demo", "campaign.json")
    return render_template("demo_ai.html", meta=meta, slug="demo")


def _build_diffs(slug, before_snaps, entries):
    """Compare before snapshots to current state and return diff list."""
    diffs = []
    for (eid, etype), before in before_snaps.items():
        after = db.entity_snapshot(slug, eid, etype)
        if not after:
            continue
        log_added = after["log_count"] - before["log_count"]
        rel_changed = before["relationship"] != after["relationship"]
        if not log_added and not rel_changed:
            continue
        diff = {"entity_name": before["name"], "log_added": log_added}
        if before["score"] is not None and after["score"] is not None:
            diff["score_before"] = before["score"]
            diff["score_after"] = after["score"]
        if rel_changed:
            diff["relationship_before"] = before["relationship"]
            diff["relationship_after"] = after["relationship"]
        diffs.append(diff)
    return diffs


@demo_bp.route("/demo/ai/propose", methods=["POST"])
def demo_ai_propose():
    r = campaign_access("demo")
    if r: return r
    LIMIT = 3
    MAX_NOTES = 5000
    visitor_id = request.cookies.get("demo_id")
    ip = (request.headers.get("X-Forwarded-For", request.remote_addr) or "").split(",")[0].strip()
    ip_key = "ip:" + ip if ip else None
    counts = _load_demo_counts()
    used = max(
        counts.get(visitor_id, 0) if visitor_id else 0,
        counts.get(ip_key, 0) if ip_key else 0
    )
    if used >= LIMIT:
        return jsonify({"error": "limit", "remaining": 0})
    data = request.get_json()
    notes = (data.get("notes") or "").strip()
    if not notes:
        return jsonify({"error": "empty"}), 400
    if len(notes) > MAX_NOTES:
        return jsonify({"error": "too_long"}), 400
    meta = load("demo", "campaign.json")
    current_session = db.get_current_session("demo")
    npcs = db.get_npcs("demo", include_hidden=True)
    factions = db.get_factions("demo", include_hidden=True)
    locations = db.get_locations("demo", include_hidden=True)
    party = db.get_all_party_characters("demo")
    try:
        proposals = ai.propose_log_entries(notes, meta.get("name", "Demo"), current_session, npcs, factions, party=party, locations=locations)
    except Exception:
        return jsonify({"error": "ai_error"}), 500
    if visitor_id:
        counts[visitor_id] = used + 1
    if ip_key:
        counts[ip_key] = max(counts.get(ip_key, 0), used + 1)
    if visitor_id or ip_key:
        _save_demo_counts(counts)
    remaining = LIMIT - (used + 1)
    return jsonify({"proposals": proposals, "remaining": remaining})


@demo_bp.route("/demo/ai/commit_parsed", methods=["POST"])
@limiter.limit("20 per hour")
def demo_ai_commit_parsed():
    r = campaign_access("demo")
    if r: return r
    data = request.get_json()
    entries = data.get("entries", [])[:50]
    current_session = db.get_current_session("demo")
    npc_by_name = {n["name"].lower(): n["id"] for n in db.get_npcs("demo", include_hidden=True)}
    faction_by_name = {f["name"].lower(): f["id"] for f in db.get_factions("demo", include_hidden=True)}
    location_by_name = {loc["name"].lower(): loc["id"] for loc in db.get_locations("demo", include_hidden=True)}
    before = {}
    for e in entries:
        eid = e.get("entity_id")
        if eid:
            before[(eid, e.get("entity_type", "npc"))] = db.entity_snapshot("demo", eid, e.get("entity_type", "npc"))
    committed = 0
    for entry in entries:
        entity_id = entry.get("entity_id")
        entity_type = entry.get("entity_type", "npc")
        note = entry.get("note", "").strip()[:500]
        if not note:
            continue
        if entity_type == "location":
            if not entity_id:
                name = (entry.get("entity_name") or "").strip()[:100]
                entity_id = location_by_name.get(name.lower()) if name else None
            if not entity_id:
                continue
            polarity = entry.get("polarity") or None
            intensity = int(entry.get("intensity") or 1)
            event_type = entry.get("event_type") or None
            visibility = entry.get("visibility", "public")
            session_n = int(entry.get("session") or current_session)
            db.log_location("demo", entity_id, session_n, note, polarity=polarity,
                            intensity=intensity, event_type=event_type, visibility=visibility)
            committed += 1
            continue
        if not entity_id:
            name = (entry.get("entity_name") or "").strip()[:100]
            if not name:
                continue
            name_lower = name.lower()
            entity_id = npc_by_name.get(name_lower) or faction_by_name.get(name_lower)
            if not entity_id:
                pol = entry.get("polarity")
                rel = "friendly" if pol == "positive" else "hostile" if pol == "negative" else "neutral"
                entity_id = db.slugify(name)
                if entity_type == "faction":
                    db.add_faction("demo", name, rel, description="", hidden=True)
                    faction_by_name[name_lower] = entity_id
                else:
                    db.add_npc("demo", name, role="", relationship=rel, description="", hidden=True, factions=[])
                    npc_by_name[name_lower] = entity_id
            before[(entity_id, entity_type)] = db.entity_snapshot("demo", entity_id, entity_type)
        polarity = entry.get("polarity") or None
        intensity = int(entry.get("intensity") or 1)
        event_type = entry.get("event_type") or None
        visibility = entry.get("visibility", "public")
        session_n = int(entry.get("session") or current_session)
        if entity_type == "npc":
            src_evt = db.log_npc("demo", entity_id, session_n, note, polarity=polarity,
                                 intensity=intensity, event_type=event_type, visibility=visibility)
        else:
            src_evt = db.log_faction("demo", entity_id, session_n, note, polarity=polarity,
                                     intensity=intensity, event_type=event_type, visibility=visibility)
        if polarity and polarity != "neutral":
            db.apply_ripple("demo", entity_id, entity_type, session_n, note, polarity, intensity,
                            event_type, visibility=visibility, source_event_id=src_evt)
        committed += 1
    return jsonify({"committed": committed, "diffs": _build_diffs("demo", before, entries)})


@demo_bp.route("/demo/ai/commit_futures", methods=["POST"])
@limiter.limit("20 per hour")
def demo_ai_commit_futures():
    r = campaign_access("demo")
    if r: return r
    data = request.get_json()
    entries = data.get("entries", [])[:50]
    current_session = db.get_current_session("demo")
    before = {(e["entity_id"], e.get("entity_type", "npc")): db.entity_snapshot("demo", e["entity_id"], e.get("entity_type", "npc"))
              for e in entries if e.get("entity_id")}
    committed = 0
    for entry in entries:
        entity_id = entry.get("entity_id")
        entity_type = entry.get("entity_type", "npc")
        note = entry.get("note", "").strip()[:500]
        if not entity_id or not note:
            continue
        confidence = entry.get("confidence", "medium")
        intensity = 3 if confidence == "high" else 2 if confidence == "medium" else 1
        if entity_type == "npc":
            db.log_npc("demo", entity_id, current_session, note,
                       intensity=intensity, event_type="projected", visibility="public")
        else:
            db.log_faction("demo", entity_id, current_session, note,
                           intensity=intensity, event_type="projected", visibility="public")
        committed += 1
    return jsonify({"committed": committed, "diffs": _build_diffs("demo", before, entries)})

