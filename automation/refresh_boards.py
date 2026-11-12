#!/usr/bin/env python3
"""Builds the board data files from the newest winterization feed (see export_feed.py).  Read only; writes CSVs to an output folder.
  python3 refresh_boards.py --feed .../winterization_feed_latest.json --state state --out out_refresh_<stamp>
Writes (crew board): stages.csv kpis.csv season.csv arrivals.csv shrink_done.csv     (office board): pipeline.csv projfinish.csv     manifest.json
State folder: season_base.csv (season history, updated here), billed_decom_wos.txt (DECOM work orders already billed in 2026, from the last billed report),
arrivals_extra.json (boats finished before the move history started: {"WO": "YYYY-MM-DD"}), refresh_state.json (last page date label).
Team totals for the season chart stay as set in season_base.csv.
"""
import argparse, collections, csv, json, re
def isnssc(c):
    # NSSC label, or a card named "NSSC | ..." that has not been labeled yet (Screaming Eagle K04, 11/12)
    return "NSSC" in c["labels"] or c["name"].strip().upper().startswith("NSSC")
def isram(c):
    # RAM label excludes a card from the season unless it also carries winterization (13xx) operations (Lauren 11/12: Second Chance is both)
    return "RAM" in c["labels"] and not any(str(o.get("code","")).startswith("13") for o in c.get("ops",[]))
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
LM = {"To Shrink", "QA/Final Review", "To Bill", "Done", "Generating WW Estimate", "WW Estimate Out"}
LS = LM - {"To Shrink"}
TECH_LISTS = ["Roebuck", "Nick", "Butler", "O'Leary"]
FRESH = {"1300", "1301", "1302", "1305"}
SEASON_START = date(2026, 9, 1)
AVG = 2502.4   # 2026 average billed per boat (office board)


def load(feed):
    f = json.load(open(feed))
    dec = [c for c in f["cards"] if not c["closed"] and "WO " in c["name"] and not ((isnssc(c)) or isram(c))]  # note cards without a WO are not boats
    return f, dec


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--feed", required=True); ap.add_argument("--state", required=True); ap.add_argument("--out", required=True); a = ap.parse_args()
    f, dec = load(a.feed); st = Path(a.state); out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    gen = datetime.fromisoformat(f["generated_et"]); today = gen.date()
    opn = [c for c in f["cards"] if not c["closed"] and "WO " in c["name"]]
    cnt = collections.Counter(c["list"] for c in opn)
    # stages
    rows = [("Awaiting DFS", cnt["Awaiting DFS"]), ("Backlog", cnt["Backlog"] + cnt["Hauled"]), ("With techs", sum(cnt[x] for x in TECH_LISTS))] + \
           [(n, cnt[n]) for n in ["To Shrink", "QA/Final Review", "To Bill", "Generating WW Estimate", "WW Estimate Out", "Done"]]
    known = sum(n for _, n in rows)
    with open(out / "stages.csv", "w") as w:
        w.write("stage,boats,stage_order\n"); [w.write(f"{s},{n},{i+1}\n") for i, (s, n) in enumerate(rows)]
    # kpis
    mech = sum(c["list"] in LM for c in dec); shr = sum(c["list"] in LS for c in dec)
    import csv as _csv
    _loc = {}
    if (st / "location_exceptions.csv").exists():
        for _r in _csv.DictReader(open(st / "location_exceptions.csv")): _loc[_r["wo"]] = _r["kind"]
    _wo = lambda c: (re.search(r"WO (\d{6})", c["name"]) or [None, None])[1]
    # Hauled ring (Lauren 11/10): stored boats we service that are out of the water. Trailer boats count as hauled; boats stored IN THE WATER are left out of the ring; NSSC and RAM are already out of dec.
    hdec = [c for c in dec if _loc.get(_wo(c)) != "IN_WATER"]
    _ph = list(_csv.DictReader(open(st / "placeholders.csv"))) if (st / "placeholders.csv").exists() else []
    _ph = [r for r in _ph if not any(r["name"].lower() in c["name"].lower() for c in f["cards"] if not c["closed"])]   # once a real card exists, it counts and the placeholder row drops out   # boats we service and store with no card yet (Lauren 11/10)
    _ph_n, _ph_h = len(_ph), sum(1 for r in _ph if r.get("hauled", "").upper().startswith("Y"))
    haul = sum(("Hauled" in c["labels"]) or c["list"] in LM | {"Hauled"} or _loc.get(_wo(c)) == "TRAILER" for c in hdec)
    wtot = sum(any(o["code"] in FRESH for o in c["ops"]) for c in dec)
    wdone = sum(("FRESH WATER COMPLETE" in c["labels"]) and any(o["code"] in FRESH for o in c["ops"]) for c in dec)
    ahead = [c for c in dec if c["list"] not in LM]
    k = dict(ahead_of_shrink=len(dec) + _ph_n - shr, past_shrink=shr,
             parts_complete=sum("Parts Kitted - Complete" in c["labels"] for c in ahead),
             parts_incomplete=sum("Parts Kitted - Incomplete" in c["labels"] for c in ahead),
             hauled_ahead=sum("Hauled" in c["labels"] for c in ahead),
             open_cards=len(opn), ram_cards=sum(isram(c) for c in opn), total_boats=len(dec) + _ph_n,
             mechanics_done=mech, shrink_done=shr, water_done=wdone, water_total=wtot, hauled_done=haul + _ph_h, hauled_total=len(hdec) + _ph_n,
             hauled_all=haul + _ph_h + sum((("Hauled" in c["labels"]) or c["list"] in LM | {"Hauled"}) and isnssc(c) and not isram(c) for c in opn),
             hauled_nssc=sum((("Hauled" in c["labels"]) or c["list"] in LM | {"Hauled"}) and isnssc(c) and not isram(c) for c in opn),
             nssc_total=sum(isnssc(c) and not isram(c) for c in opn),
             total_all=len(dec) + _ph_n + sum(isnssc(c) and not isram(c) for c in opn))
    k["parts_not_marked"] = len(ahead) - k["parts_complete"] - k["parts_incomplete"]
    with open(out / "kpis.csv", "w") as w:
        w.write("metric,value\n"); [w.write(f"{m},{v}\n") for m, v in k.items()]; w.write(f"as_of,{today}\n")
    # arrivals / shrink finished, from the full move history (ET dates), first time only, DECOM cards on the board
    ids = {c["id"] for c in dec}; wo_of = {c["id"]: (re.search(r"WO (\d+)", c["name"]) or [None, ""])[1] for c in dec}
    arr, sd, sa, ss = [], [], set(), set()
    for m in sorted(f["moves"], key=lambda m: m["when"]):
        if m["card_id"] not in ids: continue
        day = datetime.fromisoformat(m["when"]).astimezone(ET).strftime("%Y-%m-%d"); cid = m["card_id"]
        if m["to"] in LM and m["from"] not in LM and cid not in sa: arr.append(day); sa.add(cid)
        if m["to"] in LS and m["from"] not in LS and cid not in ss: sd.append((day, m["to"])); ss.add(cid)
    extra = json.load(open(st / "arrivals_extra.json")) if (st / "arrivals_extra.json").exists() else {}
    have = {wo_of[i] for i in sa}
    for wo, d in extra.items():
        if wo not in have: arr.append(d)
    with open(out / "arrivals.csv", "w") as w:
        w.write("day\n"); [w.write(d + "\n") for d in sorted(arr)]
    with open(out / "shrink_done.csv", "w") as w:
        w.write("day,went_to\n"); [w.write(f"{d},{t}\n") for d, t in sorted(sd)]
    # season history: today's point
    base = list(csv.DictReader(open(st / "season_base.csv"))); day = (today - SEASON_START).days
    tot = {r["team"]: r["total"] for r in base if r["season"] == "2026"}
    base = [r for r in base if not (r["season"] == "2026" and int(r["day"]) == day)]
    for team, n in (("Mechanics", mech), ("Shrink team", shr)):
        t = int(tot[team]); base.append(dict(team=team, season="2026", day=str(day), boats=str(n), total=str(t), pct=str(round(100 * n / t, 1))))
    with open(out / "season.csv", "w", newline="") as w:
        cw = csv.DictWriter(w, ["team", "season", "day", "boats", "total", "pct"]); cw.writeheader(); cw.writerows(base)
    # office: pipeline and projected finish
    billed = set(open(st / "billed_decom_wos.txt").read().split()) if (st / "billed_decom_wos.txt").exists() else set()
    pipe = collections.Counter(c["list"] for c in dec if c["list"] in ("To Shrink", "QA/Final Review") and wo_of[c["id"]] not in billed)
    with open(out / "pipeline.csv", "w") as w:
        w.write("stage,boats,est_billable\n"); [w.write(f"{s},{pipe[s]},{round(pipe[s]*AVG)}\n") for s in ("To Shrink", "QA/Final Review")]
    end = today - timedelta(days=1)
    def pace(days, left):
        ds = [date.fromisoformat(x) for x in days]; n = sum(1 for x in ds if end - timedelta(days=14) < x <= end); r = n / 2
        return r, (end + timedelta(days=round(left / r * 7))).isoformat() if r else ""
    tr, td = pace(arr, len(dec) - mech); sr, sdn = pace([d for d, _ in sd], len(dec) - shr)
    with open(out / "projfinish.csv", "w") as w:
        w.write("team,boats_left,per_week,projected_done\n"); w.write(f"Tech's,{len(dec)-mech},{tr:g},{td}\n"); w.write(f"Shrink team's,{len(dec)-shr},{sr:g},{sdn}\n")
    label = f"{today:%B} {today.day}"
    prev = json.load(open(st / "refresh_state.json")) if (st / "refresh_state.json").exists() else {}
    man = dict(feed_generated=f["generated_et"], today=str(today), page_label_new=label, page_label_old=prev.get("label", ""), as_of_new=str(today), as_of_old=prev.get("as_of", ""), season_day=day,
               checks=dict(cards_in_known_lists=known, open_cards=len(opn), season_boats=len(dec)), kpis=k)
    json.dump(man, open(out / "manifest.json", "w"), indent=1)
    (out / "season_base_next.csv").write_text((out / "season.csv").read_text())
    print(json.dumps(man, indent=1))


if __name__ == "__main__": main()
