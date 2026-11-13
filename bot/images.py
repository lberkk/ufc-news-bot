"""Feed görselini indirir, kontrol eder ve yüklemeye hazırlar."""
import hashlib
import io
import re

import requests
from PIL import Image

UA = {"User-Agent": "Mozilla/5.0 (compatible; ufc-news-bot/1.0)"}
MAX_BYTES = 5 * 1024 * 1024


def _og_image(page_url):
    try:
        html = requests.get(page_url, headers=UA, timeout=20).text[:200000]
    except requests.RequestException:
        return None
    for pat in (r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)',
                r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']'):
        m = re.search(pat, html)
        if m:
            return m.group(1)
    return None


def prepare(item, cfg, store):
    """(jpeg_bytes, sha256) döner; kullanılabilir görsel yoksa (None, None)."""
    if cfg.get("image_mode", "feed") != "feed" or item["source"] in cfg.get("image_blocklist", []):
        return None, None
    url = item.get("image") or _og_image(item["link"])
    if not url:
        return None, None
    item["image"] = url
    try:
        raw = requests.get(url, headers=UA, timeout=30).content
        img = Image.open(io.BytesIO(raw))
        img.load()
    except Exception as exc:
        print(f"[image] indirilemedi: {exc}")
        return None, None
    digest = hashlib.sha256(raw).hexdigest()
    if store.image_hash_count(digest) >= 3:  # site logosu / varsayılan kapak
        print("[image] tekrar eden görsel, atlandı")
        return None, None
    if img.width < cfg.get("image_min_width", 600):
        print(f"[image] çok küçük ({img.width}px), atlandı")
        return None, None
    img = img.convert("RGB")
    if img.width > 2048:
        img = img.resize((2048, round(img.height * 2048 / img.width)))
    for quality in (90, 80, 70):
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=quality)
        if buf.tell() <= MAX_BYTES:
            return buf.getvalue(), digest
    return None, None
