"""SQLite durumu: görülen haberler, atılan postlar, görsel özetleri."""
import difflib
import re
import sqlite3
import time

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

    def published_last_24h(self):
        since = time.time() - 24 * 3600
        return self.db.execute(
            "SELECT COUNT(*) FROM items WHERE seen_at>? AND status IN ('posted','draft')", (since,)
        ).fetchone()[0]

    def image_hash_count(self, h):
        return self.db.execute("SELECT COUNT(*) FROM items WHERE image_hash=?", (h,)).fetchone()[0]
