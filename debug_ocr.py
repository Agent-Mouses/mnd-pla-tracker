#!/usr/bin/env python3
"""Debug: test OCR on one image, print raw output."""
import sys, glob, os
from ocr import ocr_image

base = os.path.join(os.path.dirname(__file__), "mnd_pla_data", "target_media")

if len(sys.argv) > 1:
    img = sys.argv[1]
else:
    # Use latest record with image
    for d in sorted(os.listdir(base), reverse=True):
        imgs = glob.glob(os.path.join(base, d, "*.jpg*"))
        if imgs:
            img = imgs[0]
            break

print(f"Image: {img}")
text = ocr_image(img)
print("--- RAW OCR ---")
print(text)
print("--- END ---")
print(f"Length: {len(text)}")

# Quick check for key markers
for kw in ["①", "②", "③", "年", "架", "sortie", "UAV", "無人機", "戰機", "fighter"]:
    if kw in text or kw.lower() in text.lower():
        print(f"  ✓ Found: {kw}")
    else:
        print(f"  ✗ Missing: {kw}")
