"""Thin Yahoo Fantasy API client.

Requests XML (the format Yahoo documents) and strips the XML namespace so the
parsers can use plain tag names. Handles token refresh, Yahoo's 999 rate-limit
status, and transient errors with backoff.
"""
from __future__ import annotations

import logging
import time
import xml.etree.ElementTree as ET

import requests

from . import auth

BASE_URL = "https://fantasysports.yahooapis.com/fantasy/v2"
log = logging.getLogger(__name__)


def strip_namespace(root: ET.Element) -> ET.Element:
    for el in root.iter():
        if isinstance(el.tag, str) and "}" in el.tag:
            el.tag = el.tag.split("}", 1)[1]
    return root


def parse_xml(text: str | bytes) -> ET.Element:
    return strip_namespace(ET.fromstring(text))


class YahooClient:
    def __init__(self, client_id: str, client_secret: str, refresh_token: str,
                 redirect_uri: str = auth.DEFAULT_REDIRECT_URI, min_interval: float = 0.4):
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self.redirect_uri = redirect_uri
        self.min_interval = min_interval
        self.access_token: str | None = None
        self.calls = 0
        self._last_call = 0.0
        self.session = requests.Session()

    @classmethod
    def from_env(cls) -> "YahooClient":
        return cls(*auth.credentials_from_env())

    def _refresh(self) -> None:
        tok = auth.refresh_access_token(self.client_id, self.client_secret, self.refresh_token, self.redirect_uri)
        self.access_token = tok["access_token"]
        new_refresh = tok.get("refresh_token")
        if new_refresh and new_refresh != self.refresh_token:
            # Yahoo has historically returned the same refresh token. If that ever
            # changes, the GitHub secret will need updating; flag it loudly.
            log.warning("Yahoo issued a NEW refresh token. Update the YAHOO_REFRESH_TOKEN secret "
                        "if runs start failing with auth errors.")
            self.refresh_token = new_refresh

    def get(self, path: str, retries: int = 4) -> ET.Element:
        """GET a resource path such as 'league/461.l.8049/standings' and return parsed XML."""
        if self.access_token is None:
            self._refresh()
        url = f"{BASE_URL}/{path.lstrip('/')}"
        refreshed = False
        for attempt in range(retries + 1):
            wait = self.min_interval - (time.monotonic() - self._last_call)
            if wait > 0:
                time.sleep(wait)
            self._last_call = time.monotonic()
            self.calls += 1
            try:
                resp = self.session.get(url, headers={"Authorization": f"Bearer {self.access_token}"}, timeout=30)
            except requests.RequestException as e:
                log.warning("Network error on %s: %s", path, e)
                time.sleep(2 ** attempt)
                continue
            if resp.status_code == 200:
                return parse_xml(resp.content)
            if resp.status_code == 401 and not refreshed:
                log.info("Access token expired; refreshing")
                self._refresh()
                refreshed = True
                continue
            if resp.status_code == 999 or resp.status_code == 429:
                delay = 60 * (attempt + 1)
                log.warning("Rate limited by Yahoo (%s). Sleeping %ss", resp.status_code, delay)
                time.sleep(delay)
                continue
            if resp.status_code >= 500:
                time.sleep(2 ** attempt)
                continue
            raise RuntimeError(f"Yahoo API error {resp.status_code} for {path}: {resp.text[:500]}")
        raise RuntimeError(f"Yahoo API request failed after {retries + 1} attempts: {path}")
