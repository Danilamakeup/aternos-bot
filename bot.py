import discord
from discord.ext import commands
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

monitor_task = None


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
            raise ValueError(
                "VarInt слишком большой"
            )

        if not (byte & 0x80):
            break

    return result


# =========================================================
# ПРОВЕРКА MINECRAFT-СЕРВЕРА
# =========================================================

async def check_minecraft_server():

    reader = None
    writer = None

    print("=" * 60)

    print(
        f"[Aternos] Проверяю "
        f"{SERVER_HOST}:{SERVER_PORT}"
    )

    try:

        # -------------------------------------------------
        # TCP CONNECTION
        # -------------------------------------------------

        print(
            "[Aternos] Подключаюсь к серверу..."
        )

        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(
                SERVER_HOST,
                SERVER_PORT
            ),
            timeout=10
        )

        print(
            "[Aternos] TCP соединение установлено!"
        )

        # -------------------------------------------------
        # MINECRAFT HANDSHAKE
        # -------------------------------------------------

        protocol_version = 767

        host_bytes = SERVER_HOST.encode(
            "utf-8"
        )

        handshake_data = (
            encode_varint(0) +
            encode_varint(protocol_version) +
            encode_varint(len(host_bytes)) +
            host_bytes +
            struct.pack(
                ">H",
                SERVER_PORT
            ) +
            encode_varint(1)
        )

        handshake_packet = (
            encode_varint(
                len(handshake_data)
            ) +
            handshake_data
        )

        writer.write(
            handshake_packet
        )

        # -------------------------------------------------
        # STATUS REQUEST
        # -------------------------------------------------

        status_request = (
            encode_varint(1) +
            encode_varint(0)
        )

        writer.write(
            status_request
        )

        await writer.drain()

        print(
            "[Aternos] Status Request отправлен"
        )

        # -------------------------------------------------
        # RESPONSE
        # -------------------------------------------------

        packet_length = await asyncio.wait_for(
            read_varint(reader),
            timeout=10
        )

        print(
            f"[Aternos] Размер ответа: "
            f"{packet_length} байт"
        )

        packet_id = await asyncio.wait_for(
            read_varint(reader),
            timeout=10
        )

        print(
            f"[Aternos] Packet ID: "
            f"{packet_id}"
        )

        if packet_id != 0:

            raise ValueError(
                f"Неожиданный Packet ID: "
                f"{packet_id}"
            )

        # -------------------------------------------------
        # JSON
        # -------------------------------------------------

        json_length = await asyncio.wait_for(
            read_varint(reader),
            timeout=10
        )

        print(
            f"[Aternos] JSON размер: "
            f"{json_length} байт"
        )

        json_data = await asyncio.wait_for(
            reader.readexactly(
                json_length
            ),
            timeout=10
        )

        json_text = json_data.decode(
            "utf-8"
        )

        print(
            "[Aternos] Ответ:"
        )

        print(
            json_text[:1000]
        )

        data = json.loads(
            json_text
        )

        # -------------------------------------------------
        # PLAYERS
        # -------------------------------------------------

        players = data.get(
            "players",
            {}
        )

        online = players.get(
            "online",
            0
        )

        maximum = players.get(
            "max",
            0
        )

        # -------------------------------------------------
        # VERSION
        # -------------------------------------------------

        version_data = data.get(
            "version",
            {}
        )

        version = version_data.get(
            "name",
            "Unknown"
        )

        # =================================================
        # ГЛАВНОЕ ИСПРАВЛЕНИЕ
        # =================================================

        # Aternos может отвечать даже когда Minecraft
        # сервер выключен.
        #
        # В этом случае он может вернуть:
        #
        # §c Offline
        #
        # Поэтому просто факт получения JSON
        # НЕ означает, что сервер онлайн.

        version_clean = str(
            version
        ).replace(
            "§c",
            ""
        ).strip().lower()

        if (
            "offline" in version_clean
            or version_clean == ""
        ):

            print(
                "[Aternos] 🔴 Сервер OFFLINE"
            )

            print(
                "[Aternos] Aternos вернул "
                "'Offline'"
            )

            print("=" * 60)

            return {
                "online": False,
                "players": 0,
                "max_players": maximum,
                "version": version
            }

        # -------------------------------------------------
        # ONLINE
        # -------------------------------------------------

        print(
            "[Aternos] 🟢 УСПЕХ!"
        )

        print(
            f"[Aternos] ONLINE | "
            f"{online}/{maximum} | "
            f"Версия: {version}"
        )

        print("=" * 60)

        return {
            "online": True,
            "players": online,
            "max_players": maximum,
            "version": version
        }

    # =====================================================
    # ERRORS
    # =====================================================

    except asyncio.TimeoutError:

        print(
            "[Aternos ERROR] "
            "TIMEOUT: сервер не ответил."
        )

    except ConnectionRefusedError as e:

        print(
            "[Aternos ERROR] "
            f"CONNECTION REFUSED: {e}"
        )

    except OSError as e:

        print(
            "[Aternos ERROR] "
            f"{type(e).__name__}: {e}"
        )

    except json.JSONDecodeError as e:

        print(
            "[Aternos ERROR] "
            f"JSON ERROR: {e}"
        )

    except Exception as e:

        print(
            "[Aternos ERROR] "
            f"{type(e).__name__}: {e}"
        )

    finally:

        if writer:

            writer.close()

            try:
                await writer.wait_closed()
            except Exception:
                pass

    print("=" * 60)

    return {
        "online": False,
        "players": 0,
        "max_players": 0,
        "version": None
    }


# =========================================================
# DISCORD READY
# =========================================================

@bot.event
async def on_ready():

    global monitor_task

    print("=" * 60)

    print(
        f"[Discord] Бот запущен как: "
        f"{bot.user}"
    )

    print(
        f"[Discord] Minecraft: "
        f"{SERVER_HOST}:{SERVER_PORT}"
    )

    print(
        f"[Discord] Интервал проверки: "
        f"{CHECK_INTERVAL} секунд"
    )

    print("=" * 60)

    # Запускаем монитор только один раз

    if (
        monitor_task is None
        or monitor_task.done()
    ):

        print(
            "[Monitor] Запускаю "
            "фоновый монитор..."
        )

        monitor_task = asyncio.create_task(
            server_monitor()
        )


# =========================================================
# !ping
# =========================================================

@bot.command()
async def ping(ctx):

    await ctx.send(
        "🏓 Pong! Бот работает."
    )


# =========================================================
# !статус
# =========================================================

@bot.command()
async def статус(ctx):

    await ctx.send(
        "🔎 Проверяю Minecraft-сервер..."
    )

    print(
        f"[Discord] Пользователь "
        f"{ctx.author} использовал !статус"
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
            f"⚠️ Подробности смотри "
            f"в **Render Logs**."
        )


# =========================================================
# !status
# =========================================================

@bot.command()
async def status(ctx):

    await ctx.invoke(
        статус
    )


# =========================================================
# ФОНОВЫЙ МОНИТОР
# =========================================================

async def server_monitor():

    print(
        "[Monitor] Фоновый монитор запущен!"
    )

    # Небольшая задержка после запуска Discord

    await asyncio.sleep(5)

    while True:

        print("\n")
        print(
            "#" * 60
        )

        print(
            "[Monitor] НАЧАЛО ПРОВЕРКИ"
        )

        print(
            "#" * 60
        )

        status = await check_minecraft_server()

        if status["online"]:

            print(
                f"[Monitor] 🟢 ONLINE "
                f"{status['players']}/"
                f"{status['max_players']}"
            )

        else:

            print(
                "[Monitor] 🔴 OFFLINE"
            )

        print(
            "#" * 60
        )

        await asyncio.sleep(
            CHECK_INTERVAL
        )


# =========================================================
# RENDER WEB SERVER
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

    runner = web.AppRunner(
        app
    )

    await runner.setup()

    # Render сам передаёт PORT.
    # Обычно это 10000.

    port = int(
        os.environ.get(
            "PORT",
            10000
        )
    )

    site = web.TCPSite(
        runner,
        "0.0.0.0",
        port
    )

    await site.start()

    print(
        f"[Web] Сервер запущен "
        f"на порту {port}"
    )


# =========================================================
# MAIN
# =========================================================

async def main():

    await start_web_server()

    print(
        "[Bot] Запускаю Discord..."
    )

    await bot.start(
        TOKEN
    )


# =========================================================
# START
# =========================================================

asyncio.run(
    main()
)
