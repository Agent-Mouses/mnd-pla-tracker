#!/usr/bin/env python3
"""Download missing File/ media for 35 early posts (77xxx series).

Extracts ../File/XXXXX links from saved HTML, downloads from
https://www.mnd.gov.tw/File/XXXXX, saves with content-disposition filename.

Refs: https://github.com/Agent-Mouses/mnd-pla-tracker/issues/1
"""
import os, re, subprocess, time, urllib.parse

DATA = os.path.join(os.path.dirname(__file__), "mnd_pla_data")
BASE_URL = "https://www.mnd.gov.tw/File/"

MISSING_IDS = [
    77588, 77592, 77599, 77614, 77617, 77623, 77639, 77649, 77656, 77658,
    77661, 77679, 77680, 77681, 77687, 77691, 77692, 77701, 77710, 77714,
    77754, 77760, 77762, 77776, 77819, 77826, 77829, 77845, 77868, 77871,
    77878, 77880, 77883, 77887, 77889,
]

def extract_file_ids(html_path):
    """Extract unique File/ IDs from HTML."""
    with open(html_path) as f:
        return sorted(set(re.findall(r'href="\.\./File/(\d+)"', f.read())))

def download_file(file_id, dest_dir):
    """Download a single File/ resource, return saved filename or None."""
    url = BASE_URL + file_id
    tmp = os.path.join(dest_dir, f"_tmp_{file_id}")
    r = subprocess.run(
        ["curl", "-sS", "-D", "-", "-o", tmp, url],
        capture_output=True, text=True, timeout=60,
    )
    headers = r.stdout
    if not os.path.exists(tmp) or os.path.getsize(tmp) == 0:
        return None

    # Parse filename from content-disposition
    m = re.search(r"filename\*=UTF-8''(.+?)[\r\n]", headers)
    if m:
        fname = urllib.parse.unquote(m.group(1).strip())
    else:
        m = re.search(r'filename="(.+?)"', headers)
        fname = m.group(1) if m else f"{file_id}.bin"

    # Sanitize
    fname = re.sub(r'[/\\:*?"<>|]', '_', fname)
    dest = os.path.join(dest_dir, fname)
    os.rename(tmp, dest)
    return fname

def main():
    ok = fail = 0
    for post_id in MISSING_IDS:
        html = os.path.join(DATA, "html", f"{post_id}.html")
        dest = os.path.join(DATA, "target_media", str(post_id))
        os.makedirs(dest, exist_ok=True)

        file_ids = extract_file_ids(html)
        print(f"{post_id}: {len(file_ids)} files", end="", flush=True)

        for i, fid in enumerate(file_ids, 1):
            fname = download_file(fid, dest)
            if fname:
                print(f" ✓{i}", end="", flush=True)
                ok += 1
            else:
                print(f" ✗{i}", end="", flush=True)
                fail += 1
            time.sleep(0.5)
        print()

    print(f"\nDone: {ok} downloaded, {fail} failed")
    # Verify
    still_empty = [p for p in MISSING_IDS if not os.listdir(os.path.join(DATA, "target_media", str(p)))]
    if still_empty:
        print(f"Still empty: {still_empty}")
    else:
        print("All 35 directories now have files ✓")

if __name__ == "__main__":
    main()
