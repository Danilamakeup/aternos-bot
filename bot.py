import discord
from discord.ext import commands
import os

TOKEN = os.getenv("TOKEN")  # будем брать из Render

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"Бот запущен как {bot.user}")

@bot.command()
async def ping(ctx):
    await ctx.send("Pong! Бот работает")

@bot.command()
async def статус(ctx):
    await ctx.send("Пока заглушка. Скоро добавим Aternos")

bot.run(TOKEN)
