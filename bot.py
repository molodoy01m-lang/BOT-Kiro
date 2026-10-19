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
intents.guilds = True

GIRL_BANNER_URL = "https://media.discordapp.net/attachments/1544309714962227230/1557815971660435456/banner_girl.png?ex=6ac92cae&is=6ac7db2e&hm=250e0baedfe61fc5baff21e59e0e6bd61f5e494d88ade315be12b6e3c199c916&=&format=webp&quality=lossless&width=2048&height=729"
GIRL_STAFF_ROLE_IDS = [1532745811778207985, 1530890552676188301, 1530886657530925256]

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
        activity = discord.Activity(
            type=discord.ActivityType.watching, 
            name="alashproject.kz | /help"
        )
        await self.change_presence(activity=activity)
        print("==========================================")
        print(f" KIRO BOT УСПЕШНО ЗАПУЩЕН: {self.user} ")
        print("==========================================")

bot = KiroBot()

# --------------------------------------------------
# COMMANDS
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
