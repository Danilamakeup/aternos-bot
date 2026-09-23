import discord
from discord.ext import commands
import os
from aiohttp import web
import asyncio

TOKEN = os.getenv("TOKEN")

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

# Маленький веб-сервер, чтобы Render не убивал бота
async def handle(request):
    return web.Response(text="Bot is alive")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"Web server started on port {port}")

async def main():
    await start_web_server()
    await bot.start(TOKEN)

asyncio.run(main())
