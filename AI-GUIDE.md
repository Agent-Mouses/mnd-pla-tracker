# AI Agent Guide

OCR pipeline that extracts PLA air activity data from Taiwan MND map images into a queryable SQLite database.

## Stack

- **Python 3** with Tesseract OCR
- **SQLite** for data storage
- **Input:** MND map images in `mnd_pla_data/target_media/`

## Key Files

| File | Purpose |
|------|---------|
| `main.py` | CLI entry point |
| `ocr.py` | Image → text extraction |
| `parser.py` | Text → structured data |
| `text_parser.py` | Zone/sortie parsing |
| `db.py` | SQLite operations |
| `loader.py` | Bulk data loading |
| `export_panel.py` | Panel data export |

## Setup

```bash
pip install -r requirements.txt
brew install tesseract    # macOS
```

## Usage

```bash
python main.py            # Process all images
python export_panel.py    # Export panel dataset
```

## Data

- `mnd_pla_data/records.jsonl` — scraped MND records
- `mnd_pla_data/target_media/<id>/` — map images per record
- Raw data is public (from Taiwan MND website)
