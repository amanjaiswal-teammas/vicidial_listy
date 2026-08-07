"""Translate gateway payloads into stable, IVR-safe routing decisions."""

from __future__ import annotations

from datetime import timezone, datetime, timedelta
import os
from typing import Any

from services.external_gateway import ExternalGateway, GatewayError

UTC = timezone.utc


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        pass
    # Shiprocket's own date fields (e.g. delivered_date, and whatever the
    # EDD field turns out to be) have shown up as "YYYY-MM-DD HH:MM:SS"
    # rather than ISO-8601 with a "T" — try that shape too.
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
    except ValueError:
        return None


def _latest_order(customer: dict[str, Any]) -> dict[str, Any] | None:
    nodes = customer.get("orders", {}).get("nodes", [])
    candidates = [node for node in nodes if isinstance(node, dict)]
    if not candidates:
        return None
    return max(candidates, key=lambda order: _parse_timestamp(order.get("processedAt") or order.get("createdAt")) or datetime.min.replace(tzinfo=UTC))



def _shipment_summary(tracking: dict[str, Any]) -> dict[str, Any] | None:
    tracking_data = tracking.get("tracking_data", {})
    tracks = tracking_data.get("shipment_track", []) if isinstance(tracking_data, dict) else []
    first = tracks[0] if tracks and isinstance(tracks[0], dict) else {}

    # NOTE: the API guide's tracking payload example is abridged and doesn't
    # document an estimated-delivery-date field. Shiprocket's live API has
    # used different key names across versions (edd, etd,
    # expected_delivery_date), sometimes on the track entry and sometimes on
    # tracking_data itself. Trying the common candidates here as a best
    # effort — VERIFY the actual key against a live response and adjust if
    # it doesn't match; until then this may just come back None.
    estimated_delivery = (
        first.get("edd")
        or first.get("etd")
        or first.get("expected_delivery_date")
        or (tracking_data.get("edd") if isinstance(tracking_data, dict) else None)
        or (tracking_data.get("expected_delivery_date") if isinstance(tracking_data, dict) else None)
    )

    return {
        "known": tracking_data.get("track_status") == 1,
        "status": first.get("current_status"),
        "courier": first.get("courier_name"),
        "awb": first.get("awb_code"),
        "tracking_url": tracking_data.get("track_url"),
        "delivered_date": first.get("delivered_date"),
        "estimated_delivery": estimated_delivery,
    }


def _gateway_failure(error: GatewayError) -> dict[str, Any]:
    if error.status_code == 404:
        return {"outcome": "CUSTOMER_NOT_FOUND", "prompt_id": "customer_not_found", "handoff": False}
    if error.status_code == 409:
        return {"outcome": "CUSTOMER_AMBIGUOUS", "prompt_id": "agent_handoff", "handoff": True}
    return {
        "outcome": "SERVICE_UNAVAILABLE",
        "prompt_id": "agent_handoff",
        "handoff": True,
        "request_id": error.request_id,
    }


def _humanize_status(value: str | None) -> str:
    """Shopify/Shiprocket statuses come back SCREAMING_SNAKE or Title Case
    ("UNFULFILLED", "In Transit") — lowercase and de-underscore them so they
    read naturally if ever logged or used for TTS."""
    if not value:
        return "being processed"
    return value.replace("_", " ").strip().lower()


# Static .wav playback: both Shopify's displayFulfillmentStatus (a fixed
# enum) and Shiprocket's current_status (free text - NOT a fixed enum, see
# the caveat given when this was discussed) get normalized into one of
# these closed set of canonical keys, each with a pre-recorded audio file
# per language (sounds/<lang>/status/<key>.wav). Anything that doesn't
# match a keyword falls back to "status_unknown" and gets logged, so you
# can extend the table (and record the matching audio) as new values show up.
#
# Order matters below: more specific checks (e.g. "rto" containing
# "delivered" as in "RTO Delivered") must be checked before the broader
# "delivered" check, or they'd be mis-bucketed.
_STATUS_AUDIO_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("returned", ("rto", "return", "cancel")),
    ("out_for_delivery", ("out for delivery",)),
    ("delivered", ("delivered",)),
    ("in_transit", ("in transit",)),
    ("picked_up", ("picked up", "pickup generated", "out for pickup")),
    ("delayed_pickup", ("pickup error", "pickup exception", "pickup rescheduled", "undelivered", "exception")),
    ("on_hold", ("on hold",)),
    ("scheduled", ("scheduled",)),
    ("partially_fulfilled", ("partially fulfilled",)),
    ("processing", ("in progress", "pending fulfillment")),
    ("unfulfilled", ("unfulfilled", "open", "restocked")),
    ("fulfilled", ("fulfilled",)),  # bare Shopify FULFILLED with no live shipment data - must stay after "unfulfilled"
]


def normalize_status_audio_key(raw_status: str | None) -> str:
    """Map a raw Shopify/Shiprocket status string to one of the canonical
    pre-recorded audio keys. See sounds/manifest.json for the exact file
    per key per language."""
    if not raw_status:
        return "status_unknown"
    normalized = raw_status.strip().lower().replace("_", " ")
    for key, keywords in _STATUS_AUDIO_KEYWORDS:
        if any(kw in normalized for kw in keywords):
            return key
    import logging
    logging.getLogger(__name__).warning("Unmapped status for audio playback: %r - using status_unknown", raw_status)
    return "status_unknown"


def _edd_epoch(shipment: dict[str, Any] | None) -> int | None:
    """Raw estimated-delivery-date as a Unix epoch (seconds), for Asterisk's
    SayUnixTime()/date-speaking apps - NOT a formatted string, since the
    dialplan speaks it itself via a static prompt + dynamic date, rather
    than us handing back finished prose. Returns None if EDD isn't present
    (see the earlier caveat: the API guide doesn't document this field, and
    it may simply be absent on some/all responses until confirmed)."""
    if not shipment:
        return None
    parsed = _parse_timestamp(shipment.get("estimated_delivery"))
    return int(parsed.timestamp()) if parsed else None


def customer_category(
    customer: dict[str, Any],
    *,
    now: datetime | None = None,
    min_orders: int = 3,
    window_days: int = 182,  # ~6 months
) -> str:
    """Classify the Shopify customer by fulfilled-order volume in the trailing window.

    PREMIUM: at least `min_orders` orders with displayFulfillmentStatus == FULFILLED
    whose processedAt/createdAt falls within the last `window_days` days.
    Everyone else is NON_PREMIUM.

    Note: order data comes from the customer's embedded `orders.nodes`, which the
    gateway caps at the 5 most recent orders. If a customer could plausibly have
    more than 5 fulfilled orders in the window, this undercounts rather than
    overcounts — it will never wrongly promote someone to PREMIUM, but it could
    miss a genuinely premium customer whose 6th+ most recent order also qualifies.
    """
    reference = now or datetime.now(UTC)
    cutoff = reference - timedelta(days=window_days)

    nodes = customer.get("orders", {}).get("nodes", [])
    fulfilled_recent = 0
    for node in nodes:
        if not isinstance(node, dict):
            continue
        if str(node.get("displayFulfillmentStatus", "")).upper() != "FULFILLED":
            continue
        placed_at = _parse_timestamp(node.get("processedAt") or node.get("createdAt"))
        if placed_at is not None and placed_at >= cutoff:
            fulfilled_recent += 1

    return "PREMIUM" if fulfilled_recent >= min_orders else "NON_PREMIUM"



async def latest_order_status(gateway: ExternalGateway, caller_number: str) -> dict[str, Any]:
    """Return one of the four order-status branches in the supplied IVR flow."""
    try:
        customer = await gateway.customer_by_phone(caller_number)
    except GatewayError as exc:
        return _gateway_failure(exc)

    category = customer_category(customer)
    order = _latest_order(customer)
    if not order:
        return {
            "outcome": "NO_ORDER",
            "prompt_id": "no_recent_order",
            "handoff": False,
            "customer_category": category,
            "order_status": None,
            "status_audio_key": None,
            "delivery": None,
            "edd_epoch": None,
        }

    placed_at = _parse_timestamp(order.get("processedAt") or order.get("createdAt"))
    age_days = (datetime.now(UTC) - placed_at).days if placed_at else None
    fulfilled = str(order.get("displayFulfillmentStatus", "")).upper() == "FULFILLED"
    fulfillment_status = order.get("displayFulfillmentStatus")
    shipment = None
    tracking_reference = order.get("name")

    # Shiprocket resolves a channel order id/name. Tracking is supplementary: a
    # tracking 404 must not turn an otherwise valid Shopify order into an error.
    if fulfilled and isinstance(tracking_reference, str) and tracking_reference:
        try:
            tracking = await gateway.tracking_by_order(tracking_reference)
            shipment = _shipment_summary(tracking)
        except GatewayError as exc:
            shipment = None
            import logging
            logging.getLogger(__name__).warning(
                "tracking lookup failed for order %s (ref=%s): %s %s",
                order.get("name"), tracking_reference, exc.status_code, exc.message,
            )

    within_five_days = age_days is not None and age_days <= 5
    if fulfilled and within_five_days:
        outcome = "SHIPPED_WITHIN_5_DAYS"
        prompt_id = "shipped_within_5_days"
    elif fulfilled:
        outcome = "SHIPPED_AFTER_5_DAYS"
        prompt_id = "shipped_after_5_days"
    elif within_five_days:
        outcome = "NOT_SHIPPED_WITHIN_5_DAYS"
        prompt_id = "not_shipped_within_5_days"
    else:
        outcome = "NOT_SHIPPED_AFTER_5_DAYS"
        prompt_id = "not_shipped_after_5_days"

    if fulfilled:
        order_status = (shipment or {}).get("status") or fulfillment_status
        delivery = (shipment or {}).get("estimated_delivery") or (shipment or {}).get("delivered_date")
    else:
        order_status = fulfillment_status
        delivery = None

    result = {
        "outcome": outcome,
        "prompt_id": prompt_id,
        "handoff": False,
        "customer_category": category,
        "order_status": order_status,
        "status_audio_key": normalize_status_audio_key(order_status),
        "delivery": delivery,
        "edd_epoch": _edd_epoch(shipment),
        "order": {
            "number": order.get("name"),
            "placed_at": placed_at.isoformat() if placed_at else None,
            "age_days": age_days,
            "fulfillment_status": order.get("displayFulfillmentStatus"),
        },
        "shipment": shipment,
    }
    return result
