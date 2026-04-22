import pytesseract
from PIL import Image, ImageFilter, ImageOps

def ocr_image(path: str) -> str:
    """OCR the table region of a MND PLA activity map.
    
    The map is ~720x1040. The table with zone data sits in the top-left quadrant.
    We upscale 3x and threshold to remove the watermark for clean OCR.
    """
    img = Image.open(path)
    w, h = img.size

    # Crop: full width, top 50% (captures title + table generously)
    crop = img.crop((0, 0, w, int(h * 0.50)))

    # Upscale 3x for better small-text recognition
    cw, ch = crop.size
    crop = crop.resize((cw * 3, ch * 3), Image.LANCZOS)

    # Convert to grayscale, threshold to remove watermark (light gray numbers)
    gray = crop.convert("L")
    # Threshold: anything lighter than 180 becomes white (kills watermark)
    bw = gray.point(lambda x: 0 if x < 180 else 255)

    text = pytesseract.image_to_string(bw, lang="chi_tra+eng", config="--psm 4")
    return text
