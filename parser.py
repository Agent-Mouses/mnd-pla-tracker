import re
from dataclasses import dataclass, field

@dataclass
class ZoneEntry:
    zone: str = ""
    time_window: str = ""
    aircraft_types: list = field(default_factory=list)
    total_sorties: int = 0
    crossed_median: int = 0
    has_uav: bool = False
    raw_block: str = ""

@dataclass
class ParsedMap:
    date_start: str = ""
    date_end: str = ""
    zones: list = field(default_factory=list)
    has_uav: bool = False
    total_sorties: int = 0
    raw_text: str = ""

TYPE_MAP = [
    ("無人機", "UAV"), ("UAV", "UAV"),
    ("主戰機", "fighter"), ("輔戰機", "fighter"), ("戰機", "fighter"), ("fighter", "fighter"),
    ("轟炸機", "bomber"), ("bomber", "bomber"),
    ("預警機", "AEW"), ("AEW", "AEW"),
    ("電偵機", "ELINT"), ("電戰機", "EW"),
    ("運輸機", "transport"), ("transport", "transport"),
    ("直升機", "helicopter"), ("helicopter", "helicopter"),
    ("反潛機", "ASW"), ("ASW", "ASW"),
    ("空中加油", "tanker"), ("tanker", "tanker"),
    ("support", "support"),
]

def _roc_to_iso(y, m, d):
    return f"{y + 1911}-{m:02d}-{d:02d}"

def _parse_date(text):
    m = re.search(r"(\d{2,3})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日.*?至\s*(\d{2,3})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日", text)
    if m:
        return (_roc_to_iso(int(m.group(1)), int(m.group(2)), int(m.group(3))),
                _roc_to_iso(int(m.group(4)), int(m.group(5)), int(m.group(6))))
    m = re.search(r"(\w{3,9})\.?\s*(\d{1,2}),?\s*(\d{4})\s*to\s*\d+,?\s*(\w{3,9})\.?\s*(\d{1,2}),?\s*(\d{4})", text, re.I)
    if m:
        from datetime import datetime
        try:
            ds = datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)}", "%b %d %Y").strftime("%Y-%m-%d")
            de = datetime.strptime(f"{m.group(4)} {m.group(5)} {m.group(6)}", "%b %d %Y").strftime("%Y-%m-%d")
            return ds, de
        except ValueError:
            pass
    return "", ""

def _extract_types(block):
    """Extract aircraft type list from a block."""
    types = []
    # Check both Chinese and English
    for key, val in TYPE_MAP:
        if key in block or key.lower() in block.lower():
            if val not in types:
                types.append(val)
    return types

def _extract_count(block):
    """Extract sortie count — prefer English (N sorties) as it's more reliable from OCR."""
    # English: (4 sorties of ...) or (1 sortie of ...)
    m = re.search(r"\((\d+)\s*sorties?\s*of\s", block, re.I)
    if m:
        return int(m.group(1))
    # Chinese: 計N架次 or N架次 or N架
    m = re.search(r"計\s*(\d+)\s*架", block)
    if m:
        return int(m.group(1))
    m = re.search(r"(\d+)\s*架", block)
    if m:
        return int(m.group(1))
    return 0

def _extract_crossed(block):
    cm = re.search(r"(\d+)\s*架次?\s*逾越中線", block)
    if not cm:
        cm = re.search(r"(\d+)\s*sorties?\s*crossed", block, re.I)
    if not cm:
        cm = re.search(r"(\d+)\s*sortie\s*crossed", block, re.I)
    return int(cm.group(1)) if cm else 0

def _split_zones(text):
    """Split OCR text into zone blocks by time window patterns (HHMM-HHMM).
    
    Zone markers ①②③ are unreliable in OCR, so we split on time windows instead.
    OCR often merges the count digit with the time, e.g. '1005-17004' (1005-1700 + 4架次).
    """
    # Normalize: fix merged time+count like "1005-17004" → "1005-1700"
    # The time pattern is always 4 digits - 4 digits
    # Find all time-window-like patterns
    pattern = r"(\d{4})\s*[-~]\s*(\d{4,})"
    
    blocks = []
    matches = list(re.finditer(pattern, text))
    
    for i, m in enumerate(matches):
        start_time = m.group(1)
        end_raw = m.group(2)
        # If end_time is >4 digits, the extra digits are the sortie count merged in
        end_time = end_raw[:4]
        
        time_window = f"{start_time}-{end_time}"
        
        # Block text: from this match to the next match (or end)
        block_start = m.start()
        block_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        block_text = text[block_start:block_end]
        
        blocks.append((time_window, block_text))
    
    return blocks

def _parse_zones(text):
    zones = []
    blocks = _split_zones(text)
    
    for i, (time_window, block) in enumerate(blocks):
        types = _extract_types(block)
        # Sum all English sortie counts in this block (there may be multiple lines)
        # e.g. "(4 sorties of fighter / UAV)" and "(1 sortie of UAV)" in separate sub-blocks
        # But usually one count per zone block
        total = 0
        for m in re.finditer(r"\((\d+)\s*sorties?\s*of\s", block, re.I):
            total += int(m.group(1))
        if total == 0:
            total = _extract_count(block)
        
        crossed = _extract_crossed(block)
        has_uav = "UAV" in types
        zone_label = f"zone{i+1}"
        
        zones.append(ZoneEntry(
            zone=zone_label, time_window=time_window, aircraft_types=types,
            total_sorties=total, crossed_median=crossed, has_uav=has_uav,
            raw_block=block.strip()
        ))
    return zones

def parse(text):
    ds, de = _parse_date(text)
    zones = _parse_zones(text)
    has_uav = any(z.has_uav for z in zones)
    total = sum(z.total_sorties for z in zones)
    return ParsedMap(date_start=ds, date_end=de, zones=zones,
                     has_uav=has_uav, total_sorties=total, raw_text=text)
