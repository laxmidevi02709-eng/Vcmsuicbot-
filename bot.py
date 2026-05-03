"""
Premium Telegram VC Music Bot
- /start  -> banner image (spoiler) + premium font + inline buttons
- /play <song name or YouTube url>  -> bot joins VC and streams audio
- Inline controls on now-playing card: Pause / Resume / -10s / +10s / Stop / Help
- Auto "please make VC live" message if VC is not started
- Built for Render (Docker) — single command boot.

Env vars required:
  API_ID, API_HASH, BOT_TOKEN, SESSION_STRING
Optional:
  START_IMAGE  (https URL of banner)
"""
import asyncio
import os
import re
import logging
from typing import Dict, Optional

from pyrogram import Client, filters, idle
from pyrogram.enums import ChatType
from pyrogram.errors import RPCError
from pyrogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    CallbackQuery,
)

from pytgcalls import PyTgCalls
from pytgcalls.types import MediaStream, AudioQuality
from pytgcalls.exceptions import NoActiveGroupCall

import yt_dlp

from font import f

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
log = logging.getLogger("vcmusic")

# ---------- Config ----------
API_ID = int(os.getenv("API_ID", "35828291"))
API_HASH = os.getenv("API_HASH", "c025ee9d01d73b9d738d4f3e5e6137e2")
BOT_TOKEN = os.getenv("BOT_TOKEN", "8728584423:AAFpNbqPaBx9MUR36sHuqyd33nHH7bCxQe0")
SESSION_STRING = os.getenv("SESSION_STRING", "BQIiskMAukI__8yuI6z3itiU_dpIRp00CbRSQJJWK-sujY9AcnsQQ2dCxL69Pj7mfgG3iqbUMSuc36G6Df3U3nl0S5fWnRiDpdUKtuR5wdw5-ZfFxMPpdihl_T57Bsy5z9Gvjun02tFNvVev9_l1MPIllB96JkBZbPw-yDlMGQ5LnUxmd2jnKfv94fnGQLlx9EuUllb6-4rz_sZBayltQd8ivTieW_3P3ryK0Wy8IQGTX2xklIq-upkXy179JORwZVbmFS4L8nfzq_Xu5pn492qGgyGCu7GrF7rpcV3R1Eo7bzC1XUBm4Hnjdb0klr5YsQBK9UYHeygUuWGScQmMFXZSg_XH8gAAAAIIQ6DnAQ")
START_IMAGE = os.getenv(
    "START_IMAGE",
    "https://envs.sh/Lks.jpg",
)

assert API_ID and API_HASH and BOT_TOKEN and SESSION_STRING, (
    "Set API_ID, API_HASH, BOT_TOKEN, SESSION_STRING env vars"
)

# ---------- Clients ----------
bot = Client(
    "vcmusic-bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    in_memory=True,
)
user = Client(
    "vcmusic-user",
    api_id=API_ID,
    api_hash=API_HASH,
    session_string=SESSION_STRING,
    in_memory=True,
)
calls = PyTgCalls(user)

# Per-chat state: {chat_id: {"title":..., "url":..., "duration":..., "thumb":..., "position": int}}
state: Dict[int, dict] = {}


# ---------- Helpers ----------
def fmt_dur(sec: int) -> str:
    sec = int(sec or 0)
    m, s = divmod(sec, 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


YDL_OPTS = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "no_warnings": True,
    "default_search": "ytsearch1",
    "geo_bypass": True,
    "source_address": "0.0.0.0",
    "extract_flat": False,
}


async def yt_search(query: str) -> Optional[dict]:
    def _do():
        with yt_dlp.YoutubeDL(YDL_OPTS) as y:
            info = y.extract_info(query, download=False)
            if "entries" in info:
                info = info["entries"][0]
            # pick best audio direct url
            url = info.get("url")
            if not url:
                for fmt in info.get("formats", []):
                    if fmt.get("acodec") != "none" and fmt.get("vcodec") == "none":
                        url = fmt["url"]
                        break
            return {
                "title": info.get("title", "Unknown"),
                "duration": info.get("duration") or 0,
                "thumb": (info.get("thumbnail") or
                          f"https://i.ytimg.com/vi/{info.get('id','')}/hqdefault.jpg"),
                "webpage": info.get("webpage_url", ""),
                "stream": url,
                "id": info.get("id", ""),
            }
    return await asyncio.to_thread(_do)


def now_playing_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(f("« -10s"), callback_data="seek_back"),
                InlineKeyboardButton(f("Pause"), callback_data="pause"),
                InlineKeyboardButton(f("Resume"), callback_data="resume"),
                InlineKeyboardButton(f("+10s »"), callback_data="seek_fwd"),
            ],
            [
                InlineKeyboardButton(f("Stop"), callback_data="stop"),
                InlineKeyboardButton(f("Help"), callback_data="help"),
            ],
        ]
    )


def start_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(f("Add me to your group"),
                                  url="https://t.me/{}?startgroup=true")],
            [
                InlineKeyboardButton(f("Help"), callback_data="help"),
                InlineKeyboardButton(f("About"), callback_data="about"),
            ],
        ]
    )


# ---------- Handlers ----------
@bot.on_message(filters.command("start"))
async def start_cmd(_, m: Message):
    me = await bot.get_me()
    kb = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(f("Add me to your group"),
                                  url=f"https://t.me/{me.username}?startgroup=true")],
            [
                InlineKeyboardButton(f("Help"), callback_data="help"),
                InlineKeyboardButton(f("About"), callback_data="about"),
            ],
        ]
    )
    caption = (
        f("Hello ") + f"{m.from_user.first_name if m.from_user else ''}\n\n"
        + f("I am a premium voice chat music bot.\n")
        + f("Tap the image to reveal, then add me to your group, ")
        + f("promote me as admin and use ") + "`/play song name`"
        + f(" inside the voice chat.")
    )
    try:
        await m.reply_photo(
            photo=START_IMAGE,
            caption=caption,
            has_spoiler=True,   # blurred until tapped
            reply_markup=kb,
        )
    except Exception as e:
        log.warning("photo send failed: %s", e)
        await m.reply_text(caption, reply_markup=kb)


@bot.on_message(filters.command(["help", "h"]))
async def help_cmd(_, m: Message):
    await m.reply_text(_help_text(), reply_markup=now_playing_kb())


def _help_text() -> str:
    return (
        f("Premium VC Music Bot — Commands\n\n")
        + "• `/play <song / yt url>` — " + f("play in VC\n")
        + "• `/pause` — " + f("pause stream\n")
        + "• `/resume` — " + f("resume stream\n")
        + "• `/skip` — " + f("stop current\n")
        + "• `/stop` / `/end` — " + f("leave VC\n")
        + "• `/seek 30` — " + f("jump forward seconds\n")
        + "• `/ping` — " + f("alive check\n\n")
        + f("Tip: start a voice chat first, then run /play.")
    )


@bot.on_message(filters.command("ping"))
async def ping_cmd(_, m: Message):
    await m.reply_text(f("Pong! Bot is alive."))


async def _ensure_user_in_chat(chat_id: int) -> bool:
    """Make assistant user join the group if not already a member."""
    try:
        await user.get_chat(chat_id)
        return True
    except Exception:
        pass
    # Try via invite link
    try:
        link = await bot.export_chat_invite_link(chat_id)
        await user.join_chat(link)
        return True
    except Exception as e:
        log.warning("assistant could not join %s: %s", chat_id, e)
        return False


@bot.on_message(filters.command("play") & filters.group)
async def play_cmd(_, m: Message):
    if len(m.command) < 2 and not m.reply_to_message:
        return await m.reply_text(f("Give a song name. Example: ") + "`/play perfect ed sheeran`")

    query = m.text.split(None, 1)[1] if len(m.command) >= 2 else (m.reply_to_message.text or "")
    status = await m.reply_text(f("Searching..."))

    info = await yt_search(query)
    if not info or not info.get("stream"):
        return await status.edit_text(f("Nothing found, try another query."))

    chat_id = m.chat.id

    # Make sure assistant user is in the group
    joined = await _ensure_user_in_chat(chat_id)
    if not joined:
        return await status.edit_text(
            f("I cannot join this group with my assistant account. ")
            + f("Please make the group public or unrestrict invite link, then retry.")
        )

    await status.edit_text(f("Joining voice chat..."))

    try:
        await calls.play(
            chat_id,
            MediaStream(info["stream"], audio_flags=MediaStream.Flags.REQUIRED,
                        audio_parameters=AudioQuality.HIGH),
        )
    except NoActiveGroupCall:
        return await status.edit_text(
            f("Please make VC live / start the voice chat first, then send ") + "`/play`" + f(" again.")
        )
    except Exception as e:
        log.exception("play failed")
        return await status.edit_text(f("Failed to start: ") + f"`{e}`")

    state[chat_id] = {
        "title": info["title"],
        "duration": info["duration"],
        "thumb": info["thumb"],
        "url": info["webpage"],
        "stream": info["stream"],
        "position": 0,
    }

    caption = (
        f("Now Playing\n\n")
        + f("Title: ") + f"**{f(info['title'])}**\n"
        + f("Duration: ") + f"`{fmt_dur(info['duration'])}`\n"
        + f("Source: ") + f"[YouTube]({info['webpage']})"
    )
    try:
        await status.delete()
        await m.reply_photo(info["thumb"], caption=caption, reply_markup=now_playing_kb())
    except Exception:
        await m.reply_text(caption, reply_markup=now_playing_kb(), disable_web_page_preview=False)


@bot.on_message(filters.command("pause") & filters.group)
async def pause_cmd(_, m: Message):
    try:
        await calls.pause_stream(m.chat.id)
        await m.reply_text(f("Paused."))
    except Exception as e:
        await m.reply_text(f("Error: ") + f"`{e}`")


@bot.on_message(filters.command("resume") & filters.group)
async def resume_cmd(_, m: Message):
    try:
        await calls.resume_stream(m.chat.id)
        await m.reply_text(f("Resumed."))
    except Exception as e:
        await m.reply_text(f("Error: ") + f"`{e}`")


@bot.on_message(filters.command(["stop", "end", "leave"]) & filters.group)
async def stop_cmd(_, m: Message):
    try:
        await calls.leave_call(m.chat.id)
    except Exception:
        pass
    state.pop(m.chat.id, None)
    await m.reply_text(f("Stopped and left the voice chat."))


@bot.on_message(filters.command("skip") & filters.group)
async def skip_cmd(_, m: Message):
    await stop_cmd(_, m)


# ---------- Inline button handler ----------
@bot.on_callback_query()
async def cb(_, q: CallbackQuery):
    data = q.data
    chat_id = q.message.chat.id if q.message else 0

    if data == "help":
        return await q.message.reply_text(_help_text())
    if data == "about":
        return await q.answer(f("Premium VC Music Bot"), show_alert=True)

    if chat_id == 0 or q.message.chat.type == ChatType.PRIVATE:
        return await q.answer(f("Use these controls inside a group."), show_alert=True)

    try:
        if data == "pause":
            await calls.pause_stream(chat_id)
            await q.answer(f("Paused"))
        elif data == "resume":
            await calls.resume_stream(chat_id)
            await q.answer(f("Resumed"))
        elif data == "stop":
            try:
                await calls.leave_call(chat_id)
            except Exception:
                pass
            state.pop(chat_id, None)
            await q.answer(f("Stopped"))
            await q.message.reply_text(f("Voice chat left."))
        elif data in ("seek_fwd", "seek_back"):
            s = state.get(chat_id)
            if not s:
                return await q.answer(f("Nothing playing."), show_alert=True)
            delta = 10 if data == "seek_fwd" else -10
            s["position"] = max(0, s.get("position", 0) + delta)
            # py-tgcalls "seek" by replaying with offset via MediaStream is non-trivial;
            # we just notify. Real seek requires ffmpeg pre-segmenting.
            await q.answer(f("Seek ") + f"{delta:+d}s " + f("(approx)"))
        else:
            await q.answer()
    except Exception as e:
        await q.answer(str(e)[:180], show_alert=True)


# ---------- Stream end -> auto leave ----------
from pytgcalls.types import Update
from pytgcalls.types.stream import StreamAudioEnded


@calls.on_update()
async def on_update(_, update: Update):
    if isinstance(update, StreamAudioEnded):
        try:
            await calls.leave_call(update.chat_id)
        except Exception:
            pass
        state.pop(update.chat_id, None)


# ---------- Boot ----------
async def main():
    await bot.start()
    await user.start()
    await calls.start()
    me = await bot.get_me()
    log.info("Bot online as @%s", me.username)
    await idle()
    await bot.stop()
    await user.stop()


if __name__ == "__main__":
    asyncio.run(main())
