import os
import io
from pptx import Presentation
from pptx.oxml.ns import qn
from PIL import Image, ImageDraw, ImageFont

PPTX_PATH = "WORKING VERSION.pptx"
OUTPUT_DIR = "extracted_pptx_photos"
NAME_FONT_SIZE = 28
BORDER = 18
BOTTOM_PAD = 90

os.makedirs(OUTPUT_DIR, exist_ok=True)


def get_image_from_blip(shape, slide):
    blip = shape._element.find('.//' + qn('a:blip'))
    if blip is None:
        return None
    r_embed = blip.get(qn('r:embed'))
    if not r_embed:
        return None
    try:
        return slide.part.related_part(r_embed).blob
    except (KeyError, Exception):
        return None


def get_text(shape):
    if shape.has_text_frame:
        return shape.text_frame.text.strip()
    return ""


def extract_images_from_group(group_shape, slide):
    results = []
    for s in group_shape.shapes:
        if s.shape_type == 6:
            results.extend(extract_images_from_group(s, slide))
        else:
            img = get_image_from_blip(s, slide)
            if img:
                results.append(img)
    return results


def collect_all_texts_recursive(shapes, out, off_x=0, off_y=0):
    """Collect (text, abs_left, abs_top, abs_right) for all text boxes recursively."""
    for shape in shapes:
        ax = (shape.left or 0) + off_x
        ay = (shape.top  or 0) + off_y
        if shape.shape_type == 6:
            collect_all_texts_recursive(shape.shapes, out, ax, ay)
        elif shape.has_text_frame:
            t = shape.text_frame.text.strip()
            if t and len(t) < 60:
                out.append((t, ax, ay, ax + (shape.width or 0)))


def find_nearest_text(photo_left, photo_right, photo_bottom,
                      all_texts, exclude_names, max_gap=2000000):
    """Find best unused text: closest below and horizontally overlapping."""
    best_name = ""
    best_score = (float("inf"), float("inf"))
    p_cx = (photo_left + photo_right) / 2
    for (text, tl, tt, tr) in all_texts:
        if text in exclude_names:
            continue
        gap = tt - photo_bottom
        if 0 <= gap <= max_gap:
            overlap = min(photo_right, tr) - max(photo_left, tl)
            if overlap > 0:
                t_cx = (tl + tr) / 2
                score = (gap, abs(p_cx - t_cx))
                if score < best_score:
                    best_score = score
                    best_name = text
    return best_name


def collect_pairs(shapes, slide, all_texts, matched_names, pairs):
    for shape in shapes:
        if shape.shape_type == 6:
            sub = list(shape.shapes)
            group_images = []
            group_names = []

            for s in sub:
                if s.shape_type == 6:
                    imgs = extract_images_from_group(s, slide)
                    group_images.extend(imgs)
                    if not imgs:
                        collect_pairs([s], slide, all_texts, matched_names, pairs)
                elif s.shape_type == 5:
                    img = get_image_from_blip(s, slide)
                    if img:
                        group_images.append(img)
                elif s.has_text_frame:
                    t = get_text(s)
                    if t and len(t) < 60:
                        group_names.append(t)

            for i, img in enumerate(group_images):
                name = group_names[i] if i < len(group_names) else ""
                if name:
                    matched_names.add(name)
                pairs.append((img, name, shape.left or 0, shape.top or 0))

        elif shape.shape_type == 5:
            img = get_image_from_blip(shape, slide)
            if img:
                sl = shape.left or 0
                st = shape.top or 0
                sr = sl + (shape.width or 0)
                sb = st + (shape.height or 0)
                name = find_nearest_text(sl, sr, sb, all_texts, matched_names)
                if name:
                    matched_names.add(name)
                pairs.append((img, name, sl, st))


def make_polaroid(image_bytes, name):
    photo = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", NAME_FONT_SIZE)
    except Exception:
        font = ImageFont.load_default()

    card_w = photo.width + BORDER * 2
    card_h = photo.height + BORDER + BOTTOM_PAD
    card = Image.new("RGB", (card_w, card_h), (255, 255, 255))
    card.paste(photo, (BORDER, BORDER))

    if name:
        draw = ImageDraw.Draw(card)
        lines = [l.strip() for l in name.split("\n") if l.strip()]
        line_heights = [draw.textbbox((0, 0), l, font=font)[3] for l in lines]
        total_h = sum(line_heights) + (len(lines) - 1) * 5
        y = photo.height + BORDER + (BOTTOM_PAD - total_h) // 2
        for i, line in enumerate(lines):
            bbox = draw.textbbox((0, 0), line, font=font)
            x = (card_w - (bbox[2] - bbox[0])) // 2
            draw.text((x, y), line, fill=(20, 20, 20), font=font)
            y += line_heights[i] + 5
    return card


prs = Presentation(PPTX_PATH)
total = 0
unnamed = 0

for slide_num, slide in enumerate(prs.slides):
    all_texts = []
    collect_all_texts_recursive(slide.shapes, all_texts)

    matched_names = set()
    pairs = []
    collect_pairs(slide.shapes, slide, all_texts, matched_names, pairs)

    print(f"Slide {slide_num + 1}: {len(pairs)} photos found")

    for img_bytes, name, *_ in pairs:
        if name:
            safe = name.replace("\n", " ").replace("/", "-").strip()
            out_path = os.path.join(OUTPUT_DIR, f"{safe}.jpg")
        else:
            unnamed += 1
            out_path = os.path.join(OUTPUT_DIR, f"slide{slide_num+1}_unnamed{unnamed}.jpg")

        card = make_polaroid(img_bytes, name)
        card.save(out_path, "JPEG", quality=95)
        total += 1
        print(f"  -> {os.path.basename(out_path)}")

print(f"\nDone! {total} polaroids saved to '{OUTPUT_DIR}/'")
if unnamed:
    print(f"  ({unnamed} had no name matched — rename these manually)")
