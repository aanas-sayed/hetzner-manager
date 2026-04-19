"""
Hetzner Cloud API client wrapper.
Handles all API interactions with proper error handling.
"""

import json
import os
import sys
from typing import Optional
import requests

from src import log as _log

HETZNER_API_BASE = "https://api.hetzner.cloud/v1"


class HetznerAPIError(Exception):
    """Raised when Hetzner API returns an error."""
    def __init__(self, message: str, status_code: int = None, details: dict = None):
        super().__init__(message)
        self.status_code = status_code
        self.details = details or {}


class HetznerClient:
    """Thin wrapper around the Hetzner Cloud REST API."""

    def __init__(self, api_token: str):
        self.api_token = api_token
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
        })

    def _request(self, method: str, path: str, **kwargs) -> dict:
        url = f"{HETZNER_API_BASE}{path}"
        logger = _log.get()
        payload = kwargs.get("json")

        logger.debug("API → %s %s  payload=%s", method, path,
                     json.dumps(payload) if payload else "none")

        if _log.DRY_RUN and method.upper() in ("POST", "DELETE", "PUT", "PATCH"):
            logger.info("DRY-RUN API %s %s", method, path)
            if payload:
                logger.debug("DRY-RUN payload: %s", json.dumps(payload, indent=2))
            _log.dry_action(f"API {method} {url}")
            if payload:
                _log.dry_action(f"  payload: {json.dumps(payload)}")
            return {}

        try:
            resp = self.session.request(method, url, **kwargs)
        except requests.RequestException as e:
            logger.error("API network error: %s %s — %s", method, path, e)
            raise HetznerAPIError(f"Network error: {e}")

        logger.info("API %s %s → %d", method, path, resp.status_code)

        if not resp.ok:
            try:
                err = resp.json().get("error", {})
                msg = err.get("message", resp.text)
                code = err.get("code", "unknown")
            except Exception:
                msg = resp.text
                code = "unknown"
            logger.error("API error %d: %s [code=%s]", resp.status_code, msg, code)
            raise HetznerAPIError(
                f"API error ({resp.status_code}): {msg} [code={code}]",
                status_code=resp.status_code,
                details=err if isinstance(err, dict) else {},
            )

        if resp.status_code == 204:
            return {}
        result = resp.json()
        logger.debug("API ← response: %s", json.dumps(result)[:2000])
        return result

    # ── Server Types ─────────────────────────────────────────────────────────

    def get_server_types(self) -> list[dict]:
        data = self._request("GET", "/server_types", params={"per_page": 50})
        return data.get("server_types", [])

    # ── Locations ─────────────────────────────────────────────────────────────

    def get_locations(self) -> list[dict]:
        data = self._request("GET", "/locations", params={"per_page": 50})
        return data.get("locations", [])

    # ── Images ────────────────────────────────────────────────────────────────

    def get_images(self, image_type: str = "system") -> list[dict]:
        data = self._request(
            "GET", "/images",
            params={"type": image_type, "per_page": 50, "include_deprecated": False}
        )
        return data.get("images", [])

    # ── SSH Keys ──────────────────────────────────────────────────────────────

    def get_ssh_keys(self) -> list[dict]:
        data = self._request("GET", "/ssh_keys", params={"per_page": 50})
        return data.get("ssh_keys", [])

    def create_ssh_key(self, name: str, public_key: str) -> dict:
        data = self._request("POST", "/ssh_keys", json={"name": name, "public_key": public_key})
        return data.get("ssh_key", {})

    def delete_ssh_key(self, key_id: int) -> None:
        self._request("DELETE", f"/ssh_keys/{key_id}")

    # ── Servers ───────────────────────────────────────────────────────────────

    def create_server(self, payload: dict) -> dict:
        data = self._request("POST", "/servers", json=payload)
        return data

    def get_server(self, server_id: int) -> dict:
        data = self._request("GET", f"/servers/{server_id}")
        return data.get("server", {})

    def list_servers(self) -> list[dict]:
        data = self._request("GET", "/servers", params={"per_page": 50})
        return data.get("servers", [])

    def delete_server(self, server_id: int) -> dict:
        return self._request("DELETE", f"/servers/{server_id}")

    def get_server_action(self, server_id: int, action_id: int) -> dict:
        data = self._request("GET", f"/servers/{server_id}/actions/{action_id}")
        return data.get("action", {})

    # ── Networks ──────────────────────────────────────────────────────────────

    def get_networks(self) -> list[dict]:
        data = self._request("GET", "/networks", params={"per_page": 50})
        return data.get("networks", [])

    # ── Pricing ───────────────────────────────────────────────────────────────

    def get_pricing(self) -> dict:
        return self._request("GET", "/pricing")


def get_client() -> HetznerClient:
    """Create a HetznerClient from environment or prompt."""
    token = os.environ.get("HETZNER_API_TOKEN")
    if not token:
        from src.ui import prompt_input, error, info
        info("No HETZNER_API_TOKEN environment variable found.")
        token = prompt_input("Enter your Hetzner API token").strip()
        if not token:
            error("API token is required.")
            sys.exit(1)
    return HetznerClient(token)
