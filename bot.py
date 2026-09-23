```python
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

# Minecraft Java 26.2 = protocol 776
PROTOCOL_VERSION = 776

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
        data = await reader.readexactly(1)
        byte = data[0]

        result |= (byte & 0x7F) << (7 * num_read)

        num_read += 1

        if num_read > 5:
            raise ValueError("VarInt слишком большой")

        if not (byte & 0x80):
            return result


# =========================================================
# ПРОВЕРКА MINECRAFT
# =========================================================

async def check_minecraft_server():

    reader = None
    writer = None

    print()
    print("=" * 70)
    print(
        f"[Aternos] Проверка "
        f"{SERVER_HOST}:{SERVER_PORT}"
    )
    print(
        f"[Aternos] Protocol: {PROTOCOL_VERSION}"
    )

    try:

        # -------------------------------------------------
        # TCP
        # -------------------------------------------------

        print(
            "[Aternos] Подключаюсь..."
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
        # HANDSHAKE
        # -------------------------------------------------

        host_bytes = SERVER_HOST.encode("utf-8")

        handshake_data = (
            encode_varint(0) +
            encode_varint(PROTOCOL_VERSION) +
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

        status_request_data = encode_varint(0)

        status_packet = (
            encode_varint(len(status_request_data)) +
            status_request_data
        )

        writer.write(status_packet)

        await writer.drain()

        print(
            "[Aternos] Status Request отправлен"
        )

        # -------------------------------------------------
        # RESPONSE PACKET
        # -------------------------------------------------

        packet_length = await asyncio.wait_for(
            read_varint(reader),
            timeout=10
        )

        print(
            f"[Aternos] Packet size: "
            f"{packet_length}"
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
                f"Ожидался Packet ID 0, "
                f"получен {packet_id}"
            )

        # -------------------------------------------------
        # JSON LENGTH
        # -------------------------------------------------

        json_length = await asyncio.wait_for(
            read_varint(reader),
            timeout=10
        )

        print(
            f"[Aternos] JSON size: "
            f"{json_length}"
        )

        # Защита от странного ответа
        if json_length <= 0 or json_length > 5_000_000:
            raise ValueError(
                f"Некорректный JSON размер: "
                f"{json_length}"
            )

        # -------------------------------------------------
        # JSON
        # -------------------------------------------------

        json_data = await asyncio.wait_for(
            reader.readexactly(json_length),
            timeout=10
        )

        json_text = json_data.decode(
            "utf-8",
            errors="replace"
        )

        print(
            "[Aternos] Получен ответ:"
        )

        print(
            json_text[:2000]
        )

        data = json.loads(json_text)

        # -------------------------------------------------
        # VERSION
        # -------------------------------------------------

        version_data = data.get(
            "version",
            {}
        )

        version = str(
            version_data.get(
                "name",
                "Unknown"
            )
        )

        # -------------------------------------------------
        # PLAYERS
        # -------------------------------------------------

        players_data = data.get(
            "players",
            {}
        )

        online = int(
            players_data.get(
                "online",
                0
            )
        )

        maximum = int(
            players_data.get(
                "max",
                0
            )
        )

        # =================================================
        # OFFLINE ATERNOS
        # =================================================

        version_clean = (
            version
            .replace("§c", "")
            .replace("§r", "")
            .strip()
            .lower()
        )

        if "offline" in version_clean:

            print(
                "[Aternos] 🔴 OFFLINE"
            )

            print(
                "[Aternos] Сервер выключен. "
                "Aternos вернул Offline."
            )

            print("=" * 70)

            return {
                "online": False,
                "players": 0,
                "max_players": maximum,
                "version": version,
                "motd": None
            }

        # =================================================
        # ONLINE
        # =================================================

        description = data.get(
            "description",
            ""
        )

        if isinstance(description, dict):
            motd = description.get(
                "text",
                ""
            )
        else:
            motd = str(description)

        print(
            "[Aternos] 🟢 ONLINE!"
        )

        print(
            f"[Aternos] Players: "
            f"{online}/{maximum}"
        )

        print(
            f"[Aternos] Version: "
            f"{version}"
        )

        print(
            "=" * 70
        )

        return {
            "online": True,
            "players": online,
            "max_players": maximum,
            "version": version,
            "motd": motd
        }

    # =====================================================
    # ERRORS
    # =====================================================

    except asyncio.TimeoutError:

        print(
            "[Aternos ERROR] "
            "TIMEOUT"
        )

        print(
            "[Aternos ERROR] "
            "Сервер не ответил вовремя."
        )

    except ConnectionRefusedError as e:

        print(
            "[Aternos ERROR] "
            f"CONNECTION REFUSED: {e}"
        )

    except json.JSONDecodeError as e:

        print(
            "[Aternos ERROR] "
            f"JSON ERROR: {e}"
        )

    except UnicodeDecodeError as e:

        print(
            "[Aternos ERROR] "
            f"UNICODE ERROR: {e}"
        )

    except OSError as e:

        print(
            "[Aternos ERROR] "
            f"{type(e).__name__}: {e}"
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

    print("=" * 70)

    return {
        "online": False,
        "players": 0,
        "max_players": 0,
        "version": None,
        "motd": None
    }


# =========================================================
# DISCORD READY
# =========================================================

@bot.event
async def on_ready():

    global monitor_task

    print()
    print("=" * 70)

    print(
        f"[Discord] Бот: {bot.user}"
    )

    print(
        f"[Discord] Minecraft: "
        f"{SERVER_HOST}:{SERVER_PORT}"
    )

    print(
        f"[Discord] Minecraft protocol: "
        f"{PROTOCOL_VERSION}"
    )

    print(
        "[Discord] Minecraft: Java 26.2"
    )

    print(
        "[Discord] Core: Paper"
    )

    print("=" * 70)

    # -----------------------------------------------------
    # START MONITOR
    # -----------------------------------------------------

    if (
        monitor_task is None
        or monitor_task.done()
    ):

        print(
            "[Monitor] Запускаю монитор..."
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
        f"[Discord] {ctx.author} "
        f"использовал !статус"
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
            f"⚙️ Ядро: **Paper**\n"
            f"🌐 `{SERVER_HOST}:{SERVER_PORT}`"
        )

    else:

        await ctx.send(
            f"🔴 **Сервер оффлайн**\n\n"
            f"🌐 `{SERVER_HOST}:{SERVER_PORT}`\n"
            f"🎮 Minecraft: **26.2**"
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

    # Ждём подключения Discord

    await asyncio.sleep(5)

    while True:

        try:

            print()
            print(
                "#" * 70
            )

            print(
                "[Monitor] Начинаю проверку..."
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
                "#" * 70
            )

        except Exception as e:

            print(
                "[Monitor ERROR] "
                f"{type(e).__name__}: {e}"
            )

        await asyncio.sleep(
            CHECK_INTERVAL
        )


# =========================================================
# RENDER WEB SERVER
# =========================================================

async def handle(request):

    return web.Response(
        text="Aternos Discord Bot is alive"
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
        f"[Web] Render web server "
        f"запущен на порту {port}"
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

asyncio.run(main())
```
