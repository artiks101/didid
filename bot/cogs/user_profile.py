import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from bot.utils import LogColors

DB_FILE = Path(__file__).resolve().parent.parent.parent / "messages.db"


def format_voice_duration(seconds: float) -> str:
    """Форматирует секунды голосового чата в читаемый вид (дни, часы, минуты, секунды)."""
    secs = int(seconds)
    days, rem = divmod(secs, 86400)
    hours, rem = divmod(rem, 3600)
    mins, s = divmod(rem, 60)

    parts = []
    if days > 0:
        parts.append(f"{days} дн.")
    if hours > 0:
        parts.append(f"{hours} ч.")
    if mins > 0:
        parts.append(f"{mins} мин.")
    if s > 0 or not parts:
        parts.append(f"{s} сек.")
    return " ".join(parts)


class UserActivityTracker:
    """Хранилище активности участников (сообщения и голосовое время) в SQLite."""

    def __init__(self, db_path: Path = DB_FILE):
        self.db_path = str(db_path)
        self._active_voice: dict[int, float] = {}  # member_id -> start_timestamp
        self._init_db()

    def _init_db(self):
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS user_activity (
                        user_id INTEGER,
                        guild_id INTEGER,
                        message_count INTEGER DEFAULT 0,
                        voice_seconds REAL DEFAULT 0,
                        PRIMARY KEY (user_id, guild_id)
                    )
                """)
                conn.commit()
        except Exception:
            pass

    def increment_messages(self, user_id: int, guild_id: int):
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT INTO user_activity (user_id, guild_id, message_count, voice_seconds)
                    VALUES (?, ?, 1, 0)
                    ON CONFLICT(user_id, guild_id) DO UPDATE SET message_count = message_count + 1
                """, (user_id, guild_id))
                conn.commit()
        except Exception:
            pass

    def add_voice_seconds(self, user_id: int, guild_id: int, seconds: float):
        if seconds <= 0:
            return
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT INTO user_activity (user_id, guild_id, message_count, voice_seconds)
                    VALUES (?, ?, 0, ?)
                    ON CONFLICT(user_id, guild_id) DO UPDATE SET voice_seconds = voice_seconds + ?
                """, (user_id, guild_id, seconds, seconds))
                conn.commit()
        except Exception:
            pass

    def voice_join(self, user_id: int):
        self._active_voice[user_id] = time.time()

    def voice_leave(self, user_id: int, guild_id: int):
        start = self._active_voice.pop(user_id, None)
        if start:
            duration = time.time() - start
            self.add_voice_seconds(user_id, guild_id, duration)

    def voice_switch(self, user_id: int, guild_id: int):
        start = self._active_voice.get(user_id)
        if start:
            duration = time.time() - start
            self.add_voice_seconds(user_id, guild_id, duration)
        self._active_voice[user_id] = time.time()

    def get_stats(self, user_id: int, guild_id: int) -> tuple[int, float, Optional[float]]:
        msg_count = 0
        voice_secs = 0.0
        current_session = None

        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT message_count, voice_seconds FROM user_activity WHERE user_id=? AND guild_id=?",
                    (user_id, guild_id)
                )
                row = cursor.fetchone()
                if row:
                    msg_count = row[0] or 0
                    voice_secs = row[1] or 0.0

                # Проверяем также сообщения в таблице messages
                cursor.execute("SELECT COUNT(*) FROM messages WHERE author_id=?", (user_id,))
                cached_msgs = cursor.fetchone()
                if cached_msgs and cached_msgs[0] > msg_count:
                    msg_count = cached_msgs[0]
        except Exception:
            pass

        # Если участник прямо сейчас в голосовом канале
        if user_id in self._active_voice:
            session_dur = time.time() - self._active_voice[user_id]
            voice_secs += session_dur
            current_session = session_dur

        return msg_count, voice_secs, current_session


tracker = UserActivityTracker()


class UserProfileCog(commands.Cog):
    """Команда /me и отслеживание статистики сообщений и голосовых каналов."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        # Инициализируем голосовые сессии для участников, которые уже сидят в войсе
        for guild in self.bot.guilds:
            for voice_channel in guild.voice_channels:
                for member in voice_channel.members:
                    if not member.bot and member.id not in tracker._active_voice:
                        tracker.voice_join(member.id)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        tracker.increment_messages(message.author.id, message.guild.id)

        # Резервный текстовый триггер /me или !me
        if message.content.strip().lower() in ("/me", "!me", ".me"):
            try:
                await message.delete()
            except Exception:
                pass
            embed = self._build_me_embed(message.author)
            try:
                await message.author.send(embed=embed)
            except Exception:
                await message.channel.send(embed=embed, delete_after=25)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if member.bot or not member.guild:
            return

        # Подключение к каналу
        if before.channel is None and after.channel is not None:
            tracker.voice_join(member.id)
        # Отключение от канала
        elif before.channel is not None and after.channel is None:
            tracker.voice_leave(member.id, member.guild.id)
        # Переход между каналами
        elif before.channel and after.channel and before.channel.id != after.channel.id:
            tracker.voice_switch(member.id, member.guild.id)

    def _build_me_embed(self, member: discord.Member) -> discord.Embed:
        guild = member.guild
        msg_count, voice_secs, current_session = tracker.get_stats(member.id, guild.id)

        # Время на сервере
        if member.joined_at:
            now = datetime.now(timezone.utc)
            delta_days = (now - member.joined_at).days
            join_ts = int(member.joined_at.timestamp())
            days_str = f"**{delta_days} дн.** *(с <t:{join_ts}:D> • <t:{join_ts}:R>)*"
        else:
            days_str = "`Информация недоступна`"

        # Голосовое время
        voice_str = format_voice_duration(voice_secs)
        voice_extra = ""
        if current_session is not None and member.voice and member.voice.channel:
            ch_name = getattr(member.voice.channel, "name", "голосовой канал")
            voice_extra = f"\n🟢 *Сейчас в <#{member.voice.channel.id}> ({format_voice_duration(current_session)})*"

        # Роли участника (без @everyone)
        roles = [r.mention for r in reversed(member.roles[1:])]
        roles_str = ", ".join(roles[:8]) if roles else "Нет специальных ролей"
        if len(member.roles) > 9:
            roles_str += f" *(и ещё {len(member.roles) - 9})*"

        embed = discord.Embed(
            title=f"👤 Ваш профиль: {member.display_name}",
            color=member.color if member.color.value != 0 else LogColors.BLUE,
            timestamp=discord.utils.utcnow()
        )
        embed.set_thumbnail(url=member.display_avatar.url)

        embed.add_field(name="📅 На сервере", value=days_str, inline=False)
        embed.add_field(name="💬 Написано сообщений", value=f"**{msg_count}** сообщений", inline=True)
        embed.add_field(name="🎙️ Время в голосовых", value=f"**{voice_str}**{voice_extra}", inline=True)
        embed.add_field(name="🛡️ Ваши роли", value=roles_str, inline=False)

        created_ts = int(member.created_at.timestamp())
        embed.set_footer(
            text=f"Аккаунт создан: {member.created_at.strftime('%d.%m.%Y')} • ID: {member.id}"
        )
        return embed

    @app_commands.command(name="me", description="Ваша персональная статистика: дни на сервере, сообщения, время в войсе")
    async def me_slash(self, interaction: discord.Interaction):
        """Слэш-команда /me (приватная, видна только автору)"""
        if not isinstance(interaction.user, discord.Member):
            member = interaction.guild.get_member(interaction.user.id) or interaction.user
        else:
            member = interaction.user

        embed = self._build_me_embed(member)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @commands.command(name="me")
    async def me_prefix(self, ctx: commands.Context):
        """Текстовая команда !me"""
        embed = self._build_me_embed(ctx.author)
        try:
            await ctx.message.delete()
        except Exception:
            pass
        try:
            await ctx.author.send(embed=embed)
        except Exception:
            await ctx.send(embed=embed, delete_after=25)


async def setup(bot: commands.Bot):
    await bot.add_cog(UserProfileCog(bot))
