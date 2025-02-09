import discord
from discord.ext import commands
import os 

bot = commands.Bot(command_prefix="?")


bot.load_extension("cogs.temp")
YOUR_TOKEN = ""

@bot.event
async def on_ready():
    print("Bot is ready")





bot.run(YOUR_TOKEN)