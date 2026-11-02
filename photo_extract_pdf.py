import cv2
import numpy as np
from PIL import Image
import fitz  # PyMuPDF
import os

PDF_PATH = "faculty.pdf"
OUTPUT_DIR = "extracted_photos"
DPI = 300
MIN_WIDTH = 80
MIN_HEIGHT = 80

os.makedirs(OUTPUT_DIR, exist_ok=True)

doc = fitz.open(PDF_PATH)
photo_count = 0

for page_num in range(len(doc)):
    page = doc[page_num]
    pix = page.get_pixmap(dpi=DPI)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    img_np = np.array(img)

    gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
    blurred = cv2.GaussianBlur(gray, (3, 3), 0)
    edges = cv2.Canny(blurred, 30, 100)

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    closed = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel)

    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    boxes = []
    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)
        aspect = w / h if h > 0 else 0
        if w >= MIN_WIDTH and h >= MIN_HEIGHT and 0.4 < aspect < 2.0:
            boxes.append((x, y, w, h))

    # Remove boxes that are mostly contained inside a larger box
    def is_inside(inner, outer, threshold=0.85):
        ix, iy, iw, ih = inner
        ox, oy, ow, oh = outer
        overlap_x = max(0, min(ix+iw, ox+ow) - max(ix, ox))
        overlap_y = max(0, min(iy+ih, oy+oh) - max(iy, oy))
        overlap_area = overlap_x * overlap_y
        inner_area = iw * ih
        return overlap_area / inner_area > threshold if inner_area > 0 else False

    filtered = []
    boxes_sorted = sorted(boxes, key=lambda b: b[2]*b[3], reverse=True)
    for i, box in enumerate(boxes_sorted):
        dominated = any(
            is_inside(box, other) for j, other in enumerate(boxes_sorted) if i != j
        )
        if not dominated:
            filtered.append(box)

    for x, y, w, h in filtered:
        crop = img_np[y:y+h, x:x+w]
        out_path = os.path.join(OUTPUT_DIR, f"page{page_num+1}_photo{photo_count+1}.jpg")
        cv2.imwrite(out_path, cv2.cvtColor(crop, cv2.COLOR_RGB2BGR))
        photo_count += 1

print(f"Done! Extracted {photo_count} photos to '{OUTPUT_DIR}/'")
