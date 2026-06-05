import urllib.request
import urllib.parse
import json
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

WG_EASY_URL = "http://eduguard-wg:51821"
WG_PASSWORD = "admin"

class WgEasyClient:
    def __init__(self):
        self.base_url = WG_EASY_URL
        self.password = WG_PASSWORD
        self.session_cookie = None
        self._login()

    def _login(self):
        """Authenticate with wg-easy and store session cookie."""
        data = urllib.parse.urlencode({"password": self.password}).encode()
        req = urllib.request.Request(
            f"{self.base_url}/api/session",
            method="POST",
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        try:
            resp = urllib.request.urlopen(req)
            self.session_cookie = resp.headers.get("Set-Cookie")
            logger.info("[WG-EASY] Authenticated successfully")
        except Exception as e:
            logger.error(f"[WG-EASY] Login failed: {e}")
            raise

    def _request(self, path: str, method="GET", data=None) -> dict:
        """Make authenticated request to wg-easy API."""
        headers = {}
        if self.session_cookie:
            headers["Cookie"] = self.session_cookie
        if data and method == "POST":
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        req = urllib.request.Request(
            f"{self.base_url}{path}",
            method=method,
            data=data.encode() if data else None,
            headers=headers
        )
        try:
            resp = urllib.request.urlopen(req)
            return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 401:
                self._login()
                return self._request(path, method, data)
            raise

    def list_clients(self) -> List[dict]:
        return self._request("/api/wireguard/client")

    def create_client(self, name: str) -> dict:
        data = urllib.parse.urlencode({"name": name})
        return self._request("/api/wireguard/client", method="POST", data=data)

    def delete_client(self, client_id: str) -> dict:
        return self._request(f"/api/wireguard/client/{client_id}", method="DELETE")

    def get_client_config(self, client_id: str) -> dict:
        return self._request(f"/api/wireguard/client/{client_id}/configuration")

    def get_client_qr(self, client_id: str) -> bytes:
        """Get QR code PNG for client."""
        headers = {"Cookie": self.session_cookie} if self.session_cookie else {}
        req = urllib.request.Request(
            f"{self.base_url}/api/wireguard/client/{client_id}/qrcode.svg",
            headers=headers
        )
        resp = urllib.request.urlopen(req)
        return resp.read()

    def update_client_name(self, client_id: str, name: str) -> dict:
        data = urllib.parse.urlencode({"name": name})
        return self._request(f"/api/wireguard/client/{client_id}/name", method="POST", data=data)

wg_client = WgEasyClient()
