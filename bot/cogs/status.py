import platform
import sys
import time
from datetime import datetime, timezone
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from bot.config import Config
from bot.utils import LogColors, message_cache

try:
    import psutil
except ImportError:
    psutil = None

START_TIME = time.time()


class StatusCog(commands.Cog):
    """Команда проверки статуса и работоспособности бота."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _build_status_embed(self) -> discord.Embed:
        uptime_seconds = int(time.time() - START_TIME)
        days, remainder = divmod(uptime_seconds, 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, seconds = divmod(remainder, 60)

        uptime_parts = []
        if days > 0:
            uptime_parts.append(f"{days} дн.")
        if hours > 0:
            uptime_parts.append(f"{hours} ч.")
        if minutes > 0:
            uptime_parts.append(f"{minutes} мин.")
        uptime_parts.append(f"{seconds} сек.")
        uptime_str = " ".join(uptime_parts)

        latency_ms = round(self.bot.latency * 1000)

        # Канал логов
        log_channel = self.bot.get_channel(Config.LOG_CHANNEL_ID)
        if log_channel:
            perms = log_channel.permissions_for(log_channel.guild.me)
            can_send = perms.send_messages and perms.embed_links
            log_status = f"{log_channel.mention} (`#{log_channel.name}`)"
            log_health = "🟢 Доступен (права есть)" if can_send else "🔴 Нет прав на отправку"
        else:
            log_status = f"`ID: {Config.LOG_CHANNEL_ID}`"
            log_health = "⚠️ Канал не найден в кэше"

        # RAM
        ram_str = "Н/Д"
        if psutil:
            try:
                proc = psutil.Process()
                ram_mb = proc.memory_info().rss / (1024 * 1024)
                ram_str = f"{ram_mb:.1f} MB"
            except Exception:
                pass

        embed = discord.Embed(
            title="🛡️ Статус Discord Security & Moderation Logger",
            color=LogColors.GREEN,
            timestamp=discord.utils.utcnow(),
        )

        embed.add_field(name="🟢 Состояние", value="`В сети 24/7`", inline=True)
        embed.add_field(name="📶 Задержка (Пинг)", value=f"`{latency_ms} мс`", inline=True)
        embed.add_field(name="💾 Память (RAM)", value=f"`{ram_str}`", inline=True)

        embed.add_field(
            name="⏱️ Время работы (Uptime)",
            value=f"**{uptime_str}**\n*(Запущен: <t:{int(START_TIME)}:R>)*",
            inline=False,
        )

        embed.add_field(
            name="📢 Канал для логов",
            value=f"{log_status}\nСтатус: {log_health}",
            inline=True,
        )
        embed.add_field(
            name="🌐 Серверов / Кэш",
            value=f"Серверов: `{len(self.bot.guilds)}`\nСообщений в кэше: `{len(message_cache._cache)}`",
            inline=True,
        )

        embed.add_field(
            name="⚙️ Активные системы защиты",
            value="• **Audit Logs** — отслеживание всех действий администрации\n• **Direct Events** — контроль сообщений, войса и ролей\n• **Message Tracker** — сохранение удаленного контента",
            inline=False,
        )

        py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        embed.set_footer(
            text=f"Python {py_ver} • discord.py {discord.__version__} • Wispbyte"
        )
        return embed

    @app_commands.command(name="status", description="Показывает текущий статус и статистику работы бота")
    async def status_slash(self, interaction: discord.Interaction):
        """Слэш-команда /status"""
        embed = self._build_status_embed()
        await interaction.response.send_message(embed=embed)

    @commands.command(name="status")
    async def status_prefix(self, ctx: commands.Context):
        """Текстовая команда !status"""
        embed = self._build_status_embed()
        await ctx.send(embed=embed)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Перехват текстового ввода /status, !status, .status если слэш еще не подтянулся в интерфейс"""
        if message.author.bot or not message.guild:
            return
        if message.content.strip().lower() in ("/status", "!status", ".status"):
            embed = self._build_status_embed()
            try:
                await message.channel.send(embed=embed)
            except Exception:
                pass


async def setup(bot: commands.Bot):
    await bot.add_cog(StatusCog(bot))

