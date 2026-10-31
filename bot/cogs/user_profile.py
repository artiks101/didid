import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Union

import discord
from discord import app_commands
from discord.ext import commands, tasks

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
        # member_id -> (guild_id, last_flush_timestamp)
        self._active_voice: dict[int, tuple[int, float]] = {}
        # member_id -> session_start_timestamp (для вычисления непрерывной текущей сессии)
        self._session_start: dict[int, float] = {}
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

    def voice_join(self, user_id: int, guild_id: int):
        now = time.time()
        self._active_voice[user_id] = (guild_id, now)
        if user_id not in self._session_start:
            self._session_start[user_id] = now

    def voice_leave(self, user_id: int, guild_id: int):
        now = time.time()
        info = self._active_voice.pop(user_id, None)
        self._session_start.pop(user_id, None)
        if info:
            g_id, last_time = info
            elapsed = now - last_time
            if elapsed > 0:
                self.add_voice_seconds(user_id, g_id or guild_id, elapsed)

    def voice_switch(self, user_id: int, guild_id: int):
        now = time.time()
        info = self._active_voice.get(user_id)
        if info:
            g_id, last_time = info
            elapsed = now - last_time
            if elapsed > 0:
                self.add_voice_seconds(user_id, g_id or guild_id, elapsed)
        self._active_voice[user_id] = (guild_id, now)

    def flush_all(self):
        """Регулярно сохраняет накопленное голосовое время всех активных участников в SQLite."""
        if not self._active_voice:
            return
        now = time.time()
        for user_id, (guild_id, last_time) in list(self._active_voice.items()):
            elapsed = now - last_time
            if elapsed > 0:
                self.add_voice_seconds(user_id, guild_id, elapsed)
                self._active_voice[user_id] = (guild_id, now)

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

        # Если участник прямо сейчас в голосовом канале:
        # к уже сохраненным в БД секундам прибавляем несинхронизированные секунды текущего интервала
        if user_id in self._active_voice:
            _, last_time = self._active_voice[user_id]
            unflushed = max(0.0, time.time() - last_time)
            voice_secs += unflushed

            start_sess = self._session_start.get(user_id, last_time)
            current_session = max(0.0, time.time() - start_sess)

        return msg_count, voice_secs, current_session


tracker = UserActivityTracker()


class UserProfileCog(commands.Cog):
    """Команда /me и отслеживание статистики сообщений и голосовых каналов."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.sync_voice_activity.start()

    def cog_unload(self):
        self.sync_voice_activity.cancel()
        tracker.flush_all()

    @tasks.loop(seconds=15)
    async def sync_voice_activity(self):
        """Каждые 15 секунд сбрасывает голосовое время в SQLite, предотвращая потерю данных при перезагрузках."""
        try:
            tracker.flush_all()
        except Exception:
            pass

    @sync_voice_activity.before_loop
    async def before_sync(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_ready(self):
        # Инициализируем голосовые сессии для участников, которые уже сидят в войсе
        for guild in self.bot.guilds:
            channels = list(guild.voice_channels) + list(guild.stage_channels)
            for voice_channel in channels:
                for member in voice_channel.members:
                    if not member.bot and member.id not in tracker._active_voice:
                        tracker.voice_join(member.id, guild.id)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        tracker.increment_messages(message.author.id, message.guild.id)

        # Резервный текстовый триггер /me или !me (с поддержкой ника/упоминания)
        content = message.content.strip()
        lower = content.lower()
        if lower.startswith(("/me", "!me", ".me")):
            parts = content.split(maxsplit=1)
            target = message.author
            if len(parts) > 1 and message.guild:
                query = parts[1].strip()
                if message.mentions:
                    target = message.mentions[0]
                else:
                    found = discord.utils.find(
                        lambda m: query.lower() in m.name.lower() or query.lower() in (m.nick or "").lower() or str(m.id) == query,
                        message.guild.members
                    )
                    if found:
                        target = found

            try:
                await message.delete()
            except Exception:
                pass

            embed = self._build_me_embed(target, is_self=(target.id == message.author.id))
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
            tracker.voice_join(member.id, member.guild.id)
        # Отключение от канала
        elif before.channel is not None and after.channel is None:
            tracker.voice_leave(member.id, member.guild.id)
        # Переход между каналами
        elif before.channel and after.channel and before.channel.id != after.channel.id:
            tracker.voice_switch(member.id, member.guild.id)

    def _build_me_embed(self, member: discord.Member, is_self: bool = True) -> discord.Embed:
        guild = getattr(member, "guild", None)
        guild_id = guild.id if guild else 0
        msg_count, voice_secs, current_session = tracker.get_stats(member.id, guild_id)

        # Время на сервере
        if hasattr(member, "joined_at") and member.joined_at:
            now = datetime.now(timezone.utc)
            delta_days = (now - member.joined_at).days
            join_ts = int(member.joined_at.timestamp())
            days_str = f"**{delta_days} дн.** *(с <t:{join_ts}:D> • <t:{join_ts}:R>)*"
        else:
            days_str = "`Информация недоступна`"

        # Голосовое время
        voice_str = format_voice_duration(voice_secs)
        voice_extra = ""
        if current_session is not None and hasattr(member, "voice") and member.voice and member.voice.channel:
            voice_extra = f"\n🟢 *Сейчас в <#{member.voice.channel.id}> ({format_voice_duration(current_session)})*"

        # Роли участника (без @everyone)
        roles = [r.mention for r in reversed(member.roles[1:])] if hasattr(member, "roles") else []
        roles_str = ", ".join(roles[:8]) if roles else "Нет специальных ролей"
        if hasattr(member, "roles") and len(member.roles) > 9:
            roles_str += f" *(и ещё {len(member.roles) - 9})*"

        title = f"👤 Ваш профиль: {member.display_name}" if is_self else f"👤 Профиль участника: {member.display_name}"
        roles_label = "🛡️ Ваши роли" if is_self else "🛡️ Роли участника"
        color = member.color if hasattr(member, "color") and member.color.value != 0 else LogColors.BLUE

        embed = discord.Embed(
            title=title,
            color=color,
            timestamp=discord.utils.utcnow()
        )
        avatar_url = member.display_avatar.url if hasattr(member, "display_avatar") else None
        if avatar_url:
            embed.set_thumbnail(url=avatar_url)

        embed.add_field(name="📅 На сервере", value=days_str, inline=False)
        embed.add_field(name="💬 Написано сообщений", value=f"**{msg_count}** сообщений", inline=True)
        embed.add_field(name="🎙️ Время в голосовых", value=f"**{voice_str}**{voice_extra}", inline=True)
        embed.add_field(name=roles_label, value=roles_str, inline=False)

        created_str = member.created_at.strftime('%d.%m.%Y') if hasattr(member, "created_at") and member.created_at else "Н/Д"
        embed.set_footer(
            text=f"Аккаунт создан: {created_str} • ID: {member.id}"
        )
        return embed

    @app_commands.command(
        name="me",
        description="Статистика участника: дни на сервере, сообщения, время в войсе"
    )
    @app_commands.describe(
        member="Участник сервера, чью статистику показать (оставьте пустым для себя)"
    )
    async def me_slash(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
        """Слэш-команда /me [участник] (приватная, видна только автору вызова)"""
        caller = interaction.user if isinstance(interaction.user, discord.Member) else interaction.guild.get_member(interaction.user.id)
        target = member or caller
        if not target:
            target = interaction.user

        is_self = (caller is not None and target.id == caller.id)
        embed = self._build_me_embed(target, is_self=is_self)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @commands.command(name="me")
    async def me_prefix(self, ctx: commands.Context, *, member: Optional[discord.Member] = None):
        """Текстовая команда !me [@участник]"""
        target = member or ctx.author
        is_self = (target.id == ctx.author.id)
        embed = self._build_me_embed(target, is_self=is_self)
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
