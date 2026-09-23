import time

import requests

OAUTH_URL = "https://zoom.us/oauth/token"
API_BASE = "https://api-us.zoom.us/v2"


class ZoomClient:
    """Server-to-Server OAuth + Cloud Recording endpoints.

    Token TTL is ~1h; cached in memory and refreshed on 401 (once).
    """

    def __init__(self, account_id: str, client_id: str, client_secret: str):
        self._account_id = account_id
        self._auth = (client_id, client_secret)
        self._token: str | None = None
        self._token_exp = 0.0

    def _get_token(self, force: bool = False) -> str:
        if not force and self._token and time.time() < self._token_exp - 60:
            return self._token
        resp = requests.post(
            OAUTH_URL,
            params={
                "grant_type": "account_credentials",
                "account_id": self._account_id,
            },
            auth=self._auth,
            timeout=30,
        )
        resp.raise_for_status()
        body = resp.json()
        self._token = body["access_token"]
        self._token_exp = time.time() + int(body.get("expires_in", 3600))
        return self._token

    def _get(self, path: str, params: dict | None = None) -> dict:
        for attempt in range(2):
            token = self._get_token(force=attempt > 0)
            resp = requests.get(
                f"{API_BASE}{path}",
                params=params,
                headers={"Authorization": f"Bearer {token}"},
                timeout=30,
            )
            if resp.status_code == 401 and attempt == 0:
                continue
            if resp.status_code == 429:
                retry_after = max(5, int(resp.headers.get("Retry-After", "5")))
                time.sleep(retry_after)
                resp.raise_for_status()
            resp.raise_for_status()
            return resp.json()
        raise RuntimeError("Zoom API: повторная 401 после обновления токена")

    def list_users(self) -> list[dict]:
        users: list[dict] = []
        params: dict = {"page_size": 300}
        while True:
            body = self._get("/users", params)
            users.extend(body.get("users", []))
            next_token = body.get("next_page_token")
            if not next_token:
                return users
            params["next_page_token"] = next_token

    def list_recordings(self, user_id: str, date_from: str, date_to: str) -> list[dict]:
        """All recorded meetings of one user in [date_from, date_to] (YYYY-MM-DD)."""
        meetings: list[dict] = []
        params: dict = {"from": date_from, "to": date_to, "page_size": 300}
        while True:
            body = self._get(f"/users/{user_id}/recordings", params)
            meetings.extend(body.get("meetings", []))
            next_token = body.get("next_page_token")
            if not next_token:
                return meetings
            params["next_page_token"] = next_token

    def download(self, download_url: str) -> requests.Response:
        token = self._get_token()
        resp = requests.get(
            download_url,
            params={"access_token": token},
            stream=True,
            timeout=300,
        )
        resp.raise_for_status()
        return resp
