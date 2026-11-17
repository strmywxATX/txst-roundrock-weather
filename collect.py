#!/usr/bin/env python3
"""Collector for the Texas State University Round Rock weather station archive.

Pulls recent observations for TexMesonet station 142 and merges them into
monthly CSV files under data/YYYY/YYYY-MM.csv (UTC months, native units).
Rows are keyed by observation time, so re-running is safe: new times are
added and existing times are refreshed with the latest values.

Usage:
    python collect.py                 # fetch the last 24 hours and merge
    python collect.py --minutes 180   # fetch a shorter window
    python collect.py --from-file x   # merge a saved API response (testing)

The source is isolated in fetch_texmesonet(); to move to another feed
(Synoptic, CampbellCloud, the datalogger), add a function that returns the
same list of row dicts and call it from main().
"""
import argparse
import csv
import json
import os
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

STATION_ID = 142
STATION_NAME = "Texas State University Round Rock"
API = "https://www.texmesonet.org/api/AllChartingFieldsById/{sid}/{minutes}"
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

# archive column -> TexMesonet field
FIELDS = [
    ("air_temp_2m_c", "airTemp"),
    ("air_temp_9m_c", "airTemp9m"),
    ("rh_pct", "humidity"),
    ("precip_mm", "precip"),
    ("wind_speed_10m_ms", "windSpeed10m"),
    ("wind_gust_10m_ms", "windGust10m"),
    ("wind_dir_10m_deg", "windDirection10m"),
    ("pressure_mb", "airPressure"),
    ("solar_wm2", "solarRadiation"),
    ("soil_temp_5cm_c", "soilTemp5"),
    ("soil_temp_10cm_c", "soilTemp10"),
    ("soil_temp_20cm_c", "soilTemp20"),
    ("soil_temp_50cm_c", "soilTemp50"),
    ("soil_vwc_5cm", "soilMoist5"),
    ("soil_vwc_10cm", "soilMoist10"),
    ("soil_vwc_20cm", "soilMoist20"),
    ("soil_vwc_50cm", "soilMoist50"),
]
HEADER = ["time_utc"] + [c for c, _ in FIELDS]


def clean(value):
    """Return a tidy numeric string, or '' when the value is missing."""
    if value is None:
        return ""
    s = str(value).strip()
    if s == "":
        return ""
    try:
        f = float(s)
    except ValueError:
        return ""
    if f != f or f in (float("inf"), float("-inf")):
        return ""
    return ("%.4f" % f).rstrip("0").rstrip(".") or "0"


def norm_time(s):
    """Normalize an API timestamp to 'YYYY-MM-DDTHH:MMZ' (UTC)."""
    s = s.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")


def parse_response(text):
    """Parse a TexMesonet response (JSON or XML) into a list of row dicts."""
    text = text.lstrip("﻿ \r\n\t")
    records = []
    if text.startswith("{") or text.startswith("["):
        payload = json.loads(text)
        values = payload.get("values") or payload.get("Values") or []
        for v in values:
            records.append({k.lower(): val for k, val in v.items()})
    else:
        root = ET.fromstring(text)
        for el in root.iter():
            kids = {c.tag.split("}")[-1].lower(): (c.text or "") for c in el}
            if "datetime" in kids:
                records.append(kids)
    rows = []
    for r in records:
        t = r.get("datetime")
        if not t:
            continue
        row = {"time_utc": norm_time(t)}
        for col, src in FIELDS:
            row[col] = clean(r.get(src.lower()))
        if any(row[c] for c, _ in FIELDS):
            rows.append(row)
    return rows


def fetch_texmesonet(minutes):
    url = API.format(sid=STATION_ID, minutes=minutes)
    req = urllib.request.Request(url, headers={
        "Accept": "application/json",
        "User-Agent": "txst-roundrock-weather-archive (Texas State University, Geography & Environmental Studies)",
    })
    last_err = None
    for _ in range(3):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return parse_response(resp.read().decode("utf-8", "replace"))
        except Exception as err:  # network hiccup: retry
            last_err = err
    raise SystemExit("TexMesonet request failed: %s" % last_err)


def month_path(time_utc):
    return os.path.join(DATA_DIR, time_utc[:4], time_utc[:7] + ".csv")


def read_month(path):
    rows = {}
    if os.path.exists(path):
        with open(path, newline="") as fh:
            for r in csv.DictReader(fh):
                rows[r["time_utc"]] = {h: r.get(h, "") for h in HEADER}
    return rows


def write_month(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=HEADER, lineterminator="\n")
        w.writeheader()
        for t in sorted(rows):
            w.writerow(rows[t])


def merge(new_rows):
    """Merge rows into the monthly files. Returns (added, changed)."""
    by_month = {}
    for r in new_rows:
        by_month.setdefault(month_path(r["time_utc"]), []).append(r)
    added = changed = 0
    for path, rows in by_month.items():
        existing = read_month(path)
        dirty = False
        for r in rows:
            old = existing.get(r["time_utc"])
            if old is None:
                added += 1
                dirty = True
            elif old != r:
                changed += 1
                dirty = True
            existing[r["time_utc"]] = r
        if dirty:
            write_month(path, existing)
    return added, changed


def write_index():
    months, first, last, count = [], None, None, 0
    for year in sorted(os.listdir(DATA_DIR)) if os.path.isdir(DATA_DIR) else []:
        ydir = os.path.join(DATA_DIR, year)
        if not os.path.isdir(ydir):
            continue
        for name in sorted(os.listdir(ydir)):
            if not name.endswith(".csv"):
                continue
            rows = read_month(os.path.join(ydir, name))
            if not rows:
                continue
            times = sorted(rows)
            months.append({"month": name[:-4], "file": "%s/%s" % (year, name), "rows": len(times),
                           "first": times[0], "last": times[-1]})
            first = first or times[0]
            last = times[-1]
            count += len(times)
    index = {"station": STATION_NAME, "texmesonet_id": STATION_ID, "synoptic_id": "TW142",
             "first": first, "last": last, "rows": count, "months": months}
    path = os.path.join(DATA_DIR, "index.json")
    old = None
    if os.path.exists(path):
        with open(path) as fh:
            old = fh.read()
    new = json.dumps(index, indent=1) + "\n"
    if new != old:
        with open(path, "w") as fh:
            fh.write(new)
    return index


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--minutes", type=int, default=1440,
                    help="look-back window; 1440 or less returns 15-minute records")
    ap.add_argument("--from-file", help="merge a saved API response instead of calling the API")
    args = ap.parse_args()

    if args.from_file:
        with open(args.from_file) as fh:
            rows = parse_response(fh.read())
    else:
        rows = fetch_texmesonet(args.minutes)
    if not rows:
        print("No observations returned; archive left unchanged.")
        return 0
    added, changed = merge(rows)
    index = write_index()
    print("Fetched %d rows: %d new, %d updated. Archive: %s rows, %s to %s."
          % (len(rows), added, changed, index["rows"], index["first"], index["last"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
