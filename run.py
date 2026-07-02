import asyncio
import os
import logging
from dotenv import load_dotenv
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup

from downloader.youtube import YouTubeDownloader
from downloader.instagram import InstagramDownloader

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

TELEGRAM_MAX_FILE_SIZE = 50 * 1024 * 1024
pending_callbacks = {}
COOKIES_FILE = os.path.join(os.path.dirname(__file__), "cookies.txt")


async def handle_update(bot, update):
    msg = update.message
    if msg:
        chat_id = msg.chat.id
        text = msg.text or ""
        document = msg.document
        username = msg.from_user.username if msg.from_user else "unknown"

        # Handle cookies.txt file upload
        if document and document.file_name == "cookies.txt":
            await handle_cookies_upload(bot, chat_id, document)
            return

        print(f"[MSG] {username}: {text}")

        if text == "/start":
            has_cookies = os.path.exists(COOKIES_FILE)
            status = "ready" if has_cookies else "needs cookies"
            await bot.send_message(
                chat_id=chat_id,
                text=(
                    "YouTube & Instagram Downloader Bot\n\n"
                    "Send me a link and I'll download it!\n\n"
                    "Supported:\n"
                    "- YouTube videos (with quality selection)\n"
                    "- Instagram posts & reels\n\n"
                    f"Status: {status}\n\n"
                    "Send /help for more info."
                ),
            )
        elif text == "/help":
            await bot.send_message(
                chat_id=chat_id,
                text=(
                    "How to use:\n\n"
                    "1. Send a YouTube or Instagram link\n"
                    "2. For YouTube: pick a quality\n"
                    "3. Wait for the download\n"
                    "4. Get your video!\n\n"
                    "YouTube links: youtube.com/watch, youtu.be/\n"
                    "Instagram links: instagram.com/p/, instagram.com/reel/\n\n"
                    "If YouTube says 'bot detected', send a cookies.txt file."
                ),
            )
        elif YouTubeDownloader.is_youtube_url(text):
            await handle_youtube(bot, chat_id, text)
        elif InstagramDownloader.is_instagram_url(text):
            await handle_instagram(bot, chat_id, text)
        elif text:
            await bot.send_message(chat_id=chat_id, text="Unsupported link. Send a YouTube or Instagram URL.")
        return

    query = update.callback_query
    if query:
        await query.answer()
        chat_id = query.message.chat.id
        message_id = query.message.message_id
        data = query.data

        if data == "cancel":
            await bot.edit_message_text("Download cancelled.", chat_id=chat_id, message_id=message_id)
            pending_callbacks.pop(chat_id, None)
            return

        stored = pending_callbacks.get(chat_id)
        if not stored or stored["message_id"] != message_id:
            await bot.edit_message_text("Session expired.", chat_id=chat_id, message_id=message_id)
            return

        quality = data.replace("quality_", "")
        url = stored["url"]
        await bot.edit_message_text(f"Downloading in {quality}...", chat_id=chat_id, message_id=message_id)

        status_msg = await bot.send_message(chat_id=chat_id, text="Starting download...")

        def progress_cb(pct, speed):
            asyncio.create_task(_update_progress(bot, chat_id, status_msg.message_id, pct, speed))

        try:
            filepath = await YouTubeDownloader.download(url, quality, progress_cb)
            await _send_file(bot, chat_id, filepath, status_msg)
        except Exception as e:
            logger.error(f"YouTube download error: {e}")
            await bot.edit_message_text(f"Download failed: {e}", chat_id=chat_id, message_id=status_msg.message_id)

        pending_callbacks.pop(chat_id, None)


async def handle_cookies_upload(bot, chat_id, document):
    status_msg = await bot.send_message(chat_id=chat_id, text="Saving cookies...")
    try:
        file = await document.get_file()
        await file.download_to_drive(COOKIES_FILE)
        await bot.edit_message_text("Cookies saved! YouTube should work now.", chat_id=chat_id, message_id=status_msg.message_id)
        print(f"[COOKIES] Saved cookies.txt from user {chat_id}")
    except Exception as e:
        await bot.edit_message_text(f"Failed to save cookies: {e}", chat_id=chat_id, message_id=status_msg.message_id)


async def handle_youtube(bot, chat_id, url):
    status_msg = await bot.send_message(chat_id=chat_id, text="Fetching video info...")
    try:
        info = await YouTubeDownloader.get_formats(url)
        title = info["title"]
        formats = info["formats"]

        buttons = []
        for fmt in formats:
            buttons.append(InlineKeyboardButton(fmt["label"], callback_data=f"quality_{fmt['label']}"))
        buttons.append(InlineKeyboardButton("Cancel", callback_data="cancel"))
        keyboard = [buttons[i:i+3] for i in range(0, len(buttons), 3)]

        await bot.edit_message_text(
            f"Video: {title}\n\nSelect quality:",
            chat_id=chat_id, message_id=status_msg.message_id,
            reply_markup=InlineKeyboardMarkup(keyboard))
        pending_callbacks[chat_id] = {"message_id": status_msg.message_id, "url": url}
        print(f"[YOUTUBE] Sent quality options for: {title}")
    except Exception as e:
        logger.error(f"YouTube info error: {e}")
        await bot.edit_message_text(f"Error: {e}", chat_id=chat_id, message_id=status_msg.message_id)


async def handle_instagram(bot, chat_id, url):
    status_msg = await bot.send_message(chat_id=chat_id, text="Downloading Instagram content...")

    def progress_cb(pct, speed):
        asyncio.create_task(_update_progress(bot, chat_id, status_msg.message_id, pct, speed))

    try:
        files = await InstagramDownloader.download(url, progress_cb)
        await bot.edit_message_text("Uploading...", chat_id=chat_id, message_id=status_msg.message_id)
        for filepath in files:
            await _send_file(bot, chat_id, filepath, status_msg)
        print(f"[INSTAGRAM] Sent {len(files)} files")
    except Exception as e:
        logger.error(f"Instagram download error: {e}")
        await bot.edit_message_text(f"Download failed: {e}", chat_id=chat_id, message_id=status_msg.message_id)


async def _update_progress(bot, chat_id, message_id, pct, speed):
    try:
        bar_len = 20
        filled = int(bar_len * pct / 100)
        bar = "█" * filled + "░" * (bar_len - filled)
        text = f"Downloading... [{bar}] {pct:.0f}%\n{speed}"
        await bot.edit_message_text(text=text, chat_id=chat_id, message_id=message_id)
    except Exception:
        pass


async def _send_file(bot, chat_id, filepath, status_msg):
    file_size = os.path.getsize(filepath)
    if file_size > TELEGRAM_MAX_FILE_SIZE:
        await bot.edit_message_text(
            f"File too large ({file_size/1024/1024:.1f}MB). Max 50MB.",
            chat_id=chat_id, message_id=status_msg.message_id)
        os.remove(filepath)
        return

    await bot.edit_message_text("Uploading to Telegram...", chat_id=chat_id, message_id=status_msg.message_id)
    with open(filepath, "rb") as f:
        if filepath.endswith(".mp4"):
            await bot.send_video(chat_id=chat_id, video=f, read_timeout=120, write_timeout=120)
        else:
            await bot.send_document(chat_id=chat_id, document=f, read_timeout=120, write_timeout=120)
    await bot.delete_message(chat_id=chat_id, message_id=status_msg.message_id)
    os.remove(filepath)


async def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    bot = Bot(token=token)

    me = await bot.get_me()
    print(f"Bot started: @{me.username}")
    print("Waiting for messages...")

    offset = 0
    while True:
        try:
            updates = await bot.get_updates(offset=offset, timeout=10)
            for update in updates:
                offset = update.update_id + 1
                asyncio.create_task(handle_update(bot, update))
        except Exception as e:
            logger.error(f"Polling error: {e}")
            await asyncio.sleep(2)


if __name__ == "__main__":
    asyncio.run(main())
