"""
Premium Telegram VC Music Bot
- Pyrogram + py-tgcalls + yt-dlp
- Health server on PORT 8000 (Render Web Service compatible)
"""

import os
import re
import asyncio
import logging
from os import getenv

from aiohttp import web
from pyrogram import Client, filters, idle
from pyrogram.types import (
    Message,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    CallbackQuery,
)
from pyrogram.enums import ChatMemberStatus

import yt_dlp
from pytgcalls import PyTgCalls
from pytgcalls.types import Update, MediaStream
from pytgcalls.types.stream import StreamEnded
from pytgcalls.exceptions import NoActiveGroupCall

# ---------- Logging ----------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
log = logging.getLogger("vcbot")

# ---------- Config ----------
API_ID = int(getenv("API_ID", "35828291"))
API_HASH = getenv("API_HASH", "c025ee9d01d73b9d738d4f3e5e6137e2")
BOT_TOKEN = getenv("BOT_TOKEN", "8728584423:AAFpNbqPaBx9MUR36sHuqyd33nHH7bCxQe0")
SESSION_STRING = getenv("SESSION_STRING", "BQIiskMAukI__8yuI6z3itiU_dpIRp00CbRSQJJWK-sujY9AcnsQQ2dCxL69Pj7mfgG3iqbUMSuc36G6Df3U3nl0S5fWnRiDpdUKtuR5wdw5-ZfFxMPpdihl_T57Bsy5z9Gvjun02tFNvVev9_l1MPIllB96JkBZbPw-yDlMGQ5LnUxmd2jnKfv94fnGQLlx9EuUllb6-4rz_sZBayltQd8ivTieW_3P3ryK0Wy8IQGTX2xklIq-upkXy179JORwZVbmFS4L8nfzq_Xu5pn492qGgyGCu7GrF7rpcV3R1Eo7bzC1XUBm4Hnjdb0klr5YsQBK9UYHeygUuWGScQmMFXZSg_XH8gAAAAIIQ6DnAQ")
OWNER_ID = int(getenv("OWNER_ID", "7953454559"))
PORT = int(getenv("PORT", "8000"))
START_IMAGE = getenv(
    "START_IMAGE",
    "https://files.catbox.moe/7e1z6m.jpg",
)

assert API_ID and API_HASH and BOT_TOKEN and SESSION_STRING, (
    "API_ID, API_HASH, BOT_TOKEN, SESSION_STRING must be set"
)

# ---------- Premium Font ----------
_FONT_MAP = str.maketrans(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ",
    "𝖺𝖻𝖼𝖽𝖾𝖿𝗀𝗁𝗂𝗃𝗄𝗅𝗆𝗇𝗈𝗉𝗊𝗋𝗌𝗍𝗎𝗏𝗐𝗑𝗒𝗓𝖠𝖡𝖢𝖣𝖤𝖥𝖦𝖧𝖨𝖩𝖪𝖫𝖬𝖭𝖮𝖯𝖰𝖱𝖲𝖳𝖴𝖵𝖶𝖷𝖸𝖹",
)


def font(text: str) -> str:
    return text.translate(_FONT_MAP)


# ---------- Clients ----------
bot = Client(
    "vcmusicbot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    in_memory=True,
)

assistant = Client(
    "vcassistant",
    api_id=API_ID,
    api_hash=API_HASH,
    session_string=SESSION_STRING,
    in_memory=True,
)

calls = PyTgCalls(assistant)

# chat_id -> queue list of dict(title, url, thumb, requester)
QUEUES: dict[int, list[dict]] = {}


# ---------- yt-dlp helpers ----------
YDL_OPTS = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "no_warnings": True,
    "default_search": "ytsearch1",
    "geo_bypass": True,
    "nocheckcertificate": True,
    "source_address": "0.0.0.0",
}


async def yt_search(query: str) -> dict | None:
    def _run():
        with yt_dlp.YoutubeDL(YDL_OPTS) as ydl:
            info = ydl.extract_info(query, download=False)
            if "entries" in info:
                info = info["entries"][0]
            return {
                "title": info.get("title", "Unknown"),
                "url": info["url"],
                "webpage": info.get("webpage_url", ""),
                "thumb": (info.get("thumbnail")
                          or f"https://i.ytimg.com/vi/{info.get('id','')}/hqdefault.jpg"),
                "duration": info.get("duration", 0),
            }

    try:
        return await asyncio.to_thread(_run)
    except Exception as e:
        log.error("yt_search failed: %s", e)
        return None


# ---------- UI ----------
def player_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("⏸ Pause", callback_data="pause"),
                InlineKeyboardButton("▶️ Resume", callback_data="resume"),
                InlineKeyboardButton("⏹ Stop", callback_data="stop"),
            ],
            [
                InlineKeyboardButton("⏭ Skip", callback_data="skip"),
                InlineKeyboardButton("❌ Close", callback_data="close"),
            ],
        ]
    )


def start_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "➕ " + font("Add Me To Group"),
                    url=f"https://t.me/{BOT_USERNAME}?startgroup=true",
                )
            ],
            [
                InlineKeyboardButton("📜 " + font("Help"), callback_data="help"),
                InlineKeyboardButton("👑 " + font("Owner"), url="https://t.me/"),
            ],
        ]
    )


BOT_USERNAME = "your_bot"  # replaced at startup


# ---------- Commands ----------
@bot.on_message(filters.command(["start"]))
async def start_cmd(_, m: Message):
    caption = (
        f"👋 {font('Hey')} {m.from_user.mention}!\n\n"
        f"🎶 {font('I am a Premium VC Music Bot')}\n"
        f"⚡ {font('Stream high quality music in your group voice chat')}\n\n"
        f"➤ {font('Add me to your group, start a Voice Chat, and use')} /play <song>"
    )
    try:
        await m.reply_photo(
            photo=START_IMAGE,
            caption=caption,
            has_spoiler=True,
            reply_markup=start_kb(),
        )
    except Exception:
        await m.reply_text(caption, reply_markup=start_kb())


@bot.on_message(filters.command(["help"]))
async def help_cmd(_, m: Message):
    text = (
        f"📜 **{font('Commands')}**\n\n"
        "• /play <song name or url> — play music in VC\n"
        "• /pause — pause stream\n"
        "• /resume — resume stream\n"
        "• /skip — play next in queue\n"
        "• /stop — stop and leave VC\n"
        "• /ping — bot status\n"
    )
    await m.reply_text(text)


@bot.on_message(filters.command(["ping"]))
async def ping_cmd(_, m: Message):
    await m.reply_text(f"🏓 {font('Pong! Bot is alive')}")


async def _ensure_assistant_in_chat(chat_id: int, m: Message) -> bool:
    try:
        await bot.get_chat_member(chat_id, (await assistant.get_me()).id)
        return True
    except Exception:
        try:
            chat = await bot.get_chat(chat_id)
            invite = chat.invite_link or (await bot.export_chat_invite_link(chat_id))
            await assistant.join_chat(invite)
            return True
        except Exception as e:
            await m.reply_text(f"⚠️ {font('Could not join assistant')}: `{e}`")
            return False


@bot.on_message(filters.command(["play"]) & filters.group)
async def play_cmd(_, m: Message):
    if len(m.command) < 2 and not m.reply_to_message:
        return await m.reply_text(f"❓ {font('Usage')}: /play <song name>")
    query = m.text.split(None, 1)[1] if len(m.command) >= 2 else m.reply_to_message.text
    status = await m.reply_text(f"🔍 {font('Searching')}...")

    info = await yt_search(query)
    if not info:
        return await status.edit(f"❌ {font('No results found')}")

    if not await _ensure_assistant_in_chat(m.chat.id, m):
        return

    QUEUES.setdefault(m.chat.id, [])
    item = {**info, "requester": m.from_user.mention}

    try:
        if QUEUES[m.chat.id]:
            QUEUES[m.chat.id].append(item)
            return await status.edit(
                f"➕ {font('Added to queue')}: **{info['title']}**\n"
                f"📍 {font('Position')}: {len(QUEUES[m.chat.id])}"
            )

        QUEUES[m.chat.id].append(item)
        await calls.play(m.chat.id, MediaStream(info["url"]))
        await status.delete()
        await m.reply_photo(
            photo=info["thumb"],
            caption=(
                f"🎵 **{font('Now Playing')}**\n\n"
                f"📌 **{info['title']}**\n"
                f"👤 {font('Requested by')}: {item['requester']}"
            ),
            reply_markup=player_kb(),
        )
    except NoActiveGroupCall:
        QUEUES[m.chat.id].clear()
        await status.edit(
            f"⚠️ {font('No active Voice Chat. Please start a VC first, then run /play again')}"
        )
    except Exception as e:
        QUEUES[m.chat.id].clear()
        await status.edit(f"❌ {font('Error')}: `{e}`")


@bot.on_message(filters.command(["pause"]) & filters.group)
async def pause_cmd(_, m: Message):
    try:
        await calls.pause_stream(m.chat.id)
        await m.reply_text(f"⏸ {font('Paused')}")
    except Exception as e:
        await m.reply_text(f"❌ `{e}`")


@bot.on_message(filters.command(["resume"]) & filters.group)
async def resume_cmd(_, m: Message):
    try:
        await calls.resume_stream(m.chat.id)
        await m.reply_text(f"▶️ {font('Resumed')}")
    except Exception as e:
        await m.reply_text(f"❌ `{e}`")


@bot.on_message(filters.command(["stop", "end"]) & filters.group)
async def stop_cmd(_, m: Message):
    QUEUES.pop(m.chat.id, None)
    try:
        await calls.leave_call(m.chat.id)
    except Exception:
        pass
    await m.reply_text(f"⏹ {font('Stopped and left VC')}")


@bot.on_message(filters.command(["skip"]) & filters.group)
async def skip_cmd(_, m: Message):
    q = QUEUES.get(m.chat.id, [])
    if len(q) <= 1:
        QUEUES.pop(m.chat.id, None)
        try:
            await calls.leave_call(m.chat.id)
        except Exception:
            pass
        return await m.reply_text(f"📭 {font('Queue empty, left VC')}")

    q.pop(0)
    nxt = q[0]
    try:
        await calls.play(m.chat.id, MediaStream(nxt["url"]))
        await m.reply_text(f"⏭ {font('Now playing')}: **{nxt['title']}**")
    except Exception as e:
        await m.reply_text(f"❌ `{e}`")


# ---------- Callback buttons ----------
@bot.on_callback_query()
async def cb(_, q: CallbackQuery):
    data = q.data
    chat_id = q.message.chat.id
    try:
        if data == "pause":
            await calls.pause_stream(chat_id)
            await q.answer("Paused", show_alert=False)
        elif data == "resume":
            await calls.resume_stream(chat_id)
            await q.answer("Resumed", show_alert=False)
        elif data == "stop":
            QUEUES.pop(chat_id, None)
            await calls.leave_call(chat_id)
            await q.answer("Stopped")
        elif data == "skip":
            qlist = QUEUES.get(chat_id, [])
            if len(qlist) <= 1:
                QUEUES.pop(chat_id, None)
                await calls.leave_call(chat_id)
                await q.answer("Queue empty")
            else:
                qlist.pop(0)
                await calls.play(chat_id, MediaStream(qlist[0]["url"]))
                await q.answer(f"Skipped → {qlist[0]['title'][:30]}")
        elif data == "close":
            await q.message.delete()
        elif data == "help":
            await q.message.reply_text(
                f"📜 {font('Use')} /help {font('to see all commands')}"
            )
            await q.answer()
    except Exception as e:
        await q.answer(f"Error: {e}", show_alert=True)


# ---------- Stream end handler (auto-next) ----------
@calls.on_update()
async def stream_end(_, update: Update):
    if isinstance(update, StreamEnded):
        chat_id = update.chat_id
        q = QUEUES.get(chat_id, [])
        if q:
            q.pop(0)
        if q:
            try:
                await calls.play(chat_id, MediaStream(q[0]["url"]))
                await bot.send_message(
                    chat_id,
                    f"🎵 {font('Now playing')}: **{q[0]['title']}**",
                )
                return
            except Exception as e:
                log.error("auto-next failed: %s", e)
        QUEUES.pop(chat_id, None)
        try:
            await calls.leave_call(chat_id)
        except Exception:
            pass


# ---------- Health Server (PORT 8000) ----------
async def health(_):
    return web.json_response({"status": "ok", "bot": "vcmusicbot"})


async def run_web():
    app = web.Application()
    app.router.add_get("/", health)
    app.router.add_get("/health", health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    log.info("Health server listening on 0.0.0.0:%d", PORT)


# ---------- Main ----------
async def main():
    global BOT_USERNAME
    await bot.start()
    await assistant.start()
    await calls.start()
    me = await bot.get_me()
    BOT_USERNAME = me.username
    await run_web()
    log.info("✅ Bot @%s started successfully", BOT_USERNAME)
    await idle()
    await bot.stop()
    await assistant.stop()


if __name__ == "__main__":
    asyncio.run(main())
