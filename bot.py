import discord
from discord.ext import commands, tasks
import os
from aiohttp import web
import asyncio
import json
import struct


# =========================
# НАСТРОЙКИ
# =========================

TOKEN = os.getenv("TOKEN")

SERVER_HOST = "heavenserver.aternos.me"
SERVER_PORT = 15419

# Как часто проверять сервер
CHECK_INTERVAL = 60


# =========================
# DISCORD
# =========================

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)


# =========================
# MINECRAFT VARINT
# =========================

def encode_varint(value):
    result = bytearray()

    while True:
        temp = value & 0x7F
        value >>= 7

        if value:
            temp |= 0x80

        result.append(temp)

        if not value:
            break

    return bytes(result)


async def read_varint(reader):
    num_read = 0
    result = 0

    while True:
        byte = await reader.readexactly(1)
        byte = byte[0]

        result |= (byte & 0x7F) << (7 * num_read)
        num_read += 1

        if num_read > 5:
            raise ValueError("VarInt слишком большой")

        if not (byte & 0x80):
            break

    return result


# =========================
# ПРОВЕРКА MINECRAFT-СЕРВЕРА
# =========================

async def check_minecraft_server():
    reader = None
    writer = None

    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(SERVER_HOST, SERVER_PORT),
            timeout=5
        )

        # Handshake
        protocol_version = 767  # 1.21.x

        host_bytes = SERVER_HOST.encode("utf-8")

        handshake_data = (
            encode_varint(0) +
            encode_varint(protocol_version) +
            encode_varint(len(host_bytes)) +
            host_bytes +
            struct.pack(">H", SERVER_PORT) +
            encode_varint(1)
        )

        packet = encode_varint(len(handshake_data)) + handshake_data

        writer.write(packet)

        # Status Request
        writer.write(encode_varint(1) + encode_varint(0))

        await writer.drain()

        # Ответ сервера
        packet_length = await asyncio.wait_for(
            read_varint(reader),
            timeout=5
        )

        packet_id = await asyncio.wait_for(
            read_varint(reader),
            timeout=5
        )

        if packet_id != 0:
            raise ValueError("Неожиданный packet ID")

        json_length = await asyncio.wait_for(
            read_varint(reader),
            timeout=5
        )

        json_data = await asyncio.wait_for(
            reader.readexactly(json_length),
            timeout=5
        )

        data = json.loads(json_data.decode("utf-8"))

        players = data.get("players", {})

        online = players.get("online", 0)
        maximum = players.get("max", 0)

        version = data.get("version", {}).get("name", "Unknown")

        return {
            "online": True,
            "players": online,
            "max_players": maximum,
            "version": version
        }

    except Exception as e:
        print(f"[Aternos] Сервер недоступен: {type(e).__name__}: {e}")

        return {
            "online": False,
            "players": 0,
            "max_players": 0,
            "version": None
        }

    finally:
        if writer:
            writer.close()

            try:
                await writer.wait_closed()
            except Exception:
                pass


# =========================
# DISCORD КОМАНДЫ
# =========================

@bot.event
async def on_ready():
    print(f"Бот запущен как {bot.user}")
    print(f"Проверяем Minecraft-сервер: {SERVER_HOST}:{SERVER_PORT}")

    if not server_monitor.is_running():
        server_monitor.start()


@bot.command()
async def ping(ctx):
    await ctx.send("🏓 Pong! Бот работает")


@bot.command()
async def статус(ctx):
    status = await check_minecraft_server()

    if status["online"]:
        await ctx.send(
            f"🟢 **Сервер онлайн!**\n"
            f"👥 Игроки: **{status['players']} / {status['max_players']}**\n"
            f"🎮 Версия: **{status['version']}**\n"
            f"🌐 `{SERVER_HOST}:{SERVER_PORT}`"
        )

    else:
        await ctx.send(
            f"🔴 **Сервер оффлайн**\n"
            f"🌐 `{SERVER_HOST}:{SERVER_PORT}`\n"
            f"😴 Похоже, Aternos его выключил."
        )


# Английская команда на всякий случай
@bot.command()
async def status(ctx):
    await ctx.invoke(статус)


# =========================
# АВТОМАТИЧЕСКИЙ МОНИТОРИНГ
# =========================

last_status = None


@tasks.loop(seconds=CHECK_INTERVAL)
async def server_monitor():
    global last_status

    status = await check_minecraft_server()

    current_status = (
        status["online"],
        status["players"],
        status["max_players"]
    )

    print(
        f"[Monitor] "
        f"{'ONLINE' if status['online'] else 'OFFLINE'} | "
        f"{status['players']}/{status['max_players']}"
    )

    # Здесь пока просто отслеживаем изменения.
    # Позже можно добавить автоматическое сообщение в Discord.

    if current_status != last_status:
        last_status = current_status

        if status["online"]:
            print(
                f"🟢 Aternos ONLINE: "
                f"{status['players']}/{status['max_players']}"
            )
        else:
            print("🔴 Aternos OFFLINE")


@server_monitor.before_loop
async def before_monitor():
    await bot.wait_until_ready()


# =========================
# WEB-СЕРВЕР ДЛЯ RENDER
# =========================

async def handle(request):
    return web.Response(
        text="Bot is alive"
    )


async def start_web_server():
    app = web.Application()

    app.router.add_get("/", handle)

    runner = web.AppRunner(app)
    await runner.setup()

    port = int(os.environ.get("PORT", 8080))

    site = web.TCPSite(
        runner,
        "0.0.0.0",
        port
    )

    await site.start()

    print(f"Web server started on port {port}")


# =========================
# ЗАПУСК
# =========================

async def main():
    await start_web_server()
    await bot.start(TOKEN)


asyncio.run(main())
