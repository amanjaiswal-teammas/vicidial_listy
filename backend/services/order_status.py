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
    return {
        "known": tracking_data.get("track_status") == 1,
        "status": first.get("current_status"),
        "courier": first.get("courier_name"),
        "awb": first.get("awb_code"),
        "tracking_url": tracking_data.get("track_url"),
        "delivery": first.get("delivered_date"),
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
            "delivery": None,
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
        delivery = (shipment or {}).get("delivery")
    else:
        order_status = fulfillment_status
        delivery = None

    return {
        "outcome": outcome,
        "prompt_id": prompt_id,
        "handoff": False,
        "customer_category": category,
        "order_status": order_status,
        "delivery": delivery,
        "order": {
            "number": order.get("name"),
            "placed_at": placed_at.isoformat() if placed_at else None,
            "age_days": age_days,
            "fulfillment_status": order.get("displayFulfillmentStatus"),
        },
        "shipment": shipment,
    }



