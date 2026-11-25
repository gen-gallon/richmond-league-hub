"""Pull league data from Yahoo and write the JSON the static site reads.

Usage:
    python -m ingest.build            # refresh current season; backfill any missing past seasons
    python -m ingest.build --full     # re-pull every season, including cached finished ones

Environment:
    YAHOO_CLIENT_ID, YAHOO_CLIENT_SECRET, YAHOO_REFRESH_TOKEN   (required)
    YAHOO_LEAGUE_ID      league id in the current season (e.g. 8049)
    YAHOO_LEAGUE_KEY     optional full key (e.g. 461.l.8049); overrides YAHOO_LEAGUE_ID
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import parse
from .client import YahooClient
from .history import apply_owner_config, build_history

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "site" / "data"
SEASONS = DATA / "seasons"
CONFIG = ROOT / "config"
log = logging.getLogger("ingest")


def load_json(path: Path, default=None):
    return json.loads(path.read_text()) if path.exists() else default


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=1, sort_keys=False) + "\n")


def current_league_key(client: YahooClient) -> str:
    if os.environ.get("YAHOO_LEAGUE_KEY"):
        return os.environ["YAHOO_LEAGUE_KEY"]
    league_id = os.environ.get("YAHOO_LEAGUE_ID")
    if not league_id:
        sys.exit("Set YAHOO_LEAGUE_ID (or YAHOO_LEAGUE_KEY).")
    game_key = parse.parse_game_key(client.get("game/nfl"))
    return f"{game_key}.l.{league_id}"


def fetch_player_names(client: YahooClient, league_key: str, player_keys: list[str]) -> dict:
    names = {}
    for i in range(0, len(player_keys), 25):
        batch = ",".join(player_keys[i:i + 25])
        try:
            names.update(parse.parse_players(client.get(f"league/{league_key}/players;player_keys={batch}")))
        except RuntimeError as e:
            log.warning("Player lookup failed for %s batch %s: %s", league_key, i // 25, e)
    return names


def pull_season(client: YahooClient, league_key: str, existing: dict | None) -> dict:
    meta = parse.parse_league(client.get(f"league/{league_key}"))
    log.info("Pulling %s season %s (%s)", meta["name"], meta["season"], league_key)
    settings = parse.parse_settings(client.get(f"league/{league_key}/settings"))
    standings = parse.parse_standings(client.get(f"league/{league_key}/standings"))

    # Matchups: one call per week. For an in-progress season, keep weeks that were
    # already final in the previous pull and only re-fetch recent ones.
    last_week = meta["end_week"] if meta["is_finished"] else min(meta["current_week"] or 0, meta["end_week"] or 0)
    old_by_week: dict[int, list] = {}
    if existing and not meta["is_finished"]:
        for m in existing.get("matchups", []):
            old_by_week.setdefault(m["week"], []).append(m)
    matchups = []
    for week in range(meta["start_week"] or 1, (last_week or 0) + 1):
        cached = old_by_week.get(week)
        if cached and week < (meta["current_week"] or 0) - 1 and all(m["status"] == "postevent" for m in cached):
            matchups.extend(cached)
            continue
        try:
            matchups.extend(parse.parse_scoreboard(client.get(f"league/{league_key}/scoreboard;week={week}")))
        except RuntimeError as e:
            log.warning("Scoreboard week %s failed for %s: %s", week, league_key, e)

    # Draft: only changes once per season.
    draft = (existing or {}).get("draft") or []
    if not draft and meta["draft_status"] == "postdraft":
        draft = parse.parse_draft(client.get(f"league/{league_key}/draftresults"))
        names = fetch_player_names(client, league_key, [d["player_key"] for d in draft if d["player_key"]])
        for d in draft:
            d.update(names.get(d["player_key"], {}))

    try:
        transactions = parse.parse_transactions(client.get(f"league/{league_key}/transactions"))
    except RuntimeError as e:
        log.warning("Transactions failed for %s: %s", league_key, e)
        transactions = (existing or {}).get("transactions", [])

    return {**meta, "settings": settings, "standings": standings, "matchups": matchups,
            "draft": draft, "transactions": transactions}


def write_outputs(seasons: list[dict], demo: bool = False) -> None:
    """Write index.json and history.json from season dicts (already saved individually)."""
    config = load_json(CONFIG / "owners.json", {}) or {}
    apply_owner_config(seasons, config)
    for s in seasons:
        write_json(SEASONS / f"{s['season']}.json", s)
    seasons = sorted(seasons, key=lambda s: s["season"])
    current = seasons[-1]
    write_json(DATA / "history.json", build_history(seasons))
    write_json(DATA / "index.json", {
        "league_name": current["name"],
        "current_season": current["season"],
        "seasons": [s["season"] for s in seasons],
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "demo": demo,
    })
    # Helper for filling in config/owners.json: every owner id and the names it has used.
    seen: dict[str, dict] = {}
    for s in seasons:
        for t in s["standings"]:
            e = seen.setdefault(t["owner_id"], {"names": [], "seasons": []})
            if t["owner_name"] not in e["names"]:
                e["names"].append(t["owner_name"])
            e["seasons"].append(s["season"])
    write_json(CONFIG / "owners_seen.json", seen)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true", help="re-pull finished seasons too")
    ap.add_argument("--max-seasons", type=int, default=40)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    client = YahooClient.from_env()
    key = current_league_key(client)
    cached = {p.stem: load_json(p) for p in SEASONS.glob("*.json")}
    cached_by_key = {s["league_key"]: s for s in cached.values() if s and not s.get("demo")}

    seasons, seen_keys = [], set()
    while key and key not in seen_keys and len(seasons) < args.max_seasons:
        seen_keys.add(key)
        existing = cached_by_key.get(key)
        if existing and existing.get("is_finished") and not args.full:
            log.info("Using cached season %s", existing["season"])
            season = existing
        else:
            try:
                season = pull_season(client, key, existing)
            except RuntimeError as e:
                # Very old seasons can be unavailable; stop walking back rather than fail the run.
                log.warning("Stopping history walk at %s: %s", key, e)
                break
        seasons.append(season)
        key = season.get("renew")

    if not seasons:
        sys.exit("No seasons pulled.")
    # Remove demo files once real data exists.
    for p in SEASONS.glob("*.json"):
        if (load_json(p) or {}).get("demo"):
            p.unlink()
    write_outputs(seasons)
    log.info("Done: %d seasons, %d API calls", len(seasons), client.calls)


if __name__ == "__main__":
    main()
