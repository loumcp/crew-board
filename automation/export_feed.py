#!/usr/bin/env python3
"""Read-only. Saves a snapshot of the winterization board for the automatic board refresh.
Writes two files into the feed folder (default: Marina_Service_Ops/00_CURRENT/03_Latest_Exports/feed; a backup copy also goes to Google Drive > Winterization Feed when that folder exists):
  winterization_feed_<YYYY-MM-DD_HHMM>.json   (kept as history)
  winterization_feed_latest.json              (what the scheduled refresh reads)
Contents: lists, labels, every card (id, name, closed, list, labels, op codes with checked state) and every list move (full history).
Never writes to Trello. Credentials: env TRELLO_KEY and TRELLO_TOKEN.
  python3 export_feed.py --board nUn1lqjT
  python3 export_feed.py --snapshot board_export.json --out /tmp/feed      # offline test from a Trello export
"""
import argparse, json, os, re, sys, urllib.parse, urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pull_card_moves as pm

ET = ZoneInfo("America/New_York")
DEFAULT_OUT = Path.home() / "Marina_Service_Ops/00_CURRENT/03_Latest_Exports/feed"
DRIVE_COPY = Path.home() / "Library/CloudStorage/GoogleDrive-lm.mcpsiegrist@gmail.com/My Drive/Winterization Feed"   # optional backup copy
CODE_RE = re.compile(r"^\s*(\d{4}(?:\.\d+)?)\s*\|")


def get(path, key, token, **q):
    q.update(key=key, token=token)
    base = os.environ.get("TRELLO_API_BASE", "https://api.trello.com/1")
    with urllib.request.urlopen(f"{base}{path}?{urllib.parse.urlencode(q)}", timeout=120) as r:
        return json.loads(r.read())


def card_row(c, lists, ops):
    return {"id": c["id"], "name": c["name"], "closed": bool(c["closed"]), "list": lists.get(c["idList"], ""),
            "labels": [l["name"] for l in c.get("labels", [])], "ops": ops}


def ops_of(checklists):
    out = []
    for cl in checklists:
        if cl.get("name") != "WORK ORDER OPERATIONS": continue
        for it in cl.get("checkItems", []):
            m = CODE_RE.match(it.get("name", ""))
            if m: out.append({"code": m[1], "done": it.get("state") == "complete"})
    return out


def from_snapshot(path):
    d = json.load(open(path)); lists = {l["id"]: l["name"] for l in d["lists"]}
    ck = {}
    for cl in d["checklists"]: ck.setdefault(cl["idCard"], []).append(cl)
    cards = [card_row(c, lists, ops_of(ck.get(c["id"], []))) for c in d["cards"]]
    return lists, cards, pm.moves(d["actions"])


def from_trello(board, key, token):
    ls = get(f"/boards/{board}/lists", key, token, filter="all", fields="name"); lists = {l["id"]: l["name"] for l in ls}
    cs = get(f"/boards/{board}/cards/all", key, token, fields="name,closed,idLabels,idList,labels", checklists="all", checklist_fields="name")
    cards = [card_row(c, lists, ops_of(c.get("checklists", []))) for c in cs]
    return lists, cards, pm.moves(pm.fetch_all(board, key, token))


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--board", default="nUn1lqjT"); ap.add_argument("--snapshot"); ap.add_argument("--out", default=str(DEFAULT_OUT)); a = ap.parse_args()
    if a.snapshot: lists, cards, mv = from_snapshot(a.snapshot)
    else: lists, cards, mv = from_trello(a.board, os.environ["TRELLO_KEY"], os.environ["TRELLO_TOKEN"])
    now = datetime.now(ET)
    feed = {"generated_et": now.isoformat(timespec="seconds"), "board": a.board, "lists": sorted(lists.values()), "cards": cards,
            "moves": [{"when": m["when"].isoformat(timespec="seconds"), "card_id": m["card_id"], "wo": m["wo"], "from": m["frm"], "to": m["to"]} for m in mv]}
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    txt = json.dumps(feed, separators=(",", ":"))
    for folder in [out] + ([DRIVE_COPY] if DRIVE_COPY.is_dir() and str(out) == str(DEFAULT_OUT) else []):
        (folder / f"winterization_feed_{now:%Y-%m-%d_%H%M}.json").write_text(txt)
        (folder / "winterization_feed_latest.json").write_text(txt)
        print(f"Feed saved: {len(cards)} cards, {len(mv)} moves -> {folder}")


if __name__ == "__main__": main()
