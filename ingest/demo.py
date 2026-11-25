"""Generate clearly-labelled fake data so the site can be previewed before Yahoo access is approved.

    python -m ingest.demo
"""
from __future__ import annotations

import random

from .build import SEASONS, write_outputs
from .parse import owner_id_for

OWNERS = ["Commish", "Big Mike", "Dutch", "Sully", "Tank", "Pags", "Rocco", "Fitz", "Murph", "Goose"]
TEAM_WORDS = ["Gridiron", "Dynasty", "Thunder", "Blitz", "Mayhem", "Ballers", "Hogs", "Kings", "Sharks", "Bandits"]
PLAYERS = [("Josh Allen", "QB"), ("Lamar Jackson", "QB"), ("Bijan Robinson", "RB"), ("Jahmyr Gibbs", "RB"),
           ("Ja'Marr Chase", "WR"), ("CeeDee Lamb", "WR"), ("Justin Jefferson", "WR"), ("Puka Nacua", "WR"),
           ("Brock Bowers", "TE"), ("Saquon Barkley", "RB"), ("Jalen Hurts", "QB"), ("Amon-Ra St. Brown", "WR")]


def fake_season(year: int, rng: random.Random, finished: bool, current_week: int) -> dict:
    lk = f"999.l.{year}"
    teams = []
    for i, owner in enumerate(OWNERS):
        teams.append({"team_key": f"{lk}.t.{i + 1}", "team_id": i + 1,
                      "name": f"{owner}'s {rng.choice(TEAM_WORDS)}", "owner_id": owner_id_for(None, owner),
                      "owner_name": owner, "logo": None, "moves": rng.randint(5, 40), "trades": rng.randint(0, 4),
                      "wins": 0, "losses": 0, "ties": 0, "points_for": 0.0, "points_against": 0.0,
                      "rank": None, "playoff_seed": None, "streak": None})
    by_key = {t["team_key"]: t for t in teams}
    skill = {t["team_key"]: rng.uniform(95, 125) for t in teams}
    matchups = []
    reg_weeks = 14
    last = 17 if finished else current_week
    for week in range(1, min(reg_weeks, last) + 1):
        order = list(by_key)
        rng.shuffle(order)
        for a, b in zip(order[::2], order[1::2]):
            pa, pb = round(rng.gauss(skill[a], 22), 2), round(rng.gauss(skill[b], 22), 2)
            live = not finished and week == current_week
            matchups.append({"week": week, "status": "midevent" if live else "postevent",
                             "is_playoffs": False, "is_consolation": False, "is_tied": pa == pb,
                             "winner_team_key": None if live else (a if pa > pb else b),
                             "teams": [{"team_key": a, "points": pa, "projected": round(skill[a], 2)},
                                       {"team_key": b, "points": pb, "projected": round(skill[b], 2)}]})
            if not live:
                for k, mine, theirs in ((a, pa, pb), (b, pb, pa)):
                    t = by_key[k]
                    t["points_for"] = round(t["points_for"] + mine, 2)
                    t["points_against"] = round(t["points_against"] + theirs, 2)
                    t["wins" if mine > theirs else "losses"] += 1
    seeded = sorted(teams, key=lambda t: (-t["wins"], -t["points_for"]))
    for i, t in enumerate(seeded):
        t["playoff_seed"] = i + 1
        t["rank"] = i + 1
    if finished:
        # Simple 6-team bracket with byes; final ranks from playoff results.
        def play(week, a, b, playoffs=True):
            pa, pb = round(rng.gauss(skill[a["team_key"]], 22), 2), round(rng.gauss(skill[b["team_key"]], 22), 2)
            matchups.append({"week": week, "status": "postevent", "is_playoffs": playoffs, "is_consolation": False,
                             "is_tied": False, "winner_team_key": a["team_key"] if pa > pb else b["team_key"],
                             "teams": [{"team_key": a["team_key"], "points": pa, "projected": None},
                                       {"team_key": b["team_key"], "points": pb, "projected": None}]})
            return (a, b) if pa > pb else (b, a)
        s = seeded
        w1, _ = play(15, s[2], s[5])
        w2, _ = play(15, s[3], s[4])
        f1, l1 = play(16, s[0], w2)
        f2, l2 = play(16, s[1], w1)
        champ, runner = play(17, f1, f2)
        third, fourth = play(17, l1, l2)
        for rank, t in enumerate([champ, runner, third, fourth], start=1):
            t["rank"] = rank
        rest = [t for t in seeded if t not in (champ, runner, third, fourth)]
        for rank, t in enumerate(rest, start=5):
            t["rank"] = rank
    draft = []
    pool = PLAYERS[:]
    rng.shuffle(pool)
    for pick, (name, pos) in enumerate(pool, start=1):
        draft.append({"pick": pick, "round": 1, "cost": rng.randint(15, 70), "team_key": rng.choice(list(by_key)),
                      "player_key": f"999.p.{pick}", "name": name, "position": pos, "nfl_team": None})
    tx = []
    for i in range(8):
        name, pos = rng.choice(PLAYERS)
        tx.append({"id": i, "type": "add", "status": "successful", "timestamp": 1700000000 + i * 86400,
                   "faab_bid": None, "trader_team_key": None, "tradee_team_key": None,
                   "players": [{"name": name, "position": pos, "nfl_team": None, "action": "add",
                                "source_type": "freeagents", "source_team_key": None, "destination_type": "team",
                                "destination_team_key": rng.choice(list(by_key))}]})
    tx.sort(key=lambda t: -t["timestamp"])
    return {"league_key": lk, "league_id": str(year), "name": "Bro Lovers (DEMO DATA)", "season": year,
            "num_teams": 10, "start_week": 1, "end_week": 17, "current_week": 17 if finished else current_week,
            "is_finished": finished, "draft_status": "postdraft", "scoring_type": "head",
            "renew": f"999.l.{year - 1}" if year > 2007 else None, "renewed": None,
            "settings": {"num_playoff_teams": 6, "playoff_start_week": 15, "uses_faab": True,
                         "is_auction_draft": True, "draft_type": "live"},
            "standings": sorted(teams, key=lambda t: t["rank"]), "matchups": matchups, "draft": draft,
            "transactions": tx, "demo": True}


def main() -> None:
    rng = random.Random(8049)
    for p in SEASONS.glob("*.json"):
        p.unlink()
    seasons = [fake_season(y, rng, finished=y < 2026, current_week=12) for y in range(2007, 2027)]
    write_outputs(seasons, demo=True)
    print(f"Wrote {len(seasons)} demo seasons")


if __name__ == "__main__":
    main()
