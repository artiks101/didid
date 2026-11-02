import io
from pathlib import Path
from typing import Optional
from PIL import Image, ImageDraw, ImageFont

FONTS_DIR = Path(__file__).resolve().parent / "assets" / "fonts"


def get_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    font_name = "segoeuib.ttf" if bold else "segoeui.ttf"
    font_path = FONTS_DIR / font_name
    if not font_path.exists():
        font_path = FONTS_DIR / ("arialbd.ttf" if bold else "arial.ttf")
    try:
        return ImageFont.truetype(str(font_path), size)
    except Exception:
        return ImageFont.load_default()


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
    avatar_bytes: Optional[bytes] = None
) -> io.BytesIO:
    """Генерирует графическую карточку профиля участника в стиле Figma/Discord."""
    width, height = 600, 520
    card = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(card)

    # 1. Основной фон карточки с закругленными углами
    draw.rounded_rectangle([(0, 0), (width, height)], radius=20, fill=(35, 36, 40, 255), outline=(51, 53, 59, 255), width=2)

    # 2. Верхний баннер с мягким градиентом
    banner_height = 110
    banner = Image.new("RGBA", (width, banner_height), (0, 0, 0, 0))
    b_draw = ImageDraw.Draw(banner)
    for y in range(banner_height):
        ratio = y / banner_height
        r = int(43 * (1 - ratio) + 24 * ratio)
        g = int(45 * (1 - ratio) + 25 * ratio)
        b = int(49 * (1 - ratio) + 28 * ratio)
        b_draw.line([(0, y), (width, y)], fill=(r, g, b, 255))
    card.paste(banner, (0, 0), banner)

    # Радужная акцентная полоска на самом верху баннера (5px)
    accent_bar = Image.new("RGBA", (width, 5), (0, 0, 0, 0))
    a_draw = ImageDraw.Draw(accent_bar)
    for x in range(width):
        ratio = x / width
        if ratio < 0.5:
            sub = ratio / 0.5
            r = int(46 * (1 - sub) + 52 * sub)
            g = int(204 * (1 - sub) + 152 * sub)
            b = int(113 * (1 - sub) + 219 * sub)
        else:
            sub = (ratio - 0.5) / 0.5
            r = int(52 * (1 - sub) + 155 * sub)
            g = int(152 * (1 - sub) + 89 * sub)
            b = int(219 * (1 - sub) + 182 * sub)
        a_draw.line([(x, 0), (x, 5)], fill=(r, g, b, 255))
    card.paste(accent_bar, (0, 0), accent_bar)

    # 3. Аватарка участника
    av_x, av_y, av_r = 75, 110, 45
    rendered_avatar = False
    if avatar_bytes:
        try:
            av_img = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA")
            av_img = av_img.resize((av_r * 2, av_r * 2), Image.Resampling.LANCZOS)
            mask = Image.new("L", (av_r * 2, av_r * 2), 0)
            m_draw = ImageDraw.Draw(mask)
            m_draw.ellipse([(0, 0), (av_r * 2, av_r * 2)], fill=255)
            card.paste(av_img, (av_x - av_r, av_y - av_r), mask)
            rendered_avatar = True
        except Exception:
            rendered_avatar = False

    if not rendered_avatar:
        draw.ellipse([(av_x - av_r, av_y - av_r), (av_x + av_r, av_y + av_r)], fill=(241, 196, 15, 255))
        draw.ellipse([(av_x - 14, av_y - 8), (av_x - 6, av_y)], fill=(30, 31, 34, 255))
        draw.ellipse([(av_x + 6, av_y - 8), (av_x + 14, av_y)], fill=(30, 31, 34, 255))
        draw.arc([(av_x - 18, av_y + 2), (av_x + 18, av_y + 22)], 0, 180, fill=(30, 31, 34, 255), width=4)

    # Внешняя рамка аватарки
    draw.ellipse([(av_x - av_r, av_y - av_r), (av_x + av_r, av_y + av_r)], outline=(35, 36, 40, 255), width=6)

    # Точка онлайн-статуса
    dot_x, dot_y, dot_r = av_x + 30, av_y + 30, 12
    draw.ellipse([(dot_x - dot_r, dot_y - dot_r), (dot_x + dot_r, dot_y + dot_r)], fill=(46, 204, 113, 255), outline=(35, 36, 40, 255), width=4)

    # 4. Бейджи ролей (в правом верхнем углу)
    badge_x = 570
    font_badge = get_font(12, bold=True)
    if roles:
        for r_name, r_color in reversed(roles[:2]):
            t_w = int(draw.textlength(r_name, font=font_badge))
            b_w = t_w + 24
            badge_x -= b_w
            draw.rounded_rectangle([(badge_x, 122), (badge_x + b_w, 152)], radius=15, fill=(43, 45, 49, 255), outline=r_color, width=1)
            draw.text((badge_x + 12, 130), r_name, fill=r_color, font=font_badge)
            badge_x -= 10

    # 5. Имя пользователя и бейдж "УЧАСТНИК"
    font_name = get_font(22, bold=True)
    # Обрезаем очень длинные ники, чтобы не вылезали
    clean_name = display_name if len(display_name) <= 18 else display_name[:17] + "…"
    draw.text((30, 172), clean_name, fill=(255, 255, 255, 255), font=font_name)
    name_w = int(draw.textlength(clean_name, font=font_name))

    pill_x = 30 + name_w + 12
    font_pill = get_font(10, bold=True)
    draw.rounded_rectangle([(pill_x, 176), (pill_x + 78, 198)], radius=5, fill=(88, 101, 242, 255))
    draw.text((pill_x + 9, 180), "УЧАСТНИК", fill=(255, 255, 255, 255), font=font_pill)

    # Никнейм / тег и ID
    font_sub = get_font(12, bold=False)
    draw.text((30, 204), f"@{handle} • ID: {user_id}", fill=(148, 155, 164, 255), font=font_sub)

    # 6. Блок 1: На сервере
    draw.rounded_rectangle([(30, 230), (290, 298)], radius=14, fill=(30, 31, 34, 255), outline=(46, 48, 53, 255), width=1)
    font_label = get_font(11, bold=True)
    draw.text((46, 242), "📅 НА СЕРВЕРЕ", fill=(148, 155, 164, 255), font=font_label)
    font_val = get_font(17, bold=True)
    draw.text((46, 264), f"{days_on_server} дн.", fill=(255, 255, 255, 255), font=font_val)
    days_w = int(draw.textlength(f"{days_on_server} дн.", font=font_val))
    draw.text((46 + days_w + 8, 268), f"({join_date_str})", fill=(148, 155, 164, 255), font=font_sub)

    # Блок 2: Сообщения
    draw.rounded_rectangle([(310, 230), (570, 298)], radius=14, fill=(30, 31, 34, 255), outline=(46, 48, 53, 255), width=1)
    draw.text((326, 242), "💬 СООБЩЕНИЯ", fill=(148, 155, 164, 255), font=font_label)
    draw.text((326, 264), f"{msg_count} сообщений", fill=(255, 255, 255, 255), font=font_val)

    # 7. Блок 3: Время в голосовых (Главная карточка)
    draw.rounded_rectangle([(30, 310), (570, 390)], radius=14, fill=(30, 31, 34, 255), outline=(46, 204, 113, 255), width=2)
    font_voice_title = get_font(12, bold=True)
    draw.text((46, 322), "🎙️ ВРЕМЯ В ГОЛОСОВЫХ КАНАЛАХ", fill=(46, 204, 113, 255), font=font_voice_title)
    if avg_voice_str:
        draw.text((320, 322), f"⏱️ В среднем: {avg_voice_str}", fill=(148, 155, 164, 255), font=font_sub)

    font_voice_val = get_font(21, bold=True)
    draw.text((46, 348), voice_str, fill=(255, 255, 255, 255), font=font_voice_val)

    if current_voice_str:
        # Бейдж текущего войса / AFK
        draw.rounded_rectangle([(315, 344), (555, 376)], radius=16, fill=(35, 36, 40, 255), outline=(46, 204, 113, 120), width=1)
        draw.ellipse([(328, 356), (336, 364)], fill=(46, 204, 113, 255))
        # Ограничиваем длину названия канала в бейдже
        c_text = current_voice_str if len(current_voice_str) <= 24 else current_voice_str[:23] + "…"
        draw.text((344, 351), c_text, fill=(46, 204, 113, 255), font=font_badge)

    # 8. Блок 4: Победы в Топ-1 месяца
    draw.rounded_rectangle([(30, 402), (570, 456)], radius=12, fill=(30, 31, 34, 255), outline=(46, 48, 53, 255), width=1)
    font_reward = get_font(13, bold=True)
    draw.text((46, 422), "🏆 Победы в Топ-1 месяца:", fill=(241, 196, 15, 255), font=font_reward)

    # Пилюля побед в войсе
    draw.rounded_rectangle([(270, 414), (395, 444)], radius=8, fill=(35, 36, 40, 255), outline=(51, 53, 59, 255), width=1)
    draw.text((282, 421), f"🎙️ В голосе: {voice_wins}", fill=(219, 222, 225, 255), font=font_sub)

    # Пилюля побед в чате
    draw.rounded_rectangle([(410, 414), (535, 444)], radius=8, fill=(35, 36, 40, 255), outline=(51, 53, 59, 255), width=1)
    draw.text((422, 421), f"💬 В чате: {chat_wins}", fill=(219, 222, 225, 255), font=font_sub)

    # 9. Футер
    draw.line([(30, 474), (570, 474)], fill=(46, 48, 53, 255), width=1)
    font_footer = get_font(11, bold=False)
    draw.text((30, 488), f"Аккаунт создан: {created_date_str} • ID: {user_id}", fill=(109, 111, 120, 255), font=font_footer)

    buffer = io.BytesIO()
    card.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer
