import json, os, glob

DATA_DIR = os.path.join(os.path.dirname(__file__), "mnd_pla_data")

def load_records() -> list[dict]:
    """Load all records from JSONL, return list of dicts."""
    path = os.path.join(DATA_DIR, "records.jsonl")
    records = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records

def find_image(record: dict) -> str | None:
    """Find the map image for a record in target_media/<id>/."""
    rid = str(record["id"])
    media_dir = os.path.join(DATA_DIR, "target_media", rid)
    if not os.path.isdir(media_dir):
        return None
    for fname in os.listdir(media_dir):
        if fname.lower().endswith((".jpg", ".jpeg", ".png", ".tif", ".bmp", ".webp")):
            return os.path.join(media_dir, fname)
    return None

def records_with_images() -> list[tuple[dict, str]]:
    """Return (record, image_path) pairs for all records that have images."""
    out = []
    for rec in load_records():
        img = find_image(rec)
        if img:
            out.append((rec, img))
    return out
