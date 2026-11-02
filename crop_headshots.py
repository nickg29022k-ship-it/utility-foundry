"""
Extracts headshots from the PPTX using PowerPoint's own crop data (fillRect).
No face detection needed — this is the exact crop PPT was already showing.
"""
import os
import io
from pptx import Presentation
from pptx.oxml.ns import qn
from PIL import Image, ImageDraw, ImageFont

PPTX_PATH  = "WORKING VERSION.pptx"
OUTPUT_DIR = "headshots"
NAME_FONT_SIZE = 28
BORDER     = 18
BOTTOM_PAD = 90

os.makedirs(OUTPUT_DIR, exist_ok=True)


def get_fill_rect(blip_fill_elem):
    """Read fillRect l/t/r/b in 1/100000 units (may be absent = no crop)."""
    stretch = blip_fill_elem.find(qn('a:stretch'))
    if stretch is None:
        return (0, 0, 0, 0)
    fr = stretch.find(qn('a:fillRect'))
    if fr is None:
        return (0, 0, 0, 0)
    l = int(fr.get('l', 0))
    t = int(fr.get('t', 0))
    r = int(fr.get('r', 0))
    b = int(fr.get('b', 0))
    return (l, t, r, b)


def apply_ppt_crop(img_bytes, l, t, r, b):
    """
    Apply PowerPoint fillRect crop to the image.
    l/t/r/b are in 1/100000 units (negative = image extends beyond shape edge).
    """
    img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    W, H = img.size

    # Convert to fractions
    lf = l / 100000.0
    tf = t / 100000.0
    rf = r / 100000.0
    bf = b / 100000.0

    # Fill rect dimensions relative to shape (1.0 = shape size)
    # fill_rect spans from lf to (1 - rf) horizontally, tf to (1 - bf) vertically
    fill_w = 1.0 - lf - rf   # total width of fill rect in shape units
    fill_h = 1.0 - tf - bf

    # Fraction of image that maps to the shape's visible area
    crop_x1 = (-lf) / (fill_w if fill_w != 0 else 1)
    crop_y1 = (-tf) / (fill_h if fill_h != 0 else 1)
    crop_x2 = crop_x1 + 1.0 / (fill_w if fill_w != 0 else 1)
    crop_y2 = crop_y1 + 1.0 / (fill_h if fill_h != 0 else 1)

    # Clamp to [0, 1]
    crop_x1 = max(0.0, min(1.0, crop_x1))
    crop_y1 = max(0.0, min(1.0, crop_y1))
    crop_x2 = max(0.0, min(1.0, crop_x2))
    crop_y2 = max(0.0, min(1.0, crop_y2))

    px1 = int(crop_x1 * W)
    py1 = int(crop_y1 * H)
    px2 = int(crop_x2 * W)
    py2 = int(crop_y2 * H)

    if px2 <= px1 or py2 <= py1:
        return img  # no crop / invalid
    return img.crop((px1, py1, px2, py2))


def make_polaroid(photo_img, name):
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", NAME_FONT_SIZE)
    except Exception:
        font = ImageFont.load_default()

    card_w = photo_img.width  + BORDER * 2
    card_h = photo_img.height + BORDER + BOTTOM_PAD
    card = Image.new("RGB", (card_w, card_h), (255, 255, 255))
    card.paste(photo_img, (BORDER, BORDER))

    if name:
        draw = ImageDraw.Draw(card)
        lines = [l.strip() for l in name.split("\n") if l.strip()]
        line_heights = [draw.textbbox((0, 0), ln, font=font)[3] for ln in lines]
        total_h = sum(line_heights) + (len(lines) - 1) * 5
        y = photo_img.height + BORDER + (BOTTOM_PAD - total_h) // 2
        for i, ln in enumerate(lines):
            bbox = draw.textbbox((0, 0), ln, font=font)
            x = (card_w - (bbox[2] - bbox[0])) // 2
            draw.text((x, y), ln, fill=(20, 20, 20), font=font)
            y += line_heights[i] + 5
    return card


def get_text(shape):
    if shape.has_text_frame:
        return shape.text_frame.text.strip()
    return ""


def collect_all_texts(shapes, out, off_x=0, off_y=0):
    for shape in shapes:
        ax = (shape.left or 0) + off_x
        ay = (shape.top  or 0) + off_y
        if shape.shape_type == 6:
            collect_all_texts(shape.shapes, out, ax, ay)
        elif shape.has_text_frame:
            t = get_text(shape)
            if t and len(t) < 60:
                out.append((t, ax, ay, ax + (shape.width or 0)))


def find_nearest_text(photo_left, photo_right, photo_bottom,
                      all_texts, exclude_names, max_gap=2000000):
    best_name = ""
    best_score = (float("inf"), float("inf"))
    p_cx = (photo_left + photo_right) / 2
    for (text, tl, tt, tr) in all_texts:
        if text in exclude_names:
            continue
        gap = tt - photo_bottom
        if 0 <= gap <= max_gap:
            if min(photo_right, tr) > max(photo_left, tl):
                t_cx = (tl + tr) / 2
                score = (gap, abs(p_cx - t_cx))
                if score < best_score:
                    best_score = score
                    best_name = text
    return best_name


def extract_images_from_group(group_shape, slide):
    results = []
    for s in group_shape.shapes:
        if s.shape_type == 6:
            results.extend(extract_images_from_group(s, slide))
        else:
            blip_fill = s._element.find('.//' + qn('a:blipFill'))
            if blip_fill is not None:
                blip = blip_fill.find(qn('a:blip'))
                if blip is not None:
                    r_embed = blip.get(qn('r:embed'))
                    if r_embed:
                        try:
                            img_bytes = slide.part.related_part(r_embed).blob
                            crop = get_fill_rect(blip_fill)
                            results.append((img_bytes, crop))
                        except Exception:
                            pass
    return results


def collect_pairs(shapes, slide, all_texts, matched_names, pairs):
    for shape in shapes:
        if shape.shape_type == 6:
            sub = list(shape.shapes)

            # Collect (local_left, img_bytes, crop) and (local_left, name)
            # then sort by horizontal position before pairing — fixes XML order mismatches
            photo_entries = []   # (local_left, img_bytes, crop)
            text_entries  = []   # (local_left, name)

            for s in sub:
                local_left = s.left or 0

                if s.shape_type == 6:
                    imgs = extract_images_from_group(s, slide)
                    for img_bytes, crop in imgs:
                        photo_entries.append((local_left, img_bytes, crop))
                    if not imgs:
                        collect_pairs([s], slide, all_texts, matched_names, pairs)

                elif s.shape_type == 5:
                    blip_fill = s._element.find('.//' + qn('a:blipFill'))
                    if blip_fill is not None:
                        blip = blip_fill.find(qn('a:blip'))
                        if blip is not None:
                            r_embed = blip.get(qn('r:embed'))
                            if r_embed:
                                try:
                                    img_bytes = slide.part.related_part(r_embed).blob
                                    crop = get_fill_rect(blip_fill)
                                    photo_entries.append((local_left, img_bytes, crop))
                                except Exception:
                                    pass

                elif s.has_text_frame:
                    t = get_text(s)
                    if t and len(t) < 60:
                        text_entries.append((local_left, t))

            photo_entries.sort(key=lambda x: x[0])
            text_entries.sort(key=lambda x: x[0])

            # Match each photo to the nearest unused text by horizontal position
            used_text = set()
            for p_left, img_bytes, crop in photo_entries:
                best_idx  = None
                best_dist = float("inf")
                for j, (t_left, t_name) in enumerate(text_entries):
                    if j in used_text:
                        continue
                    dist = abs(p_left - t_left)
                    if dist < best_dist:
                        best_dist = dist
                        best_idx  = j

                name = ""
                if best_idx is not None and best_dist < 4000000:  # ~4.4 inch max gap
                    name = text_entries[best_idx][1]
                    used_text.add(best_idx)

                if name:
                    matched_names.add(name)
                pairs.append((img_bytes, crop, name, shape.left or 0, shape.top or 0))

        elif shape.shape_type == 5:
            blip_fill = shape._element.find('.//' + qn('a:blipFill'))
            if blip_fill is not None:
                blip = blip_fill.find(qn('a:blip'))
                if blip is not None:
                    r_embed = blip.get(qn('r:embed'))
                    if r_embed:
                        try:
                            img_bytes = slide.part.related_part(r_embed).blob
                            crop = get_fill_rect(blip_fill)
                            sl = shape.left or 0
                            sr = sl + (shape.width or 0)
                            sb = (shape.top or 0) + (shape.height or 0)
                            name = find_nearest_text(sl, sr, sb, all_texts, matched_names)
                            if name:
                                matched_names.add(name)
                            pairs.append((img_bytes, crop, name, sl, shape.top or 0))
                        except Exception:
                            pass


prs = Presentation(PPTX_PATH)
total = 0
unnamed = 0

for slide_num, slide in enumerate(prs.slides):
    all_texts = []
    collect_all_texts(slide.shapes, all_texts)
    matched_names = set()
    pairs = []
    collect_pairs(slide.shapes, slide, all_texts, matched_names, pairs)

    print(f"Slide {slide_num + 1}: {len(pairs)} photos")

    for img_bytes, (l, t, r, b), name, *_ in pairs:
        cropped = apply_ppt_crop(img_bytes, l, t, r, b)
        card = make_polaroid(cropped, name)

        if name:
            safe = name.replace("\n", " ").replace("/", "-").strip()
            out_path = os.path.join(OUTPUT_DIR, f"{safe}.jpg")
        else:
            unnamed += 1
            out_path = os.path.join(OUTPUT_DIR, f"slide{slide_num+1}_unnamed{unnamed}.jpg")

        card.save(out_path, "JPEG", quality=95)
        total += 1
        print(f"  -> {os.path.basename(out_path)}")

print(f"\nDone! {total} headshots saved to '{OUTPUT_DIR}/'")
if unnamed:
    print(f"  ({unnamed} need manual renaming)")
