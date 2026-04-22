#!/usr/bin/env python3
"""MND PLA Activity Tracker — unified database from ALL text + OCR sources."""
import argparse, os
from loader import load_records, find_image
from text_parser import parse_record
from ocr import ocr_image
from parser import parse as parse_ocr
from db import upsert_activity, enrich_ocr, query, stats, export_csv

def cmd_build(args):
    """Full pipeline: parse all text → OCR images → unified DB → export CSV."""
    records = load_records()

    # Step 1: Parse ALL records from text
    print(f"[1/3] Parsing {len(records)} records from text...")
    for rec in records:
        parsed = parse_record(rec)
        upsert_activity(rec, parsed)
    print(f"  ✓ {len(records)} records parsed and stored")

    # Step 2: OCR-enrich records with images
    pairs = [(rec, find_image(rec)) for rec in records]
    pairs = [(rec, img) for rec, img in pairs if img]
    print(f"\n[2/3] OCR-enriching {len(pairs)} records with images...")
    if args.limit:
        pairs = pairs[:args.limit]

    ok = err = empty = 0
    for rec, img_path in pairs:
        rid = rec["id"]
        try:
            text = ocr_image(img_path)
            parsed = parse_ocr(text)
            enrich_ocr(rid, img_path, parsed)
            if parsed.total_sorties > 0:
                uav = " [UAV]" if parsed.has_uav else ""
                print(f"  ✓ {rid} | {parsed.date_start} | {len(parsed.zones)} zones | {parsed.total_sorties} sorties{uav}")
                ok += 1
            else:
                print(f"  · {rid} | no zones parsed")
                empty += 1
        except Exception as e:
            print(f"  ✗ {rid}: {e}")
            err += 1
    print(f"  Done: {ok} enriched, {empty} empty, {err} errors")

    # Step 3: Export
    out = args.output or "output/mnd_pla"
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    print(f"\n[3/3] Exporting CSV...")
    export_csv(out)

    # Summary
    print("\n" + "="*50)
    s = stats()
    print(f"  Total records:    {s['total_records']}")
    print(f"  With date:        {s['with_date']}")
    print(f"  With image/OCR:   {s['with_image']}")
    print(f"  With OCR zones:   {s['with_ocr_zones']}")
    print(f"  Has UAV:          {s['has_uav']}")
    print(f"  Date range:       {s['date_range']}")
    print(f"  By source:        {s['by_source']}")

def cmd_query(args):
    rows = query(uav_only=args.uav, date_from=getattr(args, "from"),
                 date_to=args.to, aircraft_type=args.type, crossed_only=args.crossed)
    if not rows:
        print("No results."); return
    print(f"{'ID':<7} {'Date':<12} {'Aircraft':>4} {'Types':<30} {'UAV':>4} {'Cross':>5} {'Ships':>5} {'Areas':<20} {'Src':<10}")
    print("-" * 105)
    for r in rows:
        print(f"{r['id']:<7} {r['date'] or '?'::<12} {r['total_aircraft'] or 0:>4} "
              f"{r['aircraft_types'] or ''::<30} {'✓' if r['has_uav'] else '':>4} "
              f"{r['crossed_median'] or 0:>5} {r['ships'] or 0:>5} "
              f"{r['areas'] or ''::<20} {r['source']:<10}")

def cmd_stats(args):
    s = stats()
    for k, v in s.items():
        print(f"  {k}: {v}")

def cmd_export(args):
    out = args.output or "output/mnd_pla"
    export_csv(out)

def main():
    p = argparse.ArgumentParser(prog="mnd-tracker", description="MND PLA Activity Tracker")
    sub = p.add_subparsers(dest="cmd")

    bp = sub.add_parser("build", help="Full pipeline: text parse + OCR → DB + CSV")
    bp.add_argument("--limit", type=int, help="OCR only first N images")
    bp.add_argument("--output", "-o", default="output/mnd_pla")

    qp = sub.add_parser("query", help="Query the database")
    qp.add_argument("--uav", action="store_true", help="UAV entries only")
    qp.add_argument("--from", dest="from", help="Start date YYYY-MM-DD")
    qp.add_argument("--to", help="End date YYYY-MM-DD")
    qp.add_argument("--type", help="Aircraft type filter (fighter/UAV/bomber...)")
    qp.add_argument("--crossed", action="store_true", help="Median-line crossings only")

    sub.add_parser("stats", help="Database statistics")

    xp = sub.add_parser("export", help="Export DB to CSV")
    xp.add_argument("--output", "-o", default="output/mnd_pla")

    args = p.parse_args()
    cmds = {"build": cmd_build, "query": cmd_query, "stats": cmd_stats, "export": cmd_export}
    if args.cmd in cmds:
        cmds[args.cmd](args)
    else:
        p.print_help()

if __name__ == "__main__":
    main()
