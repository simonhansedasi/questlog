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

admin_bp = Blueprint('admin_bp', __name__)

@admin_bp.route("/admin/invites")
@login_required
@admin_required
def admin_invites():
    invites = load_invites()
    return render_template("admin/invites.html", invites=invites)


@admin_bp.route("/admin/invites/generate", methods=["POST"])
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
def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("admin"):
            return redirect(url_for("admin_bp.admin_login"))
        return f(*args, **kwargs)
    return decorated


@admin_bp.route("/admin/login", methods=["GET", "POST"])
@limiter.limit("10 per hour", methods=["POST"])
def admin_login():
    if session.get("admin"):
        return redirect(url_for("admin_bp.admin_index"))
    error = None
    if request.method == "POST":
        pin = request.form.get("pin", "").strip()
        admin_pin = os.environ.get("ADMIN_PIN", "")
        if admin_pin and pin == admin_pin:
            session["admin"] = True
            return redirect(url_for("admin_bp.admin_index"))
        error = "Invalid admin PIN."
    return render_template("admin/login.html", error=error)


@admin_bp.route("/admin/logout", methods=["POST"])
def admin_logout():
    session.pop("admin", None)
    return redirect(url_for("admin_bp.admin_login"))


@admin_bp.route("/admin")
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



@admin_bp.route("/admin/campaign/<slug>/pin", methods=["POST"])
@admin_required
def admin_reset_dm_pin(slug):
    new_pin = request.form.get("new_pin", "").strip()
    if not new_pin:
        return redirect(url_for("admin_bp.admin_index"))
    p = CAMPAIGNS / slug / "campaign.json"
    if not p.exists():
        abort(404)
    meta = json.loads(p.read_text())
    meta["dm_pin"] = new_pin
    p.write_text(json.dumps(meta, indent=2))
    return redirect(url_for("admin_bp.admin_index"))
