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

auth_bp = Blueprint('auth', __name__)

@auth_bp.route("/login", methods=["GET"])
def login():
    if session.get("user"):
        return redirect(url_for("player.index"))
    return render_template("login.html")


@auth_bp.route("/logout", methods=["POST"])
def logout():
    next_url = request.args.get("next", "").strip()
    session.clear()
    if next_url and next_url.startswith("/"):
        session["post_login_next"] = next_url
    return redirect(url_for("auth.login"))


_DEV_TOKEN = os.environ.get("DEV_LOGIN_TOKEN", "")

@auth_bp.route("/dev/login/<token>/<username>")
def dev_login(token, username):
    if not _DEV_TOKEN or token != _DEV_TOKEN:
        abort(404)
    users = load_users()
    if username not in users:
        abort(404)
    session["user"] = username
    session["display_name"] = users[username].get("display_name", username)
    session["admin"] = users[username].get("admin", False)
    return redirect(url_for("player.index"))


@auth_bp.route("/auth/google")
def auth_google():
    redirect_uri = url_for("auth.auth_google_callback", _external=True)
    return oauth.google.authorize_redirect(redirect_uri)


@auth_bp.route("/auth/google/callback")
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
    # Auto-resolve any pending email invites for this user's email
    if email:
        email_lower = email.lower()
        for cdir in CAMPAIGNS.iterdir():
            cjson = cdir / "campaign.json"
            if not cjson.exists():
                continue
            try:
                cmeta = json.loads(cjson.read_text())
                pending = cmeta.get("invited_emails", [])
                if email_lower in pending:
                    cmeta["invited_emails"] = [e for e in pending if e != email_lower]
                    if username not in cmeta.get("members", []) and username != cmeta.get("owner"):
                        cmeta.setdefault("members", []).append(username)
                    cjson.write_text(json.dumps(cmeta, indent=2))
            except Exception:
                pass
    next_url = session.pop("post_login_next", None)
    session["user"] = username
    session["display_name"] = users[username].get("display_name", username)
    if next_url and next_url.startswith("/"):
        return redirect(next_url)
    if is_new_user or not users[username].get("onboarding_seen"):
        return redirect(url_for("auth.welcome"))
    return redirect(url_for("player.index"))


@auth_bp.route("/signup")
def signup():
    return redirect(url_for("auth.login"))
@auth_bp.route("/welcome")
@login_required
def welcome():
    return render_template("welcome.html")


@auth_bp.route("/welcome", methods=["POST"])
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
            return redirect(url_for("player.setup_wizard", slug=result))
        return result or redirect(url_for("player.index"))

    if choice == "campaign":
        user_data = users.get(username, {})
        limit = user_data.get("world_limit", 3) + user_data.get("extra_worlds", 0)
        if _user_world_count(username) >= limit:
            flash("You've reached your world limit. Delete a world to make room.", "error")
            return redirect(url_for("player.index"))
        result = _create_onboarding_campaign(username, "campaign")
        if isinstance(result, str):
            return redirect(url_for("async_camp.async_campaign_lobby", slug=result))
        return result or redirect(url_for("player.index"))

    if choice == "obsidian":
        user_data = users.get(username, {})
        limit = user_data.get("world_limit", 3) + user_data.get("extra_worlds", 0)
        if _user_world_count(username) >= limit:
            flash("You've reached your world limit. Delete a world to make room.", "error")
            return redirect(url_for("player.index"))
        result = _create_onboarding_campaign(username, "obsidian")
        if isinstance(result, str):
            return redirect(url_for("dm_bp.dm_import", slug=result))
        return result or redirect(url_for("player.index"))

    return redirect(url_for("player.index"))
