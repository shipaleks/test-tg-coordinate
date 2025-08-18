#!/usr/bin/env python3
"""
Script to upload media files to Telegram and get their file_ids.
Run this locally, then use the file_ids as environment variables on Railway.
"""

import asyncio
import os
import sys
from pathlib import Path
from telegram import Bot
from telegram.error import TelegramError

async def upload_media():
    """Upload media files and print their file_ids."""
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        print("Error: TELEGRAM_BOT_TOKEN environment variable is required")
        sys.exit(1)
    
    # Get your chat ID (you can get it by messaging the bot and checking updates)
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not chat_id:
        print("Error: TELEGRAM_CHAT_ID environment variable is required")
        print("You can get it by messaging your bot and running:")
        print("curl https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates")
        sys.exit(1)
    
    bot = Bot(token=bot_token)
    
    # Files to upload
    files = [
        ("docs/howtobot_hd.mp4", "video"),
        ("docs/howtobot.mp4", "video"),
        ("docs/IMG_9249.PNG", "photo"),
        ("docs/IMG_9248.PNG", "photo"),
        ("docs/IMG_9247.PNG", "photo"),
    ]
    
    print("Uploading media files to Telegram...\n")
    
    for file_path, media_type in files:
        path = Path(file_path)
        if not path.exists():
            print(f"❌ File not found: {file_path}")
            continue
        
        try:
            with open(path, "rb") as f:
                if media_type == "video":
                    message = await bot.send_video(chat_id=chat_id, video=f)
                    file_id = message.video.file_id
                elif media_type == "animation":
                    message = await bot.send_animation(chat_id=chat_id, animation=f)
                    file_id = message.animation.file_id
                elif media_type == "photo":
                    message = await bot.send_photo(chat_id=chat_id, photo=f)
                    # Get the largest photo size
                    file_id = message.photo[-1].file_id
                
                print(f"✅ {file_path}:")
                print(f"   File ID: {file_id}")
                print(f"   Type: {media_type}")
                print()
                
        except TelegramError as e:
            print(f"❌ Failed to upload {file_path}: {e}")
    
    print("\nAdd these to your Railway environment variables:")
    print("HOWTO_VIDEO_FILE_ID=<file_id from howtobot_hd.mp4 (or howtobot.mp4)>")
    print("HOWTO_STEP1_FILE_ID=<file_id from IMG_9249.PNG>")
    print("HOWTO_STEP2_FILE_ID=<file_id from IMG_9248.PNG>")
    print("HOWTO_STEP3_FILE_ID=<file_id from IMG_9247.PNG>")

if __name__ == "__main__":
    asyncio.run(upload_media())
