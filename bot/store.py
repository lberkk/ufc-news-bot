"""SQLite durumu: görülen haberler, atılan postlar, görsel özetleri."""
import difflib
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


def normalize(title):
    return re.sub(r"[^a-z0-9 ]", "", title.lower()).strip()


class Store:
    def __init__(self, path="state.db"):
        self.db = sqlite3.connect(path)
        self.db.executescript(SCHEMA)

    def seen(self, link):
        return self.db.execute("SELECT 1 FROM items WHERE link=?", (link,)).fetchone() is not None

    def similar(self, title, window_hours, threshold):
        since = time.time() - window_hours * 3600
        norm = normalize(title)
        rows = self.db.execute("SELECT norm FROM items WHERE seen_at>? AND status IN ('posted','draft')", (since,))
        return any(difflib.SequenceMatcher(None, norm, r[0]).ratio() >= threshold for r in rows)

    def record(self, item, status, post_text=None, image_hash=None, post_id=None):
        self.db.execute(
            "INSERT OR REPLACE INTO items VALUES (?,?,?,?,?,?,?,?,?,?)",
            (item["link"], item["source"], item["title"], normalize(item["title"]), time.time(),
             status, post_text, item.get("image"), image_hash, post_id),
        )
        self.db.commit()

    def published_today(self):
        """Türkiye saatiyle bugün gece yarısından beri atılan post sayısı."""
        now = datetime.now(TZ)
        since = now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        return self.db.execute(
            "SELECT COUNT(*) FROM items WHERE seen_at>? AND status='posted'", (since,)
        ).fetchone()[0]

    def last_post_time(self):
        """Son atılan postun zamanı (epoch); hiç yoksa 0."""
        row = self.db.execute("SELECT MAX(seen_at) FROM items WHERE status='posted'").fetchone()
        return row[0] or 0

    def recent_posts(self, hours=24, limit=30):
        """Son paylaşılan post metinleri, eskiden yeniye."""
        since = time.time() - hours * 3600
        rows = self.db.execute(
            "SELECT post_text FROM items WHERE seen_at>? AND status IN ('posted','draft') "
            "AND post_text IS NOT NULL ORDER BY seen_at DESC LIMIT ?", (since, limit),
        ).fetchall()
        return [" ".join(r[0].split()) for r in reversed(rows)]

    def image_hash_count(self, h):
        return self.db.execute("SELECT COUNT(*) FROM items WHERE image_hash=?", (h,)).fetchone()[0]
