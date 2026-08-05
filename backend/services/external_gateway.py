"""Small, timeout-bounded client for the supplied Shopify/Shiprocket gateway."""

from __future__ import annotations

import asyncio
import json
import os
import re
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


class GatewayError(Exception):
    def __init__(self, status_code: int, message: str, request_id: str | None = None):
        self.status_code = status_code
        self.message = message
        self.request_id = request_id
        super().__init__(message)


@dataclass(frozen=True)
class GatewaySettings:
    base_url: str
    token: str
    shop_domain: str
    timeout_seconds: float

    @classmethod
    def from_environment(cls) -> "GatewaySettings":
        token = os.environ.get("EXTERNAL_API_TOKEN", "")
        shop_domain = os.environ.get("SHOP_DOMAIN", "")
        if not token or not shop_domain:
            raise RuntimeError("EXTERNAL_API_TOKEN and SHOP_DOMAIN must be configured")
        return cls(
            base_url=os.environ.get("EXTERNAL_API_BASE_URL", "https://external-apis.oneguardian.in/api/v1").rstrip("/"),
            token=token,
            shop_domain=shop_domain,
            timeout_seconds=float(os.environ.get("EXTERNAL_API_TIMEOUT_SECONDS", "4.0")),
        )


class ExternalGateway:
    def __init__(self, settings: GatewaySettings):
        self.settings = settings

    async def customer_by_phone(self, phone: str) -> dict[str, Any]:
        normalised = re.sub(r"[^0-9+]", "", phone)
        if not re.fullmatch(r"\+?[0-9]{8,15}", normalised):
            raise GatewayError(400, "Caller number is not a valid E.164 phone number")
        return await self._request("GET", f"/customers/phone/{quote(normalised, safe='+')}")

    async def tracking_by_order(self, order_reference: str) -> dict[str, Any]:
        return await self._request("GET", f"/tracking/order/{quote(order_reference, safe='')}")

    async def _request(self, method: str, path: str) -> dict[str, Any]:
        return await asyncio.to_thread(self._request_sync, method, path)

    def _request_sync(self, method: str, path: str) -> dict[str, Any]:
        request = Request(
            f"{self.settings.base_url}{path}",
            method=method,
            headers={
                "Authorization": f"Bearer {self.settings.token}",
                "X-Shop-Domain": self.settings.shop_domain,
                "Accept": "application/json",
            },
        )
        try:
            with urlopen(request, timeout=self.settings.timeout_seconds) as response:  # nosec B310 - controlled base URL
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            payload = self._read_error_payload(exc)
            raise GatewayError(exc.code, payload.get("message", "External API request failed"), payload.get("requestId")) from exc
        except (URLError, TimeoutError) as exc:
            raise GatewayError(503, "External API is unavailable") from exc

        if not payload.get("success"):
            raise GatewayError(502, payload.get("message", "External API returned an unsuccessful response"), payload.get("requestId"))
        data = payload.get("data")
        # Some endpoints (observed: tracking/order) wrap a single object in a
        # one-element array instead of returning the object directly. Unwrap it
        # rather than treating it as a shape error.
        if isinstance(data, list):
            if len(data) == 1 and isinstance(data[0], dict):
                data = data[0]
            else:
                raise GatewayError(502, "External API returned an unexpected list shape for data")

        if not isinstance(data, dict):
            raise GatewayError(502, "External API returned an unexpected response")
        return data

    @staticmethod
    def _read_error_payload(error: HTTPError) -> dict[str, Any]:
        try:
            return json.loads(error.read().decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {}