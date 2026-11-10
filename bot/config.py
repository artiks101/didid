import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Загружаем переменные из .env файла
env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path)


class Config:
    BOT_TOKEN: str = os.getenv("DISCORD_BOT_TOKEN", "").strip()
    
    # ID канала для логов
    raw_channel_id = os.getenv("LOG_CHANNEL_ID", "0").strip()
    try:
        LOG_CHANNEL_ID: int = int(raw_channel_id) if raw_channel_id else 0
    except ValueError:
        LOG_CHANNEL_ID: int = 0

    # ID канала для публикации топов активности участников
    raw_top_channel_id = os.getenv("TOP_CHANNEL_ID", "1566474940465680604").strip()
    try:
        TOP_CHANNEL_ID: int = int(raw_top_channel_id) if raw_top_channel_id else 1566474940465680604
    except ValueError:
        TOP_CHANNEL_ID: int = 1566474940465680604

    # ID канала для объявления победителей топов месяца с @everyone
    raw_rewards_channel_id = os.getenv("REWARDS_NOTIFICATION_CHANNEL_ID", "1479104437954936912").strip()
    try:
        REWARDS_NOTIFICATION_CHANNEL_ID: int = int(raw_rewards_channel_id) if raw_rewards_channel_id else 1479104437954936912
    except ValueError:
        REWARDS_NOTIFICATION_CHANNEL_ID: int = 1479104437954936912

    # Роли за победу в топах месяца (Топ-1 войс и Топ-1 чат)
    raw_voice_role = os.getenv("VOICE_TOP_ROLE_ID", "1566478706422190141").strip()
    try:
        VOICE_TOP_ROLE_ID: int = int(raw_voice_role) if raw_voice_role else 1566478706422190141
    except ValueError:
        VOICE_TOP_ROLE_ID: int = 1566478706422190141

    raw_chat_role = os.getenv("CHAT_TOP_ROLE_ID", "1566479181821247681").strip()
    try:
        CHAT_TOP_ROLE_ID: int = int(raw_chat_role) if raw_chat_role else 1566479181821247681
    except ValueError:
        CHAT_TOP_ROLE_ID: int = 1566479181821247681

    # ID AFK канала (время нахождения в котором нигде не учитывается)
    raw_afk_channel_id = os.getenv("AFK_CHANNEL_ID", "1546888695116996618").strip()
    try:
        AFK_CHANNEL_ID: int = int(raw_afk_channel_id) if raw_afk_channel_id else 1546888695116996618
    except ValueError:
        AFK_CHANNEL_ID: int = 1546888695116996618

    # ID конкретного сервера (если задан)
    raw_guild_id = os.getenv("GUILD_ID", "").strip()
    try:
        GUILD_ID: int | None = int(raw_guild_id) if raw_guild_id else None
    except ValueError:
        GUILD_ID: int | None = None

    # Логировать ли ботов с правами администратора
    LOG_BOTS: bool = os.getenv("LOG_BOTS", "False").strip().lower() in ("true", "1", "yes")

    @classmethod
    def validate(cls) -> list[str]:
        errors = []
        if not cls.BOT_TOKEN or cls.BOT_TOKEN == "your_bot_token_here":
            errors.append("Не указан DISCORD_BOT_TOKEN в файле .env")
        if not cls.LOG_CHANNEL_ID or cls.LOG_CHANNEL_ID <= 0:
            errors.append("Не указан или некорректен LOG_CHANNEL_ID в файле .env (должен быть числовой ID канала)")
        return errors

