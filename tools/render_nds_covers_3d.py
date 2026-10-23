import os
import sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageOps, ImageFilter, ImageFont

CANVAS_SIZE = (1200, 1500)
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

    right_edge = arr[:, -5:]
    if (right_edge.mean() > 240) and ((right_edge > 220).all(axis=2).mean() > 0.85):
        for x in range(w - 1, int(w * 0.5), -1):
            if arr[:, x].mean() < 160:
                cut_x = max(int(w * 0.5), x - 6)
                return rgb.crop((0, 0, cut_x, h))
    return rgb

def draw_nds_dual_screens(draw: ImageDraw.ImageDraw, x: int, y: int, size: int = 24, color: tuple = (255, 255, 255, 255)):
    """Draws the iconic Nintendo DS dual screens symbol."""
    w = int(size * 1.3)
    h = int(size * 0.42)
    gap = int(size * 0.16)
    r = max(2, int(size * 0.12))
    draw.rounded_rectangle([x, y, x + w, y + h], radius=r, outline=color, width=2)
    draw.rounded_rectangle([x, y + h + gap, x + w, y + h * 2 + gap], radius=r, outline=color, width=2)

def create_nds_logo_badge(width: int = 86, is_light: bool = False) -> Image.Image:
    """Creates the official Nintendo DS branding mark for the top of the spine."""
    badge_h = 95
    badge = Image.new("RGBA", (width, badge_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(badge)

    bg_color = (235, 238, 245, 255) if is_light else (24, 26, 32, 255)
    border_color = (0, 120, 215, 255) if is_light else (55, 60, 72, 255)

    draw.rounded_rectangle([0, 0, width - 1, badge_h - 1], radius=8, fill=bg_color, outline=border_color, width=2)

    try:
        f_nin = ImageFont.truetype(r"C:\Windows\Fonts\arialbd.ttf", 12)
        f_ds_big = ImageFont.truetype(r"C:\Windows\Fonts\arialbd.ttf", 36)
    except Exception:
        f_nin = f_ds_big = ImageFont.load_default()

    text_color = (15, 20, 28, 255) if is_light else (255, 255, 255, 255)

    # "NINTENDO"
    t_nin = "NINTENDO"
    tb = draw.textbbox((0, 0), t_nin, font=f_nin)
    tw = tb[2] - tb[0]
    draw.text(((width - tw) // 2, 8), t_nin, font=f_nin, fill=(0, 120, 215, 255) if is_light else (170, 180, 200, 255))

    # Bold "DS" + Dual Screens
    ds_y = 26
    tb_ds = draw.textbbox((0, 0), "DS", font=f_ds_big)
    tw_ds = tb_ds[2] - tb_ds[0]

    total_w = tw_ds + 24
    start_x = (width - total_w) // 2
    draw.text((start_x, ds_y), "DS", font=f_ds_big, fill=text_color)

    scr_x = start_x + tw_ds + 6
    scr_w = 16
    scr_h = 13
    scr_col = (0, 120, 215, 255) if is_light else (255, 255, 255, 255)
    draw.rounded_rectangle([scr_x, ds_y + 8, scr_x + scr_w, ds_y + 8 + scr_h], radius=2, outline=scr_col, width=2)
    draw.rounded_rectangle([scr_x, ds_y + 8 + scr_h + 3, scr_x + scr_w, ds_y + 8 + scr_h * 2 + 3], radius=2, outline=scr_col, width=2)

    return badge

def create_nds_spine(title: str, prod_code: str = "NTR", height: int = 1220, width: int = 105, theme: str = "dark") -> Image.Image:
    is_light = (theme == "light")
    bg = (248, 250, 253, 255) if is_light else (16, 17, 20, 255)
    spine = Image.new("RGBA", (width, height), bg)
    draw = ImageDraw.Draw(spine)

    for x in range(width):
        factor = 0.86 + 0.14 * (x / width)
        col = (int(240 * factor), int(244 * factor), int(250 * factor), 255) if is_light else (int(15 * factor), int(16 * factor), int(20 * factor), 255)
        draw.line([(x, 0), (x, height)], fill=col)

    notch_col = (205, 212, 222, 255) if is_light else (10, 11, 13, 255)
    draw.rectangle([0, 110, 14, 140], fill=notch_col)
    draw.rectangle([0, height - 140, 14, height - 110], fill=notch_col)

    # Top Nintendo DS Badge (Variant A - User Approved)
    top_badge = create_nds_logo_badge(width=width - 20, is_light=is_light)
    spine.alpha_composite(top_badge, (10, 25))

    # Bottom Nintendo Oval Badge
    pill_w, pill_h = width - 26, 30
    pill_x, pill_y = 13, height - 60
    draw.rounded_rectangle([pill_x, pill_y, pill_x + pill_w, pill_y + pill_h], radius=15, outline=(228, 0, 15, 255), width=2)
    try:
        f_pill = ImageFont.truetype(r"C:\Windows\Fonts\arialbd.ttf", 15)
        f_title = ImageFont.truetype(r"C:\Windows\Fonts\segoeuib.ttf", 32)
    except Exception:
        f_pill = f_title = ImageFont.load_default()

    tb_n = draw.textbbox((0, 0), "Nintendo", font=f_pill)
    tw_n, th_n = tb_n[2] - tb_n[0], tb_n[3] - tb_n[1]
    draw.text((pill_x + (pill_w - tw_n) // 2, pill_y + (pill_h - th_n) // 2 - 1), "Nintendo", font=f_pill, fill=(228, 0, 15, 255))

    # Product Code just above bottom pill
    if prod_code:
        try:
            f_code = ImageFont.truetype(r"C:\Windows\Fonts\segoeui.ttf", 13)
        except Exception:
            f_code = ImageFont.load_default()
        cb = draw.textbbox((0, 0), prod_code, font=f_code)
        cw, ch = cb[2] - cb[0], cb[3] - cb[1]
        c_cv = Image.new("RGBA", (cw + 4, ch + 4), (0, 0, 0, 0))
        ImageDraw.Draw(c_cv).text((-cb[0] + 2, -cb[1] + 2), prod_code, font=f_code, fill=(130, 135, 145, 255) if is_light else (140, 145, 155, 255))
        c_rot = c_cv.rotate(90, expand=True, resample=Image.Resampling.BICUBIC)
        spine.alpha_composite(c_rot, ((width - c_rot.width) // 2, height - 85 - c_rot.height))

    # Spine Title: Dynamic measurement & vertical centering
    clean_title = (title or "").strip()
    dummy = Image.new("RGBA", (10, 10))
    tb = ImageDraw.Draw(dummy).textbbox((0, 0), clean_title, font=f_title)
    tw, th = tb[2] - tb[0], tb[3] - tb[1]

    t_cv = Image.new("RGBA", (tw + 8, th + 8), (0, 0, 0, 0))
    tc = (18, 22, 28, 255) if is_light else (245, 248, 252, 255)
    ImageDraw.Draw(t_cv).text((-tb[0] + 4, -tb[1] + 4), clean_title, font=f_title, fill=tc)
    rot_title = t_cv.rotate(90, expand=True, resample=Image.Resampling.BICUBIC)

    top_bound = 135
    bottom_bound = height - 145
    max_h = bottom_bound - top_bound
    if rot_title.height > max_h:
        rot_title = ImageOps.contain(rot_title, (width - 20, max_h), Image.Resampling.LANCZOS)

    cy = (top_bound + bottom_bound) // 2
    py = cy - (rot_title.height // 2)
    px = (width - rot_title.width) // 2
    spine.alpha_composite(rot_title, (px, py))

    # Edge bevels
    edge_high = (255, 255, 255, 240) if is_light else (80, 85, 95, 200)
    edge_dark = (195, 200, 210, 255) if is_light else (30, 33, 40, 255)
    draw.line([(width - 2, 0), (width - 2, height)], fill=edge_high, width=2)
    draw.line([(2, 0), (2, height)], fill=edge_dark, width=2)

    return spine

def render_nds_deluxe_cover(art_img: Image.Image, title: str, theme: str = "dark") -> Image.Image:
    """Deluxe Dual Screen Software edition for horizontal or square covers."""
    clean_art = trim_white_scan_strip(art_img)
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

    # 1. Header: Nintendo DS Official Software
    header_h = 76
    h_bg = (238, 242, 248, 255) if is_light else (22, 25, 30, 255)
    draw.rectangle([0, 0, face_w, header_h], fill=h_bg)

    draw_nds_dual_screens(draw, 28, 20, size=24, color=(0, 120, 215, 255) if is_light else (255, 255, 255, 255))

    h_text_color = (20, 24, 30, 255) if is_light else (255, 255, 255, 255)
    draw.text((75, 17), "NINTENDO DS", font=f_header, fill=h_text_color)
    draw.text((77, 46), "DUAL SCREEN SOFTWARE EDITION", font=f_sub, fill=(110, 120, 135, 255) if is_light else (145, 155, 170, 255))

    accent_color = (0, 120, 215, 255)
    draw.line([(0, header_h - 2), (face_w, header_h - 2)], fill=accent_color, width=2)

    # 2. Footer
    footer_h = 54
    footer_y = face_h - footer_h
    foot_bg = (236, 240, 246, 255) if is_light else (20, 23, 28, 255)
    draw.rectangle([0, footer_y, face_w, face_h], fill=foot_bg)
    draw.line([(0, footer_y), (face_w, footer_y)], fill=(195, 200, 210, 255) if is_light else (35, 38, 45, 255), width=2)

    draw.rounded_rectangle([25, footer_y + 11, 195, footer_y + 43], radius=5, fill=(0, 120, 215, 255))
    draw.text((36, footer_y + 17), "Touch Screen Compatible", font=f_small, fill=(255, 255, 255, 255))

    draw.rounded_rectangle([face_w - 175, footer_y + 11, face_w - 25, footer_y + 43], radius=5, outline=(218, 165, 32, 255), width=2)
    draw.text((face_w - 160, footer_y + 18), "OFFICIAL SEAL", font=f_footer, fill=(218, 165, 32, 255))

    # 3. Center Screen
    screen_y = header_h
    screen_h = footer_y - screen_y

    bg_art = clean_art.convert("RGBA").resize((face_w, screen_h), Image.Resampling.LANCZOS).filter(ImageFilter.GaussianBlur(36))
    tint_screen = Image.new("RGBA", (face_w, screen_h), (0, 0, 0, 70 if not is_light else 30))
    bg_art.paste(tint_screen, (0, 0), tint_screen)
    face.paste(bg_art, (0, screen_y))

    scaled_art = ImageOps.contain(clean_art.convert("RGBA"), (face_w, screen_h), Image.Resampling.LANCZOS)
    ax = (face_w - scaled_art.width) // 2
    ay = screen_y + (screen_h - scaled_art.height) // 2

    sh = Image.new("RGBA", (face_w, face_h), (0, 0, 0, 0))
    sh_draw = ImageDraw.Draw(sh)
    sh_draw.rectangle([ax - 4, ay - 4, ax + scaled_art.width + 4, ay + scaled_art.height + 4], fill=(0, 0, 0, 160))
    face.alpha_composite(sh.filter(ImageFilter.GaussianBlur(18)))
    face.paste(scaled_art, (ax, ay))

    return face

def render_nds_3d(cover_img: Image.Image, title: str, prod_code: str = "NTR", theme: str = "dark") -> Image.Image:
    is_light = (theme == "light")
    canvas = Image.new("RGBA", CANVAS_SIZE, (0, 0, 0, 0))

    # 1. Contact Drop Shadow
    shadow = Image.new("RGBA", CANVAS_SIZE, (0, 0, 0, 0))
    s_draw = ImageDraw.Draw(shadow)
    shadow_poly = [(115, 1290), (235, 1345), (1040, 1290), (1075, 1360), (250, 1445), (95, 1375)]
    s_draw.polygon(shadow_poly, fill=(0, 0, 0, 125 if is_light else 165))
    canvas.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(32)))

    # 2. Plastic Case Backing
    back_draw = ImageDraw.Draw(canvas)
    back_poly = [(125, 150), (235, 115), (1040, 170), (1040, 1290), (235, 1345), (125, 1310)]
    case_bg = (246, 248, 252, 255) if is_light else (15, 16, 19, 255)
    back_draw.polygon(back_poly, fill=case_bg)

    # 3. Clean Art & Aspect Ratio Check
    clean_art = trim_white_scan_strip(cover_img)
    w_raw, h_raw = clean_art.size
    ratio = w_raw / max(h_raw, 1)

    face_w, face_h = 800, 1110
    if ratio <= 0.85:
        # Standard vertical cover (3:4)
        face = Image.new("RGBA", (face_w, face_h), (255, 255, 255, 255) if is_light else (18, 20, 24, 255))
        scaled_art = ImageOps.fit(clean_art.convert("RGBA"), (face_w, face_h), Image.Resampling.LANCZOS)
        face.alpha_composite(scaled_art, (0, 0))
        border_col = (0, 0, 0, 25) if is_light else (255, 255, 255, 20)
        ImageDraw.Draw(face).rectangle([0, 0, face_w - 1, face_h - 1], outline=border_col, width=2)
    else:
        # Wide or Square cover -> Deluxe software edition
        face = render_nds_deluxe_cover(clean_art, title, theme=theme)

    canvas.alpha_composite(warp(face, FRONT_CORNERS))

    # 4. Spine
    spine_img = create_nds_spine(title, prod_code=prod_code, theme=theme)
    canvas.alpha_composite(warp(spine_img, SPINE_CORNERS))

    # 5. Case Edge Highlights
    d = ImageDraw.Draw(canvas)
    ridge_col = (255, 255, 255, 255) if is_light else (150, 155, 165, 220)
    d.line([(235, 120), (235, 1340)], fill=ridge_col, width=3)

    top_col = (255, 255, 255, 240) if is_light else (165, 170, 180, 210)
    d.line([(130, 155), (235, 120)], fill=top_col, width=3)
    d.line([(235, 120), (1035, 175)], fill=top_col, width=3)

    outer_col = (215, 222, 232, 220) if is_light else (80, 85, 95, 200)
    d.line([(130, 155), (130, 1305)], fill=outer_col, width=4)

    bottom_col = (195, 200, 210, 230) if is_light else (40, 43, 50, 210)
    d.line([(130, 1305), (235, 1340)], fill=bottom_col, width=3)
    d.line([(235, 1340), (1035, 1285)], fill=bottom_col, width=3)

    right_col = (205, 212, 222, 200) if is_light else (60, 65, 75, 170)
    d.line([(1035, 175), (1035, 1285)], fill=right_col, width=2)

    alpha = canvas.split()[-1]
    bbox = alpha.point(lambda p: 255 if p > 5 else 0).getbbox()
    if bbox:
        m = 12
        cropped = canvas.crop((max(0, bbox[0] - m), max(0, bbox[1] - m), min(CANVAS_SIZE[0], bbox[2] + m), min(CANVAS_SIZE[1], bbox[3] + m)))
        return cropped.resize((840, 1080), Image.Resampling.LANCZOS)
    return canvas.resize((840, 1080), Image.Resampling.LANCZOS)

def render_nds_flat(cover_img: Image.Image, target_size: tuple[int, int] = (810, 1080)) -> Image.Image:
    clean_art = trim_white_scan_strip(cover_img)
    w, h = clean_art.size
    ratio = w / max(h, 1)
    if ratio <= 0.82:
        return ImageOps.fit(clean_art.convert("RGB"), target_size, Image.Resampling.LANCZOS)

    deluxe = render_nds_deluxe_cover(clean_art, "", theme="dark")
    return deluxe.resize(target_size, Image.Resampling.LANCZOS).convert("RGB")
