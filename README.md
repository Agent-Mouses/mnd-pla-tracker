# MND PLA Activity Tracker

> **AI Agent?** Read **[AI-GUIDE.md](AI-GUIDE.md)** for project orientation and operations.

Extracts zone-level sortie data from Taiwan MND "PLA air activities" map images via OCR, matches to existing scraped records, and builds a queryable SQLite database — with a focus on UAV activity tracking.

## Data Layout

```
mnd_pla_data/
  records.jsonl          # scraped MND records (1399 entries)
  records.csv            # same data, CSV format
  target_media/<id>/     # map images per record (~290 records)
  json/<id>.json         # individual record JSON files
```

## Setup

```bash
pip install -r requirements.txt
# Tesseract with Chinese Traditional:
# macOS: brew install tesseract tesseract-lang
# Ubuntu: apt install tesseract-ocr tesseract-ocr-chi-tra
```

## Usage

```bash
# OCR all images and enrich records in DB
python main.py enrich

# Process only first N records
python main.py enrich --limit 10

# Query the database
python main.py query                    # all zone entries
python main.py query --uav              # UAV entries only
python main.py query --from 2025-01-01 --to 2025-12-31
python main.py query --type bomber
python main.py query --crossed          # median-line crossings

# Database stats
python main.py stats
```

## How It Works

1. `loader.py` — reads `records.jsonl`, finds matching images in `target_media/<id>/`
2. `ocr.py` — crops the table region (top-left 65%×45%) and runs Tesseract (chi_tra+eng)
3. `parser.py` — extracts per-zone data: time window, aircraft types, sortie count, median-line crossings, UAV flag
4. `db.py` — stores in SQLite: `records` table (JSONL metadata + OCR results) + `sorties` table (one row per zone)
5. `main.py` — CLI for enrich/query/stats

## Parsing Details

The MND maps use a table format like:
```
① 1005-1700時 主、輔戰機及無人機計4架次 (4 sorties of fighter / UAV) 1架逾越中線
② 1240-1940時 主、輔戰機計11架次 (11 sorties of fighter / bomber / support aircraft)
③ 0935-1815時 無人機1架 (1 sortie of UAV)
```

The parser handles both Chinese and English text, ROC dates (115年→2026), compound aircraft types, and median-line crossing counts.
