import os
import asyncio
import aiohttp
import io
import random
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
    return "ALASH PROJECT BOT is Alive!"

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

AUTO_ROLE_ID = 1555292717830119514
WELCOME_CHANNEL_ID = 1497873420216439016
LEVEL_CHANNEL_ID = 1498243470513405992

CLAN_LOG_CHANNEL_ID = 1558250408617443398 
SERVER_LOG_CHANNEL_ID = 1535037929163063548 

SERVER_CONNECT_IP = "connect connect.alashproject.kz"

user_levels = {}
verified_users = {}

clans_db = {}
user_clan_mapping = {}
active_lobbies = {}

GIRL_BANNER_URL = "https://media.discordapp.net/attachments/1544309714962227230/1557815971660435456/banner_girl.png?ex=6ac92cae&is=6ac7db2e&hm=250e0baedfe61fc5baff21e59e0e6bd61f5e494d88ade315be12b6e3c199c916&=&format=webp&quality=lossless&width=2048&height=729"
MEDIA_BANNER_URL = "https://multibot.pro/api/embeds/images/nfmpvssumgp3km0o"
TICKET_BANNER_URL = "https://multibot.pro/api/embeds/images/g4mmec3lwfcrwi4l"

STAFF_ROLE_IDS = [
    1557002520696463431, 1532745811778207985, 1530888080905601044,
    1530890552676188301, 1530886657530925256, 1530888429888602152
]
GIRL_STAFF_ROLE_IDS = [1532745811778207985, 1530890552676188301, 1530886657530925256]
MEDIA_STAFF_ROLE_IDS = [1530888828246556753, 1532745811778207985, 1530886657530925256]

MEDIA_ROLE_ID = 1530924449912586351
temp_voice_channels = {}
CYBERSHOK_MAPS = ["de_mirage", "de_inferno", "de_dust2", "de_nuke", "de_anubis", "de_ancient", "de_vertigo"]

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


def has_staff_permission(member: discord.Member, channel_name: str) -> bool:
    user_role_ids = [role.id for role in member.roles]
    if "девушка" in channel_name:
        required_roles = GIRL_STAFF_ROLE_IDS
    elif "медиа" in channel_name:
        required_roles = MEDIA_STAFF_ROLE_IDS
    else:
        required_roles = STAFF_ROLE_IDS
    return any(role_id in user_role_ids for role_id in required_roles)


# --------------------------------------------------
# CYBERSHOK MAP BAN & CAPTAIN PICK VIEWS
# --------------------------------------------------
class CybershokMapVetoView(View):
    def __init__(self, lobby_id: int, cap1: int, cap2: int, remaining_maps: list, current_turn: int, team1: list, team2: list):
        super().__init__(timeout=None)
        self.lobby_id = lobby_id
        self.cap1 = cap1
        self.cap2 = cap2
        self.maps = remaining_maps
        self.turn = current_turn
        self.team1 = team1
        self.team2 = team2

        for m in self.maps:
            btn = Button(label=m, style=discord.ButtonStyle.danger, custom_id=f"cb_ban_{m}_{lobby_id}")
            btn.callback = self.make_ban_callback(m)
            self.add_item(btn)

    def make_ban_callback(self, map_name: str):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.turn:
                return await interaction.response.send_message("❌ Не этот капитан должен выбирать!", ephemeral=True)

            self.maps.remove(map_name)
            next_turn = self.cap2 if self.turn == self.cap1 else self.cap1

            if len(self.maps) == 1:
                final_map = self.maps[0]
                t1_mentions = "\n".join([f"• <@{uid}>" for uid in self.team1])
                t2_mentions = "\n".join([f"• <@{uid}>" for uid in self.team2])

                embed = discord.Embed(
                    title=f"⚡ CYBERSHOK MATCH #{self.lobby_id} - READY TO PLAY",
                    description=(
                        f"🎮 **Карта:** `{final_map}`\n\n"
                        f"🔵 **Команда 1 (Капитан <@{self.cap1}>):**\n{t1_mentions}\n\n"
                        f"🔴 **Команда 2 (Капитан <@{self.cap2}>):**\n{t2_mentions}\n\n"
                        f"🚀 **Команда подключения (Connect IP):**\n"
                        f"```\n{SERVER_CONNECT_IP}\n```\n"
                        f"Удачи в игре!"
                    ),
                    color=discord.Color.green()
                )
                await interaction.response.edit_message(embed=embed, view=None)
            else:
                embed = discord.Embed(
                    title=f"🗺️ CYBERSHOK MAP VETO (Матч #{self.lobby_id})",
                    description=(
                        f"🚫 **<@{interaction.user.id}>** убрал карту (BAN): `{map_name}`\n\n"
                        f"Следующий бан делает капитан: <@{next_turn}>\n"
                        f"Оставшиеся карты: {', '.join([f'`{m}`' for m in self.maps])}"
                    ),
                    color=discord.Color.gold()
                )
                next_view = CybershokMapVetoView(self.lobby_id, self.cap1, self.cap2, self.maps, next_turn, self.team1, self.team2)
                await interaction.response.edit_message(embed=embed, view=next_view)

        return callback


class CybershokPlayerPickView(View):
    def __init__(self, lobby_id: int, cap1: int, cap2: int, available_players: list, team1: list, team2: list, current_turn: int):
        super().__init__(timeout=None)
        self.lobby_id = lobby_id
        self.cap1 = cap1
        self.cap2 = cap2
        self.available_players = available_players
        self.team1 = team1
        self.team2 = team2
        self.turn = current_turn

        for uid in self.available_players:
            btn = Button(label=f"Пик: {uid}", style=discord.ButtonStyle.primary, custom_id=f"cb_pick_{uid}_{lobby_id}")
            btn.callback = self.make_pick_callback(uid)
            self.add_item(btn)

    def make_pick_callback(self, picked_uid: int):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.turn:
                return await interaction.response.send_message("❌ Не ваша очередь выбирать!", ephemeral=True)

            self.available_players.remove(picked_uid)

            if self.turn == self.cap1:
                self.team1.append(picked_uid)
                next_turn = self.cap2
            else:
                self.team2.append(picked_uid)
                next_turn = self.cap1

            if len(self.available_players) == 1:
                last_p = self.available_players.pop(0)
                if next_turn == self.cap1:
                    self.team1.append(last_p)
                else:
                    self.team2.append(last_p)

                embed = discord.Embed(
                    title=f"🗺️ CYBERSHOK MAP VETO (Матч #{self.lobby_id})",
                    description=(
                        f"✅ Игроки выбраны!\n\n"
                        f"Первый бан делает капитан: <@{self.cap1}>\n"
                        f"Доступные карты: {', '.join([f'`{m}`' for m in CYBERSHOK_MAPS])}"
                    ),
                    color=discord.Color.gold()
                )
                veto_view = CybershokMapVetoView(self.lobby_id, self.cap1, self.cap2, CYBERSHOK_MAPS.copy(), self.cap1, self.team1, self.team2)
                await interaction.response.edit_message(embed=embed, view=veto_view)
            else:
                t1_str = "\n".join([f"• <@{uid}>" for uid in self.team1])
                t2_str = "\n".join([f"• <@{uid}>" for uid in self.team2])
                avail_str = "\n".join([f"• <@{uid}>" for uid in self.available_players])

                embed = discord.Embed(
                    title=f"👥 CYBERSHOK CAPTAIN PICK (Матч #{self.lobby_id})",
                    description=(
                        f"🔵 **Команда 1 (<@{self.cap1}>):**\n{t1_str}\n\n"
                        f"🔴 **Команда 2 (<@{self.cap2}>):**\n{t2_str}\n\n"
                        f"📋 **Оставшиеся игроки:**\n{avail_str}\n\n"
                        f"Очередь выбора капитана: <@{next_turn}>"
                    ),
                    color=discord.Color.blue()
                )
                next_view = CybershokPlayerPickView(self.lobby_id, self.cap1, self.cap2, self.available_players, self.team1, self.team2, next_turn)
                await interaction.response.edit_message(embed=embed, view=next_view)

        return callback


# --------------------------------------------------
# QUEUE LOBBY (5x5 CYBERSHOK SYSTEM)
# --------------------------------------------------
class QueueLobbyView(View):
    def __init__(self, lobby_id: int):
        super().__init__(timeout=None)
        self.lobby_id = lobby_id

    @discord.ui.button(label="Присоединиться", style=discord.ButtonStyle.success, custom_id="mix_queue_join")
    async def join_queue(self, interaction: discord.Interaction, button: Button):
        lobby = active_lobbies.get(self.lobby_id)
        if not lobby:
            return await interaction.response.send_message("❌ Лобби не найдено или было удалено.", ephemeral=True)

        user = interaction.user
        if user.id in lobby["players"]:
            return await interaction.response.send_message("❌ Вы уже зашли в это лобби!", ephemeral=True)

        if len(lobby["players"]) >= 10:
            return await interaction.response.send_message("❌ Лобби заполнено (10/10)!", ephemeral=True)

        lobby["players"].append(user.id)
        count = len(lobby["players"])

        players_list = "\n".join([f"{i+1}. <@{uid}>" for i, uid in enumerate(lobby["players"])])

        embed = discord.Embed(
            title=f"⚔️ CYBERSHOK 5x5 MATCH #{self.lobby_id} ({lobby['mode']})",
            description=(
                f"**Ожидание игроков ({count}/10)**\n\n"
                f"**Участники:**\n{players_list}"
            ),
            color=discord.Color.blue()
        )

        msg = lobby.get("message")
        if msg:
            await msg.edit(embed=embed, view=self)

        await interaction.response.send_message(f"✅ Вы присоединились к лобби! ({count}/10)", ephemeral=True)

        if count == 10:
            guild = interaction.guild
            category = discord.utils.get(guild.categories, name="⚔️ 5X5 MIX MATCHES")
            if not category:
                category = await guild.create_category(name="⚔️ 5X5 MIX MATCHES")

            text_ch = await guild.create_text_channel(name=f"⚔️│матч-{self.lobby_id}", category=category)
            team1_vc = await guild.create_voice_channel(name=f"🔊│Команда #1 [{self.lobby_id}]", category=category, user_limit=5)
            team2_vc = await guild.create_voice_channel(name=f"🔊│Команда #2 [{self.lobby_id}]", category=category, user_limit=5)

            all_players = lobby["players"].copy()
            random.shuffle(all_players)

            cap1 = all_players.pop(0)
            cap2 = all_players.pop(0)

            team1 = [cap1]
            team2 = [cap2]

            pings = " ".join([f"<@{uid}>" for uid in lobby["players"]])
            avail_str = "\n".join([f"• <@{uid}>" for uid in all_players])

            pick_embed = discord.Embed(
                title=f"👥 CYBERSHOK CAPTAIN PICK (Матч #{self.lobby_id})",
                description=(
                    f"👑 **Капитан 1:** <@{cap1}>\n"
                    f"👑 **Капитан 2:** <@{cap2}>\n\n"
                    f"📋 **Ожидают выбора:**\n{avail_str}\n\n"
                    f"**Капитан 1 (<@{cap1}>) выбирает первым!**"
                ),
                color=discord.Color.gold()
            )

            pick_view = CybershokPlayerPickView(self.lobby_id, cap1, cap2, all_players, team1, team2, current_turn=cap1)
            await text_ch.send(content=f"🔔 {pings}", embed=pick_embed, view=pick_view)

    @discord.ui.button(label="Покинуть", style=discord.ButtonStyle.danger, custom_id="mix_queue_leave")
    async def leave_queue(self, interaction: discord.Interaction, button: Button):
        lobby = active_lobbies.get(self.lobby_id)
        if not lobby or interaction.user.id not in lobby["players"]:
            return await interaction.response.send_message("❌ Вас нет в этом лобби.", ephemeral=True)

        lobby["players"].remove(interaction.user.id)
        count = len(lobby["players"])

        if count == 0:
            msg = lobby.get("message")
            if msg:
                await msg.delete()
            del active_lobbies[self.lobby_id]
            return await interaction.response.send_message("🚪 Лобби было удалено, так как из него все вышли.", ephemeral=True)

        players_list = "\n".join([f"{i+1}. <@{uid}>" for i, uid in enumerate(lobby["players"])])

        embed = discord.Embed(
            title=f"⚔️ CYBERSHOK 5x5 MATCH #{self.lobby_id} ({lobby['mode']})",
            description=(
                f"**Ожидание игроков ({count}/10)**\n\n"
                f"**Участники:**\n{players_list}"
            ),
            color=discord.Color.blue()
        )

        msg = lobby.get("message")
        if msg:
            await msg.edit(embed=embed, view=self)

        await interaction.response.send_message("🚪 Вы вышли из лобби.", ephemeral=True)


class MixLobbyView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(Button(label="alashproject.kz", emoji="🌐", url="https://alashproject.kz/", row=0))

    async def start_queue_lobby(self, interaction: discord.Interaction, mode: str):
        user = interaction.user
        lobby_id = len(active_lobbies) + 1

        embed = discord.Embed(
            title=f"⚔️ CYBERSHOK 5x5 MATCH #{lobby_id} ({mode})",
            description=(
                f"**Ожидание игроков (1/10)**\n\n"
                f"**Участники:**\n1. {user.mention}"
            ),
            color=discord.Color.blue()
        )

        view = QueueLobbyView(lobby_id)
        await interaction.response.send_message(embed=embed, view=view)
        msg = await interaction.original_response()

        active_lobbies[lobby_id] = {
            "owner": user.id,
            "mode": mode,
            "players": [user.id],
            "message": msg
        }

    @discord.ui.button(label="Создать 5x5 FreePick", style=discord.ButtonStyle.primary, custom_id="mix_freepick_open", row=1)
    async def freepick_btn(self, interaction: discord.Interaction, button: Button):
        await self.start_queue_lobby(interaction, "5x5 FreePick")

    @discord.ui.button(label="Закрытое 5x5 FreePick", style=discord.ButtonStyle.secondary, custom_id="mix_freepick_close", row=1)
    async def freepick_close_btn(self, interaction: discord.Interaction, button: Button):
        await self.start_queue_lobby(interaction, "Закрытое 5x5 FreePick")

    @discord.ui.button(label="Создать 5x5 Автобаланс", style=discord.ButtonStyle.primary, custom_id="mix_autobalance_open", row=2)
    async def autobalance_btn(self, interaction: discord.Interaction, button: Button):
        await self.start_queue_lobby(interaction, "5x5 Автобаланс")

    @discord.ui.button(label="Закрытое 5x5 Автобаланс", style=discord.ButtonStyle.secondary, custom_id="mix_autobalance_close", row=2)
    async def autobalance_close_btn(self, interaction: discord.Interaction, button: Button):
        await self.start_queue_lobby(interaction, "Закрытое 5x5 Автобаланс")

    @discord.ui.button(label="Получить роль", style=discord.ButtonStyle.success, custom_id="mix_get_role", row=3)
    async def get_role_btn(self, interaction: discord.Interaction, button: Button):
        guild = interaction.guild
        user = interaction.user
        
        role = discord.utils.get(guild.roles, name="5x5 MIX")
        if not role:
            try:
                role = await guild.create_role(name="5x5 MIX", color=discord.Color.purple(), reason="Авто-создание роли MIX")
            except Exception as e:
                return await interaction.response.send_message(f"❌ Ошибка создания роли: {e}", ephemeral=True)

        if role in user.roles:
            await user.remove_roles(role)
            await interaction.response.send_message("➖ С вас снята роль **5x5 MIX**.", ephemeral=True)
        else:
            await user.add_roles(role)
            await interaction.response.send_message("✅ Вам выдана роль **5x5 MIX**!", ephemeral=True)


# --------------------------------------------------
# PRIVATE VOICE CHANNELS & CONTROLS
# --------------------------------------------------
class RenameVoiceModal(Modal, title="Переименовать канал"):
    new_name = TextInput(label="Новое название канала", placeholder="Введите новое название...", required=True, max_length=100)
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.user.voice.channel.edit(name=self.new_name.value)
        await interaction.response.send_message(f"✅ Канал переименован в: **{self.new_name.value}**", ephemeral=True)


class UserActionView(View):
    def __init__(self, action: str):
        super().__init__(timeout=60)
        self.action = action

    @discord.ui.select(cls=UserSelect, placeholder="Выберите пользователя...")
    async def select_user(self, interaction: discord.Interaction, select: UserSelect):
        target_member = select.values[0]
        voice_channel = interaction.user.voice.channel
        if self.action == "add":
            await voice_channel.set_permissions(target_member, connect=True, view_channel=True)
            await interaction.response.send_message(f"✅ Пользователю {target_member.mention} доступ разрешен.", ephemeral=True)
        elif self.action == "block":
            await voice_channel.set_permissions(target_member, connect=False)
            if target_member in voice_channel.members:
                await target_member.move_to(None)
            await interaction.response.send_message(f"🚫 Пользователь {target_member.mention} заблокирован.", ephemeral=True)
        elif self.action == "transfer":
            temp_voice_channels[voice_channel.id] = target_member.id
            await interaction.response.send_message(f"👑 Права на канал переданы {target_member.mention}.", ephemeral=True)


class VoiceControlPanel(View):
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

    @discord.ui.button(emoji="🔓", style=discord.ButtonStyle.secondary, custom_id="vc_open", row=0)
    async def open_channel(self, interaction: discord.Interaction, button: Button):
        is_ok, result = self.check_owner(interaction)
        if not is_ok: return await interaction.response.send_message(result, ephemeral=True)
        await result.set_permissions(interaction.guild.default_role, connect=True)
        await interaction.response.send_message("🔓 Канал открыт для всех.", ephemeral=True)

    @discord.ui.button(emoji="👥", style=discord.ButtonStyle.secondary, custom_id="vc_add_user", row=0)
    async def add_user(self, interaction: discord.Interaction, button: Button):
        is_ok, _ = self.check_owner(interaction)
        if not is_ok: return await interaction.response.send_message(_, ephemeral=True)
        await interaction.response.send_message("Выберите пользователя:", view=UserActionView("add"), ephemeral=True)

    @discord.ui.button(emoji="✏️", style=discord.ButtonStyle.secondary, custom_id="vc_rename", row=0)
    async def rename_channel(self, interaction: discord.Interaction, button: Button):
        is_ok, _ = self.check_owner(interaction)
        if not is_ok: return await interaction.response.send_message(_, ephemeral=True)
        await interaction.response.send_modal(RenameVoiceModal())

    @discord.ui.button(emoji="👑", style=discord.ButtonStyle.secondary, custom_id="vc_transfer", row=1)
    async def transfer_owner(self, interaction: discord.Interaction, button: Button):
        is_ok, _ = self.check_owner(interaction)
        if not is_ok: return await interaction.response.send_message(_, ephemeral=True)
        await interaction.response.send_message("Выберите нового владельца:", view=UserActionView("transfer"), ephemeral=True)

    @discord.ui.button(emoji="🔒", style=discord.ButtonStyle.secondary, custom_id="vc_close", row=1)
    async def close_channel(self, interaction: discord.Interaction, button: Button):
        is_ok, result = self.check_owner(interaction)
        if not is_ok: return await interaction.response.send_message(result, ephemeral=True)
        await result.set_permissions(interaction.guild.default_role, connect=False)
        await interaction.response.send_message("🔒 Канал закрыт от посторонних.", ephemeral=True)

    @discord.ui.button(emoji="🚫", style=discord.ButtonStyle.secondary, custom_id="vc_kick_user", row=1)
    async def kick_user_btn(self, interaction: discord.Interaction, button: Button):
        is_ok, _ = self.check_owner(interaction)
        if not is_ok: return await interaction.response.send_message(_, ephemeral=True)
        await interaction.response.send_message("Выберите кого выгнать:", view=UserActionView("block"), ephemeral=True)


# --------------------------------------------------
# FACEIT VERIFICATION SYSTEM
# --------------------------------------------------
class FaceitVerifyView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(Button(label="Верифицироваться", emoji="✅", style=discord.ButtonStyle.success, url="https://alashproject.kz/"))

    @discord.ui.button(label="Мой профиль", emoji="👤", style=discord.ButtonStyle.primary, custom_id="faceit_profile_btn")
    async def profile_button(self, interaction: discord.Interaction, button: Button):
        user_id = interaction.user.id
        if user_id in verified_users:
            data = verified_users[user_id]
            await interaction.response.send_message(f"👤 Ваш профиль FACEIT:\n• Уровень: **{data['level']}**\n• Steam: **{data['steam']}**", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Вы еще не прошли FACEIT верификацию на сайте alashproject.kz!", ephemeral=True)

    @discord.ui.button(label="Обновить уровень", emoji="🔄", style=discord.ButtonStyle.secondary, custom_id="faceit_refresh_btn")
    async def refresh_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message("🔄 Уровень успешно обновлен с сайта alashproject.kz!", ephemeral=True)

    @discord.ui.button(label="Сбросить профиль", emoji="🛑", style=discord.ButtonStyle.danger, custom_id="faceit_reset_btn")
    async def reset_button(self, interaction: discord.Interaction, button: Button):
        user_id = interaction.user.id
        if user_id in verified_users:
            del verified_users[user_id]
            await interaction.response.send_message("🛑 Профиль сброшен.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Профиль не найден.", ephemeral=True)


# --------------------------------------------------
# TICKET SYSTEM & MODALS
# --------------------------------------------------
class TicketControlView(View):
    def __init__(self, ticket_type: str = "general"):
        super().__init__(timeout=None)
        self.ticket_type = ticket_type

    @discord.ui.button(label="Взяться", style=discord.ButtonStyle.success, custom_id="ticket_take_btn_alash")
    async def take_button(self, interaction: discord.Interaction, button: Button):
        if not has_staff_permission(interaction.user, interaction.channel.name):
            return await interaction.response.send_message("❌ У вас нет прав!", ephemeral=True)
        await interaction.response.defer()
        await interaction.followup.send(f"**{interaction.user.mention}** взял(а)ся за тикет!")

    @discord.ui.button(label="Взять на рассмотрение", style=discord.ButtonStyle.primary, custom_id="ticket_review_btn_alash")
    async def review_button(self, interaction: discord.Interaction, button: Button):
        if not has_staff_permission(interaction.user, interaction.channel.name):
            return await interaction.response.send_message("❌ У вас нет прав!", ephemeral=True)
        await interaction.response.defer()
        await interaction.followup.send(f"**{interaction.user.mention}** взял тикет на рассмотрение.")

    @discord.ui.button(label="Закрыть тикет", style=discord.ButtonStyle.danger, custom_id="ticket_close_btn_alash")
    async def close_button(self, interaction: discord.Interaction, button: Button):
        if not has_staff_permission(interaction.user, interaction.channel.name):
            return await interaction.response.send_message("❌ У вас нет прав!", ephemeral=True)
        await interaction.response.send_message("***Тикет закрывается...***", ephemeral=False)
        await asyncio.sleep(3)
        await interaction.channel.delete(reason="Тикет закрыт")


class GirlTicketMainView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Получить роль девушка", emoji="🌸", style=discord.ButtonStyle.secondary, custom_id="open_girl_ticket_btn_alash")
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
            if guild.get_role(r_id): overwrites[guild.get_role(r_id)] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

        t_channel = await guild.create_text_channel(name=ch_name, category=interaction.channel.category, overwrites=overwrites)
        embed = discord.Embed(description="**🌸 Заявка на роль Девушки**\nОжидайте ответа модераторов.", color=discord.Color.from_rgb(255, 105, 180))
        embed.add_field(name="• Пользователь", value=user.mention)
        await t_channel.send(content=f"{user.mention} " + " ".join(pings), embed=embed, view=TicketControlView("girl"))
        await interaction.followup.send(f"Ваш тикет создан: {t_channel.mention}", ephemeral=True)


class TicketSelectView(View):
    def __init__(self):
        super().__init__(timeout=60)

    @discord.ui.select(placeholder="Выберите категорию...", options=[
        discord.SelectOption(label="Жалоба на игроков", value="Жалоба на игроков"),
        discord.SelectOption(label="Вопросы по серверу", value="Вопросы по серверу"),
        discord.SelectOption(label="Проблемы с верификацией", value="Проблемы с верификацией"),
        discord.SelectOption(label="Технические неполадки", value="Баги и неполадки")
    ])
    async def select_callback(self, interaction: discord.Interaction, select: discord.ui.Select):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        user = interaction.user
        cat_sel = select.values[0]
        ch_name = f"заявление-{user.name}"
        if discord.utils.get(guild.text_channels, name=ch_name):
            return await interaction.followup.send("У вас уже открыт тикет!", ephemeral=True)

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False), 
            user: discord.PermissionOverwrite(read_messages=True, send_messages=True), 
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        pings = [guild.get_role(r).mention for r in STAFF_ROLE_IDS if guild.get_role(r)]
        for r_id in STAFF_ROLE_IDS:
            if guild.get_role(r_id): overwrites[guild.get_role(r_id)] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

        t_channel = await guild.create_text_channel(name=ch_name, category=interaction.channel.category, overwrites=overwrites)
        embed = discord.Embed(description="**Система поддержки ALASH PROJECT KZ**\nОпишите вашу ситуацию.", color=discord.Color.from_rgb(57, 255, 20))
        embed.add_field(name="• Пользователь", value=user.mention)
        embed.add_field(name="• Категория", value=cat_sel)
        await t_channel.send(content=f"{user.mention} " + " ".join(pings), embed=embed, view=TicketControlView("general"))
        await interaction.followup.send(f"Тикет создан: {t_channel.mention}", ephemeral=True)


class TicketMainView(View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="Открыть тикет", style=discord.ButtonStyle.secondary, custom_id="open_ticket_main_btn_alash")
    async def open_ticket(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message("Выберите категорию:", view=TicketSelectView(), ephemeral=True)


class MediaApplicationModal(Modal, title="Подать заявку на Медиа"):
    game_nick = TextInput(label="Ваш ник в игре", required=True, max_length=50)
    tiktok_link = TextInput(label="Ссылка на TikTok / Канал", required=True, max_length=150)
    steam_id = TextInput(label="Ваш steam ID", style=discord.TextStyle.paragraph, required=True, max_length=100)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        user = interaction.user
        ch_name = f"медиа-{user.name}"
        if discord.utils.get(guild.text_channels, name=ch_name):
            return await interaction.followup.send("У вас уже есть медиа тикет!", ephemeral=True)

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False), 
            user: discord.PermissionOverwrite(read_messages=True, send_messages=True), 
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        pings = [guild.get_role(r).mention for r in MEDIA_STAFF_ROLE_IDS if guild.get_role(r)]
        for r_id in MEDIA_STAFF_ROLE_IDS:
            if guild.get_role(r_id): overwrites[guild.get_role(r_id)] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

        t_channel = await guild.create_text_channel(name=ch_name, category=interaction.channel.category, overwrites=overwrites)
        embed = discord.Embed(title="🎬 Заявка на Медиа", color=discord.Color.red())
        embed.add_field(name="• Пользователь", value=user.mention)
        embed.add_field(name="• Ник", value=self.game_nick.value)
        embed.add_field(name="• Канал", value=self.tiktok_link.value)
        embed.add_field(name="• Steam ID", value=self.steam_id.value)
        embed.set_thumbnail(url=user.display_avatar.url)
        await t_channel.send(content=f"{user.mention} " + " ".join(pings), embed=embed, view=TicketControlView("media"))
        await interaction.followup.send(f"Медиа тикет создан: {t_channel.mention}", ephemeral=True)


class MediaMainView(View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="Подать заявку", style=discord.ButtonStyle.secondary, custom_id="open_media_modal_btn_alash")
    async def apply_media_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(MediaApplicationModal())


# --------------------------------------------------
# CLAN SYSTEM (PRIVATE DM INVITES WITH GUILD_ID FIXED)
# --------------------------------------------------
class ClanInviteAcceptView(View):
    def __init__(self, clan_owner_id: int, target_user_id: int, guild_id: int):
        super().__init__(timeout=120)
        self.clan_owner_id = clan_owner_id
        self.target_user_id = target_user_id
        self.guild_id = guild_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.target_user_id:
            await interaction.response.send_message("❌ Это приглашение предназначено не для вас!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Принять", style=discord.ButtonStyle.success, emoji="✅")
    async def accept_invite(self, interaction: discord.Interaction, button: Button):
        clan = clans_db.get(self.clan_owner_id)
        if not clan:
            return await interaction.response.send_message("❌ Клан не найден или был удален.", ephemeral=True)

        if len(clan["members"]) >= 10:
            return await interaction.response.send_message("❌ В клане уже максимальное количество участников (10/10)!", ephemeral=True)

        if interaction.user.id in user_clan_mapping:
            return await interaction.response.send_message("❌ Вы уже состоите в клане!", ephemeral=True)

        clan["members"].append(interaction.user.id)
        user_clan_mapping[interaction.user.id] = self.clan_owner_id

        guild = interaction.client.get_guild(self.guild_id)
        member = guild.get_member(interaction.user.id) if guild else None

        if guild and member:
            clan_role = guild.get_role(clan["role_id"])
            if clan_role:
                try: 
                    await member.add_roles(clan_role, reason="Вступление в клан")
                except Exception as e:
                    print(f"Ошибка выдачи роли: {e}")

            category = guild.get_channel(clan["category"])
            text_ch = guild.get_channel(clan["text_ch"])
            voice_ch = guild.get_channel(clan["voice_ch"])

            if category: await category.set_permissions(member, read_messages=True, connect=True, view_channel=True)
            if text_ch: await text_ch.set_permissions(member, read_messages=True, send_messages=True)
            if voice_ch: await voice_ch.set_permissions(member, connect=True, speak=True)

            try:
                new_nick = f"[{clan['tag']}] {member.display_name}"
                if len(new_nick) <= 32:
                    await member.edit(nick=new_nick)
            except Exception as e:
                print(f"Ошибка изменения ника: {e}")

            await send_custom_log(
                guild=guild,
                channel_id=CLAN_LOG_CHANNEL_ID,
                emoji="👥",
                title="Игрок вступил в клан",
                description_lines=[
                    f"**Участник:** {member.name} ({member.mention})",
                    f"**Клан:** {clan['name']} (`[{clan['tag']}]`)"
                ],
                color=discord.Color.green()
            )

        await interaction.response.edit_message(content=f"🎉 **{interaction.user.mention}**, вы успешно вступили в клан **{clan['name']}**!", view=None)

    @discord.ui.button(label="Отклонить", style=discord.ButtonStyle.danger, emoji="✖️")
    async def decline_invite(self, interaction: discord.Interaction, button: Button):
        await interaction.response.edit_message(content=f"❌ Вы отклонили приглашение в клан.", view=None)


class InviteUserSelect(View):
    def __init__(self, clan_owner_id):
        super().__init__(timeout=60)
        self.clan_owner_id = clan_owner_id

    @discord.ui.select(cls=UserSelect, placeholder="Выберите игрока для приглашения...")
    async def select_user(self, interaction: discord.Interaction, select: UserSelect):
        target_member = select.values[0]
        clan = clans_db.get(self.clan_owner_id)

        if not clan:
            return await interaction.response.send_message("❌ Ваш клан не найден.", ephemeral=True)

        if len(clan["members"]) >= 10:
            return await interaction.response.send_message("❌ В клане максимальное количество участников (10/10).", ephemeral=True)

        if target_member.id in clan["members"]:
            return await interaction.response.send_message("❌ Этот игрок уже состоит в вашем клане!", ephemeral=True)

        if target_member.id in user_clan_mapping:
            return await interaction.response.send_message("❌ Этот игрок уже состоит в другом клане!", ephemeral=True)

        invite_view = ClanInviteAcceptView(self.clan_owner_id, target_member.id, interaction.guild.id)
        try:
            await target_member.send(
                content=(
                    f"✉️ **Приглашение в клан!**\n\n"
                    f"Игрок **{interaction.user.name}** приглашает вас в клан **{clan['name']}** (`[{clan['tag']}]`) на сервере **{interaction.guild.name}**!\n"
                    f"Нажмите кнопку ниже, чтобы принять решение:"
                ),
                view=invite_view
            )
            await interaction.response.send_message(f"✅ Приглашение отправлено пользователю {target_member.mention} в личные сообщения!", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message(
                f"⚠️ Не удалось отправить сообщение {target_member.mention}. У пользователя закрыты личные сообщения!", 
                ephemeral=True
            )


class KickUserSelect(View):
    def __init__(self, clan_owner_id):
        super().__init__(timeout=60)
        self.clan_owner_id = clan_owner_id

    @discord.ui.select(cls=UserSelect, placeholder="Выберите игрока для исключения...")
    async def select_user(self, interaction: discord.Interaction, select: UserSelect):
        target_member = select.values[0]
        clan = clans_db.get(self.clan_owner_id)
        guild = interaction.guild

        if not clan:
            return await interaction.response.send_message("❌ Ваш клан не найден.", ephemeral=True)

        if target_member.id == self.clan_owner_id:
            return await interaction.response.send_message("❌ Вы не можете исключить самого себя как лидера!", ephemeral=True)

        if target_member.id not in clan["members"]:
            return await interaction.response.send_message("❌ Этот игрок не состоит в вашем клане.", ephemeral=True)

        clan["members"].remove(target_member.id)
        user_clan_mapping.pop(target_member.id, None)

        clan_role = guild.get_role(clan["role_id"])
        if clan_role:
            try: await target_member.remove_roles(clan_role)
            except: pass

        category = guild.get_channel(clan["category"])
        text_ch = guild.get_channel(clan["text_ch"])
        voice_ch = guild.get_channel(clan["voice_ch"])

        if category: await category.set_permissions(target_member, overwrite=None)
        if text_ch: await text_ch.set_permissions(target_member, overwrite=None)
        if voice_ch: await voice_ch.set_permissions(target_member, overwrite=None)

        tag = clan["tag"]
        try:
            current_nick = target_member.display_name
            if current_nick.startswith(f"[{tag}] "):
                clean_nick = current_nick[len(tag) + 3:]
                await target_member.edit(nick=clean_nick)
        except: pass

        await send_custom_log(
            guild=guild,
            channel_id=CLAN_LOG_CHANNEL_ID,
            emoji="👢",
            title="Исключение игрока из клана",
            description_lines=[
                f"**Участник:** {target_member.name} ({target_member.mention})",
                f"**Клан:** {clan['name']} (`[{tag}]`)",
                f"**Исключил лидер:** {interaction.user.name} ({interaction.user.mention})"
            ],
            color=discord.Color.orange()
        )

        await interaction.response.send_message(f"✅ Игрок {target_member.mention} успешно исключен из клана.", ephemeral=True)


class ClanManagementView(View):
    def __init__(self, clan_owner_id):
        super().__init__(timeout=None)
        self.clan_owner_id = clan_owner_id

    @discord.ui.button(label="Пригласить игрока", style=discord.ButtonStyle.success, custom_id="clan_invite_btn", row=0)
    async def invite_btn(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.clan_owner_id:
            return await interaction.response.send_message("❌ Только лидер клана может приглашать участников!", ephemeral=True)
        await interaction.response.send_message("Выберите игрока для добавления в клан:", view=InviteUserSelect(self.clan_owner_id), ephemeral=True)

    @discord.ui.button(label="Исключить игрока", style=discord.ButtonStyle.secondary, custom_id="clan_kick_btn", row=0)
    async def kick_btn(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.clan_owner_id:
            return await interaction.response.send_message("❌ Только лидер клана может исключать участников!", ephemeral=True)
        await interaction.response.send_message("Выберите игрока для исключения из клана:", view=KickUserSelect(self.clan_owner_id), ephemeral=True)

    @discord.ui.button(label="Распустить клан (Disband)", style=discord.ButtonStyle.danger, custom_id="clan_disband_btn", row=1)
    async def disband_btn(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.clan_owner_id:
            return await interaction.response.send_message("❌ Только лидер клана может распустить его!", ephemeral=True)

        clan = clans_db.get(self.clan_owner_id)
        if not clan:
            return await interaction.response.send_message("❌ Клан не найден.", ephemeral=True)

        guild = interaction.guild
        tag = clan["tag"]
        c_name = clan["name"]

        for uid in clan["members"]:
            member = guild.get_member(uid)
            if member:
                user_clan_mapping.pop(uid, None)
                try:
                    current_nick = member.display_name
                    if current_nick.startswith(f"[{tag}] "):
                        clean_nick = current_nick[len(tag) + 3:]
                        await member.edit(nick=clean_nick)
                except: pass

        clan_role = guild.get_role(clan["role_id"])
        if clan_role:
            try: await clan_role.delete()
            except: pass

        text_ch = guild.get_channel(clan["text_ch"])
        voice_ch = guild.get_channel(clan["voice_ch"])
        category = guild.get_channel(clan["category"])

        if text_ch: await text_ch.delete()
        if voice_ch: await voice_ch.delete()
        if category: await category.delete()

        del clans_db[self.clan_owner_id]

        await send_custom_log(
            guild=guild,
            channel_id=CLAN_LOG_CHANNEL_ID,
            emoji="🛑",
            title="Расформирование клана",
            description_lines=[
                f"**Клан:** {c_name} (`[{tag}]`)",
                f"**Распустил:** {interaction.user.name} ({interaction.user.mention})"
            ],
            color=discord.Color.red()
        )

        await interaction.response.send_message("🛑 Клан успешно распущен, роль, категория и каналы удалены.", ephemeral=True)


class ClanMemberView(View):
    def __init__(self, clan_owner_id):
        super().__init__(timeout=None)
        self.clan_owner_id = clan_owner_id

    @discord.ui.button(label="Покинуть клан", style=discord.ButtonStyle.danger, custom_id="clan_leave_btn", emoji="🚪")
    async def leave_clan_btn(self, interaction: discord.Interaction, button: Button):
        user_id = interaction.user.id
        if user_id == self.clan_owner_id:
            return await interaction.response.send_message("❌ Лидер клана не может покинуть клан! Чтобы распустить его, нажмите 'Распустить клан'.", ephemeral=True)

        clan = clans_db.get(self.clan_owner_id)
        if not clan or user_id not in clan["members"]:
            return await interaction.response.send_message("❌ Вы не состоите в этом клане.", ephemeral=True)

        clan["members"].remove(user_id)
        user_clan_mapping.pop(user_id, None)

        guild = interaction.guild
        clan_role = guild.get_role(clan["role_id"])
        if clan_role:
            try: await interaction.user.remove_roles(clan_role)
            except: pass

        category = guild.get_channel(clan["category"])
        text_ch = guild.get_channel(clan["text_ch"])
        voice_ch = guild.get_channel(clan["voice_ch"])

        if category: await category.set_permissions(interaction.user, overwrite=None)
        if text_ch: await text_ch.set_permissions(interaction.user, overwrite=None)
        if voice_ch: await voice_ch.set_permissions(interaction.user, overwrite=None)

        tag = clan["tag"]
        try:
            current_nick = interaction.user.display_name
            if current_nick.startswith(f"[{tag}] "):
                clean_nick = current_nick[len(tag) + 3:]
                await interaction.user.edit(nick=clean_nick)
        except: pass

        await send_custom_log(
            guild=guild,
            channel_id=CLAN_LOG_CHANNEL_ID,
            emoji="🚪",
            title="Игрок покинул клан",
            description_lines=[
                f"**Участник:** {interaction.user.name} ({interaction.user.mention})",
                f"**Клан:** {clan['name']} (`[{tag}]`)"
            ],
            color=discord.Color.orange()
        )

        await interaction.response.send_message(f"🚪 Вы успешно покинули клан **{clan['name']}**.", ephemeral=True)


class CreateClanModal(Modal, title="Создание клана"):
    clan_name = TextInput(label="Название клана", placeholder="Введите название...", required=True, max_length=50)
    clan_tag = TextInput(label="Тег клана", placeholder="Введите тег...", required=True, max_length=10)

    async def on_submit(self, interaction: discord.Interaction):
        user = interaction.user
        user_id = user.id
        guild = interaction.guild
        
        if user_id in user_clan_mapping:
            return await interaction.response.send_message("❌ У вас уже есть клан! Сначала распустите текущий клан.", ephemeral=True)

        name = self.clan_name.value
        tag = self.clan_tag.value.upper()

        try:
            clan_role = await guild.create_role(name=f"{name} Clan", color=discord.Color.random(), reason=f"Клан создан: {name}")
            await user.add_roles(clan_role)
        except Exception as e:
            return await interaction.response.send_message(f"❌ Ошибка при создании роли: {e}", ephemeral=True)

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False, connect=False, view_channel=False),
            user: discord.PermissionOverwrite(read_messages=True, send_messages=True, connect=True, speak=True, view_channel=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, connect=True, view_channel=True, manage_channels=True)
        }

        try:
            category = await guild.create_category(name=f"🛡️ Клан [{tag}]", overwrites=overwrites)
            text_channel = await guild.create_text_channel(name=f"💬│чат-{tag.lower()}", category=category)
            voice_channel = await guild.create_voice_channel(name=f"🔊│войс-{tag}", category=category)
        except Exception as e:
            return await interaction.response.send_message(f"❌ Ошибка при создании каналов: {e}", ephemeral=True)

        clans_db[user_id] = {
            "name": name,
            "tag": tag,
            "owner": user_id,
            "members": [user_id],
            "score": 1000,
            "role_id": clan_role.id,
            "category": category.id,
            "text_ch": text_channel.id,
            "voice_ch": voice_channel.id
        }
        user_clan_mapping[user_id] = user_id

        try:
            new_nick = f"[{tag}] {user.display_name}"
            if len(new_nick) <= 32: await user.edit(nick=new_nick)
        except: pass

        await send_custom_log(
            guild=guild,
            channel_id=CLAN_LOG_CHANNEL_ID,
            emoji="⚔️",
            title="Создание клана",
            description_lines=[
                f"**Клан:** {name} (`[{tag}]`)",
                f"**Основатель:** {user.name} ({user.mention})",
                f"**Роль:** {clan_role.name}"
            ],
            color=discord.Color.blue()
        )

        await interaction.response.send_message(
            f"✅ Клан **{name}** с тегом **[{tag}]** успешно создан!\n"
            f"• Авто-роль: {clan_role.mention}\n"
            f"• Категория: **🛡️ Клан [{tag}]**\n"
            f"• Чат: {text_channel.mention}\n"
            f"• Войс: {voice_channel.mention}",
            ephemeral=True
        )


class ClanPanelView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(Button(label="alashproject.kz", emoji="🌐", url="https://alashproject.kz/", row=0))

    @discord.ui.button(label="Создать клан", style=discord.ButtonStyle.primary, custom_id="create_clan_btn_alash", row=1)
    async def create_clan(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(CreateClanModal())

    @discord.ui.button(label="Рейтинг кланов", style=discord.ButtonStyle.secondary, custom_id="clan_rating_btn_alash", row=1)
    async def clan_rating(self, interaction: discord.Interaction, button: Button):
        if not clans_db:
            return await interaction.response.send_message("🏆 Рейтинг кланов пуст.", ephemeral=True)
        
        sorted_clans = sorted(clans_db.values(), key=lambda x: x["score"], reverse=True)
        desc = ""
        for i, c in enumerate(sorted_clans[:10], 1):
            desc += f"**{i}.** [{c['tag']}] {c['name']} — **{c['score']} очков** (Участников: {len(c['members'])})\n"
        
        embed = discord.Embed(title="🏆 Рейтинг кланов", description=desc, color=discord.Color.gold())
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Мой клан", style=discord.ButtonStyle.secondary, custom_id="my_clan_btn_alash", row=1)
    async def my_clan(self, interaction: discord.Interaction, button: Button):
        user_id = interaction.user.id
        clan_owner_id = user_clan_mapping.get(user_id)

        if not clan_owner_id or clan_owner_id not in clans_db:
            return await interaction.response.send_message("🛡️ У вас пока нет клана.", ephemeral=True)

        clan = clans_db[clan_owner_id]
        members_list = ", ".join([f"<@{uid}>" for uid in clan['members']])
        guild = interaction.guild
        clan_role = guild.get_role(clan["role_id"])
        text_ch = guild.get_channel(clan["text_ch"])
        voice_ch = guild.get_channel(clan["voice_ch"])

        embed = discord.Embed(
            title=f"🛡️ Клан: {clan['name']} [{clan['tag']}]",
            description=(
                f"• **Лидер:** <@{clan['owner']}>\n"
                f"• **Роль:** {clan_role.mention if clan_role else 'Удалена'}\n"
                f"• **Очки:** {clan['score']}\n"
                f"• **Чат:** {text_ch.mention if text_ch else 'Удален'}\n"
                f"• **Войс:** {voice_ch.mention if voice_ch else 'Удален'}\n\n"
                f"• **Участники ({len(clan['members'])}/10):**\n{members_list}"
            ),
            color=discord.Color.blue()
        )
        
        if user_id == clan['owner']:
            view = ClanManagementView(clan_owner_id)
        else:
            view = ClanMemberView(clan_owner_id)

        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


# --------------------------------------------------
# BOT INIT & PRESENCE STATUS
# --------------------------------------------------
class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        self.add_view(TicketMainView())
        self.add_view(GirlTicketMainView())
        self.add_view(TicketControlView())
        self.add_view(MediaMainView())
        self.add_view(VoiceControlPanel())
        self.add_view(FaceitVerifyView())
        self.add_view(ClanPanelView())
        self.add_view(MixLobbyView())

    async def on_ready(self):
        activity = discord.Activity(
            type=discord.ActivityType.watching, 
            name="alashproject.kz | /help"
        )
        await self.change_presence(activity=activity)
        print("==========================================")
        print(f" БОТ УСПЕШНО ЗАПУЩЕН И ОНЛАЙН: {self.user} ")
        print("==========================================")

bot = MyBot()


# --------------------------------------------------
# SERVER EVENTS & AUDIT LOGGING
# --------------------------------------------------
@bot.event
async def on_member_join(member):
    role = member.guild.get_role(AUTO_ROLE_ID)
    if role:
        try: await member.add_roles(role, reason="Авто-роль")
        except: pass
    w_channel = member.guild.get_channel(WELCOME_CHANNEL_ID)
    if w_channel:
        embed = discord.Embed(description=f"Добро пожаловать на сервер, {member.mention}!", color=discord.Color.from_rgb(255, 50, 50))
        embed.set_image(url=member.display_avatar.url)
        await w_channel.send(content=f"Приветствую тебя в нашем дискорд канале, {member.mention}!", embed=embed)


@bot.event
async def on_message(message):
    if message.author.bot: return
    uid = message.author.id
    if uid not in user_levels: user_levels[uid] = {"exp": 0, "level": 1}
    
    user_levels[uid]["exp"] += 7
    
    if user_levels[uid]["exp"] >= user_levels[uid]["level"] * 100:
        user_levels[uid]["level"] += 1
        l_ch = message.guild.get_channel(LEVEL_CHANNEL_ID)
        if l_ch: await l_ch.send(f"Поздравляем {message.author.mention}! Ты достиг {user_levels[uid]['level']} уровня!")
    await bot.process_commands(message)


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
            f"**Содержание сообщения:**\n`{message.content or 'Медиа / Вложение'}`"
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

    await send_custom_log(
        guild=guild,
        channel_id=SERVER_LOG_CHANNEL_ID,
        emoji="🔨",
        title="Бан участника",
        description_lines=[
            f"**Участник:** {user.name} ({user.mention})",
            f"**Забанил:** {moderator.name if moderator else 'Неизвестно'}",
            f"**Причина:** `{reason}`"
        ],
        color=discord.Color.dark_red()
    )


@bot.event
async def on_member_unban(guild, user):
    async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.unban):
        moderator = entry.user
        break
    else:
        moderator = None

    await send_custom_log(
        guild=guild,
        channel_id=SERVER_LOG_CHANNEL_ID,
        emoji="🔓",
        title="Разбан участника",
        description_lines=[
            f"**Участник:** {user.name} ({user.mention})",
            f"**Разбанил:** {moderator.name if moderator else 'Неизвестно'}"
        ],
        color=discord.Color.green()
    )


@bot.event
async def on_member_update(before, after):
    if before.timed_out_until != after.timed_out_until:
        guild = after.guild
        if after.timed_out_until is not None:
            async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.member_update):
                if entry.target.id == after.id:
                    moderator = entry.user
                    break
            else:
                moderator = None

            await send_custom_log(
                guild=guild,
                channel_id=SERVER_LOG_CHANNEL_ID,
                emoji="🔇",
                title="Выдан мут (Timeout)",
                description_lines=[
                    f"**Участник:** {after.name} ({after.mention})",
                    f"**Модератор:** {moderator.name if moderator else 'Неизвестно'}",
                    f"**До:** {after.timed_out_until}"
                ],
                color=discord.Color.orange()
            )
        else:
            await send_custom_log(
                guild=guild,
                channel_id=SERVER_LOG_CHANNEL_ID,
                emoji="🔊",
                title="Снят мут",
                description_lines=[
                    f"**Участник:** {after.name} ({after.mention})"
                ],
                color=discord.Color.blue()
            )


@bot.event
async def on_voice_state_update(member, before, after):
    # 1. Авто-создание приватных комнат (динамический войс)
    if after.channel and "создать войс" in after.channel.name.lower():
        v_ch = await member.guild.create_voice_channel(name=f"Комната {member.name}", category=after.channel.category)
        await v_ch.set_permissions(member, connect=True, speak=True, manage_channels=True)
        temp_voice_channels[v_ch.id] = member.id
        await member.move_to(v_ch)

    # 2. Авто-удаление пустых приватных комнат
    if before.channel and before.channel.id in temp_voice_channels:
        if len(before.channel.members) == 0:
            del temp_voice_channels[before.channel.id]
            await before.channel.delete()

    # --------------------------------------------------
    # ГОЛОСОВОЙ КАНАЛ АУДИТ ЛОГИ (ПОДРОБНЫЙ МОНИТОРИНГ)
    # --------------------------------------------------
    guild = member.guild

    # Подключение к голосовому каналу (Connect)
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

    # Отключение от голосового канала (Disconnect)
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

    # Перемещение между каналами (Move)
    elif before.channel != after.channel and before.channel is not None and after.channel is not None:
        moderator = None
        try:
            async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.member_move):
                if entry.target.id == member.id:
                    moderator = entry.user
                    break
        except Exception:
            pass

        mod_info = f"\n**Переместил модератор:** {moderator.mention}" if moderator else ""

        await send_custom_log(
            guild=guild,
            channel_id=SERVER_LOG_CHANNEL_ID,
            emoji="↔️",
            title="Перемещение в голосовом канале",
            description_lines=[
                f"**Участник:** {member.name} ({member.mention})",
                f"**Из канала:** {before.channel.mention}",
                f"**В канал:** {after.channel.mention}" + mod_info
            ],
            color=discord.Color.blue()
        )

    # Заглушение микрофона сервера (Server Mute / Unmute)
    if before.mute != after.mute:
        action = "Заглушен микрофон (Server Mute)" if after.mute else "Снята заглушка (Server Unmute)"
        emoji = "🔇" if after.mute else "🔊"
        
        moderator = None
        try:
            async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.member_update):
                if entry.target.id == member.id:
                    moderator = entry.user
                    break
        except Exception:
            pass

        mod_info = f"\n**Модератор:** {moderator.mention}" if moderator else ""

        await send_custom_log(
            guild=guild,
            channel_id=SERVER_LOG_CHANNEL_ID,
            emoji=emoji,
            title=f"Голосовой чат: {action}",
            description_lines=[
                f"**Участник:** {member.name} ({member.mention})",
                f"**Канал:** {after.channel.mention if after.channel else 'Вне канала'}" + mod_info
            ],
            color=discord.Color.orange() if after.mute else discord.Color.green()
        )

    # Отключение звука сервера (Server Deafen / Undeafen)
    if before.deaf != after.deaf:
        action = "Отключен звук (Server Deafen)" if after.deaf else "Включен звук (Server Undeafen)"
        emoji = "🎧" if after.deaf else "🔊"

        moderator = None
        try:
            async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.member_update):
                if entry.target.id == member.id:
                    moderator = entry.user
                    break
        except Exception:
            pass

        mod_info = f"\n**Модератор:** {moderator.mention}" if moderator else ""

        await send_custom_log(
            guild=guild,
            channel_id=SERVER_LOG_CHANNEL_ID,
            emoji=emoji,
            title=f"Голосовой чат: {action}",
            description_lines=[
                f"**Участник:** {member.name} ({member.mention})",
                f"**Канал:** {after.channel.mention if after.channel else 'Вне канала'}" + mod_info
            ],
            color=discord.Color.dark_orange() if after.deaf else discord.Color.green()
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
# OTHER BOT COMMANDS (!clear & PANEL SETUP)
# --------------------------------------------------
@bot.command(name="clear", aliases=["purge", "clean"])
@commands.has_permissions(manage_messages=True)
async def clear_messages(ctx, amount: int = 10):
    """Удаление сообщений (например, !clear 10)"""
    deleted = await ctx.channel.purge(limit=amount + 1)
    confirm_msg = await ctx.send(f"🧹 Успешно удалено **{len(deleted) - 1}** сообщений!")
    await asyncio.sleep(3)
    await confirm_msg.delete()

@clear_messages.error
async def clear_messages_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ У вас нет прав для удаления сообщений (`Manage Messages`).", delete_after=5)
    elif isinstance(error, commands.BadArgument):
        await ctx.send("❌ Укажите число сообщений. Пример: `!clear 10`", delete_after=5)


@bot.command()
async def send_mix(ctx):
    embed = discord.Embed(
        title="<a:15770animatedarrowyellow:1503049767016595586> Создание лобби",
        description=(
            "Выберите режим матча\n\n"
            "<a:15770animatedarrowyellow:1503049767016595586> **5x5 FreePick**\n"
            "Команды выбирают капитаны. Рейтинг ELO не начисляется\n\n"
            "<a:15770animatedarrowyellow:1503049767016595586> **5x5 Автобаланс**\n"
            "Команды балансируются по Faceit LVL / ELO. Рейтинг ELO начисляется\n\n"
            "<a:15770animatedarrowyellow:1503049767016595586> **Требования**\n"
            "• Привязка Discord обязательна: https://alashproject.kz/\n"
            "• Доступен CS2 SkinChanger и Паблик сервер\n"
            "• Свободный сервер должен быть доступен"
        ),
        color=discord.Color.from_rgb(180, 0, 0)
    )
    await ctx.send(embed=embed, view=MixLobbyView())


@bot.command()
async def send_verification(ctx):
    embed = discord.Embed(
        title="<a:15770animatedarrowyellow:1503049767016595586> FACEIT Верификация",
        description=(
            "Нажмите кнопку ниже, чтобы пройти верификацию.\n\n"
            "<a:a_pink_dot:1503133833548271646> Проверка Discord\n"
            "<a:a_pink_dot:1503133833548271646> Проверка профиля FACEIT\n"
            "<a:a_pink_dot:1503133833548271646> Проверка привязанного Steam для CS2\n"
            "<a:a_pink_dot:1503133833548271646> Определение FACEIT Level 1–10\n"
            "<a:a_pink_dot:1503133833548271646> Защита от повторной привязки аккаунта\n\n"
            "После успешной проверки бот автоматически выдаст роль верификации и роль вашего FACEIT Level.\n"
            "**ALASH PROJECT KZ**"
        ),
        color=discord.Color.blue()
    )
    await ctx.send(embed=embed, view=FaceitVerifyView())


@bot.command()
async def send_voice_panel(ctx):
    embed = discord.Embed(
        description=(
            "# **Управление приватной комнатой**\n\n"
            "🔓 • Открыть канал\n"
            "👥 • Добавить пользователя\n"
            "✏️ • Переименовать канал\n\n"
            "👑 • Передать канал\n"
            "🔒 • Закрыть канал\n"
            "🚫 • Выгнать пользователя\n\n"
            "*Кнопки активны в вашем войсе.*"
        ), 
        color=discord.Color.dark_grey()
    )
    await ctx.send(embed=embed, view=VoiceControlPanel())


@bot.command()
async def send_girl_ticket(ctx):
    file = await get_discord_file_from_url(GIRL_BANNER_URL, "banner_girl.png")
    if file:
        img_embed = discord.Embed(color=discord.Color.from_rgb(255, 105, 180)).set_image(url="attachment://banner_girl.png")
        await ctx.send(file=file, embed=img_embed)
    text_embed = discord.Embed(
        description=(
            "<:793670heart:1503151722611347586> **Роль Девушка**\n\n"
            "<a:a_pink_dot:1503133833548271646> Нажмите кнопку ниже для создания тикета."
        ), 
        color=discord.Color.from_rgb(255, 105, 180)
    )
    await ctx.send(embed=text_embed, view=GirlTicketMainView())


@bot.command()
async def send_ticket(ctx):
    file = await get_discord_file_from_url(TICKET_BANNER_URL, "banner.png")
    if file:
        img_embed = discord.Embed(color=discord.Color.from_rgb(57, 255, 20)).set_image(url="attachment://banner.png")
        await ctx.send(file=file, embed=img_embed)
    text_embed = discord.Embed(
        description=(
            "<:18690member:1503151722611347586> **Система поддержки ALASH PROJECT KZ**\n\n"
            "<a:15770animatedarrowyellow:1503049767016595586> **Возникли вопросы или проблемы? Опишите ситуацию**"
        ), 
        color=discord.Color.from_rgb(57, 255, 20)
    )
    await ctx.send(embed=text_embed, view=TicketMainView())


@bot.command()
async def send_media(ctx):
    file = await get_discord_file_from_url(MEDIA_BANNER_URL, "banner_media.png")
    if file:
        img_embed = discord.Embed(color=discord.Color.from_rgb(180, 0, 0)).set_image(url="attachment://banner_media.png")
        await ctx.send(file=file, embed=img_embed)
    text_embed = discord.Embed(
        description=(
            "<a:a_pink_dot:1503133833548271646> Наш проект готов к сотрудничеству с медиа игроками.\n\n"
            "<a:15770animatedarrowyellow:1503049767016595586> **Что вы получите**\n"
            "<a:a_pink_dot:1503133833548271646> Роль <@&{MEDIA_ROLE_ID}>"
        ).format(MEDIA_ROLE_ID=MEDIA_ROLE_ID), 
        color=discord.Color.from_rgb(180, 0, 0)
    )
    await ctx.send(embed=text_embed, view=MediaMainView())


@bot.command()
async def send_clan(ctx):
    embed = discord.Embed(
        title="<a:15770animatedarrowyellow:1503049767016595586> Клановые войны",
        description=(
            "Создай клан, собери команду и бросай вызов другим кланам в матчах 5v5\n\n"
            "<a:15770animatedarrowyellow:1503049767016595586> **Как начать**\n"
            "<a:a_pink_dot:1503133833548271646> Нажми \"Создать клан\" и введи название и тег\n"
            "<a:a_pink_dot:1503133833548271646> Пригласи минимум 4 участников через \"Мой клан\"\n"
            "<a:a_pink_dot:1503133833548271646> Бросай вызовы через меню управления кланом\n\n"
            "<a:15770animatedarrowyellow:1503049767016595586> **Правила**\n"
            "<a:a_pink_dot:1503133833548271646> Минимум 5 участников для участия в войнах\n"
            "<a:a_pink_dot:1503133833548271646> Cooldown между вызовами одному клану — 2 ч.\n"
            "<a:a_pink_dot:1503133833548271646> Если клан не собрал 5 игроков за 5 мин до матча — NO-SHOW\n"
            "<a:a_pink_dot:1503133833548271646> Тег клана автоматически добавляется к нику каждого участника\n\n"
            "**Alash project kz**"
        ),
        color=discord.Color.from_rgb(180, 0, 0)
    )
    embed.set_footer(text="alashproject.kz")
    await ctx.send(embed=embed, view=ClanPanelView())


# --------------------------------------------------
# RUN BOT WITH SAFE TOKEN CHECK
# --------------------------------------------------
raw_token = os.getenv("DISCORD_TOKEN")

if not raw_token:
    print("❌ КРИТИЧЕСКАЯ ОШИБКА: Переменная DISCORD_TOKEN не найдена в Environment на Render!")
else:
    token = raw_token.strip().strip('"').strip("'")
    try:
        bot.run(token)
    except discord.errors.LoginFailure:
        print("❌ ОШИБКА АВТОРИЗАЦИИ: Неверный DISCORD_TOKEN! Пересоздайте токен в Discord Developer Portal.")
    except Exception as e:
        print(f"❌ НЕИЗВЕСТНАЯ ОШИБКА ПРИ ЗАПУСКЕ: {e}")