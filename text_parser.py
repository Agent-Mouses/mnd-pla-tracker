"""Parse structured activity data from JSONL text fields.

Extracts: date, aircraft types, total count, UAV flag, crossed median,
ships, areas — from all available text sources per record.
"""
import re
from datetime import datetime

AIRCRAFT_TYPES = {
    "J-10": "fighter", "J-11": "fighter", "J-16": "fighter", "J-7": "fighter",
    "Su-30": "fighter", "Su-35": "fighter", "JH-7": "fighter",
    "H-6": "bomber",
    "UAV": "UAV", "UAS": "UAV", "TB-001": "UAV", "BZK": "UAV", "WZ-7": "UAV",
    "無人機": "UAV", "CH-4": "UAV", "CH-5": "UAV",
    "Y-8": "ISR", "Y-9": "ISR", "KJ-": "AEW", "KJ500": "AEW", "KJ200": "AEW",
    "RECCE": "ISR", "ASW": "ASW", "EW": "EW", "ELINT": "ELINT",
    "Y-20": "transport", "IL-76": "transport",
    "helicopter": "helicopter", "tanker": "tanker",
}

AREA_MAP = [
    (r"southwest(?:ern)?", "SW_ADIZ"), (r"西南空域|西南", "SW_ADIZ"),
    (r"southeast(?:ern)?", "SE_ADIZ"), (r"東南部空域|東南", "SE_ADIZ"),
    (r"north(?:ern)?", "N_ADIZ"), (r"北部空域|北部", "N_ADIZ"),
    (r"east(?:ern)?", "E_ADIZ"), (r"東部空域|東部", "E_ADIZ"),
    (r"median\s*line", "median_line"), (r"逾越中線|中線", "median_line"),
    (r"Taiwan\s*Strait", "strait"), (r"臺海|台海", "strait"),
]

def _classify_aircraft(text):
    types = []
    for key, val in AIRCRAFT_TYPES.items():
        if key.lower() in text.lower() or key in text:
            if val not in types:
                types.append(val)
    return types

def _extract_areas(text):
    areas = []
    for pattern, val in AREA_MAP:
        if re.search(pattern, text, re.I) and val not in areas:
            areas.append(val)
    return areas

def _parse_date(rec):
    """Extract date from any available field."""
    ft = rec.get("full_text", "")
    
    # Best: "PLA Activities YYYY.MM.DD" in full_text
    m = re.search(r"PLA Activities\s+(\d{4})\.(\d{1,2})\.(\d{1,2})", ft)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    
    # older_page_date: "Nov. 01, 2020（Sunday morning）"
    opd = rec.get("older_page_date") or ""
    m = re.search(r"(\w{3,9})\.?\s*(\d{1,2}),?\s*(\d{4})", opd)
    if m:
        try:
            return datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)}", "%b %d %Y").strftime("%Y-%m-%d")
        except ValueError:
            pass
    
    # ROC date in older_page_date
    m = re.search(r"(\d{2,3})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日", opd)
    if m:
        return f"{int(m.group(1))+1911}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    
    # ROC date in full_text (only 2-3 digit years to avoid matching other numbers)
    m = re.search(r"(?:中華民國|資料時間[：:]\s*)(\d{2,3})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日", ft)
    if m:
        return f"{int(m.group(1))+1911}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    
    return ""

def _get_activity_section(ft):
    """Extract the relevant activity section from full_text."""
    # New format: "PLA activities: ..."
    m = re.search(r"PLA activities[：:]\s*(.*?)(?:Keywords|Share|Return to list)", ft, re.S | re.I)
    if m:
        return m.group(1).strip()
    # Old format: "Aircraft Type: ... Activity Area: ... Reactions: ..."
    m = re.search(r"Aircraft Type[：:]\s*(.*?)(?:Keywords|Share|Return to list)", ft, re.S)
    if m:
        return m.group(1).strip()
    # Chinese format: 偵獲共機...
    m = re.search(r"(偵獲.*?)(?:Keywords|Share|國軍運用)", ft, re.S)
    if m:
        return m.group(1).strip()
    return ""

def _extract_total_aircraft(text):
    """Extract total aircraft count from activity text."""
    m = re.search(r"(\d+)\s*sorties?\s*of\s*PLA\s*aircraft", text, re.I)
    if m: return int(m.group(1))
    m = re.search(r"(\d+)\s*PLA\s*aircraft", text, re.I)
    if m: return int(m.group(1))
    # Chinese: 偵獲共機N架次 or 共機N架
    m = re.search(r"(?:偵獲)?共機\s*(\d+)\s*架", text)
    if m: return int(m.group(1))
    if "未偵獲共機" in text: return 0
    return 0

def _extract_crossed(text):
    """Extract median-line crossing count."""
    m = re.search(r"(\d+)\s*out\s+of\s+\d+\s+sorties?\s+crossed", text, re.I)
    if m: return int(m.group(1))
    m = re.search(r"(\d+)\s*of\s+(?:the\s+)?(?:detected\s+)?aircraft\s+(?:had\s+)?crossed", text, re.I)
    if m: return int(m.group(1))
    m = re.search(r"(\d+)\s*(?:sorties?\s+)?crossed\s+the\s+median", text, re.I)
    if m:
        return int(m.group(1))
    # Chinese
    m = re.search(r"(\d+)\s*架次?\s*逾越中線", text)
    if m:
        return int(m.group(1))
    return 0

def _extract_ships(text):
    total = 0
    m = re.search(r"(\d+)\s*PLAN\s*(?:ships?|vessels?)", text, re.I)
    if m: total += int(m.group(1))
    m = re.search(r"(\d+)\s*official\s*ships?", text, re.I)
    if m: total += int(m.group(1))
    # Chinese: 共艦N艘 + 公務船N艘
    m = re.search(r"共艦\s*(\d+)\s*艘", text)
    if m: total += int(m.group(1))
    m = re.search(r"公務船\s*(\d+)\s*艘", text)
    if m: total += int(m.group(1))
    return total

def _extract_entered_adiz(text):
    """Extract count that entered ADIZ (different from crossed median)."""
    m = re.search(r"(\d+)\s*(?:of\s+(?:the\s+)?(?:\d+\s+)?(?:detected\s+)?(?:aircraft|sorties?)\s+(?:had\s+)?)?entered\s+Taiwan", text, re.I)
    if m:
        return int(m.group(1))
    m = re.search(r"(\d+)\s*out\s+of\s+\d+\s+sorties?\s+crossed.*?entered", text, re.I)
    if m:
        return int(m.group(1))
    return 0

def parse_record(rec):
    """Parse a JSONL record into unified activity fields."""
    rid = rec["id"]
    at_field = rec.get("aircraft_type") or ""
    pla_text = rec.get("pla_activities_text") or ""
    ft = rec.get("full_text") or ""
    activity_area = rec.get("activity_area") or ""

    # --- DATE ---
    date = _parse_date(rec)

    # --- ACTIVITY SECTION from full_text ---
    ft_section = _get_activity_section(ft)

    # Combine all text for extraction
    all_text = f"{at_field} {pla_text} {ft_section} {activity_area}"

    # --- AIRCRAFT TYPES ---
    aircraft_types = _classify_aircraft(all_text)
    has_uav = "UAV" in aircraft_types

    # --- TOTAL AIRCRAFT ---
    total_aircraft = rec.get("total_aircraft") or 0
    if not total_aircraft:
        total_aircraft = _extract_total_aircraft(all_text)

    # --- CROSSED MEDIAN ---
    crossed_median = _extract_crossed(all_text)

    # --- ENTERED ADIZ ---
    entered_adiz = _extract_entered_adiz(all_text)

    # --- SHIPS ---
    ships = _extract_ships(all_text)

    # --- AREAS ---
    # Also check page_title for area info (e.g. "southwestern ADIZ")
    area_text = f"{all_text} {rec.get('page_title', '')}"
    areas = _extract_areas(area_text)

    # --- SOURCE ---
    has_media = (rec.get("target_media_count") or 0) > 0
    if has_media:
        source = "image"
    elif at_field:
        source = "aircraft_type"
    elif pla_text:
        source = "pla_text"
    else:
        source = "full_text"

    return {
        "id": rid,
        "date": date,
        "total_aircraft": total_aircraft,
        "aircraft_types": aircraft_types,
        "has_uav": has_uav,
        "crossed_median": crossed_median,
        "entered_adiz": entered_adiz,
        "ships": ships,
        "areas": areas,
        "source": source,
    }
