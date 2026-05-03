"""Run locally:  python gen_session.py
Generates a Pyrogram v2 SESSION_STRING for the assistant user account that joins VC."""
from pyrogram import Client

api_id = int(input("API_ID: ").strip())
api_hash = input("API_HASH: ").strip()

with Client("gen", api_id=api_id, api_hash=api_hash, in_memory=True) as app:
    print("\nSESSION_STRING =\n")
    print(app.export_session_string())
