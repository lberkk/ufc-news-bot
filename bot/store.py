"""SQLite durumu: görülen haberler, kuyruk, atılan postlar, uygulama gönderimleri."""
import difflib
import json
import re
import sqlite3
import time
from datetime import datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Istanbul")

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    link TEXT PRIMARY KEY, source TEXT, title TEXT, norm TEXT,
    seen_at REAL, status TEXT, post_text TEXT, image_url TEXT,
    image_hash TEXT, post_id TEXT
);
"""
# Sonradan eklenen sütunlar; eski state.db'ye otomatik eklenir.
NEW_COLUMNS = {
    "published": "REAL", "posted_at": "REAL", "category": "TEXT",
    "ai_title": "TEXT", "ai_summary": "TEXT", "ai_title_en": "TEXT", "ai_summary_en": "TEXT",
    "fighters": "TEXT", "app_status": "TEXT", "video_url": "TEXT", "tg_status": "TEXT",
}
# status: filtered | duplicate | skipped | queued (X sırasında) | posted | draft
ACCEPTED = "('queued','posted','draft')"


def normalize(title):
    return re.sub(r"[^a-z0-9 ]", "", title.lower()).strip()


class Store:
    def __init__(self, path="state.db"):
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        have = {r["name"] for r in self.db.execute("PRAGMA table_info(items)")}
        for name, kind in NEW_COLUMNS.items():
            if name not in have:
                self.db.execute(f"ALTER TABLE items ADD COLUMN {name} {kind}")
        self.db.commit()

    def seen(self, link):
        return self.db.execute("SELECT 1 FROM items WHERE link=?", (link,)).fetchone() is not None

    def similar(self, title, window_hours, threshold):
        since = time.time() - window_hours * 3600
        norm = normalize(title)
        rows = self.db.execute(f"SELECT norm FROM items WHERE seen_at>? AND status IN {ACCEPTED}", (since,))
        return any(difflib.SequenceMatcher(None, norm, r[0]).ratio() >= threshold for r in rows)

    def record(self, item, status, result=None):
        """Yeni haberi kaydeder. result: writer.write_post çıktısı (kabul edilen haberlerde)."""
        r = result or {}
        self.db.execute(
            "INSERT OR REPLACE INTO items (link, source, title, norm, seen_at, status, post_text, "
            "image_url, published, category, ai_title, ai_summary, ai_title_en, ai_summary_en, fighters) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (item["link"], item["source"], item["title"], normalize(item["title"]), time.time(),
             status, r.get("text"), item.get("image"), item.get("published"), r.get("category"),
             r.get("title"), r.get("summary"), r.get("title_en"), r.get("summary_en"), json.dumps(r["fighters"], ensure_ascii=False) if "fighters" in r else None),
        )
        self.db.commit()

    def mark_posted(self, link, status, image_hash, post_id):
        self.db.execute(
            "UPDATE items SET status=?, image_hash=?, post_id=?, posted_at=? WHERE link=?",
            (status, image_hash, post_id, time.time(), link),
        )
        self.db.commit()

    def set_app_status(self, link, status):
        self.db.execute("UPDATE items SET app_status=? WHERE link=?", (status, link))
        self.db.commit()

    def set_video(self, link, video_url):
        self.db.execute("UPDATE items SET video_url=? WHERE link=?", (video_url, link))
        self.db.commit()

    def video_used(self, video_url):
        return self.db.execute("SELECT 1 FROM items WHERE video_url=?", (video_url,)).fetchone() is not None

    def set_tg_status(self, link, status):
        self.db.execute("UPDATE items SET tg_status=? WHERE link=?", (status, link))
        self.db.commit()

    def tg_pending(self, limit):
        """Telegram'a gönderilmeyi bekleyen videolu haberler (eskiden yeniye)."""
        rows = self.db.execute(
            "SELECT link, post_text, video_url FROM items "
            "WHERE status='queued' AND video_url IS NOT NULL AND tg_status IS NULL "
            "ORDER BY COALESCE(published, seen_at) LIMIT ?", (limit,),
        )
        return [dict(r) for r in rows]

    def queued(self, since, newest_first):
        """X'e gönderilmeyi bekleyen haberler."""
        order = "DESC" if newest_first else "ASC"
        rows = self.db.execute(
            "SELECT link, source, title, image_url AS image, post_text, category, "
            "COALESCE(published, seen_at) AS published FROM items "
            # Videolu haberler Telegram üzerinden elle paylaşılır; bot X'e ayrıca atmaz.
            f"WHERE status='queued' AND video_url IS NULL AND COALESCE(published, seen_at)>=? ORDER BY COALESCE(published, seen_at) {order}",
            (since,),
        )
        return [dict(r) for r in rows]

    def app_pending(self, limit):
        """Uygulamaya gönderilmeyi bekleyen, alanları dolu haberler (eskiden yeniye)."""
        rows = self.db.execute(
            "SELECT link, source, image_url, category, ai_title, ai_summary, ai_title_en, ai_summary_en, fighters, "
            "COALESCE(published, seen_at) AS published FROM items "
            f"WHERE status IN {ACCEPTED} AND ai_summary_en IS NOT NULL AND app_status IS NULL "
            "ORDER BY COALESCE(published, seen_at) LIMIT ?", (limit,),
        )
        return [dict(r) for r in rows]

    def published_today(self, exclude=()):
        """Türkiye saatiyle bugün gece yarısından beri atılan post sayısı.
        exclude: sayılmayacak (başlangıç, bitiş) epoch aralıkları (örn. etkinlik pencereleri)."""
        now = datetime.now(TZ)
        since = now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        rows = self.db.execute(
            "SELECT COALESCE(posted_at, seen_at) FROM items WHERE COALESCE(posted_at, seen_at)>? AND status='posted'", (since,)
        ).fetchall()
        return sum(1 for (t,) in rows if not any(s <= t < e for s, e in exclude))

    def last_post_time(self):
        """Son atılan postun zamanı (epoch); hiç yoksa 0."""
        row = self.db.execute(
            "SELECT MAX(COALESCE(posted_at, seen_at)) FROM items WHERE status='posted'"
        ).fetchone()
        return row[0] or 0

    def recent_posts(self, hours=24, limit=30):
        """Son kabul edilen haberlerin post metinleri (X'te paylaşılmayı bekleyenler dahil), eskiden yeniye."""
        since = time.time() - hours * 3600
        rows = self.db.execute(
            f"SELECT post_text FROM items WHERE seen_at>? AND status IN {ACCEPTED} "
            "AND post_text IS NOT NULL ORDER BY seen_at DESC LIMIT ?", (since, limit),
        ).fetchall()
        return [" ".join(r[0].split()) for r in reversed(rows)]

    def image_hash_count(self, h):
        return self.db.execute("SELECT COUNT(*) FROM items WHERE image_hash=?", (h,)).fetchone()[0]
