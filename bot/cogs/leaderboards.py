import asyncio
from datetime import timedelta
import logging
from typing import Optional
import discord
from discord import app_commands
from discord.ext import commands, tasks

from bot.config import Config
from bot.utils import LogColors
from bot.cogs.user_profile import tracker, format_voice_duration

logger = logging.getLogger("bot.cogs.leaderboards")

MEDALS = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]


def build_voice_top_embed(guild: Optional[discord.Guild], period: str = "week") -> discord.Embed:
    guild_id = guild.id if guild else 0
    top_data = tracker.get_top_voice(guild_id, period=period, limit=10)

    period_labels = {
        "week": "За неделю (последние 7 дней)",
        "month": "За месяц (последние 30 дней)",
        "all": "За всё время",
    }
    period_title = period_labels.get(period, "За неделю")

    embed = discord.Embed(
        title=f"🎙️ Топ участников по голосовому времени",
        color=LogColors.BLUE,
        timestamp=discord.utils.utcnow()
    )

    lines = [f"📊 **Период:** `{period_title}`\n"]
    if top_data:
        for idx, (user_id, secs) in enumerate(top_data):
            medal = MEDALS[idx] if idx < len(MEDALS) else f"**#{idx+1}**"
            dur_str = format_voice_duration(secs)
            lines.append(f"{medal} <@{user_id}> — **{dur_str}**")
    else:
        lines.append("*В выбранном периоде пока нет активности в голосовых каналах.*")

    embed.description = "\n".join(lines)
    embed.set_footer(text="Нажимайте кнопки ниже для переключения периода")
    return embed


def build_messages_top_embed(guild: Optional[discord.Guild], period: str = "week") -> discord.Embed:
    guild_id = guild.id if guild else 0
    top_data = tracker.get_top_messages(guild_id, period=period, limit=10)

    period_labels = {
        "week": "За неделю (последние 7 дней)",
        "month": "За месяц (последние 30 дней)",
        "all": "За всё время",
    }
    period_title = period_labels.get(period, "За неделю")

    embed = discord.Embed(
        title=f"💬 Топ участников по сообщениям",
        color=LogColors.GREEN,
        timestamp=discord.utils.utcnow()
    )

    lines = [f"📊 **Период:** `{period_title}`\n"]
    if top_data:
        for idx, (user_id, count) in enumerate(top_data):
            medal = MEDALS[idx] if idx < len(MEDALS) else f"**#{idx+1}**"
            lines.append(f"{medal} <@{user_id}> — **{count}** сообщений")
    else:
        lines.append("*В выбранном периоде пока нет сообщений.*")

    embed.description = "\n".join(lines)
    embed.set_footer(text="Нажимайте кнопки ниже для переключения периода")
    return embed


class VoiceTopView(discord.ui.View):
    """Интерактивная панель переключения периодов топа по голосовому времени."""

    def __init__(self, current_period: str = "week"):
        super().__init__(timeout=None)
        if current_period == "week":
            self.btn_week.style = discord.ButtonStyle.primary
            self.btn_month.style = discord.ButtonStyle.secondary
            self.btn_all.style = discord.ButtonStyle.secondary
        elif current_period == "month":
            self.btn_week.style = discord.ButtonStyle.secondary
            self.btn_month.style = discord.ButtonStyle.primary
            self.btn_all.style = discord.ButtonStyle.secondary
        else:
            self.btn_week.style = discord.ButtonStyle.secondary
            self.btn_month.style = discord.ButtonStyle.secondary
            self.btn_all.style = discord.ButtonStyle.primary

    @discord.ui.button(label="📅 За неделю", style=discord.ButtonStyle.primary, custom_id="voicetop_btn_week")
    async def btn_week(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = build_voice_top_embed(interaction.guild, period="week")
        view = VoiceTopView(current_period="week")
        await interaction.response.edit_message(embed=embed, view=view)

    @discord.ui.button(label="🗓️ За месяц", style=discord.ButtonStyle.secondary, custom_id="voicetop_btn_month")
    async def btn_month(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = build_voice_top_embed(interaction.guild, period="month")
        view = VoiceTopView(current_period="month")
        await interaction.response.edit_message(embed=embed, view=view)

    @discord.ui.button(label="🏆 За всё время", style=discord.ButtonStyle.secondary, custom_id="voicetop_btn_all")
    async def btn_all(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = build_voice_top_embed(interaction.guild, period="all")
        view = VoiceTopView(current_period="all")
        await interaction.response.edit_message(embed=embed, view=view)


class MessagesTopView(discord.ui.View):
    """Интерактивная панель переключения периодов топа по сообщениям."""

    def __init__(self, current_period: str = "week"):
        super().__init__(timeout=None)
        if current_period == "week":
            self.btn_week.style = discord.ButtonStyle.primary
            self.btn_month.style = discord.ButtonStyle.secondary
            self.btn_all.style = discord.ButtonStyle.secondary
        elif current_period == "month":
            self.btn_week.style = discord.ButtonStyle.secondary
            self.btn_month.style = discord.ButtonStyle.primary
            self.btn_all.style = discord.ButtonStyle.secondary
        else:
            self.btn_week.style = discord.ButtonStyle.secondary
            self.btn_month.style = discord.ButtonStyle.secondary
            self.btn_all.style = discord.ButtonStyle.primary

    @discord.ui.button(label="📅 За неделю", style=discord.ButtonStyle.primary, custom_id="msgstop_btn_week")
    async def btn_week(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = build_messages_top_embed(interaction.guild, period="week")
        view = MessagesTopView(current_period="week")
        await interaction.response.edit_message(embed=embed, view=view)

    @discord.ui.button(label="🗓️ За месяц", style=discord.ButtonStyle.secondary, custom_id="msgstop_btn_month")
    async def btn_month(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = build_messages_top_embed(interaction.guild, period="month")
        view = MessagesTopView(current_period="month")
        await interaction.response.edit_message(embed=embed, view=view)

    @discord.ui.button(label="🏆 За всё время", style=discord.ButtonStyle.secondary, custom_id="msgstop_btn_all")
    async def btn_all(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = build_messages_top_embed(interaction.guild, period="all")
        view = MessagesTopView(current_period="all")
        await interaction.response.edit_message(embed=embed, view=view)


class LeaderboardsCog(commands.Cog):
    """Публикация и автообновление топов активности (голосовые каналы и сообщения)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._lock = asyncio.Lock()
        self.auto_refresh_tops.start()
        self.auto_check_monthly_rewards.start()

    def cog_unload(self):
        self.auto_refresh_tops.cancel()
        self.auto_check_monthly_rewards.cancel()

    async def update_guild_leaderboard(self, guild: discord.Guild) -> bool:
        """Обновляет или отправляет карточки топов в настроенный канал, очищая дубликаты."""
        async with self._lock:
            channel = self.bot.get_channel(Config.TOP_CHANNEL_ID)
            if not isinstance(channel, discord.TextChannel):
                return False

            perms = channel.permissions_for(guild.me)
            if not (perms.send_messages and perms.embed_links):
                logger.warning(f"Нет прав Send Messages или Embed Links в канале топов #{channel.name}")
                return False

            voice_msg_id, msgs_msg_id = tracker.get_top_message_ids(guild.id)
            voice_msg: Optional[discord.Message] = None
            msgs_msg: Optional[discord.Message] = None

            # Ищем существующие карточки бота в истории канала для устранения дублирования
            existing_voice_msgs: list[discord.Message] = []
            existing_text_msgs: list[discord.Message] = []

            try:
                async for msg in channel.history(limit=30):
                    if msg.author.id == self.bot.user.id and msg.embeds:
                        title = msg.embeds[0].title or ""
                        if "голосовому времени" in title:
                            existing_voice_msgs.append(msg)
                        elif "по сообщениям" in title:
                            existing_text_msgs.append(msg)
            except Exception as e:
                logger.warning(f"Ошибка при проверке истории #{channel.name}: {e}")

            # Если бот обнаружил дубликаты (например, от одновременных вызовов), удаляем лишние
            if len(existing_voice_msgs) > 1:
                for extra in existing_voice_msgs[1:]:
                    try:
                        await extra.delete()
                    except Exception:
                        pass
                existing_voice_msgs = existing_voice_msgs[:1]

            if len(existing_text_msgs) > 1:
                for extra in existing_text_msgs[1:]:
                    try:
                        await extra.delete()
                    except Exception:
                        pass
                existing_text_msgs = existing_text_msgs[:1]

            if existing_voice_msgs:
                voice_msg = existing_voice_msgs[0]
            elif voice_msg_id:
                try:
                    voice_msg = await channel.fetch_message(voice_msg_id)
                except (discord.NotFound, discord.HTTPException):
                    voice_msg = None

            if existing_text_msgs:
                msgs_msg = existing_text_msgs[0]
            elif msgs_msg_id:
                try:
                    msgs_msg = await channel.fetch_message(msgs_msg_id)
                except (discord.NotFound, discord.HTTPException):
                    msgs_msg = None

            voice_embed = build_voice_top_embed(guild, period="week")
            voice_view = VoiceTopView(current_period="week")

            msgs_embed = build_messages_top_embed(guild, period="week")
            msgs_view = MessagesTopView(current_period="week")

            # 1. Голосовой топ: редактируем существующее или отправляем новое
            if voice_msg:
                try:
                    await voice_msg.edit(embed=voice_embed, view=voice_view)
                except Exception:
                    voice_msg = await channel.send(embed=voice_embed, view=voice_view)
            else:
                voice_msg = await channel.send(embed=voice_embed, view=voice_view)

            # 2. Топ по сообщениям: редактируем существующее или отправляем новое
            if msgs_msg:
                try:
                    await msgs_msg.edit(embed=msgs_embed, view=msgs_view)
                except Exception:
                    msgs_msg = await channel.send(embed=msgs_embed, view=msgs_view)
            else:
                msgs_msg = await channel.send(embed=msgs_embed, view=msgs_view)

            # Сохраняем актуальные ID сообщений
            tracker.save_top_message_ids(
                guild.id,
                voice_msg.id if voice_msg else None,
                msgs_msg.id if msgs_msg else None
            )
            return True

    @tasks.loop(minutes=15)
    async def auto_refresh_tops(self):
        """Регулярно обновляет информацию в карточках топов каждые 15 минут."""
        for guild in self.bot.guilds:
            try:
                await self.update_guild_leaderboard(guild)
            except Exception as e:
                logger.exception(f"Ошибка при фоновом обновлении топов на '{guild.name}': {e}")

    @auto_refresh_tops.before_loop
    async def before_auto_refresh(self):
        await self.bot.wait_until_ready()

    async def distribute_monthly_roles(self, guild: discord.Guild, target_month: Optional[str] = None) -> tuple[bool, str, Optional[discord.Embed]]:
        """
        Выдает ежемесячные роли победителям топов (по голосу и сообщениям):
        - Снимает роли у предыдущих победителей
        - Взаимное исключение: 1 участник не может иметь обе роли
        - При лидерстве одного участника в обоих топах: роль отдается тому топу, где отрыв от 2-го места больше.
          Вторая роль достается 2-му месту.
        - Сохраняет факт вручения в БД и отправляет красивое объявление.
        """
        now = discord.utils.utcnow()
        if not target_month:
            if now.day == 1:
                target_month = (now.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
            else:
                target_month = now.strftime("%Y-%m")

        voice_top = tracker.get_top_voice(guild.id, limit=5, month_str=target_month)
        chat_top = tracker.get_top_messages(guild.id, limit=5, month_str=target_month)

        if not voice_top and not chat_top:
            return False, f"Нет данных активности за месяц `{target_month}`.", None

        voice_role = guild.get_role(Config.VOICE_TOP_ROLE_ID)
        chat_role = guild.get_role(Config.CHAT_TOP_ROLE_ID)

        if not voice_role and not chat_role:
            return False, "Роли победителей (VOICE_TOP_ROLE_ID / CHAT_TOP_ROLE_ID) не найдены на сервере.", None

        v1_id, v1_score = voice_top[0] if voice_top else (None, 0.0)
        v2_id, v2_score = voice_top[1] if len(voice_top) > 1 else (None, 0.0)

        c1_id, c1_score = chat_top[0] if chat_top else (None, 0)
        c2_id, c2_score = chat_top[1] if len(chat_top) > 1 else (None, 0)

        voice_winner_id: Optional[int] = None
        chat_winner_id: Optional[int] = None
        tie_details: Optional[str] = None

        if v1_id is not None and c1_id is None:
            voice_winner_id = v1_id
        elif c1_id is not None and v1_id is None:
            chat_winner_id = c1_id
        elif v1_id != c1_id:
            voice_winner_id = v1_id
            chat_winner_id = c1_id
        else:
            # v1_id == c1_id: один участник на первом месте в обоих топах!
            # Вычисляем относительный отрыв от 2-го места
            if v2_score > 0:
                v_margin = (v1_score - v2_score) / v2_score
                v_margin_str = f"+{v_margin * 100:.1f}%"
            else:
                v_margin = 999999.0
                v_margin_str = "абсолютный (нет 2-го места)"

            if c2_score > 0:
                c_margin = (c1_score - c2_score) / float(c2_score)
                c_margin_str = f"+{c_margin * 100:.1f}%"
            else:
                c_margin = 999999.0
                c_margin_str = "абсолютный (нет 2-го места)"

            same_user = v1_id
            if v_margin >= c_margin:
                # Отрыв по голосу больше: отдаем голосовую роль, а роль чата отдаем 2-му месту
                voice_winner_id = same_user
                chat_winner_id = c2_id
                tie_details = (
                    f"⭐ Участник <@{same_user}> занял **1-е место в обоих топах**!\n"
                    f"• Отрыв в голосовом топе: **{v_margin_str}**\n"
                    f"• Отрыв в топе сообщений: **{c_margin_str}**\n"
                    f"🎙️ По правилу наибольшего отрыва ему присвоена роль за голосовой чат!\n"
                    f"💬 Роль за текстовый чат переходит ко **2-му месту** — <@{c2_id}>."
                )
            else:
                # Отрыв по сообщениям больше: отдаем роль чата, а голосовую роль отдаем 2-му месту
                chat_winner_id = same_user
                voice_winner_id = v2_id
                tie_details = (
                    f"⭐ Участник <@{same_user}> занял **1-е место в обоих топах**!\n"
                    f"• Отрыв в топе сообщений: **{c_margin_str}**\n"
                    f"• Отрыв в голосовом топе: **{v_margin_str}**\n"
                    f"💬 По правилу наибольшего отрыва ему присвоена роль за текстовый чат!\n"
                    f"🎙️ Роль за голосовой чат переходит ко **2-му месту** — <@{v2_id}>."
                )

        # 1. Забираем роли у предыдущих победителей
        if voice_role:
            for member in voice_role.members:
                if member.id != voice_winner_id:
                    try:
                        await member.remove_roles(voice_role, reason=f"Смена победителя голосового топа за {target_month}")
                    except Exception as e:
                        logger.warning(f"Не удалось снять роль голоса у {member.name}: {e}")

        if chat_role:
            for member in chat_role.members:
                if member.id != chat_winner_id:
                    try:
                        await member.remove_roles(chat_role, reason=f"Смена победителя топа сообщений за {target_month}")
                    except Exception as e:
                        logger.warning(f"Не удалось снять роль чата у {member.name}: {e}")

        # 2. Выдаем роли новым победителям
        if voice_role and voice_winner_id:
            m = guild.get_member(voice_winner_id)
            if m and voice_role not in m.roles:
                try:
                    await m.add_roles(voice_role, reason=f"Победитель голосового топа за {target_month}")
                except Exception as e:
                    logger.warning(f"Не удалось выдать роль голоса {m.name}: {e}")

        if chat_role and chat_winner_id:
            m = guild.get_member(chat_winner_id)
            if m and chat_role not in m.roles:
                try:
                    await m.add_roles(chat_role, reason=f"Победитель топа сообщений за {target_month}")
                except Exception as e:
                    logger.warning(f"Не удалось выдать роль чата {m.name}: {e}")

        # Записываем факт награждения в SQLite
        tracker.record_month_reward(guild.id, target_month, voice_winner_id, chat_winner_id)

        # 3. Формируем объявление
        embed = discord.Embed(
            title=f"👑 Итоги месяца ({target_month}) и вручение ролей!",
            color=LogColors.PURPLE,
            timestamp=discord.utils.utcnow()
        )

        v_mention = f"<@{voice_winner_id}>" if voice_winner_id else "`Никто`"
        v_role_mention = voice_role.mention if voice_role else f"`ID: {Config.VOICE_TOP_ROLE_ID}`"
        v_stat = format_voice_duration(v1_score if voice_winner_id == v1_id else v2_score)

        c_mention = f"<@{chat_winner_id}>" if chat_winner_id else "`Никто`"
        c_role_mention = chat_role.mention if chat_role else f"`ID: {Config.CHAT_TOP_ROLE_ID}`"
        c_stat = f"{c1_score if chat_winner_id == c1_id else c2_score} сообщений"

        embed.add_field(
            name="🎙️ Победитель голосового топа",
            value=f"Участник: {v_mention}\nНаграда: {v_role_mention}\nРезультат: **{v_stat}**",
            inline=False
        )

        embed.add_field(
            name="💬 Победитель по сообщениям",
            value=f"Участник: {c_mention}\nНаграда: {c_role_mention}\nРезультат: **{c_stat}**",
            inline=False
        )

        if tie_details:
            embed.add_field(name="⚖️ Разрешение ситуации двух первых мест", value=tie_details, inline=False)

        embed.set_footer(text=f"Награды выданы • Роли действуют до конца следующего месяца")

        # Отправляем в канал топов
        top_channel = self.bot.get_channel(Config.TOP_CHANNEL_ID)
        if isinstance(top_channel, discord.TextChannel):
            try:
                await top_channel.send(embed=embed)
            except Exception:
                pass

        return True, f"Награды за `{target_month}` успешно распределены!", embed

    @tasks.loop(hours=1)
    async def auto_check_monthly_rewards(self):
        """Ежечасно проверяет окончание месяца и автоматически выдает роли победителям."""
        now = discord.utils.utcnow()
        is_first_day = (now.day == 1)
        next_day = now + timedelta(days=1)
        is_last_day_late = (next_day.day == 1 and now.hour >= 23 and now.minute >= 45)

        if not (is_first_day or is_last_day_late):
            return

        if is_first_day:
            target_month = (now.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
        else:
            target_month = now.strftime("%Y-%m")

        for guild in self.bot.guilds:
            if not tracker.is_month_awarded(guild.id, target_month):
                try:
                    await self.distribute_monthly_roles(guild, target_month=target_month)
                except Exception as e:
                    logger.exception(f"Ошибка при автоматической выдаче наград за {target_month}: {e}")

    @auto_check_monthly_rewards.before_loop
    async def before_auto_monthly(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_ready(self):
        # Регистрируем персистентные кнопки для мгновенной обработки после перезапуска
        self.bot.add_view(VoiceTopView("week"))
        self.bot.add_view(MessagesTopView("week"))

    @app_commands.command(
        name="updatetop",
        description="Обновить или пересоздать карточки топов в канале"
    )
    @app_commands.default_permissions(administrator=True)
    async def updatetop_slash(self, interaction: discord.Interaction):
        """Слэш-команда ручного обновления карточек топов (для администраторов)"""
        await interaction.response.defer(ephemeral=True)
        if not interaction.guild:
            await interaction.followup.send("❌ Команда доступна только на сервере.", ephemeral=True)
            return

        ok = await self.update_guild_leaderboard(interaction.guild)
        if ok:
            channel = self.bot.get_channel(Config.TOP_CHANNEL_ID)
            ch_name = f"#{channel.name}" if channel else str(Config.TOP_CHANNEL_ID)
            await interaction.followup.send(f"✅ Карточки топов успешно обновлены в канале {ch_name}!", ephemeral=True)
        else:
            await interaction.followup.send(f"❌ Не удалось найти канал с ID `{Config.TOP_CHANNEL_ID}` или отсутствуют права на отправку.", ephemeral=True)

    @app_commands.command(
        name="reward_monthly",
        description="[Администратор] Вручить ежемесячные роли победителям топов (по голосу и чату)"
    )
    @app_commands.describe(
        month="Месяц в формате ГГГГ-ММ (например: 2026-11). Оставьте пустым для завершенного/текущего месяца"
    )
    @app_commands.default_permissions(administrator=True)
    async def reward_monthly_slash(self, interaction: discord.Interaction, month: Optional[str] = None):
        """Ручной запуск распределения ежемесячных ролей"""
        await interaction.response.defer(ephemeral=True)
        if not interaction.guild:
            await interaction.followup.send("❌ Команда доступна только на сервере.", ephemeral=True)
            return

        ok, msg, embed = await self.distribute_monthly_roles(interaction.guild, target_month=month)
        if ok and embed:
            await interaction.followup.send(f"✅ {msg}", embed=embed, ephemeral=True)
        else:
            await interaction.followup.send(f"⚠️ {msg}", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(LeaderboardsCog(bot))

