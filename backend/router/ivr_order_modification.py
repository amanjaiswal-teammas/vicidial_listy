"""Router for the 'Press 2: Need Changes in the order' IVR branch.

Mirrors the style of routers/ivr.py: a plain-text /dialplan/* surface for
Asterisk CURL()/CUT(), plus JSON endpoints for anything else that talks to
this service directly.
"""

from __future__ import annotations

import re
from functools import lru_cache

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from services.external_gateway import ExternalGateway, GatewaySettings
from services.order_modification import (
    confirm_cancellation,
    eligibility_branch,
    latest_order_for_modification,
    order_by_reference,
)

router = APIRouter(prefix="/api/v1/ivr", tags=["ivr", "order-modification"])

UNKNOWN_STATUS = "UNKNOWN_STATUS"

# BVO... style channel order id/name, per the API guide's example
# (digits, letters, and # _ . - separators, max 128 chars).
ORDER_REFERENCE_RE = re.compile(r"^[A-Za-z0-9#_.\-]{1,128}$")


@lru_cache
def gateway() -> ExternalGateway:
    return ExternalGateway(GatewaySettings.from_environment())


def _to_indian_e164(caller_number: str) -> str:
    """Dialplan callers pass a bare 10-digit subscriber number
    (Asterisk CALLERID(num)); reject anything else and prefix the
    country code before it ever reaches the gateway.

    Kept in sync with routers/ivr.py's helper of the same name; if you
    already share a utils module between routers, import it from there
    instead of duplicating this.
    """
    digits = re.sub(r"\D", "", caller_number)
    if len(digits) != 10:
        raise ValueError("caller_number must be exactly 10 digits")
    return f"91{digits}"


def _validate_order_reference(order_reference: str) -> str:
    cleaned = order_reference.strip()
    if not ORDER_REFERENCE_RE.fullmatch(cleaned):
        raise ValueError("order_reference has an invalid format")
    return cleaned


def _product_names_field(names: list[str] | None) -> str:
    # "/" is CUT()'s field delimiter in the existing dialplan convention, so
    # keep it out of individual fields; commas are safe within a field.
    return ", ".join(n.replace("/", "-") for n in (names or []))


def _summary_line(result: dict) -> str:
    """prompt_id/handoff/order_id/order_reference/order_value/product_names/within_30/is_cod

    order_id (numeric legacyResourceId) is what the dialplan must hold onto
    and pass back into .../modify/confirm — order_reference is display-only.
    """
    return "/".join(
        [
            str(result.get("prompt_id") or UNKNOWN_STATUS),
            "1" if result.get("handoff") else "0",
            str(result.get("order_id") or ""),
            str(result.get("order_reference") or ""),
            str(result.get("order_value") or ""),
            _product_names_field(result.get("product_names")),
            "1" if result.get("within_30_minutes") else "0",
            "1" if result.get("is_cod") else "0",
        ]
    )


# ---------------------------------------------------------------------------
# Dialplan (plain-text) endpoints
# ---------------------------------------------------------------------------


@router.get("/dialplan/orders/modify/latest", response_class=PlainTextResponse)
async def dialplan_latest_order_for_modification(caller_number: str = Query(...)) -> str:
    """'Press 2' entry point. Resolves the caller's last order.

    Dialplan usage:
        Set(API_RESULT=${CURL(.../dialplan/orders/modify/latest?caller_number=${CALLERID(num)})})
        Set(para1=${CUT(API_RESULT,/,1)})  ; prompt_id
        Set(para2=${CUT(API_RESULT,/,2)})  ; handoff: 1 -> agent, 0 -> continue
        Set(para3=${CUT(API_RESULT,/,3)})  ; order_id — numeric, keep this: pass to .../modify/confirm
        Set(para4=${CUT(API_RESULT,/,4)})  ; order reference for playback (e.g. BV0379248424535)
        Set(para5=${CUT(API_RESULT,/,5)})  ; order value, e.g. "1299.00 INR"
        Set(para6=${CUT(API_RESULT,/,6)})  ; product names, comma-separated
        Set(para7=${CUT(API_RESULT,/,7)})  ; within 30 min: 1/0
        Set(para8=${CUT(API_RESULT,/,8)})  ; COD: 1/0
    """
    try:
        normalised_number = _to_indian_e164(caller_number)
    except ValueError:
        return UNKNOWN_STATUS

    try:
        result = await latest_order_for_modification(gateway(), normalised_number)
    except RuntimeError:
        return UNKNOWN_STATUS
    except Exception:
        return UNKNOWN_STATUS

    return _summary_line(result)


@router.get("/dialplan/orders/modify/lookup", response_class=PlainTextResponse)
async def dialplan_order_lookup(order_reference: str = Query(...)) -> str:
    """'Press 2, then enter your order id starting with BVO' path.
    Same response shape as .../modify/latest.

    ⚠️ See the KNOWN GAP note on services.order_modification.order_by_reference:
    the underlying GET /orders/:orderId call needs a numeric legacyResourceId,
    not the "BV0..." order name the script has callers key in — this endpoint
    will 404 for a name-style input until that's resolved.
    """
    try:
        cleaned_reference = _validate_order_reference(order_reference)
    except ValueError:
        return UNKNOWN_STATUS

    try:
        result = await order_by_reference(gateway(), cleaned_reference)
    except RuntimeError:
        return UNKNOWN_STATUS
    except Exception:
        return UNKNOWN_STATUS

    return _summary_line(result)


@router.get("/dialplan/orders/modify/eligibility", response_class=PlainTextResponse)
async def dialplan_eligibility(
    order_reference: str = Query(...),
    within_30_minutes: bool = Query(...),
    is_cod: bool = Query(...),
    already_cancelled: bool = Query(False),
) -> str:
    """'Press 1 to continue' step: which of the four scripted branches applies.

    Dialplan calls this with the flags it already has from the .../latest or
    .../lookup response (fields 6 and 7), so the branch decision doesn't
    require a second gateway round trip.

    Returns 'prompt_id/handoff'.
    """
    branch = eligibility_branch(
        {
            "within_30_minutes": within_30_minutes,
            "is_cod": is_cod,
            "already_cancelled": already_cancelled,
        }
    )
    handoff = "1" if branch.get("handoff") else "0"
    return f"{branch.get('prompt_id', UNKNOWN_STATUS)}/{handoff}"


@router.get("/dialplan/orders/modify/confirm", response_class=PlainTextResponse)
async def dialplan_confirm_cancellation(
    order_id: str = Query(..., description="Numeric order_id from field 3 of the .../latest or .../lookup response — NOT the order reference/name"),
    confirmed: bool = Query(..., description="true for Press 1 (confirm), false for Press 2 (keep order)"),
) -> str:
    """'Press 1 to confirm cancellation, Press 2 to continue with the order.'

    Re-validates eligibility server-side against a fresh order fetch before
    cancelling. Returns 'prompt_id/handoff'.
    """
    try:
        cleaned_id = _validate_order_reference(order_id)
    except ValueError:
        return UNKNOWN_STATUS

    try:
        result = await confirm_cancellation(gateway(), cleaned_id, confirmed=confirmed)
    except RuntimeError:
        return UNKNOWN_STATUS
    except Exception:
        return UNKNOWN_STATUS

    handoff = "1" if result.get("handoff") else "0"
    return f"{result.get('prompt_id', UNKNOWN_STATUS)}/{handoff}"


# ---------------------------------------------------------------------------
# JSON endpoints
# ---------------------------------------------------------------------------


class OrderLookupRequest(BaseModel):
    caller_number: str = Field(description="Caller ID in E.164 format, including country code")


class OrderReferenceRequest(BaseModel):
    order_reference: str = Field(description="Shopify order id or name, e.g. BVO379248121171_436833826 or #1042")


class ConfirmCancellationRequest(BaseModel):
    order_id: str = Field(description="Numeric legacyResourceId (or gid://shopify/Order/<id>) — NOT the order name/reference")
    confirmed: bool = Field(description="True for Press 1 (confirm), False for Press 2 (keep order)")


@router.post("/orders/modify/latest")
async def get_latest_order_for_modification(
    body: OrderLookupRequest,
    x_agi_secret: str | None = Header(default=None),
) -> dict:
    try:
        return await latest_order_for_modification(gateway(), body.caller_number)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="IVR service is not configured") from exc


@router.post("/orders/modify/lookup")
async def get_order_by_reference(
    body: OrderReferenceRequest,
    x_agi_secret: str | None = Header(default=None),
) -> dict:
    try:
        cleaned_reference = _validate_order_reference(body.order_reference)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        return await order_by_reference(gateway(), cleaned_reference)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="IVR service is not configured") from exc


@router.post("/orders/modify/confirm")
async def post_confirm_cancellation(
    body: ConfirmCancellationRequest,
    x_agi_secret: str | None = Header(default=None),
) -> dict:
    """Executes the actual Shopify cancellation call when confirmed=True."""
    try:
        cleaned_id = _validate_order_reference(body.order_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        return await confirm_cancellation(gateway(), cleaned_id, confirmed=body.confirmed)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="IVR service is not configured") from exc
