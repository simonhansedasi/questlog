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
    _get_backlinks, _compute_site_stats, get_pending_incoming_transfers,
    CAMPAIGNS, USERS_FILE, INVITES_FILE,
    _DEFAULT_TERMS, _BLANK_TEMPLATES,
    STRIPE_PUBLISHABLE_KEY, STRIPE_WEBHOOK_SECRET,
    STRIPE_PRICE_PRO, STRIPE_PRICE_PRO_ANNUAL, STRIPE_PRICE_WORLD, STRIPE_PRICE_PARTY,
    DEMO_SOURCE, DEMO_DIR, DEMO_STAMP, DEMO_COUNTS_FILE,
    _load_demo_counts, _save_demo_counts, reset_demo,
    _build_diffs, _create_onboarding_campaign,
)
from extensions import limiter, oauth

player_bp = Blueprint('player', __name__)

@player_bp.route("/")
def index():
    if not session.get("user"):
        return render_template("landing.html", stats=_compute_site_stats())
    username = session["user"]
    all_campaigns = campaigns()
    my_campaigns = [c for c in all_campaigns if c.get("owner") == username and not c.get("demo")]
    member_campaigns = [c for c in all_campaigns if username in c.get("members", []) and c.get("owner") != username and not c.get("demo")]
    demo_campaigns = [c for c in all_campaigns if c.get("demo")]
    for c in my_campaigns + member_campaigns:
        if c.get("onboarding_mode") == "party":
            _g = db.get_party_game(c["slug"])
            c["party_phase"] = _g.get("phase")
        _ag = db.get_async_campaign(c["slug"])
        if _ag and _ag.get("phase") in ("recruiting", "active"):
            c["async_phase"] = _ag.get("phase")
    incoming_transfers = get_pending_incoming_transfers(username)
    return render_template("index.html", my_campaigns=my_campaigns, member_campaigns=member_campaigns, demo_campaigns=demo_campaigns, incoming_transfers=incoming_transfers)


@player_bp.route("/guide")
def guide():
    return render_template("guide.html")


@player_bp.route("/<slug>/setup")
@login_required
def setup_wizard(slug):
    _validate_slug(slug)
    meta = load(slug, "campaign.json")
    if meta.get("onboarding_mode") != "wizard":
        abort(404)
    if meta.get("owner") != session.get("user"):
        abort(403)
    npcs = db.get_npcs(slug, include_hidden=True)
    return render_template("setup_wizard.html", slug=slug, meta=meta, npcs=npcs)


@player_bp.route("/<slug>/setup/step", methods=["POST"])
@login_required
@limiter.limit("120 per hour")
def setup_wizard_step(slug):
    _validate_slug(slug)
    meta = load(slug, "campaign.json")
    if meta.get("onboarding_mode") != "wizard":
        abort(404)
    if meta.get("owner") != session.get("user"):
        abort(403)
    data = request.get_json()
    step = data.get("step")
    value = (data.get("value") or "").strip()[:200]
    if not value:
        return jsonify({"error": "empty"}), 400

    current_session = 1

    if step == 0:
        meta["name"] = value
        meta["system"] = "Any"
        (CAMPAIGNS / slug / "campaign.json").write_text(json.dumps(meta, indent=2))
        return jsonify({"ok": True, "next_step": 1})

    elif step == 1:
        npc_id = db.slugify(value)
        existing = [n["id"] for n in db.get_npcs(slug, include_hidden=True)]
        if npc_id in existing:
            npc_id = npc_id + "_2"
        db.add_npc(slug, value, role="Character", relationship="neutral",
                   description="", hidden=False)
        return jsonify({"ok": True, "next_step": 2, "npc_id": db.slugify(value), "npc_name": value})

    elif step == 2:
        db.add_npc(slug, value, role="Character", relationship="neutral",
                   description="", hidden=False)
        return jsonify({"ok": True, "next_step": 3, "npc_id": db.slugify(value), "npc_name": value})

    elif step == 3:
        db.add_faction(slug, value, relationship="neutral", description="", hidden=False)
        return jsonify({"ok": True, "next_step": 4})

    elif step == 4:
        db.add_location(slug, value, hidden=False)
        return jsonify({"ok": True, "next_step": 5})

    elif step == 5:
        db.add_quest(slug, value, description=value, hidden=False, status="active")
        return jsonify({"ok": True, "next_step": 6})

    elif step == 6:
        npc_id = data.get("npc_id", "")
        db.log_npc(slug, npc_id, current_session, value,
                   polarity="neutral", intensity=1, event_type="other", visibility="public")
        return jsonify({"ok": True, "next_step": 7})

    elif step == 7:
        npc_id = data.get("npc_id", "")
        db.log_npc(slug, npc_id, current_session, value,
                   polarity="neutral", intensity=1, event_type="other", visibility="public")
        return jsonify({"ok": True, "next_step": 8})

    elif step == 8:
        npc1_id = data.get("npc1_id", "")
        npc2_id = data.get("npc2_id", "")
        relation = data.get("relation", "ally")
        if npc1_id and npc2_id and relation in ("ally", "rival"):
            db.add_npc_relation(slug, npc1_id, npc2_id, "npc", relation, 0.8)
            db.add_npc_relation(slug, npc2_id, npc1_id, "npc", relation, 0.8)
        return jsonify({"ok": True, "done": True})

    return jsonify({"error": "unknown step"}), 400


@player_bp.route("/wiki")
def wiki():
    return render_template("wiki.html")


@player_bp.route("/sw.js")
def service_worker():
    return app.send_static_file("sw.js")


@player_bp.route("/robots.txt")
def robots_txt():
    return app.response_class(
        "User-agent: *\nAllow: /\nAllow: /demo/\nAllow: /guide\nDisallow: /admin/\nDisallow: /account/\nSitemap: https://rippleforge.gg/sitemap.xml\n",
        mimetype="text/plain"
    )


@player_bp.route("/sitemap.xml")
def sitemap_xml():
    xml = ('<?xml version="1.0" encoding="UTF-8"?>'
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
           '<url><loc>https://rippleforge.gg/</loc><priority>1.0</priority></url>'
           '<url><loc>https://rippleforge.gg/demo/</loc><priority>0.9</priority></url>'
           '<url><loc>https://rippleforge.gg/guide</loc><priority>0.8</priority></url>'
           '<url><loc>https://rippleforge.gg/demo/world/ripples</loc><priority>0.7</priority></url>'
           '<url><loc>https://rippleforge.gg/demo/ai</loc><priority>0.7</priority></url>'
           '</urlset>')
    return app.response_class(xml, mimetype="application/xml")


@player_bp.route("/demo/<slug>/clone", methods=["POST"])
@login_required
def clone_campaign(slug):
    _validate_slug(slug)
    src = CAMPAIGNS / slug
    if not src.exists():
        abort(404)
    meta = json.loads((src / "campaign.json").read_text())
    if not meta.get("demo"):
        abort(403)
    username = session.get("user")
    if username:
        users = load_users()
        user = users.get(username, {})
        limit = user.get("world_limit", 3) + user.get("extra_worlds", 0)
        if _user_world_count(username) >= limit:
            template = request.form.get("template", "ttrpg")
            dm_pin = request.form.get("dm_pin", "")
            try:
                checkout = stripe.checkout.Session.create(
                    payment_method_types=["card"],
                    mode="payment",
                    line_items=[{"price": STRIPE_PRICE_WORLD, "quantity": 1}],
                    metadata={"username": username, "source_slug": slug, "template": template, "dm_pin": dm_pin},
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
    new_meta["owner"] = session["user"]
    new_meta.pop("demo", None)
    new_meta.pop("public", None)
    pin = request.form.get("dm_pin", "").strip()
    new_meta["dm_pin"] = pin if pin else str(secrets.randbelow(9000) + 1000)
    new_meta["created"] = datetime.date.today().isoformat()
    if slug == "example":
        mode = request.form.get("template", "ttrpg")
        new_meta["mode"] = mode
        new_meta["name"] = ""
        new_meta["description"] = ""
        new_meta["system"] = ""
        new_meta["party_name"] = ""
        new_meta["observer_name"] = ""
        tmpl = _BLANK_TEMPLATES.get(mode, {})
        if tmpl:
            new_meta["terminology"] = {k: v for k, v in tmpl.items() if k != "observer_default"}
        else:
            new_meta.pop("terminology", None)
    (dst / "campaign.json").write_text(json.dumps(new_meta, indent=2))
    session[f"dm_{new_slug}"] = True
    return redirect(url_for("dm_bp.dm", slug=new_slug))


@player_bp.route("/<slug>/")
def campaign(slug):
    if slug == "demo":
        reset_demo()
    r = campaign_access(slug)
    if r: return r
    meta = load(slug, "campaign.json")
    if not meta:
        abort(404)
    if meta.get("onboarding_mode") == "party":
        _g = db.get_party_game(slug)
        if _g.get("phase") != "done":
            return redirect(url_for("party_game.party_play", slug=slug))
    # Redirect to campaign while async campaign is active or recruiting
    _async_game = db.get_async_campaign(slug)
    if _async_game and _async_game.get("phase") in ("recruiting", "active"):
        _username = session.get("user")
        _is_owner = _username == meta.get("owner")
        _is_dm = bool(session.get(f"dm_{slug}")) or _is_owner
        _players = _async_game.get("players", [])
        _is_player = any(p["username"] == _username for p in _players)
        if _is_dm or _is_player:
            if _is_owner:
                session[f"dm_{slug}"] = True  # grant DM session so lobby's @dm_required passes
            if _async_game.get("phase") == "active":
                return redirect(url_for("async_camp.async_campaign_play", slug=slug))
            else:
                return redirect(url_for("async_camp.async_campaign_lobby", slug=slug) if _is_dm
                                else url_for("async_camp.async_campaign_play", slug=slug))
    is_dm = bool(session.get(f"dm_{slug}"))
    party = db.get_all_party_characters(slug, include_hidden=is_dm)
    quests = db.get_quests(slug, include_hidden=is_dm)
    active = [q for q in quests if q["status"] == "active"]
    journal_entries = db.get_journal(slug)
    latest_journal = None
    if journal_entries:
        e = journal_entries[-1]
        latest_journal = {**e, "recap_html": Markup(markdown.markdown(e.get("recap", ""), extensions=["nl2br"]))}
    npcs = db.get_npcs(slug, include_hidden=is_dm)
    factions = db.get_factions(slug, include_hidden=is_dm)
    locations = db.get_locations(slug)
    current_session = db.get_current_session(slug)
    async_campaign = db.get_async_campaign(slug)
    username = session.get("user")
    async_visible = False
    if async_campaign and async_campaign.get("phase") == "active":
        players = async_campaign.get("players", [])
        async_visible = is_dm or any(p["username"] == username for p in players)
    return render_template("campaign.html", meta=meta, party=party, active=active, slug=slug,
                           latest_journal=latest_journal,
                           current_session=current_session,
                           recent_entities=db.get_recent_entities(slug, current_session),
                           npc_count=len(npcs), faction_count=len(factions),
                           npcs=npcs, factions=factions, locations=locations,
                           async_campaign=async_campaign, async_visible=async_visible,
                           is_dm=is_dm)


@player_bp.route("/<slug>/party")
def party(slug):
    r = campaign_access(slug)
    if r: return r
    meta = load(slug, "campaign.json")
    is_dm = bool(session.get(f"dm_{slug}"))
    is_player = bool(session.get("user")) and not is_dm
    viewer = session.get("user")
    parties = db.get_parties(slug)
    selected_party_id = request.args.get("party", parties[0]["id"] if parties else "default")
    characters = db.get_party(slug, party_id=selected_party_id, include_hidden=is_dm)
    npcs = db.get_npcs(slug, include_hidden=is_dm)
    factions = db.get_factions(slug, include_hidden=is_dm)
    locations = db.get_locations(slug, include_hidden=is_dm)
    current_session = db.get_current_session(slug)
    npc_names = {n["id"]: n["name"] for n in npcs}
    faction_names = {f["id"]: f["name"] for f in factions}
    party_display_name = meta.get("party_name") or "The Party"
    def _resolve_actor(e):
        actor = e.get("actor_id", "")
        atype = e.get("actor_type", "")
        if atype == "npc":
            return npc_names.get(actor, actor)
        elif atype == "faction":
            return faction_names.get(actor, actor)
        elif actor:
            return actor
        return None

    all_chars_for_actor = db.get_all_party_characters(slug, include_hidden=is_dm)
    _actor_npcs  = db.get_npcs(slug, include_hidden=is_dm)
    _actor_facs  = db.get_factions(slug, include_hidden=is_dm)
    _actor_locs  = db.get_locations(slug, include_hidden=is_dm)

    for char in characters:
        char["_conditions"] = db.get_character_conditions(
            slug, char["name"], include_hidden=is_dm, include_resolved=False
        )
        raw_log = char.get("log", [])
        visible = db.get_visible_log(raw_log, is_dm=is_dm)
        for e in visible:
            e["_actor_name"] = _resolve_actor(e)
        char["_log"] = list(reversed(visible))

        _cname = char["name"]
        _cslug = db.slugify(_cname)
        _al = []
        for _n in _actor_npcs:
            for _e in db.get_visible_log(_n.get("log", []), is_dm=is_dm):
                _aid = _e.get("actor_id") or ""
                if _aid == _cname or _aid == _cslug:
                    _al.append({**_e, "_target_name": _n["name"], "_target_id": _n["id"], "_target_type": "npc"})
        for _f in _actor_facs:
            for _e in db.get_visible_log(_f.get("log", []), is_dm=is_dm):
                _aid = _e.get("actor_id") or ""
                if _aid == _cname or _aid == _cslug:
                    _al.append({**_e, "_target_name": _f["name"], "_target_id": _f["id"], "_target_type": "faction"})
        for _loc in _actor_locs:
            for _e in db.get_visible_log(_loc.get("log", []), is_dm=is_dm):
                _aid = _e.get("actor_id") or ""
                if _aid == _cname or _aid == _cslug:
                    _al.append({**_e, "_target_name": _loc["name"], "_target_id": _loc["id"], "_target_type": "location"})
        for _oc in all_chars_for_actor:
            if _oc["name"] == _cname:
                continue
            for _e in db.get_visible_log(_oc.get("log", []), is_dm=is_dm):
                _aid = _e.get("actor_id") or ""
                if _aid == _cname or _aid == _cslug:
                    _al.append({**_e, "_target_name": _oc["name"], "_target_id": db.slugify(_oc["name"]), "_target_type": "char"})
        _al.sort(key=lambda e: e.get("session", 0), reverse=True)
        char["_actor_log"] = _al

    # Combined party timeline: group events + individual character events
    raw_group = [e for e in meta.get("party_group_log", [])
                 if not e.get("deleted") and (is_dm or e.get("visibility", "public") != "dm_only")]
    party_log = []
    for e in raw_group:
        party_log.append({**e, "_source": e.get("party_name") or party_display_name,
                          "_source_type": "group", "_actor_name": _resolve_actor(e)})
    for char in characters:
        for e in char.get("_log", []):
            party_log.append({**e, "_source": char["name"], "_source_type": "character"})
    party_log.sort(key=lambda e: (e.get("session", 0), e.get("id", "")), reverse=True)

    return render_template("party.html", meta=meta, characters=characters, slug=slug,
                           is_dm=is_dm, is_player=is_player, npcs=npcs, factions=factions,
                           locations=locations, viewer=viewer, current_session=current_session,
                           party_log=party_log, party_display_name=party_display_name,
                           parties=parties, selected_party_id=selected_party_id,
                           all_party_chars=all_chars_for_actor)


@player_bp.route("/<slug>/party/char/<char_slug>")
def char_page(slug, char_slug):
    r = campaign_access(slug)
    if r: return r
    meta = load(slug, "campaign.json")
    is_dm = bool(session.get(f"dm_{slug}")) or (session.get("user") == meta.get("owner"))
    is_player = bool(session.get("user")) and not is_dm
    viewer = session.get("user")
    all_chars = db.get_all_party_characters(slug, include_hidden=is_dm)
    char = next((c for c in all_chars if db.slugify(c["name"]) == char_slug), None)
    if not char:
        abort(404)
    if char.get("hidden") and not is_dm:
        abort(404)
    npcs = db.get_npcs(slug, include_hidden=is_dm)
    factions = db.get_factions(slug, include_hidden=is_dm)
    locations = db.get_locations(slug, include_hidden=is_dm)
    npc_names = {n["id"]: n["name"] for n in npcs}
    faction_names = {f["id"]: f["name"] for f in factions}
    def _resolve_actor(e):
        actor = e.get("actor_id", "")
        atype = e.get("actor_type", "")
        if atype == "npc": return npc_names.get(actor, actor)
        if atype == "faction": return faction_names.get(actor, actor)
        return actor or None
    raw_log = char.get("log", [])
    visible = db.get_visible_log(raw_log, is_dm=is_dm)
    for e in visible:
        e["_actor_name"] = _resolve_actor(e)
    char["_log"] = list(reversed(visible))
    char["_conditions"] = db.get_character_conditions(slug, char["name"], include_hidden=is_dm, include_resolved=False)
    _actor_npcs = db.get_npcs(slug, include_hidden=is_dm)
    _actor_facs = db.get_factions(slug, include_hidden=is_dm)
    _actor_locs = db.get_locations(slug, include_hidden=is_dm)
    _cname = char["name"]
    _cslug = db.slugify(_cname)
    _al = []
    for _n in _actor_npcs:
        for _e in db.get_visible_log(_n.get("log", []), is_dm=is_dm):
            _aid = _e.get("actor_id") or ""
            if _aid == _cname or _aid == _cslug:
                _al.append({**_e, "_target_name": _n["name"], "_target_id": _n["id"], "_target_type": "npc"})
    for _f in _actor_facs:
        for _e in db.get_visible_log(_f.get("log", []), is_dm=is_dm):
            _aid = _e.get("actor_id") or ""
            if _aid == _cname or _aid == _cslug:
                _al.append({**_e, "_target_name": _f["name"], "_target_id": _f["id"], "_target_type": "faction"})
    for _loc in _actor_locs:
        for _e in db.get_visible_log(_loc.get("log", []), is_dm=is_dm):
            _aid = _e.get("actor_id") or ""
            if _aid == _cname or _aid == _cslug:
                _al.append({**_e, "_target_name": _loc["name"], "_target_id": _loc["id"], "_target_type": "location"})
    for _pc in all_chars:
        if _pc["name"] == _cname:
            continue
        for _e in db.get_visible_log(_pc.get("log", []), is_dm=is_dm):
            _aid = _e.get("actor_id") or ""
            if _aid == _cname or _aid == _cslug:
                _al.append({**_e, "_target_name": _pc["name"], "_target_id": db.slugify(_pc["name"]), "_target_type": "char"})
    char["_actor_log"] = sorted(_al, key=lambda e: e.get("session", 0), reverse=True)
    current_session = db.get_current_session(slug)
    return render_template("char.html", meta=meta, char=char, slug=slug,
                           is_dm=is_dm, is_player=is_player, viewer=viewer,
                           npcs=npcs, factions=factions, locations=locations,
                           all_party_chars=all_chars, current_session=current_session)


@player_bp.route("/<slug>/assets")
def assets(slug):
    r = campaign_access(slug)
    if r: return r
    meta = load(slug, "campaign.json")
    data = db.get_assets(slug)
    stronghold = db.get_stronghold(slug)
    return render_template("assets.html", meta=meta, assets=data, stronghold=stronghold, slug=slug)


@player_bp.route("/<slug>/world")
def world(slug):
    r = campaign_access(slug)
    if r: return r
    meta = load(slug, "campaign.json")
    if meta and meta.get("onboarding_mode") == "party":
        _g = db.get_party_game(slug)
        if _g.get("phase") != "done":
            return redirect(url_for("party_game.party_play", slug=slug))
    is_dm = bool(session.get(f"dm_{slug}")) or (session.get("user") == meta.get("owner"))
    npcs = db.get_npcs(slug, include_hidden=is_dm)
    factions = db.get_factions(slug, include_hidden=is_dm)

    # Branch context (narrator-only; clear stale session vars for non-narrators)
    branches = db.get_branches(slug)
    if is_dm or bool(meta.get("demo_mode")):
        active_branch_id = session.get(f"branch_{slug}")
        active_branch = next((b for b in branches if b["id"] == active_branch_id), None)
    else:
        session.pop(f"branch_{slug}", None)
        active_branch = None
    fork_point = active_branch["fork_point"] if active_branch else None

    # Compute max_session from unfiltered logs
    all_sessions = [e.get("session", 0) for n in npcs for e in n.get("log", [])]
    all_sessions += [e.get("session", 0) for f in factions for e in f.get("log", [])]
    max_session = max(all_sessions) if all_sessions else 1

    as_of = request.args.get('as_of', type=int)

    # Apply log filters for world card display
    def _effective_dead(entity, cutoff):
        """Return whether entity was dead at the given session cutoff."""
        if not entity.get("dead"):
            return False
        dead_sess = entity.get("dead_session")
        if dead_sess is not None:
            return dead_sess <= cutoff
        # Fallback: infer from last log entry (must be called before log is filtered)
        sessions = [e.get("session", 0) for e in entity.get("log", [])]
        return (max(sessions) if sessions else 0) <= cutoff

    if active_branch:
        for n in npcs:
            n["dead"] = _effective_dead(n, fork_point)
            n["log"] = db.filter_log_for_branch(n.get("log", []), active_branch, branches)
        for f in factions:
            f["log"] = db.filter_log_for_branch(f.get("log", []), active_branch, branches)
    elif as_of:
        for n in npcs:
            n["dead"] = _effective_dead(n, as_of)
            n["log"] = [e for e in n.get("log", []) if e.get("session", 0) <= as_of]
        for f in factions:
            f["log"] = [e for e in f.get("log", []) if e.get("session", 0) <= as_of]

    # Always strip soft-deleted entries before template rendering
    for n in npcs:
        n["log"] = [e for e in n.get("log", []) if not e.get("deleted")]
    for f in factions:
        f["log"] = [e for e in f.get("log", []) if not e.get("deleted")]

    # When time-scrubbing or in a branch, hide entities not yet introduced
    if as_of or active_branch:
        npcs = [n for n in npcs if n.get("log")]
        factions = [f for f in factions if f.get("log")]

    for n in npcs:
        n["_rel"] = db.compute_npc_relationship(n, is_dm=is_dm,
                                                active_branch=active_branch, all_branches=branches)
    for f in factions:
        f["_rel"] = db.compute_npc_relationship(f, is_dm=is_dm,
                                                 active_branch=active_branch, all_branches=branches)
    conditions = db.get_conditions(slug, include_hidden=is_dm, include_resolved=False)
    for c in conditions:
        c["_severity"] = db.compute_condition_severity(c, is_dm=is_dm)
    locations = db.get_locations(slug, include_hidden=is_dm)
    party = db.get_all_party_characters(slug, include_hidden=is_dm)

    # Build _actor_log for each NPC: events on other entities where this NPC was the actor
    _scan_targets = (
        [(n, "npc") for n in npcs] +
        [(f, "faction") for f in factions] +
        [(loc, "location") for loc in locations] +
        [(pc, "char") for pc in party]
    )
    for _npc in npcs:
        _al = []
        for _ent, _etype in _scan_targets:
            if _etype == "npc" and _ent["id"] == _npc["id"]:
                continue
            _tid = db.slugify(_ent["name"]) if _etype == "char" else _ent.get("id", "")
            for _e in db.get_visible_log(_ent.get("log", []), is_dm=is_dm):
                if _e.get("actor_id") == _npc["id"]:
                    _al.append({**_e, "_target_name": _ent["name"], "_target_id": _tid, "_target_type": _etype})
        _npc["_actor_log"] = sorted(_al, key=lambda e: e.get("session", 0), reverse=True)

    return render_template("world.html", meta=meta, npcs=npcs, factions=factions,
                           conditions=conditions, locations=locations, slug=slug, is_dm=is_dm,
                           as_of=as_of, max_session=max_session,
                           branches=branches, active_branch=active_branch, party=party)


@player_bp.route("/<slug>/branch/create", methods=["POST"])
def branch_create(slug):
    _validate_slug(slug)
    meta = load(slug, "campaign.json")
    if not meta.get("demo_mode"):
        if not session.get("user"):
            return redirect(url_for("auth.login"))
        if meta.get("owner") != session.get("user"):
            abort(403)
    name = request.form.get("name", "").strip()
    fork_point = request.form.get("fork_point", type=int)
    parent_branch = request.form.get("parent_branch", "").strip() or None
    if not name or not fork_point:
        flash("Branch name and fork session required.")
        return redirect(url_for("player.world", slug=slug))
    branch_id = db.create_branch(slug, name, fork_point, parent_branch=parent_branch)
    session[f"branch_{slug}"] = branch_id
    return redirect(url_for("player.world", slug=slug))


@player_bp.route("/<slug>/branch/switch", methods=["POST"])
def branch_switch(slug):
    _validate_slug(slug)
    meta = load(slug, "campaign.json")
    if not meta.get("demo_mode"):
        if not session.get("user"):
            return redirect(url_for("auth.login"))
        is_narrator = (meta.get("owner") == session.get("user")) or bool(session.get(f"dm_{slug}"))
        if not is_narrator:
            abort(403)
    branch_id = request.form.get("branch_id", "").strip()
    if branch_id:
        session[f"branch_{slug}"] = branch_id
    else:
        session.pop(f"branch_{slug}", None)
    return redirect(url_for("player.world", slug=slug))


@player_bp.route("/<slug>/branch/delete", methods=["POST"])
def branch_delete(slug):
    _validate_slug(slug)
    meta = load(slug, "campaign.json")
    if not meta.get("demo_mode"):
        if not session.get("user"):
            return redirect(url_for("auth.login"))
        if meta.get("owner") != session.get("user"):
            abort(403)
    branch_id = request.form.get("branch_id", "").strip()
    if branch_id:
        db.delete_branch(slug, branch_id)
        if session.get(f"branch_{slug}") == branch_id:
            session.pop(f"branch_{slug}", None)
    return redirect(url_for("player.world", slug=slug))


def get_ripple_chains(slug, include_hidden=False):
    npcs = db.get_npcs(slug, include_hidden=include_hidden)
    factions = db.get_factions(slug, include_hidden=include_hidden)
    party = db.get_all_party_characters(slug, include_hidden=True)

    all_events = {}
    for npc in npcs:
        for entry in npc.get("log", []):
            if entry.get("id") and not entry.get("deleted"):
                all_events[entry["id"]] = {"event": entry, "entity_name": npc["name"], "entity_id": npc["id"], "entity_type": "npc"}
    for faction in factions:
        for entry in faction.get("log", []):
            if entry.get("id") and not entry.get("deleted"):
                all_events[entry["id"]] = {"event": entry, "entity_name": faction["name"], "entity_id": faction["id"], "entity_type": "faction"}

    chains = {}
    for event_data in all_events.values():
        src = event_data["event"].get("ripple_source")
        if src and src.get("event_id"):
            sid = src["event_id"]
            if sid not in chains:
                chains[sid] = {"source": all_events.get(sid), "ripples": []}
            chains[sid]["ripples"].append(event_data)

    # Surface character conditions as chain outcomes
    npc_index = {n["id"]: n for n in npcs}
    faction_index = {f["id"]: f for f in factions}
    for char in party:
        for cond in char.get("conditions", []):
            if cond.get("resolved"):
                continue
            linked_id = cond.get("linked_npc_id") or cond.get("linked_faction_id")
            if not linked_id:
                continue
            is_npc = bool(cond.get("linked_npc_id"))
            entity = npc_index.get(linked_id) if is_npc else faction_index.get(linked_id)
            if not entity:
                continue
            acquired = cond.get("acquired_session", 0)
            trigger = next(
                (e for e in entity.get("log", []) if e.get("session") == acquired and e.get("id")),
                None
            )
            if not trigger:
                continue
            tid = trigger["id"]
            if tid not in chains:
                chains[tid] = {
                    "source": all_events.get(tid) or {
                        "event": trigger,
                        "entity_name": entity["name"],
                        "entity_id": linked_id,
                        "entity_type": "npc" if is_npc else "faction",
                    },
                    "ripples": [],
                }
            chains[tid]["ripples"].append({
                "entity_name": char["name"],
                "entity_id": None,
                "entity_type": "character_condition",
                "condition": cond,
                "event": {
                    "session": acquired,
                    "note": cond.get("description") or cond["name"],
                    "polarity": None,
                },
            })

    result = [c for c in chains.values() if c["source"]]
    result.sort(key=lambda x: x["source"]["event"].get("session", 0), reverse=True)
    return result


@player_bp.route("/<slug>/world/ripples")
def ripple_chains(slug):
    r = campaign_access(slug)
    if r: return r
    meta = load(slug, "campaign.json")
    is_dm = bool(session.get(f"dm_{slug}"))
    chains = get_ripple_chains(slug, include_hidden=is_dm)
    npcs = db.get_npcs(slug, include_hidden=is_dm)
    factions = db.get_factions(slug, include_hidden=is_dm)
    locations = db.get_locations(slug, include_hidden=is_dm)
    return render_template("ripples.html", meta=meta, slug=slug, chains=chains, is_dm=is_dm,
                           npcs=npcs, factions=factions, locations=locations)


@player_bp.route("/<slug>/world/graph")
def world_graph(slug):
    r = campaign_access(slug)
    if r: return r
    meta = load(slug, "campaign.json")
    is_dm = bool(session.get(f"dm_{slug}"))
    return render_template("graph.html", meta=meta, slug=slug, is_dm=is_dm)


@player_bp.route("/<slug>/world/graph-data")
def world_graph_data(slug):
    r = campaign_access(slug)
    if r: return r
    meta = load(slug, "campaign.json")
    is_dm = bool(session.get(f"dm_{slug}")) or (session.get("user") == meta.get("owner"))
    as_of = request.args.get('as_of', type=int)
    npcs = db.get_npcs(slug, include_hidden=is_dm)
    factions = db.get_factions(slug, include_hidden=is_dm)

    # Branch context (narrator-only)
    branches = db.get_branches(slug)
    if is_dm or bool(meta.get("demo_mode")):
        active_branch_id = session.get(f"branch_{slug}")
        active_branch = next((b for b in branches if b["id"] == active_branch_id), None)
    else:
        active_branch = None
    fork_point = active_branch["fork_point"] if active_branch else None

    nodes = []
    edges = []
    seen_edges = set()
    _rel_color_map = {"ally": "allied", "rival": "hostile", "hostile": "hostile",
                      "family": "friendly", "friendly": "friendly",
                      "other": "neutral", "member": "allied"}
    _rel_hex = {"allied": "#7ec87e", "friendly": "#5ba87e", "neutral": "#888888", "hostile": "#e05c5c"}

    def _vis(e): return e.get("visibility", "dm_only" if e.get("dm_only") else "public")

    def _branch_filter(log):
        if active_branch:
            return db.filter_log_for_branch(log, active_branch, branches)
        elif as_of:
            return [e for e in log if e.get("session", 0) <= as_of]
        return [e for e in log if not e.get("branch")]

    # Only include IDs of entities that are visible at this point in time,
    # so edges don't reference nodes that haven't appeared yet.
    def _entity_visible(entity):
        if not (as_of or active_branch):
            return True
        return bool(_branch_filter(entity.get("log", [])))

    party = db.get_all_party_characters(slug, include_hidden=is_dm)
    known_ids = ({n["id"] for n in npcs if _entity_visible(n)} |
                 {f["id"] for f in factions if _entity_visible(f)} |
                 {f"_char_{db.slugify(c['name'])}" for c in party})

    effective_as_of = as_of or fork_point

    def _graph_effective_dead(entity, cutoff):
        if not entity.get("dead"):
            return False
        if cutoff is None:
            return True
        dead_sess = entity.get("dead_session")
        if dead_sess is not None:
            return dead_sess <= cutoff
        sessions = [e.get("session", 0) for e in entity.get("log", [])]
        return (max(sessions) if sessions else 0) <= cutoff

    # Neutral-observer moral score: net harm/benefit each entity has caused as actor_id.
    # Only counts direct DM-logged events — excludes ripples (auto-propagation) and
    # self-actor entries (pre-"caused by" AI convention where actor_id == log owner).
    _actor_net = {}
    def _tally_actor(entries, self_id=None):
        for _e in entries:
            if _e.get("deleted"):
                continue
            _aid = _e.get("actor_id")
            if not _aid:
                continue
            if self_id and _aid == self_id:
                continue
            if _e.get("ripple_source"):
                continue
            if not is_dm and _vis(_e) != "public":
                continue
            _pol = _e.get("polarity")
            _int = float(_e.get("intensity") or 1)
            if _pol == "negative":
                _actor_net[_aid] = _actor_net.get(_aid, 0) - _int
            elif _pol == "positive":
                _actor_net[_aid] = _actor_net.get(_aid, 0) + _int

    for _entity in list(npcs) + list(factions):
        _tally_actor(_branch_filter(_entity.get("log", [])), self_id=_entity["id"])
    _tally_actor(_branch_filter(meta.get("party_group_log", [])))

    def _moral_rel(net):
        if net >= 6:  return "allied"
        if net >= 3:  return "friendly"
        if net > -3:  return "neutral"
        return "hostile"

    for npc in npcs:
        # When time-scrubbing or in a branch, skip entities not yet introduced
        time_log = [e for e in _branch_filter(npc.get("log", [])) if not e.get("deleted")]
        if (as_of or active_branch) and not time_log:
            continue
        rel = db.compute_npc_relationship(npc, is_dm=is_dm, max_session=as_of,
                                          active_branch=active_branch, all_branches=branches)
        visible_log = [e for e in time_log if is_dm or _vis(e) == "public"]
        last_note = visible_log[-1]["note"] if visible_log else ""
        nodes.append({"data": {
            "id": npc["id"],
            "label": npc["name"],
            "type": "npc",
            "relationship": rel["relationship"],
            "score": rel.get("score") or 0,
            "hidden": bool(npc.get("hidden")),
            "dead": _graph_effective_dead(npc, effective_as_of),
            "log_count": len(visible_log),
            "role": npc.get("role", ""),
            "last_note": last_note,
            "has_conflict": bool(rel.get("has_conflict")),
            "formal_relationship": rel.get("formal_relationship"),
            "personal_relationship": rel.get("personal_relationship"),
            "moral_rel": _moral_rel(_actor_net.get(npc["id"], 0)),
            "moral_score": round(_actor_net.get(npc["id"], 0), 1),
        }})
        for edge in npc.get("relations", []):
            tid = edge.get("target")
            if not tid or tid not in known_ids:
                continue
            if not is_dm and edge.get("dm_only"):
                continue
            is_dm_edge = bool(edge.get("dm_only"))
            key = (frozenset([npc["id"], tid]), True) if is_dm_edge else frozenset([npc["id"], tid])
            if key in seen_edges:
                continue
            seen_edges.add(key)
            edge_id = f"{npc['id']}__{tid}{'__dm' if is_dm_edge else ''}"
            formal_rel = edge.get("formal_relation")
            personal_rel = edge.get("personal_relation")
            if formal_rel and personal_rel and formal_rel != personal_rel:
                _fr = _rel_color_map.get(formal_rel, "neutral")
                _pr = _rel_color_map.get(personal_rel, "neutral")
                edges.append({"data": {
                    "id": edge_id + "__formal",
                    "source": npc["id"], "target": tid,
                    "relation": "conflict_formal",
                    "relationship": _fr,
                    "rel_color": _rel_hex.get(_fr, "#888888"),
                    "weight": float(edge.get("weight", 0.5)),
                    "dm_only": is_dm_edge,
                }})
                edges.append({"data": {
                    "id": edge_id + "__personal",
                    "source": npc["id"], "target": tid,
                    "relation": "conflict_personal",
                    "relationship": _pr,
                    "rel_color": _rel_hex.get(_pr, "#888888"),
                    "weight": float(edge.get("weight", 0.5)),
                    "dm_only": is_dm_edge,
                }})
            else:
                edges.append({"data": {
                    "id": edge_id,
                    "source": npc["id"],
                    "target": tid,
                    "relation": edge.get("relation", "ally"),
                    "weight": float(edge.get("weight", 0.5)),
                    "dm_only": is_dm_edge,
                }})
        # Faction membership edges (one per faction the NPC belongs to)
        for fid in npc.get("factions", []):
            if not fid or fid not in known_ids:
                continue
            key = frozenset([npc["id"], fid])
            if key not in seen_edges:
                seen_edges.add(key)
                edges.append({"data": {
                    "id": f"{npc['id']}__{fid}__member",
                    "source": npc["id"],
                    "target": fid,
                    "relation": "member",
                    "weight": 0.8,
                }})
        # Hidden faction membership edges — DM only
        if is_dm:
            for fid in npc.get("hidden_factions", []):
                if not fid or fid not in known_ids:
                    continue
                key = (frozenset([npc["id"], fid]), True)
                if key not in seen_edges:
                    seen_edges.add(key)
                    edges.append({"data": {
                        "id": f"{npc['id']}__{fid}__member__dm",
                        "source": npc["id"],
                        "target": fid,
                        "relation": "member",
                        "weight": 0.8,
                        "dm_only": True,
                    }})

    for faction in factions:
        time_log = [e for e in _branch_filter(faction.get("log", [])) if not e.get("deleted")]
        if (as_of or active_branch) and not time_log:
            continue
        visible_log = [e for e in time_log if is_dm or _vis(e) == "public"]
        last_note = visible_log[-1]["note"] if visible_log else ""
        frel = db.compute_npc_relationship(faction, is_dm=is_dm, max_session=as_of,
                                           active_branch=active_branch, all_branches=branches)
        nodes.append({"data": {
            "id": faction["id"],
            "label": faction["name"],
            "type": "faction",
            "relationship": frel["relationship"],
            "score": frel.get("score") or 0,
            "hidden": bool(faction.get("hidden")),
            "log_count": len(visible_log),
            "role": "",
            "last_note": last_note,
            "has_conflict": bool(frel.get("has_conflict")),
            "formal_relationship": frel.get("formal_relationship"),
            "personal_relationship": frel.get("personal_relationship"),
            "moral_rel": _moral_rel(_actor_net.get(faction["id"], 0)),
            "moral_score": round(_actor_net.get(faction["id"], 0), 1),
        }})
        for edge in faction.get("relations", []):
            tid = edge.get("target")
            if not tid or tid not in known_ids:
                continue
            if not is_dm and edge.get("dm_only"):
                continue
            is_dm_edge = bool(edge.get("dm_only"))
            key = (frozenset([faction["id"], tid]), True) if is_dm_edge else frozenset([faction["id"], tid])
            if key in seen_edges:
                continue
            seen_edges.add(key)
            edge_id = f"{faction['id']}__{tid}{'__dm' if is_dm_edge else ''}"
            formal_rel = edge.get("formal_relation")
            personal_rel = edge.get("personal_relation")
            if formal_rel and personal_rel and formal_rel != personal_rel:
                _fr = _rel_color_map.get(formal_rel, "neutral")
                _pr = _rel_color_map.get(personal_rel, "neutral")
                edges.append({"data": {
                    "id": edge_id + "__formal",
                    "source": faction["id"], "target": tid,
                    "relation": "conflict_formal",
                    "relationship": _fr,
                    "rel_color": _rel_hex.get(_fr, "#888888"),
                    "weight": float(edge.get("weight", 0.5)),
                    "dm_only": is_dm_edge,
                }})
                edges.append({"data": {
                    "id": edge_id + "__personal",
                    "source": faction["id"], "target": tid,
                    "relation": "conflict_personal",
                    "relationship": _pr,
                    "rel_color": _rel_hex.get(_pr, "#888888"),
                    "weight": float(edge.get("weight", 0.5)),
                    "dm_only": is_dm_edge,
                }})
            else:
                edges.append({"data": {
                    "id": edge_id,
                    "source": faction["id"],
                    "target": tid,
                    "relation": edge.get("relation", "ally"),
                    "weight": float(edge.get("weight", 0.5)),
                    "dm_only": is_dm_edge,
                }})

    # ── Dynamic inter-entity edges from ripple actor history ─────────────────
    for irel in db.get_inter_entity_relations(slug, max_session=as_of,
                                               active_branch=active_branch, all_branches=branches):
        if not irel.get("computed"):
            continue
        if irel.get("dm_only") and not is_dm:
            continue
        a_id, b_id = irel["a_id"], irel["b_id"]
        if a_id not in known_ids or b_id not in known_ids:
            continue
        static_key = frozenset([a_id, b_id])
        score = irel.get("score") or 0
        if static_key in seen_edges:
            # Enrich the existing static edge with computed dynamics
            for edge in edges:
                ed = edge["data"]
                if frozenset([ed.get("source", ""), ed.get("target", "")]) == static_key \
                        and not ed.get("dm_only") and not ed.get("dynamic"):
                    ed["dynamic_score"] = score
                    ed["dynamic_relationship"] = irel["relationship"]
                    break
        else:
            seen_edges.add(static_key)
            edges.append({"data": {
                "id": f"{a_id}__{b_id}__dynamic",
                "source": a_id,
                "target": b_id,
                "relation": "inter_faction",
                "interaction": True,
                "dynamic": True,
                "dynamic_score": score,
                "dynamic_relationship": irel["relationship"],
                "weight": min(1.0, abs(score) / 4),
            }})

    # ── Party hub(s) + characters ─────────────────────────────────────────────
    meta = load(slug, "campaign.json")
    party_name = meta.get("party_name") or "Party"
    _parties_data = db.get_parties(slug)
    _multi_party = len(_parties_data) > 1
    # Map char name → hub node id so character edges connect to the right star
    _char_hub = {}
    for _pg in _parties_data:
        _phub = f"_party_{_pg['id']}" if _multi_party else "_party"
        for _pc in _pg.get("characters", []):
            _char_hub[_pc["name"]] = _phub
    _default_hub = f"_party_{_parties_data[0]['id']}" if _multi_party else "_party"

    if party:
        # Build reverse lookup: event_id → entity_id so character known_events
        # can be translated into entity connections
        event_to_entity = {}
        for npc in npcs:
            for entry in npc.get("log", []):
                if entry.get("id"):
                    event_to_entity[entry["id"]] = npc["id"]
        for faction in factions:
            for entry in faction.get("log", []):
                if entry.get("id"):
                    event_to_entity[entry["id"]] = faction["id"]

        # Emit one star hub per party group
        _rel_map = {"ally": "friendly", "rival": "hostile"}
        for _pg in _parties_data:
            _phub = f"_party_{_pg['id']}" if _multi_party else "_party"
            _hub_label = _pg["name"] if _multi_party else party_name
            nodes.append({"data": {
                "id": _phub,
                "label": _hub_label,
                "type": "party",
                "relationship": "allied",
                "score": 0,
                "hidden": False,
                "log_count": 0,
                "role": "",
                "last_note": "",
            }})
            # Party hub → explicit party_relations
            for pr in meta.get("party_relations", []):
                tid = pr.get("target")
                if not tid or tid not in known_ids:
                    continue
                key = frozenset([_phub, tid])
                if key not in seen_edges:
                    seen_edges.add(key)
                    edges.append({"data": {
                        "id": f"{_phub}__{tid}",
                        "source": _phub,
                        "target": tid,
                        "relation": "party_contact",
                        "relationship": _rel_map.get(pr.get("relation", "ally"), "neutral"),
                        "weight": float(pr.get("weight", 0.5)),
                    }})

        # Individual character nodes + their known_event connections
        for char in party:
            cid = f"_char_{db.slugify(char['name'])}"
            _phub = _char_hub.get(char["name"], _default_hub)
            nodes.append({"data": {
                "id": cid,
                "label": char["name"],
                "type": "character",
                "relationship": "allied",
                "score": 0,
                "hidden": bool(char.get("hidden")),
                "dead": bool(char.get("dead") or char.get("status") == "dead"),
                "log_count": 0,
                "role": char.get("class", ""),
                "last_note": "",
            }})
            edges.append({"data": {
                "id": f"{_phub}__{cid}",
                "source": _phub,
                "target": cid,
                "relation": "member",
                "weight": 0.8,
            }})
            # Faction membership edges for party characters
            for fid in char.get("factions", []):
                if not fid or fid not in known_ids:
                    continue
                key = frozenset([cid, fid])
                if key not in seen_edges:
                    seen_edges.add(key)
                    edges.append({"data": {
                        "id": f"{cid}__{fid}__member",
                        "source": cid,
                        "target": fid,
                        "relation": "member",
                        "weight": 0.8,
                    }})
            # Active condition edges (linked_npc_id / linked_faction_id)
            for cond in char.get("conditions", []):
                if cond.get("resolved"):
                    continue
                if not is_dm and cond.get("hidden"):
                    continue
                target = cond.get("linked_faction_id") or cond.get("linked_npc_id")
                if not target or target not in known_ids:
                    continue
                key = frozenset([cid, target])
                if key not in seen_edges:
                    seen_edges.add(key)
                    edges.append({"data": {
                        "id": f"{cid}__{target}__condition",
                        "source": cid,
                        "target": target,
                        "relation": "bond",
                        "interaction": True,
                        "weight": 0.6,
                    }})
            # Connect character to entities they specifically know about
            char_connected = set()
            for event_id in char.get("known_events", []):
                entity_id = event_to_entity.get(event_id)
                if entity_id and entity_id not in char_connected:
                    char_connected.add(entity_id)
                    key = frozenset([cid, entity_id])
                    if key not in seen_edges:
                        seen_edges.add(key)
                        edges.append({"data": {
                            "id": f"{cid}__{entity_id}",
                            "source": cid,
                            "target": entity_id,
                            "relation": "knows",
                            "interaction": True,
                            "weight": 0.25,
                        }})
            # Direct personal relations with full dual-axis conflict support
            for rel in char.get("relations", []):
                tid = rel.get("target")
                if not tid or tid not in known_ids:
                    continue
                is_dm_edge = bool(rel.get("dm_only"))
                key = (frozenset([cid, tid]), True) if is_dm_edge else frozenset([cid, tid])
                if key in seen_edges:
                    continue
                seen_edges.add(key)
                edge_id = f"{cid}__{tid}__charrel{'__dm' if is_dm_edge else ''}"
                formal_rel = rel.get("formal_relation")
                personal_rel = rel.get("personal_relation")
                if formal_rel and personal_rel and formal_rel != personal_rel:
                    _fr = _rel_color_map.get(formal_rel, "neutral")
                    _pr = _rel_color_map.get(personal_rel, "neutral")
                    edges.append({"data": {
                        "id": edge_id + "__formal",
                        "source": cid, "target": tid,
                        "relation": "conflict_formal",
                        "relationship": _fr,
                        "rel_color": _rel_hex.get(_fr, "#888888"),
                        "weight": float(rel.get("weight", 0.5)),
                        "dm_only": is_dm_edge,
                    }})
                    edges.append({"data": {
                        "id": edge_id + "__personal",
                        "source": cid, "target": tid,
                        "relation": "conflict_personal",
                        "relationship": _pr,
                        "rel_color": _rel_hex.get(_pr, "#888888"),
                        "weight": float(rel.get("weight", 0.5)),
                        "dm_only": is_dm_edge,
                    }})
                else:
                    _eff_rel = rel.get("relation") or rel.get("formal_relation") or "ally"
                    edges.append({"data": {
                        "id": edge_id,
                        "source": cid, "target": tid,
                        "relation": "char_relation",
                        "relationship": _rel_color_map.get(_eff_rel, "neutral"),
                        "weight": float(rel.get("weight", 0.5)),
                        "dm_only": is_dm_edge,
                    }})

    # ── Party-affiliate NPCs → party hub ─────────────────────────────────────
    for npc in npcs:
        if not npc.get("party_affiliate"):
            continue
        key = frozenset([_default_hub, npc["id"]])
        if key not in seen_edges:
            seen_edges.add(key)
            edges.append({"data": {
                "id": f"{_default_hub}__{npc['id']}__affiliate",
                "source": _default_hub,
                "target": npc["id"],
                "relation": "party_affiliate",
                "weight": 0.9,
            }})

    _pol_rel = {"positive": "friendly", "negative": "hostile", "neutral": "neutral"}

    def _add_acted_edge(src, tgt, polarity, dm_only=False):
        if not is_dm and dm_only:
            return
        key = frozenset([src, tgt])
        if key in seen_edges:
            return
        seen_edges.add(key)
        rel = _pol_rel.get(polarity, "neutral")
        edges.append({"data": {
            "id": f"{src}__{tgt}__acted",
            "source": src,
            "target": tgt,
            "relation": "party_contact",
            "relationship": rel,
            "weight": 0.5,
            "interaction": True,
        }})

    # ── NPC/faction/char actor → character diamond ────────────────────────────
    for char in party:
        cid = f"_char_{db.slugify(char['name'])}"
        for entry in char.get("log", []):
            if entry.get("deleted"):
                continue
            aid = entry.get("actor_id")
            if not aid:
                continue
            if entry.get("actor_type") == "char":
                aid = f"_char_{db.slugify(aid)}"
            if aid not in known_ids or aid == cid:
                continue
            _add_acted_edge(aid, cid, entry.get("polarity"), entry.get("actor_dm_only", False))

    # ── Character diamond → NPC/faction (char caused event on NPC or faction) ──
    for npc in npcs:
        for entry in npc.get("log", []):
            if entry.get("deleted") or entry.get("actor_type") != "char":
                continue
            raw_name = entry.get("actor_id", "")
            if not raw_name:
                continue
            cid = f"_char_{db.slugify(raw_name)}"
            if cid not in known_ids:
                continue
            _add_acted_edge(cid, npc["id"], entry.get("polarity"), entry.get("actor_dm_only", False))
    for faction in factions:
        for entry in faction.get("log", []):
            if entry.get("deleted") or entry.get("actor_type") != "char":
                continue
            raw_name = entry.get("actor_id", "")
            if not raw_name:
                continue
            cid = f"_char_{db.slugify(raw_name)}"
            if cid not in known_ids:
                continue
            _add_acted_edge(cid, faction["id"], entry.get("polarity"), entry.get("actor_dm_only", False))

    # ── Actor → party star edges (from party_group_log) ───────────────────────
    for entry in meta.get("party_group_log", []):
        if entry.get("deleted"):
            continue
        aid = entry.get("actor_id")
        if not aid:
            continue
        if entry.get("actor_type") == "char":
            aid = f"_char_{db.slugify(aid)}"
        if aid not in known_ids:
            continue
        _add_acted_edge(aid, _default_hub, entry.get("polarity"), entry.get("actor_dm_only", False))

    return jsonify({"nodes": nodes, "edges": edges})


@player_bp.route("/<slug>/world/npc/<npc_id>")
def npc(slug, npc_id):
    r = campaign_access(slug)
    if r: return r
    meta = load(slug, "campaign.json")
    is_dm = bool(session.get(f"dm_{slug}")) or (session.get("user") == meta.get("owner"))
    is_player = bool(session.get("user")) and not is_dm
    npc_obj = next((n for n in db.get_npcs(slug, include_hidden=True) if n["id"] == npc_id), None)
    if not npc_obj:
        abort(404)
    npc_hidden = npc_obj.get("hidden", False)
    # Hidden NPCs: non-DM can still view if there are public actor-caused events to show;
    # strip the NPC's own log to only visible entries for non-DM viewers.
    if npc_hidden and not is_dm:
        npc_obj = dict(npc_obj)
        npc_obj["log"] = db.get_visible_log(npc_obj.get("log", []), is_dm=False)

    # Branch context — filter log to fork_point
    branches = db.get_branches(slug)
    active_branch_id = session.get(f"branch_{slug}")
    active_branch = next((b for b in branches if b["id"] == active_branch_id), None)
    fork_point = active_branch["fork_point"] if active_branch else None
    if active_branch:
        npc_obj["log"] = db.filter_log_for_branch(npc_obj.get("log", []), active_branch, branches)
    viewer_character = None
    viewer_known_events = None
    if is_player and session.get("user"):
        viewer_character = db.get_player_character(slug, session["user"])
        if viewer_character:
            viewer_known_events = set(viewer_character.get("known_events", []))

    party = db.get_all_party_characters(slug) if is_dm else []
    factions = db.get_factions(slug) if is_dm else []
    world_npcs = db.get_npcs(slug) if is_dm else []

    # DM preview: see the world through a character's eyes
    preview_char = None
    preview_known_events = None
    if is_dm:
        preview_name = request.args.get("preview", "").strip()
        if preview_name:
            preview_char = next((c for c in party if c["name"] == preview_name), None)
            if preview_char:
                preview_known_events = set(preview_char.get("known_events", []))

    # Use preview lens if active, otherwise viewer lens
    effective_known_events = preview_known_events if preview_char else viewer_known_events
    effective_is_dm = is_dm and not preview_char
    rel_data = db.compute_npc_relationship(npc_obj, known_events=effective_known_events, is_dm=effective_is_dm,
                                           active_branch=active_branch, all_branches=branches)

    char_bonds = db.get_conditions_for_npc(slug, npc_id) if is_dm else []

    ripple_chains = {}
    if is_dm:
        source_ids = [e["id"] for e in npc_obj.get("log", [])
                      if e.get("id") and e.get("polarity") and not e.get("ripple_source")]
        ripple_chains = db.get_ripple_chains(slug, source_ids)

    inter_entity = []
    formalize_suggestions = []
    if is_dm:
        npc_names = {n["id"]: n["name"] for n in db.get_npcs(slug, include_hidden=True)}
        faction_names = {f["id"]: f["name"] for f in db.get_factions(slug, include_hidden=True)}
        for rel in db.get_inter_entity_relations(slug):
            if not rel.get("computed"):
                continue
            if rel["a_id"] == npc_id or rel["b_id"] == npc_id:
                other_id = rel["b_id"] if rel["a_id"] == npc_id else rel["a_id"]
                other_type = rel["b_type"] if rel["a_id"] == npc_id else rel["a_type"]
                name_map = npc_names if other_type == "npc" else faction_names
                inter_entity.append({
                    "entity_id": other_id, "entity_type": other_type,
                    "entity_name": name_map.get(other_id, other_id),
                    "relationship": rel["relationship"],
                    "score": rel.get("score"),
                    "trend": rel.get("trend"),
                })
        _suggest_map = {"allied": "ally", "friendly": "ally", "hostile": "rival", "war": "rival"}
        existing_edges = {(r.get("target"), r.get("target_type", "npc"))
                          for r in npc_obj.get("relations", [])}
        for er in inter_entity:
            suggested = _suggest_map.get(er["relationship"])
            check_id = f"_char_{db.slugify(er['entity_id'])}" if er["entity_type"] == "char" else er["entity_id"]
            if suggested and (check_id, er["entity_type"]) not in existing_edges:
                formalize_suggestions.append({**er, "suggested_relation": suggested})

    all_factions_full = db.get_factions(slug, include_hidden=True) if is_dm else factions
    link_npcs = db.get_npcs(slug, include_hidden=is_dm)
    link_factions = db.get_factions(slug, include_hidden=is_dm)
    link_locations = db.get_locations(slug, include_hidden=is_dm)
    backlinks = _get_backlinks(npc_obj["name"], npc_id, link_npcs, link_factions, link_locations)

    actor_logs = []
    for _n in db.get_npcs(slug, include_hidden=is_dm):
        if _n["id"] == npc_id:
            continue
        for _e in db.get_visible_log(_n.get("log", []), is_dm=is_dm):
            if _e.get("actor_id") == npc_id:
                actor_logs.append({**_e, "_target_name": _n["name"], "_target_id": _n["id"], "_target_type": "npc"})
    for _f in db.get_factions(slug, include_hidden=is_dm):
        for _e in db.get_visible_log(_f.get("log", []), is_dm=is_dm):
            if _e.get("actor_id") == npc_id:
                actor_logs.append({**_e, "_target_name": _f["name"], "_target_id": _f["id"], "_target_type": "faction"})
    for _loc in db.get_locations(slug, include_hidden=is_dm):
        for _e in db.get_visible_log(_loc.get("log", []), is_dm=is_dm):
            if _e.get("actor_id") == npc_id:
                actor_logs.append({**_e, "_target_name": _loc["name"], "_target_id": _loc["id"], "_target_type": "location"})
    for _pc in db.get_all_party_characters(slug, include_hidden=is_dm):
        for _e in db.get_visible_log(_pc.get("log", []), is_dm=is_dm):
            if _e.get("actor_id") == npc_id:
                actor_logs.append({**_e, "_target_name": _pc["name"], "_target_id": db.slugify(_pc["name"]), "_target_type": "char"})
    actor_logs.sort(key=lambda e: e.get("session", 0), reverse=True)

    # If NPC is hidden and viewer is not DM, only render if there's public content to show
    if npc_hidden and not is_dm and not actor_logs and not npc_obj.get("log"):
        abort(404)

    return render_template("npc.html", meta=meta, npc=npc_obj, slug=slug,
                           is_dm=is_dm, is_player=is_player,
                           viewer_known_events=effective_known_events,
                           preview_char=preview_char,
                           current_session=db.get_current_session(slug),
                           rel_data=rel_data, party=party,
                           factions=factions, world_npcs=world_npcs,
                           char_bonds=char_bonds,
                           ripple_chains=ripple_chains,
                           inter_entity=inter_entity,
                           formalize_suggestions=formalize_suggestions,
                           active_branch=active_branch,
                           all_factions=all_factions_full,
                           link_npcs=link_npcs, link_factions=link_factions,
                           link_locations=link_locations,
                           backlinks=backlinks,
                           actor_logs=actor_logs)


@player_bp.route("/<slug>/world/faction/<faction_id>")
def faction(slug, faction_id):
    r = campaign_access(slug)
    if r: return r
    meta = load(slug, "campaign.json")
    is_dm = bool(session.get(f"dm_{slug}")) or (session.get("user") == meta.get("owner"))
    faction_obj = next((f for f in db.get_factions(slug, include_hidden=is_dm) if f["id"] == faction_id), None)
    if not faction_obj:
        abort(404)

    # Branch context — filter log to fork_point
    branches = db.get_branches(slug)
    active_branch_id = session.get(f"branch_{slug}")
    active_branch = next((b for b in branches if b["id"] == active_branch_id), None)
    fork_point = active_branch["fork_point"] if active_branch else None
    if active_branch:
        faction_obj["log"] = db.filter_log_for_branch(faction_obj.get("log", []), active_branch, branches)

    rel_data = db.compute_npc_relationship(faction_obj, is_dm=is_dm,
                                           active_branch=active_branch, all_branches=branches)
    all_npcs = db.get_npcs(slug, include_hidden=is_dm)
    affiliated_npcs = [
        n for n in all_npcs
        if faction_id in n.get("factions", [])
        or (is_dm and faction_id in n.get("hidden_factions", []))
    ]
    all_factions = db.get_factions(slug, include_hidden=is_dm)
    party = db.get_all_party_characters(slug) if is_dm else []

    ripple_chains = {}
    if is_dm:
        source_ids = [e["id"] for e in faction_obj.get("log", [])
                      if e.get("id") and e.get("polarity") and not e.get("ripple_source")]
        ripple_chains = db.get_ripple_chains(slug, source_ids)

    inter_entity = []
    if is_dm:
        npc_names = {n["id"]: n["name"] for n in all_npcs}
        faction_names_map = {f["id"]: f["name"] for f in all_factions}
        for rel in db.get_inter_entity_relations(slug):
            if not rel.get("computed"):
                continue
            if rel["a_id"] == faction_id or rel["b_id"] == faction_id:
                other_id = rel["b_id"] if rel["a_id"] == faction_id else rel["a_id"]
                other_type = rel["b_type"] if rel["a_id"] == faction_id else rel["a_type"]
                name_map = npc_names if other_type == "npc" else faction_names_map
                inter_entity.append({
                    "entity_id": other_id, "entity_type": other_type,
                    "entity_name": name_map.get(other_id, other_id),
                    "relationship": rel["relationship"],
                    "score": rel.get("score"),
                    "trend": rel.get("trend"),
                })

    link_npcs = all_npcs
    link_factions = all_factions
    link_locations = db.get_locations(slug, include_hidden=is_dm)
    backlinks = _get_backlinks(faction_obj["name"], faction_id, link_npcs, link_factions, link_locations)
    char_bonds = db.get_conditions_for_faction(slug, faction_id)

    actor_logs = []
    for _n in db.get_npcs(slug, include_hidden=is_dm):
        for _e in db.get_visible_log(_n.get("log", []), is_dm=is_dm):
            if _e.get("actor_id") == faction_id:
                actor_logs.append({**_e, "_target_name": _n["name"], "_target_id": _n["id"], "_target_type": "npc"})
    for _f in db.get_factions(slug, include_hidden=is_dm):
        if _f["id"] == faction_id:
            continue
        for _e in db.get_visible_log(_f.get("log", []), is_dm=is_dm):
            if _e.get("actor_id") == faction_id:
                actor_logs.append({**_e, "_target_name": _f["name"], "_target_id": _f["id"], "_target_type": "faction"})
    for _loc in db.get_locations(slug, include_hidden=is_dm):
        for _e in db.get_visible_log(_loc.get("log", []), is_dm=is_dm):
            if _e.get("actor_id") == faction_id:
                actor_logs.append({**_e, "_target_name": _loc["name"], "_target_id": _loc["id"], "_target_type": "location"})
    for _pc in db.get_all_party_characters(slug, include_hidden=is_dm):
        for _e in db.get_visible_log(_pc.get("log", []), is_dm=is_dm):
            if _e.get("actor_id") == faction_id:
                actor_logs.append({**_e, "_target_name": _pc["name"], "_target_id": db.slugify(_pc["name"]), "_target_type": "char"})
    actor_logs.sort(key=lambda e: e.get("session", 0), reverse=True)

    affiliated_chars = faction_obj.get("affiliated_chars", [])
    faction_party_affiliated = faction_obj.get("party_affiliated", False)

    return render_template("faction.html", meta=meta, faction=faction_obj, slug=slug,
                           is_dm=is_dm, rel_data=rel_data,
                           current_session=db.get_current_session(slug),
                           affiliated_npcs=affiliated_npcs,
                           affiliated_chars=affiliated_chars,
                           faction_party_affiliated=faction_party_affiliated,
                           world_npcs=all_npcs, all_factions=all_factions, party=party,
                           ripple_chains=ripple_chains,
                           inter_entity=inter_entity,
                           active_branch=active_branch,
                           link_npcs=link_npcs, link_factions=link_factions,
                           link_locations=link_locations,
                           backlinks=backlinks,
                           char_bonds=char_bonds,
                           actor_logs=actor_logs)


@player_bp.route("/<slug>/world/location/<location_id>")
def location(slug, location_id):
    r = campaign_access(slug)
    if r: return r
    meta = load(slug, "campaign.json")
    is_dm = bool(session.get(f"dm_{slug}")) or (session.get("user") == meta.get("owner"))
    loc_obj = db.get_location(slug, location_id)
    if not loc_obj:
        abort(404)
    if loc_obj.get("hidden") and not is_dm:
        abort(404)
    loc_obj["log"] = [e for e in loc_obj.get("log", []) if not e.get("deleted")]
    link_npcs = db.get_npcs(slug, include_hidden=is_dm)
    link_factions = db.get_factions(slug, include_hidden=is_dm)
    link_locations = db.get_locations(slug, include_hidden=is_dm)
    party = db.get_all_party_characters(slug)
    backlinks = _get_backlinks(loc_obj["name"], location_id, link_npcs, link_factions, link_locations)
    # Collect events from other entities tagged at this location
    tagged_here = []
    for n in link_npcs:
        for e in n.get("log", []):
            if e.get("deleted") or e.get("location_id") != location_id:
                continue
            vis = e.get("visibility", "public")
            if not is_dm and vis == "dm_only":
                continue
            tagged_here.append({**e, "_entity_name": n["name"], "_entity_type": "npc", "_entity_id": n["id"]})
    for f in link_factions:
        for e in f.get("log", []):
            if e.get("deleted") or e.get("location_id") != location_id:
                continue
            vis = e.get("visibility", "public")
            if not is_dm and vis == "dm_only":
                continue
            tagged_here.append({**e, "_entity_name": f["name"], "_entity_type": "faction", "_entity_id": f["id"]})
    tagged_here.sort(key=lambda e: (e.get("session", 0),))
    branches = db.get_branches(slug)
    active_branch_id = session.get(f"branch_{slug}") if is_dm or meta.get("demo_mode") else None
    active_branch = next((b for b in branches if b["id"] == active_branch_id), None)
    return render_template("location.html", meta=meta, location=loc_obj, slug=slug,
                           is_dm=is_dm,
                           current_session=db.get_current_session(slug),
                           link_npcs=link_npcs, link_factions=link_factions,
                           link_locations=link_locations,
                           party=party,
                           tagged_here=tagged_here,
                           backlinks=backlinks,
                           active_branch=active_branch)


@player_bp.route("/<slug>/story")
def story(slug):
    r = campaign_access(slug)
    if r: return r
    meta = load(slug, "campaign.json")
    is_dm = bool(session.get(f"dm_{slug}"))
    quests = db.get_quests(slug, include_hidden=is_dm)
    npcs = db.get_npcs(slug, include_hidden=is_dm)
    factions = db.get_factions(slug, include_hidden=is_dm)
    locations = db.get_locations(slug)
    return render_template("story.html", meta=meta, quests=quests, slug=slug,
                           npcs=npcs, factions=factions, locations=locations)


@player_bp.route("/<slug>/journal")
def journal(slug):
    r = campaign_access(slug)
    if r: return r
    meta = load(slug, "campaign.json")
    is_dm = bool(session.get(f"dm_{slug}"))
    all_entries = db.get_journal(slug, include_deleted=is_dm)
    active = [e for e in all_entries if not e.get("deleted")]
    deleted = [e for e in all_entries if e.get("deleted")] if is_dm else []
    npcs = db.get_npcs(slug, include_hidden=is_dm)
    factions = db.get_factions(slug, include_hidden=is_dm)
    locations = db.get_locations(slug, include_hidden=is_dm)
    party = db.get_all_party_characters(slug)
    entries_rendered = [
        {**e, "idx": e["_raw_idx"], "recap_html": Markup(markdown.markdown(
            str(wikilinks_filter(e.get("recap", ""), slug, npcs, factions, locations, party)),
            extensions=["nl2br"]
        ))}
        for e in reversed(active)
    ]
    deleted_rendered = [
        {**e, "idx": e["_raw_idx"]}
        for e in deleted
    ]
    session_nums = {e["session"] for e in entries_rendered if "session" in e}
    deltas = {n: db.get_session_delta(slug, n) for n in session_nums}
    return render_template("journal.html", meta=meta, slug=slug, is_dm=is_dm,
                           entries=entries_rendered, deltas=deltas, deleted=deleted_rendered,
                           npcs=npcs, factions=factions, locations=locations, party=party)


@player_bp.route("/<slug>/dm/journal/post", methods=["POST"])
@dm_required
def dm_post_journal(slug):
    session_n = int(request.form.get("session") or 0)
    date = request.form.get("date", "").strip() or datetime.date.today().isoformat()
    recap = request.form.get("recap", "").strip()
    if recap:
        db.post_journal(slug, session_n, date, recap)
        flash("Posted to journal", "success")
    return redirect(url_for("player.journal", slug=slug))


@player_bp.route("/<slug>/dm/journal/<int:idx>/delete", methods=["POST"])
@dm_required
def dm_delete_journal(slug, idx):
    db.delete_journal_entry(slug, idx)
    return redirect(url_for("player.journal", slug=slug))


@player_bp.route("/<slug>/dm/journal/<int:idx>/restore", methods=["POST"])
@dm_required
def dm_restore_journal(slug, idx):
    db.restore_journal_entry(slug, idx)
    flash("Entry restored", "success")
    return redirect(url_for("player.journal", slug=slug))


@player_bp.route("/<slug>/references")
def references(slug):
    r = campaign_access(slug)
    if r: return r
    meta = load(slug, "campaign.json")
    if not meta:
        abort(404)
    return render_template("references.html", slug=slug, meta=meta,
                           references=db.get_references(slug))
