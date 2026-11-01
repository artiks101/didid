import logging
from typing import Optional
import discord
from discord.ext import commands

from bot.config import Config
from bot.utils import (
    LogColors,
    is_admin,
    format_user,
    format_channel,
    format_spoiler,
    build_embed,
    get_actor_role_label,
    message_cache,
    ShowMessageContentView,
)

logger = logging.getLogger("bot.cogs.direct_events")


class DirectEventsCog(commands.Cog):
    """Прямые действия администраторов и модераторов на сервере (сообщения, голос, статус прав)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _get_log_channel(self, guild: discord.Guild) -> Optional[discord.TextChannel]:
        """Возвращает канал для отправки логов."""
        if Config.GUILD_ID and guild.id != Config.GUILD_ID:
            return None

        channel = self.bot.get_channel(Config.LOG_CHANNEL_ID)
        if isinstance(channel, discord.TextChannel):
            return channel
        return None

    # =========================================================================
    # Кэширование всех входящих сообщений для отслеживания удалений
    # =========================================================================
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.guild:
            message_cache.add(message)

    # =========================================================================
    # 1. Редактирование сообщений администратором / модератором
    # =========================================================================
    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if not before.guild or before.author.bot:
            return

        if before.content == after.content:
            return

        if not await is_admin(before.guild, before.author):
            return

        log_channel = self._get_log_channel(before.guild)
        if not log_channel or log_channel.id == before.channel.id:
            return

        actor_label = get_actor_role_label(before.author, before.guild)
        old_text = format_spoiler(before.content) if before.content else "*[Пусто или только вложение]*"
        new_text = format_spoiler(after.content) if after.content else "*[Пусто или только вложение]*"

        embed = build_embed(
            title=f"✏️ {actor_label} отредактировал сообщение",
            color=LogColors.YELLOW,
            actor=before.author,
            fields=[
                ("Канал", format_channel(before.channel), True),
                ("Ссылка на сообщение", f"[Перейти к сообщению]({after.jump_url})", True),
                ("Было (спойлер)", f">>> {old_text}", False),
                ("Стало (спойлер)", f">>> {new_text}", False),
            ],
            footer_text="Событие: MESSAGE_EDIT",
            guild=before.guild,
        )

        view = ShowMessageContentView(after.content) if after.content else None
        try:
            if view:
                await log_channel.send(embed=embed, view=view)
            else:
                await log_channel.send(embed=embed)
        except Exception as e:
            logger.exception(f"Ошибка при отправке лога редактирования: {e}")

    # =========================================================================
    # 2. Удаление сообщения администратора / модератора
    # =========================================================================
    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if not message.guild:
            return

        del_data = message_cache.on_delete(message)

        if message.author.bot:
            return

        if not await is_admin(message.guild, message.author):
            return

        log_channel = self._get_log_channel(message.guild)
        if not log_channel or log_channel.id == message.channel.id:
            return

        actor_label = get_actor_role_label(message.author, message.guild)
        raw_content = message.content or del_data.get("content", "")
        spoiler_content = format_spoiler(raw_content)

        fields = [
            ("Канал", format_channel(message.channel), True),
            ("Текст сообщения (нажмите, чтобы раскрыть)", f">>> {spoiler_content}", False),
        ]

        attachments = (
            [a.url for a in message.attachments]
            if message.attachments
            else del_data.get("attachments", [])
        )
        if attachments:
            att_list = "\n".join([f"• ||[{url.split('/')[-1]}]({url})||" for url in attachments])
            fields.append(("Вложения (спойлер)", att_list[:1024], False))

        embed = build_embed(
            title=f"🗑️ Удалено сообщение ({actor_label.lower()})",
            color=LogColors.RED,
            actor=message.author,
            fields=fields,
            footer_text="Событие: MESSAGE_DELETE",
            guild=message.guild,
        )

        view = ShowMessageContentView(raw_content, attachments)
        try:
            await log_channel.send(embed=embed, view=view)
        except Exception as e:
            logger.exception(f"Ошибка при отправке лога удаления сообщения: {e}")

    # =========================================================================
    # 3. Критическое событие: получение или потеря прав Администратора
    # =========================================================================
    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if not before.guild:
            return

        log_channel = self._get_log_channel(before.guild)
        if not log_channel:
            return

        old_admin = before.guild_permissions.administrator
        new_admin = after.guild_permissions.administrator

        if not old_admin and new_admin:
            embed = build_embed(
                title="🚨 КРИТИЧЕСКАЯ БЕЗОПАСНОСТЬ: ВЫДАНЫ ПРАВА АДМИНИСТРАТОРА",
                color=LogColors.RED,
                actor=after,
                description=f"Участник {format_user(after)} получил полные права **Administrator**!",
                fields=[
                    ("Текущие роли участника", ", ".join([r.mention for r in after.roles[1:]]) or "Нет ролей", False),
                ],
                footer_text="КРИТИЧЕСКИЙ АЛЕРТ: ADMIN_GRANTED",
                guild=before.guild,
            )
            await log_channel.send(embed=embed)

        elif old_admin and not new_admin:
            embed = build_embed(
                title="🛡️ Права администратора сняты",
                color=LogColors.YELLOW,
                actor=after,
                description=f"Участник {format_user(after)} больше не имеет прав **Administrator**.",
                fields=[
                    ("Текущие роли участника", ", ".join([r.mention for r in after.roles[1:]]) or "Нет ролей", False),
                ],
                footer_text="БЕЗОПАСНОСТЬ: ADMIN_REVOKED",
                guild=before.guild,
            )
            await log_channel.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(DirectEventsCog(bot))
