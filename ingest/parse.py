"""Pure functions that turn Yahoo XML responses into small, explicit dicts.

Only whitelisted fields are kept. In particular, manager emails and raw Yahoo
GUIDs are never written out: owners are identified by a short hash of the GUID.
"""
from __future__ import annotations

import hashlib
import xml.etree.ElementTree as ET
from typing import Any


def _text(el: ET.Element | None, path: str, default: str | None = None) -> str | None:
    if el is None:
        return default
    found = el.find(path)
    if found is None or found.text is None:
        return default
    return found.text.strip()


def _int(el, path, default=None):
    v = _text(el, path)
    try:
        return int(v) if v not in (None, "") else default
    except ValueError:
        return default


def _float(el, path, default=None):
    v = _text(el, path)
    try:
        return float(v) if v not in (None, "") else default
    except ValueError:
        return default


def _bool(el, path) -> bool:
    return _text(el, path) == "1"


def owner_id_for(guid: str | None, fallback: str | None) -> str:
    basis = guid if guid and guid not in ("--", "") else f"name:{fallback or 'unknown'}"
    return hashlib.sha1(basis.encode()).hexdigest()[:10]


def renew_to_league_key(renew: str | None) -> str | None:
    """Yahoo 'renew'/'renewed' fields look like '380_169896' -> '380.l.169896'."""
    if not renew or "_" not in renew:
        return None
    game_key, league_id = renew.split("_", 1)
    return f"{game_key}.l.{league_id}"


# ---------------------------------------------------------------- game / league

def parse_game_key(root: ET.Element) -> str:
    game = root.find(".//game")
    key = _text(game, "game_key")
    if not key:
        raise ValueError("No game_key in response")
    return key


def parse_league(root: ET.Element) -> dict[str, Any]:
    lg = root.find(".//league") if root.tag != "league" else root
    if lg is None:
        raise ValueError("No <league> element in response")
    return {
        "league_key": _text(lg, "league_key"),
        "league_id": _text(lg, "league_id"),
        "name": _text(lg, "name"),
        "season": _int(lg, "season"),
        "num_teams": _int(lg, "num_teams"),
        "start_week": _int(lg, "start_week", 1),
        "end_week": _int(lg, "end_week"),
        "current_week": _int(lg, "current_week"),
        "is_finished": _bool(lg, "is_finished"),
        "draft_status": _text(lg, "draft_status"),
        "scoring_type": _text(lg, "scoring_type"),
        "renew": renew_to_league_key(_text(lg, "renew")),
        "renewed": renew_to_league_key(_text(lg, "renewed")),
    }


def parse_settings(root: ET.Element) -> dict[str, Any]:
    st = root.find(".//settings")
    return {
        "num_playoff_teams": _int(st, "num_playoff_teams"),
        "playoff_start_week": _int(st, "playoff_start_week"),
        "uses_faab": _bool(st, "uses_faab"),
        "is_auction_draft": _bool(st, "is_auction_draft"),
        "draft_type": _text(st, "draft_type"),
    }


# ---------------------------------------------------------------- teams

def _manager(team: ET.Element) -> tuple[str, str]:
    """Return (owner_id, display_name) for a team's primary manager."""
    managers = team.findall("./managers/manager")
    if not managers:
        return owner_id_for(None, _text(team, "name")), _text(team, "name") or "Unknown"
    primary = next((m for m in managers if not _bool(m, "is_comanager")), managers[0])
    nickname = _text(primary, "nickname") or "Unknown"
    if nickname == "--hidden--":
        nickname = _text(team, "name") or "Unknown"
    return owner_id_for(_text(primary, "guid"), nickname), nickname


def parse_team_basic(team: ET.Element) -> dict[str, Any]:
    owner_id, owner_name = _manager(team)
    return {
        "team_key": _text(team, "team_key"),
        "team_id": _int(team, "team_id"),
        "name": _text(team, "name"),
        "owner_id": owner_id,
        "owner_name": owner_name,
        "logo": _text(team, "team_logos/team_logo/url"),
        "moves": _int(team, "number_of_moves"),
        "trades": _int(team, "number_of_trades"),
    }


def parse_standings(root: ET.Element) -> list[dict[str, Any]]:
    out = []
    for team in root.iter("team"):
        if team.find("team_standings") is None:
            continue
        row = parse_team_basic(team)
        ts = team.find("team_standings")
        row.update({
            "rank": _int(ts, "rank"),
            "playoff_seed": _int(ts, "playoff_seed"),
            "wins": _int(ts, "outcome_totals/wins", 0),
            "losses": _int(ts, "outcome_totals/losses", 0),
            "ties": _int(ts, "outcome_totals/ties", 0),
            "points_for": _float(ts, "points_for", 0.0),
            "points_against": _float(ts, "points_against", 0.0),
            "streak": (f"{(_text(ts, 'streak/type') or '')[:1].upper()}{_text(ts, 'streak/value') or ''}"
                       if ts.find("streak") is not None else None),
        })
        out.append(row)
    out.sort(key=lambda r: (r["rank"] is None, r["rank"] or 0))
    return out


# ---------------------------------------------------------------- matchups

def parse_scoreboard(root: ET.Element) -> list[dict[str, Any]]:
    out = []
    for m in root.iter("matchup"):
        teams = []
        for t in m.findall("./teams/team"):
            teams.append({
                "team_key": _text(t, "team_key"),
                "points": _float(t, "team_points/total"),
                "projected": _float(t, "team_projected_points/total"),
            })
        out.append({
            "week": _int(m, "week"),
            "status": _text(m, "status"),
            "is_playoffs": _bool(m, "is_playoffs"),
            "is_consolation": _bool(m, "is_consolation"),
            "is_tied": _bool(m, "is_tied"),
            "winner_team_key": _text(m, "winner_team_key"),
            "teams": teams,
        })
    return out


# ---------------------------------------------------------------- draft

def parse_draft(root: ET.Element) -> list[dict[str, Any]]:
    out = []
    for d in root.iter("draft_result"):
        out.append({
            "pick": _int(d, "pick"),
            "round": _int(d, "round"),
            "cost": _int(d, "cost"),
            "team_key": _text(d, "team_key"),
            "player_key": _text(d, "player_key"),
        })
    out.sort(key=lambda r: r["pick"] or 0)
    return out


def parse_players(root: ET.Element) -> dict[str, dict[str, Any]]:
    out = {}
    for p in root.iter("player"):
        key = _text(p, "player_key")
        if key:
            out[key] = {
                "name": _text(p, "name/full"),
                "position": _text(p, "display_position"),
                "nfl_team": _text(p, "editorial_team_abbr"),
            }
    return out


# ---------------------------------------------------------------- transactions

def parse_transactions(root: ET.Element) -> list[dict[str, Any]]:
    out = []
    for tx in root.iter("transaction"):
        players = []
        for p in tx.findall("./players/player"):
            td = p.find("transaction_data")
            players.append({
                "name": _text(p, "name/full"),
                "position": _text(p, "display_position"),
                "nfl_team": _text(p, "editorial_team_abbr"),
                "action": _text(td, "type"),
                "source_type": _text(td, "source_type"),
                "source_team_key": _text(td, "source_team_key"),
                "destination_type": _text(td, "destination_type"),
                "destination_team_key": _text(td, "destination_team_key"),
            })
        out.append({
            "id": _int(tx, "transaction_id"),
            "type": _text(tx, "type"),
            "status": _text(tx, "status"),
            "timestamp": _int(tx, "timestamp"),
            "faab_bid": _int(tx, "faab_bid"),
            "trader_team_key": _text(tx, "trader_team_key"),
            "tradee_team_key": _text(tx, "tradee_team_key"),
            "players": players,
        })
    out.sort(key=lambda r: r["timestamp"] or 0, reverse=True)
    return out
