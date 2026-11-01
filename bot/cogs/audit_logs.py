import asyncio
import logging
from datetime import timedelta
from typing import Optional, Tuple
import discord
from discord.ext import commands, tasks
from discord import AuditLogAction

from bot.config import Config
from bot.utils import (
    LogColors,
    is_admin,
    format_user,
    format_channel,
    format_role,
    format_spoiler,
    build_embed,
    get_actor_role_label,
    message_cache,
    ShowMessageContentView,
    PERMISSION_NAMES_RU,
)

logger = logging.getLogger("bot.cogs.audit_logs")


class AuditLogsCog(commands.Cog):
    """Отслеживание действий администраторов и модераторов в журнале аудита (Audit Logs)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.auto_clean_old_logs.start()

    def cog_unload(self):
        self.auto_clean_old_logs.cancel()

    @tasks.loop(hours=1)
    async def auto_clean_old_logs(self):
        """Автоматически удаляет отчеты старше 3 дней в канале логов."""
        channel = self.bot.get_channel(Config.LOG_CHANNEL_ID)
        if not isinstance(channel, discord.TextChannel):
            return

        perms = channel.permissions_for(channel.guild.me)
        if not (perms.read_messages and perms.read_message_history and perms.manage_messages):
            logger.warning(f"Нет прав Manage Messages для автоочистки логов в #{channel.name}")
            return

        now = discord.utils.utcnow()
        cutoff = now - timedelta(days=3)
        fourteen_days_ago = now - timedelta(days=14)

        try:
            # 1. Быстрое удаление пачками сообщений между 3 и 14 днями (Discord Bulk Delete API)
            deleted = await channel.purge(
                limit=500,
                before=cutoff,
                after=fourteen_days_ago,
                bulk=True,
                reason="Автоочистка отчетов старше 3 дней"
            )
            if deleted:
                logger.info(f"🧹 Удалено {len(deleted)} старых отчетов (старше 3 дней) из #{channel.name}")

            # 2. Если в канале остались архивные сообщения старше 14 дней, удаляем по одному
            older_count = 0
            async for old_msg in channel.history(limit=50, before=fourteen_days_ago):
                try:
                    await old_msg.delete()
                    older_count += 1
                    await asyncio.sleep(1.0)
                except (discord.NotFound, discord.Forbidden):
                    break
                except Exception:
                    pass

            if older_count > 0:
                logger.info(f"🧹 Удалено {older_count} архивных сообщений (старше 14 дней) из #{channel.name}")

        except discord.Forbidden:
            logger.warning(f"Нет прав на удаление сообщений в канале логов {channel.id}")
        except Exception as e:
            logger.exception(f"Ошибка при очистке отчетов старше 3 дней: {e}")

    @auto_clean_old_logs.before_loop
    async def before_auto_clean(self):
        await self.bot.wait_until_ready()

    def _get_log_channel(self, guild: discord.Guild) -> Optional[discord.TextChannel]:
        """Возвращает канал для отправки логов."""
        if Config.GUILD_ID and guild.id != Config.GUILD_ID:
            return None

        channel = self.bot.get_channel(Config.LOG_CHANNEL_ID)
        if isinstance(channel, discord.TextChannel):
            return channel
        return None

    @commands.Cog.listener()
    async def on_audit_log_entry_create(self, entry: discord.AuditLogEntry):
        """Срабатывает мгновенно при появлении новой записи в журнале аудита."""
        guild = entry.guild
        if not guild:
            return

        log_channel = self._get_log_channel(guild)
        if not log_channel:
            return

        actor = entry.user
        if actor and actor.bot and not Config.LOG_BOTS:
            return

        # Все действия из журнала аудита по своей природе требуют привилегированных прав на сервере
        # (бан, кик, каналы, роли, права доступа, удаление сообщений, таймаут и т.д.).
        # Проверяем, что автор не отфильтрован
        if actor:
            is_mod = await is_admin(guild, actor)
            # Если автор не имеет глобальных прав модератора, но совершил модераторское действие
            # в канале/ролях благодаря локальным правам, мы все равно логируем!
            if not is_mod and entry.action not in (
                AuditLogAction.kick,
                AuditLogAction.ban,
                AuditLogAction.unban,
                AuditLogAction.member_update,
                AuditLogAction.member_role_update,
                AuditLogAction.role_create,
                AuditLogAction.role_update,
                AuditLogAction.role_delete,
                AuditLogAction.channel_create,
                AuditLogAction.channel_update,
                AuditLogAction.channel_delete,
                AuditLogAction.overwrite_create,
                AuditLogAction.overwrite_update,
                AuditLogAction.overwrite_delete,
                AuditLogAction.message_delete,
                AuditLogAction.message_bulk_delete,
                AuditLogAction.guild_update,
                AuditLogAction.webhook_create,
                AuditLogAction.webhook_update,
                AuditLogAction.webhook_delete,
            ):
                return

        embed, view = await self._create_audit_embed(entry)
        if embed:
            try:
                if view:
                    await log_channel.send(embed=embed, view=view)
                else:
                    await log_channel.send(embed=embed)
            except discord.Forbidden:
                logger.error(f"Нет прав на отправку сообщений в лог-канал {log_channel.id}")
            except Exception as e:
                logger.exception(f"Ошибка при отправке лога аудита: {e}")

    async def _create_audit_embed(
        self, entry: discord.AuditLogEntry
    ) -> Tuple[Optional[discord.Embed], Optional[discord.ui.View]]:
        action = entry.action
        actor = entry.user
        target = entry.target
        reason = entry.reason
        guild = entry.guild
        actor_label = get_actor_role_label(actor, guild)

        # ----------------------------------------------------------------------
        # 1. Кик, бан, разбан
        # ----------------------------------------------------------------------
        if action == AuditLogAction.ban:
            embed = build_embed(
                title=f"⛔ {actor_label} заблокировал участника (Бан)",
                color=LogColors.RED,
                actor=actor,
                fields=[
                    ("Нарушитель", format_user(target), False),
                ],
                footer_text="Действие: BAN",
                reason=reason,
                guild=guild,
            )
            return embed, None

        if action == AuditLogAction.unban:
            embed = build_embed(
                title=f"🔓 {actor_label} разблокировал участника (Разбан)",
                color=LogColors.GREEN,
                actor=actor,
                fields=[
                    ("Пользователь", format_user(target), False),
                ],
                footer_text="Действие: UNBAN",
                reason=reason,
                guild=guild,
            )
            return embed, None

        if action == AuditLogAction.kick:
            embed = build_embed(
                title=f"👢 {actor_label} выгнал участника (Кик)",
                color=LogColors.RED,
                actor=actor,
                fields=[
                    ("Участник", format_user(target), False),
                ],
                footer_text="Действие: KICK",
                reason=reason,
                guild=guild,
            )
            return embed, None

        # ----------------------------------------------------------------------
        # 2. Таймаут (мьют) и обновление участника
        # ----------------------------------------------------------------------
        if action == AuditLogAction.member_update:
            fields = [("Участник", format_user(target), False)]

            if hasattr(entry.after, "timed_out_until"):
                old_timeout = getattr(entry.before, "timed_out_until", None)
                new_timeout = getattr(entry.after, "timed_out_until", None)
                if new_timeout:
                    fields.append(("Действие", "⏳ **Наложен таймаут**", False))
                    fields.append(
                        ("Истекает", f"<t:{int(new_timeout.timestamp())}:F> (<t:{int(new_timeout.timestamp())}:R>)", False)
                    )
                elif old_timeout and not new_timeout:
                    fields.append(("Действие", "🟢 **Таймаут досрочно снят**", False))

            if hasattr(entry.after, "nick"):
                fields.append(("Старый ник", f"`{entry.before.nick or 'По умолчанию'}`", True))
                fields.append(("Новый ник", f"`{entry.after.nick or 'По умолчанию'}`", True))

            if hasattr(entry.after, "mute"):
                state = "заглушен (микрофон)" if entry.after.mute else "микрофон включен"
                fields.append(("Серверный мьют", state, False))
            if hasattr(entry.after, "deaf"):
                state = "заглушен (звук)" if entry.after.deaf else "звук включен"
                fields.append(("Серверный деф", state, False))

            embed = build_embed(
                title=f"👤 {actor_label} обновил участника",
                color=LogColors.YELLOW,
                actor=actor,
                fields=fields,
                footer_text="Действие: MEMBER_UPDATE",
                reason=reason,
                guild=guild,
            )
            return embed, None

        if action == AuditLogAction.automod_timeout_member:
            embed = build_embed(
                title="🤖 Автомодерация: Таймаут участника",
                color=LogColors.RED,
                actor=actor,
                fields=[
                    ("Участник", format_user(target), False),
                ],
                footer_text="Действие: AUTOMOD_TIMEOUT",
                reason=reason,
                guild=guild,
            )
            return embed, None

        # ----------------------------------------------------------------------
        # 3. Назначение и снятие ролей участнику
        # ----------------------------------------------------------------------
        if action == AuditLogAction.member_role_update:
            added_roles = getattr(entry.after, "roles", []) or []
            removed_roles = getattr(entry.before, "roles", []) or []

            fields = [("Целевой участник", format_user(target), False)]
            if added_roles:
                roles_str = ", ".join([format_role(r) for r in added_roles])
                fields.append(("➕ Выданы роли", roles_str, False))
            if removed_roles:
                roles_str = ", ".join([format_role(r) for r in removed_roles])
                fields.append(("➖ Сняты роли", roles_str, False))

            embed = build_embed(
                title=f"🛡️ {actor_label} изменил роли участнику",
                color=LogColors.BLUE,
                actor=actor,
                fields=fields,
                footer_text="Действие: MEMBER_ROLE_UPDATE",
                reason=reason,
                guild=guild,
            )
            return embed, None

        # ----------------------------------------------------------------------
        # 4. Создание, удаление, изменение ролей (с деталями прав)
        # ----------------------------------------------------------------------
        if action == AuditLogAction.role_create:
            embed = build_embed(
                title=f"✨ {actor_label} создал новую роль",
                color=LogColors.GREEN,
                actor=actor,
                fields=[
                    ("Роль", format_role(target), False),
                ],
                footer_text="Действие: ROLE_CREATE",
                reason=reason,
                guild=guild,
            )
            return embed, None

        if action == AuditLogAction.role_delete:
            role_name = getattr(entry.before, "name", "Удаленная роль")
            embed = build_embed(
                title=f"🗑️ {actor_label} удалил роль",
                color=LogColors.RED,
                actor=actor,
                fields=[
                    ("Название удаленной роли", f"**{role_name}**", False),
                ],
                footer_text="Действие: ROLE_DELETE",
                reason=reason,
                guild=guild,
            )
            return embed, None

        if action == AuditLogAction.role_update:
            fields = [("Роль", format_role(target), False)]
            color = LogColors.YELLOW

            b_perm = getattr(entry.before, "permissions", None)
            a_perm = getattr(entry.after, "permissions", None)
            if b_perm and a_perm:
                perm_diffs = []
                if not b_perm.administrator and a_perm.administrator:
                    color = LogColors.RED
                    fields.append(("🚨 ВНИМАНИЕ", "🚨 **РОЛИ ВЫДАНЫ ПРАВА АДМИНИСТРАТОРА (ADMINISTRATOR)** 🚨", False))
                elif b_perm.administrator and not a_perm.administrator:
                    fields.append(("⚠️ ВНИМАНИЕ", "Права администратора сняты с роли", False))

                for flag, name_ru in PERMISSION_NAMES_RU.items():
                    v_before = getattr(b_perm, flag, False)
                    v_after = getattr(a_perm, flag, False)
                    if not v_before and v_after:
                        perm_diffs.append(f"🟢 **Включено**: `{name_ru}`")
                    elif v_before and not v_after:
                        perm_diffs.append(f"🔴 **Отключено**: `{name_ru}`")

                if perm_diffs:
                    fields.append(("Измененные права роли", "\n".join(perm_diffs[:25]), False))

            if hasattr(entry.after, "name"):
                fields.append(("Смена названия", f"`{entry.before.name}` ➔ `{entry.after.name}`", False))
            if hasattr(entry.after, "color") or hasattr(entry.after, "colour"):
                old_c = getattr(entry.before, "colour", getattr(entry.before, "color", None))
                new_c = getattr(entry.after, "colour", getattr(entry.after, "color", None))
                fields.append(("Смена цвета", f"`{old_c}` ➔ `{new_c}`", False))
            if hasattr(entry.after, "hoist"):
                state = "Отображается отдельно" if entry.after.hoist else "Не отображается отдельно"
                fields.append(("Отображение в списке", state, False))
            if hasattr(entry.after, "mentionable"):
                state = "Можно упоминать" if entry.after.mentionable else "Нельзя упоминать"
                fields.append(("Упоминаемость", state, False))

            embed = build_embed(
                title=f"⚙️ {actor_label} изменил настройки роли",
                color=color,
                actor=actor,
                fields=fields,
                footer_text="Действие: ROLE_UPDATE",
                reason=reason,
                guild=guild,
            )
            return embed, None

        # ----------------------------------------------------------------------
        # 5. Каналы (создание, удаление, изменение)
        # ----------------------------------------------------------------------
        if action == AuditLogAction.channel_create:
            embed = build_embed(
                title=f"📁 {actor_label} создал новый канал",
                color=LogColors.GREEN,
                actor=actor,
                fields=[
                    ("Канал", format_channel(target), False),
                    ("Тип", f"`{getattr(target, 'type', 'Канал')}`", True),
                ],
                footer_text="Действие: CHANNEL_CREATE",
                reason=reason,
                guild=guild,
            )
            return embed, None

        if action == AuditLogAction.channel_delete:
            channel_name = getattr(entry.before, "name", "Удаленный канал")
            embed = build_embed(
                title=f"🗑️ {actor_label} удалил канал",
                color=LogColors.RED,
                actor=actor,
                fields=[
                    ("Удаленный канал", f"`#{channel_name}`", False),
                ],
                footer_text="Действие: CHANNEL_DELETE",
                reason=reason,
                guild=guild,
            )
            return embed, None

        if action == AuditLogAction.channel_update:
            fields = [("Канал", format_channel(target), False)]
            if hasattr(entry.after, "name"):
                fields.append(("Смена названия", f"`{entry.before.name}` ➔ `{entry.after.name}`", False))
            if hasattr(entry.after, "topic"):
                fields.append(("Новая тема", f"Было: `{entry.before.topic}`\nСтало: `{entry.after.topic}`", False))
            if hasattr(entry.after, "slowmode_delay"):
                fields.append(("Медленный режим", f"`{entry.before.slowmode_delay} сек.` ➔ `{entry.after.slowmode_delay} сек.`", False))
            if hasattr(entry.after, "nsfw"):
                state = "Включен (18+)" if entry.after.nsfw else "Выключен"
                fields.append(("NSFW режим", state, False))

            embed = build_embed(
                title=f"📝 {actor_label} изменил канал",
                color=LogColors.YELLOW,
                actor=actor,
                fields=fields,
                footer_text="Действие: CHANNEL_UPDATE",
                reason=reason,
                guild=guild,
            )
            return embed, None

        # ----------------------------------------------------------------------
        # 6. Права доступа в каналах (Overwrites) с деталями
        # ----------------------------------------------------------------------
        if action in (AuditLogAction.overwrite_create, AuditLogAction.overwrite_update, AuditLogAction.overwrite_delete):
            extra = entry.extra
            target_str = "`Неизвестно`"
            if isinstance(extra, discord.Role):
                target_str = f"Роль: {format_role(extra)}"
            elif isinstance(extra, (discord.Member, discord.User)):
                target_str = f"Участник: {format_user(extra)}"
            elif extra:
                target_str = f"`ID: {getattr(extra, 'id', extra)}`"

            action_name = {
                AuditLogAction.overwrite_create: f"🔒 {actor_label} создал права в канале",
                AuditLogAction.overwrite_update: f"🔒 {actor_label} изменил права доступа в канале",
                AuditLogAction.overwrite_delete: f"🔒 {actor_label} сбросил права доступа в канале"
            }[action]

            color = LogColors.YELLOW if action == AuditLogAction.overwrite_update else (
                LogColors.GREEN if action == AuditLogAction.overwrite_create else LogColors.RED
            )

            fields = [
                ("Канал", format_channel(target), False),
                ("Для кого", target_str, False),
            ]

            if action == AuditLogAction.overwrite_delete:
                fields.append(("Изменения", "⚪ **Все персональные права сброшены к стандартным для канала**", False))
            elif action == AuditLogAction.overwrite_create:
                created_perms = []
                a_allow = getattr(entry.after, "allow", None)
                a_deny = getattr(entry.after, "deny", None)
                if a_allow:
                    for flag, name_ru in PERMISSION_NAMES_RU.items():
                        if getattr(a_allow, flag, False):
                            created_perms.append(f"🟢 **Разрешено**: `{name_ru}`")
                if a_deny:
                    for flag, name_ru in PERMISSION_NAMES_RU.items():
                        if getattr(a_deny, flag, False):
                            created_perms.append(f"🔴 **Запрещено**: `{name_ru}`")
                if created_perms:
                    fields.append(("Установленные права", "\n".join(created_perms[:25]), False))
            elif action == AuditLogAction.overwrite_update:
                diff_perms = []
                b_allow = getattr(entry.before, "allow", None)
                a_allow = getattr(entry.after, "allow", None)
                b_deny = getattr(entry.before, "deny", None)
                a_deny = getattr(entry.after, "deny", None)

                # Изменения разрешений (allow)
                if a_allow or b_allow:
                    ba = b_allow or discord.Permissions()
                    aa = a_allow or discord.Permissions()
                    for flag, name_ru in PERMISSION_NAMES_RU.items():
                        v_before = getattr(ba, flag, False)
                        v_after = getattr(aa, flag, False)
                        if not v_before and v_after:
                            diff_perms.append(f"🟢 **Разрешено**: `{name_ru}`")
                        elif v_before and not v_after:
                            diff_perms.append(f"⚪ **Сброшено разрешение**: `{name_ru}`")

                # Изменения запретов (deny)
                if a_deny or b_deny:
                    bd = b_deny or discord.Permissions()
                    ad = a_deny or discord.Permissions()
                    for flag, name_ru in PERMISSION_NAMES_RU.items():
                        v_before = getattr(bd, flag, False)
                        v_after = getattr(ad, flag, False)
                        if not v_before and v_after:
                            diff_perms.append(f"🔴 **Запрещено**: `{name_ru}`")
                        elif v_before and not v_after:
                            diff_perms.append(f"⚪ **Сброшен запрет**: `{name_ru}`")

                if diff_perms:
                    fields.append(("Конкретные изменения прав", "\n".join(diff_perms[:25]), False))
                else:
                    fields.append(("Конкретные изменения прав", "*Права были обновлены*", False))

            embed = build_embed(
                title=action_name,
                color=color,
                actor=actor,
                fields=fields,
                footer_text=f"Действие: {action.name.upper()}",
                reason=reason,
                guild=guild,
            )
            return embed, None

        # ----------------------------------------------------------------------
        # 7. Модерация сообщений (удаление чужих сообщений с показом текста)
        # ----------------------------------------------------------------------
        if action == AuditLogAction.message_delete:
            extra = entry.extra
            count = getattr(extra, "count", 1) if extra else 1
            ch = getattr(extra, "channel", None) if extra else None
            if ch and ch.id == Config.LOG_CHANNEL_ID:
                return None, None
            ch_str = format_channel(ch) if ch else "`Неизвестный канал`"

            # Даем паузу 0.3 сек для завершения обработки события on_message_delete
            await asyncio.sleep(0.3)

            target_id = target.id if target else 0
            channel_id = ch.id if ch else 0
            cached_data = message_cache.pop_recent_deletion(channel_id, target_id)

            fields = [
                ("Автор сообщения", format_user(target), True),
                ("Канал", ch_str, True),
                ("Кол-во сообщений", f"`{count}`", True),
            ]

            raw_content = ""
            attachments = []
            if cached_data and (cached_data.get("content") or cached_data.get("attachments")):
                raw_content = cached_data.get("content", "")
                attachments = cached_data.get("attachments", [])

                if raw_content:
                    spoiler_text = format_spoiler(raw_content)
                    fields.append(
                        ("Текст удаленного сообщения (нажмите, чтобы раскрыть)", f">>> {spoiler_text}", False)
                    )
                if attachments:
                    att_list = "\n".join([f"• ||[{url.split('/')[-1]}]({url})||" for url in attachments])
                    fields.append(("Вложения (спойлер)", att_list[:1024], False))
            elif count == 1:
                fields.append(
                    ("Текст сообщения", "*⚠️ Сообщение не было в кэше бота (отправлено до запуска бота)*", False)
                )

            embed = build_embed(
                title=f"🧹 {actor_label} удалил чужое сообщение",
                color=LogColors.RED,
                actor=actor,
                fields=fields,
                footer_text="Действие: MESSAGE_DELETE",
                reason=reason,
                guild=guild,
            )

            view = ShowMessageContentView(raw_content, attachments) if (raw_content or attachments) else None
            return embed, view

        if action == AuditLogAction.message_bulk_delete:
            count = getattr(entry.extra, "count", 0) if entry.extra else 0
            embed = build_embed(
                title=f"💥 {actor_label} произвел массовую очистку сообщений",
                color=LogColors.RED,
                actor=actor,
                fields=[
                    ("Канал", format_channel(target), True),
                    ("Количество удаленных сообщений", f"`{count}`", True),
                ],
                footer_text="Действие: MESSAGE_BULK_DELETE",
                reason=reason,
                guild=guild,
            )
            return embed, None

        # ----------------------------------------------------------------------
        # 8. Настройки сервера (Guild Update)
        # ----------------------------------------------------------------------
        if action == AuditLogAction.guild_update:
            fields = []
            if hasattr(entry.after, "name"):
                fields.append(("Название сервера", f"`{entry.before.name}` ➔ `{entry.after.name}`", False))
            if hasattr(entry.after, "verification_level"):
                fields.append(("Уровень проверки", f"`{entry.before.verification_level}` ➔ `{entry.after.verification_level}`", False))
            if hasattr(entry.after, "default_notifications"):
                fields.append(("Уведомления по умолч.", f"`{entry.before.default_notifications}` ➔ `{entry.after.default_notifications}`", False))
            if hasattr(entry.after, "afk_timeout"):
                fields.append(("AFK таймаут", f"`{entry.before.afk_timeout} сек.` ➔ `{entry.after.afk_timeout} сек.`", False))
            if hasattr(entry.after, "afk_channel"):
                fields.append(("AFK канал", f"{format_channel(entry.after.afk_channel)}", False))
            if hasattr(entry.after, "owner"):
                fields.append(("🚨 ПЕРЕДАЧА ВЛАДЕЛЬЦА СЕРВЕРА", f"Новый владелец: {format_user(entry.after.owner)}", False))

            embed = build_embed(
                title="🏰 Изменены общие настройки сервера",
                color=LogColors.PURPLE,
                actor=actor,
                fields=fields,
                footer_text="Действие: GUILD_UPDATE",
                reason=reason,
                guild=guild,
            )
            return embed, None

        # ----------------------------------------------------------------------
        # 9. Вебхуки (Webhook)
        # ----------------------------------------------------------------------
        if action == AuditLogAction.webhook_create:
            embed = build_embed(
                title=f"🪝 {actor_label} создал вебхук",
                color=LogColors.GREEN,
                actor=actor,
                fields=[
                    ("Имя вебхука", f"**{getattr(target, 'name', 'Webhook')}**", True),
                    ("Канал", format_channel(getattr(target, "channel", None)), True),
                ],
                footer_text="Действие: WEBHOOK_CREATE",
                reason=reason,
                guild=guild,
            )
            return embed, None

        if action == AuditLogAction.webhook_delete:
            embed = build_embed(
                title=f"🗑️ {actor_label} удалил вебхук",
                color=LogColors.RED,
                actor=actor,
                fields=[
                    ("Имя вебхука", f"**{getattr(entry.before, 'name', 'Webhook')}**", True),
                ],
                footer_text="Действие: WEBHOOK_DELETE",
                reason=reason,
                guild=guild,
            )
            return embed, None

        if action == AuditLogAction.webhook_update:
            embed = build_embed(
                title=f"🔧 {actor_label} обновил вебхук",
                color=LogColors.YELLOW,
                actor=actor,
                fields=[
                    ("Имя вебхука", f"**{getattr(target, 'name', 'Webhook')}**", True),
                ],
                footer_text="Действие: WEBHOOK_UPDATE",
                reason=reason,
                guild=guild,
            )
            return embed, None

        # ----------------------------------------------------------------------
        # 10. Приглашения (Invites)
        # ----------------------------------------------------------------------
        if action == AuditLogAction.invite_create:
            code = getattr(target, "code", "Unknown")
            channel = getattr(target, "channel", None)
            max_uses = getattr(target, "max_uses", 0)
            max_age = getattr(target, "max_age", 0)
            embed = build_embed(
                title=f"✉️ {actor_label} создал приглашение",
                color=LogColors.BLUE,
                actor=actor,
                fields=[
                    ("Код инвайта", f"`discord.gg/{code}`", True),
                    ("Канал", format_channel(channel), True),
                    ("Лимиты", f"Использований: `{max_uses or 'Бесконечно'}` | Срок: `{max_age or 'Бессрочно'}`", False),
                ],
                footer_text="Действие: INVITE_CREATE",
                reason=reason,
                guild=guild,
            )
            return embed, None

        if action == AuditLogAction.invite_delete:
            code = getattr(target, "code", "Unknown")
            embed = build_embed(
                title=f"❌ {actor_label} удалил приглашение",
                color=LogColors.RED,
                actor=actor,
                fields=[
                    ("Код инвайта", f"`discord.gg/{code}`", True),
                ],
                footer_text="Действие: INVITE_DELETE",
                reason=reason,
                guild=guild,
            )
            return embed, None

        return None, None


async def setup(bot: commands.Bot):
    await bot.add_cog(AuditLogsCog(bot))
