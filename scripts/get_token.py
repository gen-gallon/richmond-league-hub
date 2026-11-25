"""One-time setup: get a Yahoo refresh token for the scheduled job.

Run this on your own computer after Yahoo approves your API access:

    pip install requests
    python scripts/get_token.py

It asks for your Client ID and Client Secret, opens Yahoo's consent page,
and prints the refresh token to save as the YAHOO_REFRESH_TOKEN GitHub secret.
Nothing is written to disk.
"""
from __future__ import annotations

import getpass
import sys
import urllib.parse
import webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ingest import auth  # noqa: E402


def main() -> None:
    client_id = input("Yahoo Client ID: ").strip()
    client_secret = getpass.getpass("Yahoo Client Secret (hidden): ").strip()
    redirect = input(f"Redirect URI [{auth.DEFAULT_REDIRECT_URI}]: ").strip() or auth.DEFAULT_REDIRECT_URI

    url = auth.AUTH_URL + "?" + urllib.parse.urlencode({
        "client_id": client_id, "redirect_uri": redirect, "response_type": "code", "language": "en-us",
    })
    print("\nOpen this URL, sign in with the Yahoo account that's in the league, and click Agree:\n")
    print(url + "\n")
    try:
        webbrowser.open(url)
    except Exception:
        pass
    if redirect == "oob":
        code = input("Paste the code Yahoo shows you: ").strip()
    else:
        code = input("Paste the 'code' value from the URL you were redirected to: ").strip()

    tok = auth.exchange_code(client_id, client_secret, code, redirect)
    print("\nSuccess. Add these as GitHub repository secrets "
          "(Settings > Secrets and variables > Actions > New repository secret):\n")
    print("  YAHOO_CLIENT_ID      =", client_id)
    print("  YAHOO_CLIENT_SECRET  = (the secret you just typed)")
    print("  YAHOO_REFRESH_TOKEN  =", tok["refresh_token"])
    if redirect != auth.DEFAULT_REDIRECT_URI:
        print("  YAHOO_REDIRECT_URI   =", redirect)
    print("\nTreat the refresh token like a password.")


if __name__ == "__main__":
    main()
