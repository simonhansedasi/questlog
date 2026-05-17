from flask import Blueprint, render_template, abort, redirect, url_for, request, session, Response, jsonify, flash
from markupsafe import Markup
from pathlib import Path
from functools import wraps
import json, os, re, secrets, datetime, uuid, shutil, time, random, zipfile, io, threading
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

dm_bp = Blueprint('dm_bp', __name__)

_bg_parses: dict = {}  # slug -> threading.Thread


def _bg_parse(slug, current_session):
    try:
        meta = load(slug, "campaign.json")
        full_notes = db.get_session_notes(slug)
        cursor = db.get_notes_parse_cursor(slug)
        notes = full_notes[cursor:].strip()
        if not notes:
            db.set_proposals_status(slug, None)
            return
        npcs = db.get_npcs(slug, include_hidden=True)
        factions = db.get_factions(slug, include_hidden=True)
        locations = db.get_locations(slug, include_hidden=True)
        party = db.get_all_party_characters(slug)
        ships = db.get_assets(slug).get("ships", [])
        conditions = db.get_conditions(slug, include_hidden=True, include_resolved=False)
        causal_context = db.build_causal_context(slug, current_session)
        with ThreadPoolExecutor(max_workers=2) as pool:
            f_proposals = pool.submit(ai.propose_log_entries, notes, meta.get("name", ""),
                                      current_session, npcs, factions, party,
                                      ships=ships, conditions=conditions,
                                      causal_context=causal_context, locations=locations)
            f_relations = pool.submit(ai.suggest_relations, notes, npcs, factions)
            proposals = f_proposals.result()
            rel_suggestions = f_relations.result()
        party_names = {c["name"].lower() for c in party}
        proposals = [p for p in proposals if (p.get("entity_name") or "").lower() not in party_names]
        _party_display = meta.get("party_name") or "The Party"
        entity_names = {n["id"]: n["name"] for n in npcs}
        entity_names.update({f["id"]: f["name"] for f in factions})
        for p in proposals:
            if p.get("entity_type") in ("party_group", "party"):
                p["entity_type"] = "party_group"
                p["entity_id"] = None
                p["entity_name"] = _party_display
            if p.get("actor_id"):
                p["actor_name"] = entity_names.get(p["actor_id"], p["actor_id"])
            p["agent_source"] = True
        _already = set()
        for n in npcs:
            for r in n.get("relations", []):
                _already.add((n["id"], r.get("target", "")))
                _already.add((r.get("target", ""), n["id"]))
        for f in factions:
            for r in f.get("relations", []):
                _already.add((f["id"], r.get("target", "")))
                _already.add((r.get("target", ""), f["id"]))
        rel_suggestions = [
            s for s in rel_suggestions
            if (s.get("source_id"), s.get("target_id")) not in _already
        ]
        new_cursor = cursor + len(full_notes[cursor:])
        db.save_proposals(slug, proposals, current_session, parse_cursor=new_cursor)
        db.save_relation_suggestions(slug, rel_suggestions)
        db.set_proposals_status(slug, "ready")
    except Exception as e:
        db.set_proposals_status(slug, "error", str(e))


def _start_bg_parse(slug, current_session):
    if slug in _bg_parses and _bg_parses[slug].is_alive():
        return
    db.set_proposals_status(slug, "computing")
    t = threading.Thread(target=_bg_parse, args=(slug, current_session), daemon=True)
    _bg_parses[slug] = t
    t.start()


@dm_bp.route("/share/<token>")
def share(token):
    for d in CAMPAIGNS.iterdir():
        if not d.is_dir() or not (d / "campaign.json").exists():
            continue
        meta = json.loads((d / "campaign.json").read_text())
        if meta.get("share_token") == token:
            slug = meta["slug"]
            session[f"view_{slug}"] = True
            return redirect(url_for("player.campaign", slug=slug))
    abort(404)


# ── DM auth ───────────────────────────────────────────────────────────────────

@dm_bp.route("/<slug>/dm/login", methods=["GET", "POST"])
@login_required
@limiter.limit("10 per hour", methods=["POST"])
def dm_login(slug):
    if slug == "demo":
        abort(404)
    campaign_access(slug)
    meta = load(slug, "campaign.json")
    if not meta:
        abort(404)
    if session.get("user") == meta.get("owner"):
        session[f"dm_{slug}"] = True
        return redirect(url_for("dm_bp.dm", slug=slug))
    error = None
    if request.method == "POST":
        pin = request.form.get("pin", "").strip()
        if pin == str(meta.get("dm_pin", "")):
            session[f"dm_{slug}"] = True
            return redirect(url_for("dm_bp.dm", slug=slug))
        error = "Incorrect PIN."
    return render_template("dm/login.html", meta=meta, slug=slug, error=error)


@dm_bp.route("/<slug>/dm/logout", methods=["POST"])
def dm_logout(slug):
    session.pop(f"dm_{slug}", None)
    return redirect(url_for("player.campaign", slug=slug))


# ── DM routes ─────────────────────────────────────────────────────────────────

@dm_bp.route("/<slug>/api/revision")
def campaign_revision(slug):
    r = campaign_access(slug)
    if r: return jsonify({"error": "unauthorized"}), 403
    files = [
        CAMPAIGNS / slug / "world" / "npcs.json",
        CAMPAIGNS / slug / "world" / "factions.json",
        CAMPAIGNS / slug / "story" / "quests.json",
    ]
    rev = max((f.stat().st_mtime for f in files if f.exists()), default=0)
    return jsonify({"rev": rev})


@dm_bp.route("/<slug>/brief")
def brief(slug):
    r = campaign_access(slug)
    if r: return r
    meta = load(slug, "campaign.json")
    is_dm = bool(session.get(f"dm_{slug}"))
    current_session = db.get_current_session(slug)
    quests = db.get_quests(slug, include_hidden=is_dm) if not is_dm else []
    active_quests = [q for q in quests if q.get("status") == "active"] if not is_dm else []
    intel = db.get_dm_intelligence(slug, current_session) if is_dm else None  # brief page — no branch context needed
    saved_futures = db.get_futures(slug) if is_dm else None
    return render_template("brief.html", meta=meta, slug=slug,
                           is_dm=is_dm,
                           current_session=current_session,
                           intel=intel,
                           hot=db.get_recent_entities(slug, current_session,
                                                      include_hidden=is_dm),
                           cold=db.get_neglected_entities(slug, current_session) if is_dm else [],
                           shifts=db.get_relationship_shifts(slug, current_session,
                                                             include_hidden=is_dm),
                           active_quests=active_quests,
                           saved_futures=saved_futures)


@dm_bp.route("/<slug>/dm")
@dm_required
def dm(slug):
    meta = load(slug, "campaign.json")
    if not meta:
        abort(404)
    branches = db.get_branches(slug)
    active_branch_id = session.get(f"branch_{slug}")
    active_branch = next((b for b in branches if b["id"] == active_branch_id), None)
    raw_plan = db.get_session_plan(slug)
    plan_html = Markup(markdown.markdown(raw_plan, extensions=["nl2br"])) if raw_plan else None
    current_session = db.get_current_session(slug)
    intel = db.get_dm_intelligence(slug, current_session, active_branch=active_branch, all_branches=branches)
    saved_futures   = db.get_futures(slug)
    saved_proposals = db.get_proposals(slug)
    conditions = db.get_conditions(slug, include_hidden=True, include_resolved=False)
    for c in conditions:
        c["_severity"] = db.compute_condition_severity(c, is_dm=True)
    condition_alerts = db.get_condition_alerts(slug, is_dm=True)
    pending_projections = db.get_pending_projections(slug)
    relation_suggestions = db.get_relation_suggestions(slug)
    pending_ripples = db.get_pending_ripples(slug)
    party = db.get_party(slug)
    parties = db.get_parties(slug)
    all_party_chars = db.get_all_party_characters(slug, include_hidden=True)
    if len(parties) > 1:
        _char_group = {c["name"]: p["name"] for p in parties for c in p.get("characters", [])}
        for _c in all_party_chars:
            _c["_group_name"] = _char_group.get(_c["name"], "")
    _char_actor_npcs = db.get_npcs(slug, include_hidden=True)
    _char_actor_factions = db.get_factions(slug, include_hidden=True)
    _char_actor_locs = db.get_locations(slug, include_hidden=True)
    char_actor_logs = {}
    for _char in all_party_chars:
        _cname = _char["name"]
        _cslug = db.slugify(_cname)
        _al = []
        for _n in _char_actor_npcs:
            for _e in _n.get("log", []):
                _aid = _e.get("actor_id") or ""
                if _aid == _cname or _aid == _cslug:
                    _al.append({**_e, "_target_name": _n["name"], "_target_id": _n["id"], "_target_type": "npc"})
        for _f in _char_actor_factions:
            for _e in _f.get("log", []):
                _aid = _e.get("actor_id") or ""
                if _aid == _cname or _aid == _cslug:
                    _al.append({**_e, "_target_name": _f["name"], "_target_id": _f["id"], "_target_type": "faction"})
        for _loc in _char_actor_locs:
            for _e in _loc.get("log", []):
                _aid = _e.get("actor_id") or ""
                if _aid == _cname or _aid == _cslug:
                    _al.append({**_e, "_target_name": _loc["name"], "_target_id": _loc["id"], "_target_type": "location"})
        for _oc in all_party_chars:
            if _oc["name"] == _cname:
                continue
            for _e in _oc.get("log", []):
                _aid = _e.get("actor_id") or ""
                if _aid == _cname or _aid == _cslug:
                    _al.append({**_e, "_target_name": _oc["name"], "_target_id": db.slugify(_oc["name"]), "_target_type": "char"})
        _al.sort(key=lambda e: e.get("session", 0), reverse=True)
        char_actor_logs[_cname] = _al
    faction_actor_logs = {}
    _scan_all = (
        [(n, n["name"]) for n in db.get_npcs(slug, include_hidden=True)] +
        [(f, f["name"]) for f in db.get_factions(slug, include_hidden=True)] +
        [(loc, loc["name"]) for loc in db.get_locations(slug, include_hidden=True)] +
        [(c, c["name"]) for c in all_party_chars]
    )
    for _ent, _tname in _scan_all:
        for _e in _ent.get("log", []):
            if _e.get("actor_type") == "faction" and _e.get("actor_id"):
                faction_actor_logs.setdefault(_e["actor_id"], []).append(
                    {**_e, "_target_name": _tname})
    for _fid in faction_actor_logs:
        faction_actor_logs[_fid].sort(key=lambda e: e.get("session", 0), reverse=True)
    _party_display_name = meta.get("party_name") or "The Party"
    _multi_party = len(parties) > 1
    all_entities = (
        ([{"id": f"_party_{p['id']}" if _multi_party else "_party",
           "name": p["name"] if _multi_party else _party_display_name,
           "type": "party", "actor_only": True} for p in parties] if parties else
         [{"id": "_party", "name": _party_display_name, "type": "party", "actor_only": True}]) +
        [{"id": n["id"], "name": n["name"], "type": "npc"} for n in db.get_npcs(slug, include_hidden=True)] +
        [{"id": f["id"], "name": f["name"], "type": "faction"} for f in db.get_factions(slug, include_hidden=True)] +
        [{"id": db.slugify(c["name"]), "name": c["name"], "type": "char"} for c in all_party_chars]
    )
    all_users_data = load_users()
    members = meta.get("members", [])
    members_info = [{"username": u, "display_name": all_users_data.get(u, {}).get("display_name", u)} for u in members]
    invited_emails = meta.get("invited_emails", [])
    all_log_entries = db.get_all_log_entries(slug)
    if active_branch:
        all_log_entries = db.filter_log_for_branch(all_log_entries, active_branch, branches)
    # Sort within each session: ripples immediately follow their source event
    def _order_with_ripples(entries):
        by_session = {}
        for e in entries:
            by_session.setdefault(e.get("session", 0), []).append(e)
        result = []
        for sess in sorted(by_session.keys(), reverse=True):
            grp = by_session[sess]
            ripple_map = {}
            sources = []
            for e in grp:
                sid = (e.get("ripple_source") or {}).get("event_id")
                if sid:
                    ripple_map.setdefault(sid, []).append(e)
                else:
                    sources.append(e)
            for e in sources:
                result.append(e)
                for r in ripple_map.pop(e.get("id", ""), []):
                    result.append(r)
            for orphans in ripple_map.values():
                result.extend(orphans)
        return result

    all_log_entries = _order_with_ripples(all_log_entries)
    _evt_idx = {e["id"]: e["source"] for e in all_log_entries if e.get("id")}
    _eid_name = {ae["id"]: ae["name"] for ae in all_entities}
    for _e in all_log_entries:
        _other = None
        _rs = _e.get("ripple_source")
        if _rs and isinstance(_rs, dict) and _rs.get("event_id"):
            _other = _evt_idx.get(_rs["event_id"])
        elif _e.get("actor_id"):
            if _e.get("actor_type") == "char":
                _other = _e["actor_id"]
            else:
                _other = _eid_name.get(_e["actor_id"])
        _e["_other"] = _other
    return render_template("dm/index.html", meta=meta, slug=slug,
                           session_plan=raw_plan, plan_html=plan_html,
                           session_notes=db.get_session_notes(slug),
                           notes_parse_cursor=db.get_notes_parse_cursor(slug),
                           npcs=db.get_npcs(slug),
                           factions=db.get_factions(slug),
                           locations=db.get_locations(slug),
                           conditions=conditions,
                           party=party,
                           party_relations=meta.get("party_relations", []),
                           current_session=current_session,
                           assets=db.get_assets(slug),
                           members_info=members_info,
                           invited_emails=invited_emails,
                           intel=intel,
                           condition_alerts=condition_alerts,
                           saved_futures=saved_futures,
                           saved_proposals=saved_proposals,
                           pending_projections=pending_projections,
                           relation_suggestions=relation_suggestions,
                           pending_ripples=pending_ripples,
                           all_entities=all_entities,
                           branches=branches,
                           active_branch=active_branch,
                           all_log_entries=all_log_entries,
                           parties=parties,
                           all_party_chars=all_party_chars,
                           char_actor_logs=char_actor_logs,
                           faction_actor_logs=faction_actor_logs)


@dm_bp.route("/<slug>/dm/log/quick", methods=["POST"])
@dm_required
def dm_quick_log(slug):
    entity = request.form.get("entity", "")
    note = request.form.get("note", "").strip()
    polarity = request.form.get("polarity") or None
    intensity = int(request.form.get("intensity") or 1)
    event_type = request.form.get("event_type", "").strip() or None
    axis = request.form.get("axis") or None
    session_n = int(request.form.get("session") or 0)
    visibility = request.form.get("visibility", "public")
    actor_id = request.form.get("actor_id") or None
    actor_type = request.form.get("actor_type") or None
    actor_dm_only = bool(request.form.get("actor_dm_only"))
    location_id = request.form.get("location_id") or None
    is_ajax = bool(request.form.get("ajax"))
    active_branch_id = session.get(f"branch_{slug}") or None
    _meta_ql = load(slug, "campaign.json")
    _party_name_ql = _meta_ql.get("party_name") or "The Party"
    if ":" in entity:
        entity_type, entity_id = entity.split(":", 1)
        witnesses = request.form.getlist("witnesses")
        also_fids = request.form.getlist("also_faction_ids")
        before = {}
        if is_ajax:
            for n in db.get_npcs(slug, include_hidden=True):
                snap = db.entity_snapshot(slug, n["id"], "npc")
                if snap:
                    before[(n["id"], "npc")] = snap
            for f in db.get_factions(slug, include_hidden=True):
                snap = db.entity_snapshot(slug, f["id"], "faction")
                if snap:
                    before[(f["id"], "faction")] = snap
        if entity_type == "npc" and note:
            src_evt = db.log_npc(slug, entity_id, session_n, note, polarity=polarity,
                                 intensity=intensity, event_type=event_type, visibility=visibility,
                                 actor_id=actor_id, actor_type=actor_type,
                                 actor_dm_only=actor_dm_only, branch=active_branch_id, axis=axis,
                                 location_id=location_id)
            for fid in also_fids:
                if fid:
                    _also_ripple = {"entity_id": entity_id, "entity_type": "npc", "event_id": src_evt}
                    db.log_faction(slug, fid, session_n, note,
                                   polarity=polarity, intensity=intensity,
                                   event_type=event_type, visibility=visibility,
                                   ripple_source=_also_ripple,
                                   branch=active_branch_id)
            if polarity:
                db.apply_ripple(slug, entity_id, "npc", session_n, note, polarity, intensity,
                                event_type, visibility=visibility, source_event_id=src_evt,
                                branch=active_branch_id,
                                actor_id=actor_id, actor_type=actor_type)
            if src_evt:
                for w in witnesses:
                    db.reveal_event(slug, src_evt, w)
            for char_name, cond in db.get_conditions_for_npc(slug, entity_id):
                flash(f"⚔ {char_name} — {cond['name']}", "condition_alert")
            if not is_ajax:
                flash("Logged", "success")
        elif entity_type == "faction" and note:
            src_evt = db.log_faction(slug, entity_id, session_n, note, polarity=polarity,
                                     intensity=intensity, event_type=event_type, visibility=visibility,
                                     actor_id=actor_id, actor_type=actor_type,
                                     actor_dm_only=actor_dm_only, branch=active_branch_id,
                                     location_id=location_id)
            if polarity:
                db.apply_ripple(slug, entity_id, "faction", session_n, note, polarity, intensity,
                                event_type, visibility=visibility, source_event_id=src_evt,
                                branch=active_branch_id,
                                actor_id=actor_id, actor_type=actor_type)
            if src_evt:
                for w in witnesses:
                    db.reveal_event(slug, src_evt, w)
            for char_name, cond in db.get_conditions_for_faction(slug, entity_id):
                flash(f"⚔ {char_name} — {cond['name']}", "condition_alert")
            if not is_ajax:
                flash("Logged", "success")
        elif entity_type == "condition" and note:
            src_evt = db.log_condition(slug, entity_id, session_n, note, polarity=polarity,
                                       intensity=intensity, event_type=event_type, visibility=visibility,
                                       location_id=location_id)
            if polarity:
                db.apply_ripple(slug, entity_id, "condition", session_n, note, polarity, intensity,
                                event_type, visibility=visibility, source_event_id=src_evt)
            if not is_ajax:
                flash("Logged", "success")
        elif entity_type == "party" and note:
            db.log_character(slug, entity_id, session_n, note, polarity=polarity,
                             intensity=intensity, event_type=event_type, visibility=visibility,
                             actor_id=actor_id, actor_type=actor_type, actor_dm_only=actor_dm_only,
                             location_id=location_id)
            if not is_ajax:
                flash("Logged", "success")
        elif entity_type == "party_group" and note:
            if entity_id and entity_id != "_party":
                _ql_parties = db.get_parties(slug)
                _ql_pg = next((p for p in _ql_parties if p["id"] == entity_id), None)
                _ql_pname = _ql_pg["name"] if _ql_pg else _party_name_ql
            else:
                _ql_pname = _party_name_ql
            db.log_party_group(slug, session_n, note, polarity=polarity,
                               intensity=intensity, event_type=event_type, visibility=visibility,
                               actor_id=actor_id, actor_type=actor_type, actor_dm_only=actor_dm_only,
                               location_id=location_id, party_name=_ql_pname)
            if not is_ajax:
                flash("Logged", "success")
        elif entity_type == "location" and note:
            db.log_location(slug, entity_id, session_n, note, visibility=visibility,
                            polarity=polarity, intensity=intensity, event_type=event_type)
            if not is_ajax:
                flash("Logged", "success")
        if is_ajax:
            return jsonify({"ok": True, "diffs": _build_diffs(slug, before, [])})
    return redirect(url_for("dm_bp.dm", slug=slug))


@dm_bp.route("/<slug>/dm/session/plan", methods=["POST"])
@dm_required
def dm_set_session_plan(slug):
    db.set_session_plan(slug, request.form.get("plan", ""))
    flash("Plan saved", "success")
    return redirect(url_for("dm_bp.dm", slug=slug))


@dm_bp.route("/<slug>/dm/session/brief", methods=["POST"])
@dm_required
def dm_generate_brief(slug):
    brief = db.generate_session_brief(slug)
    return jsonify({"brief": brief})


@dm_bp.route("/<slug>/dm/entity/<entity_type>/<entity_id>/panel")
@dm_required
def dm_entity_panel(slug, entity_type, entity_id):
    current_session = db.get_current_session(slug)
    all_npcs = db.get_npcs(slug, include_hidden=True)
    all_factions = db.get_factions(slug, include_hidden=True)
    npc_names = {n["id"]: n["name"] for n in all_npcs}
    faction_names = {f["id"]: f["name"] for f in all_factions}
    if entity_type == "party":
        meta = load(slug, "campaign.json")
        raw_rels = meta.get("party_relations", [])
        relations = []
        for i, rel in enumerate(raw_rels):
            tid = rel.get("target", "")
            ttype = rel.get("target_type", "faction")
            name = (npc_names if ttype == "npc" else faction_names).get(tid, tid)
            relations.append({"idx": i, "target_id": tid, "target_type": ttype,
                              "target_name": name, "relation": rel["relation"],
                              "weight": rel.get("weight", 0.5)})
        return jsonify({
            "name": meta.get("party_name") or "Party",
            "entity_type": "party", "entity_id": "_party",
            "session": current_session, "entries": [], "relations": relations,
        })
    if entity_type == "character":
        char = next((c for c in db.get_all_party_characters(slug) if c["name"] == entity_id), None)
        if not char:
            return jsonify({"error": "Not found"}), 404
        relations = []
        for rel in char.get("relations", []):
            tid = rel.get("target", "")
            ttype = rel.get("target_type", "npc")
            name = (npc_names if ttype == "npc" else faction_names).get(tid, tid)
            relations.append({"idx": tid, "target_id": tid, "target_type": ttype,
                              "target_name": name, "relation": rel["relation"],
                              "weight": rel.get("weight", 0.5)})
        return jsonify({
            "name": char["name"], "entity_type": "character", "entity_id": entity_id,
            "session": current_session, "entries": [], "relations": relations,
        })
    if entity_type == "npc":
        entity = next((n for n in all_npcs if n["id"] == entity_id), None)
    else:
        entity = next((f for f in all_factions if f["id"] == entity_id), None)
    if not entity:
        return jsonify({"error": "Not found"}), 404
    log = entity.get("log", [])
    recent = list(reversed(log[-3:] if len(log) >= 3 else log[:]))
    relations = []
    for i, rel in enumerate(entity.get("relations", [])):
        tid = rel.get("target", "")
        ttype = rel.get("target_type", "npc")
        name = (npc_names if ttype == "npc" else faction_names).get(tid, tid)
        relations.append({"idx": i, "target_id": tid, "target_type": ttype,
                          "target_name": name, "relation": rel["relation"],
                          "weight": rel.get("weight", 0.5)})
    char_relations = []
    if entity_type == "npc":
        for char in db.get_all_party_characters(slug):
            for rel in char.get("relations", []):
                if rel.get("target") == entity_id:
                    char_relations.append({"char_name": char["name"],
                                           "relation": rel["relation"],
                                           "weight": rel.get("weight", 0.5)})
    return jsonify({
        "name": entity["name"],
        "entity_type": entity_type,
        "entity_id": entity_id,
        "session": current_session,
        "entries": recent,
        "relations": relations,
        "char_relations": char_relations,
    })


@dm_bp.route("/<slug>/dm/session/notes", methods=["POST"])
@dm_required
def dm_set_session_notes(slug):
    new_notes = request.form.get("notes", "")
    db.set_session_notes(slug, new_notes)
    cursor = db.get_notes_parse_cursor(slug)
    if len(new_notes) < cursor:
        db.set_notes_parse_cursor(slug, len(new_notes))
    if request.form.get("ajax"):
        users = load_users()
        user_data = users.get(session.get("user", ""), {})
        if user_data.get("ai_enabled") or user_data.get("admin"):
            session_override = request.form.get("session_override")
            current_session = int(session_override) if session_override else db.get_current_session(slug)
            _start_bg_parse(slug, current_session)
        return jsonify({"ok": True})
    flash("Notes saved", "success")
    return redirect(url_for("dm_bp.dm", slug=slug))


@dm_bp.route("/<slug>/dm/session/proposals", methods=["GET"])
@dm_required
def dm_get_proposals(slug):
    status_data = db.get_proposals_status(slug)
    status = status_data["status"]
    if status == "ready":
        saved = db.get_proposals(slug)
        rel_suggestions = db.get_relation_suggestions(slug) or []
        return jsonify({"status": "ready", "proposals": saved["proposals"],
                        "session": saved["session"], "rel_suggestions": rel_suggestions})
    elif status == "computing":
        # Stale "computing" after a gunicorn restart — no live thread, reset
        if slug not in _bg_parses or not _bg_parses[slug].is_alive():
            db.set_proposals_status(slug, None)
            return jsonify({"status": "none"})
        return jsonify({"status": "computing"})
    elif status == "error":
        return jsonify({"status": "error", "error": status_data["error"]}), 500
    return jsonify({"status": "none"})


@dm_bp.route("/<slug>/dm/session/reset_parse_cursor", methods=["POST"])
@dm_required
def dm_reset_parse_cursor(slug):
    db.reset_notes_parse_cursor(slug)
    return ("", 204)


@dm_bp.route("/<slug>/dm/session/recap", methods=["POST"])
@dm_required
@ai_required
@limiter.limit("30 per hour")
def dm_generate_recap(slug):
    meta = load(slug, "campaign.json")
    notes = db.get_session_notes(slug)
    current_session = db.get_current_session(slug)
    all_entries = db.get_all_log_entries(slug)
    session_entries = [
        e for e in all_entries
        if e.get("session") == current_session
        and e.get("visibility", "public") != "dm_only"
        and not e.get("dm_only")
    ]
    if (not notes or not notes.strip()) and not session_entries:
        return jsonify({"error": "No session notes or logged events to summarize."}), 400
    quests = db.get_quests(slug, include_hidden=True)
    npcs = db.get_npcs(slug, include_hidden=False)
    try:
        recap = ai.generate_recap(notes, meta.get("name", ""), quests, npcs,
                                  log_entries=session_entries, session_n=current_session)
        recap_html = Markup(markdown.markdown(recap, extensions=["nl2br"]))
        return jsonify({"recap": recap, "recap_html": str(recap_html)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@dm_bp.route("/<slug>/dm/session/propose", methods=["POST"])
@dm_required
@ai_required
@limiter.limit("30 per hour")
def dm_propose_entries(slug):
    meta = load(slug, "campaign.json")
    full_notes = db.get_session_notes(slug)
    cursor = db.get_notes_parse_cursor(slug)
    notes = full_notes[cursor:].strip()
    if not notes:
        return jsonify({"error": "No new notes to parse since last commit. Keep writing and try again."}), 400
    session_override = request.form.get("session_override")
    current_session = int(session_override) if session_override else db.get_current_session(slug)
    npcs = db.get_npcs(slug, include_hidden=True)
    factions = db.get_factions(slug, include_hidden=True)
    locations = db.get_locations(slug, include_hidden=True)
    party = db.get_all_party_characters(slug)
    ships = db.get_assets(slug).get("ships", [])
    conditions = db.get_conditions(slug, include_hidden=True, include_resolved=False)
    causal_context = db.build_causal_context(slug, current_session)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            f_proposals = pool.submit(ai.propose_log_entries, notes, meta.get("name", ""),
                                      current_session, npcs, factions, party,
                                      ships=ships, conditions=conditions,
                                      causal_context=causal_context, locations=locations)
            f_relations = pool.submit(ai.suggest_relations, notes, npcs, factions)
            proposals = f_proposals.result()
            rel_suggestions = f_relations.result()
        party_names = {c["name"].lower() for c in party}
        proposals = [p for p in proposals if (p.get("entity_name") or "").lower() not in party_names]
        # Normalize party_group proposals and resolve actor names for display
        _party_display = meta.get("party_name") or "The Party"
        entity_names = {n["id"]: n["name"] for n in npcs}
        entity_names.update({f["id"]: f["name"] for f in factions})
        for p in proposals:
            if p.get("entity_type") in ("party_group", "party"):
                p["entity_type"] = "party_group"
                p["entity_id"] = None
                p["entity_name"] = _party_display
            if p.get("actor_id"):
                p["actor_name"] = entity_names.get(p["actor_id"], p["actor_id"])
        # Strip AI suggestions for edges that already exist in the graph (LLMs sometimes ignore the existing list)
        _already = set()
        for n in npcs:
            for r in n.get("relations", []):
                _already.add((n["id"], r.get("target", "")))
                _already.add((r.get("target", ""), n["id"]))
        for f in factions:
            for r in f.get("relations", []):
                _already.add((f["id"], r.get("target", "")))
                _already.add((r.get("target", ""), f["id"]))
        rel_suggestions = [
            s for s in rel_suggestions
            if (s.get("source_id"), s.get("target_id")) not in _already
        ]
        new_cursor = cursor + len(full_notes[cursor:])
        db.save_proposals(slug, proposals, current_session, parse_cursor=new_cursor)
        db.save_relation_suggestions(slug, rel_suggestions)
        return jsonify({"proposals": proposals, "session": current_session,
                        "relation_suggestions": rel_suggestions})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@dm_bp.route("/<slug>/dm/relation_suggestion/accept", methods=["POST"])
@dm_required
def dm_accept_relation_suggestion(slug):
    data = request.get_json()
    source_id   = data.get("source_id")
    source_type = data.get("source_type", "npc")
    target_id   = data.get("target_id")
    target_type = data.get("target_type", "npc")
    relation    = data.get("relation", "ally")
    weight      = float(data.get("weight", 0.5))
    # char node IDs in the graph are _char_<slug>, not the raw name
    if target_type == "char":
        target_id = f"_char_{db.slugify(target_id)}"
    if source_type == "char":
        source_id = f"_char_{db.slugify(source_id)}"
    if source_type == "npc":
        db.add_npc_relation(slug, source_id, target_id, target_type, relation, weight)
    elif source_type == "char":
        db.add_character_relation(slug, source_id, target_id, target_type, relation, weight)
    else:
        db.add_faction_relation(slug, source_id, target_id, target_type, relation, weight)
    backfilled = db.backfill_relation_ripples(slug, source_id, source_type,
                                              target_id, target_type, relation, weight)
    db.dismiss_relation_suggestion(slug, source_id, target_id)
    return jsonify({"ok": True, "backfilled": backfilled})


@dm_bp.route("/<slug>/dm/relation_suggestion/dismiss", methods=["POST"])
@dm_required
def dm_dismiss_relation_suggestion(slug):
    data = request.get_json()
    db.dismiss_relation_suggestion(slug, data.get("source_id"), data.get("target_id"))
    return jsonify({"ok": True})


def _resolve_faction(slug, faction_name, faction_by_name, created):
    """Return faction id for faction_name, creating the faction if it doesn't exist."""
    if not faction_name:
        return ""
    name_lower = faction_name.strip().lower()
    if name_lower in faction_by_name:
        return faction_by_name[name_lower]
    new_id = db.slugify(faction_name.strip())
    db.add_faction(slug, faction_name.strip(), "neutral", description="", hidden=True)
    faction_by_name[name_lower] = new_id
    created.append({"name": faction_name.strip(), "type": "faction", "id": new_id})
    return new_id


@dm_bp.route("/<slug>/dm/session/commit_proposals", methods=["POST"])
@dm_required
@limiter.limit("30 per hour")
def dm_commit_proposals(slug):
    data = request.get_json()
    if not data or "entries" not in data:
        return jsonify({"error": "No entries"}), 400
    saved_proposals = db.get_proposals(slug)
    pending_cursor = saved_proposals.get("parse_cursor")
    current_session = saved_proposals.get("session") or db.get_current_session(slug)
    db.clear_proposals(slug)
    active_branch_id = session.get(f"branch_{slug}") or None

    meta = load(slug, "campaign.json")
    _party_name_cp = meta.get("party_name") or "The Party"
    npc_by_name = {n["name"].lower(): n["id"] for n in db.get_npcs(slug, include_hidden=True)}
    faction_by_name = {f["name"].lower(): f["id"] for f in db.get_factions(slug, include_hidden=True)}
    condition_by_name = {c["name"].lower(): c["id"] for c in db.get_conditions(slug, include_hidden=True, include_resolved=True)}
    location_by_name = {loc["name"].lower(): loc["id"] for loc in db.get_locations(slug, include_hidden=True)}
    char_by_name = {c["name"].lower(): c["name"] for c in db.get_all_party_characters(slug, include_hidden=True)}

    committed = 0
    created = []
    logged_entity_ids = set()

    # Pre-pass: create all new NPC/faction entities first so actor references resolve correctly
    for entry in data["entries"]:
        etype = entry.get("entity_type", "npc")
        if etype in ("ship", "condition", "location", "party", "party_group", "char"):
            continue
        # Don't trust entity_id from AI for existence — check by name only
        if entry.get("entity_id") and (
            entry["entity_id"] in npc_by_name.values() or
            entry["entity_id"] in faction_by_name.values()
        ):
            continue
        name = (entry.get("entity_name") or "").strip()
        if not name:
            continue
        name_lower = name.lower()
        entity_hidden = bool(entry.get("entity_hidden", False))
        if etype == "faction":
            if name_lower not in faction_by_name:
                rel = "friendly" if entry.get("polarity") == "positive" else "hostile" if entry.get("polarity") == "negative" else "neutral"
                db.add_faction(slug, name, rel, description="", hidden=entity_hidden)
                faction_by_name[name_lower] = db.slugify(name)
                created.append({"name": name, "type": "faction", "id": db.slugify(name)})
        else:
            if name_lower not in npc_by_name and name_lower not in faction_by_name:
                rel = "friendly" if entry.get("polarity") == "positive" else "hostile" if entry.get("polarity") == "negative" else "neutral"
                faction_ref = _resolve_faction(slug, entry.get("faction_name"), faction_by_name, created)
                db.add_npc(slug, name, role="", relationship=rel, description="", hidden=entity_hidden,
                           factions=[faction_ref] if faction_ref else [])
                npc_by_name[name_lower] = db.slugify(name)
                created.append({"name": name, "type": "npc", "id": db.slugify(name)})

    for entry in data["entries"]:
        entity_id = entry.get("entity_id")
        entity_type = entry.get("entity_type", "npc")
        if entity_type in ("char", "party"):
            continue
        note = entry.get("note", "").strip()
        if not note:
            continue

        if entity_type == "ship":
            ship_name = (entry.get("entity_name") or "").strip()
            event_type = entry.get("event_type") or None
            visibility = entry.get("visibility", "public")
            session_n = int(entry.get("session") or current_session)
            if ship_name and db.log_ship(slug, ship_name, session_n, note, event_type=event_type, visibility=visibility):
                committed += 1
            continue

        if entity_type == "condition":
            if not entity_id:
                name = (entry.get("entity_name") or "").strip()
                if not name:
                    continue
                entity_id = condition_by_name.get(name.lower())
                if not entity_id:
                    meta_c = entry.get("condition_meta") or {}
                    entity_id = db.slugify(name)
                    db.add_condition(slug, name,
                                     region=meta_c.get("region", ""),
                                     effect_type=meta_c.get("effect_type", "custom"),
                                     effect_scope=meta_c.get("effect_scope", ""),
                                     magnitude=meta_c.get("magnitude", ""),
                                     hidden=False)
                    condition_by_name[name.lower()] = entity_id
                    created.append({"name": name, "type": "condition", "id": entity_id})
            polarity = entry.get("polarity") or None
            intensity = int(entry.get("intensity") or 1)
            event_type = entry.get("event_type") or None
            visibility = entry.get("visibility", "public")
            session_n = int(entry.get("session") or current_session)
            src_evt = db.log_condition(slug, entity_id, session_n, note, polarity=polarity,
                                       intensity=intensity, event_type=event_type, visibility=visibility)
            if polarity:
                db.apply_ripple(slug, entity_id, "condition", session_n, note, polarity, intensity,
                                event_type, visibility=visibility, source_event_id=src_evt)
            committed += 1
            continue

        if entity_type == "location":
            if not entity_id:
                name = (entry.get("entity_name") or "").strip()
                entity_id = location_by_name.get(name.lower()) if name else None
            if not entity_id:
                continue
            polarity = entry.get("polarity") or None
            intensity = int(entry.get("intensity") or 1)
            event_type = entry.get("event_type") or None
            visibility = entry.get("visibility", "public")
            session_n = int(entry.get("session") or current_session)
            db.log_location(slug, entity_id, session_n, note, polarity=polarity,
                            intensity=intensity, event_type=event_type, visibility=visibility)
            committed += 1
            continue

        # If AI gave an entity_id that doesn't exist, discard it and fall back to name lookup
        if entity_id and entity_type not in ("party_group", "ship", "condition", "location"):
            if entity_id not in npc_by_name.values() and entity_id not in faction_by_name.values():
                entity_id = None

        if not entity_id and entity_type not in ("party_group",):
            name = (entry.get("entity_name") or "").strip()
            if not name:
                continue
            name_lower = name.lower()
            if entity_type == "faction":
                entity_id = faction_by_name.get(name_lower) or npc_by_name.get(name_lower)
            else:
                entity_id = npc_by_name.get(name_lower) or faction_by_name.get(name_lower)

            if not entity_id:
                # Don't create ghost NPCs for known party characters
                if entity_type != "faction" and char_by_name.get(name_lower):
                    char_canon = char_by_name[name_lower]
                    _session_n = int(entry.get("session") or current_session)
                    _polarity = entry.get("polarity") or None
                    _intensity = int(entry.get("intensity") or 1)
                    _event_type = entry.get("event_type") or None
                    _visibility = entry.get("visibility", "public")
                    _actor_id = entry.get("actor_id") or None
                    _actor_type = entry.get("actor_type") or None
                    if _actor_id and _actor_id.startswith("__proposed__:"):
                        _pname = _actor_id[13:].lower()
                        _actor_id = npc_by_name.get(_pname) or faction_by_name.get(_pname) or None
                    db.log_character(slug, char_canon, _session_n, note, polarity=_polarity, intensity=_intensity,
                                     event_type=_event_type, visibility=_visibility, actor_id=_actor_id, actor_type=_actor_type)
                    committed += 1
                    continue
                polarity_hint = entry.get("polarity") or ""
                rel = "friendly" if polarity_hint == "positive" else "hostile" if polarity_hint == "negative" else "neutral"
                new_id = db.slugify(name)
                if entity_type == "faction":
                    db.add_faction(slug, name, rel, description="", hidden=True)
                    faction_by_name[name_lower] = new_id
                else:
                    faction_ref = _resolve_faction(slug, entry.get("faction_name"), faction_by_name, created)
                    db.add_npc(slug, name, role="", relationship=rel, description="", hidden=True,
                               factions=[faction_ref] if faction_ref else [])
                    npc_by_name[name_lower] = new_id
                entity_id = new_id
                created.append({"name": name, "type": entity_type, "id": new_id})

        if entity_type == "npc" and entry.get("faction_name"):
            faction_ref = _resolve_faction(slug, entry.get("faction_name"), faction_by_name, created)
            if faction_ref:
                npcs_current = db.get_npcs(slug, include_hidden=True)
                npc_obj = next((n for n in npcs_current if n["id"] == entity_id), None)
                if npc_obj and faction_ref not in npc_obj.get("factions", []):
                    db.update_npc(slug, entity_id, factions=npc_obj.get("factions", []) + [faction_ref])

        polarity = entry.get("polarity") or None
        intensity = int(entry.get("intensity") or 1)
        event_type = entry.get("event_type") or None
        visibility = entry.get("visibility", "public")
        session_n = int(entry.get("session") or current_session)
        discrete = bool(entry.get("discrete"))
        actor_id = entry.get("actor_id") or None
        actor_type = entry.get("actor_type") or None
        actor_dm_only = bool(entry.get("actor_dm_only"))
        location_id = entry.get("location_id") or None
        if actor_id and actor_id.startswith("__proposed__:"):
            proposed_name = actor_id[13:].lower()
            actor_id = npc_by_name.get(proposed_name) or faction_by_name.get(proposed_name) or None
        axis = entry.get("axis") or None
        if discrete:
            visibility = "dm_only"
        if entity_type in ("party", "party_group") or entity_id == "_party":
            src_evt = db.log_party_group(slug, session_n, note, polarity=polarity,
                                         intensity=intensity, event_type=event_type, visibility=visibility,
                                         actor_id=actor_id, actor_type=actor_type,
                                         location_id=location_id, party_name=_party_name_cp)
        elif entity_type == "faction" or entity_id in faction_by_name.values():
            src_evt = db.log_faction(slug, entity_id, session_n, note, polarity=polarity,
                                     intensity=intensity, event_type=event_type, visibility=visibility,
                                     actor_id=actor_id, actor_type=actor_type, actor_dm_only=actor_dm_only,
                                     branch=active_branch_id, axis=axis, location_id=location_id)
        else:
            src_evt = db.log_npc(slug, entity_id, session_n, note, polarity=polarity,
                                 intensity=intensity, event_type=event_type, visibility=visibility,
                                 actor_id=actor_id, actor_type=actor_type, actor_dm_only=actor_dm_only,
                                 branch=active_branch_id, axis=axis, location_id=location_id)
        if polarity:
            if discrete:
                entity_name = (entry.get("entity_name") or "").strip() or entity_id
                db.add_pending_ripple(slug, entity_id, entity_type, entity_name,
                                      src_evt, session_n, note, polarity, intensity,
                                      event_type, visibility)
            else:
                db.apply_ripple(slug, entity_id, entity_type, session_n, note, polarity, intensity,
                                event_type, visibility=visibility, source_event_id=src_evt,
                                branch=active_branch_id,
                                actor_id=actor_id, actor_type=actor_type)
        if src_evt:
            for w in (entry.get("witnesses") or []):
                db.reveal_event(slug, src_evt, w)
        logged_entity_ids.add(entity_id)
        committed += 1

    if pending_cursor is not None:
        current_notes = db.get_session_notes(slug)
        if pending_cursor <= len(current_notes):
            db.set_notes_parse_cursor(slug, pending_cursor)
        else:
            db.reset_notes_parse_cursor(slug)

    cond_alerts = [
        {"char_name": a["char_name"], "condition_name": a["condition"]["name"],
         "entity_name": a["entity_name"]}
        for a in db.get_condition_alerts_for_entities(slug, logged_entity_ids)
    ]
    return jsonify({"committed": committed, "created": created, "condition_alerts": cond_alerts})


@dm_bp.route("/<slug>/dm/import/session/propose", methods=["POST"])
@dm_required
@limiter.limit("300 per hour")
def dm_import_session_propose(slug):
    meta = load(slug, "campaign.json")
    data = request.get_json()
    session_n = int(data.get("session_n", 1))
    notes = data.get("notes", "").strip()[:10_000]
    if not notes:
        return jsonify({"proposals": [], "session_n": session_n})

    npcs = db.get_npcs(slug, include_hidden=True)
    factions = db.get_factions(slug, include_hidden=True)
    party = db.get_all_party_characters(slug)
    causal_context = db.build_causal_context(slug, session_n)

    try:
        proposals = ai.propose_log_entries(
            notes, meta.get("name", ""), session_n,
            npcs, factions, party=party,
            causal_context=causal_context
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    for p in proposals:
        p["session"] = session_n

    return jsonify({"proposals": proposals, "session_n": session_n})


@dm_bp.route("/<slug>/dm/import/session/commit", methods=["POST"])
@dm_required
@limiter.limit("30 per hour")
def dm_import_session_commit(slug):
    data = request.get_json()
    if not data or "entries" not in data:
        return jsonify({"error": "No entries"}), 400

    current_session = db.get_current_session(slug)
    active_branch_id = session.get(f"branch_{slug}") or None

    npc_by_name = {n["name"].lower(): n["id"] for n in db.get_npcs(slug, include_hidden=True)}
    faction_by_name = {f["name"].lower(): f["id"] for f in db.get_factions(slug, include_hidden=True)}
    condition_by_name = {c["name"].lower(): c["id"] for c in db.get_conditions(slug, include_hidden=True, include_resolved=True)}
    party_names = {c["name"].lower() for c in db.get_all_party_characters(slug)}

    committed = 0
    created = []

    # Pre-pass: create new NPC/faction entities first so actor references resolve
    for entry in data["entries"]:
        if (entry.get("entity_name") or "").strip().lower() in party_names:
            continue
        etype = entry.get("entity_type", "npc")
        if entry.get("entity_id") or etype in ("ship", "condition", "location", "party", "party_group"):
            continue
        name = (entry.get("entity_name") or "").strip()
        if not name:
            continue
        name_lower = name.lower()
        if etype == "faction":
            if name_lower not in faction_by_name:
                rel = "friendly" if entry.get("polarity") == "positive" else "hostile" if entry.get("polarity") == "negative" else "neutral"
                db.add_faction(slug, name, rel, description="", hidden=True)
                faction_by_name[name_lower] = db.slugify(name)
                created.append({"name": name, "type": "faction", "id": db.slugify(name)})
        else:
            if name_lower not in npc_by_name and name_lower not in faction_by_name:
                rel = "friendly" if entry.get("polarity") == "positive" else "hostile" if entry.get("polarity") == "negative" else "neutral"
                faction_ref = _resolve_faction(slug, entry.get("faction_name"), faction_by_name, created)
                db.add_npc(slug, name, role="", relationship=rel, description="", hidden=True,
                           factions=[faction_ref] if faction_ref else [])
                npc_by_name[name_lower] = db.slugify(name)
                created.append({"name": name, "type": "npc", "id": db.slugify(name)})

    for entry in data["entries"]:
        if (entry.get("entity_name") or "").strip().lower() in party_names:
            continue
        entity_id = entry.get("entity_id")
        entity_type = entry.get("entity_type", "npc")
        note = entry.get("note", "").strip()[:500]
        if not note:
            continue

        if entity_type == "ship":
            ship_name = (entry.get("entity_name") or "").strip()
            session_n = int(entry.get("session") or current_session)
            if ship_name and db.log_ship(slug, ship_name, session_n, note,
                                         event_type=entry.get("event_type"),
                                         visibility=entry.get("visibility", "public")):
                committed += 1
            continue

        if entity_type == "condition":
            if not entity_id:
                name = (entry.get("entity_name") or "").strip()
                if not name:
                    continue
                entity_id = condition_by_name.get(name.lower())
                if not entity_id:
                    meta_c = entry.get("condition_meta") or {}
                    entity_id = db.slugify(name)
                    db.add_condition(slug, name, region=meta_c.get("region", ""),
                                     effect_type=meta_c.get("effect_type", "custom"),
                                     effect_scope=meta_c.get("effect_scope", ""),
                                     magnitude=meta_c.get("magnitude", ""), hidden=False)
                    condition_by_name[name.lower()] = entity_id
                    created.append({"name": name, "type": "condition", "id": entity_id})
            polarity = entry.get("polarity") or None
            intensity = int(entry.get("intensity") or 1)
            session_n = int(entry.get("session") or current_session)
            src_evt = db.log_condition(slug, entity_id, session_n, note, polarity=polarity,
                                       intensity=intensity, event_type=entry.get("event_type"),
                                       visibility=entry.get("visibility", "public"))
            if polarity:
                db.apply_ripple(slug, entity_id, "condition", session_n, note, polarity, intensity,
                                entry.get("event_type"), visibility=entry.get("visibility", "public"),
                                source_event_id=src_evt)
            committed += 1
            continue

        if not entity_id:
            name = (entry.get("entity_name") or "").strip()
            if not name:
                continue
            name_lower = name.lower()
            if entity_type == "faction":
                entity_id = faction_by_name.get(name_lower) or npc_by_name.get(name_lower)
            else:
                entity_id = npc_by_name.get(name_lower) or faction_by_name.get(name_lower)
            if not entity_id:
                rel = "friendly" if entry.get("polarity") == "positive" else "hostile" if entry.get("polarity") == "negative" else "neutral"
                entity_id = db.slugify(name)
                if entity_type == "faction":
                    db.add_faction(slug, name, rel, description="", hidden=True)
                    faction_by_name[name_lower] = entity_id
                else:
                    faction_ref = _resolve_faction(slug, entry.get("faction_name"), faction_by_name, created)
                    db.add_npc(slug, name, role="", relationship=rel, description="", hidden=True,
                               factions=[faction_ref] if faction_ref else [])
                    npc_by_name[name_lower] = entity_id
                created.append({"name": name, "type": entity_type, "id": entity_id})

        polarity = entry.get("polarity") or None
        intensity = int(entry.get("intensity") or 1)
        event_type = entry.get("event_type") or None
        visibility = entry.get("visibility", "public")
        session_n = int(entry.get("session") or current_session)
        actor_id = entry.get("actor_id") or None
        actor_type = entry.get("actor_type") or None

        if entity_type == "faction" or entity_id in faction_by_name.values():
            src_evt = db.log_faction(slug, entity_id, session_n, note, polarity=polarity,
                                     intensity=intensity, event_type=event_type, visibility=visibility,
                                     actor_id=actor_id, actor_type=actor_type,
                                     branch=active_branch_id)
        else:
            src_evt = db.log_npc(slug, entity_id, session_n, note, polarity=polarity,
                                 intensity=intensity, event_type=event_type, visibility=visibility,
                                 actor_id=actor_id, actor_type=actor_type,
                                 branch=active_branch_id)
        if polarity:
            db.apply_ripple(slug, entity_id, entity_type, session_n, note, polarity, intensity,
                            event_type, visibility=visibility, source_event_id=src_evt)
        committed += 1

    return jsonify({"committed": committed, "created": created})


@dm_bp.route("/<slug>/dm/ripple/<ripple_id>/reveal", methods=["POST"])
@dm_required
def dm_reveal_ripple(slug, ripple_id):
    pending = db.get_pending_ripples(slug)
    ripple = next((r for r in pending if r["id"] == ripple_id), None)
    if not ripple:
        return jsonify({"error": "Not found"}), 404
    data = request.get_json() or {}
    raw_depth = data.get("depth")
    # depth=None → full BFS; depth=-1 → witnesses only (no graph traversal); depth=N → N hops
    if raw_depth is None:
        depth = None
    elif int(raw_depth) == -1:
        depth = 0   # depth=0 means: don't enter any frontier, only fire extras
    else:
        depth = int(raw_depth)
    extra_entities = data.get("extra_entities", [])
    rippled = db.apply_ripple_scoped(
        slug,
        ripple["source_entity_id"], ripple["source_entity_type"],
        ripple["session_n"], ripple["note"],
        ripple["polarity"], ripple["intensity"],
        event_type=ripple.get("event_type"),
        visibility=ripple.get("visibility", "dm_only"),
        source_event_id=ripple.get("source_event_id"),
        depth=depth,
        extra_entities=extra_entities,
    )
    db.resolve_pending_ripple(slug, ripple_id)
    return jsonify({"rippled": len(rippled), "targets": rippled})


@dm_bp.route("/<slug>/dm/ripple/<ripple_id>/dismiss", methods=["POST"])
@dm_required
def dm_dismiss_ripple(slug, ripple_id):
    db.resolve_pending_ripple(slug, ripple_id)
    return jsonify({"ok": True})


@dm_bp.route("/<slug>/dm/session/notes/export")
@dm_required
def dm_export_notes(slug):
    notes = db.get_session_notes(slug)
    return Response(
        notes,
        mimetype="text/markdown",
        headers={"Content-Disposition": f"attachment; filename={slug}_session_notes.md"}
    )


@dm_bp.route("/<slug>/dm/export")
@dm_required
def dm_export_campaign(slug):
    campaign_dir = CAMPAIGNS / slug
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(campaign_dir.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(campaign_dir))
    buf.seek(0)
    return Response(
        buf.read(),
        mimetype="application/zip",
        headers={"Content-Disposition": f"attachment; filename={slug}_campaign.zip"}
    )


_SESSION_SPLIT_RE = re.compile(
    r'^\s*(?:#+\s*)?(?:\[)?[Ss]ession\s+(\d+)(?:\])?\s*(?:[:\-—].*)?$',
    re.MULTILINE
)

def _split_sessions(text):
    """Split text on Session N markers. Returns list of {n, text} dicts."""
    matches = list(_SESSION_SPLIT_RE.finditer(text))
    if not matches:
        return [{"n": 1, "text": text.strip()}]
    sessions = []
    for i, m in enumerate(matches):
        n = int(m.group(1))
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        if body:
            sessions.append({"n": n, "text": body})
    return sessions


@dm_bp.route("/<slug>/dm/import", methods=["GET"])
@dm_required
def dm_import(slug):
    meta = load(slug, "campaign.json")
    return render_template("dm/import.html", meta=meta, slug=slug)


@dm_bp.route("/<slug>/dm/import/preview", methods=["POST"])
@dm_required
def dm_import_preview(slug):
    f = request.files.get("notes_file")
    if not f:
        return jsonify({"error": "No file"}), 400
    raw = f.read(500_000).decode("utf-8", errors="replace")
    sessions = _split_sessions(raw)
    return jsonify({"sessions": [
        {"n": s["n"], "preview": s["text"][:200], "chars": len(s["text"])}
        for s in sessions
    ], "full": sessions})


@dm_bp.route("/<slug>/dm/import/session", methods=["POST"])
@dm_required
@limiter.limit("300 per hour")
def dm_import_session(slug):
    meta = load(slug, "campaign.json")
    data = request.get_json()
    session_n = int(data.get("session_n", 1))
    notes = data.get("notes", "").strip()[:10_000]
    if not notes:
        return jsonify({"committed": 0, "created": []})

    npcs = db.get_npcs(slug, include_hidden=True)
    factions = db.get_factions(slug, include_hidden=True)
    party = db.get_all_party_characters(slug)

    causal_context = db.build_causal_context(slug, session_n)
    try:
        proposals = ai.propose_log_entries(
            notes, meta.get("name", ""), session_n,
            npcs, factions, party=party,
            causal_context=causal_context
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    npc_by_name = {n["name"].lower(): n["id"] for n in npcs}
    faction_by_name = {f["name"].lower(): f["id"] for f in factions}
    condition_by_name = {c["name"].lower(): c["id"] for c in db.get_conditions(slug, include_hidden=True, include_resolved=True)}
    party_names = {c["name"].lower() for c in party}
    committed = 0
    created = []

    for entry in proposals:
        if (entry.get("entity_name") or "").strip().lower() in party_names:
            continue
        entity_id = entry.get("entity_id")
        entity_type = entry.get("entity_type", "npc")
        note = entry.get("note", "").strip()[:500]
        if not note:
            continue

        if entity_type == "ship":
            ship_name = (entry.get("entity_name") or "").strip()
            if ship_name and db.log_ship(slug, ship_name, session_n, note,
                                         event_type=entry.get("event_type"),
                                         visibility=entry.get("visibility", "public")):
                committed += 1
            continue

        if entity_type == "condition":
            if not entity_id:
                name = (entry.get("entity_name") or "").strip()
                if not name:
                    continue
                entity_id = condition_by_name.get(name.lower())
                if not entity_id:
                    meta_c = entry.get("condition_meta") or {}
                    entity_id = db.slugify(name)
                    db.add_condition(slug, name, region=meta_c.get("region", ""),
                                     effect_type=meta_c.get("effect_type", "custom"),
                                     effect_scope=meta_c.get("effect_scope", ""),
                                     magnitude=meta_c.get("magnitude", ""), hidden=False)
                    condition_by_name[name.lower()] = entity_id
                    created.append({"name": name, "type": "condition"})
            polarity = entry.get("polarity") or None
            intensity = int(entry.get("intensity") or 1)
            src_evt = db.log_condition(slug, entity_id, session_n, note, polarity=polarity,
                                       intensity=intensity, event_type=entry.get("event_type"),
                                       visibility=entry.get("visibility", "public"))
            if polarity:
                db.apply_ripple(slug, entity_id, "condition", session_n, note, polarity, intensity,
                                entry.get("event_type"), visibility=entry.get("visibility", "public"),
                                source_event_id=src_evt)
            committed += 1
            continue

        if entity_type in ("party", "party_group") or entity_id == "_party":
            polarity = entry.get("polarity") or None
            intensity = int(entry.get("intensity") or 1)
            event_type = entry.get("event_type") or None
            visibility = entry.get("visibility", "public")
            actor_id = entry.get("actor_id") or None
            actor_type = entry.get("actor_type") or None
            db.log_party_group(slug, session_n, note, polarity=polarity,
                               intensity=intensity, event_type=event_type, visibility=visibility,
                               actor_id=actor_id, actor_type=actor_type,
                               party_name=meta.get("party_name") or "The Party")
            committed += 1
            continue

        if not entity_id:
            name = (entry.get("entity_name") or "").strip()
            if not name:
                continue
            name_lower = name.lower()
            if entity_type == "faction":
                entity_id = faction_by_name.get(name_lower) or npc_by_name.get(name_lower)
            else:
                entity_id = npc_by_name.get(name_lower) or faction_by_name.get(name_lower)
            if not entity_id:
                pol = entry.get("polarity")
                rel = "friendly" if pol == "positive" else "hostile" if pol == "negative" else "neutral"
                entity_id = db.slugify(name)
                if entity_type == "faction":
                    db.add_faction(slug, name, rel, description="", hidden=True)
                    faction_by_name[name_lower] = entity_id
                else:
                    faction_ref = _resolve_faction(slug, entry.get("faction_name"), faction_by_name, created)
                    db.add_npc(slug, name, role="", relationship=rel, description="", hidden=True, factions=[faction_ref] if faction_ref else [])
                    npc_by_name[name_lower] = entity_id
                created.append({"name": name, "type": entity_type})

        polarity = entry.get("polarity") or None
        intensity = int(entry.get("intensity") or 1)
        event_type = entry.get("event_type") or None
        visibility = entry.get("visibility", "public")
        if entity_type == "faction" or entity_id in faction_by_name.values():
            src_evt = db.log_faction(slug, entity_id, session_n, note, polarity=polarity,
                                     intensity=intensity, event_type=event_type, visibility=visibility)
        else:
            src_evt = db.log_npc(slug, entity_id, session_n, note, polarity=polarity,
                                 intensity=intensity, event_type=event_type, visibility=visibility)
        if polarity:
            db.apply_ripple(slug, entity_id, entity_type, session_n, note, polarity, intensity,
                            event_type, visibility=visibility, source_event_id=src_evt)
        committed += 1

    return jsonify({"committed": committed, "created": created, "session_n": session_n})


@dm_bp.route("/<slug>/dm/import/obsidian", methods=["POST"])
@dm_required
def dm_import_obsidian(slug):
    f = request.files.get("vault_zip")
    if not f:
        return jsonify({"error": "No file uploaded."}), 400
    raw = f.read(10_000_000)  # 10 MB cap
    try:
        result = vault_importer.parse_vault_zip(raw)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    # Mark entities that already exist in this campaign
    existing_npc_ids = {n["id"] for n in db.get_npcs(slug)}
    existing_faction_ids = {f["id"] for f in db.get_factions(slug)}
    existing_quest_ids = {q["id"] for q in db.get_quests(slug)}
    existing_location_ids = {l["id"] for l in db.get_locations(slug)}

    for n in result["npcs"]:
        n["exists"] = db.slugify(n["name"]) in existing_npc_ids
    for f2 in result["factions"]:
        f2["exists"] = db.slugify(f2["name"]) in existing_faction_ids
    for q in result["quests"]:
        q["exists"] = db.slugify(q["name"]) in existing_quest_ids
    for loc in result["locations"]:
        loc["exists"] = db.slugify(loc["name"]) in existing_location_ids

    return jsonify(result)


@dm_bp.route("/<slug>/dm/import/obsidian/confirm", methods=["POST"])
@dm_required
def dm_import_obsidian_confirm(slug):
    data = request.get_json()
    npcs_in = data.get("npcs", [])
    factions_in = data.get("factions", [])
    quests_in = data.get("quests", [])
    locations_in = data.get("locations", [])

    created = {"npcs": 0, "factions": 0, "quests": 0, "locations": 0}

    # Create factions first so NPCs can reference them
    existing_factions = db.get_factions(slug)
    faction_id_map = {f["id"]: f["id"] for f in existing_factions}
    faction_name_map = {f["name"].lower(): f["id"] for f in existing_factions}
    for f2 in factions_in:
        fid = db.slugify(f2["name"])
        if fid not in faction_id_map:
            db.add_faction(slug, f2["name"], "neutral", f2.get("description", ""), hidden=False)
            faction_id_map[fid] = fid
            faction_name_map[f2["name"].lower()] = fid
            created["factions"] += 1

    existing_npc_ids = {n["id"] for n in db.get_npcs(slug)}
    for n in npcs_in:
        nid = db.slugify(n["name"])
        if nid in existing_npc_ids:
            continue
        fn = (n.get("faction_name") or "").strip().lower()
        faction_ids = [faction_name_map[fn]] if fn and fn in faction_name_map else []
        db.add_npc(slug, n["name"], n.get("role", ""), "neutral",
                   n.get("description", ""), hidden=False, factions=faction_ids)
        existing_npc_ids.add(nid)
        created["npcs"] += 1

    existing_quest_ids = {q["id"] for q in db.get_quests(slug)}
    for q in quests_in:
        qid = db.slugify(q["name"])
        if qid in existing_quest_ids:
            continue
        db.add_quest(slug, q["name"], q.get("description", ""), hidden=False, status=q.get("status", "active"))
        existing_quest_ids.add(qid)
        created["quests"] += 1

    existing_location_ids = {l["id"] for l in db.get_locations(slug)}
    for loc in locations_in:
        lid = db.slugify(loc["name"])
        if lid in existing_location_ids:
            continue
        db.add_location(slug, loc["name"], loc.get("role", ""), loc.get("description", ""),
                        hidden=False, dm_notes="")
        existing_location_ids.add(lid)
        created["locations"] += 1

    total = sum(created.values())
    return jsonify({"ok": True, "created": created, "total": total})


@dm_bp.route("/<slug>/dm/log", methods=["GET", "POST"])
@dm_required
def dm_log(slug):
    meta = load(slug, "campaign.json")
    npcs = db.get_npcs(slug)
    factions = db.get_factions(slug)
    quests = db.get_quests(slug)

    if request.method == "POST":
        session_n = int(request.form.get("session") or 0)

        for npc in npcs:
            note = request.form.get(f"npc_{npc['id']}_note", "").strip()
            polarity = request.form.get(f"npc_{npc['id']}_polarity") or None
            intensity = int(request.form.get(f"npc_{npc['id']}_intensity") or 1)
            event_type = request.form.get(f"npc_{npc['id']}_event_type", "").strip() or None
            if note:
                db.log_npc(slug, npc["id"], session_n, note, polarity=polarity, intensity=intensity, event_type=event_type)

        for f in factions:
            note = request.form.get(f"faction_{f['id']}_note", "").strip()
            rel = request.form.get(f"faction_{f['id']}_rel", "").strip()
            if note:
                db.log_faction(slug, f["id"], session_n, note)
            if rel and rel != f.get("relationship"):
                db.update_faction(slug, f["id"], relationship=rel)

        for q in quests:
            note = request.form.get(f"quest_{q['id']}_note", "").strip()
            status = request.form.get(f"quest_{q['id']}_status", "").strip()
            if note:
                db.log_quest(slug, q["id"], session_n, note)
            if status and status != q.get("status"):
                db.set_quest_status(slug, q["id"], status)
            for i, obj in enumerate(q.get("objectives", [])):
                checked = request.form.get(f"quest_{q['id']}_obj_{i}") == "on"
                if checked != obj.get("done", False):
                    db.set_objective(slug, q["id"], i, checked)

        flash("Session log saved", "success")
        return redirect(url_for("dm_bp.dm", slug=slug))

    return render_template("dm/log.html", meta=meta, slug=slug,
                           npcs=npcs, factions=factions, quests=quests)


@dm_bp.route("/<slug>/dm/npcs/add", methods=["GET", "POST"])
@dm_required
def dm_add_npc(slug):
    meta = load(slug, "campaign.json")
    if request.method == "POST":
        db.add_npc(
            slug,
            name=request.form["name"].strip(),
            role=request.form.get("role", "").strip(),
            relationship=request.form.get("relationship", "neutral"),
            description=request.form.get("description", "").strip(),
            hidden="hidden" in request.form,
            factions=request.form.getlist("factions"),
            hidden_factions=request.form.getlist("hidden_factions"),
            image_url=request.form.get("image_url", "").strip() if _allowed_image_url(request.form.get("image_url", "").strip())[0] else None,
            dm_notes=request.form.get("dm_notes", "").strip() or None,
        )
        if request.form.get("ajax"):
            return jsonify({"ok": True})
        return redirect(url_for("dm_bp.dm", slug=slug))
    return render_template("dm/add_npc.html", meta=meta, slug=slug,
                           factions=db.get_factions(slug))


@dm_bp.route("/<slug>/dm/factions/add", methods=["GET", "POST"])
@dm_required
def dm_add_faction(slug):
    meta = load(slug, "campaign.json")
    if request.method == "POST":
        db.add_faction(
            slug,
            name=request.form["name"].strip(),
            relationship=request.form.get("relationship", "neutral"),
            description=request.form.get("description", "").strip(),
            hidden="hidden" in request.form,
            image_url=request.form.get("image_url", "").strip() if _allowed_image_url(request.form.get("image_url", "").strip())[0] else None,
            dm_notes=request.form.get("dm_notes", "").strip() or None,
        )
        if request.form.get("ajax"):
            return jsonify({"ok": True})
        return redirect(url_for("dm_bp.dm", slug=slug))
    return render_template("dm/add_faction.html", meta=meta, slug=slug)


@dm_bp.route("/<slug>/dm/quests/add", methods=["GET", "POST"])
@dm_required
def dm_add_quest(slug):
    meta = load(slug, "campaign.json")
    if request.method == "POST":
        db.add_quest(
            slug,
            title=request.form["title"].strip(),
            description=request.form.get("description", "").strip(),
            hidden="hidden" in request.form,
        )
        return redirect(url_for("dm_bp.dm", slug=slug))
    return render_template("dm/add_quest.html", meta=meta, slug=slug)


@dm_bp.route("/<slug>/dm/quests/<quest_id>/objective", methods=["POST"])
@dm_required
def dm_add_objective(slug, quest_id):
    text = request.form.get("text", "").strip()
    if text:
        db.add_objective(slug, quest_id, text)
    return redirect(url_for("player.story", slug=slug))


@dm_bp.route("/<slug>/dm/party/add", methods=["GET", "POST"])
@dm_required
def dm_add_character(slug):
    meta = load(slug, "campaign.json")
    if request.method == "POST":
        raw_session = request.form.get("session_joined", "").strip()
        db.add_character(
            slug,
            name=request.form["name"].strip(),
            race=request.form.get("race", "").strip(),
            char_class=request.form.get("char_class", "").strip(),
            level=request.form.get("level", 1),
            notes=request.form.get("notes", "").strip(),
            hidden="hidden" in request.form,
            party_id=request.form.get("party_id") or None,
            session=int(raw_session) if raw_session.isdigit() else None,
        )
        return redirect(url_for("dm_bp.dm", slug=slug))
    parties = db.get_parties(slug)
    current_session = db.get_current_session(slug) or 1
    return render_template("dm/add_character.html", meta=meta, slug=slug, parties=parties,
                           current_session=current_session)


@dm_bp.route("/<slug>/dm/party/create", methods=["POST"])
@dm_required
def dm_create_party(slug):
    name = request.form.get("name", "").strip()
    if not name:
        flash("Party name is required.", "error")
        return redirect(url_for("player.party", slug=slug))
    db.add_party(slug, name)
    return redirect(url_for("player.party", slug=slug))


@dm_bp.route("/<slug>/dm/party/<party_id>/rename", methods=["POST"])
@dm_required
def dm_rename_party(slug, party_id):
    name = request.form.get("name", "").strip()
    if not name:
        flash("Party name is required.", "error")
        return redirect(url_for("player.party", slug=slug))
    db.rename_party(slug, party_id, name)
    return redirect(url_for("player.party", slug=slug, party=party_id))


@dm_bp.route("/<slug>/dm/party/<party_id>/delete", methods=["POST"])
@dm_required
def dm_delete_party(slug, party_id):
    parties = db.get_parties(slug)
    if len(parties) <= 1:
        flash("Cannot delete the last group.", "error")
        return redirect(url_for("player.party", slug=slug))
    target = next((p for p in parties if p["id"] == party_id), None)
    if target and target.get("characters"):
        flash("Remove all characters from this group before deleting it.", "error")
        return redirect(url_for("player.party", slug=slug, party=party_id))
    db.delete_party(slug, party_id)
    return redirect(url_for("player.party", slug=slug))


@dm_bp.route("/<slug>/assets/currency", methods=["POST"])
def set_currency(slug):
    r = campaign_access(slug)
    if r: return r
    db.set_currency(slug, request.form.get("key", "gold").strip(), request.form.get("amount", 0))
    return redirect(url_for("player.assets", slug=slug))


@dm_bp.route("/<slug>/assets/item", methods=["POST"])
def add_item(slug):
    r = campaign_access(slug)
    if r: return r
    name = request.form.get("name", "").strip()
    if name:
        db.add_item(slug, name, request.form.get("notes", "").strip())
    return redirect(url_for("player.assets", slug=slug))


@dm_bp.route("/<slug>/assets/item/<int:idx>/remove", methods=["POST"])
def remove_item(slug, idx):
    r = campaign_access(slug)
    if r: return r
    db.remove_item(slug, idx)
    return redirect(url_for("player.assets", slug=slug))


@dm_bp.route("/<slug>/assets/item/<int:idx>/edit", methods=["POST"])
def edit_item(slug, idx):
    r = campaign_access(slug)
    if r: return r
    name = request.form.get("name", "").strip()
    if name:
        db.edit_item(slug, idx, name, request.form.get("notes", "").strip())
    return redirect(url_for("player.assets", slug=slug))




@dm_bp.route("/<slug>/dm/assets/ship", methods=["POST"])
@dm_required
def dm_add_ship(slug):
    name = request.form.get("name", "").strip()
    ship_type = request.form.get("type", "").strip()
    hp = request.form.get("hp", "").strip()
    notes = request.form.get("notes", "").strip()
    weapons = [{"name": w.strip(), "hp": 50, "max_hp": 50} for w in request.form.get("weapons", "").split(",") if w.strip()]
    crew = [c.strip() for c in request.form.get("crew", "").split(",") if c.strip()]
    cargo = [c.strip() for c in request.form.get("cargo", "").split(",") if c.strip()]
    if name:
        db.add_ship(slug, name, ship_type, hp=hp, weapons=weapons, crew=crew, cargo=cargo, notes=notes)
    return redirect(url_for("player.assets", slug=slug))


@dm_bp.route("/<slug>/dm/assets/stronghold", methods=["POST"])
@dm_required
def dm_set_stronghold(slug):
    db.set_stronghold(
        slug,
        name=request.form.get("name", "").strip(),
        kind=request.form.get("type", "").strip(),
        location=request.form.get("location", "").strip(),
        condition=request.form.get("condition", "").strip(),
        notes=request.form.get("notes", "").strip(),
    )
    return redirect(url_for("player.assets", slug=slug))


@dm_bp.route("/<slug>/dm/assets/stronghold/feature", methods=["POST"])
@dm_required
def dm_add_stronghold_feature(slug):
    text = request.form.get("text", "").strip()
    if text:
        db.add_stronghold_feature(slug, text)
    return redirect(url_for("player.assets", slug=slug))


@dm_bp.route("/<slug>/dm/assets/stronghold/feature/<int:idx>/remove", methods=["POST"])
@dm_required
def dm_remove_stronghold_feature(slug, idx):
    db.remove_stronghold_feature(slug, idx)
    return redirect(url_for("player.assets", slug=slug))


@dm_bp.route("/<slug>/dm/assets/stronghold/upgrade", methods=["POST"])
@dm_required
def dm_add_stronghold_upgrade(slug):
    text = request.form.get("text", "").strip()
    if text:
        db.add_stronghold_upgrade(slug, text)
    return redirect(url_for("player.assets", slug=slug))


@dm_bp.route("/<slug>/dm/assets/stronghold/upgrade/<int:idx>/remove", methods=["POST"])
@dm_required
def dm_remove_stronghold_upgrade(slug, idx):
    db.remove_stronghold_upgrade(slug, idx)
    return redirect(url_for("player.assets", slug=slug))


@dm_bp.route("/<slug>/dm/assets/stronghold/delete", methods=["POST"])
@dm_required
def dm_delete_stronghold(slug):
    db.delete_stronghold(slug)
    return redirect(url_for("player.assets", slug=slug))


@dm_bp.route("/<slug>/dm/assets/ship/<int:ship_idx>/edit", methods=["POST"])
@dm_required
def dm_edit_ship(slug, ship_idx):
    db.update_ship(slug, ship_idx,
        name=request.form.get("name", "").strip(),
        kind=request.form.get("type", "").strip(),
        hp=request.form.get("hp", "").strip(),
        notes=request.form.get("notes", "").strip())
    return redirect(url_for("player.assets", slug=slug))


@dm_bp.route("/<slug>/dm/assets/ship/<int:ship_idx>/crew", methods=["POST"])
@dm_required
def dm_add_crew(slug, ship_idx):
    member = request.form.get("member", "").strip()
    if member:
        db.add_crew(slug, ship_idx, member)
    return redirect(url_for("player.assets", slug=slug))


@dm_bp.route("/<slug>/dm/assets/ship/<int:ship_idx>/crew/<int:crew_idx>/remove", methods=["POST"])
@dm_required
def dm_remove_crew(slug, ship_idx, crew_idx):
    db.remove_crew(slug, ship_idx, crew_idx)
    return redirect(url_for("player.assets", slug=slug))


@dm_bp.route("/<slug>/dm/assets/ship/<int:ship_idx>/cargo", methods=["POST"])
@dm_required
def dm_add_cargo(slug, ship_idx):
    item = request.form.get("item", "").strip()
    if item:
        db.add_cargo(slug, ship_idx, item)
    return redirect(url_for("player.assets", slug=slug))


@dm_bp.route("/<slug>/dm/assets/ship/<int:ship_idx>/cargo/<int:cargo_idx>/remove", methods=["POST"])
@dm_required
def dm_remove_cargo(slug, ship_idx, cargo_idx):
    db.remove_cargo(slug, ship_idx, cargo_idx)
    return redirect(url_for("player.assets", slug=slug))


@dm_bp.route("/<slug>/dm/assets/ship/<int:ship_idx>/delete", methods=["POST"])
@dm_required
def dm_delete_ship(slug, ship_idx):
    db.delete_ship(slug, ship_idx)
    return redirect(url_for("player.assets", slug=slug))


@dm_bp.route("/<slug>/dm/assets/ship/<int:ship_idx>/weapon", methods=["POST"])
@dm_required
def dm_add_weapon(slug, ship_idx):
    name = request.form.get("name", "").strip()
    max_hp = int(request.form.get("max_hp") or 50)
    if name:
        db.add_weapon(slug, ship_idx, name, max_hp)
    return redirect(url_for("player.assets", slug=slug))


@dm_bp.route("/<slug>/assets/ship/<int:ship_idx>/weapon/<int:weapon_idx>/hp", methods=["POST"])
def set_weapon_hp(slug, ship_idx, weapon_idx):
    r = campaign_access(slug)
    if r: return r
    hp = request.form.get("hp", "0")
    try:
        db.set_weapon_hp(slug, ship_idx, weapon_idx, int(hp))
    except ValueError:
        pass
    return redirect(url_for("player.assets", slug=slug))


# ── DM inline edit routes ─────────────────────────────────────────────────────

@dm_bp.route("/<slug>/dm/npc/<npc_id>/delete", methods=["POST"])
@dm_required
def dm_delete_npc(slug, npc_id):
    db.delete_npc(slug, npc_id)
    return redirect(url_for("player.world", slug=slug))


@dm_bp.route("/<slug>/dm/faction/<faction_id>/delete", methods=["POST"])
@dm_required
def dm_delete_faction(slug, faction_id):
    db.delete_faction(slug, faction_id)
    return redirect(url_for("player.world", slug=slug))


@dm_bp.route("/<slug>/dm/quest/<quest_id>/delete", methods=["POST"])
@dm_required
def dm_delete_quest(slug, quest_id):
    db.delete_quest(slug, quest_id)
    return redirect(url_for("player.story", slug=slug))


@dm_bp.route("/<slug>/dm/character/<char_name>/delete", methods=["POST"])
@dm_required
def dm_delete_character(slug, char_name):
    db.delete_character(slug, char_name)
    return redirect(url_for("player.party", slug=slug))


@dm_bp.route("/<slug>/dm/references/<ref_id>/delete", methods=["POST"])
@dm_required
def dm_delete_reference(slug, ref_id):
    db.delete_reference(slug, ref_id)
    return redirect(url_for("player.references", slug=slug))


@dm_bp.route("/<slug>/dm/assets/ship/<int:ship_idx>/weapon/<int:weapon_idx>/delete", methods=["POST"])
@dm_required
def dm_delete_weapon(slug, ship_idx, weapon_idx):
    db.delete_weapon(slug, ship_idx, weapon_idx)
    return redirect(url_for("player.assets", slug=slug))


@dm_bp.route("/<slug>/dm/npc/<npc_id>/log/<int:idx>/delete", methods=["POST"])
@dm_required
def dm_delete_npc_log(slug, npc_id, idx):
    db.delete_npc_log_entry(slug, npc_id, idx)
    return redirect(url_for("player.npc", slug=slug, npc_id=npc_id))


@dm_bp.route("/<slug>/dm/npc/<npc_id>/log/<event_id>/edit", methods=["POST"])
@dm_required
def dm_edit_npc_log(slug, npc_id, event_id):
    db.edit_log_entry(slug, npc_id, "npc", event_id,
                      note=request.form.get("note", "").strip() or None,
                      polarity=request.form.get("polarity") or None,
                      intensity=request.form.get("intensity"),
                      visibility=request.form.get("visibility"))
    if request.form.get("ajax"):
        return jsonify(ok=True)
    flash("Entry updated", "success")
    return redirect(url_for("player.npc", slug=slug, npc_id=npc_id))


@dm_bp.route("/<slug>/dm/faction/<faction_id>/log/<int:idx>/delete", methods=["POST"])
@dm_required
def dm_delete_faction_log(slug, faction_id, idx):
    db.delete_faction_log_entry(slug, faction_id, idx)
    return redirect(url_for("player.faction", slug=slug, faction_id=faction_id))


@dm_bp.route("/<slug>/dm/faction/<faction_id>/log/<event_id>/edit", methods=["POST"])
@dm_required
def dm_edit_faction_log(slug, faction_id, event_id):
    db.edit_log_entry(slug, faction_id, "faction", event_id,
                      note=request.form.get("note", "").strip() or None,
                      polarity=request.form.get("polarity") or None,
                      intensity=request.form.get("intensity"),
                      visibility=request.form.get("visibility"))
    if request.form.get("ajax"):
        return jsonify(ok=True)
    flash("Entry updated", "success")
    return redirect(url_for("player.faction", slug=slug, faction_id=faction_id))


@dm_bp.route("/<slug>/dm/event/<event_id>/undo_ripple", methods=["POST"])
@dm_required
def dm_undo_ripple(slug, event_id):
    removed = db.undo_ripple_chain(slug, event_id)
    if removed:
        flash(f"Removed {removed} ripple event{'s' if removed != 1 else ''}", "success")
    else:
        flash("No ripple events found for this entry", "info")
    next_url = request.form.get("next") or request.referrer or url_for("dm_bp.dm", slug=slug)
    return redirect(next_url)


@dm_bp.route("/<slug>/dm/event/<event_id>/delete_entry", methods=["POST"])
@dm_required
def dm_delete_log_entry_by_id(slug, event_id):
    entity_type = request.form.get("entity_type")
    entity_id = request.form.get("entity_id")
    db.delete_log_entry_by_id(slug, entity_id, entity_type, event_id)
    next_url = request.form.get("next") or request.referrer or url_for("dm_bp.dm", slug=slug)
    return redirect(next_url)


@dm_bp.route("/<slug>/dm/log/event/delete", methods=["POST"])
@dm_required
def dm_delete_log_event_ajax(slug):
    data = request.get_json() or {}
    event_id = data.get("event_id", "")
    entity_type = data.get("entity_type", "")
    entity_id = data.get("entity_id", "")
    if not event_id or not entity_type:
        return jsonify({"error": "missing fields"}), 400
    db.delete_log_entry_by_id(slug, entity_id, entity_type, event_id)
    return jsonify({"ok": True})


@dm_bp.route("/<slug>/dm/log/event/edit", methods=["POST"])
@dm_required
def dm_edit_log_event_ajax(slug):
    data = request.get_json() or {}
    event_id = data.get("event_id", "")
    entity_type = data.get("entity_type", "")
    entity_id = data.get("entity_id", "")
    if not event_id or not entity_type:
        return jsonify({"error": "missing fields"}), 400
    actor_id = data.get("actor_id") or None
    location_id = data.get("location_id") or None
    db.edit_log_entry(slug, entity_id, entity_type, event_id,
                      note=data.get("note") or None,
                      polarity=data.get("polarity") or "",
                      intensity=data.get("intensity"),
                      visibility=data.get("visibility") or None,
                      actor_id=actor_id,
                      actor_type=data.get("actor_type") or None,
                      location_id=location_id,
                      clear_actor=data.get("clear_actor", False),
                      clear_location=data.get("clear_location", False))
    event_id_str = event_id
    witnesses_add = data.get("witnesses_add") or []
    witnesses_remove = data.get("witnesses_remove") or []
    for char_name in witnesses_add:
        db.reveal_event(slug, event_id_str, char_name)
    for char_name in witnesses_remove:
        db.unreveal_event(slug, event_id_str, char_name)
    return jsonify({"ok": True})


@dm_bp.route("/<slug>/dm/event/<event_id>/restore_ripple", methods=["POST"])
@dm_required
def dm_restore_ripple(slug, event_id):
    entity_type = request.form.get("entity_type")
    entity_id = request.form.get("entity_id")
    db.restore_log_entry_by_id(slug, entity_id, entity_type, event_id)
    next_url = request.form.get("next") or request.referrer or url_for("dm_bp.dm", slug=slug)
    return redirect(next_url)


@dm_bp.route("/<slug>/dm/event/<event_id>/move", methods=["POST"])
@dm_required
def dm_move_log_entry(slug, event_id):
    source_type = request.form.get("source_type")
    source_id = request.form.get("source_id")
    target = request.form.get("target", "")
    if not target or ":" not in target:
        abort(400)
    target_type, target_id = target.split(":", 1)
    db.move_log_entry(slug, source_id, source_type, event_id, target_id, target_type)
    next_url = request.form.get("next") or request.referrer or url_for("dm_bp.dm", slug=slug)
    return redirect(next_url)


@dm_bp.route("/<slug>/dm/session/discard_proposals", methods=["POST"])
@dm_required
def dm_discard_proposals(slug):
    saved = db.get_proposals(slug)
    pending_cursor = saved.get("parse_cursor")
    db.clear_proposals(slug)
    if pending_cursor is not None:
        current_notes = db.get_session_notes(slug)
        if pending_cursor <= len(current_notes):
            db.set_notes_parse_cursor(slug, pending_cursor)
        else:
            db.reset_notes_parse_cursor(slug)
    return ("", 204)


# ── Condition routes ──────────────────────────────────────────────────────────

@dm_bp.route("/<slug>/dm/conditions/add", methods=["POST"])
@dm_required
def dm_add_condition(slug):
    name = request.form.get("name", "").strip()
    if not name:
        flash("Condition name required.", "error")
        return redirect(url_for("dm_bp.dm", slug=slug))
    db.add_condition(
        slug, name,
        region=request.form.get("region", "").strip(),
        effect_type=request.form.get("effect_type", "custom").strip(),
        effect_scope=request.form.get("effect_scope", "").strip(),
        magnitude=request.form.get("magnitude", "").strip(),
        description=request.form.get("description", "").strip(),
        hidden=request.form.get("hidden") == "1",
    )
    flash(f"Condition '{name}' added.", "success")
    return redirect(url_for("dm_bp.dm", slug=slug))


@dm_bp.route("/<slug>/dm/condition/<condition_id>/delete", methods=["POST"])
@dm_required
def dm_delete_condition(slug, condition_id):
    db.delete_condition(slug, condition_id)
    return redirect(url_for("dm_bp.dm", slug=slug))


@dm_bp.route("/<slug>/dm/condition/<condition_id>/status", methods=["POST"])
@dm_required
def dm_toggle_condition_status(slug, condition_id):
    conditions = db.get_conditions(slug, include_hidden=True, include_resolved=True)
    c = next((x for x in conditions if x["id"] == condition_id), None)
    if c:
        db.set_condition_status(slug, condition_id, "resolved" if c.get("status") == "active" else "active")
    return redirect(request.form.get("next") or url_for("dm_bp.dm", slug=slug))


@dm_bp.route("/<slug>/dm/condition/<condition_id>/toggle_hidden", methods=["POST"])
@dm_required
def dm_toggle_condition_hidden(slug, condition_id):
    conditions = db.get_conditions(slug, include_hidden=True, include_resolved=True)
    c = next((x for x in conditions if x["id"] == condition_id), None)
    if c:
        db.set_condition_hidden(slug, condition_id, not c.get("hidden", True))
    return redirect(request.form.get("next") or url_for("dm_bp.dm", slug=slug))


@dm_bp.route("/<slug>/dm/condition/<condition_id>/log/<int:idx>/delete", methods=["POST"])
@dm_required
def dm_delete_condition_log(slug, condition_id, idx):
    db.delete_condition_log_entry(slug, condition_id, idx)
    return redirect(request.form.get("next") or url_for("dm_bp.dm", slug=slug))


@dm_bp.route("/<slug>/dm/world/futures", methods=["POST"])
@dm_required
@ai_required
@limiter.limit("30 per hour")
def dm_propose_futures(slug):
    meta = load(slug, "campaign.json")
    current_session = db.get_current_session(slug)
    world_summary = db.get_world_state_summary(slug, current_session)
    causal_context = db.build_causal_context(slug, current_session)
    try:
        futures = ai.propose_futures(meta.get("name", ""), current_session, world_summary,
                                     causal_context=causal_context)
        npc_by_name = {n["name"].lower(): n["id"] for n in db.get_npcs(slug, include_hidden=True)}
        faction_by_name = {f["name"].lower(): f["id"] for f in db.get_factions(slug, include_hidden=True)}
        condition_by_name = {c["name"].lower(): c["id"] for c in db.get_conditions(slug, include_hidden=True)}
        for f in futures:
            name = (f.get("entity_name") or "").lower()
            kind = f.get("entity_kind", "npc")
            if kind == "condition":
                f["entity_id"] = condition_by_name.get(name)
            elif kind == "faction":
                f["entity_id"] = faction_by_name.get(name) or npc_by_name.get(name)
            else:
                f["entity_id"] = npc_by_name.get(name) or faction_by_name.get(name)
        db.save_futures(slug, futures, current_session)
        return jsonify({"futures": futures, "session": current_session})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@dm_bp.route("/<slug>/dm/world/confirm_projection", methods=["POST"])
@dm_required
def dm_confirm_projection(slug):
    data = request.get_json()
    entity_id   = data.get("entity_id")
    entity_type = data.get("entity_type", "npc")
    event_id    = data.get("event_id")
    new_type    = data.get("event_type", "other")
    current_session = db.get_current_session(slug)
    entry = db.confirm_projection(slug, entity_id, entity_type, event_id, new_type, current_session)
    if not entry:
        return jsonify({"error": "Entry not found"}), 404
    return jsonify({"ok": True, "event_type": entry["event_type"]})


@dm_bp.route("/<slug>/dm/world/dismiss_projection", methods=["POST"])
@dm_required
def dm_dismiss_projection(slug):
    data = request.get_json()
    db.dismiss_projection(slug, data.get("entity_id"), data.get("entity_type", "npc"), data.get("event_id"))
    return jsonify({"ok": True})


@dm_bp.route("/<slug>/dm/world/commit_futures", methods=["POST"])
@dm_required
def dm_commit_futures(slug):
    data = request.get_json()
    entries = data.get("entries", [])
    current_session = db.get_current_session(slug)
    npc_by_name = {n["name"].lower(): n["id"] for n in db.get_npcs(slug, include_hidden=True)}
    faction_by_name = {f["name"].lower(): f["id"] for f in db.get_factions(slug, include_hidden=True)}
    condition_by_name = {c["name"].lower(): c["id"] for c in db.get_conditions(slug, include_hidden=True)}
    for entry in entries:
        if not entry.get("entity_id"):
            name = (entry.get("entity_name") or "").lower()
            kind = entry.get("entity_kind", entry.get("entity_type", "npc"))
            if kind == "condition":
                entry["entity_id"] = condition_by_name.get(name)
                entry["entity_type"] = "condition"
            else:
                entry["entity_id"] = npc_by_name.get(name) or faction_by_name.get(name)
                if entry["entity_id"] and entry["entity_id"] in faction_by_name.values():
                    entry["entity_type"] = "faction"
    before = {(e["entity_id"], e.get("entity_type", "npc")): db.entity_snapshot(slug, e["entity_id"], e.get("entity_type", "npc"))
              for e in entries if e.get("entity_id")}
    committed = 0
    for entry in entries:
        entity_id = entry.get("entity_id")
        entity_type = entry.get("entity_type", "npc")
        note = entry.get("note", "").strip()
        if not entity_id or not note:
            continue
        confidence = entry.get("confidence", "medium")
        intensity = 3 if confidence == "high" else 2 if confidence == "medium" else 1
        if entity_type == "condition":
            db.log_condition(slug, entity_id, current_session, note,
                             intensity=intensity, event_type="projected", visibility="public")
        elif entity_type == "npc":
            db.log_npc(slug, entity_id, current_session, note,
                       intensity=intensity, event_type="projected", visibility="public")
        else:
            db.log_faction(slug, entity_id, current_session, note,
                           intensity=intensity, event_type="projected", visibility="public")
        committed += 1
    return jsonify({"committed": committed, "diffs": _build_diffs(slug, before, entries)})


@dm_bp.route("/<slug>/dm/quest/<quest_id>/log/<int:idx>/delete", methods=["POST"])
@dm_required
def dm_delete_quest_log(slug, quest_id, idx):
    db.delete_quest_log_entry(slug, quest_id, idx)
    return redirect(url_for("player.story", slug=slug))


@dm_bp.route("/<slug>/dm/character/<char_name>/toggle_hidden", methods=["POST"])
@dm_required
def dm_toggle_character_hidden(slug, char_name):
    chars = db.get_all_party_characters(slug)
    char = next((c for c in chars if c["name"] == char_name), None)
    if char:
        db.set_character_hidden(slug, char_name, not char.get("hidden", False))
    if request.form.get("next") == "dm":
        return redirect(url_for("dm_bp.dm", slug=slug))
    return redirect(url_for("player.party", slug=slug))


@dm_bp.route("/<slug>/dm/character/<char_name>/toggle_dead", methods=["POST"])
@dm_required
def dm_toggle_character_dead(slug, char_name):
    chars = db.get_all_party_characters(slug)
    char = next((c for c in chars if c["name"] == char_name), None)
    if char:
        db.set_character_dead(slug, char_name, not char.get("dead", False))
    if request.form.get("next") == "dm":
        return redirect(url_for("dm_bp.dm", slug=slug))
    return redirect(url_for("player.party", slug=slug))


@dm_bp.route("/<slug>/dm/assets/property", methods=["POST"])
@dm_required
def dm_add_property(slug):
    name = request.form.get("name", "").strip()
    if name:
        db.add_property(slug, name, request.form.get("notes", "").strip())
    return redirect(url_for("player.assets", slug=slug))


@dm_bp.route("/<slug>/dm/assets/property/<int:idx>/remove", methods=["POST"])
@dm_required
def dm_remove_property(slug, idx):
    db.remove_property(slug, idx)
    return redirect(url_for("player.assets", slug=slug))


@dm_bp.route("/<slug>/dm/npc/<npc_id>/toggle_hidden", methods=["POST"])
@dm_required
def dm_toggle_npc_hidden(slug, npc_id):
    npcs = db.get_npcs(slug)
    npc = next((n for n in npcs if n["id"] == npc_id), None)
    if npc:
        db.set_npc_hidden(slug, npc_id, not npc.get("hidden", False))
    if request.form.get("next") == "dm":
        return redirect(url_for("dm_bp.dm", slug=slug))
    return redirect(url_for("player.npc", slug=slug, npc_id=npc_id))


@dm_bp.route("/<slug>/dm/npc/<npc_id>/toggle_dead", methods=["POST"])
@dm_required
def dm_toggle_npc_dead(slug, npc_id):
    npcs = db.get_npcs(slug)
    npc = next((n for n in npcs if n["id"] == npc_id), None)
    if npc:
        marking_dead = not npc.get("dead", False)
        dead_sess = db.get_current_session(slug) if marking_dead else None
        db.set_npc_dead(slug, npc_id, marking_dead, dead_session=dead_sess)
    if request.form.get("ajax"):
        return jsonify(ok=True)
    if request.form.get("next") == "dm":
        return redirect(url_for("dm_bp.dm", slug=slug))
    return redirect(url_for("player.npc", slug=slug, npc_id=npc_id))


@dm_bp.route("/<slug>/dm/npc/<npc_id>/toggle_party_affiliate", methods=["POST"])
@dm_required
def dm_toggle_npc_party_affiliate(slug, npc_id):
    npcs = db.get_npcs(slug)
    npc = next((n for n in npcs if n["id"] == npc_id), None)
    if npc:
        db.set_npc_party_affiliate(slug, npc_id, not npc.get("party_affiliate", False))
    if request.form.get("ajax"):
        return jsonify(ok=True)
    if request.form.get("next") == "dm":
        return redirect(url_for("dm_bp.dm", slug=slug))
    return redirect(url_for("player.npc", slug=slug, npc_id=npc_id))


@dm_bp.route("/<slug>/dm/npc/<npc_id>/edit", methods=["POST"])
@dm_required
def dm_edit_npc(slug, npc_id):
    target_rel = request.form.get("relationship") or None
    score_offset = None
    if target_rel and target_rel in db._TIER_MIN:
        npcs = db.get_npcs(slug)
        npc_obj = next((n for n in npcs if n["id"] == npc_id), None)
        if npc_obj:
            rel_data = db.compute_npc_relationship(npc_obj, is_dm=True)
            if rel_data.get("computed") and rel_data.get("score_natural") is not None:
                natural = rel_data["score_natural"]
                tier_floor = db._TIER_MIN[target_rel]
                score_offset = round(tier_floor - natural, 4) if natural < tier_floor else 0.0
    db.update_npc(
        slug, npc_id,
        name=request.form.get("name", "").strip() or None,
        role=request.form.get("role", "").strip() or None,
        relationship=target_rel,
        description=request.form.get("description") or None,
        factions=request.form.getlist("factions"),
        hidden_factions=request.form.getlist("hidden_factions"),
        score_offset=score_offset,
    )
    if request.form.get("ajax"):
        return jsonify({"ok": True})
    flash("NPC updated", "success")
    if request.form.get("next") == "dm":
        return redirect(url_for("dm_bp.dm", slug=slug))
    return redirect(url_for("player.npc", slug=slug, npc_id=npc_id))


@dm_bp.route("/<slug>/dm/npc/<npc_id>/notes", methods=["POST"])
@dm_required
def dm_edit_npc_notes(slug, npc_id):
    description = request.form.get("description", "").strip()
    dm_notes = request.form.get("dm_notes", "").strip()
    image_url = request.form.get("image_url", "").strip()
    ok, err = _allowed_image_url(image_url)
    if not ok:
        if request.form.get("ajax"):
            return jsonify({"ok": False, "error": err})
        flash(err, "error")
        return redirect(url_for("player.npc", slug=slug, npc_id=npc_id))
    db.update_npc(slug, npc_id, description=description or None, dm_notes=dm_notes if "dm_notes" in request.form else None, image_url=image_url or None)
    if request.form.get("ajax"):
        return jsonify({"ok": True})
    return redirect(url_for("player.npc", slug=slug, npc_id=npc_id))


@dm_bp.route("/<slug>/dm/npc/<npc_id>/log", methods=["POST"])
@dm_required
def dm_log_npc(slug, npc_id):
    note = request.form.get("note", "").strip()
    session_n = int(request.form.get("session") or 0)
    polarity = request.form.get("polarity") or None
    intensity = int(request.form.get("intensity") or 1)
    event_type = request.form.get("event_type", "").strip() or None
    visibility = request.form.get("visibility", "public")
    if visibility not in ("public", "restricted", "dm_only"):
        visibility = "public"
    witnesses = request.form.getlist("witnesses")
    actor_id = request.form.get("actor_id") or None
    actor_type = request.form.get("actor_type") or None
    actor_dm_only = bool(request.form.get("actor_dm_only"))
    axis = request.form.get("axis") or None
    if note:
        src_evt = db.log_npc(slug, npc_id, session_n, note, polarity=polarity, intensity=intensity,
                             event_type=event_type, visibility=visibility,
                             actor_id=actor_id, actor_type=actor_type, actor_dm_only=actor_dm_only,
                             axis=axis)
        for fid in request.form.getlist("also_faction_ids"):
            if fid:
                db.log_faction(slug, fid, session_n, note,
                               polarity=polarity, intensity=intensity,
                               event_type=event_type, visibility=visibility)
        if polarity:
            db.apply_ripple(slug, npc_id, "npc", session_n, note, polarity, intensity,
                            event_type, visibility=visibility, source_event_id=src_evt,
                            actor_id=actor_id, actor_type=actor_type)
        if src_evt:
            for w in witnesses:
                db.reveal_event(slug, src_evt, w)
        flash("Entry added", "success")
    return redirect(url_for("player.npc", slug=slug, npc_id=npc_id))


@dm_bp.route("/<slug>/dm/faction/<faction_id>/toggle_hidden", methods=["POST"])
@dm_required
def dm_toggle_faction_hidden(slug, faction_id):
    factions = db.get_factions(slug)
    faction = next((f for f in factions if f["id"] == faction_id), None)
    if faction:
        db.set_faction_hidden(slug, faction_id, not faction.get("hidden", False))
    if request.form.get("next") == "dm":
        return redirect(url_for("dm_bp.dm", slug=slug))
    return redirect(url_for("player.faction", slug=slug, faction_id=faction_id))


@dm_bp.route("/<slug>/dm/faction/<faction_id>/toggle_party_affiliated", methods=["POST"])
@dm_required
def dm_toggle_faction_party_affiliated(slug, faction_id):
    faction = next((f for f in db.get_factions(slug, include_hidden=True) if f["id"] == faction_id), None)
    if faction:
        db.set_faction_party_affiliated(slug, faction_id, not faction.get("party_affiliated", False))
    next_url = request.form.get("next") or url_for("player.faction", slug=slug, faction_id=faction_id)
    return redirect(next_url)


@dm_bp.route("/<slug>/dm/faction/<faction_id>/toggle_char_member", methods=["POST"])
@dm_required
def dm_toggle_faction_char_member(slug, faction_id):
    char_name = request.form.get("char_name", "").strip()
    faction = next((f for f in db.get_factions(slug, include_hidden=True) if f["id"] == faction_id), None)
    if faction and char_name:
        currently = char_name in faction.get("affiliated_chars", [])
        db.set_faction_char_member(slug, faction_id, char_name, not currently)
    next_url = request.form.get("next") or url_for("player.faction", slug=slug, faction_id=faction_id)
    return redirect(next_url)


@dm_bp.route("/<slug>/dm/faction/<faction_id>/edit", methods=["POST"])
@dm_required
def dm_edit_faction(slug, faction_id):
    target_rel = request.form.get("relationship") or None
    score_offset = None
    if target_rel and target_rel in db._TIER_MIN:
        factions = db.get_factions(slug)
        faction_obj = next((f for f in factions if f["id"] == faction_id), None)
        if faction_obj:
            rel_data = db.compute_npc_relationship(faction_obj, is_dm=True)
            if rel_data.get("computed") and rel_data.get("score_natural") is not None:
                natural = rel_data["score_natural"]
                tier_floor = db._TIER_MIN[target_rel]
                score_offset = round(tier_floor - natural, 4) if natural < tier_floor else 0.0
    db.update_faction(
        slug, faction_id,
        relationship=target_rel,
        description=request.form.get("description") or None,
        score_offset=score_offset,
        role=request.form.get("role", "").strip() or None,
    )
    if request.form.get("ajax"):
        return jsonify({"ok": True})
    flash("Faction updated", "success")
    if request.form.get("next") == "dm":
        return redirect(url_for("dm_bp.dm", slug=slug))
    return redirect(url_for("player.faction", slug=slug, faction_id=faction_id))


@dm_bp.route("/<slug>/dm/faction/<faction_id>/notes", methods=["POST"])
@dm_required
def dm_edit_faction_notes(slug, faction_id):
    description = request.form.get("description", "").strip()
    dm_notes = request.form.get("dm_notes", "").strip()
    image_url = request.form.get("image_url", "").strip()
    ok, err = _allowed_image_url(image_url)
    if not ok:
        if request.form.get("ajax"):
            return jsonify({"ok": False, "error": err})
        flash(err, "error")
        return redirect(url_for("player.faction", slug=slug, faction_id=faction_id))
    db.update_faction(slug, faction_id, description=description or None, dm_notes=dm_notes if "dm_notes" in request.form else None, image_url=image_url or None)
    if request.form.get("ajax"):
        return jsonify({"ok": True})
    return redirect(url_for("player.faction", slug=slug, faction_id=faction_id))


@dm_bp.route("/<slug>/dm/faction/<faction_id>/log", methods=["POST"])
@dm_required
def dm_log_faction(slug, faction_id):
    note = request.form.get("note", "").strip()
    session_n = int(request.form.get("session") or 0)
    polarity = request.form.get("polarity") or None
    intensity = int(request.form.get("intensity") or 1)
    event_type = request.form.get("event_type", "").strip() or None
    visibility = request.form.get("visibility", "public")
    if visibility not in ("public", "restricted", "dm_only"):
        visibility = "public"
    witnesses = request.form.getlist("witnesses")
    actor_id = request.form.get("actor_id") or None
    actor_type = request.form.get("actor_type") or None
    actor_dm_only = bool(request.form.get("actor_dm_only"))
    if note:
        src_evt = db.log_faction(slug, faction_id, session_n, note, polarity=polarity,
                                 intensity=intensity, event_type=event_type, visibility=visibility,
                                 actor_id=actor_id, actor_type=actor_type, actor_dm_only=actor_dm_only)
        if polarity:
            db.apply_ripple(slug, faction_id, "faction", session_n, note, polarity, intensity,
                            event_type, visibility=visibility, source_event_id=src_evt,
                            actor_id=actor_id, actor_type=actor_type)
        if src_evt:
            for w in witnesses:
                db.reveal_event(slug, src_evt, w)
        flash("Entry added", "success")
    return redirect(url_for("player.faction", slug=slug, faction_id=faction_id))


@dm_bp.route("/<slug>/dm/quest/<quest_id>/toggle_hidden", methods=["POST"])
@dm_required
def dm_toggle_quest_hidden(slug, quest_id):
    quests = db.get_quests(slug)
    quest = next((q for q in quests if q["id"] == quest_id), None)
    if quest:
        db.set_quest_hidden(slug, quest_id, not quest.get("hidden", False))
    return redirect(url_for("player.story", slug=slug))


@dm_bp.route("/<slug>/dm/quest/<quest_id>/obj/<int:idx>/delete", methods=["POST"])
@dm_required
def dm_delete_objective(slug, quest_id, idx):
    db.delete_objective(slug, quest_id, idx)
    return redirect(url_for("player.story", slug=slug))


@dm_bp.route("/<slug>/dm/quest/<quest_id>/obj/<int:idx>/edit", methods=["POST"])
@dm_required
def dm_edit_objective(slug, quest_id, idx):
    text = request.form.get("text", "").strip()
    if text:
        db.edit_objective(slug, quest_id, idx, text)
    return redirect(url_for("player.story", slug=slug))


@dm_bp.route("/<slug>/dm/quest/<quest_id>/description", methods=["POST"])
@dm_required
def dm_edit_quest_description(slug, quest_id):
    db.edit_quest_description(slug, quest_id, request.form.get("description", "").strip())
    return redirect(url_for("player.story", slug=slug))


@dm_bp.route("/<slug>/dm/quest/<quest_id>/update", methods=["POST"])
@dm_required
def dm_update_quest(slug, quest_id):
    status = request.form.get("status", "").strip()
    note = request.form.get("note", "").strip()
    session_n = int(request.form.get("session") or 0)
    if status:
        db.set_quest_status(slug, quest_id, status)
    if note:
        db.log_quest(slug, quest_id, session_n, note)
    return redirect(url_for("player.story", slug=slug))


@dm_bp.route("/<slug>/dm/quest/<quest_id>/obj/<int:idx>/toggle", methods=["POST"])
@dm_required
def dm_toggle_objective(slug, quest_id, idx):
    quests = db.get_quests(slug)
    quest = next((q for q in quests if q["id"] == quest_id), None)
    if quest:
        current = quest.get("objectives", [])[idx].get("done", False)
        db.set_objective(slug, quest_id, idx, not current)
    return redirect(url_for("player.story", slug=slug))


@dm_bp.route("/<slug>/dm/npc/<npc_id>/relation", methods=["POST"])
@dm_required
def dm_add_npc_relation(slug, npc_id):
    db.add_npc_relation(slug, npc_id,
                        target_id=request.form.get("target_id", "").strip(),
                        target_type=request.form.get("target_type", "npc"),
                        relation=request.form.get("relation", "ally"),
                        weight=float(request.form.get("weight", 0.5)),
                        dm_only=bool(request.form.get("dm_only")))
    if request.form.get("ajax"):
        return jsonify({"ok": True})
    flash("Relation added", "success")
    if request.form.get("next") == "dm":
        return redirect(url_for("dm_bp.dm", slug=slug))
    return redirect(url_for("player.npc", slug=slug, npc_id=npc_id))


@dm_bp.route("/<slug>/dm/npc/<npc_id>/relation/<int:rel_idx>/delete", methods=["POST"])
@dm_required
def dm_remove_npc_relation(slug, npc_id, rel_idx):
    db.remove_npc_relation(slug, npc_id, rel_idx)
    if request.form.get("ajax"):
        return jsonify({"ok": True})
    if request.form.get("next") == "dm":
        return redirect(url_for("dm_bp.dm", slug=slug))
    return redirect(url_for("player.npc", slug=slug, npc_id=npc_id))


@dm_bp.route("/<slug>/dm/faction/<faction_id>/relation", methods=["POST"])
@dm_required
def dm_add_faction_relation(slug, faction_id):
    db.add_faction_relation(slug, faction_id,
                            target_id=request.form.get("target_id", "").strip(),
                            target_type=request.form.get("target_type", "faction"),
                            relation=request.form.get("relation", "ally"),
                            weight=float(request.form.get("weight", 0.5)),
                            dm_only=bool(request.form.get("dm_only")))
    if request.form.get("ajax"):
        return jsonify({"ok": True})
    flash("Relation added", "success")
    if request.form.get("next") == "dm":
        return redirect(url_for("dm_bp.dm", slug=slug))
    return redirect(url_for("player.faction", slug=slug, faction_id=faction_id))


@dm_bp.route("/<slug>/dm/faction/<faction_id>/relation/<int:rel_idx>/delete", methods=["POST"])
@dm_required
def dm_remove_faction_relation(slug, faction_id, rel_idx):
    db.remove_faction_relation(slug, faction_id, rel_idx)
    if request.form.get("ajax"):
        return jsonify({"ok": True})
    if request.form.get("next") == "dm":
        return redirect(url_for("dm_bp.dm", slug=slug))
    return redirect(url_for("player.faction", slug=slug, faction_id=faction_id))


@dm_bp.route("/<slug>/dm/location/add", methods=["POST"])
@dm_required
def dm_add_location(slug):
    name = request.form.get("name", "").strip()
    if not name:
        flash("Name required", "error")
        return redirect(url_for("dm_bp.dm", slug=slug))
    loc_id = db.add_location(slug, name,
                             role=request.form.get("role", "").strip() or None,
                             description=request.form.get("description", "").strip(),
                             hidden=bool(request.form.get("hidden")),
                             dm_notes=request.form.get("dm_notes", "").strip() or None)
    return redirect(url_for("player.location", slug=slug, location_id=loc_id))


@dm_bp.route("/<slug>/dm/location/<location_id>/toggle_hidden", methods=["POST"])
@dm_required
def dm_location_toggle_hidden(slug, location_id):
    loc = db.get_location(slug, location_id)
    if loc:
        db.set_location_hidden(slug, location_id, not loc.get("hidden", False))
    return redirect(url_for("player.location", slug=slug, location_id=location_id))


@dm_bp.route("/<slug>/dm/location/<location_id>/notes", methods=["POST"])
@dm_required
def dm_location_notes(slug, location_id):
    db.update_location(slug, location_id,
                       description=request.form.get("description", "").strip(),
                       dm_notes=request.form.get("dm_notes", "").strip() or None)
    if request.form.get("ajax"):
        return jsonify({"ok": True})
    return redirect(url_for("player.location", slug=slug, location_id=location_id))


@dm_bp.route("/<slug>/dm/location/<location_id>/edit", methods=["POST"])
@dm_required
def dm_location_edit(slug, location_id):
    db.update_location(slug, location_id,
                       name=request.form.get("name", "").strip() or None,
                       role=request.form.get("role", "").strip() or None)
    return redirect(url_for("player.location", slug=slug, location_id=location_id))


@dm_bp.route("/<slug>/dm/location/<location_id>/log", methods=["POST"])
@dm_required
def dm_location_log(slug, location_id):
    db.log_location(slug, location_id,
                    session=int(request.form.get("session", db.get_current_session(slug))),
                    note=request.form.get("note", "").strip(),
                    visibility=request.form.get("visibility", "public"),
                    polarity=request.form.get("polarity") or None,
                    intensity=int(request.form.get("intensity", 1)),
                    event_type=request.form.get("event_type", "").strip() or None,
                    actor_id=request.form.get("actor_id") or None,
                    actor_type=request.form.get("actor_type") or None)
    return redirect(url_for("player.location", slug=slug, location_id=location_id))


@dm_bp.route("/<slug>/dm/location/<location_id>/log/<int:idx>/delete", methods=["POST"])
@dm_required
def dm_location_log_delete(slug, location_id, idx):
    db.delete_location_log_entry(slug, location_id, idx)
    return redirect(url_for("player.location", slug=slug, location_id=location_id))


@dm_bp.route("/<slug>/dm/location/<location_id>/delete", methods=["POST"])
@dm_required
def dm_location_delete(slug, location_id):
    db.delete_location(slug, location_id)
    flash("Location deleted", "success")
    return redirect(url_for("player.world", slug=slug))


@dm_bp.route("/<slug>/dm/party/<party_id>/relation", methods=["POST"])
@dm_required
def dm_add_party_relation(slug, party_id):
    db.add_party_relation(slug,
                          target_id=request.form.get("target_id", "").strip(),
                          target_type=request.form.get("target_type", "faction"),
                          relation=request.form.get("relation", "ally"),
                          weight=float(request.form.get("weight", 0.5)))
    if request.form.get("ajax"):
        return jsonify({"ok": True})
    return redirect(url_for("dm_bp.dm", slug=slug))


@dm_bp.route("/<slug>/dm/party/<party_id>/relation/<int:idx>/delete", methods=["POST"])
@dm_required
def dm_remove_party_relation(slug, party_id, idx):
    db.remove_party_relation(slug, idx)
    if request.form.get("ajax"):
        return jsonify({"ok": True})
    return redirect(url_for("dm_bp.dm", slug=slug))


@dm_bp.route("/<slug>/dm/npc/<npc_id>/event/<event_id>/reveal", methods=["POST"])
@dm_required
def dm_reveal_event(slug, npc_id, event_id):
    char_name = request.form.get("char_name", "").strip()
    if char_name:
        db.reveal_event(slug, event_id, char_name)
        flash(f"Revealed to {char_name}", "success")
    return redirect(url_for("player.npc", slug=slug, npc_id=npc_id))


@dm_bp.route("/<slug>/dm/npc/<npc_id>/char_relation", methods=["POST"])
@dm_required
def dm_add_char_relation_npc(slug, npc_id):
    char_name = request.form.get("char_name", "").strip()
    relation = request.form.get("relation", "ally")
    weight = float(request.form.get("weight", 0.5))
    if char_name:
        db.add_character_relation(slug, char_name, npc_id, "npc", relation, weight)
    if request.form.get("ajax"):
        return jsonify({"ok": True})
    return redirect(url_for("player.npc", slug=slug, npc_id=npc_id))


@dm_bp.route("/<slug>/dm/npc/<npc_id>/char_relation/delete", methods=["POST"])
@dm_required
def dm_remove_char_relation_npc(slug, npc_id):
    char_name = request.form.get("char_name", "").strip()
    if char_name:
        db.remove_character_relation(slug, char_name, npc_id)
    if request.form.get("ajax"):
        return jsonify({"ok": True})
    return redirect(url_for("player.npc", slug=slug, npc_id=npc_id))


@dm_bp.route("/<slug>/dm/character/<char_name>/relation", methods=["POST"])
@dm_required
def dm_add_char_own_relation(slug, char_name):
    target_id = request.form.get("target_id", "").strip()
    target_type = request.form.get("target_type", "npc")
    relation = request.form.get("relation", "ally")
    formal_relation = request.form.get("formal_relation", "").strip() or None
    personal_relation = request.form.get("personal_relation", "").strip() or None
    weight = float(request.form.get("weight", 0.5))
    if target_id:
        db.add_character_relation(slug, char_name, target_id, target_type, relation, weight,
                                  formal_relation=formal_relation, personal_relation=personal_relation)
    if request.form.get("ajax"):
        return jsonify({"ok": True})
    next_url = request.form.get("next")
    if next_url:
        return redirect(next_url)
    return redirect(url_for("dm_bp.dm", slug=slug))


@dm_bp.route("/<slug>/dm/character/<char_name>/relation/<target_id>/delete", methods=["POST"])
@dm_required
def dm_delete_char_own_relation(slug, char_name, target_id):
    db.remove_character_relation(slug, char_name, target_id)
    if request.form.get("ajax"):
        return jsonify({"ok": True})
    next_url = request.form.get("next")
    if next_url:
        return redirect(next_url)
    return redirect(url_for("dm_bp.dm", slug=slug))


@dm_bp.route("/<slug>/dm/npc/<npc_id>/event/<event_id>/witness", methods=["POST"])
@dm_required
def dm_witness_npc_event(slug, npc_id, event_id):
    data = request.get_json()
    char_name = (data or {}).get("char_name", "").strip()
    if not char_name:
        return jsonify({"error": "char_name required"}), 400
    party = db.get_all_party_characters(slug)
    char = next((c for c in party if c["name"] == char_name), None)
    if not char:
        return jsonify({"error": "Character not found"}), 404
    if event_id in char.get("known_events", []):
        db.unreveal_event(slug, event_id, char_name)
        return jsonify({"known": False})
    else:
        db.reveal_event(slug, event_id, char_name)
        return jsonify({"known": True})


@dm_bp.route("/<slug>/dm/faction/<faction_id>/event/<event_id>/witness", methods=["POST"])
@dm_required
def dm_witness_faction_event(slug, faction_id, event_id):
    data = request.get_json()
    char_name = (data or {}).get("char_name", "").strip()
    if not char_name:
        return jsonify({"error": "char_name required"}), 400
    party = db.get_all_party_characters(slug)
    char = next((c for c in party if c["name"] == char_name), None)
    if not char:
        return jsonify({"error": "Character not found"}), 404
    if event_id in char.get("known_events", []):
        db.unreveal_event(slug, event_id, char_name)
        return jsonify({"known": False})
    else:
        db.reveal_event(slug, event_id, char_name)
        return jsonify({"known": True})


@dm_bp.route("/<slug>/dm/party/<char_name>/assign", methods=["POST"])
@dm_required
def dm_assign_character_user(slug, char_name):
    email = request.form.get("email", "").strip().lower()
    if email and "@" not in email:
        flash("Enter a valid email address.", "error")
        return redirect(url_for("dm_bp.dm", slug=slug) + "#assignment")
    db.assign_character_user(slug, char_name, email)
    flash(f"{'Assigned to ' + email if email else 'Unassigned'}", "success")
    return redirect(url_for("dm_bp.dm", slug=slug) + "#assignment")


@dm_bp.route("/<slug>/dm/character/<char_name>/update", methods=["POST"])
@char_or_dm_required
def dm_update_character(slug, char_name):
    new_name = request.form.get("name", "").strip() or None
    faction_id = request.form.get("faction_id", "").strip()
    db.update_character(
        slug, char_name,
        level=request.form.get("level") or None,
        status=request.form.get("status") or None,
        notes=request.form.get("notes"),
        new_name=new_name,
        factions=[faction_id] if faction_id else [],
    )
    flash("Character updated", "success")
    return redirect(url_for("player.party", slug=slug))


@dm_bp.route("/<slug>/dm/character/<char_name>/set_faction", methods=["POST"])
@dm_required
def dm_set_character_faction(slug, char_name):
    faction_id = request.form.get("faction_id", "").strip()
    db.update_character(slug, char_name, factions=[faction_id] if faction_id else [])
    return redirect(url_for("dm_bp.dm", slug=slug))


@dm_bp.route("/<slug>/dm/character/<char_name>/log/<event_id>/delete", methods=["POST"])
@dm_required
def dm_delete_character_log(slug, char_name, event_id):
    db.delete_log_entry_by_id(slug, char_name, "character", event_id)
    return redirect(url_for("player.party", slug=slug))


@dm_bp.route("/<slug>/dm/character/<char_name>/log/<event_id>/edit", methods=["POST"])
@dm_required
def dm_edit_character_log(slug, char_name, event_id):
    db.edit_log_entry(slug, char_name, "character", event_id,
                      note=request.form.get("note", "").strip() or None,
                      polarity=request.form.get("polarity") or None,
                      intensity=request.form.get("intensity"),
                      visibility=request.form.get("visibility"))
    if request.form.get("ajax"):
        return jsonify(ok=True)
    flash("Entry updated", "success")
    return redirect(url_for("player.party", slug=slug))


@dm_bp.route("/<slug>/dm/character/<char_name>/condition/add", methods=["POST"])
@char_or_dm_required
def dm_add_character_condition(slug, char_name):
    db.add_character_condition(
        slug, char_name,
        name=request.form.get("name", "").strip(),
        category=request.form.get("category", "other"),
        description=request.form.get("description", "").strip(),
        acquired_session=request.form.get("acquired_session") or db.get_current_session(slug),
        linked_npc_id=request.form.get("linked_npc_id") or None,
        linked_faction_id=request.form.get("linked_faction_id") or None,
        hidden=bool(request.form.get("hidden")),
    )
    return redirect(url_for("player.party", slug=slug))


@dm_bp.route("/<slug>/dm/character/<char_name>/condition/<cond_id>/resolve", methods=["POST"])
@char_or_dm_required
def dm_resolve_character_condition(slug, char_name, cond_id):
    db.resolve_character_condition(slug, char_name, cond_id)
    return redirect(request.form.get("next") or url_for("player.party", slug=slug))


@dm_bp.route("/<slug>/dm/character/<char_name>/condition/<cond_id>/toggle_hidden", methods=["POST"])
@dm_required
def dm_toggle_character_condition_hidden(slug, char_name, cond_id):
    db.toggle_character_condition_hidden(slug, char_name, cond_id)
    return redirect(request.form.get("next") or url_for("player.party", slug=slug))


@dm_bp.route("/<slug>/dm/character/<char_name>/condition/<cond_id>/delete", methods=["POST"])
@char_or_dm_required
def dm_delete_character_condition(slug, char_name, cond_id):
    db.delete_character_condition(slug, char_name, cond_id)
    return redirect(request.form.get("next") or url_for("player.party", slug=slug))


@dm_bp.route("/<slug>/npc/<npc_id>/log", methods=["POST"])
def player_log_npc(slug, npc_id):
    r = campaign_access(slug)
    if r: return r
    if not session.get("user"):
        abort(403)
    note = request.form.get("note", "").strip()
    session_n = int(request.form.get("session") or 0)
    polarity = request.form.get("polarity") or None
    intensity = int(request.form.get("intensity") or 1)
    event_type = request.form.get("event_type", "").strip() or None
    if note:
        db.log_npc(slug, npc_id, session_n, note, polarity=polarity, intensity=intensity, event_type=event_type)
        flash("Entry added", "success")
    return redirect(url_for("player.npc", slug=slug, npc_id=npc_id))


@dm_bp.route("/<slug>/character/<char_name>/notes", methods=["POST"])
def player_update_character_notes(slug, char_name):
    r = campaign_access(slug)
    if r: return r
    if not session.get("user"):
        abort(403)
    db.update_character(slug, char_name, notes=request.form.get("notes", "").strip())
    flash("Notes saved", "success")
    return redirect(url_for("player.party", slug=slug))


@dm_bp.route("/<slug>/dm/references/add", methods=["POST"])
@dm_required
def dm_add_reference(slug):
    title = request.form.get("title", "").strip()
    source = request.form.get("source", "").strip()
    notes = request.form.get("notes", "").strip()
    columns = [c.strip() for c in request.form.get("columns", "").split(",") if c.strip()]
    rows = [
        [cell.strip() for cell in line.split(",")]
        for line in request.form.get("rows", "").splitlines()
        if line.strip()
    ]
    if title:
        db.add_reference(slug, title, source, notes, columns, rows)
    return redirect(url_for("player.references", slug=slug))


@dm_bp.route("/<slug>/dm/members/add", methods=["POST"])
@login_required
@dm_required
def dm_member_add(slug):
    meta = load(slug, "campaign.json")
    if meta.get("owner") != session.get("user"):
        abort(403)
    email = request.form.get("email", "").strip().lower()
    if not email or "@" not in email:
        flash("Enter a valid email address.", "error")
        return redirect(url_for("dm_bp.dm", slug=slug) + "#players")
    # Check if a user with this email already has an account
    users = load_users()
    existing_username = next((u for u, d in users.items() if d.get("email", "").lower() == email), None)
    members = meta.get("members", [])
    if existing_username:
        if existing_username not in members and existing_username != meta.get("owner"):
            members.append(existing_username)
            meta["members"] = members
            (CAMPAIGNS / slug / "campaign.json").write_text(json.dumps(meta, indent=2))
        flash(f"Added {existing_username}.", "success")
    else:
        invited = meta.get("invited_emails", [])
        if email not in invited:
            invited.append(email)
            meta["invited_emails"] = invited
            (CAMPAIGNS / slug / "campaign.json").write_text(json.dumps(meta, indent=2))
            if mail:
                owner_display = users.get(meta.get("owner"), {}).get("display_name", "Your GM")
                join_url = f"https://rippleforge.gg/{slug}/"
                mail.send_invite(email, meta.get("name", "your campaign"), owner_display, join_url)
        flash(f"Invite sent to {email}.", "success")
    return redirect(url_for("dm_bp.dm", slug=slug) + "#players")


@dm_bp.route("/<slug>/dm/members/resend", methods=["POST"])
@login_required
@dm_required
def dm_member_resend(slug):
    meta = load(slug, "campaign.json")
    if meta.get("owner") != session.get("user"):
        abort(403)
    users = load_users()
    owner_display = users.get(meta.get("owner"), {}).get("display_name", "Your GM")
    join_url = f"https://rippleforge.gg/{slug}/"
    campaign_name = meta.get("name", "your campaign")
    # Pending invite — email posted directly
    email = request.form.get("email", "").strip().lower()
    if email and email in meta.get("invited_emails", []):
        if mail:
            mail.send_invite(email, campaign_name, owner_display, join_url)
        flash(f"Invite resent to {email}.", "success")
        return redirect(url_for("dm_bp.dm", slug=slug) + "#players")
    # Confirmed member — username posted, look up their email
    username = request.form.get("username", "").strip()
    if username and username in meta.get("members", []):
        member_email = users.get(username, {}).get("email", "")
        if member_email and mail:
            mail.send_invite(member_email, campaign_name, owner_display, join_url)
            flash(f"Invite resent to {member_email}.", "success")
        else:
            flash("No email on file for that player.", "error")
    return redirect(url_for("dm_bp.dm", slug=slug) + "#players")


@dm_bp.route("/<slug>/dm/members/remove", methods=["POST"])
@login_required
@dm_required
def dm_member_remove(slug):
    meta = load(slug, "campaign.json")
    if meta.get("owner") != session.get("user"):
        abort(403)
    username = request.form.get("username", "").strip()
    email = request.form.get("email", "").strip().lower()
    if username:
        meta["members"] = [m for m in meta.get("members", []) if m != username]
    if email:
        meta["invited_emails"] = [e for e in meta.get("invited_emails", []) if e != email]
    (CAMPAIGNS / slug / "campaign.json").write_text(json.dumps(meta, indent=2))
    return redirect(url_for("dm_bp.dm", slug=slug) + "#players")


@dm_bp.route("/<slug>/dm/share/generate", methods=["POST"])
@login_required
@dm_required
def dm_generate_share(slug):
    meta = load(slug, "campaign.json")
    if meta.get("owner") != session.get("user"):
        abort(403)
    meta["share_token"] = secrets.token_urlsafe(16)
    (CAMPAIGNS / slug / "campaign.json").write_text(json.dumps(meta, indent=2))
    return redirect(url_for("dm_bp.dm", slug=slug))


@dm_bp.route("/<slug>/dm/settings", methods=["POST"])
@login_required
@dm_required
def dm_settings(slug):
    meta = load(slug, "campaign.json")
    if meta.get("owner") != session.get("user"):
        abort(403)
    meta["name"] = request.form.get("name", "").strip() or meta["name"]
    meta["system"] = request.form.get("system", "").strip()
    meta["description"] = request.form.get("description", "").strip()
    meta["party_name"] = request.form.get("party_name", "").strip()
    meta["observer_name"] = request.form.get("observer_name", "").strip()
    new_pin = request.form.get("dm_pin", "").strip()
    if new_pin and new_pin.isdigit() and 4 <= len(new_pin) <= 8:
        meta["dm_pin"] = new_pin
    (CAMPAIGNS / slug / "campaign.json").write_text(json.dumps(meta, indent=2))
    flash("Settings saved", "success")
    return redirect(url_for("dm_bp.dm", slug=slug))


@dm_bp.route("/<slug>/dm/convert", methods=["GET", "POST"])
@login_required
@dm_required
def dm_convert(slug):
    meta = load(slug, "campaign.json")
    if meta.get("owner") != session.get("user"):
        abort(403)
    current_mode = meta.get("mode", "ttrpg")

    if request.method == "GET":
        target_mode = request.args.get("target", "ttrpg")
        if target_mode not in _BLANK_TEMPLATES or target_mode == current_mode:
            return redirect(url_for("dm_bp.dm", slug=slug))
        npcs = load(slug, "world/npcs.json").get("npcs", [])
        return render_template("dm/convert_confirm.html", slug=slug, meta=meta,
                               target_mode=target_mode, npcs=npcs)

    target_mode = request.form.get("target_mode", "")
    if target_mode not in _BLANK_TEMPLATES or target_mode == current_mode:
        flash("Invalid mode conversion.", "error")
        return redirect(url_for("dm_bp.dm", slug=slug))

    # Non-TTRPG → TTRPG: redirect to character selection step first
    if current_mode != "ttrpg" and target_mode == "ttrpg" and "party_ids" not in request.form:
        return redirect(url_for("dm_bp.dm_convert", slug=slug, target="ttrpg"))

    # Apply terminology
    tmpl = _BLANK_TEMPLATES.get(target_mode, {})
    if tmpl:
        meta["terminology"] = {k: v for k, v in tmpl.items() if k != "observer_default"}
        meta["observer_name"] = tmpl.get("observer_default", meta.get("observer_name", ""))
    else:
        meta.pop("terminology", None)
        meta["observer_name"] = "The Party"
    meta["mode"] = target_mode
    (CAMPAIGNS / slug / "campaign.json").write_text(json.dumps(meta, indent=2))

    # TTRPG → other: move party members to NPCs
    if current_mode == "ttrpg" and target_mode != "ttrpg":
        party_data = load(slug, "party.json")
        characters = party_data.get("characters", [])
        if characters:
            npc_role = tmpl.get("npc", "Character")
            world_data = load(slug, "world/npcs.json")
            world_data.setdefault("npcs", [])
            existing_ids = {n["id"] for n in world_data["npcs"]}

            # Build both lookup maps: _char_<slug> and raw name → new NPC id
            char_id_map = {}   # "_char_alekszi_cometrider" → "alekszi_cometrider"
            char_name_map = {} # "Alekszi Cometrider" → "alekszi_cometrider"
            for char in characters:
                npc_id = db.slugify(char["name"])
                char_id_map[f"_char_{npc_id}"] = npc_id
                char_name_map[char["name"]] = npc_id

            # Add new NPC entries, migrating relations from party char
            newly_added = {}  # npc_id → npc dict
            for char in characters:
                npc_id = db.slugify(char["name"])
                if npc_id in existing_ids:
                    continue
                migrated_rels = []
                for rel in char.get("relations", []):
                    new_rel = dict(rel)
                    t = rel.get("target", "")
                    if t in char_id_map:
                        new_rel["target"] = char_id_map[t]
                        new_rel["target_type"] = "npc"
                    migrated_rels.append(new_rel)
                new_npc = {
                    "id": npc_id,
                    "name": char["name"],
                    "role": npc_role,
                    "relationship": "",
                    "description": char.get("notes", ""),
                    "hidden": False,
                    "factions": [],
                    "hidden_factions": [],
                    "log": char.get("log", []),
                    "relations": migrated_rels,
                }
                world_data["npcs"].append(new_npc)
                newly_added[npc_id] = new_npc

            # Remap existing NPC relations and actor_id refs; collect back-relations
            back_rels = {}  # converted_npc_id → list of relation dicts pointing back
            for npc in world_data["npcs"]:
                if npc["id"] in newly_added:
                    continue
                for rel in npc.get("relations", []):
                    t = rel.get("target", "")
                    if t in char_id_map:
                        new_t = char_id_map[t]
                        rel["target"] = new_t
                        rel["target_type"] = "npc"
                        back_rels.setdefault(new_t, []).append({
                            "target": npc["id"],
                            "target_type": "npc",
                            "relation": rel["relation"],
                            "weight": rel.get("weight", 0.5),
                        })
                # Update actor_id in log entries: char name → NPC slug, type char → npc
                for entry in npc.get("log", []):
                    if entry.get("actor_type") == "char":
                        raw = entry.get("actor_id", "")
                        if raw in char_name_map:
                            entry["actor_id"] = char_name_map[raw]
                            entry["actor_type"] = "npc"

            # Apply back-relations to newly created NPCs
            for npc_id, backs in back_rels.items():
                npc = newly_added.get(npc_id)
                if not npc:
                    continue
                existing_targets = {r["target"] for r in npc.get("relations", [])}
                for b in backs:
                    if b["target"] not in existing_targets:
                        npc.setdefault("relations", []).append(b)
                        existing_targets.add(b["target"])

            (CAMPAIGNS / slug / "world" / "npcs.json").write_text(json.dumps(world_data, indent=2))

            factions_data = load(slug, "world/factions.json")
            for faction in factions_data.get("factions", []):
                for rel in faction.get("relations", []):
                    t = rel.get("target", "")
                    if t in char_id_map:
                        rel["target"] = char_id_map[t]
                        rel["target_type"] = "npc"
                for entry in faction.get("log", []):
                    if entry.get("actor_type") == "char":
                        raw = entry.get("actor_id", "")
                        if raw in char_name_map:
                            entry["actor_id"] = char_name_map[raw]
                            entry["actor_type"] = "npc"
            (CAMPAIGNS / slug / "world" / "factions.json").write_text(json.dumps(factions_data, indent=2))

        (CAMPAIGNS / slug / "party.json").write_text(json.dumps({"characters": []}, indent=2))

    # Other → TTRPG: add selected NPCs as party members
    elif current_mode != "ttrpg" and target_mode == "ttrpg":
        selected_ids = set(request.form.getlist("party_ids"))
        if selected_ids:
            world_data = load(slug, "world/npcs.json")
            party_data = load(slug, "party.json")
            party_data.setdefault("characters", [])
            existing_names = {c["name"] for c in party_data["characters"]}
            for npc in world_data.get("npcs", []):
                if npc["id"] in selected_ids and npc["name"] not in existing_names:
                    party_data["characters"].append({
                        "name": npc["name"],
                        "race": "",
                        "class": "",
                        "level": 1,
                        "status": "active",
                        "hidden": False,
                        "notes": npc.get("description", ""),
                        "known_events": [],
                        "relations": npc.get("relations", []),
                    })
            (CAMPAIGNS / slug / "party.json").write_text(json.dumps(party_data, indent=2))

    mode_labels = {"ttrpg": "TTRPG", "fiction": "Fiction", "historical": "Historical"}
    flash(f"World converted to {mode_labels.get(target_mode, target_mode)} mode.", "success")
    return redirect(url_for("dm_bp.dm", slug=slug))


@dm_bp.route("/<slug>/dm/set_observer", methods=["POST"])
@dm_required
def dm_set_observer(slug):
    meta = load(slug, "campaign.json")
    observer = request.form.get("observer_name", "").strip()
    if observer:
        meta["observer_name"] = observer
        (CAMPAIGNS / slug / "campaign.json").write_text(json.dumps(meta, indent=2))
    return redirect(url_for("dm_bp.dm", slug=slug))


@dm_bp.route("/<slug>/dm/delete", methods=["POST"])
@login_required
@dm_required
def dm_delete_campaign(slug):
    meta = load(slug, "campaign.json")
    if meta.get("owner") != session.get("user"):
        abort(403)
    if meta.get("demo"):
        flash("Starter content cannot be deleted.", "error")
        return redirect(url_for("dm_bp.dm", slug=slug))
    if request.form.get("confirm_name", "").strip() != meta.get("name", ""):
        flash("Campaign name didn't match — not deleted.", "error")
        return redirect(url_for("dm_bp.dm", slug=slug))
    shutil.rmtree(str(CAMPAIGNS / slug))
    session.pop(f"dm_{slug}", None)
    flash("Campaign deleted.", "success")
    return redirect(url_for("player.index"))


@dm_bp.route("/<slug>/dm/transfer", methods=["POST"])
@login_required
@dm_required
def dm_transfer_initiate(slug):
    meta = load(slug, "campaign.json")
    if meta.get("owner") != session.get("user"):
        abort(403)
    email = request.form.get("email", "").strip().lower()
    if not email:
        flash("Enter the recipient's Gmail address.", "error")
        return redirect(url_for("dm_bp.dm", slug=slug))
    users = load_users()
    sender_email = users.get(session["user"], {}).get("email", "").lower()
    if email == sender_email:
        flash("You can't transfer a world to yourself.", "error")
        return redirect(url_for("dm_bp.dm", slug=slug))
    to_username = next((u for u, d in users.items() if d.get("email", "").lower() == email), None)
    if not to_username:
        flash("No RippleForge account found for that address.", "error")
        return redirect(url_for("dm_bp.dm", slug=slug))
    sender = users.get(session["user"], {})
    meta["pending_transfer"] = {
        "to_username": to_username,
        "to_email": email,
        "from_display_name": sender.get("display_name") or session["user"],
        "initiated_at": datetime.datetime.utcnow().isoformat(),
    }
    (CAMPAIGNS / slug / "campaign.json").write_text(json.dumps(meta, indent=2))
    flash(f"Transfer request sent to {email}. World is locked until they accept or you cancel.", "success")
    return redirect(url_for("dm_bp.dm", slug=slug))


@dm_bp.route("/<slug>/dm/transfer/cancel", methods=["POST"])
@login_required
@dm_required
def dm_transfer_cancel(slug):
    meta = load(slug, "campaign.json")
    if meta.get("owner") != session.get("user"):
        abort(403)
    meta.pop("pending_transfer", None)
    (CAMPAIGNS / slug / "campaign.json").write_text(json.dumps(meta, indent=2))
    flash("Transfer cancelled. World is unlocked.", "success")
    return redirect(url_for("dm_bp.dm", slug=slug))


@dm_bp.route("/<slug>/dm/npc/<npc_id>/collapse_into", methods=["POST"])
@login_required
@dm_required
def dm_collapse_npc(slug, npc_id):
    target_id = request.form.get("target_id", "").strip()
    if not target_id or target_id == npc_id:
        flash("Select a different character to collapse into.", "error")
        return redirect(url_for("dm_bp.dm", slug=slug))
    ok = db.collapse_npc_into(slug, npc_id, target_id)
    if not ok:
        flash("Collapse failed — one of the characters wasn't found.", "error")
        return redirect(url_for("dm_bp.dm", slug=slug))
    target_npcs = db.get_npcs(slug, include_hidden=True)
    target = next((n for n in target_npcs if n["id"] == target_id), None)
    tname = target["name"] if target else target_id
    flash(f"Collapsed into {tname}. All history merged.", "success")
    return redirect(url_for("player.world", slug=slug))


@dm_bp.route("/<slug>/dm/npc/<npc_id>/join_party", methods=["POST"])
@login_required
@dm_required
def dm_npc_join_party(slug, npc_id):
    char_name = request.form.get("char_name", "").strip()
    if not char_name:
        flash("Select a party character to merge into.", "error")
        return redirect(url_for("player.npc", slug=slug, npc_id=npc_id))
    ok = db.npc_join_party(slug, npc_id, char_name)
    if not ok:
        flash("Join party failed — NPC or character not found.", "error")
        return redirect(url_for("player.npc", slug=slug, npc_id=npc_id))
    flash(f"Merged into {char_name}. Full history transferred.", "success")
    return redirect(url_for("player.party", slug=slug))


@dm_bp.route("/<slug>/dm/npc/<npc_id>/join_party_new", methods=["POST"])
@login_required
@dm_required
def dm_npc_join_party_new(slug, npc_id):
    npcs = db.get_npcs(slug, include_hidden=True)
    npc = next((n for n in npcs if n["id"] == npc_id), None)
    if not npc:
        flash("NPC not found.", "error")
        return redirect(url_for("dm_bp.dm", slug=slug))
    char_name = npc["name"]
    ok = db.npc_to_party_member(slug, npc_id)
    if not ok:
        flash("Conversion failed.", "error")
        return redirect(url_for("dm_bp.dm", slug=slug))
    flash(f"{char_name} joined the party. Full history transferred.", "success")
    return redirect(url_for("player.party", slug=slug))


# ── Admin routes ──────────────────────────────────────────────────────────────

