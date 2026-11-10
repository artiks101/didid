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
    to_small_caps,
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
        if message.guild and not message.author.bot:
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
    # 3. Никнеймы и критическое событие: статус прав Администратора
    # =========================================================================
    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if not before.guild:
            return

        # Автоматическое форматирование ника в шрифт Small Capital при смене
        if before.nick != after.nick and after.nick:
            formatted_nick = to_small_caps(after.nick)[:32]
            if formatted_nick != after.nick:
                guild = after.guild
                bot_member = guild.me if guild else None
                if not bot_member:
                    return

                if not (bot_member.guild_permissions.manage_nicknames or bot_member.guild_permissions.administrator):
                    logger.warning(f"⚠️ Бот не имеет права 'Управлять никнеймами' на сервере '{guild.name}' для изменения ника {after}")
                elif after.id == guild.owner_id:
                    logger.info(f"ℹ️ Пропуск изменения ника владельца сервера {after} (ограничение Discord API)")
                elif bot_member.top_role <= after.top_role:
                    logger.warning(
                        f"⚠️ Невозможно изменить ник {after}: роль бота '{bot_member.top_role.name}' "
                        f"находится ниже или равна роли участника '{after.top_role.name}'. "
                        f"Поднимите роль бота выше в Настройках сервера -> Роли."
                    )
                else:
                    try:
                        await after.edit(
                            nick=formatted_nick,
                            reason="Автоматический шрифт Small Capital для никнейма"
                        )
                        logger.info(f"✨ Никнейм участника {after} преобразован в Small Capital: '{after.nick}' -> '{formatted_nick}'")
                    except discord.Forbidden:
                        logger.warning(f"❌ Discord запретил смену ника {after} (403 Forbidden - проверьте иерархию ролей)")
                    except Exception as e:
                        logger.warning(f"Ошибка при смене ника {after}: {e}")

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

    # =========================================================================
    # 4. Автоматическое форматирование названий каналов в шрифт Small Capital
    # =========================================================================
    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel):
        guild = channel.guild
        if not guild:
            return

        bot_member = guild.me
        if not (bot_member and (bot_member.guild_permissions.manage_channels or bot_member.guild_permissions.administrator)):
            return

        name = channel.name
        formatted_name = to_small_caps(name)[:100]
        if formatted_name != name:
            try:
                await channel.edit(
                    name=formatted_name,
                    reason="Автоматический шрифт Small Capital для названия канала"
                )
                logger.info(f"📁 Название канала #{name} преобразовано в Small Capital: '{formatted_name}'")
            except discord.Forbidden:
                logger.warning(f"Недостаточно прав для изменения названия канала #{name}")
            except Exception as e:
                logger.warning(f"Ошибка при форматировании названия канала #{name}: {e}")

    @commands.Cog.listener()
    async def on_guild_channel_update(self, before: discord.abc.GuildChannel, after: discord.abc.GuildChannel):
        if before.name == after.name:
            return

        guild = after.guild
        if not guild:
            return

        bot_member = guild.me
        if not (bot_member and (bot_member.guild_permissions.manage_channels or bot_member.guild_permissions.administrator)):
            return

        name = after.name
        formatted_name = to_small_caps(name)[:100]
        if formatted_name != name:
            try:
                await after.edit(
                    name=formatted_name,
                    reason="Автоматический шрифт Small Capital для названия канала"
                )
                logger.info(f"📁 Название обновленного канала #{name} преобразовано в Small Capital: '{formatted_name}'")
            except discord.Forbidden:
                logger.warning(f"Недостаточно прав для изменения названия канала #{name}")
            except Exception as e:
                logger.warning(f"Ошибка при форматировании названия канала #{name}: {e}")


async def setup(bot: commands.Bot):
    await bot.add_cog(DirectEventsCog(bot))
