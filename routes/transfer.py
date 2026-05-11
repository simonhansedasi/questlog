from flask import Blueprint, redirect, url_for, request, session, flash
import json, secrets, datetime
import stripe

from routes.utils import (
    login_required, load_users, load, _user_world_count,
    CAMPAIGNS, STRIPE_PRICE_WORLD,
)

transfer_bp = Blueprint('transfer_bp', __name__)


@transfer_bp.route("/transfer/<slug>/accept", methods=["POST"])
@login_required
def accept(slug):
    username = session["user"]
    meta = load(slug, "campaign.json")
    pt = meta.get("pending_transfer")
    if not pt or pt.get("to_username") != username:
        flash("No pending transfer for you on this world.", "error")
        return redirect(url_for("player.index"))

    users = load_users()
    user = users.get(username, {})
    limit = user.get("world_limit", 3) + user.get("extra_worlds", 0)

    if _user_world_count(username) >= limit:
        try:
            checkout = stripe.checkout.Session.create(
                payment_method_types=["card"],
                mode="payment",
                line_items=[{"price": STRIPE_PRICE_WORLD, "quantity": 1}],
                metadata={"username": username, "action": "accept_transfer", "transfer_slug": slug},
                success_url=request.host_url.rstrip("/") + f"/billing/transfer/success?session_id={{CHECKOUT_SESSION_ID}}",
                cancel_url=request.host_url.rstrip("/") + url_for("player.index"),
            )
            return redirect(checkout.url)
        except stripe.StripeError:
            flash("World limit reached and payment failed. Try again.", "error")
            return redirect(url_for("player.index"))

    meta["owner"] = username
    meta.pop("pending_transfer", None)
    (CAMPAIGNS / slug / "campaign.json").write_text(json.dumps(meta, indent=2))
    session[f"dm_{slug}"] = True
    flash(f"World transferred! Welcome to {meta.get('name', 'your new world')}.", "success")
    return redirect(url_for("dm_bp.dm", slug=slug))


@transfer_bp.route("/transfer/<slug>/decline", methods=["POST"])
@login_required
def decline(slug):
    username = session["user"]
    meta = load(slug, "campaign.json")
    pt = meta.get("pending_transfer")
    if not pt or pt.get("to_username") != username:
        flash("No pending transfer for you on this world.", "error")
        return redirect(url_for("player.index"))

    meta.pop("pending_transfer", None)
    (CAMPAIGNS / slug / "campaign.json").write_text(json.dumps(meta, indent=2))
    flash("Transfer declined.", "success")
    return redirect(url_for("player.index"))
