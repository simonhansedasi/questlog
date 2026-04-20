from flask import Flask, render_template, abort, redirect, url_for, request, session, Response, jsonify, flash
from markupsafe import Markup
from werkzeug.security import check_password_hash
from functools import wraps
from pathlib import Path
import json
import os
import sys
import secrets
import shutil
import datetime
import markdown

sys.path.insert(0, str(Path(__file__).parent))
from src import data as db
from src import ai

from dotenv import load_dotenv
load_dotenv()


class PrefixMiddleware:
    def __init__(self, app, prefix):
        self.app = app
        self.prefix = prefix

    def __call__(self, environ, start_response):
        environ["SCRIPT_NAME"] = self.prefix
        return self.app(environ, start_response)


app = Flask(__name__)
app.secret_key = os.environ.get("QUESTBOOK_SECRET", "change-me-in-production")
_prefix = os.environ.get("QUESTBOOK_PREFIX", "")
if _prefix:
    app.wsgi_app = PrefixMiddleware(app.wsgi_app, _prefix)
CAMPAIGNS = Path(__file__).parent / "campaigns"
USERS_FILE = Path(__file__).parent / "users.json"

@app.template_filter("compute_rel")
def compute_rel_filter(npc):
    return db.compute_npc_relationship(npc)


def load_users():
    if not USERS_FILE.exists():
        return {}
    return json.loads(USERS_FILE.read_text()).get("users", {})


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("user"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


def campaign_access(slug):
    """Allow access if: logged-in owner, logged-in user with share link, or share link viewer."""
    meta = load(slug, "campaign.json")
    owner = meta.get("owner")
    if session.get("user"):
        if owner and session.get("user") != owner:
            # Non-owner accounts must have visited the share link
            if not session.get(f"view_{slug}"):
                abort(403)
        return
    # Read-only via share token (no account)
    if session.get(f"view_{slug}"):
        return
    # No access
    return redirect(url_for("login"))


def dm_required(f):
    @wraps(f)
    def decorated(slug, *args, **kwargs):
        if not session.get(f"dm_{slug}"):
            return redirect(url_for("dm_login", slug=slug))
        return f(slug, *args, **kwargs)
    return decorated


def load(slug, *parts):
    p = CAMPAIGNS / slug / Path(*parts)
    if not p.exists():
        return {}
    return json.loads(p.read_text())


def campaigns():
    return [
        json.loads((d / "campaign.json").read_text())
        for d in sorted(CAMPAIGNS.iterdir())
        if d.is_dir() and (d / "campaign.json").exists()
    ]


# ── Auth routes ───────────────────────────────────────────────────────────────

@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user"):
        return redirect(url_for("index"))
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "")
        users = load_users()
        user = users.get(username)
        if user and check_password_hash(user["password_hash"], password):
            session["user"] = username
            session["display_name"] = user.get("display_name", username)
            return redirect(url_for("index"))
        error = "Invalid username or password."
    return render_template("login.html", error=error)


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))


# ── Public routes ─────────────────────────────────────────────────────────────

@app.route("/")
@login_required
def index():
    username = session["user"]
    all_campaigns = campaigns()
    my_campaigns = [c for c in all_campaigns if c.get("owner") == username]
    demo_campaigns = [c for c in all_campaigns if c.get("demo")]
    return render_template("index.html", my_campaigns=my_campaigns, demo_campaigns=demo_campaigns)


@app.route("/demo/<slug>/clone", methods=["POST"])
@login_required
def clone_campaign(slug):
    src = CAMPAIGNS / slug
    if not src.exists():
        abort(404)
    meta = json.loads((src / "campaign.json").read_text())
    if not meta.get("demo"):
        abort(403)
    unique_id = secrets.token_hex(3)
    new_slug = f"{slug}-{unique_id}"
    dst = CAMPAIGNS / new_slug
    shutil.copytree(str(src), str(dst))
    new_meta = json.loads((dst / "campaign.json").read_text())
    new_meta["slug"] = new_slug
    new_meta["owner"] = session["user"]
    new_meta.pop("demo", None)
    pin = request.form.get("dm_pin", "").strip()
    new_meta["dm_pin"] = pin if pin else str(secrets.randbelow(9000) + 1000)
    new_meta["created"] = datetime.date.today().isoformat()
    (dst / "campaign.json").write_text(json.dumps(new_meta, indent=2))
    session[f"dm_{new_slug}"] = True
    return redirect(url_for("dm", slug=new_slug))


@app.route("/<slug>/")
def campaign(slug):
    r = campaign_access(slug)
    if r: return r
    meta = load(slug, "campaign.json")
    if not meta:
        abort(404)
    is_dm = bool(session.get(f"dm_{slug}"))
    party = db.get_party(slug, include_hidden=is_dm)
    quests = db.get_quests(slug, include_hidden=is_dm)
    active = [q for q in quests if q["status"] == "active"]
    journal_entries = db.get_journal(slug)
    latest_journal = None
    if journal_entries:
        e = journal_entries[-1]
        latest_journal = {**e, "recap_html": Markup(markdown.markdown(e.get("recap", ""), extensions=["nl2br"]))}
    npcs = db.get_npcs(slug, include_hidden=is_dm)
    factions = db.get_factions(slug, include_hidden=is_dm)
    current_session = db.get_current_session(slug)
    return render_template("campaign.html", meta=meta, party=party, active=active, slug=slug,
                           latest_journal=latest_journal,
                           current_session=current_session,
                           recent_entities=db.get_recent_entities(slug, current_session),
                           npc_count=len(npcs), faction_count=len(factions))


@app.route("/<slug>/party")
def party(slug):
    r = campaign_access(slug)
    if r: return r
    meta = load(slug, "campaign.json")
    is_dm = bool(session.get(f"dm_{slug}"))
    is_player = bool(session.get("user")) and not is_dm
    characters = db.get_party(slug, include_hidden=is_dm)
    return render_template("party.html", meta=meta, characters=characters, slug=slug,
                           is_player=is_player)


@app.route("/<slug>/assets")
def assets(slug):
    r = campaign_access(slug)
    if r: return r
    meta = load(slug, "campaign.json")
    data = db.get_assets(slug)
    stronghold = db.get_stronghold(slug)
    return render_template("assets.html", meta=meta, assets=data, stronghold=stronghold, slug=slug)


@app.route("/<slug>/world")
def world(slug):
    r = campaign_access(slug)
    if r: return r
    meta = load(slug, "campaign.json")
    is_dm = bool(session.get(f"dm_{slug}"))
    npcs = db.get_npcs(slug, include_hidden=is_dm)
    factions = db.get_factions(slug, include_hidden=is_dm)
    return render_template("world.html", meta=meta, npcs=npcs, factions=factions, slug=slug)


@app.route("/<slug>/world/npc/<npc_id>")
def npc(slug, npc_id):
    r = campaign_access(slug)
    if r: return r
    meta = load(slug, "campaign.json")
    is_dm = bool(session.get(f"dm_{slug}"))
    is_player = bool(session.get("user")) and not is_dm
    npc = next((n for n in db.get_npcs(slug, include_hidden=is_dm) if n["id"] == npc_id), None)
    if not npc:
        abort(404)
    rel_data = db.compute_npc_relationship(npc)
    return render_template("npc.html", meta=meta, npc=npc, slug=slug,
                           is_player=is_player, current_session=db.get_current_session(slug),
                           rel_data=rel_data)


@app.route("/<slug>/world/faction/<faction_id>")
def faction(slug, faction_id):
    r = campaign_access(slug)
    if r: return r
    meta = load(slug, "campaign.json")
    is_dm = bool(session.get(f"dm_{slug}"))
    faction = next((f for f in db.get_factions(slug, include_hidden=is_dm) if f["id"] == faction_id), None)
    if not faction:
        abort(404)
    return render_template("faction.html", meta=meta, faction=faction, slug=slug)


@app.route("/<slug>/story")
def story(slug):
    r = campaign_access(slug)
    if r: return r
    meta = load(slug, "campaign.json")
    is_dm = bool(session.get(f"dm_{slug}"))
    quests = db.get_quests(slug, include_hidden=is_dm)
    return render_template("story.html", meta=meta, quests=quests, slug=slug)


@app.route("/<slug>/journal")
def journal(slug):
    r = campaign_access(slug)
    if r: return r
    meta = load(slug, "campaign.json")
    is_dm = bool(session.get(f"dm_{slug}"))
    entries = db.get_journal(slug)
    entries_rendered = [
        {**e, "idx": i, "recap_html": Markup(markdown.markdown(e.get("recap", ""), extensions=["nl2br"]))}
        for i, e in reversed(list(enumerate(entries)))
    ]
    return render_template("journal.html", meta=meta, slug=slug, is_dm=is_dm, entries=entries_rendered)


@app.route("/<slug>/dm/journal/post", methods=["POST"])
@dm_required
def dm_post_journal(slug):
    session_n = int(request.form.get("session") or 0)
    date = request.form.get("date", "").strip() or datetime.date.today().isoformat()
    recap = request.form.get("recap", "").strip()
    if recap:
        db.post_journal(slug, session_n, date, recap)
        flash("Posted to journal", "success")
    return redirect(url_for("journal", slug=slug))


@app.route("/<slug>/dm/journal/<int:idx>/delete", methods=["POST"])
@dm_required
def dm_delete_journal(slug, idx):
    db.delete_journal_entry(slug, idx)
    return redirect(url_for("journal", slug=slug))


@app.route("/<slug>/references")
def references(slug):
    r = campaign_access(slug)
    if r: return r
    meta = load(slug, "campaign.json")
    if not meta:
        abort(404)
    return render_template("references.html", slug=slug, meta=meta,
                           references=db.get_references(slug))


# ── Share link ────────────────────────────────────────────────────────────────

@app.route("/share/<token>")
def share(token):
    for d in CAMPAIGNS.iterdir():
        if not d.is_dir() or not (d / "campaign.json").exists():
            continue
        meta = json.loads((d / "campaign.json").read_text())
        if meta.get("share_token") == token:
            slug = meta["slug"]
            session[f"view_{slug}"] = True
            return redirect(url_for("campaign", slug=slug))
    abort(404)


# ── DM auth ───────────────────────────────────────────────────────────────────

@app.route("/<slug>/dm/login", methods=["GET", "POST"])
@login_required
def dm_login(slug):
    campaign_access(slug)
    meta = load(slug, "campaign.json")
    if not meta:
        abort(404)
    error = None
    if request.method == "POST":
        pin = request.form.get("pin", "").strip()
        if pin == str(meta.get("dm_pin", "")):
            session[f"dm_{slug}"] = True
            return redirect(url_for("dm", slug=slug))
        error = "Incorrect PIN."
    return render_template("dm/login.html", meta=meta, slug=slug, error=error)


@app.route("/<slug>/dm/logout", methods=["POST"])
def dm_logout(slug):
    session.pop(f"dm_{slug}", None)
    return redirect(url_for("campaign", slug=slug))


# ── DM routes ─────────────────────────────────────────────────────────────────

@app.route("/<slug>/api/revision")
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


@app.route("/<slug>/brief")
def brief(slug):
    r = campaign_access(slug)
    if r: return r
    meta = load(slug, "campaign.json")
    is_dm = bool(session.get(f"dm_{slug}"))
    current_session = db.get_current_session(slug)
    quests = db.get_quests(slug, include_hidden=is_dm) if not is_dm else []
    active_quests = [q for q in quests if q.get("status") == "active"] if not is_dm else []
    return render_template("brief.html", meta=meta, slug=slug,
                           is_dm=is_dm,
                           current_session=current_session,
                           hot=db.get_recent_entities(slug, current_session,
                                                      include_hidden=is_dm),
                           cold=db.get_neglected_entities(slug, current_session) if is_dm else [],
                           shifts=db.get_relationship_shifts(slug, current_session,
                                                             include_hidden=is_dm),
                           active_quests=active_quests)


@app.route("/<slug>/dm")
@dm_required
def dm(slug):
    meta = load(slug, "campaign.json")
    if not meta:
        abort(404)
    raw_plan = db.get_session_plan(slug)
    plan_html = Markup(markdown.markdown(raw_plan, extensions=["nl2br"])) if raw_plan else None
    current_session = db.get_current_session(slug)
    return render_template("dm/index.html", meta=meta, slug=slug,
                           session_plan=raw_plan, plan_html=plan_html,
                           session_notes=db.get_session_notes(slug),
                           npcs=db.get_npcs(slug),
                           factions=db.get_factions(slug),
                           party=db.get_party(slug),
                           current_session=current_session,
                           recent_entities=db.get_recent_entities(slug, current_session),
                           assets=db.get_assets(slug))


@app.route("/<slug>/dm/log/quick", methods=["POST"])
@dm_required
def dm_quick_log(slug):
    entity = request.form.get("entity", "")
    note = request.form.get("note", "").strip()
    polarity = request.form.get("polarity") or None
    intensity = int(request.form.get("intensity") or 1)
    event_type = request.form.get("event_type", "").strip() or None
    session_n = int(request.form.get("session") or 0)
    if ":" in entity:
        entity_type, entity_id = entity.split(":", 1)
        if entity_type == "npc" and note:
            db.log_npc(slug, entity_id, session_n, note, polarity=polarity, intensity=intensity, event_type=event_type)
            flash("Logged", "success")
        elif entity_type == "faction" and note:
            db.log_faction(slug, entity_id, session_n, note)
            flash("Logged", "success")
    return redirect(url_for("dm", slug=slug))


@app.route("/<slug>/dm/session/plan", methods=["POST"])
@dm_required
def dm_set_session_plan(slug):
    db.set_session_plan(slug, request.form.get("plan", ""))
    flash("Plan saved", "success")
    return redirect(url_for("dm", slug=slug))


@app.route("/<slug>/dm/session/notes", methods=["POST"])
@dm_required
def dm_set_session_notes(slug):
    db.set_session_notes(slug, request.form.get("notes", ""))
    flash("Notes saved", "success")
    return redirect(url_for("dm", slug=slug))


@app.route("/<slug>/dm/session/recap", methods=["POST"])
@dm_required
def dm_generate_recap(slug):
    meta = load(slug, "campaign.json")
    notes = db.get_session_notes(slug)
    if not notes or not notes.strip():
        return jsonify({"error": "No session notes to summarize."}), 400
    quests = db.get_quests(slug, include_hidden=True)
    npcs = db.get_npcs(slug, include_hidden=False)
    try:
        recap = ai.generate_recap(notes, meta.get("name", ""), quests, npcs)
        return jsonify({"recap": recap})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/<slug>/dm/session/notes/export")
@dm_required
def dm_export_notes(slug):
    notes = db.get_session_notes(slug)
    return Response(
        notes,
        mimetype="text/markdown",
        headers={"Content-Disposition": f"attachment; filename={slug}_session_notes.md"}
    )


@app.route("/<slug>/dm/log", methods=["GET", "POST"])
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
        return redirect(url_for("dm", slug=slug))

    return render_template("dm/log.html", meta=meta, slug=slug,
                           npcs=npcs, factions=factions, quests=quests)


@app.route("/<slug>/dm/npcs/add", methods=["GET", "POST"])
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
        )
        return redirect(url_for("dm", slug=slug))
    return render_template("dm/add_npc.html", meta=meta, slug=slug)


@app.route("/<slug>/dm/factions/add", methods=["GET", "POST"])
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
        )
        return redirect(url_for("dm", slug=slug))
    return render_template("dm/add_faction.html", meta=meta, slug=slug)


@app.route("/<slug>/dm/quests/add", methods=["GET", "POST"])
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
        return redirect(url_for("dm", slug=slug))
    return render_template("dm/add_quest.html", meta=meta, slug=slug)


@app.route("/<slug>/dm/quests/<quest_id>/objective", methods=["POST"])
@dm_required
def dm_add_objective(slug, quest_id):
    text = request.form.get("text", "").strip()
    if text:
        db.add_objective(slug, quest_id, text)
    return redirect(url_for("story", slug=slug))


@app.route("/<slug>/dm/party/add", methods=["GET", "POST"])
@dm_required
def dm_add_character(slug):
    meta = load(slug, "campaign.json")
    if request.method == "POST":
        db.add_character(
            slug,
            name=request.form["name"].strip(),
            race=request.form.get("race", "").strip(),
            char_class=request.form.get("char_class", "").strip(),
            level=request.form.get("level", 1),
            notes=request.form.get("notes", "").strip(),
            hidden="hidden" in request.form,
        )
        return redirect(url_for("dm", slug=slug))
    return render_template("dm/add_character.html", meta=meta, slug=slug)


@app.route("/<slug>/assets/currency", methods=["POST"])
def set_currency(slug):
    r = campaign_access(slug)
    if r: return r
    db.set_currency(slug, request.form.get("key", "gold").strip(), request.form.get("amount", 0))
    return redirect(url_for("assets", slug=slug))


@app.route("/<slug>/assets/item", methods=["POST"])
def add_item(slug):
    r = campaign_access(slug)
    if r: return r
    name = request.form.get("name", "").strip()
    if name:
        db.add_item(slug, name, request.form.get("notes", "").strip())
    return redirect(url_for("assets", slug=slug))


@app.route("/<slug>/assets/item/<int:idx>/remove", methods=["POST"])
def remove_item(slug, idx):
    r = campaign_access(slug)
    if r: return r
    db.remove_item(slug, idx)
    return redirect(url_for("assets", slug=slug))




@app.route("/<slug>/dm/assets/ship", methods=["POST"])
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
    return redirect(url_for("assets", slug=slug))


@app.route("/<slug>/dm/assets/stronghold", methods=["POST"])
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
    return redirect(url_for("assets", slug=slug))


@app.route("/<slug>/dm/assets/stronghold/feature", methods=["POST"])
@dm_required
def dm_add_stronghold_feature(slug):
    text = request.form.get("text", "").strip()
    if text:
        db.add_stronghold_feature(slug, text)
    return redirect(url_for("assets", slug=slug))


@app.route("/<slug>/dm/assets/stronghold/feature/<int:idx>/remove", methods=["POST"])
@dm_required
def dm_remove_stronghold_feature(slug, idx):
    db.remove_stronghold_feature(slug, idx)
    return redirect(url_for("assets", slug=slug))


@app.route("/<slug>/dm/assets/stronghold/upgrade", methods=["POST"])
@dm_required
def dm_add_stronghold_upgrade(slug):
    text = request.form.get("text", "").strip()
    if text:
        db.add_stronghold_upgrade(slug, text)
    return redirect(url_for("assets", slug=slug))


@app.route("/<slug>/dm/assets/stronghold/upgrade/<int:idx>/remove", methods=["POST"])
@dm_required
def dm_remove_stronghold_upgrade(slug, idx):
    db.remove_stronghold_upgrade(slug, idx)
    return redirect(url_for("assets", slug=slug))


@app.route("/<slug>/dm/assets/stronghold/delete", methods=["POST"])
@dm_required
def dm_delete_stronghold(slug):
    db.delete_stronghold(slug)
    return redirect(url_for("assets", slug=slug))


@app.route("/<slug>/dm/assets/ship/<int:ship_idx>/edit", methods=["POST"])
@dm_required
def dm_edit_ship(slug, ship_idx):
    db.update_ship(slug, ship_idx,
        name=request.form.get("name", "").strip(),
        kind=request.form.get("type", "").strip(),
        hp=request.form.get("hp", "").strip(),
        notes=request.form.get("notes", "").strip())
    return redirect(url_for("assets", slug=slug))


@app.route("/<slug>/dm/assets/ship/<int:ship_idx>/crew", methods=["POST"])
@dm_required
def dm_add_crew(slug, ship_idx):
    member = request.form.get("member", "").strip()
    if member:
        db.add_crew(slug, ship_idx, member)
    return redirect(url_for("assets", slug=slug))


@app.route("/<slug>/dm/assets/ship/<int:ship_idx>/crew/<int:crew_idx>/remove", methods=["POST"])
@dm_required
def dm_remove_crew(slug, ship_idx, crew_idx):
    db.remove_crew(slug, ship_idx, crew_idx)
    return redirect(url_for("assets", slug=slug))


@app.route("/<slug>/dm/assets/ship/<int:ship_idx>/cargo", methods=["POST"])
@dm_required
def dm_add_cargo(slug, ship_idx):
    item = request.form.get("item", "").strip()
    if item:
        db.add_cargo(slug, ship_idx, item)
    return redirect(url_for("assets", slug=slug))


@app.route("/<slug>/dm/assets/ship/<int:ship_idx>/cargo/<int:cargo_idx>/remove", methods=["POST"])
@dm_required
def dm_remove_cargo(slug, ship_idx, cargo_idx):
    db.remove_cargo(slug, ship_idx, cargo_idx)
    return redirect(url_for("assets", slug=slug))


@app.route("/<slug>/dm/assets/ship/<int:ship_idx>/delete", methods=["POST"])
@dm_required
def dm_delete_ship(slug, ship_idx):
    db.delete_ship(slug, ship_idx)
    return redirect(url_for("assets", slug=slug))


@app.route("/<slug>/dm/assets/ship/<int:ship_idx>/weapon", methods=["POST"])
@dm_required
def dm_add_weapon(slug, ship_idx):
    name = request.form.get("name", "").strip()
    max_hp = int(request.form.get("max_hp") or 50)
    if name:
        db.add_weapon(slug, ship_idx, name, max_hp)
    return redirect(url_for("assets", slug=slug))


@app.route("/<slug>/assets/ship/<int:ship_idx>/weapon/<int:weapon_idx>/hp", methods=["POST"])
def set_weapon_hp(slug, ship_idx, weapon_idx):
    hp = request.form.get("hp", "0")
    try:
        db.set_weapon_hp(slug, ship_idx, weapon_idx, int(hp))
    except ValueError:
        pass
    return redirect(url_for("assets", slug=slug))


# ── DM inline edit routes ─────────────────────────────────────────────────────

@app.route("/<slug>/dm/npc/<npc_id>/delete", methods=["POST"])
@dm_required
def dm_delete_npc(slug, npc_id):
    db.delete_npc(slug, npc_id)
    return redirect(url_for("world", slug=slug))


@app.route("/<slug>/dm/faction/<faction_id>/delete", methods=["POST"])
@dm_required
def dm_delete_faction(slug, faction_id):
    db.delete_faction(slug, faction_id)
    return redirect(url_for("world", slug=slug))


@app.route("/<slug>/dm/quest/<quest_id>/delete", methods=["POST"])
@dm_required
def dm_delete_quest(slug, quest_id):
    db.delete_quest(slug, quest_id)
    return redirect(url_for("story", slug=slug))


@app.route("/<slug>/dm/character/<char_name>/delete", methods=["POST"])
@dm_required
def dm_delete_character(slug, char_name):
    db.delete_character(slug, char_name)
    return redirect(url_for("party", slug=slug))


@app.route("/<slug>/dm/references/<ref_id>/delete", methods=["POST"])
@dm_required
def dm_delete_reference(slug, ref_id):
    db.delete_reference(slug, ref_id)
    return redirect(url_for("references", slug=slug))


@app.route("/<slug>/dm/assets/ship/<int:ship_idx>/weapon/<int:weapon_idx>/delete", methods=["POST"])
@dm_required
def dm_delete_weapon(slug, ship_idx, weapon_idx):
    db.delete_weapon(slug, ship_idx, weapon_idx)
    return redirect(url_for("assets", slug=slug))


@app.route("/<slug>/dm/npc/<npc_id>/log/<int:idx>/delete", methods=["POST"])
@dm_required
def dm_delete_npc_log(slug, npc_id, idx):
    db.delete_npc_log_entry(slug, npc_id, idx)
    return redirect(url_for("npc", slug=slug, npc_id=npc_id))


@app.route("/<slug>/dm/faction/<faction_id>/log/<int:idx>/delete", methods=["POST"])
@dm_required
def dm_delete_faction_log(slug, faction_id, idx):
    db.delete_faction_log_entry(slug, faction_id, idx)
    return redirect(url_for("faction", slug=slug, faction_id=faction_id))


@app.route("/<slug>/dm/quest/<quest_id>/log/<int:idx>/delete", methods=["POST"])
@dm_required
def dm_delete_quest_log(slug, quest_id, idx):
    db.delete_quest_log_entry(slug, quest_id, idx)
    return redirect(url_for("story", slug=slug))


@app.route("/<slug>/dm/character/<char_name>/toggle_hidden", methods=["POST"])
@dm_required
def dm_toggle_character_hidden(slug, char_name):
    chars = db.get_party(slug)
    char = next((c for c in chars if c["name"] == char_name), None)
    if char:
        db.set_character_hidden(slug, char_name, not char.get("hidden", False))
    if request.form.get("next") == "dm":
        return redirect(url_for("dm", slug=slug))
    return redirect(url_for("party", slug=slug))


@app.route("/<slug>/dm/assets/property", methods=["POST"])
@dm_required
def dm_add_property(slug):
    name = request.form.get("name", "").strip()
    if name:
        db.add_property(slug, name, request.form.get("notes", "").strip())
    return redirect(url_for("assets", slug=slug))


@app.route("/<slug>/dm/assets/property/<int:idx>/remove", methods=["POST"])
@dm_required
def dm_remove_property(slug, idx):
    db.remove_property(slug, idx)
    return redirect(url_for("assets", slug=slug))


@app.route("/<slug>/dm/npc/<npc_id>/toggle_hidden", methods=["POST"])
@dm_required
def dm_toggle_npc_hidden(slug, npc_id):
    npcs = db.get_npcs(slug)
    npc = next((n for n in npcs if n["id"] == npc_id), None)
    if npc:
        db.set_npc_hidden(slug, npc_id, not npc.get("hidden", False))
    if request.form.get("next") == "dm":
        return redirect(url_for("dm", slug=slug))
    return redirect(url_for("npc", slug=slug, npc_id=npc_id))


@app.route("/<slug>/dm/npc/<npc_id>/edit", methods=["POST"])
@dm_required
def dm_edit_npc(slug, npc_id):
    db.update_npc(
        slug, npc_id,
        relationship=request.form.get("relationship") or None,
        description=request.form.get("description") or None,
    )
    flash("NPC updated", "success")
    return redirect(url_for("npc", slug=slug, npc_id=npc_id))


@app.route("/<slug>/dm/npc/<npc_id>/log", methods=["POST"])
@dm_required
def dm_log_npc(slug, npc_id):
    note = request.form.get("note", "").strip()
    session_n = int(request.form.get("session") or 0)
    polarity = request.form.get("polarity") or None
    intensity = int(request.form.get("intensity") or 1)
    event_type = request.form.get("event_type", "").strip() or None
    if note:
        db.log_npc(slug, npc_id, session_n, note, polarity=polarity, intensity=intensity, event_type=event_type)
        flash("Entry added", "success")
    return redirect(url_for("npc", slug=slug, npc_id=npc_id))


@app.route("/<slug>/dm/faction/<faction_id>/toggle_hidden", methods=["POST"])
@dm_required
def dm_toggle_faction_hidden(slug, faction_id):
    factions = db.get_factions(slug)
    faction = next((f for f in factions if f["id"] == faction_id), None)
    if faction:
        db.set_faction_hidden(slug, faction_id, not faction.get("hidden", False))
    if request.form.get("next") == "dm":
        return redirect(url_for("dm", slug=slug))
    return redirect(url_for("faction", slug=slug, faction_id=faction_id))


@app.route("/<slug>/dm/faction/<faction_id>/edit", methods=["POST"])
@dm_required
def dm_edit_faction(slug, faction_id):
    db.update_faction(
        slug, faction_id,
        relationship=request.form.get("relationship") or None,
        description=request.form.get("description") or None,
    )
    return redirect(url_for("faction", slug=slug, faction_id=faction_id))


@app.route("/<slug>/dm/faction/<faction_id>/log", methods=["POST"])
@dm_required
def dm_log_faction(slug, faction_id):
    note = request.form.get("note", "").strip()
    session_n = int(request.form.get("session") or 0)
    if note:
        db.log_faction(slug, faction_id, session_n, note)
    return redirect(url_for("faction", slug=slug, faction_id=faction_id))


@app.route("/<slug>/dm/quest/<quest_id>/toggle_hidden", methods=["POST"])
@dm_required
def dm_toggle_quest_hidden(slug, quest_id):
    quests = db.get_quests(slug)
    quest = next((q for q in quests if q["id"] == quest_id), None)
    if quest:
        db.set_quest_hidden(slug, quest_id, not quest.get("hidden", False))
    return redirect(url_for("story", slug=slug))


@app.route("/<slug>/dm/quest/<quest_id>/obj/<int:idx>/delete", methods=["POST"])
@dm_required
def dm_delete_objective(slug, quest_id, idx):
    db.delete_objective(slug, quest_id, idx)
    return redirect(url_for("story", slug=slug))


@app.route("/<slug>/dm/quest/<quest_id>/obj/<int:idx>/edit", methods=["POST"])
@dm_required
def dm_edit_objective(slug, quest_id, idx):
    text = request.form.get("text", "").strip()
    if text:
        db.edit_objective(slug, quest_id, idx, text)
    return redirect(url_for("story", slug=slug))


@app.route("/<slug>/dm/quest/<quest_id>/description", methods=["POST"])
@dm_required
def dm_edit_quest_description(slug, quest_id):
    db.edit_quest_description(slug, quest_id, request.form.get("description", "").strip())
    return redirect(url_for("story", slug=slug))


@app.route("/<slug>/dm/quest/<quest_id>/update", methods=["POST"])
@dm_required
def dm_update_quest(slug, quest_id):
    status = request.form.get("status", "").strip()
    note = request.form.get("note", "").strip()
    session_n = int(request.form.get("session") or 0)
    if status:
        db.set_quest_status(slug, quest_id, status)
    if note:
        db.log_quest(slug, quest_id, session_n, note)
    return redirect(url_for("story", slug=slug))


@app.route("/<slug>/dm/quest/<quest_id>/obj/<int:idx>/toggle", methods=["POST"])
@dm_required
def dm_toggle_objective(slug, quest_id, idx):
    quests = db.get_quests(slug)
    quest = next((q for q in quests if q["id"] == quest_id), None)
    if quest:
        current = quest.get("objectives", [])[idx].get("done", False)
        db.set_objective(slug, quest_id, idx, not current)
    return redirect(url_for("story", slug=slug))


@app.route("/<slug>/dm/character/<char_name>/update", methods=["POST"])
@dm_required
def dm_update_character(slug, char_name):
    db.update_character(
        slug, char_name,
        level=request.form.get("level") or None,
        status=request.form.get("status") or None,
        notes=request.form.get("notes"),
    )
    flash("Character updated", "success")
    return redirect(url_for("party", slug=slug))


@app.route("/<slug>/npc/<npc_id>/log", methods=["POST"])
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
    return redirect(url_for("npc", slug=slug, npc_id=npc_id))


@app.route("/<slug>/character/<char_name>/notes", methods=["POST"])
def player_update_character_notes(slug, char_name):
    r = campaign_access(slug)
    if r: return r
    if not session.get("user"):
        abort(403)
    db.update_character(slug, char_name, notes=request.form.get("notes", "").strip())
    flash("Notes saved", "success")
    return redirect(url_for("party", slug=slug))


@app.route("/<slug>/dm/references/add", methods=["POST"])
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
    return redirect(url_for("references", slug=slug))


@app.route("/<slug>/dm/share/generate", methods=["POST"])
@login_required
@dm_required
def dm_generate_share(slug):
    meta = load(slug, "campaign.json")
    if meta.get("owner") != session.get("user"):
        abort(403)
    meta["share_token"] = secrets.token_urlsafe(16)
    (CAMPAIGNS / slug / "campaign.json").write_text(json.dumps(meta, indent=2))
    return redirect(url_for("dm", slug=slug))


@app.route("/<slug>/dm/settings", methods=["POST"])
@login_required
@dm_required
def dm_settings(slug):
    meta = load(slug, "campaign.json")
    if meta.get("owner") != session.get("user"):
        abort(403)
    meta["name"] = request.form.get("name", "").strip() or meta["name"]
    meta["system"] = request.form.get("system", "").strip()
    meta["description"] = request.form.get("description", "").strip()
    (CAMPAIGNS / slug / "campaign.json").write_text(json.dumps(meta, indent=2))
    flash("Settings saved", "success")
    return redirect(url_for("dm", slug=slug))


@app.route("/<slug>/dm/delete", methods=["POST"])
@login_required
@dm_required
def dm_delete_campaign(slug):
    meta = load(slug, "campaign.json")
    if meta.get("owner") != session.get("user"):
        abort(403)
    if request.form.get("confirm_name", "").strip() != meta.get("name", ""):
        return redirect(url_for("dm", slug=slug))
    shutil.rmtree(str(CAMPAIGNS / slug))
    session.pop(f"dm_{slug}", None)
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=5052)
