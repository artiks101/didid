import asyncio
import logging
from typing import Dict, Optional

import discord
from discord import app_commands
from discord.ext import commands

logger = logging.getLogger("bot.cogs.radio")

# Список популярных качественных онлайн-радиостанций
RADIO_STATIONS = {
    "record": {
        "name": "Radio Record",
        "url": "https://air.radiorecord.ru/rr_320",
        "description": "Электронная танцевальная музыка №1",
        "emoji": "📻",
    },
    "deep": {
        "name": "Record Deep",
        "url": "https://air.radiorecord.ru/deep_320",
        "description": "Атмосферный и глубокий House & Deep",
        "emoji": "🌊",
    },
    "chill": {
        "name": "Record Chill-Out",
        "url": "https://air.radiorecord.ru/chil_320",
        "description": "Расслабляющая и спокойная музыка для отдыха",
        "emoji": "☕",
    },
    "russian": {
        "name": "Record Russian Hits",
        "url": "https://air.radiorecord.ru/rus_320",
        "description": "Лучшие танцевальные хиты на русском",
        "emoji": "🇷🇺",
    },
    "europa": {
        "name": "Europa Plus",
        "url": "http://ep256.hostingradio.ru:8052/europaplus256.mp3",
        "description": "Мировые топ-хиты и поп-музыка",
        "emoji": "⭐",
    },
    "dfm": {
        "name": "DFM",
        "url": "http://dfm.hostingradio.ru/dfm96.aacp",
        "description": "Зажигательное клубное танцевальное радио",
        "emoji": "🔥",
    },
    "lofi": {
        "name": "Lofi Chill Radio",
        "url": "https://stream.zeno.fm/f3wvbbqmdg8uv",
        "description": "Lofi Hip Hop биты для работы, учебы и отдыха",
        "emoji": "🎧",
    },
    "newradio": {
        "name": "Новое Радио",
        "url": "http://icecast.newradio.cdnvideo.ru/newradio3",
        "description": "Главные русские суперхиты",
        "emoji": "🎶",
    },
}

DEFAULT_STATION_KEY = "record"


class GuildRadioState:
    """Хранит состояние плеера для конкретного сервера."""

    def __init__(self, guild_id: int):
        self.guild_id = guild_id
        self.station_key: str = DEFAULT_STATION_KEY
        self.custom_url: Optional[str] = None
        self.custom_name: Optional[str] = None
        self.volume: float = 0.5  # 50%
        self.is_paused: bool = False
        self.channel_id: Optional[int] = None
        self.text_channel_id: Optional[int] = None
        self.message: Optional[discord.Message] = None
        self.disconnect_task: Optional[asyncio.Task] = None

    @property
    def display_name(self) -> str:
        if self.custom_url:
            return self.custom_name or "Пользовательский поток"
        station = RADIO_STATIONS.get(self.station_key)
        return station["name"] if station else "Radio Record"

    @property
    def stream_url(self) -> str:
        if self.custom_url:
            return self.custom_url
        station = RADIO_STATIONS.get(self.station_key)
        return station["url"] if station else RADIO_STATIONS[DEFAULT_STATION_KEY]["url"]

    @property
    def emoji(self) -> str:
        if self.custom_url:
            return "🔗"
        station = RADIO_STATIONS.get(self.station_key)
        return station["emoji"] if station else "📻"


class RadioStationSelect(discord.ui.Select):
    """Выпадающий список для выбора радиостанции."""

    def __init__(self, current_key: str):
        options = []
        for key, st in RADIO_STATIONS.items():
            options.append(
                discord.SelectOption(
                    label=st["name"],
                    value=key,
                    description=st["description"][:100],
                    emoji=st["emoji"],
                    default=(key == current_key),
                )
            )
        super().__init__(
            placeholder="📻 Выберите радиостанцию для переключения...",
            min_values=1,
            max_values=1,
            options=options,
            row=0,
        )

    async def callback(self, interaction: discord.Interaction):
        cog: Optional[RadioCog] = interaction.client.get_cog("RadioCog")
        if not cog:
            return await interaction.response.send_message("❌ Модуль радио недоступен", ephemeral=True)

        vc = interaction.guild.voice_client
        if vc and vc.channel and interaction.user not in vc.channel.members:
            return await interaction.response.send_message(
                "⚠️ Переключать станцию могут только участники в этом голосовом канале!",
                ephemeral=True,
            )

        selected_key = self.values[0]
        await interaction.response.defer()
        await cog.change_station(interaction.guild, selected_key, interaction=interaction)


class RadioPlayerView(discord.ui.View):
    """Интерактивная панель управления воспроизведением радио."""

    def __init__(self, cog: "RadioCog", guild: discord.Guild, state: GuildRadioState):
        super().__init__(timeout=None)
        self.cog = cog
        self.guild = guild
        self.state = state

        # Добавляем селектор станций
        self.add_item(RadioStationSelect(state.station_key))

        # Обновляем вид кнопки паузы
        pause_label = "Возобновить" if state.is_paused else "Пауза"
        pause_emoji = "▶️" if state.is_paused else "⏸️"
        self.pause_button.label = pause_label
        self.pause_button.emoji = pause_emoji

    def _check_user_in_voice(self, interaction: discord.Interaction) -> bool:
        vc = interaction.guild.voice_client
        if not vc or not vc.channel:
            return False
        return interaction.user in vc.channel.members

    @discord.ui.button(label="Пауза", style=discord.ButtonStyle.secondary, emoji="⏸️", row=1)
    async def pause_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = interaction.guild.voice_client
        if not vc:
            return await interaction.response.send_message("⚠️ Бот не подключен к голосовому каналу.", ephemeral=True)

        if not self._check_user_in_voice(interaction):
            return await interaction.response.send_message(
                "⚠️ Управлять радио могут только участники, находящиеся в этом голосовом канале!",
                ephemeral=True,
            )

        if self.state.is_paused:
            vc.resume()
            self.state.is_paused = False
            button.label = "Пауза"
            button.emoji = "⏸️"
        else:
            vc.pause()
            self.state.is_paused = True
            button.label = "Возобновить"
            button.emoji = "▶️"

        embed = self.cog.build_embed(interaction.guild, self.state)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="-10%", style=discord.ButtonStyle.primary, emoji="🔉", row=1)
    async def volume_down(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = interaction.guild.voice_client
        if not self._check_user_in_voice(interaction):
            return await interaction.response.send_message(
                "⚠️ Управлять радио могут только участники, находящиеся в этом голосовом канале!",
                ephemeral=True,
            )

        new_vol = max(0.1, round(self.state.volume - 0.1, 1))
        self.state.volume = new_vol
        if vc and vc.source and isinstance(vc.source, discord.PCMVolumeTransformer):
            vc.source.volume = new_vol

        embed = self.cog.build_embed(interaction.guild, self.state)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="+10%", style=discord.ButtonStyle.primary, emoji="🔊", row=1)
    async def volume_up(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = interaction.guild.voice_client
        if not self._check_user_in_voice(interaction):
            return await interaction.response.send_message(
                "⚠️ Управлять радио могут только участники, находящиеся в этом голосовом канале!",
                ephemeral=True,
            )

        new_vol = min(2.0, round(self.state.volume + 0.1, 1))
        self.state.volume = new_vol
        if vc and vc.source and isinstance(vc.source, discord.PCMVolumeTransformer):
            vc.source.volume = new_vol

        embed = self.cog.build_embed(interaction.guild, self.state)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Отключить", style=discord.ButtonStyle.danger, emoji="⏹️", row=1)
    async def stop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._check_user_in_voice(interaction):
            return await interaction.response.send_message(
                "⚠️ Отключить радио могут только участники, находящиеся в этом голосовом канале!",
                ephemeral=True,
            )

        await interaction.response.defer(ephemeral=True)
        await self.cog.stop_radio(interaction.guild, interaction=interaction)


class RadioCog(commands.Cog):
    """Модуль воспроизведения онлайн-радио в голосовых каналах."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.states: Dict[int, GuildRadioState] = {}

    def get_state(self, guild_id: int) -> GuildRadioState:
        if guild_id not in self.states:
            self.states[guild_id] = GuildRadioState(guild_id)
        return self.states[guild_id]

    def _get_target_voice_channel(
        self,
        channel: discord.abc.GuildChannel,
        member: discord.Member,
    ) -> Optional[discord.VoiceChannel | discord.StageChannel]:
        """Определяет целевой голосовой канал.

        Если команда вызвана в текстовом чате голосового канала (VoiceChannel / StageChannel),
        подключается именно к этому каналу.
        Иначе, если пользователь находится в войсе, подключается к его каналу.
        """
        # Если чат сам является голосовым каналом (встроенный чат войса в Discord)
        if isinstance(channel, (discord.VoiceChannel, discord.StageChannel)):
            return channel

        # Иначе проверяем, находится ли пользователь в войсе
        if member.voice and member.voice.channel:
            return member.voice.channel

        return None

    def _create_audio_source(self, url: str, volume: float) -> discord.PCMVolumeTransformer:
        ffmpeg_opts = {
            "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
            "options": "-vn",
        }
        source = discord.FFmpegPCMAudio(url, **ffmpeg_opts)
        return discord.PCMVolumeTransformer(source, volume=volume)

    def build_embed(self, guild: discord.Guild, state: GuildRadioState) -> discord.Embed:
        vc = guild.voice_client
        channel_name = "Не подключен"
        if vc and vc.channel:
            channel_name = vc.channel.name
        elif state.channel_id:
            ch = guild.get_channel(state.channel_id)
            if ch:
                channel_name = ch.name

        status_text = "⏸️ На паузе" if state.is_paused else "🟢 В эфире"
        vol_pct = int(round(state.volume * 100))

        # Полоса громкости
        bar_len = 10
        filled = min(bar_len, max(0, int(round((state.volume / 1.0) * (bar_len / 2)))))
        bar = "▰" * filled + "▱" * (bar_len - filled)

        embed = discord.Embed(
            title="📻 Онлайн Радиовещание",
            color=0x9B59B6,
            timestamp=discord.utils.utcnow(),
        )
        embed.set_thumbnail(url="https://cdn-icons-png.flaticon.com/512/3075/3075908.png")

        embed.add_field(
            name=f"{state.emoji} Текущая станция",
            value=f"**{state.display_name}**",
            inline=True,
        )
        embed.add_field(
            name="📡 Статус",
            value=f"`{status_text}`",
            inline=True,
        )
        embed.add_field(
            name="🔊 Голосовой канал",
            value=f"`#{channel_name}`",
            inline=True,
        )
        embed.add_field(
            name=f"🔈 Громкость: {vol_pct}%",
            value=f"`{bar}` ({vol_pct}%)",
            inline=False,
        )

        embed.set_footer(
            text="Управляйте радио кнопками ниже или выберите станцию в меню",
            icon_url=guild.icon.url if guild.icon else None,
        )
        return embed

    async def play_stream(
        self,
        guild: discord.Guild,
        target_channel: discord.VoiceChannel | discord.StageChannel,
        text_channel: discord.abc.Messageable,
        station_or_url: Optional[str] = None,
        interaction: Optional[discord.Interaction] = None,
    ):
        state = self.get_state(guild.id)
        state.channel_id = target_channel.id
        if hasattr(text_channel, "id"):
            state.text_channel_id = text_channel.id

        # Отменяем автоотключение, если было запланировано
        if state.disconnect_task and not state.disconnect_task.done():
            state.disconnect_task.cancel()
            state.disconnect_task = None

        # Разбор станции или прямой ссылки
        if station_or_url:
            clean = station_or_url.strip()
            if clean.startswith("http://") or clean.startswith("https://"):
                state.custom_url = clean
                state.custom_name = "Прямой аудиопоток"
            else:
                found_key = None
                for key, st in RADIO_STATIONS.items():
                    if clean.lower() in (key.lower(), st["name"].lower()):
                        found_key = key
                        break
                if found_key:
                    state.station_key = found_key
                    state.custom_url = None
                else:
                    state.station_key = DEFAULT_STATION_KEY
                    state.custom_url = None

        # Подключение к голосовому каналу
        vc: Optional[discord.VoiceClient] = guild.voice_client
        try:
            if not vc or not vc.is_connected():
                vc = await target_channel.connect()
            elif vc.channel.id != target_channel.id:
                await vc.move_to(target_channel)
        except Exception as e:
            err_str = str(e)
            logger.exception(f"Ошибка подключения к голосовому каналу {target_channel.name}: {e}")
            if "davey" in err_str.lower() or "nacl" in err_str.lower():
                msg = (
                    f"❌ **Не удалось подключиться к каналу:** {e}\n\n"
                    f"💡 *Для работы голоса в discord.py требуется библиотека `davey` и `PyNaCl`.*\n"
                    f"Они уже добавлены в `requirements.txt`. Перезапустите бота на сервере хостинга "
                    f"или выполните: `pip install davey PyNaCl`."
                )
            else:
                msg = f"❌ Не удалось подключиться к каналу **{target_channel.name}**: {e}"

            if interaction:
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await text_channel.send(msg, delete_after=15)
            return

        # Воспроизведение потока
        try:
            if vc.is_playing() or vc.is_paused():
                vc.stop()

            audio_source = self._create_audio_source(state.stream_url, state.volume)
            vc.play(audio_source, after=lambda err: self._on_playback_error(guild, err))
            state.is_paused = False
        except discord.ClientException as e:
            err_msg = str(e)
            logger.error(f"ClientException при воспроизведении радио: {err_msg}")
            msg = f"❌ Ошибка воспроизведения: {err_msg}"
            if interaction:
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await text_channel.send(msg, delete_after=15)
            return
        except FileNotFoundError:
            msg = "❌ **FFmpeg не найден на сервере!**\nДля работы радио необходимо установить `ffmpeg` на хостинге бота."
            logger.error(msg)
            if interaction:
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await text_channel.send(msg, delete_after=15)
            return
        except Exception as e:
            logger.exception(f"Непредвиденная ошибка воспроизведения радио: {e}")
            msg = f"❌ Ошибка запуска аудиопотока: {e}"
            if interaction:
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await text_channel.send(msg, delete_after=15)
            return

        # ========================================================
        # УСПЕШНЫЙ ЗАПУСК РАДИО:
        # Только здесь отправляем публичный виджет для всех участников!
        # ========================================================
        embed = self.build_embed(guild, state)
        view = RadioPlayerView(self, guild, state)

        # Удаляем предыдущий плеер, если был
        if state.message:
            try:
                await state.message.delete()
            except Exception:
                pass

        try:
            state.message = await text_channel.send(embed=embed, view=view)
        except Exception as e:
            logger.warning(f"Ошибка отправки публичной панели плеера: {e}")

        # Автору команды отправляем персональный ответ (ephemeral)
        if interaction:
            try:
                await interaction.followup.send(
                    f"📻 Радио **{state.display_name}** успешно запущено в канале **{target_channel.name}**!",
                    ephemeral=True,
                )
            except Exception:
                pass

    async def change_station(
        self,
        guild: discord.Guild,
        station_key: str,
        interaction: Optional[discord.Interaction] = None,
    ):
        state = self.get_state(guild.id)
        state.station_key = station_key
        state.custom_url = None

        vc: Optional[discord.VoiceClient] = guild.voice_client
        if vc and vc.is_connected():
            try:
                if vc.is_playing() or vc.is_paused():
                    vc.stop()
                audio_source = self._create_audio_source(state.stream_url, state.volume)
                vc.play(audio_source, after=lambda err: self._on_playback_error(guild, err))
                state.is_paused = False
            except Exception as e:
                logger.exception(f"Ошибка смены станции: {e}")

        embed = self.build_embed(guild, state)
        view = RadioPlayerView(self, guild, state)

        if state.message:
            try:
                await state.message.edit(embed=embed, view=view)
            except Exception:
                pass

        if interaction:
            try:
                await interaction.followup.send(
                    f"📻 Станция переключена на **{state.display_name}**", ephemeral=True
                )
            except Exception:
                pass

    async def stop_radio(
        self,
        guild: discord.Guild,
        interaction: Optional[discord.Interaction] = None,
    ):
        state = self.get_state(guild.id)
        if state.disconnect_task and not state.disconnect_task.done():
            state.disconnect_task.cancel()
            state.disconnect_task = None

        vc: Optional[discord.VoiceClient] = guild.voice_client
        if vc:
            if vc.is_playing() or vc.is_paused():
                vc.stop()
            await vc.disconnect(force=True)

        embed = discord.Embed(
            title="📻 Онлайн Радио",
            description="⏹️ Воспроизведение остановлено. Бот отключился от голосового канала.",
            color=0xE74C3C,
        )

        if state.message:
            try:
                await state.message.edit(embed=embed, view=None)
            except Exception:
                pass
            state.message = None

        if interaction:
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message("⏹️ Радио выключено.", ephemeral=True)
                else:
                    await interaction.followup.send("⏹️ Радио выключено.", ephemeral=True)
            except Exception:
                pass

    def _on_playback_error(self, guild: discord.Guild, error: Optional[Exception]):
        if error:
            logger.error(f"Ошибка потока радио на сервере {guild.name} ({guild.id}): {error}")

    # ==========================================
    # СЛЭШ-КОМАНДЫ
    # ==========================================

    @app_commands.command(
        name="radio",
        description="Подключить бота в голосовой канал и включить радио",
    )
    @app_commands.describe(
        station="Радиостанция (Record, Deep, Chill, DFM, Europa Plus, Lofi) или прямая ссылка на поток",
    )
    @app_commands.choices(
        station=[
            app_commands.Choice(name="📻 Radio Record (Танцевальная музыка)", value="record"),
            app_commands.Choice(name="🌊 Record Deep (Deep House)", value="deep"),
            app_commands.Choice(name="☕ Record Chill-Out (Релакс / Чилл)", value="chill"),
            app_commands.Choice(name="🇷🇺 Record Russian Hits (Русские хиты)", value="russian"),
            app_commands.Choice(name="⭐ Europa Plus (Поп / Мировые хиты)", value="europa"),
            app_commands.Choice(name="🔥 DFM (Клубная танцевальная музыка)", value="dfm"),
            app_commands.Choice(name="🎧 Lofi Chill Radio (Lofi биты для учебы/отдыха)", value="lofi"),
            app_commands.Choice(name="🎶 Новое Радио (Свежие суперхиты)", value="newradio"),
        ]
    )
    async def slash_radio(
        self,
        interaction: discord.Interaction,
        station: Optional[str] = None,
    ):
        target_channel = self._get_target_voice_channel(interaction.channel, interaction.user)
        if not target_channel:
            return await interaction.response.send_message(
                "⚠️ **Вы должны находиться в голосовом канале** или ввести команду в текстовом чате нужного голосового канала!",
                ephemeral=True,
            )

        # Все промежуточные статусы и ошибки видит ТОЛЬКО автор команды
        await interaction.response.defer(ephemeral=True)
        await self.play_stream(
            guild=interaction.guild,
            target_channel=target_channel,
            text_channel=interaction.channel,
            station_or_url=station,
            interaction=interaction,
        )

    @app_commands.command(
        name="radio_stop",
        description="Остановить воспроизведение радио и отключить бота от голосового канала",
    )
    async def slash_radio_stop(self, interaction: discord.Interaction):
        vc = interaction.guild.voice_client
        if not vc or not vc.is_connected():
            return await interaction.response.send_message(
                "⚠️ Бот в данный момент не подключен к голосовому каналу.",
                ephemeral=True,
            )
        await interaction.response.defer(ephemeral=True)
        await self.stop_radio(interaction.guild, interaction=interaction)

    # ==========================================
    # ТЕКСТОВЫЕ КОМАНДЫ ПРЕФИКСА (!)
    # ==========================================

    @commands.command(name="radio", aliases=["радио", "play", "join", "connect"])
    async def cmd_radio(self, ctx: commands.Context, *, station: Optional[str] = None):
        """Включить радио в голосовом канале."""
        target_channel = self._get_target_voice_channel(ctx.channel, ctx.author)
        if not target_channel:
            return await ctx.send(
                "⚠️ **Вы должны находиться в голосовом канале** или ввести команду прямо в текстовом чате голосового канала!",
                delete_after=12,
            )

        try:
            await ctx.message.delete()
        except Exception:
            pass

        await self.play_stream(
            guild=ctx.guild,
            target_channel=target_channel,
            text_channel=ctx.channel,
            station_or_url=station,
        )

    @commands.command(name="stop", aliases=["стоп", "leave", "disconnect", "radio_stop"])
    async def cmd_stop(self, ctx: commands.Context):
        """Остановить радио и выйти из голосового канала."""
        vc = ctx.guild.voice_client
        if not vc or not vc.is_connected():
            return await ctx.send("⚠️ Бот в данный момент не подключен к голосовому каналу.", delete_after=10)

        try:
            await ctx.message.delete()
        except Exception:
            pass

        await self.stop_radio(ctx.guild)

    @commands.command(name="volume", aliases=["громкость", "vol"])
    async def cmd_volume(self, ctx: commands.Context, volume: int):
        """Установить громкость от 1 до 100%."""
        if volume < 1 or volume > 150:
            return await ctx.send("⚠️ Укажите громкость от 1 до 100%.", delete_after=10)

        state = self.get_state(ctx.guild.id)
        state.volume = volume / 100.0

        vc = ctx.guild.voice_client
        if vc and vc.source and isinstance(vc.source, discord.PCMVolumeTransformer):
            vc.source.volume = state.volume

        if state.message:
            try:
                embed = self.build_embed(ctx.guild, state)
                view = RadioPlayerView(self, ctx.guild, state)
                await state.message.edit(embed=embed, view=view)
            except Exception:
                pass

        try:
            await ctx.message.delete()
        except Exception:
            pass

    # ==========================================
    # АВТООТКЛЮЧЕНИЕ ПРИ ПУСТОМ КАНАЛЕ
    # ==========================================

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ):
        """Если все слушатели вышли из канала, бот автоматически отключается через 90 сек."""
        guild = member.guild
        vc: Optional[discord.VoiceClient] = guild.voice_client
        if not vc or not vc.channel:
            return

        # Проверяем, сколько живых пользователей (не ботов) осталось в канале
        human_listeners = [m for m in vc.channel.members if not m.bot]
        state = self.get_state(guild.id)

        if len(human_listeners) == 0:
            if state.disconnect_task is None or state.disconnect_task.done():
                state.disconnect_task = asyncio.create_task(self._auto_disconnect_after_delay(guild, 90))
        else:
            if state.disconnect_task and not state.disconnect_task.done():
                state.disconnect_task.cancel()
                state.disconnect_task = None

    async def _auto_disconnect_after_delay(self, guild: discord.Guild, delay_seconds: int):
        try:
            await asyncio.sleep(delay_seconds)
            vc: Optional[discord.VoiceClient] = guild.voice_client
            if vc and vc.channel:
                human_listeners = [m for m in vc.channel.members if not m.bot]
                if len(human_listeners) == 0:
                    logger.info(f"В канале {vc.channel.name} не осталось слушателей. Автоотключение радио.")
                    await self.stop_radio(guild)
        except asyncio.CancelledError:
            pass


async def setup(bot: commands.Bot):
    await bot.add_cog(RadioCog(bot))
