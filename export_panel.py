#!/usr/bin/env python3
"""Export mnd-pla-tracker DB to PLAReport JSON for drone-monitor panel."""
import json, sqlite3, os, sys

DB_PATH = os.path.join(os.path.dirname(__file__), "tracker.db")
DATA_DIR = os.path.join(os.path.dirname(__file__), "mnd_pla_data")

def _load_image_urls():
    """Build id → infographic image URL map from JSONL target_media_files."""
    urls = {}
    jsonl = os.path.join(DATA_DIR, "records.jsonl")
    if not os.path.exists(jsonl):
        return urls
    with open(jsonl) as f:
        for line in f:
            r = json.loads(line.strip())
            for mf in (r.get("target_media_files") or []):
                src = mf.get("source_url", "")
                if "/NewUpload/" in src and src.lower().endswith((".jpg", ".jpeg", ".png")):
                    urls[r["id"]] = src
                    break
    return urls

def export_pla_reports(db_path=DB_PATH, out_path=None):
    c = sqlite3.connect(db_path)
    c.row_factory = sqlite3.Row
    img_urls = _load_image_urls()

    rows = c.execute("""SELECT id, date, total_aircraft, aircraft_types, has_uav,
        crossed_median, entered_adiz, ships, areas, source, url, report_window,
        has_image, ocr_date, ocr_total_sorties, ocr_has_uav, ocr_zones_json
        FROM activities WHERE date != '' ORDER BY date DESC""").fetchall()

    reports = []
    for r in rows:
        types = [t for t in (r["aircraft_types"] or "").split("+") if t]
        area_map = {"SW_ADIZ": "SW ADIZ", "SE_ADIZ": "SE ADIZ", "N_ADIZ": "Northern ADIZ",
                    "E_ADIZ": "Eastern ADIZ", "median_line": "Median Line", "strait": "Taiwan Strait"}
        areas = [area_map.get(a, a) for a in (r["areas"] or "").split("+") if a]

        uav_count = 0
        if r["ocr_zones_json"]:
            try:
                for z in json.loads(r["ocr_zones_json"]):
                    if z.get("has_uav"):
                        uav_count += z.get("total_sorties", 0)
            except (json.JSONDecodeError, TypeError):
                pass
        if r["has_uav"] and uav_count == 0:
            uav_count = 1

        reports.append({
            "id": r["id"],
            "issueDate": r["date"],
            "reportWindow": r["report_window"],
            "totalAircraft": r["total_aircraft"] or 0,
            "uavCount": uav_count,
            "crossedMedian": r["crossed_median"] or 0,
            "aircraftTypes": types,
            "activityAreas": areas,
            "reactions": None,
            "infographicUrl": img_urls.get(r["id"]),
            "sourceUrl": r["url"] or f"https://www.mnd.gov.tw/en/news/plaact/{r['id']}",
            "uavKeywordFlag": bool(r["has_uav"]),
        })

    c.close()
    if out_path:
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        with open(out_path, "w") as f:
            json.dump(reports, f)
        print(f"Exported {len(reports)} reports to {out_path}")

    uav = sum(1 for r in reports if r["uavKeywordFlag"])
    with_img = sum(1 for r in reports if r["infographicUrl"])
    print(f"  Total: {len(reports)}, UAV: {uav}, With images: {with_img}", file=sys.stderr)

if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else None
    export_pla_reports(out_path=out)
