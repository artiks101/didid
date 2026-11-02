import asyncio
import io
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Union

import discord
from discord import app_commands
from discord.ext import commands, tasks

from bot.card_generator import create_profile_card_image, release_memory
from bot.config import Config
from bot.utils import LogColors

DB_FILE = Path(__file__).resolve().parent.parent.parent / "messages.db"


def is_afk_channel(channel: Optional[Union[discord.VoiceChannel, discord.StageChannel, discord.abc.GuildChannel]]) -> bool:
    """Проверяет, является ли канал AFK-каналом (по явному ID или серверной настройке afk_channel)."""
    if not channel:
        return False
    if channel.id == Config.AFK_CHANNEL_ID:
        return True
    guild = getattr(channel, "guild", None)
    if guild and getattr(guild, "afk_channel", None) and channel.id == guild.afk_channel.id:
        return True
    return False


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


RU_MONTHS = [
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря"
]


def format_relative_time_ru(joined_at: datetime, now: Optional[datetime] = None) -> str:
    """Форматирует относительное время регистрации/входа на сервер на русском языке (аналог <t:ts:R>)."""
    if now is None:
        now = datetime.now(timezone.utc)
    delta_days = (now - joined_at).days
    if delta_days <= 0:
        return "сегодня"
    elif delta_days == 1:
        return "вчера"
    elif delta_days < 30:
        d = delta_days
        if 11 <= (d % 100) <= 14:
            suf = "дней"
        elif d % 10 == 1:
            suf = "день"
        elif 2 <= (d % 10) <= 4:
            suf = "дня"
        else:
            suf = "дней"
        return f"{d} {suf} назад"
    elif delta_days < 365:
        months = max(1, round(delta_days / 30.4375))
        if 11 <= (months % 100) <= 14:
            suf = "месяцев"
        elif months % 10 == 1:
            suf = "месяц"
        elif 2 <= (months % 10) <= 4:
            suf = "месяца"
        else:
            suf = "месяцев"
        return f"{months} {suf} назад"
    else:
        years = round(delta_days / 365.25)
        if years < 1:
            years = 1
        if 11 <= (years % 100) <= 14:
            suf = "лет"
        elif years % 10 == 1:
            suf = "год"
        elif 2 <= (years % 10) <= 4:
            suf = "года"
        else:
            suf = "лет"
        return f"{years} {suf} назад"


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
            with sqlite3.connect(self.db_path, timeout=10.0) as conn:
                conn.execute("PRAGMA journal_mode = WAL")
                conn.execute("PRAGMA synchronous = NORMAL")
                conn.execute("PRAGMA busy_timeout = 5000")
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS user_activity (
                        user_id INTEGER,
                        guild_id INTEGER,
                        message_count INTEGER DEFAULT 0,
                        voice_seconds REAL DEFAULT 0,
                        PRIMARY KEY (user_id, guild_id)
                    )
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS activity_daily (
                        user_id INTEGER,
                        guild_id INTEGER,
                        date TEXT,
                        message_count INTEGER DEFAULT 0,
                        voice_seconds REAL DEFAULT 0,
                        PRIMARY KEY (user_id, guild_id, date)
                    )
                """)
                conn.execute("CREATE INDEX IF NOT EXISTS idx_act_daily ON activity_daily(guild_id, date)")
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS top_messages (
                        guild_id INTEGER PRIMARY KEY,
                        voice_msg_id INTEGER,
                        messages_msg_id INTEGER,
                        rules_msg_id INTEGER
                    )
                """)
                try:
                    conn.execute("ALTER TABLE top_messages ADD COLUMN rules_msg_id INTEGER")
                except Exception:
                    pass
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS monthly_rewards (
                        guild_id INTEGER,
                        year_month TEXT,
                        voice_winner_id INTEGER,
                        chat_winner_id INTEGER,
                        awarded_at REAL,
                        PRIMARY KEY (guild_id, year_month)
                    )
                """)
                # Миграция: если таблица activity_daily пуста, заполняем текущими данными из user_activity
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM activity_daily")
                if cursor.fetchone()[0] == 0:
                    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                    conn.execute("""
                        INSERT OR IGNORE INTO activity_daily (user_id, guild_id, date, message_count, voice_seconds)
                        SELECT user_id, guild_id, ?, message_count, voice_seconds FROM user_activity
                    """, (today,))
                conn.commit()
        except Exception:
            pass

    def increment_messages(self, user_id: int, guild_id: int):
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT INTO user_activity (user_id, guild_id, message_count, voice_seconds)
                    VALUES (?, ?, 1, 0)
                    ON CONFLICT(user_id, guild_id) DO UPDATE SET message_count = message_count + 1
                """, (user_id, guild_id))
                conn.execute("""
                    INSERT INTO activity_daily (user_id, guild_id, date, message_count, voice_seconds)
                    VALUES (?, ?, ?, 1, 0)
                    ON CONFLICT(user_id, guild_id, date) DO UPDATE SET message_count = message_count + 1
                """, (user_id, guild_id, today))
                conn.commit()
        except Exception:
            pass

    def add_voice_seconds(self, user_id: int, guild_id: int, seconds: float):
        if seconds <= 0:
            return
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT INTO user_activity (user_id, guild_id, message_count, voice_seconds)
                    VALUES (?, ?, 0, ?)
                    ON CONFLICT(user_id, guild_id) DO UPDATE SET voice_seconds = voice_seconds + ?
                """, (user_id, guild_id, seconds, seconds))
                conn.execute("""
                    INSERT INTO activity_daily (user_id, guild_id, date, message_count, voice_seconds)
                    VALUES (?, ?, ?, 0, ?)
                    ON CONFLICT(user_id, guild_id, date) DO UPDATE SET voice_seconds = voice_seconds + ?
                """, (user_id, guild_id, today, seconds, seconds))
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
        """Регулярно сохраняет накопленное голосовое время всех активных участников в SQLite единой транзакцией."""
        if not self._active_voice:
            return
        now = time.time()
        updates = []
        for user_id, (guild_id, last_time) in list(self._active_voice.items()):
            elapsed = now - last_time
            if elapsed > 0:
                updates.append((user_id, guild_id, elapsed))
                self._active_voice[user_id] = (guild_id, now)

        if not updates:
            return

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        try:
            with sqlite3.connect(self.db_path, timeout=10.0) as conn:
                conn.execute("PRAGMA busy_timeout = 5000")
                cursor = conn.cursor()
                for user_id, guild_id, seconds in updates:
                    cursor.execute("""
                        INSERT INTO user_activity (user_id, guild_id, message_count, voice_seconds)
                        VALUES (?, ?, 0, ?)
                        ON CONFLICT(user_id, guild_id) DO UPDATE SET voice_seconds = voice_seconds + ?
                    """, (user_id, guild_id, seconds, seconds))
                    cursor.execute("""
                        INSERT INTO activity_daily (user_id, guild_id, date, message_count, voice_seconds)
                        VALUES (?, ?, ?, 0, ?)
                        ON CONFLICT(user_id, guild_id, date) DO UPDATE SET voice_seconds = voice_seconds + ?
                    """, (user_id, guild_id, today, seconds, seconds))
                conn.commit()
        except Exception:
            pass

    def delete_user_data(self, user_id: int, guild_id: Optional[int] = None):
        """Полностью удаляет данные активности и кэшированных сообщений участника."""
        self._active_voice.pop(user_id, None)
        self._session_start.pop(user_id, None)

        try:
            with sqlite3.connect(self.db_path) as conn:
                if guild_id:
                    conn.execute("DELETE FROM user_activity WHERE user_id=? AND guild_id=?", (user_id, guild_id))
                    conn.execute("DELETE FROM activity_daily WHERE user_id=? AND guild_id=?", (user_id, guild_id))
                else:
                    conn.execute("DELETE FROM user_activity WHERE user_id=?", (user_id,))
                    conn.execute("DELETE FROM activity_daily WHERE user_id=?", (user_id,))
                conn.commit()
        except Exception:
            pass

        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("DELETE FROM messages WHERE author_id=?", (user_id,))
                conn.execute("DELETE FROM recent_deletions WHERE author_id=?", (user_id,))
                conn.execute("UPDATE monthly_rewards SET voice_winner_id=NULL WHERE voice_winner_id=?", (user_id,))
                conn.execute("UPDATE monthly_rewards SET chat_winner_id=NULL WHERE chat_winner_id=?", (user_id,))
                conn.commit()
        except Exception:
            pass

    def get_top_voice(self, guild_id: int, period: str = "week", limit: int = 10, month_str: Optional[str] = None) -> list[tuple[int, float]]:
        """
        Возвращает топ участников по голосовому времени: [(user_id, voice_seconds), ...]
        period: 'week' (7 дней), 'month' (30 дней), 'all' (всё время)
        month_str: если указан (например '2026-10'), фильтрует строго по этому календарному месяцу
        """
        self.flush_all()
        results = []
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                if month_str:
                    cursor.execute("""
                        SELECT user_id, SUM(voice_seconds) as total
                        FROM activity_daily
                        WHERE guild_id = ? AND strftime('%Y-%m', date) = ?
                        GROUP BY user_id
                        HAVING total > 0
                        ORDER BY total DESC
                        LIMIT ?
                    """, (guild_id, month_str, limit))
                elif period == "week":
                    cursor.execute("""
                        SELECT user_id, SUM(voice_seconds) as total
                        FROM activity_daily
                        WHERE guild_id = ? AND date >= date('now', '-7 days')
                        GROUP BY user_id
                        HAVING total > 0
                        ORDER BY total DESC
                        LIMIT ?
                    """, (guild_id, limit))
                elif period == "month":
                    cursor.execute("""
                        SELECT user_id, SUM(voice_seconds) as total
                        FROM activity_daily
                        WHERE guild_id = ? AND date >= date('now', '-30 days')
                        GROUP BY user_id
                        HAVING total > 0
                        ORDER BY total DESC
                        LIMIT ?
                    """, (guild_id, limit))
                else:  # all
                    cursor.execute("""
                        SELECT user_id, voice_seconds as total
                        FROM user_activity
                        WHERE guild_id = ? AND voice_seconds > 0
                        ORDER BY total DESC
                        LIMIT ?
                    """, (guild_id, limit))
                results = cursor.fetchall()
        except Exception:
            pass
        return results

    def get_top_messages(self, guild_id: int, period: str = "week", limit: int = 10, month_str: Optional[str] = None) -> list[tuple[int, int]]:
        """
        Возвращает топ участников по сообщениям: [(user_id, message_count), ...]
        period: 'week' (7 дней), 'month' (30 дней), 'all' (всё время)
        month_str: если указан (например '2026-10'), фильтрует строго по этому календарному месяцу
        """
        results = []
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                if month_str:
                    cursor.execute("""
                        SELECT user_id, SUM(message_count) as total
                        FROM activity_daily
                        WHERE guild_id = ? AND strftime('%Y-%m', date) = ?
                        GROUP BY user_id
                        HAVING total > 0
                        ORDER BY total DESC
                        LIMIT ?
                    """, (guild_id, month_str, limit))
                elif period == "week":
                    cursor.execute("""
                        SELECT user_id, SUM(message_count) as total
                        FROM activity_daily
                        WHERE guild_id = ? AND date >= date('now', '-7 days')
                        GROUP BY user_id
                        HAVING total > 0
                        ORDER BY total DESC
                        LIMIT ?
                    """, (guild_id, limit))
                elif period == "month":
                    cursor.execute("""
                        SELECT user_id, SUM(message_count) as total
                        FROM activity_daily
                        WHERE guild_id = ? AND date >= date('now', '-30 days')
                        GROUP BY user_id
                        HAVING total > 0
                        ORDER BY total DESC
                        LIMIT ?
                    """, (guild_id, limit))
                else:  # all
                    cursor.execute("""
                        SELECT user_id, message_count as total
                        FROM user_activity
                        WHERE guild_id = ? AND message_count > 0
                        ORDER BY total DESC
                        LIMIT ?
                    """, (guild_id, limit))
                results = cursor.fetchall()
        except Exception:
            pass
        return results

    def is_month_awarded(self, guild_id: int, year_month: str) -> bool:
        """Проверяет, были ли уже выданы награды за указанный месяц."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT 1 FROM monthly_rewards WHERE guild_id=? AND year_month=?", (guild_id, year_month))
                return cursor.fetchone() is not None
        except Exception:
            return False

    def record_month_reward(self, guild_id: int, year_month: str, voice_winner_id: Optional[int], chat_winner_id: Optional[int]):
        """Записывает факт вручения ежемесячных наград."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT INTO monthly_rewards (guild_id, year_month, voice_winner_id, chat_winner_id, awarded_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(guild_id, year_month) DO UPDATE SET
                        voice_winner_id = excluded.voice_winner_id,
                        chat_winner_id = excluded.chat_winner_id,
                        awarded_at = excluded.awarded_at
                """, (guild_id, year_month, voice_winner_id, chat_winner_id, time.time()))
                conn.commit()
        except Exception:
            pass

    def get_top_message_ids(self, guild_id: int) -> tuple[Optional[int], Optional[int], Optional[int]]:
        """Возвращает сохраненные ID сообщений для топов (voice_msg_id, messages_msg_id, rules_msg_id)."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT voice_msg_id, messages_msg_id, rules_msg_id FROM top_messages WHERE guild_id=?", (guild_id,))
                row = cursor.fetchone()
                if row:
                    return row[0], row[1], row[2]
        except Exception:
            pass
        return None, None, None

    def save_top_message_ids(self, guild_id: int, voice_msg_id: Optional[int], messages_msg_id: Optional[int], rules_msg_id: Optional[int] = None):
        """Сохраняет ID сообщений топов и правил в БД."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT INTO top_messages (guild_id, voice_msg_id, messages_msg_id, rules_msg_id)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(guild_id) DO UPDATE SET
                        voice_msg_id = COALESCE(?, voice_msg_id),
                        messages_msg_id = COALESCE(?, messages_msg_id),
                        rules_msg_id = COALESCE(?, rules_msg_id)
                """, (guild_id, voice_msg_id, messages_msg_id, rules_msg_id, voice_msg_id, messages_msg_id, rules_msg_id))
                conn.commit()
        except Exception:
            pass

    def get_user_wins(self, user_id: int, guild_id: int) -> tuple[int, int]:
        """Возвращает (voice_wins, chat_wins) для участника."""
        voice_wins = 0
        chat_wins = 0
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT COUNT(*) FROM monthly_rewards WHERE guild_id=? AND voice_winner_id=?",
                    (guild_id, user_id)
                )
                row_v = cursor.fetchone()
                if row_v:
                    voice_wins = row_v[0] or 0

                cursor.execute(
                    "SELECT COUNT(*) FROM monthly_rewards WHERE guild_id=? AND chat_winner_id=?",
                    (guild_id, user_id)
                )
                row_c = cursor.fetchone()
                if row_c:
                    chat_wins = row_c[0] or 0
        except Exception:
            pass
        return voice_wins, chat_wins

    def get_stats(self, user_id: int, guild_id: int) -> tuple[int, float, Optional[float], float]:
        msg_count = 0
        voice_secs = 0.0
        current_session = None
        active_days = 0

        try:
            with sqlite3.connect(self.db_path, timeout=5.0) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT message_count, voice_seconds FROM user_activity WHERE user_id=? AND guild_id=?",
                    (user_id, guild_id)
                )
                row = cursor.fetchone()
                if row:
                    msg_count = row[0] or 0
                    voice_secs = row[1] or 0.0

                # Количество уникальных дней с голосовой активностью
                cursor.execute(
                    "SELECT COUNT(DISTINCT date) FROM activity_daily WHERE user_id=? AND guild_id=? AND voice_seconds > 0",
                    (user_id, guild_id)
                )
                row_days = cursor.fetchone()
                if row_days and row_days[0]:
                    active_days = row_days[0]

                # Проверяем, есть ли уже сохраненная активность за сегодня
                today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                cursor.execute(
                    "SELECT 1 FROM activity_daily WHERE user_id=? AND guild_id=? AND date=? AND voice_seconds > 0",
                    (user_id, guild_id, today_str)
                )
                today_exists = cursor.fetchone() is not None

                # Проверяем также сообщения в таблице messages
                cursor.execute("SELECT COUNT(*) FROM messages WHERE author_id=?", (user_id,))
                cached_msgs = cursor.fetchone()
                if cached_msgs and cached_msgs[0] > msg_count:
                    msg_count = cached_msgs[0]
        except Exception:
            today_exists = False

        # Если участник прямо сейчас в голосовом канале:
        # к уже сохраненным в БД секундам прибавляем несинхронизированные секунды текущего интервала
        if user_id in self._active_voice:
            _, last_time = self._active_voice[user_id]
            unflushed = max(0.0, time.time() - last_time)
            voice_secs += unflushed

            start_sess = self._session_start.get(user_id, last_time)
            current_session = max(0.0, time.time() - start_sess)

            # Если сегодня еще не сохранялось в activity_daily, добавляем сегодняшний день
            if not today_exists:
                active_days += 1

        if active_days == 0 and voice_secs > 0:
            active_days = 1

        avg_daily = (voice_secs / active_days) if active_days > 0 else 0.0

        return msg_count, voice_secs, current_session, avg_daily


tracker = UserActivityTracker()


class UserProfileCog(commands.Cog):
    """Команда /me и отслеживание статистики сообщений и голосовых каналов."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.sync_voice_activity.start()

    def cog_unload(self):
        self.sync_voice_activity.cancel()
        tracker.flush_all()

    @tasks.loop(seconds=30)
    async def sync_voice_activity(self):
        """Каждые 30 секунд сбрасывает голосовое время в SQLite в отдельном потоке."""
        try:
            await asyncio.to_thread(tracker.flush_all)
        except Exception:
            pass

    @sync_voice_activity.before_loop
    async def before_sync(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_ready(self):
        # Инициализируем голосовые сессии для участников, которые уже сидят в войсе (пропуская AFK)
        for guild in self.bot.guilds:
            channels = list(guild.voice_channels) + list(guild.stage_channels)
            for voice_channel in channels:
                if is_afk_channel(voice_channel):
                    continue
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

            target_guild = target.guild if hasattr(target, "guild") and target.guild else message.guild
            guild_id = target_guild.id if target_guild else 0
            stats = tracker.get_stats(target.id, guild_id)
            card_buf = await self._render_profile_card(target, stats)

            if card_buf:
                file = discord.File(fp=card_buf, filename="profile_card.png")
                try:
                    await message.author.send(file=file)
                except Exception:
                    file.fp.seek(0)
                    await message.channel.send(file=file, delete_after=35)
            else:
                embed = self._build_me_embed(target, is_self=(target.id == message.author.id))
                try:
                    await message.author.send(embed=embed)
                except Exception:
                    await message.channel.send(embed=embed, delete_after=25)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if member.bot or not member.guild:
            return

        before_afk = is_afk_channel(before.channel)
        after_afk = is_afk_channel(after.channel)

        # 1. Подключение к обычному войсу (из оффлайна или переход из AFK)
        if (before.channel is None or before_afk) and (after.channel is not None and not after_afk):
            tracker.voice_join(member.id, member.guild.id)
        # 2. Отключение от войса или переход в AFK канал
        elif (before.channel is not None and not before_afk) and (after.channel is None or after_afk):
            tracker.voice_leave(member.id, member.guild.id)
        # 3. Переход между разными обычными (не AFK) каналами
        elif before.channel and after.channel and not before_afk and not after_afk and before.channel.id != after.channel.id:
            tracker.voice_switch(member.id, member.guild.id)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        """Срабатывает при выходе участника с сервера, а также при его исключении (кике) или блокировке (бане)."""
        if member.bot:
            return
        guild_id = member.guild.id if member.guild else None
        tracker.delete_user_data(member.id, guild_id)

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: Union[discord.User, discord.Member]):
        """Срабатывает при блокировке (бане) пользователя."""
        if getattr(user, "bot", False):
            return
        tracker.delete_user_data(user.id, guild.id if guild else None)

    def _build_me_embed(self, member: discord.Member, is_self: bool = True) -> discord.Embed:
        guild = getattr(member, "guild", None)
        guild_id = guild.id if guild else 0
        msg_count, voice_secs, current_session, avg_daily = tracker.get_stats(member.id, guild_id)
        voice_wins, chat_wins = tracker.get_user_wins(member.id, guild_id)

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
        avg_line = ""
        if voice_secs > 0:
            avg_line = f"\n⏱️ В среднем: **{format_voice_duration(avg_daily)}** в день"

        voice_extra = ""
        in_afk = hasattr(member, "voice") and member.voice and member.voice.channel and is_afk_channel(member.voice.channel)
        if in_afk:
            voice_extra = "\n💤 *Сейчас в AFK канале (время не учитывается)*"
        elif current_session is not None and hasattr(member, "voice") and member.voice and member.voice.channel:
            voice_extra = f"\n🟢 *Сейчас в <#{member.voice.channel.id}> ({format_voice_duration(current_session)})*"

        # Победы в Топ-1 месяца
        v_crown = " 👑" if voice_wins > 0 else ""
        c_crown = " 👑" if chat_wins > 0 else ""
        wins_str = f"🎙️ В голосе: **{voice_wins}**{v_crown} • 💬 В чате: **{chat_wins}**{c_crown}"

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
        embed.add_field(name="🎙️ Время в голосовых", value=f"**{voice_str}**{avg_line}{voice_extra}", inline=True)
        embed.add_field(name="🏆 Победы в Топ-1 месяца", value=wins_str, inline=False)
        embed.add_field(name=roles_label, value=roles_str, inline=False)

        created_str = member.created_at.strftime('%d.%m.%Y') if hasattr(member, "created_at") and member.created_at else "Н/Д"
        embed.set_footer(
            text=f"Аккаунт создан: {created_str} • ID: {member.id}"
        )
        return embed

    async def _render_profile_card(self, member: discord.Member, stats: tuple) -> Optional[io.BytesIO]:
        """Генерирует графическую карточку профиля участника (Pillow) в фоновом потоке."""
        try:
            msg_count, voice_secs, current_session, avg_daily = stats
            guild = getattr(member, "guild", None)
            guild_id = guild.id if guild else 0
            voice_wins, chat_wins = tracker.get_user_wins(member.id, guild_id)

            days_on_server = 0
            join_date_str = "Н/Д"
            if hasattr(member, "joined_at") and member.joined_at:
                now = datetime.now(timezone.utc)
                days_on_server = (now - member.joined_at).days
                rel_time = format_relative_time_ru(member.joined_at, now)
                m_idx = member.joined_at.month - 1
                month_name = RU_MONTHS[m_idx] if 0 <= m_idx < 12 else ""
                date_part = f"с {member.joined_at.day} {month_name} {member.joined_at.year} г." if month_name else f"с {member.joined_at.strftime('%d.%m.%Y')}"
                join_date_str = f"{date_part} • {rel_time}"

            voice_str = format_voice_duration(voice_secs)
            avg_voice_str = f"{format_voice_duration(avg_daily)} / день" if voice_secs > 0 else ""

            current_voice_str = ""
            in_afk = hasattr(member, "voice") and member.voice and member.voice.channel and is_afk_channel(member.voice.channel)
            if in_afk:
                current_voice_str = "В AFK канале"
            elif current_session is not None and hasattr(member, "voice") and member.voice and member.voice.channel:
                c_name = getattr(member.voice.channel, "name", "войсе")
                current_voice_str = f"В #{c_name} ({format_voice_duration(current_session)})"

            created_date_str = member.created_at.strftime("%d.%m.%Y") if hasattr(member, "created_at") and member.created_at else "Н/Д"

            # Роли участника с их цветами (исключая @everyone)
            roles = []
            if hasattr(member, "roles"):
                for r in reversed(member.roles[1:]):
                    r_col = (r.color.r, r.color.g, r.color.b, 255) if r.color.value != 0 else (150, 150, 150, 255)
                    roles.append((r.name, r_col))

            avatar_bytes = None
            if hasattr(member, "display_avatar") and member.display_avatar:
                try:
                    avatar_bytes = await member.display_avatar.read()
                except Exception:
                    avatar_bytes = None

            return await asyncio.to_thread(
                create_profile_card_image,
                display_name=member.display_name,
                handle=member.name,
                user_id=member.id,
                days_on_server=days_on_server,
                join_date_str=join_date_str,
                msg_count=msg_count,
                voice_str=voice_str,
                avg_voice_str=avg_voice_str,
                current_voice_str=current_voice_str,
                voice_wins=voice_wins,
                chat_wins=chat_wins,
                created_date_str=created_date_str,
                roles=roles,
                avatar_bytes=avatar_bytes,
                animated=True
            )
        except Exception:
            return None

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
        try:
            # Мгновенный defer (ephemeral), чтобы не истек 3-секундный таймаут Discord при генерации GIF
            await interaction.response.defer(ephemeral=True)

            target_guild = getattr(target, "guild", None) or interaction.guild
            guild_id = target_guild.id if target_guild else 0
            stats = tracker.get_stats(target.id, guild_id)
            card_buf = await self._render_profile_card(target, stats)

            if card_buf:
                file = discord.File(fp=card_buf, filename="profile_card.gif")
                await interaction.followup.send(file=file, ephemeral=True)
                try:
                    card_buf.close()
                except Exception:
                    pass
                release_memory()
            else:
                embed = self._build_me_embed(target, is_self=is_self)
                await interaction.followup.send(embed=embed, ephemeral=True)

            # Автоматическое удаление через 3 минуты (180 сек), если пользователь не скрыл сам
            async def _auto_delete():
                await asyncio.sleep(180)
                try:
                    await interaction.delete_original_response()
                except Exception:
                    pass

            asyncio.create_task(_auto_delete())
        except (discord.NotFound, discord.HTTPException):
            pass

    @commands.command(name="me")
    async def me_prefix(self, ctx: commands.Context, *, member: Optional[discord.Member] = None):
        """Текстовая команда !me [@участник]"""
        target = member or ctx.author
        is_self = (target.id == ctx.author.id)
        target_guild = getattr(target, "guild", None) or ctx.guild
        guild_id = target_guild.id if target_guild else 0
        stats = tracker.get_stats(target.id, guild_id)
        card_buf = await self._render_profile_card(target, stats)

        try:
            await ctx.message.delete()
        except Exception:
            pass

        if card_buf:
            file = discord.File(fp=card_buf, filename="profile_card.gif")
            try:
                await ctx.author.send(file=file)
            except Exception:
                file.fp.seek(0)
                await ctx.send(file=file, delete_after=180)
        else:
            embed = self._build_me_embed(target, is_self=is_self)
            try:
                await ctx.author.send(embed=embed)
            except Exception:
                await ctx.send(embed=embed, delete_after=180)


async def setup(bot: commands.Bot):
    await bot.add_cog(UserProfileCog(bot))
