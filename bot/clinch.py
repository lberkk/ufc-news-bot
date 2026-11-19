"""Kabul edilen haberleri Clinch uygulamasının veritabanına gönderir."""
import json
import os
from datetime import datetime, timezone

import requests

CATEGORIES = {"Maç duyurusu": "fight_announcement", "Sakatlık": "injury", "Sonuç": "result"}


def enabled():
    return bool(os.environ.get("CLINCH_API_URL") and os.environ.get("CLINCH_API_KEY"))


def _payload(row):
    payload = {
        "source_url": row["link"],
        "source_name": row["source"],
        "ai_title_tr": row["ai_title"],
        "ai_summary_tr": row["ai_summary"],
        "ai_title_en": row["ai_title_en"],
        "ai_summary_en": row["ai_summary_en"],
        "published_at": datetime.fromtimestamp(row["published"], timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "category": CATEGORIES.get(row["category"], "general"),
        "fighter_names": json.loads(row["fighters"] or "[]"),
    }
    if row.get("image_url"):
        payload["image_url"] = row["image_url"]
    return payload


def send(row):
    """'sent', 'rejected' (400: bir daha denenmez) veya None (sonraki koşuda yeniden denenir) döner."""
    headers = {"Content-Type": "application/json", "x-api-key": os.environ["CLINCH_API_KEY"]}
    for attempt in range(2):
        try:
            r = requests.post(os.environ["CLINCH_API_URL"], headers=headers, json=_payload(row), timeout=15)
        except requests.RequestException as exc:
            print(f"[clinch] bağlantı hatası: {exc}")
            continue
        if r.status_code in (200, 201):
            return "sent"
        print(f"[clinch] HTTP {r.status_code}: {r.text[:200]}")
        if r.status_code == 400:
            return "rejected"
        if r.status_code < 500:
            return None  # 401 vb.: anahtar düzelince yeniden denenir
    return None
