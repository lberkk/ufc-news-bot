"""Haberlere gömülü X postlarını bulur ve videolu olanları seçer."""
import re

import requests

LINK = re.compile(r"(?:twitter|x)\.com/([A-Za-z0-9_]{1,15})/status(?:es)?/(\d+)")
# Resmi olmayan, X'in gömülü post (embed) uç noktası; anahtar istemez.
SYNDICATION = "https://cdn.syndication.twimg.com/tweet-result"


def links(html):
    """HTML içindeki X post linkleri, sırası korunarak ve tekrarsız: [(url, id), ...]."""
    out = {}
    for user, tid in LINK.findall(html or ""):
        out.setdefault(tid, f"https://x.com/{user}/status/{tid}")
    return [(url, tid) for tid, url in out.items()]


def has_video(tweet_id):
    """True/False; uç noktaya ulaşılamazsa None."""
    try:
        r = requests.get(SYNDICATION, params={"id": tweet_id, "token": "x"}, timeout=10)
        if r.status_code != 200:
            return None
        media = r.json().get("mediaDetails") or []
    except (requests.RequestException, ValueError):
        return None
    return any(m.get("type") in ("video", "animated_gif") for m in media)


def find_video(html, only_video=True, max_checks=5):
    """Haberdeki ilk videolu X postunun linki. Video kontrolü çalışmazsa ilk link döner."""
    found = links(html)
    if found and not only_video:
        return found[0][0]
    for url, tid in found[:max_checks]:
        video = has_video(tid)
        if video is None:
            print(f"[xvideo] video kontrolü yapılamadı, ilk link kullanılıyor: {found[0][0]}")
            return found[0][0]
        if video:
            return url
    return None
