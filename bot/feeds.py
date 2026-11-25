"""RSS kaynaklarını okur ve ortak bir biçime çevirir."""
import calendar
import re
import time
import html as htmllib
import requests

import feedparser

UA = "ufc-news-bot/1.0 (RSS reader)"


def _image_from_entry(entry):
    for key in ("media_content", "media_thumbnail"):
        for m in entry.get(key) or []:
            if m.get("url"):
                return htmllib.unescape(m["url"])
    for enc in entry.get("enclosures") or []:
        if (enc.get("type") or "").startswith("image") and enc.get("href"):
            return htmllib.unescape(enc["href"])
    html = entry.get("summary", "") or ""
    for c in entry.get("content") or []:
        html += c.get("value", "")
    m = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', html)
    return htmllib.unescape(m.group(1)) if m else None


def _clean(html):
    text = re.sub(r"<[^>]+>", " ", html or "")
    return re.sub(r"\s+", " ", text).strip()


def _paragraphs(html, limit=12000):
    """HTML'deki <p>/<h2-4> bloklarını paragraf paragraf (boş satırla ayrılmış) düz metne çevirir."""
    html = re.sub(r"<(script|style|nav|header|footer|figure)[^>]*>.*?</\1>", " ", html or "", flags=re.S | re.I)
    parts = re.findall(r"<(p|h[2-4])[^>]*>(.*?)</\1>", html, re.S | re.I)
    out, size = [], 0
    for _, p in parts:
        t = re.sub(r"\s+([,.;:!?])", r"\1", htmllib.unescape(_clean(p)))
        if not t or re.search(r"(?i)^(follow|subscribe|read more|related:)", t):
            continue
        if size + len(t) > limit:
            break  # paragraf sınırında kes
        out.append(t)
        size += len(t) + 2
    return "\n\n".join(out)


def fetch_all(feeds):
    """[(feed_name, [item, ...])] döner. Okunamayan feed boş liste verir."""
    out = []
    for feed in feeds:
        items = []
        try:
            parsed = feedparser.parse(feed["url"], agent=UA)
            for e in parsed.entries:
                if not e.get("link") or not e.get("title"):
                    continue
                t = e.get("published_parsed") or e.get("updated_parsed")
                items.append({
                    "source": feed["name"],
                    "title": _clean(e.title),
                    "summary": _clean(e.get("summary", ""))[:1200],
                    "link": e.link,
                    "published": calendar.timegm(t) if t else time.time(),
                    "image": _image_from_entry(e),
                    "body": _paragraphs("".join(c.get("value", "") for c in e.get("content") or [])),
                    "html": e.get("summary", "") + "".join(c.get("value", "") for c in e.get("content") or []),
                })
        except Exception as exc:  # tek feed'in hatası botu durdurmasın
            print(f"[feed] {feed['name']} okunamadı: {exc}")
        print(f"[feed] {feed['name']}: {len(items)} kayıt")
        out.append((feed["name"], items))
    return out

def fetch_article(url, limit=12000):
    """Haber sayfasının gövde metnini döner; alınamazsa boş metin."""
    try:
        page = requests.get(url, headers={"User-Agent": "Mozilla/5.0 (compatible; ufc-news-bot/1.0)"}, timeout=20).text
    except requests.RequestException as exc:
        print(f"[article] alınamadı: {exc}")
        return ""
    return _paragraphs(page, limit)
