"""All-time aggregates computed from per-season files. Pure functions, no I/O."""
from __future__ import annotations

from collections import defaultdict
from typing import Any


def _finished_matchup(m: dict, season_finished: bool) -> bool:
    if len(m["teams"]) != 2 or any(t["points"] is None for t in m["teams"]):
        return False
    return season_finished or m.get("status") == "postevent"


def apply_owner_config(seasons: list[dict], config: dict) -> None:
    """Merge owner ids (someone switched Yahoo accounts) and apply display-name overrides in place."""
    merge = config.get("merge", {})
    names = config.get("names", {})
    for s in seasons:
        for t in s["standings"]:
            t["owner_id"] = merge.get(t["owner_id"], t["owner_id"])
            if t["owner_id"] in names:
                t["owner_name"] = names[t["owner_id"]]


def build_history(seasons: list[dict], top_n: int = 10) -> dict[str, Any]:
    seasons = sorted(seasons, key=lambda s: s["season"])
    owners: dict[str, dict] = {}
    h2h: dict[str, dict[str, dict[str, int]]] = defaultdict(lambda: defaultdict(lambda: {"w": 0, "l": 0, "t": 0}))
    champions, weekly_scores, games, season_rows = [], [], [], []

    for s in seasons:
        finished = s.get("is_finished", False)
        n_playoff = (s.get("settings") or {}).get("num_playoff_teams")
        team_owner = {t["team_key"]: t for t in s["standings"]}

        for t in s["standings"]:
            o = owners.setdefault(t["owner_id"], {
                "owner_id": t["owner_id"], "name": t["owner_name"], "seasons": 0,
                "wins": 0, "losses": 0, "ties": 0, "points_for": 0.0, "points_against": 0.0,
                "titles": 0, "runner_ups": 0, "playoffs": 0, "last_places": 0,
                "playoff_wins": 0, "playoff_losses": 0, "finishes": [], "title_years": [],
            })
            o["name"] = t["owner_name"]  # most recent name wins
            o["seasons"] += 1
            o["wins"] += t["wins"]
            o["losses"] += t["losses"]
            o["ties"] += t["ties"]
            o["points_for"] += t["points_for"]
            o["points_against"] += t["points_against"]
            if finished and t["rank"]:
                o["finishes"].append(t["rank"])
                if t["rank"] == 1:
                    o["titles"] += 1
                    o["title_years"].append(s["season"])
                elif t["rank"] == 2:
                    o["runner_ups"] += 1
                if t["rank"] == s.get("num_teams"):
                    o["last_places"] += 1
                if n_playoff and t.get("playoff_seed") and t["playoff_seed"] <= n_playoff:
                    o["playoffs"] += 1
            games_played = t["wins"] + t["losses"] + t["ties"]
            season_rows.append({
                "season": s["season"], "owner_id": t["owner_id"], "team": t["name"],
                "wins": t["wins"], "losses": t["losses"], "ties": t["ties"],
                "points_for": t["points_for"], "rank": t["rank"] if finished else None,
                "ppg": round(t["points_for"] / games_played, 2) if games_played else 0,
            })

        if finished:
            by_rank = {t["rank"]: t for t in s["standings"]}
            champ, runner = by_rank.get(1), by_rank.get(2)
            if champ:
                champions.append({
                    "season": s["season"], "owner_id": champ["owner_id"], "team": champ["name"],
                    "record": f'{champ["wins"]}-{champ["losses"]}' + (f'-{champ["ties"]}' if champ["ties"] else ""),
                    "runner_up_owner_id": runner["owner_id"] if runner else None,
                    "runner_up_team": runner["name"] if runner else None,
                })

        for m in s.get("matchups", []):
            if m.get("is_consolation") or not _finished_matchup(m, finished):
                continue
            a, b = m["teams"]
            ta, tb = team_owner.get(a["team_key"]), team_owner.get(b["team_key"])
            if not ta or not tb:
                continue
            oa, ob = ta["owner_id"], tb["owner_id"]
            pa, pb = a["points"], b["points"]
            for t, pts in ((ta, pa), (tb, pb)):
                weekly_scores.append({"season": s["season"], "week": m["week"], "owner_id": t["owner_id"],
                                      "team": t["name"], "points": pts, "playoffs": m["is_playoffs"]})
            if pa > pb:
                res_a = "w"
            elif pb > pa:
                res_a = "l"
            else:
                res_a = "t"
            res_b = {"w": "l", "l": "w", "t": "t"}[res_a]
            h2h[oa][ob][res_a] += 1
            h2h[ob][oa][res_b] += 1
            if m["is_playoffs"] and res_a != "t":
                winner, loser = (oa, ob) if res_a == "w" else (ob, oa)
                owners[winner]["playoff_wins"] += 1
                owners[loser]["playoff_losses"] += 1
            hi, lo = (a, b) if pa >= pb else (b, a)
            games.append({
                "season": s["season"], "week": m["week"], "playoffs": m["is_playoffs"],
                "winner_owner_id": team_owner[hi["team_key"]]["owner_id"], "winner_team": team_owner[hi["team_key"]]["name"],
                "loser_owner_id": team_owner[lo["team_key"]]["owner_id"], "loser_team": team_owner[lo["team_key"]]["name"],
                "winner_points": hi["points"], "loser_points": lo["points"],
                "margin": round(hi["points"] - lo["points"], 2),
            })

    for o in owners.values():
        gp = o["wins"] + o["losses"] + o["ties"]
        o["win_pct"] = round((o["wins"] + 0.5 * o["ties"]) / gp, 3) if gp else 0
        o["points_for"] = round(o["points_for"], 2)
        o["points_against"] = round(o["points_against"], 2)
        o["avg_finish"] = round(sum(o["finishes"]) / len(o["finishes"]), 2) if o["finishes"] else None
        o["best_finish"] = min(o["finishes"]) if o["finishes"] else None
        del o["finishes"]

    scored = [w for w in weekly_scores if w["points"] > 0]
    decided = [g for g in games if g["margin"] > 0]
    return {
        "owners": sorted(owners.values(), key=lambda o: (-o["titles"], -o["win_pct"])),
        "champions": sorted(champions, key=lambda c: -c["season"]),
        "h2h": {a: dict(v) for a, v in h2h.items()},
        "records": {
            "high_scores": sorted(scored, key=lambda w: -w["points"])[:top_n],
            "low_scores": sorted(scored, key=lambda w: w["points"])[:top_n],
            "blowouts": sorted(decided, key=lambda g: -g["margin"])[:top_n],
            "closest": sorted(decided, key=lambda g: g["margin"])[:top_n],
            "best_seasons": sorted(season_rows, key=lambda r: (-r["wins"], -r["points_for"]))[:top_n],
            "most_points_season": sorted(season_rows, key=lambda r: -r["points_for"])[:top_n],
        },
    }
