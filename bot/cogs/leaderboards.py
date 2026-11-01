import asyncio
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

    def cog_unload(self):
        self.auto_refresh_tops.cancel()

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


async def setup(bot: commands.Bot):
    await bot.add_cog(LeaderboardsCog(bot))

