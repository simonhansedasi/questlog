from flask import Flask, request, session, jsonify
from markupsafe import Markup
from werkzeug.middleware.proxy_fix import ProxyFix
import os, re, uuid

from src import data as db
from dotenv import load_dotenv
load_dotenv()

from extensions import limiter, oauth


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

limiter.init_app(app)
oauth.init_app(app)
oauth.register(
    name="google",
    client_id=os.environ.get("GOOGLE_CLIENT_ID"),
    client_secret=os.environ.get("GOOGLE_CLIENT_SECRET"),
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)

@app.errorhandler(429)
def rate_limit_error(e):
    return jsonify({"error": "Rate limit reached — 30 AI calls per hour. Try again shortly."}), 429


# ── Template filters ──────────────────────────────────────────────────────────

@app.template_filter("compute_rel")
def compute_rel_filter(npc, is_dm=True):
    return db.compute_npc_relationship(npc, is_dm=is_dm)


@app.template_filter("slugify")
def slugify_filter(text):
    return db.slugify(text or "")


@app.template_filter("wikilinks")
def wikilinks_filter(text, slug, npcs, factions, locations=None, party=None):
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
            entity = entity.strip()
            display = display.strip()
        else:
            entity = display = inner.strip()
        key = entity.lower()
        if key in lookup:
            etype, eid = lookup[key]
            if etype == 'location':
                return f'<a href="/{slug}/world/location/{eid}" class="wikilink">{Markup.escape(display)}</a>'
            if etype == 'party':
                return f'<a href="/{slug}/party/char/{eid}" class="wikilink">{Markup.escape(display)}</a>'
            return f'<a href="/{slug}/world/{etype}/{eid}" class="wikilink">{Markup.escape(display)}</a>'
        return str(Markup.escape(display))

    return Markup(re.sub(r'\[\[([^\]\[]+)\]\]', replace, escaped))


# ── After-request hooks ───────────────────────────────────────────────────────

@app.after_request
def stamp_demo_visitor(response):
    if request.path.startswith("/demo") and not request.cookies.get("demo_id"):
        response.set_cookie("demo_id", str(uuid.uuid4()), max_age=30*24*3600, samesite="Lax", httponly=True)
    return response


# ── Context processor ─────────────────────────────────────────────────────────

from routes.utils import (
    load, load_users, _user_world_count, _DEFAULT_TERMS,
)

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


# ── Blueprint registration ────────────────────────────────────────────────────

from routes.auth          import auth_bp
from routes.admin         import admin_bp
from routes.billing       import billing_bp
from routes.party_game    import party_game_bp
from routes.async_campaign import async_camp_bp
from routes.demo          import demo_bp
from routes.player        import player_bp
from routes.dm            import dm_bp
from routes.transfer      import transfer_bp

app.register_blueprint(auth_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(billing_bp)
app.register_blueprint(party_game_bp)
app.register_blueprint(async_camp_bp)
app.register_blueprint(demo_bp)
app.register_blueprint(player_bp)
app.register_blueprint(dm_bp)
app.register_blueprint(transfer_bp)


if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=5052)
