"""Scarica risultati e box score NBA (API pubblica non ufficiale di ESPN) e li accumula in data/games.json."""
import json, os, sys, time, traceback, datetime as dt
import requests

BASE = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"
OUT = "data/games.json"
START = os.environ.get("START_DATE", "2025-10-21")  # da dove scaricare lo storico


def get(url, **params):
    for i in range(3):
        try:
            r = requests.get(url, params=params, timeout=25)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            print("  errore di rete, riprovo:", e, file=sys.stderr)
            time.sleep(2 * (i + 1))
    return None


def num(x):
    try:
        return int(x)
    except (TypeError, ValueError):
        return 0


def players(summary):
    out = []
    for team in summary.get("boxscore", {}).get("players", []):
        abbr = team["team"]["abbreviation"]
        for block in team.get("statistics", [])[:1]:
            labels = block.get("labels", [])
            for a in block.get("athletes", []):
                if a.get("didNotPlay") or not a.get("stats"):
                    continue
                d = dict(zip(labels, a["stats"]))
                out.append({
                    "n": a["athlete"]["displayName"], "t": abbr,
                    "pos": (a["athlete"].get("position") or {}).get("abbreviation", ""),
                    "min": num(d.get("MIN")), "pts": num(d.get("PTS")),
                    "reb": num(d.get("REB")), "ast": num(d.get("AST")),
                    "stl": num(d.get("STL")), "blk": num(d.get("BLK")),
                    "tov": num(d.get("TO")), "fg": d.get("FG", "0-0"), "tp": d.get("3PT", "0-0"),
                })
    return out


def teams_of(ev):
    comp = ev["competitions"][0]["competitors"]
    home = next(c for c in comp if c["homeAway"] == "home")
    away = next(c for c in comp if c["homeAway"] == "away")
    return home, away


def save(data):
    data["updated"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes")
    tmp = OUT + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, separators=(",", ":"), ensure_ascii=False)
    os.replace(tmp, OUT)


def main():
    os.makedirs("data", exist_ok=True)
    data = {"games": {}}
    if os.path.exists(OUT):
        try:
            data = json.load(open(OUT, encoding="utf-8"))
        except Exception:
            print("File dati illeggibile, riparto da zero", file=sys.stderr)
            data = {"games": {}}
    games = data.setdefault("games", {})

    if games and data.get("from") == START:
        last = max(g["date"][:10] for g in games.values())
        start = dt.date.fromisoformat(last) - dt.timedelta(days=2)
    else:
        start = dt.date.fromisoformat(START)
    data["from"] = START

    day, end, errors = start, dt.date.today() + dt.timedelta(days=1), 0
    print("Scarico dal", start, "al", end, "- partite già salvate:", len(games))
    while day <= end:
        sb = get(BASE + "/scoreboard", dates=day.strftime("%Y%m%d"), limit=100)
        added = 0
        for ev in (sb or {}).get("events", []):
            try:
                if not ev["status"]["type"]["completed"] or ev["id"] in games:
                    continue
                home, away = teams_of(ev)
                summ = get(BASE + "/summary", event=ev["id"])
                if not summ:
                    errors += 1
                    continue
                games[ev["id"]] = {
                    "date": ev["date"],
                    "away": {"t": away["team"]["abbreviation"], "s": num(away["score"])},
                    "home": {"t": home["team"]["abbreviation"], "s": num(home["score"])},
                    "players": players(summ),
                }
                added += 1
            except Exception:
                errors += 1
                print("Partita saltata:", ev.get("id"), file=sys.stderr)
                traceback.print_exc()
        if added:
            save(data)  # salva i progressi giorno per giorno
            print(day, "- aggiunte", added, "partite")
        day += dt.timedelta(days=1)

    upcoming = {}
    for off in (0, 1):
        d = dt.date.today() + dt.timedelta(days=off)
        sb = get(BASE + "/scoreboard", dates=d.strftime("%Y%m%d"), limit=100)
        for ev in (sb or {}).get("events", []):
            try:
                if ev["status"]["type"]["completed"]:
                    continue
                home, away = teams_of(ev)
                upcoming[ev["id"]] = {"date": ev["date"], "home": home["team"]["abbreviation"], "away": away["team"]["abbreviation"]}
            except Exception:
                errors += 1
    data["upcoming"] = sorted(upcoming.values(), key=lambda g: g["date"])
    save(data)
    print("Fatto. Partite totali:", len(games), "- problemi:", errors)


if __name__ == "__main__":
    main()
