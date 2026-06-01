import asyncio
from logger import get_logger

log = get_logger("alerts")

_bot = None
_chat_id = None


def _init_bot():
    global _bot, _chat_id
    if _bot is not None:
        return True
    try:
        from telegram import Bot
        from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
        if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
            return False
        _bot = Bot(token=TELEGRAM_BOT_TOKEN)
        _chat_id = TELEGRAM_CHAT_ID
        return True
    except Exception as e:
        log.warning(f"Telegram init failed: {e}")
        return False


async def send_alert(message: str):
    if not _init_bot():
        log.warning(f"Telegram skipped (not configured): {message}")
        return
    try:
        await _bot.send_message(chat_id=_chat_id, text=message)
        log.info(f"Telegram alert sent: {message[:60]}")
    except Exception as e:
        log.warning(f"Telegram alert failed (non-critical): {e}")
