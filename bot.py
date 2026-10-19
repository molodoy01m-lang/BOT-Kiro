import os
import asyncio
import aiohttp
import io
import collections
import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput
from flask import Flask
from threading import Thread
import yt_dlp

# --------------------------------------------------
# WEB SERVER FOR RENDER 24/7
# --------------------------------------------------
app = Flask('')

@app.route('/')
def home():
    return "KIRO BOT is Alive!"

def run_web():
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_web, daemon=True)
    t.start()

keep_alive()

# --------------------------------------------------
# DISCORD BOT SETUP & INTENTS
# --------------------------------------------------
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.voice_states = True
intents.moderation = True
intents.guilds = True

# ЛОГ АРНАЛАРЫНЫҢ ID-ЛЕРІ
SERVER_LOG_CHANNEL_ID = 1561671362647691284  # Сервер логтары (Бан, разбан, сообщение өшу, войс)
GIRL_LOG_CHANNEL_ID = 1557052405194166405    # Девушка тикетінің логтары

GIRL_BANNER_URL = "https://media.discordapp.net/attachments/1544309714962227230/1557815971660435456/banner_girl.png?ex=6ac92cae&is=6ac7db2e&hm=250e0baedfe61fc5baff21e59e0e6bd61f5e494d88ade315be12b6e3c199c916&=&format=webp&quality=lossless&width=2048&height=729"
GIRL_STAFF_ROLE_IDS = [1556691625294696559, 1554889319574143088]

# --------------------------------------------------
# LOG HELPER FUNCTION
# --------------------------------------------------
async def send_custom_log(guild: discord.Guild, channel_id: int, emoji: str, title: str, description_lines: list, color: discord.Color):
    log_channel = guild.get_channel(channel_id)
    if log_channel:
        desc = "\n".join(description_lines)
        embed = discord.Embed(
            title=f"{emoji} {title}",
            description=desc,
            color=color,
            timestamp=discord.utils.utcnow()
        )
        await log_channel.send(embed=embed)

async def get_discord_file_from_url(url: str, filename: str):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status == 200:
                data = await resp.read()
                return discord.File(io.BytesIO(data), filename=filename)
    return None

def has_staff_permission(member: discord.Member) -> bool:
    user_role_ids = [role.id for role in member.roles]
    return any(role_id in user_role_ids for role_id in GIRL_STAFF_ROLE_IDS)

# --------------------------------------------------
# MUSIC SYSTEM CONFIGURATION (SOUNDCLOUD ENGINE)
# --------------------------------------------------
music_queues = collections.defaultdict(list)

YTDL_OPTIONS = {
    'format': 'bestaudio/best',
    'extractaudio': True,
    'audioformat': 'mp3',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'scsearch',
    'source_address': '0.0.0.0'
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}

ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)

def play_next(ctx):
    if len(music_queues[ctx.guild.id]) > 0:
        url, title = music_queues[ctx.guild.id].pop(0)
        try:
            source = discord.FFmpegPCMAudio(url, **FFMPEG_OPTIONS)
            ctx.voice_client.play(source, after=lambda e: play_next(ctx))
            asyncio.run_coroutine_threadsafe(ctx.send(f"🎵 Сейчас играет: **{title}**"), bot.loop)
        except Exception as e:
            asyncio.run_coroutine_threadsafe(ctx.send(f"❌ Ошибка воспроизведения следующего трека: `{e}`"), bot.loop)
            play_next(ctx)
    else:
        asyncio.run_coroutine_threadsafe(ctx.send("🎶 Очередь воспроизведения пуста."), bot.loop)

# --------------------------------------------------
# TICKET CONTROL & VIEWS WITH GIRL LOGS
# --------------------------------------------------
class TicketControlView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Взяться", style=discord.ButtonStyle.success, custom_id="kiro_ticket_take")
    async def take_button(self, interaction: discord.Interaction, button: Button):
        if not has_staff_permission(interaction.user):
            return await interaction.response.send_message("❌ У вас нет прав!", ephemeral=True)
        await interaction.response.defer()
        await interaction.followup.send(f"**{interaction.user.mention}** взял(а)ся за тикет!")

    @discord.ui.button(label="Взять на рассмотрение", style=discord.ButtonStyle.primary, custom_id="kiro_ticket_review")
    async def review_button(self, interaction: discord.Interaction, button: Button):
        if not has_staff_permission(interaction.user):
            return await interaction.response.send_message("❌ У вас нет прав!", ephemeral=True)
        await interaction.response.defer()
        await interaction.followup.send(f"**{interaction.user.mention}** взял тикет на рассмотрение.")

    @discord.ui.button(label="Закрыть тикет", style=discord.ButtonStyle.danger, custom_id="kiro_ticket_close")
    async def close_button(self, interaction: discord.Interaction, button: Button):
        if not has_staff_permission(interaction.user):
            return await interaction.response.send_message("❌ У вас нет прав!", ephemeral=True)
        
        # GIRL LOG: Тикет жабылғанда
        await send_custom_log(
            guild=interaction.guild,
            channel_id=GIRL_LOG_CHANNEL_ID,
            emoji="🌸",
            title="Тикет роли Девушка закрыт",
            description_lines=[
                f"**Канал:** `{interaction.channel.name}`",
                f"**Модератор:** {interaction.user.name} ({interaction.user.mention})"
            ],
            color=discord.Color.from_rgb(255, 105, 180)
        )

        await interaction.response.send_message("***Тикет закрывается...***", ephemeral=False)
        await asyncio.sleep(3)
        await interaction.channel.delete(reason="Тикет закрыт")


class GirlTicketMainView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Получить роль девушка", emoji="🌸", style=discord.ButtonStyle.secondary, custom_id="kiro_open_girl_ticket")
    async def open_girl_ticket(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        user = interaction.user
        ch_name = f"девушка-{user.name}"
        
        if discord.utils.get(guild.text_channels, name=ch_name):
            return await interaction.followup.send("У вас уже открыт тикет!", ephemeral=True)
        
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False), 
            user: discord.PermissionOverwrite(read_messages=True, send_messages=True), 
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        pings = [guild.get_role(r).mention for r in GIRL_STAFF_ROLE_IDS if guild.get_role(r)]
        for r_id in GIRL_STAFF_ROLE_IDS:
            if guild.get_role(r_id): 
                overwrites[guild.get_role(r_id)] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

        t_channel = await guild.create_text_channel(name=ch_name, category=interaction.channel.category, overwrites=overwrites)
        
        embed = discord.Embed(
            description=(
                "**🌸 Заявка на роль Девушки**\n\n"
                "• Ожидайте ответа модераторов.\n"
                "• Подготовьте доказательства для верификации."
            ), 
            color=discord.Color.from_rgb(255, 105, 180)
        )
        embed.add_field(name="• Пользователь", value=user.mention)
        
        await t_channel.send(content=f"{user.mention} " + " ".join(pings), embed=embed, view=TicketControlView())
        
        # GIRL LOG: Тикет ашылғанда
        await send_custom_log(
            guild=guild,
            channel_id=GIRL_LOG_CHANNEL_ID,
            emoji="🌸",
            title="Создан тикет Девушки",
            description_lines=[
                f"**Пользователь:** {user.name} ({user.mention})",
                f"**Канал:** {t_channel.mention}"
            ],
            color=discord.Color.from_rgb(255, 105, 180)
        )

        await interaction.followup.send(f"Ваш тикет создан: {t_channel.mention}", ephemeral=True)

# --------------------------------------------------
# BOT INITIALIZATION & PRESENCE STATUS
# --------------------------------------------------
class KiroBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        self.add_view(GirlTicketMainView())
        self.add_view(TicketControlView())

    async def on_ready(self):
        # БОТ СТАТУСЫ: "Смотрит kiro.discord | /help"
        activity = discord.Activity(
            type=discord.ActivityType.watching, 
            name="kiro.discord | /help"
        )
        await self.change_presence(activity=activity)
        print("==========================================")
        print(f" KIRO BOT УСПЕШНО ЗАПУЩЕН: {self.user} ")
        print("==========================================")

bot = KiroBot()

# --------------------------------------------------
# SERVER LOGS EVENTS (СЕРВЕР ЛОГТАРЫ)
# --------------------------------------------------
@bot.event
async def on_message_delete(message):
    if message.author.bot: return
    await send_custom_log(
        guild=message.guild,
        channel_id=SERVER_LOG_CHANNEL_ID,
        emoji="🗑️",
        title="Удаление сообщения",
        description_lines=[
            f"**Автор:** {message.author.name} ({message.author.mention})",
            f"**Канал:** {message.channel.mention}",
            f"**Содержание:**\n`{message.content or 'Медиа / Вложение'}`"
        ],
        color=discord.Color.red()
    )

@bot.event
async def on_member_ban(guild, user):
    async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.ban):
        moderator = entry.user
        reason = entry.reason or "Не указана"
        break
    else:
        moderator = None
        reason = "Не указана"

    log_channel = guild.get_channel(SERVER_LOG_CHANNEL_ID)
    if log_channel:
        embed = discord.Embed(title="🚫 Бан выдан", color=discord.Color.red())
        embed.add_field(name="Игрок", value=f"{user.mention}\n`{user.id}`", inline=True)
        embed.add_field(name="Разбан", value="Никогда", inline=True)
        embed.add_field(name="Причина", value=f"`{reason}`", inline=True)
        
        mod_name = moderator.name if moderator else "Неизвестно"
        mod_id = moderator.id if moderator else "00000000"
        embed.set_footer(text=f"Администратор: {mod_name} • {mod_id}")
        embed.set_thumbnail(url=user.display_avatar.url)
        await log_channel.send(embed=embed)

@bot.event
async def on_member_unban(guild, user):
    async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.unban):
        moderator = entry.user
        reason = entry.reason or "Снято из профиля"
        break
    else:
        moderator = None
        reason = "Снято из профиля"

    log_channel = guild.get_channel(SERVER_LOG_CHANNEL_ID)
    if log_channel:
        embed = discord.Embed(title="✅ Бан снят", color=discord.Color.green())
        embed.add_field(name="Игрок", value=f"{user.mention}\n`{user.id}`", inline=True)
        embed.add_field(name="Причина разбана", value=f"`{reason}`", inline=True)
        
        mod_name = moderator.name if moderator else "Неизвестно"
        mod_id = moderator.id if moderator else "00000000"
        embed.set_footer(text=f"Администратор: {mod_name} • {mod_id}")
        embed.set_thumbnail(url=user.display_avatar.url)
        await log_channel.send(embed=embed)

@bot.event
async def on_voice_state_update(member, before, after):
    guild = member.guild
    if before.channel is None and after.channel is not None:
        await send_custom_log(
            guild=guild,
            channel_id=SERVER_LOG_CHANNEL_ID,
            emoji="🎙️",
            title="Подключение к голосовому каналу",
            description_lines=[
                f"**Участник:** {member.name} ({member.mention})",
                f"**Канал:** {after.channel.mention}"
            ],
            color=discord.Color.green()
        )
    elif before.channel is not None and after.channel is None:
        await send_custom_log(
            guild=guild,
            channel_id=SERVER_LOG_CHANNEL_ID,
            emoji="🚪",
            title="Отключение от голосового канала",
            description_lines=[
                f"**Участник:** {member.name} ({member.mention})",
                f"**Канал:** {before.channel.mention}"
            ],
            color=discord.Color.red()
        )

# --------------------------------------------------
# MUSIC COMMANDS (!play, !skip, !stop, !leave)
# --------------------------------------------------
@bot.command(name="play", aliases=["p"])
async def play(ctx, *, search: str):
    """Воспроизведение музыки через SoundCloud"""
    if not ctx.author.voice:
        return await ctx.send("❌ Сначала зайдите в голосовой канал!")

    voice_channel = ctx.author.voice.channel

    if not ctx.voice_client:
        try:
            await voice_channel.connect()
        except Exception as e:
            return await ctx.send(f"❌ Ошибка подключения к голосовому каналу: `{e}`")

    msg = await ctx.send("🔍 Поиск трека...")
    query = search if search.startswith("http://") or search.startswith("https://") else f"scsearch:{search}"

    try:
        loop = asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(query, download=False))

        if not data:
            return await msg.edit(content="❌ Не удалось найти этот трек.")

        if 'entries' in data and len(data['entries']) > 0:
            data = data['entries'][0]

        song_url = data.get('url')
        song_title = data.get('title', 'Трек')

        if not song_url:
            return await msg.edit(content="❌ Не удалось получить ссылку на аудипоток.")

        if ctx.voice_client.is_playing() or ctx.voice_client.is_paused():
            music_queues[ctx.guild.id].append((song_url, song_title))
            await msg.edit(content=f"➕ Добавлено в очередь: **{song_title}**")
        else:
            try:
                source = discord.FFmpegPCMAudio(song_url, **FFMPEG_OPTIONS)
                ctx.voice_client.play(source, after=lambda e: play_next(ctx))
                await msg.edit(content=f"🎵 Сейчас играет: **{song_title}**")
            except Exception as e:
                await msg.edit(content=f"❌ Ошибка воспроизведения FFmpeg: `{e}`")

    except Exception as e:
        await msg.edit(content=f"❌ Ошибка поиска трека: `{e}`")


@bot.command(name="skip", aliases=["s"])
async def skip(ctx):
    """Пропустить текущий трек"""
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.stop()
        await ctx.send("⏭️ Трек пропущен!")
    else:
        await ctx.send("❌ Сейчас ничего не играет.")


@bot.command(name="stop")
async def stop(ctx):
    """Остановить воспроизведение и очистить очередь"""
    if ctx.voice_client:
        music_queues[ctx.guild.id].clear()
        ctx.voice_client.stop()
        await ctx.send("⏹️ Воспроизведение остановлено, очередь очищена.")


@bot.command(name="leave")
async def leave(ctx):
    """Отключить бота от голосового канала"""
    if ctx.voice_client:
        music_queues[ctx.guild.id].clear()
        await ctx.voice_client.disconnect()
        await ctx.send("👋 Бот отключился от голосового канала.")
    else:
        await ctx.send("❌ Бот не находится в голосовом канале.")

# --------------------------------------------------
# PANEL COMMAND (С БАННЕРОМ)
# --------------------------------------------------
@bot.command()
async def send_girl_ticket(ctx):
    # Баннер суретін жіберу бөлімі:
    file = await get_discord_file_from_url(GIRL_BANNER_URL, "banner_girl.png")
    if file:
        img_embed = discord.Embed(color=discord.Color.from_rgb(255, 105, 180)).set_image(url="attachment://banner_girl.png")
        await ctx.send(file=file, embed=img_embed)
        
    text_embed = discord.Embed(
        description=(
            "💗 **Роль Девушка**\n\n"
            "• Нажмите кнопку ниже, чтобы создать тикет для верификации и получения роли Девушка\n\n"
            "» **Информация**\n"
            "• Создайте тикет для верификации\n"
            "• Предоставьте доказательства\n"
            "• Модераторы рассмотрят ваш запрос\n\n"
            "» Чтобы получить роль, откройте тикет или обратитесь к администрации сервера."
        ), 
        color=discord.Color.from_rgb(255, 105, 180)
    )
    await ctx.send(embed=text_embed, view=GirlTicketMainView())

# --------------------------------------------------
# RUN BOT
# --------------------------------------------------
raw_token = os.getenv("DISCORD_TOKEN")

if not raw_token:
    print("❌ КРИТИЧЕСКАЯ ОШИБКА: DISCORD_TOKEN не найден!")
else:
    token = raw_token.strip().strip('"').strip("'")
    try:
        bot.run(token)
    except Exception as e:
        print(f"❌ ОШИБКА ЗАПУСКА: {e}")
