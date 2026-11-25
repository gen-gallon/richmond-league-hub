import json
from pathlib import Path

from ingest import build, parse
from ingest.client import parse_xml
from ingest.history import build_history

FX = Path(__file__).parent / "fixtures"


def load(name):
    return parse_xml((FX / f"{name}.xml").read_bytes())


def test_league_meta_and_renew_key():
    lg = parse.parse_league(load("league"))
    assert lg["league_key"] == "461.l.8049"
    assert lg["season"] == 2026 and lg["current_week"] == 12 and lg["is_finished"] is False
    assert lg["renew"] == "449.l.31337"
    assert lg["renewed"] is None


def test_game_key():
    assert parse.parse_game_key(load("game")) == "461"


def test_settings():
    st = parse.parse_settings(load("settings"))
    assert st["num_playoff_teams"] == 6 and st["playoff_start_week"] == 15 and st["is_auction_draft"]


def test_standings_sorted_primary_manager_and_no_pii():
    rows = parse.parse_standings(load("standings"))
    assert [r["rank"] for r in rows] == [1, 2]
    alan, mike = rows
    assert alan["owner_name"] == "Alan" and alan["wins"] == 9 and alan["points_for"] == 1250.75
    assert alan["streak"] == "L1"
    assert mike["owner_name"] == "Mike"  # co-manager skipped
    assert mike["logo"] == "https://example.com/logo2.png"
    blob = json.dumps(rows)
    assert "@" not in blob and "GUID" not in blob


def test_scoreboard():
    (m,) = parse.parse_scoreboard(load("scoreboard"))
    assert m["week"] == 11 and m["status"] == "postevent" and not m["is_playoffs"]
    assert m["winner_team_key"] == "461.l.8049.t.1"
    assert m["teams"][0]["points"] == 132.4 and m["teams"][1]["projected"] == 110.0


def test_draft_and_players():
    d = parse.parse_draft(load("draftresults"))
    assert [x["pick"] for x in d] == [1, 2] and d[0]["cost"] == 61
    p = parse.parse_players(load("players"))
    assert p["461.p.11"] == {"name": "Josh Allen", "position": "QB", "nfl_team": "Buf"}


def test_transactions():
    tx = parse.parse_transactions(load("transactions"))
    assert tx[0]["type"] == "trade" and tx[0]["trader_team_key"] == "461.l.8049.t.1"
    add_drop = tx[1]
    assert [p["action"] for p in add_drop["players"]] == ["add", "drop"]
    assert add_drop["players"][0]["destination_team_key"] == "461.l.8049.t.1"


class FakeClient:
    """Serves fixture files by resource path, recording calls."""
    def __init__(self):
        self.paths = []
        self.calls = 0

    def get(self, path):
        self.paths.append(path)
        tail = path.split("/")[-1]
        if path.startswith("game/"):
            return load("game")
        if tail.startswith("scoreboard"):
            root = load("scoreboard")
            root.find(".//matchup/week").text = tail.split("=")[1]
            return root
        if tail.startswith("players"):
            return load("players")
        for name in ("settings", "standings", "draftresults", "transactions"):
            if tail == name:
                return load(name)
        return load("league")


def test_pull_season_end_to_end_and_incremental():
    c = FakeClient()
    s = build.pull_season(c, "461.l.8049", None)
    assert s["season"] == 2026 and len(s["standings"]) == 2
    assert sum(p.startswith("league/461.l.8049/scoreboard;week=") for p in c.paths) == 12
    assert s["draft"][0]["name"] == "Josh Allen"

    # Second run reuses final weeks older than current_week - 1 and skips the draft.
    c2 = FakeClient()
    build.pull_season(c2, "461.l.8049", s)
    weeks = [p for p in c2.paths if "scoreboard" in p]
    assert len(weeks) < 12
    assert not any("draftresults" in p for p in c2.paths)


def test_history_aggregates():
    c = FakeClient()
    s = build.pull_season(c, "461.l.8049", None)
    s["is_finished"] = True
    h = build_history([s])
    assert h["champions"][0]["team"] == "Alan's Team"
    alan = next(o for o in h["owners"] if o["name"] == "Alan")
    assert alan["titles"] == 1 and alan["playoffs"] == 1
    mike_id = next(o["owner_id"] for o in h["owners"] if o["name"] == "Mike")
    assert h["h2h"][alan["owner_id"]][mike_id]["w"] == 12  # fixture week repeated 12 times
    assert h["records"]["high_scores"][0]["points"] == 132.4
