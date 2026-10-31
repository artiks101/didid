import time
from collections import OrderedDict
from typing import Optional, Union, Any
import discord
from bot.config import Config


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


class MessageCache:
    """Кэш сообщений для сохранения текста удаленных сообщений."""

    def __init__(self, max_size: int = 5000):
        self.max_size = max_size
        self._cache: OrderedDict[int, dict] = OrderedDict()
        self._recent_deletions: list[dict] = []

    def add(self, message: discord.Message):
        if not message.guild:
            return
        self._cache[message.id] = {
            "id": message.id,
            "channel_id": message.channel.id,
            "author_id": message.author.id,
            "author_name": str(message.author),
            "content": message.content or "",
            "attachments": [a.url for a in message.attachments],
            "created_at": message.created_at,
        }
        if len(self._cache) > self.max_size:
            self._cache.popitem(last=False)

    def on_delete(self, message: discord.Message) -> dict:
        cached = self._cache.pop(message.id, None)
        content = message.content if message.content else (cached["content"] if cached else "")
        attachments = (
            [a.url for a in message.attachments]
            if message.attachments
            else (cached["attachments"] if cached else [])
        )
        author_id = message.author.id if message.author else (cached["author_id"] if cached else 0)

        entry = {
            "message_id": message.id,
            "channel_id": message.channel.id,
            "author_id": author_id,
            "content": content,
            "attachments": attachments,
            "deleted_at": time.time(),
        }
        self._recent_deletions.append(entry)

        # Очищаем записи старше 60 секунд
        now = time.time()
        self._recent_deletions = [d for d in self._recent_deletions if now - d["deleted_at"] < 60]
        return entry

    def pop_recent_deletion(self, channel_id: int, author_id: int) -> Optional[dict]:
        now = time.time()
        candidates = [
            d
            for d in self._recent_deletions
            if d["channel_id"] == channel_id
            and (author_id == 0 or d["author_id"] == author_id)
            and now - d["deleted_at"] < 35
        ]
        if candidates:
            res = candidates[-1]
            try:
                self._recent_deletions.remove(res)
            except ValueError:
                pass
            return res
        return None


# Глобальный экземпляр кэша сообщений
message_cache = MessageCache()


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
