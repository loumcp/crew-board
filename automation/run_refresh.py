#!/usr/bin/env python3
"""Pulls the winterization Trello board (read only), rebuilds the crew board CSVs, and refuses to publish if the numbers look wrong.
Needs env TRELLO_KEY and TRELLO_TOKEN. Run from the repo root:  python3 automation/run_refresh.py"""
import csv, json, os, shutil, subprocess, sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
A = ROOT / "automation"; ST = A / "state"; WORK = ROOT / ".work"
FILES = ["kpis.csv", "stages.csv", "season.csv", "arrivals.csv", "shrink_done.csv"]
shutil.rmtree(WORK, ignore_errors=True); WORK.mkdir()

cmd = [sys.executable, str(A / "export_feed.py"), "--board", "nUn1lqjT", "--out", str(WORK / "feed")]
if os.environ.get("SNAPSHOT"): cmd += ["--snapshot", os.environ["SNAPSHOT"]]   # offline test only
subprocess.run(cmd, check=True)
feed = WORK / "feed" / "winterization_feed_latest.json"
subprocess.run([sys.executable, str(A / "refresh_boards.py"), "--feed", str(feed), "--state", str(ST), "--out", str(WORK / "out")], check=True, stdout=subprocess.DEVNULL)
out = WORK / "out"

# sanity checks: do not publish a broken refresh
f = json.load(open(feed))
kp = {r["metric"]: r["value"] for r in csv.DictReader(open(out / "kpis.csv"))}
old = {r["metric"]: r["value"] for r in csv.DictReader(open(ROOT / "kpis.csv"))}
total, old_total = int(kp["total_boats"]), int(old.get("total_boats", 0) or 0)
if len(f["cards"]) < 150 or not (100 <= total <= 220) or (old_total and abs(total - old_total) > 15):
    sys.exit(f"Refusing to publish: {len(f['cards'])} cards, total_boats {total} (was {old_total}). Nothing changed.")
if int(kp["mechanics_done"]) < int(old.get("mechanics_done", 0) or 0) - 5:
    sys.exit("Refusing to publish: mechanics_done dropped by more than 5. Nothing changed.")

if int(kp["shrink_done"]) < int(old.get("shrink_done", 0) or 0) - 5:
    sys.exit("Refusing to publish: shrink_done dropped by more than 5. Nothing changed.")

changed = False
for fn in FILES:
    new = (out / fn).read_text()
    if not (ROOT / fn).exists() or (ROOT / fn).read_text() != new: changed = True
    (ROOT / fn).write_text(new); (ROOT / "data").mkdir(exist_ok=True); (ROOT / "data" / fn).write_text(new)
if changed:
    now = datetime.now(ZoneInfo("America/New_York"))
    label = f"{now:%B} {now.day}, {now.hour % 12 or 12}:{now:%M} {now:%p}"
    (ROOT / "updated.txt").write_text(label); (ROOT / "data" / "updated.txt").write_text(label)
    shutil.copy(out / "season_base_next.csv", ST / "season_base.csv")
    (ST / "refresh_state.json").write_text(json.dumps({"label": label, "as_of": kp.get("as_of", "")}))
    print("Updated:", label, "| boats", total, "| mechanics done", kp["mechanics_done"], "| shrink done", kp["shrink_done"])
else:
    print("No change.")
shutil.rmtree(WORK, ignore_errors=True)
