from functools import lru_cache
import re

from fastapi import APIRouter, Header, HTTPException, Request, status, Query
from pydantic import BaseModel, Field

from services.external_gateway import ExternalGateway, GatewaySettings, GatewayError
from services.order_status import latest_order_status, customer_category

from fastapi.responses import PlainTextResponse
import os


router = APIRouter(prefix="/api/v1/ivr", tags=["ivr"])


class LatestOrderRequest(BaseModel):
    caller_number: str = Field(description="Caller ID in E.164 format, including country code")


@lru_cache
def gateway() -> ExternalGateway:
    return ExternalGateway(GatewaySettings.from_environment())



UNKNOWN_STATUS = "UNKNOWN_STATUS"


def _to_indian_e164(caller_number: str) -> str:
    """Dialplan callers pass a bare 10-digit subscriber number (Asterisk
    CALLERID(num)); reject anything else and prefix the country code before
    it ever reaches the gateway."""
    digits = re.sub(r"\D", "", caller_number)
    if len(digits) != 10:
        raise ValueError("caller_number must be exactly 10 digits")
    return f"91{digits}"



@router.get("/dialplan/orders/latest", response_class=PlainTextResponse)
async def get_latest_order_status_dialplan(
    caller_number: str = Query(...),
) -> str:
    """Plain-text endpoint for Asterisk CURL().
    Returns 'prompt_id/handoff/order_status/estimated_delivery_date'.

    Dialplan usage:
        Set(API_RESULT=${CURL(http://host/api/v1/ivr/dialplan/orders/latest?caller_number=${CALLERID(num)})})
        Set(para1=${CUT(API_RESULT,/,1)})   ; prompt file to Playback
        Set(para2=${CUT(API_RESULT,/,2)})   ; "1" -> agent, "0" -> continue
        Set(para3=${CUT(API_RESULT,/,3)})   ; order status text (TTS or SayAlpha)
        Set(para4=${CUT(API_RESULT,/,4)})   ; EDD, empty if not shipped/unknown
    """

    try:
        normalised_number = _to_indian_e164(caller_number)
    except ValueError:
        return UNKNOWN_STATUS

    try:
        result = await latest_order_status(gateway(), normalised_number)
    except RuntimeError:
        return UNKNOWN_STATUS
    except Exception:
        return UNKNOWN_STATUS

    prompt_id = result.get("prompt_id") or UNKNOWN_STATUS
    handoff = "1" if result.get("handoff") else "0"
    order_status = result.get("order_status") or ""
    delivery = result.get("delivery") or ""
    return f"{prompt_id}/{handoff}/{order_status}/{delivery}"


@router.get("/dialplan/customers/category", response_class=PlainTextResponse)
async def get_customer_category_dialplan(
    caller_number: str = Query(..., description="Caller ID, E.164, e.g. 919876543210"),
) -> str:
    """Plain-text endpoint for Asterisk CURL(). Returns 'prompt_id/handoff'."""

    try:
        normalised_number = _to_indian_e164(caller_number)
    except ValueError:
        return UNKNOWN_STATUS

    try:
        customer = await gateway().customer_by_phone(normalised_number)
    except RuntimeError:
        return UNKNOWN_STATUS
    except GatewayError:
        return "non_premium/0/new"
    except Exception:
        return UNKNOWN_STATUS

    category = customer_category(customer)
    prompt_id = "premium" if category == "PREMIUM" else "non_premium"
    handoff = "1" if category == "PREMIUM" else "0"
    customer_type = "existing"
    return f"{prompt_id}/{handoff}/{customer_type}"


# def verify_agi_secret(provided: str | None) -> None:
#     import os
#
#     expected = os.environ.get("AGI_SHARED_SECRET", "")
#     if not expected or provided != expected:
#         raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid AGI credentials")


@router.post("/orders/latest")
async def get_latest_order_status(
    body: LatestOrderRequest,
    request: Request,
    x_agi_secret: str | None = Header(default=None),
) -> dict:
    """Resolve caller ID to the latest-order IVR branch; never expose gateway credentials to Asterisk."""
    # verify_agi_secret(x_agi_secret)
    try:
        return await latest_order_status(gateway(), body.caller_number)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="IVR service is not configured") from exc


@router.post("/customers/category")
async def get_customer_category(
    body: LatestOrderRequest,
    x_agi_secret: str | None = Header(default=None),
) -> dict[str, str | bool]:
    """Classify the caller before selecting the Premium/Non-Premium IVR branch."""
    # verify_agi_secret(x_agi_secret)
    try:
        customer = await gateway().customer_by_phone(body.caller_number)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="IVR service is not configured") from exc
    except GatewayError:
        # Do not expose gateway details to Asterisk. The existing menu can use
        # agent_handoff to safely recover from lookup failures.
        return {"customer_category": "UNKNOWN", "prompt_id": "agent_handoff", "handoff": True}

    category = customer_category(customer)
    return {
        "customer_category": category,
        "prompt_id": "premium_customer" if category == "PREMIUM" else "non_premium_customer",
        "handoff": category == "PREMIUM",
    }
