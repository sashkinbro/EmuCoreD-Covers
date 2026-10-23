import os
import sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageOps, ImageFilter, ImageFont

CANVAS_SIZE = (1200, 1500)

# Subtle realistic 3D perspective coordinates for vertical Nintendo 3DS box
SPINE_CORNERS = [(130, 155), (235, 120), (235, 1340), (130, 1305)]
FRONT_CORNERS = [(235, 120), (1035, 175), (1035, 1285), (235, 1340)]

def warp(source: Image.Image, corners: list[tuple[int, int]], out_size: tuple[int, int] = CANVAS_SIZE) -> Image.Image:
    width, height = source.size
    original = [(0, 0), (width, 0), (width, height), (0, height)]
    matrix, values = [], []
    for (x, y), (u, v) in zip(corners, original):
        matrix.extend([[x, y, 1, 0, 0, 0, -u*x, -u*y], [0, 0, 0, x, y, 1, -v*x, -v*y]])
        values.extend([u, v])
    coefficients = np.linalg.solve(np.array(matrix, dtype=float), np.array(values, dtype=float))
    return source.transform(out_size, Image.Transform.PERSPECTIVE, coefficients, Image.Resampling.BICUBIC)

def trim_white_scan_strip(im: Image.Image) -> Image.Image:
    """Only trims the solid white scan strip on scanned JP/EU covers. Never crops real art."""
    rgb = im.convert("RGB")
    arr = np.array(rgb)
    h, w, _ = arr.shape

    # Must have solid white right edge
    right_edge = arr[:, -5:]
    if (right_edge.mean() > 240) and ((right_edge > 220).all(axis=2).mean() > 0.85):
        for x in range(w - 1, int(w * 0.5), -1):
            if arr[:, x].mean() < 160:
                cut_x = max(int(w * 0.5), x - 6)
                return rgb.crop((0, 0, cut_x, h))
    return rgb

def create_n3ds_spine(title: str, prod_code: str = "", height: int = 1220, width: int = 105, theme: str = "dark") -> Image.Image:
    is_light = (theme == "light")
    bg = (250, 252, 255, 255) if is_light else (22, 24, 28, 255)
    spine = Image.new("RGBA", (width, height), bg)
    draw = ImageDraw.Draw(spine)

    # Plastic lighting gradient across spine
    for x in range(width):
        factor = 0.88 + 0.12 * (x / width)
        if is_light:
            col = (int(242 * factor), int(246 * factor), int(252 * factor), 255)
        else:
            col = (int(18 * factor), int(20 * factor), int(24 * factor), 255)
        draw.line([(x, 0), (x, height)], fill=col)

    # Spine Molded Latches / Notches
    notch_col = (205, 212, 222, 255) if is_light else (12, 13, 16, 255)
    draw.rectangle([0, 95, 16, 125], fill=notch_col)
    draw.rectangle([0, height - 125, 16, height - 95], fill=notch_col)

    # Top Red Nintendo Badge
    badge_w, badge_h = width - 26, 34
    badge_x, badge_y = 13, 35
    draw.rounded_rectangle([badge_x, badge_y, badge_x + badge_w, badge_y + badge_h], radius=8, fill=(228, 0, 15, 255))
    try:
        font_pill = ImageFont.truetype(r"C:\Windows\Fonts\arialbd.ttf", 16)
        font_3ds = ImageFont.truetype(r"C:\Windows\Fonts\segoeuib.ttf", 20)
    except Exception:
        font_pill = ImageFont.load_default()
        font_3ds = ImageFont.load_default()

    tb = draw.textbbox((0, 0), "Nintendo", font=font_pill)
    tw, th = tb[2] - tb[0], tb[3] - tb[1]
    draw.text((badge_x + (badge_w - tw) // 2, badge_y + (badge_h - th) // 2 - 1), "Nintendo", font=font_pill, fill=(255, 255, 255, 255))

    # "3DS" sub mark
    stb = draw.textbbox((0, 0), "3DS", font=font_3ds)
    stw = stb[2] - stb[0]
    draw.text(((width - stw) // 2, 78), "3DS", font=font_3ds, fill=(228, 0, 15, 255) if is_light else (240, 50, 50, 255))

    # Bottom Product Code
    if prod_code:
        try:
            font_code = ImageFont.truetype(r"C:\Windows\Fonts\segoeui.ttf", 14)
        except Exception:
            font_code = ImageFont.load_default()
        code_s = prod_code.upper()
        cb = draw.textbbox((0, 0), code_s, font=font_code)
        cw, ch = cb[2] - cb[0], cb[3] - cb[1]
        c_cv = Image.new("RGBA", (cw + 4, ch + 4), (0, 0, 0, 0))
        ImageDraw.Draw(c_cv).text((-cb[0] + 2, -cb[1] + 2), code_s, font=font_code, fill=(130, 135, 145, 255) if is_light else (140, 145, 155, 255))
        c_rot = c_cv.rotate(90, expand=True, resample=Image.Resampling.BICUBIC)
        spine.alpha_composite(c_rot, ((width - c_rot.width) // 2, height - c_rot.height - 25))

    # Game Title running along the spine: perfectly centered
    clean_title = (title or "").strip()
    try:
        font_title = ImageFont.truetype(r"C:\Windows\Fonts\segoeuib.ttf", 30)
    except Exception:
        font_title = ImageFont.load_default()

    dummy = Image.new("RGBA", (10, 10))
    tb = ImageDraw.Draw(dummy).textbbox((0, 0), clean_title, font=font_title)
    tw, th = tb[2] - tb[0], tb[3] - tb[1]

    t_cv = Image.new("RGBA", (tw + 8, th + 8), (0, 0, 0, 0))
    tc = (22, 25, 30, 255) if is_light else (245, 248, 252, 255)
    ImageDraw.Draw(t_cv).text((-tb[0] + 4, -tb[1] + 4), clean_title, font=font_title, fill=tc)
    rot_title = t_cv.rotate(90, expand=True, resample=Image.Resampling.BICUBIC)

    max_h = height - 230
    if rot_title.height > max_h:
        rot_title = ImageOps.contain(rot_title, (width - 24, max_h), Image.Resampling.LANCZOS)

    cy = (120 + (height - 90)) // 2
    py = cy - (rot_title.height // 2)
    px = (width - rot_title.width) // 2
    spine.alpha_composite(rot_title, (px, py))

    # Edge bevel lines on spine
    edge_high = (255, 255, 255, 240) if is_light else (85, 90, 100, 200)
    edge_dark = (195, 200, 210, 255) if is_light else (35, 38, 44, 255)
    draw.line([(width - 2, 0), (width - 2, height)], fill=edge_high, width=2)
    draw.line([(2, 0), (2, height)], fill=edge_dark, width=2)

    return spine

def render_n3ds_deluxe_cover(art_img: Image.Image, title: str, theme: str = "dark") -> Image.Image:
    face_w, face_h = 800, 1110
    is_light = (theme == "light")

    bg_color = (248, 250, 254, 255) if is_light else (18, 20, 24, 255)
    face = Image.new("RGBA", (face_w, face_h), bg_color)
    draw = ImageDraw.Draw(face)

    try:
        f_pill = ImageFont.truetype(r"C:\Windows\Fonts\arialbd.ttf", 16)
        f_header = ImageFont.truetype(r"C:\Windows\Fonts\segoeuib.ttf", 24)
        f_sub = ImageFont.truetype(r"C:\Windows\Fonts\segoeui.ttf", 13)
        f_footer = ImageFont.truetype(r"C:\Windows\Fonts\arialbd.ttf", 14)
        f_small = ImageFont.truetype(r"C:\Windows\Fonts\arial.ttf", 12)
    except Exception:
        f_pill = f_header = f_sub = f_footer = f_small = ImageFont.load_default()

    # Clean artwork: strip white scan bar ONLY if present, zero crop on real art!
    clean_art = trim_white_scan_strip(art_img)

    # Sleek Slim Header (height 76)
    header_h = 76
    h_bg = (240, 243, 248, 255) if is_light else (22, 25, 30, 255)
    draw.rectangle([0, 0, face_w, header_h], fill=h_bg)

    draw.rounded_rectangle([25, 18, 125, 52], radius=7, fill=(228, 0, 15, 255))
    draw.text((38, 24), "Nintendo", font=f_pill, fill=(255, 255, 255, 255))

    h_text_color = (20, 24, 30, 255) if is_light else (255, 255, 255, 255)
    draw.text((145, 17), "NINTENDO 3DS", font=f_header, fill=h_text_color)
    draw.text((147, 46), "OFFICIAL SOFTWARE EDITION", font=f_sub, fill=(125, 135, 150, 255) if is_light else (145, 155, 170, 255))

    accent_color = (0, 140, 230, 255) if is_light else (228, 0, 15, 255)
    draw.line([(0, header_h - 2), (face_w, header_h - 2)], fill=accent_color, width=2)

    # Slim Footer (height 54)
    footer_h = 54
    footer_y = face_h - footer_h
    foot_bg = (236, 240, 246, 255) if is_light else (20, 23, 28, 255)
    draw.rectangle([0, footer_y, face_w, face_h], fill=foot_bg)
    draw.line([(0, footer_y), (face_w, footer_y)], fill=(195, 200, 210, 255) if is_light else (35, 38, 45, 255), width=2)

    draw.rounded_rectangle([25, footer_y + 11, 160, footer_y + 43], radius=5, fill=(0, 115, 210, 255))
    draw.text((34, footer_y + 17), "Nintendo Network", font=f_small, fill=(255, 255, 255, 255))
    draw.text((190, footer_y + 18), "Playable in 2D and 3D", font=f_footer, fill=(90, 100, 115, 255) if is_light else (165, 175, 190, 255))

    draw.rounded_rectangle([face_w - 175, footer_y + 11, face_w - 25, footer_y + 43], radius=5, outline=(218, 165, 32, 255), width=2)
    draw.text((face_w - 160, footer_y + 18), "OFFICIAL SEAL", font=f_footer, fill=(218, 165, 32, 255))

    # Center Artwork Screen
    screen_y = header_h
    screen_h = footer_y - screen_y

    # Ambient background from art
    bg_art = clean_art.resize((face_w, screen_h), Image.Resampling.LANCZOS).filter(ImageFilter.GaussianBlur(36))
    tint_screen = Image.new("RGBA", (face_w, screen_h), (0, 0, 0, 70 if not is_light else 30))
    bg_art.paste(tint_screen, (0, 0), tint_screen)
    face.paste(bg_art, (0, screen_y))

    # Scaled artwork 100% UNTOUCHED and centered inside screen_h
    scaled_art = ImageOps.contain(clean_art, (face_w, screen_h), Image.Resampling.LANCZOS)
    ax = (face_w - scaled_art.width) // 2
    ay = screen_y + (screen_h - scaled_art.height) // 2

    # Soft natural shadow behind art
    sh = Image.new("RGBA", (face_w, face_h), (0, 0, 0, 0))
    sh_draw = ImageDraw.Draw(sh)
    sh_draw.rectangle([ax - 4, ay - 4, ax + scaled_art.width + 4, ay + scaled_art.height + 4], fill=(0, 0, 0, 160))
    face.alpha_composite(sh.filter(ImageFilter.GaussianBlur(18)))

    # Composite sharp art
    face.paste(scaled_art, (ax, ay))

    return face

def render_n3ds_3d(cover_img: Image.Image, title: str, prod_code: str = "", theme: str = "dark") -> Image.Image:
    is_light = (theme == "light")
    canvas = Image.new("RGBA", CANVAS_SIZE, (0, 0, 0, 0))

    # 1. Contact Drop Shadow beneath the case
    shadow = Image.new("RGBA", CANVAS_SIZE, (0, 0, 0, 0))
    s_draw = ImageDraw.Draw(shadow)
    shadow_poly = [
        (115, 1290), (235, 1345), (1040, 1290), (1075, 1360), (250, 1445), (95, 1375)
    ]
    s_draw.polygon(shadow_poly, fill=(0, 0, 0, 125 if is_light else 165))
    canvas.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(32)))

    # 2. Plastic Case Backing
    back_draw = ImageDraw.Draw(canvas)
    back_poly = [
        (125, 150), (235, 115), (1040, 170), (1040, 1290), (235, 1345), (125, 1310)
    ]
    case_bg = (248, 250, 254, 255) if is_light else (18, 20, 23, 255)
    back_draw.polygon(back_poly, fill=case_bg)

    # 3. Clean artwork and check aspect ratio
    clean_art = trim_white_scan_strip(cover_img)
    w_clean, h_clean = clean_art.size
    ratio = w_clean / max(h_clean, 1)

    face_w, face_h = 800, 1110
    if ratio <= 0.85:
        # Standard vertical cover (3:4) fills face completely with ZERO crop
        face = Image.new("RGBA", (face_w, face_h), (255, 255, 255, 255) if is_light else (18, 20, 24, 255))
        scaled_art = ImageOps.fit(clean_art.convert("RGBA"), (face_w, face_h), Image.Resampling.LANCZOS)
        face.alpha_composite(scaled_art, (0, 0))
        border_col = (0, 0, 0, 25) if is_light else (255, 255, 255, 20)
        ImageDraw.Draw(face).rectangle([0, 0, face_w - 1, face_h - 1], outline=border_col, width=2)
    else:
        # Square (~1:1) or Horizontal (16:9 / 4:3): Deluxe Software Edition (ZERO CROPPING!)
        face = render_n3ds_deluxe_cover(clean_art, title, theme=theme)

    canvas.alpha_composite(warp(face, FRONT_CORNERS))

    # 4. Spine (Left side with centered title)
    spine_img = create_n3ds_spine(title, prod_code=prod_code, theme=theme)
    canvas.alpha_composite(warp(spine_img, SPINE_CORNERS))

    # 5. Case Edge Highlights & Translucent Bevels
    d = ImageDraw.Draw(canvas)
    ridge_col = (255, 255, 255, 255) if is_light else (160, 165, 175, 230)
    d.line([(235, 120), (235, 1340)], fill=ridge_col, width=3)

    top_col = (255, 255, 255, 240) if is_light else (175, 180, 190, 220)
    d.line([(130, 155), (235, 120)], fill=top_col, width=3)
    d.line([(235, 120), (1035, 175)], fill=top_col, width=3)

    outer_col = (215, 222, 232, 220) if is_light else (85, 90, 100, 200)
    d.line([(130, 155), (130, 1305)], fill=outer_col, width=4)

    bottom_col = (195, 200, 210, 230) if is_light else (45, 48, 55, 220)
    d.line([(130, 1305), (235, 1340)], fill=bottom_col, width=3)
    d.line([(235, 1340), (1035, 1285)], fill=bottom_col, width=3)

    right_col = (205, 212, 222, 200) if is_light else (65, 70, 80, 180)
    d.line([(1035, 175), (1035, 1285)], fill=right_col, width=2)

    alpha = canvas.split()[-1]
    bbox = alpha.point(lambda p: 255 if p > 5 else 0).getbbox()
    if bbox:
        m = 12
        cropped = canvas.crop((max(0, bbox[0] - m), max(0, bbox[1] - m), min(CANVAS_SIZE[0], bbox[2] + m), min(CANVAS_SIZE[1], bbox[3] + m)))
        return cropped.resize((840, 1080), Image.Resampling.LANCZOS)
    return canvas.resize((840, 1080), Image.Resampling.LANCZOS)

def render_n3ds_flat(cover_img: Image.Image, target_size: tuple[int, int] = (810, 1080)) -> Image.Image:
    clean_art = trim_white_scan_strip(cover_img)
    w, h = clean_art.size
    ratio = w / max(h, 1)
    if ratio <= 0.82:
        return ImageOps.fit(clean_art.convert("RGB"), target_size, Image.Resampling.LANCZOS)

    # Square or wide cover: Deluxe Software Edition formatted to flat vertical presentation
    deluxe = render_n3ds_deluxe_cover(clean_art, "", theme="dark")
    return deluxe.resize(target_size, Image.Resampling.LANCZOS).convert("RGB")
