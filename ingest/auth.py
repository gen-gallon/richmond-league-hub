"""OAuth 2.0 helpers for the Yahoo Fantasy Sports API.

Yahoo uses a standard authorization-code flow. You run scripts/get_token.py
once on your own machine to get a refresh token; after that, the scheduled job
trades the refresh token for a short-lived access token on every run.
"""
from __future__ import annotations

import base64
import os

import requests

AUTH_URL = "https://api.login.yahoo.com/oauth2/request_auth"
TOKEN_URL = "https://api.login.yahoo.com/oauth2/get_token"
DEFAULT_REDIRECT_URI = "oob"


class AuthError(RuntimeError):
    pass


def _basic_auth_header(client_id: str, client_secret: str) -> str:
    raw = f"{client_id}:{client_secret}".encode()
    return "Basic " + base64.b64encode(raw).decode()


def _post_token(client_id: str, client_secret: str, data: dict) -> dict:
    resp = requests.post(
        TOKEN_URL,
        headers={
            "Authorization": _basic_auth_header(client_id, client_secret),
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data=data,
        timeout=30,
    )
    if resp.status_code != 200:
        raise AuthError(f"Yahoo token request failed ({resp.status_code}): {resp.text[:500]}")
    return resp.json()


def exchange_code(client_id: str, client_secret: str, code: str, redirect_uri: str = DEFAULT_REDIRECT_URI) -> dict:
    return _post_token(
        client_id,
        client_secret,
        {"grant_type": "authorization_code", "code": code.strip(), "redirect_uri": redirect_uri},
    )


def refresh_access_token(client_id: str, client_secret: str, refresh_token: str,
                         redirect_uri: str = DEFAULT_REDIRECT_URI) -> dict:
    return _post_token(
        client_id,
        client_secret,
        {"grant_type": "refresh_token", "refresh_token": refresh_token, "redirect_uri": redirect_uri},
    )


def credentials_from_env() -> tuple[str, str, str, str]:
    """Read credentials from environment variables (GitHub Secrets in CI)."""
    missing = [k for k in ("YAHOO_CLIENT_ID", "YAHOO_CLIENT_SECRET", "YAHOO_REFRESH_TOKEN") if not os.environ.get(k)]
    if missing:
        raise AuthError("Missing environment variables: " + ", ".join(missing))
    return (
        os.environ["YAHOO_CLIENT_ID"],
        os.environ["YAHOO_CLIENT_SECRET"],
        os.environ["YAHOO_REFRESH_TOKEN"],
        os.environ.get("YAHOO_REDIRECT_URI", DEFAULT_REDIRECT_URI),
    )
