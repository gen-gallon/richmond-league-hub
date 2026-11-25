"use strict";

const $ = (sel) => document.querySelector(sel);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmt = (n, d = 2) => (n == null ? "–" : Number(n).toFixed(d));
const rec = (w, l, t) => `${w}-${l}${t ? "-" + t : ""}`;
const cache = {};

async function getJSON(path) {
  if (!cache[path]) {
    cache[path] = fetch(path, { cache: "no-cache" }).then((r) => {
      if (!r.ok) throw new Error(`${path}: ${r.status}`);
      return r.json();
    });
  }
  return cache[path];
}

const state = { index: null, history: null, owners: {} };
const ownerName = (id) => state.owners[id]?.name ?? "Unknown";

function table(headers, rows) {
  const th = headers.map((h) => `<th class="${h.num ? "num" : ""}">${esc(h.label)}</th>`).join("");
  const body = rows.map((r) => `<tr>${r.map((c, i) => `<td class="${headers[i].num ? "num" : ""}">${c}</td>`).join("")}</tr>`).join("");
  return `<div class="card scroll"><table><thead><tr>${th}</tr></thead><tbody>${body}</tbody></table></div>`;
}

function teamCell(t) {
  return `<div class="team">${esc(t.name)}</div><div class="owner">${esc(t.owner_name)}</div>`;
}

// ---------------------------------------------------------------- This season
function standingsTable(season, { final = false } = {}) {
  const nPlayoff = season.settings?.num_playoff_teams;
  return table(
    [{ label: final ? "Finish" : "#" }, { label: "Team" }, { label: "W-L", num: true }, { label: "PF", num: true }, { label: "PA", num: true }, { label: final ? "Seed" : "Strk", num: true }],
    season.standings.map((t) => [
      final && t.rank === 1 ? `<span class="pill gold">Champ</span>` : esc(t.rank ?? ""),
      teamCell(t),
      rec(t.wins, t.losses, t.ties),
      fmt(t.points_for),
      fmt(t.points_against),
      final ? esc(t.playoff_seed ?? "") : (t.streak ? `<span class="${t.streak[0]}">${esc(t.streak)}</span>` : ""),
    ])
  );
}

function matchupCards(season, week) {
  const byKey = Object.fromEntries(season.standings.map((t) => [t.team_key, t]));
  const ms = season.matchups.filter((m) => m.week === week);
  if (!ms.length) return `<p class="muted">No matchups for week ${week}.</p>`;
  return `<div class="grid">${ms.map((m) => {
    const rows = m.teams.map((s) => {
      const t = byKey[s.team_key] || { name: s.team_key, owner_name: "" };
      const win = m.winner_team_key === s.team_key;
      return `<div class="row ${win ? "win" : ""}"><div>${teamCell(t)}</div><div class="pts">${fmt(s.points)}</div></div>`;
    }).join("");
    const tag = m.is_playoffs ? (m.is_consolation ? "Consolation" : "Playoffs") : "";
    const live = m.status === "midevent" ? "Live" : m.status === "preevent" ? "Upcoming" : "Final";
    const proj = m.status !== "postevent" && m.teams.every((s) => s.projected != null)
      ? ` · Proj ${fmt(m.teams[0].projected, 1)}–${fmt(m.teams[1].projected, 1)}` : "";
    return `<div class="card matchup">${rows}<div class="meta">${live}${tag ? " · " + tag : ""}${proj}</div></div>`;
  }).join("")}</div>`;
}

function transactionsList(season, limit = 15) {
  const byKey = Object.fromEntries(season.standings.map((t) => [t.team_key, t]));
  const name = (k) => esc(byKey[k]?.name ?? "");
  const items = season.transactions.filter((t) => t.status === "successful").slice(0, limit).map((tx) => {
    const when = tx.timestamp ? new Date(tx.timestamp * 1000).toLocaleDateString(undefined, { month: "short", day: "numeric" }) : "";
    let desc;
    if (tx.type === "trade") {
      desc = `<b>Trade</b> ${name(tx.trader_team_key)} ⇄ ${name(tx.tradee_team_key)}: ` +
        tx.players.map((p) => `${esc(p.name)} → ${name(p.destination_team_key)}`).join(", ");
    } else {
      desc = tx.players.map((p) => p.action === "add"
        ? `<span class="W">+</span> ${esc(p.name)} <span class="muted">${esc(p.position ?? "")}</span> to ${name(p.destination_team_key)}${tx.faab_bid ? ` ($${tx.faab_bid})` : ""}`
        : `<span class="L">−</span> ${esc(p.name)} <span class="muted">${esc(p.position ?? "")}</span> from ${name(p.source_team_key)}`
      ).join("<br>");
    }
    return `<div class="tx"><div class="when">${when}</div>${desc}</div>`;
  });
  return items.length ? `<div class="card">${items.join("")}</div>` : `<p class="muted">No transactions yet.</p>`;
}

async function renderSeason() {
  const s = await getJSON(`data/seasons/${state.index.current_season}.json`);
  const weeks = [...new Set(s.matchups.map((m) => m.week))].sort((a, b) => a - b);
  const latest = weeks.at(-1);
  const el = $("#tab-season");
  el.innerHTML = `
    <h2>${s.season} Standings</h2>${standingsTable(s, { final: s.is_finished })}
    <h2>Matchups</h2>
    <div class="controls"><label for="week">Week</label>
      <select id="week">${weeks.map((w) => `<option ${w === latest ? "selected" : ""}>${w}</option>`).join("")}</select></div>
    <div id="matchups">${latest ? matchupCards(s, latest) : "<p class='muted'>No games yet.</p>"}</div>
    <h2>Recent Transactions</h2>${transactionsList(s)}`;
  $("#week")?.addEventListener("change", (e) => { $("#matchups").innerHTML = matchupCards(s, Number(e.target.value)); });
}

// ---------------------------------------------------------------- All-time
function renderHistory() {
  const h = state.history;
  const champs = h.champions.map((c) => `
    <div class="card champ"><div class="yr">${c.season}</div>
      <div class="team">${esc(c.team)}</div><div class="owner">${esc(ownerName(c.owner_id))} · ${esc(c.record)}</div>
      ${c.runner_up_team ? `<div class="owner">def. ${esc(c.runner_up_team)}</div>` : ""}</div>`).join("");
  const owners = table(
    [{ label: "Owner" }, { label: "Yrs", num: true }, { label: "Titles", num: true }, { label: "Record", num: true },
     { label: "Win %", num: true }, { label: "Playoffs", num: true }, { label: "Playoff W-L", num: true },
     { label: "Avg Finish", num: true }, { label: "Points", num: true }, { label: "Last", num: true }],
    h.owners.map((o) => [
      `<span class="team">${esc(o.name)}</span>`, o.seasons,
      o.titles ? `<span class="pill gold">${o.titles}</span>` : "0",
      rec(o.wins, o.losses, o.ties), fmt(o.win_pct, 3).replace(/^0/, ""), o.playoffs,
      rec(o.playoff_wins, o.playoff_losses), fmt(o.avg_finish, 1), Math.round(o.points_for).toLocaleString(), o.last_places,
    ])
  );
  $("#tab-history").innerHTML = `<h2>Champions</h2><div class="champs">${champs || "<p class='muted'>No completed seasons yet.</p>"}</div>
    <h2>Owner Leaderboard</h2>${owners}
    <p class="muted">Record and points are regular season. Playoff W-L excludes consolation games.</p>`;
}

// ---------------------------------------------------------------- Head-to-head
function renderH2H() {
  const h = state.history;
  const ids = h.owners.map((o) => o.owner_id).sort((a, b) => ownerName(a).localeCompare(ownerName(b)));
  const head = `<th class="rowh">vs →</th>` + ids.map((id) => `<th>${esc(ownerName(id))}</th>`).join("");
  const rows = ids.map((a) => `<tr><th class="rowh">${esc(ownerName(a))}</th>` + ids.map((b) => {
    if (a === b) return `<td class="self"></td>`;
    const r = h.h2h[a]?.[b];
    if (!r) return `<td class="muted">–</td>`;
    const cls = r.w > r.l ? "W" : r.l > r.w ? "L" : "";
    return `<td class="${cls}">${rec(r.w, r.l, r.t)}</td>`;
  }).join("") + "</tr>").join("");
  $("#tab-h2h").innerHTML = `<h2>All-Time Head-to-Head</h2>
    <p class="muted">Read across: row owner's record against column owner. Includes playoffs, excludes consolation.</p>
    <div class="card scroll"><table class="h2h"><thead><tr>${head}</tr></thead><tbody>${rows}</tbody></table></div>`;
}

// ---------------------------------------------------------------- Records
function renderRecords() {
  const r = state.history.records;
  const wk = (w) => `${w.season} Wk ${w.week}${w.playoffs ? ` <span class="pill">PO</span>` : ""}`;
  const scoreTable = (rows) => table([{ label: "Owner" }, { label: "Team" }, { label: "When" }, { label: "Pts", num: true }],
    rows.map((x) => [esc(ownerName(x.owner_id)), esc(x.team), wk(x), `<b>${fmt(x.points)}</b>`]));
  const gameTable = (rows) => table([{ label: "Winner" }, { label: "Loser" }, { label: "When" }, { label: "Score", num: true }, { label: "Margin", num: true }],
    rows.map((g) => [esc(ownerName(g.winner_owner_id)), esc(ownerName(g.loser_owner_id)), wk(g), `${fmt(g.winner_points)}–${fmt(g.loser_points)}`, `<b>${fmt(g.margin)}</b>`]));
  const seasonTable = (rows) => table([{ label: "Owner" }, { label: "Team" }, { label: "Season" }, { label: "W-L", num: true }, { label: "PF", num: true }, { label: "PPG", num: true }],
    rows.map((x) => [esc(ownerName(x.owner_id)), esc(x.team), x.season, rec(x.wins, x.losses, x.ties), fmt(x.points_for), fmt(x.ppg)]));
  $("#tab-records").innerHTML = `
    <h2>Highest Single-Week Scores</h2>${scoreTable(r.high_scores)}
    <h2>Lowest Single-Week Scores</h2>${scoreTable(r.low_scores)}
    <h2>Biggest Blowouts</h2>${gameTable(r.blowouts)}
    <h2>Closest Games</h2>${gameTable(r.closest)}
    <h2>Best Regular Seasons</h2>${seasonTable(r.best_seasons)}
    <h2>Most Points in a Season</h2>${seasonTable(r.most_points_season)}`;
}

// ---------------------------------------------------------------- Past seasons
async function renderPastSeason(year) {
  const s = await getJSON(`data/seasons/${year}.json`);
  const byKey = Object.fromEntries(s.standings.map((t) => [t.team_key, t]));
  const auction = s.settings?.is_auction_draft;
  const draft = [...s.draft].sort((a, b) => auction ? (b.cost ?? 0) - (a.cost ?? 0) : a.pick - b.pick).slice(0, 25);
  const draftTable = draft.length ? table(
    [{ label: auction ? "#" : "Pick" }, { label: "Player" }, { label: "Pos" }, { label: "Team" }, { label: auction ? "Cost" : "Rd", num: true }],
    draft.map((d, i) => [auction ? i + 1 : d.pick, esc(d.name ?? d.player_key), esc(d.position ?? ""), esc(byKey[d.team_key]?.name ?? ""),
      auction ? `$${d.cost ?? "?"}` : d.round])
  ) : `<p class="muted">No draft data.</p>`;
  $("#past").innerHTML = `<h2>${s.season}: ${esc(s.name)}</h2>${standingsTable(s, { final: s.is_finished })}
    <h2>${auction ? "Top Auction Prices" : "Draft (first 25 picks)"}</h2>${draftTable}`;
}

function renderSeasons() {
  const years = [...state.index.seasons].reverse();
  $("#tab-seasons").innerHTML = `<div class="controls"><label for="season-pick">Season</label>
    <select id="season-pick">${years.map((y) => `<option>${y}</option>`).join("")}</select></div><div id="past"></div>`;
  $("#season-pick").addEventListener("change", (e) => renderPastSeason(e.target.value));
  renderPastSeason(years[0]);
}

// ---------------------------------------------------------------- Boot
const renderers = { season: renderSeason, history: renderHistory, h2h: renderH2H, records: renderRecords, seasons: renderSeasons };
const rendered = new Set();

function show(tab) {
  document.querySelectorAll(".tabs button").forEach((b) => b.setAttribute("aria-selected", b.dataset.tab === tab));
  document.querySelectorAll(".tab").forEach((s) => (s.hidden = s.id !== `tab-${tab}`));
  if (!rendered.has(tab)) {
    rendered.add(tab);
    Promise.resolve(renderers[tab]()).catch(fail);
  }
  history.replaceState(null, "", `#${tab}`);
}

function fail(err) {
  const el = $("#error");
  el.hidden = false;
  el.textContent = `Couldn't load league data (${err.message}).`;
}

(async function init() {
  try {
    [state.index, state.history] = await Promise.all([getJSON("data/index.json"), getJSON("data/history.json")]);
  } catch (e) { return fail(e); }
  state.owners = Object.fromEntries(state.history.owners.map((o) => [o.owner_id, o]));
  $("#league-name").textContent = state.index.league_name;
  $("#since").textContent = `Est. ${state.index.seasons[0]} · ${state.index.seasons.length} seasons`;
  $("#demo-banner").hidden = !state.index.demo;
  $("#updated").textContent = `Updated ${new Date(state.index.updated_at).toLocaleString()}.`;
  document.querySelectorAll(".tabs button").forEach((b) => b.addEventListener("click", () => show(b.dataset.tab)));
  const initial = location.hash.slice(1);
  show(renderers[initial] ? initial : "season");
})();
