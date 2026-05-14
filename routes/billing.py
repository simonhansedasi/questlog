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

billing_bp = Blueprint('billing_bp', __name__)

@billing_bp.route("/billing")
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


@billing_bp.route("/billing/checkout/pro-annual", methods=["POST"])
@login_required
def billing_checkout_pro_annual():
    username = session["user"]
    users = load_users()
    user = users.get(username, {})
    if user.get("subscription_status") == "active":
        flash("You're already on Pro.", "info")
        return redirect(url_for("billing_bp.billing"))
    try:
        checkout = stripe.checkout.Session.create(
            payment_method_types=["card"],
            mode="subscription",
            line_items=[{"price": STRIPE_PRICE_PRO_ANNUAL, "quantity": 1}],
            metadata={"username": username},
            success_url=request.host_url.rstrip("/") + "/billing/pro/success?session_id={CHECKOUT_SESSION_ID}",
            cancel_url=request.host_url.rstrip("/") + url_for("billing_bp.billing"),
        )
        return redirect(checkout.url)
    except stripe.StripeError:
        flash("Could not start checkout. Please try again.", "error")
        return redirect(url_for("billing_bp.billing"))


@billing_bp.route("/billing/checkout/pro", methods=["POST"])
@login_required
def billing_checkout_pro():
    username = session["user"]
    users = load_users()
    user = users.get(username, {})
    if user.get("subscription_status") == "active":
        flash("You're already on Pro.", "info")
        return redirect(url_for("billing_bp.billing"))
    try:
        checkout = stripe.checkout.Session.create(
            payment_method_types=["card"],
            mode="subscription",
            line_items=[{"price": STRIPE_PRICE_PRO, "quantity": 1}],
            metadata={"username": username},
            subscription_data={"trial_period_days": 14},
            success_url=request.host_url.rstrip("/") + "/billing/pro/success?session_id={CHECKOUT_SESSION_ID}",
            cancel_url=request.host_url.rstrip("/") + url_for("billing_bp.billing"),
        )
        return redirect(checkout.url)
    except stripe.StripeError as e:
        flash("Could not start checkout. Please try again.", "error")
        return redirect(url_for("billing_bp.billing"))


@billing_bp.route("/billing/pro/success")
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
    return redirect(url_for("player.index"))


@billing_bp.route("/billing/world/success")
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
        return redirect(url_for("player.index"))
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
    return redirect(url_for("dm_bp.dm", slug=new_slug))


@billing_bp.route("/billing/transfer/success")
@login_required
def billing_transfer_success():
    session_id = request.args.get("session_id")
    if not session_id:
        abort(400)
    try:
        cs = stripe.checkout.Session.retrieve(session_id)
    except stripe.StripeError:
        abort(400)
    if cs.payment_status != "paid":
        flash("Payment not completed.", "error")
        return redirect(url_for("player.index"))
    username = getattr(cs.metadata, "username", None)
    if username != session.get("user"):
        abort(403)
    if getattr(cs.metadata, "action", None) != "accept_transfer":
        abort(400)
    slug = getattr(cs.metadata, "transfer_slug", None)
    if not slug:
        abort(400)
    cf = CAMPAIGNS / slug / "campaign.json"
    if not cf.exists():
        flash("The world no longer exists.", "error")
        return redirect(url_for("player.index"))
    meta = json.loads(cf.read_text())
    pt = meta.get("pending_transfer")
    if not pt or pt.get("to_username") != username:
        flash("Transfer is no longer pending.", "error")
        return redirect(url_for("player.index"))
    meta["owner"] = username
    meta.pop("pending_transfer", None)
    cf.write_text(json.dumps(meta, indent=2))
    session[f"dm_{slug}"] = True
    flash(f"World transferred! Welcome to {meta.get('name', 'your new world')}.", "success")
    return redirect(url_for("dm_bp.dm", slug=slug))


@billing_bp.route("/billing/portal", methods=["POST"])
@login_required
def billing_portal():
    username = session["user"]
    users = load_users()
    u = users.get(username, {})
    customer_id = u.get("stripe_customer_id")
    if not customer_id:
        flash("No active subscription found.", "error")
        return redirect(url_for("billing_bp.billing"))
    try:
        portal = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=request.host_url.rstrip("/") + url_for("billing_bp.billing"),
        )
        return redirect(portal.url)
    except stripe.StripeError:
        flash("Could not open billing portal. Please try again.", "error")
        return redirect(url_for("billing_bp.billing"))


@billing_bp.route("/stripe/webhook", methods=["POST"])
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
