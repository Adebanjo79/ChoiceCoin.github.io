from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests


@dataclass(frozen=True)
class OpenSeaMintTx:
    to: str
    data: str
    value: int
    chain: str
    raw: dict[str, Any]


class OpenSeaError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None, payload: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload


class OpenSeaClient:
    def __init__(self, api_key: str, base_url: str = "https://api.opensea.io", chain: str = "robinhood"):
        if not api_key:
            raise ValueError("OPENSEA_API_KEY is required for signed SeaDrop mints")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.chain = chain
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/json",
                "Content-Type": "application/json",
                "X-API-KEY": api_key,
                "User-Agent": "robinhood-seadrop-copier/0.1",
            }
        )

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        url = f"{self.base_url}{path}"
        resp = self.session.request(method, url, timeout=30, **kwargs)
        try:
            payload = resp.json()
        except Exception:
            payload = resp.text
        if resp.status_code >= 400:
            message = _format_opensea_error(payload) or f"OpenSea HTTP {resp.status_code}"
            raise OpenSeaError(message, status_code=resp.status_code, payload=payload)
        return payload

    def collection_slug_for_contract(self, contract: str) -> str:
        data = self._request("GET", f"/api/v2/chain/{self.chain}/contract/{contract}")
        slug = data.get("collection") if isinstance(data, dict) else None
        if not slug:
            raise OpenSeaError(f"No OpenSea collection for contract {contract}", payload=data)
        return str(slug)

    def get_drop(self, slug: str) -> dict[str, Any]:
        data = self._request("GET", f"/api/v2/drops/{slug}")
        if not isinstance(data, dict):
            raise OpenSeaError("Unexpected drop response", payload=data)
        return data

    def build_mint_transaction(self, slug: str, minter: str, quantity: int) -> OpenSeaMintTx:
        data = self._request(
            "POST",
            f"/api/v2/drops/{slug}/mint",
            json={"minter": minter, "quantity": int(quantity)},
        )
        if not isinstance(data, dict):
            raise OpenSeaError("Unexpected mint response", payload=data)

        # OpenSea docs/SDK use both target/calldata and to/data shapes.
        to_addr = data.get("to") or data.get("target")
        calldata = data.get("data") or data.get("calldata")
        value_raw = data.get("value", "0")
        chain = str(data.get("chain") or self.chain)
        if not to_addr or not calldata:
            raise OpenSeaError("Mint response missing to/data", payload=data)
        if isinstance(value_raw, str):
            value = int(value_raw, 16) if value_raw.startswith("0x") else int(value_raw)
        else:
            value = int(value_raw)
        return OpenSeaMintTx(to=to_addr, data=calldata, value=value, chain=chain, raw=data)


def _format_opensea_error(payload: Any) -> str:
    if isinstance(payload, dict):
        errors = payload.get("errors")
        if isinstance(errors, list) and errors:
            return "; ".join(str(e) for e in errors)
        for key in ("message", "detail", "error"):
            if payload.get(key):
                return str(payload[key])
    if isinstance(payload, str) and payload.strip():
        return payload.strip()[:300]
    return ""