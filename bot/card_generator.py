import io
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from PIL import Image, ImageDraw, ImageFont

FONTS_DIR = Path(__file__).resolve().parent / "assets" / "fonts"


def clean_emoji_text(text: str) -> str:
    """Удаляет символы эмодзи, которые могут отсутствовать в системных шрифтах и вызывать пустые квадраты."""
    pattern = r"[\U00010000-\U0010ffff\u2600-\u27bf\u2300-\u23ff\u2b50-\u2b55\u200d\ufe0f]"
    cleaned = re.sub(pattern, "", text)
    return re.sub(r"\s+", " ", cleaned).strip()


def get_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    font_name = "segoeuib.ttf" if bold else "segoeui.ttf"
    font_path = FONTS_DIR / font_name
    if not font_path.exists():
        font_path = FONTS_DIR / ("arialbd.ttf" if bold else "arial.ttf")
    try:
        return ImageFont.truetype(str(font_path), size)
    except Exception:
        return ImageFont.load_default()


def draw_calendar_icon(draw: ImageDraw.ImageDraw, x: int, y: int, size: int = 24, color=(148, 155, 164, 255)):
    draw.rounded_rectangle([(x, y + 4), (x + size, y + size + 2)], radius=4, outline=color, width=2)
    draw.line([(x, y + 10), (x + size, y + 10)], fill=color, width=2)
    draw.line([(x + 5, y), (x + 5, y + 5)], fill=color, width=2)
    draw.line([(x + size - 5, y), (x + size - 5, y + 5)], fill=color, width=2)
    draw.point([(x + 6, y + 15), (x + 12, y + 15), (x + 18, y + 15)], fill=color)


def draw_chat_icon(draw: ImageDraw.ImageDraw, x: int, y: int, size: int = 24, color=(148, 155, 164, 255)):
    draw.rounded_rectangle([(x, y), (x + size, y + size - 5)], radius=5, outline=color, width=2)
    draw.polygon([(x + 4, y + size - 5), (x + 11, y + size - 5), (x + 4, y + size + 3)], fill=color)


def draw_mic_icon(draw: ImageDraw.ImageDraw, x: int, y: int, color=(46, 204, 113, 255)):
    draw.rounded_rectangle([(x + 6, y), (x + 18, y + 16)], radius=6, fill=color)
    draw.arc([(x + 2, y + 6), (x + 22, y + 22)], 0, 180, fill=color, width=3)
    draw.line([(x + 12, y + 22), (x + 12, y + 28)], fill=color, width=3)
    draw.line([(x + 6, y + 28), (x + 18, y + 28)], fill=color, width=3)


def draw_trophy_icon(draw: ImageDraw.ImageDraw, x: int, y: int, color=(241, 196, 15, 255)):
    draw.polygon([(x + 4, y), (x + 22, y), (x + 18, y + 14), (x + 8, y + 14)], fill=color)
    draw.arc([(x, y + 1), (x + 10, y + 10)], 90, 270, fill=color, width=3)
    draw.arc([(x + 16, y + 1), (x + 26, y + 10)], 270, 90, fill=color, width=3)
    draw.rectangle([(x + 11, y + 14), (x + 15, y + 19)], fill=color)
    draw.rectangle([(x + 7, y + 19), (x + 19, y + 23)], fill=color)


def draw_clock_icon(draw: ImageDraw.ImageDraw, x: int, y: int, size: int = 20, color=(148, 155, 164, 255)):
    draw.ellipse([(x, y), (x + size, y + size)], outline=color, width=2)
    cx, cy = x + size // 2, y + size // 2
    draw.line([(cx, cy), (cx, cy - 6)], fill=color, width=2)
    draw.line([(cx, cy), (cx + 5, cy)], fill=color, width=2)


@dataclass
class CardTheme:
    """Конфигурация темы/скина карточки профиля (для будущих кастомных дизайнов и магазина)."""
    id: str = "default"
    name: str = "Discord Dark"
    card_bg: tuple[int, int, int, int] = (35, 36, 40, 255)         # #232428 (тело карточки)
    card_border: tuple[int, int, int, int] = (55, 57, 63, 255)     # #37393f
    banner_top: tuple[int, int, int] = (45, 47, 52)                # #2d2f34 (верх шапки)
    banner_bottom: tuple[int, int, int] = (24, 25, 28)             # #18191c (низ шапки)
    banner_image_bytes: Optional[bytes] = None                      # Кастомный арт шапки (для покупки)
    card_bg_image_bytes: Optional[bytes] = None                     # Кастомный фон всей карточки (для покупки)
    box_bg: tuple[int, int, int, int] = (30, 31, 34, 255)          # #1e1f22 (плашки со статистикой)
    box_border: tuple[int, int, int, int] = (48, 50, 56, 255)      # #303238
    voice_box_border: tuple[int, int, int, int] = (46, 204, 113, 255) # Неоновый зеленый
    accent_colors: list[tuple[int, int, int]] = field(default_factory=lambda: [
        (46, 204, 113),   # Зеленый
        (26, 188, 156),   # Бирюзовый
        (52, 152, 219),   # Синий
        (155, 89, 182),   # Пурпурный
        (235, 69, 158),   # Розовый
        (46, 204, 113),   # Замыкание в зеленый
    ])


DEFAULT_THEME = CardTheme()


def create_accent_strip(w: int, h: int = 10, colors: Optional[list[tuple[int, int, int]]] = None) -> Image.Image:
    """Генерирует бесшовную циклическую полоску градиента шириной 2 * w для плавной анимации."""
    palette = colors or DEFAULT_THEME.accent_colors
    strip = Image.new("RGBA", (w * 2, h))
    draw = ImageDraw.Draw(strip)
    n_segs = len(palette) - 1
    for x in range(w * 2):
        pos = (x / w) % 1.0
        seg = min(int(pos * n_segs), n_segs - 1)
        sub = (pos * n_segs) - seg
        c1, c2 = palette[seg], palette[seg + 1]
        r = int(c1[0] * (1 - sub) + c2[0] * sub)
        g = int(c1[1] * (1 - sub) + c2[1] * sub)
        b = int(c1[2] * (1 - sub) + c2[2] * sub)
        draw.line([(x, 0), (x, h)], fill=(r, g, b, 255))
    return strip


def create_profile_card_image(
    display_name: str,
    handle: str,
    user_id: int,
    days_on_server: int,
    join_date_str: str,
    msg_count: int,
    voice_str: str,
    avg_voice_str: str,
    current_voice_str: str,
    voice_wins: int,
    chat_wins: int,
    created_date_str: str,
    roles: list[tuple[str, tuple[int, int, int, int]]],
    avatar_bytes: Optional[bytes] = None,
    animated: bool = True,
    theme: Optional[CardTheme] = None
) -> io.BytesIO:
    """Генерирует сверхчёткую 2X Retina графическую карточку профиля участника."""
    # Разрешение 1200 x 1040 (2x от 600x520) для идеальной чёткости на любых экранах
    w, h = 1200, 1040
    active_theme = theme or DEFAULT_THEME
    card = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(card)

    # 1. Основной фон карточки
    draw.rounded_rectangle([(0, 0), (w, h)], radius=36, fill=active_theme.card_bg, outline=active_theme.card_border, width=3)
    if active_theme.card_bg_image_bytes:
        try:
            bg_art = Image.open(io.BytesIO(active_theme.card_bg_image_bytes)).convert("RGBA")
            bg_art = bg_art.resize((w, h), Image.Resampling.LANCZOS)
            bg_mask = Image.new("L", (w, h), 0)
            ImageDraw.Draw(bg_mask).rounded_rectangle([(0, 0), (w, h)], radius=36, fill=255)
            card.paste(bg_art, (0, 0), bg_mask)
        except Exception:
            pass

    # 2. Верхний баннер (600x110 в 2X = 1200x220)
    banner_h = 220
    if active_theme.banner_image_bytes:
        try:
            b_art = Image.open(io.BytesIO(active_theme.banner_image_bytes)).convert("RGBA")
            b_art = b_art.resize((w, banner_h), Image.Resampling.LANCZOS)
            b_mask_full = Image.new("L", (w, h), 0)
            ImageDraw.Draw(b_mask_full).rounded_rectangle([(0, 0), (w, h)], radius=36, fill=255)
            b_mask = b_mask_full.crop((0, 0, w, banner_h))
            card.paste(b_art, (0, 0), b_mask)
        except Exception:
            pass
    else:
        banner = Image.new("RGBA", (w, banner_h), (0, 0, 0, 0))
        b_draw = ImageDraw.Draw(banner)
        for y in range(banner_h):
            ratio = y / banner_h
            r = int(active_theme.banner_top[0] * (1 - ratio) + active_theme.banner_bottom[0] * ratio)
            g = int(active_theme.banner_top[1] * (1 - ratio) + active_theme.banner_bottom[1] * ratio)
            b = int(active_theme.banner_top[2] * (1 - ratio) + active_theme.banner_bottom[2] * ratio)
            b_draw.line([(0, y), (w, y)], fill=(r, g, b, 255))
        card.paste(banner, (0, 0), banner)

    # 3. Аватарка: Центр x=140, y=220 (аккуратно на линии стыка баннера), диаметр 160 (r=80)
    av_x, av_y, av_r = 140, 220, 80
    rendered_avatar = False
    if avatar_bytes:
        try:
            av_img = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA")

            # Если у аватарки белый/светлый фон в углах (стикеры/мемы), очищаем наружный фон до прозрачности
            corners = [
                (0, 0),
                (av_img.width - 1, 0),
                (0, av_img.height - 1),
                (av_img.width - 1, av_img.height - 1)
            ]
            white_corners = sum(1 for pt in corners if sum(av_img.getpixel(pt)[:3]) / 3 > 235)
            if white_corners >= 3:
                for pt in corners:
                    pix = av_img.getpixel(pt)
                    if sum(pix[:3]) / 3 > 230 and pix[3] > 0:
                        ImageDraw.floodfill(av_img, pt, (0, 0, 0, 0), thresh=25)

            # Центрированная обрезка до квадрата и увеличение на 5% для полного прилегания без микрополос
            w_orig, h_orig = av_img.size
            min_dim = min(w_orig, h_orig)
            cx, cy = w_orig // 2, h_orig // 2
            av_sq = av_img.crop((cx - min_dim // 2, cy - min_dim // 2, cx + min_dim // 2, cy + min_dim // 2))

            target_dim = int(av_r * 2 * 1.05)
            av_scaled = av_sq.resize((target_dim, target_dim), Image.Resampling.LANCZOS)
            offset = (target_dim - av_r * 2) // 2
            av_final = av_scaled.crop((offset, offset, offset + av_r * 2, offset + av_r * 2))

            # 4x суперсэмплированная гладкая круглая маска
            s = 4
            mask_hi = Image.new("L", (av_r * 2 * s, av_r * 2 * s), 0)
            m_draw = ImageDraw.Draw(mask_hi)
            m_draw.ellipse([(0, 0), (av_r * 2 * s - 1, av_r * 2 * s - 1)], fill=255)
            mask = mask_hi.resize((av_r * 2, av_r * 2), Image.Resampling.LANCZOS)

            card.paste(av_final, (av_x - av_r, av_y - av_r), mask)
            rendered_avatar = True
        except Exception:
            rendered_avatar = False

    if not rendered_avatar:
        draw.ellipse([(av_x - av_r, av_y - av_r), (av_x + av_r, av_y + av_r)], fill=(241, 196, 15, 255))
        draw.ellipse([(av_x - 24, av_y - 14), (av_x - 12, av_y)], fill=(30, 31, 34, 255))
        draw.ellipse([(av_x + 12, av_y - 14), (av_x + 24, av_y)], fill=(30, 31, 34, 255))
        draw.arc([(av_x - 32, av_y + 4), (av_x + 32, av_y + 40)], 0, 180, fill=(30, 31, 34, 255), width=8)

    # Защитная сглаженная рамка вокруг аватарки в цвет карточки
    # Внутренний радиус перекрывает микрокрай аватарки, исключая любые белые полосы
    s = 4
    ring_box = av_r + 16
    ring_hi = Image.new("RGBA", (ring_box * 2 * s, ring_box * 2 * s), (0, 0, 0, 0))
    r_draw = ImageDraw.Draw(ring_hi)
    c_ring = ring_box * s
    r_draw.ellipse(
        [(c_ring - (av_r + 6) * s, c_ring - (av_r + 6) * s), (c_ring + (av_r + 6) * s, c_ring + (av_r + 6) * s)],
        fill=active_theme.card_bg
    )
    r_draw.ellipse(
        [(c_ring - (av_r - 4) * s, c_ring - (av_r - 4) * s), (c_ring + (av_r - 4) * s, c_ring + (av_r - 4) * s)],
        fill=(0, 0, 0, 0)
    )
    ring_img = ring_hi.resize((ring_box * 2, ring_box * 2), Image.Resampling.LANCZOS)
    card.paste(ring_img, (av_x - ring_box, av_y - ring_box), ring_img)

    # Точка онлайн-статуса со сглаженной подложкой
    dot_x, dot_y, dot_r = av_x + 54, av_y + 54, 20
    dot_bg_r = dot_r + 7
    d_hi = Image.new("RGBA", (dot_bg_r * 2 * s, dot_bg_r * 2 * s), (0, 0, 0, 0))
    d_draw = ImageDraw.Draw(d_hi)
    c_dot = dot_bg_r * s
    # Темный круг подложки цвета карточки, гарантированно стирающий край авы под точкой
    d_draw.ellipse(
        [(c_dot - dot_bg_r * s, c_dot - dot_bg_r * s), (c_dot + dot_bg_r * s, c_dot + dot_bg_r * s)],
        fill=active_theme.card_bg
    )
    # Зеленая точка онлайн
    d_draw.ellipse(
        [(c_dot - dot_r * s, c_dot - dot_r * s), (c_dot + dot_r * s, c_dot + dot_r * s)],
        fill=(46, 204, 113, 255)
    )
    dot_img = d_hi.resize((dot_bg_r * 2, dot_bg_r * 2), Image.Resampling.LANCZOS)
    card.paste(dot_img, (dot_x - dot_bg_r, dot_y - dot_bg_r), dot_img)

    # 4. Бейджи ролей (в правом верхнем углу)
    font_badge = get_font(22, bold=True)
    badge_x = 1140
    if roles:
        for r_name, r_color in reversed(roles[:2]):
            t_w = int(draw.textlength(r_name, font=font_badge))
            b_w = t_w + 44
            badge_x -= b_w
            draw.rounded_rectangle([(badge_x, 240), (badge_x + b_w, 298)], radius=28, fill=(43, 45, 49, 255), outline=r_color, width=2)
            draw.text((badge_x + 22, 254), r_name, fill=r_color, font=font_badge)
            badge_x -= 18

    # 5. Имя пользователя и бейдж "УЧАСТНИК"
    font_name = get_font(42, bold=True)
    clean_name = display_name if len(display_name) <= 18 else display_name[:17] + "…"
    draw.text((60, 340), clean_name, fill=(255, 255, 255, 255), font=font_name)
    name_w = int(draw.textlength(clean_name, font=font_name))

    # Бейдж "УЧАСТНИК"
    pill_x = 60 + name_w + 20
    font_pill = get_font(19, bold=True)
    draw.rounded_rectangle([(pill_x, 348), (pill_x + 145, 390)], radius=10, fill=(88, 101, 242, 255))
    draw.text((pill_x + 16, 356), "УЧАСТНИК", fill=(255, 255, 255, 255), font=font_pill)

    # Никнейм / тег и ID
    font_sub = get_font(23, bold=False)
    draw.text((60, 404), f"@{handle} • ID: {user_id}", fill=(148, 155, 164, 255), font=font_sub)

    # 6. Блок 1: На сервере
    draw.rounded_rectangle([(60, 454), (580, 588)], radius=24, fill=active_theme.box_bg, outline=active_theme.box_border, width=2)
    draw_calendar_icon(draw, 90, 478, size=24)
    font_label = get_font(21, bold=True)
    draw.text((124, 478), "НА СЕРВЕРЕ", fill=(148, 155, 164, 255), font=font_label)
    font_val = get_font(33, bold=True)
    draw.text((90, 520), f"{days_on_server} дн.", fill=(255, 255, 255, 255), font=font_val)
    days_w = int(draw.textlength(f"{days_on_server} дн.", font=font_val))
    font_sub_join = get_font(18, bold=False)
    sub_text = f"({join_date_str})"
    while draw.textlength(sub_text, font=font_sub_join) + days_w + 104 > 565 and font_sub_join.size > 13:
        font_sub_join = get_font(font_sub_join.size - 1, bold=False)
    draw.text((90 + days_w + 14, 530), sub_text, fill=(148, 155, 164, 255), font=font_sub_join)

    # Блок 2: Сообщения
    draw.rounded_rectangle([(620, 454), (1140, 588)], radius=24, fill=active_theme.box_bg, outline=active_theme.box_border, width=2)
    draw_chat_icon(draw, 650, 478, size=24)
    draw.text((684, 478), "СООБЩЕНИЯ", fill=(148, 155, 164, 255), font=font_label)
    draw.text((650, 520), f"{msg_count} сообщений", fill=(255, 255, 255, 255), font=font_val)

    # 7. Блок 3: Время в голосовых (Главная карточка)
    draw.rounded_rectangle([(60, 614), (1140, 770)], radius=24, fill=active_theme.box_bg, outline=active_theme.voice_box_border, width=3)
    draw_mic_icon(draw, 90, 638, color=active_theme.voice_box_border[:3])
    font_voice_title = get_font(23, bold=True)
    draw.text((124, 638), "ВРЕМЯ В ГОЛОСОВЫХ КАНАЛАХ", fill=active_theme.voice_box_border[:3], font=font_voice_title)

    if avg_voice_str:
        draw_clock_icon(draw, 640, 642, size=20)
        draw.text((670, 638), f"В среднем: {avg_voice_str}", fill=(148, 155, 164, 255), font=font_sub)

    font_voice_val = get_font(42, bold=True)
    draw.text((90, 686), voice_str, fill=(255, 255, 255, 255), font=font_voice_val)

    if current_voice_str:
        # Очищаем спецсимволы и неподдерживаемые эмодзи в названии текущего войса для аккуратного отображения
        c_clean = clean_emoji_text(current_voice_str)
        pill_text = c_clean if len(c_clean) <= 28 else c_clean[:27] + "…"
        pt_w = int(draw.textlength(pill_text, font=font_badge))
        pw = pt_w + 64
        px = 1140 - 32 - pw
        draw.rounded_rectangle([(px, 680), (px + pw, 744)], radius=32, fill=active_theme.card_bg, outline=(46, 204, 113, 140), width=2)
        draw.ellipse([(px + 18, 706), (px + 32, 720)], fill=(46, 204, 113, 255))
        draw.text((px + 44, 696), pill_text, fill=(46, 204, 113, 255), font=font_badge)

    # 8. Блок 4: Победы в Топ-1 месяца
    draw.rounded_rectangle([(60, 796), (1140, 904)], radius=22, fill=active_theme.box_bg, outline=active_theme.box_border, width=2)
    draw_trophy_icon(draw, 90, 836, color=(241, 196, 15, 255))
    font_reward = get_font(25, bold=True)
    draw.text((124, 832), "Победы в Топ-1 месяца:", fill=(241, 196, 15, 255), font=font_reward)

    font_pill_reward = get_font(23, bold=False)
    # Пилюля побед в войсе
    draw.rounded_rectangle([(550, 820), (810, 880)], radius=16, fill=active_theme.card_bg, outline=active_theme.card_border, width=2)
    draw_mic_icon(draw, 572, 838, color=(148, 155, 164, 255))
    draw.text((606, 834), f"В голосе: {voice_wins}", fill=(219, 222, 225, 255), font=font_pill_reward)

    # Пилюля побед в чате
    draw.rounded_rectangle([(834, 820), (1094, 880)], radius=16, fill=active_theme.card_bg, outline=active_theme.card_border, width=2)
    draw_chat_icon(draw, 856, 842, size=20, color=(148, 155, 164, 255))
    draw.text((890, 834), f"В чате: {chat_wins}", fill=(219, 222, 225, 255), font=font_pill_reward)

    # 9. Футер
    draw.line([(60, 940), (1140, 940)], fill=active_theme.box_border, width=2)
    font_footer = get_font(21, bold=False)
    draw.text((60, 966), f"Аккаунт создан: {created_date_str} • ID: {user_id}", fill=(115, 118, 128, 255), font=font_footer)

    # 10. Верхняя неоновая полоска (статичная или анимированная бегущая волна)
    stripe_h = 10
    strip = create_accent_strip(w, stripe_h, colors=active_theme.accent_colors)

    # Маска скругления для верхних углов карточки (radius 36)
    tcm_full = Image.new("L", (w, h), 0)
    ImageDraw.Draw(tcm_full).rounded_rectangle([(0, 0), (w, h)], radius=36, fill=255)
    top_corner_mask = tcm_full.crop((0, 0, w, stripe_h))

    if not animated:
        bar = strip.crop((0, 0, w, stripe_h))
        card.paste(bar, (0, 0), top_corner_mask)
        buffer = io.BytesIO()
        card.save(buffer, format="PNG")
        buffer.seek(0)
        return buffer

    # Генерация 16-кадрового плавного циклического GIF
    num_frames = 16
    frames = []
    bg_color = (49, 51, 56)  # Цвет темы Discord Dark для бесшовных скругленных углов
    for i in range(num_frames):
        shift_px = int((i / num_frames) * w)
        bar = strip.crop((shift_px, 0, shift_px + w, stripe_h))
        f = card.copy()
        f.paste(bar, (0, 0), top_corner_mask)
        flat = Image.new("RGB", (w, h), bg_color)
        flat.paste(f, (0, 0), f)
        frames.append(flat)

    pal_img = frames[0].convert("P", palette=Image.Palette.ADAPTIVE, colors=256)
    p_frames = [f.quantize(palette=pal_img, dither=Image.Dither.NONE) for f in frames]

    buffer = io.BytesIO()
    p_frames[0].save(
        buffer,
        format="GIF",
        save_all=True,
        append_images=p_frames[1:],
        duration=65,
        loop=0
    )
    buffer.seek(0)
    return buffer
