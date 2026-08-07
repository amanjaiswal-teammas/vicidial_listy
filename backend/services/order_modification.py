"""Translate gateway payloads into the 'Press 2: Need Changes in the order'
(self-service cancellation) IVR branch.

Flow being modeled:

  Press 2
    -> "Your last order id is X worth Y, consisting of Z. Press 1 to continue,
        Press 2 for a different order id."
    (Press 1, or Press 2 + enter a BVO order id, both land on the same order)
    -> within 30 minutes of the order being placed?
         no  -> "already processed, cannot be cancelled" (main menu / advisor)
         yes -> payment mode COD?
                  no  -> hand off to an advisor
                  yes -> "processing cancellation, Press 1 to confirm,
                          Press 2 to continue with the order"
                         1 -> cancel the order
                         2 -> leave the order alone, it ships in 24-48h

PAYMENT MODE: confirmed against a live gateway response — the order carries
a `tags` array (e.g. ["autoconfirm", "COD", "GoKwik", "Low Risk",
"OrderReady"]) and COD orders are tagged exactly "COD". `_is_cod` matches
that tag case-insensitively.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from services.external_gateway import ExternalGateway, GatewayError

UTC = timezone.utc

CANCELLATION_WINDOW_MINUTES = 30
COD_TAG = "cod"


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
    return max(
        candidates,
        key=lambda order: _parse_timestamp(order.get("processedAt") or order.get("createdAt"))
        or datetime.min.replace(tzinfo=UTC),
    )


def _product_names(order: dict[str, Any]) -> list[str]:
    nodes = order.get("lineItems", {}).get("nodes", [])
    return [n.get("title") for n in nodes if isinstance(n, dict) and n.get("title")]


def _order_value(order: dict[str, Any]) -> str | None:
    money = order.get("totalPriceSet", {}).get("shopMoney", {})
    amount = money.get("amount")
    currency = money.get("currencyCode")
    if amount is None:
        return None
    return f"{amount} {currency}".strip()


def _is_cod(order: dict[str, Any]) -> bool:
    tags = order.get("tags") or []
    if isinstance(tags, str):
        tags = [tags]
    return any(isinstance(t, str) and t.strip().lower() == COD_TAG for t in tags)


def _within_cancellation_window(order: dict[str, Any], *, now: datetime | None = None) -> bool:
    placed_at = _parse_timestamp(order.get("processedAt") or order.get("createdAt"))
    if placed_at is None:
        return False
    reference = now or datetime.now(UTC)
    return (reference - placed_at) <= timedelta(minutes=CANCELLATION_WINDOW_MINUTES)


def _order_id(order: dict[str, Any]) -> str | None:
    """The numeric Shopify order id GET/cancel actually take.

    legacyResourceId is the documented, directly-usable form. Fall back to
    parsing the numeric suffix off the gid:// id if legacyResourceId is ever
    missing from a payload.
    """
    legacy_id = order.get("legacyResourceId")
    if legacy_id:
        return str(legacy_id)
    gid = order.get("id")
    if isinstance(gid, str) and "/" in gid:
        return gid.rsplit("/", 1)[-1] or None
    return None


def _summarize(order: dict[str, Any]) -> dict[str, Any]:
    return {
        # order_id: numeric legacyResourceId — pass this to order_by_id / cancel_order.
        "order_id": _order_id(order),
        # order_reference: human-readable order name (e.g. "BV0379248424535")
        # for prompts and for Shiprocket tracking-by-order — NOT accepted by
        # the get-order or cancel-order endpoints.
        "order_reference": order.get("name") or _order_id(order),
        "order_value": _order_value(order),
        "product_names": _product_names(order),
        "already_cancelled": order.get("cancelledAt") is not None,
        "fulfillment_status": order.get("displayFulfillmentStatus"),
        "within_30_minutes": _within_cancellation_window(order),
        "is_cod": _is_cod(order),
    }


def _gateway_failure(error: GatewayError) -> dict[str, Any]:
    if error.status_code == 404:
        return {"outcome": "ORDER_NOT_FOUND", "prompt_id": "order_not_found", "handoff": False}
    if error.status_code == 409:
        return {"outcome": "AMBIGUOUS", "prompt_id": "agent_handoff", "handoff": True}
    return {
        "outcome": "SERVICE_UNAVAILABLE",
        "prompt_id": "agent_handoff",
        "handoff": True,
        "request_id": error.request_id,
    }


async def latest_order_for_modification(gateway: ExternalGateway, caller_number: str) -> dict[str, Any]:
    """'Press 2' entry point: resolve the caller's most recent order for the summary prompt."""
    try:
        customer = await gateway.customer_by_phone(caller_number)
    except GatewayError as exc:
        return _gateway_failure(exc)

    order = _latest_order(customer)
    if not order:
        return {"outcome": "NO_ORDER", "prompt_id": "no_recent_order", "handoff": False}

    return {
        "outcome": "ORDER_FOUND",
        "prompt_id": "order_summary",
        "handoff": False,
        **_summarize(order),
    }


async def order_by_reference(gateway: ExternalGateway, order_id_or_reference: str) -> dict[str, Any]:
    """'Press 2, then enter a different order id' path — same summary shape.

    ⚠️ KNOWN GAP: GET /orders/:orderId (the only Shopify order-fetch endpoint
    this gateway exposes) only accepts a numeric legacyResourceId or a
    gid://shopify/Order/<id> — it does NOT support lookup by order *name*
    (the "BV0..." value shown in the confirmed live response, and what the
    script tells callers to key in). Passing a name-style value here will
    404. Until there's a name-search endpoint (or the caller can be prompted
    for the numeric id instead), this function only works if
    order_id_or_reference is already the numeric id/gid — e.g. because an
    earlier step resolved it. Flagging rather than silently papering over it.
    """
    try:
        order = await gateway.order_by_id(order_id_or_reference)
    except GatewayError as exc:
        return _gateway_failure(exc)

    return {
        "outcome": "ORDER_FOUND",
        "prompt_id": "order_summary",
        "handoff": False,
        **_summarize(order),
    }


def eligibility_branch(summary: dict[str, Any]) -> dict[str, Any]:
    """After 'Press 1 to continue' on the order summary — pick the scripted branch.

      within 30 min, COD      -> ask for cancel confirmation
      within 30 min, not COD  -> hand off to an advisor
      after 30 min             -> cannot cancel (main menu / advisor)
    """
    if summary.get("already_cancelled"):
        return {"outcome": "ALREADY_CANCELLED", "prompt_id": "already_cancelled", "handoff": False}

    if not summary.get("within_30_minutes"):
        return {"outcome": "WINDOW_EXPIRED", "prompt_id": "cannot_cancel_window_expired", "handoff": False}

    if not summary.get("is_cod"):
        return {"outcome": "NOT_COD", "prompt_id": "agent_handoff", "handoff": True}

    return {"outcome": "CONFIRM_CANCELLATION", "prompt_id": "confirm_cancellation", "handoff": False}


async def confirm_cancellation(
    gateway: ExternalGateway,
    order_id: str,
    *,
    confirmed: bool,
    staff_note: str | None = None,
) -> dict[str, Any]:
    """'Press 1 to confirm cancellation / Press 2 to continue with the order.'

    order_id must be the numeric legacyResourceId (or gid://shopify/Order/<id>)
    returned as "order_id" by latest_order_for_modification /
    order_by_reference — NOT the display order name/reference.

    Re-fetches and re-validates the order immediately before cancelling,
    since time may have passed between the summary prompt and the caller's
    keypress and the 30-minute window or COD status could have changed.
    """
    if not confirmed:
        return {"outcome": "CANCELLATION_DECLINED", "prompt_id": "order_will_ship", "handoff": False}

    try:
        order = await gateway.order_by_id(order_id)
    except GatewayError as exc:
        return _gateway_failure(exc)

    summary = _summarize(order)
    branch = eligibility_branch(summary)
    if branch["outcome"] != "CONFIRM_CANCELLATION":
        # Window closed, payment mode looks different now, or it's already
        # cancelled - don't cancel silently, surface the current state instead.
        return branch

    try:
        job = await gateway.cancel_order(
            order_id,
            reason="CUSTOMER",
            refund=True,
            restock=True,
            notify_customer=True,
            staff_note=staff_note or "IVR self-service cancellation",
        )
    except GatewayError as exc:
        if exc.status_code == 422:
            return {
                "outcome": "CANCELLATION_REJECTED",
                "prompt_id": "agent_handoff",
                "handoff": True,
                "message": exc.message,
            }
        return _gateway_failure(exc)

    return {
        "outcome": "CANCELLED",
        "prompt_id": "order_cancelled",
        "handoff": False,
        "job_id": job.get("id"),
        "job_done": job.get("done", False),
    }
