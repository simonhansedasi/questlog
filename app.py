from flask import Flask, render_template, abort, redirect, url_for, request, session, Response, jsonify, flash
from markupsafe import Markup
from werkzeug.middleware.proxy_fix import ProxyFix
from functools import wraps
from pathlib import Path
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import json
import os
import re
import sys
import random
import secrets
import shutil
import datetime
import markdown
import uuid
import zipfile
import io
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse
from authlib.integrations.flask_client import OAuth
import stripe

sys.path.insert(0, str(Path(__file__).parent))
from src import data as db
from src import ai
from src import importer as vault_importer

from dotenv import load_dotenv
load_dotenv()

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY")
STRIPE_PUBLISHABLE_KEY = os.environ.get("STRIPE_PUBLISHABLE_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_SIGNING_SECRET", "")
STRIPE_PRICE_PRO = "price_1TS6sQHVw7SLO5uo3e0vIZZ3"
STRIPE_PRICE_PRO_ANNUAL = "price_1TTWCKHVw7SLO5uofngMWjVK"
STRIPE_PRICE_WORLD = "price_1TS6qIHVw7SLO5uoIpwNWs0n"
STRIPE_PRICE_PARTY = "price_1TTW4AHVw7SLO5uowdfuAKHR"


class PrefixMiddleware:
    def __init__(self, app, prefix):
        self.app = app
        self.prefix = prefix

    def __call__(self, environ, start_response):
        environ["SCRIPT_NAME"] = self.prefix
        return self.app(environ, start_response)


app = Flask(__name__)
app.secret_key = os.environ.get("QUESTBOOK_SECRET", "change-me-in-production")
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("QUESTBOOK_HTTPS", "1") != "0"
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
_prefix = os.environ.get("QUESTBOOK_PREFIX", "")
if _prefix:
    app.wsgi_app = PrefixMiddleware(app.wsgi_app, _prefix)

def _limiter_key():
    return session.get("user") or get_remote_address()

limiter = Limiter(key_func=_limiter_key, app=app, default_limits=[], storage_uri="memory://")

@app.errorhandler(429)
def rate_limit_error(e):
    return jsonify({"error": "Rate limit reached — 30 AI calls per hour. Try again shortly."}), 429

oauth = OAuth(app)
oauth.register(
    name="google",
    client_id=os.environ.get("GOOGLE_CLIENT_ID"),
    client_secret=os.environ.get("GOOGLE_CLIENT_SECRET"),
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)

CAMPAIGNS = Path(__file__).parent / "campaigns"
USERS_FILE = Path(__file__).parent / "users.json"

# Image URL allowlist — root domains whose CDNs are self-moderated
_IMAGE_ALLOWED_DOMAINS = {
    "imgur.com", "wikimedia.org", "wikipedia.org", "wikidata.org",
    "unsplash.com", "githubusercontent.com", "github.com",
    "discordapp.com", "discordapp.net", "discord.com",
    "pinimg.com", "twimg.com",
    "artstation.com", "deviantart.com", "deviantart.net",
    "redd.it", "reddit.com",
    "nocookie.net", "wikia.com", "fandom.com",
    "wizards.com", "dndbeyond.com",
    "staticflickr.com", "flickr.com",
    "backblazeb2.com", "googleusercontent.com",
    "cdninstagram.com",
}

def _allowed_image_url(url):
    """Return (ok, error_msg). Empty string always ok (clears portrait)."""
    if not url:
        return True, None
    try:
        parsed = urlparse(url)
    except Exception:
        return False, "Invalid URL."
    if parsed.scheme != "https":
        return False, "Portrait URL must use https://."
    host = (parsed.hostname or "").lower()
    parts = host.split(".")
    root = ".".join(parts[-2:]) if len(parts) >= 2 else host
    if root not in _IMAGE_ALLOWED_DOMAINS:
        return False, "That image host isn't on the allowlist. Use Imgur, ArtStation, DeviantArt, Wikimedia, Discord CDN, or another supported host."
    return True, None


def _user_world_count(username):
    """Count non-demo campaigns owned by this user."""
    count = 0
    for d in CAMPAIGNS.iterdir():
        if not d.is_dir():
            continue
        cf = d / "campaign.json"
        if not cf.exists():
            continue
        try:
            meta = json.loads(cf.read_text())
        except Exception:
            continue
        if meta.get("owner") == username and not meta.get("demo_mode") and not meta.get("demo"):
            count += 1
    return count
INVITES_FILE = Path(__file__).parent / "invites.json"


_SLUG_RE = re.compile(r'^[a-z0-9][a-z0-9_-]{0,49}$')

def _validate_slug(slug):
    if not _SLUG_RE.match(slug):
        abort(404)

@app.template_filter("compute_rel")
def compute_rel_filter(npc, is_dm=True):
    return db.compute_npc_relationship(npc, is_dm=is_dm)


@app.template_filter("wikilinks")
def wikilinks_filter(text, slug, npcs, factions, locations=None, party=None):
    """Replace [[Entity Name]] with links to matching NPC/faction/location/party pages."""
    if not text:
        return Markup('')
    lookup = {}
    for n in (npcs or []):
        lookup[n['name'].lower()] = ('npc', n['id'])
    for f in (factions or []):
        lookup[f['name'].lower()] = ('faction', f['id'])
    for loc in (locations or []):
        lookup[loc['name'].lower()] = ('location', loc['id'])
    for c in (party or []):
        lookup[c['name'].lower()] = ('party', db.slugify(c['name']))
    escaped = str(Markup.escape(text))

    def replace(m):
        inner = m.group(1)
        if '|' in inner:
            entity, display = inner.split('|', 1)
        else:
            entity = display = inner
        key = entity.lower()
        if key in lookup:
            etype, eid = lookup[key]
            if etype == 'location':
                return f'<a href="/{slug}/world/location/{eid}" class="wikilink">{Markup.escape(display)}</a>'
            if etype == 'party':
                return f'<a href="/{slug}/party" class="wikilink">{Markup.escape(display)}</a>'
            return f'<a href="/{slug}/world/{etype}/{eid}" class="wikilink">{Markup.escape(display)}</a>'
        return str(Markup.escape(display))

    return Markup(re.sub(r'\[\[([^\]\[]+)\]\]', replace, escaped))


def _get_backlinks(entity_name, entity_id, all_npcs, all_factions, all_locations=None):
    """Return list of entities whose description mentions [[entity_name]]."""
    pattern = re.compile(r'\[\[' + re.escape(entity_name) + r'(\|[^\]]+)?\]\]', re.IGNORECASE)
    links = []
    for n in (all_npcs or []):
        if n.get('id') != entity_id and pattern.search(n.get('description') or ''):
            links.append({'type': 'npc', 'id': n['id'], 'name': n['name']})
    for f in (all_factions or []):
        if f.get('id') != entity_id and pattern.search(f.get('description') or ''):
            links.append({'type': 'faction', 'id': f['id'], 'name': f['name']})
    for loc in (all_locations or []):
        if loc.get('id') != entity_id and pattern.search(loc.get('description') or ''):
            links.append({'type': 'location', 'id': loc['id'], 'name': loc['name']})
    return links


@app.after_request
def stamp_demo_visitor(response):
    if request.path.startswith("/demo") and not request.cookies.get("demo_id"):
        response.set_cookie("demo_id", str(uuid.uuid4()), max_age=30*24*3600, samesite="Lax", httponly=True)
    return response


_DEFAULT_TERMS = {
    "npc": "NPC", "npcs": "NPCs",
    "session": "Session", "sessions": "Sessions",
    "dm": "DM", "party": "Party",
    "faction": "Faction", "factions": "Factions",
    "notes_label": "Session Notes",
    "session_tools_label": "Session Tools",
    "parse_cta": "Parse into Events",
    "recap_cta": "Generate Recap",
    "quick_log_label": "Quick Log",
    "dm_controls": "DM Controls",
    "log_verb": "Log",
    # nav + section labels
    "cast_label": "Party",
    "assets_label": "Assets",
    "story_label": "Story",
    "brief_nav": "Brief",
    "journal_label": "Journal",
    "brief_cta": "Brief me",
    "recap_section_label": "Player Recap",
    "share_label": "Player Share Link",
    "players_label": "Players",
    "quest_label": "Quest",
    "quests_label": "Quests",
}

_BLANK_TEMPLATES = {
    "ttrpg": {},
    "fiction": {
        "npc": "Character", "npcs": "Characters",
        "session": "Chapter", "sessions": "Chapters",
        "dm": "Author", "party": "Reader",
        "faction": "Group", "factions": "Groups",
        "notes_label": "Chapter Notes",
        "session_tools_label": "Write & Parse",
        "parse_cta": "Extract Story Events",
        "recap_cta": "Generate Chapter Summary",
        "quick_log_label": "Quick Event",
        "dm_controls": "Author Controls",
        "log_verb": "Log",
        "cast_label": "Cast",
        "assets_label": "Props",
        "story_label": "Arcs",
        "brief_nav": "Outline",
        "journal_label": "Journal",
        "brief_cta": "Story Brief",
        "recap_section_label": "Chapter Summary",
        "share_label": "Reader Share Link",
        "players_label": "Collaborators",
        "quest_label": "Arc",
        "quests_label": "Story Arcs",
        "observer_default": "The Reader",
    },
    "historical": {
        "npc": "Figure", "npcs": "Figures",
        "session": "Period", "sessions": "Periods",
        "dm": "Historian", "party": "Posterity",
        "faction": "Institution", "factions": "Institutions",
        "notes_label": "Source Notes",
        "session_tools_label": "Write & Extract Records",
        "parse_cta": "Extract Historical Records",
        "recap_cta": "Generate Chronicle Entry",
        "quick_log_label": "Quick Record",
        "dm_controls": "Archivist Controls",
        "log_verb": "Record",
        "cast_label": "Principals",
        "assets_label": "Artifacts",
        "story_label": "Threads",
        "brief_nav": "Brief",
        "journal_label": "Chronicle",
        "brief_cta": "Research Brief",
        "recap_section_label": "Chronicle Entry",
        "share_label": "Researcher Share Link",
        "players_label": "Collaborators",
        "quest_label": "Thread",
        "quests_label": "Threads",
        "observer_default": "Posterity",
    },
}

@app.context_processor
def inject_viewer_character():
    slug = request.view_args.get("slug") if request.view_args else None
    if not slug and request.path.startswith("/demo"):
        slug = "demo"
    meta = load(slug, "campaign.json") if slug else {}
    is_public = bool(meta.get("public"))
    is_demo = bool(meta.get("demo_mode"))
    terms = {**_DEFAULT_TERMS, **meta.get("terminology", {})}
    world_mode = meta.get("mode", "ttrpg")
    user_ai_enabled = False
    user_pro = False
    worlds_used = 0
    worlds_limit = 1
    if session.get("user"):
        all_users = load_users()
        u = all_users.get(session["user"], {})
        user_ai_enabled = bool(u.get("ai_enabled") or u.get("admin"))
        user_pro = u.get("subscription_status") == "active"
        worlds_used = _user_world_count(session["user"])
        worlds_limit = u.get("world_limit", 3) + u.get("extra_worlds", 0)
    # can_write: True for owner/members/DMs and demo; False for share-link-only viewers
    can_write = is_demo
    if not can_write and slug:
        if session.get(f"dm_{slug}"):
            can_write = True
        elif session.get("user"):
            owner = meta.get("owner")
            members = meta.get("members", [])
            can_write = (session["user"] == owner or session["user"] in members)
    if slug and session.get("user") and not session.get(f"dm_{slug}"):
        char = db.get_player_character(slug, session["user"])
        return {"viewer_character": char, "is_public": is_public, "is_demo": is_demo, "terms": terms, "world_mode": world_mode, "user_ai_enabled": user_ai_enabled, "can_write": can_write, "user_pro": user_pro, "worlds_used": worlds_used, "worlds_limit": worlds_limit}
    return {"viewer_character": None, "is_public": is_public, "is_demo": is_demo, "terms": terms, "world_mode": world_mode, "user_ai_enabled": user_ai_enabled, "can_write": can_write, "user_pro": user_pro, "worlds_used": worlds_used, "worlds_limit": worlds_limit}


DEMO_SOURCE = CAMPAIGNS / "ashford"
DEMO_DIR = CAMPAIGNS / "demo"
DEMO_STAMP = DEMO_DIR / ".reset_stamp"
DEMO_COUNTS_FILE = CAMPAIGNS / "demo_parse_counts.json"


def _load_demo_counts():
    if DEMO_COUNTS_FILE.exists():
        try:
            return json.loads(DEMO_COUNTS_FILE.read_text())
        except Exception:
            return {}
    return {}


def _save_demo_counts(counts):
    DEMO_COUNTS_FILE.write_text(json.dumps(counts))

def reset_demo(force=False):
    if not force and DEMO_STAMP.exists():
        age = datetime.datetime.now() - datetime.datetime.fromtimestamp(DEMO_STAMP.stat().st_mtime)
        if age < datetime.timedelta(minutes=30):
            return
    if DEMO_DIR.exists():
        shutil.rmtree(DEMO_DIR)
    shutil.copytree(DEMO_SOURCE, DEMO_DIR)
    meta = json.loads((DEMO_DIR / "campaign.json").read_text())
    meta["slug"] = "demo"
    meta.pop("public", None)
    meta.pop("demo", None)
    meta["demo_mode"] = True
    (DEMO_DIR / "campaign.json").write_text(json.dumps(meta, indent=2))
    DEMO_STAMP.touch()


def load_users():
    if not USERS_FILE.exists():
        return {}
    return json.loads(USERS_FILE.read_text()).get("users", {})


def save_users(users_dict):
    USERS_FILE.write_text(json.dumps({"users": users_dict}, indent=2))


def load_invites():
    if not INVITES_FILE.exists():
        return []
    return json.loads(INVITES_FILE.read_text()).get("invites", [])


def save_invites(invites):
    INVITES_FILE.write_text(json.dumps({"invites": invites}, indent=2))


def generate_invite_code():
    import random, string
    chars = string.ascii_uppercase + string.digits
    a = "".join(random.choices(chars, k=4))
    b = "".join(random.choices(chars, k=4))
    return f"RF-{a}-{b}"



def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("user"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


def campaign_access(slug):
    """Allow access if: public campaign, logged-in owner/member, share-link visitor."""
    meta = load(slug, "campaign.json")
    if meta.get("public"):
        if request.method != "GET" and not request.path.endswith("/dm/login"):
            abort(403)
        return None
    if meta.get("demo_mode"):
        return None  # full read+write, no auth required
    owner = meta.get("owner")
    members = meta.get("members", [])
    if session.get("user"):
        user = session["user"]
        if user == owner or user in members:
            return  # full access for owner and invited players
        # Non-member: must have visited the share link, but read-only
        if not session.get(f"view_{slug}"):
            abort(403)
        if request.method != "GET" and not request.path.endswith("/dm/login"):
            abort(403)
        return
    # Unauthenticated share-link visitor: read-only GET only
    if session.get(f"view_{slug}"):
        if request.method != "GET" and not request.path.endswith("/dm/login"):
            abort(403)
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


def char_or_dm_required(f):
    """Allow DMs OR the logged-in player assigned to the character in the route."""
    @wraps(f)
    def decorated(slug, char_name, *args, **kwargs):
        if session.get(f"dm_{slug}"):
            return f(slug, char_name, *args, **kwargs)
        user = session.get("user")
        if user:
            assigned = db.get_player_character(slug, user)
            if assigned and assigned.get("name") == char_name:
                return f(slug, char_name, *args, **kwargs)
        return redirect(url_for("login"))
    return decorated


def load(slug, *parts):
    _validate_slug(slug)
    p = CAMPAIGNS / slug / Path(*parts)
    if not p.exists():
        return {}
    return json.loads(p.read_text())


def campaigns():
    result = []
    for d in sorted(CAMPAIGNS.iterdir()):
        if d.is_dir() and (d / "campaign.json").exists():
            meta = json.loads((d / "campaign.json").read_text())
            if "slug" not in meta:
                meta["slug"] = d.name
            result.append(meta)
    return result


# ── Auth routes ───────────────────────────────────────────────────────────────

@app.route("/login", methods=["GET"])
def login():
    if session.get("user"):
        return redirect(url_for("index"))
    return render_template("login.html")


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/auth/google")
def auth_google():
    redirect_uri = url_for("auth_google_callback", _external=True)
    return oauth.google.authorize_redirect(redirect_uri)


@app.route("/auth/google/callback")
def auth_google_callback():
    token = oauth.google.authorize_access_token()
    info = token.get("userinfo") or oauth.google.userinfo()
    google_sub = info["sub"]
    email = info.get("email", "")
    name = info.get("name", email.split("@")[0])

    users = load_users()

    # Find existing account by google_sub or email
    username = next((u for u, d in users.items() if d.get("google_sub") == google_sub), None)
    if not username:
        username = next((u for u, d in users.items() if d.get("email") == email and email), None)

    is_new_user = username is None
    if not username:
        # Derive a clean username from the email prefix
        base = re.sub(r'[^a-z0-9_]', '_', email.split("@")[0].lower())[:20] or "user"
        candidate = base
        i = 2
        while candidate in users:
            candidate = f"{base[:17]}_{i}"
            i += 1
        username = candidate
        users[username] = {
            "display_name": name,
            "email": email,
            "google_sub": google_sub,
            "created_at": datetime.datetime.utcnow().isoformat(),
            "ai_enabled": False,
            "world_limit": 3,
        }
    else:
        # Keep google_sub and email up to date on existing account
        users[username]["google_sub"] = google_sub
        users[username].setdefault("email", email)

    save_users(users)
    session["user"] = username
    session["display_name"] = users[username].get("display_name", username)
    if is_new_user or not users[username].get("onboarding_seen"):
        return redirect(url_for("welcome"))
    return redirect(url_for("index"))


@app.route("/signup")
def signup():
    return redirect(url_for("login"))


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        users = load_users()
        user = users.get(session.get("user", ""))
        if not user or not user.get("admin"):
            abort(403)
        return f(*args, **kwargs)
    return decorated


def ai_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        users = load_users()
        user = users.get(session.get("user", ""), {})
        if not user.get("ai_enabled") and not user.get("admin"):
            return jsonify({"error": "ai_locked"}), 403
        return f(*args, **kwargs)
    return decorated


@app.route("/admin/invites")
@login_required
@admin_required
def admin_invites():
    invites = load_invites()
    return render_template("admin/invites.html", invites=invites)


@app.route("/admin/invites/generate", methods=["POST"])
@login_required
@admin_required
def admin_generate_invite():
    invites = load_invites()
    code = generate_invite_code()
    invites.append({
        "code": code,
        "created_at": datetime.datetime.utcnow().isoformat(),
        "used_by": None,
        "used_at": None
    })
    save_invites(invites)
    return jsonify({"code": code})




# ── Public routes ─────────────────────────────────────────────────────────────

@app.route("/")
def index():
    if not session.get("user"):
        return render_template("landing.html")
    username = session["user"]
    all_campaigns = campaigns()
    my_campaigns = [c for c in all_campaigns if c.get("owner") == username and not c.get("demo")]
    member_campaigns = [c for c in all_campaigns if username in c.get("members", []) and c.get("owner") != username and not c.get("demo")]
    demo_campaigns = [c for c in all_campaigns if c.get("demo")]
    for c in my_campaigns:
        if c.get("onboarding_mode") == "party":
            _g = db.get_party_game(c["slug"])
            c["party_phase"] = _g.get("phase")
    return render_template("index.html", my_campaigns=my_campaigns, member_campaigns=member_campaigns, demo_campaigns=demo_campaigns)


@app.route("/guide")
def guide():
    return render_template("guide.html")


@app.route("/<slug>/setup")
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


@app.route("/<slug>/setup/step", methods=["POST"])
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


def _party_game_access(slug):
    """Load and return campaign meta for a party-mode campaign. No auth required."""
    _validate_slug(slug)
    meta = load(slug, "campaign.json")
    if meta.get("onboarding_mode") != "party":
        abort(404)
    return meta


@app.route("/<slug>/play")
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
                    cancel_url=request.host_url.rstrip("/") + url_for("index"),
                )
                return redirect(checkout.url)
            except stripe.StripeError:
                flash("Upgrade to Pro for unlimited Party Mode games.", "error")
                return redirect(url_for("index"))
    return render_template("party_play.html", slug=slug, meta=meta, game=game)


@app.route("/<slug>/play/action", methods=["POST"])
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


@app.route("/<slug>/play/generate-scenario", methods=["POST"])
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


@app.route("/<slug>/play/referee", methods=["POST"])
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


@app.route("/<slug>/play/generate-arc", methods=["POST"])
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


@app.route("/<slug>/play/generate-secrets", methods=["POST"])
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


@app.route("/<slug>/play/generate-summary", methods=["POST"])
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


@app.route("/<slug>/play/complete", methods=["POST"])
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


@app.route("/wiki")
def wiki():
    return render_template("wiki.html")


@app.route("/sw.js")
def service_worker():
    return app.send_static_file("sw.js")


@app.route("/robots.txt")
def robots_txt():
    return app.response_class(
        "User-agent: *\nAllow: /\nAllow: /demo/\nAllow: /guide\nDisallow: /admin/\nDisallow: /account/\nSitemap: https://rippleforge.gg/sitemap.xml\n",
        mimetype="text/plain"
    )


@app.route("/sitemap.xml")
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


@app.route("/demo/<slug>/clone", methods=["POST"])
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
                    cancel_url=request.host_url.rstrip("/") + url_for("index"),
                )
                return redirect(checkout.url)
            except stripe.StripeError:
                flash("World limit reached. Upgrade to create more worlds.", "error")
                return redirect(url_for("index"))
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
    return redirect(url_for("dm", slug=new_slug))


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
                cancel_url=request.host_url.rstrip("/") + url_for("index"),
            )
            return redirect(checkout.url)
        except stripe.StripeError:
            flash("World limit reached. Upgrade to create more worlds.", "error")
            return redirect(url_for("index"))
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
    else:
        new_meta["name"] = ""
        new_meta["mode"] = "ttrpg"
        new_meta["observer_name"] = "The Party"
        new_meta.pop("terminology", None)
    new_meta["description"] = ""
    new_meta["system"] = "Party Mode" if onboarding_mode == "party" else ""
    new_meta["party_name"] = ""
    new_meta["onboarding_mode"] = onboarding_mode
    (dst / "campaign.json").write_text(json.dumps(new_meta, indent=2))
    session[f"dm_{new_slug}"] = True
    return new_slug


@app.route("/welcome")
@login_required
def welcome():
    return render_template("welcome.html")


@app.route("/welcome", methods=["POST"])
@login_required
def welcome_post():
    choice = request.form.get("choice", "deepend")
    username = session["user"]
    users = load_users()
    users[username]["onboarding_seen"] = True
    save_users(users)

    if choice == "wizard":
        result = _create_onboarding_campaign(username, "wizard")
        if isinstance(result, str):
            return redirect(url_for("setup_wizard", slug=result))
        return result or redirect(url_for("index"))

    if choice == "party":
        user_data = users.get(username, {})
        is_pro = user_data.get("subscription_status") in ("active", "trialing") or bool(user_data.get("ks_tier"))

        # Non-pro with free game already played → $2 one-time party game
        if not is_pro and user_data.get("party_plays", 0) >= 3:
            try:
                checkout = stripe.checkout.Session.create(
                    payment_method_types=["card"],
                    mode="payment",
                    line_items=[{"price": STRIPE_PRICE_PARTY, "quantity": 1}],
                    metadata={"username": username},
                    success_url=request.host_url.rstrip("/") + "/billing/party/success?session_id={CHECKOUT_SESSION_ID}",
                    cancel_url=request.host_url.rstrip("/") + url_for("index"),
                )
                return redirect(checkout.url)
            except stripe.StripeError:
                flash("Could not start checkout. Try again.", "error")
                return redirect(url_for("index"))

        # World limit reached → Pro users: prompt to delete a world first
        limit = user_data.get("world_limit", 3) + user_data.get("extra_worlds", 0)
        if _user_world_count(username) >= limit:
            flash("You've reached your world limit. Delete a world from your home screen to make room for a new party game.", "error")
            return redirect(url_for("index"))

        result = _create_onboarding_campaign(username, "party")
        if isinstance(result, str):
            return redirect(url_for("party_play", slug=result))
        return result or redirect(url_for("index"))

    return redirect(url_for("index"))


@app.route("/demo/reset", methods=["GET", "POST"])
def demo_reset():
    reset_demo(force=True)
    return redirect("/demo/")


@app.route("/demo/")
def demo_splash():
    reset_demo()
    r = campaign_access("demo")
    if r: return r
    meta = load("demo", "campaign.json")
    return render_template("demo_splash.html", meta=meta, slug="demo")


@app.route("/demo/ai")
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


@app.route("/demo/ai/propose", methods=["POST"])
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
    party = db.get_party("demo")
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


@app.route("/demo/ai/commit_parsed", methods=["POST"])
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


@app.route("/demo/ai/commit_futures", methods=["POST"])
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


@app.route("/<slug>/")
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
            return redirect(url_for("party_play", slug=slug))
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
    viewer = session.get("user")
    characters = db.get_party(slug, include_hidden=is_dm)
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

    for char in characters:
        char["_conditions"] = db.get_character_conditions(
            slug, char["name"], include_hidden=is_dm, include_resolved=False
        )
        raw_log = char.get("log", [])
        visible = db.get_visible_log(raw_log, is_dm=is_dm)
        for e in visible:
            e["_actor_name"] = _resolve_actor(e)
        char["_log"] = list(reversed(visible))

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
                           party_log=party_log, party_display_name=party_display_name)


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
    if meta and meta.get("onboarding_mode") == "party":
        _g = db.get_party_game(slug)
        if _g.get("phase") != "done":
            return redirect(url_for("party_play", slug=slug))
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
    return render_template("world.html", meta=meta, npcs=npcs, factions=factions,
                           conditions=conditions, locations=locations, slug=slug, is_dm=is_dm,
                           as_of=as_of, max_session=max_session,
                           branches=branches, active_branch=active_branch)


@app.route("/<slug>/branch/create", methods=["POST"])
def branch_create(slug):
    _validate_slug(slug)
    meta = load(slug, "campaign.json")
    if not meta.get("demo_mode"):
        if not session.get("user"):
            return redirect(url_for("login"))
        if meta.get("owner") != session.get("user"):
            abort(403)
    name = request.form.get("name", "").strip()
    fork_point = request.form.get("fork_point", type=int)
    parent_branch = request.form.get("parent_branch", "").strip() or None
    if not name or not fork_point:
        flash("Branch name and fork session required.")
        return redirect(url_for("world", slug=slug))
    branch_id = db.create_branch(slug, name, fork_point, parent_branch=parent_branch)
    session[f"branch_{slug}"] = branch_id
    return redirect(url_for("world", slug=slug))


@app.route("/<slug>/branch/switch", methods=["POST"])
def branch_switch(slug):
    _validate_slug(slug)
    meta = load(slug, "campaign.json")
    if not meta.get("demo_mode"):
        if not session.get("user"):
            return redirect(url_for("login"))
        is_narrator = (meta.get("owner") == session.get("user")) or bool(session.get(f"dm_{slug}"))
        if not is_narrator:
            abort(403)
    branch_id = request.form.get("branch_id", "").strip()
    if branch_id:
        session[f"branch_{slug}"] = branch_id
    else:
        session.pop(f"branch_{slug}", None)
    return redirect(url_for("world", slug=slug))


@app.route("/<slug>/branch/delete", methods=["POST"])
def branch_delete(slug):
    _validate_slug(slug)
    meta = load(slug, "campaign.json")
    if not meta.get("demo_mode"):
        if not session.get("user"):
            return redirect(url_for("login"))
        if meta.get("owner") != session.get("user"):
            abort(403)
    branch_id = request.form.get("branch_id", "").strip()
    if branch_id:
        db.delete_branch(slug, branch_id)
        if session.get(f"branch_{slug}") == branch_id:
            session.pop(f"branch_{slug}", None)
    return redirect(url_for("world", slug=slug))


def get_ripple_chains(slug, include_hidden=False):
    npcs = db.get_npcs(slug, include_hidden=include_hidden)
    factions = db.get_factions(slug, include_hidden=include_hidden)
    party = db.get_party(slug, include_hidden=True)

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


@app.route("/<slug>/world/ripples")
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


@app.route("/<slug>/world/graph")
def world_graph(slug):
    r = campaign_access(slug)
    if r: return r
    meta = load(slug, "campaign.json")
    is_dm = bool(session.get(f"dm_{slug}"))
    return render_template("graph.html", meta=meta, slug=slug, is_dm=is_dm)


@app.route("/<slug>/world/graph-data")
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

    party = db.get_party(slug, include_hidden=is_dm)
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

    # ── Party hub + characters ────────────────────────────────────────────────
    meta = load(slug, "campaign.json")
    party_name = meta.get("party_name") or "Party"
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

        nodes.append({"data": {
            "id": "_party",
            "label": party_name,
            "type": "party",
            "relationship": "allied",
            "score": 0,
            "hidden": False,
            "log_count": 0,
            "role": "",
            "last_note": "",
        }})

        # Party hub → explicit party_relations (DM-set, not auto-generated from logs)
        _rel_map = {"ally": "friendly", "rival": "hostile"}
        for pr in meta.get("party_relations", []):
            tid = pr.get("target")
            if not tid or tid not in known_ids:
                continue
            key = frozenset(["_party", tid])
            if key not in seen_edges:
                seen_edges.add(key)
                edges.append({"data": {
                    "id": f"_party__{tid}",
                    "source": "_party",
                    "target": tid,
                    "relation": "party_contact",
                    "relationship": _rel_map.get(pr.get("relation", "ally"), "neutral"),
                    "weight": float(pr.get("weight", 0.5)),
                }})

        # Individual character nodes + their known_event connections
        for char in party:
            cid = f"_char_{db.slugify(char['name'])}"
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
                "id": f"_party__{cid}",
                "source": "_party",
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
                    edges.append({"data": {
                        "id": edge_id,
                        "source": cid, "target": tid,
                        "relation": "char_relation",
                        "relationship": _rel_color_map.get(rel.get("relation", "ally"), "neutral"),
                        "weight": float(rel.get("weight", 0.5)),
                        "dm_only": is_dm_edge,
                    }})

    # ── Party-affiliate NPCs → party hub ─────────────────────────────────────
    for npc in npcs:
        if not npc.get("party_affiliate"):
            continue
        key = frozenset(["_party", npc["id"]])
        if key not in seen_edges:
            seen_edges.add(key)
            edges.append({"data": {
                "id": f"_party__{npc['id']}__affiliate",
                "source": "_party",
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

    # ── NPC/faction actor → character diamond (NPC caused event on char) ──────
    for char in party:
        cid = f"_char_{db.slugify(char['name'])}"
        for entry in char.get("log", []):
            if entry.get("deleted"):
                continue
            aid = entry.get("actor_id")
            if not aid or aid not in known_ids:
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
        if not aid or aid not in known_ids:
            continue
        _add_acted_edge(aid, "_party", entry.get("polarity"), entry.get("actor_dm_only", False))

    return jsonify({"nodes": nodes, "edges": edges})


@app.route("/<slug>/world/npc/<npc_id>")
def npc(slug, npc_id):
    r = campaign_access(slug)
    if r: return r
    meta = load(slug, "campaign.json")
    is_dm = bool(session.get(f"dm_{slug}")) or (session.get("user") == meta.get("owner"))
    is_player = bool(session.get("user")) and not is_dm
    npc_obj = next((n for n in db.get_npcs(slug, include_hidden=is_dm) if n["id"] == npc_id), None)
    if not npc_obj:
        abort(404)

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

    party = db.get_party(slug) if is_dm else []
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
                           backlinks=backlinks)


@app.route("/<slug>/world/faction/<faction_id>")
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
    party = db.get_party(slug) if is_dm else []

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
                           char_bonds=char_bonds)


@app.route("/<slug>/world/location/<location_id>")
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
    party = db.get_party(slug)
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
    all_entries = db.get_journal(slug, include_deleted=is_dm)
    active = [e for e in all_entries if not e.get("deleted")]
    deleted = [e for e in all_entries if e.get("deleted")] if is_dm else []
    npcs = db.get_npcs(slug, include_hidden=is_dm)
    factions = db.get_factions(slug, include_hidden=is_dm)
    locations = db.get_locations(slug, include_hidden=is_dm)
    party = db.get_party(slug)
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


@app.route("/<slug>/dm/journal/<int:idx>/restore", methods=["POST"])
@dm_required
def dm_restore_journal(slug, idx):
    db.restore_journal_entry(slug, idx)
    flash("Entry restored", "success")
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
        return redirect(url_for("dm", slug=slug))
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


@app.route("/<slug>/dm")
@dm_required
def dm(slug):
    meta = load(slug, "campaign.json")
    if not meta:
        abort(404)
    if meta.get("onboarding_mode") == "party":
        _g = db.get_party_game(slug)
        if _g.get("phase") != "done":
            return redirect(url_for("party_play", slug=slug))
    branches = db.get_branches(slug)
    active_branch_id = session.get(f"branch_{slug}")
    active_branch = next((b for b in branches if b["id"] == active_branch_id), None)
    raw_plan = db.get_session_plan(slug)
    plan_html = Markup(markdown.markdown(raw_plan, extensions=["nl2br"])) if raw_plan else None
    current_session = db.get_current_session(slug)
    all_users = list(load_users().keys())
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
    _party_display_name = meta.get("party_name") or "The Party"
    all_entities = (
        [{"id": "_party", "name": _party_display_name, "type": "party", "actor_only": True}] +
        [{"id": n["id"], "name": n["name"], "type": "npc"} for n in db.get_npcs(slug, include_hidden=True)] +
        [{"id": f["id"], "name": f["name"], "type": "faction"} for f in db.get_factions(slug, include_hidden=True)] +
        [{"id": db.slugify(c["name"]), "name": c["name"], "type": "char"} for c in party]
    )
    all_users_data = load_users()
    members = meta.get("members", [])
    members_info = [{"username": u, "display_name": all_users_data.get(u, {}).get("display_name", u)} for u in members]
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
                           all_users=all_users,
                           members_info=members_info,
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
                           all_log_entries=all_log_entries)


@app.route("/<slug>/dm/log/quick", methods=["POST"])
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
                                branch=active_branch_id)
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
                                branch=active_branch_id)
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
            db.log_party_group(slug, session_n, note, polarity=polarity,
                               intensity=intensity, event_type=event_type, visibility=visibility,
                               actor_id=actor_id, actor_type=actor_type, actor_dm_only=actor_dm_only,
                               location_id=location_id, party_name=_party_name_ql)
            if not is_ajax:
                flash("Logged", "success")
        elif entity_type == "location" and note:
            db.log_location(slug, entity_id, session_n, note, visibility=visibility,
                            polarity=polarity, intensity=intensity, event_type=event_type)
            if not is_ajax:
                flash("Logged", "success")
        if is_ajax:
            return jsonify({"ok": True, "diffs": _build_diffs(slug, before, [])})
    return redirect(url_for("dm", slug=slug))


@app.route("/<slug>/dm/session/plan", methods=["POST"])
@dm_required
def dm_set_session_plan(slug):
    db.set_session_plan(slug, request.form.get("plan", ""))
    flash("Plan saved", "success")
    return redirect(url_for("dm", slug=slug))


@app.route("/<slug>/dm/session/brief", methods=["POST"])
@dm_required
def dm_generate_brief(slug):
    brief = db.generate_session_brief(slug)
    return jsonify({"brief": brief})


@app.route("/<slug>/dm/entity/<entity_type>/<entity_id>/panel")
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
        char = next((c for c in db.get_party(slug) if c["name"] == entity_id), None)
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
        for char in db.get_party(slug):
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


@app.route("/<slug>/dm/session/notes", methods=["POST"])
@dm_required
def dm_set_session_notes(slug):
    new_notes = request.form.get("notes", "")
    db.set_session_notes(slug, new_notes)
    if len(new_notes) < db.get_notes_parse_cursor(slug):
        db.reset_notes_parse_cursor(slug)
    flash("Notes saved", "success")
    return redirect(url_for("dm", slug=slug))


@app.route("/<slug>/dm/session/reset_parse_cursor", methods=["POST"])
@dm_required
def dm_reset_parse_cursor(slug):
    db.reset_notes_parse_cursor(slug)
    return ("", 204)


@app.route("/<slug>/dm/session/recap", methods=["POST"])
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


@app.route("/<slug>/dm/session/propose", methods=["POST"])
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
    party = db.get_party(slug)
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
        new_cursor = cursor + len(full_notes[cursor:])
        db.save_proposals(slug, proposals, current_session, parse_cursor=new_cursor)
        db.save_relation_suggestions(slug, rel_suggestions)
        return jsonify({"proposals": proposals, "session": current_session,
                        "relation_suggestions": rel_suggestions})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/<slug>/dm/relation_suggestion/accept", methods=["POST"])
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


@app.route("/<slug>/dm/relation_suggestion/dismiss", methods=["POST"])
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


@app.route("/<slug>/dm/session/commit_proposals", methods=["POST"])
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
    party_names = {c["name"].lower() for c in db.get_party(slug)}

    committed = 0
    created = []
    logged_entity_ids = set()

    # Pre-pass: create all new NPC/faction entities first so actor references resolve correctly
    for entry in data["entries"]:
        if (entry.get("entity_name") or "").strip().lower() in party_names:
            continue
        etype = entry.get("entity_type", "npc")
        if etype in ("ship", "condition", "location", "party", "party_group"):
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
        if (entry.get("entity_name") or "").strip().lower() in party_names:
            continue
        entity_id = entry.get("entity_id")
        entity_type = entry.get("entity_type", "npc")
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
                                     hidden=True)
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
                                         party_name=_party_name_cp)
        elif entity_type == "faction" or entity_id in faction_by_name.values():
            src_evt = db.log_faction(slug, entity_id, session_n, note, polarity=polarity,
                                     intensity=intensity, event_type=event_type, visibility=visibility,
                                     actor_id=actor_id, actor_type=actor_type, actor_dm_only=actor_dm_only,
                                     branch=active_branch_id, axis=axis)
        else:
            src_evt = db.log_npc(slug, entity_id, session_n, note, polarity=polarity,
                                 intensity=intensity, event_type=event_type, visibility=visibility,
                                 actor_id=actor_id, actor_type=actor_type, actor_dm_only=actor_dm_only,
                                 branch=active_branch_id, axis=axis)
        if polarity:
            if discrete:
                entity_name = (entry.get("entity_name") or "").strip() or entity_id
                db.add_pending_ripple(slug, entity_id, entity_type, entity_name,
                                      src_evt, session_n, note, polarity, intensity,
                                      event_type, visibility)
            else:
                db.apply_ripple(slug, entity_id, entity_type, session_n, note, polarity, intensity,
                                event_type, visibility=visibility, source_event_id=src_evt,
                                branch=active_branch_id)
        if src_evt:
            for w in (entry.get("witnesses") or []):
                db.reveal_event(slug, src_evt, w)
        logged_entity_ids.add(entity_id)
        committed += 1

    if pending_cursor is not None:
        db.set_notes_parse_cursor(slug, pending_cursor)

    cond_alerts = [
        {"char_name": a["char_name"], "condition_name": a["condition"]["name"],
         "entity_name": a["entity_name"]}
        for a in db.get_condition_alerts_for_entities(slug, logged_entity_ids)
    ]
    return jsonify({"committed": committed, "created": created, "condition_alerts": cond_alerts})


@app.route("/<slug>/dm/import/session/propose", methods=["POST"])
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
    party = db.get_party(slug)
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


@app.route("/<slug>/dm/import/session/commit", methods=["POST"])
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
    party_names = {c["name"].lower() for c in db.get_party(slug)}

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
                                     magnitude=meta_c.get("magnitude", ""), hidden=True)
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


@app.route("/<slug>/dm/ripple/<ripple_id>/reveal", methods=["POST"])
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


@app.route("/<slug>/dm/ripple/<ripple_id>/dismiss", methods=["POST"])
@dm_required
def dm_dismiss_ripple(slug, ripple_id):
    db.resolve_pending_ripple(slug, ripple_id)
    return jsonify({"ok": True})


@app.route("/<slug>/dm/session/notes/export")
@dm_required
def dm_export_notes(slug):
    notes = db.get_session_notes(slug)
    return Response(
        notes,
        mimetype="text/markdown",
        headers={"Content-Disposition": f"attachment; filename={slug}_session_notes.md"}
    )


@app.route("/<slug>/dm/export")
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


@app.route("/<slug>/dm/import", methods=["GET"])
@dm_required
def dm_import(slug):
    meta = load(slug, "campaign.json")
    return render_template("dm/import.html", meta=meta, slug=slug)


@app.route("/<slug>/dm/import/preview", methods=["POST"])
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


@app.route("/<slug>/dm/import/session", methods=["POST"])
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
    party = db.get_party(slug)

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
                                     magnitude=meta_c.get("magnitude", ""), hidden=True)
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


@app.route("/<slug>/dm/import/obsidian", methods=["POST"])
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

    for n in result["npcs"]:
        n["exists"] = db.slugify(n["name"]) in existing_npc_ids
    for f2 in result["factions"]:
        f2["exists"] = db.slugify(f2["name"]) in existing_faction_ids
    for q in result["quests"]:
        q["exists"] = db.slugify(q["name"]) in existing_quest_ids

    return jsonify(result)


@app.route("/<slug>/dm/import/obsidian/confirm", methods=["POST"])
@dm_required
def dm_import_obsidian_confirm(slug):
    data = request.get_json()
    npcs_in = data.get("npcs", [])
    factions_in = data.get("factions", [])
    quests_in = data.get("quests", [])

    created = {"npcs": 0, "factions": 0, "quests": 0}

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

    total = sum(created.values())
    return jsonify({"ok": True, "created": created, "total": total})


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
            factions=request.form.getlist("factions"),
            hidden_factions=request.form.getlist("hidden_factions"),
            image_url=request.form.get("image_url", "").strip() if _allowed_image_url(request.form.get("image_url", "").strip())[0] else None,
            dm_notes=request.form.get("dm_notes", "").strip() or None,
        )
        if request.form.get("ajax"):
            return jsonify({"ok": True})
        return redirect(url_for("dm", slug=slug))
    return render_template("dm/add_npc.html", meta=meta, slug=slug,
                           factions=db.get_factions(slug))


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
            image_url=request.form.get("image_url", "").strip() if _allowed_image_url(request.form.get("image_url", "").strip())[0] else None,
            dm_notes=request.form.get("dm_notes", "").strip() or None,
        )
        if request.form.get("ajax"):
            return jsonify({"ok": True})
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


@app.route("/<slug>/assets/item/<int:idx>/edit", methods=["POST"])
def edit_item(slug, idx):
    r = campaign_access(slug)
    if r: return r
    name = request.form.get("name", "").strip()
    if name:
        db.edit_item(slug, idx, name, request.form.get("notes", "").strip())
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
    r = campaign_access(slug)
    if r: return r
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


@app.route("/<slug>/dm/npc/<npc_id>/log/<event_id>/edit", methods=["POST"])
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
    return redirect(url_for("npc", slug=slug, npc_id=npc_id))


@app.route("/<slug>/dm/faction/<faction_id>/log/<int:idx>/delete", methods=["POST"])
@dm_required
def dm_delete_faction_log(slug, faction_id, idx):
    db.delete_faction_log_entry(slug, faction_id, idx)
    return redirect(url_for("faction", slug=slug, faction_id=faction_id))


@app.route("/<slug>/dm/faction/<faction_id>/log/<event_id>/edit", methods=["POST"])
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
    return redirect(url_for("faction", slug=slug, faction_id=faction_id))


@app.route("/<slug>/dm/event/<event_id>/undo_ripple", methods=["POST"])
@dm_required
def dm_undo_ripple(slug, event_id):
    removed = db.undo_ripple_chain(slug, event_id)
    if removed:
        flash(f"Removed {removed} ripple event{'s' if removed != 1 else ''}", "success")
    else:
        flash("No ripple events found for this entry", "info")
    next_url = request.form.get("next") or request.referrer or url_for("dm", slug=slug)
    return redirect(next_url)


@app.route("/<slug>/dm/event/<event_id>/delete_entry", methods=["POST"])
@dm_required
def dm_delete_log_entry_by_id(slug, event_id):
    entity_type = request.form.get("entity_type")
    entity_id = request.form.get("entity_id")
    db.delete_log_entry_by_id(slug, entity_id, entity_type, event_id)
    next_url = request.form.get("next") or request.referrer or url_for("dm", slug=slug)
    return redirect(next_url)


@app.route("/<slug>/dm/log/event/delete", methods=["POST"])
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


@app.route("/<slug>/dm/log/event/edit", methods=["POST"])
@dm_required
def dm_edit_log_event_ajax(slug):
    data = request.get_json() or {}
    event_id = data.get("event_id", "")
    entity_type = data.get("entity_type", "")
    entity_id = data.get("entity_id", "")
    if not event_id or not entity_type:
        return jsonify({"error": "missing fields"}), 400
    db.edit_log_entry(slug, entity_id, entity_type, event_id,
                      note=data.get("note") or None,
                      polarity=data.get("polarity") or "",
                      intensity=data.get("intensity"))
    return jsonify({"ok": True})


@app.route("/<slug>/dm/event/<event_id>/restore_ripple", methods=["POST"])
@dm_required
def dm_restore_ripple(slug, event_id):
    entity_type = request.form.get("entity_type")
    entity_id = request.form.get("entity_id")
    db.restore_log_entry_by_id(slug, entity_id, entity_type, event_id)
    next_url = request.form.get("next") or request.referrer or url_for("dm", slug=slug)
    return redirect(next_url)


@app.route("/<slug>/dm/event/<event_id>/move", methods=["POST"])
@dm_required
def dm_move_log_entry(slug, event_id):
    source_type = request.form.get("source_type")
    source_id = request.form.get("source_id")
    target = request.form.get("target", "")
    if not target or ":" not in target:
        abort(400)
    target_type, target_id = target.split(":", 1)
    db.move_log_entry(slug, source_id, source_type, event_id, target_id, target_type)
    next_url = request.form.get("next") or request.referrer or url_for("dm", slug=slug)
    return redirect(next_url)


@app.route("/<slug>/dm/session/discard_proposals", methods=["POST"])
@dm_required
def dm_discard_proposals(slug):
    db.clear_proposals(slug)
    return ("", 204)


# ── Condition routes ──────────────────────────────────────────────────────────

@app.route("/<slug>/dm/conditions/add", methods=["POST"])
@dm_required
def dm_add_condition(slug):
    name = request.form.get("name", "").strip()
    if not name:
        flash("Condition name required.", "error")
        return redirect(url_for("dm", slug=slug))
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
    return redirect(url_for("dm", slug=slug))


@app.route("/<slug>/dm/condition/<condition_id>/delete", methods=["POST"])
@dm_required
def dm_delete_condition(slug, condition_id):
    db.delete_condition(slug, condition_id)
    return redirect(url_for("dm", slug=slug))


@app.route("/<slug>/dm/condition/<condition_id>/status", methods=["POST"])
@dm_required
def dm_toggle_condition_status(slug, condition_id):
    conditions = db.get_conditions(slug, include_hidden=True, include_resolved=True)
    c = next((x for x in conditions if x["id"] == condition_id), None)
    if c:
        db.set_condition_status(slug, condition_id, "resolved" if c.get("status") == "active" else "active")
    return redirect(request.form.get("next") or url_for("dm", slug=slug))


@app.route("/<slug>/dm/condition/<condition_id>/toggle_hidden", methods=["POST"])
@dm_required
def dm_toggle_condition_hidden(slug, condition_id):
    conditions = db.get_conditions(slug, include_hidden=True, include_resolved=True)
    c = next((x for x in conditions if x["id"] == condition_id), None)
    if c:
        db.set_condition_hidden(slug, condition_id, not c.get("hidden", True))
    return redirect(request.form.get("next") or url_for("dm", slug=slug))


@app.route("/<slug>/dm/condition/<condition_id>/log/<int:idx>/delete", methods=["POST"])
@dm_required
def dm_delete_condition_log(slug, condition_id, idx):
    db.delete_condition_log_entry(slug, condition_id, idx)
    return redirect(request.form.get("next") or url_for("dm", slug=slug))


@app.route("/<slug>/dm/world/futures", methods=["POST"])
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


@app.route("/<slug>/dm/world/confirm_projection", methods=["POST"])
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


@app.route("/<slug>/dm/world/dismiss_projection", methods=["POST"])
@dm_required
def dm_dismiss_projection(slug):
    data = request.get_json()
    db.dismiss_projection(slug, data.get("entity_id"), data.get("entity_type", "npc"), data.get("event_id"))
    return jsonify({"ok": True})


@app.route("/<slug>/dm/world/commit_futures", methods=["POST"])
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


@app.route("/<slug>/dm/character/<char_name>/toggle_dead", methods=["POST"])
@dm_required
def dm_toggle_character_dead(slug, char_name):
    chars = db.get_party(slug)
    char = next((c for c in chars if c["name"] == char_name), None)
    if char:
        db.set_character_dead(slug, char_name, not char.get("dead", False))
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


@app.route("/<slug>/dm/npc/<npc_id>/toggle_dead", methods=["POST"])
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
        return redirect(url_for("dm", slug=slug))
    return redirect(url_for("npc", slug=slug, npc_id=npc_id))


@app.route("/<slug>/dm/npc/<npc_id>/toggle_party_affiliate", methods=["POST"])
@dm_required
def dm_toggle_npc_party_affiliate(slug, npc_id):
    npcs = db.get_npcs(slug)
    npc = next((n for n in npcs if n["id"] == npc_id), None)
    if npc:
        db.set_npc_party_affiliate(slug, npc_id, not npc.get("party_affiliate", False))
    if request.form.get("ajax"):
        return jsonify(ok=True)
    if request.form.get("next") == "dm":
        return redirect(url_for("dm", slug=slug))
    return redirect(url_for("npc", slug=slug, npc_id=npc_id))


@app.route("/<slug>/dm/npc/<npc_id>/edit", methods=["POST"])
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
        return redirect(url_for("dm", slug=slug))
    return redirect(url_for("npc", slug=slug, npc_id=npc_id))


@app.route("/<slug>/dm/npc/<npc_id>/notes", methods=["POST"])
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
        return redirect(url_for("npc", slug=slug, npc_id=npc_id))
    db.update_npc(slug, npc_id, description=description or None, dm_notes=dm_notes if "dm_notes" in request.form else None, image_url=image_url or None)
    if request.form.get("ajax"):
        return jsonify({"ok": True})
    return redirect(url_for("npc", slug=slug, npc_id=npc_id))


@app.route("/<slug>/dm/npc/<npc_id>/log", methods=["POST"])
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
                            event_type, visibility=visibility, source_event_id=src_evt)
        if src_evt:
            for w in witnesses:
                db.reveal_event(slug, src_evt, w)
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


@app.route("/<slug>/dm/faction/<faction_id>/toggle_party_affiliated", methods=["POST"])
@dm_required
def dm_toggle_faction_party_affiliated(slug, faction_id):
    faction = next((f for f in db.get_factions(slug, include_hidden=True) if f["id"] == faction_id), None)
    if faction:
        db.set_faction_party_affiliated(slug, faction_id, not faction.get("party_affiliated", False))
    next_url = request.form.get("next") or url_for("faction", slug=slug, faction_id=faction_id)
    return redirect(next_url)


@app.route("/<slug>/dm/faction/<faction_id>/toggle_char_member", methods=["POST"])
@dm_required
def dm_toggle_faction_char_member(slug, faction_id):
    char_name = request.form.get("char_name", "").strip()
    faction = next((f for f in db.get_factions(slug, include_hidden=True) if f["id"] == faction_id), None)
    if faction and char_name:
        currently = char_name in faction.get("affiliated_chars", [])
        db.set_faction_char_member(slug, faction_id, char_name, not currently)
    next_url = request.form.get("next") or url_for("faction", slug=slug, faction_id=faction_id)
    return redirect(next_url)


@app.route("/<slug>/dm/faction/<faction_id>/edit", methods=["POST"])
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
        return redirect(url_for("dm", slug=slug))
    return redirect(url_for("faction", slug=slug, faction_id=faction_id))


@app.route("/<slug>/dm/faction/<faction_id>/notes", methods=["POST"])
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
        return redirect(url_for("faction", slug=slug, faction_id=faction_id))
    db.update_faction(slug, faction_id, description=description or None, dm_notes=dm_notes if "dm_notes" in request.form else None, image_url=image_url or None)
    if request.form.get("ajax"):
        return jsonify({"ok": True})
    return redirect(url_for("faction", slug=slug, faction_id=faction_id))


@app.route("/<slug>/dm/faction/<faction_id>/log", methods=["POST"])
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
                            event_type, visibility=visibility, source_event_id=src_evt)
        if src_evt:
            for w in witnesses:
                db.reveal_event(slug, src_evt, w)
        flash("Entry added", "success")
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


@app.route("/<slug>/dm/npc/<npc_id>/relation", methods=["POST"])
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
        return redirect(url_for("dm", slug=slug))
    return redirect(url_for("npc", slug=slug, npc_id=npc_id))


@app.route("/<slug>/dm/npc/<npc_id>/relation/<int:rel_idx>/delete", methods=["POST"])
@dm_required
def dm_remove_npc_relation(slug, npc_id, rel_idx):
    db.remove_npc_relation(slug, npc_id, rel_idx)
    if request.form.get("ajax"):
        return jsonify({"ok": True})
    if request.form.get("next") == "dm":
        return redirect(url_for("dm", slug=slug))
    return redirect(url_for("npc", slug=slug, npc_id=npc_id))


@app.route("/<slug>/dm/faction/<faction_id>/relation", methods=["POST"])
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
        return redirect(url_for("dm", slug=slug))
    return redirect(url_for("faction", slug=slug, faction_id=faction_id))


@app.route("/<slug>/dm/faction/<faction_id>/relation/<int:rel_idx>/delete", methods=["POST"])
@dm_required
def dm_remove_faction_relation(slug, faction_id, rel_idx):
    db.remove_faction_relation(slug, faction_id, rel_idx)
    if request.form.get("ajax"):
        return jsonify({"ok": True})
    if request.form.get("next") == "dm":
        return redirect(url_for("dm", slug=slug))
    return redirect(url_for("faction", slug=slug, faction_id=faction_id))


@app.route("/<slug>/dm/location/add", methods=["POST"])
@dm_required
def dm_add_location(slug):
    name = request.form.get("name", "").strip()
    if not name:
        flash("Name required", "error")
        return redirect(url_for("dm", slug=slug))
    loc_id = db.add_location(slug, name,
                             role=request.form.get("role", "").strip() or None,
                             description=request.form.get("description", "").strip(),
                             hidden=bool(request.form.get("hidden")),
                             dm_notes=request.form.get("dm_notes", "").strip() or None)
    return redirect(url_for("location", slug=slug, location_id=loc_id))


@app.route("/<slug>/dm/location/<location_id>/toggle_hidden", methods=["POST"])
@dm_required
def dm_location_toggle_hidden(slug, location_id):
    loc = db.get_location(slug, location_id)
    if loc:
        db.set_location_hidden(slug, location_id, not loc.get("hidden", False))
    return redirect(url_for("location", slug=slug, location_id=location_id))


@app.route("/<slug>/dm/location/<location_id>/notes", methods=["POST"])
@dm_required
def dm_location_notes(slug, location_id):
    db.update_location(slug, location_id,
                       description=request.form.get("description", "").strip(),
                       dm_notes=request.form.get("dm_notes", "").strip() or None)
    if request.form.get("ajax"):
        return jsonify({"ok": True})
    return redirect(url_for("location", slug=slug, location_id=location_id))


@app.route("/<slug>/dm/location/<location_id>/edit", methods=["POST"])
@dm_required
def dm_location_edit(slug, location_id):
    db.update_location(slug, location_id,
                       name=request.form.get("name", "").strip() or None,
                       role=request.form.get("role", "").strip() or None)
    return redirect(url_for("location", slug=slug, location_id=location_id))


@app.route("/<slug>/dm/location/<location_id>/log", methods=["POST"])
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
    return redirect(url_for("location", slug=slug, location_id=location_id))


@app.route("/<slug>/dm/location/<location_id>/log/<int:idx>/delete", methods=["POST"])
@dm_required
def dm_location_log_delete(slug, location_id, idx):
    db.delete_location_log_entry(slug, location_id, idx)
    return redirect(url_for("location", slug=slug, location_id=location_id))


@app.route("/<slug>/dm/location/<location_id>/delete", methods=["POST"])
@dm_required
def dm_location_delete(slug, location_id):
    db.delete_location(slug, location_id)
    flash("Location deleted", "success")
    return redirect(url_for("world", slug=slug))


@app.route("/<slug>/dm/party/<party_id>/relation", methods=["POST"])
@dm_required
def dm_add_party_relation(slug, party_id):
    db.add_party_relation(slug,
                          target_id=request.form.get("target_id", "").strip(),
                          target_type=request.form.get("target_type", "faction"),
                          relation=request.form.get("relation", "ally"),
                          weight=float(request.form.get("weight", 0.5)))
    if request.form.get("ajax"):
        return jsonify({"ok": True})
    return redirect(url_for("dm", slug=slug))


@app.route("/<slug>/dm/party/<party_id>/relation/<int:idx>/delete", methods=["POST"])
@dm_required
def dm_remove_party_relation(slug, party_id, idx):
    db.remove_party_relation(slug, idx)
    if request.form.get("ajax"):
        return jsonify({"ok": True})
    return redirect(url_for("dm", slug=slug))


@app.route("/<slug>/dm/npc/<npc_id>/event/<event_id>/reveal", methods=["POST"])
@dm_required
def dm_reveal_event(slug, npc_id, event_id):
    char_name = request.form.get("char_name", "").strip()
    if char_name:
        db.reveal_event(slug, event_id, char_name)
        flash(f"Revealed to {char_name}", "success")
    return redirect(url_for("npc", slug=slug, npc_id=npc_id))


@app.route("/<slug>/dm/npc/<npc_id>/char_relation", methods=["POST"])
@dm_required
def dm_add_char_relation_npc(slug, npc_id):
    char_name = request.form.get("char_name", "").strip()
    relation = request.form.get("relation", "ally")
    weight = float(request.form.get("weight", 0.5))
    if char_name:
        db.add_character_relation(slug, char_name, npc_id, "npc", relation, weight)
    if request.form.get("ajax"):
        return jsonify({"ok": True})
    return redirect(url_for("npc", slug=slug, npc_id=npc_id))


@app.route("/<slug>/dm/npc/<npc_id>/char_relation/delete", methods=["POST"])
@dm_required
def dm_remove_char_relation_npc(slug, npc_id):
    char_name = request.form.get("char_name", "").strip()
    if char_name:
        db.remove_character_relation(slug, char_name, npc_id)
    if request.form.get("ajax"):
        return jsonify({"ok": True})
    return redirect(url_for("npc", slug=slug, npc_id=npc_id))


@app.route("/<slug>/dm/character/<char_name>/relation", methods=["POST"])
@dm_required
def dm_add_char_own_relation(slug, char_name):
    target_id = request.form.get("target_id", "").strip()
    target_type = request.form.get("target_type", "npc")
    relation = request.form.get("relation", "ally")
    weight = float(request.form.get("weight", 0.5))
    if target_id:
        db.add_character_relation(slug, char_name, target_id, target_type, relation, weight)
    if request.form.get("ajax"):
        return jsonify({"ok": True})
    return redirect(url_for("dm", slug=slug))


@app.route("/<slug>/dm/character/<char_name>/relation/<target_id>/delete", methods=["POST"])
@dm_required
def dm_delete_char_own_relation(slug, char_name, target_id):
    db.remove_character_relation(slug, char_name, target_id)
    if request.form.get("ajax"):
        return jsonify({"ok": True})
    return redirect(url_for("dm", slug=slug))


@app.route("/<slug>/dm/npc/<npc_id>/event/<event_id>/witness", methods=["POST"])
@dm_required
def dm_witness_npc_event(slug, npc_id, event_id):
    data = request.get_json()
    char_name = (data or {}).get("char_name", "").strip()
    if not char_name:
        return jsonify({"error": "char_name required"}), 400
    party = db.get_party(slug)
    char = next((c for c in party if c["name"] == char_name), None)
    if not char:
        return jsonify({"error": "Character not found"}), 404
    if event_id in char.get("known_events", []):
        db.unreveal_event(slug, event_id, char_name)
        return jsonify({"known": False})
    else:
        db.reveal_event(slug, event_id, char_name)
        return jsonify({"known": True})


@app.route("/<slug>/dm/faction/<faction_id>/event/<event_id>/witness", methods=["POST"])
@dm_required
def dm_witness_faction_event(slug, faction_id, event_id):
    data = request.get_json()
    char_name = (data or {}).get("char_name", "").strip()
    if not char_name:
        return jsonify({"error": "char_name required"}), 400
    party = db.get_party(slug)
    char = next((c for c in party if c["name"] == char_name), None)
    if not char:
        return jsonify({"error": "Character not found"}), 404
    if event_id in char.get("known_events", []):
        db.unreveal_event(slug, event_id, char_name)
        return jsonify({"known": False})
    else:
        db.reveal_event(slug, event_id, char_name)
        return jsonify({"known": True})


@app.route("/<slug>/dm/party/<char_name>/assign", methods=["POST"])
@dm_required
def dm_assign_character_user(slug, char_name):
    username = request.form.get("username", "").strip()
    db.assign_character_user(slug, char_name, username)
    flash(f"{'Assigned ' + username if username else 'Unassigned'}", "success")
    return redirect(url_for("dm", slug=slug) + "#world")


@app.route("/<slug>/dm/character/<char_name>/update", methods=["POST"])
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
    return redirect(url_for("party", slug=slug))


@app.route("/<slug>/dm/character/<char_name>/set_faction", methods=["POST"])
@dm_required
def dm_set_character_faction(slug, char_name):
    faction_id = request.form.get("faction_id", "").strip()
    db.update_character(slug, char_name, factions=[faction_id] if faction_id else [])
    return redirect(url_for("dm", slug=slug))


@app.route("/<slug>/dm/character/<char_name>/log/<event_id>/delete", methods=["POST"])
@dm_required
def dm_delete_character_log(slug, char_name, event_id):
    db.delete_log_entry_by_id(slug, char_name, "character", event_id)
    return redirect(url_for("party", slug=slug))


@app.route("/<slug>/dm/character/<char_name>/log/<event_id>/edit", methods=["POST"])
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
    return redirect(url_for("party", slug=slug))


@app.route("/<slug>/dm/character/<char_name>/condition/add", methods=["POST"])
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
    return redirect(url_for("party", slug=slug))


@app.route("/<slug>/dm/character/<char_name>/condition/<cond_id>/resolve", methods=["POST"])
@char_or_dm_required
def dm_resolve_character_condition(slug, char_name, cond_id):
    db.resolve_character_condition(slug, char_name, cond_id)
    return redirect(request.form.get("next") or url_for("party", slug=slug))


@app.route("/<slug>/dm/character/<char_name>/condition/<cond_id>/toggle_hidden", methods=["POST"])
@dm_required
def dm_toggle_character_condition_hidden(slug, char_name, cond_id):
    db.toggle_character_condition_hidden(slug, char_name, cond_id)
    return redirect(request.form.get("next") or url_for("party", slug=slug))


@app.route("/<slug>/dm/character/<char_name>/condition/<cond_id>/delete", methods=["POST"])
@char_or_dm_required
def dm_delete_character_condition(slug, char_name, cond_id):
    db.delete_character_condition(slug, char_name, cond_id)
    return redirect(request.form.get("next") or url_for("party", slug=slug))


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


@app.route("/<slug>/dm/members/add", methods=["POST"])
@login_required
@dm_required
def dm_member_add(slug):
    meta = load(slug, "campaign.json")
    if meta.get("owner") != session.get("user"):
        abort(403)
    username = request.form.get("username", "").strip().lower()
    users = load_users()
    if not username or username not in users:
        flash(f"User '{username}' not found.", "error")
        return redirect(url_for("dm", slug=slug) + "#share")
    members = meta.get("members", [])
    if username not in members and username != meta.get("owner"):
        members.append(username)
        meta["members"] = members
        (CAMPAIGNS / slug / "campaign.json").write_text(json.dumps(meta, indent=2))
    return redirect(url_for("dm", slug=slug) + "#share")


@app.route("/<slug>/dm/members/remove", methods=["POST"])
@login_required
@dm_required
def dm_member_remove(slug):
    meta = load(slug, "campaign.json")
    if meta.get("owner") != session.get("user"):
        abort(403)
    username = request.form.get("username", "").strip()
    members = meta.get("members", [])
    meta["members"] = [m for m in members if m != username]
    (CAMPAIGNS / slug / "campaign.json").write_text(json.dumps(meta, indent=2))
    return redirect(url_for("dm", slug=slug) + "#share")


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
    meta["party_name"] = request.form.get("party_name", "").strip()
    meta["observer_name"] = request.form.get("observer_name", "").strip()
    new_pin = request.form.get("dm_pin", "").strip()
    if new_pin and new_pin.isdigit() and 4 <= len(new_pin) <= 8:
        meta["dm_pin"] = new_pin
    (CAMPAIGNS / slug / "campaign.json").write_text(json.dumps(meta, indent=2))
    flash("Settings saved", "success")
    return redirect(url_for("dm", slug=slug))


@app.route("/<slug>/dm/set_observer", methods=["POST"])
@dm_required
def dm_set_observer(slug):
    meta = load(slug, "campaign.json")
    observer = request.form.get("observer_name", "").strip()
    if observer:
        meta["observer_name"] = observer
        (CAMPAIGNS / slug / "campaign.json").write_text(json.dumps(meta, indent=2))
    return redirect(url_for("dm", slug=slug))


@app.route("/<slug>/dm/delete", methods=["POST"])
@login_required
@dm_required
def dm_delete_campaign(slug):
    meta = load(slug, "campaign.json")
    if meta.get("owner") != session.get("user"):
        abort(403)
    if meta.get("demo"):
        flash("Starter content cannot be deleted.", "error")
        return redirect(url_for("dm", slug=slug))
    if request.form.get("confirm_name", "").strip() != meta.get("name", ""):
        flash("Campaign name didn't match — not deleted.", "error")
        return redirect(url_for("dm", slug=slug))
    shutil.rmtree(str(CAMPAIGNS / slug))
    session.pop(f"dm_{slug}", None)
    flash("Campaign deleted.", "success")
    return redirect(url_for("index"))


# ── Admin routes ──────────────────────────────────────────────────────────────

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("admin"):
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return decorated


@app.route("/admin/login", methods=["GET", "POST"])
@limiter.limit("10 per hour", methods=["POST"])
def admin_login():
    if session.get("admin"):
        return redirect(url_for("admin_index"))
    error = None
    if request.method == "POST":
        pin = request.form.get("pin", "").strip()
        admin_pin = os.environ.get("ADMIN_PIN", "")
        if admin_pin and pin == admin_pin:
            session["admin"] = True
            return redirect(url_for("admin_index"))
        error = "Invalid admin PIN."
    return render_template("admin/login.html", error=error)


@app.route("/admin/logout", methods=["POST"])
def admin_logout():
    session.pop("admin", None)
    return redirect(url_for("admin_login"))


@app.route("/admin")
@admin_required
def admin_index():
    users = load_users()
    all_campaigns = []
    for d in sorted(CAMPAIGNS.iterdir()):
        if d.is_dir() and (d / "campaign.json").exists():
            meta = json.loads((d / "campaign.json").read_text())
            if not meta.get("demo_mode"):
                all_campaigns.append({"slug": d.name, "name": meta.get("name", d.name),
                                       "owner": meta.get("owner", ""), "has_pin": bool(meta.get("dm_pin"))})
    return render_template("admin/index.html", users=users, campaigns=all_campaigns)



@app.route("/admin/campaign/<slug>/pin", methods=["POST"])
@admin_required
def admin_reset_dm_pin(slug):
    new_pin = request.form.get("new_pin", "").strip()
    if not new_pin:
        return redirect(url_for("admin_index"))
    p = CAMPAIGNS / slug / "campaign.json"
    if not p.exists():
        abort(404)
    meta = json.loads(p.read_text())
    meta["dm_pin"] = new_pin
    p.write_text(json.dumps(meta, indent=2))
    return redirect(url_for("admin_index"))


# ── Account routes ─────────────────────────────────────────────────────────────


# ── Billing routes ─────────────────────────────────────────────────────────────

@app.route("/billing")
@login_required
def billing():
    username = session["user"]
    users = load_users()
    user = users.get(username, {})
    is_pro = user.get("subscription_status") in ("active", "trialing")
    cancel_at_period_end = user.get("cancel_at_period_end", False)
    period_end_ts = user.get("subscription_period_end")
    cancel_date = None
    if cancel_at_period_end and period_end_ts:
        import datetime as _dt
        cancel_date = _dt.datetime.utcfromtimestamp(period_end_ts).strftime("%B %-d, %Y")
    used = _user_world_count(username)
    limit = user.get("world_limit", 3) + user.get("extra_worlds", 0)
    return render_template("billing.html",
        is_pro=is_pro,
        cancel_at_period_end=cancel_at_period_end,
        cancel_date=cancel_date,
        worlds_used=used,
        worlds_limit=limit,
        stripe_pk=STRIPE_PUBLISHABLE_KEY,
    )


@app.route("/billing/checkout/pro-annual", methods=["POST"])
@login_required
def billing_checkout_pro_annual():
    username = session["user"]
    users = load_users()
    user = users.get(username, {})
    if user.get("subscription_status") == "active":
        flash("You're already on Pro.", "info")
        return redirect(url_for("billing"))
    try:
        checkout = stripe.checkout.Session.create(
            payment_method_types=["card"],
            mode="subscription",
            line_items=[{"price": STRIPE_PRICE_PRO_ANNUAL, "quantity": 1}],
            metadata={"username": username},
            success_url=request.host_url.rstrip("/") + "/billing/pro/success?session_id={CHECKOUT_SESSION_ID}",
            cancel_url=request.host_url.rstrip("/") + url_for("billing"),
        )
        return redirect(checkout.url)
    except stripe.StripeError:
        flash("Could not start checkout. Please try again.", "error")
        return redirect(url_for("billing"))


@app.route("/billing/checkout/pro", methods=["POST"])
@login_required
def billing_checkout_pro():
    username = session["user"]
    users = load_users()
    user = users.get(username, {})
    if user.get("subscription_status") == "active":
        flash("You're already on Pro.", "info")
        return redirect(url_for("billing"))
    try:
        checkout = stripe.checkout.Session.create(
            payment_method_types=["card"],
            mode="subscription",
            line_items=[{"price": STRIPE_PRICE_PRO, "quantity": 1}],
            metadata={"username": username},
            subscription_data={"trial_period_days": 14},
            success_url=request.host_url.rstrip("/") + "/billing/pro/success?session_id={CHECKOUT_SESSION_ID}",
            cancel_url=request.host_url.rstrip("/") + url_for("billing"),
        )
        return redirect(checkout.url)
    except stripe.StripeError as e:
        flash("Could not start checkout. Please try again.", "error")
        return redirect(url_for("billing"))


@app.route("/billing/pro/success")
@login_required
def billing_pro_success():
    session_id = request.args.get("session_id")
    if not session_id:
        abort(400)
    try:
        cs = stripe.checkout.Session.retrieve(session_id, expand=["subscription"])
    except stripe.StripeError:
        abort(400)
    username = getattr(cs.metadata, "username", None)
    if username != session.get("user"):
        abort(403)
    users = load_users()
    u = users.get(username, {})
    u["subscription_status"] = "active"
    u["stripe_customer_id"] = cs.customer
    u["stripe_subscription_id"] = cs.subscription.id if cs.subscription else None
    u["world_limit"] = 10
    u["ai_enabled"] = True
    users[username] = u
    save_users(users)
    flash("Welcome to Pro! You now have 10 worlds and AI features unlocked.", "success")
    return redirect(url_for("index"))


@app.route("/billing/world/success")
@login_required
def billing_world_success():
    session_id = request.args.get("session_id")
    if not session_id:
        abort(400)
    try:
        cs = stripe.checkout.Session.retrieve(session_id)
    except stripe.StripeError:
        abort(400)
    if cs.payment_status != "paid":
        flash("Payment not completed.", "error")
        return redirect(url_for("index"))
    username = getattr(cs.metadata, "username", None)
    if username != session.get("user"):
        abort(403)
    source_slug = getattr(cs.metadata, "source_slug", "example")
    template = getattr(cs.metadata, "template", "ttrpg")
    dm_pin = getattr(cs.metadata, "dm_pin", "")
    src = CAMPAIGNS / source_slug
    if not src.exists():
        src = CAMPAIGNS / "example"
    new_slug = secrets.token_hex(4)
    dst = CAMPAIGNS / new_slug
    shutil.copytree(str(src), str(dst))
    new_meta = json.loads((dst / "campaign.json").read_text())
    new_meta["slug"] = new_slug
    new_meta["owner"] = username
    new_meta.pop("demo", None)
    new_meta.pop("public", None)
    new_meta["dm_pin"] = dm_pin if dm_pin else str(secrets.randbelow(9000) + 1000)
    new_meta["created"] = datetime.date.today().isoformat()
    if source_slug == "example":
        new_meta["mode"] = template
        tmpl = _BLANK_TEMPLATES.get(template, {})
        if tmpl:
            new_meta["terminology"] = {k: v for k, v in tmpl.items() if k != "observer_default"}
            if not new_meta.get("observer_name") and "observer_default" in tmpl:
                new_meta["observer_name"] = tmpl["observer_default"]
        else:
            new_meta.pop("terminology", None)
    (dst / "campaign.json").write_text(json.dumps(new_meta, indent=2))
    session[f"dm_{new_slug}"] = True
    flash("World created!", "success")
    return redirect(url_for("dm", slug=new_slug))


@app.route("/billing/party/success")
@login_required
def billing_party_success():
    session_id = request.args.get("session_id")
    if not session_id:
        abort(400)
    try:
        cs = stripe.checkout.Session.retrieve(session_id)
    except stripe.StripeError:
        abort(400)
    if cs.payment_status != "paid":
        flash("Payment not completed.", "error")
        return redirect(url_for("index"))
    username = getattr(cs.metadata, "username", None)
    if username != session.get("user"):
        abort(403)
    result = _create_onboarding_campaign(username, "party")
    if isinstance(result, str):
        return redirect(url_for("party_play", slug=result))
    flash("Payment received! You can now start your party game.", "success")
    return redirect(url_for("index"))


@app.route("/billing/portal", methods=["POST"])
@login_required
def billing_portal():
    username = session["user"]
    users = load_users()
    u = users.get(username, {})
    customer_id = u.get("stripe_customer_id")
    if not customer_id:
        flash("No active subscription found.", "error")
        return redirect(url_for("billing"))
    try:
        portal = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=request.host_url.rstrip("/") + url_for("billing"),
        )
        return redirect(portal.url)
    except stripe.StripeError:
        flash("Could not open billing portal. Please try again.", "error")
        return redirect(url_for("billing"))


@app.route("/stripe/webhook", methods=["POST"])
def stripe_webhook():
    payload = request.get_data()
    sig = request.headers.get("Stripe-Signature", "")
    if STRIPE_WEBHOOK_SECRET:
        try:
            event = stripe.Webhook.construct_event(payload, sig, STRIPE_WEBHOOK_SECRET)
        except (stripe.errors.SignatureVerificationError, ValueError):
            abort(400)
    else:
        try:
            event = json.loads(payload)
        except json.JSONDecodeError:
            abort(400)
    if event["type"] in ("customer.subscription.updated", "customer.subscription.deleted"):
        sub = event["data"]["object"]
        status = sub["status"]
        cancel_at_period_end = sub.get("cancel_at_period_end", False)
        current_period_end = sub.get("current_period_end")
        users = load_users()
        for uname, u in users.items():
            if u.get("stripe_subscription_id") == sub["id"]:
                u["subscription_status"] = status
                u["cancel_at_period_end"] = cancel_at_period_end
                u["subscription_period_end"] = current_period_end
                if status not in ("active", "trialing"):
                    u["world_limit"] = 3
                    u["cancel_at_period_end"] = False
                save_users(users)
                break
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=5052)
