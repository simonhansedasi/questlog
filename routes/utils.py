from flask import session, request, redirect, url_for, abort
from markupsafe import Markup
from pathlib import Path
from functools import wraps
import json, os, re, secrets, datetime, uuid, shutil, time, random, zipfile, io
import stripe

from src import data as db



stripe.api_key = os.environ.get("STRIPE_SECRET_KEY")
STRIPE_PUBLISHABLE_KEY = os.environ.get("STRIPE_PUBLISHABLE_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_SIGNING_SECRET", "")
STRIPE_PRICE_PRO = "price_1TS6sQHVw7SLO5uo3e0vIZZ3"
STRIPE_PRICE_PRO_ANNUAL = "price_1TTWCKHVw7SLO5uofngMWjVK"
STRIPE_PRICE_WORLD = "price_1TS6qIHVw7SLO5uoIpwNWs0n"
STRIPE_PRICE_PARTY = "price_1TTW4AHVw7SLO5uowdfuAKHR"

CAMPAIGNS = Path(__file__).parent.parent / "campaigns"
USERS_FILE = Path(__file__).parent.parent / "users.json"

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


_stats_cache = {"data": None, "ts": 0.0}

def _compute_site_stats():
    now = time.time()
    if _stats_cache["data"] and now - _stats_cache["ts"] < 300:
        return _stats_cache["data"]

    try:
        all_users = json.loads(USERS_FILE.read_text()).get("users", {})
        user_count = sum(1 for u in all_users.values() if u.get("google_sub"))
    except Exception:
        user_count = 0

    world_count = 0
    char_count = 0
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
        if meta.get("demo") or meta.get("demo_mode"):
            continue
        world_count += 1
        try:
            npcs_file = d / "world" / "npcs.json"
            if npcs_file.exists():
                char_count += len(json.loads(npcs_file.read_text()).get("npcs", []))
        except Exception:
            pass
        try:
            party_file = d / "party.json"
            if party_file.exists():
                char_count += len(json.loads(party_file.read_text()).get("characters", []))
        except Exception:
            pass

    stats = {
        "users": f"{user_count:,}",
        "worlds": f"{world_count:,}",
        "characters": f"{char_count:,}",
    }
    _stats_cache["data"] = stats
    _stats_cache["ts"] = now
    return stats
INVITES_FILE = Path(__file__).parent.parent / "invites.json"


_SLUG_RE = re.compile(r'^[a-z0-9][a-z0-9_-]{0,49}$')

def _validate_slug(slug):
    if not _SLUG_RE.match(slug):
        abort(404)

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
            return redirect(url_for("auth.login"))
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
    return redirect(url_for("auth.login"))


def dm_required(f):
    @wraps(f)
    def decorated(slug, *args, **kwargs):
        if not session.get(f"dm_{slug}"):
            # Auto-grant for campaign owner without a redirect
            meta = load(slug, "campaign.json")
            if meta and session.get("user") == meta.get("owner"):
                session[f"dm_{slug}"] = True
            else:
                return redirect(url_for("dm_bp.dm_login", slug=slug))
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
        return redirect(url_for("auth.login"))
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
