import sqlite3, json, csv, os

DB_PATH = os.path.join(os.path.dirname(__file__), "tracker.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS activities (
    id INTEGER PRIMARY KEY,          -- MND record ID
    date TEXT,                       -- WHEN: YYYY-MM-DD
    total_aircraft INTEGER,          -- HOW MANY: total aircraft/sorties
    aircraft_types TEXT,             -- WHAT: fighter+bomber+UAV etc
    has_uav INTEGER DEFAULT 0,       -- UAV OR NOT: 1/0
    crossed_median INTEGER DEFAULT 0,-- HOW: sorties crossing median line
    entered_adiz INTEGER DEFAULT 0,  -- HOW: sorties entering ADIZ
    ships INTEGER DEFAULT 0,         -- WHO ELSE: PLAN ships + official ships
    areas TEXT,                      -- WHERE: SW_ADIZ, N_ADIZ, median_line etc
    source TEXT,                     -- data source: image/aircraft_type/pla_text/full_text
    -- original fields
    url TEXT,
    page_title TEXT,
    report_window TEXT,
    aircraft_type_raw TEXT,
    pla_activities_text TEXT,
    -- OCR fields (NULL if no image)
    has_image INTEGER DEFAULT 0,
    ocr_date TEXT,
    ocr_total_sorties INTEGER,
    ocr_has_uav INTEGER,
    ocr_zones_json TEXT
);
CREATE TABLE IF NOT EXISTS sorties (
    id INTEGER PRIMARY KEY,
    record_id INTEGER REFERENCES activities(id),
    zone TEXT,
    time_window TEXT,
    aircraft_types TEXT,
    total_sorties INTEGER,
    crossed_median INTEGER,
    has_uav INTEGER
);
CREATE INDEX IF NOT EXISTS idx_act_date ON activities(date);
CREATE INDEX IF NOT EXISTS idx_act_uav ON activities(has_uav);
CREATE INDEX IF NOT EXISTS idx_sort_rec ON sorties(record_id);
CREATE INDEX IF NOT EXISTS idx_sort_uav ON sorties(has_uav);
"""

def get_conn(db=DB_PATH):
    c = sqlite3.connect(db)
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA)
    return c

def upsert_activity(rec, parsed_text, db=DB_PATH):
    """Insert/update a record with text-parsed data."""
    c = get_conn(db)
    p = parsed_text
    c.execute("""INSERT OR REPLACE INTO activities
        (id, date, total_aircraft, aircraft_types, has_uav, crossed_median, entered_adiz, ships, areas, source,
         url, page_title, report_window, aircraft_type_raw, pla_activities_text)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (rec["id"], p["date"], p["total_aircraft"], "+".join(p["aircraft_types"]),
         int(p["has_uav"]), p["crossed_median"], p["entered_adiz"], p["ships"],
         "+".join(p["areas"]), p["source"],
         rec.get("final_url"), rec.get("page_title"), rec.get("report_window"),
         rec.get("aircraft_type"), rec.get("pla_activities_text")))
    c.commit()
    c.close()

def enrich_ocr(record_id, image_path, parsed_ocr, db=DB_PATH):
    """Add OCR zone data to an existing activity record."""
    c = get_conn(db)
    zones_json = json.dumps([{
        "zone": z.zone, "time_window": z.time_window,
        "aircraft_types": z.aircraft_types, "total_sorties": z.total_sorties,
        "crossed_median": z.crossed_median, "has_uav": z.has_uav
    } for z in parsed_ocr.zones])

    # Update OCR fields + override date/uav if OCR found them
    updates = {"has_image": 1, "ocr_zones_json": zones_json,
               "ocr_total_sorties": parsed_ocr.total_sorties, "ocr_has_uav": int(parsed_ocr.has_uav)}
    if parsed_ocr.date_start:
        updates["ocr_date"] = parsed_ocr.date_start
        updates["date"] = parsed_ocr.date_start  # OCR date is more reliable
    if parsed_ocr.has_uav:
        updates["has_uav"] = 1
    if parsed_ocr.total_sorties:
        # Merge OCR aircraft types into the record
        ocr_types = set()
        for z in parsed_ocr.zones:
            ocr_types.update(z.aircraft_types)
        if ocr_types:
            # Get existing types
            row = c.execute("SELECT aircraft_types FROM activities WHERE id=?", (record_id,)).fetchone()
            existing = set(row["aircraft_types"].split("+")) if row and row["aircraft_types"] else set()
            merged = existing | ocr_types
            updates["aircraft_types"] = "+".join(sorted(merged))
        # Sum crossed from OCR zones
        ocr_crossed = sum(z.crossed_median for z in parsed_ocr.zones)
        if ocr_crossed:
            updates["crossed_median"] = ocr_crossed

    set_clause = ", ".join(f"{k}=?" for k in updates)
    c.execute(f"UPDATE activities SET {set_clause} WHERE id=?", (*updates.values(), record_id))

    c.execute("DELETE FROM sorties WHERE record_id=?", (record_id,))
    for z in parsed_ocr.zones:
        c.execute("""INSERT INTO sorties (record_id, zone, time_window, aircraft_types, total_sorties, crossed_median, has_uav)
            VALUES (?,?,?,?,?,?,?)""",
            (record_id, z.zone, z.time_window, "+".join(z.aircraft_types),
             z.total_sorties, z.crossed_median, int(z.has_uav)))
    c.commit()
    c.close()

def query(uav_only=False, date_from=None, date_to=None, aircraft_type=None, crossed_only=False, db=DB_PATH):
    c = get_conn(db)
    sql = "SELECT * FROM activities WHERE 1=1"
    params = []
    if uav_only:
        sql += " AND has_uav=1"
    if date_from:
        sql += " AND date>=?"; params.append(date_from)
    if date_to:
        sql += " AND date<=?"; params.append(date_to)
    if aircraft_type:
        sql += " AND LOWER(aircraft_types) LIKE LOWER(?)"; params.append(f"%{aircraft_type}%")
    if crossed_only:
        sql += " AND crossed_median>0"
    sql += " ORDER BY date DESC"
    rows = c.execute(sql, params).fetchall()
    c.close()
    return [dict(r) for r in rows]

def stats(db=DB_PATH):
    c = get_conn(db)
    r = lambda sql: c.execute(sql).fetchone()[0]
    s = {
        "total_records": r("SELECT COUNT(*) FROM activities"),
        "with_date": r("SELECT COUNT(*) FROM activities WHERE date!=''"),
        "with_image": r("SELECT COUNT(*) FROM activities WHERE has_image=1"),
        "with_ocr_zones": r("SELECT COUNT(*) FROM activities WHERE ocr_total_sorties>0"),
        "has_uav": r("SELECT COUNT(*) FROM activities WHERE has_uav=1"),
        "total_crossed": r("SELECT COALESCE(SUM(crossed_median),0) FROM activities"),
        "date_range": r("SELECT MIN(date) FROM activities WHERE date!=''") + " to " + r("SELECT MAX(date) FROM activities WHERE date!=''"),
        "by_source": {},
    }
    for row in c.execute("SELECT source, COUNT(*) as n FROM activities GROUP BY source ORDER BY n DESC"):
        s["by_source"][row["source"]] = row["n"]
    c.close()
    return s

def export_csv(out_path, db=DB_PATH):
    c = get_conn(db)
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)

    # Unified activity view
    act_path = out_path + "_activities.csv"
    rows = c.execute("""SELECT id, date, total_aircraft, aircraft_types, has_uav,
        crossed_median, entered_adiz, ships, areas, source, url, page_title, report_window,
        aircraft_type_raw, pla_activities_text, has_image,
        ocr_date, ocr_total_sorties, ocr_has_uav, ocr_zones_json
        FROM activities ORDER BY date, id""").fetchall()
    with open(act_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id","date","total_aircraft","aircraft_types","has_uav",
                     "crossed_median","entered_adiz","ships","areas","source","url","page_title",
                     "report_window","aircraft_type_raw","pla_activities_text",
                     "has_image","ocr_date","ocr_total_sorties","ocr_has_uav","ocr_zones_json"])
        for r in rows:
            w.writerow(list(r))
    print(f"  Activities: {act_path} ({len(rows)} rows)")

    # Zone-level sorties
    sort_path = out_path + "_sorties.csv"
    rows = c.execute("""SELECT s.record_id, a.date,
        s.zone, s.time_window, s.aircraft_types, s.total_sorties, s.crossed_median, s.has_uav
        FROM sorties s JOIN activities a ON a.id=s.record_id
        ORDER BY a.date, s.zone""").fetchall()
    with open(sort_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["record_id","date","zone","time_window","aircraft_types","total_sorties","crossed_median","has_uav"])
        for r in rows:
            w.writerow(list(r))
    print(f"  Sorties:    {sort_path} ({len(rows)} rows)")

    c.close()
