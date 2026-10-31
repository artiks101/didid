import asyncio
import logging
import sys
from pathlib import Path

# Обеспечиваем поддержку UTF-8 и emoji в Windows консоли
if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import discord
from discord.ext import commands

# Добавляем корневую директорию проекта в sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from bot.config import Config

# Настройка логирования в консоль
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("bot.main")


def acquire_single_instance_lock():
    """Предотвращает одновременный запуск двух копий бота."""
    if sys.platform == "win32":
        try:
            import msvcrt
            lock_path = root_dir / ".bot.lock"
            f = open(lock_path, "w")
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
            return f
        except (IOError, OSError):
            logger.error("❌ ВНИМАНИЕ: Другая копия бота уже запущена!")
            logger.error("   Пожалуйста, закройте предыдущее окно консоли перед запуском.")
            input("\nНажмите Enter для выхода...")
            sys.exit(1)
    return None

_lock_handle = acquire_single_instance_lock()

# Настройка Intents
intents = discord.Intents.default()
intents.members = True          # Отслеживание участников и прав
intents.message_content = True  # Чтение текста сообщений при редактировании/удалении
intents.guilds = True           # Информация о серверах и каналах
intents.voice_states = True     # Отслеживание голосовых каналов
if hasattr(intents, "moderation"):
    intents.moderation = True   # Аудит и модерация (discord.py >= 2.0)

bot = commands.Bot(
    command_prefix="!",
    intents=intents,
    help_command=None
)


@bot.event
async def on_ready():
    logger.info("=" * 60)
    logger.info(f"✅ Бот успешно авторизован как: {bot.user} (ID: {bot.user.id})")
    logger.info(f"🌐 Серверов подключено: {len(bot.guilds)}")

    # Проверка канала логов
    channel = bot.get_channel(Config.LOG_CHANNEL_ID)
    if channel:
        logger.info(f"📢 Канал для логов найден: #{channel.name} (ID: {channel.id}) на сервере '{channel.guild.name}'")
        perms = channel.permissions_for(channel.guild.me)
        if not perms.send_messages or not perms.embed_links:
            logger.warning("⚠️ ВНИМАНИЕ: У бота нет прав 'Send Messages' или 'Embed Links' в канале логов!")
    else:
        logger.warning(
            f"⚠️ Канал логов с ID {Config.LOG_CHANNEL_ID} не найден в кэше бота!\n"
            f"   Убедитесь, что ID указан верно в .env и бот добавлен на соответствующий сервер."
        )

    # Установка статуса
    activity = discord.Activity(
        type=discord.ActivityType.watching,
        name="за действиями администраторов"
    )
    await bot.change_presence(status=discord.Status.online, activity=activity)

    # Мгновенная регистрация слэш-команд на серверах
    for guild in bot.guilds:
        try:
            bot.tree.copy_global_to(guild=guild)
            synced = await bot.tree.sync(guild=guild)
            logger.info(f"⚡ Слэш-команды мгновенно зарегистрированы на '{guild.name}': {len(synced)}")
        except Exception as e:
            logger.warning(f"Ошибка регистрации слэш-команд на '{guild.name}': {e}")

    try:
        await bot.tree.sync()
    except Exception:
        pass

    logger.info("🛡️ Модули логирования активированы и готовы к работе.")
    logger.info("=" * 60)


async def main():
    errors = Config.validate()
    if errors:
        logger.error("❌ Ошибки конфигурации:")
        for err in errors:
            logger.error(f"  • {err}")
        logger.info("\nПожалуйста, заполните параметры в файле .env перед запуском.")
        return

    # Загружаем коги (модули)
    initial_extensions = [
        "bot.cogs.audit_logs",
        "bot.cogs.direct_events",
        "bot.cogs.status",
    ]

    for ext in initial_extensions:
        try:
            await bot.load_extension(ext)
            logger.info(f"Загружен модуль: {ext}")
        except Exception as e:
            logger.exception(f"Не удалось загрузить модуль {ext}: {e}")

    try:
        await bot.start(Config.BOT_TOKEN)
    except discord.LoginFailure:
        logger.error("❌ Ошибка авторизации: указан неверный DISCORD_BOT_TOKEN в файле .env.")
    except Exception as e:
        logger.exception(f"❌ Критическая ошибка при работе бота: {e}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем.")
