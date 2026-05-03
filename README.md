# Premium Telegram VC Music Bot

Pyrogram + py-tgcalls based music bot with premium font, blurred (spoiler) start banner,
inline controls (Pause / Resume / -10s / +10s / Stop / Help), YouTube search via yt-dlp,
and a one-shot deploy on Render via Docker.

## 1. Get credentials

- `API_ID` & `API_HASH` — https://my.telegram.org
- `BOT_TOKEN` — @BotFather (disable privacy mode, add to your group as admin)
- `SESSION_STRING` — run locally:
  ```bash
  pip install pyrogram tgcrypto
  python gen_session.py
  ```
  Use a **second Telegram account** (not your main) — this user joins the VC.

## 2. Deploy on Render (one click)

1. Push this folder to GitHub.
2. On https://render.com → **New → Blueprint** → pick the repo (`render.yaml` auto-detected).
3. Service type is **Background Worker** + **Docker** — no build issues.
4. Set env vars: `API_ID`, `API_HASH`, `BOT_TOKEN`, `SESSION_STRING`, optional `START_IMAGE`.
5. Deploy. Logs should show `Bot online as @yourbot`.

> Why Docker? `py-tgcalls` needs `ffmpeg` and prebuilt native wheels.
> The classic Render Python build fails on `pip install` for this lib —
> Docker solves it permanently.

## 3. Use it

In your group:
1. Add the bot as **admin** (Manage Voice Chats permission).
2. Add the assistant user (the one whose `SESSION_STRING` you used) to the group.
3. Start the **Voice Chat** in the group.
4. `/play perfect ed sheeran`  →  bot joins VC and streams.

## Commands

```
/start            premium banner (spoiler image)
/play <query|url> play song in voice chat
/pause /resume    control playback
/skip /stop       leave voice chat
/ping             alive
/help             show help
```
