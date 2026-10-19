import os
import asyncio
import aiohttp
import io
import collections
import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput, UserSelect
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

# Скриншоттағы сіздің ID-леріңіз сақталды:
AUTO_ROLE_ID = 1532847437125783805
SERVER_LOG_CHANNEL_ID = 1561671362647691284
GIRL_LOG_CHANNEL_ID = 1557052405194166405

# Деңгей көтерілгенде хабарлама баратын арна ID-сін осы жерге жазыңыз:
LEVEL_CHANNEL_ID = 1542652618734575738

GIRL_BANNER_URL = "https://media.discordapp.net/attachments/1544309714962227230/1557815971660435456/banner_girl.png?ex=6ac92cae&is=6ac7db2e&hm=250e0baedfe61fc5baff21e59e0e6bd61f5e494d88ade315be12b6e3c199c916&=&format=webp&quality=lossless&width=2048&height=729"
GIRL_STAFF_ROLE_IDS = [1554889319574143088, 1556691625294696559]

temp_voice_channels = {}

# --------------------------------------------------
# LEVEL / XP SYSTEM DATA
# --------------------------------------------------
user_xp = collections.defaultdict(int)
user_level = collections.defaultdict(lambda: 1)

def xp_for_level(level):
    return level * 100

# --------------------------------------------------
# HELPER FUNCTIONS
# --------------------------------------------------
async def send_custom_log(guild: discord.Guild, channel_id: int, emoji: str, title: str, description_lines: list, color: discord.Color):
    if channel_id == 0: return
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
# TEMP VOICE INTERFACE & MODALS
# --------------------------------------------------
class VoiceRenameModal(Modal, title="Изменить название"):
    channel_name = TextInput(label="Новое название канала", placeholder="Введите название...", required=True, max_length=100)
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.user.voice.channel.edit(name=self.channel_name.value)
        await interaction.response.send_message(f"✅ Канал переименован в: **{self.channel_name.value}**", ephemeral=True)

class VoiceLimitModal(Modal, title="Лимит пользователей"):
    user_limit = TextInput(label="Лимит мест (0-99)", placeholder="0 — без лимита", required=True, max_length=2)
    async def on_submit(self, interaction: discord.Interaction):
        try:
            val = int(self.user_limit.value)
            if 0 <= val <= 99:
                await interaction.user.voice.channel.edit(user_limit=val)
                await interaction.response.send_message(f"✅ Лимит мест установлен: **{val}**", ephemeral=True)
            else:
                await interaction.response.send_message("❌ Введите число от 0 до 99.", ephemeral=True)
        except ValueError:
            await interaction.response.send_message("❌ Введите корректное число.", ephemeral=True)

class VoiceUserSelectView(View):
    def __init__(self, action: str):
        super().__init__(timeout=60)
        self.action = action

    @discord.ui.select(cls=UserSelect, placeholder="Выберите пользователя...")
    async def select_user(self, interaction: discord.Interaction, select: UserSelect):
        target_member = select.values[0]
        voice_channel = interaction.user.voice.channel

        if self.action == "trust":
            await voice_channel.set_permissions(target_member, connect=True, view_channel=True)
            await interaction.response.send_message(f"✅ Пользователь {target_member.mention} добавлен в доверенные.", ephemeral=True)
        elif self.action == "untrust":
            await voice_channel.set_permissions(target_member, overwrite=None)
            await interaction.response.send_message(f"➖ Доверие с {target_member.mention} снято.", ephemeral=True)
        elif self.action == "kick":
            if target_member in voice_channel.members:
                await target_member.move_to(None)
                await interaction.response.send_message(f"👢 Пользователь {target_member.mention} выгнан из канала.", ephemeral=True)
            else:
                await interaction.response.send_message("❌ Пользователь не в вашем канале.", ephemeral=True)
        elif self.action == "ban":
            await voice_channel.set_permissions(target_member, connect=False)
            if target_member in voice_channel.members:
                await target_member.move_to(None)
            await interaction.response.send_message(f"🚫 Пользователь {target_member.mention} заблокирован.", ephemeral=True)
        elif self.action == "unban":
            await voice_channel.set_permissions(target_member, overwrite=None)
            await interaction.response.send_message(f"✅ Разблокирован пользователь {target_member.mention}.", ephemeral=True)
        elif self.action == "transfer":
            temp_voice_channels[voice_channel.id] = target_member.id
            await interaction.response.send_message(f"👑 Владение каналом передано {target_member.mention}.", ephemeral=True)

class TempVoiceControlView(View):
    def __init__(self):
        super().__init__(timeout=None)

    def check_owner(self, interaction: discord.Interaction):
        if not interaction.user.voice or not interaction.user.voice.channel:
            return False, "❌ Вы должны находиться в своем приватном канале!"
        voice_channel = interaction.user.voice.channel
        owner_id = temp_voice_channels.get(voice_channel.id)
        if not owner_id or owner_id != interaction.user.id:
            return False, "❌ Вы не являетесь владельцем этого приватного канала!"
        return True, voice_channel

    @discord.ui.button(emoji="🔤", style=discord.ButtonStyle.secondary, custom_id="tv_rename", row=0)
    async def rename_btn(self, interaction: discord.Interaction, button: Button):
        ok, res = self.check_owner(interaction)
        if not ok: return await interaction.response.send_message(res, ephemeral=True)
        await interaction.response.send_modal(VoiceRenameModal())

    @discord.ui.button(emoji="👥", style=discord.ButtonStyle.secondary, custom_id="tv_limit", row=0)
    async def limit_btn(self, interaction: discord.Interaction, button: Button):
        ok, res = self.check_owner(interaction)
        if not ok: return await interaction.response.send_message(res, ephemeral=True)
        await interaction.response.send_modal(VoiceLimitModal())

    @discord.ui.button(emoji="🔒", style=discord.ButtonStyle.secondary, custom_id="tv_lock", row=0)
    async def lock_btn(self, interaction: discord.Interaction, button: Button):
        ok, res = self.check_owner(interaction)
        if not ok: return await interaction.response.send_message(res, ephemeral=True)
        await res.set_permissions(interaction.guild.default_role, connect=False)
        await interaction.response.send_message("🔒 Канал закрыт от всех.", ephemeral=True)

    @discord.ui.button(emoji="🔓", style=discord.ButtonStyle.secondary, custom_id="tv_unlock", row=0)
    async def unlock_btn(self, interaction: discord.Interaction, button: Button):
        ok, res = self.check_owner(interaction)
        if not ok: return await interaction.response.send_message(res, ephemeral=True)
        await res.set_permissions(interaction.guild.default_role, connect=True)
        await interaction.response.send_message("🔓 Канал открыт для всех.", ephemeral=True)

    @discord.ui.button(emoji="👤", style=discord.ButtonStyle.secondary, custom_id="tv_trust", row=1)
    async def trust_btn(self, interaction: discord.Interaction, button: Button):
        ok, res = self.check_owner(interaction)
        if not ok: return await interaction.response.send_message(res, ephemeral=True)
        await interaction.response.send_message("Выберите пользователя для доверия:", view=VoiceUserSelectView("trust"), ephemeral=True)

    @discord.ui.button(emoji="🚫", style=discord.ButtonStyle.secondary, custom_id="tv_ban", row=1)
    async def ban_btn(self, interaction: discord.Interaction, button: Button):
        ok, res = self.check_owner(interaction)
        if not ok: return await interaction.response.send_message(res, ephemeral=True)
        await interaction.response.send_message("Выберите кого забанить:", view=VoiceUserSelectView("ban"), ephemeral=True)

    @discord.ui.button(emoji="👢", style=discord.ButtonStyle.secondary, custom_id="tv_kick", row=1)
    async def kick_btn(self, interaction: discord.Interaction, button: Button):
        ok, res = self.check_owner(interaction)
        if not ok: return await interaction.response.send_message(res, ephemeral=True)
        await interaction.response.send_message("Выберите кого выгнать:", view=VoiceUserSelectView("kick"), ephemeral=True)

    @discord.ui.button(emoji="👑", style=discord.ButtonStyle.secondary, custom_id="tv_transfer", row=2)
    async def transfer_btn(self, interaction: discord.Interaction, button: Button):
        ok, res = self.check_owner(interaction)
        if not ok: return await interaction.response.send_message(res, ephemeral=True)
        await interaction.response.send_message("Выберите нового владельца:", view=VoiceUserSelectView("transfer"), ephemeral=True)

    @discord.ui.button(emoji="🗑️", style=discord.ButtonStyle.danger, custom_id="tv_delete", row=2)
    async def delete_btn(self, interaction: discord.Interaction, button: Button):
        ok, res = self.check_owner(interaction)
        if not ok: return await interaction.response.send_message(res, ephemeral=True)
        await interaction.response.send_message("🗑️ Удаление канала...", ephemeral=True)
        del temp_voice_channels[res.id]
        await res.delete()

# --------------------------------------------------
# MUSIC SYSTEM CONFIGURATION
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
            asyncio.run_coroutine_threadsafe(ctx.send(f"❌ Ошибка воспроизведения: `{e}`"), bot.loop)
            play_next(ctx)
    else:
        asyncio.run_coroutine_threadsafe(ctx.send("🎶 Очередь воспроизведения пуста."), bot.loop)

# --------------------------------------------------
# TICKET CONTROL & VIEWS
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
# BOT INIT & PRESENCE STATUS
# --------------------------------------------------
class KiroBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        self.add_view(GirlTicketMainView())
        self.add_view(TicketControlView())
        self.add_view(TempVoiceControlView())

    async def on_ready(self):
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
# MEMBER JOIN (AUTO-ROLE ONLY)
# --------------------------------------------------
@bot.event
async def on_member_join(member):
    if AUTO_ROLE_ID != 0:
        role = member.guild.get_role(AUTO_ROLE_ID)
        if role:
            try:
                await member.add_roles(role, reason="Авто-роль при входе")
            except Exception as e:
                print(f"Ошибка выдачи авто-роли: {e}")

# --------------------------------------------------
# MESSAGE EVENT (XP & LEVEL SYSTEM)
# --------------------------------------------------
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    # XP қосу
    u_id = message.author.id
    user_xp[u_id] += 15
    curr_lvl = user_level[u_id]
    
    # Деңгей көтерілуін тексеру
    if user_xp[u_id] >= xp_for_level(curr_lvl):
        user_level[u_id] += 1
        new_lvl = user_level[u_id]
        
        # Хабарлама жазу (Скриншоттағыдай дәл мәтінмен)
        lvl_msg = f"Кутты болсын котакбас {message.author.mention}! Котерылдын {new_lvl} уровня!"
        
        target_ch = message.guild.get_channel(LEVEL_CHANNEL_ID) if LEVEL_CHANNEL_ID != 0 else message.channel
        if target_ch:
            await target_ch.send(lvl_msg)

    await bot.process_commands(message)

# --------------------------------------------------
# VOICE AUTO-CREATION & LOGS
# --------------------------------------------------
@bot.event
async def on_voice_state_update(member, before, after):
    if after.channel and "создать войс" in after.channel.name.lower():
        v_ch = await member.guild.create_voice_channel(
            name=f"Комната {member.name}", 
            category=after.channel.category
        )
        await v_ch.set_permissions(member, connect=True, speak=True, manage_channels=True)
        temp_voice_channels[v_ch.id] = member.id
        await member.move_to(v_ch)

    if before.channel and before.channel.id in temp_voice_channels:
        if len(before.channel.members) == 0:
            del temp_voice_channels[before.channel.id]
            await before.channel.delete()

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
# SERVER LOGS EVENTS
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

# --------------------------------------------------
# CLEAR & VOICE PANEL COMMANDS
# --------------------------------------------------
@bot.command(name="clear", aliases=["purge", "clean"])
@commands.has_permissions(manage_messages=True)
async def clear_messages(ctx, amount: int = 10):
    deleted = await ctx.channel.purge(limit=amount + 1)
    confirm_msg = await ctx.send(f"🧹 Успешно удалено **{len(deleted) - 1}** сообщений!")
    await asyncio.sleep(3)
    await confirm_msg.delete()

@bot.command()
async def send_voice_panel(ctx):
    embed = discord.Embed(
        title="🔊 TempVoice Interface",
        description=(
            "Этот **интерфейс** можно использовать для управления личными каналами.\n"
            "Дополнительные возможности доступны через кнопки ниже.\n\n"
            "🔤 **НАЗВАНИЕ** | 👥 **ЛИМИТ** | 🔒 **ДОСТУП**\n"
            "👤 **ДОВЕРЯТЬ** | 🚫 **ЗАБАНИТЬ** | 👢 **ВЫГНАТЬ**\n"
            "👑 **ПЕРЕДАТЬ** | 🗑️ **УДАЛИТЬ**\n\n"
            "*Нажмите нужную кнопку ниже для управления каналом.*"
        ),
        color=discord.Color.from_rgb(220, 50, 50)
    )
    await ctx.send(embed=embed, view=TempVoiceControlView())

# --------------------------------------------------
# MUSIC COMMANDS
# --------------------------------------------------
@bot.command(name="play", aliases=["p"])
async def play(ctx, *, search: str):
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
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.stop()
        await ctx.send("⏭️ Трек пропущен!")
    else:
        await ctx.send("❌ Сейчас ничего не играет.")

@bot.command(name="stop")
async def stop(ctx):
    if ctx.voice_client:
        music_queues[ctx.guild.id].clear()
        ctx.voice_client.stop()
        await ctx.send("⏹️ Воспроизведение остановлено, очередь очищена.")

@bot.command(name="leave")
async def leave(ctx):
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
