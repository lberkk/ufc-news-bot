"""Videolu alıntı postlarını kopyala-yapıştır için Telegram'a gönderir."""
import os

import requests


def enabled():
    return bool(os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID"))


def send(text):
    """Gönderildiyse True, değilse False (sonraki koşuda yeniden denenir)."""
    url = f"https://api.telegram.org/bot{os.environ['TELEGRAM_BOT_TOKEN']}/sendMessage"
    body = {"chat_id": os.environ["TELEGRAM_CHAT_ID"], "text": text, "disable_web_page_preview": True}
    try:
        r = requests.post(url, json=body, timeout=15)
    except requests.RequestException as exc:
        print(f"[telegram] bağlantı hatası: {exc}")
        return False
    if r.status_code != 200:
        print(f"[telegram] HTTP {r.status_code}: {r.text[:200]}")
    return r.status_code == 200
