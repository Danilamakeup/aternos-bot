import discord
from discord.ext import commands, tasks
import os
from aiohttp import web
import asyncio
import json
import struct


# =========================================================
# НАСТРОЙКИ
# =========================================================

TOKEN = os.getenv("TOKEN")

SERVER_HOST = "heavenserver.aternos.me"
SERVER_PORT = 15419

# Проверка сервера каждые 60 секунд
CHECK_INTERVAL = 60


# =========================================================
# DISCORD
# =========================================================

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)


# =========================================================
# MINECRAFT VARINT
# =========================================================

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
        byte_data = await reader.readexactly(1)
        byte = byte_data[0]

        result |= (byte & 0x7F) << (7 * num_read)

        num_read += 1

        if num_read > 5:
            raise ValueError("VarInt слишком большой")

        if not (byte & 0x80):
            break

    return result


# =========================================================
# ПРОВЕРКА MINECRAFT-СЕРВЕРА
# =========================================================

async def check_minecraft_server():

    reader = None
    writer = None

    print(
        f"[Aternos] Проверяю "
        f"{SERVER_HOST}:{SERVER_PORT}"
    )

    try:

        # -------------------------------------------------
        # TCP CONNECT
        # -------------------------------------------------

        print("[Aternos] Подключаюсь к серверу...")

        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(
                SERVER_HOST,
                SERVER_PORT
            ),
            timeout=8
        )

        print("[Aternos] TCP соединение установлено!")


        # -------------------------------------------------
        # MINECRAFT HANDSHAKE
        # -------------------------------------------------

        protocol_version = 767

        host_bytes = SERVER_HOST.encode("utf-8")

        handshake_data = (
            encode_varint(0) +
            encode_varint(protocol_version) +
            encode_varint(len(host_bytes)) +
            host_bytes +
            struct.pack(">H", SERVER_PORT) +
            encode_varint(1)
        )

        handshake_packet = (
            encode_varint(len(handshake_data)) +
            handshake_data
        )

        writer.write(handshake_packet)


        # -------------------------------------------------
        # STATUS REQUEST
        # -------------------------------------------------

        status_request = (
            encode_varint(1) +
            encode_varint(0)
        )

        writer.write(status_request)

        await writer.drain()

        print("[Aternos] Status Request отправлен")


        # -------------------------------------------------
        # ПОЛУЧАЕМ ОТВЕТ
        # -------------------------------------------------

        packet_length = await asyncio.wait_for(
            read_varint(reader),
            timeout=8
        )

        print(
            f"[Aternos] Размер ответа: "
            f"{packet_length} байт"
        )

        packet_id = await asyncio.wait_for(
            read_varint(reader),
            timeout=8
        )

        print(
            f"[Aternos] Packet ID: "
            f"{packet_id}"
        )

        if packet_id != 0:
            raise ValueError(
                f"Неожиданный Packet ID: {packet_id}"
            )


        # -------------------------------------------------
        # JSON
        # -------------------------------------------------

        json_length = await asyncio.wait_for(
            read_varint(reader),
            timeout=8
        )

        print(
            f"[Aternos] JSON размер: "
            f"{json_length} байт"
        )

        json_data = await asyncio.wait_for(
            reader.readexactly(json_length),
            timeout=8
        )

        json_text = json_data.decode("utf-8")

        print(
            f"[Aternos] Получен ответ: "
            f"{json_text[:500]}"
        )

        data = json.loads(json_text)


        # -------------------------------------------------
        # ИГРОКИ
        # -------------------------------------------------

        players = data.get("players", {})

        online = players.get("online", 0)
        maximum = players.get("max", 0)

        version_data = data.get(
            "version",
            {}
        )

        version = version_data.get(
            "name",
            "Unknown"
        )


        print(
            f"[Aternos] УСПЕХ! "
            f"ONLINE | {online}/{maximum} | "
            f"Версия: {version}"
        )

        return {
            "online": True,
            "players": online,
            "max_players": maximum,
            "version": version
        }


    # =====================================================
    # ОШИБКИ
    # =====================================================

    except asyncio.TimeoutError:

        print(
            "[Aternos ERROR] TIMEOUT: "
            "сервер не ответил за отведённое время."
        )

        return {
            "online": False,
            "players": 0,
            "max_players": 0,
            "version": None
        }


    except ConnectionRefusedError as e:

        print(
            f"[Aternos ERROR] "
            f"CONNECTION REFUSED: {e}"
        )

        return {
            "online": False,
            "players": 0,
            "max_players": 0,
            "version": None
        }


    except OSError as e:

        print(
            f"[Aternos ERROR] "
            f"OS ERROR: {type(e).__name__}: {e}"
        )

        return {
            "online": False,
            "players": 0,
            "max_players": 0,
            "version": None
        }


    except json.JSONDecodeError as e:

        print(
            f"[Aternos ERROR] "
            f"JSON ERROR: {e}"
        )

        return {
            "online": False,
            "players": 0,
            "max_players": 0,
            "version": None
        }


    except Exception as e:

        print(
            f"[Aternos ERROR] "
            f"{type(e).__name__}: {e}"
        )

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


# =========================================================
# DISCORD: READY
# =========================================================

@bot.event
async def on_ready():

    print("=" * 50)

    print(
        f"Бот запущен как: "
        f"{bot.user}"
    )

    print(
        f"Мониторинг: "
        f"{SERVER_HOST}:{SERVER_PORT}"
    )

    print(
        f"Интервал проверки: "
        f"{CHECK_INTERVAL} секунд"
    )

    print("=" * 50)

    if not server_monitor.is_running():
        server_monitor.start()


# =========================================================
# !PING
# =========================================================

@bot.command()
async def ping(ctx):

    await ctx.send(
        "🏓 Pong! Бот работает."
    )


# =========================================================
# !СТАТУС
# =========================================================

@bot.command()
async def статус(ctx):

    await ctx.send(
        "🔎 Проверяю Minecraft-сервер..."
    )

    status = await check_minecraft_server()

    if status["online"]:

        await ctx.send(
            f"🟢 **Сервер онлайн!**\n\n"
            f"👥 Игроки: "
            f"**{status['players']} / "
            f"{status['max_players']}**\n"
            f"🎮 Версия: "
            f"**{status['version']}**\n"
            f"🌐 `{SERVER_HOST}:{SERVER_PORT}`"
        )

    else:

        await ctx.send(
            f"🔴 **Сервер оффлайн**\n\n"
            f"🌐 `{SERVER_HOST}:{SERVER_PORT}`\n"
            f"⚠️ Подробности смотри в "
            f"**Render Logs**."
        )


# =========================================================
# !STATUS
# =========================================================

@bot.command()
async def status(ctx):

    await ctx.invoke(статус)


# =========================================================
# АВТОМАТИЧЕСКИЙ МОНИТОРИНГ
# =========================================================

last_status = None


@tasks.loop(seconds=CHECK_INTERVAL)
async def server_monitor():

    global last_status

    print(
        "\n"
        + "=" * 50
    )

    print(
        "[Monitor] Начинаю проверку..."
    )

    status = await check_minecraft_server()

    current_status = (
        status["online"],
        status["players"],
        status["max_players"]
    )

    print(
        f"[Monitor] Результат: "
        f"{'ONLINE' if status['online'] else 'OFFLINE'}"
        f" | "
        f"{status['players']}/"
        f"{status['max_players']}"
    )


    # Если состояние изменилось
    if current_status != last_status:

        print(
            "[Monitor] ⚡ Состояние изменилось!"
        )

        last_status = current_status

    else:

        print(
            "[Monitor] Состояние без изменений."
        )

    print(
        "=" * 50
        + "\n"
    )


@server_monitor.before_loop
async def before_monitor():

    print(
        "[Monitor] Жду готовности Discord..."
    )

    await bot.wait_until_ready()

    print(
        "[Monitor] Discord готов!"
    )


# =========================================================
# WEB SERVER ДЛЯ RENDER
# =========================================================

async def handle(request):

    return web.Response(
        text="Bot is alive"
    )


async def start_web_server():

    app = web.Application()

    app.router.add_get(
        "/",
        handle
    )

    runner = web.AppRunner(app)

    await runner.setup()

    port = int(
        os.environ.get(
            "PORT",
            8080
        )
    )

    site = web.TCPSite(
        runner,
        "0.0.0.0",
        port
    )

    await site.start()

    print(
        f"Web server started on port {port}"
    )


# =========================================================
# MAIN
# =========================================================

async def main():

    await start_web_server()

    print(
        "[Bot] Запускаю Discord..."
    )

    await bot.start(TOKEN)


asyncio.run(main())
