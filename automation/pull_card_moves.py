#!/usr/bin/env python3
"""Read-only. Pulls every list move on a Trello board (Trello keeps the full history) and writes:
  card_moves_<stamp>.csv       every move: when (ET), card, WO, from list, to list, who
  shrink_complete_<stamp>.csv  one row per card: first time it left To Shrink (= shrink finished), and the list it went to
Never writes to Trello. Credentials: env TRELLO_KEY and TRELLO_TOKEN.
  python3 pull_card_moves.py --board nUn1lqjT --out out_moves
  python3 pull_card_moves.py --snapshot board.json --out out_moves      # offline, uses the export's (partial) action list
"""
import argparse, csv, json, os, re, time, urllib.parse, urllib.request
from pathlib import Path
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
ET = ZoneInfo("America/New_York")
WO_RE = re.compile(r"WO (\d+)")


def fetch_all(board, key, token, base=None):
    base = base or os.environ.get("TRELLO_API_BASE", "https://api.trello.com/1")
    acts, before = [], None
    while True:
        q = {"key": key, "token": token, "filter": "updateCard:idList,createCard", "limit": 1000}
        if before: q["before"] = before
        with urllib.request.urlopen(f"{base}/boards/{board}/actions?{urllib.parse.urlencode(q)}", timeout=60) as r:
            page = json.loads(r.read())
        acts += page
        if len(page) < 1000: return acts
        before = min(a["date"] for a in page); time.sleep(0.3)


def moves(actions):
    out = []
    for a in actions:
        d = a.get("data", {})
        if a.get("type") == "updateCard" and "listBefore" in d and "listAfter" in d:
            name = d.get("card", {}).get("name", ""); m = WO_RE.search(name)
            when = datetime.fromisoformat(a["date"].replace("Z", "+00:00")).astimezone(ET)
            out.append(dict(when=when, card=name, wo=m[1] if m else "", frm=d["listBefore"]["name"], to=d["listAfter"]["name"],
                            who=(a.get("memberCreator") or {}).get("fullName", ""), card_id=d.get("card", {}).get("id", "")))
    return sorted(out, key=lambda x: x["when"])


def shrink_complete(mv):
    """First move out of To Shrink per card. Later moves back into To Shrink are ignored (a re-do shows in the full move list)."""
    first = {}
    for m in mv:
        if m["frm"] == "To Shrink" and m["card_id"] not in first: first[m["card_id"]] = m
    return list(first.values())


def main(argv=None):
    ap = argparse.ArgumentParser(); ap.add_argument("--board"); ap.add_argument("--snapshot"); ap.add_argument("--out", default="out_moves")
    a = ap.parse_args(argv)
    if a.snapshot: acts = json.load(open(a.snapshot)).get("actions", []); note = " (offline: the export holds only the latest ~1000 actions)"
    else: acts = fetch_all(a.board, os.environ["TRELLO_KEY"], os.environ["TRELLO_TOKEN"]); note = ""
    mv = moves(acts); sc = shrink_complete(mv)
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True); stamp = time.strftime("%Y%m%d_%H%M%S")
    with open(out / f"card_moves_{stamp}.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(["when_ET", "wo", "card", "from_list", "to_list", "moved_by"])
        for m in mv: w.writerow([m["when"].strftime("%Y-%m-%d %H:%M"), m["wo"], m["card"], m["frm"], m["to"], m["who"]])
    with open(out / f"shrink_complete_{stamp}.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(["shrink_done_ET", "wo", "card", "went_to", "moved_by"])
        for m in sc: w.writerow([m["when"].strftime("%Y-%m-%d %H:%M"), m["wo"], m["card"], m["to"], m["who"]])
    print(f"{len(acts)} actions | {len(mv)} list moves | {len(sc)} cards have left To Shrink{note}")
    print(f"Wrote card_moves_{stamp}.csv and shrink_complete_{stamp}.csv in {out}")


if __name__ == "__main__":
    main()
