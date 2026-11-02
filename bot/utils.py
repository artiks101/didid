import json
import sqlite3
import time
from collections import OrderedDict
from pathlib import Path
from typing import Optional, Union, Any
import discord
from bot.config import Config

DB_FILE = Path(__file__).resolve().parent.parent / "messages.db"


class LogColors:
    RED = 0xE74C3C       # Удаление, бан, кик, снятие прав
    GREEN = 0x2ECC71     # Создание, разбан, выдача прав
    YELLOW = 0xF1C40F    # Изменение, таймаут, редактирование
    BLUE = 0x3498DB      # Инфо, каналы, голосовые
    PURPLE = 0x9B59B6    # Настройки сервера, роли


# Права, которые определяют принадлежность к модераторам/администраторам
STAFF_PERMISSIONS: set[str] = {
    "administrator",
    "manage_guild",
    "manage_roles",
    "manage_channels",
    "manage_messages",
    "manage_threads",
    "manage_webhooks",
    "kick_members",
    "ban_members",
    "moderate_members",
    "view_audit_log",
    "mute_members",
    "deafen_members",
    "move_members",
    "priority_speaker",
}

# Полный словарь переводов прав Discord на русский язык
PERMISSION_NAMES_RU: dict[str, str] = {
    "administrator": "Администратор (полный доступ)",
    "view_channel": "Просмотр канала",
    "send_messages": "Отправка сообщений",
    "send_messages_in_threads": "Отправка сообщений в ветках",
    "create_public_threads": "Создание публичных веток",
    "create_private_threads": "Создание приватных веток",
    "embed_links": "Встраивание ссылок",
    "attach_files": "Прикрепление файлов",
    "add_reactions": "Добавление реакций",
    "use_external_emojis": "Внешние эмодзи",
    "use_external_stickers": "Внешние стикеры",
    "mention_everyone": "Упоминание @everyone / @here",
    "manage_messages": "Управление сообщениями",
    "manage_threads": "Управление ветками",
    "read_message_history": "Чтение истории сообщений",
    "send_tts_messages": "Отправка TTS сообщений",
    "use_application_commands": "Команды приложений",
    "manage_channels": "Управление каналами",
    "manage_roles": "Управление ролями",
    "manage_permissions": "Управление правами доступа",
    "manage_webhooks": "Управление вебхуками",
    "manage_guild": "Управление сервером",
    "kick_members": "Исключение участников (Кик)",
    "ban_members": "Блокировка участников (Бан)",
    "moderate_members": "Таймаут участников",
    "connect": "Подключение (голосовой канал)",
    "speak": "Разговор (голосовой канал)",
    "stream": "Видео / Стрим",
    "mute_members": "Отключение микрофона участникам",
    "deafen_members": "Отключение звука участникам",
    "move_members": "Перемещение участников",
    "priority_speaker": "Приоритетный спикер",
    "request_to_speak": "Запрос слова (трибуна)",
    "send_polls": "Создание опросов",
    "bypass_slowmode": "Обход медленного режима",
    "change_nickname": "Изменение никнейма",
    "manage_nicknames": "Управление никнеймами",
    "create_instant_invite": "Создание приглашений",
}


class PersistentMessageCache:
    """Энергонезависимый кэш сообщений на базе SQLite, сохраняющийся между перезапусками бота."""

    def __init__(self, db_path: Path = DB_FILE, max_age_days: int = 14):
        self.db_path = str(db_path)
        self.max_age_days = max_age_days
        self._init_db()

    def _init_db(self):
        try:
            with sqlite3.connect(self.db_path, timeout=10.0) as conn:
                conn.execute("PRAGMA journal_mode = WAL")
                conn.execute("PRAGMA synchronous = NORMAL")
                conn.execute("PRAGMA busy_timeout = 5000")
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS messages (
                        id INTEGER PRIMARY KEY,
                        channel_id INTEGER,
                        author_id INTEGER,
                        author_name TEXT,
                        content TEXT,
                        attachments TEXT,
                        created_at REAL
                    )
                """)
                conn.execute("CREATE INDEX IF NOT EXISTS idx_chan_auth ON messages(channel_id, author_id)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_time ON messages(created_at)")
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS recent_deletions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        message_id INTEGER,
                        channel_id INTEGER,
                        author_id INTEGER,
                        content TEXT,
                        attachments TEXT,
                        deleted_at REAL
                    )
                """)
                # Автоочистка старых данных (старше 14 дней)
                cutoff = time.time() - (self.max_age_days * 86400)
                conn.execute("DELETE FROM messages WHERE created_at < ?", (cutoff,))
                conn.execute("DELETE FROM recent_deletions WHERE deleted_at < ?", (time.time() - 300,))
                conn.commit()
        except Exception:
            pass

    def add(self, message: discord.Message):
        if not message.guild:
            return
        attachments_json = json.dumps([a.url for a in message.attachments])
        created_ts = message.created_at.timestamp() if message.created_at else time.time()
        try:
            with sqlite3.connect(self.db_path, timeout=5.0) as conn:
                conn.execute("PRAGMA busy_timeout = 5000")
                conn.execute(
                    "INSERT OR REPLACE INTO messages VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (message.id, message.channel.id, message.author.id, str(message.author), message.content or "", attachments_json, created_ts)
                )
        except Exception:
            pass

    def on_delete(self, message: discord.Message) -> dict:
        content = message.content or ""
        attachments = [a.url for a in message.attachments] if message.attachments else []
        author_id = message.author.id if message.author else 0

        # Если сообщение не было в памяти Discord, восстанавливаем из SQLite
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT content, attachments, author_id FROM messages WHERE id = ?", (message.id,))
                row = cursor.fetchone()
                if row:
                    if not content and row[0]:
                        content = row[0]
                    if not attachments and row[1]:
                        attachments = json.loads(row[1])
                    if not author_id and row[2]:
                        author_id = row[2]

                now = time.time()
                conn.execute(
                    "INSERT INTO recent_deletions (message_id, channel_id, author_id, content, attachments, deleted_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (message.id, message.channel.id, author_id, content, json.dumps(attachments), now)
                )
                conn.commit()
        except Exception:
            pass

        return {
            "message_id": message.id,
            "channel_id": message.channel.id,
            "author_id": author_id,
            "content": content,
            "attachments": attachments,
            "deleted_at": time.time(),
        }

    def pop_recent_deletion(self, channel_id: int, author_id: int) -> Optional[dict]:
        now = time.time()
        res = None
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """SELECT id, message_id, content, attachments FROM recent_deletions
                       WHERE channel_id = ? AND (author_id = ? OR author_id = 0) AND (? - deleted_at < 60)
                       ORDER BY deleted_at DESC LIMIT 1""",
                    (channel_id, author_id, now)
                )
                row = cursor.fetchone()
                if row:
                    del_id, msg_id, content, att_json = row
                    attachments = json.loads(att_json) if att_json else []
                    res = {"message_id": msg_id, "content": content, "attachments": attachments}
                    conn.execute("DELETE FROM recent_deletions WHERE id = ?", (del_id,))
                    conn.commit()
                else:
                    cursor.execute(
                        """SELECT id, content, attachments FROM messages
                           WHERE channel_id = ? AND author_id = ?
                           ORDER BY created_at DESC LIMIT 1""",
                        (channel_id, author_id)
                    )
                    row = cursor.fetchone()
                    if row:
                        msg_id, content, att_json = row
                        attachments = json.loads(att_json) if att_json else []
                        res = {"message_id": msg_id, "content": content, "attachments": attachments}
        except Exception:
            pass
        return res

    def get_count(self) -> int:
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM messages")
                row = cursor.fetchone()
                return row[0] if row else 0
        except Exception:
            return 0


# Глобальный экземпляр энергонезависимого кэша
message_cache = PersistentMessageCache()


class ShowMessageContentView(discord.ui.View):
    """Интерактивная кнопка для показа полного текста удаленного сообщения."""

    def __init__(self, content: str, attachments: list[str] = None):
        super().__init__(timeout=None)
        self.content = content or "*[Сообщение не содержало текста]*"
        self.attachments = attachments or []

    @discord.ui.button(label="Показать текст сообщения", style=discord.ButtonStyle.secondary, emoji="👁️")
    async def show_content(self, interaction: discord.Interaction, button: discord.ui.Button):
        text = self.content
        msg = f"**Содержимое удаленного сообщения:**\n>>> {text}"
        if self.attachments:
            att_text = "\n".join([f"• {url}" for url in self.attachments])
            msg += f"\n\n**Вложения:**\n{att_text}"
        await interaction.response.send_message(msg[:2000], ephemeral=True)


def format_spoiler(text: str, max_len: int = 800) -> str:
    """Форматирует текст под спойлер (раскрывается по клику)."""
    if not text:
        return "*[Пустое сообщение]*"
    # Экранируем двойные черты, чтобы не ломать спойлер
    clean = text.replace("||", "\\|\\|")
    if len(clean) > max_len:
        clean = clean[:max_len] + "..."
    return f"||{clean}||"


def check_member_privileged(member: discord.Member) -> bool:
    """Проверяет, обладает ли участник административными или модераторскими правами через любые свои роли."""
    if member.id == member.guild.owner_id:
        return True
    perms = member.guild_permissions
    if perms.administrator:
        return True
    return any(getattr(perms, p, False) for p in STAFF_PERMISSIONS)


async def is_admin(guild: discord.Guild, user_or_member: Optional[Union[discord.User, discord.Member]]) -> bool:
    """
    Проверяет, обладает ли пользователь администраторскими или модераторскими правами
    (напрямую или через выданные роли на управление, удаление, модерацию).
    """
    if not user_or_member or not guild:
        return False

    if user_or_member.bot and not Config.LOG_BOTS:
        return False

    if user_or_member.id == guild.owner_id:
        return True

    member = user_or_member if isinstance(user_or_member, discord.Member) else guild.get_member(user_or_member.id)
    if not member:
        try:
            member = await guild.fetch_member(user_or_member.id)
        except (discord.NotFound, discord.HTTPException):
            return False

    return check_member_privileged(member)


def get_actor_role_label(actor: Optional[Union[discord.User, discord.Member]], guild: Optional[discord.Guild] = None) -> str:
    """Определяет понятный статус пользователя: Администратор или Модератор."""
    if not actor:
        return "Администратор / Модератор"
    if guild and actor.id == guild.owner_id:
        return "Владелец сервера"
    if isinstance(actor, discord.Member):
        if actor.guild_permissions.administrator:
            return "Администратор"
        return "Модератор"
    return "Модератор"


def format_user(user: Optional[Union[discord.User, discord.Member]]) -> str:
    """Форматирует пользователя с упоминанием, именем и ID."""
    if not user:
        return "`Неизвестно`"
    return f"{user.mention} (**{user.name}** | ID: `{user.id}`)"


def format_channel(channel: Optional[Union[discord.abc.GuildChannel, discord.Thread, discord.Object]]) -> str:
    """Форматирует канал или тред с упоминанием и ID."""
    if not channel:
        return "`Неизвестный канал`"
    if hasattr(channel, "mention"):
        return f"{channel.mention} (`#{getattr(channel, 'name', 'канал')}` | ID: `{channel.id}`)"
    return f"`ID: {channel.id}`"


def format_role(role: Optional[Union[discord.Role, discord.Object]]) -> str:
    """Форматирует роль с упоминанием и ID."""
    if not role:
        return "`Неизвестная роль`"
    if isinstance(role, discord.Role):
        return f"{role.mention} (**{role.name}** | ID: `{role.id}`)"
    return f"`ID: {role.id}`"


def build_embed(
    title: str,
    color: int,
    actor: Optional[Union[discord.User, discord.Member]] = None,
    description: str = "",
    fields: Optional[list[tuple[str, str, bool]]] = None,
    footer_text: str = "",
    reason: Optional[str] = None,
    guild: Optional[discord.Guild] = None,
) -> discord.Embed:
    """Создает красиво оформленный Embed для логов."""
    embed = discord.Embed(
        title=title,
        description=description,
        color=color,
        timestamp=discord.utils.utcnow()
    )

    if actor:
        avatar_url = actor.display_avatar.url if hasattr(actor, "display_avatar") else None
        role_label = get_actor_role_label(actor, guild)
        embed.set_author(
            name=f"{role_label}: {actor.name} ({actor.id})",
            icon_url=avatar_url
        )

    if fields:
        for name, value, inline in fields:
            if value:
                embed.add_field(name=name, value=value[:1024], inline=inline)

    # Причину добавляем ТОЛЬКО если она явно указана
    if reason and reason.strip() and reason.strip().lower() not in ("не указана", "none"):
        embed.add_field(name="Причина", value=f"`{reason.strip()}`", inline=False)

    footer = "Security & Moderation Logger"
    if footer_text:
        footer = f"{footer} • {footer_text}"
    embed.set_footer(text=footer)

    return embed
